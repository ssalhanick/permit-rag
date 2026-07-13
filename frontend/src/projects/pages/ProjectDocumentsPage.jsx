import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchProjectDocuments } from "../../api.js";
import { useProject } from "../ProjectContext.jsx";

/**
 * Regulatory documents bound to this project workspace.
 */
export default function ProjectDocumentsPage() {
  const { projectId } = useProject();
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError("");
      try {
        const res = await fetchProjectDocuments(projectId);
        setDocs(res.data || []);
      } catch (err) {
        setError(err.message || "Failed to load documents.");
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId]);

  return (
    <div className="project-documents-page">
      {error && <div className="error-box">{error}</div>}

      <section className="panel">
        <p className="muted">
          These regulatory documents are bound to this project workspace. Share more from the{" "}
          <Link to="/documents">document browser</Link>.
        </p>

        {loading ? (
          <p>Loading documents…</p>
        ) : docs.length === 0 ? (
          <p className="muted">No documents shared yet.</p>
        ) : (
          <div className="doc-table-wrap">
            <table className="doc-table">
              <thead>
                <tr>
                  <th>Doc ID</th>
                  <th>Municipality</th>
                  <th>Status</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <tr key={d.id}>
                    <td><strong>{d.doc_id}</strong></td>
                    <td>{d.municipality}</td>
                    <td>{d.document_status}</td>
                    <td>{d.doc_type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
