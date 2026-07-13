# permit_rag — State

_Updated: 2026-07-12 (scan library UX + per-project dashboard)_

## Phase

**Sprint 14–15 active** — User scan library + project dashboard UX shipped in frontend. Backend migration 017 + library/link API coded; **not yet applied to prod**.

**Sprint 13 closed.** Prod backend on ECS task def **`:11`**. Deploy needed for migrations 016–017 + new API routes.

## Blocked on

1. **Mobile OAuth deep links (deferred)** — M0-6/M0-7 device Google/Apple roundtrip
2. **Terraform ECS task def** — do **not** bare `terraform apply` until RDS `DATABASE_URL` drift fixed
3. **Prod deploy gap** — apply migrations 016 + **017** and deploy backend before library/link sync works on device against prod

## Sprint 14–15 deliverables

- [x] Capture boundary — single room + structure (multi-room) Capacitor plugin
- [x] Interchange JSON schema v1.0 (room) + v2.0 (structure with rooms[])
- [x] Local persist — Capacitor Filesystem + `library` scope for user collection
- [x] Migration 016 — `project_room_scans` (derived only, A+C)
- [x] **Migration 017** — `user_room_scans` + `project_room_scan_links` (library → project attach)
- [x] API — project room-scans + **GET/POST /auth/me/room-scans**, link/unlink on projects
- [x] UI — **profile Room Scans library**, **home promo**, **per-project dashboard** (scans, queries, docs, members)
- [x] RAG — active room `derived` + kickoff in `generate_answer()` when `project_id` set
- [x] iOS AR — openRoomAR, applyMaterial, redesign.json per room
- [x] Speech — native startSpeechRecognition + design-intent overlay patches
- [ ] Android room capture — ARCore or manual polygon fallback
- [ ] Optional: OAuth deep links; Firebase push

## Verification

**Migrations 016 + 017:**

```bash
ENVIRONMENT=production python scripts/run_migration.py db/migrations/016_project_room_scans.sql
ENVIRONMENT=production python scripts/run_migration.py db/migrations/017_user_room_scan_library.sql
ENVIRONMENT=production python scripts/check_room_scans.py
```

**Backend tests (venv):**

```bash
python -m pytest tests/test_project_room_scans.py tests/test_query_answer_route.py -v
```

**Frontend:**

```bash
cd frontend && npm run test
npm run build:mobile && npx cap sync ios
```

**Device pass:**
- Profile → Room Scans → capture house/room → appears in library
- Project → Scans → Add from library → set active → Query uses room context
- Home page shows Room Scans promo card
- Project dashboard shows linked scans + recent queries

**RAGAs:** run after prod deploy if generator prompt changed materially (faithfulness >= 0.85).

## Next tasks

1. **Apply migration 017** to prod RDS
2. **Deploy backend** with library/link routes to prod ECS
3. **Device smoke** — library capture + link-to-project on iPhone
4. **Android** — stub methods exist; implement ARCore or 2D fallback
5. Optional: M0-6/M0-7 OAuth; Firebase push

## Module status

| Module | Current state |
|--------|---------------|
| db | Migrations 001–**017**; `user_room_scans`, `project_room_scan_links`, legacy `project_room_scans` |
| api | User library CRUD; project link/unlink; room-scans + design-intent |
| rag | `project_context` + `design_intent`; generator accepts `project_context` |
| frontend | Scan library, project dashboard layout, home promo, 50 frontend tests |
| eval | avg faithfulness **0.910** ✅ (re-run after deploy) |

## Decisions log

| Decision | Choice |
|----------|--------|
| Multi-scan privacy | **A+C** — geometry on device; derived summaries in RDS |
| Scan ownership | **User library first** — link scans/structures/rooms to projects on demand |
| Structure hierarchy | `scan_type` structure + room rows linked by `parent_scan_id` |
| Design generative layer | LLM → overlay patch only; RealityKit renders materials |
| Active scan for chat | One `is_active` room per project via `project_room_scan_links` |

## Canonical validation

```bash
python -m pytest tests/test_project_room_scans.py tests/test_query_answer_route.py -v
cd frontend && npm run test
npm run build:mobile && npx cap sync ios
ENVIRONMENT=production python scripts/check_room_scans.py
```
