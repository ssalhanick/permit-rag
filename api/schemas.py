"""
api/schemas.py — Pydantic models for request/response schemas
==============================================================
All API request and response bodies are defined here.
Keeps route files thin and enables OpenAPI schema generation.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

DocumentStatusType = Literal["active", "superseded", "repealed", "needs_ocr", "draft", "rejected"]
DocumentVisibilityType = Literal["private", "team"]  # migration 040, tier-3 only
AuthorityLevelType = Literal["municipal", "county", "state", "federal"]
DocTypeType = Literal[
    "building_code",
    "zoning_ordinance",
    "permit_checklist",
    "fire_code",
    "plumbing_code",
    "electrical_code",
    "mechanical_code",
    "energy_code",
    "accessibility_code",
    "osha_standard",
    "administrative_rule",
    "amendment",
    "state_statute",
    "federal_regulation",
    "other",
]


# ── Request models ───────────────────────────────────────────


class QueryRequest(BaseModel):
    """Body for POST /query — maps to rag.retriever.retrieve() args."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Natural-language question about permit/code compliance.",
        json_schema_extra={"examples": ["What are the setback requirements for a residential fence in Dallas?"]},
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of chunks to retrieve.",
    )
    municipality: str | None = Field(
        default=None,
        description="Optional municipality filter (e.g. 'dallas', 'plano'). "
                    "If omitted and 'address' is provided, the municipality is "
                    "auto-resolved via geocoding.",
    )
    address: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "Optional civic address (e.g. '1234 Main St, Dallas, TX 75201'). "
            "When provided and 'municipality' is not set, the API geocodes the "
            "address via the Census Bureau API and resolves the municipality via "
            "PostGIS point-in-polygon. 'municipality' takes precedence if both "
            "are supplied."
        ),
    )
    min_similarity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Discard results below this cosine similarity.",
    )
    project_id: str | None = Field(
        default=None,
        description="Optional project identifier to bind this query context to in logs and LangSmith.",
    )
    chunk_ids: list[str] | None = Field(
        default=None,
        description="Optional pre-retrieved chunk UUIDs from on-device search (mobile tier).",
    )


# ── Response models ──────────────────────────────────────────


class ChunkResponse(BaseModel):
    """A single retrieved chunk with metadata."""

    id: UUID = Field(description="Chunk primary key.")
    document_id: UUID = Field(description="Parent document UUID.")
    doc_id: str = Field(description="Human-readable document identifier.")
    chunk_index: int = Field(description="Position within the document.")
    content: str = Field(description="Chunk text content.")
    municipality: str = Field(description="Source municipality.")
    authority_level: str = Field(description="Authority level (municipal/state/federal).")
    doc_type: str = Field(description="Document type.")
    document_status: str = Field(description="Document status (active/superseded/repealed).")
    source_tier: int = Field(default=1, description="Source tier: 1=corpus, 2=user ordinance upload, 3=project doc.")
    # Sprint 2 reranker fields
    similarity: float = Field(description="Raw cosine similarity to the query (0-1). Same as raw_similarity.")
    raw_similarity: float = Field(default=0.0, description="Raw cosine similarity from pgvector before provenance reranking.")
    reranked_score: float = Field(default=0.0, description="Final score after provenance weighting (raw_similarity x provenance_weight).")
    provenance_weight: float = Field(default=1.0, description="Provenance multiplier (retrieval_weight x tier_factor).")
    filtered_out: bool = Field(default=False, description="True if filtered by reranker threshold. Shown greyed-out in UI.")


class DiagnosticsResponse(BaseModel):
    """Retrieval diagnostics for monitoring and evaluation."""

    top_similarity: float = Field(description="Highest similarity score.")
    mean_similarity: float = Field(description="Average similarity across returned chunks.")
    unique_doc_count: int = Field(description="Number of distinct source documents.")
    unique_doc_ids: list[str] = Field(description="List of distinct doc_id values.")


class QueryResponse(BaseModel):
    """Response for POST /query — ranked chunks with metadata."""

    query: str = Field(description="Original query string.")
    top_k: int = Field(description="Requested top_k.")
    municipality: str | None = Field(description="Applied municipality filter.")
    num_results: int = Field(description="Number of chunks returned.")
    latency_ms: int = Field(description="End-to-end retrieval latency in milliseconds.")
    model: str = Field(description="Embedding model used.")
    chunks: list[ChunkResponse] = Field(description="Ranked chunks (descending similarity).")
    diagnostics: DiagnosticsResponse = Field(description="Retrieval quality diagnostics.")


class HealthResponse(BaseModel):
    """Response for GET /health."""

    status: str = Field(description="Service status: 'healthy' or 'unhealthy'.")
    database: bool = Field(description="True if the database is reachable.")
    version: str = Field(description="API version string.")
    # Sprint 7 — Task 16D: graph layer health (additive, non-load-bearing)
    graph_health: bool = Field(
        default=False,
        description=(
            "True if Neo4j is reachable via Bolt. "
            "False does not affect overall 'status' — graph is additive, "
            "not required for the RAG retrieval path."
        ),
    )


class AHJDisclaimer(BaseModel):
    """Authority Having Jurisdiction disclaimer attached to generated answers."""

    text: str = Field(
        description=(
            "Disclaimer text reminding the user that this tool surfaces the written "
            "ordinance and that the AHJ (city building department) has final authority."
        )
    )
    learn_more_url: str | None = Field(
        default=None,
        description="URL to the building department's permit portal for the resolved jurisdiction.",
    )


