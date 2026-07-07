/**
 * mobileAuth.js — OAuth via system browser + deep links on Capacitor.
 */

import { Browser } from "@capacitor/browser";
import { App } from "@capacitor/app";
import { getOAuthRedirectUri, isNativePlatform } from "./platform.js";

/**
 * Build Cognito hosted UI authorize URL.
 *
 * @param {{ identityProvider?: string, providerLabel?: string }} opts
 * @returns {string}
 */
export function buildCognitoAuthorizeUrl(opts = {}) {
  const domain = import.meta.env.VITE_COGNITO_DOMAIN;
  const clientId = import.meta.env.VITE_COGNITO_APP_CLIENT_ID;
  const redirectUri = encodeURIComponent(getOAuthRedirectUri());
  let url =
    `https://${domain}/oauth2/authorize` +
    `?response_type=code` +
    `&client_id=${clientId}` +
    `&redirect_uri=${redirectUri}` +
    `&scope=email+openid+profile`;
  if (opts.identityProvider) {
    url += `&identity_provider=${encodeURIComponent(opts.identityProvider)}`;
  }
  return url;
}

/**
 * Open Cognito OAuth in system browser (mobile) or same window (web).
 *
 * @param {{ identityProvider?: string }} opts
 */
export async function startOAuthLogin(opts = {}) {
  const url = buildCognitoAuthorizeUrl(opts);
  if (isNativePlatform()) {
    await Browser.open({ url, presentationStyle: "popover" });
    return;
  }
  window.location.href = url;
}

/**
 * Register a handler for OAuth deep-link returns on native.
 *
 * @param {(url: string) => void} onDeepLink
 * @returns {Promise<() => void>} cleanup function
 */
export async function registerOAuthDeepLink(onDeepLink) {
  if (!isNativePlatform()) {
    return () => {};
  }
  const sub = await App.addListener("appUrlOpen", (event) => {
    if (event?.url) {
      onDeepLink(event.url);
    }
  });
  return () => {
    sub.remove();
  };
}

/** Close in-app browser after OAuth callback (native). */
export async function closeOAuthBrowser() {
  if (!isNativePlatform()) {
    return;
  }
  try {
    await Browser.close();
  } catch {
    // browser may already be closed
  }
}

/**
 * Parse authorization code from callback URL (web path or custom scheme).
 *
 * @param {string} url
 * @returns {{ code: string | null, error: string | null }}
 */
export function parseOAuthCallbackUrl(url) {
  try {
    const normalized = url.includes("://")
      ? url.replace(/^[^:]+:\/\//, "https://dummy/")
      : url;
    const parsed = new URL(normalized, "https://dummy.local");
    const error = parsed.searchParams.get("error");
    if (error) {
      return {
        code: null,
        error: decodeURIComponent(parsed.searchParams.get("error_description") || error),
      };
    }
    return { code: parsed.searchParams.get("code"), error: null };
  } catch {
    return { code: null, error: "Invalid OAuth callback URL." };
  }
}

/**
 * Exchange OAuth code for tokens at Cognito /oauth2/token.
 *
 * @param {string} code
 * @returns {Promise<object>}
 */
export async function exchangeOAuthCode(code) {
  const domain = import.meta.env.VITE_COGNITO_DOMAIN;
  const clientId = import.meta.env.VITE_COGNITO_APP_CLIENT_ID;
  const redirectUri = getOAuthRedirectUri();
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: clientId,
    code,
    redirect_uri: redirectUri,
  });
  const res = await fetch(`https://${domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return JSON.parse(text);
}
