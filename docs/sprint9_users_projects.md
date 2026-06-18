# Sprint 9 — Users & Projects

_permit_rag · authored 2026-06-17 · respects AGENTS.md rules throughout_

---

## Decisions locked in

| # | Decision |
|---|---|
| 1 | **JWT** — stateless HS256 access tokens (short-lived) + refresh tokens (long-lived, stored-hash for revocation) |
| 2 | **Multi-identifier login** — users may authenticate with `username`, `email`, or `phone_number` |
| 3 | **Project sharing** — `project_members` join table; `owner / editor / viewer` roles; only owner changes roles; ownership can be transferred; shared documents visible to all members |
| 4 | **Logout everywhere** — refresh token hash stored in `users` table; rotating or revoking it invalidates all sessions |
| 5 | **Username hardening** — lowercase-stored, reserved-word blocked, strict character/length/structure rules (see Phase 0) |
| 6 | **Phone optional, email required** — at registration email is mandatory; phone is an optional second identifier |

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (Vite+React)                                          │
│  • Login form (username OR email OR phone)                      │
│  • Project sidebar + member management drawer                   │
│  • Share document modal (pick project, pick role)               │
└──────────────────────┬──────────────────────────────────────────┘
                       │ JWT Bearer
┌──────────────────────▼──────────────────────────────────────────┐
│  FastAPI                                                         │
│  POST /auth/register · /auth/login · /auth/refresh              │
│  POST /auth/logout-all                                          │
│  GET/POST/PATCH /projects · /projects/{id}/members              │
│  POST /projects/{id}/documents/{doc_id}/share                   │
└──────────────────────┬──────────────────────────────────────────┘
                       │ psycopg3 pool (db/client.py only)
┌──────────────────────▼──────────────────────────────────────────┐
│  Postgres                                                        │
│  users · projects · project_members · project_documents         │
│  (+ documents.project_id nullable FK for upload-time binding)   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 0 — Username hardening rules

Enforce these at **every layer** — DB, Python validator, and Pydantic schema.

### Allowed structure

| Rule | Value | Rationale |
|---|---|---|
| Allowed chars | `a-z 0-9 _ . -` | Underscore/dot/hyphen are industry-standard (GitHub, Slack) |
| Min length | 3 | Prevents `a`, `ab` squatting |
| Max length | 30 | Fits UI; matches Twitter/GitHub |
| Must start with | letter or digit | No `_admin`, `.hidden` style confusion |
| Must end with | letter or digit | No trailing dots/dashes |
| No consecutive specials | `__ .. -- .- -_` etc. | Blocks visual spoofing (`user__admin`) |
| Case | **stored lowercase** | Login is case-insensitive; prevents `Admin` vs `admin` impersonation |

### Regex (use both checks)

```python
import re

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.\-]{1,28}[a-z0-9]$")
CONSECUTIVE_SPECIAL_RE = re.compile(r"[_\.\-]{2,}")

def validate_username(raw: str) -> str:
    """Normalize and validate a username. Returns lowercased value or raises ValueError."""
    username = raw.strip().lower()
    if not USERNAME_RE.match(username):
        raise ValueError(
            "Username must be 3-30 characters, start and end with a letter or digit, "
            "and contain only letters, digits, underscores, dots, or hyphens."
        )
    if CONSECUTIVE_SPECIAL_RE.search(username):
        raise ValueError("Username may not contain consecutive special characters.")
    if username in RESERVED_USERNAMES:
        raise ValueError(f"Username '{username}' is reserved.")
    return username
```

### Reserved username blocklist

```python
RESERVED_USERNAMES: frozenset[str] = frozenset({
    # Routing conflicts
    "api", "auth", "login", "logout", "register", "me", "self",
    # System actors
    "admin", "administrator", "root", "superuser", "system", "service",
    # Common confusion
    "null", "undefined", "true", "false", "none",
    # Support / trust & safety
    "support", "help", "billing", "security", "abuse", "noreply",
    # Brand protection
    "permitrag", "permit_rag", "permit.rag",
})
```

> [!NOTE]
> `validate_username()` lives in `api/auth.py` (the auth module) and is called by the register route before hitting the DB. This keeps all identity logic in one place per AGENTS.md.

---

## Phase 1 — Migration 011

File: `db/migrations/011_users_projects.sql`

> [!CAUTION]
> Never modify this file after running it — AGENTS.md rule. Test against local Docker first.