class ConflictWarning(BaseModel):
    """
    Lightweight conflict signal surfaced when retrieved chunks from different
    authority levels appear to state contradictory requirements for the same
    subject (Sprint 5 / Task 15 — scoped version).
    """

    subject: str = Field(
        description="Subject keyword or phrase where the conflict was detected."
    )
    chunk_a_doc_id: str = Field(description="doc_id of the first conflicting chunk.")
    chunk_a_index: int = Field(description="chunk_index of the first conflicting chunk.")
    chunk_a_authority: str = Field(description="Authority level of the first chunk.")
    chunk_b_doc_id: str = Field(description="doc_id of the second conflicting chunk.")
    chunk_b_index: int = Field(description="chunk_index of the second conflicting chunk.")
    chunk_b_authority: str = Field(description="Authority level of the second chunk.")
    detail: str = Field(
        description="Human-readable explanation of the detected conflict."
    )


class CitationResponse(BaseModel):
    """A single citation extracted from the generated answer."""

    doc_id: str = Field(description="Human-readable document identifier.")
    chunk_index: int = Field(description="Chunk position within the document.")
    found_in_context: bool = Field(description="True if citation matched a retrieved chunk.")
    municipality: str | None = Field(description="Source municipality.")
    authority_level: str | None = Field(description="Authority level of cited source.")


class SubAnswerResponse(BaseModel):
    """
    One sub-question's own answer from a fanned-out compound query.

    Item 3 (compound-answer structuring): a compound question like "what are
    the setback and height requirements, and do I need an electrical permit?"
    is graded and generated per sub-question instead of once over a merged
    chunk pool, so each part's citations are attributable and a part can
    abstain independently instead of the whole query being all-or-nothing.
    Populated only for a genuinely fanned-out compound query — empty
    ``AnswerResponse.sub_answers`` means either a simple query or a compound
    query whose fan-out fell back to the single-answer path.
    """

    question: str = Field(description="This sub-question's own text.")
    municipality: str | None = Field(
        default=None, description="Jurisdiction this sub-question resolved to."
    )
    abstained: bool = Field(
        default=False,
        description="True when this part alone couldn't be answered — the other parts may still.",
    )
    answer: str | None = Field(
        default=None, description="This part's generated answer text. Null when abstained."
    )
    abstain_message: str | None = Field(
        default=None, description="Conversational explanation when this part abstained."
    )
    citations: list[CitationResponse] = Field(
        default_factory=list, description="Citations for this part only, never another part's."
    )
    unsupported_citations: list[str] = Field(
        default_factory=list,
        description="This part's own fabricated-citation sentences, not the whole answer's.",
    )


class MediaRefResponse(BaseModel):
    """A sourced how-to video link (Media Curator, agent #17)."""

    title: str = Field(description="Video title.")
    url: str = Field(description="Vetted video URL (youtube.com only).")
    provider: str = Field(default="youtube", description="Source provider.")
    jurisdiction: str | None = Field(
        default=None,
        description="Municipality the link is specific to, or null for a national how-to.",
    )
    relevance_note: str | None = Field(
        default=None, description="Why this video is relevant to the task."
    )


class ClarifyingOption(BaseModel):
    """Interactive multiple-choice option for clarifying low-confidence or broad queries."""

    label: str = Field(description="The question or clarification category.")
    choices: list[str] = Field(description="List of clickable option choices.")


