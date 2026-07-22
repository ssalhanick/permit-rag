import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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

  return (
    <main className="page">
      <section className="panel">
        <h1>Upload Permit Document</h1>
        <p className="muted">
          Add a new ordinance, code, or reference document to the corpus.
          The file will be chunked and embedded in the background.
          All fields are required for proper metadata tagging.
        </p>

        <div className="upload-mode-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "file"}
            className={mode === "file" ? "" : "secondary-button"}
            onClick={() => setMode("file")}
          >
            Upload file
          </button>
          {isSuperadmin ? (
            <button
              type="button"
              role="tab"
              aria-selected={mode === "url"}
              className={mode === "url" ? "" : "secondary-button"}
              onClick={() => setMode("url")}
            >
              Pull from URL
            </button>
          ) : null}
        </div>

        {mode === "url" && isSuperadmin ? (
          <form onSubmit={handlePullSubmit} className="form upload-form">
            <fieldset className="upload-fieldset">
              <legend>Page URL</legend>
              <label htmlFor="pull-url">HTTPS page to scan for documents *</label>
              <input
                id="pull-url"
                type="url"
                value={pullUrl}
                onChange={(e) => setPullUrl(e.target.value)}
                placeholder="https://www.dallascityhall.com/departments/sustainabledevelopment/buildinginspection"
                required
              />
              <p className="field-hint">
                Linked PDF / DOCX / PPTX / HTML / TXT / MD files are discovered and
                ingested only if new or changed. Unchanged files are skipped;
                changed files supersede the old version.
              </p>
            </fieldset>

            <fieldset className="upload-fieldset">
              <legend>Metadata for discovered files</legend>
              <div className="row">
                <div>
                  <label htmlFor="pull-municipality">Municipality *</label>
                  <input
                    id="pull-municipality"
                    name="municipality"
                    value={form.municipality}
                    onChange={handleChange}
                    placeholder="dallas"
                    required
                  />
                </div>
                <div>
                  <label htmlFor="pull-authority">Authority Level *</label>
                  <select
                    id="pull-authority"
                    name="authority_level"
                    value={form.authority_level}
                    onChange={handleChange}
                  >
                    {AUTHORITY_LEVELS.map((v) => (
                      <option key={v} value={v}>{v}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="row">
                <div>
                  <label htmlFor="pull-doc-type">Document Type *</label>
                  <select
                    id="pull-doc-type"
                    name="doc_type"
                    value={form.doc_type}
                    onChange={handleChange}
                  >
                    {DOC_TYPES.map((v) => (
                      <option key={v} value={v}>{v.replace(/_/g, " ")}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="pull-source-tier">Source Tier *</label>
                  <select
                    id="pull-source-tier"
                    name="source_tier"
                    value={form.source_tier}
                    onChange={handleChange}
                  >
                    {SOURCE_TIERS.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <label htmlFor="pull-subject-tags">
                Subject Tags{" "}
                <span className="field-hint">(comma-separated)</span>
              </label>
              <input
                id="pull-subject-tags"
                name="subject_tags"
                value={form.subject_tags}
                onChange={handleChange}
                placeholder="permits, checklists"
              />
            </fieldset>

            {pullStatus === "loading" || pullStatus === "polling" ? (
              <div className="upload-status upload-status-loading">
                {pullStatus === "loading"
                  ? "Starting pull…"
                  : `Pulling… ${pullJob?.processed_files ?? 0}/${pullJob?.total_files ?? "?"} files processed.`}
              </div>
            ) : null}

            {pullStatus === "error" && pullError ? (
              <div className="upload-status upload-status-error">{pullError}</div>
            ) : null}

            {pullJob?.files?.length ? (
              <table className="pull-results-table">
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Verdict</th>
                    <th>doc_id</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {pullJob.files.map((f) => (
                    <tr key={f.url}>
                      <td title={f.url}>{f.filename}</td>
                      <td>
                        {f.verdict}
                        {f.url_changed ? " ⚠ url changed" : ""}
                      </td>
                      <td>{f.doc_id ? <code>{f.doc_id}</code> : "—"}</td>
                      <td>{f.detail || ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}

            {pullStatus === "success" ? (
              <div className="upload-success">
                <h2>✅ Pull complete</h2>
                <p className="muted">
                  {pullJob?.total_files ?? 0} file(s) discovered on the page.
                  Rows marked <strong>flagged</strong> need human review.
                </p>
                <button type="button" onClick={handlePullReset}>Pull another page</button>
              </div>
            ) : (
              <div className="upload-actions">
                <button type="submit" disabled={!canPull}>
                  {pullStatus === "polling" ? "Pulling…" : "Pull"}
                </button>
              </div>
            )}
          </form>
        ) : null}

        {mode === "file" && status === "loading" ? (
          <div className="upload-status upload-status-loading">
            Upload in progress. Keep this page open until response returns.
          </div>
        ) : null}

        {mode === "file" && status === "error" && error ? (
          <div className="upload-status upload-status-error">{error}</div>
        ) : null}

        {mode === "file" ? (status === "success" && result ? (
          <div className="upload-success">
            <h2>✅ Upload accepted</h2>
            <dl className="result-dl">
              <dt>doc_id</dt>
              <dd><code>{result.doc_id}</code></dd>
              <dt>Status</dt>
              <dd>{result.status}</dd>
              <dt>Saved to</dt>
              <dd><code>{result.local_path}</code></dd>
              <dt>Next step</dt>
              <dd>
                Chunking and embedding are running in the background.
                Poll{" "}
                <a
                  href={`${API_BASE_URL}${API_PREFIX}/documents/${result.doc_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  /documents/{result.doc_id}
                </a>{" "}
                until <code>document_status</code> = <code>active</code>.
              </dd>
            </dl>
            <button type="button" onClick={handleReset}>Upload another</button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="form upload-form">

            {/* ── File picker ── */}
            <fieldset className="upload-fieldset">
              <legend>File</legend>
              <label htmlFor="upload-file">PDF or HTML file *</label>
              <input
                id="upload-file"
                type="file"
                accept=".pdf,.html,.htm"
                onChange={handleFileChange}
                required
              />
              {file && (
                <p className="muted upload-file-name">
                  Selected: <strong>{file.name}</strong> ({(file.size / 1024).toFixed(1)} KB)
                </p>
              )}
              {!file ? <p className="field-hint">Accepted: .pdf, .html, .htm</p> : null}
              {isNativePlatform() ? (
                <div className="mobile-upload-actions">
                  <button type="button" className="secondary-button" onClick={handleMobileCapture}>
                    Take photo
                  </button>
                  <button type="button" className="secondary-button" onClick={handleMobilePick}>
                    Pick from gallery
                  </button>
                </div>
              ) : null}
            </fieldset>

            {/* ── Identity ── */}
            <fieldset className="upload-fieldset">
              <legend>Identity</legend>

              <label htmlFor="doc_id">
                Document ID *{" "}
                <span className="field-hint">(unique slug, e.g. plano-pool-ordinance-2024)</span>
              </label>
              <input
                id="doc_id"
                name="doc_id"
                value={form.doc_id}
                onChange={handleChange}
                placeholder="plano-pool-ordinance-2024"
                pattern="[a-z0-9\-_]+"
                title="Lowercase alphanumeric, hyphens, underscores only"
                required
              />

              <label htmlFor="source_url">
                Source URL{" "}
                <span className="field-hint">(optional — where you obtained this document)</span>
              </label>
              <input
                id="source_url"
                name="source_url"
                type="url"
                value={form.source_url}
                onChange={handleChange}
                placeholder="https://www.plano.gov/..."
              />
            </fieldset>

            {/* ── Classification ── */}
            <fieldset className="upload-fieldset">
              <legend>Classification</legend>

              <div className="row">
                <div>
                  <label htmlFor="municipality">Municipality *</label>
                  <input
                    id="municipality"
                    name="municipality"
                    value={form.municipality}
                    onChange={handleChange}
                    placeholder="plano"
                    required
                  />
                  <p className="field-hint">
                    Must match an existing jurisdiction (dallas, plano, fortworth, texas, federal)
                    or a new one you're seeding.
                  </p>
                </div>

                <div>
                  <label htmlFor="authority_level">Authority Level *</label>
                  <select
                    id="authority_level"
                    name="authority_level"
                    value={form.authority_level}
                    onChange={handleChange}
                  >
                    {AUTHORITY_LEVELS.map((v) => (
                      <option key={v} value={v}>{v}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="row">
                <div>
                  <label htmlFor="doc_type">Document Type *</label>
                  <select
                    id="doc_type"
                    name="doc_type"
                    value={form.doc_type}
                    onChange={handleChange}
                  >
                    {DOC_TYPES.map((v) => (
                      <option key={v} value={v}>{v.replace(/_/g, " ")}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="source_tier">Source Tier *</label>
                  <select
                    id="source_tier"
                    name="source_tier"
                    value={form.source_tier}
                    onChange={handleChange}
                  >
                    {SOURCE_TIERS.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <label htmlFor="subject_tags">
                Subject Tags{" "}
                <span className="field-hint">(comma-separated, e.g. pools,setbacks,fences)</span>
              </label>
              <input
                id="subject_tags"
                name="subject_tags"
                value={form.subject_tags}
                onChange={handleChange}
                placeholder="pools, setbacks, fences"
              />

              {user && projects.length > 0 && (
                <div style={{ marginTop: "10px" }}>
                  <label htmlFor="projectId">Bind to Project Workspace (optional)</label>
                  <select
                    id="projectId"
                    name="project_id"
                    value={form.project_id || ""}
                    onChange={(e) => setForm(prev => ({ ...prev, project_id: e.target.value }))}
                  >
                    <option value="">-- No project (global document) --</option>
                    {projects.map(p => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                  <p className="field-hint">Bind this document specifically to one project workspace.</p>
                </div>
              )}
            </fieldset>

            {blockers.length ? (
              <div className="upload-checklist">
                <strong>Before upload:</strong>
                <ul>
                  {blockers.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="upload-ready">Ready to upload.</p>
            )}

            <div className="upload-actions">
              <button type="submit" disabled={!canSubmit}>
                {status === "loading" ? "Uploading…" : "Upload & Ingest"}
              </button>
            </div>
          </form>
        )) : null}
      </section>
    </main>
  );
}
