import React, { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useProject } from "./ProjectContext.jsx";
import { getProjectNavItems, getProjectPageTitle } from "./projectNavConfig.js";

/**
 * Project dashboard shell — sidebar + nested pages (like profile layout).
 */
export default function ProjectLayout() {
  const { project, loading, error } = useProject();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
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
    <div className="profile-dashboard-layout project-dashboard-layout">
      {sidebarOpen && (
        <button
          type="button"
          className="profile-sidebar-backdrop"
          aria-label="Close project menu"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={`profile-sidebar${sidebarOpen ? " profile-sidebar--open" : ""}`}
        aria-label="Project navigation"
      >
        <div className="profile-sidebar-user">
          <div className="profile-sidebar-avatar" aria-hidden="true">
            {(project.name || "P").slice(0, 2).toUpperCase()}
          </div>
          <div className="profile-sidebar-user-meta">
            <strong>{project.name}</strong>
            <span className="profile-sidebar-role">{project.municipality || "No jurisdiction"}</span>
          </div>
        </div>

        <nav className="profile-sidebar-nav">
          <p className="profile-sidebar-section-label">Project</p>
          <ul>
            {navItems.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  end={item.end}
                  className={({ isActive }) =>
                    `profile-sidebar-link${isActive ? " profile-sidebar-link--active" : ""}`
                  }
                  onClick={() => setSidebarOpen(false)}
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
          <p className="profile-sidebar-section-label">App</p>
          <ul>
            <li>
              <NavLink to="/projects" className="profile-sidebar-link" onClick={() => setSidebarOpen(false)}>
                All Projects
              </NavLink>
            </li>
            <li>
              <NavLink to="/" className="profile-sidebar-link" onClick={() => setSidebarOpen(false)}>
                New Query
              </NavLink>
            </li>
            <li>
              <NavLink to="/profile/room-scans" className="profile-sidebar-link" onClick={() => setSidebarOpen(false)}>
                My Scan Library
              </NavLink>
            </li>
          </ul>
        </nav>
      </aside>

      <div className="profile-main">
        <header className="profile-main-header">
          <button
            type="button"
            className="profile-sidebar-toggle"
            aria-expanded={sidebarOpen}
            onClick={() => setSidebarOpen((open) => !open)}
          >
            Menu
          </button>
          <h1>{pageTitle}</h1>
        </header>
        <div className="profile-main-content">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
