# Sprint 12 — User Profile Dashboard (Base Users)

**Branch:** `feat/sprint-12-user-profile-dashboard`  
**Status:** Planned

## Goal

Replace the single-page `/profile` tab UI with a **WordPress admin–style dashboard**: fixed left sidebar, nested subpages, and a main content area. Scope is **base users** (`role=member`) — not the separate CMS Admin Dashboard (`/admin/*`).

## Decisions locked in

| # | Decision |
|---|----------|
| 1 | **Layout pattern** — WP admin shell: dark sidebar + light content pane; sidebar collapses on mobile |
| 2 | **Routing** — nested React Router routes under `/profile/*`; `/profile` redirects to `/profile/dashboard` |
| 3 | **Phase 1 = frontend-only** — reuse existing APIs; no new backend routes until Phase 3 |
| 4 | **Migrate, don't rewrite** — extract Query History and My Documents from `ProfilePage.jsx` into subpage components |
| 5 | **Separate from CMS** — admin document governance stays on `/documents`; super-admin CMS plan is out of scope |
| 6 | **Auth source (Phase 1–2)** — user info from JWT via `AuthContext`; fix `user.id` vs `user.user_id` inconsistency during refactor |

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Site Nav (existing Nav.jsx — public links + logout)            │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│  ProfileLayout (/profile/*)                                      │
│  ┌──────────────┐  ┌──────────────────────────────────────────┐ │
│  │ Sidebar      │  │ Page header (title + optional actions)    │ │
│  │              │  ├──────────────────────────────────────────┤ │
│  │ Dashboard    │  │ <Outlet /> — active subpage               │ │
│  │ Query Hist   │  │                                           │ │
│  │ My Documents │  │                                           │ │
│  │ Account      │  │                                           │ │
│  │              │  │                                           │ │
│  │ [Back to app]│  │                                           │ │
│  └──────────────┘  └──────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Sidebar navigation (Phase 1)

| Label | Route | Source |
|-------|-------|--------|
| Dashboard | `/profile/dashboard` | New — summary cards + quick links |
| Query History | `/profile/history` | Migrate from `ProfilePage.jsx` tab |
| My Documents | `/profile/documents` | Migrate from `ProfilePage.jsx` tab |
| Account | `/profile/account` | New — read-only JWT fields + logout-all |
| Projects | `/projects` | External link (existing page) |
| New Query | `/` | External link |

Active route highlights sidebar item (`NavLink` + `aria-current="page"`).

## Phases

### Phase 1 — Shell + route migration (MVP)

**Deliverables**

- [x] `ProfileLayout.jsx` — sidebar + `<Outlet />`
- [x] `profileNavConfig.js` — nav items (single source of truth)
- [x] Nested routes in `main.jsx` under `/profile`
- [x] `ProfileHistoryPage.jsx` — extracted query history logic
- [x] `ProfileDocumentsPage.jsx` — extracted documents table logic
- [x] Redirect `/profile` → `/profile/dashboard`
- [x] CSS: `.profile-dashboard-layout`, `.profile-sidebar`, `.profile-main` (mobile stack + drawer toggle)
- [x] Fix `AuthContext` user shape: expose `user_id` alias or standardize on `id` everywhere

**Out of scope Phase 1**

- Password change, email edit, avatar upload
- Admin-only profile sections

### Phase 2 — Dashboard home

**Deliverables**

- [ ] `ProfileDashboardPage.jsx` — overview widgets:
  - Recent query count (from `fetchQueryHistory`)
  - Project count (from `fetchProjects`)
  - Uploaded doc count (filtered like current profile)
- [ ] Quick-action cards: Run query, Upload doc, View projects
- [ ] Optional: last 3 queries snippet with “View all” link

### Phase 3 — Account & security (backend additions)

**Deliverables**

- [ ] `GET /auth/me` — return `{ id, username, email, phone_number, role, created_at }` (no password hash)
- [ ] `ProfileAccountPage.jsx` — show email/phone from API
- [ ] Wire `POST /auth/logout-all` (API exists; add frontend helper if missing)
- [ ] Optional: `PATCH /auth/password` — change password with current-password verification

**Migration note:** add `tests/test_auth_me.py` or extend `tests/test_sprint9.py`.

## Scope table

| In scope | Out of scope |
|----------|--------------|
| WP-style sidebar layout for `/profile/*` | CMS Admin Dashboard (`/admin/*`) |
| Migrate history + documents subpages | User avatar upload |
| Dashboard overview cards | Admin user management UI |
| Account read-only + logout-all | Billing / token usage panels |
| Mobile-responsive sidebar | Dark mode toggle (defer) |
| shadcn/ui where it fits (Card, Button) | New RBAC roles |

## Existing APIs (Phase 1–2 — no backend changes)

| Endpoint | Used by |
|----------|---------|
| `GET /query/history` | History page, dashboard stats |
| `DELETE /query/history/{id}` | History page |
| `GET /documents` | Documents page, dashboard stats |
| `GET /projects` | Documents share dropdown, dashboard stats |
| `POST /projects/{id}/documents/{uuid}/share` | Documents page |
| `POST /admin/documents/{doc_id}/purge-project-upload` | Documents purge (admin token) |
| `POST /auth/logout-all` | Account page (Phase 2+) |

## Proposed file structure

```
frontend/src/
  profile/
    ProfileLayout.jsx
    profileNavConfig.js
    pages/
      ProfileDashboardPage.jsx
      ProfileHistoryPage.jsx
      ProfileDocumentsPage.jsx
      ProfileAccountPage.jsx
  ProfilePage.jsx          → delete or re-export ProfileLayout after migration
  main.jsx                 → nested /profile routes
  styles.css               → profile dashboard layout classes
```

## UI spec (WordPress admin feel)

- **Sidebar width:** ~240px desktop; full-width overlay drawer on `< 768px`
- **Sidebar colors:** `#1d2327` background, `#f0f0f1` text, `#2271b1` active accent (WP blue)
- **Content area:** white panel, max-width ~1200px, page title H1 at top
- **Touch targets:** keep 44px minimum (Sprint 10 WCAG)
- **Reuse:** `.doc-table-wrap` for document table horizontal scroll

## Known bug to fix during refactor

`AuthContext` sets `user.id` from JWT `sub`, but `ProfilePage.jsx` references `user.user_id`. Standardize on one field before migrating document filter logic.

## Verification checklist

### Phase 1

- [ ] `/profile` redirects to `/profile/dashboard`
- [ ] Sidebar highlights active subpage on direct URL load
- [ ] Query History: reload, expand, copy, delete still work
- [ ] My Documents: share-to-project and purge (with admin token) still work
- [ ] Mobile: sidebar toggles without breaking site nav
- [ ] `cd frontend && npm run test`

### Phase 2

- [ ] Dashboard shows accurate counts for logged-in user
- [ ] Quick links navigate correctly

### Phase 3

- [ ] `GET /auth/me` returns email without exposing password hash
- [ ] Logout-all clears refresh token and forces re-login on refresh
- [ ] `py -m pytest tests/test_sprint9.py -v` (or new auth tests)

## Governance rules

- No new inline Supabase/Anthropic calls — API helpers stay in `frontend/src/api.js`
- Profile purge continues to use stored admin token (`documentAdminUtils.js`)
- Admin role users use the same profile shell in Phase 1; admin-only CMS features remain on `/documents` and future `/admin/*`

## Relationship to other plans

| Plan | Relationship |
|------|--------------|
| [Sprint 9 — Users & Projects](sprint9_users_projects.md) | Auth, projects, query history — foundation |
| [Sprint 11 — Document Governance UI](sprint11_document_updates.md) | Admin doc edit on `/documents`; profile documents page is user uploads only |
| CMS Admin Dashboard (brain artifact) | Separate super-admin tool; do not merge into `/profile` |
