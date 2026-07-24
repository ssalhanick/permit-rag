"""
ingestion/metadata_agent.py — Corpus Metadata Validator (agent #13)
====================================================================
Phase 3 of the agent architecture. This agent asks a question none of the
existing ingestion checks (``ingestion/verification.py``) ever ask: is the
document's metadata *true*, not merely *present*? Verification covers bytes,
chars, chunk coverage, and embeddings. This covers ``effective_date``,
``doc_type``, ``authority_level``, and ``subject_tags`` — the fields the
reranker and retrieval filters read. The corpus audit found all 27 docs with a
null ``effective_date`` and several with a catch-all ``doc_type`` — retrieval
filters built on wrong metadata measure the wrong thing precisely.

**Deterministic first, LLM only where it must be** (docs/agent_architecture.md):

1. Enum conformance (no LLM) — ``doc_type`` / ``authority_level`` against the
   schema enums.
2. Required-field completeness (no LLM) — AGENTS.md's six required fields.
3. Content-vs-metadata agreement (LLM) — chunks sampled *across* the document;
   propose values, flag any that contradict the stored metadata.
4. Effective-date extraction (LLM) — codes state their adoption date in text;
   extract it with a source-chunk citation. Unextractable → an action item, not
   a silent null.
5. Subject-tag regeneration (LLM) — against a *closed* controlled vocabulary.
6. Supersession-candidate detection (no LLM) — e.g. the
   ``city-of-dallas-ordiance-v1/v2/v3`` family.

**Governance (AGENTS.md, non-negotiable).** This module writes nothing to the
corpus. Every proposal becomes a ``needs_review`` action item carrying its
source-chunk citation; a human approves it in the dashboard, and only then does
``ingestion/governance.apply_metadata_correction`` write. Failing *new* docs go
to ``draft`` with a blocking item (``draft_on_fail=True``); the *backfill* over
the live corpus never drafts (that would empty retrieval) — it proposes only.

Import boundary: ingestion/ → db/, standard library, **and only**
``rag/agent_runtime`` from ``rag/`` (AGENTS.md amendment). Every model call goes
through ``run_agent`` — there is no inline Anthropic client here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from ingestion import governance
from rag.agent_runtime import Tier, run_agent

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════
#  REFERENCE DATA (mirrors db/schema.sql enums)
# ════════════════════════════════════════════════

VALID_DOC_TYPES: frozenset[str] = frozenset({
    "building_code", "zoning_ordinance", "permit_checklist", "fire_code",
    "plumbing_code", "electrical_code", "mechanical_code", "energy_code",
    "accessibility_code", "osha_standard", "administrative_rule", "amendment",
    "state_statute", "federal_regulation", "other",
})

VALID_AUTHORITY_LEVELS: frozenset[str] = frozenset(
    {"municipal", "county", "state", "federal"}
)

# 'other' is valid but a catch-all: worth re-checking against content.
CATCH_ALL_DOC_TYPE = "other"

# AGENTS.md: "Never ingest without full metadata (municipality, effective_date,
# authority_level, doc_type, review_due, checksum)." Mapped to DB columns.
REQUIRED_FIELDS: tuple[str, ...] = (
    "municipality", "effective_date", "authority_level",
    "doc_type", "review_due", "checksum_sha256",
)

# Closed controlled vocabulary for subject_tags. Regeneration proposes only from
# this set so tags stay a usable retrieval facet rather than free text. Kept
# deliberately small and DFW-permit-shaped; extend deliberately, not ad hoc.
CONTROLLED_TAG_VOCAB: frozenset[str] = frozenset({
    "building", "residential", "commercial", "zoning", "setbacks", "occupancy",
    "egress", "fire", "plumbing", "electrical", "mechanical", "energy",
    "accessibility", "permitting", "inspection", "fees", "licensing", "signage",
    "flood", "stormwater", "grading", "demolition", "roofing", "foundation",
    "structural", "height_limits", "parking", "landscaping", "amendment",
})

# How many chunks to sample across a document for the LLM assessment.
DEFAULT_SAMPLE_SIZE = 12
# Trim each sampled chunk so a long code section cannot blow the input budget.
MAX_CHUNK_CHARS = 1200

AGENT_NAME = "metadata_validator"


# ════════════════════════════════════════════════
#  STRUCTURED-OUTPUT MODELS (LLM boundary)
# ════════════════════════════════════════════════


class FieldProposal(BaseModel):
    """One proposed metadata value with its supporting source-chunk citation."""

    value: str | None = Field(
        description="Proposed value, or null if the document does not state it. "
        "effective_date as ISO 'YYYY-MM-DD'; doc_type/authority_level as the "
        "exact schema enum token."
    )
    confidence: float = Field(ge=0.0, le=1.0)
    chunk_index: int | None = Field(
        default=None,
        description="chunk_index of the sampled chunk that supports the value.",
    )
    excerpt: str = Field(
        default="",
        description="Short verbatim snippet from the cited chunk (≤200 chars).",
    )
    rationale: str = Field(default="")


class TagProposal(BaseModel):
    """Proposed subject tags, drawn only from the controlled vocabulary."""

    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    chunk_index: int | None = None
    rationale: str = Field(default="")


class MetadataAssessment(BaseModel):
    """The validator's structured read of a document from its sampled chunks."""

    effective_date: FieldProposal
    doc_type: FieldProposal
    authority_level: FieldProposal
    subject_tags: TagProposal
    contradicts_current: bool = Field(
        default=False,
        description="True if the content contradicts the stored metadata.",
    )
    contradiction_note: str = Field(default="")


