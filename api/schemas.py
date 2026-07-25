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

DocumentStatusType = Literal["active", "superseded", "repealed", "needs_ocr", "draft"]
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


class ErrorResponse(BaseModel):
    """Standard error response body."""

    detail: str = Field(description="Human-readable error description.")


class DocumentSummaryResponse(BaseModel):
    """Summary metadata for a single document."""

    id: UUID = Field(description="Document UUID primary key.")
    doc_id: str = Field(description="Human-readable document identifier.")
    source_url: str = Field(description="Canonical source URL.")
    municipality: str = Field(description="Source municipality.")
    authority_level: AuthorityLevelType = Field(description="Authority level.")
    doc_type: DocTypeType = Field(description="Document type.")
    subject_tags: list[str] = Field(description="Subject tags from registry metadata.")
    document_status: DocumentStatusType = Field(description="Lifecycle status.")
    is_current: bool = Field(description="Whether this row is the current active revision.")
    effective_date: date | None = Field(description="Effective date if known.")
    review_due: date | None = Field(description="Review due date if tracked.")
    retrieval_weight: float = Field(description="Retrieval weighting factor.")
    updated_at: datetime = Field(description="Last update timestamp.")


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


class ProjectResponse(BaseModel):
    """Project representation response."""
    id: UUID
    name: str
    description: str | None = None
    owner_user_id: UUID
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


class UserMeResponse(BaseModel):
    """Response for GET /auth/me — current user profile."""
    id: UUID
    username: str
    email: str
    role: str
    cognito_sub: str
    created_at: datetime
    active_project_id: UUID | None = None


class SetActiveProjectRequest(BaseModel):
    """Payload to set or clear the caller's single "active" project."""
    project_id: UUID | None = Field(default=None, description="Project to activate, or null to clear")

