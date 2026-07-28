# UX Audit — Production Walkthrough (2026-07-03)

**Environment:** `https://permits.scottsalhanick.com` (production)
**Method:** Scripted Playwright (headless Chromium), desktop 1440×900 + mobile 390×844
**Test account:** Cognito user `uxaudit_user1` / `ssalhanick+uxaudit@gmail.com` (created for this audit)
**Test data created:** project "UX Audit Test Project" (`22cd04d1-a1b8-4b8f-b44a-5287ed09c0bc`)
**Screenshots:** `C:\Users\ssalh\permit_rag_ux_audit\shots\`

> **Status update (2026-07-28 doc health check, code spot-check, not a live
> re-run):** all 4 P0 blockers are fixed — `register()` now generates a
> non-email username (`AuthContext.jsx`), `VITE_MAPBOX_TOKEN` is wired into
> `deploy.yml`, and `terraform/main.tf:616` has a comment citing P0-2 by name
> explaining the CloudFront routing fix. P1 #9 (dev jargon) and #13 (page
> title) confirmed fixed; #8 (admin-only upload) and #10 (empty skeleton)
> likely fixed; #5 (wizard data on project card) superseded by Phase 5's
> Permit Strategy panel. **Still open:** #7 (raw UUID for Add Member,
> confirmed in code), #6 (collaborator dedupe, unclear), #18 (`graph_health`
> ops note, never documented). Not re-checked: #11, #12, #15, #17 (need a
> live run, not just a code read).

---

## Executive summary

Auth (login, sign-out, Google SSO redirect, protected-route redirect) and the
kickoff wizard flow work well. But **two of the three core value paths are
broken on production**: no new user can register with email+password, and no
query returns an answer. A first-time visitor today cannot sign up, and a
signed-in user gets a raw JavaScript error instead of a compliance answer.
These are launch blockers, not polish items.

---

## P0 — Broken (users are hard-stuck)

### 1. Email/password registration fails for every user

Sign Up always returns Cognito error:
`Username cannot be of email format, since user pool is configured for email alias.`

The form passes the email as the Cognito `Username` in `userPool.signUp(email, ...)`
(`frontend/src/context/AuthContext.jsx`, `register()`), but the pool uses
email as an *alias*, so the username must not be an email.

- **Impact:** zero self-service signups. Google SSO is the only working entry.
- **Verified workaround:** direct Cognito `SignUp` with a non-email username +
  email attribute works; login with email alias afterwards works fine.
- **Fix:** generate a non-email username in `register()` (e.g. slug + random
  suffix), keep `email` as a user attribute. One-line-ish change.

### 2. Query answers never render — raw JS error shown instead

Submitting any question shows a red box: `Cannot read properties of null (reading 'num_chunks')`.

Root-cause chain (verified by direct API probes):

1. Production corpus is **empty** — `GET /documents` returns `[]`, `POST /query`
   returns `num_results: 0`. The RDS database never had documents ingested
   (13 active docs exist only in the local database).
2. `POST /query/answer` therefore returns an API error ("No relevant chunks
   found for this query").
3. CloudFront's SPA custom-error mapping rewrites that API error response into
   `index.html` with **status 200** (`x-cache: Error from cloudfront`).
4. The frontend parses the HTML as JSON, gets `null`, and crashes on
   `.num_chunks` — surfacing a developer stack-trace string to the user.

- **Impact:** the product's core function is dead on prod, and it fails ugly.
- **Fixes (all three needed):**
  - Ingest/sync the corpus into the production database (embedding budget check first).
  - Scope CloudFront custom-error responses to the frontend origin only, so API
    4xx/5xx pass through as JSON. (This also causes finding #4.)
  - Frontend: guard the response shape and show a friendly "no results / try
    again" message instead of the exception text.

### 3. Mapbox autocomplete disabled on prod + dev hint leaked to users

The prod build was made without `VITE_MAPBOX_TOKEN`, so every address field is
a plain input showing this end-user-visible message:

> "Address autocomplete: set VITE_MAPBOX_TOKEN in frontend/.env to enable."

- **Impact:** wizard step 1 has no suggestions, so `municipality` is never
  captured → projects get "Default Jurisdiction: None (Global search)" and the
  jurisdiction resolver loses its best signal. Internal config instructions
  display to customers.
- **Fix:** inject `VITE_MAPBOX_TOKEN` in `deploy.yml` (same pattern as the
  Cognito vars). Change the fallback copy to something user-neutral
  ("Enter the full street address including city").

### 4. Hard refresh / deep link on `/projects` shows raw JSON

Loading `https://permits.scottsalhanick.com/projects` directly (F5, bookmark,
shared link) renders `{"detail":"Authorization header missing."}` — the API
route shadows the SPA route at the edge.

- **Impact:** refresh anywhere in the projects panel dumps users onto a dead
  JSON page with no way back but the URL bar.
- **Fix:** namespace API routes (`/api/*`) or adjust CloudFront behaviors so
  browser navigations (GET, `Accept: text/html`) route to the SPA.

---

## P1 — Confusing (users likely get lost)

### 5. Wizard answers vanish after project creation

The wizard collects address, spaces, work types, and shows recommended permits
("Electrical", "Plumbing") — then none of it is visible anywhere afterward.
Project detail shows "No description provided", jurisdiction "None". The
permit recommendations are never shown again.

