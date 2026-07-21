import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import { buildKickoffPath } from "./projectKickoffRoutes.js";
import { createProject, fetchProjects } from "./api.js";

/**
 * Project list — searchable/filterable, select a project to open its dashboard
 * workspace, or set it as the active project from the nav.
 */
export default function ProjectsPage() {
  const { user, activeProject, setActiveProject } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedProjectId = searchParams.get("projectId");
  const [projects, setProjects] = useState([]);
  const [newProjForm, setNewProjForm] = useState({ name: "", description: "", municipality: "" });
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [statusFilter, setStatusFilter] = useState("ongoing");
  const [search, setSearch] = useState("");
  const [hasRoomScans, setHasRoomScans] = useState(false);

  const loadProjects = async () => {
    if (!user) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await fetchProjects({
        status: statusFilter === "all" ? undefined : statusFilter,
        search: search || undefined,
        hasRoomScans: hasRoomScans || undefined,
      });
      setProjects(res.data || []);
    } catch (err) {
      setError(err.message || "Failed to load projects.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, [user, statusFilter, search, hasRoomScans]);

  const handleSetActive = async (e, projectId) => {
    e.stopPropagation();
    try {
      await setActiveProject(projectId);
    } catch (err) {
      setError(err.message || "Failed to set active project.");
    }
  };

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
          <div className="flex items-center gap-2">
            <Link to="/projects/trash" className="secondary-button">
              Recently deleted
            </Link>
            <Link to="/profile/room-scans" className="secondary-button">
              My scan library
            </Link>
          </div>
        </header>

        {error && <div className="error-box">{error}</div>}
        {success && <div className="success-box">{success}</div>}

        <div className="project-grid project-grid--list-only">
          <section className="panel project-list-panel">
            <h3>My projects</h3>

            <div className="mb-3 flex flex-wrap items-center gap-2">
              <div className="flex rounded-md border border-slate-700" role="tablist" aria-label="Status filter">
                {["ongoing", "archived", "all"].map((s) => (
                  <button
                    key={s}
                    type="button"
                    role="tab"
                    aria-selected={statusFilter === s}
                    onClick={() => setStatusFilter(s)}
                    className={`px-3 py-1.5 text-sm capitalize ${
                      statusFilter === s ? "bg-slate-700 text-slate-100" : "text-slate-400"
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search name, address, municipality…"
                className="min-w-[220px] flex-1 rounded border border-slate-600 bg-slate-800 px-2 py-1.5 text-sm text-slate-100"
              />
              <label className="flex items-center gap-1.5 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={hasRoomScans}
                  onChange={(e) => setHasRoomScans(e.target.checked)}
                />
                Has room scans
              </label>
            </div>

            {loading && <p>Loading projects…</p>}
            {!loading && projects.length === 0 && <p className="muted">No matching projects.</p>}
            <ul className="project-list-items">
              {projects.map((p) => (
                <li key={p.id} className="flex items-center gap-2">
                  <button
                    type="button"
                    className="project-list-item-btn flex-1"
                    onClick={() => openProject(p.id)}
                  >
                    <span className="project-list-item-text">
                      <strong>{p.name}</strong>
                      {p.address && <span className="kickoff-project-address">{p.address}</span>}
                    </span>
                    <span className="flex items-center gap-2">
                      {p.municipality && <span className="muni-badge">{p.municipality}</span>}
                      <span className={`muni-badge ${p.is_archived ? "opacity-60" : ""}`}>
                        {p.is_archived ? "Archived" : "Ongoing"}
                      </span>
                    </span>
                  </button>
                  {activeProject?.id === p.id ? (
                    <span className="muni-badge bg-sky-700 text-slate-100">Active</span>
                  ) : (
                    <button
                      type="button"
                      className="text-button"
                      onClick={(e) => handleSetActive(e, p.id)}
                    >
                      Set active
                    </button>
                  )}
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
