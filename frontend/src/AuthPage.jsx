import React, { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";

/**
 * Screen states:
 *  "login"    — email + password sign-in form
 *  "register" — email + password sign-up form
 *  "confirm"  — enter Cognito email confirmation code after sign-up
 *  "mfa"      — enter TOTP code during login
 *  "mfa_setup"— QR code screen to enroll authenticator app
 */

export default function AuthPage() {
  const { login, register, confirmSignUp, confirmMfa, beginMfaSetup, confirmMfaSetup,
          forgotPassword, confirmForgotPassword, loginWithGoogle, user } =
    useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || "/";
  // Redirect new/fresh sign-ins to the project kickoff wizard.
  // Preserve the original destination when the user was mid-navigation to a protected page.
  const dest = from === "/" ? "/kickoff" : from;

  const [screen, setScreen] = useState("login");
  const [pendingEmail, setPendingEmail] = useState("");
  const [mfaSetupData, setMfaSetupData] = useState(null); // { secretCode, qrUri }

  const [form, setForm] = useState({ email: "", password: "", confirmPassword: "", code: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  if (user) {
    setTimeout(() => navigate(dest, { replace: true }), 0);
    return null;
  }

  const handleChange = (e) => setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));

  const reset = (nextScreen) => {
    setError("");
    setSuccess("");
    setScreen(nextScreen);
  };

  // ── Login ─────────────────────────────────────────────────────

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await login(form.email, form.password);
      if (result.screen === "mfa") {
        reset("mfa");
      } else {
        navigate(dest, { replace: true });
      }
    } catch (err) {
      setError(err.message || "Sign-in failed.");
    } finally {
      setLoading(false);
    }
  };

  // ── Register ──────────────────────────────────────────────────

  const handleRegister = async (e) => {
    e.preventDefault();
    if (form.password !== form.confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await register(form.email, form.password);
      if (result.screen === "confirm") {
        setPendingEmail(form.email);
        reset("confirm");
        setSuccess("Check your email for a 6-digit confirmation code.");
      }
    } catch (err) {
      setError(err.message || "Registration failed.");
    } finally {
      setLoading(false);
    }
  };

  // ── Email confirmation ────────────────────────────────────────

  const handleConfirm = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await confirmSignUp(pendingEmail, form.code);
      navigate(dest, { replace: true });
    } catch (err) {
      setError(err.message || "Confirmation failed. Check your code.");
    } finally {
      setLoading(false);
    }
  };

  // ── MFA challenge ─────────────────────────────────────────────

  const handleMfa = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await confirmMfa(form.code);
      navigate(dest, { replace: true });
    } catch (err) {
      setError(err.message || "Invalid code. Try again.");
    } finally {
      setLoading(false);
    }
  };

  // ── MFA setup ─────────────────────────────────────────────────

  const handleBeginMfaSetup = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await beginMfaSetup();
      setMfaSetupData(data);
      reset("mfa_setup");
    } catch (err) {
      setError(err.message || "Could not begin MFA setup.");
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmMfaSetup = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await confirmMfaSetup(form.code);
      setSuccess("Two-factor authentication enabled.");
      setMfaSetupData(null);
      navigate(dest, { replace: true });
    } catch (err) {
      setError(err.message || "Setup failed. Check the code.");
    } finally {
      setLoading(false);
    }
  };

  // ── Forgot password ───────────────────────────────────────────

  const handleForgotPassword = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await forgotPassword(form.email);
      setPendingEmail(form.email);
      reset("reset");
      setSuccess("Check your email for a 6-digit reset code.");
    } catch (err) {
      setError(err.message || "Could not send reset code. Check the email address.");
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    if (form.password !== form.confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await confirmForgotPassword(pendingEmail, form.code, form.password);
      reset("login");
      setSuccess("Password reset! Sign in with your new password.");
    } catch (err) {
      setError(err.message || "Reset failed. Check the code and try again.");
    } finally {
      setLoading(false);
    }
  };

  // ── Google SSO ────────────────────────────────────────────────

  const googleEnabled = import.meta.env.VITE_COGNITO_GOOGLE_ENABLED === "true";

  // ── Render ────────────────────────────────────────────────────

  return (
    <main className="page auth-page">
      <section className="panel auth-panel">

        {/* ── Login ─────────────────────────── */}
        {screen === "login" && (
          <>
            <h2>Sign In</h2>
            <p className="muted">Sign in to access your projects and shared workspace.</p>

            {error && <div className="error-box">{error}</div>}
            {success && <div className="success-box">{success}</div>}

            <form onSubmit={handleLogin} className="form">
              <div>
                <label htmlFor="email">Email Address</label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  value={form.email}
                  onChange={handleChange}
                  placeholder="you@example.com"
                  required
                />
              </div>
              <div>
                <label htmlFor="password">Password</label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  value={form.password}
                  onChange={handleChange}
                  placeholder="••••••••••••"
                  required
                />
              </div>
              <button type="submit" disabled={loading} className="primary-button">
                {loading ? "Signing in…" : "Sign In"}
              </button>
            </form>

            {googleEnabled && (
              <div className="auth-divider">
                <span>or</span>
              </div>
            )}

            {googleEnabled && (
              <button type="button" className="google-button" onClick={loginWithGoogle}>
                <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
                  <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/>
                  <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/>
                  <path fill="#FBBC05" d="M3.964 10.707A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.707V4.961H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.039l3.007-2.332z"/>
                  <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.961L3.964 7.293C4.672 5.163 6.656 3.58 9 3.58z"/>
                </svg>
                Sign in with Google
              </button>
            )}

            <div className="auth-toggle">
              <button type="button" className="text-button" onClick={() => reset("register")}>
                Don&apos;t have an account? Sign Up
              </button>
              <button type="button" className="text-button" onClick={() => reset("forgot")}>
                Forgot your password?
              </button>
            </div>
          </>
        )}

        {/* ── Register ──────────────────────── */}
        {screen === "register" && (
          <>
            <h2>Create an Account</h2>
            <p className="muted">Sign up to collaborate, create projects, and share documents.</p>

            {error && <div className="error-box">{error}</div>}

            <form onSubmit={handleRegister} className="form">
              <div>
                <label htmlFor="email">Email Address</label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  value={form.email}
                  onChange={handleChange}
                  placeholder="you@example.com"
                  required
                />
              </div>
              <div>
                <label htmlFor="password">Password</label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  value={form.password}
                  onChange={handleChange}
                  placeholder="Minimum 8 characters"
                  required
                />
              </div>
              <div>
                <label htmlFor="confirmPassword">Confirm Password</label>
                <input
                  id="confirmPassword"
                  name="confirmPassword"
                  type="password"
                  value={form.confirmPassword}
                  onChange={handleChange}
                  placeholder="••••••••••••"
                  required
                />
              </div>
              <button type="submit" disabled={loading} className="primary-button">
                {loading ? "Creating account…" : "Sign Up"}
              </button>
            </form>

            <div className="auth-toggle">
              <button type="button" className="text-button" onClick={() => reset("login")}>
                Already have an account? Sign In
              </button>
            </div>
          </>
        )}

        {/* ── Email confirmation code ────────── */}
        {screen === "confirm" && (
          <>
            <h2>Confirm Your Email</h2>
            <p className="muted">
              We sent a 6-digit code to <strong>{pendingEmail}</strong>. Enter it below.
            </p>

            {error && <div className="error-box">{error}</div>}
            {success && <div className="success-box">{success}</div>}

            <form onSubmit={handleConfirm} className="form">
              <div>
                <label htmlFor="code">Confirmation Code</label>
                <input
                  id="code"
                  name="code"
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={form.code}
                  onChange={handleChange}
                  placeholder="123456"
                  required
                  autoFocus
                />
              </div>
              <button type="submit" disabled={loading} className="primary-button">
                {loading ? "Verifying…" : "Confirm Email"}
              </button>
            </form>

            <div className="auth-toggle">
              <button type="button" className="text-button" onClick={() => reset("login")}>
                Back to Sign In
              </button>
            </div>
          </>
        )}

        {/* ── TOTP MFA challenge ─────────────── */}
        {screen === "mfa" && (
          <>
            <h2>Two-Factor Authentication</h2>
            <p className="muted">Open your authenticator app and enter the 6-digit code.</p>

            {error && <div className="error-box">{error}</div>}

            <form onSubmit={handleMfa} className="form">
              <div>
                <label htmlFor="code">Authenticator Code</label>
                <input
                  id="code"
                  name="code"
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={form.code}
                  onChange={handleChange}
                  placeholder="123456"
                  required
                  autoFocus
                />
              </div>
              <button type="submit" disabled={loading} className="primary-button">
                {loading ? "Verifying…" : "Verify"}
              </button>
            </form>
          </>
        )}

        {/* ── TOTP MFA setup (enrollment) ────── */}
        {screen === "mfa_setup" && mfaSetupData && (
          <>
            <h2>Set Up Two-Factor Authentication</h2>
            <p className="muted">
              Scan the QR code with Google Authenticator, Authy, or any TOTP app, then enter
              the 6-digit code to confirm.
            </p>

            {error && <div className="error-box">{error}</div>}
            {success && <div className="success-box">{success}</div>}

            <div className="mfa-qr-wrap">
              <img
                src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(mfaSetupData.qrUri)}`}
                alt="Scan with authenticator app"
                width={180}
                height={180}
              />
              <p className="muted mfa-secret">
                Manual entry: <code>{mfaSetupData.secretCode}</code>
              </p>
            </div>

            <form onSubmit={handleConfirmMfaSetup} className="form">
              <div>
                <label htmlFor="code">Authenticator Code</label>
                <input
                  id="code"
                  name="code"
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={form.code}
                  onChange={handleChange}
                  placeholder="123456"
                  required
                  autoFocus
                />
              </div>
              <button type="submit" disabled={loading} className="primary-button">
                {loading ? "Enabling…" : "Enable 2FA"}
              </button>
            </form>

            <div className="auth-toggle">
              <button type="button" className="text-button" onClick={() => navigate(dest, { replace: true })}>
                Skip for now
              </button>
            </div>
          </>
        )}

        {/* ── Forgot password — request reset code ────── */}
        {screen === "forgot" && (
          <>
            <h2>Reset Your Password</h2>
            <p className="muted">
              Enter your email and we&apos;ll send you a 6-digit reset code.
            </p>

            {error && <div className="error-box">{error}</div>}

            <form onSubmit={handleForgotPassword} className="form">
              <div>
                <label htmlFor="email">Email Address</label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  value={form.email}
                  onChange={handleChange}
                  placeholder="you@example.com"
                  required
                  autoFocus
                />
              </div>
              <button type="submit" disabled={loading} className="primary-button">
                {loading ? "Sending code…" : "Send Reset Code"}
              </button>
            </form>

            <div className="auth-toggle">
              <button type="button" className="text-button" onClick={() => reset("login")}>
                Back to Sign In
              </button>
            </div>
          </>
        )}

        {/* ── Forgot password — enter code + new password ─ */}
        {screen === "reset" && (
          <>
            <h2>Enter New Password</h2>
            <p className="muted">
              We sent a 6-digit code to <strong>{pendingEmail}</strong>. Enter it below along
              with your new password.
            </p>

            {error && <div className="error-box">{error}</div>}
            {success && <div className="success-box">{success}</div>}

            <form onSubmit={handleResetPassword} className="form">
              <div>
                <label htmlFor="code">Reset Code</label>
                <input
                  id="code"
                  name="code"
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={form.code}
                  onChange={handleChange}
                  placeholder="123456"
                  required
                  autoFocus
                />
              </div>
              <div>
                <label htmlFor="password">New Password</label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  value={form.password}
                  onChange={handleChange}
                  placeholder="Minimum 8 characters"
                  required
                />
              </div>
              <div>
                <label htmlFor="confirmPassword">Confirm New Password</label>
                <input
                  id="confirmPassword"
                  name="confirmPassword"
                  type="password"
                  value={form.confirmPassword}
                  onChange={handleChange}
                  placeholder="••••••••••••"
                  required
                />
              </div>
              <button type="submit" disabled={loading} className="primary-button">
                {loading ? "Resetting…" : "Reset Password"}
              </button>
            </form>

            <div className="auth-toggle">
              <button type="button" className="text-button" onClick={() => reset("forgot")}>
                Resend code
              </button>
              <button type="button" className="text-button" onClick={() => reset("login")}>
                Back to Sign In
              </button>
            </div>
          </>
        )}

      </section>
    </main>
  );
}
