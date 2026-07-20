# permit_rag — State

_Updated: 2026-07-20 (Leonardo.ai Integration + Deterministic Kickoff)_

## Phase

**Sprint 17 active** — Scan → Design → Preview → Generate image → Save; AR textures prefer `asset_url` then product photos.

## Blocked on

1. **Mobile OAuth deep links (deferred)** — M0-6/M0-7 device Google/Apple roundtrip

## Sprint 17 deliverables

- [x] Migration `018_design_intent_usage.sql` + token helpers
- [x] Design-intent scan routes + `RoomDesignPage` Preview/Save/history/DXF
- [x] AR live voice dictation → design-intent overlays
- [x] Product `image_url` → AR textures
- [x] Generative room preview — `commerce/room_image.py`, `POST /commerce/room-preview-image`
- [x] Device `asset_url` stamp + iOS prefer asset over product photo
- [x] Full-screen redesign image blend projection + opacity controller buttons
- [x] Pointer selection (camera center-raycast target-locks) and translucent green highlights
- [x] Long press on walls → custom text generation dialog + presets list dropdown
- [x] Fix double-image ghosting/flicker by performing in-place material updates instead of scene rebuilds on texture preloads
- [x] Apply migration 018 to prod RDS (already applied)
- [x] Landing page accessibility redesign (Outfit/Lexend fonts, Navy/Teal color system, tactile hero buttons hover/active/focus, logout icon)
- [x] Conversational project kickoff (Persona, budget context, custom compliance guide rules, migration 020)
- [x] Animated SVG logo — `LogoSVG.jsx` React component, `useLogoAnimation` hook, hero entrance on landing page, static themed version in nav
- [x] Replace kickoff free-form chat wizard step with deterministic materials checkboxes (Migration 021)
- [x] Deploy backend with new routes and Leonardo.ai key to ECS
- [x] Optional: `LEONARDO_API_KEY` (and `OPENAI_API_KEY`) in prod SSM for live images
- [x] Kickoff wizard step reordering (rooms -> work -> material -> scan -> summary) and redirect to scans tab on LiDAR choice
- [x] Sticky and automatic active project context on `/query` page via localStorage
- [x] Fix layout squeezing on `/query` and `/debug-query` pages for desktop views

## Verification

```bash
.venv/bin/python -m pytest tests/test_commerce_room_image.py tests/test_room_preview_image_route.py tests/test_room_design_intent.py tests/test_gis.py tests/test_kickoff_chat.py tests/test_project_context.py -v
cd frontend && npm run test && npm run build:mobile && npx cap sync ios
```

**Device pass:**
- Scan Single Room → Design → Preview
- Generate image (optional photo) → image shows on page
- Save → Open AR
- Tap `O+` to blend in full-screen redesign projection image.
- Point phone at a wall to auto-highlight it green; tap Dictate to refurbish.
- Long-press a wall to open the text dialog + suggestion presets dropdown.
- Export DXF

## Next tasks

1. iPhone smoke of complete flow

## Module status

| Module | Current state |
|--------|---------------|
| commerce | `room_image.py` Leonardo.ai + OpenAI + mock PNG |
| api | `/commerce/room-preview-image` (now supports `tiling`) |
| frontend | Kickoff materials selection step; Animated SVG logo (hero + nav); Generate image button; device PNG + asset_url |
| iOS | Blend opacity, pointer selectors, long-press generative dropdown, single-anchor mapping |

## Decisions log

| Decision | Choice |
|----------|--------|
| Gen image provider | Leonardo.ai when keyed; OpenAI fallback; mock PNG fallback otherwise |
| Kickoff flow | Deterministic checkbox selections for spaces, work types, and materials |
| Asset storage | Device-only relative path under `room_scans/.../generated_preview.png` |
| AR texture order | `asset_url` first, then `product_ref.image_url` |
| Photo input | Optional Capacitor Camera; folded into prompt |
| Touch handling | Solid bottom container controlPanel to isolate button touch events |
| Color Palette | Default Navy (#0E2A47) background with Sage/Teal color system |

## Canonical validation

```bash
.venv/bin/python -m pytest tests/test_commerce_room_image.py tests/test_room_preview_image_route.py tests/test_gis.py tests/test_kickoff_chat.py tests/test_project_context.py -v
cd frontend && npm run test
npm run build:mobile && npx cap sync ios
```