```sql
-- ── Enum ──────────────────────────────────────────────────────
create type project_role as enum ('owner', 'editor', 'viewer');

-- ── users ─────────────────────────────────────────────────────
create table users (
    id                   uuid primary key default gen_random_uuid(),
    username             text unique not null,   -- always stored lowercase; see validate_username()
    email                text unique not null,   -- required; used as recovery/notification address
    phone_number         text unique,            -- optional; E.164 format: +12145550100
    password_hash        text not null,          -- Argon2id encoded string
    role                 text not null default 'member'
                             constraint chk_user_role check (role in ('admin','member')),
    is_active            boolean not null default true,
    -- Refresh token revocation (logout-everywhere)
    refresh_token_hash   text,                   -- SHA-256 of last issued refresh token
    token_family         uuid default gen_random_uuid(),
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now()
);

create index idx_users_username on users (username);
create index idx_users_email    on users (email)        where email is not null;
create index idx_users_phone    on users (phone_number) where phone_number is not null;
create index idx_users_active   on users (is_active)    where is_active = true;

create trigger trg_users_updated_at
    before update on users
    for each row execute function update_updated_at();

-- ── projects ──────────────────────────────────────────────────
create table projects (
    id              uuid primary key default gen_random_uuid(),
    name            text not null,
    description     text,
    owner_user_id   uuid not null references users(id) on delete restrict,
    municipality    text,
    is_active       boolean not null default true,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index idx_projects_owner        on projects (owner_user_id);
create index idx_projects_municipality on projects (municipality);
create index idx_projects_active       on projects (is_active) where is_active = true;

create trigger trg_projects_updated_at
    before update on projects
    for each row execute function update_updated_at();

-- ── project_members ───────────────────────────────────────────
create table project_members (
    project_id  uuid not null references projects(id) on delete cascade,
    user_id     uuid not null references users(id)    on delete cascade,
    role        project_role not null default 'viewer',
    invited_at  timestamptz not null default now(),
    primary key (project_id, user_id)
);

create index idx_project_members_user on project_members (user_id);

-- ── project_documents (shared doc registry) ───────────────────
-- A document can be shared into multiple projects.
create table project_documents (
    project_id   uuid not null references projects(id) on delete cascade,
    document_id  uuid not null references documents(id) on delete cascade,
    added_by     uuid references users(id) on delete set null,
    added_at     timestamptz not null default now(),
    primary key (project_id, document_id)
);

create index idx_project_documents_document on project_documents (document_id);

-- ── FK on documents for upload-time project binding ───────────
alter table documents
    add column project_id uuid references projects(id) on delete set null;

create index idx_documents_project
    on documents (project_id) where project_id is not null;

-- ── RLS (service_role full access — user-scoped policies later) ─
alter table users             enable row level security;
alter table projects          enable row level security;
alter table project_members   enable row level security;
alter table project_documents enable row level security;

create policy "service_role_all" on users             for all using (true) with check (true);
create policy "service_role_all" on projects          for all using (true) with check (true);
create policy "service_role_all" on project_members   for all using (true) with check (true);
create policy "service_role_all" on project_documents for all using (true) with check (true);
```

**Run command:**
```powershell
psql $env:DATABASE_URL -f db/migrations/011_users_projects.sql
```

---

## Phase 2 — New dependencies

Add to `pyproject.toml`:
```toml
"argon2-cffi>=23.1",
"PyJWT>=2.8",
"email-validator>=2.1",
"phonenumbers>=8.13",
```

Install:
```powershell
py -m pip install argon2-cffi PyJWT email-validator phonenumbers
```

---

## Phase 3 — `api/auth.py`

All JWT and password logic lives here exclusively. No other module calls `jwt.*` or `argon2.*`.

### Functions to implement

| Function | Signature | Notes |
|---|---|---|
| `hash_password` | `(plaintext: str) -> str` | Argon2id via `argon2-cffi` |
| `verify_password` | `(plaintext: str, hashed: str) -> bool` | Catches `VerifyMismatchError` |
| `hash_for_storage` | `(token: str) -> str` | SHA-256 hex; used for refresh token DB storage |
| `create_access_token` | `(user_id, role) -> str` | 15-min HS256 JWT |
| `create_refresh_token` | `(user_id, family) -> str` | 7-day JWT; `family` UUID rotates each use |
| `decode_token` | `(token, expected_type) -> dict` | Raises HTTP 401 on expired/invalid/wrong type |
| `get_current_user` | FastAPI `Depends` | Extracts `user_id` + `role` from `Authorization: Bearer` |

