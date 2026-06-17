# Session: 2026-06-16c

## Type

Sprint 8 — Task 16F.

## Goal

Tag cited `Chunk` nodes in Neo4j with query-signal metadata after every `/query/answer` call.

---

## Completed

### Task 16F — Graph citation signals

**Problem:** After a `/query/answer` call the graph had no knowledge of which chunks were
actually cited in the generated answer. There was no feedback loop from retrieval quality
back into the graph — every node was equally "unvisited."

**Design decisions:**

- New `(:Query)-[:CITED]->(:Chunk)` edge — a `Query` node is keyed on `(session_id, cited_at)`
  so repeated calls within a session produce distinct nodes.
- Chunk nodes receive three new optional properties updated by every citation event:
  `last_cited_at`, `last_cited_query`, `citation_count` (incremented via `coalesce(c.citation_count, 0) + 1`).
- Called via FastAPI `BackgroundTasks` — fires **after** the HTTP response is sent.
  Zero latency impact on the caller.
- **Non-raising contract** preserved: all exceptions caught at WARNING level.
  Graph down = log entry, answer still returned.
- Import boundary respected: `db.graph_client` is lazy-imported inside the background
  task closure; `api/routes/query.py` does not add a module-level `db` import.

**Behavior matrix:**

| cited_keys | Neo4j | BackgroundTask scheduled | Graph write |
|------------|-------|--------------------------|-------------|
| non-empty  | ✅     | ✅                        | ✅ Chunk nodes stamped |
| non-empty  | ❌     | ✅                        | ❌ WARNING log, no raise |
| empty      | any   | ❌                        | — skipped entirely |

**Changes:**

- `db/graph_client.py`:
  - Added `record_cited_chunks(*, query_text, session_id, cited_pairs, cited_at_iso)`.
  - No-op when `cited_pairs` is empty (skips session open entirely).
  - Cypher: `MERGE (:Query {session_id, cited_at})` → `UNWIND cited_pairs` →
    `MATCH (:Chunk {doc_id, chunk_index})` → `MERGE (:Query)-[:CITED]->(:Chunk)` →
    `SET c.last_cited_at, c.last_cited_query, c.citation_count += 1`.
  - `cited_pairs` serialised as `list[list]` (not tuples) — Neo4j driver requirement.

- `api/routes/query.py`:
  - Added `datetime, timezone` import.
  - Added `BackgroundTasks` to FastAPI import + `query_answer` signature.
  - After `cited_keys` is built (the existing Fix-2 citation filter block),
    schedules `record_cited_chunks` as a background task when `cited_keys` is non-empty.
  - Lazy `from db import graph_client as _gc` inside the scheduling block
    (preserves `api/ → db/` import boundary, avoids module-level coupling).

---

### Testing — tests/test_sprint8.py (12 tests)

**record_cited_chunks() unit tests (10):**

- `test_function_exists_and_is_callable` — importable
- `test_accepts_expected_keyword_args` — signature has all 4 kwargs
- `test_noop_on_empty_cited_pairs` — driver.session never opened
- `test_session_run_called_with_pairs` — run() called when pairs given
- `test_session_id_passed_to_cypher` — session_id in Cypher kwargs
- `test_cited_pairs_serialised_as_lists` — inner elements are lists not tuples
- `test_query_text_passed_to_cypher` — query_text forwarded
- `test_does_not_raise_on_connection_error` — ConnectionError silenced
- `test_does_not_raise_on_run_exception` — run() RuntimeError silenced

**query_answer BackgroundTask wiring tests (3):**

- `test_background_tasks_param_accepted` — signature check
- `test_background_task_scheduled_when_cited_keys_exist` — add_task called
- `test_background_task_not_scheduled_when_no_cited_keys` — add_task NOT called

---

## Test results

```
py -m pytest tests/test_sprint5.py tests/test_sprint6.py tests/test_sprint7.py tests/test_sprint8.py -v
72 passed in 18.52s ✅
```

| Sprint | Tests | Status |
|--------|-------|--------|
| Sprint 5 | 16 | ✅ PASS |
| Sprint 6 | 24 | ✅ PASS |
| Sprint 7 | 20 | ✅ PASS |
| Sprint 8 | 12 | ✅ PASS |
| **Total** | **72** | ✅ |

---

## Files changed

**New files:**
- `tests/test_sprint8.py`
- `journals/session_260616c.md`

**Modified files:**
- `db/graph_client.py` (added `record_cited_chunks()`)
- `api/routes/query.py` (BackgroundTasks wiring for Task 16F)
- `README.md` (current status → Sprint 8)
- `STATE.md` (Sprint 8 task tracking)

---

## Validation steps run this session

1. `Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get` → `status=healthy graph_health=True` ✅
2. `py -m evaluation.eval_guard` → avg faithfulness `0.910` ≥ `0.850` ✅ **PASS** ✅
3. `py -m pytest tests/test_sprint8.py -v` → **12 passed** ✅
4. `py -m pytest tests/test_sprint5.py tests/test_sprint6.py tests/test_sprint7.py tests/test_sprint8.py -v` → **72 passed** ✅

## Git commit message

feat(sprint8): graph citation signals via BackgroundTasks (16F) — record_cited_chunks stamps Chunk nodes + CITED edges after /query/answer

---

## Next session should

1. Run live validation: `Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get` → confirm `graph_health=True`
2. Run `py -m evaluation.eval_guard` to confirm no RAGAs regression
3. Sprint 8 — BM25 A/B eval: run hybrid vs dense-only retrieval evaluation with `RETRIEVAL_HYBRID_ENABLED=true` and compare faithfulness/relevancy delta
4. Sprint 8 — Add remaining 8 DFW city boundary layers to PostGIS (backlog)

## Prompt for next session

Read `AGENTS.md`, `STATE.md`, and `journals/session_260616c.md`. Sprint 8 Task 16F is complete (graph citation signals). Continue Sprint 8:

Run live validation first:
- `Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get` (expect `graph_health=True`)
- `py -m evaluation.eval_guard`

Then start the BM25 A/B eval: set `RETRIEVAL_HYBRID_ENABLED=true` and run a full RAGAs eval, compare faithfulness/relevancy/context_precision against the dense-only baseline in `evaluation/results/ragas_20260531_122639.json`. Document the delta in the session journal and decide whether to promote hybrid as the default.
