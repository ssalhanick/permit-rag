# Session 2026-07-24 (c) — Agent architecture Phase 3 (Metadata Validator + dashboard v1)

Branch: `agents/phase-3`. Machine A (repo machine, empty DB, no corpus).

## Task (restated at session start)

Phase 3 — Corpus Metadata Validator + 27-doc backfill + superadmin dashboard v1
(action queue + metadata review). First blocker: fix the migration numbering
(Phase 3 → 028, cascade 029/030) before writing any SQL, because
`027_agent_action_item_dedupe` already owns 027 on prod + machine B. Governance
non-negotiable: writes through `ingestion/governance.py` only, never
auto-supersede, never auto-update on URL change, failing docs → `draft` with a
blocking action item. Register the validator through the registry; `ingestion/`
may import only `rag/agent_runtime` from `rag/`; every model call through
`run_agent`.

## What was accomplished (all machine A, mocked/offline)

### Migration numbering fixed first (docs/agent_architecture.md)
- Phase 3 migration → **028**, Phase 4 → 029, Phase 6 → 030. Updated the Phase 3
  section, the Phase 4/6 section headers, and the Files list, with a numbering
  note explaining why 027 is skipped (dedupe migration) and that the duplicate
  026 is recorded, not renamed.

### Migration 028 — `db/migrations/028_metadata_validation.sql`
- `ALTER TYPE verification_stage ADD VALUE IF NOT EXISTS 'metadata'` and
  `verification_result ADD VALUE IF NOT EXISTS 'needs_review'`. Additive,
  idempotent, no new tables (proposals reuse `agent_action_items` from 026;
  per-stage results reuse `ingestion_verifications`). `db/schema.sql` enums
  updated to match a fresh build.

### Governance-gated write path
- `db/client.update_document_metadata_fields` — writes the four retrieval-driving
  fields (`effective_date`, `doc_type`, `authority_level`, `subject_tags`) that
  `update_document_admin_fields` deliberately does **not** touch.
- `ingestion/governance.apply_metadata_correction` — the single corpus writer for
  corrected metadata; called only after human approval in the dashboard.
- `ingestion/governance.flag_document_for_review` — files a deduped blocking
  action item; `set_draft` gates the draft move. **Key decision:** the backfill
  over the live corpus passes `set_draft=False` — drafting all 27
  currently-null-`effective_date` docs would empty retrieval. Drafting is the
  ingest-time path only.

### `ingestion/metadata_agent.py` — Corpus Metadata Validator (agent #13)
- Deterministic first: `check_enum_conformance` (doc_type/authority against the
  schema enums → a `fail`), `check_completeness` (AGENTS.md's six required
  fields + empty subject_tags), `detect_supersession_candidates` (strips a
  trailing `-vN`/`-YYYYMMDD` tag to find families like
  `city-of-dallas-ordiance-v1/v2/v3`; flags only, never proposes a supersession).