### Logout-everywhere flow

```
POST /auth/login
  → issue refresh_token
  → store SHA-256(refresh_token) in users.refresh_token_hash

POST /auth/refresh (body: {refresh_token})
  → decode token → check DB hash matches → issue new pair
  → update hash + rotate token_family UUID

POST /auth/logout-all
  → set users.refresh_token_hash = NULL
  → generate new token_family UUID
  → all existing refresh tokens are now invalid
```

> [!IMPORTANT]
> Access tokens cannot be revoked mid-TTL. Keep `API_JWT_ACCESS_TTL_MIN=15` in production to limit exposure window.

---

## Phase 4 — `db/client.py` additions

All functions ≤ 50 lines per AGENTS.md. Add as three new labelled sections.

### USERS section — function signatures

```python
def create_user(*, username, email, phone_number, password_hash, role="member") -> dict:
    """Insert user. Raises psycopg.errors.UniqueViolation on duplicate username/email/phone."""

def get_user_by_identifier(identifier: str) -> Optional[dict]:
    """Try username, then email, then phone_number. Returns first match or None."""

def get_user_by_id(user_id: UUID) -> Optional[dict]:
    """Fetch active user by primary key."""

def update_refresh_token_hash(user_id: UUID, token_hash: Optional[str], family: Optional[UUID]) -> None:
    """Store or clear refresh_token_hash + token_family atomically."""

def get_refresh_token_meta(user_id: UUID) -> Optional[dict]:
    """Return {refresh_token_hash, token_family} for revocation check."""

def deactivate_user(user_id: UUID) -> Optional[dict]:
    """Soft-delete: is_active=False, refresh_token_hash=NULL."""
```

### PROJECTS section — function signatures

```python
def create_project(*, name, owner_user_id, description=None, municipality=None) -> dict:
    """Create project + enroll owner as role='owner' in one transaction."""

def get_project(project_id: UUID) -> Optional[dict]:
    """Fetch active project by UUID."""

def list_projects_for_user(user_id: UUID) -> list[dict]:
    """All active projects where user is a member (any role)."""

def update_project(project_id: UUID, *, name=None, description=None, municipality=None) -> Optional[dict]:
    """Update mutable project fields. Skips if no args provided."""

def transfer_project_ownership(project_id: UUID, new_owner_id: UUID) -> Optional[dict]:
    """
    Atomic:
      1. UPDATE projects SET owner_user_id = new_owner_id
      2. UPSERT project_members (new owner, role='owner')
      3. UPDATE project_members SET role='editor' WHERE user_id = old_owner_id
    Returns updated project row.
    """

def archive_project(project_id: UUID) -> Optional[dict]:
    """Soft-delete: is_active=False."""
```

### PROJECT MEMBERS section — function signatures

```python
def get_project_role(project_id: UUID, user_id: UUID) -> Optional[str]:
    """Return role string or None if not a member."""

def list_project_members(project_id: UUID) -> list[dict]:
    """Join with users table: returns id, username, email, role, invited_at."""

def upsert_project_member(project_id: UUID, user_id: UUID, *, role: str) -> dict:
    """Add or update member. ON CONFLICT (project_id, user_id) DO UPDATE role."""

def remove_project_member(project_id: UUID, user_id: UUID) -> bool:
    """Remove member. Raises ValueError if user is current owner."""
```

### PROJECT DOCUMENTS section — function signatures

```python
def share_document_to_project(project_id: UUID, document_id: UUID, added_by: UUID) -> dict:
    """Insert into project_documents. ON CONFLICT DO NOTHING (idempotent)."""

def list_project_documents(project_id: UUID) -> list[dict]:
    """JOIN documents — returns doc metadata for all docs shared into project."""

def unshare_document_from_project(project_id: UUID, document_id: UUID) -> bool:
    """DELETE from project_documents. Returns False if row not found."""
```

---

## Phase 5 — New API routes

### `api/routes/auth.py`

| Method | Path | Auth required | Description |
|---|---|---|---|
| `POST` | `/auth/register` | none | Create account |
| `POST` | `/auth/login` | none | Login; returns access + refresh tokens |
| `POST` | `/auth/refresh` | refresh token in body | Rotate tokens; revoke old refresh |
| `POST` | `/auth/logout-all` | Bearer access | Clear refresh hash; all sessions dead |

