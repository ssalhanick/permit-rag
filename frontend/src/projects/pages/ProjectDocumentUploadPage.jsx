import React, { useState } from "react";
import { Link } from "react-router-dom";
import { API_BASE_URL, API_PREFIX } from "../../api.js";
import { useProject } from "../ProjectContext.jsx";
import { FileText, Upload, CheckCircle, AlertTriangle, Lock, Users } from "lucide-react";

const ALLOWED_EXTENSIONS =
  ".pdf,.html,.htm,.docx,.pptx,.txt,.md,.markdown,.jpg,.jpeg,.png,.gif,.tiff,.tif,.bmp,.webp,.xlsx,.xls,.csv,.dwg,.dxf";

/**
 * Upload a private or team-visible document to this project — drawings,
 * plans, spreadsheets, CAD, or any other project-specific reference material.
 * No approval workflow, unlike an ordinance or overlay petition: this lands
 * instantly, scoped to just this project.
 */
export default function ProjectDocumentUploadPage() {
  const { project, projectId, canEdit, loading: projectLoading } = useProject();
  const [file, setFile] = useState(null);
  const [visibility, setVisibility] = useState("team");
  const [subjectTags, setSubjectTags] = useState("");
  const [status, setStatus] = useState(null); // null | "loading" | "success" | "error"
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const canSubmit = canEdit && file && status !== "loading";

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus("loading");
    setError("");

    const body = new FormData();
    body.append("file", file);
    body.append("visibility", visibility);
    if (subjectTags.trim()) {
      body.append("subject_tags", subjectTags.trim());
    }

    try {
      const accessToken = localStorage.getItem("access_token");
      const res = await fetch(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/documents/upload`, {
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
      setError(err.message || "Failed to upload document.");
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
        Upload a project document
      </h1>
      <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
        Attach drawings, plans, spreadsheets, images, or CAD files to {project?.name || "this project"}.
        This is private reference material, not a shared corpus contribution — it's available
        instantly, no staff review needed.
      </p>

      {!canEdit && (
        <div className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-700/60 dark:bg-amber-900/20 mb-6">
          <AlertTriangle className="w-5 h-5 shrink-0 text-amber-500 mt-0.5" />
          <p className="text-amber-800 dark:text-amber-300">
            Only this project's owner or editors can upload documents.
          </p>
        </div>
      )}

      {status === "success" && result ? (
        <div className="flex items-start gap-3 rounded-lg border border-emerald-300 bg-emerald-50 p-4 text-sm dark:border-emerald-700/60 dark:bg-emerald-900/20">
          <CheckCircle className="w-5 h-5 shrink-0 text-emerald-500 mt-0.5" />
          <div>
            <p className="font-semibold text-emerald-800 dark:text-emerald-300">
              Upload accepted — status: {result.status}
            </p>
            <p className="text-emerald-700 dark:text-emerald-400 mt-0.5">{result.message}</p>
            <Link
              to={`/projects/${projectId}/documents`}
              className="inline-block mt-2 text-xs font-bold text-emerald-700 dark:text-emerald-300 hover:underline"
            >
              View project documents →
            </Link>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Visibility
            </label>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setVisibility("team")}
                disabled={!canEdit}
                className={`flex-1 flex items-center gap-2 rounded-lg border p-3 text-sm text-left transition-colors ${
                  visibility === "team"
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-950/40 text-blue-800 dark:text-blue-200"
                    : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-blue-300"
                }`}
              >
                <Users className="w-4 h-4 shrink-0" />
                <span>
                  <span className="block font-semibold">Team</span>
                  <span className="block text-xs opacity-80">Visible to the whole project</span>
                </span>
              </button>
              <button
                type="button"
                onClick={() => setVisibility("private")}
                disabled={!canEdit}
                className={`flex-1 flex items-center gap-2 rounded-lg border p-3 text-sm text-left transition-colors ${
                  visibility === "private"
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-950/40 text-blue-800 dark:text-blue-200"
                    : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-blue-300"
                }`}
              >
                <Lock className="w-4 h-4 shrink-0" />
                <span>
                  <span className="block font-semibold">Private</span>
                  <span className="block text-xs opacity-80">Visible only to you</span>
                </span>
              </button>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Tags (optional)
            </label>
            <input
              type="text"
              value={subjectTags}
              onChange={(e) => setSubjectTags(e.target.value)}
              placeholder="e.g. floor-plan, electrical, revision-2"
              className="tt-input w-full"
              disabled={!canEdit}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
              File
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
                accept={ALLOWED_EXTENSIONS}
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                disabled={!canEdit}
              />
            </label>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-1.5">
              PDF, Word, PowerPoint, text, and images are searchable in AI answers. Spreadsheets and
              CAD files (DWG/DXF) are stored for download but aren't searchable yet.
            </p>
          </div>

          {status === "error" && (
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          )}

          <button type="submit" className="tt-btn-primary text-sm" disabled={!canSubmit}>
            {status === "loading" ? "Uploading…" : "Upload document"}
          </button>
        </form>
      )}
    </div>
  );
}
