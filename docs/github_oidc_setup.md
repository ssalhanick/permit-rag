# GitHub Actions OIDC Setup for AWS Deploy

GitHub Actions authenticates to AWS using **OpenID Connect (OIDC)** — not SAML, not long-lived access keys.

---

## Step 1 — Add the OIDC identity provider (IAM)

1. AWS Console → **IAM** → **Identity providers** → **Add provider**
2. **Provider type:** `OpenID Connect` ← not SAML
3. **Provider URL** — paste exactly (lowercase, no trailing slash, no spaces):

   ```
   https://token.actions.githubusercontent.com
   ```

4. Click **Get thumbprint**. If that button fails or stays red, paste this thumbprint manually:

   ```
   6938fd4d98bab03faadb97b34396831e3780aea1
   ```

5. **Audience:** `sts.amazonaws.com`
6. Click **Add provider**

If the provider already exists, skip this step.

### Provider URL not working? Common fixes

| Problem | Fix |
|---------|-----|
| Red error on URL or thumbprint | Use manual thumbprint above; do not add a trailing `/` |
| Wrong hostname | Must be `token.actions.githubusercontent.com` — not `github.com`, not `vstoken.actions...` (old URL) |
| Wrong casing | All lowercase: `githubusercontent` not `GitHubusercontent` |
| **Get thumbprint** times out | Network/firewall blocking AWS → GitHub; use CLI below from your machine |
| Provider already exists | IAM → Identity providers — if listed, skip to Step 2 |

### CLI fallback (run locally if console fails)

```powershell
aws iam create-open-id-connect-provider --url "https://token.actions.githubusercontent.com" --client-id-list "sts.amazonaws.com" --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1"
```

If you get `EntityAlreadyExists`, the provider is already there — proceed to Step 2.

Verify:

```powershell
aws iam list-open-id-connect-providers
```

You should see an ARN ending in `oidc-provider/token.actions.githubusercontent.com`.

---

## Step 2 — Create the deploy IAM role

1. IAM → **Roles** → **Create role**
2. **Trusted entity type:** `Web identity`
3. **Identity provider:** `token.actions.githubusercontent.com`
4. **Audience:** `sts.amazonaws.com`
5. Click **Next** (skip attaching policies for now — add a custom policy in Step 3)
6. Role name: `github-permit-rag-deploy`
7. After creation, open the role → **Trust relationships** → **Edit trust policy**

