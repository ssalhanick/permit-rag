# permit_rag — State

_Updated: 2026-07-12 (Sprint 14 iOS room capture — sync verified pending prod check)_

## Phase

**Sprint 14 active** — iOS RoomPlan capture wired on device; derived summary syncs to `projects.room_summary`. Android ARCore/manual fallback and product use (compliance rules + RAG context) still open.

**Sprint 13 closed.** Prod backend on ECS task def **`:11`** (mobile CORS). Mobile Phase 0 gates M0-1–M0-5, M0-8, M0-9 pass.

## Blocked on

1. **Mobile OAuth deep links (deferred)** — M0-6/M0-7 device Google/Apple roundtrip; web Apple SSO verified
2. **Terraform ECS task def** — do **not** bare `terraform apply` until RDS `DATABASE_URL` drift fixed or moved to SSM (task def `:10` broke prod DB auth)
3. **Prod deploy gap** — Sprint 14 backend (`UpdateProjectRequest` kickoff fields) may need GHA deploy before prod API matches local branch

## Sprint 14 deliverables

- [x] Capture boundary — `startCapture()` Capacitor plugin (iOS RoomPlan)
- [x] Interchange JSON schema v1.0 + `deriveRoomMetrics` / `buildRoomSummaryForSync`
- [x] Local persist — per-project JSON in `roomScanStorage.js` (device only; no mesh leaves phone)
- [x] Sync summary only — `PATCH /api/projects/{id}/room-summary` → `projects.room_summary` jsonb
- [x] UI — `RoomScanPanel` on Projects; Projects nav link; kickoff entry from Projects page
- [ ] Android room capture — ARCore or manual polygon fallback
- [ ] Product use — rule-based compliance UI on scan metrics; inject `room_summary` into `/query/answer`
- [ ] Optional: OAuth deep links; Firebase push

## Room summary verification (Sprint 14 sync gate)

Mobile `.env.mobile` points at **prod** (`https://permits.scottsalhanick.com`) → scan data lands in **RDS**, not local Docker.

**Python (uses `DATABASE_URL` from env profile):**

```bash
# Prod RDS (after filling .env.production)
ENVIRONMENT=production python scripts/check_room_summary.py

# Optional: one project
ENVIRONMENT=production python scripts/check_room_summary.py <project-uuid>

# Local Docker (only if API/mobile pointed at localhost)
python scripts/check_room_summary.py
```

**Raw SQL** — `scripts/check_room_summary.sql` via `psql` or RDS Query Editor.

**Pass:** at least one row with `room_summary.derived` (wall_count, max_ceiling_height_m, etc.) after a device scan.

**Also in app:** Projects → select project → Room Scan section shows synced metrics.

## Next tasks (Sprint 14 priority)

1. **Confirm prod sync** — run `check_room_summary.py` with `ENVIRONMENT=production`; deploy backend if empty
2. **Compliance UI** — egress/width rule checks on `room_summary.derived` (no LLM)
3. **RAG project context** — pass `room_summary` + kickoff fields into `generate_answer()` when `project_id` set
4. **Android** — ARCore or manual polygon fallback in `RoomCapturePlugin`
5. **Optional:** M0-6/M0-7 OAuth; Firebase push

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
| db | Migrations 001–**015**; `projects.room_summary` jsonb; kickoff fields updatable via PATCH |
| api | room-summary PATCH; `UpdateProjectRequest` for kickoff fields (owner/editor) |
| rag | Mini-RAG when `project_id` set; **room_summary not yet in generator context** |
| frontend | iOS RoomPlan plugin; RoomScanPanel; Projects kickoff deep links; 48 frontend tests |
| eval | avg faithfulness **0.910** ✅ (gate >= 0.85) |

## Operational snapshot

- **Site:** `https://permits.scottsalhanick.com`
- **ECS:** `permit-rag-backend:11` (mobile CORS; keep until terraform creds fixed)
- **Branch:** `deployment/sites` (Sprint 13 merged; Sprint 14 work may be local/uncommitted)
- **Auth:** Cognito; mobile `com.scottsalhanick.permitrag://auth/callback`

## Decisions log (Sprint 13–14)

| Decision | Choice |
|----------|--------|
| Capacitor config | `capacitor.config.json` (not `.ts` / ESM `.js`) |
| Mapbox on mobile | Deferred — manual address on kickoff |
| Room scan privacy | Full interchange JSON on device; only `derived` summary syncs to RDS |
| RoomPlan availability | `RoomCaptureSession.isSupported` (not ARKit mesh classification alone) |
| iOS deployment target | 16.0 (RoomPlan) |
| Push on device | Off until `google-services.json`; env `VITE_PUSH_NOTIFICATIONS_ENABLED` |
| ECS CORS update | Manual task def clone from `:9` → `:11`; avoid terraform-only deploy |

## Canonical validation

```powershell
.\.venv\Scripts\Activate.ps1
py -m pytest tests/test_query_answer_route.py tests/test_mini_rag.py tests/test_api_main.py -v
cd frontend; npm run test
npm run build:mobile; npx cap sync ios
$env:ENVIRONMENT="production"; py scripts/check_room_summary.py
.\scripts\sprint12_p0_smoke.ps1
$env:ENVIRONMENT="production"; py -m evaluation.prod_preflight
```
