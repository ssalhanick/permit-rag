import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

/**
 * Frontend route guard for superadmin-only pages.
 *
 * The backend already enforces superadmin on every /admin/agents route
 * (api/routes/agents_admin.py); this guard is the missing frontend half — it
 * keeps a non-superadmin from ever rendering the dashboard shell. Unauthenticated
 * users go to /auth; signed-in non-superadmins get a plain 403 message rather
 * than a redirect loop.
 */
export default function SuperadminRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div style={{ padding: "2rem" }}>Loading…</div>;
  }
  if (!user) {
    return <Navigate to="/auth" state={{ from: location }} replace />;
  }
  if (user.role !== "superadmin") {
    return (
      <div style={{ padding: "2rem" }}>
        <h2>403 — Superadmin only</h2>
        <p>This dashboard is restricted to superadmins.</p>
      </div>
    );
  }
  return children;
}
