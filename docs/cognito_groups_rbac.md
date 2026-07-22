# Cognito Groups RBAC — Global Roles Transition

**Status:** Planned  
**Depends on:** Cognito User Pool (`us-east-1_HF3i1xgNF`), existing `users.role`, project_members RBAC  
**Goal:** Make **Cognito groups** the source of truth for global app roles (`member` / `admin` / `superadmin`), so staff power is managed in AWS — not hand-edited SQL. Superadmin can see everything in the product API.

---

## Why

Today:

| Layer | What exists | Gap |
|-------|-------------|-----|
| Cognito | Sign-in (Apple/Google/password) | No groups → no staff roles in JWT |
| `users.role` | `admin` \| `member` (DB check constraint) | Always provisioned as `member`; never synced from Cognito |
| Project RBAC | `owner` / `editor` / `viewer` | Correct; keep for project scoping |
| Ops admin | `X-Admin-Token` + `X-Admin-Role` | Corpus pull/purge/supersede — shared secret |

Industry pattern we want:

1. **IdP groups** (Cognito) = global staff roles  
2. **Resource roles** (project_members) = per-project access  
3. **Break-glass ops token** = destructive corpus / infra actions (keep separate)

---

## Role model (target)

### Global roles (from Cognito groups)

| Cognito group name | App role | Product power |
|--------------------|----------|---------------|
| *(none)* | `member` | Own projects + memberships only |
| `admin` | `admin` | Corpus UI, document governance UI, list users (read), see all projects |
| `superadmin` | `superadmin` | Everything `admin` has + user deactivate, purge any tier (when wired to JWT), bypass all project checks |

Precedence if user is in multiple groups: **`superadmin` > `admin` > `member`**.

### Project roles (unchanged — stay in RDS)

`project_members.role`: `owner` | `editor` | `viewer`

Global `superadmin` / `admin` **bypass** membership checks for read (and for write where product policy allows). They do **not** auto-insert as project `owner` unless we later add an explicit “impersonate / join” action.

### Ops token (unchanged — keep)

| Action | Auth |
|--------|------|
| `POST /admin/documents/pull-page`, supersede, metadata patch | Prefer Cognito `admin`+ **or** keep token during transition |
| Purge non-tier-3 / break-glass | Prefer Cognito `superadmin` **or** elevated `X-Admin-Role` |

**Decision (recommended):** Phase 1 sync Cognito → app RBAC for product “see everything.” Phase 2 optionally retire `X-Admin-Token` for staff who already have Cognito groups; keep token as emergency break-glass in SSM.

---

## Cognito console setup (do first — no code)

1. Open Cognito User Pool → **Groups**.
2. Create groups (exact names):
   - `admin`
   - `superadmin`
3. Add your Cognito user(s) to `superadmin` (console → Users → Groups).
4. Confirm app clients issue tokens that include groups:
   - Access token claim: `cognito:groups` (array of strings)
   - Frontend / mobile must send the token that contains groups (usually **access token**; if only ID token is sent today, verify `cognito:groups` is present or switch to access token).
5. Optional later: Pre Token Generation Lambda to copy groups into a custom claim — only if Hosted UI / federated IdP strips groups (unlikely for native Cognito groups).

**Out of scope for Cognito groups:** per-project membership. That stays in `project_members`.

---

## Application design

### Source of truth

```
Cognito groups (JWT cognito:groups)
        │
        ▼
api/auth.get_current_user  →  map_groups_to_role(groups)
        │
        ▼
RDS users.role  (mirror for SQL filters + /auth/me)
```

Rules:

- On every authenticated request (or at least on `/auth/me` + `get_current_user`), recompute role from JWT groups and **upsert** `users.role`.
- Cognito demotion wins: leave `superadmin` group → next login becomes `admin` or `member`.
- Never allow elevating role via SQL alone as the long-term path (SQL is break-glass only).
- New users with no groups → `member` (current default).

### Mapping helper

```python
def map_cognito_groups_to_role(groups: list[str] | None) -> str:
    g = {x.lower() for x in (groups or [])}
    if "superadmin" in g:
        return "superadmin"
    if "admin" in g:
        return "admin"
    return "member"
```

Read groups from verified JWT payload: `payload.get("cognito:groups") or []`.

### API helpers

| Helper | Meaning |
|--------|---------|
| `is_staff(user)` | `role in ("admin", "superadmin")` |
| `is_superadmin(user)` | `role == "superadmin"` |
| `require_staff(...)` | 403 unless staff |
| `require_superadmin(...)` | 403 unless superadmin |

### Project access change

Today: `_require_role(project_id, user_id, allowed)` membership only.

Target:

```text
if is_staff(current_user):
    allow  # or allow read-only for admin, write for superadmin — decide per route
else:
    existing project_members check
```

**Recommended product policy:**

| Route class | `admin` | `superadmin` |
|-------------|---------|--------------|
| List all projects / open any project (read) | yes | yes |
| Mutate any project (patch, members, delete) | no | yes |
| List all users | yes (read) | yes |
| Deactivate user | no | yes |
| Upload / pull corpus UI | yes | yes |

