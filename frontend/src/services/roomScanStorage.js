/**
 * roomScanStorage.js — on-device room scan persistence (JSON per project).
 */

const STORAGE_PREFIX = "permit_rag_room_scans_";

/**
 * Build localStorage key for a project's scan manifest.
 *
 * @param {string} projectId
 * @returns {string}
 */
export function scanStorageKey(projectId) {
  return `${STORAGE_PREFIX}${projectId}`;
}

/**
 * Load all saved scans for a project.
 *
 * @param {string} projectId
 * @returns {object[]}
 */
export function loadRoomScans(projectId) {
  if (!projectId || typeof localStorage === "undefined") {
    return [];
  }
  const raw = localStorage.getItem(scanStorageKey(projectId));
  if (!raw) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/**
 * Append a scan to the project manifest (full interchange JSON kept on device).
 *
 * @param {string} projectId
 * @param {object} scan
 * @returns {object[]}
 */
export function saveRoomScan(projectId, scan) {
  const manifest = loadRoomScans(projectId);
  const entry = {
    id: scan.id || `scan_${Date.now()}`,
    saved_at: new Date().toISOString(),
    ...scan,
  };
  manifest.push(entry);
  localStorage.setItem(scanStorageKey(projectId), JSON.stringify(manifest));
  return manifest;
}

/**
 * Return the most recent scan for a project.
 *
 * @param {string} projectId
 * @returns {object | null}
 */
export function getLatestRoomScan(projectId) {
  const scans = loadRoomScans(projectId);
  return scans.length ? scans[scans.length - 1] : null;
}
