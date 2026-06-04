import React, { useState } from "react";
import { API_BASE_URL } from "./api.js";

const AUTHORITY_LEVELS = ["municipal", "state", "federal", "regional"];
const DOC_TYPES = [
  "building_code",
  "zoning_ordinance",
  "fire_code",
  "electrical_code",
  "plumbing_code",
  "mechanical_code",
  "energy_code",
  "accessibility_standard",
  "environmental_regulation",
  "licensing_requirement",
  "permit_guide",
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
};

export default function UploadPage() {
  const [form, setForm] = useState(DEFAULT_FORM);
  const [file, setFile] = useState(null);
  const [adminToken, setAdminToken] = useState("");
  const [status, setStatus] = useState(null); // null | 'loading' | 'success' | 'error'
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

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
    // Auto-suggest doc_id from filename if field is empty
    if (f && !form.doc_id) {
      const suggested = f.name
        .replace(/\.[^/.]+$/, "")        // strip extension
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")     // non-alnum → hyphen
        .replace(/^-+|-+$/g, "");        // trim leading/trailing hyphens
      setForm((prev) => ({ ...prev, doc_id: suggested }));
    }
  };

  const canSubmit =
    file &&
    form.doc_id.trim() &&
    form.municipality.trim() &&
    adminToken.trim() &&
    status !== "loading";

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

    try {
      const res = await fetch(`${API_BASE_URL}/admin/documents/upload`, {
        method: "POST",
        headers: { "X-Admin-Token": adminToken.trim() },
        body,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail || `HTTP ${res.status}`);
      }
      setResult(data);
      setStatus("success");
    } catch (err) {
      setError(err.message || "Upload failed.");
      setStatus("error");
    }
  };

  const handleReset = () => {
    setForm(DEFAULT_FORM);
    setFile(null);
    setAdminToken("");
    setStatus(null);
    setResult(null);
    setError("");
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

        {status === "success" && result ? (
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
                  href={`${API_BASE_URL}/documents/${result.doc_id}`}
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
            </fieldset>

            {/* ── Auth ── */}
            <fieldset className="upload-fieldset">
              <legend>Admin Auth</legend>
              <label htmlFor="admin-token">X-Admin-Token *</label>
              <input
                id="admin-token"
                type="password"
                value={adminToken}
                onChange={(e) => setAdminToken(e.target.value)}
                placeholder="Your API_ADMIN_TOKEN value"
                required
              />
            </fieldset>

            {error && <p className="error">{error}</p>}

            <div className="upload-actions">
              <button type="submit" disabled={!canSubmit}>
                {status === "loading" ? "Uploading…" : "Upload & Ingest"}
              </button>
            </div>
          </form>
        )}
      </section>
    </main>
  );
}
