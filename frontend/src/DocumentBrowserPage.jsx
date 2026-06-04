import React, { useEffect, useMemo, useState } from "react";
import { fetchDocuments, fetchDocumentStatus } from "./api.js";

const DEFAULT_FILTERS = {
  municipality: "",
  status: "",
  authority: "",
  doc_type: "",
};

export default function DocumentBrowserPage() {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [rows, setRows] = useState([]);
  const [statusBuckets, setStatusBuckets] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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

  function handleChange(event) {
    const { name, value } = event.target;
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  function resetFilters() {
    setFilters(DEFAULT_FILTERS);
  }

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
