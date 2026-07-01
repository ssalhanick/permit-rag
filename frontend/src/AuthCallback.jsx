import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";

/**
 * AuthCallback — exchanges the Cognito authorization code for tokens.
 * Cognito's /oauth2/token endpoint supports CORS for public SPA clients.
 */
export default function AuthCallback() {
  const { handleOAuthCallback } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [status, setStatus] = useState("Completing sign-in…");
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    const params = new URLSearchParams(window.location.search);
    const errorParam = params.get("error");
    const errorDesc = params.get("error_description");

    if (errorParam) {
      setError(decodeURIComponent(errorDesc || errorParam));
      return;
    }

    const code = params.get("code");
    if (!code) {
      setError("No authorization code in URL.");
      return;
    }

    const domain = import.meta.env.VITE_COGNITO_DOMAIN;
    const clientId = import.meta.env.VITE_COGNITO_APP_CLIENT_ID;
    const redirectUri = `${window.location.origin}/auth/callback`;
    const tokenUrl = `https://${domain}/oauth2/token`;

    setStatus(`Exchanging code with ${tokenUrl}…`);

    const body = new URLSearchParams({
      grant_type: "authorization_code",
      client_id: clientId,
      code,
      redirect_uri: redirectUri,
    });

    fetch(tokenUrl, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    })
      .then(async (res) => {
        const text = await res.text();
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${text}`);
        }
        return JSON.parse(text);
      })
      .then(async (tokens) => {
        if (tokens.error) {
          throw new Error(`${tokens.error}: ${tokens.error_description || ""}`);
        }
        setStatus("Loading profile…");
        await handleOAuthCallback(tokens.id_token, tokens.access_token, tokens.refresh_token);
        navigate("/kickoff", { replace: true });
      })
      .catch((err) => {
        setError(err.message || "Token exchange failed.");
      });
  }, [handleOAuthCallback, navigate]);

  if (error) {
    return (
      <main className="page auth-page">
        <section className="panel auth-panel">
          <h2>Sign-in Failed</h2>
          <div className="error-box">{error}</div>
          <div className="auth-toggle">
            <button
              type="button"
              className="text-button"
              onClick={() => navigate("/auth", { replace: true })}
            >
              Back to Sign In
            </button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="page auth-page">
      <section className="panel auth-panel">
        <p className="muted">{status}</p>
      </section>
    </main>
  );
}
