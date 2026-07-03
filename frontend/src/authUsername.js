/**
 * authUsername.js — Cognito username generation (P0-1 fix, UX audit 260703)
 * -------------------------------------------------------------------------
 * The user pool is configured with email as an ALIAS, which means the
 * Cognito Username must NOT be in email format. Users still sign in with
 * their email (alias resolution) — this generated username is internal.
 */

/**
 * Build a non-email Cognito username from an email address.
 *
 * - Takes the local part (before @), lowercased
 * - Replaces any character outside [a-z0-9_-] with "_"
 * - Appends a random 8-char hex suffix so distinct accounts never collide
 *   (email uniqueness is enforced separately by the alias)
 *
 * @param {string} email - the email address the user registered with
 * @param {() => string} [randomSuffix] - injectable suffix generator (for tests)
 * @returns {string} a Cognito-safe username, never in email format
 */
export function usernameFromEmail(email, randomSuffix = defaultRandomSuffix) {
  const localPart = String(email).split("@")[0].toLowerCase();
  const sanitized = localPart.replace(/[^a-z0-9_-]/g, "_").slice(0, 40) || "user";
  return `${sanitized}_${randomSuffix()}`;
}

/** Random 8-char hex suffix. */
function defaultRandomSuffix() {
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = new Uint8Array(4);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }
  return Math.random().toString(16).slice(2, 10).padEnd(8, "0");
}