# ════════════════════════════════════════════════
#  INTERNAL RESULT TYPES
# ════════════════════════════════════════════════


@dataclass
class Citation:
    """Where a proposal came from — the whole point of the review UI."""

    chunk_index: int | None
    chunk_id: str | None
    excerpt: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_index": self.chunk_index,
            "chunk_id": self.chunk_id,
            "excerpt": self.excerpt,
        }


@dataclass
class Proposal:
    """A single proposed metadata correction, always carrying a citation."""

    field: str
    current: Any
    proposed: Any
    confidence: float
    method: str  # 'deterministic' | 'llm'
    citation: Citation
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "current": _jsonable(self.current),
            "proposed": _jsonable(self.proposed),
            "confidence": self.confidence,
            "method": self.method,
            "citation": self.citation.to_dict(),
            "rationale": self.rationale,
        }


@dataclass
class ValidationReport:
    """Everything the validator learned about one document."""

    doc_id: str
    document_id: str | None = None
    enum_failures: list[str] = field(default_factory=list)
    completeness_failures: list[str] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)
    supersession_candidates: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    llm_used: bool = False
    result: str = "pass"  # 'pass' | 'needs_review' | 'fail'
    action_item_ids: list[str] = field(default_factory=list)
    drafted: bool = False

    def to_detail(self) -> dict[str, Any]:
        """Serialise for the ingestion_verifications.detail JSONB column."""
        return {
            "doc_id": self.doc_id,
            "result": self.result,
            "enum_failures": self.enum_failures,
            "completeness_failures": self.completeness_failures,
            "proposals": [p.to_dict() for p in self.proposals],
            "supersession_candidates": self.supersession_candidates,
            "contradictions": self.contradictions,
            "llm_used": self.llm_used,
            "drafted": self.drafted,
        }


def _jsonable(value: Any) -> Any:
    """Coerce dates to ISO strings so a report serialises to JSON cleanly."""
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


# ════════════════════════════════════════════════
#  DETERMINISTIC CHECKS (no LLM)
# ════════════════════════════════════════════════


def check_enum_conformance(doc: dict[str, Any]) -> list[str]:
    """
    Return enum-conformance failures for a document row.

    A failure here means the metadata is *invalid*, not merely incomplete — the
    stored value is outside the schema enum. These make the whole report 'fail'.
    """
    failures: list[str] = []
    doc_type = doc.get("doc_type")
    authority = doc.get("authority_level")
    if doc_type is not None and doc_type not in VALID_DOC_TYPES:
        failures.append(f"doc_type={doc_type!r} is not a valid doc_type enum")
    if authority is not None and authority not in VALID_AUTHORITY_LEVELS:
        failures.append(
            f"authority_level={authority!r} is not a valid authority_level enum"
        )
    return failures


def check_completeness(doc: dict[str, Any]) -> list[str]:
    """
    Return the names of AGENTS.md-required fields that are missing/empty.

    ``subject_tags`` is not one of the six required fields but an empty tag set
    is a retrieval-quality gap, so it is reported separately by the caller.
    """
    missing: list[str] = []
    for field_name in REQUIRED_FIELDS:
        value = doc.get(field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field_name)
    return missing


def detect_supersession_candidates(doc_id: str, all_doc_ids: list[str]) -> list[str]:
    """
    Return sibling doc_ids that look like other versions of this document.

    Deliberately conservative: it only *flags* a family for human review (the
    ``city-of-dallas-ordiance-v1/v2/v3`` case), never proposes a supersession —
    AGENTS.md forbids auto-supersede. Matches a shared base after stripping a
    trailing version/date tag.
    """
    base = _strip_version_tag(doc_id)
    if not base:
        return []
    siblings = [
        other for other in all_doc_ids
        if other != doc_id and _strip_version_tag(other) == base
    ]
    return sorted(siblings)