**Validation rules:**
- `username`: run through `validate_username()` from `api/auth.py` (lowercase, regex, reserved-word check)
- `password`: ≥ 10 chars
- `email`: `EmailStr` via pydantic-email-validator — **required** at registration
- `phone_number`: optional; if provided, validate with `phonenumbers.parse()` and store as E.164

### `api/routes/projects.py`

| Method | Path | Min Role | Description |
|---|---|---|---|
| `POST` | `/projects` | authenticated | Create; caller becomes owner |
| `GET` | `/projects` | authenticated | List caller's projects |
| `GET` | `/projects/{id}` | viewer | Project details |
| `PATCH` | `/projects/{id}` | owner | Update name / description / municipality |
| `DELETE` | `/projects/{id}` | owner | Archive (soft-delete) |
| `POST` | `/projects/{id}/transfer` | owner | Transfer ownership |
| `GET` | `/projects/{id}/members` | viewer | List members + roles |
| `POST` | `/projects/{id}/members` | owner | Add member |
| `PATCH` | `/projects/{id}/members/{uid}` | owner | Change role |
| `DELETE` | `/projects/{id}/members/{uid}` | owner | Remove member |
| `GET` | `/projects/{id}/documents` | viewer | List shared docs |
| `POST` | `/projects/{id}/documents` | editor/owner | Share document into project |
| `DELETE` | `/projects/{id}/documents/{doc_id}` | editor/owner | Unshare document |

**Role guard helper** (lives in `api/routes/projects.py`):
```python
def _require_role(project_id: UUID, user_id: UUID, allowed: set[str]) -> None:
    """Raise HTTP 403 if user's project role is not in allowed set."""
    role = db_client.get_project_role(project_id, user_id)
    if role not in allowed:
        raise HTTPException(status_code=403, detail="Insufficient project role.")
```

### Wire into `api/main.py`
```python
from api.routes.auth     import router as auth_router
from api.routes.projects import router as projects_router

app.include_router(auth_router)
app.include_router(projects_router)
```

---

## Phase 6 — Pydantic schemas (add to `api/schemas.py`)

```python
class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    # Pattern left loose here — full hardening (lowercase, reserved words, consecutive special)
    # is enforced by validate_username() in api/auth.py before the DB call.
    password: str = Field(min_length=10)
    email: EmailStr                          # required
    phone_number: Optional[str] = None       # optional; E.164 validated in route handler

class LoginRequest(BaseModel):
    identifier: str   # username, email, or phone — route resolves which
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str

class UserResponse(BaseModel):
    id: UUID
    username: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    role: str
    created_at: datetime
    # password_hash NEVER included

class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    municipality: Optional[str] = None

class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    owner_user_id: UUID
    municipality: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

class ProjectMemberResponse(BaseModel):
    user_id: UUID
    username: str
    email: Optional[str] = None
    role: str   # owner | editor | viewer
    invited_at: datetime

class AddMemberRequest(BaseModel):
    user_id: UUID
    role: str = Field(default="viewer", pattern=r"^(editor|viewer)$")
    # 'owner' is set only via /transfer endpoint

class TransferOwnershipRequest(BaseModel):
    new_owner_id: UUID

class ShareDocumentRequest(BaseModel):
    document_id: UUID
```

---

## Phase 7 — Upload route update

In `api/routes/upload.py`, add `project_id` to the upload body and auto-share on ingest:

```python
# Add to existing upload body schema:
project_id: Optional[UUID] = None

# After insert_document() succeeds:
if body.project_id:
    db_client.share_document_to_project(
        body.project_id,
        doc_row["id"],
        current_user["user_id"],
    )
```

---

## Phase 8 — Frontend UI components

| Component | Route/Location | Key API calls |
|---|---|---|
| `LoginPage` | `/login` | `POST /auth/login` |
| `RegisterPage` | `/register` | `POST /auth/register` |
| `ProjectsSidebar` | Persistent left rail | `GET /projects` |
| `CreateProjectModal` | Sidebar button | `POST /projects` |
| `ProjectMembersDrawer` | Project header | `GET /projects/{id}/members` |
| `AddMemberModal` | Inside drawer | `POST /projects/{id}/members` |
| `ChangeRoleDropdown` | Each member row (owner only) | `PATCH /projects/{id}/members/{uid}` |
| `TransferOwnershipModal` | Owner-only action | `POST /projects/{id}/transfer` |
| `ShareDocumentModal` | Document detail | `POST /projects/{id}/documents` |
| `ProjectDocumentsPanel` | Project view | `GET /projects/{id}/documents` |

