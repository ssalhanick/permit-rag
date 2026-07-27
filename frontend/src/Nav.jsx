import React, { useState, useRef, useEffect } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import {
  LayoutDashboard,
  FolderKanban,
  CheckSquare,
  Sparkles,
  FileText,
  Settings,
  LogOut,
  ShieldCheck,
  User,
  History,
  Layers,
  ChevronDown
} from "lucide-react";
import LogoSVG from "./components/LogoSVG.jsx";
import ProjectSwitcher from "./components/ProjectSwitcher.jsx";

export default function Nav() {
  const { user, logout } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const menuRef = useRef(null);

  const toggleMenu = () => setIsOpen(!isOpen);
  const closeMenu = () => {
    setIsOpen(false);
    setUserMenuOpen(false);
  };

  // Close user menu popover on outside click
  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setUserMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const username = user?.username || user?.email?.split("@")[0] || "Alex Rivera";
  const userEmail = user?.email || `${username.toLowerCase().replace(/\s+/g, ".")}@home.io`;

  // Get user initials for avatar
  const initials = username
    .split(" ")
    .map((n) => n[0])
    .join("")
    .substring(0, 2)
    .toUpperCase();

  const isSuperAdmin = user?.role === "superadmin" || user?.is_superadmin;

  return (
    <header className="tt-nav-wrapper">
      <nav className={`tt-site-nav ${isOpen ? "tt-site-nav-open" : ""}`}>
        {/* Brand Logo Header */}
        <div className="tt-nav-brand-section">
          <NavLink to="/" className="tt-nav-brand-link" aria-label="ToolTime Home" onClick={closeMenu}>
            <LogoSVG className="nav-brand-logo nav-logo-themed" aria-hidden="true" />
          </NavLink>

          <button
            type="button"
            className="tt-nav-mobile-toggle"
            onClick={toggleMenu}
            aria-label="Toggle navigation"
            aria-expanded={isOpen}
          >
            {isOpen ? "✕" : "☰"}
          </button>
        </div>

        {/* Primary Navigation Bar (Information Architecture Streamlined) */}
        <div className={`tt-nav-collapse ${isOpen ? "tt-show" : ""}`}>
          <div className="tt-nav-links-group">
            {user ? (
              <>
                <NavLink
                  to="/dashboard"
                  className={({ isActive }) =>
                    `tt-nav-item ${isActive ? "tt-nav-item-active" : ""}`
                  }
                  onClick={closeMenu}
                >
                  <LayoutDashboard className="w-4 h-4 mr-1.5" />
                  Dashboard
                </NavLink>

                <NavLink
                  to="/projects"
                  className={({ isActive }) =>
                    `tt-nav-item ${isActive ? "tt-nav-item-active" : ""}`
                  }
                  onClick={closeMenu}
                >
                  <FolderKanban className="w-4 h-4 mr-1.5" />
                  Projects
                </NavLink>

                <NavLink
                  to="/tasks"
                  className={({ isActive }) =>
                    `tt-nav-item ${isActive ? "tt-nav-item-active" : ""}`
                  }
                  onClick={closeMenu}
                >
                  <CheckSquare className="w-4 h-4 mr-1.5" />
                  Tasks
                </NavLink>

                <NavLink
                  to="/query"
                  className={({ isActive }) =>
                    `tt-nav-item ${isActive ? "tt-nav-item-active" : ""}`
                  }
                  onClick={closeMenu}
                >
                  <Sparkles className="w-4 h-4 mr-1.5 text-cyan-400" />
                  AI Assistant
                </NavLink>

                <NavLink
                  to="/documents"
                  className={({ isActive }) =>
                    `tt-nav-item ${isActive ? "tt-nav-item-active" : ""}`
                  }
                  onClick={closeMenu}
                >
                  <FileText className="w-4 h-4 mr-1.5" />
                  Documents
                </NavLink>
              </>
            ) : null}
          </div>

          {/* User Profile Mini Menu Dropdown Trigger */}
          <div className="tt-nav-user-section" ref={menuRef}>
            {user ? (
              <div className="tt-user-dropdown-container">
                <button
                  type="button"
                  className="tt-user-trigger-btn"
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  aria-expanded={userMenuOpen}
                  aria-label="User Account Menu"
                >
                  <div className="tt-user-avatar">{initials}</div>
                  <span className="tt-user-name text-sm font-medium text-slate-200 hidden sm:inline">
                    {username}
                  </span>
                  <Settings className="w-4 h-4 text-slate-400 hover:text-slate-200 transition-colors" />
                  <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${userMenuOpen ? "rotate-180" : ""}`} />
                </button>

                {/* Dropdown Mini Menu */}
                {userMenuOpen && (
                  <div className="tt-user-dropdown-menu">
                    {/* Header */}
                    <div className="tt-dropdown-header">
                      <div className="tt-dropdown-avatar">{initials}</div>
                      <div className="tt-dropdown-user-info">
                        <span className="tt-dropdown-username">{username}</span>
                        <span className="tt-dropdown-email">{userEmail}</span>
                        {isSuperAdmin && (
                          <span className="inline-block mt-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-400 bg-emerald-950/80 border border-emerald-800/80 px-1.5 py-0.5 rounded">
                            Superadmin
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Active Project Switcher Section */}
                    <div className="mb-2 px-1">
                      <ProjectSwitcher onSelect={() => setUserMenuOpen(false)} />
                    </div>

                    <div className="tt-dropdown-divider" />

                    {/* Shortcuts */}
                    <div className="tt-dropdown-section-label">Account & Tools</div>
                    <NavLink
                      to="/profile"
                      className="tt-dropdown-link"
                      onClick={closeMenu}
                    >
                      <User className="w-4 h-4 text-slate-400" />
                      Profile & Account
                    </NavLink>

                    <NavLink
                      to="/profile/history"
                      className="tt-dropdown-link"
                      onClick={closeMenu}
                    >
                      <History className="w-4 h-4 text-slate-400" />
                      Query History
                    </NavLink>

                    <NavLink
                      to="/profile/room-scans"
                      className="tt-dropdown-link"
                      onClick={closeMenu}
                    >
                      <Layers className="w-4 h-4 text-slate-400" />
                      Room Scan Library
                    </NavLink>

                    {/* Superadmin Menu Items */}
                    {isSuperAdmin && (
                      <>
                        <div className="tt-dropdown-divider" />
                        <div className="tt-dropdown-section-label">Administration</div>
                        <NavLink
                          to="/admin/agents"
                          className="tt-dropdown-link text-emerald-400 hover:text-emerald-300"
                          onClick={closeMenu}
                        >
                          <ShieldCheck className="w-4 h-4 text-emerald-400" />
                          Agent Orchestration
                        </NavLink>
                      </>
                    )}

                    <div className="tt-dropdown-divider" />

                    {/* Sign Out */}
                    <button
                      type="button"
                      className="tt-dropdown-btn-signout"
                      onClick={() => {
                        logout();
                        closeMenu();
                      }}
                    >
                      <LogOut className="w-4 h-4" />
                      Sign Out
                    </button>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
      </nav>
    </header>
  );
}
