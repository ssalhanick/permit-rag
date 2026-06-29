import React from "react";
import { Link } from "react-router-dom";

const QUICK_LINKS = [
  {
    title: "Run a query",
    description: "Search municipal codes and get cited answers.",
    path: "/",
  },
  {
    title: "Query history",
    description: "Review and reload past searches.",
    path: "/profile/history",
  },
  {
    title: "My documents",
    description: "Manage uploads and share to projects.",
    path: "/profile/documents",
  },
  {
    title: "Projects",
    description: "Open workspaces and collaborators.",
    path: "/projects",
  },
];

/**
 * Profile home — quick links until Phase 2 stat widgets land.
 */
export default function ProfileDashboardPage() {
  return (
    <section className="panel profile-dashboard-home">
      <p className="muted">
        Welcome to your profile dashboard. Use the sidebar or the links below to manage
        your permit research activity.
      </p>

      <div className="profile-quick-links">
        {QUICK_LINKS.map((link) => (
          <Link key={link.path} to={link.path} className="profile-quick-link-card">
            <strong>{link.title}</strong>
            <span>{link.description}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
