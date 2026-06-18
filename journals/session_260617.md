# Session: 2026-06-17

## Type

Sprint 9 — JWT Auth, Projects, and Query History.

## Goal

Implement visual-safe JWT authentication, project workspace coordination, private query history log tracking, document sharing, and a React profile view.

---

## Completed

### JWT Auth, Sessions & Projects

**Auth & JWT Sessions:**
- Implemented Argon2id password hashing and E.164 phone formatting.
- Set up strict visual-safe username validation (no consecutive dots/underscores/hyphens, no reserved words).
- Generated secure short-lived Access JWT tokens and long-lived Refresh JWT tokens.
- Deployed token family rotation (token reuse prevention) and logout-all-sessions.

**Project Lifecycle & Document Sharing:**
- Created projects and project members tables supporting ownership transfer and cascading deletion.
- Enforced RBAC roles (`owner`, `editor`, `viewer`) for project updates and document sharing.
- Implemented project document binding on upload, and project sharing to copy custom documents to other projects.

---

### Private Query History & Frontend Integration

**Query History & Deletion:**
- Logged persistent query log history linked to `user_id` and `project_id`.
- Added query history retrieval (`GET /query/history`) and single-entry query deletion (`DELETE /query/history/{query_id}`).
- Standardized routes to use `/query/history` prefixes in `api/routes/query.py`.

**React Frontend Integration:**
- Created `frontend/src/ProfilePage.jsx` with tab panels for:
  - **Query History**: Lists and expands past queries, copies answers to clipboard, reloads queries, and deletes history entries.
  - **My Documents**: Lists user-uploaded documents, purges them via admin purge, and copies/duplicates documents to other projects.
- Integrated `/profile` route in `main.jsx` and navigated from `Nav.jsx`.
- Added `useEffect` in `App.jsx` to prefill the search form when url parameters `q` and `m` are present.

---

### Removal of Superadmin Controls

- Removed all user listing and delete account endpoints (`GET /admin/users` and `DELETE /admin/users/{user_id}`) from the backend.
- Removed user list state, tables, and buttons from the frontend dashboard.
- Deleted `TestAdminUsersAPI` test class from the test suite to match the user's specification.

---

## Testing — tests/test_sprint9.py (21 tests)

- **Auth & Validation primitives (8 tests)** — Argon2id hashing, E.164 phone structure, visual-safety username restrictions.
- **Session & JWT Tokens (3 tests)** — Token generation/decoding, rotation reuse prevention, logout.
- **Project CRUD & RBAC (6 tests)** — CRUD actions, role membership checking, ownership transfer, cascaded deletion.
- **Document Sharing & Query history (4 tests)** — Sharing to projects, query log deletion, and authorization.

All **21 sprint tests** pass successfully, bringing the total test suite to **93 passing tests**.

---

## Next Steps / Blockers

- **Mapbox token**: Set up `VITE_MAPBOX_TOKEN` in `frontend/.env` to enable map address autocompletion.

---

## Next Session Prompt

To begin the next session:
1. Start the FastAPI backend and Vite frontend development servers.
2. Submit a test query through the UI to reproduce the RAG hang.
3. Diagnose the browser console errors, fetch payloads, and uvicorn stdout logs.
4. Fix any UI hook state-locks, request/response payload parsing mismatches, or backend background task execution hangs in `/query/answer` so that responses resolve cleanly and queries are successfully saved to the user's history.
