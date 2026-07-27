import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";
import { useTheme } from "../../context/ThemeContext.jsx";
import { Sun, Moon, Monitor } from "lucide-react";

export default function ProfileAccountPage() {
  const { user, logout } = useAuth();
  const { themeMode, setThemeMode, isDarkMode } = useTheme();
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
      <div className="mb-6 pb-6 border-b border-slate-200 dark:border-slate-800">
        <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-1">
          Appearance & Theme Preferences
        </h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
          ToolTime automatically adapts to your operating system theme preference by default, or you can manually override it below.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <button
            type="button"
            onClick={() => setThemeMode("system")}
            className={`p-3 rounded-xl border flex items-center justify-center gap-2 text-xs font-bold transition-all ${
              themeMode === "system"
                ? "border-blue-600 bg-blue-50 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-500 shadow-sm"
                : "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:border-slate-300"
            }`}
          >
            <Monitor className="w-4 h-4" />
            System Preference
          </button>

          <button
            type="button"
            onClick={() => setThemeMode("dark")}
            className={`p-3 rounded-xl border flex items-center justify-center gap-2 text-xs font-bold transition-all ${
              themeMode === "dark"
                ? "border-blue-600 bg-blue-50 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-500 shadow-sm"
                : "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:border-slate-300"
            }`}
          >
            <Moon className="w-4 h-4" />
            Dark Mode
          </button>

          <button
            type="button"
            onClick={() => setThemeMode("light")}
            className={`p-3 rounded-xl border flex items-center justify-center gap-2 text-xs font-bold transition-all ${
              themeMode === "light"
                ? "border-blue-600 bg-blue-50 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-500 shadow-sm"
                : "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:border-slate-300"
            }`}
          >
            <Sun className="w-4 h-4" />
            Light Mode
          </button>
        </div>

        <div className="mt-3 text-[11px] text-slate-500 dark:text-slate-400">
          Active theme: <strong className="text-slate-800 dark:text-slate-200">{isDarkMode ? "Dark Mode" : "Light Mode"}</strong> ({themeMode === "system" ? "Following System OS" : "Manual Preference"})
        </div>
      </div>

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

      <div className="profile-account-actions mt-6">
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
