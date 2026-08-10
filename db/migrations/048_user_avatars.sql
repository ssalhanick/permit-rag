-- db/migrations/048_user_avatars.sql
-- Profile photos for user accounts.
-- ─────────────────────────────────────────────────────────
-- Images live in Postgres as bytea rather than on disk because the backend
-- ECS task definition (terraform/main.tf, aws_ecs_task_definition.backend)
-- declares no volume and no EFS mount -- the existing UPLOAD_DIR
-- ("documents/raw", api/routes/upload.py) is ephemeral container disk that is
-- wiped on every deploy. An avatar written there would silently vanish. S3 was
-- the alternative; it was rejected for this feature because it adds a boto3
-- dependency, an IAM policy, and a terraform apply to the deploy path for
-- what is at most a few hundred 20 KB thumbnails.
--
-- Rows stay small because the browser resizes to 256x256 and re-encodes to
-- WebP before upload (frontend/src/avatarUtils.js, resizeImageToSquare), and
-- POST /auth/me/avatar independently caps the body at 512 KB. The client-side
-- canvas pass is also what strips EXIF (including GPS coordinates) and
-- normalizes HEIC/JPEG/PNG down to a single stored format -- the server never
-- parses HEIC, so no libheif lands in the image.
--
-- ── Why a separate table instead of columns on users ──
-- A bytea column on users would be pulled into memory by every existing
-- "SELECT * FROM users" -- including get_or_create_cognito_user and
-- get_user_by_id, which run on EVERY authenticated request via
-- api/auth.py's get_current_user. Narrowing those to explicit column lists
-- would work but silently breaks the next time someone adds a users column.
-- A 1:1 side table makes the cost opt-in: SELECT * FROM users can never touch
-- image bytes, and only the avatar endpoints join in. This is the same
-- row-existence pattern 043_contractor_profiles.sql applies for the same
-- reason -- keep the hot table narrow, gate on the side table.
--
-- updated_at is what the frontend uses as a cache-buster (?v=<epoch>) and what
-- GET /users/{id}/avatar turns into an ETag, so a re-upload is visible
-- immediately despite Cache-Control. It lives here, not on users, so that a
-- user with no photo simply has no row.

CREATE TABLE IF NOT EXISTS user_avatars (
    user_id    uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    data       bytea       NOT NULL,
    mime       text        NOT NULL
                   CONSTRAINT chk_user_avatar_mime
                   CHECK (mime IN ('image/webp', 'image/jpeg', 'image/png')),
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE user_avatars IS
    'Profile photos, one row per user, absent when the user has none. Kept off '
    'the users table so "SELECT * FROM users" (run on every authenticated '
    'request) never loads image bytes.';

COMMENT ON COLUMN user_avatars.data IS
    'Raw image bytes, already resized to 256x256 client-side. Capped at 512 KB '
    'by MAX_AVATAR_BYTES in api/routes/auth.py.';

COMMENT ON COLUMN user_avatars.mime IS
    'Stored format, always one the browser can render natively. HEIC is an '
    'accepted upload format but is transcoded to WebP client-side, so it is '
    'deliberately absent from the CHECK constraint.';

COMMENT ON COLUMN user_avatars.updated_at IS
    'Drives the ETag on GET /users/{id}/avatar and the ?v= cache-buster the '
    'frontend appends, so a replaced photo appears without a hard refresh.';
