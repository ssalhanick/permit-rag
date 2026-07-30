-- db/migrations/044_contractor_profiles.sql
-- Contractor identity + licensing (contractor marketplace milestone 1).
-- ─────────────────────────────────────────────────────────
-- NOT the Phase 6 "ontology/bids" slot (034) -- that reservation is for the
-- Field Ontology's per-form mapping corpus (form_templates/field_mappings,
-- docs/agent_architecture.md "What the Field Ontology actually is", part 4)
-- plus whatever the Bid Evaluator's PDF-upload extraction needs, neither of
-- which this table has anything to do with. A contractor having a
-- SourceBinding.PROFILE-sourced ontology field (contractor.license_number)
-- does not mean building its backing table fulfills that reservation --
-- this was an earlier mistake in this branch, corrected once caught. See
-- 034_ontology_and_bids.sql for the actual Phase 6 deliverable and
-- STATE.md's "Migration numbering" note for the full ledger.
--
-- Deliberately NOT layered onto users.role (member/admin/superadmin) -- that
-- column is a staff/ops permission axis (docs/cognito_groups_rbac.md),
-- orthogonal to "is this user also a contractor." Gating is done at the
-- application layer by checking for a contractor_profiles row
-- (api/contractor_auth.py), not by adding a value to that column.
--
-- No verification_status/KYC column: the requirement is "license and
-- insurance are required before a contractor can bid," not a manual
-- approval workflow -- a deliberate scope line, not an oversight. Likewise
-- no document-upload column for insurance certs: structured fields (number,
-- expiration, carrier) only in this pass.

CREATE TABLE contractor_profiles (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 uuid NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    business_name           text NOT NULL,
    contact_name            text,
    phone                   text,
    trades                  text[] NOT NULL DEFAULT '{}',   -- work.type vocabulary, forms/ontology.py
    service_municipalities  text[] NOT NULL DEFAULT '{}',   -- same vocabulary as projects.municipality
    bio                     text,
    years_in_business       integer,
    is_active               boolean NOT NULL DEFAULT true,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_contractor_profiles_user   ON contractor_profiles (user_id);
CREATE INDEX idx_contractor_profiles_trades ON contractor_profiles USING gin (trades);

CREATE TRIGGER trg_contractor_profiles_updated_at
    BEFORE UPDATE ON contractor_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TABLE contractor_licenses (
    id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contractor_profile_id       uuid NOT NULL REFERENCES contractor_profiles(id) ON DELETE CASCADE,
    trade                       text NOT NULL,   -- validated at the service layer, not a DB CHECK
    license_number              text NOT NULL,   -- format-checked via forms.ontology.validate_value("contractor.license_number", ...)
    issuing_authority           text,
    expiration_date             date NOT NULL,
    insurance_provider          text,
    insurance_policy_number     text,
    insurance_coverage_amount   numeric(12,2),
    insurance_expiration_date   date,
    created_at                  timestamptz NOT NULL DEFAULT now(),
    updated_at                  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_contractor_licenses_contractor ON contractor_licenses (contractor_profile_id);
CREATE INDEX idx_contractor_licenses_expiration ON contractor_licenses (expiration_date);

CREATE TRIGGER trg_contractor_licenses_updated_at
    BEFORE UPDATE ON contractor_licenses
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

COMMENT ON TABLE contractor_profiles IS
    'A user acting as a contractor in the bidding marketplace. 1:1 with users -- '
    'any existing homeowner account can also become a contractor by creating one '
    'of these. Gates contractor-only routes via row existence, not users.role.';
COMMENT ON TABLE contractor_licenses IS
    'One row per trade license a contractor holds. A contractor needs at least '
    'one non-expired row here (api/contractor_auth.require_biddable_contractor) '
    'before they can submit a bid. Self-attested and format-checked only -- no '
    'integration with a real state licensing board (e.g. TDLR) in this pass.';
COMMENT ON COLUMN contractor_licenses.expiration_date IS
    'Drives the in-app color-coded expiration badge (green/amber/red) on the '
    'license-management page. No push/email reminders in this pass -- no '
    'notification infrastructure exists in this codebase yet.';
