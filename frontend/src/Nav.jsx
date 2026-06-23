import React from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";

export default function Nav() {
  const { user, logout } = useAuth();

  return (
    <nav className="site-nav">
      <span className="site-nav-brand">permit_rag</span>
      <div className="site-nav-links">
        <NavLink
          to="/"
          className={({ isActive }) => "nav-link" + (isActive ? " nav-link-active" : "")}
          end
        >
          Query
        </NavLink>
        {user && (
          <>
            <NavLink
              to="/upload"
              className={({ isActive }) => "nav-link" + (isActive ? " nav-link-active" : "")}
            >
              Upload Document
            </NavLink>
            <NavLink
              to="/documents"
              className={({ isActive }) => "nav-link" + (isActive ? " nav-link-active" : "")}
            >
              Documents
            </NavLink>
            <NavLink
              to="/projects"
              className={({ isActive }) => "nav-link" + (isActive ? " nav-link-active" : "")}
            >
              Projects
            </NavLink>
            <NavLink
              to="/profile"
              className={({ isActive }) => "nav-link" + (isActive ? " nav-link-active" : "")}
            >
              Profile
            </NavLink>
          </>
        )}
      </div>
      
      <div className="site-nav-auth" style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "12px" }}>
        {user ? (
          <>
            <span style={{ color: "#94a3b8", fontSize: "0.85rem" }}>
              Logged in as <NavLink to="/profile" style={{ color: "#3b82f6", textDecoration: "none", fontWeight: "bold" }}>{user.username}</NavLink>
            </span>
            <button
              type="button"
              onClick={logout}
              className="secondary-button"
              style={{
                padding: "4px 8px",
                fontSize: "0.8rem",
                cursor: "pointer",
                background: "#dc2626",
                border: "none",
                borderRadius: "4px",
                color: "#fff"
              }}
            >
              Sign Out
            </button>
          </>
        ) : (
          <NavLink to="/auth" className="nav-link nav-link-active" style={{ fontSize: "0.85rem", padding: "4px 10px" }}>
            Sign In
          </NavLink>
        )}
      </div>
    </nav>
  );
}
