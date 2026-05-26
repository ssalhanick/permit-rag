# permit_rag — Agent Rules

## Identity

You are working on permit_rag, a RAG-powered construction permit
compliance tool for the DFW market. Contractors and project managers
query it to get cited answers from Dallas, Plano, Frisco, McKinney,
and Fort Worth municipal codes, plus Texas state and federal regs.

---

## Pre-Session Protocol (mandatory, no exceptions)

1. Read STATE.md in full
2. Read the most recent journals/session\_{date}.md
3. Restate the current blocker or next task before touching anything
4. If STATE.md and the journal conflict, the journal wins

---

## Code Rules

- Python 3.11+ only — no walrus operator abuse, no 3.10 match hacks
- Every function: type hints + docstring + max 50 lines
- Write the test before or immediately after every new function
- No hardcoded secrets, URLs, or credentials — .env only
- No inline supabase calls — go through db/client.py exclusively
- No inline anthropic calls — go through rag/generator.py exclusively
- All git commands will be run manually, though I will ask for assistance and may need clarification on git best practices
- All python module terminal commands will be run manually (I'll run them after you generate them)
- If you want me to run an ad hoc terminal command, please provide the full command in a single line for me to paste into the terminal.
- At the end of a session, write a prompt for the next session and a single line git commit message summary of the session. It can be long, but it has to be a single line.

---

## Import Boundaries (never cross these)

```
ingestion/  →  may import: db/, standard library only
rag/        →  may import: db/, audit/, standard library only
api/        →  may import: rag/, db/, audit/, standard library only
audit/      →  may import: db/, standard library only
evaluation/ →  may import: rag/, db/, standard library only
scripts/    →  may import: anything (one-off use only)
```

---

## RAG Quality Rules

- Never change pipeline.py without running RAGAs immediately after
- Faithfulness must clear 0.85 before any customer demo
- Every generated answer must include at least one citation
- Superseded documents must never be the sole source of an answer
- Chunk conflicts must surface a ConflictWarning — never silently resolve

---

## Document Governance Rules

- Never delete a document — supersede or repeal only
- Never ingest without full metadata (municipality, effective_date,
  authority_level, doc_type, review_due, checksum)
- Source URL changes → flag for human review, never auto-update
- registry.json is modified only via governance.py, never by hand

---

## State and Journal Rules

- Update STATE.md at end of every session — no exceptions
- Write journals/session_YYYY-MM-DD.md at end of every session
- Decisions (library choices, schema changes, arch calls) → STATE.md
  decisions log immediately, not retroactively
- Blockers → STATE.md immediately, stop work until documented
- Completed work → journal only, remove from STATE.md task queue
- At end of session, provide a `prompt for next session`

---

## Never Do These

- Never modify a migration after it has been deployed
- Never commit documents/raw/, .env, **pycache**, node_modules
- Never run a harvest or embed job without checking budget in STATE.md
- Never leave STATE.md stale — if you touched the project, update it
- Never guess at a governance decision — check AGENTS.md first,
  then ask if still unclear
