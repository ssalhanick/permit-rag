export function suggestDocIdFromFilename(filename) {
  if (!filename || !filename.trim()) {
    return "";
  }
  return filename
    .replace(/\.[^/.]+$/, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function getUploadBlockers({ file, docId, municipality, adminToken, status }) {
  const blockers = [];
  if (!file) {
    blockers.push("Select a PDF or HTML file.");
  }
  if (!docId.trim()) {
    blockers.push("Enter a document ID.");
  }
  if (!municipality.trim()) {
    blockers.push("Enter a municipality.");
  }
  if (!adminToken.trim()) {
    blockers.push("Enter X-Admin-Token.");
  }
  if (status === "loading") {
    blockers.push("Upload is in progress.");
  }
  return blockers;
}

export function formatUploadError(message) {
  const normalized = (message || "").toLowerCase();
  if (normalized.includes("401") || normalized.includes("invalid or missing admin token")) {
    return "Auth failed. Check X-Admin-Token value.";
  }
  if (normalized.includes("unsupported file type")) {
    return "File type not allowed. Use .pdf, .html, or .htm.";
  }
  if (normalized.includes("failed to fetch")) {
    return "Cannot reach API. Check server, URL, and CORS settings.";
  }
  return message || "Upload failed.";
}
