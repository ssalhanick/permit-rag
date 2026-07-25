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

- `py -m pytest tests/ -q` → **438 passed** (was 398; +40: `test_metadata_agent.py`
  24, `test_agents_admin_routes.py` 10, `test_governance_metadata.py` 4,
  `test_agent_runtime.py` +2 temperature). Zero existing test files edited.
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

## Machine-B follow-up fix — `temperature` deprecated on Sonnet 5

First live backfill run 400'd on **every** doc:
`` `temperature` is deprecated for this model. `` The validator's `Tier.MID`
call hits `claude-sonnet-5`, which dropped the `temperature` param; Haiku 4.5
(all of Phase 1/2) still accepts it, so this was the first time it surfaced.

Fixed in the single call site, not the validator: `run_agent._dispatch` now
**learns** unsupported models — on a "temperature deprecated" 400 it records the
model in `_TEMPERATURE_UNSUPPORTED`, retries without the param, and omits it for
every later call in the process. No hard-coded list to rot; Haiku still sends
temperature unchanged. Tests: `test_agent_runtime.py` +2 (retry-then-succeed;
learned-model-skips-from-start). Suite now **438**. `verify_phase2 --no-db` still
18/18. **Machine B must pull `agents/phase-3` and re-run the backfill.**

Second machine-B finding: the first clean LLM run validated only **11 of 19**
docs — 8 errored in the model call and `validate_corpus` swallowed them (looked
identical to a pass in the totals). Two fixes: (1) the assessment `max_tokens`
was 1024, which truncates the 4-proposal structured JSON on verbose docs and
fails the parse → raised to **2048**; (2) `validate_corpus` now records a
`result="error"` report (with the exception string) instead of dropping the doc,
and the backfill report prints errored docs as 💥 with an "ERRORED (dropped)"
count. A silent drop can no longer masquerade as a clean sweep. Corpus is **19
docs** on machine B (the arch doc's "27" is stale). Deterministic pass: 19/19
`needs_review`, all missing `effective_date` + `checksum_sha256` (checksums are a
separate source-identity backfill, not the validator's job).

## Machine-B correction — `-vN` is a PDF part, not a version

Domain correction from the owner: `city-of-dallas-ordiance-v1/v2/v3` are **parts
of one oversized PDF** split for ingestion, not superseding versions. The arch
doc (and the Phase 2 q6 notes) assumed a supersession family — wrong.
`detect_supersession_candidates` was flagging them off the `-vN` suffix, a false
positive (the validator's tracked false-flag rate). Fixed: `_strip_version_tag`
now strips **only** the `-YYYYMMDD` datestamp — the suffix
`governance.rescrape_document` actually appends on a changed re-pull — and leaves
`-vN` intact. Test `test_supersession_ignores_version_part_suffixes` asserts the
`-vN` family is NOT grouped; the datestamp test stays. arch doc + STATE punch
item 2 corrected. Also this session: LLM parse failures now **degrade to the
deterministic result** (never drop the doc) with an `llm_note`; `max_tokens`
4096; excerpts capped short + quote/newline-free to stop the JSON truncation on
verbose ordinance docs. Suite **440**.

## Deployment + iteration on prod (2026-07-24, later)

Phase 3 merged to `deployment/sites` and GHA-deployed; `/admin/agents` is live on
prod. `agents/phase-3` re-synced with `deployment/sites` (merge commit) so the
feature branch is not stale. Suite is **442** after the additions below.

**Machine-B live validator dry-run — 19/19 clean.** After the `temperature`,
truncation, and `-vN` fixes: all 19 docs `needs_review`, cited proposals, zero
drops, zero supersession false-flags. Correct high-conf dates:
`texas-accessibility-standards` / `ADA-Standards` → 2012-03-15 (0.95 / 0.75). The
recent low-conf dates (Dallas ordinances, ftworth) read as scrape/"current
through" dates — reject on review. `checksum_sha256` null on all 19 (separate
source-identity backfill, not this agent).

**Post-deploy fixes/additions (all on prod):**
- `list_action_items` `source_agent` param cast to `::text` — a null agent
  filter (the Action Queue tab) was erroring with "could not determine data type
  for parameter $2". DB-integration bug the mocked tests can't catch; matches the
  working cast at `db/client.py:816`.
- Metadata Review: **proposed values are double-click editable**; the edit is
  what gets written on approve (`subject_tags` as a comma list; dates/enums as
  text). Card/table spacing tidied.
- New **Documents** tab + `GET /admin/agents/documents` — read-only corpus
  metadata view (all statuses), null date / missing checksum / draft highlighted.

## Operational tail — DONE (2026-07-24)

Migration 028 applied on prod RDS; backfill `--apply` run against prod (filed the
review items + verification rows); the good proposals approved in `/admin/agents`
— corrected `effective_date`/tags written through
`governance.apply_metadata_correction`. **Phase 3 is complete end-to-end:** built,
tested (442), deployed, and the prod corpus metadata is now corrected.

## Still open (not Phase 3)

- `checksum_sha256` backfill (source-identity) — separate, all 19 docs.
- q6 / Dallas ordinance is a **retrieval** problem (answer spans 3 PDF parts),
  not supersession — corrected in the arch doc; a Phase 4+ retrieval concern.
- Fresh live RAGAs baseline before RAGAs gates anything.

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
py -m pytest tests/ -q                 # expect 442 passed
py scripts/verify_phase2.py --no-db    # 18/18, incl. the anthropic grep
```

## Commit messages (this session)

```
feat: Phase 3 Corpus Metadata Validator + governance write path + superadmin dashboard v1
fix: metadata validator surfaces LLM-dropped docs, raises assessment max_tokens to 2048
fix: metadata validator degrades to deterministic on LLM parse failure; max_tokens 4096, shorter excerpts
fix: metadata validator — no supersession false-flag on -vN part suffixes
hotfix: cast list_action_items source_agent param to text so a null agent filter doesn't error
feat: inline-editable proposed values in metadata review; tidy card/table spacing
feat: superadmin read-only corpus metadata view (Documents tab)
```

## Prompt for next session

> Read STATE.md, the latest `journals/session_*.md`, AGENTS.md, and
> docs/agent_architecture.md before touching anything. Restate the current task
> first — AGENTS.md pre-session protocol.
>
> **Machine A (this repo) has an EMPTY database and no `documents/raw/`.** Only
> these work here: `py -m pytest tests/ -q` (442, fully mocked),
> `py -m ruff check rag/ tests/`, `py scripts/verify_phase2.py --no-db`. Anything
> DB/corpus-dependent (validator, backfill, migration apply,
> `check_migration_details`, RAGAs) runs on machine B — collect it into ONE block.
>
> **Phase 3 is SHIPPED and deployed** — Corpus Metadata Validator (agent #13) +
> backfill + superadmin dashboard v1 (`/admin/agents`: action queue,
> inline-editable metadata review, read-only Documents view). Machine-A 442 tests
> + `verify_phase2 --no-db` 18/18; machine-B validator dry-run 19/19 clean; live
> on prod. **Do not rebuild it.**
>
> **First, finish the Phase 3 operational tail on prod** (STATE punch item 1 —
> this is corpus work through the shipped tool, not code): apply migration 028 to
> prod RDS, run `ENVIRONMENT=production py scripts/backfill_document_metadata.py
> --apply --report`, then approve the good proposals in `/admin/agents` (the two
> 2012-03-15 ADA/TAS dates; edit/reject the recent low-conf dates and lossy tag
> sets). That writes the corrected metadata through `governance.apply_metadata_correction`.
>
> **Then start Phase 4 — Prompt Router + fragment library + Media Curator** (its
> own chat, own branch, migration **029**). `rag/agents/prompt_router.py` composes
> the system prompt from versioned fragments (persona ∥ jurisdiction ∥ intent ∥
> experience ∥ bounded project notes) by lookup, not an LLM call; author the
> persona playbooks; demote `projects.custom_system_prompt` to bounded notes; wire
> the **`research` default** (never `diy`) + Clarification nudge; make `max_tokens`
> persona/intent-aware (kill the hard-coded 1024 that truncates `diy`/`hiring_contractor`
> at `rag/generator.py`) and make `stop_reason == "max_tokens"` a Guardrail trip
> that files an action item. This is the highest demo-value phase (one question,
> three personas, three genuinely different answers).
>
> Carried, still open: `checksum_sha256` backfill (source-identity, separate); a
> fresh **live** (`--no-answer-cache`) multi-sample RAGAs baseline before RAGAs
> gates anything (judge swings ±0.15 on one query); q6/Dallas is a retrieval
> (3-part PDF) problem, not governance.
```
