# permit_rag — State

_Updated: 2026-07-13 (room design Preview/Save + revision history + AR live dictation)_

## Phase

**Sprint 17 active** — Single-room Scan → Design (text/mic) → Preview → Save; device-only `redesign.json` v2 revisions; DXF export; design token accounting (migration 018); AR live voice dictation.

**Sprint 16 closed** — commerce overlays, product resolver, materials estimate.

## Blocked on

1. **Mobile OAuth deep links (deferred)** — M0-6/M0-7 device Google/Apple roundtrip
2. **Terraform ECS task def** — do **not** bare `terraform apply` until RDS `DATABASE_URL` drift fixed
3. **Prod deploy gap** — apply migration **018** and deploy backend with scan_id design-intent routes

## Sprint 17 deliverables

- [x] Migration `018_design_intent_usage.sql` + `db/client.py` token helpers
- [x] `POST /projects/{id}/room-scans/{scan_id}/design-intent` (standalone + structure child)
- [x] `POST /auth/me/room-scans/{scan_id}/design-intent` (library)
- [x] `rag/design_intent.py` returns usage; soft monthly cap via `DESIGN_INTENT_MONTHLY_TOKEN_CAP`
- [x] `RoomDesignPage` — Preview (LLM) / Save (device), revision history, branch, AR + DXF export
- [x] `redesign.json` v2 revisions on device; iOS AR reads `active_revision_id`
- [x] Demote Scan House; post-scan nav to design page; single-room `structureId` fix
- [ ] Apply migration 018 to prod RDS (manual)
- [ ] Deploy backend with new design-intent routes to ECS
- [ ] Device smoke: Preview → Save → branch → AR → DXF share sheet

## Verification

**Migration 018:**

```bash
ENVIRONMENT=production python scripts/run_migration.py db/migrations/018_design_intent_usage.sql
```

**Backend tests:**

```bash
.venv/bin/python -m pytest tests/test_room_design_intent.py tests/test_commerce_takeoff.py tests/test_commerce_product_resolver.py -v
```

**Frontend:**

```bash
cd frontend && npm install && npm run test && npm run build:mobile && npx cap sync ios
```

**Device pass:**
- Profile → Scan Single Room → design page
- Preview "white subway tile" → product cards; Save → revision in history
- Branch from revision → new Preview/Save without re-LLM on Save
- AR shows active revision; Export DXF → share sheet
- Project-linked scan uses project design route; tokens logged with `project_id`

## Next tasks

1. Apply migration 018 + deploy backend to prod ECS
2. iPhone device smoke (Preview/Save/branch/AR/DXF)
3. Optional: library scan list → project link CTA from design page

## Module status

| Module | Current state |
|--------|---------------|
| api | scan_id design-intent routes; token usage in response |
| rag | `design_intent.py` usage metadata |
| frontend | `RoomDesignPage`, `designHistory.js`, `roomCadExport.js`, case-insensitive lookups, 60 tests pass |
| iOS | AR v2 `active_revision_id` overlay resolution; lowercased UUID alignment |

## Decisions log

| Decision | Choice |
|----------|--------|
| Revision storage | Device-only `redesign.json` v2; no cloud sync of full history |
| LLM timing | Cloud Haiku on Preview only; Save persists without API |
| Terminology | Preview / Save — never "draft" |
| Token cap | Soft monthly cap per user (`DESIGN_INTENT_MONTHLY_TOKEN_CAP`, default 500k) |

## Canonical validation

```bash
.venv/bin/python -m pytest tests/test_room_design_intent.py tests/test_commerce_takeoff.py -v
cd frontend && npm run test
npm run build:mobile && npx cap sync ios
```
