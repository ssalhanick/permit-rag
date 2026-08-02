/**
 * ProjectKickoffPage.jsx
 * Shown immediately after sign-in when no prior destination was saved.
 * Three paths:
 *   1. Guided wizard — 5-step conversational setup (default)
 *   2. Basic form   — name + address only (opt-out)
 *   3. Existing     — pick a previously created project
 */

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import AddressAutocomplete from "./components/AddressAutocomplete.jsx";
import PermitTags from "./components/PermitTags.jsx";
import { createProject, fetchProjects, getProject, updateProject, postKickoffChat } from "./api.js";
import { projectToWizardState } from "./projectKickoffRoutes.js";
import { useVoiceInput } from "./hooks/useVoiceInput.js";
import MicPermissionHelp from "./components/MicPermissionHelp.jsx";
import {
  SPACE_OPTIONS,
  WORK_TYPE_OPTIONS,
  MATERIAL_OPTIONS,
  isCosmeticOnly,
  recommendPermits,
} from "./projectPermitRules.js";

// ── Constants ─────────────────────────────────────────────────

const WIZARD_STEPS = [
  { id: 1, question: "Where is the project located?" },
  { id: 2, question: "What would you like to call this project?" },
  { id: 3, question: "Which spaces will be involved?" },
  { id: 4, question: "What type of work are you planning to do?" },
  { id: 5, question: "Let's align on some details to customize your compliance guide." },
  { id: 6, question: "Here's what we found — does this look right?" },
];

const BLANK_WIZARD = {
  address: "",
  municipality: null,
  latitude: null,
  longitude: null,
  name: "",
  // True once the user has typed into the name field directly (as opposed to
  // it being auto-derived from address/spaces) — see the auto-populate
  // effects below. Once true, address changes stop overwriting a name the
  // user chose on purpose.
  nameManuallyEdited: false,
  spaces: [],
  otherSpaces: "",
  workTypes: [],
  otherWorkTypes: "",
  materials: [],
  otherMaterials: "",
  budget: "",
  persona: "",
  customSystemPrompt: "",
  comments: "",
  // null = not yet chosen. The room-scan step requires an explicit true/false
  // before Next will advance — see wizardNext's "roomScan" case.
  doRoomScan: null,
};

/**
 * Case-insensitive de-dupe that keeps the first-seen casing.
 *
 * @param {string[]} values
 * @returns {string[]}
 */
function dedupeLabels(values) {
  const seen = new Set();
  const result = [];
  for (const value of values) {
    const key = value.trim().toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    result.push(value.trim());
  }
  return result;
}

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
 * A boxed textarea with a mic button that appends dictated speech.
 * Shared by CheckboxGrid's "Other" field and the closing comments step.
 */
function VoiceTextarea({ id, label, value, onChange, placeholder, rows = 2, maxLength }) {
  const voice = useVoiceInput({
    onTranscript: (transcript) =>
      onChange(value.trim() ? `${value.trim()}, ${transcript}` : transcript),
  });

  return (
    <div className="kickoff-other-field">
      {label && (
        <label htmlFor={id} className="kickoff-other-label">
          {label}
        </label>
      )}
      <div className="kickoff-voice-input-box">
        <textarea
          id={id}
          className="kickoff-other-input kickoff-other-textarea"
          rows={rows}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          maxLength={maxLength}
        />
        <button
          type="button"
          className={`kickoff-mic-button${voice.listening ? " kickoff-mic-button--listening" : ""}`}
          onClick={voice.startListening}
          disabled={voice.listening}
          aria-label={voice.listening ? "Listening…" : "Dictate with voice"}
          title={voice.listening ? "Listening…" : "Dictate with voice"}
        >
          {voice.listening ? "…" : "🎙"}
        </button>
      </div>
      {voice.error && <p className="kickoff-voice-error">{voice.error}</p>}
      <MicPermissionHelp errorCode={voice.errorCode} />
    </div>
  );
}

/**
 * Close (×) button — exits the whole kickoff/intake flow from any step.
 */
