# API Usage Guide

FastAPI serves interactive docs at:

- `http://localhost:8000/docs` (Swagger UI)
- `http://localhost:8000/redoc` (ReDoc)

Start API locally:

```powershell
py -m uvicorn api.main:app --reload --port 8000
```

## Endpoints

## Runtime config notes

- CORS is now env-driven:
  - `API_CORS_ALLOW_ORIGINS` (comma-separated allowlist)
  - `API_CORS_ALLOW_ALL=true` (dev-only wildcard override)
- Error payload shape is normalized for API and validation errors:
  - `{"detail": "<string>"}`
- Admin auth uses token + optional role allowlist:
  - `API_ADMIN_AUTH_REQUIRED=true|false` (default `true`)
  - `API_ADMIN_TOKEN=<secret>`
  - `API_ADMIN_ALLOWED_ROLES=admin,owner` (default `admin`)
  - Policy: rotate `API_ADMIN_TOKEN` at least every 30 days and immediately after suspected credential exposure or team membership changes.

### `GET /health`

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
```

### `POST /query`

```powershell
$body = @{
  query = "What are the setback requirements for a residential fence in Dallas?"
  top_k = 5
  municipality = "dallas"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/query" `
  -Method Post -ContentType "application/json" -Body $body
```

### `GET /documents`

Filter by any combination of `municipality`, `status`, `authority`, and `doc_type`.

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/documents?municipality=dallas&status=active&authority=municipal&doc_type=building_code" -Method Get
```

### `GET /documents/{doc_id}`

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/documents/dallas-building-code" -Method Get
```

### `GET /documents/status`

Returns grouped counts by `document_status` for the selected filter scope.

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/documents/status?municipality=dallas&authority=municipal" -Method Get
```

### `PATCH /admin/documents/{doc_id}`

Updates mutable governance metadata (`document_status`, `is_current`, `retrieval_weight`, `review_due`).
When admin auth is enabled, pass:
- `X-Admin-Token` (required)
- `X-Admin-Role` (must be in `API_ADMIN_ALLOWED_ROLES`, default `admin`)

```powershell
$body = @{
  document_status = "draft"
  retrieval_weight = 0.55
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/admin/documents/dallas-building-code" `
  -Method Patch -ContentType "application/json" `
  -Headers @{ "X-Admin-Token" = "your-token"; "X-Admin-Role" = "admin" } -Body $body
```

### `POST /admin/documents/{doc_id}/supersede`

Marks the target document as superseded by another `replacement_doc_id`.

```powershell
$body = @{
  replacement_doc_id = "dallas-building-code-2026"
  superseded_weight = 0.10
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/admin/documents/dallas-building-code-2024" `
  -Method Post -ContentType "application/json" `
  -Headers @{ "X-Admin-Token" = "your-token"; "X-Admin-Role" = "admin" } -Body $body
```
