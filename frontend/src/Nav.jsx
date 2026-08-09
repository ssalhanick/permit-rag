import React, { useState, useRef, useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import { useIsSuperAdmin } from "./hooks/useIsSuperAdmin.js";
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
  ChevronDown,
  LogIn,
  ArrowRight,
  HardHat,
  UploadCloud,
  MapPin,
  Compass
} from "lucide-react";
import LogoSVG from "./components/LogoSVG.jsx";
import ProjectSwitcher from "./components/ProjectSwitcher.jsx";
import AiAssistantWidget from "./components/AiAssistantWidget.jsx";

export default function Nav() {
  const { user, logout } = useAuth();
  const location = useLocation();
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

  const isSuperAdmin = useIsSuperAdmin();

  return (
    <header className="tt-nav-wrapper">
      <nav className={`tt-site-nav ${isOpen ? "tt-site-nav-open" : ""}`}>
        {/* Brand Logo Header */}
        <div className="tt-nav-brand-section">
          {/* "/" redirects a signed-in user straight back to /dashboard (App.jsx)
              -- that makes the logo a dead click while signed in, so it points
              at /welcome instead, the always-reachable marketing page. */}
          <NavLink
            to={user ? "/welcome" : "/"}
            className="tt-nav-brand-link"
            aria-label="ToolTime Home"
            onClick={closeMenu}
          >
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
            {user && (
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
              </>
            )}

            {user && (
              <NavLink
                to="/coverage"
                className={({ isActive }) =>
                  `tt-btn-outline text-xs whitespace-nowrap shrink-0 ${
                    isActive ? "tt-btn-outline-active" : ""
                  }`
                }
                onClick={closeMenu}
              >
                <Compass className="w-3.5 h-3.5 mr-1.5 shrink-0" />
                <span>Coverage Map</span>
              </NavLink>
            )}
          </div>

          {/* User Profile / Auth Action Section */}
          <div className="tt-nav-user-section" ref={menuRef}>
            {user ? (
              <div className="tt-user-dropdown-container">
                {/* Desktop compact trigger pill (hidden on mobile, visible on desktop) */}
                <button
                  type="button"
                  className="tt-user-trigger-btn hidden min-[901px]:inline-flex"
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  aria-expanded={userMenuOpen}
                  aria-label="User Account Menu"
                >
                  <div className="tt-user-avatar">{initials}</div>
                  <span className="tt-user-name text-sm font-medium text-slate-200">
                    {username}
                  </span>
                  <Settings className="w-4 h-4 text-slate-400 hover:text-slate-200 transition-colors" />
                  <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${userMenuOpen ? "rotate-180" : ""}`} />
                </button>

                {/* Dropdown Mini Menu:
                    - On Desktop (min-width: 901px): renders as absolute popover when userMenuOpen is true.
                    - On Mobile (max-width: 900px): renders directly inline inside the mobile collapse drawer! */}
                <div className={`tt-user-dropdown-menu ${userMenuOpen ? "block" : "hidden min-[901px]:hidden"} min-[901px]:${userMenuOpen ? "block" : "hidden"} max-[900px]:block`}>
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
                    <ProjectSwitcher onSelect={closeMenu} />
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

                  <NavLink
                    to={user.has_contractor_profile ? "/contractor/dashboard" : "/contractor/onboarding"}
                    className="tt-dropdown-link"
                    onClick={closeMenu}
                  >
                    <HardHat className="w-4 h-4 text-slate-400" />
                    {user.has_contractor_profile ? "Contractor Dashboard" : "Become a Contractor"}
                  </NavLink>

                  {/* Superadmin Menu Items */}
                  <div className="tt-dropdown-divider" />
                  <div className="tt-dropdown-section-label">Administration & Resources</div>
                  <NavLink
                    to="/coverage"
                    className="tt-dropdown-link"
                    onClick={closeMenu}
                  >
                    <Compass className="w-4 h-4 text-blue-400" />
                    Coverage Map & GIS
                  </NavLink>

                  <NavLink
                    to="/documents"
                    className="tt-dropdown-link"
                    onClick={closeMenu}
                  >
                    <FileText className="w-4 h-4 text-slate-400" />
                    Document Corpus
                  </NavLink>

                  {isSuperAdmin && (
                    <NavLink
                      to="/upload"
                      className="tt-dropdown-link text-emerald-400 hover:text-emerald-300"
                      onClick={closeMenu}
                    >
                      <UploadCloud className="w-4 h-4 text-emerald-400" />
                      Upload Document
                    </NavLink>
                  )}

                  {isSuperAdmin && (
                    <NavLink
                      to="/admin/agents"
                      className="tt-dropdown-link text-emerald-400 hover:text-emerald-300"
                      onClick={closeMenu}
                    >
                      <ShieldCheck className="w-4 h-4 text-emerald-400" />
                      Agent Orchestration
                    </NavLink>
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
              </div>
            ) : (
              <div className="flex flex-col min-[901px]:flex-row items-stretch min-[901px]:items-center gap-2.5 w-full min-[901px]:w-auto mt-3 min-[901px]:mt-0 pt-3 min-[901px]:pt-0 border-t min-[901px]:border-t-0 border-slate-800 shrink-0">
                {/* 1. Coverage Map (Outlined Button: 2px border, no background, accessible hover) */}
                <NavLink
                  to="/coverage"
                  className={({ isActive }) =>
                    `tt-btn-outline text-xs whitespace-nowrap shrink-0 w-full min-[901px]:w-auto ${
                      isActive ? "tt-btn-outline-active" : ""
                    }`
                  }
                  onClick={closeMenu}
                >
                  <Compass className="w-3.5 h-3.5 mr-1.5 shrink-0" />
                  <span>Coverage Map</span>
                </NavLink>

                {/* 2. Get Started (Primary CTA Button) */}
                <NavLink
                  to="/auth"
                  className="tt-btn-primary flex items-center justify-center gap-1.5 text-xs px-4 py-2 whitespace-nowrap shrink-0 w-full min-[901px]:w-auto"
                  onClick={closeMenu}
                >
                  <span>Get Started</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </NavLink>

                {/* 3. Sign In */}
                <NavLink
                  to="/auth"
                  className="tt-nav-item flex items-center justify-center gap-1.5 whitespace-nowrap shrink-0 w-full min-[901px]:w-auto text-xs"
                  onClick={closeMenu}
                >
                  <LogIn className="w-4 h-4 text-slate-400" />
                  <span>Sign In</span>
                </NavLink>
              </div>
            )}
          </div>
        </div>
      </nav>
      {/* Floating Corner AI Assistant Modal — hidden on /query, /kickoff, form pages (petitions),
          project settings, and project dashboard pages */}
      {(() => {
        const p = location.pathname;
        const isQuery = p === "/query";
        const isKickoff = p.startsWith("/kickoff");
        const isFormPage = p.includes("/petition") || p.includes("/petitions");
        const isSettingsPage = p.endsWith("/settings");
        const isDashboard = p === "/dashboard" || p.match(/\/projects\/[^/]+\/?(dashboard)?$/);
        if (isQuery || isKickoff || isFormPage || isSettingsPage || isDashboard) return null;
        return <AiAssistantWidget />;
      })()}
    </header>
  );
}
