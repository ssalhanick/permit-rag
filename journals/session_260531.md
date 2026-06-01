# Session: 2026-05-31

## Type

Enhancement — hybrid retrieval guardrails + documents API routes/tests/docs.

## Goal

Investigate q1 faithfulness collapse under hybrid retrieval, add non-municipality authority/source guardrails to reduce cross-jurisdiction noise, re-run previews/evaluations, and close out state before moving to API work.

---

## Completed

### Retrieval guardrail implementation

- Added non-municipality authority guardrails in `rag/retriever.py`:
  - authority target detection from query scope (state/federal/ADA cues),
  - municipal-authority penalty for `municipality=None` retrievals,
  - scope-match bonus and scope-mismatch penalty for state/federal authority.
- Kept guardrails env-gated for rollback-safe tuning:
  - `RETRIEVAL_AUTHORITY_GUARDRAIL_ENABLED`
  - `RETRIEVAL_NON_MUNI_MUNICIPAL_PENALTY`
  - `RETRIEVAL_NON_MUNI_SCOPE_MATCH_BONUS`
  - `RETRIEVAL_NON_MUNI_SCOPE_MISMATCH_PENALTY`
- Preserved municipality-filtered behavior (Dallas/Plano queries are not penalized by this guardrail path).

### Tests + retrieval previews

- Expanded `tests/test_retriever.py` for guardrail behavior:
  - state-scoped query reranks state chunk over municipal noise,
  - municipality-filtered path bypasses non-municipality guardrails.
- Verified tests pass: `6 passed`.
- Re-ran retrieval previews under hybrid mode:
  - q1 (`Do I need a permit for electrical work in Texas?`) still includes some municipal docs, but state source remains top-ranked.
  - q5 (`fire sprinkler ... Dallas`) remained strong on Dallas code sources.

### Evaluation runs

- Focused run: `py -m evaluation.ragas_eval --query 0 1 2 3 5 --export`
  - output: `evaluation/results/ragas_20260531_094718.json`
  - avg faithfulness: `0.784`
  - avg relevancy: `0.778`
  - avg context precision: `0.663`
- Full 7-query run: `py -m evaluation.ragas_eval --export`
  - output: `evaluation/results/ragas_20260531_102544.json`
  - avg faithfulness: `0.852` (gate pass vs 0.85)
  - avg relevancy: `0.832`
  - avg context precision: `0.621`
- Comparison to prior hybrid full run (`ragas_20260531_003019.json`):
  - faithfulness: `0.798 -> 0.852` (`+0.054`)
  - q1 faithfulness: `0.353 -> 0.438` (improved but still weakest query)

### Eval export enrichment

- Updated `evaluation/ragas_eval.py` export payload to include query-level top retrieval provenance:
  - `most_relevant_chunk_id`
  - `most_relevant_doc_id`

### State/docs closeout

- Updated `STATE.md` with latest subset/full metrics, deltas, decisions, deliverables checklist, and validation commands.
- README health check completed and updated:
  - added new guardrail env vars in ingestion/retrieval config block,
  - refreshed hybrid status note with latest full-run gate result and caution on q1 instability.

### Documents API route implementation

- Added `api/routes/documents.py` with:
  - `GET /documents` for list/filtering by `municipality`, `status`, `authority`, `doc_type`
  - `GET /documents/{doc_id}` for document detail + `chunk_count`
  - `GET /documents/status` for grouped status counts under optional filters
- Updated `api/schemas.py` with typed document filter aliases + response models:
  - `DocumentSummaryResponse`, `DocumentDetailResponse`,
  - `DocumentStatusCountResponse`, `DocumentStatusResponse`
- Extended `db/client.py`:
  - `list_documents()` now accepts `authority_level` + `doc_type` filters
  - added `get_document_status_counts()` grouped aggregation helper
- Wired router in API bootstrap:
  - `api/routes/__init__.py` exports `documents_router`
  - `api/main.py` includes `documents_router`
- Added route tests in `tests/test_documents_routes.py`:
  - filter forwarding + response shape
  - invalid filter 422 behavior
  - detail success/404
  - status aggregation shape
- Added API usage docs/examples:
  - `docs/api.md` (endpoint-specific examples)
  - `README.md` API quick start + curl examples

### Validation blocker

- Could not execute new smoke checks or confirmatory eval from this session tooling:
  - every attempted shell command returned unknown exit status with no reliable stdout/stderr.
- Marked as blocker in `STATE.md` with pending commands for immediate follow-up run in local terminal.

---

## Validation outcomes observed this session

