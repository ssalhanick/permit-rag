# Environment & Secrets Strategy

_Created: 2026-06-30 | Status: Planned (not yet implemented)_

---

## Current state (as-built)

### Backend env loading

`api/load_env.py` runs `bootstrap_env()` at startup. Load order:

| Profile | File 1 | File 2 (wins) |
|---------|--------|---------------|
| `local` | `.env.local` | `.env` |
| `production` | `.env.production` (if on disk) | `.env` |

In ECS, neither dotenv file is present (Dockerfile copies none). Vars come from:
- ECS task definition environment variables
- Two `ENV` lines baked directly into the `Dockerfile`

### Frontend env loading

Vite's built-in layering. `frontend/.env` is always loaded; `frontend/.env.production` only during `npm run build`. Both files are gitignored, so CI/CD injects vars explicitly via workflow `env:` block.

### Known gaps

| # | Gap | Risk |
|---|-----|------|
| 1 | Cognito values hardcoded in `deploy.yml` lines 110–114 | Rotating a value requires a code change + PR |
| 2 | `COGNITO_USER_POOL_ID` + `COGNITO_REGION` baked into `Dockerfile` | Image is environment-coupled; can't promote same image across envs |
| 3 | True secrets (`ANTHROPIC_API_KEY`, `DATABASE_URL`, `API_ADMIN_TOKEN`, `LANGSMITH_API_KEY`) stored as plaintext in ECS task definition | Visible in AWS Console; not rotatable without manual task def edit |

---

## Target state

```
┌─────────────────────────────────────────────────────────┐
│ GitHub repository                                       │
│  vars.*    — non-sensitive config (Cognito, regions)    │
│  secrets.* — true secrets (Mapbox token)                │
└──────────────────┬──────────────────────────────────────┘
                   │ injected at build time
                   ▼
┌─────────────────────────────────────────────────────────┐
│ GitHub Actions (deploy.yml)                             │
│  Frontend build: ${{ vars.VITE_COGNITO_* }}             │
│  Backend deploy: image is env-agnostic                  │
└──────────────────┬──────────────────────────────────────┘
                   │ image pushed to ECR
                   ▼
┌─────────────────────────────────────────────────────────┐
│ ECS Task Definition                                     │
│  Plain env vars — non-sensitive config                  │
│    COGNITO_USER_POOL_ID, COGNITO_REGION, LOG_LEVEL ...  │
│  valueFrom SSM — true secrets                           │
│    DATABASE_URL, ANTHROPIC_API_KEY, API_ADMIN_TOKEN ... │
└──────────────────┬──────────────────────────────────────┘
                   │ resolved at container start
                   ▼
┌─────────────────────────────────────────────────────────┐
│ AWS SSM Parameter Store (SecureString)                  │
│  /permit_rag/prod/database_url                          │
│  /permit_rag/prod/anthropic_api_key                     │
│  /permit_rag/prod/admin_token                           │
│  /permit_rag/prod/langsmith_api_key                     │
│  /permit_rag/prod/neo4j_auth          (if AuraDB used)  │
│  /permit_rag/prod/neo4j_bolt_url      (if AuraDB used)  │
└─────────────────────────────────────────────────────────┘
```

---

## Migration plan

Execute gaps in order. Each step is independently deployable and reversible.

---

### Gap 1 — Move frontend config to GitHub repository variables

**Risk:** Zero. GitHub UI change only, no code or infra touched.

**Step 1.1 — Create GitHub repository variables**

In GitHub → Settings → Secrets and variables → Actions → Variables tab, add:

| Variable name | Value |
|---------------|-------|
| `VITE_COGNITO_USER_POOL_ID` | `us-east-1_HF3i1xgNF` |
| `VITE_COGNITO_APP_CLIENT_ID` | `21admh46opa2gaaii3oaq0nlgd` |
| `VITE_COGNITO_REGION` | `us-east-1` |
| `VITE_COGNITO_DOMAIN` | `us-east-1hf3i1xgnf.auth.us-east-1.amazoncognito.com` |
| `VITE_COGNITO_GOOGLE_ENABLED` | `true` |
| `VITE_API_BASE_URL` | _(empty string)_ |

