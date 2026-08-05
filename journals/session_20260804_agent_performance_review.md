# Session 2026-08-04 — Agent performance review (Manager + live sub-agents, ~1.5 weeks post Phase-5 launch)

Runs on `agents/review`, cut fresh from the tip of `deployment/sites` (zero
divergence either direction at start) — kept off `fix/room-scan` and other
in-flight branches on purpose. Most recent prior journal entries:
`journals/session_20260801.md` (19-item bug-triage batch, branch
`fix/room-scan`, closed out 2026-08-02 per its commit) and STATE.md's own
`2026-08-02` header (system & migration health check — no separate journal
file was written for that session; a pre-existing documentation gap, not
this session's to fix).

## Scope and framing

Scott asked for a real performance review of the Manager and the other live
agents "since launch" (~1 week), plus updated directions where warranted —
not a vibe check. permit_rag runs a genuine hand-rolled multi-agent
architecture (`rag/agents/manager.py` orchestrating ~12 live sub-agents),
shipped in phases through **2026-07-26** (Phase 5 — feedback loop, dashboard
v2, Citation Verifier, Permit Strategy) — 9 days before this session, close
enough to "about a week" for the framing to hold. Document-upload/chunking
work is separate and more recent (07-30/07-31); expected to be quiet, and it
is.

This checkout's local DB is empty (STATE.md's own verification table), so
this session split into two parts:
- **Part A** (this document): everything answerable with zero DB access —
  the real RAGAs eval history, facts already on record in STATE.md/AGENTS.md,
  and a code-level design read of every live agent.
- **Part B** (handed off, §6): the two batch scripts that grade agents
  against real trace/feedback data need to run wherever that data actually
  lives — commands below, no DB access attempted from this session.

## Summary

- **Found a live, currently-exposed prod database credential committed to
  git** (§0) — unrelated to the agent review itself, discovered while
  checking on migration 045's status. Flagged to Scott directly in chat;
  not remediated by this session pending his direction (rotating a prod
  password and/or rewriting pushed history are both his call).
- No hard failures found among the live agents. The Manager's
  degrade-gracefully posture (every non-critical step wrapped and defaulting
  safely) is working as designed.
- **One real, evidence-backed instruction gap found and fixed**: the Frisco
  and McKinney prompt fragments told the model to "apply [city] ordinance
  amendments" despite zero real ingested content for either — contradicted
  AGENTS.md's own documented caveat. Fixed (§3).
- **One live data-quality trap found in the eval tooling itself**: "latest"
  RAGAs export can resolve to an abandoned, reverted experiment rather than
  what's actually deployed (§1) — true of the 07-31 file at the time this
  was checked; superseded by the 08-02 run, see §1's note. Not a code bug —
  flagged so nobody trusts "latest" blind going forward.
- **One stalled human queue found**: a metadata backfill has sat unreviewed
  in `/admin/agents` for 9+ days (§2). The agent did its job; a human didn't
  clear the queue.
- **Real per-agent traffic numbers (calls, error rate, correction rate)
  don't exist yet in a place this session can reach** — handed off as exact
  commands, not run here (§6).
- **Migration 045's status is better than STATE.md's punch list currently
  says** (§5) — a post-045 RAGAs run already happened 2026-08-02
  (`ragas_20260802_034009.json`) and shows no regression, but it doesn't
  actually exercise the private-document scenario the fix targets. STATE.md
  updated to reflect this precisely rather than leaving the stale "not
  RAGAs-verified" claim standing.
- **`py -m pytest tests/ -q` initially looked hung (20+ min, then Scott's own
  concurrent run got OOM-killed) — resolved** (§7). Root cause was mundane:
  Docker Desktop's daemon wasn't running (6 tests need a real Postgres
  connection and were burning 30s pool timeouts each), a real gap in
  `rag/permit_classifier.py`'s NLI-model path with no suite-wide guard against
  it (this repo had no `tests/conftest.py` at all — added one), and most of
  the apparent hang was this session's own diagnostic runs competing with
  Scott's simultaneous terminal invocation on the identical machine. With
  Docker up and nothing running concurrently: **832 passed, 0 failed, 22s.**

