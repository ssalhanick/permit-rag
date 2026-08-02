/**
 * useIsSuperAdmin.js
 * Single source of truth for "is the current user a superadmin" — was
 * previously two inconsistent ad hoc checks: Nav.jsx checked
 * `role === "superadmin" || is_superadmin`, SuperadminRoute.jsx checked only
 * `role !== "superadmin"`. Checking both field shapes here means either
 * backend response convention works everywhere this hook is used.
 */

import { useAuth } from "../context/AuthContext.jsx";

export function useIsSuperAdmin() {
  const { user } = useAuth();
  return Boolean(user?.role === "superadmin" || user?.is_superadmin);
}