class AnswerResponse(BaseModel):
    """Response for POST /query/answer — generated answer with citations."""

    query: str = Field(description="Original query string.")
    answer: str = Field(description="Claude-generated answer text with inline citations.")
    citations: list[CitationResponse] = Field(description="Structured citations extracted from the answer.")
    model: str = Field(description="LLM model used for generation.")
    input_tokens: int = Field(description="Prompt tokens consumed.")
    output_tokens: int = Field(description="Completion tokens consumed.")
    latency_generation_ms: int = Field(description="Generation latency in milliseconds.")
    latency_retrieval_ms: int = Field(description="Retrieval latency in milliseconds.")
    num_chunks: int = Field(description="Number of chunks sent to the generator.")
    # Sprint 6 — Fix 2: citation-aware chunk filtering
    total_chunks_retrieved: int = Field(
        description=(
            "Total chunks returned by retrieval before citation filtering. "
            "Equals len(chunks) when no citations matched context (fallback)."
        )
    )
    chunks: list[ChunkResponse] = Field(
        description=(
            "Chunks cited by the generated answer (found_in_context=True). "
            "Falls back to all retrieved chunks when no citations matched context."
        )
    )
    diagnostics: DiagnosticsResponse = Field(description="Retrieval quality diagnostics.")
    # Sprint 3 — Task 11: multi-permit classifier
    permit_types: list[str] = Field(
        default_factory=list,
        description=(
            "Detected permit type(s) for this query "
            "(e.g. ['building', 'electrical', 'plumbing']). "
            "Populated by the zero-shot NLI classifier with keyword fallback."
        ),
    )
    ahj_disclaimer: AHJDisclaimer = Field(
        description=(
            "Authority Having Jurisdiction disclaimer. Always present. Informs the user "
            "that the AHJ (city building department) has final authority over permit decisions."
        )
    )
    # Sprint 5 — Task 14C: resolved jurisdiction from address geocoding
    resolved_municipality: str | None = Field(
        default=None,
        description=(
            "Municipality auto-resolved from the 'address' field via geocoding + "
            "PostGIS point-in-polygon. Null when address was not provided or resolution failed."
        ),
    )
    # Sprint 5 — Task 15: lightweight conflict detection
    conflict_warnings: list[ConflictWarning] = Field(
        default_factory=list,
        description=(
            "Conflict warnings surfaced when retrieved chunks from different "
            "authority levels appear to state contradictory requirements "
            "for the same subject."
        ),
    )
    # Phase 4 — Clarification nudge: set when persona was absent and the Prompt
    # Router fell back to the neutral `research` default. The UI can offer a
    # one-time prompt to set a role for tailored answers. Null when a persona
    # was known (no nudge needed).
    persona_nudge: str | None = Field(
        default=None,
        description=(
            "Present only when no persona was set and the answer used the neutral "
            "'research' default. A hint to ask the user for their role."
        ),
    )
    # Phase 4 query-UX: a grounding-floor miss returns 200 with abstained=true and
    # a conversational message in `answer` (not a 422 error). Citations are empty;
    # `chunks` still carries what retrieval found so the UI can show context.
    abstained: bool = Field(
        default=False,
        description=(
            "True when the system declined to answer because retrieval fell below "
            "the grounding floor. `answer` holds a conversational explanation; this "
            "is a normal outcome, not an error."
        ),
    )
    # Dual-Mode Fallback: structured interactive multiple choice options to clarify low-confidence/broad queries
    clarifying_options: list[ClarifyingOption] = Field(
        default_factory=list,
        description=(
            "Interactive multiple-choice option chips surfaced on broad/unverified "
            "queries to guide the user into narrowing their request."
        ),
    )
    # Phase 4 second pass — Media Curator: sourced how-to videos, diy path only.
    # Empty for every other persona, on an abstain, and when the query names no
    # curated task. Every URL is vetted (youtube.com); no model-invented links.
    media_refs: list[MediaRefResponse] = Field(
        default_factory=list,
        description=(
            "Sourced how-to video links, populated only for the 'diy' persona. "
            "Empty otherwise. Every URL is from a vetted source (zero unsourced URLs)."
        ),
    )
    # Media C2: a diy compliance-abstain answered from how-to video transcripts.
    # The answer is grounded in instructional video content, NOT permit code, and
    # carries `educational_disclaimer` instead of a compliance claim.
    how_to: bool = Field(
        default=False,
        description=(
            "True when this answer was generated from how-to video transcripts "
            "(a diy query with no confident compliance answer). Educational, not "
            "compliance guidance."
        ),
    )
    educational_disclaimer: str | None = Field(
        default=None,
        description=(
            "Present only on a how-to answer. Warns that the content is general "
            "instructional guidance, not permit/code compliance advice."
        ),
    )
    # Citation Verifier (#9): statements that cite a source retrieval never
    # returned (fabricated citations). Empty on a clean answer. Advisory — the
    # frontend surfaces a "verify independently" note, never blocks the answer.
    unsupported_citations: list[str] = Field(
        default_factory=list,
        description=(
            "Answer sentences whose citation points at a chunk that was not "
            "retrieved. Empty when every citation resolves."
        ),
    )
    # Item 3: per-sub-question breakdown of a fanned-out compound query.
    # Additive — `answer`/`citations` above always carry a backward-compatible
    # combined answer regardless, so an unmodified client needs no changes.
    # Empty for every non-compound query.
    sub_answers: list[SubAnswerResponse] = Field(
        default_factory=list,
        description=(
            "Per-sub-question breakdown of a fanned-out compound query, each with "
            "its own citations and abstain state. Empty for a simple query, or a "
            "compound query whose fan-out fell back to the single-answer path."
        ),
    )
    # Phase 5 feedback loop: the audit run this answer came from. The client
    # sends it back with a thumbs up/down to POST /query/feedback. Null when
    # tracing was disabled (no run row to attach feedback to).
    run_id: str | None = Field(
        default=None,
        description=(
            "Audit run id (agent_runs.id) for this answer. Pass it to "
            "POST /query/feedback to rate the answer. Null if tracing was off."
        ),
    )


class FeedbackRequest(BaseModel):
    """Body for POST /query/feedback — a thumbs up/down on an answer."""

    run_id: UUID = Field(description="The answer's run id, from AnswerResponse.run_id.")
    rating: Literal["up", "down"] = Field(description="Thumbs up or thumbs down.")
    comment: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional free-text comment (most useful on a thumbs-down).",
    )


class FeedbackResponse(BaseModel):
    """Acknowledgement for a recorded answer rating."""

    id: UUID = Field(description="The stored feedback row id.")
    run_id: UUID = Field(description="Run the feedback is attached to.")
    rating: Literal["up", "down"] = Field(description="The rating stored.")


class PermitStrategyResponse(BaseModel):
    """Permit Strategy (#11) output for a project — set, order, and fee estimate."""

    permits: list[str] = Field(description="Required permit categories, deduplicated.")
    sequence: list[str] = Field(description="Permits in the order they should be pulled.")
    fee_breakdown: dict[str, int] = Field(description="Per-permit fee estimate (USD).")
    estimated_fees_usd: int = Field(description="Total estimated permit fees (USD).")
    notes: str = Field(description="Plain-language sequencing note.")
    fee_disclaimer: str = Field(description="Reminder that fees are estimates, not a quote.")