Replace with (update account ID and repo if different):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:ssalhanick/permit-rag:*"
        }
      }
    }
  ]
}
```

To lock deploys to the production branch only, use:

```json
"token.actions.githubusercontent.com:sub": "repo:ssalhanick/permit-rag:ref:refs/heads/deployment/sites"
```

For branch deploys **and** manual `workflow_dispatch`, use two conditions or the broader `repo:ssalhanick/permit-rag:*` pattern above.

Copy the role ARN — you will store it as GitHub variable `AWS_ROLE_ARN`.

---

## Step 3 — Attach deploy permissions

**Do not attach existing Terraform policies** like `permit-rag-ecs-secrets-policy`. That policy is for **ECS containers at runtime** (read SSM secrets). GitHub Actions needs a **new, separate policy** to push Docker images, restart ECS, upload to S3, and invalidate CloudFront.

### What each existing policy is for

| Name in IAM | Used by | Purpose |
|-------------|---------|---------|
| `permit-rag-ecs-secrets-policy` | ECS task execution role | Read `/permit_rag/prod/*` from SSM at container startup |
| `AmazonECSTaskExecutionRolePolicy` | ECS task execution role | Pull images from ECR, write logs |
| **New: `permit-rag-github-deploy`** | **`github-permit-rag-deploy` role** | **CI deploy: ECR push, ECS redeploy, S3 sync, CloudFront invalidation** |

Searching "ECR" in IAM will show ECR-related *resources*, not a ready-made "GitHub push" policy. You create a custom policy.

---

### Console: add permissions to the GitHub role

1. IAM → **Roles** → open **`github-permit-rag-deploy`** (the role you created in Step 2)
2. **Permissions** tab → **Add permissions** → **Create inline policy**
3. Click **JSON** tab
4. Paste the policy below (already filled for this project’s Terraform outputs)
5. Click **Next**
6. Policy name: `permit-rag-github-deploy`
7. Click **Create policy**

You should see one inline policy on the role. Trust relationship + this policy = what GitHub Actions needs.

---

### Policy JSON (permit_rag production — copy/paste)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRLogin",
      "Effect": "Allow",
      "Action": ["ecr:GetAuthorizationToken"],
      "Resource": "*"
    },
    {
      "Sid": "ECRPush",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "arn:aws:ecr:us-east-1:983003703881:repository/permit-rag-backend"
    },
    {
      "Sid": "ECSDeploy",
      "Effect": "Allow",
      "Action": [
        "ecs:UpdateService",
        "ecs:DescribeServices"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3FrontendSync",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::permit-rag-frontend-20260618213648878000000001",
        "arn:aws:s3:::permit-rag-frontend-20260618213648878000000001/*"
      ]
    },
    {
      "Sid": "CloudFrontInvalidate",
      "Effect": "Allow",
      "Action": ["cloudfront:CreateInvalidation"],
      "Resource": "arn:aws:cloudfront::983003703881:distribution/E32MQDJSIESTC6"
    }
  ]
}
```

If you recreate frontend infra later, update the S3 bucket name and CloudFront ID from:

```powershell
terraform -chdir=terraform output -raw frontend_bucket_name
terraform -chdir=terraform output -raw cloudfront_distribution_id
```

---

### What each statement allows

| Sid | GitHub Action step | Why |
|-----|-------------------|-----|
| `ECRLogin` | `aws ecr get-login-password` / `amazon-ecr-login` | Auth to registry (must be `Resource: *`) |
| `ECRPush` | `docker push` to `permit-rag-backend` | Upload new backend image |
| `ECSDeploy` | `aws ecs update-service --force-new-deployment` | Roll out new container |
| `S3FrontendSync` | `aws s3 sync frontend/dist/` | Publish React build |
| `CloudFrontInvalidate` | `aws cloudfront create-invalidation` | Clear CDN cache |

---

### Optional: Visual editor path (if you prefer clicks over JSON)

On **Create inline policy** → **Visual** tab, add four statement groups:

1. **Service: ECR** → Actions: `GetAuthorizationToken` → Resources: All
2. **Service: ECR** → Actions: push-related (`PutImage`, `UploadLayerPart`, etc.) → Resource: `permit-rag-backend` repository ARN
3. **Service: ECS** → Actions: `UpdateService`, `DescribeServices` → Resources: All (or cluster/service ARNs if you want tighter scope)
4. **Service: S3** → Actions: `ListBucket`, `PutObject`, `DeleteObject` → Bucket + `bucket/*` for frontend bucket
5. **Service: CloudFront** → Action: `CreateInvalidation` → Your distribution ARN

JSON is faster and less error-prone — use the block above.

---

### Policies you should NOT attach to the GitHub role

- `permit-rag-ecs-secrets-policy` — SSM read for running ECS tasks only
- `AdministratorAccess` — too broad
- `AmazonEC2ContainerRegistryFullAccess` — works but over-permissive (all repos in account)


---

## Step 4 — GitHub repository variables

Repo → **Settings** → **Secrets and variables** → **Actions** → **Variables**:

| Variable | Value |
|----------|-------|
| `AWS_REGION` | `us-east-1` |
| `AWS_ROLE_ARN` | `arn:aws:iam::983003703881:role/github-permit-rag-deploy` |
| `ECR_REPOSITORY` | `983003703881.dkr.ecr.us-east-1.amazonaws.com/permit-rag-backend` |
| `ECS_CLUSTER` | `permit-rag-cluster` |
| `ECS_SERVICE` | `permit-rag-service` |
| `S3_FRONTEND_BUCKET` | `permit-rag-frontend-20260618213648878000000001` |
| `CLOUDFRONT_DISTRIBUTION_ID` | `E32MQDJSIESTC6` |

Optional secret: `VITE_MAPBOX_TOKEN` (frontend build only).

No `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` needed when OIDC is configured correctly.

---

## Verify OIDC works

After `.github/workflows/deploy.yml` is on `deployment/sites`, push a commit or run **Actions → Deploy to AWS → Run workflow**.

Common failures:

| Error | Fix |
|-------|-----|
| `Not authorized to perform sts:AssumeRoleWithWebIdentity` | Trust policy `sub` claim does not match repo/branch |
| `Could not assume role` | Wrong `AWS_ROLE_ARN` in GitHub variables |
| Provider not found | Step 1 not done, or wrong provider URL |
| Used SAML by mistake | Delete and re-add as **OpenID Connect** |

---

## Reference

- [GitHub: Configuring OpenID Connect in AWS](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- Local fallback deploy: `npm run deploy` / `scripts/deploy.ps1`
