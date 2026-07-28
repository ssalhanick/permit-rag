import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserAttribute,
  CognitoUserPool,
} from "amazon-cognito-identity-js";
import { getProject, registerTokenRefresher, requestJson, setActiveProjectApi } from "../api.js";
import { usernameFromEmail } from "../authUsername.js";
import {
  closeOAuthBrowser,
  exchangeOAuthCode,
  parseOAuthCallbackUrl,
  registerOAuthDeepLink,
  startOAuthLogin,
} from "../mobileAuth.js";
import { isNativePlatform } from "../platform.js";

// ── Cognito User Pool singleton ───────────────────────────────

const _poolId = import.meta.env.VITE_COGNITO_USER_POOL_ID;
const _clientId = import.meta.env.VITE_COGNITO_APP_CLIENT_ID;

const isAuthConfigured = Boolean(
  _poolId && !_poolId.startsWith("REPLACE_") && _clientId && !_clientId.startsWith("REPLACE_")
);

if (!isAuthConfigured) {
  console.error(
    "[AuthContext] Missing Cognito env vars. " +
    "Set VITE_COGNITO_USER_POOL_ID and VITE_COGNITO_APP_CLIENT_ID in frontend/.env and restart Vite."
  );
}

// Only construct the real pool when configured — a pool built from fake
// placeholder IDs would fail confusingly deep inside the Cognito SDK instead
// of surfacing a clear error at the top of the app (see AuthConfigErrorScreen).
const userPool = isAuthConfigured
  ? new CognitoUserPool({ UserPoolId: _poolId, ClientId: _clientId })
  : null;

/**
 * Shown instead of the app when required Cognito env vars are missing or
 * still contain the "REPLACE_" placeholder, so a misconfigured deploy fails
 * loudly instead of silently breaking sign-in.
 */
