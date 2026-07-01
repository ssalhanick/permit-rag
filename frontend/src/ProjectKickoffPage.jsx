/**
 * ProjectKickoffPage.jsx
 * Shown immediately after sign-in when no prior destination was saved.
 * Three paths:
 *   1. Guided wizard — 5-step conversational setup (default)
 *   2. Basic form   — name + address only (opt-out)
 *   3. Existing     — pick a previously created project
 */

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import AddressAutocomplete from "./components/AddressAutocomplete.jsx";
import { createProject, fetchProjects } from "./api.js";
import {
  SPACE_OPTIONS,
  WORK_TYPE_OPTIONS,
  isCosmeticOnly,
  recommendPermits,
} from "./projectPermitRules.js";

// ── Constants ─────────────────────────────────────────────────

const WIZARD_STEPS = [
  { id: 1, question: "Where is the project located?" },
  { id: 2, question: "What would you like to call this project?" },
  { id: 3, question: "Which spaces will be involved?" },
  { id: 4, question: "What type of work are you planning to do?" },
  { id: 5, question: "Here's what we found — does this look right?" },
];

const BLANK_WIZARD = {
  address: "",
  municipality: null,
  name: "",
  spaces: [],
  otherSpaces: "",
  workTypes: [],
  otherWorkTypes: "",
};

// ── Sub-components ────────────────────────────────────────────

/**
 * A "chat bubble" styled question from the app.
 */
function ChatBubble({ text }) {
  return (
    <div className="kickoff-chat-bubble" aria-live="polite">
      <span className="kickoff-chat-avatar" aria-hidden="true">🏗</span>
      <p>{text}</p>
    </div>
  );
}

/**
 * Step progress dots at the top of the wizard.
 */
function WizardProgress({ current, total }) {
  return (
    <div className="kickoff-wizard-progress" aria-label={`Step ${current} of ${total}`}>
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className={`kickoff-progress-dot${i + 1 === current ? " active" : i + 1 < current ? " done" : ""}`}
          aria-hidden="true"
        />
      ))}
      <span className="kickoff-step-label">{current} / {total}</span>
    </div>
  );
}

/**
 * A grid of checkboxes with an optional free-text "Other" field.
 */
function CheckboxGrid({ options, selected, onChange, otherValue, onOtherChange, otherLabel = "Other" }) {
  const toggle = (label) => {
    onChange(
      selected.includes(label)
        ? selected.filter((x) => x !== label)
        : [...selected, label],
    );
  };

  return (
    <div className="kickoff-checkbox-grid">
      {options.map((opt) => (
        <label key={opt} className="kickoff-checkbox-item">
          <input
            type="checkbox"
            checked={selected.includes(opt)}
            onChange={() => toggle(opt)}
          />
          {opt}
        </label>
      ))}
      {onOtherChange && (
        <div className="kickoff-other-field">
          <label htmlFor="other-input" className="kickoff-other-label">
            {otherLabel}
          </label>
          <input
            id="other-input"
            type="text"
            className="kickoff-other-input"
            placeholder="Describe anything else…"
            value={otherValue}
            onChange={(e) => onOtherChange(e.target.value)}
            maxLength={200}
          />
        </div>
      )}
    </div>
  );
}

/**
 * Permit recommendation tags displayed in Step 5.
 */
