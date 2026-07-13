/**
 * scanIds.js — generate UUIDs for scan rows (RDS project_room_scans.id).
 */

/**
 * @returns {string}
 */
export function newScanId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const hex = Date.now().toString(16).padStart(12, "0");
  return `00000000-0000-4000-8000-${hex.slice(-12)}`;
}