## 0. Urgent, out-of-scope finding: a live prod DB password is committed to git

Discovered while checking whether migration 045 had been verified yet (§5),
not part of this review's original scope — surfacing it first because it's
time-sensitive.

`evaluation/results/reprocess/20260802_101100/reprocess_20260802_101100_report.txt`
and the paired `.log` file (committed in `a53f476`/`ca81c3e`, 2026-08-02)
contain the full prod RDS connection string **in plaintext, including the
password**, logged by `scripts/reprocess_corpus.sh`/`.ps1` when it printed
its own invocation args. Both files are tracked (not gitignored) and
**already pushed to `origin/deployment/sites`** — confirmed
`git merge-base --is-ancestor` against `origin/deployment/sites` returns
true, and local/remote are at the identical commit. This violates AGENTS.md's
"No hardcoded secrets, URLs, or credentials — .env only" rule directly, and
the exposure is live, not historical (the password in the file is presumably
still the real prod password until rotated).

**Not remediated by this session.** Rotating the RDS password is an
infrastructure action (`terraform apply` or AWS console), and scrubbing an
already-pushed secret from git history is a destructive, hard-to-reverse
operation affecting shared history — both are Scott's call, raised directly
in chat rather than acted on unilaterally. The likely code fix (whatever
prints "DB target args" in the reprocess scripts should redact the password
before writing to a tracked report/log) is small and safe to do once he
decides how he wants the existing exposure handled.

## 1. Retrieval / Answer Generator — quality trend

The Evaluator's only two agent-specific metric contracts
(`evaluation/agent_eval.py`) are `answer_generator` (RAGAs faithfulness
≥0.85) and `prompt_router` (see §3). Both are checkable, at least partly,
without a DB: `evaluation/results/*.json` holds 52 real timestamped RAGAs
runs back to 2026-05-29, 14 of them from 07-25 onward.

Faithfulness swung **0.79–0.94** across the review window — expected
volatility on a 7-fixed-query set, consistent with STATE.md's own "measure,
don't gate" decision (single-shot RAGAs swings ±0.15).

**The finding, and how it resolved:** `evaluation/agent_eval.py`'s
`_latest_faithfulness()` reads `eval_guard._latest_ragas_export()` —
whatever file is chronologically newest. When first checked this session,
that was `ragas_20260731_165237.json` (avg faithfulness **0.885**) — the
**chunking-step-3 experiment STATE.md documents as a STOP-SHIP regression
that was reverted** in prod, not the deployed step-2 config's real,
user-confirmed **0.937**. Both clear 0.85, so nothing was on fire, but it
was silently grading an abandoned corpus state. That specific gap is now
moot — `ragas_20260802_034009.json` (2026-08-02, post-migration-045) is now the
latest file and reads **0.935**, consistent with the deployed config, not
the reverted one. The underlying mechanism (latest-by-timestamp ≠
latest-deployed) is still true and will resurface the next time an
experiment gets tested and reverted — see STATE.md punch #3(c).

**Recommendation unchanged:** this reinforces STATE.md's own open punch-list
item #3(b) — establish the multi-sample **live** baseline before trusting
this contract check unattended.

## 2. Corpus Metadata Validator (#13) — stalled review queue

No query needed — already on record in STATE.md's migration-drift table: a
backfill ran on the corpus machine 2026-07-26 and its proposals are **still
sitting unapproved in `/admin/agents`, now 9+ days later**.

Read charitably, this is a finding about the human side of the loop, not the
agent: the Validator proposed corrections correctly; nobody has cleared the
queue since. Worth clearing before it gets stale enough that a reviewer has
to re-derive context to trust an old proposal.

## 3. Prompt Router (#2) — updated directions, and why