`VITE_MAPBOX_TOKEN` stays in **Secrets** (it is a true secret).

**Step 1.2 — Update `deploy.yml` frontend build step**

Replace the hardcoded `env:` block:

```yaml
# Before (hardcoded)
env:
  VITE_MAPBOX_TOKEN: ${{ secrets.VITE_MAPBOX_TOKEN }}
  VITE_API_BASE_URL: ""
  VITE_COGNITO_USER_POOL_ID: us-east-1_HF3i1xgNF
  VITE_COGNITO_APP_CLIENT_ID: 21admh46opa2gaaii3oaq0nlgd
  VITE_COGNITO_REGION: us-east-1
  VITE_COGNITO_DOMAIN: us-east-1hf3i1xgnf.auth.us-east-1.amazoncognito.com
  VITE_COGNITO_GOOGLE_ENABLED: "true"

# After (references)
env:
  VITE_MAPBOX_TOKEN: ${{ secrets.VITE_MAPBOX_TOKEN }}
  VITE_API_BASE_URL: ${{ vars.VITE_API_BASE_URL }}
  VITE_COGNITO_USER_POOL_ID: ${{ vars.VITE_COGNITO_USER_POOL_ID }}
  VITE_COGNITO_APP_CLIENT_ID: ${{ vars.VITE_COGNITO_APP_CLIENT_ID }}
  VITE_COGNITO_REGION: ${{ vars.VITE_COGNITO_REGION }}
  VITE_COGNITO_DOMAIN: ${{ vars.VITE_COGNITO_DOMAIN }}
  VITE_COGNITO_GOOGLE_ENABLED: ${{ vars.VITE_COGNITO_GOOGLE_ENABLED }}
```

**Verification:** Push to `deployment/sites`, confirm frontend build succeeds and Google SSO still works on `permits.scottsalhanick.com`.

---

### Gap 2 — Remove ENV from Dockerfile

**Risk:** Low. Requires one ECS task def update before removing from Dockerfile.

**Step 2.1 — Add Cognito vars to ECS task definition**

In AWS Console → ECS → Task Definitions → your task def → Create new revision → Container → Environment variables, add:

| Key | Value | Type |
|-----|-------|------|
| `COGNITO_USER_POOL_ID` | `us-east-1_HF3i1xgNF` | Value |
| `COGNITO_REGION` | `us-east-1` | Value |

Deploy the new revision. Confirm the service is stable and `/health` returns 200.

**Step 2.2 — Remove from Dockerfile**

Delete the two baked-in lines:

```dockerfile
# Remove these two lines:
ENV COGNITO_USER_POOL_ID=us-east-1_HF3i1xgNF
ENV COGNITO_REGION=us-east-1
```

Push and deploy. The task definition now owns these values; the image is environment-agnostic.

**Verification:** `GET /health` returns 200. `GET /auth/me` with a valid Cognito token returns user profile.

---

### Gap 3 — Move true secrets to SSM Parameter Store

**Risk:** Medium. Requires IAM policy check and task definition rewrite. Test in staging first if available.

**Step 3.1 — Identify which secrets are currently plaintext in ECS**

Check the current ECS task definition for any of these as plain `value` (not `valueFrom`):

| Secret | Current location | Target SSM path |
|--------|-----------------|-----------------|
| `ANTHROPIC_API_KEY` | ECS task def (plaintext) | `/permit_rag/prod/anthropic_api_key` |
| `DATABASE_URL` | ECS task def (plaintext) | `/permit_rag/prod/database_url` |
| `API_ADMIN_TOKEN` | ECS task def (plaintext) | `/permit_rag/prod/admin_token` |
| `LANGSMITH_API_KEY` | ECS task def (plaintext) | `/permit_rag/prod/langsmith_api_key` |
| `NEO4J_AUTH` | ECS task def (plaintext) | `/permit_rag/prod/neo4j_auth` |
| `NEO4J_BOLT_URL` | ECS task def (plaintext) | `/permit_rag/prod/neo4j_bolt_url` |

