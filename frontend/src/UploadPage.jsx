import React, { useEffect, useState } from "react";
import {
  UploadCloud,
  Link2,
  FileText,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Camera,
  Image as ImageIcon,
} from "lucide-react";
import { API_BASE_URL, API_PREFIX, fetchProjects, getPullJob, pullPage } from "./api.js";
import { useAuth } from "./context/AuthContext.jsx";
import { formatUploadError, getUploadBlockers, suggestDocIdFromFilename } from "./uploadUtils.js";
import { isNativePlatform } from "./platform.js";
import { capturePhotoForUpload, pickImageForUpload } from "./services/mobileUpload.js";

// Must match db/schema.sql enums (authority_level, doc_type)
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
const SOURCE_TIERS = [
  { value: 1, label: "1 — Corpus (scraped, authoritative)" },
  { value: 2, label: "2 — User ordinance upload (supplementary)" },
  { value: 3, label: "3 — Project document (drawings/specs)" },
];

const DEFAULT_FORM = {
  doc_id: "",
  municipality: "",
  authority_level: "municipal",
  doc_type: "zoning_ordinance",
  subject_tags: "",
  source_tier: 2,
  source_url: "",
  project_id: "",
};

// ── Shared field primitives (Tailwind, matches QueryPage/ProjectDashboardPage) ──

const inputClass =
  "w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 " +
  "rounded-xl px-3 py-2 text-xs sm:text-sm text-slate-900 dark:text-slate-100 " +
  "placeholder:text-slate-400 dark:placeholder:text-slate-500 " +
  "focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors";

const labelClass = "block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5";
const hintClass = "text-[11px] text-slate-500 dark:text-slate-400 mt-1";

function Field({ label, hint, htmlFor, children }) {
  return (
    <div>
      <label htmlFor={htmlFor} className={labelClass}>
        {label}
      </label>
      {children}
      {hint && <p className={hintClass}>{hint}</p>}
    </div>
  );
}

function StatusBanner({ tone, children }) {
  const tones = {
    loading: "bg-blue-50/80 dark:bg-blue-950/40 border-blue-200/80 dark:border-blue-800/60 text-blue-900 dark:text-blue-200",
    error: "bg-rose-50/80 dark:bg-rose-950/40 border-rose-200/80 dark:border-rose-800/60 text-rose-900 dark:text-rose-200",
    success: "bg-emerald-50/80 dark:bg-emerald-950/40 border-emerald-200/80 dark:border-emerald-800/60 text-emerald-900 dark:text-emerald-200",
  };
  const icons = {
    loading: <Loader2 className="w-4 h-4 flex-shrink-0 mt-0.5 animate-spin" />,
    error: <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />,
    success: <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" />,
  };
  return (
    <div className={`flex gap-2.5 p-3 border rounded-xl text-xs ${tones[tone]}`}>
      {icons[tone]}
      <div className="flex-1">{children}</div>
    </div>
  );
}

