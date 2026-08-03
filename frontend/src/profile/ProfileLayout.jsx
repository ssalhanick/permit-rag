import React, { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import {
  getProfilePageTitle,
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

        <nav className="profile-sidebar-nav space-y-1">
          <p className="profile-sidebar-section-label text-[11px] font-extrabold uppercase tracking-widest text-slate-400 mb-2 px-3">
            Account Navigation
          </p>
          <ul className="space-y-1">
            {PROFILE_NAV_ITEMS.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  end={item.end}
                  className={({ isActive }) =>
                    `profile-sidebar-link flex items-center px-3 py-2.5 rounded-xl font-medium text-xs transition-colors ${
                      isActive
                        ? "profile-sidebar-link--active bg-blue-50 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400 font-bold"
                        : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-200"
                    }`
                  }
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
