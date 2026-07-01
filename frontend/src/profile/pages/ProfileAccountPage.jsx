import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";

/**
 * Read-only account details from JWT until GET /auth/me lands in Phase 3.
 */
export default function ProfileAccountPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");
  const [loggingOutAll, setLoggingOutAll] = useState(false);

  const userId = user?.id || user?.user_id;

  const handleLogoutAll = async () => {
    if (!window.confirm("Log out from all devices? You will need to sign in again.")) {
      return;
    }
    setLoggingOutAll(true);
    setActionError("");
    setActionSuccess("");
    try {
      await logout();
      navigate("/auth");
    } catch (err) {
      setActionError(`Logout failed: ${err.message}`);
    } finally {
      setLoggingOutAll(false);
    }
  };

  return (
    <section className="panel profile-account-panel">
      <p className="muted">
        Account details come from your session token. Email and phone editing arrive in a later
        sprint.
      </p>

      {actionError && (
        <div className="profile-flash profile-flash--error">{actionError}</div>
      )}
      {actionSuccess && (
        <div className="profile-flash profile-flash--success">{actionSuccess}</div>
      )}

      <dl className="profile-account-details">
        <div>
          <dt>Username</dt>
          <dd>{user?.username}</dd>
        </div>
        <div>
          <dt>Role</dt>
          <dd>{user?.role === "admin" ? "Admin" : "Member"}</dd>
        </div>
        <div>
          <dt>User ID</dt>
          <dd>
            <code>{userId}</code>
          </dd>
        </div>
      </dl>

      <div className="profile-account-actions">
        <button
          type="button"
          className="secondary-button profile-btn-danger"
          disabled={loggingOutAll}
          onClick={handleLogoutAll}
        >
          {loggingOutAll ? "Logging out..." : "Log out all devices"}
        </button>
      </div>
    </section>
  );
}
