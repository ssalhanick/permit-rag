import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchDeletedProjects, hardDeleteProject, restoreProject } from "../../api.js";

/**
 * Recently deleted projects — restore, or permanently delete.
 */
export default function ProjectTrashPage() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetchDeletedProjects();
      setProjects(res.data || []);
    } catch (err) {
      setError(err.message || "Failed to load recently deleted projects.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleRestore = async (project) => {
    setActionLoading(true);
    setError("");
    try {
      await restoreProject(project.id);
      setSuccess(`Restored "${project.name}".`);
      await load();
    } catch (err) {
      setError(err.message || "Failed to restore project.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleHardDelete = async (project) => {
    if (
      !window.confirm(
        `Permanently delete "${project.name}"? This also deletes any documents uploaded only to this project. This cannot be undone.`
      )
    ) {
      return;
    }
    setActionLoading(true);
    setError("");
    try {
      await hardDeleteProject(project.id);
      setSuccess(`Permanently deleted "${project.name}".`);
      await load();
    } catch (err) {
      setError(err.message || "Failed to permanently delete project.");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <main className="page project-page">
      <div className="project-list-page">
        <header className="project-list-header">
          <div>
            <h1>Recently deleted</h1>
            <p className="muted">Soft-deleted projects. Room scans are kept — restore or permanently delete.</p>
          </div>
          <Link to="/projects" className="secondary-button">
            Back to projects
          </Link>
        </header>

        {error && <div className="error-box">{error}</div>}
        {success && <div className="success-box">{success}</div>}

        <section className="panel project-list-panel">
          {loading && <p>Loading…</p>}
          {!loading && projects.length === 0 && <p className="muted">Trash is empty.</p>}
          <ul className="project-list-items">
            {projects.map((p) => (
              <li key={p.id} className="flex items-center gap-2">
                <span className="project-list-item-text flex-1">
                  <strong>{p.name}</strong>
                  {p.address && <span className="kickoff-project-address">{p.address}</span>}
                </span>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={actionLoading}
                  onClick={() => handleRestore(p)}
                >
                  Restore
                </button>
                <button
                  type="button"
                  className="primary-button danger-button"
                  disabled={actionLoading}
                  onClick={() => handleHardDelete(p)}
                >
                  Permanently delete
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </main>
  );
}
