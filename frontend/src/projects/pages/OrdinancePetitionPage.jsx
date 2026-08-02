import React, { useState } from "react";
import { Link } from "react-router-dom";
import { API_BASE_URL, API_PREFIX } from "../../api.js";
import { useProject } from "../ProjectContext.jsx";
import { FileText, Upload, CheckCircle } from "lucide-react";

// Must match db/schema.sql enums (authority_level, doc_type) — same lists
// UploadPage.jsx (admin) uses, since a petition becomes a real corpus
// document once approved.
const AUTHORITY_LEVELS = ["municipal", "county", "state", "federal"];
const DOC_TYPES = [
  "building_code",
  "zoning_ordinance",
  "permit_checklist",
  "fire_code",
  "plumbing_code",
  "electrical_code",
  "mechanical_code",
  "energy_code",
  "accessibility_code",
  "osha_standard",
  "administrative_rule",
  "amendment",
  "state_statute",
  "federal_regulation",
  "other",
];

/**
 * Petition a jurisdiction-wide ordinance or code into the shared corpus.
 * Any authenticated user can submit one; a verified contributor's petition
 * auto-approves straight into the corpus, everyone else's queues for staff
 * review. Not scoped to this project on the backend (any petition helps
 * every project in that jurisdiction) — routed under the project for
 * navigational consistency with the overlay petition page.
 */
export default function OrdinancePetitionPage() {
  const { project, projectId, loading: projectLoading } = useProject();
  const [municipality, setMunicipality] = useState(project?.municipality || "");
  const [authorityLevel, setAuthorityLevel] = useState("municipal");
  const [docType, setDocType] = useState("zoning_ordinance");
  const [subjectTags, setSubjectTags] = useState("");
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState(null); // null | "loading" | "success" | "error"
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const canSubmit = municipality.trim() && file && status !== "loading";

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus("loading");
    setError("");

    const body = new FormData();
    body.append("file", file);
    body.append("municipality", municipality.trim());
    body.append("authority_level", authorityLevel);
    body.append("doc_type", docType);
    if (subjectTags.trim()) {
      body.append("subject_tags", subjectTags.trim());
    }

    try {
      const accessToken = localStorage.getItem("access_token");
      const res = await fetch(`${API_BASE_URL}${API_PREFIX}/documents/petitions`, {
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
        Petition an ordinance or code
      </h1>
      <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
        Contribute a jurisdiction-wide ordinance or code to the shared corpus — this helps every
        project in that jurisdiction, not just {project?.name || "this one"}. Verified contributors'
        petitions are approved instantly; everyone else's is queued for a quick staff review.
      </p>

      {status === "success" && result ? (
        <div className="flex items-start gap-3 rounded-lg border border-emerald-300 bg-emerald-50 p-4 text-sm dark:border-emerald-700/60 dark:bg-emerald-900/20">
          <CheckCircle className="w-5 h-5 shrink-0 text-emerald-500 mt-0.5" />
          <div>
            <p className="font-semibold text-emerald-800 dark:text-emerald-300">
              Petition submitted
            </p>
            <p className="text-emerald-700 dark:text-emerald-400 mt-0.5">{result.message}</p>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 sm:p-8 shadow-sm space-y-5">
          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">
              Jurisdiction *
            </label>
            <input
              type="text"
              value={municipality}
              onChange={(e) => setMunicipality(e.target.value)}
              placeholder="e.g. Dallas, Collin County, Texas"
              className="tt-input w-full px-3.5 py-2.5 text-sm"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">
                Authority level
              </label>
              <select
                value={authorityLevel}
                onChange={(e) => setAuthorityLevel(e.target.value)}
                className="tt-input w-full px-3.5 py-2.5 text-sm"
              >
                {AUTHORITY_LEVELS.map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">
                Document type
              </label>
              <select
                value={docType}
                onChange={(e) => setDocType(e.target.value)}
                className="tt-input w-full px-3.5 py-2.5 text-sm"
              >
                {DOC_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">
              Tags (optional)
            </label>
            <input
              type="text"
              value={subjectTags}
              onChange={(e) => setSubjectTags(e.target.value)}
              placeholder="e.g. setbacks, pools, decks"
              className="tt-input w-full px-3.5 py-2.5 text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">
              Source document (PDF or HTML) *
            </label>
            <label className="flex items-center gap-2 rounded-xl border border-dashed border-slate-300 dark:border-slate-600 p-5 text-sm text-slate-500 dark:text-slate-400 cursor-pointer hover:border-blue-400 transition-colors">
              <Upload className="w-5 h-5 text-slate-400" />
              {file ? (
                <span className="flex items-center gap-1.5 font-medium text-slate-700 dark:text-slate-300">
                  <FileText className="w-4 h-4 text-blue-500" /> {file.name}
                </span>
              ) : (
                "Choose a file…"
              )}
              <input
                type="file"
                accept=".pdf,.html,.htm"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
          </div>

          {status === "error" && (
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          )}

          <div className="pt-2">
            <button type="submit" className="tt-btn-primary text-sm px-6 py-2.5 rounded-xl" disabled={!canSubmit}>
              {status === "loading" ? "Submitting…" : "Submit petition"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
