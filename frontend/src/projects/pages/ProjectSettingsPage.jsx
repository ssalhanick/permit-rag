import React, { useEffect, useState } from "react";
import { updateProject } from "../../api.js";
import { useProject } from "../ProjectContext.jsx";

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
      // budget is a free-text string in the API (context, not a computed number)
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
      setSuccess("Project settings saved.");
    } catch (err) {
      setError(err.message || "Failed to save project settings.");
    } finally {
      setSaving(false);
    }
  };

  const disabled = !canEdit || saving;

  return (
    <div className="max-w-2xl">
      <h2 className="text-xl font-semibold text-slate-800 mb-1">Project Settings</h2>
      <p className="text-sm text-slate-500 mb-4">
        Your role tailors answers (DIY gets how-to guides); the jurisdiction scopes
        retrieval to the right municipal code.
      </p>

      {!canEdit && (
        <div className="p-3 mb-4 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg text-sm">
          You have view-only access to this project — settings can't be edited.
        </div>
      )}
      {error && (
        <div className="p-3 mb-4 bg-red-50 border border-red-200 text-red-800 rounded-lg text-sm">{error}</div>
      )}
      {success && (
        <div className="p-3 mb-4 bg-green-50 border border-green-200 text-green-800 rounded-lg text-sm">{success}</div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <label className="block">
          <span className="block text-sm font-medium text-slate-700 mb-1">Project name</span>
          <input type="text" value={form.name} onChange={setField("name")} disabled={disabled}
            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm" />
        </label>

        <label className="block">
          <span className="block text-sm font-medium text-slate-700 mb-1">Description</span>
          <textarea value={form.description} onChange={setField("description")} disabled={disabled} rows={2}
            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm" />
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <label className="block">
            <span className="block text-sm font-medium text-slate-700 mb-1">Your role</span>
            <select value={form.persona} onChange={setField("persona")} disabled={disabled}
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm bg-white">
              {PERSONA_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="block text-sm font-medium text-slate-700 mb-1">Experience level</span>
            <select value={form.experience} onChange={setField("experience")} disabled={disabled}
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm bg-white">
              {EXPERIENCE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="block text-sm font-medium text-slate-700 mb-1">Municipality (jurisdiction)</span>
            <input type="text" value={form.municipality} onChange={setField("municipality")} disabled={disabled}
              placeholder="e.g. dallas, plano, frisco"
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm" />
          </label>

          <label className="block">
            <span className="block text-sm font-medium text-slate-700 mb-1">Budget</span>
            <input type="text" value={form.budget} onChange={setField("budget")} disabled={disabled}
              placeholder="e.g. $5,000"
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm" />
          </label>
        </div>

        <label className="block">
          <span className="block text-sm font-medium text-slate-700 mb-1">Address</span>
          <input type="text" value={form.address} onChange={setField("address")} disabled={disabled}
            placeholder="Used to auto-detect jurisdiction when municipality is blank"
            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm" />
        </label>

        <label className="block">
          <span className="block text-sm font-medium text-slate-700 mb-1">Project notes</span>
          <textarea value={form.project_notes} onChange={setField("project_notes")} disabled={disabled} rows={3}
            placeholder="Bounded notes the assistant considers (kept short)."
            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm" />
        </label>

        <div className="flex items-center gap-3 pt-2">
          <button type="submit" disabled={disabled}
            className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium disabled:opacity-50">
            {saving ? "Saving…" : "Save settings"}
          </button>
          <button type="button" onClick={() => setForm(toForm(project))} disabled={disabled}
            className="px-4 py-2 border border-slate-300 text-slate-700 rounded-md text-sm">
            Reset
          </button>
        </div>
      </form>
    </div>
  );
}
