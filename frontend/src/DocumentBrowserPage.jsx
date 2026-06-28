import React, { useCallback, useEffect, useMemo, useState } from "react";
import { fetchDocuments, fetchDocumentStatus, fetchProjects, shareDocumentToProject } from "./api.js";
import { useAuth } from "./context/AuthContext.jsx";
import DocumentAdminPanel from "./components/DocumentAdminPanel.jsx";
import { getStoredAdminToken, setStoredAdminToken } from "./documentAdminUtils.js";

const DEFAULT_FILTERS = {
  municipality: "",
  status: "",
  authority: "",
  doc_type: "",
};

export default function DocumentBrowserPage() {
  const { user } = useAuth();
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [rows, setRows] = useState([]);
  const [statusBuckets, setStatusBuckets] = useState([]);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [shareSuccess, setShareSuccess] = useState("");
  const [shareError, setShareError] = useState("");
  const [adminToken, setAdminToken] = useState(() => getStoredAdminToken());
  const [showAdminSection, setShowAdminSection] = useState(false);
  const [editingDocId, setEditingDocId] = useState(null);

  const activeFilterCount = useMemo(() => {
    return Object.values(filters).filter((value) => value.trim().length > 0).length;
  }, [filters]);

  const candidateDocIds = useMemo(() => rows.map((row) => row.doc_id), [rows]);

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [docsResult, statusResult] = await Promise.all([
        fetchDocuments(filters),
        fetchDocumentStatus(filters),
      ]);
      setRows(docsResult.data || []);
      setStatusBuckets(statusResult.data?.counts || []);
    } catch (requestError) {
      setError(requestError.message || "Failed to load documents.");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    if (user) {
      fetchProjects()
        .then((res) => setProjects(res.data || []))
        .catch(() => {});
    } else {
      setProjects([]);
    }
  }, [user]);

  function handleChange(event) {
    const { name, value } = event.target;
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  function resetFilters() {
    setFilters(DEFAULT_FILTERS);
  }

  function handleAdminTokenChange(event) {
    const value = event.target.value;
    setAdminToken(value);
    setStoredAdminToken(value);
  }

  const handleShare = async (docId, projId) => {
    if (!projId) return;
    setShareError("");
    setShareSuccess("");
    try {
      await shareDocumentToProject(projId, docId);
      setShareSuccess("Document shared with project successfully!");
      setTimeout(() => setShareSuccess(""), 3000);
    } catch (err) {
      setShareError(err.message || "Failed to share document.");
      setTimeout(() => setShareError(""), 3000);
    }
  };

  return (
    <main className="page">
      <section className="panel">
        <h1>Document Browser</h1>
        <p className="muted">Browse document metadata and status counts from API routes.</p>

        <div className="doc-filter-grid">
          <div>
            <label htmlFor="municipality">Municipality</label>
            <input id="municipality" name="municipality" value={filters.municipality} onChange={handleChange} />
          </div>
          <div>
            <label htmlFor="status">Status</label>
            <input id="status" name="status" value={filters.status} onChange={handleChange} />
          </div>
          <div>
            <label htmlFor="authority">Authority</label>
            <input id="authority" name="authority" value={filters.authority} onChange={handleChange} />
          </div>
          <div>
            <label htmlFor="doc_type">Doc Type</label>
            <input id="doc_type" name="doc_type" value={filters.doc_type} onChange={handleChange} />
          </div>
        </div>

        <div className="doc-actions">
          <button type="button" className="secondary-button" onClick={resetFilters} disabled={activeFilterCount === 0}>
            Clear filters
          </button>
          <span className="muted">
            {loading ? "Loading..." : `${rows.length} document(s), ${statusBuckets.length} status bucket(s)`}
          </span>
        </div>

        {user ? (
          <div className="doc-admin-token-section">
            <button
              type="button"
              className="secondary-button"
              onClick={() => setShowAdminSection((prev) => !prev)}
            >
              {showAdminSection ? "Hide admin actions" : "Admin actions"}
            </button>
            {showAdminSection ? (
              <div className="doc-admin-token-field">
                <label htmlFor="doc-admin-token">X-Admin-Token</label>
                <input
                  id="doc-admin-token"
                  type="password"
                  value={adminToken}
                  onChange={handleAdminTokenChange}
                  placeholder="Your API_ADMIN_TOKEN value"
                />
                <p className="field-hint muted">Required to save metadata or supersede documents.</p>
              </div>
            ) : null}
          </div>
        ) : null}

        {error ? <p className="error">{error}</p> : null}
        {shareSuccess && <div className="success-box" style={{ marginTop: "10px" }}>{shareSuccess}</div>}
        {shareError && <div className="error-box" style={{ marginTop: "10px" }}>{shareError}</div>}
      </section>

      {editingDocId ? (
        <DocumentAdminPanel
          docId={editingDocId}
          adminToken={adminToken}
          candidateDocIds={candidateDocIds}
          onClose={() => setEditingDocId(null)}
          onSaved={loadDocuments}
        />
      ) : null}

      <section className="panel">
        <h2>Status Summary</h2>
        {statusBuckets.length ? (
          <ul className="status-bucket-list">
            {statusBuckets.map((bucket) => (
              <li key={bucket.status}>
                <strong>{bucket.status}</strong>: {bucket.count}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No status data for current filter scope.</p>
        )}
      </section>

      <section className="panel">
        <h2>Documents</h2>
        {rows.length ? (
          <div className="doc-table-wrap">
            <table className="doc-table">
              <thead>
                <tr>
                  <th>doc_id</th>
                  <th>municipality</th>
                  <th>doc_type</th>
                  <th>authority</th>
                  <th>status</th>
                  <th>updated_at</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.doc_id}</td>
                    <td>{row.municipality}</td>
                    <td>{row.doc_type}</td>
                    <td>{row.authority_level}</td>
                    <td>{row.document_status}</td>
                    <td>{row.updated_at}</td>
                    <td>
                      <div className="doc-row-actions">
                        {user ? (
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => setEditingDocId(row.doc_id)}
                          >
                            Edit
                          </button>
                        ) : null}
                        {user && projects.length > 0 ? (
                          <select
                            value=""
                            onChange={(e) => handleShare(row.id, e.target.value)}
                            style={{ width: "auto", fontSize: "0.8rem", padding: "2px 6px" }}
                          >
                            <option value="">Share with project...</option>
                            {projects.map((p) => (
                              <option key={p.id} value={p.id}>{p.name}</option>
                            ))}
                          </select>
                        ) : user ? (
                          <span className="muted" style={{ fontSize: "0.8rem" }}>No projects</span>
                        ) : (
                          <span className="muted" style={{ fontSize: "0.8rem" }}>Sign in to share</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">No documents found for current filters.</p>
        )}
      </section>
    </main>
  );
}
