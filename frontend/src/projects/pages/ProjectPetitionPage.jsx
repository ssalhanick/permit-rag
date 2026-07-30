import React, { useState } from "react";
import { Link } from "react-router-dom";
import { API_BASE_URL, API_PREFIX } from "../../api.js";
import { useProject } from "../ProjectContext.jsx";
import { FileText, Upload, CheckCircle, AlertTriangle } from "lucide-react";

const OVERLAY_TYPE_OPTIONS = [
  { value: "historic_district", label: "Historic district" },
  { value: "conservation_district", label: "Conservation district" },
  { value: "hoa", label: "HOA bylaws" },
  { value: "other", label: "Other" },
];

/**
 * Petition a historic/conservation-district or HOA overlay scoped to this
 * project's own address. A staff reviewer approves it (optionally refining
 * the boundary), after which its documents surface for any OTHER project
 * whose address falls inside that boundary too — not just this one.
 */
export default function ProjectPetitionPage() {
  const { project, projectId, canEdit, loading: projectLoading } = useProject();
  const [name, setName] = useState("");
  const [overlayType, setOverlayType] = useState("historic_district");
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState(null); // null | "loading" | "success" | "error"
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const hasCoordinates = project?.latitude != null && project?.longitude != null;
  const canSubmit = canEdit && hasCoordinates && name.trim() && file && status !== "loading";

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus("loading");
    setError("");

    const body = new FormData();
    body.append("file", file);
    body.append("name", name.trim());
    body.append("overlay_type", overlayType);
    if (notes.trim()) {
      body.append("notes", notes.trim());
    }

    try {
      const accessToken = localStorage.getItem("access_token");
      const res = await fetch(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/overlays`, {
        method: "POST",
        headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
        body,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail || `HTTP ${res.status}`);
      }
      setResult(data);
      setStatus("success");
    } catch (err) {
      setError(err.message || "Failed to submit petition.");
      setStatus("error");
    }
  };

  if (projectLoading) {
    return <div className="max-w-2xl mx-auto p-6 text-sm text-slate-500">Loading…</div>;
  }

  return (
    <div className="max-w-2xl mx-auto p-4 sm:p-6">
      <nav className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-4">
        <Link to={`/projects/${projectId}/dashboard`} className="hover:text-blue-600 dark:hover:text-blue-400">
          ← Back to project
        </Link>
      </nav>

      <h1 className="text-2xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight mb-1">
        Petition an area
      </h1>
      <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
        Upload documentation for a historic district, conservation district, or HOA that applies
        to this project's address. A staff reviewer confirms the boundary and approves it — once
        approved, it applies to any other project inside that same boundary too, not just this one.
      </p>

      {!canEdit && (
        <div className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-700/60 dark:bg-amber-900/20 mb-6">
          <AlertTriangle className="w-5 h-5 shrink-0 text-amber-500 mt-0.5" />
          <p className="text-amber-800 dark:text-amber-300">
            Only this project's owner or editors can submit a petition.
          </p>
        </div>
      )}

      {canEdit && !hasCoordinates && (
        <div className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-700/60 dark:bg-amber-900/20 mb-6">
          <AlertTriangle className="w-5 h-5 shrink-0 text-amber-500 mt-0.5" />
          <p className="text-amber-800 dark:text-amber-300">
            This project has no address on file yet. Set an address in{" "}
            <Link to={`/projects/${projectId}/settings`} className="underline">
              Settings
            </Link>{" "}
            before petitioning — a petition needs a point to draw its boundary around.
          </p>
        </div>
      )}

      {status === "success" && result ? (
        <div className="flex items-start gap-3 rounded-lg border border-emerald-300 bg-emerald-50 p-4 text-sm dark:border-emerald-700/60 dark:bg-emerald-900/20">
          <CheckCircle className="w-5 h-5 shrink-0 text-emerald-500 mt-0.5" />
          <div>
            <p className="font-semibold text-emerald-800 dark:text-emerald-300">
              Petition submitted — status: {result.status}
            </p>
            <p className="text-emerald-700 dark:text-emerald-400 mt-0.5">
              "{result.name}" is awaiting staff review. You'll see it reflected once approved.
            </p>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Swiss Avenue Historic District"
              className="tt-input w-full"
              disabled={!canEdit}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Type
            </label>
            <select
              value={overlayType}
              onChange={(e) => setOverlayType(e.target.value)}
              className="tt-input w-full"
              disabled={!canEdit}
            >
              {OVERLAY_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Notes (optional)
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              className="tt-input w-full"
              disabled={!canEdit}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Source document (PDF or HTML)
            </label>
            <label className="flex items-center gap-2 rounded-lg border border-dashed border-slate-300 dark:border-slate-600 p-4 text-sm text-slate-500 dark:text-slate-400 cursor-pointer hover:border-blue-400">
              <Upload className="w-4 h-4" />
              {file ? (
                <span className="flex items-center gap-1.5 text-slate-700 dark:text-slate-300">
                  <FileText className="w-4 h-4" /> {file.name}
                </span>
              ) : (
                "Choose a file…"
              )}
              <input
                type="file"
                accept=".pdf,.html,.htm"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                disabled={!canEdit}
              />
            </label>
          </div>

          {status === "error" && (
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          )}

          <button type="submit" className="tt-btn-primary text-sm" disabled={!canSubmit}>
            {status === "loading" ? "Submitting…" : "Submit petition"}
          </button>
        </form>
      )}
    </div>
  );
}