class CoverageResponse(BaseModel):
    """Deterministic coverage-area check for a project's resolved jurisdiction/address.

    Distinct from a low-confidence retrieval abstain — this is a factual check
    (does the resolved municipality have real documents, or does the address
    fall outside every loaded boundary) rather than a retrieval-quality signal.
    """

    status: str = Field(description="covered | no_documents | no_boundary_data | unresolved")
    municipality: str | None = Field(default=None, description="Resolved municipality, if any.")
    message: str = Field(description="Human-readable explanation, safe to show directly to a user.")
    is_covered: bool = Field(description="True only when status == 'covered'.")
    overlays: list[OverlayResponse] = Field(
        default_factory=list,
        description=(
            "Approved historic/conservation-district or HOA overlays whose boundary "
            "contains this project's address, independent of municipality-level status."
        ),
    )


class OverlayResponse(BaseModel):
    """A historic/conservation-district or HOA overlay petition (migration 038)."""

    id: UUID
    name: str
    overlay_type: str = Field(description="historic_district | conservation_district | hoa | other")
    jurisdiction_id: str | None = None
    status: str = Field(description="petitioned | approved | rejected")
    petitioning_project_id: UUID | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    notes: str | None = None
    created_at: datetime


class ApproveOverlayRequest(BaseModel):
    """Optional refinement when a staff reviewer approves a petitioned overlay."""

    geojson_polygon: str | None = Field(
        default=None,
        description=(
            "A GeoJSON geometry (as a JSON string) to replace the petitioner's "
            "default buffer with a refined tight boundary. Omit to approve the "
            "existing (default-buffer) geometry as-is."
        ),
    )


class RejectDocumentRequest(BaseModel):
    """Optional reason when a staff reviewer rejects a pending ordinance
    petition (migration 047). The document row is kept (not deleted) so the
    submitter can see why via their own Documents library."""

    reason: str | None = Field(default=None, description="Shown to the submitter as the rejection reason.")


class SetVerifiedContributorRequest(BaseModel):
    """Admin-settable tiered-trust flag (migration 041) — Type 1 of the
    document-upload plan. A verified contributor's ordinance petitions
    auto-approve into the shared corpus instead of queuing for review."""

    is_verified_contributor: bool


class ErrorResponse(BaseModel):
    """Standard error response body."""

    detail: str = Field(description="Human-readable error description.")


class DocumentSummaryResponse(BaseModel):
    """Summary metadata for a single document."""

    id: UUID = Field(description="Document UUID primary key.")
    doc_id: str = Field(description="Human-readable document identifier.")
    source_url: str = Field(description="Canonical source URL.")
    municipality: str = Field(description="Source municipality.")
    # Plain str (not the Literal) so a how-to transcript doc (migration 031:
    # authority_level='educational', doc_type='how_to_video') serializes without a
    # ValidationError. The compliance corpus lists filter to content_class=authority,
    # but this keeps every serialization path crash-safe.
    authority_level: str = Field(description="Authority level.")
    doc_type: str = Field(description="Document type.")
    subject_tags: list[str] = Field(description="Subject tags from registry metadata.")
    document_status: DocumentStatusType = Field(description="Lifecycle status.")
    is_current: bool = Field(description="Whether this row is the current active revision.")
    effective_date: date | None = Field(description="Effective date if known.")
    review_due: date | None = Field(description="Review due date if tracked.")
    retrieval_weight: float = Field(description="Retrieval weighting factor.")
    updated_at: datetime = Field(description="Last update timestamp.")
    uploaded_by: UUID | None = Field(
        default=None, description="Uploader user id, for tier-3 project documents."
    )
    project_id: UUID | None = Field(
        default=None, description="Owning project id, for tier-3 project documents."
    )
    source_tier: int | None = Field(
        default=None, description="1=shared corpus, 2=pending petition, 3=project document."
    )
    rejection_reason: str | None = Field(
        default=None, description="Set when document_status is 'rejected' (migration 047)."
    )


class DocumentDetailResponse(DocumentSummaryResponse):
    """Detailed metadata for a single document."""

    checksum_sha256: str | None = Field(description="Source checksum fingerprint.")
    source_etag: str | None = Field(description="Source ETag when available.")
    local_path: str | None = Field(description="Relative raw file path.")
    superseded_by: UUID | None = Field(description="UUID of replacement document, if any.")
    ingested_at: datetime = Field(description="Ingestion timestamp.")
    chunk_count: int = Field(description="Total number of stored chunks for this document.")


class DocumentStatusCountResponse(BaseModel):
    """Per-status count bucket returned by the status endpoint."""

    status: DocumentStatusType = Field(description="Document lifecycle status.")
    count: int = Field(description="Number of documents in this status bucket.")


class DocumentStatusResponse(BaseModel):
    """Aggregated status totals for filtered document subsets."""

    municipality: str | None = Field(description="Applied municipality filter.")
    authority: AuthorityLevelType | None = Field(description="Applied authority filter.")
    doc_type: DocTypeType | None = Field(description="Applied document type filter.")
    status: DocumentStatusType | None = Field(description="Applied status filter.")
    total_documents: int = Field(description="Total documents matching all filters.")
    counts: list[DocumentStatusCountResponse] = Field(
        description="Counts grouped by document_status."
    )


