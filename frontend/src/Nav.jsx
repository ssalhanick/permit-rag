import React from "react";
import { NavLink } from "react-router-dom";

export default function Nav() {
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
        <NavLink
          to="/upload"
          className={({ isActive }) => "nav-link" + (isActive ? " nav-link-active" : "")}
        >
          Upload Document
        </NavLink>
      </div>
    </nav>
  );
}
