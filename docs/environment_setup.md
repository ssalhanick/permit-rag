# Environment Setup — Local vs Production

## How it works

| Where | Profile | Config source |
|-------|---------|---------------|
| Laptop (`npm run dev`, uvicorn) | `local` | `.env.local` + `.env` |
| ECS Fargate (AWS deploy) | `production` | Terraform task env + SSM secrets |
| Laptop + RDS debug (optional) | `production` | `.env.production` + `.env` |

`api/load_env.py` runs at API startup and picks the profile:

1. **ECS** → `production` (no dotenv files in container)
2. **`ENVIRONMENT=production`** → production
3. **Otherwise** → `local` (default on your machine)

### Load order

```
local:      .env.local  →  .env (secrets override)
production: .env.production (if present)  →  .env
```

## First-time local setup

```powershell
Copy-Item .env.local.example .env.local
Copy-Item .env.example .env
# Edit .env — add ANTHROPIC_API_KEY, API_JWT_SECRET, API_ADMIN_TOKEN

docker compose up -d db neo4j
py -m uvicorn api.main:app --reload --port 8000
cd frontend; npm run dev
```

Health check should show `"database": true`:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
```

## Production (AWS)

No `.env` files in the Docker image. GitHub Actions pushes to ECR; ECS task definition sets:

- `ENVIRONMENT=production`
- `DATABASE_URL` → RDS (from Terraform)
- Secrets → SSM Parameter Store (`ANTHROPIC_API_KEY`, `API_JWT_SECRET`, etc.)

Frontend CI build uses Vite production mode — API calls use same-origin paths via CloudFront (`permits.scottsalhanick.com`).

## Optional: debug against RDS from laptop

```powershell
Copy-Item .env.production.example .env.production
# Fill RDS endpoint + password in .env.production

$env:ENVIRONMENT="production"
py -m uvicorn api.main:app --reload --port 8000
```

## Files (git)

| File | Committed | Purpose |
|------|-----------|---------|
| `.env.local.example` | yes | Local infra template |
| `.env.production.example` | yes | RDS debug template |
| `.env.example` | yes | Shared secrets template |
| `.env.local` | no | Your local infra |
| `.env.production` | no | Your RDS debug config |
| `.env` | no | API keys, JWT, admin token |

## Verification

```powershell
py -m pytest tests/test_load_env.py -v
```
