# permit_rag — State

_Updated: 2026-07-09 (Sprint 13 closed — Sprint 14 room capture next)_

## Phase

**Sprint 13 closed.** Capacitor mobile shell on `feat/capacitor-wrapper` merged to `deployment/sites`. Prod backend on ECS task def **`:11`** (mobile CORS). Android device verified: email login + RAG query against prod.

**Sprint 14 active** — wire native room capture per [`docs/sprint_14_3d-room-capture-agnostic-guide.md`](docs/sprint_14_3d-room-capture-agnostic-guide.md). Stubs exist (`frontend/plugins/room-capture/`, `roomCapture.js`, `roomMetrics.js`); RoomPlan UI not wired.

## Blocked on

1. **Room capture native plugin** — Swift RoomPlan + Android ARCore path; interchange JSON schema v1.0 → `projects.room_summary`
2. **Mobile OAuth deep links (deferred)** — M0-6/M0-7 device Google/Apple roundtrip; web Apple SSO verified
3. **Terraform ECS task def** — do **not** bare `terraform apply` until RDS `DATABASE_URL` drift fixed or moved to SSM (task def `:10` broke prod DB auth)

## Next tasks (Sprint 14 priority)

1. **Capture boundary** — `startCapture() -> RoomCaptureResult` behind Capacitor plugin; no mesh leaves device
2. **Interchange schema v1.0** — versioned JSON surfaces + derived summary (area, wall lengths)
3. **Persist locally** — SQLite or per-scan JSON under `assetLifecycle` pattern
4. **Sync summary only** — `PATCH /api/projects/{id}/room-summary` (migration 015 applied local + RDS)
5. **iOS RoomPlan** — LiDAR devices; Android fallback manual polygon / ARCore planes
6. **Optional:** Android OAuth deep-link intent-filter; Firebase + `VITE_PUSH_NOTIFICATIONS_ENABLED=true` for push

## Sprint 13 deliverables — CLOSED ✅

- [x] Capacitor 7 shell — `frontend/capacitor.config.json`, `platform.js`, `mobileAuth.js`
- [x] Mobile auth — Cognito OAuth via `@capacitor/browser` + deep-link handler in `AuthContext.jsx`
- [x] Offline banner, biometric gate scaffold, mobile upload, `X-Client-Tier: mobile`
- [x] Mini-RAG — `rag/mini_rag.py`, `retrieve_with_project()`, corpus sync API
- [x] Asset lifecycle + corpus cache scaffolds (frontend services + tests)
- [x] Room capture plugin stubs + `room_summary` migration 015 (local + RDS)
- [x] Mobile CI — `.github/workflows/mobile-release.yml`, `fastlane/`
- [x] Prod deploy — GHA backend + frontend; ECS `:11` mobile CORS
- [x] Phase 0 gates — M0-1–M0-5, M0-8, M0-9 pass; M0-6/M0-7 deferred (see `docs/mobile_phase0_gates.md`)
- [x] Push crash fix — `initPushNotifications()` gated until Firebase (`VITE_PUSH_NOTIFICATIONS_ENABLED`)

**Verification:** `cd frontend; npm run test` (40 pass). Android device: email login, project create, RAG query + citation. `.\scripts\sprint12_p0_smoke.ps1` (documents + SPA; health assertion fixed).

## Mobile Phase 0 — status

| Gate | Item | Status |
|------|------|--------|
| M0-1 | Mobile CORS on ECS `:11` | ✅ |
| M0-2 | Cognito mobile callback URLs | ✅ |
| M0-3 | ECS redeploy with CORS | ✅ |
| M0-4 | `build:mobile` + `cap sync` | ✅ |
| M0-5 | Device email/password vs prod | ✅ |
| M0-6 | Device Google deep link | ⏸ deferred |
| M0-7 | Device Apple deep link | ⏸ deferred (web Apple verified) |
| M0-8 | Device RAG + citation | ✅ |
| M0-9 | Web prod smoke | ✅ |

## Module status

| Module | Current state |
|--------|---------------|
| db | Migrations 001–**015** applied (local + RDS); `projects.room_summary` jsonb live |
| api | Sprint 13 routes: `/api/corpus/sync`, asset sync-ack, room-summary PATCH |
| rag | Mini-RAG merge + conflict warnings when `project_id` set |
| frontend | Capacitor 7; mobile build via `npm run build:mobile` + `.env.mobile` |
| eval | avg faithfulness **0.910** ✅ (gate >= 0.85) |

## Operational snapshot

- **Site:** `https://permits.scottsalhanick.com`
- **ECS:** `permit-rag-backend:11` (mobile CORS; keep until terraform creds fixed)
- **Branch:** `deployment/sites` (Sprint 13 merged)
- **Auth:** Cognito; mobile `com.scottsalhanick.permitrag://auth/callback`

## Decisions log (Sprint 13)

| Decision | Choice |
|----------|--------|
| Capacitor config | `capacitor.config.json` (not `.ts` / ESM `.js`) |
| Mapbox on mobile | Deferred — manual address on kickoff |
| Biometric plugin | `@aparajita/capacitor-biometric-auth@^7.2.0` |
| Push on device | Off until `google-services.json`; env `VITE_PUSH_NOTIFICATIONS_ENABLED` |
| ECS CORS update | Manual task def clone from `:9` → `:11`; avoid terraform-only deploy |

## Canonical validation

```powershell
.\.venv\Scripts\Activate.ps1
py -m pytest tests/test_query_answer_route.py tests/test_mini_rag.py tests/test_api_main.py -v
cd frontend; npm run test
npm run build:mobile; npx cap sync android
.\scripts\sprint12_p0_smoke.ps1
$env:ENVIRONMENT="production"; py -m evaluation.prod_preflight
```
