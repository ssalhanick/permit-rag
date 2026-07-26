# Session 2026-07-26 (cont.) — Phase 5 deploy + answer-agent wiring

Continuation of the Phase 5 build. Repo work on machine A (macOS); prod DB ops on
the user's Windows machine against the real RDS.

## Accomplished

### Deployed the feedback loop + dashboard v2 to prod
- Migration `033_answer_feedback` applied on the **real RDS**; `76aa291`+`ead0fe4`
  merged to `deployment/sites`, GHA green. `/admin/agents` shows Scorecard /
  Corrections / Autonomy.
- **Loop verified end-to-end on prod:** a 👎 ("ceiling fan is in the corpus") →
  `review_feedback.py --apply` → attributed `agent_corrections` → confirmed in the
  dashboard Corrections tab.

### RDS-from-laptop lesson (cost real debugging time; now recorded)
`ENVIRONMENT=production` did **not** reach the RDS — that machine's `.env.production`
host is the in-VPC `permit-rag-postgres`, a *different* local DB, so
`review_feedback.py` under it found "0 un-reviewed down-votes" while the vote was
on the RDS. Fix: the real DSN is
`postgresql://postgres:<SSM /permit_rag/prod/db_password>@<rds_endpoint>/permit_rag?sslmode=require`
(`terraform output -raw rds_endpoint` / `-raw db_password`), passed via
`--database-url`, from an SG-allowlisted IP (campus/home only, `terraform/main.tf`).
The raw `inet_server_addr()` private IP is not routable. Recorded in STATE decisions
log + the `permit-rag-db-target-drift` memory. Also audited every prod DB op from
journals 0721+ — the app being healthy (docs=19, media live, votes land) proves the
real RDS has migrations 022→033; the wrong-DB laptop ops were idempotent/harmless.

### Wired two of the three answer agents into the live path
- **Citation Verifier #9** — new Manager **wave 5** `_verify_citations`:
  deterministic (`use_llm=False`, $0, no latency) over the settled answer + the
  exact chunk set (`state.answer_chunks`); surfaces **fabricated citations** (a claim
  citing a chunk retrieval never returned) as `AnswerResponse.unsupported_citations`
  + an amber QueryPage banner. Can't regress RAGAs (that harness bypasses the
  Manager). `tests/test_citation_wire.py` (2: clean → none, fabricated → flagged).
- **Permit Strategy #11** — `GET /projects/{id}/permit-strategy` (membership-gated,
  deterministic `plan_permits(use_llm=False)`) + a "Permit strategy" panel on the
  project dashboard (`fetchPermitStrategy`). `tests/test_permit_strategy_route.py` (4).

### Deferred (user decision): Query Deconstructor #5
The retrieval-fan-out rewrite is the one change that alters the live retrieval
flow and can only be quality-validated on the real corpus (RAGAs bypasses the
Manager; machine A has no corpus). Tracked as the next answer-agent wire — build
gated + validate on machine B before deploy.

## Verification (machine A)
`py -m pytest tests/ -q` → **581 passed** (was 575; +2 citation-wire, +4
permit-strategy-route). New files ruff-clean; `frontend/ npm run build` clean.

## Commit message (this continuation)
```
feat(phase5-wire): Citation Verifier #9 into Manager wave 5 (unsupported_citations) + Permit Strategy #11 endpoint/panel (GET /projects/{id}/permit-strategy) — #5 Deconstructor deferred; 581 pytest green
```

## Prompt for next session
> Read STATE.md, the latest `journals/session_*.md`, AGENTS.md before touching
> anything. Restate the task.
>
> Phase 5 is largely done and mostly deployed. Remaining:
> 1. **Deploy the #9/#11 wire (code-only, no migration):** commit, then
>    `git checkout deployment/sites && git merge --ff-only agents/phase-5 && git push
>    origin deployment/sites` → GHA. Smoke a fabricated-citation banner + the project
>    "Permit strategy" panel on prod.
> 2. **Wire #5 Query Deconstructor** behind a conservative gate (simple queries
>    byte-identical; only compound queries fan out one retrieval per sub-question →
>    merge/dedup/re-rank/ground). Validate on **machine B**: `test_query_answer_route`
>    green + RAGAs (`--no-answer-cache`) unchanged + hand-check compound queries.
>    Do NOT merge to `deployment/sites` until that passes.
> 3. **Machine B eval loops:** `run_agent_eval.py` over real traces (with the real
>    RDS `--database-url`), and the **multi-sample live RAGAs baseline** (run 3+,
>    average out q6's ±0.15), then repoint `eval_guard` off `ragas_20260531`.
>
> RDS access from a laptop: use `--database-url` with the terraform endpoint + SSM
> password from an allowlisted IP — NOT `ENVIRONMENT=production` (see STATE decisions
> log / the db-target-drift memory).