function KickoffCloseButton({ onClick, disabled }) {
  return (
    <button
      type="button"
      className="kickoff-close-button"
      onClick={onClick}
      disabled={disabled}
      aria-label="Exit project setup"
      title="Exit project setup"
    >
      ×
    </button>
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

  const inputId = `${otherLabel.toLowerCase().replace(/\s+/g, "-")}-input`;

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
        <VoiceTextarea
          id={inputId}
          label={otherLabel}
          value={otherValue}
          onChange={onOtherChange}
          placeholder="Describe anything else…"
          maxLength={200}
        />
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────

export default function ProjectKickoffPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialMode = searchParams.get("mode") || "landing";
  const editProjectId = searchParams.get("projectId");
  const returnTo = searchParams.get("returnTo") || "/";

  // "landing" | "wizard" | "basic" | "existing"
  const [mode, setMode] = useState(
    ["wizard", "basic", "existing"].includes(initialMode) ? initialMode : "landing",
  );
  const [wizardStep, setWizardStep] = useState(1);
  const [wizard, setWizard] = useState(BLANK_WIZARD);
  const [editingProjectId, setEditingProjectId] = useState(editProjectId || null);
  const [hasLidar, setHasLidar] = useState(false);

  // Dynamic steps based on device LiDAR availability
  const steps = useMemo(() => {
    const list = [
      { key: "address", question: "Where is the project located?" },
      { key: "persona", question: "What is your role on this project?" },
      { key: "budget", question: "What is your estimated project budget?" },
      { key: "spaces", question: "Which spaces will be involved?" },
      { key: "workTypes", question: "What type of work are you planning to do?" },
      { key: "materials", question: "What specific materials or scopes are you planning?" },
    ];
    if (hasLidar) {
      list.push({ key: "roomScan", question: "Would you like to perform a 3D room scan?" });
    }
    list.push(
      { key: "name", question: "What would you like to call this project?" },
      { key: "comments", question: "Anything else we should know about this project?" },
      { key: "confirm", question: "Here's what we found — does this look right?" }
    );
    return list;
  }, [hasLidar]);

  // Check LiDAR capability on mount. This only decides whether the roomScan
  // step is offered at all — it must never pre-select an answer on the
  // user's behalf, or Yes ends up chosen before they've seen the step.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const { isRoomCaptureAvailable } = await import("./services/roomCapture.js");
        const available = await isRoomCaptureAvailable();
        if (active) {
          setHasLidar(available);
        }
      } catch {
        if (active) setHasLidar(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  // Kickoff Chat State
  const [chatHistory, setChatHistory] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  // Basic form state
  const [basicName, setBasicName] = useState("");
  const [basicAddress, setBasicAddress] = useState("");
  const [basicMunicipality, setBasicMunicipality] = useState(null);
  const [basicLatitude, setBasicLatitude] = useState(null);
  const [basicLongitude, setBasicLongitude] = useState(null);

  // Existing projects
  const [projects, setProjects] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(false);

  // Shared submit state
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [prefillLoading, setPrefillLoading] = useState(Boolean(editProjectId));

  const finishNavigation = (projectId) => {
    if (wizard.doRoomScan && projectId) {
      navigate(`/projects/${projectId}/scans`, { replace: true });
      return;
    }
    if (returnTo === "/projects" && projectId) {
      navigate(`/projects?projectId=${projectId}`, { replace: true });
      return;
    }
    if (returnTo && returnTo !== "/") {
      navigate(returnTo, { replace: true });
      return;
    }
    navigate(projectId ? `/?p=${projectId}` : "/", { replace: true });
  };

  // Load existing projects once on mount
  useEffect(() => {
    setProjectsLoading(true);
    fetchProjects()
      .then((res) => setProjects(res.data || []))
      .catch(() => {})
      .finally(() => setProjectsLoading(false));
  }, []);

  // Prefill wizard when editing an existing project from Projects page
  useEffect(() => {
    if (!editProjectId) {
      setPrefillLoading(false);
      return;
    }
    setPrefillLoading(true);
    getProject(editProjectId)
      .then((res) => {
        setWizard(projectToWizardState(res.data));
        setEditingProjectId(editProjectId);
        setMode("wizard");
        setWizardStep(1);
      })
      .catch((err) => {
        setError(err?.message || "Failed to load project for kickoff setup.");
        setMode("landing");
      })
      .finally(() => setPrefillLoading(false));
  }, [editProjectId]);

  // Initialize chatbot dialog at chat step
  useEffect(() => {
    const currentStep = steps[wizardStep - 1];
    if (currentStep?.key === "chat" && chatHistory.length === 0) {
      const city = wizard.municipality || "DFW";
      const roleMap = {
        "diy": "doing it yourself (DIY)",
        "hiring-contractor": "hiring a contractor",
        "contractor": "working as the contractor",
        "research": "doing general research",
      };
      const roleStr = roleMap[wizard.persona] || "user";
      const formattedBudget = wizard.budget ? `$${parseInt(wizard.budget, 10).toLocaleString()}` : "not set";
      setChatHistory([
        {
          role: "assistant",
          content: `Thanks! I see you are planning a project in ${city} with a budget of ${formattedBudget} and you are ${roleStr}. To customize your compliance guide: What specific materials/scopes are you planning?`,
        },
      ]);
    }
  }, [wizardStep, chatHistory.length, wizard.municipality, wizard.persona, wizard.budget, steps]);

  // Auto-populate project name from street + first selected space when reaching the name step.
  // Keyed off nameManuallyEdited (not "is name already non-empty") so that
  // going back and changing the address re-derives the suggestion instead of
  // leaving a stale one — the name only ever stops following address changes
  // once the user has actually typed into the field themselves.
  useEffect(() => {
    const currentStep = steps[wizardStep - 1];
    if (currentStep?.key !== "name") return;
    if (wizard.nameManuallyEdited) return;
    const streetWord = wizard._streetWord || "";
    const firstSpace = wizard.spaces?.[0] || wizard.otherSpaces?.trim() || "";
    const suggested = [streetWord, firstSpace].filter(Boolean).join(" ");
    if (suggested && suggested !== wizard.name) {
      setWizard((w) => ({ ...w, name: suggested }));
    }
  }, [wizardStep, steps]);

  // Backfill name when chat flow skips name step and lands on confirm — same
  // "only if untouched" rule as the effect above.
  useEffect(() => {
    const currentStep = steps[wizardStep - 1];
    if (currentStep?.key !== "confirm") return;
    if (wizard.nameManuallyEdited) return;
    const streetWord = wizard._streetWord || "";
    const spaces = [
      ...wizard.spaces,
      ...(wizard.otherSpaces?.trim() ? [wizard.otherSpaces.trim()] : []),
    ];
    const spaceSuffix = spaces.length > 1 ? "Home Renovation" : spaces[0] || "";
    const derived = [streetWord, spaceSuffix].filter(Boolean).join(" ")
      || (wizard.address.split(",")[0] || "").trim();
    if (derived && derived !== wizard.name) {
      setWizard((w) => ({ ...w, name: derived }));
    }
  }, [wizardStep, steps]);


  const handleChatSend = async (e) => {
    e?.preventDefault();
    if (!chatInput.trim() || chatLoading) return;

    const userMessage = { role: "user", content: chatInput.trim() };
    const updatedHistory = [...chatHistory, userMessage];
    setChatHistory(updatedHistory);
    setChatInput("");
    setChatLoading(true);
    setError("");

    try {
      const res = await postKickoffChat({
        history: updatedHistory,
        address: wizard.address,
        municipality: wizard.municipality,
        spaces: wizard.spaces,
        work_types: wizard.workTypes,
      });

      if (res.data.is_complete) {
        setWizard((w) => ({
          ...w,
          budget: res.data.budget || "",
          persona: res.data.persona || "",
          customSystemPrompt: res.data.custom_system_prompt || "",
        }));
        setChatHistory((h) => [
          ...h,
          {
            role: "assistant",
            content: "Perfect, I have synthesized custom compliance guidelines for your project profile! Let's check them on the next screen.",
          },
        ]);
        const confirmIdx = steps.findIndex((s) => s.key === "confirm");
        setTimeout(() => {
          if (confirmIdx !== -1) {
            setWizardStep(confirmIdx + 1);
          }
        }, 1500);
      } else {
        setChatHistory((h) => [
          ...h,
          {
            role: "assistant",
            content: res.data.next_question || "Could you tell me a bit more about that?",
          },
        ]);
      }
    } catch (err) {
      setError(err?.message || "Failed to progress kickoff conversation.");
    } finally {
      setChatLoading(false);
    }
  };

  // Derived permit recommendations for wizard step 5
  const allWorkTypes = useMemo(() => {
    const base = [...wizard.workTypes];
    if (wizard.otherWorkTypes.trim()) base.push(wizard.otherWorkTypes.trim());
    return dedupeLabels(base);
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
    const currentStep = steps[wizardStep - 1];
    if (currentStep?.key === "address" && !wizard.address.trim()) {
      setError("Please enter a project address.");
      return;
    }
    if (currentStep?.key === "name") {
      if (!wizard.name.trim()) {
        setError("Please enter a project name.");
        return;
      }
    }
    if (currentStep?.key === "persona" && !wizard.persona) {
      setError("Please select your role on this project.");
      return;
    }
    if (currentStep?.key === "budget" && !wizard.budget) {
      setError("Please enter your estimated project budget.");
      return;
    }
    if (currentStep?.key === "roomScan" && wizard.doRoomScan === null) {
      setError("Please choose whether you'd like to perform a 3D scan.");
      return;
    }
    if (wizardStep < steps.length) {
      setWizardStep((s) => s + 1);
    }
  };

  // Skip advances past only the current step — unlike skip() below, it never
  // leaves the intake flow. Bypasses this step's validation on purpose: that
  // is the point of skipping.
  const wizardSkip = () => {
    setError("");
    if (wizardStep < steps.length) {
      setWizardStep((s) => s + 1);
    }
  };

  // ── Project creation ───────────────────────────────────────

  const submitWizard = async () => {
    setError("");
    setSubmitting(true);
    const allSpaces = [...wizard.spaces];
    if (wizard.otherSpaces.trim()) allSpaces.push(wizard.otherSpaces.trim());

    // Derive a name if the chat flow skipped the name step and left it blank
    let resolvedName = wizard.name.trim();
    if (!resolvedName) {
      const streetWord = wizard._streetWord || "";
      const spaceSuffix = allSpaces.length > 1
        ? "Home Renovation"
        : allSpaces[0] || "";
      resolvedName = [streetWord, spaceSuffix].filter(Boolean).join(" ");
    }
    if (!resolvedName) {
      // Last resort: use the street portion of the address
      resolvedName = (wizard.address.split(",")[0] || "").trim();
    }
    if (!resolvedName) {
      setError("Please enter a project name.");
      setSubmitting(false);
      return;
    }

    const allMaterials = [...wizard.materials];
    if (wizard.otherMaterials.trim()) allMaterials.push(wizard.otherMaterials.trim());

    const payload = {
      name: resolvedName,
      address: wizard.address.trim(),
      municipality: wizard.municipality || undefined,
      latitude: wizard.latitude || undefined,
      longitude: wizard.longitude || undefined,
      spaces: allSpaces.length ? allSpaces : undefined,
      work_types: allWorkTypes.length ? allWorkTypes : undefined,
      materials: allMaterials.length ? allMaterials : undefined,
      recommended_permits: recommendedPermits.length ? recommendedPermits : undefined,
      budget: wizard.budget || undefined,
      persona: wizard.persona || undefined,
      custom_system_prompt: wizard.customSystemPrompt || undefined,
      project_notes: wizard.comments.trim() || undefined,
    };

    try {
      if (editingProjectId) {
        const res = await updateProject(editingProjectId, payload);
        const pid = res.data?.id || editingProjectId;
        if (pid) localStorage.setItem("activeProjectId", pid);
        finishNavigation(pid);
        return;
      }
      const res = await createProject(payload);
      const pid = res.data?.id;
      if (pid) localStorage.setItem("activeProjectId", pid);
      finishNavigation(pid);
    } catch (err) {
      setError(err?.message || (editingProjectId ? "Failed to update project." : "Failed to create project."));
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
        latitude: basicLatitude || undefined,
        longitude: basicLongitude || undefined,
      });
      const pid = res.data?.id;
      if (pid) localStorage.setItem("activeProjectId", pid);
      finishNavigation(pid);
    } catch (err) {
      setError(err?.message || "Failed to create project.");
      setSubmitting(false);
    }
  };

  // ── Skip ──────────────────────────────────────────────────

  const skip = () => {
    if (returnTo && returnTo !== "/") {
      navigate(returnTo, { replace: true });
      return;
    }
    navigate("/", { replace: true });
  };

  if (prefillLoading) {
    return (
      <main className="page kickoff-page">
        <section className="panel kickoff-panel">
          <p className="muted">Loading project setup…</p>
        </section>
      </main>
    );
  }

  // ── Renders ───────────────────────────────────────────────

  if (mode === "landing") {
    return (
      <main className="page kickoff-page">
        <section className="panel kickoff-panel">
          <KickoffCloseButton onClick={skip} />
          <h1 className="kickoff-heading">{returnTo === "/projects" ? "Project setup" : "Welcome back."}</h1>
          <p className="muted kickoff-subheading">
            {returnTo === "/projects"
              ? "Start a guided setup or pick up an existing project."
              : "What would you like to work on today?"}
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
          <KickoffCloseButton onClick={skip} />
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
                    onClick={() => navigate(`/projects/${p.id}/dashboard`, { replace: true })}
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
          <KickoffCloseButton onClick={skip} disabled={submitting} />
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
                onSelect={({ address, municipality, coordinates }) => {
                  setBasicAddress(address);
                  setBasicMunicipality(municipality);
                  if (coordinates) {
                    setBasicLongitude(coordinates[0]);
                    setBasicLatitude(coordinates[1]);
                  } else {
                    setBasicLongitude(null);
                    setBasicLatitude(null);
                  }
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

  const step = steps[wizardStep - 1];
  const isLastStep = wizardStep === steps.length;

  return (
    <main className="page kickoff-page">
      <section className="panel kickoff-panel">
        <KickoffCloseButton onClick={skip} disabled={submitting} />
        <WizardProgress current={wizardStep} total={steps.length} />

        <ChatBubble text={step?.question || ""} />

        {error && <div className="error-box">{error}</div>}

        {/* Step 1 — Address */}
        {step?.key === "address" && (
          <div className="kickoff-step-body">
            <AddressAutocomplete
              id="wizard-address"
              value={wizard.address}
              onChange={(val) => setWizard((w) => ({ ...w, address: val }))}
              onSelect={({ address, municipality, coordinates }) => {
                // Extract street name portion (e.g. "Holliday" from "123 Holliday Ln, ...")
                const street = address.split(",")[0] || "";
                const streetWord = street.trim().split(" ").slice(1).join(" ") || street.trim();
                setWizard((w) => ({
                  ...w,
                  address,
                  municipality,
                  latitude: coordinates ? coordinates[1] : null,
                  longitude: coordinates ? coordinates[0] : null,
                  _streetWord: streetWord,
                }));
              }}
              placeholder="1234 Main St, Dallas, TX 75201"
            />
          </div>
        )}

        {/* Name step — last question, auto-filled from street + first space */}
        {step?.key === "name" && (
          <div className="kickoff-step-body">
            <div className="kickoff-form-group">
              <label htmlFor="wizard-name" className="kickoff-sr-label">Project name</label>
              <input
                id="wizard-name"
                type="text"
                className="kickoff-text-input"
                value={wizard.name}
                onChange={(e) =>
                  setWizard((w) => ({ ...w, name: e.target.value, nameManuallyEdited: true }))
                }
                placeholder="e.g. Holliday Kitchen"
                maxLength={120}
                autoFocus
              />
            </div>
          </div>
        )}

        {/* Step: Persona / Role */}
        {step?.key === "persona" && (
          <div className="kickoff-step-body">
            <div className="kickoff-form-group">
              <label htmlFor="wizard-persona" className="kickoff-sr-label">Your Role</label>
              <select
                id="wizard-persona"
                className="kickoff-select"
                value={wizard.persona}
                onChange={(e) => setWizard((w) => ({ ...w, persona: e.target.value }))}
                required
                autoFocus
              >
                <option value="" disabled>Select your role...</option>
                <option value="diy">DIY (Doing it myself)</option>
                <option value="hiring_contractor">Hiring a contractor</option>
                <option value="contractor">Contractor myself</option>
                <option value="research">Just doing research</option>
              </select>
            </div>
          </div>
        )}

        {/* Step: Budget */}
        {step?.key === "budget" && (
          <div className="kickoff-step-body">
            <div className="kickoff-budget-wrapper">
              <span className="kickoff-budget-prefix">$</span>
              <input
                id="wizard-budget"
                type="number"
                inputMode="numeric"
                pattern="[0-9]*"
                value={wizard.budget}
                onChange={(e) => setWizard((w) => ({ ...w, budget: e.target.value }))}
                placeholder="0"
                className="kickoff-budget-input"
                autoFocus
              />
            </div>
          </div>
        )}

        {/* Step 3 — Spaces */}
        {step?.key === "spaces" && (
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
        {step?.key === "workTypes" && (
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

        {/* Optional Room Scan Step */}
        {step?.key === "roomScan" && (
          <div className="kickoff-step-body">
            <div className="kickoff-room-scan-options">
              <label className={`kickoff-radio-item ${wizard.doRoomScan === true ? "active" : ""}`}>
                <input
                  type="radio"
                  name="doRoomScan"
                  checked={wizard.doRoomScan === true}
                  onChange={() => setWizard((w) => ({ ...w, doRoomScan: true }))}
                  style={{ display: "none" }}
                />
                <div className="kickoff-radio-content">
                  <span className="kickoff-radio-icon">📸</span>
                  <div className="kickoff-radio-text">
                    <strong>Yes, I want to perform a 3D scan</strong>
                    <p>Use device LiDAR camera to scan walls, openings, and objects. Highly recommended for accurate rules.</p>
                  </div>
                </div>
              </label>

              <label className={`kickoff-radio-item ${wizard.doRoomScan === false ? "active" : ""}`}>
                <input
                  type="radio"
                  name="doRoomScan"
                  checked={wizard.doRoomScan === false}
                  onChange={() => setWizard((w) => ({ ...w, doRoomScan: false }))}
                  style={{ display: "none" }}
                />
                <div className="kickoff-radio-content">
                  <span className="kickoff-radio-icon">⏩</span>
                  <div className="kickoff-radio-text">
                    <strong>No, skip 3D scan for now</strong>
                    <p>You can still record measurements or scan from the project dashboard later.</p>
                  </div>
                </div>
              </label>
            </div>
          </div>
        )}

        {/* Specific Materials Step */}
        {step?.key === "materials" && (
          <div className="kickoff-step-body">
            <CheckboxGrid
              options={MATERIAL_OPTIONS}
              selected={wizard.materials}
              onChange={(materials) => setWizard((w) => ({ ...w, materials }))}
              otherValue={wizard.otherMaterials}
              onOtherChange={(otherMaterials) => setWizard((w) => ({ ...w, otherMaterials }))}
              otherLabel="Other material / scope"
            />
          </div>
        )}

        {/* General comments — optional, text or voice */}
        {step?.key === "comments" && (
          <div className="kickoff-step-body">
            <VoiceTextarea
              id="wizard-comments"
              value={wizard.comments}
              onChange={(comments) => setWizard((w) => ({ ...w, comments }))}
              placeholder="Anything else we should know — access constraints, timeline, HOA rules, existing damage…"
              rows={5}
              maxLength={1200}
            />
          </div>
        )}

        {/* Permit preview + confirm */}
        {step?.key === "confirm" && (
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
              {wizard.materials.length > 0 && (
                <div className="kickoff-summary-row">
                  <dt>Materials</dt>
                  <dd>{wizard.materials.join(", ")}{wizard.otherMaterials ? `, ${wizard.otherMaterials}` : ""}</dd>
                </div>
              )}
              {wizard.budget && (
                <div className="kickoff-summary-row">
                  <dt>Estimated Budget</dt>
                  <dd>{wizard.budget}</dd>
                </div>
              )}
              {hasLidar && (
                <div className="kickoff-summary-row">
                  <dt>LiDAR Scan Opt-in</dt>
                  <dd>
                    {wizard.doRoomScan === true
                      ? "Yes, requested"
                      : wizard.doRoomScan === false
                        ? "No, skipped"
                        : "Not chosen"}
                  </dd>
                </div>
              )}
              {wizard.comments.trim() && (
                <div className="kickoff-summary-row">
                  <dt>Comments</dt>
                  <dd>{wizard.comments.trim()}</dd>
                </div>
              )}
            </dl>

            {wizard.customSystemPrompt && (
              <div className="kickoff-custom-prompt-section">
                <p className="kickoff-section-label">Custom Compliance Guidelines</p>
                <div className="kickoff-custom-prompt-box">
                  <p>{wizard.customSystemPrompt}</p>
                </div>
              </div>
            )}

            <div className="kickoff-permit-section" style={{ marginTop: "1rem" }}>
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
              className="primary-button"
              onClick={submitWizard}
              disabled={submitting}
            >
              {submitting
                ? (editingProjectId ? "Saving…" : "Creating…")
                : (editingProjectId ? "Save Setup" : "Create Project")}
            </button>
          ) : step?.key === "chat" ? null : (
            <button
              type="button"
              className="primary-button"
              onClick={wizardNext}
              disabled={submitting}
            >
              Next →
            </button>
          )}
        </div>

        {/* Skip advances past this step only — the confirm/submit step has nothing to skip */}
        {!isLastStep && (
          <div className="kickoff-footer-actions">
            <button type="button" className="text-button" onClick={wizardSkip} disabled={submitting}>
              Skip for now
            </button>
          </div>
        )}
      </section>
    </main>
  );
}