Adjust in implementation if founder wants `admin` to mutate everything too.

### Frontend

- `/auth/me` already returns `role` — use it.
- Gate `/upload` Pull tab, document governance actions, future CMS nav on `role`.
- Never hide-only; API must enforce.

---

## Schema migration — `023_global_roles.sql` (additive)

Expand `users.role` check constraint:

```sql
-- drop old chk_user_role; add new one allowing:
-- 'member' | 'admin' | 'superadmin'
```

No change to `project_role` enum.

Optional audit column (nice-to-have, not required for MVP):

```sql
ALTER TABLE users ADD COLUMN role_synced_at timestamptz;
```

---

## Code touch list

| Area | Change |
|------|--------|
| `api/auth.py` | Read `cognito:groups`; map role; persist via new `db.client.sync_user_role` |
| `db/client.py` | `sync_user_role(user_id, role)`; keep `get_or_create_cognito_user` default `member` then sync |
| `api/routes/projects.py` | Staff bypass on list/get; superadmin on mutate-all |
| `api/routes/documents.py` / admin | Prefer JWT staff for governance where practical |
| `api/routes/pull.py` | Phase 2: allow Cognito staff **or** token |
| Frontend AuthContext / nav | Show admin surfaces when `role` is staff |
| Tests | Group→role mapping unit tests; staff bypass project list; demotion sync |

Import boundary unchanged: auth stays in `api/`; no Cognito calls from `ingestion/`.

---

## Phased rollout

### Phase 0 — Cognito only (you, today)

- [ ] Create `admin` and `superadmin` groups in Cognito  
- [ ] Add yourself to `superadmin`  
- [ ] Decode your access token (jwt.io or small script) — confirm `cognito:groups` includes `superadmin`  
- [ ] If groups missing: fix which token the app sends (access vs id)

### Phase 1 — Sync + see everything (MVP)

- [ ] Migration `023_global_roles.sql`  
- [ ] `map_cognito_groups_to_role` + sync in `get_current_user`  
- [ ] Staff bypass for **list projects** and **get project** (read)  
- [ ] Superadmin bypass for project **mutations** (optional same PR)  
- [ ] `/auth/me` returns synced role  
- [ ] Tests green  
- [ ] Local + prod migration; smoke: login → `role=superadmin` → see other users’ projects

### Phase 2 — Wire product admin surfaces

- [ ] Document governance / upload / pull: accept Cognito `admin`+ in addition to `X-Admin-Token`  
- [ ] Frontend: show admin nav for staff roles  
- [ ] Keep SSM `API_ADMIN_TOKEN` as break-glass

### Phase 3 — Harden (optional)

- [ ] Audit log for staff project access / user deactivate  
- [ ] Restrict `admin` mutate policy if too wide  
- [ ] Cognito group → IAM-style permission strings only if multi-tenant customers demand it  
- [ ] Document offboarding: remove from Cognito group (role demotes on next token)

---

## What stays out of Cognito groups

| Concern | Where it lives |
|---------|----------------|
| Project membership | `project_members` |
| Project-specific editor/viewer | `project_role` enum |
| Corpus checksum / document identity | documents table |
| Emergency purge without Cognito login | `API_ADMIN_TOKEN` |

Do **not** model one Cognito group per project. That does not scale and fights Cognito’s model.

---

## Security notes

- Enforce on API every time — UI gates are UX only.  
- Token refresh: group changes apply when Cognito issues a new token (re-login or refresh). Document that for operators.  
- Federated Apple/Google users: Cognito groups still work — assign the Cognito user (linked identity) to the group in the console.  
- Privaterelay emails do not block groups.  
- Never put group names in client env vars as “secret.” Groups are authorization claims, not credentials.

---

## Verification checklist

- [ ] User in no groups → `/auth/me` → `role=member`; project list = memberships only  
- [ ] User in `admin` → `role=admin`; can list all projects (read)  
- [ ] User in `superadmin` → `role=superadmin`; can open any project  
- [ ] Remove from group, refresh token → role demotes in RDS  
- [ ] Non-staff cannot hit staff-only routes (403)  
- [ ] `X-Admin-Token` still works for pull/purge during Phase 1–2  
- [ ] `py -m pytest` covering mapping + one project bypass test  
- [ ] Frontend: staff sees admin entry points; member does not  

---

## Decisions log (this plan)

| Decision | Choice |
|----------|--------|
| Global role source of truth | Cognito groups (`cognito:groups`) |
| Group names | `admin`, `superadmin` (exact) |
| Default | no groups → `member` |
| Project RBAC | Keep in RDS; staff bypass by policy |
| Ops token | Keep as break-glass; Phase 2 dual-auth for corpus routes |
| RDS `users.role` | Mirror cache for queries + `/auth/me`, synced on auth |

---

## Prompt for implementation session

> Read STATE.md, AGENTS.md, and docs/cognito_groups_rbac.md.  
> Implement Phase 1: migration 023, map Cognito groups → role in `api/auth.py`, sync to RDS, staff bypass on project list/get.  
> Do not remove `X-Admin-Token` yet.  
> Confirm access token includes `cognito:groups` before coding if unsure.
