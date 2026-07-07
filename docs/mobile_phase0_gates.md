# Mobile Phase 0 Gates (M0-1 … M0-9)

Separate from Sprint 12 P0 web checklist (`docs/sprint12_p0_prod_checklist.md`).

| # | Check | Pass |
|---|-------|------|
| M0-1 | Terraform CORS includes mobile origins | ☐ |
| M0-2 | Cognito mobile callback/logout URLs registered | ☐ |
| M0-3 | ECS redeploy after CORS change | ☐ |
| M0-4 | `npm run build:mobile` → `cap sync` → signed artifact | ☐ |
| M0-5 | Physical device: email/password login vs prod API | ☐ |
| M0-6 | Physical device: Google OAuth deep-link roundtrip | ☐ |
| M0-7 | Physical device: Sign in with Apple deep-link roundtrip | ☐ |
| M0-8 | Physical device: RAG query → JSON + citation | ☐ |
| M0-9 | Web prod smoke — no regression from mobile CORS changes | ☐ |

## Local before deploy

```powershell
cd frontend
npm run test
npm run build:mobile
npx cap sync
```