- `sample_chunks` spreads the sample evenly across the document (not the first k
  — that is exactly `harvester.py`'s cover-page bug).
- One structured `run_agent` call (`Tier.MID`, `output_format=MetadataAssessment`)
  for content-vs-metadata agreement + date extraction. `build_proposals`
  re-validates enum/vocab against the deterministic source of truth and only
  proposes a change that is valid, cited, and actually different. **Every
  proposal carries a `Citation` (chunk_index → real chunk_id + excerpt).**
- `validate_document` proposes and files action items via governance; it never
  writes the corpus itself. `file_action_items`/`save_verification` default off
  (a dry run touches nothing). `validate_corpus` is the backfill driver.

### Registration + verification stage
- Registered `metadata_validator` through the registry via
  `api/main._register_di_agents()` (rag/ cannot import ingestion/, so api wires
  it; lazily bound). Roster is now 10 specs.
- `ingestion/verification.py` summary emoji map gains `needs_review`.

### `scripts/backfill_document_metadata.py` (machine B only)
- Uses `_db_target` for target safety. Dry-run by default (files nothing);
  `--apply` files action items; `--no-llm` skips the priced call; `--report`
  prints per-doc detail with citations. Never drafts, never writes the corpus.

### Dashboard v1 backend — `api/routes/agents_admin.py`
- `/admin/agents/action-items` (list) + `/{id}/resolve`;
  `/admin/agents/metadata-review` (list) + `/{doc_id}/apply`. Every route
  superadmin-gated via `is_superadmin`. Approve routes the write through
  `governance.apply_metadata_correction` and records an `agent_corrections` row
  (resolution closes the loop → training data). Registered in `api/main.py` +
  `api/routes/__init__.py`.

### Dashboard v1 frontend — `frontend/src/admin/`
- `SuperadminRoute.jsx` (the new frontend guard; backend gate already existed),
  `AgentDashboardPage.jsx` (tabbed shell), `ActionQueue.jsx`,
  `MetadataReviewPane.jsx` (renders each proposal with its citation; approving
  applies the selected fields). `/admin/agents` route wired in `main.jsx`;
  superadmin-only "Agents" nav link. API helpers added to `api.js`.

## Verification performed (machine A)

- `py -m pytest tests/ -q` → **436 passed** (was 398; +38 Phase 3:
  `test_metadata_agent.py` 24, `test_agents_admin_routes.py` 10,
  `test_governance_metadata.py` 4). Zero existing test files edited.
- `py scripts/verify_phase2.py --no-db` → **18/18**, including the grep that
  proves no inline `anthropic.Anthropic(` in `rag/` (the validator uses
  `run_agent`, and it lives in `ingestion/`, not `rag/`).
- `ruff check` clean on every new file. Compile clean.
- **Not run here:** migration 028 apply, the live validator, the backfill — all
  need the corpus (machine B).

## Findings / decisions worth keeping

1. **The DB already had `doc_type`/`authority_level` NOT NULL** (schema:86-87),
   so the "5 null docs" from the corpus audit are null in the *sidecars*, not the
   live DB — in the DB those fields carry values (possibly the `other` catch-all).
   The real DB gap is `effective_date` (nullable, 27/27 null) and empty
   `subject_tags`. The validator treats `doc_type == 'other'` as a re-check
   trigger rather than a hard failure.
2. **Backfill must not draft.** `document_status='draft'` is excluded by
   `match_chunks`, so drafting the 27 null-date live docs would empty retrieval.
   Drafting is the ingest path (`draft_on_fail=True`); the backfill proposes only.
   This is encoded in `flag_document_for_review(set_draft=...)` and asserted.
3. **Autonomy is not enforced on `apply_metadata_correction`.** The human
   superadmin approving in the dashboard *is* the L1 gate; enforcing the seeded
   `metadata_validator/semantic` (current L0) would block the approval. The
   runtime ceiling governs *auto*-application, which this phase never does.
4. **`api/` already imports `ingestion.governance`** (pull.py), so the apply
   route calling governance respects established practice even though the
   AGENTS.md boundary list omits `ingestion` from api's allowed imports.
5. **The anthropic floor was already present** (`pyproject.toml:29`,
   `anthropic>=0.104.1`) on this branch — the carried "push the floor" item is a
   no-op here.
6. **Local ruff (anaconda) is newer than machine A's** and flags a few
   pre-existing I001/SIM issues across the repo that machine A's gate does not.
   Only my new files matter; they are clean under both.

## Still open at session end (machine B)

- Apply migration 028; run the live validator + backfill; verify the dashboard
  end-to-end against the corpus.
- q6 / Dallas ordinance v1-v2-v3 supersession is now *detectable* by
  `detect_supersession_candidates`; resolving it is a human review action.
- Prod migration 028 not yet applied/deployed.

## Machine B block — Phase 3 verification (run in order)

```powershell
.\.venv\Scripts\Activate.ps1
# 0. Confirm current state BEFORE any DB write (read-only; settles prod 027 too).
py scripts/check_migration_details.py --local
# 1. Apply migration 028 (additive enum extensions).
py scripts/apply_migration.py db/migrations/028_metadata_validation.sql
# 2. Dry run the validator over the corpus (no writes, no items filed).
py scripts/backfill_document_metadata.py --local --dry-run --report
# 3. Deterministic-only pass (free), to eyeball enum/completeness/supersession.
py scripts/backfill_document_metadata.py --local --no-llm --report
# 4. When the proposals look right, file action items (still no corpus writes).
py scripts/backfill_document_metadata.py --local --apply --report
# 5. Regression + offline invariants.
py -m pytest tests/ -q                 # expect 436 passed
py scripts/verify_phase2.py --no-db    # 18/18, incl. the anthropic grep
```

## Commit message

```
feat: Phase 3 Corpus Metadata Validator + governance write path + superadmin dashboard v1
```

## Prompt for next session

> Read STATE.md, journals/session_20260724_phase3.md, AGENTS.md, and
> docs/agent_architecture.md before touching anything. Restate the current task
> first — AGENTS.md pre-session protocol.
>
> **Machine A (this repo) has an EMPTY database and no `documents/raw/`.** Only
> these work here: `py -m pytest tests/ -q` (436, fully mocked),
> `py -m ruff check rag/ tests/`, `py scripts/verify_phase2.py --no-db`. Do not
> propose the validator, backfill, migration apply, `check_migration_details.py`,
> or anything DB/corpus-dependent here — collect them into ONE machine-B block.
>
> **Phase 3 code is BUILT and mocked-tested on machine A (436 passed), not yet
> verified on the corpus or deployed.** Deliverables: migration 028
> (`028_metadata_validation.sql`, enum extensions only), `ingestion/metadata_agent.py`
> (agent #13, deterministic-first + one structured `run_agent` call, every
> proposal cites a source chunk), the governance write path
> (`apply_metadata_correction` + `flag_document_for_review` — backfill never
> drafts a live doc), `scripts/backfill_document_metadata.py`, the superadmin
> dashboard (`api/routes/agents_admin.py` + `frontend/src/admin/`,
> `/admin/agents`). Validator registered via `api/main._register_di_agents()`.
>
> **Next: run the machine-B block in the journal** (apply 028, dry-run then
> `--apply` the backfill, confirm 436 tests + verify_phase2 --no-db), then review
> the filed proposals in the dashboard, approve the good ones (each apply writes
> through governance + records a correction row), and confirm q6's Dallas
> ordinance v1/v2/v3 family is flagged by `detect_supersession_candidates`.
> After machine-B verification: merge to `deployment/sites` and GHA-deploy (028
> is additive, safe). Then move Phase 3 from README Planned → Completed.
>
> Carried, still open: the RAGAs harness needs a fresh **live**
> (`--no-answer-cache`) multi-sample baseline before it is trusted as a Phase 3
> gate (do not gate on a single number — the judge swings ±0.15 on one query).
> The `anthropic>=0.104.1` floor is already in `pyproject.toml` — no action.
```