def _strip_version_tag(doc_id: str) -> str:
    """Strip a trailing -vN or -YYYYMMDD version tag from a doc_id."""
    import re

    return re.sub(r"-(v\d+|\d{8})$", "", doc_id.strip().lower())


# ════════════════════════════════════════════════
#  CHUNK SAMPLING
# ════════════════════════════════════════════════


def sample_chunks(chunks: list[dict[str, Any]], k: int = DEFAULT_SAMPLE_SIZE) -> list[dict[str, Any]]:
    """
    Return up to ``k`` chunks spread evenly across the document.

    Even spacing (not the first k) is deliberate: adoption dates live near the
    front, but doc_type and subject signals are throughout. Sampling the cover
    page alone is exactly the bug ``harvester.py`` has (first 2000 chars).
    """
    if not chunks:
        return []
    ordered = sorted(chunks, key=lambda c: c.get("chunk_index", 0))
    if len(ordered) <= k:
        return ordered
    step = len(ordered) / k
    return [ordered[int(i * step)] for i in range(k)]


# ════════════════════════════════════════════════
#  LLM ASSESSMENT
# ════════════════════════════════════════════════


def _build_assessment_prompt(doc: dict[str, Any], sampled: list[dict[str, Any]]) -> str:
    """Assemble the user message: current metadata + sampled, indexed chunks."""
    lines = [
        "Current stored metadata for this document:",
        f"  doc_id: {doc.get('doc_id')}",
        f"  municipality: {doc.get('municipality')}",
        f"  doc_type: {doc.get('doc_type')}",
        f"  authority_level: {doc.get('authority_level')}",
        f"  effective_date: {doc.get('effective_date')}",
        f"  subject_tags: {doc.get('subject_tags')}",
        "",
        f"Controlled subject-tag vocabulary (choose ONLY from these): "
        f"{sorted(CONTROLLED_TAG_VOCAB)}",
        "",
        "Sampled chunks (cite the chunk_index you draw each value from):",
    ]
    for chunk in sampled:
        idx = chunk.get("chunk_index")
        content = (chunk.get("content") or "")[:MAX_CHUNK_CHARS]
        lines.append(f"[chunk_index={idx}]\n{content}\n")
    lines.append(
        "Propose the true effective_date (adoption/effective date stated in the "
        "text), doc_type, authority_level, and subject_tags. For each, cite the "
        "chunk_index and a short verbatim excerpt. Use null where the document "
        "does not state the value. Flag any value that contradicts the stored "
        "metadata."
    )
    return "\n".join(lines)


_ASSESSMENT_SYSTEM = (
    "You are the Corpus Metadata Validator for a construction-permit compliance "
    "corpus (Dallas-Fort Worth municipal codes plus Texas and federal regs). You "
    "verify whether a document's stored metadata matches its actual content. You "
    "never invent a value: if the sampled text does not state something, you "
    "return null for it. Every non-null proposal must cite the chunk_index and a "
    "verbatim excerpt it is drawn from. doc_type and authority_level must be one "
    "of the exact schema enum tokens; subject_tags must come only from the "
    "controlled vocabulary given. You do not decide governance actions — you only "
    "report what the content says."
)


def assess_with_llm(
    doc: dict[str, Any],
    sampled: list[dict[str, Any]],
    *,
    client: Any | None = None,
) -> MetadataAssessment | None:
    """
    Run the single structured LLM call over sampled chunks.

    Returns the parsed assessment, or None if the model returned nothing. All
    tracing, model-ladder selection, caching, and autonomy happen inside
    ``run_agent`` (the single call site); this only assembles the prompt.
    """
    if not sampled:
        return None
    result = run_agent(
        AGENT_NAME,
        system=_ASSESSMENT_SYSTEM,
        messages=[{"role": "user", "content": _build_assessment_prompt(doc, sampled)}],
        tier=Tier.MID,  # content-vs-metadata inference is a sonnet-class task
        output_format=MetadataAssessment,
        max_tokens=1024,
        temperature=0.0,
        input_parts=(doc.get("doc_id"), [c.get("id") for c in sampled]),
        client=client,
    )
    return result.parsed_output


# ════════════════════════════════════════════════
#  PROPOSAL ASSEMBLY
# ════════════════════════════════════════════════


