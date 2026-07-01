import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
} from "amazon-cognito-identity-js";
import { registerTokenRefresher, requestJson } from "../api.js";

// ── Cognito User Pool singleton ───────────────────────────────

const _poolId = import.meta.env.VITE_COGNITO_USER_POOL_ID;
const _clientId = import.meta.env.VITE_COGNITO_APP_CLIENT_ID;

if (!_poolId || _poolId.startsWith("REPLACE_") || !_clientId || _clientId.startsWith("REPLACE_")) {
  console.error(
    "[AuthContext] Missing Cognito env vars. " +
    "Set VITE_COGNITO_USER_POOL_ID and VITE_COGNITO_APP_CLIENT_ID in frontend/.env and restart Vite."
  );
}

const userPool = new CognitoUserPool({
  UserPoolId: _poolId || "us-east-1_PLACEHOLDER",
  ClientId: _clientId || "PLACEHOLDER",
});

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

  // Stores a pending CognitoUser ref during MFA challenge so confirmMfa() can reach it
  const pendingCognitoUserRef = useRef(null);

  // ── Session restoration on mount ─────────────────────────────

  const restoreSession = useCallback(async () => {
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

  // ── Register token refresher with api.js ──────────────────────

  useEffect(() => {
    registerTokenRefresher(async () => {
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
   * Returns { screen: "confirm" } — caller should show the confirmation code UI.
   */
  const register = useCallback((email, password) => {
    return new Promise((resolve, reject) => {
      userPool.signUp(email, password, [], null, (err) => {
        if (err) {
          reject(err);
        } else {
          resolve({ screen: "confirm", email });
        }
      });
    });
  }, []);

  // ── Confirm email after sign-up ───────────────────────────────

  /**
   * Confirm the 6-digit code Cognito emailed after sign-up, then auto-login.
   * Returns the RDS user profile on success.
   */
  const confirmSignUp = useCallback(async (email, code) => {
    await new Promise((resolve, reject) => {
      const cognitoUser = new CognitoUser({ Username: email, Pool: userPool });
      cognitoUser.confirmRegistration(code, true, (err) => {
        if (err) reject(err);
        else resolve();
      });
    });
    // Auto-login after confirmation (returns same shape as login)
    return login(email, "_cognito_confirm_placeholder_");
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
   * Redirect the browser to Cognito's hosted UI for Google sign-in.
   * After Google auth, Cognito redirects to /auth/callback with ?code=.
   */
  const loginWithGoogle = useCallback(() => {
    const domain = import.meta.env.VITE_COGNITO_DOMAIN;
    const clientId = import.meta.env.VITE_COGNITO_APP_CLIENT_ID;
    const redirectUri = encodeURIComponent(`${window.location.origin}/auth/callback`);
    const url =
      `https://${domain}/oauth2/authorize` +
      `?response_type=code` +
      `&client_id=${clientId}` +
      `&redirect_uri=${redirectUri}` +
      `&identity_provider=Google` +
      `&scope=email+openid+profile`;
    window.location.href = url;
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

  // ── Logout ────────────────────────────────────────────────────

  const logout = useCallback(() => {
    const cognitoUser = userPool.getCurrentUser();
    if (cognitoUser) {
      cognitoUser.signOut();
    }
    localStorage.removeItem("access_token");
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        register,
        confirmSignUp,
        confirmMfa,
        beginMfaSetup,
        confirmMfaSetup,
        forgotPassword,
        confirmForgotPassword,
        loginWithGoogle,
        handleOAuthCallback,
        logout,
      }}
    >
      {children}
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
