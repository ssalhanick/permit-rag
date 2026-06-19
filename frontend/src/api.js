const DEFAULT_BASE_URL = "http://localhost:8000";
const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL
  ? import.meta.env.VITE_API_BASE_URL
  : (typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
      ? DEFAULT_BASE_URL
      : "");

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

  // Auto-refresh token if 401 and refresh_token exists
  if (response.status === 401 && path !== "/auth/login" && path !== "/auth/register" && path !== "/auth/refresh") {
    const refreshToken = localStorage.getItem("refresh_token");
    if (refreshToken) {
      try {
        const refreshResp = await fetch(`${API_BASE_URL}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (refreshResp.ok) {
          const tokens = await refreshResp.json();
          localStorage.setItem("access_token", tokens.access_token);
          localStorage.setItem("refresh_token", tokens.refresh_token);
          
          headers["Authorization"] = `Bearer ${tokens.access_token}`;
          response = await fetch(`${API_BASE_URL}${path}`, {
            method: options.method || "GET",
            headers,
            body: options.body ? JSON.stringify(options.body) : undefined,
          });
        } else {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
        }
      } catch {
        // network error during refresh
      }
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

export async function registerUser(payload) {
  const result = await requestJson("/auth/register", {
    method: "POST",
    body: payload,
  });
  if (result.data?.access_token) {
    localStorage.setItem("access_token", result.data.access_token);
    localStorage.setItem("refresh_token", result.data.refresh_token);
  }
  return result;
}

export async function loginUser(payload) {
  const result = await requestJson("/auth/login", {
    method: "POST",
    body: payload,
  });
  if (result.data?.access_token) {
    localStorage.setItem("access_token", result.data.access_token);
    localStorage.setItem("refresh_token", result.data.refresh_token);
  }
  return result;
}

export async function logoutUser() {
  try {
    await requestJson("/auth/logout-all", { method: "POST" });
  } catch {
    // ignore if token already expired/invalid
  }
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
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

export async function fetchQueryHistory() {
  return await requestJson("/query/history");
}

export async function deleteQueryFromHistory(queryId) {
  return await requestJson(`/query/history/${queryId}`, {
    method: "DELETE",
  });
}

// ── Admin Document Purge Endpoints ─────────────────────────

export async function purgeDocumentAdmin(docId) {
  return await requestJson(`/admin/documents/${docId}`, {
    method: "DELETE",
  });
}

export { API_BASE_URL, DEFAULT_BASE_URL };