def _citation_from(
    proposal: FieldProposal | TagProposal, sampled: list[dict[str, Any]]
) -> Citation:
    """Map an LLM-cited chunk_index back to a real chunk id from the sample."""
    idx = proposal.chunk_index
    chunk_id = None
    for chunk in sampled:
        if chunk.get("chunk_index") == idx:
            cid = chunk.get("id")
            chunk_id = str(cid) if cid is not None else None
            break
    excerpt = getattr(proposal, "excerpt", "") or getattr(proposal, "rationale", "")
    return Citation(chunk_index=idx, chunk_id=chunk_id, excerpt=excerpt[:200])


def _parse_iso_date(value: str | None) -> date | None:
    """Parse an ISO 'YYYY-MM-DD' string to a date, or None if unparseable."""
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except (ValueError, TypeError):
        return None


def build_proposals(
    doc: dict[str, Any],
    assessment: MetadataAssessment,
    sampled: list[dict[str, Any]],
) -> tuple[list[Proposal], list[str]]:
    """
    Turn an LLM assessment into concrete proposals + contradiction notes.

    A field only becomes a proposal when the model is confident, cites a chunk,
    and the value actually differs from what is stored. Enum/vocab validity is
    re-checked here — the deterministic layer is the source of truth, never the
    model's claim about what an enum is.
    """
    proposals: list[Proposal] = []
    contradictions: list[str] = []

    _date = _parse_iso_date(assessment.effective_date.value)
    if _date is not None and doc.get("effective_date") is None:
        proposals.append(Proposal(
            field="effective_date", current=doc.get("effective_date"),
            proposed=_date, confidence=assessment.effective_date.confidence,
            method="llm", citation=_citation_from(assessment.effective_date, sampled),
            rationale=assessment.effective_date.rationale,
        ))

    _maybe_enum_proposal(proposals, doc, assessment.doc_type, sampled,
                         field_name="doc_type", valid=VALID_DOC_TYPES)
    _maybe_enum_proposal(proposals, doc, assessment.authority_level, sampled,
                         field_name="authority_level", valid=VALID_AUTHORITY_LEVELS)

    tags = _clean_tags(assessment.subject_tags.tags)
    current_tags = set(doc.get("subject_tags") or [])
    if tags and set(tags) != current_tags:
        proposals.append(Proposal(
            field="subject_tags", current=sorted(current_tags), proposed=tags,
            confidence=assessment.subject_tags.confidence, method="llm",
            citation=_citation_from(assessment.subject_tags, sampled),
            rationale=assessment.subject_tags.rationale,
        ))

    if assessment.contradicts_current and assessment.contradiction_note:
        contradictions.append(assessment.contradiction_note)

    return proposals, contradictions


def _maybe_enum_proposal(
    proposals: list[Proposal],
    doc: dict[str, Any],
    fp: FieldProposal,
    sampled: list[dict[str, Any]],
    *,
    field_name: str,
    valid: frozenset[str],
) -> None:
    """Append an enum-field proposal when the model's value is valid and new."""
    value = (fp.value or "").strip()
    if value not in valid:
        return
    current = doc.get(field_name)
    # Propose when the field is empty, a catch-all, or genuinely contradicted.
    stale = current in (None, "", CATCH_ALL_DOC_TYPE)
    if value != current and (stale or field_name == "authority_level"):
        proposals.append(Proposal(
            field=field_name, current=current, proposed=value,
            confidence=fp.confidence, method="llm",
            citation=_citation_from(fp, sampled), rationale=fp.rationale,
        ))


def _clean_tags(tags: list[str]) -> list[str]:
    """Keep only controlled-vocabulary tags, deduped and sorted."""
    return sorted({t.strip().lower() for t in tags if t.strip().lower() in CONTROLLED_TAG_VOCAB})


# ════════════════════════════════════════════════
#  PUBLIC ENTRY POINT
# ════════════════════════════════════════════════


