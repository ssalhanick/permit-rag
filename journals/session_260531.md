# Session: 2026-05-31

## Type

Enhancement — hybrid retrieval hyperparameter sweep and gate verification follow-through.

## Goal

Tune hybrid dense+BM25 retrieval to recover faithfulness on queries 0,1,2,3 while preserving weak-query targeting on query 5, then decide rollout status.

---

## Completed

### Focused hybrid sweep + preview validation

- Used retrieval previews (`rag.pipeline`) for q0, q1, q2, q3, q5 to inspect top-10 context behavior under hybrid settings.
- Tested a dense-leaning RRF profile:
  - `RETRIEVAL_RRF_DENSE_WEIGHT=1.4`
  - `RETRIEVAL_RRF_BM25_WEIGHT=0.6`
  - `RETRIEVAL_DENSE_TOP_N=24`
  - `RETRIEVAL_BM25_TOP_N=10`
  - `RETRIEVAL_PROCEDURAL_PENALTY_ENABLED=true`
  - `RETRIEVAL_PROCEDURAL_PENALTY=0.02`
  - `RETRIEVAL_PROCEDURAL_MAX_HITS=4`
- Observed q5 retrieval targeting improvement (Dallas fire-code chunks dominant in preview output).

### RAGAs validation runs

- Ran focused subset:
  - `py -m evaluation.ragas_eval --query 0 1 2 3 5 --export`
  - output: `evaluation/results/ragas_20260530_232025.json`
- Ran full gate check:
  - `py -m evaluation.ragas_eval --export`
  - output: `evaluation/results/ragas_20260531_003019.json`
- Kept cache disabled during tuning runs:
  - `RAGAS_ANSWER_CACHE_ENABLED=false`

### State + config updates

- Updated `STATE.md` with:
  - focused and full-run metric deltas,
  - tested hybrid parameter profile,
  - per-query faithfulness changes,
  - explicit rollout decision to keep hybrid disabled.
- Updated `.env` to set:
  - `RETRIEVAL_HYBRID_ENABLED=false`

---

## Validation outcomes observed this session

- Focused subset run (`q0,q1,q2,q3,q5`):
  - avg faithfulness: `0.813`
  - q5 faithfulness: `1.000` (improved)
  - q1 faithfulness: `0.353` (major regression)
- Full 7-query run:
  - avg faithfulness: `0.798` (FAIL vs `0.85` gate)
  - avg relevancy: `0.824`
  - avg context precision: `0.603`
- Net result:
  - hybrid improves weak-query targeting on q5,
  - but q1 regression keeps full-suite faithfulness below gate.

---

## Next session should

1. Diagnose q1 regression under hybrid retrieval (cross-jurisdiction contamination in electrical permit answers).
2. Add retrieval-time source/authority guardrails for non-municipality queries.
3. Re-run `rag.pipeline` previews for q1/q5 and `ragas_eval` subset + full suite; only enable hybrid if avg faithfulness returns to >= 0.85.

## Prompt for next session

Read `STATE.md`, `journals/session_260529.md`, `journals/session_260530.md`, and `journals/session_260531.md`. Investigate why hybrid retrieval collapses faithfulness on query 1 (electrical permit query), implement retrieval-time source/authority guardrails for non-municipality queries to reduce cross-jurisdiction noise, and rerun `rag.pipeline` previews for q1/q5 plus `py -m evaluation.ragas_eval --query 0 1 2 3 5 --export` followed by `py -m evaluation.ragas_eval --export`. Record metric deltas in `STATE.md` and keep `RETRIEVAL_HYBRID_ENABLED=false` unless avg faithfulness returns to >= 0.85.

## Git commit message

chore(eval): record hybrid sweep regressions, gate results, and keep hybrid disabled
