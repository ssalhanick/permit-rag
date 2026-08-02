import React, { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { Camera, CheckSquare, ChevronDown, Sparkles } from "lucide-react";
import { useProject } from "./ProjectContext.jsx";
import { getProjectNavItems, getProjectPageTitle } from "./projectNavConfig.js";

/**
 * Grouped quick-action button for the project header: "New Query" is the
 * primary/default click target, with "New Scan" and "New Task" tucked under
 * a caret dropdown. Replaces the standalone "New Query" tab that used to
 * live in the tab strip below.
 */
function ProjectQuickActions({ projectId }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="project-quick-actions" ref={containerRef}>
      <Link
        to={`/query?p=${projectId}`}
        className="project-quick-actions-primary"
        onClick={() => setOpen(false)}
      >
        <Sparkles className="w-3.5 h-3.5" />
        New Query
      </Link>
      <button
        type="button"
        className="project-quick-actions-caret"
        aria-label="More quick actions"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((v) => !v)}
      >
        <ChevronDown className="w-3.5 h-3.5" />
      </button>
      {open && (
        <div className="project-quick-actions-menu" role="menu">
          <Link
            to={`/projects/${projectId}/scans`}
            className="project-quick-actions-item"
            role="menuitem"
            onClick={() => setOpen(false)}
          >
            <Camera className="w-3.5 h-3.5" />
            New Scan
          </Link>
          <Link
            to="/tasks"
            className="project-quick-actions-item"
            role="menuitem"
            onClick={() => setOpen(false)}
          >
            <CheckSquare className="w-3.5 h-3.5" />
            New Task
          </Link>
        </div>
      )}
    </div>
  );
}

/**
 * Project dashboard shell — persistent tab strip + nested pages. Global/
 * account nav lives in the top Nav hamburger; this only ever shows nav
 * scoped to the current project, always visible, no toggle needed.
 */
export default function ProjectLayout() {
  const { project, loading, error } = useProject();
  const location = useLocation();
  const pageTitle = getProjectPageTitle(location.pathname);
  const navItems = project ? getProjectNavItems(project.id) : [];

  if (loading) {
    return (
      <main className="page">
        <p>Loading project…</p>
      </main>
    );
  }

  if (error || !project) {
    return (
      <main className="page">
        <p className="error-box">{error || "Project not found."}</p>
        <Link to="/projects" className="secondary-button">Back to projects</Link>
      </main>
    );
  }

  return (
    <div className="project-layout">
      <header className="project-layout-header">
        <div className="project-layout-title">
          <strong>{project.name}</strong>
          <ProjectQuickActions projectId={project.id} />
          <span className="project-layout-muni">{project.municipality || "No jurisdiction"}</span>
        </div>
        <h1>{pageTitle}</h1>
      </header>

      <nav className="project-tab-strip" aria-label="Project navigation">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.end}
            className={({ isActive }) => `project-tab${isActive ? " project-tab--active" : ""}`}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="project-layout-content">
        <Outlet />
      </div>
    </div>
  );
}
