import React, { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";

export default function AuthPage() {
  const { login, register, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || "/";

  const [isRegister, setIsRegister] = useState(false);
  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
    confirmPassword: "",
    phone: "",
    identifier: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  if (user) {
    // Already logged in
    setTimeout(() => navigate(from, { replace: true }), 0);
    return null;
  }

  const handleChange = (e) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setSuccess("");

    if (isRegister && form.password !== form.confirmPassword) {
      setError("Passwords do not match.");
      setLoading(false);
      return;
    }

    try {
      if (isRegister) {
        await register(form.username, form.password, form.email, form.phone);
        setSuccess("Registration successful! Logging you in...");
      } else {
        await login(form.identifier, form.password);
        setSuccess("Login successful!");
      }
      setTimeout(() => {
        navigate(from, { replace: true });
      }, 1000);
    } catch (err) {
      setError(err.message || "Authentication failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="page auth-page">
      <section className="panel auth-panel">
        <h2>{isRegister ? "Create an Account" : "Sign In"}</h2>
        <p className="muted">
          {isRegister
            ? "Sign up to collaborate, create projects, and share documents."
            : "Sign in to access your projects and shared workspace."}
        </p>

        {error && <div className="error-box">{error}</div>}
        {success && <div className="success-box">{success}</div>}

        <form onSubmit={handleSubmit} className="form">
          {isRegister ? (
            <>
              <div>
                <label htmlFor="username">Username</label>
                <input
                  id="username"
                  name="username"
                  value={form.username}
                  onChange={handleChange}
                  placeholder="e.g. bob_builder"
                  required
                />
              </div>
              <div>
                <label htmlFor="email">Email Address</label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  value={form.email}
                  onChange={handleChange}
                  placeholder="e.g. bob@example.com"
                  required
                />
              </div>
              <div>
                <label htmlFor="phone">Phone Number (optional)</label>
                <input
                  id="phone"
                  name="phone"
                  value={form.phone}
                  onChange={handleChange}
                  placeholder="e.g. +1 214-555-0100"
                />
              </div>
            </>
          ) : (
            <div>
              <label htmlFor="identifier">Username, Email, or Phone</label>
              <input
                id="identifier"
                name="identifier"
                value={form.identifier}
                onChange={handleChange}
                placeholder="Enter login credentials"
                required
              />
            </div>
          )}

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

          {isRegister && (
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
          )}

          <button type="submit" disabled={loading} className="primary-button">
            {loading ? "Processing..." : isRegister ? "Sign Up" : "Sign In"}
          </button>
        </form>

        <div className="auth-toggle">
          <button
            type="button"
            className="text-button"
            onClick={() => {
              setIsRegister(!isRegister);
              setError("");
              setSuccess("");
            }}
          >
            {isRegister
              ? "Already have an account? Sign In"
              : "Don't have an account? Sign Up"}
          </button>
        </div>
      </section>
    </main>
  );
}