- **Fix:** render address / spaces / work types / recommended permits on the
  project card. Verify migration 014 is applied to prod RDS and the fields
  actually persist (creation succeeded, but nothing displays them).

### 6. Collaborators tab double-counts the owner

A fresh solo project shows **"Collaborators (2)"**: a row "Creator (Owner) — OWNER"
with no email, plus "ssalhanick_uxaudit (You) — OWNER" with a **Remove** button
next to yourself.

- **Fix:** dedupe creator row; never offer "Remove" on the sole owner.

### 7. Add-member and ownership transfer require raw UUIDs

"Add Member (User UUID)" and "Transfer Ownership (New Owner UUID)" expect users
to paste a UUID no normal user can find.

- **Fix:** invite by email/username lookup. Until then, at least show each
  user's own UUID prominently in Account (it is there today, unlabeled as
  "the thing to give collaborators").

### 8. Upload page is an admin tool shown to every member

Regular members see a form requiring **X-Admin-Token**, source-tier taxonomy
("1 — Corpus (scraped, authoritative)"), and slug conventions. Also broken
copy: *"Token is sent only as request header to \`\`."* (empty template literal).

- **Fix:** split into member upload (project docs, tier 3, no admin token) vs
  admin ingestion; or hide the page for non-admin roles. Fix the empty-string copy.

### 9. Dev/internal jargon on the main query page

- "Select workspace for **LangSmith tracking**"
- "Max Source Chunks (**Top K**)"
- "Session: web-1783098477898"
- Tabs "Diagnostics" and "Developer Logs" for all users
- Quick queries labeled only **Q1–Q7** (mystery buttons; gray blobs on mobile)

- **Fix:** plain-language labels ("Project", "Number of sources"), hide
  diagnostics behind an "Advanced" toggle or admin role, show a snippet of each
  quick query as button label or tooltip.

### 10. Empty answer skeleton renders before/after failure

"Generated Compliance Answer" and "Source Citations:" headers render with empty
bodies alongside the error, and the Source Chunks / Diagnostics / Developer
Logs tabs appear active. Looks half-loaded rather than failed.

- **Fix:** hide the results panel until a successful answer arrives; show one
  clear error state.

### 11. Query history inconsistency

The sidebar "Query History" logs the session's questions, but Profile → Query
History and the project's history tab both say "No queries logged yet" (queries
failed server-side, so nothing persisted). Users see their question in one
panel and "no queries" in another.

- **Fix:** either log failed queries with a failed badge, or label the sidebar
  "This session" to distinguish it from persistent history. (Mostly resolves
  itself once P0 #2 is fixed.)

---

## P2 — Polish

12. **"Welcome back."** greets brand-new users on `/kickoff` after their first
    ever sign-in. Vary copy for first login ("Welcome!").
13. Page title is **"permit_rag frontend"** — shows in tabs, bookmarks, search.
    Use "permit_rag — DFW Permit Compliance" and set a favicon.
14. Landing page for signed-out users is nearly empty (one card, one button) —
    no product explanation, cities covered, or sample questions. Weak first
    impression for contractors evaluating the tool.
15. Kickoff mode-card emoji (🆕/📂) renders as a broken glyph box in some
    environments (observed in headless Chromium). Use an SVG icon.
16. The "Sign In" nav item stays highlighted on the auth page while a separate
    blue "Sign In" button box sits beside it in the header — duplicate CTAs.
17. Wizard step-1 validation error ("Please enter a project address.") persists
    on screen even after the user starts typing a valid address. Clear on input.
18. `graph_health: false` on prod `/health` — Neo4j not present in prod. By
    design it's additive, but conflict detection silently downgrades to the
    lightweight path; worth a line in ops docs.

---

## What works well

- Login, sign-out, bad-credential and password-mismatch errors, forgot-password
  screen, protected-route redirect to `/auth`, and the Google SSO redirect all
  behave correctly.
- Kickoff wizard flow is genuinely good: clear one-question-per-step chat
  pattern, progress dots, step validation, back/cancel/skip always available,
  permit preview with an AHJ disclaimer.
- Mobile: burger nav works, checkbox grid collapses to two columns, touch
  targets are comfortable, no horizontal overflow on any page tested.
- Profile dashboard information architecture (Dashboard / History / Documents /
  Account / Projects) is clean and predictable.

---

## Suggested fix order

| # | Item | Effort |
|---|------|--------|
| 1 | Fix `register()` username generation (P0-1) | S |
| 2 | Ingest corpus into prod RDS (P0-2, budget check first) | M |
| 3 | CloudFront: stop rewriting API errors to index.html (P0-2/P0-4) | M |
| 4 | Bake `VITE_MAPBOX_TOKEN` into prod build (P0-3) | S |
| 5 | Frontend friendly error for empty/failed answers (P0-2) | S |
| 6 | Show wizard data on project detail + verify migration 014 on prod (P1-5) | M |
| 7 | Collaborator dedupe + invite-by-email (P1-6/7) | M |
| 8 | Copy pass: jargon, Q1–Q7 labels, title, admin-token page (P1-8/9, P2) | S–M |

## Cleanup

- Cognito test user `uxaudit_user1` (delete from user pool when done)
- RDS user row + project "UX Audit Test Project" (delete manually; audit made no deletions)
