# Environment & Secrets Strategy

_Created: 2026-06-30 | Status: Partially implemented — Gap 3 (SSM-backed secrets) is done for everything except the DATABASE_URL family; see "Known gaps" below. Updated 2026-08-07 after the reprocess-log credential leak incident confirmed the actual `terraform/main.tf` state diverged from this doc._

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
| 3 | `DATABASE_URL`, `CORPUS_WRITER_URL`, `APP_READER_URL` stored as plaintext in ECS task definition (`terraform/main.tf:361-363`) — composed by interpolating the SSM-sourced password directly into a `value` field, not a `valueFrom` reference | Visible in AWS Console and in every past task definition revision (immutable — old revisions retain the old value even after rotation); not rotatable without a `terraform apply` |

**Already done, contrary to earlier drafts of this doc:** `ANTHROPIC_API_KEY`, `API_ADMIN_TOKEN`, `LANGSMITH_API_KEY`, `OPENAI_API_KEY`, `LEONARDO_API_KEY`, `FAL_API_KEY`, `SERPAPI_API_KEY`, `JWT_SECRET`, and the Neo4j values are all real `valueFrom` SSM references (`terraform/main.tf:381-417`) — Gap 3 below is closed for these. Only the DATABASE_URL family (row 3 above) remains open.

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
│ AWS SSM Parameter Store (SecureString) — actual paths     │
│ per terraform/main.tf. Not "database_url" — the full      │
│ DATABASE_URL is composed at apply time by interpolating   │
│ db_password into a connection string, not stored whole:   │
│  /permit_rag/prod/db_password                              │
│  /permit_rag/prod/anthropic_api_key                        │
│  /permit_rag/prod/admin_token                               │
│  /permit_rag/prod/langsmith_api_key                         │
│  /permit_rag/prod/neo4j_auth                                 │
│  /permit_rag/prod/neo4j_bolt_url                              │
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

**Status: done for everything except `DATABASE_URL`/`CORPUS_WRITER_URL`/`APP_READER_URL`.** `ANTHROPIC_API_KEY`, `API_ADMIN_TOKEN`, `LANGSMITH_API_KEY`, `OPENAI_API_KEY`, `LEONARDO_API_KEY`, `FAL_API_KEY`, `SERPAPI_API_KEY`, `JWT_SECRET`, `NEO4J_AUTH`, `NEO4J_BOLT_URL` are already wired as real `valueFrom` SSM references in `terraform/main.tf:381-417` — steps 3.1-3.4 below are already implemented for these and don't need re-doing. What follows is scoped to the one remaining item.

**Note on the SSM parameters themselves:** these are Terraform `data` sources (`data "aws_ssm_parameter" ...`, e.g. `main.tf:197-198`), not `resource` blocks — Terraform only *reads* them, it doesn't create or manage their values. Each parameter is created/updated out-of-band via `aws ssm put-parameter` (console or CLI), then Terraform picks up the current value on the next `plan`/`apply`. The correct path for the DB credential is `/permit_rag/prod/db_password` — **not** `/permit_rag/prod/database_url` (an earlier draft of this doc named a path that was never actually implemented).

**Remaining work — `DATABASE_URL` family (architecturally different from the others, not a simple `valueFrom` swap):**

`terraform/main.tf:361-363` composes three connection strings by interpolating `data.aws_ssm_parameter.db_password.value` directly into a plaintext `value` field:
```hcl
{ name = "DATABASE_URL", value = "postgresql://postgres:${data.aws_ssm_parameter.db_password.value}@${aws_db_instance.postgres.endpoint}/permit_rag?sslmode=require" },
```
ECS's `valueFrom` substitutes a named SSM parameter's raw content verbatim into one env var — it can't do string composition (host + password + query string), so this can't be fixed the same way the other secrets were (just adding `valueFrom` to an existing plaintext `value`). Two real options, not yet decided:

1. **Store the fully-composed connection strings as their own SSM `SecureString`s** (three new parameters — `database_url`, `corpus_writer_url`, `app_reader_url`), written by a `resource "aws_ssm_parameter"` block in Terraform (not just a `data` source, since something has to actually write the composed value), then reference each via `valueFrom`. Adds a write-capable IAM permission for Terraform's own execution identity, and means the composed connection string exists in Terraform state either way (see `docs/secrets_leak_protocol.md`'s note on local state already holding this).
2. **Have the app compose the DSN itself at runtime** from three separately-injected, individually-`valueFrom`-able pieces (host, user, password) instead of one pre-built URL — larger change, touches `api/load_env.py`/`db/client.py`'s connection setup, but avoids ever materializing the full connection string as a stored secret anywhere.

Neither is implemented. Whoever picks this up: decide between the two above before touching `main.tf` — this doc previously implied it was a one-line `valueFrom` change, which undersold the real work.

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
| Gap 3 (SSM secrets) | Mostly done — remaining scope is just the `DATABASE_URL` family, needs an architecture decision first (see Gap 3 above), then ~2-3 hrs to implement | Before any shared access / customer demo |
