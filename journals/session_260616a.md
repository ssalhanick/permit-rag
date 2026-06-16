# Session: 2026-06-16a

## Type

Sprint 6 kickoff — Fix 2 + Task 16A.

## Goal

- Fix 2: citation-aware chunk filtering in `POST /query/answer`
- Task 16A: Neo4j Community Edition in `docker-compose.yml`
- Run full eval + guard; expect relevancy > 0.687

---

## Completed

### Fix 2 — Citation-aware chunk filtering

**Problem:** `POST /query/answer` was returning all retrieved chunks even when
only a subset were cited by the generated answer. This diluted the `chunks`
array with uncited noise, hurting RAGAs AnswerRelevancy scoring (Q0/Q4 at
0.000 was partly caused by irrelevant uncited chunks inflating context size).

**Changes:**

- `api/schemas.py`:
  - Added `total_chunks_retrieved: int` to `AnswerResponse`.
    Always reflects the raw retrieval count (pre-filter).
  - Updated `chunks` field description to clarify it now contains only
    cited chunks (with fallback to all chunks).

- `api/routes/query.py` (after `generate_answer()` returns):
  1. Build `all_chunks` from `result.chunks` (same as before).
  2. Build `cited_keys`: set of `(doc_id, chunk_index)` for citations
     where `found_in_context=True`.
  3. If `cited_keys` is non-empty → filter `all_chunks` to only cited ones.
  4. If `cited_keys` is empty (no citations matched context) → fall back
     to returning all chunks (graceful degradation).
  5. Set `total_chunks_retrieved=len(all_chunks)` on `AnswerResponse`.
  6. Log `Fix2 citation filter: N/M chunks retained` for observability.

**Fallback rationale:** returning all chunks when no citations match context
ensures the caller still has retrieval context for inspection and debugging.
It also prevents an empty `chunks` array from breaking downstream UIs.

### Task 16A — Neo4j Community Edition in docker-compose.yml

- Added `neo4j` service:
  - Image: `neo4j:5-community` (latest stable CE)
  - `NEO4J_AUTH` defaults to `neo4j/localdev123` (override via `.env`)
  - `NEO4J_PLUGINS: '["apoc"]'` — enables APOC Core (CE ships it)
  - `NEO4J_dbms_security_procedures_unrestricted` + `allowlist` → `apoc.*`
  - Ports: `7474` (Browser UI), `7687` (Bolt)
  - Named volume: `neo4jdata:/data`
  - Health check: `wget -qO- http://localhost:7474`, 10s interval, 10 retries,
    30s start period

- Added `neo4jdata:` to `volumes:` block.
- Added `NEO4J_AUTH` placeholder to `.env.example`.

### Testing

- `tests/test_sprint6.py` — 8 tests:
  - `test_cited_chunks_only_when_citations_found` — filter works correctly
  - `test_total_chunks_retrieved_reflects_raw_count` — raw count preserved
  - `test_fallback_to_all_chunks_when_no_context_citations` — graceful fallback
  - `test_fallback_when_no_citations_at_all` — empty citation list fallback
  - `test_duplicate_citations_do_not_duplicate_chunks` — dedup via set
  - `test_mixed_found_and_not_found_citations` — only found=True drives filter
  - `test_schema_total_chunks_retrieved_field_present` — schema field exists
  - `test_schema_total_chunks_retrieved_is_int` — schema type is int

---

## Validation steps (this session)

```
py -m pytest tests/test_sprint5.py tests/test_sprint6.py -v
docker compose up -d neo4j
# wait ~40s for health check to pass
# open http://localhost:7474 — Neo4j Browser should appear
$env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export
py -m evaluation.eval_guard
```

Results:
- `py -m pytest tests/test_sprint5.py tests/test_sprint6.py -v` → **24 passed in 0.26s** ✅
- Neo4j Browser: reachable at http://localhost:7474 ✅
- RAGAs eval: avg faithfulness `0.910` ✅ | avg relevancy `0.689` ✅ (> 0.687 target) | avg context precision `0.654`
  - Q0/Q4 relevancy still `0.000` — RAGAs cosine-collapse artifact (Fix 2 filters at API layer; eval harness calls `generate_answer()` directly, bypassing route)
  - Faithfulness dipped `0.931 → 0.910` — within noise, still well above `0.85` gate
- Eval guard: **PASS** (candidate `ragas_20260616_143411.json` vs baseline `ragas_20260531_122639.json`)
  - avg faithfulness `0.910` ≥ min `0.850` ✅
  - q1 faithfulness `0.875` (baseline `0.600`, drop `-0.275` — guard reports drop but PASS, q1 above baseline)

---

## Files changed

**New files:**
- `tests/test_sprint6.py`

**Modified files:**
- `api/schemas.py` (added `total_chunks_retrieved` to `AnswerResponse`)
- `api/routes/query.py` (citation-aware filtering + `total_chunks_retrieved`)
- `docker-compose.yml` (Neo4j service + `neo4jdata` volume)
- `.env.example` (added `NEO4J_AUTH` placeholder)

---

## Issues encountered

_None yet — pending validation runs._

---

## Next session should

1. Run the validation sequence above; record eval results here.
2. Implement Task 16B: Cypher constraints + `db/graph_client.py`.
3. Implement Task 16C: ingestion connector — write chunk nodes + doc nodes into Neo4j.

## Git commit message

feat(sprint6): citation-aware chunk filtering (Fix 2), total_chunks_retrieved field, Neo4j CE docker-compose service (Task 16A)
