import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import { buildKickoffPath } from "./projectKickoffRoutes.js";
import { createProject, fetchProjects } from "./api.js";

/**
 * Project list — select a project to open its dashboard workspace.
 */
export default function ProjectsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedProjectId = searchParams.get("projectId");
  const [projects, setProjects] = useState([]);
  const [newProjForm, setNewProjForm] = useState({ name: "", description: "", municipality: "" });
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadProjects = async () => {
    if (!user) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await fetchProjects();
      setProjects(res.data || []);
    } catch (err) {
      setError(err.message || "Failed to load projects.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, [user]);

  useEffect(() => {
    if (requestedProjectId) {
      navigate(`/projects/${requestedProjectId}/dashboard`, { replace: true });
    }
  }, [requestedProjectId, navigate]);

  const openProject = (projectId) => {
    navigate(`/projects/${projectId}/dashboard`);
  };

  const handleCreateProject = async (e) => {
    e.preventDefault();
    setActionLoading(true);
    setError("");
    setSuccess("");
    try {
      const res = await createProject({
        name: newProjForm.name,
        description: newProjForm.description || null,
        municipality: newProjForm.municipality || null,
      });
      setNewProjForm({ name: "", description: "", municipality: "" });
      setSuccess(`Project "${res.data.name}" created.`);
      await loadProjects();
      navigate(`/projects/${res.data.id}/dashboard`);
    } catch (err) {
      setError(err.message || "Failed to create project.");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <main className="page project-page">
      <div className="project-list-page">
        <header className="project-list-header">
          <div>
            <h1>Projects</h1>
            <p className="muted">
              Each project has its own dashboard — query history, linked room scans, documents, and collaborators.
            </p>
          </div>
          <Link to="/profile/room-scans" className="secondary-button">
            My scan library
          </Link>
        </header>

        {error && <div className="error-box">{error}</div>}
        {success && <div className="success-box">{success}</div>}

        <div className="project-grid project-grid--list-only">
          <section className="panel project-list-panel">
            <h3>My projects</h3>
            {loading && <p>Loading projects…</p>}
            {!loading && projects.length === 0 && <p className="muted">No projects yet.</p>}
            <ul className="project-list-items">
              {projects.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    className="project-list-item-btn"
                    onClick={() => openProject(p.id)}
                  >
                    <span className="project-list-item-text">
                      <strong>{p.name}</strong>
                      {p.address && <span className="kickoff-project-address">{p.address}</span>}
                    </span>
                    {p.municipality && <span className="muni-badge">{p.municipality}</span>}
                  </button>
                </li>
              ))}
            </ul>

            <section className="project-kickoff-entry" aria-label="Guided project setup">
              <h4>Guided setup</h4>
              <p className="muted project-kickoff-entry-copy">
                Walk through address, spaces, work types, and permit guidance.
              </p>
              <Link
                to={buildKickoffPath({ mode: "wizard", returnTo: "/projects" })}
                className="secondary-button project-kickoff-entry-btn"
              >
                Start guided setup
              </Link>
            </section>
          </section>

          <section className="panel">
            <h3>New project</h3>
            <form onSubmit={handleCreateProject} className="form mini-form">
              <div>
                <label htmlFor="projName">Project name</label>
                <input
                  id="projName"
                  value={newProjForm.name}
                  onChange={(e) => setNewProjForm({ ...newProjForm, name: e.target.value })}
                  placeholder="e.g. Backyard pool"
                  required
                />
              </div>
              <div>
                <label htmlFor="projDesc">Description</label>
                <textarea
                  id="projDesc"
                  rows={2}
                  value={newProjForm.description}
                  onChange={(e) => setNewProjForm({ ...newProjForm, description: e.target.value })}
                  placeholder="Brief summary…"
                />
              </div>
              <div>
                <label htmlFor="projMuni">Default municipality</label>
                <input
                  id="projMuni"
                  value={newProjForm.municipality}
                  onChange={(e) => setNewProjForm({ ...newProjForm, municipality: e.target.value })}
                  placeholder="e.g. dallas"
                />
              </div>
              <button type="submit" disabled={actionLoading} className="primary-button">
                Create project
              </button>
            </form>
          </section>
        </div>
      </div>
    </main>
  );
}
