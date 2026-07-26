import { getPlatformName, isNativePlatform } from "./platform.js";

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
/** All backend routes live under /api so SPA paths (/projects, /documents, /auth) never collide at CloudFront. */
export const API_PREFIX = "/api";
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

function resolveApiPath(path) {
  if (path.startsWith("/api")) {
    return path;
  }
  return `${API_PREFIX}${path}`;
}

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

function buildDefaultHeaders(extra = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...extra,
  };
  if (isNativePlatform()) {
    headers["X-Client-Tier"] = "mobile";
    headers["X-Client-Platform"] = getPlatformName();
  }
  return headers;
}

export async function requestJson(path, options = {}) {
  const startedAt = Date.now();
  const requestId = options.requestId || `req-${startedAt}`;
  
  let headers = buildDefaultHeaders(options.headers || {});
  const token = localStorage.getItem("access_token");
  if (token && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let response = await fetch(`${API_BASE_URL}${resolveApiPath(path)}`, {
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
        response = await fetch(`${API_BASE_URL}${resolveApiPath(path)}`, {
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
  const contentType = response.headers?.get("content-type") || "";
  const looksLikeHtml =
    /text\/html/i.test(contentType) || rawText.trim().startsWith("<!doctype") || rawText.trim().startsWith("<!DOCTYPE");

  if (response.ok && looksLikeHtml) {
    const error = new Error(
      "Server returned a web page instead of API data. Try again in a moment.",
    );
    error.meta = {
      ok: false,
      status: response.status,
      data: null,
      rawText,
      elapsedMs,
      requestId,
    };
    throw error;
  }

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
  const result = await requestJson("/api/health", { headers });
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

// Phase 5 feedback loop: rate an answer (thumbs up/down + optional comment).
// `payload` = { run_id, rating: "up" | "down", comment? }.
export async function submitAnswerFeedback(payload, headers = {}) {
  const result = await requestJson("/query/feedback", {
    method: "POST",
    body: payload,
    headers,
  });
  return result;
}

export async function fetchCorpusSync(municipality) {
  const query = municipality ? `?municipality=${encodeURIComponent(municipality)}` : "";
  return await requestJson(`/corpus/sync${query}`);
}

export async function postAssetSyncAck(projectId, payload) {
  return await requestJson(`/projects/${projectId}/assets/sync-ack`, {
    method: "POST",
    body: payload,
  });
}

export async function patchProjectRoomSummary(projectId, roomSummary) {
  return await requestJson(`/projects/${projectId}/room-summary`, {
    method: "PATCH",
    body: { room_summary: roomSummary },
  });
}

export async function fetchProjectRoomScans(projectId) {
  return await requestJson(`/projects/${projectId}/room-scans`);
}

export async function postProjectRoomScans(projectId, scans) {
  return await requestJson(`/projects/${projectId}/room-scans`, {
    method: "POST",
    body: { scans },
  });
}

export async function setActiveRoomScan(projectId, scanId) {
  return await requestJson(`/projects/${projectId}/room-scans/${scanId}/active`, {
    method: "PATCH",
  });
}

export async function postDesignIntent(projectId, structureId, roomId, payload) {
  return await postDesignIntentByScan(projectId, roomId, payload);
}

export async function postDesignIntentByScan(projectId, scanId, payload) {
  return await requestJson(
    `/projects/${projectId}/room-scans/${scanId}/design-intent`,
    {
      method: "POST",
      body: payload,
    },
  );
}

export async function postLibraryDesignIntent(scanId, payload) {
  return await requestJson(`/auth/me/room-scans/${scanId}/design-intent`, {
    method: "POST",
    body: payload,
  });
}

export async function searchProducts(query, zipCode = "75034", limit = 3) {
  return await requestJson("/commerce/products/search", {
    method: "POST",
    body: { query, zip_code: zipCode, limit },
  });
}

export async function fetchMaterialsEstimate(projectId) {
  return await requestJson(`/commerce/projects/${projectId}/materials-estimate`);
}

export async function postRoomPreviewImage(payload) {
  return await requestJson("/commerce/room-preview-image", {
    method: "POST",
    body: payload,
  });
}

export async function fetchUserRoomScans() {
  return await requestJson("/auth/me/room-scans");
}

export async function postUserRoomScans(scans) {
  return await requestJson("/auth/me/room-scans", {
    method: "POST",
    body: { scans },
  });
}

export async function linkScansToProject(projectId, scanIds, activeScanId = null) {
  return await requestJson(`/projects/${projectId}/room-scans/link`, {
    method: "POST",
    body: { scan_ids: scanIds, active_scan_id: activeScanId },
  });
}

export async function unlinkScanFromProject(projectId, scanId) {
  return await requestJson(`/projects/${projectId}/room-scans/${scanId}`, {
    method: "DELETE",
  });
}

export async function fetchProject(projectId) {
  return await requestJson(`/projects/${projectId}`);
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

export async function setActiveProjectApi(projectId) {
  return await requestJson("/auth/me/active-project", {
    method: "PATCH",
    body: { project_id: projectId },
  });
}

// ── Project Endpoints ────────────────────────────────────────

export async function fetchProjects({ status, search, hasRoomScans } = {}) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (search) params.set("search", search);
  if (hasRoomScans !== undefined) params.set("has_room_scans", hasRoomScans);
  const query = params.toString();
  return await requestJson(`/projects/${query ? `?${query}` : ""}`);
}

export async function fetchDeletedProjects() {
  return await requestJson("/projects/trash");
}

export async function createProject(payload) {
  return await requestJson("/projects/", {
    method: "POST",
    body: payload,
  });
}

export async function postKickoffChat(payload) {
  return await requestJson("/projects/kickoff/chat", {
    method: "POST",
    body: payload,
  });
}

export async function updateProject(projectId, payload) {
  return await requestJson(`/projects/${projectId}`, {
    method: "PATCH",
    body: payload,
  });
}

export async function getProject(projectId) {
  return await requestJson(`/projects/${projectId}`);
}

export async function setProjectStatus(projectId, isArchived) {
  return await requestJson(`/projects/${projectId}/status`, {
    method: "PATCH",
    body: { is_archived: isArchived },
  });
}

export async function deleteProject(projectId) {
  // Soft delete — moves the project to the trash view, room scans are kept.
  return await requestJson(`/projects/${projectId}`, {
    method: "DELETE",
  });
}

export async function restoreProject(projectId) {
  return await requestJson(`/projects/${projectId}/restore`, {
    method: "POST",
  });
}

export async function hardDeleteProject(projectId) {
  return await requestJson(`/projects/${projectId}/permanent`, {
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

// Admin governance routes require an admin-role login. Auth is handled by
// requestJson's automatic Authorization: Bearer <access_token> header --
// no separate admin token is collected or sent from the browser.

export async function updateDocumentAdmin(docId, body) {
  return await requestJson(`/admin/documents/${encodeURIComponent(docId)}`, {
    method: "PATCH",
    body,
  });
}

export async function supersedeDocumentAdmin(docId, body) {
  return await requestJson(`/admin/documents/${encodeURIComponent(docId)}/supersede`, {
    method: "POST",
    body,
  });
}

export async function pullPage(payload) {
  return await requestJson("/admin/documents/pull-page", {
    method: "POST",
    body: payload,
  });
}

export async function getPullJob(jobId) {
  return await requestJson(`/admin/documents/pull-jobs/${encodeURIComponent(jobId)}`);
}

export async function purgeDocumentAdmin(docId) {
  return await requestJson(`/admin/documents/${encodeURIComponent(docId)}/purge-project-upload`, {
    method: "POST",
  });
}

// ── Superadmin Agent Dashboard (Phase 3) ─────────────────────
// All routes are superadmin-only; the backend returns 403 otherwise. Auth rides
// on requestJson's automatic Bearer header.

export async function listAgentActionItems({ status = "open", sourceAgent = null } = {}) {
  const params = new URLSearchParams({ status });
  if (sourceAgent) params.set("source_agent", sourceAgent);
  return await requestJson(`/admin/agents/action-items?${params.toString()}`);
}

export async function resolveAgentActionItem(itemId, body) {
  return await requestJson(`/admin/agents/action-items/${encodeURIComponent(itemId)}/resolve`, {
    method: "POST",
    body,
  });
}

export async function listMetadataReview({ status = "open" } = {}) {
  const params = new URLSearchParams({ status });
  return await requestJson(`/admin/agents/metadata-review?${params.toString()}`);
}

export async function applyMetadataCorrection(docId, body) {
  return await requestJson(`/admin/agents/metadata-review/${encodeURIComponent(docId)}/apply`, {
    method: "POST",
    body,
  });
}

export async function listCorpusDocuments({ status = null, municipality = null } = {}) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (municipality) params.set("municipality", municipality);
  const qs = params.toString();
  return await requestJson(`/admin/agents/documents${qs ? `?${qs}` : ""}`);
}

export { API_BASE_URL, DEFAULT_BASE_URL };
