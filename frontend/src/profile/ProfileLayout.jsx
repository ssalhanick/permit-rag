import React, { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import {
  getProfilePageTitle,
  PROFILE_EXTERNAL_LINKS,
  PROFILE_NAV_ITEMS,
} from "./profileNavConfig.js";

/**
 * WordPress-style profile shell: fixed sidebar + nested subpage outlet.
 */
export default function ProfileLayout() {
  const { user } = useAuth();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const pageTitle = getProfilePageTitle(location.pathname);

  const closeSidebar = () => setSidebarOpen(false);

  if (!user) {
    return null;
  }

  const initials = (user.username || "U").slice(0, 2).toUpperCase();

  return (
    <div className="profile-dashboard-layout">
      {sidebarOpen && (
        <button
          type="button"
          className="profile-sidebar-backdrop"
          aria-label="Close profile menu"
          onClick={closeSidebar}
        />
      )}

      <aside
        className={`profile-sidebar${sidebarOpen ? " profile-sidebar--open" : ""}`}
        id="profile-sidebar"
        aria-label="Profile navigation"
      >
        <div className="profile-sidebar-user">
          <div className="profile-sidebar-avatar" aria-hidden="true">
            {initials}
          </div>
          <div className="profile-sidebar-user-meta">
            <strong>{user.username}</strong>
            <span className="profile-sidebar-role">
              {user.role === "admin" ? "Admin" : "Member"}
            </span>
          </div>
        </div>

        <nav className="profile-sidebar-nav">
          <p className="profile-sidebar-section-label">Profile</p>
          <ul>
            {PROFILE_NAV_ITEMS.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  end={item.end}
                  className={({ isActive }) =>
                    `profile-sidebar-link${isActive ? " profile-sidebar-link--active" : ""}`
                  }
                  onClick={closeSidebar}
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>

          <p className="profile-sidebar-section-label">App</p>
          <ul>
            {PROFILE_EXTERNAL_LINKS.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  className="profile-sidebar-link profile-sidebar-link--external"
                  onClick={closeSidebar}
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>

      <div className="profile-main">
        <header className="profile-main-header">
          <button
            type="button"
            className="profile-sidebar-toggle"
            aria-expanded={sidebarOpen}
            aria-controls="profile-sidebar"
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