class DocumentAdminUpdateRequest(BaseModel):
    """Mutable governance fields for admin metadata updates."""

    document_status: DocumentStatusType | None = Field(
        default=None,
        description="Lifecycle status update.",
    )
    is_current: bool | None = Field(
        default=None,
        description="Whether this revision is currently active for retrieval.",
    )
    retrieval_weight: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Retrieval weighting factor between 0 and 1.",
    )
    review_due: date | None = Field(
        default=None,
        description="Next governance review due date.",
    )


class DocumentSupersedeRequest(BaseModel):
    """Request body for superseding one document with another."""

    replacement_doc_id: str = Field(
        min_length=3,
        max_length=200,
        description="doc_id of the replacement document.",
    )
    superseded_weight: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Retrieval weight to apply to the superseded document.",
    )


class DocumentAdminActionResponse(BaseModel):
    """Admin mutation response for document governance endpoints."""

    action: str = Field(description="Mutation action that was applied.")
    message: str = Field(description="Human-readable mutation result.")
    document: DocumentDetailResponse = Field(description="Updated document metadata.")


# ── Sprint 9 — Users & Projects Schemas ──────────────────────

class RegisterRequest(BaseModel):
    """Registration request payload."""
    username: str = Field(..., min_length=3, max_length=30, description="Alphanumeric username plus _ . - allowed")
    password: str = Field(..., min_length=10, description="Minimum 10 characters")
    email: EmailStr = Field(..., description="Required email address")
    phone_number: str | None = Field(default=None, description="Optional E.164 phone number")


class LoginRequest(BaseModel):
    """Login request payload."""
    identifier: str = Field(..., description="Username, email, or phone number")
    password: str = Field(..., description="User password")


class TokenResponse(BaseModel):
    """Authentication tokens response."""
    access_token: str = Field(..., description="Short-lived access token")
    refresh_token: str = Field(..., description="Long-lived refresh token")
    token_type: str = Field(default="bearer", description="Token scheme")


class RefreshRequest(BaseModel):
    """Token refresh request payload."""
    refresh_token: str = Field(..., description="Valid refresh token to rotate")


class UserResponse(BaseModel):
    """User representation response."""
    id: UUID
    username: str
    email: str
    phone_number: str | None = None
    role: str
    created_at: datetime


class CreateProjectRequest(BaseModel):
    """Project creation payload."""
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    municipality: str | None = Field(default=None, description="Default city scope")
    address: str | None = Field(default=None, max_length=500, description="Full civic address")
    latitude: float | None = Field(default=None, description="Latitude coordinate of the project")
    longitude: float | None = Field(default=None, description="Longitude coordinate of the project")
    spaces: list[str] | None = Field(default=None, description="Selected space labels from kickoff wizard")
    work_types: list[str] | None = Field(default=None, description="Selected work-type labels from kickoff wizard")
    materials: list[str] | None = Field(default=None, description="Selected material/scope labels from kickoff wizard")
    recommended_permits: list[str] | None = Field(default=None, description="Permit categories recommended at creation time")
    budget: str | None = Field(default=None, description="Project budget context")
    persona: str | None = Field(default=None, description="User role persona (diy, hiring_contractor, contractor)")
    custom_system_prompt: str | None = Field(default=None, description="Generated system prompt instructions")
    project_notes: str | None = Field(default=None, max_length=1200, description="Bounded project notes (<=200 tokens) composed last by the Prompt Router")


class UpdateProjectRequest(BaseModel):
    """Partial project update payload."""
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    municipality: str | None = Field(default=None, description="Default city scope")
    address: str | None = Field(default=None, max_length=500, description="Full civic address")
    latitude: float | None = Field(default=None, description="Latitude coordinate of the project")
    longitude: float | None = Field(default=None, description="Longitude coordinate of the project")
    spaces: list[str] | None = Field(default=None, description="Selected space labels from kickoff wizard")
    work_types: list[str] | None = Field(default=None, description="Selected work-type labels from kickoff wizard")
    materials: list[str] | None = Field(default=None, description="Selected material/scope labels from kickoff wizard")
    recommended_permits: list[str] | None = Field(default=None, description="Permit categories recommended at creation time")
    budget: str | None = Field(default=None, description="Project budget context")
    persona: str | None = Field(default=None, description="User role persona (diy, hiring_contractor, contractor)")
    custom_system_prompt: str | None = Field(default=None, description="Deprecated (Phase 4): use project_notes")
    experience: str | None = Field(default=None, description="Experience modifier: first_timer | experienced")
    project_notes: str | None = Field(default=None, max_length=1200, description="Bounded project notes (<=200 tokens) composed last by the Prompt Router")


class SetProjectStatusRequest(BaseModel):
    """Payload to toggle the ongoing/archived filter tag."""
    is_archived: bool


class SetMarketplaceStatusRequest(BaseModel):
    """Payload to open/close a project for contractor bidding."""
    marketplace_status: str = Field(..., pattern=r"^(unlisted|open|awarded|closed)$")


