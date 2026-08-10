import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";
import { useTheme } from "../../context/ThemeContext.jsx";
import { Sun, Moon, Monitor, Camera, Trash2 } from "lucide-react";
import Avatar from "../../components/Avatar.jsx";
import { deleteMyAvatar, updateMe, uploadMyAvatar } from "../../api.js";
import { AVATAR_ACCEPT, resizeImageToSquare } from "../../avatarUtils.js";

export default function ProfileAccountPage() {
  const { user, logout, refreshUser } = useAuth();
  const { themeMode, setThemeMode, isDarkMode } = useTheme();
  const navigate = useNavigate();
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");
  const [loggingOutAll, setLoggingOutAll] = useState(false);

  const [username, setUsername] = useState(user?.username || "");
  const [usernameError, setUsernameError] = useState("");
  const [savingUsername, setSavingUsername] = useState(false);

  const fileInputRef = useRef(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoError, setPhotoError] = useState("");

  // Keep the field in step with the profile when it loads or is refreshed
  // elsewhere, so the input never shows a stale name.
  useEffect(() => {
    setUsername(user?.username || "");
  }, [user?.username]);

  const userId = user?.id || user?.user_id;
  const usernameChanged =
    username.trim().toLowerCase() !== (user?.username || "").toLowerCase();

  const handleSaveUsername = async (event) => {
    event.preventDefault();
    const next = username.trim().toLowerCase();
    setUsernameError("");
    setActionSuccess("");
    if (!next || next === user?.username) {
      return;
    }
    setSavingUsername(true);
    try {
      await updateMe({ username: next });
      await refreshUser();
      setUsername(next);
      setActionSuccess("Username updated.");
    } catch (err) {
      // 409 is the UNIQUE index rejecting a taken name — a normal outcome
      // worth phrasing as guidance, not as a failure.
      setUsernameError(
        err?.meta?.status === 409
          ? "That username is already taken. Try another."
          : err.message || "Could not update username.",
      );
    } finally {
      setSavingUsername(false);
    }
  };

  const handlePhotoSelected = async (event) => {
    const file = event.target.files?.[0];
    // Clear immediately so re-picking the same file still fires a change event.
    event.target.value = "";
    if (!file) {
      return;
    }
    setPhotoError("");
    setActionSuccess("");
    setPhotoBusy(true);
    try {
      // Resize before upload: bounds the request to ~20 KB, strips EXIF
      // (including GPS), and converts HEIC to something every browser renders.
      const resized = await resizeImageToSquare(file);
      await uploadMyAvatar(resized);
      await refreshUser();
      setActionSuccess("Profile photo updated.");
    } catch (err) {
      setPhotoError(err.message || "Could not upload that photo.");
    } finally {
      setPhotoBusy(false);
    }
  };

  const handleRemovePhoto = async () => {
    setPhotoError("");
    setActionSuccess("");
    setPhotoBusy(true);
    try {
      await deleteMyAvatar();
      await refreshUser();
      setActionSuccess("Profile photo removed.");
    } catch (err) {
      setPhotoError(err.message || "Could not remove that photo.");
    } finally {
      setPhotoBusy(false);
    }
  };

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

      <div className="mb-6 pb-6 border-b border-slate-200 dark:border-slate-800">
        <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-1">
          Profile Photo
        </h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
          Shown next to your name across ToolTime. JPG, PNG, or HEIC — we resize
          it to a 256px square in your browser before it's uploaded.
        </p>

        <div className="flex items-center gap-4">
          <Avatar user={user} className="profile-sidebar-avatar" />

          <div className="flex flex-wrap gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept={AVATAR_ACCEPT}
              className="hidden"
              onChange={handlePhotoSelected}
            />
            <button
              type="button"
              className="secondary-button inline-flex items-center gap-1.5"
              disabled={photoBusy}
              onClick={() => fileInputRef.current?.click()}
            >
              <Camera className="w-4 h-4" />
              {photoBusy
                ? "Working..."
                : user?.avatar_updated_at
                  ? "Change photo"
                  : "Upload photo"}
            </button>
            {user?.avatar_updated_at && (
              <button
                type="button"
                className="secondary-button profile-btn-danger inline-flex items-center gap-1.5"
                disabled={photoBusy}
                onClick={handleRemovePhoto}
              >
                <Trash2 className="w-4 h-4" />
                Remove
              </button>
            )}
          </div>
        </div>

        {photoError && (
          <div className="profile-flash profile-flash--error mt-3">{photoError}</div>
        )}
      </div>

      <form onSubmit={handleSaveUsername} className="mb-6 pb-6 border-b border-slate-200 dark:border-slate-800">
        <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-1">
          Username
        </h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
          Lowercase letters, numbers, and <code>_ . -</code> only. You'll still
          sign in with your email address.
        </p>

        <div className="flex flex-wrap items-start gap-2">
          <div className="flex-1 min-w-[200px]">
            <label htmlFor="profile-username" className="sr-only">
              Username
            </label>
            <input
              id="profile-username"
              type="text"
              className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-slate-100"
              value={username}
              minLength={3}
              maxLength={30}
              autoComplete="username"
              aria-invalid={usernameError ? "true" : undefined}
              aria-describedby={usernameError ? "profile-username-error" : undefined}
              onChange={(e) => {
                setUsername(e.target.value);
                setUsernameError("");
              }}
            />
          </div>
          <button
            type="submit"
            className="primary-button"
            disabled={savingUsername || !usernameChanged || username.trim().length < 3}
          >
            {savingUsername ? "Saving..." : "Save"}
          </button>
        </div>

        {usernameError && (
          <div id="profile-username-error" className="profile-flash profile-flash--error mt-3">
            {usernameError}
          </div>
        )}
      </form>

      <dl className="profile-account-details">
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
