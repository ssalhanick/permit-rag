# permit_rag — State

_Updated: 2026-07-13 (generative room preview + AR asset_url)_

## Phase

**Sprint 17 active** — Scan → Design → Preview → Generate image → Save; AR textures prefer `asset_url` then product photos.

## Blocked on

1. **Mobile OAuth deep links (deferred)** — M0-6/M0-7 device Google/Apple roundtrip
2. **Terraform ECS task def** — do **not** bare `terraform apply` until RDS `DATABASE_URL` drift fixed
3. **Prod deploy gap** — apply migration **018** and deploy backend (design-intent + room-preview-image routes)

## Sprint 17 deliverables

- [x] Migration `018_design_intent_usage.sql` + token helpers
- [x] Design-intent scan routes + `RoomDesignPage` Preview/Save/history/DXF
- [x] AR live voice dictation → design-intent overlays
- [x] Product `image_url` → AR textures
- [x] Generative room preview — `commerce/room_image.py`, `POST /commerce/room-preview-image`
- [x] Device `asset_url` stamp + iOS prefer asset over product photo
- [ ] Apply migration 018 to prod RDS (manual)
- [ ] Deploy backend with new routes to ECS
- [ ] Optional: `OPENAI_API_KEY` in prod for live images (mock works)
- [ ] Device smoke: Preview → Generate image → Save → AR → DXF

## Verification

```bash
.venv/bin/python -m pytest tests/test_commerce_room_image.py tests/test_room_preview_image_route.py tests/test_room_design_intent.py -v
cd frontend && npm run test && npm run build:mobile && npx cap sync ios
```

**Device pass:**
- Scan Single Room → Design → Preview
- Generate image (optional photo) → image shows on page
- Save → Open AR → wall uses generated asset (or product photo)
- Export DXF

## Next tasks

1. Deploy backend (018 + room-preview-image) to prod ECS
2. Set `OPENAI_API_KEY` in `.env` / SSM for live images
3. iPhone smoke of Generate image + AR texture
4. Optional: true img2img edits API path (source photo currently layout-hint only)

## Module status

| Module | Current state |
|--------|---------------|
| commerce | `room_image.py` OpenAI + mock PNG |
| api | `/commerce/room-preview-image` |
| frontend | Generate image button; device PNG + asset_url |
| iOS | Texture precedence: asset_url → product image → color |

## Decisions log

| Decision | Choice |
|----------|--------|
| Gen image provider | OpenAI Images when keyed; mock PNG otherwise |
| Asset storage | Device-only relative path under `room_scans/.../generated_preview.png` |
| AR texture order | `asset_url` first, then `product_ref.image_url` |
| Photo input | Optional Capacitor Camera; folded into prompt (not full edits API yet) |

## Canonical validation

```bash
.venv/bin/python -m pytest tests/test_commerce_room_image.py tests/test_room_preview_image_route.py -v
cd frontend && npm run test
npm run build:mobile && npx cap sync ios
```