`rag/prompts/fragments/jurisdiction/frisco.md` and `.../mckinney.md` (both
still `<!-- version: 1 -->`, unedited since authoring) read:

> "Apply [City] ordinance amendments over the base code, and flag where
> [City] differs from state or model code in the cited text."

That instruction presumes jurisdiction-specific text exists to cite. It
doesn't: AGENTS.md's own Identity section is explicit — "Frisco and McKinney
are seeded jurisdictions with no real ingested documents yet ... do not
describe them as covered until that changes" — and `docs/backlog.md`'s
boundary-load table independently shows both still `⬜ Pending`. This is a
real, live instruction gap between what the Prompt Router hands the Answer
Generator and what AGENTS.md says is actually true, for two jurisdictions a
user can genuinely reach (both are real entries in jurisdiction resolution,
not hypothetical).

**Fixed this session** — both bumped to `<!-- version: 2 -->` (the project's
own fragment-iteration convention, STATE.md decisions log), rewritten to
state plainly that no jurisdiction-specific ordinance text is ingested for
that city yet, so any retrieved chunk is general/state-level and the model
should say so rather than imply a local amendment — leaning on `base.md`'s
existing grounding rules 5/6 (name the jurisdiction chunks actually apply to;
say so when context is insufficient) instead of fighting them.

**Cross-checked the other five jurisdiction fragments** (Dallas, Fort Worth,
Plano, Texas, Federal) against real cited `doc_id`s in the RAGAs results
(`city-of-dallas-ordiance-v3`, `plano-4`, `ada-design-standards`, etc.) —
all five are backed by real ingested content and their "apply amendments"
language is accurate as written. No change needed there.