class ProjectResponse(BaseModel):
    """Project representation response."""
    id: UUID
    name: str
    description: str | None = None
    owner_user_id: UUID
    owner_username: str | None = Field(
        default=None, description="Owner's username — only populated for staff (list_all_projects)."
    )
    owner_email: str | None = Field(
        default=None, description="Owner's email — only populated for staff (list_all_projects)."
    )
    municipality: str | None = None
    is_archived: bool
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    historic_district: str | None = None
    conservation_district: str | None = None
    spaces: list[str] | None = None
    work_types: list[str] | None = None
    materials: list[str] | None = None
    recommended_permits: list[str] | None = None
    room_summary: dict | None = None
    budget: str | None = None
    persona: str | None = None
    custom_system_prompt: str | None = None
    experience: str | None = None
    project_notes: str | None = None
    marketplace_status: str = "unlisted"
    listed_at: datetime | None = None
    bidding_closes_at: datetime | None = None
    awarded_bid_id: UUID | None = None


class KickoffChatMessage(BaseModel):
    """A message in the project kickoff chat history."""
    role: str = Field(..., description="Role of the sender, assistant or user")
    content: str = Field(..., description="Content of the message")


class KickoffChatRequest(BaseModel):
    """Payload to drive project kickoff chat progression."""
    history: list[KickoffChatMessage] = Field(..., description="Chat message history so far")
    address: str | None = Field(default=None, description="Project address context")
    municipality: str | None = Field(default=None, description="Project city context")
    spaces: list[str] | None = Field(default=None, description="Project spaces selected")
    work_types: list[str] | None = Field(default=None, description="Project work types selected")


class KickoffChatResponse(BaseModel):
    """Kickoff chat response showing next question or final profile extraction."""
    next_question: str | None = Field(default=None, description="Next prompt question from LLM")
    is_complete: bool = Field(..., description="True if LLM has gathered enough context to construct project profile")
    budget: str | None = Field(default=None, description="Extracted budget string if complete")
    persona: str | None = Field(default=None, description="Extracted persona string if complete")
    # Phase 4: kickoff emits bounded project notes composed last by the Prompt
    # Router, not a full system-prompt blob. custom_system_prompt kept for
    # back-compat with older clients; no longer populated by the kickoff chat.
    notes: str | None = Field(default=None, description="Bounded project notes (<=200 tokens) if complete")
    custom_system_prompt: str | None = Field(default=None, description="Deprecated (Phase 4): use notes")



class KickoffExtractRequest(BaseModel):
    """Free-form text (typed or dictated) describing a new project, for
    one-shot extraction -- the kickoff wizard's "free-form text/talk" entry
    paths, as opposed to the step-by-step form."""
    text: str = Field(..., min_length=1, max_length=4000, description="User's own words describing their project")


class KickoffExtractResponse(BaseModel):
    """Best-effort structured guess extracted from free-form kickoff text.

    Pre-fills the step-by-step wizard for review -- never bypasses it. Unmentioned
    fields are null/empty, never guessed. address_guess is plain text, not
    geocoded; the user still confirms it via AddressAutocomplete on step 1.
    """
    address_guess: str | None = Field(default=None, description="Address/area mentioned, as plain text")
    spaces: list[str] = Field(default_factory=list, description="Guessed spaces/rooms involved")
    work_types: list[str] = Field(default_factory=list, description="Guessed work categories")
    materials: list[str] = Field(default_factory=list, description="Guessed materials/scope")
    budget: str | None = Field(default=None, description="Guessed budget description")
    persona: str | None = Field(default=None, description="diy | hiring_contractor | contractor | research")
    comments: str | None = Field(
        default=None, description="Bounded notes (<=200 tokens), same discipline as kickoff chat's notes field"
    )


class AssetSyncAckRequest(BaseModel):
    """Mobile asset lifecycle sync acknowledgement."""
    asset_id: str = Field(..., min_length=1, max_length=120)
    checksum_sha256: str = Field(..., min_length=64, max_length=64)
    doc_id: str | None = Field(default=None, max_length=200)
    size_class: str | None = Field(default=None, max_length=32)


class AssetSyncAckResponse(BaseModel):
    """Response confirming cloud storage of mobile-uploaded asset."""
    asset_id: str
    checksum_sha256: str
    sync_state: str = "cloud_primary"


class RoomSummaryRequest(BaseModel):
    """Derived room capture summary (no raw mesh)."""
    room_summary: dict


class RoomScanUpsertItem(BaseModel):
    """One structure or room derived summary row (no surfaces)."""
    id: UUID
    scan_type: str = Field(..., pattern=r"^(structure|room)$")
    parent_scan_id: UUID | None = None
    room_label: str = Field(..., min_length=1, max_length=120)
    section: str | None = Field(default=None, max_length=64)
    structure_label: str | None = Field(default=None, max_length=120)
    captured_at: datetime
    derived: dict
    is_active: bool = False


class UpsertRoomScansRequest(BaseModel):
    """Batch upsert of structure + room derived summaries."""
    scans: list[RoomScanUpsertItem] = Field(..., min_length=1)


class UserRoomScanResponse(BaseModel):
    """User-owned derived scan summary (library entry)."""
    id: UUID
    user_id: UUID
    scan_type: str
    parent_scan_id: UUID | None = None
    room_label: str
    section: str | None = None
    structure_label: str | None = None
    captured_at: datetime
    derived: dict
    created_at: datetime
    updated_at: datetime


class ProjectLinkedRoomScanResponse(UserRoomScanResponse):
    """Scan linked to a project workspace."""
    project_id: UUID
    is_active: bool
    linked_at: datetime


class LinkRoomScansRequest(BaseModel):
    """Attach existing library scans to a project."""
    scan_ids: list[UUID] = Field(..., min_length=1)
    active_scan_id: UUID | None = None


