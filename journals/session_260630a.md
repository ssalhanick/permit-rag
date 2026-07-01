# Session: 2026-06-30 (a)

## Type

Sprint 11 — Amazon Cognito auth migration.

## Goal

Replace custom Argon2id/JWT auth with Amazon Cognito. Add Google SSO and optional TOTP 2FA. Maintain all existing project RBAC, query history, and document ownership.

---

## Completed

### AWS Setup (manual)
- Created Cognito User Pool `permit-rag-users` (email+password, TOTP MFA optional, Google as Social IdP)
- Created App Client `permit-rag-web` (SPA, no client secret, `USER_PASSWORD_AUTH` + `Authorization code grant`)
- Configured Cognito domain for OAuth callbacks
- Created Google OAuth 2.0 app `permit-rag` in Google Cloud Console, configured authorized JS origins and redirect URI

### Backend
- `db/migrations/013_cognito_auth.sql` — TRUNCATE users CASCADE, drop `password_hash`/`refresh_token_hash`/`token_family`, add `cognito_sub TEXT UNIQUE NOT NULL`
- `api/auth.py` — full rewrite: `verify_cognito_token()` with cached JWKS (1h TTL, re-fetch on unknown kid), `get_current_user` / `get_optional_current_user` FastAPI dependencies that lazy-provision RDS user row
- `api/routes/auth.py` — stripped to `GET /auth/me` only; all credential operations delegated to Cognito
- `api/schemas.py` — added `UserMeResponse`
- `db/client.py` — replaced 5 password-based helpers with `get_or_create_cognito_user()`: primary lookup by `cognito_sub`, email fallback for account linking, auto-derives username from email, retries up to 6x on unique constraint
- `pyproject.toml` — removed `argon2-cffi`, `PyJWT`, `phonenumbers`; added `python-jose[cryptography]>=3.3.0`

### Frontend
- `frontend/src/context/AuthContext.jsx` — full rewrite with `amazon-cognito-identity-js`: `login()`, `register()`, `confirmSignUp()`, `confirmMfa()`, `beginMfaSetup()`, `confirmMfaSetup()`, `loginWithGoogle()`, `handleOAuthCallback()`, `logout()`; `registerTokenRefresher` wired to `api.js` for 401 auto-refresh
- `frontend/src/AuthPage.jsx` — 5-screen state machine: login, register, email confirm, MFA challenge, MFA setup QR (uses `api.qrserver.com` for QR rendering)
- `frontend/src/AuthCallback.jsx` — new file: handles `/auth/callback` redirect, exchanges OAuth2 code for tokens via `POST /oauth2/token`, calls `handleOAuthCallback`, stores tokens in Cognito SDK localStorage format
- `frontend/src/main.jsx` — added `/auth/callback` route
- `frontend/src/api.js` — added `registerTokenRefresher`, removed custom `/auth/refresh` interceptor, removed `loginUser`/`registerUser`/`logoutUser`, added `fetchMe()`
- `frontend/package.json` — added `amazon-cognito-identity-js: ^6.3.12`
- `frontend/.env` — added `VITE_COGNITO_USER_POOL_ID`, `VITE_COGNITO_APP_CLIENT_ID`, `VITE_COGNITO_REGION`, `VITE_COGNITO_DOMAIN`, `VITE_COGNITO_GOOGLE_ENABLED`
- `.env.production` — added `COGNITO_USER_POOL_ID`, `COGNITO_REGION`

### Infrastructure
- `scripts/run_migration.py` — utility script for applying SQL migrations via `db.client`
- DB migration 013 applied to RDS successfully

### Tests
- `tests/test_sprint9.py` — removed `TestPasswordHashing`, `TestUsernameValidation`, `TestPhoneValidation`, `TestJWTTokens`, `TestAuthAPI`; added `TestCognitoVerification` (3 tests: missing kid, unknown kid, invalid signature); updated `auth_headers` fixture to patch `get_current_user` directly

---

## Files changed

- `db/migrations/013_cognito_auth.sql` (new)
- `api/auth.py` (rewrite)
- `api/routes/auth.py` (rewrite)
- `api/schemas.py` (UserMeResponse added)
- `db/client.py` (users section replaced)
- `pyproject.toml` (deps swapped)
- `frontend/package.json` (amazon-cognito-identity-js added)
- `frontend/src/context/AuthContext.jsx` (rewrite)
- `frontend/src/AuthPage.jsx` (rewrite)
- `frontend/src/AuthCallback.jsx` (new)
- `frontend/src/main.jsx` (/auth/callback route added)
- `frontend/src/api.js` (registerTokenRefresher, removed custom auth endpoints)
- `frontend/.env` (Cognito vars added)
- `.env.production` (Cognito vars added)
- `scripts/run_migration.py` (new)
- `STATE.md`, `README.md` (updated)

---

## Follow-up session (same day) completed

All items above were completed in `journals/session_20260630.md`:
- ✅ Cognito env vars filled in (`frontend/.env`, root `.env`, `.env.local`)
- ✅ Google SSO smoke tested end-to-end locally (token exchange → `/auth/me` → user provisioned)
- ✅ CI/CD pipeline already live — Sprint 11 deployed to production via `deployment/sites`
- ✅ `COGNITO_USER_POOL_ID` + `COGNITO_REGION` baked into Dockerfile
- ✅ Cognito vars injected into frontend Vite build via `deploy.yml`

## Still pending (carry into next session)

- ✅ RDS migration 013 applied to production
- ✅ Production callback URL registered in Cognito + Google Cloud Console
- ✅ Google SSO verified end-to-end on `permits.scottsalhanick.com`
- ✅ Full test suite: `test_sprint9.py` — 10 passed (fixed `auth_headers` fixture to use `app.dependency_overrides`; fixed `test_invalid_signature_raises` to mock `JWTError` not plain `Exception`)

**Sprint 11 is fully closed.**

## Prompt for next session

Read `AGENTS.md`, `STATE.md`, and `journals/session_20260630.md`. Sprint 11 is fully closed — Cognito auth with Google SSO is live and verified on `permits.scottsalhanick.com`. Begin Sprint 12: choose between (a) document update routes (`PATCH /documents/{id}` + frontend edit UI) or (b) User Profile Dashboard (WordPress-style sidebar with user settings, project list, query history). Check `README.md` Planned section and confirm priority with user before writing any code.

## Git commit message

feat(sprint11): migrate auth to Amazon Cognito with Google SSO and optional TOTP 2FA
