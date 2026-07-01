import React, { useState } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";

export default function Nav() {
  const { user, logout } = useAuth();
  const [isOpen, setIsOpen] = useState(false);

  const toggleMenu = () => setIsOpen(!isOpen);
  const closeMenu = () => setIsOpen(false);

  return (
    <nav className={`site-nav ${isOpen ? "site-nav-open" : ""}`}>
      <div className="site-nav-header">
        <span className="site-nav-brand">permit_rag</span>
        <button
          type="button"
          className="nav-mobile-toggle"
          onClick={toggleMenu}
          aria-label="Toggle navigation"
          aria-expanded={isOpen}
        >
          {isOpen ? "✕" : "☰"}
        </button>
      </div>

      <div className={`site-nav-collapse ${isOpen ? "show" : ""}`}>
        <div className="site-nav-links">
          <NavLink
            to="/"
            className={({ isActive }) => "nav-link" + (isActive ? " nav-link-active" : "")}
            onClick={closeMenu}
            end
          >
            Query
          </NavLink>
          {user && (
            <>
              <NavLink
                to="/upload"
                className={({ isActive }) => "nav-link" + (isActive ? " nav-link-active" : "")}
                onClick={closeMenu}
              >
                Upload Document
              </NavLink>
              <NavLink
                to="/profile"
                className={({ isActive }) => "nav-link" + (isActive ? " nav-link-active" : "")}
                onClick={closeMenu}
              >
                Profile
              </NavLink>
            </>
          )}
        </div>
        
        <div className="site-nav-auth">
          {user ? (
            <>
              <span className="site-nav-user-info">
                Logged in as <NavLink to="/profile" onClick={closeMenu} className="site-nav-username">{user.username}</NavLink>
              </span>
              <button
                type="button"
                onClick={() => {
                  logout();
                  closeMenu();
                }}
                className="secondary-button nav-signout-btn"
              >
                Sign Out
              </button>
            </>
          ) : (
            <NavLink to="/auth" onClick={closeMenu} className="nav-link nav-link-active nav-signin-link">
              Sign In
            </NavLink>
          )}
        </div>
      </div>
    </nav>
  );
}
