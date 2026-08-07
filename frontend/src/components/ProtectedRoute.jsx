import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  // Session restore (Cognito + /auth/me) is still in flight on a hard/direct
  // navigation — user starts null until it resolves, so don't redirect yet.
  if (loading) {
    return null;
  }

  if (!user) {
    // Redirect to /auth, but save the current location they were trying to go to
    return <Navigate to="/auth" state={{ from: location }} replace />;
  }

  return children;
}
