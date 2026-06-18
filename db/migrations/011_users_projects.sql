-- db/migrations/011_users_projects.sql
-- Adds: users, projects, project_members, project_documents tables

-- ─── Enum ─────────────────────────────────────────────────────
CREATE TYPE project_role AS ENUM ('owner', 'editor', 'viewer');

-- ─── Users ─────────────────────────────────────────────────────
CREATE TABLE users (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username             text UNIQUE NOT NULL,   -- stored lowercase
    email                text UNIQUE NOT NULL,   -- required for login/recovery
    phone_number         text UNIQUE,            -- optional; E.164
    password_hash        text NOT NULL,          -- Argon2id
    role                 text NOT NULL DEFAULT 'member'
                             CONSTRAINT chk_user_role CHECK (role in ('admin', 'member')),
    is_active            boolean NOT NULL DEFAULT true,
    refresh_token_hash   text,                   -- SHA-256 of refresh token
    token_family         uuid DEFAULT gen_random_uuid(),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_username ON users (username);
CREATE INDEX idx_users_email    ON users (email);
CREATE INDEX idx_users_phone    ON users (phone_number) WHERE phone_number IS NOT NULL;
CREATE INDEX idx_users_active   ON users (is_active) WHERE is_active = true;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── Projects ──────────────────────────────────────────────────
CREATE TABLE projects (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL,
    description     text,
    owner_user_id   uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    municipality    text,
    is_active       boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_projects_owner        ON projects (owner_user_id);
CREATE INDEX idx_projects_municipality ON projects (municipality);
CREATE INDEX idx_projects_active       ON projects (is_active) WHERE is_active = true;

CREATE TRIGGER trg_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── Project Members ───────────────────────────────────────────
CREATE TABLE project_members (
    project_id  uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        project_role NOT NULL DEFAULT 'viewer',
    invited_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, user_id)
);

CREATE INDEX idx_project_members_user ON project_members (user_id);

-- ─── Project Documents (shared documents) ──────────────────────
CREATE TABLE project_documents (
    project_id   uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id  uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    added_by     uuid REFERENCES users(id) ON DELETE SET NULL,
    added_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, document_id)
);

CREATE INDEX idx_project_documents_document ON project_documents (document_id);

-- ─── Scoping project_id on documents table ──────────────────────
ALTER TABLE documents
    ADD COLUMN project_id uuid REFERENCES projects(id) ON DELETE SET NULL;

CREATE INDEX idx_documents_project
    ON documents (project_id) WHERE project_id IS NOT NULL;

-- ─── RLS ───────────────────────────────────────────────────────
ALTER TABLE users             ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects          ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_members   ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON users             FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON projects          FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON project_members   FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON project_documents FOR ALL USING (true) WITH CHECK (true);