class RoomScanResponse(BaseModel):
    """Derived room/structure scan row."""
    id: UUID
    project_id: UUID
    scan_type: str
    parent_scan_id: UUID | None = None
    room_label: str
    section: str | None = None
    captured_at: datetime
    derived: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DesignIntentRequest(BaseModel):
    """Voice/text remodel instruction for a room-scoped AR overlay."""
    utterance: str = Field(..., min_length=1, max_length=2000)
    room_label: str | None = Field(default=None, max_length=120)
    room_derived: dict | None = None
    surface_hints: list[dict] | None = None
    selected_surface_id: str | None = Field(default=None, max_length=250)


class DesignIntentUsage(BaseModel):
    """Token usage from a design-intent LLM preview call."""
    input_tokens: int
    output_tokens: int
    model: str


class DesignIntentResponse(BaseModel):
    """Structured overlay patches for native AR application."""
    overlays: list[dict]
    explanation: str
    product_candidates: list[dict] = Field(default_factory=list)
    usage: DesignIntentUsage


class RoomPreviewImageRequest(BaseModel):
    """Generate a photoreal room redesign preview from design intent."""
    utterance: str = Field(..., min_length=1, max_length=2000)
    room_label: str | None = Field(default=None, max_length=120)
    overlays: list[dict] = Field(default_factory=list)
    source_image_b64: str | None = Field(
        default=None,
        description="Optional room photo (base64, no data: prefix) for layout hints.",
        max_length=8_000_000,
    )
    tiling: bool | None = Field(
        default=None,
        description="Optional flag to enable seamless tileable textures (Leonardo.ai only).",
    )


class RoomPreviewImageResponse(BaseModel):
    """Base64 image payload for on-device storage as overlay asset_url."""
    image_base64: str
    mime_type: str
    provider: str
    model: str
    prompt: str
    mock: bool = False


class ProductSearchRequest(BaseModel):
    """Search retailer catalog for materials near a zip code."""
    query: str = Field(..., min_length=1, max_length=200)
    zip_code: str = Field(default="75034", pattern=r"^\d{5}$")
    limit: int = Field(default=3, ge=1, le=10)


class ProductSearchResponse(BaseModel):
    """Home Depot product search results."""
    products: list[dict]
    zip_code: str
    disclaimer: str = "Prices and availability change — confirm in store."


class MaterialsEstimateLine(BaseModel):
    """One BOM line for a project materials estimate."""
    overlay_type: str
    product_title: str | None = None
    qty_estimate: dict | None = None
    line_estimate: dict | None = None
    product_ref: dict | None = None


class MaterialsEstimateResponse(BaseModel):
    """Aggregated materials estimate from design overlays."""
    lines: list[MaterialsEstimateLine]
    total_low: float | None = None
    total_high: float | None = None
    disclaimer: str = "Estimate only — confirm quantities and prices in store."


class BidLineItemRequest(BaseModel):
    """One line item within a bid submission."""
    description: str = Field(..., min_length=1, max_length=300)
    quantity: float = Field(..., gt=0)
    unit: str = Field(..., min_length=1, max_length=20)
    unit_price: float = Field(..., ge=0)
    labor_amount: float = Field(default=0, ge=0)
    material_amount: float = Field(default=0, ge=0)
    labor_hours: float | None = Field(default=None, ge=0)
    canonical_work_item: str | None = None


class CreateBidRequest(BaseModel):
    """Payload to submit a structured bid on an open project — shaped to match
    the BidDocument schema the Bid Evaluator (docs/agent_architecture.md) was
    designed around."""
    license_id: UUID
    line_items: list[BidLineItemRequest] = Field(..., min_length=1)
    allowances: list[dict] = Field(default_factory=list, description="[{description, amount}]")
    exclusions: list[dict] = Field(default_factory=list, description="[{description}]")
    payment_schedule: list[dict] = Field(default_factory=list, description="[{milestone, percent|amount, trigger}]")
    permit_responsibility: str | None = Field(default=None, pattern=r"^(contractor|homeowner)$")
    timeline_start: date | None = None
    timeline_end: date | None = None
    timeline_notes: str | None = Field(default=None, max_length=500)
    warranty_text: str | None = Field(default=None, max_length=1000)
    warranty_years: float | None = Field(default=None, ge=0, le=50)
    change_order_terms: str | None = Field(default=None, max_length=1000)
    lien_waiver_included: bool = False
    materials_source: str = Field(
        default="unspecified",
        pattern=r"^(unspecified|homeowner_supplied|contractor_supplied_manual|contractor_supplied_connector)$",
    )
    materials_source_connector: str | None = None
    materials_source_notes: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)


class BidLineItemResponse(BaseModel):
    """One line item as stored."""
    id: UUID
    description: str
    quantity: float
    unit: str
    unit_price: float
    labor_amount: float
    material_amount: float
    labor_hours: float | None = None
    canonical_work_item: str | None = None


class BidEvaluationResponse(BaseModel):
    """The Bid Evaluator's scored output for one bid — completeness, red
    flags (deterministic + LLM-assisted novel flags), and price-reasonableness
    per line item. Estimates only; see disclaimer."""
    completeness_score: float
    missing_clauses: list[str]
    red_flags: list[dict]
    price_assessments: list[dict]
    llm_flags: list[dict]
    disclaimer: str


