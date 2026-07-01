/** Shared helpers for admin document governance UI. */

export const ADMIN_TOKEN_STORAGE_KEY = "permit_rag_admin_token";

export const DOCUMENT_STATUS_OPTIONS = [
  "active",
  "superseded",
  "repealed",
  "needs_ocr",
  "draft",
];

/**
 * Build request headers for admin governance routes.
 *
 * @param {string} adminToken
 * @param {string} [adminRole]
 * @returns {Record<string, string>}
 */
export function buildAdminHeaders(adminToken, adminRole = "admin") {
  const token = (adminToken || "").trim();
  if (!token) {
    return {};
  }
  return {
    "X-Admin-Token": token,
    "X-Admin-Role": adminRole,
  };
}

/**
 * Read persisted admin token from sessionStorage.
 *
 * @returns {string}
 */
export function getStoredAdminToken() {
  if (typeof sessionStorage === "undefined") {
    return "";
  }
  return sessionStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) || "";
}

/**
 * Persist admin token for Upload and Documents pages.
 *
 * @param {string} token
 */
export function setStoredAdminToken(token) {
  if (typeof sessionStorage === "undefined") {
    return;
  }
  const trimmed = (token || "").trim();
  if (trimmed) {
    sessionStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, trimmed);
  } else {
    sessionStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
  }
}

/**
 * Build PATCH body, omitting empty unchanged fields.
 *
 * @param {object} form
 * @returns {object}
 */
export function buildUpdatePayload(form) {
  const payload = {};
  if (form.document_status) {
    payload.document_status = form.document_status;
  }
  if (form.is_current !== undefined && form.is_current !== null && form.is_current !== "") {
    payload.is_current = Boolean(form.is_current);
  }
  if (form.retrieval_weight !== undefined && form.retrieval_weight !== null && form.retrieval_weight !== "") {
    payload.retrieval_weight = Number(form.retrieval_weight);
  }
  if (form.review_due) {
    payload.review_due = form.review_due;
  }
  return payload;
}

/**
 * Validate metadata update form before PATCH.
 *
 * @param {object} payload
 * @returns {string[]}
 */
export function validateUpdatePayload(payload) {
  const errors = [];
  if (!Object.keys(payload).length) {
    errors.push("Change at least one field before saving.");
  }
  if (payload.retrieval_weight !== undefined) {
    const weight = Number(payload.retrieval_weight);
    if (Number.isNaN(weight) || weight < 0 || weight > 1) {
      errors.push("Retrieval weight must be between 0 and 1.");
    }
  }
  return errors;
}

/**
 * Validate supersede request body.
 *
 * @param {object} form
 * @returns {string[]}
 */
export function validateSupersedePayload(form) {
  const errors = [];
  const replacement = (form.replacement_doc_id || "").trim();
  if (!replacement) {
    errors.push("Enter a replacement doc_id.");
  }
  const weight = Number(form.superseded_weight ?? 0.1);
  if (Number.isNaN(weight) || weight < 0 || weight > 1) {
    errors.push("Superseded weight must be between 0 and 1.");
  }
  return errors;
}

/**
 * Map API errors to user-facing admin messages.
 *
 * @param {Error} err
 * @returns {string}
 */
export function formatAdminError(err) {
  const status = err?.meta?.status;
  const detail = err?.message || "Request failed.";
  if (status === 403) {
    return "Invalid admin token or role. Check X-Admin-Token.";
  }
  if (status === 404) {
    return "Document not found.";
  }
  if (status === 503) {
    return "Admin auth is not configured on the API.";
  }
  return detail;
}