Note: `/permit_rag/prod/anthropic_api_key`, `/permit_rag/prod/admin_token`, `/permit_rag/prod/neo4j_auth`, and `/permit_rag/prod/neo4j_bolt_url` may already exist in SSM from Terraform setup (see README). Verify before creating duplicates.

**Step 3.2 — Create / verify SSM parameters**

```powershell
# Create (or overwrite) each secret as SecureString
aws ssm put-parameter `
  --name "/permit_rag/prod/database_url" `
  --value "postgresql://..." `
  --type SecureString `
  --overwrite

aws ssm put-parameter `
  --name "/permit_rag/prod/langsmith_api_key" `
  --value "lsv2_pt_..." `
  --type SecureString `
  --overwrite

# Repeat for each secret above
```

**Step 3.3 — Verify ECS task execution role has SSM access**

The task **execution role** (not the task role) needs this policy:

```json
{
  "Effect": "Allow",
  "Action": [
    "ssm:GetParameters",
    "ssm:GetParameter"
  ],
  "Resource": "arn:aws:ssm:us-east-1:*:parameter/permit_rag/prod/*"
}
```

Check in IAM → Roles → find the ECS task execution role → Permissions. Add the policy if missing.

**Step 3.4 — Update ECS task definition to use `valueFrom`**

For each secret, change the container environment entry from:

```json
{ "name": "ANTHROPIC_API_KEY", "value": "sk-ant-..." }
```

to:

```json
{
  "name": "ANTHROPIC_API_KEY",
  "valueFrom": "arn:aws:ssm:us-east-1:<account-id>:parameter/permit_rag/prod/anthropic_api_key"
}
```

Create the new task definition revision. Force a new deployment. Watch CloudWatch logs for startup errors — a missing SSM permission or wrong ARN will cause the container to fail to start.

**Step 3.5 — Remove the legacy `API_JWT_SECRET` var**

Sprint 11 removed custom JWT minting. `API_JWT_SECRET` in `.env` is now dead code. Remove it from:
- Root `.env`
- ECS task definition (if present)
- SSM (if it was stored there)

**Verification:**
- ECS service reaches stable state
- `GET /health` returns `{"status": "healthy"}`
- `GET /auth/me` with a valid token returns user profile
- A query via `POST /query/answer` returns a cited answer (confirms Anthropic key loaded correctly)

---

## What stays as plain env vars (never goes to SSM)

These are config, not secrets — fine to leave as plain ECS task def env vars:

```
ENVIRONMENT=production
LOG_LEVEL=INFO
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-4-5-20251001
COGNITO_USER_POOL_ID=us-east-1_HF3i1xgNF
COGNITO_REGION=us-east-1
API_ADMIN_AUTH_REQUIRED=true
API_ADMIN_ALLOWED_ROLES=admin,owner
API_CORS_ALLOW_ORIGINS=https://permits.scottsalhanick.com
API_CORS_ALLOW_ALL=false
API_CORS_ALLOW_LOCALHOST=false
RAGAS_EVAL_MAX_TOKENS=4096
RAGAS_FAITH_RETRIES=2
```

---

## Rollback procedure

Each gap is independently reversible:

- **Gap 1 rollback**: Revert `deploy.yml` to hardcoded values. No infra change needed.
- **Gap 2 rollback**: Re-add `ENV` lines to `Dockerfile` and redeploy.
- **Gap 3 rollback**: Create a new task def revision replacing `valueFrom` entries with plain `value` entries. The SSM parameters remain (no data loss).

---

## Priority / timeline

| Gap | Effort | Priority |
|-----|--------|----------|
| Gap 1 (GitHub vars) | 15 min | Do next sprint |
| Gap 2 (Dockerfile ENV) | 30 min | Do next sprint |
| Gap 3 (SSM secrets) | 2–3 hrs | Before any shared access / customer demo |