function PermitTags({ permits }) {
  if (permits.length === 0) return null;
  return (
    <div className="kickoff-permit-tags" role="list" aria-label="Recommended permits">
      {permits.map((p) => (
        <span key={p} className="kickoff-permit-tag" role="listitem">
          {p}
        </span>
      ))}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────

export default function ProjectKickoffPage() {
  const navigate = useNavigate();

  // "landing" | "wizard" | "basic" | "existing"
  const [mode, setMode] = useState("landing");
  const [wizardStep, setWizardStep] = useState(1);
  const [wizard, setWizard] = useState(BLANK_WIZARD);

  // Basic form state
  const [basicName, setBasicName] = useState("");
  const [basicAddress, setBasicAddress] = useState("");
  const [basicMunicipality, setBasicMunicipality] = useState(null);

  // Existing projects
  const [projects, setProjects] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(false);

  // Shared submit state
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // Load existing projects once on mount
  useEffect(() => {
    setProjectsLoading(true);
    fetchProjects()
      .then((res) => setProjects(res.data || []))
      .catch(() => {})
      .finally(() => setProjectsLoading(false));
  }, []);

  // Derived permit recommendations for wizard step 5
  const allWorkTypes = useMemo(() => {
    const base = [...wizard.workTypes];
    if (wizard.otherWorkTypes.trim()) base.push(wizard.otherWorkTypes.trim());
    return base;
  }, [wizard.workTypes, wizard.otherWorkTypes]);

  const recommendedPermits = useMemo(
    () => recommendPermits(wizard.workTypes),
    [wizard.workTypes],
  );

  const cosmeticOnly = useMemo(
    () => isCosmeticOnly(wizard.workTypes) && wizard.workTypes.length > 0,
    [wizard.workTypes],
  );

  // ── Wizard navigation ──────────────────────────────────────

  const wizardBack = () => {
    if (wizardStep === 1) {
      setMode("landing");
      setWizardStep(1);
    } else {
      setWizardStep((s) => s - 1);
    }
    setError("");
  };

  const wizardNext = () => {
    setError("");
    if (wizardStep === 1 && !wizard.address.trim()) {
      setError("Please enter a project address.");
      return;
    }
    if (wizardStep === 2 && !wizard.name.trim()) {
      setError("Please enter a project name.");
      return;
    }
    if (wizardStep < WIZARD_STEPS.length) {
      setWizardStep((s) => s + 1);
    }
  };

  // ── Project creation ───────────────────────────────────────

  const submitWizard = async () => {
    setError("");
    setSubmitting(true);
    const allSpaces = [...wizard.spaces];
    if (wizard.otherSpaces.trim()) allSpaces.push(wizard.otherSpaces.trim());

    try {
      const res = await createProject({
        name: wizard.name.trim(),
        address: wizard.address.trim(),
        municipality: wizard.municipality || undefined,
        spaces: allSpaces.length ? allSpaces : undefined,
        work_types: allWorkTypes.length ? allWorkTypes : undefined,
        recommended_permits: recommendedPermits.length ? recommendedPermits : undefined,
      });
      const id = res.data?.id;
      navigate(id ? `/?p=${id}` : "/", { replace: true });
    } catch (err) {
      setError(err?.message || "Failed to create project.");
      setSubmitting(false);
    }
  };

  const submitBasic = async (e) => {
    e.preventDefault();
    if (!basicName.trim()) {
      setError("Project name is required.");
      return;
    }
    if (!basicAddress.trim()) {
      setError("Project address is required.");
      return;
    }
    setError("");
    setSubmitting(true);
    try {
      const res = await createProject({
        name: basicName.trim(),
        address: basicAddress.trim(),
        municipality: basicMunicipality || undefined,
      });
      const id = res.data?.id;
      navigate(id ? `/?p=${id}` : "/", { replace: true });
    } catch (err) {
      setError(err?.message || "Failed to create project.");
      setSubmitting(false);
    }
  };

  // ── Skip ──────────────────────────────────────────────────

  const skip = () => navigate("/", { replace: true });

  // ── Renders ───────────────────────────────────────────────

  if (mode === "landing") {
    return (
      <main className="page kickoff-page">
        <section className="panel kickoff-panel">
          <h1 className="kickoff-heading">Welcome back.</h1>
          <p className="muted kickoff-subheading">
            What would you like to work on today?
          </p>

          <div className="kickoff-mode-cards">
            <button
              type="button"
              className="kickoff-mode-card kickoff-mode-card--primary"
              onClick={() => { setMode("wizard"); setWizardStep(1); }}
            >
              <span className="kickoff-mode-icon" aria-hidden="true">🆕</span>
              <strong>Start a new project</strong>
              <span>Walk through a quick setup to describe the work and get permit guidance.</span>
            </button>

            {projects.length > 0 && (
              <button
                type="button"
                className="kickoff-mode-card"
                onClick={() => setMode("existing")}
              >
                <span className="kickoff-mode-icon" aria-hidden="true">📂</span>
                <strong>Continue an existing project</strong>
                <span>Pick up where you left off on one of your {projects.length} project{projects.length !== 1 ? "s" : ""}.</span>
              </button>
            )}
          </div>

          <div className="kickoff-footer-actions">
            <button
              type="button"
              className="text-button"
              onClick={() => setMode("basic")}
            >
              Create project without guided setup
            </button>
            <span className="kickoff-divider" aria-hidden="true">·</span>
            <button type="button" className="text-button" onClick={skip}>
              Skip for now
            </button>
          </div>
        </section>
      </main>
    );
  }

  // ── Existing project picker ────────────────────────────────

  if (mode === "existing") {
    return (
      <main className="page kickoff-page">
        <section className="panel kickoff-panel">
          <button
            type="button"
            className="text-button kickoff-back-link"
            onClick={() => setMode("landing")}
          >
            ← Back
          </button>
          <h2>Your Projects</h2>
          <p className="muted">Select a project to pick up the query context.</p>

          {projectsLoading ? (
            <p className="muted">Loading…</p>
          ) : (
            <ul className="kickoff-project-list">
              {projects.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    className="kickoff-project-item"
                    onClick={() => navigate(`/?p=${p.id}`, { replace: true })}
                  >
                    <strong>{p.name}</strong>
                    {p.address && <span className="kickoff-project-address">{p.address}</span>}
                    {p.municipality && <span className="kickoff-project-muni">{p.municipality}</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="kickoff-footer-actions">
            <button type="button" className="text-button" onClick={skip}>
              Skip for now
            </button>
          </div>
        </section>
      </main>
    );
  }

  // ── Basic form ─────────────────────────────────────────────

  if (mode === "basic") {
    return (
      <main className="page kickoff-page">
        <section className="panel kickoff-panel">
          <button
            type="button"
            className="text-button kickoff-back-link"
            onClick={() => { setMode("landing"); setError(""); }}
          >
            ← Back
          </button>
          <h2>New Project</h2>

          {error && <div className="error-box">{error}</div>}

          <form onSubmit={submitBasic} className="kickoff-basic-form">
            <div className="kickoff-form-group">
              <label htmlFor="basic-name">Project name <span aria-hidden="true">*</span></label>
              <input
                id="basic-name"
                type="text"
                value={basicName}
                onChange={(e) => setBasicName(e.target.value)}
                placeholder="e.g. Main St Kitchen Remodel"
                maxLength={120}
                required
              />
            </div>

            <div className="kickoff-form-group">
              <label htmlFor="basic-address">Project address <span aria-hidden="true">*</span></label>
              <AddressAutocomplete
                id="basic-address"
                value={basicAddress}
                onChange={setBasicAddress}
                onSelect={({ address, municipality }) => {
                  setBasicAddress(address);
                  setBasicMunicipality(municipality);
                }}
                placeholder="1234 Main St, Dallas, TX 75201"
              />
            </div>

            <div className="kickoff-form-actions">
              <button type="submit" disabled={submitting}>
                {submitting ? "Creating…" : "Create Project"}
              </button>
              <button
                type="button"
                className="text-button"
                onClick={skip}
                disabled={submitting}
              >
                Skip for now
              </button>
            </div>
          </form>
        </section>
      </main>
    );
  }

  // ── Guided wizard ──────────────────────────────────────────

  const step = WIZARD_STEPS[wizardStep - 1];
  const isLastStep = wizardStep === WIZARD_STEPS.length;

  return (
    <main className="page kickoff-page">
      <section className="panel kickoff-panel">
        <WizardProgress current={wizardStep} total={WIZARD_STEPS.length} />

        <ChatBubble text={step.question} />

        {error && <div className="error-box">{error}</div>}

        {/* Step 1 — Address */}
        {wizardStep === 1 && (
          <div className="kickoff-step-body">
            <AddressAutocomplete
              id="wizard-address"
              value={wizard.address}
              onChange={(val) => setWizard((w) => ({ ...w, address: val }))}
              onSelect={({ address, municipality }) => {
                setWizard((w) => ({
                  ...w,
                  address,
                  municipality,
                  // Pre-fill name from address if not yet set
                  name: w.name || address.split(",")[0] || "",
                }));
              }}
              placeholder="1234 Main St, Dallas, TX 75201"
            />
          </div>
        )}

        {/* Step 2 — Project name */}
        {wizardStep === 2 && (
          <div className="kickoff-step-body">
            <div className="kickoff-form-group">
              <label htmlFor="wizard-name" className="kickoff-sr-label">Project name</label>
              <input
                id="wizard-name"
                type="text"
                value={wizard.name}
                onChange={(e) => setWizard((w) => ({ ...w, name: e.target.value }))}
                placeholder="e.g. Main St Kitchen Remodel"
                maxLength={120}
                autoFocus
              />
            </div>
          </div>
        )}

        {/* Step 3 — Spaces */}
        {wizardStep === 3 && (
          <div className="kickoff-step-body">
            <p className="kickoff-section-label">Indoor</p>
            <CheckboxGrid
              options={SPACE_OPTIONS.indoor}
              selected={wizard.spaces}
              onChange={(spaces) => setWizard((w) => ({ ...w, spaces }))}
            />
            <p className="kickoff-section-label kickoff-section-label--gap">Outdoor</p>
            <CheckboxGrid
              options={SPACE_OPTIONS.outdoor}
              selected={wizard.spaces}
              onChange={(spaces) => setWizard((w) => ({ ...w, spaces }))}
              otherValue={wizard.otherSpaces}
              onOtherChange={(otherSpaces) => setWizard((w) => ({ ...w, otherSpaces }))}
              otherLabel="Other space"
            />
          </div>
        )}

        {/* Step 4 — Work types */}
        {wizardStep === 4 && (
          <div className="kickoff-step-body">
            <CheckboxGrid
              options={WORK_TYPE_OPTIONS}
              selected={wizard.workTypes}
              onChange={(workTypes) => setWizard((w) => ({ ...w, workTypes }))}
              otherValue={wizard.otherWorkTypes}
              onOtherChange={(otherWorkTypes) => setWizard((w) => ({ ...w, otherWorkTypes }))}
              otherLabel="Other work"
            />
          </div>
        )}

        {/* Step 5 — Permit preview + confirm */}
        {wizardStep === 5 && (
          <div className="kickoff-step-body">
            <dl className="kickoff-summary">
              <div className="kickoff-summary-row">
                <dt>Address</dt>
                <dd>{wizard.address || <em>Not set</em>}</dd>
              </div>
              <div className="kickoff-summary-row">
                <dt>Name</dt>
                <dd>{wizard.name || <em>Not set</em>}</dd>
              </div>
              {wizard.spaces.length > 0 && (
                <div className="kickoff-summary-row">
                  <dt>Spaces</dt>
                  <dd>{wizard.spaces.join(", ")}{wizard.otherSpaces ? `, ${wizard.otherSpaces}` : ""}</dd>
                </div>
              )}
              {allWorkTypes.length > 0 && (
                <div className="kickoff-summary-row">
                  <dt>Work types</dt>
                  <dd>{allWorkTypes.join(", ")}</dd>
                </div>
              )}
            </dl>

            <div className="kickoff-permit-section">
              <p className="kickoff-section-label">Likely permits needed</p>
              {cosmeticOnly ? (
                <p className="kickoff-no-permits">
                  Good news — cosmetic work typically does not require a permit.
                  Always verify with your local building department.
                </p>
              ) : recommendedPermits.length > 0 ? (
                <>
                  <PermitTags permits={recommendedPermits} />
                  <p className="kickoff-permit-disclaimer muted">
                    This is a starting estimate. Your local AHJ (Authority Having Jurisdiction)
                    has final say on permit requirements.
                  </p>
                </>
              ) : (
                <p className="muted">
                  Select work types in the previous step to see permit recommendations.
                </p>
              )}
            </div>
          </div>
        )}

        {/* Wizard navigation */}
        <div className="kickoff-wizard-nav">
          <button
            type="button"
            className="secondary-button"
            onClick={wizardBack}
            disabled={submitting}
          >
            {wizardStep === 1 ? "Cancel" : "← Back"}
          </button>

          {isLastStep ? (
            <button
              type="button"
              onClick={submitWizard}
              disabled={submitting}
            >
              {submitting ? "Creating…" : "Create Project"}
            </button>
          ) : (
            <button
              type="button"
              onClick={wizardNext}
              disabled={submitting}
            >
              Next →
            </button>
          )}
        </div>

        {/* Skip is available throughout the wizard */}
        <div className="kickoff-footer-actions">
          <button type="button" className="text-button" onClick={skip}>
            Skip for now
          </button>
        </div>
      </section>
    </main>
  );
}