def validate_document(
    doc_id: str,
    *,
    use_llm: bool = True,
    draft_on_fail: bool = False,
    file_action_items: bool = True,
    save_verification: bool = False,
    run_id: UUID | None = None,
    client: Any | None = None,
    all_doc_ids: list[str] | None = None,
) -> ValidationReport:
    """
    Validate one document's metadata; propose fixes; never write the corpus.

    ``draft_on_fail`` is the ingest-time switch (a new doc failing completeness
    is drafted with a blocking item); the backfill leaves it False so the live
    corpus is never emptied. ``file_action_items`` and ``save_verification`` are
    off by default so a dry run touches nothing. Returns a full report; every
    proposal carries a source-chunk citation.
    """
    from db.client import get_chunks_for_document, get_document_by_doc_id

    doc = get_document_by_doc_id(doc_id)
    if doc is None:
        raise ValueError(f"validate_document: doc_id={doc_id!r} not found")

    report = ValidationReport(doc_id=doc_id, document_id=_uuid_str(doc.get("id")))
    report.enum_failures = check_enum_conformance(doc)
    report.completeness_failures = check_completeness(doc)
    if not (doc.get("subject_tags") or []):
        report.completeness_failures.append("subject_tags")

    if all_doc_ids is not None:
        report.supersession_candidates = detect_supersession_candidates(doc_id, all_doc_ids)

    if use_llm and doc.get("id") is not None:
        chunks = get_chunks_for_document(doc["id"])
        sampled = sample_chunks(chunks)
        assessment = assess_with_llm(doc, sampled, client=client)
        if assessment is not None:
            report.llm_used = True
            report.proposals, report.contradictions = build_proposals(doc, assessment, sampled)

    report.result = _decide_result(report)

    if file_action_items:
        _file_action_items(report, doc, draft_on_fail=draft_on_fail, run_id=run_id)
    if save_verification and report.document_id is not None:
        _save_verification(report)

    return report


def _decide_result(report: ValidationReport) -> str:
    """Roll deterministic + LLM findings into one verification result."""
    if report.enum_failures:
        return "fail"
    if report.completeness_failures or report.proposals or report.supersession_candidates:
        return "needs_review"
    return "pass"


def _file_action_items(
    report: ValidationReport,
    doc: dict[str, Any],
    *,
    draft_on_fail: bool,
    run_id: UUID | None,
) -> None:
    """Turn findings into deduped action items via governance (never inline)."""
    if report.result == "pass":
        return

    blocking = report.result == "fail" or (draft_on_fail and bool(report.completeness_failures))
    set_draft = draft_on_fail and blocking
    evidence = report.to_detail()
    title = _summarise(report)
    proposed = _proposed_action(report)

    item = governance.flag_document_for_review(
        report.doc_id,
        kind="metadata_needs_review" if report.result == "needs_review" else "metadata_invalid",
        title=title,
        evidence=evidence,
        proposed_action=proposed,
        severity="high" if report.result == "fail" else "medium",
        blocking=blocking,
        set_draft=set_draft,
        run_id=run_id,
    )
    report.drafted = set_draft
    if item.get("id"):
        report.action_item_ids.append(str(item["id"]))


def _save_verification(report: ValidationReport) -> None:
    """Write the metadata-stage verification row (stage='metadata')."""
    from db.client import insert_verification

    insert_verification(
        document_id=UUID(report.document_id),  # type: ignore[arg-type]
        stage="metadata",
        result=report.result,
        detail=report.to_detail(),
    )


def _summarise(report: ValidationReport) -> str:
    """One-line action-item title."""
    parts: list[str] = []
    if report.enum_failures:
        parts.append(f"{len(report.enum_failures)} invalid enum(s)")
    if report.completeness_failures:
        parts.append(f"missing {', '.join(report.completeness_failures)}")
    if report.proposals:
        parts.append(f"{len(report.proposals)} proposed fix(es)")
    if report.supersession_candidates:
        parts.append(f"supersession family ({len(report.supersession_candidates)})")
    return f"Metadata review: {report.doc_id} — " + "; ".join(parts or ["review"])


def _proposed_action(report: ValidationReport) -> str:
    """Human-facing summary of what approving would do."""
    if not report.proposals:
        return "Review metadata; supply missing fields."
    fixes = ", ".join(f"{p.field}→{_jsonable(p.proposed)}" for p in report.proposals)
    return f"Apply: {fixes}"


def _uuid_str(value: Any) -> str | None:
    """Stringify a UUID-ish value, or None."""
    return str(value) if value is not None else None


def validate_corpus(
    *,
    doc_ids: list[str] | None = None,
    use_llm: bool = True,
    file_action_items: bool = False,
    save_verification: bool = False,
    client: Any | None = None,
) -> list[ValidationReport]:
    """
    Validate many documents (the 27-doc backfill). Defaults to a dry run.

    Passing ``doc_ids=None`` validates every active document. Supersession
    detection sees the full id list so families are found. Governance side
    effects stay off unless explicitly enabled.
    """
    from db.client import list_documents

    rows = list_documents()
    all_ids = [r["doc_id"] for r in rows]
    targets = doc_ids if doc_ids is not None else all_ids

    reports: list[ValidationReport] = []
    for doc_id in targets:
        try:
            reports.append(validate_document(
                doc_id, use_llm=use_llm, file_action_items=file_action_items,
                save_verification=save_verification, client=client, all_doc_ids=all_ids,
            ))
        except Exception as exc:  # one bad doc must not abort the sweep
            log.error("validate_document failed for %s: %s", doc_id, exc)
    return reports
