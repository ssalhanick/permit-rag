# frontend

Minimal Vite + React frontend kickoff for `permit_rag`.

## First interaction flow

- User submits question + optional municipality + top_k.
- App calls `POST /query/answer`.
- App renders answer, citations, and diagnostics.

## Run locally

```powershell
cd frontend; npm install; npm run dev
```

Create `frontend/.env` from `.env.example` if you need a custom API URL.