**Audited every other fragment** (all `persona/*.md`, `intent/*.md`,
`experience/*.md`) for the same kind of claim-vs-reality gap. Nothing else
turned up — all read as accurate and appropriately hedged (cost estimates
labeled as estimates, form-fill requiring human review before filing, DIY's
safety gate naming what's not DIY, etc.).

**On verification**: none of the fixed 7-query RAGAs eval set targets Frisco
or McKinney, so this change won't move that number — it's a
governance/clarity fix, not a retrieval-quality one. Real verification is a
manual hand-check the next time a Frisco/McKinney query is tried (should
abstain or clearly caveat, never imply a local amendment that doesn't
exist), not a RAGAs gate. `tests/test_prompt_router.py` (25 tests) passed
unchanged after the edit — nothing asserts on the old fragment text.

**Design note, code-confirmed**: `rag/agents/prompt_router.py::route()` never
calls a model under any condition — a missing fragment is recorded (a
Crystallizer signal) and skipped, not filled in by an LLM call. So the
Evaluator's `deterministic_rate == 1.0` contract for this agent is satisfied
**by construction** today, not just empirically. Worth confirming against
real trace data once Part B lands, but there is currently no code path
capable of breaching it.

## 4. Other live agents — design-level pass (not yet traffic-graded)

Grounded in the actual code (not just docs), read in full this session.
Labeled design-level because none of this is measured against real traffic
yet — that's Part B.

- **Manager (#1)** — 5-wave deterministic plan, `MAX_ITERATIONS=6` (nowhere
  close to hit by a 4-wave plan). Every non-critical step (permit
  classifier, jurisdiction resolver, conflict detectors, media curator, the
  deconstructor) is wrapped and degrades to a safe default on failure. Real
  failure modes are scoped tightly to retrieval and generation failure
  (500s); a grounding-floor miss is a deliberate soft-abstain, not an error.
  Sound v1 orchestrator design.
- **Guardrail (#4)** — only the truncation trip and the media-source gate
  are live under this module today (grounding floor/PII/injection still live
  inline in `query.py`/`manager.py` per its own docstring, pending a later
  migration). Both live checks are correctly non-blocking and never raise.
- **Citation Verifier (#9)** — deterministic span-match first (free); LLM
  entailment only on the ambiguous leftovers. Notably, a citation pointing at
  a chunk retrieval never returned is caught with **zero model calls** (the
  `missing_chunk` path) — the highest-value cheap check in the system for a
  compliance tool, and it already runs on every answer.
- **Permit Strategy (#11)** — fully deterministic permit set/sequence/fees,
  mirrors `frontend/src/projectPermitRules.js` by construction so the two
  can't drift; only the plain-language note is LLM-optional and degrades to
  a template on failure. Fees explicitly labeled estimates. No issues.
- **Media Curator (#17)** — only the curated `task_key` path (B1) is live;
  never fabricates a URL by construction (returns `[]` on no match, never a
  guess); correctly returns nothing for non-`diy` personas. `web_search` (B2)
  is future work, not a gap today.
- **Conflict Analyzer** — lightweight numeric cross-authority detector is
  live; a graph-backed (Neo4j) path exists and falls back transparently when
  Neo4j is unreachable. Worth confirming in Part B whether Neo4j is even
  provisioned in prod — if not, this agent has quietly been running the
  lightweight path exclusively, which is fine, just worth knowing which path
  is actually active before crediting the graph path with anything.
- **Budget Governor (#3)** — confirmed still uncapped by default
  (`AGENT_BUDGET_MAX_INPUT_TOKENS` unset) — a deliberate no-op per its own
  docstring. Model ladder is still advisory; `LLM_MODEL` wins over the tier
  decision intentionally (avoids a silent 3× cost jump). Nothing to fix;
  noting it so it isn't mistaken for dead code later.

## 5. Migration 045 — more resolved than STATE.md's punch list said

Not this review's original scope, but directly relevant since Part B (§6)
also needs Machine B, and checking on this is what surfaced §0. This
morning's — actually, three days ago's — bug-triage session
(`journals/session_20260801.md`) shipped a real security fix,
`045_match_chunks_visibility.sql`, closing a cross-tenant leak where another
user's private project document could surface verbatim in a chat answer. Its
own next-session prompt listed a RAGAs verification as the top priority.

That RAGAs run **already happened**: `ragas_20260802_034009.json`
(2026-08-02, `--no-answer-cache`), faithfulness **0.935** — consistent with
the pre-045 baseline (0.937), i.e. no regression to the general retrieval
path. STATE.md's punch list #5 still said "NOT yet RAGAs-verified" as of
this session's start; corrected below.

**Important nuance, not just a rubber stamp**: the fixed 7-query eval set has
no tier-3/private-document test case, so this run confirms migration 045
didn't break the *general* corpus path — it does not, and cannot, confirm the
fix actually blocks a cross-tenant leak, since that scenario was never in the
eval set to begin with. The real verification for the security property
itself is still a hand-check (two test users, one private doc, confirm it
doesn't surface in the other user's answer) — worth doing on Machine B
alongside Part B, distinct from the RAGAs number.

## 6. Part B — handed to Scott (needs the corpus machine)

Report-only, no `--apply`:

```bash
py scripts/run_agent_eval.py --local --days 7
py scripts/review_feedback.py --local --dry-run
```

(`--local` → `--database-url '<dsn>'` if `.env.local` isn't the right target
on that machine; `scripts/_db_target.py` prints a banner naming the actual
host either way.)

When the output is pasted back: fold real per-agent numbers (calls, error
rate, correction rate, deterministic rate) into this review, note any actual
contract breaches, and treat `--apply` (auto-demotes autonomy + files action
items) as a separate explicit decision afterward.

Full detailed Machine-B step-by-step — covering this review's Part B, the
migration-045 private-document hand-check (§5), and the credential rotation
(§0, pending Scott's direction) — handed to Scott directly in chat this
session.

## 7. pytest suite health — initially looked hung, actually three ordinary causes

Scott asked to confirm the suite passes clean before pushing anything. The
first full run looked like an indefinite hang (killed after 20+ min at ~17s
CPU time — mostly idle/waiting); his own concurrent run in a separate
terminal on this *same* machine (`hostname` confirmed both were `UTD95110`)
got OOM-killed after 54 tests. Bisecting down to a minimal reproducing pair
(`test_agent_manager.py` + `test_agents_admin_routes.py`) via `faulthandler`
stack dumps kept pointing at a heavy, slow import chain
(`torch`/`sklearn`/`pandas`/`sympy`), but that turned out to be a red herring
for the actual failures — three separate, ordinary things were stacked:

1. **Docker Desktop's daemon wasn't running at all** (not just the
   container) — 6 tests (`test_citation_wire.py`,
   `test_query_answer_route.py`) legitimately need `db/client.py`'s real
   connection pool and failed with `psycopg_pool.PoolTimeout` after the
   pool's 30s wait, hitting `127.0.0.1:5433` with nothing listening.
   `docker compose up -d` (per STATE.md's own "Is the container up?" hint)
   fixed all 6 immediately.
2. **A real, if smaller, gap**: `rag/permit_classifier.py` defaults to
   `use_nli=True`, and `rag/agents/registry.py` self-registers the real
   callable at import time — any test resolving `permit_classifier` from the
   registry without its own stub can trigger a real ~85MB HuggingFace NLI
   model load. `test_permit_classifier.py` already mocked this for itself;
   nothing else in the suite was guarded, and **this repo had no
   `tests/conftest.py` at all**. Added one with an autouse fixture patching
   `_load_nli_classifier` to `None` suite-wide — cheap, safe, real defense
   even though it wasn't the actual blocker.
3. **Most of the apparent multi-minute delay was this session's own repeated
   diagnostic pytest invocations competing with Scott's simultaneous
   terminal run** for the same CPU/RAM importing the same heavy libraries —
   not a deterministic per-file bug. Lesson: don't trust wall-clock
   bisection findings gathered under unknown concurrent load.

With Docker up and nothing else running: `py -m pytest tests/ -q` →
**832 passed, 0 failed, in 22.06s.**

## Files changed this session

- `rag/prompts/fragments/jurisdiction/frisco.md` — v1 → v2
- `rag/prompts/fragments/jurisdiction/mckinney.md` — v1 → v2
- `tests/conftest.py` — new; autouse fixture blocking the real NLI model load
- `STATE.md` — decisions log entries, Next tasks update, module status note,
  punch list #5 corrected and #7 (pytest hang) resolved and removed,
  new header entry, SECURITY section
- This file

4 commits, none pushed. Branch `agents/review`, cut from `deployment/sites`
tip. The credential-leak finding (§0) was **not** acted on — no file removal,
no history rewrite, no rotation — pending Scott's explicit direction.

## Prompt for next session

Re-read this journal, `journals/session_20260801.md`, and STATE.md's current
header, per AGENTS.md pre-session protocol. Priorities, in order:

1. **Decide on and execute credential remediation** (§0) — rotate the prod
   RDS password, decide whether to scrub git history or accept the exposure
   and just stop tracking the file going forward, and fix
   `scripts/reprocess_corpus.sh`/`.ps1` so it never logs a password into a
   tracked file again.
2. **Hand-check the migration-045 private-document scenario** (§5) — the
   RAGAs number is good but doesn't test the actual security property.
3. **Fold in Part B output** (§6) once Scott pastes back
   `run_agent_eval.py`/`review_feedback.py` results — real per-agent
   calls/error/correction numbers, any contract breaches, whether Neo4j is
   actually reachable in prod (§4).
4. **Establish the multi-sample live RAGAs baseline** (STATE.md punch #3(b),
   reinforced by §1) before trusting `run_agent_eval.py`'s faithfulness
   check unattended going forward.
5. Hand-check a live Frisco or McKinney query once real traffic/an
   opportunity exists, to confirm the v2 fragment reads as intended.
