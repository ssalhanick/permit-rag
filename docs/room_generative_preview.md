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

| Env | Behavior |
|-----|----------|
| `OPENAI_API_KEY` unset | Mock solid PNG tinted from overlay color |
| `OPENAI_API_KEY` set | OpenAI Images API (`OPENAI_IMAGE_MODEL`, default `gpt-image-1`) |

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
