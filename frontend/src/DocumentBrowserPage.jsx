import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchDocuments, fetchDocumentStatus, fetchProjects, shareDocumentToProject } from "./api.js";
import { useAuth } from "./context/AuthContext.jsx";

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

  const activeFilterCount = useMemo(() => {
    return Object.values(filters).filter((value) => value.trim().length > 0).length;
  }, [filters]);

  useEffect(() => {
    async function loadDocuments() {
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
    }
    loadDocuments();
  }, [filters]);

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

        {error ? <p className="error">{error}</p> : null}
        {shareSuccess && <div className="success-box" style={{ marginTop: "10px" }}>{shareSuccess}</div>}
        {shareError && <div className="error-box" style={{ marginTop: "10px" }}>{shareError}</div>}
      </section>

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
                      {user && projects.length > 0 ? (
                        <select 
                          value="" 
                          onChange={(e) => handleShare(row.id, e.target.value)}
                          style={{ width: "auto", fontSize: "0.8rem", padding: "2px 6px" }}
                        >
                          <option value="">Share with project...</option>
                          {projects.map(p => (
                            <option key={p.id} value={p.id}>{p.name}</option>
                          ))}
                        </select>
                      ) : user ? (
                        <span className="muted" style={{ fontSize: "0.8rem" }}>No projects</span>
                      ) : (
                        <span className="muted" style={{ fontSize: "0.8rem" }}>Sign in to share</span>
                      )}
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