- Hybrid full-suite faithfulness recovered above gate (`0.852 >= 0.85`) on latest run.
- q1 remains below target (`0.438`) and still vulnerable to cross-jurisdiction context contamination.
- Hybrid default remains `false` pending one additional confirmatory full run after API route work (stability check).

---

## Next session should

1. Run `py -m pytest tests/test_documents_routes.py` and confirm route smoke passes.
2. Run confirmatory hybrid full eval:
   - `$env:RETRIEVAL_HYBRID_ENABLED="true"; $env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export`
3. Record final metric deltas from the confirmatory run in `STATE.md` and revisit hybrid default toggle.

## Prompt for next session

Read `AGENTS.md`, `STATE.md`, and `journals/session_260531.md`. Run pending API/eval verification commands from local terminal:
`py -m pytest tests/test_documents_routes.py`
`$env:RETRIEVAL_HYBRID_ENABLED="true"; $env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export`
Then update `STATE.md` with confirmatory full-run metric deltas (faithfulness/relevancy/context precision vs `ragas_20260531_102544.json`) and decide whether `RETRIEVAL_HYBRID_ENABLED` can be default-enabled or should remain false.

## Git commit message

feat(api): add documents list/detail/status routes with typed filters, response schemas, tests, and API usage docs

---

## Closeout addendum (2026-05-31, later run)

### Final verification completed

- `py -m pytest tests/test_documents_routes.py` → `5 passed`
- Confirmatory full eval run completed:
  - command: `$env:RETRIEVAL_HYBRID_ENABLED="true"; $env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export`
  - output: `evaluation/results/ragas_20260531_122639.json`

### Confirmatory deltas vs prior full run (`ragas_20260531_102544.json`)

- avg faithfulness: `0.860` (`+0.008`)
- avg relevancy: `0.838` (`+0.006`)
- avg context precision: `0.669` (`+0.049`)
- top similarity avg: `0.790` (`+0.000`)
- top similarity min/max: `0.762/0.819` (unchanged vs prior run)

### Decision update

- `RETRIEVAL_HYBRID_ENABLED` is approved for default enablement, with env toggle retained for quick rollback if q1 regresses.

## Prompt for next session

Read `AGENTS.md`, `STATE.md`, and `journals/session_260531.md`. Validate that hybrid mode remains stable after default enablement by running one fresh full eval and comparing against `ragas_20260531_122639.json`. Then add a lightweight eval regression guard (script or test) that fails if avg faithfulness drops below `0.85` or q1 faithfulness drops by more than `0.10` from the current confirmatory baseline.

## Git commit message

chore(state): close out confirmatory eval, record final deltas, and approve hybrid default enablement

---

## Fine-tuning closeout addendum (2026-06-01)

### Evaluation stability confirmation

- Ran fresh full eval export after default hybrid enablement:
  - command: `$env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export`
  - output: `evaluation/results/ragas_20260601_112137.json`
- Confirmed stable/improved outcomes vs confirmatory baseline (`ragas_20260531_122639.json`):
  - avg faithfulness: `0.894` (above `0.85` gate)
  - q1 faithfulness: `0.933` (improved vs baseline `0.600`)

### Regression guard implementation

- Added lightweight eval gate script: `evaluation/eval_guard.py`
  - fails if avg faithfulness drops below `0.85`
  - fails if q1 faithfulness drops by more than `0.10` from baseline
  - defaults to baseline: `evaluation/results/ragas_20260531_122639.json`
- Added tests: `tests/test_eval_guard.py` (`3 passed`)
- Documented guard usage in `README.md`

### Supporting cleanup/docs

- Removed duplicate catalog entry that caused loader failure:
  - duplicate `doc_id`: `texas-contractor-licensing-electrical`
- Added short metric definitions to `README.md` for:
  - faithfulness
  - relevancy
  - context precision
  - top similarity

### Decision update

- Active RAG fine-tuning is paused for now; retrieval/generation quality is stable under current guardrails.
- Next implementation focus moves to API completion (admin routes + API hardening), while keeping eval guard checks as a regression gate.

## Prompt for next session

Read `AGENTS.md`, `STATE.md`, and `journals/session_260531.md`. Continue API completion by implementing admin routes and adding tests/docs for them. After API-impacting changes, run:
`py -m pytest tests/test_documents_routes.py`
`$env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export`
`py -m evaluation.eval_guard`
Then record API progress and any metric deltas in `STATE.md`.

## Git commit message

chore(eval): add ragas regression guard and close out hybrid tuning before API phase
