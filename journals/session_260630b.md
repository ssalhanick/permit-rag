# Session: 2026-06-30 (b)

## Type

Sprint 12 — Project kickoff wizard.

## Goal

After sign-in, prompt the user to start a new project (via a guided conversational wizard) or pick an existing one, instead of landing directly on the query page.

---

## Completed

### Database
- `db/migrations/014_project_fields.sql` — adds 4 nullable columns to `projects`: `address TEXT`, `spaces JSONB`, `work_types JSONB`, `recommended_permits JSONB`

### Backend
- `db/client.py` `create_project()` — extended with `address`, `spaces`, `work_types`, `recommended_permits` keyword args; JSONB columns serialised via `json.dumps`
- `api/schemas.py` — `CreateProjectRequest` and `ProjectResponse` updated with the 4 new optional fields
- `api/routes/projects.py` — `POST /projects` passes new fields through to `db.create_project()`

### Frontend
- `frontend/src/projectPermitRules.js` (new) — `recommendPermits(workTypes)` maps work types → permit categories (Plumbing, Electrical, Mechanical, Building, Zoning, Roofing, Demolition); `isCosmeticOnly()`; exported constants `WORK_TYPE_OPTIONS` and `SPACE_OPTIONS`
- `frontend/src/ProjectKickoffPage.jsx` (new) — three-mode page:
  - **Guided wizard** (default): 5-step conversational setup — address autocomplete, project name, spaces checkboxes (indoor + outdoor), work-type checkboxes, permit preview + confirm
  - **Basic form** (opt-out link): name + address only → create project
  - **Existing project picker**: scrollable list of user's projects; click to open in query context
  - Skip option available throughout; all paths navigate to `/?p={id}` or `/`
- `frontend/src/AuthPage.jsx` — added `dest` variable; all 6 `navigate(from, ...)` calls changed to `navigate(dest, ...)`; `dest = from === "/" ? "/kickoff" : from` so fresh logins go to `/kickoff` while mid-navigation redirects are preserved
- `frontend/src/AuthCallback.jsx` — Google SSO callback changed from `navigate("/")` to `navigate("/kickoff")`
- `frontend/src/main.jsx` — imported `ProjectKickoffPage`, added `/kickoff` route wrapped in `ProtectedRoute`
- `frontend/src/styles.css` — added kickoff styles: `.kickoff-page`, `.kickoff-panel`, `.kickoff-mode-card`, `.kickoff-chat-bubble`, `.kickoff-checkbox-grid`, `.kickoff-permit-tag`, `.kickoff-wizard-progress`, `.kickoff-summary`, responsive breakpoints

---

## Files changed

- `db/migrations/014_project_fields.sql` (new)
- `db/client.py` (create_project extended)
- `api/schemas.py` (CreateProjectRequest + ProjectResponse)
- `api/routes/projects.py` (pass-through)
- `frontend/src/projectPermitRules.js` (new)
- `frontend/src/ProjectKickoffPage.jsx` (new)
- `frontend/src/AuthPage.jsx` (dest redirect)
- `frontend/src/AuthCallback.jsx` (kickoff redirect)
- `frontend/src/main.jsx` (/kickoff route)
- `frontend/src/styles.css` (kickoff styles appended)
- `STATE.md` (updated)

---

## Still pending (carry into next session)

- Run migration 014 locally: `py scripts\run_migration.py db\migrations\014_project_fields.sql`
- Run migration 014 on RDS production
- Upgrade permit logic: swap rule-based `recommendPermits()` with a RAG query to the corpus

## Prompt for next session

Read `AGENTS.md`, `STATE.md`, and `journals/session_260630b.md`. Sprint 12 is in progress. The project kickoff wizard is built and wired but **migration 014 has not been applied yet**. First step: run `py scripts\run_migration.py db\migrations\014_project_fields.sql` locally and verify the columns appear in the DB. Then smoke-test the wizard in the browser (sign in → `/kickoff` should appear with the wizard UI). Confirm the wizard creates a project with address/spaces/work_types/recommended_permits populated. Then consider upgrading the permit recommendation from rule-based to a RAG-powered query against the corpus.

## Git commit message

feat(sprint12): add project kickoff wizard with conversational setup, permit rules, and DB fields
