# S3 Migration Notes — Scoping Only

Local disk (`documents/raw/`, via `UPLOAD_DIR` in `api/routes/upload.py`) is the
storage backend for every upload path today — admin corpus upload, overlay
petitions, and the document-upload plan's Type 1/2/3 additions all write there.
This is a short scoping doc for the later move to S3, matching the plan's
original "storage: local disk for now... write a short docs file scoping the
later move to S3, don't build it now" decision. **No code changes here.**

## Why this matters sooner than "eventually"

The app runs on ECS Fargate (`terraform/main.tf`). There is no EFS mount or any
other persistent volume attached to the task — confirmed by grep, not assumed.
`documents/raw/` on a running Fargate container is ephemeral: a task restart,
redeploy, or scaling event loses whatever was written there since the last
image build. Today that risk is narrow (only staff use the admin upload path,
deliberately). The document-upload plan changes that: Type 1/2/3 let any
authenticated user upload, so the same ephemeral-storage gap now sits behind a
much wider set of write paths. This doesn't have to be fixed before those ship
— RDS still holds the authoritative `documents`/`chunks` rows and their
embeddings regardless of what happens to the raw file — but an uploaded file
that a user expects to re-download later can silently disappear on the next
deploy. Worth knowing going in, not a reason to block on this doc.

## Target layout: bucket-per-environment

One S3 bucket per environment, following the naming convention
`terraform/main.tf`'s existing `aws_s3_bucket.frontend` already establishes
(`bucket_prefix = "permit-rag-frontend-"`):

- `permit-rag-documents-production`
- `permit-rag-documents-local` — or skip S3 entirely for local dev and keep
  `documents/raw/` for that profile; there's no reason to require AWS
  credentials just to run the app on a laptop. `api/load_env.py`'s existing
  `local` vs `production` profile split is the natural switch point.

Key prefix inside the bucket should mirror today's `local_path` shape closely
enough that `documents.local_path` stays meaningful as a relative reference
rather than needing a full rewrite: `raw/{doc_id}{suffix}`, e.g.
`raw/ordinance-petition-a1b2c3.pdf`. Keeps the mapping from a `documents` row
to its file a one-line format string on either side of the migration.

No public bucket access — every current upload path already requires
authentication to reach `_process_upload`, and there's no reason for the raw
files to be reachable outside the app itself. Private bucket, IAM-scoped
access from the ECS task role only (same pattern the frontend bucket already
uses for CloudFront's Origin Access Control, just without the public-read
side of it).

## Presigned upload URLs replace direct `UploadFile` handling

Today every upload route (`api/routes/upload.py`, `overlays.py`,
`project_documents.py`, `document_petitions.py`) does the same thing: accept a
`fastapi.UploadFile`, stream it to a local path with `shutil.copyfileobj`, then
hand the local path to `_process_upload`. Post-migration, the shape changes to:

1. Client asks the API for a presigned PUT URL for a given `doc_id` + content
   type (a new, small endpoint — none of the four routes above need to change
   their own request bodies otherwise).
2. Client uploads the file directly to S3 with that URL — the file bytes never
   transit the FastAPI process.
3. Client notifies the API the upload completed (or the API polls/uses an S3
   event), and `_process_upload` runs against the S3 object instead of a local
   path.

This is a real API shape change, not just a storage swap — every one of the
four upload routes' request/response cycle changes from "one call, multipart
body, synchronous save" to "presign, direct-to-S3 PUT, confirm." `ingestion/chunker.py`'s
`extract_text`/`chunk_document` would need to read from S3 (or a downloaded
temp copy) instead of assuming a local `Path` exists — currently baked into
`_find_raw_file`'s `raw_dir.iterdir()`-style lookups.

## One-time backfill for existing `documents/raw/` content

Whenever this actually gets built: a script (`scripts/backfill_documents_to_s3.py`,
matching the existing `scripts/backfill_*.py` naming convention) that walks
`documents/raw/`, uploads each file to the target bucket at the key layout
above, and — this is the part worth getting right — verifies the upload
(size/checksum match) before treating the local file as the source of truth
being replaced, given `documents.checksum_sha256` already exists on most rows
(migration 022) and gives a ready-made verification value rather than needing
a new one.

## Explicitly not scoped by this doc

- Whether media/room-scan storage (a separate concern from `documents/raw/`,
  it does not go through `upload.py`) moves to S3 in the same pass or a
  separate one.
- CDN/CloudFront in front of the documents bucket — the frontend bucket has
  one for public static assets; documents are private and app-fetched only,
  so the same case doesn't obviously apply. Worth a real look when this is
  actually built, not decided here.
- Any change to `db/schema.sql`'s `local_path` column name/semantics. Whether
  it becomes an S3 key as-is or gets a new column is an implementation
  decision for whoever picks this up, not fixed here.
