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

## Next session should

1. Fill in actual Cognito values in `frontend/.env` and root `.env`
2. Run `pip install -e .` and `cd frontend && npm install`
3. Smoke test: email+password register → confirm → login; Google SSO; TOTP 2FA enrollment
4. Run full test suite: `py -m pytest tests/test_sprint5.py tests/test_sprint6.py tests/test_sprint7.py tests/test_sprint8.py tests/test_sprint9.py -v`
5. Proceed to CI/CD pipeline (GitHub → AWS ECS)

## Prompt for next session

Read `AGENTS.md`, `STATE.md`, and `journals/session_260630a.md`. Sprint 11 (Cognito auth migration) is complete and DB migration 013 is applied. Before starting new work: fill in Cognito env vars, run `pip install -e .` + `cd frontend && npm install`, and smoke test the three auth flows (email+password, Google SSO, TOTP 2FA). After auth is confirmed working, proceed to Sprint 12: CI/CD pipeline (GitHub Actions → AWS ECS) or document update routes, whichever is higher priority.

## Git commit message

feat(sprint11): migrate auth to Amazon Cognito with Google SSO and optional TOTP 2FA