export default function UploadPage() {
  const { user } = useAuth();
  const isSuperadmin = user?.role === "superadmin";
  const [form, setForm] = useState(DEFAULT_FORM);
  const [file, setFile] = useState(null);
  const [projects, setProjects] = useState([]);
  const [status, setStatus] = useState(null); // null | 'loading' | 'success' | 'error'
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [mode, setMode] = useState("file"); // 'file' | 'url'
  const [pullUrl, setPullUrl] = useState("");
  const [pullJob, setPullJob] = useState(null);
  const [pullStatus, setPullStatus] = useState(null); // null | 'loading' | 'polling' | 'success' | 'error'
  const [pullError, setPullError] = useState("");

  useEffect(() => {
    if (mode === "url" && !isSuperadmin) {
      setMode("file");
    }
  }, [mode, isSuperadmin]);

  useEffect(() => {
    if (user) {
      fetchProjects()
        .then((res) => setProjects(res.data || []))
        .catch(() => {});
    } else {
      setProjects([]);
    }
  }, [user]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: name === "source_tier" ? Number(value) : value,
    }));
  };

  const handleFileChange = (e) => {
    const f = e.target.files?.[0] || null;
    setFile(f);
    if (f && !form.doc_id) {
      const suggested = suggestDocIdFromFilename(f.name);
      setForm((prev) => ({ ...prev, doc_id: suggested }));
    }
  };

  const handleMobileCapture = async () => {
    const picked = await capturePhotoForUpload();
    if (!picked) {
      return;
    }
    const f = new File([picked.blob], picked.name, { type: picked.blob.type || "image/jpeg" });
    setFile(f);
    if (!form.doc_id) {
      setForm((prev) => ({ ...prev, doc_id: suggestDocIdFromFilename(f.name) }));
    }
  };

  const handleMobilePick = async () => {
    const picked = await pickImageForUpload();
    if (!picked) {
      return;
    }
    const f = new File([picked.blob], picked.name, { type: picked.blob.type || "image/jpeg" });
    setFile(f);
    if (!form.doc_id) {
      setForm((prev) => ({ ...prev, doc_id: suggestDocIdFromFilename(f.name) }));
    }
  };

  const blockers = getUploadBlockers({
    file,
    docId: form.doc_id,
    municipality: form.municipality,
    status,
  });
  const canSubmit = blockers.length === 0;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus("loading");
    setError("");
    setResult(null);

    const body = new FormData();
    body.append("file", file);
    body.append("doc_id", form.doc_id.trim());
    body.append("municipality", form.municipality.trim().toLowerCase());
    body.append("authority_level", form.authority_level);
    body.append("doc_type", form.doc_type);
    body.append("subject_tags", form.subject_tags.trim());
    body.append("source_tier", String(form.source_tier));
    if (form.source_url.trim()) {
      body.append("source_url", form.source_url.trim());
    }
    if (form.project_id) {
      body.append("project_id", form.project_id);
    }

    try {
      const accessToken = localStorage.getItem("access_token");
      const res = await fetch(`${API_BASE_URL}${API_PREFIX}/admin/documents/upload`, {
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
      setError(formatUploadError(err.message));
      setStatus("error");
    }
  };

  const handleReset = () => {
    setForm(DEFAULT_FORM);
    setFile(null);
    setStatus(null);
    setResult(null);
    setError("");
  };

  // ── Pull from URL ──
  useEffect(() => {
    if (pullStatus !== "polling" || !pullJob?.job_id) {
      return undefined;
    }
    const timer = setInterval(async () => {
      try {
        const res = await getPullJob(pullJob.job_id);
        setPullJob(res.data);
        if (res.data.status === "complete") {
          setPullStatus("success");
        } else if (res.data.status === "failed") {
          setPullStatus("error");
          setPullError(res.data.error || "Pull job failed.");
        }
      } catch (err) {
        setPullStatus("error");
        setPullError(err.message);
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [pullStatus, pullJob?.job_id]);

  const canPull =
    pullUrl.trim().startsWith("https://") &&
    form.municipality.trim() &&
    pullStatus !== "loading" &&
    pullStatus !== "polling";

  const handlePullSubmit = async (e) => {
    e.preventDefault();
    setPullStatus("loading");
    setPullError("");
    setPullJob(null);
    try {
      const payload = {
        url: pullUrl.trim(),
        municipality: form.municipality.trim().toLowerCase(),
        authority_level: form.authority_level,
        doc_type: form.doc_type,
        subject_tags: form.subject_tags.split(",").map((t) => t.trim()).filter(Boolean),
        source_tier: form.source_tier,
      };
      const res = await pullPage(payload);
      setPullJob(res.data);
      setPullStatus("polling");
    } catch (err) {
      setPullError(formatUploadError(err.message));
      setPullStatus("error");
    }
  };

  const handlePullReset = () => {
    setPullUrl("");
    setPullJob(null);
    setPullStatus(null);
    setPullError("");
  };

  // Item: tier-2 project override. Tier 1 (general corpus) never binds to a
  // project; tier 2/3 do — tier 2 defaults to the uploader's active project
  // server-side (api/routes/upload.py::upload_document) when left blank, so
  // this picker is how a tier-2 upload overrides that default explicitly.
  const showProjectPicker = user && projects.length > 0 && form.source_tier !== 1;

  return (
    <main className="max-w-3xl mx-auto p-4 sm:p-6 pb-16">
      <div className="mb-5">
        <h1 className="text-lg sm:text-xl font-extrabold text-slate-900 dark:text-slate-100 flex items-center gap-2">
          <UploadCloud className="w-5 h-5 text-blue-600" />
          Upload Permit Document
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-1">
          Add a new ordinance, code, or reference document to the corpus. The file is
          chunked and embedded in the background, and subject tags / effective date
          are proposed automatically for review once processing finishes.
        </p>
      </div>

      <section className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 sm:p-6 space-y-5">
        {/* Mode tabs */}
        <div className="flex gap-2 border-b border-slate-100 dark:border-slate-800 pb-3" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "file"}
            onClick={() => setMode("file")}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl transition-colors ${
              mode === "file"
                ? "bg-blue-600 text-white shadow-sm"
                : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
            }`}
          >
            <UploadCloud className="w-3.5 h-3.5" />
            Upload file
          </button>
          {isSuperadmin ? (
            <button
              type="button"
              role="tab"
              aria-selected={mode === "url"}
              onClick={() => setMode("url")}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl transition-colors ${
                mode === "url"
                  ? "bg-blue-600 text-white shadow-sm"
                  : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700"
              }`}
            >
              <Link2 className="w-3.5 h-3.5" />
              Pull from URL
            </button>
          ) : null}
        </div>

        {/* ── Pull from URL tab ── */}
        {mode === "url" && isSuperadmin ? (
          <form onSubmit={handlePullSubmit} className="space-y-5">
            <div className="space-y-3">
              <h2 className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Page URL
              </h2>
              <Field
                label="HTTPS page to scan for documents *"
                htmlFor="pull-url"
                hint="Linked PDF / DOCX / PPTX / HTML / TXT / MD files are discovered and ingested only if new or changed. Unchanged files are skipped; changed files supersede the old version."
              >
                <input
                  id="pull-url"
                  type="url"
                  value={pullUrl}
                  onChange={(e) => setPullUrl(e.target.value)}
                  placeholder="https://www.dallascityhall.com/departments/sustainabledevelopment/buildinginspection"
                  required
                  className={inputClass}
                />
              </Field>
            </div>

            <div className="space-y-3">
              <h2 className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Metadata for discovered files
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field label="Municipality *" htmlFor="pull-municipality">
                  <input
                    id="pull-municipality"
                    name="municipality"
                    value={form.municipality}
                    onChange={handleChange}
                    placeholder="dallas"
                    required
                    className={inputClass}
                  />
                </Field>
                <Field label="Authority Level *" htmlFor="pull-authority">
                  <select
                    id="pull-authority"
                    name="authority_level"
                    value={form.authority_level}
                    onChange={handleChange}
                    className={inputClass}
                  >
                    {AUTHORITY_LEVELS.map((v) => (
                      <option key={v} value={v}>{v}</option>
                    ))}
                  </select>
                </Field>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field label="Document Type *" htmlFor="pull-doc-type">
                  <select
                    id="pull-doc-type"
                    name="doc_type"
                    value={form.doc_type}
                    onChange={handleChange}
                    className={inputClass}
                  >
                    {DOC_TYPES.map((v) => (
                      <option key={v} value={v}>{v.replace(/_/g, " ")}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Source Tier *" htmlFor="pull-source-tier">
                  <select
                    id="pull-source-tier"
                    name="source_tier"
                    value={form.source_tier}
                    onChange={handleChange}
                    className={inputClass}
                  >
                    {SOURCE_TIERS.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </Field>
              </div>
              <Field label="Subject Tags (comma-separated)" htmlFor="pull-subject-tags">
                <input
                  id="pull-subject-tags"
                  name="subject_tags"
                  value={form.subject_tags}
                  onChange={handleChange}
                  placeholder="permits, checklists"
                  className={inputClass}
                />
              </Field>
            </div>

            {pullStatus === "loading" || pullStatus === "polling" ? (
              <StatusBanner tone="loading">
                {pullStatus === "loading"
                  ? "Starting pull…"
                  : `Pulling… ${pullJob?.processed_files ?? 0}/${pullJob?.total_files ?? "?"} files processed.`}
              </StatusBanner>
            ) : null}

            {pullStatus === "error" && pullError ? (
              <StatusBanner tone="error">{pullError}</StatusBanner>
            ) : null}

            {pullJob?.files?.length ? (
              <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 dark:bg-slate-800/60">
                    <tr>
                      <th className="text-left font-bold text-slate-600 dark:text-slate-300 px-3 py-2">File</th>
                      <th className="text-left font-bold text-slate-600 dark:text-slate-300 px-3 py-2">Verdict</th>
                      <th className="text-left font-bold text-slate-600 dark:text-slate-300 px-3 py-2">doc_id</th>
                      <th className="text-left font-bold text-slate-600 dark:text-slate-300 px-3 py-2">Detail</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {pullJob.files.map((f) => (
                      <tr key={f.url}>
                        <td title={f.url} className="px-3 py-2 text-slate-700 dark:text-slate-300">{f.filename}</td>
                        <td className="px-3 py-2 text-slate-700 dark:text-slate-300">
                          {f.verdict}
                          {f.url_changed ? " ⚠ url changed" : ""}
                        </td>
                        <td className="px-3 py-2">{f.doc_id ? <code className="text-[11px] bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded">{f.doc_id}</code> : "—"}</td>
                        <td className="px-3 py-2 text-slate-500 dark:text-slate-400">{f.detail || ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}

            {pullStatus === "success" ? (
              <div className="space-y-3">
                <StatusBanner tone="success">
                  <span className="font-bold">Pull complete.</span> {pullJob?.total_files ?? 0} file(s) discovered
                  on the page. Rows marked <strong>flagged</strong> need human review.
                </StatusBanner>
                <button
                  type="button"
                  onClick={handlePullReset}
                  className="px-4 py-2 text-xs font-semibold rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                >
                  Pull another page
                </button>
              </div>
            ) : (
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={!canPull}
                  className="px-4 py-2 text-xs font-semibold rounded-xl bg-blue-600 hover:bg-blue-700 text-white shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {pullStatus === "polling" ? "Pulling…" : "Pull"}
                </button>
              </div>
            )}
          </form>
        ) : null}

        {/* ── Upload file tab ── */}
        {mode === "file" && status === "loading" ? (
          <StatusBanner tone="loading">
            Upload in progress. Keep this page open until response returns.
          </StatusBanner>
        ) : null}

        {mode === "file" && status === "error" && error ? (
          <StatusBanner tone="error">{error}</StatusBanner>
        ) : null}

        {mode === "file" ? (status === "success" && result ? (
          <div className="space-y-4">
            <StatusBanner tone="success">
              <span className="font-bold">Upload accepted.</span> Chunking, embedding, and metadata
              proposal are running in the background.
            </StatusBanner>
            <dl className="text-xs space-y-2 bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800 rounded-xl p-4">
              <div className="flex gap-2">
                <dt className="font-bold text-slate-600 dark:text-slate-400 w-24 flex-shrink-0">doc_id</dt>
                <dd><code className="bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded text-[11px]">{result.doc_id}</code></dd>
              </div>
              <div className="flex gap-2">
                <dt className="font-bold text-slate-600 dark:text-slate-400 w-24 flex-shrink-0">Status</dt>
                <dd className="text-slate-800 dark:text-slate-200">{result.status}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="font-bold text-slate-600 dark:text-slate-400 w-24 flex-shrink-0">Saved to</dt>
                <dd><code className="bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded text-[11px] break-all">{result.local_path}</code></dd>
              </div>
              <div className="flex gap-2">
                <dt className="font-bold text-slate-600 dark:text-slate-400 w-24 flex-shrink-0">Next step</dt>
                <dd className="text-slate-700 dark:text-slate-300">
                  Poll{" "}
                  <a
                    href={`${API_BASE_URL}${API_PREFIX}/documents/${result.doc_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 dark:text-blue-400 underline font-semibold"
                  >
                    /documents/{result.doc_id}
                  </a>{" "}
                  until <code className="bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded text-[11px]">document_status</code> is{" "}
                  <code className="bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded text-[11px]">active</code>. Proposed subject
                  tags and effective date (if any) land in the metadata review queue once processing finishes.
                </dd>
              </div>
            </dl>
            <button
              type="button"
              onClick={handleReset}
              className="px-4 py-2 text-xs font-semibold rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
            >
              Upload another
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* ── File picker ── */}
            <div className="space-y-3">
              <h2 className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                File
              </h2>
              <Field label="PDF or HTML file *" htmlFor="upload-file" hint={!file ? "Accepted: .pdf, .html, .htm" : undefined}>
                <input
                  id="upload-file"
                  type="file"
                  accept=".pdf,.html,.htm"
                  onChange={handleFileChange}
                  required
                  className={`${inputClass} file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-blue-600 file:text-white hover:file:bg-blue-700 file:cursor-pointer`}
                />
              </Field>
              {file && (
                <p className="text-xs text-slate-600 dark:text-slate-400 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-blue-500" />
                  Selected: <strong className="text-slate-800 dark:text-slate-200">{file.name}</strong> ({(file.size / 1024).toFixed(1)} KB)
                </p>
              )}
              {isNativePlatform() ? (
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleMobileCapture}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                  >
                    <Camera className="w-3.5 h-3.5" />
                    Take photo
                  </button>
                  <button
                    type="button"
                    onClick={handleMobilePick}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                  >
                    <ImageIcon className="w-3.5 h-3.5" />
                    Pick from gallery
                  </button>
                </div>
              ) : null}
            </div>

            {/* ── Identity ── */}
            <div className="space-y-3">
              <h2 className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Identity
              </h2>
              <Field
                label="Document ID *"
                htmlFor="doc_id"
                hint="Unique slug, e.g. plano-pool-ordinance-2024"
              >
                <input
                  id="doc_id"
                  name="doc_id"
                  value={form.doc_id}
                  onChange={handleChange}
                  placeholder="plano-pool-ordinance-2024"
                  pattern="[a-z0-9\-_]+"
                  title="Lowercase alphanumeric, hyphens, underscores only"
                  required
                  className={inputClass}
                />
              </Field>
              <Field
                label="Source URL"
                htmlFor="source_url"
                hint="Optional — where you obtained this document"
              >
                <input
                  id="source_url"
                  name="source_url"
                  type="url"
                  value={form.source_url}
                  onChange={handleChange}
                  placeholder="https://www.plano.gov/..."
                  className={inputClass}
                />
              </Field>
            </div>

            {/* ── Classification ── */}
            <div className="space-y-3">
              <h2 className="text-xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Classification
              </h2>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field
                  label="Municipality *"
                  htmlFor="municipality"
                  hint="Must match an existing jurisdiction (dallas, plano, fortworth, texas, federal) or a new one you're seeding."
                >
                  <input
                    id="municipality"
                    name="municipality"
                    value={form.municipality}
                    onChange={handleChange}
                    placeholder="plano"
                    required
                    className={inputClass}
                  />
                </Field>
                <Field label="Authority Level *" htmlFor="authority_level">
                  <select
                    id="authority_level"
                    name="authority_level"
                    value={form.authority_level}
                    onChange={handleChange}
                    className={inputClass}
                  >
                    {AUTHORITY_LEVELS.map((v) => (
                      <option key={v} value={v}>{v}</option>
                    ))}
                  </select>
                </Field>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field label="Document Type *" htmlFor="doc_type">
                  <select
                    id="doc_type"
                    name="doc_type"
                    value={form.doc_type}
                    onChange={handleChange}
                    className={inputClass}
                  >
                    {DOC_TYPES.map((v) => (
                      <option key={v} value={v}>{v.replace(/_/g, " ")}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Source Tier *" htmlFor="source_tier">
                  <select
                    id="source_tier"
                    name="source_tier"
                    value={form.source_tier}
                    onChange={handleChange}
                    className={inputClass}
                  >
                    {SOURCE_TIERS.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </Field>
              </div>

              <Field
                label="Subject Tags (comma-separated)"
                htmlFor="subject_tags"
                hint="Optional — additional tags will also be proposed automatically after processing, for review."
              >
                <input
                  id="subject_tags"
                  name="subject_tags"
                  value={form.subject_tags}
                  onChange={handleChange}
                  placeholder="pools, setbacks, fences"
                  className={inputClass}
                />
              </Field>

              {/* Tier-2/3 project override — irrelevant for tier 1 (general
                  corpus), so hidden entirely there. Tier 2 defaults to the
                  uploader's active project server-side when left blank; this
                  is how that default gets overridden explicitly. */}
              {showProjectPicker && (
                <Field
                  label={form.source_tier === 3 ? "Project Workspace *" : "Bind to Project Workspace"}
                  htmlFor="projectId"
                  hint={
                    form.source_tier === 2
                      ? "Defaults to your active project if left blank. Pick a different one to override that default for this upload."
                      : "Project documents (drawings/specs) belong to a specific project workspace."
                  }
                >
                  <select
                    id="projectId"
                    name="project_id"
                    value={form.project_id || ""}
                    onChange={(e) => setForm((prev) => ({ ...prev, project_id: e.target.value }))}
                    className={inputClass}
                  >
                    <option value="">
                      {form.source_tier === 2 ? "-- Your active project (default) --" : "-- Select a project --"}
                    </option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </Field>
              )}
            </div>

            {blockers.length ? (
              <div className="p-3 bg-amber-50/70 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl text-xs text-amber-900 dark:text-amber-200">
                <strong className="font-bold block mb-1">Before upload:</strong>
                <ul className="list-disc list-inside space-y-0.5">
                  {blockers.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Ready to upload.
              </p>
            )}

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={!canSubmit}
                className="px-4 py-2 text-xs font-semibold rounded-xl bg-blue-600 hover:bg-blue-700 text-white shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {status === "loading" ? "Uploading…" : "Upload & Ingest"}
              </button>
            </div>
          </form>
        )) : null}
      </section>
    </main>
  );
}
