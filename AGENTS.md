# permit_rag — Agent Rules

## Identity

You are working on permit_rag, a RAG-powered construction permit
compliance tool for the DFW market. Contractors and project managers
query it to get cited answers from Dallas, Plano, and Fort Worth
municipal codes, plus Texas state and federal regs. (Frisco and
McKinney are seeded jurisdictions with no real ingested documents yet
— see docs/backlog.md — do not describe them as covered until that
changes.)

## Response Style (token optimization)
- Bullets over prose; no restating context already established
- No preamble, no unprompted trailing summary
- One "Next:" line at the end — a single concrete action, not a menu
- Exception: genuine audits/reports where density would lose information —
  go long there, tight everywhere else

---

## Pre-Session Protocol (mandatory, no exceptions)

1. Read STATE.md in full
2. Read the most recent journals/session\_{date}.md
3. Restate the current blocker or next task before touching anything
4. If STATE.md and the journal conflict, the journal wins

---

## Post-Session Protocol (mandatory, no exceptions)
1. Do a health check of the readme file to make sure everything is documented and up to date based on the session we just finished.
2. Write a single line git commit message and put it in the session, as well as in the chat window.
3. Update the STATE.md file, removing unnecessary/outdated/deprecated documentation from the previous state. The state.md file should always include a checklist of deliverables and the validation/verification steps for the deliverables.
4. Update the session_{date}.md file with what was accomplished in the current session.
5. Write a prompt for the next session referencing what needs to be done, along with the state, previous session and agents.md file.

---

## Code Rules

- Python 3.11+ only — no walrus operator abuse, no 3.10 match hacks
- Every function: type hints + docstring + max 50 lines
- Write the test before or immediately after every new function
- No hardcoded secrets, URLs, or credentials — .env only
- No inline supabase calls — go through db/client.py exclusively
- No inline anthropic calls — go through `rag/agent_runtime.py` exclusively
  (the single Anthropic call site, Phase 1). `rag/generator.py` is the one
  remaining legacy call site; it is folded into the runtime in Phase 2.

---

## Command Execution

- Commits, pushes, merges, and deploys — always ask first, no exceptions.
  Scott is ultimately responsible if something breaks; he stays in control
  of anything that changes committed history or shipped state.
- Everything else (tests, lint, build, git status/log/diff, reads,
  migration files) — run directly, no need to ask.

---

## Import Boundaries (never cross these)

```
ingestion/  →  may import: db/, standard library only
rag/        →  may import: db/, audit/, standard library only
rag/agents/ →  may import: rag/, db/, audit/, standard library only
commerce/   →  may import: db/, standard library only
forms/      →  may import: db/, standard library only
bids/       →  may import: db/, commerce/, rag/agent_runtime (the single Anthropic
                call site, for the LLM-assisted novel-red-flag pass only), standard
                library only
api/        →  may import: rag/, commerce/, db/, audit/, standard library only
audit/      →  may import: db/, standard library only
evaluation/ →  may import: rag/, db/, standard library only
scripts/    →  may import: anything (one-off use only)
```

`rag/agents/` must NOT import `commerce/`, `forms/`, or `bids/`. Agents backed
by those packages are registered by `api/main.py` at startup via dependency
injection (`rag/agents/registry.py`), never imported into `rag/`.

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

## Todo and Plan Rules

- When a TODO item in the `README.md` is finished, it must be moved to the **Completed** section.
- Everything in the **Planned** section of `README.md` must be linked to a concrete markdown plan file located either in `.gemini/antigravity/brain/*/*.md` or inside the `permit_rag/docs/` directory.

---

## Never Do These

- Never modify a migration after it has been deployed
- Never commit documents/raw/, .env, **pycache**, node_modules
- Never run a harvest or embed job without checking budget in STATE.md
- Never leave STATE.md stale — if you touched the project, update it
- Never guess at a governance decision — check AGENTS.md first,
  then ask if still unclear
