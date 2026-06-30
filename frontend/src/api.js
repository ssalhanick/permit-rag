import { buildAdminHeaders } from "./documentAdminUtils.js";

// Mock localStorage for non-browser testing environments (e.g. Node runner)
if (typeof localStorage === "undefined") {
  global.localStorage = {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
  };
}

// Token refresher registered by AuthContext so requestJson can refresh Cognito sessions on 401
let _tokenRefresher = null;
export function registerTokenRefresher(fn) {
  _tokenRefresher = fn;
}

const DEFAULT_BASE_URL = "http://localhost:8000";
// When VITE_API_BASE_URL is explicitly set (even to ""), use it. Blank string
// means "same origin" so the Vite dev-server proxy handles routing to the backend.
const API_BASE_URL =
  import.meta.env?.VITE_API_BASE_URL !== undefined
    ? (import.meta.env.VITE_API_BASE_URL ?? "")
    : typeof window !== "undefined" &&
        (window.location.hostname === "localhost" ||
          window.location.hostname === "127.0.0.1")
      ? DEFAULT_BASE_URL
      : "";

function safeJsonParse(text) {
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export async function requestJson(path, options = {}) {
  const startedAt = Date.now();
  const requestId = options.requestId || `req-${startedAt}`;
  
  let headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  const token = localStorage.getItem("access_token");
  if (token && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method || "GET",
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  // Auto-refresh Cognito token on 401 via registered callback
  if (response.status === 401 && _tokenRefresher) {
    try {
      const newToken = await _tokenRefresher();
      if (newToken) {
        headers["Authorization"] = `Bearer ${newToken}`;
        response = await fetch(`${API_BASE_URL}${path}`, {
          method: options.method || "GET",
          headers,
          body: options.body ? JSON.stringify(options.body) : undefined,
        });
      }
    } catch {
      // refresh failed — let the original 401 propagate
    }
  }

  const rawText = await response.text();
  const data = safeJsonParse(rawText);
  const elapsedMs = Date.now() - startedAt;
  const result = {
    ok: response.ok,
    status: response.status,
    data,
    rawText,
    elapsedMs,
    requestId,
  };

  if (!response.ok) {
    const detail = data?.detail || rawText || "Request failed.";
    const error = new Error(detail);
    error.meta = result;
    throw error;
  }

  return result;
}

export async function fetchHealth(headers = {}) {
  const result = await requestJson("/health", { headers });
  return result;
}

export async function fetchAnswer(payload, headers = {}) {
  const result = await requestJson("/query/answer", {
    method: "POST",
    body: payload,
    headers,
  });
  return result;
}

function buildDocumentQuery(filters = {}) {
  const params = new URLSearchParams();
  if (filters.municipality) {
    params.set("municipality", filters.municipality.trim().toLowerCase());
  }
  if (filters.status) {
    params.set("status", filters.status);
  }
  if (filters.authority) {
    params.set("authority", filters.authority);
  }
  if (filters.doc_type) {
    params.set("doc_type", filters.doc_type);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export async function fetchDocuments(filters = {}, headers = {}) {
  const query = buildDocumentQuery(filters);
  const result = await requestJson(`/documents${query}`, { headers });
  return result;
}

export async function fetchDocumentStatus(filters = {}, headers = {}) {
  const query = buildDocumentQuery(filters);
  const result = await requestJson(`/documents/status${query}`, { headers });
  return result;
}

// ── Auth Endpoints ───────────────────────────────────────────
// Login, register, and logout are handled directly by the Cognito SDK in AuthContext.
// Only /auth/me (profile fetch) goes through the API.

export async function fetchMe() {
  return await requestJson("/auth/me");
}

// ── Project Endpoints ────────────────────────────────────────

export async function fetchProjects() {
  return await requestJson("/projects/");
}

export async function createProject(payload) {
  return await requestJson("/projects/", {
    method: "POST",
    body: payload,
  });
}

export async function getProject(projectId) {
  return await requestJson(`/projects/${projectId}`);
}

export async function deleteProject(projectId) {
  return await requestJson(`/projects/${projectId}`, {
    method: "DELETE",
  });
}

export async function transferProjectOwnership(projectId, newOwnerId) {
  return await requestJson(`/projects/${projectId}/transfer`, {
    method: "POST",
    body: { new_owner_id: newOwnerId },
  });
}

export async function fetchProjectMembers(projectId) {
  return await requestJson(`/projects/${projectId}/members`);
}

export async function addProjectMember(projectId, userId, role = "viewer") {
  return await requestJson(`/projects/${projectId}/members`, {
    method: "POST",
    body: { user_id: userId, role },
  });
}

export async function removeProjectMember(projectId, userId) {
  return await requestJson(`/projects/${projectId}/members/${userId}`, {
    method: "DELETE",
  });
}

export async function shareDocumentToProject(projectId, documentId) {
  return await requestJson(`/projects/${projectId}/documents`, {
    method: "POST",
    body: { document_id: documentId },
  });
}

export async function fetchProjectDocuments(projectId) {
  return await requestJson(`/projects/${projectId}/documents`);
}

// ── Query History Endpoints ─────────────────────────────────

export async function fetchQueryHistory(projectId) {
  const query = projectId ? `?project_id=${projectId}` : "";
  return await requestJson(`/query/history${query}`);
}

export async function deleteQueryFromHistory(queryId) {
  return await requestJson(`/query/history/${queryId}`, {
    method: "DELETE",
  });
}

// ── Admin Document Governance ────────────────────────────────

export async function fetchDocumentDetail(docId) {
  return await requestJson(`/documents/${encodeURIComponent(docId)}`);
}

export async function updateDocumentAdmin(docId, body, adminToken, adminRole = "admin") {
  return await requestJson(`/admin/documents/${encodeURIComponent(docId)}`, {
    method: "PATCH",
    body,
    headers: buildAdminHeaders(adminToken, adminRole),
  });
}

export async function supersedeDocumentAdmin(docId, body, adminToken, adminRole = "admin") {
  return await requestJson(`/admin/documents/${encodeURIComponent(docId)}/supersede`, {
    method: "POST",
    body,
    headers: buildAdminHeaders(adminToken, adminRole),
  });
}

export async function purgeDocumentAdmin(docId, adminToken, adminRole = "admin", adminUser = "") {
  const headers = buildAdminHeaders(adminToken, adminRole);
  if (adminUser.trim()) {
    headers["X-Admin-User"] = adminUser.trim();
  }
  return await requestJson(`/admin/documents/${encodeURIComponent(docId)}/purge-project-upload`, {
    method: "POST",
    headers,
  });
}

export { API_BASE_URL, DEFAULT_BASE_URL };
