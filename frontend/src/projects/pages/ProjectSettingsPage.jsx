import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { updateProject } from "../../api.js";
import { useProject } from "../ProjectContext.jsx";
import { Settings, Save, RotateCcw, AlertTriangle, CheckCircle } from "lucide-react";

/**
 * Edit all project fields, including the role/persona that drives tailored
 * answers and the jurisdiction used for retrieval.
 */
const PERSONA_OPTIONS = [
  { value: "", label: "Not set" },
  { value: "diy", label: "DIY (doing it myself)" },
  { value: "hiring_contractor", label: "Hiring a contractor" },
  { value: "contractor", label: "Contractor myself" },
  { value: "research", label: "Just researching" },
];

const EXPERIENCE_OPTIONS = [
  { value: "", label: "Not set" },
  { value: "first_timer", label: "First-timer" },
  { value: "experienced", label: "Experienced" },
];

const EDITABLE_FIELDS = [
  "name", "description", "municipality", "address",
  "persona", "experience", "budget", "project_notes",
];

function toForm(project) {
  return {
    name: project?.name || "",
    description: project?.description || "",
    municipality: project?.municipality || "",
    address: project?.address || "",
    persona: project?.persona || "",
    experience: project?.experience || "",
    budget: project?.budget ?? "",
    project_notes: project?.project_notes || "",
  };
}

export default function ProjectSettingsPage() {
  const { project, setProject, canEdit, projectId } = useProject();
  const [form, setForm] = useState(() => toForm(project));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    setForm(toForm(project));
  }, [project]);

  const setField = (key) => (e) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const buildPayload = () => {
    const original = toForm(project);
    const payload = {};
    for (const field of EDITABLE_FIELDS) {
      if (form[field] === original[field]) continue;
      payload[field] = form[field] === "" ? null : form[field];
    }
    return payload;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    const payload = buildPayload();
    if (Object.keys(payload).length === 0) {
      setSuccess("No changes to save.");
      return;
    }
    setSaving(true);
    try {
      const res = await updateProject(projectId, payload);
      setProject(res.data);
      setSuccess("Project settings saved successfully.");
    } catch (err) {
      setError(err.message || "Failed to save project settings.");
    } finally {
      setSaving(false);
    }
  };

  const disabled = !canEdit || saving;

  return (
    <div className="max-w-3xl mx-auto p-4 sm:p-6">
      {/* ── Breadcrumb Navigation ── */}
      <nav className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3 flex items-center gap-1.5">
        <Link to="/projects" className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
          Projects
        </Link>
        <span>/</span>
        <Link to={`/projects/${projectId}`} className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
          {project?.name || "Dashboard"}
        </Link>
        <span>/</span>
        <span className="text-slate-900 dark:text-slate-100 font-bold">Edit</span>
      </nav>

      {/* ── Header ── */}
      <div className="mb-6 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/80 text-blue-600 dark:text-blue-400 flex items-center justify-center flex-shrink-0 border border-blue-200/60 dark:border-blue-800/60">
          <Settings className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">
            Edit Project
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-300 mt-0.5">
            Configure project parameters, jurisdiction codes, contractor roles, and target budget.
          </p>
        </div>
      </div>

      {/* ── Card Container ── */}
      <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 sm:p-8 shadow-sm">
        {!canEdit && (
          <div className="p-4 mb-6 bg-amber-50 dark:bg-amber-950/50 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 rounded-xl text-xs font-semibold flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0" />
            <span>You have view-only access to this project — settings cannot be modified.</span>
          </div>
        )}

        {error && (
          <div className="p-4 mb-6 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded-xl text-xs font-semibold flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="p-4 mb-6 bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-200 rounded-xl text-xs font-semibold flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
            <span>{success}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
              Project Name
            </label>
            <input
              type="text"
              value={form.name}
              onChange={setField("name")}
              disabled={disabled}
              className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors disabled:opacity-50"
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
              Description
            </label>
            <textarea
              value={form.description}
              onChange={setField("description")}
              disabled={disabled}
              rows={2}
              className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors disabled:opacity-50"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
                Your Role / Persona
              </label>
              <select
                value={form.persona}
                onChange={setField("persona")}
                disabled={disabled}
                className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors disabled:opacity-50"
              >
                {PERSONA_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
                Experience Level
              </label>
              <select
                value={form.experience}
                onChange={setField("experience")}
                disabled={disabled}
                className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors disabled:opacity-50"
              >
                {EXPERIENCE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
                Municipality (Jurisdiction)
              </label>
              <input
                type="text"
                value={form.municipality}
                onChange={setField("municipality")}
                disabled={disabled}
                placeholder="e.g. dallas, plano, frisco"
                className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors disabled:opacity-50"
              />
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
                Target Budget ($)
              </label>
              <input
                type="text"
                value={form.budget}
                onChange={setField("budget")}
                disabled={disabled}
                placeholder="e.g. $18,500"
                className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors disabled:opacity-50"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
              Property Address
            </label>
            <input
              type="text"
              value={form.address}
              onChange={setField("address")}
              disabled={disabled}
              placeholder="Used to auto-detect jurisdiction when municipality is blank"
              className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors disabled:opacity-50"
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
              Project Notes
            </label>
            <textarea
              value={form.project_notes}
              onChange={setField("project_notes")}
              disabled={disabled}
              rows={3}
              placeholder="Bounded notes considered by the AI assistant."
              className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors disabled:opacity-50"
            />
          </div>

          <div className="flex items-center gap-3 pt-4 border-t border-slate-100 dark:border-slate-700/80">
            <button
              type="submit"
              disabled={disabled}
              className="tt-btn-primary text-xs flex items-center gap-1.5 px-5 py-2.5 rounded-xl disabled:opacity-50"
            >
              <Save className="w-4 h-4" />
              {saving ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={() => setForm(toForm(project))}
              disabled={disabled}
              className="tt-btn-secondary text-xs flex items-center gap-1.5 px-4 py-2.5 rounded-xl disabled:opacity-50"
            >
              <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
              Reset
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
