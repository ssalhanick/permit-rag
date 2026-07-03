# Session: 2026-07-03 (a)

## Type

Production UX audit — scripted Playwright walkthrough of every major user path on `permits.scottsalhanick.com`.

## Goal

Walk all user paths in the browser, find where users get confused/stuck/broken, write a prioritized UX report.

---

## Completed

### Setup
- Playwright + Chromium in scratch folder `C:\Users\ssalh\permit_rag_ux_audit\` (outside repo)
- Persistent browser profile for session continuity; desktop 1440×900 + mobile 390×844 passes
- Throwaway Cognito account `uxaudit_user1` / `ssalhanick+uxaudit@gmail.com` (email confirm code relayed by user)

### Paths walked
- Landing (signed out), auth (login, register, forgot password, bad creds, empty submit, Google SSO redirect), sign-out, protected-route redirect
- Kickoff wizard (all 5 steps, validation, create), basic form, existing-project picker paths
- Query page (quick queries, submit, answer/error state, network capture of `/query/answer`)
- Upload page, profile dashboard + all sections (history, documents, account), projects panel (tabs: shared docs, history, collaborators, danger zone)
- Mobile: nav burger, wizard checkbox grid, profile, projects, overflow check

### Findings — 4 P0 launch blockers (all verified by direct API/Cognito probes)
1. **Registration broken for all users** — frontend passes email as Cognito Username; pool uses email alias → hard Cognito error. Verified working via direct `SignUp` with non-email username.
2. **Queries never answer on prod** — prod RDS corpus empty (`/documents` → `[]`); CloudFront SPA error mapping rewrites API errors to `index.html` (200); frontend crashes with raw `num_chunks` null error.
3. **Mapbox token missing from prod build** — autocomplete dead, dev hint text leaked to users, municipality never captured.
4. **`/projects` deep-link/refresh** returns raw JSON 401 (SPA/API route collision at CloudFront).

### Findings — P1/P2 highlights
- Wizard-collected data (spaces, work types, recommended permits) invisible after project creation
- Collaborators tab double-counts owner ("Collaborators (2)" on solo project) + self-remove offered
- Add member / transfer ownership demand raw UUIDs
- Upload page is an admin tool (X-Admin-Token) shown to all members, with broken copy (empty `` in sentence)
- Dev jargon on query page (LangSmith, Top K, session id, Developer Logs tabs, unlabeled Q1–Q7)
- "Welcome back." for brand-new users; page title "permit_rag frontend"

### What works well
- Auth flows (login/logout/SSO redirect/guards), wizard interaction pattern, mobile responsiveness, profile IA

## Deliverable

- `docs/ux_audit_260703.md` — full report with P0/P1/P2, root causes, fix order table
- README: status line + docs TOC entry
- STATE.md: P0s recorded as blockers, next tasks reordered

## Cleanup pending

- Delete Cognito user `uxaudit_user1` from user pool
- Delete test project `22cd04d1-a1b8-4b8f-b44a-5287ed09c0bc` ("UX Audit Test Project") + RDS user row
- Scratch folder `C:\Users\ssalh\permit_rag_ux_audit\` can be deleted anytime (screenshots live there)

## Git commit message

docs: add production UX audit report — 4 P0 launch blockers (registration, empty prod corpus, mapbox token, route collision)

## Prompt for next session

Read `AGENTS.md`, `STATE.md`, and `journals/session_260703a.md`. A production UX audit (`docs/ux_audit_260703.md`) found 4 P0 launch blockers. Fix them in order: (1) registration username generation in `frontend/src/context/AuthContext.jsx` `register()` — generate a non-email username since the Cognito pool uses email alias; (2) prod corpus is empty — plan RDS ingestion after checking embed budget in STATE.md, and scope CloudFront custom-error responses so API errors return JSON, plus add a frontend response-shape guard on `/query/answer`; (3) inject `VITE_MAPBOX_TOKEN` into the prod frontend build via `deploy.yml`; (4) fix the `/projects` SPA/API route collision. Also apply migration 014 locally then to RDS. Cleanup: delete Cognito test user `uxaudit_user1` and test project `22cd04d1-a1b8-4b8f-b44a-5287ed09c0bc`.