function AuthConfigErrorScreen() {
  return (
    <div
      role="alert"
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "0.75rem",
        padding: "2rem",
        textAlign: "center",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <h1 style={{ fontSize: "1.25rem", fontWeight: 700, color: "#991b1b" }}>
        Authentication is not configured
      </h1>
      <p style={{ maxWidth: "32rem", color: "#475569" }}>
        This deployment is missing its Cognito configuration
        (VITE_COGNITO_USER_POOL_ID / VITE_COGNITO_APP_CLIENT_ID). Sign-in cannot work until
        these are set. Contact the site administrator.
      </p>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────

/**
 * Wrap cognitoUser.getSession() in a Promise.
 * Automatically refreshes the access/id tokens using the stored refresh token.
 */
function getSession(cognitoUser) {
  return new Promise((resolve, reject) => {
    cognitoUser.getSession((err, session) => {
      if (err) {
        reject(err);
      } else {
        resolve(session);
      }
    });
  });
}

/**
 * Store Cognito tokens in localStorage under the SDK's own key format so that
 * userPool.getCurrentUser() and getSession() can find them after a page reload
 * (used for tokens obtained via the OAuth2 code-exchange flow).
 */
function storeCognitoTokens(idToken, accessToken, refreshToken) {
  const clientId = import.meta.env.VITE_COGNITO_APP_CLIENT_ID;
  const prefix = `CognitoIdentityServiceProvider.${clientId}`;

  let username = "unknown";
  try {
    const payload = JSON.parse(atob(idToken.split(".")[1]));
    username = payload["cognito:username"] || payload.sub || "unknown";
  } catch {
    // keep fallback
  }

  localStorage.setItem(`${prefix}.LastAuthUser`, username);
  localStorage.setItem(`${prefix}.${username}.idToken`, idToken);
  localStorage.setItem(`${prefix}.${username}.accessToken`, accessToken);
  if (refreshToken) {
    localStorage.setItem(`${prefix}.${username}.refreshToken`, refreshToken);
  }
  localStorage.setItem(`${prefix}.${username}.clockDrift`, "0");

  // Also write to the key api.js reads for Bearer headers
  localStorage.setItem("access_token", idToken);
}

// ── Context ───────────────────────────────────────────────────

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);   // RDS user profile from /auth/me
  const [loading, setLoading] = useState(true);
  const [activeProject, setActiveProjectState] = useState(null);

  // Stores a pending CognitoUser ref during MFA challenge so confirmMfa() can reach it
  const pendingCognitoUserRef = useRef(null);

  // ── Session restoration on mount ─────────────────────────────

  const restoreSession = useCallback(async () => {
    if (!isAuthConfigured) {
      setUser(null);
      setLoading(false);
      return;
    }
    const currentCognitoUser = userPool.getCurrentUser();
    if (!currentCognitoUser) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const session = await getSession(currentCognitoUser);
      const idToken = session.getIdToken().getJwtToken();
      localStorage.setItem("access_token", idToken);

      const profile = await _fetchMe(idToken);
      setUser(profile);
    } catch {
      setUser(null);
      localStorage.removeItem("access_token");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    restoreSession();
  }, [restoreSession]);

  // ── Active project (nav switcher) ──────────────────────────────

  useEffect(() => {
    let cancelled = false;
    if (!user?.active_project_id) {
      setActiveProjectState(null);
      return;
    }
    getProject(user.active_project_id)
      .then((res) => {
        if (!cancelled) setActiveProjectState(res.data);
      })
      .catch(() => {
        if (!cancelled) setActiveProjectState(null);
      });
    return () => {
      cancelled = true;
    };
  }, [user?.active_project_id]);

  const setActiveProject = useCallback(async (projectId) => {
    const res = await setActiveProjectApi(projectId);
    setUser((prev) => (prev ? { ...prev, active_project_id: res.data.active_project_id } : prev));
    return res.data;
  }, []);

  // ── Register token refresher with api.js ──────────────────────

  useEffect(() => {
    registerTokenRefresher(async () => {
      if (!isAuthConfigured) return null;
      const currentCognitoUser = userPool.getCurrentUser();
      if (!currentCognitoUser) return null;
      try {
        const session = await getSession(currentCognitoUser);
        const idToken = session.getIdToken().getJwtToken();
        localStorage.setItem("access_token", idToken);
        return idToken;
      } catch {
        setUser(null);
        localStorage.removeItem("access_token");
        return null;
      }
    });
  }, []);

  // ── Private: fetch /auth/me to get the RDS profile ────────────

  async function _fetchMe(idToken) {
    const result = await requestJson("/auth/me", {
      headers: { Authorization: `Bearer ${idToken}` },
    });
    return result.data;
  }

  // ── Email + password sign-up ──────────────────────────────────

  /**
   * Register a new Cognito user with email and password.
   *
   * The pool uses email as an ALIAS, so the Cognito Username must not be in
   * email format — we generate an internal username from the email local part.
   * Users still sign in with their email address.
   *
   * Returns { screen: "confirm", email, username } — caller should show the
   * confirmation code UI and keep `username` for confirmSignUp().
   */
  const register = useCallback((email, password) => {
    const username = usernameFromEmail(email);
    const attributes = [new CognitoUserAttribute({ Name: "email", Value: email })];
    return new Promise((resolve, reject) => {
      userPool.signUp(username, password, attributes, null, (err) => {
        if (err) {
          reject(err);
        } else {
          resolve({ screen: "confirm", email, username });
        }
      });
    });
  }, []);

  // ── Confirm email after sign-up ───────────────────────────────

  /**
   * Confirm the 6-digit code Cognito emailed after sign-up.
   *
   * `username` must be the generated username returned by register() — the
   * email alias is not active until the account is confirmed, so confirming
   * by email would fail.
   *
   * If `password` is provided, auto-login with the (now active) email alias
   * and return login's result. Otherwise returns { screen: "login" } and the
   * caller should send the user to the sign-in form.
   */
  const confirmSignUp = useCallback(async (username, code, email, password) => {
    await new Promise((resolve, reject) => {
      const cognitoUser = new CognitoUser({ Username: username, Pool: userPool });
      cognitoUser.confirmRegistration(code, true, (err) => {
        if (err) reject(err);
        else resolve();
      });
    });
    if (email && password) {
      return login(email, password);
    }
    return { screen: "login" };
  }, []);

  // ── Email + password login ────────────────────────────────────

  /**
   * Authenticate with email + password.
   * Returns:
   *   { screen: "success", user } on normal success
   *   { screen: "mfa", cognitoUser } when TOTP is required
   */
  const login = useCallback((email, password) => {
    return new Promise((resolve, reject) => {
      const cognitoUser = new CognitoUser({ Username: email, Pool: userPool });
      const authDetails = new AuthenticationDetails({
        Username: email,
        Password: password,
      });

      cognitoUser.authenticateUser(authDetails, {
        onSuccess: async (session) => {
          const idToken = session.getIdToken().getJwtToken();
          localStorage.setItem("access_token", idToken);
          try {
            const profile = await _fetchMe(idToken);
            setUser(profile);
            resolve({ screen: "success", user: profile });
          } catch (err) {
            reject(err);
          }
        },

        onFailure: (err) => {
          reject(err);
        },

        totpRequired: () => {
          // Save ref so confirmMfa() can call sendMFACode
          pendingCognitoUserRef.current = cognitoUser;
          resolve({ screen: "mfa" });
        },

        newPasswordRequired: () => {
          reject(new Error("New password required. Contact support."));
        },
      });
    });
  }, []);

  // ── TOTP MFA confirmation ─────────────────────────────────────

  /**
   * Complete a pending TOTP MFA challenge with the 6-digit code.
   * Call only after login() returned { screen: "mfa" }.
   */
  const confirmMfa = useCallback((code) => {
    return new Promise((resolve, reject) => {
      const cognitoUser = pendingCognitoUserRef.current;
      if (!cognitoUser) {
        reject(new Error("No pending MFA challenge."));
        return;
      }
      cognitoUser.sendMFACode(
        code,
        {
          onSuccess: async (session) => {
            pendingCognitoUserRef.current = null;
            const idToken = session.getIdToken().getJwtToken();
            localStorage.setItem("access_token", idToken);
            try {
              const profile = await _fetchMe(idToken);
              setUser(profile);
              resolve({ screen: "success", user: profile });
            } catch (err) {
              reject(err);
            }
          },
          onFailure: (err) => {
            reject(err);
          },
        },
        "SOFTWARE_TOKEN_MFA",
      );
    });
  }, []);

  // ── TOTP MFA enrollment ───────────────────────────────────────

  /**
   * Begin TOTP enrollment for the currently signed-in user.
   * Returns { secretCode, qrUri } where qrUri is an otpauth:// URI for QR display.
   */
  const beginMfaSetup = useCallback(() => {
    return new Promise((resolve, reject) => {
      const cognitoUser = userPool.getCurrentUser();
      if (!cognitoUser) {
        reject(new Error("Not signed in."));
        return;
      }
      cognitoUser.associateSoftwareToken({
        associateSecretCode: (secretCode) => {
          const email = user?.email || "user";
          const qrUri = `otpauth://totp/permit-rag:${encodeURIComponent(email)}?secret=${secretCode}&issuer=permit-rag`;
          resolve({ secretCode, qrUri });
        },
        onFailure: (err) => {
          reject(err);
        },
      });
    });
  }, [user]);

  /**
   * Verify and complete TOTP enrollment with the scanned code.
   * Returns { success: true } on success.
   */
  const confirmMfaSetup = useCallback((code) => {
    return new Promise((resolve, reject) => {
      const cognitoUser = userPool.getCurrentUser();
      if (!cognitoUser) {
        reject(new Error("Not signed in."));
        return;
      }
      cognitoUser.verifySoftwareToken(code, "permit-rag", {
        onSuccess: () => resolve({ success: true }),
        onFailure: (err) => reject(err),
      });
    });
  }, []);

  // ── Forgot password ───────────────────────────────────────────

  /**
   * Initiate a Cognito forgot-password flow for the given email.
   * Cognito emails the user a 6-digit reset code.
   * Returns { screen: "reset" } — caller should show the code + new-password UI.
   */
  const forgotPassword = useCallback((email) => {
    return new Promise((resolve, reject) => {
      const cognitoUser = new CognitoUser({ Username: email, Pool: userPool });
      cognitoUser.forgotPassword({
        onSuccess: () => resolve({ screen: "reset" }),
        onFailure: (err) => reject(err),
      });
    });
  }, []);

  /**
   * Complete a forgot-password flow with the emailed code and a new password.
   * Returns { screen: "login" } on success — caller should redirect to login.
   */
  const confirmForgotPassword = useCallback((email, code, newPassword) => {
    return new Promise((resolve, reject) => {
      const cognitoUser = new CognitoUser({ Username: email, Pool: userPool });
      cognitoUser.confirmPassword(code, newPassword, {
        onSuccess: () => resolve({ screen: "login" }),
        onFailure: (err) => reject(err),
      });
    });
  }, []);

  // ── Google SSO ────────────────────────────────────────────────

  /**
   * Redirect to Cognito hosted UI for Google sign-in.
   * Uses system browser on native (Capacitor).
   */
  const loginWithGoogle = useCallback(async () => {
    await startOAuthLogin({ identityProvider: "Google" });
  }, []);

  /**
   * Sign in with Apple via Cognito identity provider (required on iOS when Google exists).
   */
  const loginWithApple = useCallback(async () => {
    await startOAuthLogin({ identityProvider: "SignInWithApple" });
  }, []);

  /**
   * Called by AuthCallback after exchanging the OAuth code for tokens.
   * Stores tokens in Cognito SDK format and loads the user profile.
   */
  const handleOAuthCallback = useCallback(async (idToken, accessToken, refreshToken) => {
    storeCognitoTokens(idToken, accessToken, refreshToken);
    localStorage.setItem("access_token", idToken);
    const profile = await _fetchMe(idToken);
    setUser(profile);
    return profile;
  }, []);

  // ── Native OAuth deep-link handler (Google / Apple) ───────────

  useEffect(() => {
    if (!isNativePlatform()) {
      return undefined;
    }
    let cleanup = () => {};
    registerOAuthDeepLink(async (url) => {
      const { code, error } = parseOAuthCallbackUrl(url);
      if (error) {
        console.error("[AuthContext] OAuth deep link error:", error);
        return;
      }
      if (!code) {
        return;
      }
      try {
        const tokens = await exchangeOAuthCode(code);
        await handleOAuthCallback(tokens.id_token, tokens.access_token, tokens.refresh_token);
        await closeOAuthBrowser();
        window.location.hash = "#/kickoff";
        window.dispatchEvent(new HashChangeEvent("hashchange"));
      } catch (err) {
        console.error("[AuthContext] OAuth token exchange failed:", err);
      }
    }).then((fn) => {
      cleanup = fn;
    });
    return () => cleanup();
  }, [handleOAuthCallback]);

  // ── Logout ────────────────────────────────────────────────────

  const logout = useCallback(() => {
    const cognitoUser = userPool?.getCurrentUser();
    if (cognitoUser) {
      cognitoUser.signOut();
    }
    localStorage.removeItem("access_token");
    setUser(null);
    setActiveProjectState(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        activeProject,
        setActiveProject,
        login,
        register,
        confirmSignUp,
        confirmMfa,
        beginMfaSetup,
        confirmMfaSetup,
        forgotPassword,
        confirmForgotPassword,
        loginWithGoogle,
        loginWithApple,
        handleOAuthCallback,
        logout,
      }}
    >
      {isAuthConfigured ? children : <AuthConfigErrorScreen />}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
