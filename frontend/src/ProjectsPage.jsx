import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import { buildKickoffPath } from "./projectKickoffRoutes.js";
import { fetchProjects } from "./api.js";

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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
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

        <section className="panel project-kickoff-entry" aria-label="Add a project">
          <h3>Add a project</h3>
          <p className="muted project-kickoff-entry-copy">
            Walk through address, spaces, work types, and permit guidance.
          </p>
          <Link
            to={buildKickoffPath({ mode: "wizard", returnTo: "/projects" })}
            className="primary-button project-kickoff-entry-btn"
          >
            Start guided setup
          </Link>
          <Link
            to={buildKickoffPath({ mode: "basic", returnTo: "/projects" })}
            className="text-button project-kickoff-entry-link"
          >
            Prefer to enter details yourself? Manual setup
          </Link>
        </section>

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
        </section>
      </div>
    </main>
  );
}