class BidResponse(BaseModel):
    """A contractor's bid on a project."""
    id: UUID
    project_id: UUID
    contractor_profile_id: UUID
    contractor_business_name: str | None = None
    license_id: UUID
    status: str
    total_price: float
    labor_total: float | None = None
    material_total: float | None = None
    allowances: list[dict] = Field(default_factory=list)
    exclusions: list[dict] = Field(default_factory=list)
    payment_schedule: list[dict] = Field(default_factory=list)
    permit_responsibility: str | None = None
    timeline_start: date | None = None
    timeline_end: date | None = None
    timeline_notes: str | None = None
    warranty_text: str | None = None
    warranty_years: float | None = None
    change_order_terms: str | None = None
    lien_waiver_included: bool
    materials_source: str
    materials_source_connector: str | None = None
    materials_source_notes: str | None = None
    notes: str | None = None
    submitted_at: datetime | None = None
    decided_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    line_items: list[BidLineItemResponse] = Field(default_factory=list)
    evaluation: BidEvaluationResponse | None = None


class MarketplaceListingResponse(BaseModel):
    """A single open project as seen by a browsing contractor — the project's
    own fields plus the room-scan-derived scope and priced materials estimate,
    so a bid can be grounded in the same data the homeowner already captured."""
    project: ProjectResponse
    room_scan_summary: dict | None = Field(default=None, description="derived metrics from the active room scan, if any")
    materials_estimate: MaterialsEstimateResponse | None = None


class ProjectMemberResponse(BaseModel):
    """Project member details response."""
    user_id: UUID
    username: str
    email: str
    role: str
    invited_at: datetime


class AddMemberRequest(BaseModel):
    """Request to enroll a member."""
    user_id: UUID = Field(..., description="UUID of the user to invite")
    role: str = Field(default="viewer", pattern=r"^(editor|viewer)$", description="Role: editor or viewer")


class TransferOwnershipRequest(BaseModel):
    """Request to transfer project ownership."""
    new_owner_id: UUID = Field(..., description="UUID of the new owner")


class ShareDocumentRequest(BaseModel):
    """Request to share a document to a project."""
    document_id: UUID = Field(..., description="UUID of the document to share")


class CreateContractorProfileRequest(BaseModel):
    """Payload to create the caller's contractor profile."""
    business_name: str = Field(..., min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    trades: list[str] | None = Field(default=None, description="Trade categories, e.g. Electrical, Plumbing")
    service_municipalities: list[str] | None = Field(default=None, description="Municipalities served")
    bio: str | None = Field(default=None, max_length=2000)
    years_in_business: int | None = Field(default=None, ge=0, le=150)


class UpdateContractorProfileRequest(BaseModel):
    """Partial update payload for the caller's contractor profile."""
    business_name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    trades: list[str] | None = None
    service_municipalities: list[str] | None = None
    bio: str | None = Field(default=None, max_length=2000)
    years_in_business: int | None = Field(default=None, ge=0, le=150)
    is_active: bool | None = None


class ContractorProfileResponse(BaseModel):
    """Contractor profile representation response."""
    id: UUID
    user_id: UUID
    business_name: str
    contact_name: str | None = None
    phone: str | None = None
    trades: list[str] = Field(default_factory=list)
    service_municipalities: list[str] = Field(default_factory=list)
    bio: str | None = None
    years_in_business: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CreateContractorLicenseRequest(BaseModel):
    """Payload to add a license/insurance record."""
    trade: str = Field(..., min_length=1, max_length=80)
    license_number: str = Field(..., min_length=1, max_length=40)
    expiration_date: date
    issuing_authority: str | None = Field(default=None, max_length=200)
    insurance_provider: str | None = Field(default=None, max_length=200)
    insurance_policy_number: str | None = Field(default=None, max_length=100)
    insurance_coverage_amount: float | None = Field(default=None, ge=0)
    insurance_expiration_date: date | None = None


class UpdateContractorLicenseRequest(BaseModel):
    """Partial update payload for a license/insurance record."""
    trade: str | None = Field(default=None, min_length=1, max_length=80)
    license_number: str | None = Field(default=None, min_length=1, max_length=40)
    expiration_date: date | None = None
    issuing_authority: str | None = Field(default=None, max_length=200)
    insurance_provider: str | None = Field(default=None, max_length=200)
    insurance_policy_number: str | None = Field(default=None, max_length=100)
    insurance_coverage_amount: float | None = Field(default=None, ge=0)
    insurance_expiration_date: date | None = None


class ContractorLicenseResponse(BaseModel):
    """License/insurance record response."""
    id: UUID
    contractor_profile_id: UUID
    trade: str
    license_number: str
    issuing_authority: str | None = None
    expiration_date: date
    insurance_provider: str | None = None
    insurance_policy_number: str | None = None
    insurance_coverage_amount: float | None = None
    insurance_expiration_date: date | None = None
    created_at: datetime
    updated_at: datetime


class UserMeResponse(BaseModel):
    """Response for GET /auth/me — current user profile."""
    id: UUID
    username: str
    email: str
    role: str
    cognito_sub: str
    created_at: datetime
    active_project_id: UUID | None = None
    has_contractor_profile: bool = False


class SetActiveProjectRequest(BaseModel):
    """Payload to set or clear the caller's single "active" project."""
    project_id: UUID | None = Field(default=None, description="Project to activate, or null to clear")

