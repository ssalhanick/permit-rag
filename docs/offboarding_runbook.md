# Offboarding Runbook

Purpose:
- Remove user/project-specific document content when a user leaves
- Keep governance-safe tombstone metadata for auditability

Scope:
- Uses `POST /admin/documents/{doc_id}/purge-project-upload`
- Deletes chunk rows (removes vectors from pgvector)
- Deletes local raw file under `documents/raw` when present
- Marks document row as `repealed`, `is_current=false`, `retrieval_weight=0.0`

## 1) Preconditions

- API is running
- `API_ADMIN_TOKEN` is configured
- Caller has valid `X-Admin-Role`
- For non-project tiers (`source_tier != 3`), role must be in `API_PURGE_ANY_TIER_ROLES`

## 2) Identify Candidate Documents

List document IDs for the offboarding user/project (manual query or admin export).

Optional file format for bulk script:
- one `doc_id` per line
- `#` comments allowed

Example `docs_to_purge.txt`:
```text
# user offboarding list
project-doc-1
project-doc-2
```

## 3) Purge Methods

### Method A — Single doc (API)

`curl -s -X POST "http://localhost:8000/admin/documents/<doc_id>/purge-project-upload" -H "X-Admin-Token: <API_ADMIN_TOKEN>" -H "X-Admin-Role: owner"`

### Method B — Bulk script (recommended)

`py -m scripts.purge_project_uploads --doc-id-file "docs_to_purge.txt" --admin-role owner`

## 4) Verification

For each purged `doc_id`:
- `GET /documents/{doc_id}` should show:
  - `document_status = repealed`
  - `is_current = false`
  - `retrieval_weight = 0.0`
  - `chunk_count = 0`

Verification command:

`curl -s "http://localhost:8000/documents/<doc_id>"`

## 5) Failure Handling

- `403` with elevated-tier message:
  - use a role in `API_PURGE_ANY_TIER_ROLES` for non-tier-3 docs
- `404`:
  - confirm `doc_id` spelling and environment
- `500`:
  - inspect API logs and retry single-doc purge first

## 6) Post-Offboarding Checklist

- Confirm all target `doc_id`s are purged
- Save command output in support/audit ticket
- Rotate `API_ADMIN_TOKEN` if offboarding involved admin-level access changes
