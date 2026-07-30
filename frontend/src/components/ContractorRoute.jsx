import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

/**
 * Frontend route guard for contractor-only pages. Mirrors SuperadminRoute's
 * shape but gates on has_contractor_profile (a marketplace participant type)
 * rather than the staff-only role column.
 */
export default function ContractorRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div style={{ padding: "2rem" }}>Loading…</div>;
  }
  if (!user) {
    return <Navigate to="/auth" state={{ from: location }} replace />;
  }
  if (!user.has_contractor_profile) {
    return <Navigate to="/contractor/onboarding" replace />;
  }
  return children;
}
