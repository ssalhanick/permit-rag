# Room generative preview images

## Goal

Connect room-scan design intent to a generative room image shown on iPhone, then textured into AR via `overlay.asset_url`.

## Flow

1. Scan room → Design page
2. Preview (LLM overlays + product cards)
3. **Generate image** → `POST /api/commerce/room-preview-image`
4. Optional camera/photo as layout hint (`source_image_b64`)
5. Save PNG under `room_scans/.../generated_preview.png`
6. Stamp `asset_url` onto overlays; Save revision stores it
7. AR prefers `asset_url` → else product `image_url`

## Provider

Preference order: fal → Leonardo → OpenAI → mock. `generate_room_preview_image()` tries each in turn and falls through on missing key or request failure.

| Env | Behavior |
|-----|----------|
| `FAL_API_KEY` set | fal.ai PATINA (`fal-ai/patina/material`), synchronous call — returns a full tileable PBR set (basecolor/normal/roughness/metalness/height); only basecolor is used until the AR material system moves off `UnlitMaterial` |
| `FAL_API_KEY` unset, `LEONARDO_API_KEY` set | Leonardo.ai Generations API (`LEONARDO_IMAGE_MODEL`, default `de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3` — Phoenix), polled to completion |
| Both unset, `OPENAI_API_KEY` set | OpenAI Images API (`OPENAI_IMAGE_MODEL`, default `gpt-image-1`) |
| None set | Mock solid PNG tinted from overlay color |

`_fal_generate`'s response parsing (`_extract_fal_basecolor_url` in `commerce/room_image.py`) was written from fal's documented request shape but wasn't confirmed against a live response — fal's docs pages were rate-limiting fetches while this was built. It defensively checks a few plausible key layouts and raises with the actual response keys if none match; if the very first real call errors, that error message is the fix.

## Key files

- `commerce/room_image.py`
- `api/routes/commerce.py` (`/room-preview-image`)
- `frontend/src/services/roomPreviewImage.js`
- `frontend/src/profile/pages/RoomDesignPage.jsx`
- iOS `RoomARPresenter` texture resolution

## Device verify

```bash
cd frontend && npm run build:mobile && npx cap sync ios
```

On iPhone: Scan → Preview → Generate image → Save → Open AR → confirm texture.
