/**
 * platform.js — Capacitor vs web detection and mobile config helpers.
 */

/** @returns {boolean} True when running inside a Capacitor native shell. */
export function isNativePlatform() {
  if (typeof window === "undefined") {
    return false;
  }
  const cap = window.Capacitor;
  if (cap && typeof cap.isNativePlatform === "function") {
    return cap.isNativePlatform();
  }
  const protocol = window.location?.protocol || "";
  return protocol === "capacitor:" || protocol === "ionic:";
}

/** @returns {"ios" | "android" | "web"} */
export function getPlatformName() {
  if (!isNativePlatform()) {
    return "web";
  }
  const cap = window.Capacitor;
  const platform = cap?.getPlatform?.();
  if (platform === "ios" || platform === "android") {
    return platform;
  }
  return "web";
}

/** Mobile builds should not load Mapbox (deferred on mobile v1). */
export function isMapboxEnabled() {
  return true;
}

/** OAuth / deep-link redirect URI for Cognito callbacks. */
export function getOAuthRedirectUri() {
  const configured = import.meta.env?.VITE_MOBILE_OAUTH_REDIRECT_URI;
  if (configured) {
    return configured;
  }
  if (isNativePlatform()) {
    return "com.scottsalhanick.permitrag://auth/callback";
  }
  if (typeof window !== "undefined" && window.location?.origin) {
    return `${window.location.origin}/auth/callback`;
  }
  return "http://localhost:5173/auth/callback";
}

/** App custom URL scheme for deep links. */
export const MOBILE_APP_SCHEME = "com.scottsalhanick.permitrag";
