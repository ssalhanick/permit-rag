const DEFAULT_BASE_URL = "http://localhost:8000";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL;

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
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method || "GET",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

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

export { API_BASE_URL, DEFAULT_BASE_URL };
