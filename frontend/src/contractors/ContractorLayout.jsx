import React, { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useContractor } from "./ContractorContext.jsx";
import { getContractorNavItems } from "./contractorNavConfig.js";

/**
 * Contractor dashboard shell — sidebar + nested pages, mirrors ProjectLayout.
 */
export default function ContractorLayout() {
  const { profile, loading, error } = useContractor();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navItems = getContractorNavItems();

  if (loading) {
    return (
      <main className="page">
        <p>Loading contractor profile…</p>
      </main>
    );
  }

  if (error || !profile) {
    return (
      <main className="page">
        <p className="error-box">{error || "Contractor profile not found."}</p>
      </main>
    );
  }

  return (
    <div className="profile-dashboard-layout project-dashboard-layout">
      {sidebarOpen && (
        <button
          type="button"
          className="profile-sidebar-backdrop"
          aria-label="Close contractor menu"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={`profile-sidebar${sidebarOpen ? " profile-sidebar--open" : ""}`}
        aria-label="Contractor navigation"
      >
        <div className="profile-sidebar-user">
          <div className="profile-sidebar-avatar" aria-hidden="true">
            {(profile.business_name || "C").slice(0, 2).toUpperCase()}
          </div>
          <div className="profile-sidebar-user-meta">
            <strong>{profile.business_name}</strong>
            <span className="profile-sidebar-role">
              {(profile.trades || []).join(", ") || "No trades listed"}
            </span>
          </div>
        </div>

        <nav className="profile-sidebar-nav">
          <p className="profile-sidebar-section-label">Contractor</p>
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
                My Projects
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
          <h1>Contractor</h1>
        </header>
        <div className="profile-main-content">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