**Auth state pattern:**
- `access_token` → React context / Zustand (in-memory)
- `refresh_token` → `localStorage` (persists across tab close)
- On HTTP 401 → call `POST /auth/refresh` → retry once → if still 401 → redirect `/login`
- Logout-everywhere button → `POST /auth/logout-all` → clear local tokens → redirect `/login`

---

## Phase 9 — Tests (`tests/test_sprint9.py`)

Target: **~20 new tests → 92 total**

| Group | Count | What it tests |
|---|---|---|
| `TestPasswordHashing` | 2 | hash+verify roundtrip; wrong password |
| `TestJWTTokens` | 4 | access/refresh roundtrip; expired → 401; wrong type → 401 |
| `TestLogoutEverywhere` | 2 | cleared hash blocks refresh; new token after re-login works |
| `TestTokenFamilyRotation` | 1 | reused refresh token from old family rejected |
| `TestUsernameValidation` | 5 | valid username passes; reserved name raises; consecutive special raises; uppercase normalized; too-short raises |
| `TestUserCreation` | 3 | create returns row; duplicate username → error; duplicate email → error |
| `TestMultiIdentifierLookup` | 4 | hit by username; hit by email; hit by phone; miss → None |
| `TestProjectLifecycle` | 3 | create enrolls owner; archive sets is_active=False; get returns row |
| `TestOwnershipTransfer` | 2 | new owner gets 'owner' role; old owner downgraded to 'editor' |
| `TestMemberRoles` | 3 | viewer blocked from editor route (403); editor blocked from transfer (403); owner succeeds |
| `TestDocumentSharing` | 3 | share adds row; list returns it; idempotent share is safe |

---

## `.env` additions

```dotenv
# JWT
# Generate secret: python -c "import secrets; print(secrets.token_hex(32))"
API_JWT_SECRET=<min-32-chars-hex>
API_JWT_ACCESS_TTL_MIN=15
API_JWT_REFRESH_TTL_DAYS=7
```

---

## Implementation order

```
1.  Add deps to pyproject.toml
    py -m pip install argon2-cffi PyJWT email-validator phonenumbers

2.  Write api/auth.py
    Write test_sprint9.py (TestPasswordHashing + TestJWTTokens + TestLogoutEverywhere)
    py -m pytest tests/test_sprint9.py -k "password or jwt or logout" -v

3.  Run migration 011 (local Docker first)
    psql $env:DATABASE_URL -f db/migrations/011_users_projects.sql

4.  Add USERS functions to db/client.py
    Write TestUserCreation + TestMultiIdentifierLookup tests

5.  Add PROJECTS + MEMBERS + PROJECT_DOCUMENTS to db/client.py
    Write TestProjectLifecycle + TestOwnershipTransfer + TestDocumentSharing tests

6.  Write api/routes/auth.py + api/routes/projects.py
    Write TestMemberRoles + TestTokenFamilyRotation tests

7.  Add schemas to api/schemas.py
    Wire both routers into api/main.py

8.  Update api/routes/upload.py (project_id param + auto-share)

9.  Full suite
    py -m pytest tests/ -v

10. Eval guard (retrieval pipeline must not regress)
    py -m evaluation.eval_guard
```

---

## Security checklist

- [ ] `password_hash` never in any `*Response` schema
- [ ] `refresh_token_hash` never in any `*Response` schema
- [ ] `API_JWT_SECRET` in `.env` only — already in `.gitignore`
- [ ] Phone numbers stored as E.164, validated before insert (optional field)
- [ ] Email required at registration; uniqueness at DB level (unique index) AND app level (409 before insert)
- [ ] Usernames stored lowercase; `validate_username()` runs before any DB call
- [ ] Reserved username blocklist kept in `api/auth.py` as a `frozenset`
- [ ] Owner cannot remove themselves (enforced in `remove_project_member`)
- [ ] Transfer endpoint auto-adds new owner if not already a member
- [ ] `token_family` UUID rotates on every refresh — replay attack detection
- [ ] Rate-limit `/auth/register` and `/auth/login` in production
- [ ] Access token TTL ≤ 15 min in production
