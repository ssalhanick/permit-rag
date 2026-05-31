# API Usage Guide

FastAPI serves interactive docs at:

- `http://localhost:8000/docs` (Swagger UI)
- `http://localhost:8000/redoc` (ReDoc)

Start API locally:

```powershell
py -m uvicorn api.main:app --reload --port 8000
```

## Endpoints

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
