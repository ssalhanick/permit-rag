/**
 * roomScanSync.js — capture → user library → optional project link (A+C privacy).
 */

import {
  postProjectRoomScans,
  patchProjectRoomSummary,
  postUserRoomScans,
  setActiveRoomScan,
} from "../api.js";
import { startRoomCapture, startStructureCapture } from "./roomCapture.js";
import {
  buildRoomScanSyncRow,
  buildRoomSummaryForSync,
  buildStructureSyncRows,
  deriveRoomMetrics,
} from "./roomMetrics.js";
import { saveRoomScan, saveToUserLibrary } from "./roomScanStorage.js";
import { newScanId } from "./scanIds.js";

/**
 * Run native room capture, persist full scan locally, sync derived summary only.
 *
 * @param {string} projectId
 * @param {{ room_label?: string, is_active?: boolean }} opts
 * @returns {Promise<{ capture: object, scans: object[] }>}
 */
export async function captureAndSyncRoom(projectId, opts = {}) {
  const capture = await startRoomCapture(opts);
  if (capture.error) {
    throw new Error(capture.error);
  }
  if (!capture.surfaces?.length) {
    throw new Error("No surfaces detected — scan again with walls visible.");
  }

  const roomId = capture.room_id || capture.id || newScanId();
  const enriched = {
    ...capture,
    scan_type: "room",
    room_id: roomId,
    derived: capture.derived || deriveRoomMetrics(capture),
  };
  await saveToUserLibrary(enriched);
  if (projectId) {
    await saveRoomScan(projectId, enriched);
  }

  const row = buildRoomScanSyncRow(enriched, { is_active: opts.is_active !== false });
  const scans = await syncRoomScanRows(projectId, [row], { libraryOnly: !projectId });
  return { capture: enriched, scans };
}

/**
 * Run structure capture (multi-room), persist locally, sync derived rows only.
 *
 * @param {string} projectId
 * @param {{ structure_label?: string }} opts
 * @returns {Promise<{ capture: object, scans: object[] }>}
 */
export async function captureAndSyncStructure(projectId, opts = {}) {
  const capture = await startStructureCapture(opts);
  if (capture.error) {
    throw new Error(capture.error);
  }
  if (!capture.rooms?.length) {
    throw new Error("No rooms detected — scan at least one room.");
  }

  const structureId = capture.structure_id || capture.id || newScanId();
  const enriched = {
    ...capture,
    scan_type: "structure",
    structure_id: structureId,
    structure_label: capture.structure_label || opts.structure_label || "Whole house",
    rooms: capture.rooms.map((room, index) => ({
      ...room,
      derived: room.derived || deriveRoomMetrics(room),
      is_active: index === 0,
    })),
  };
  await saveToUserLibrary(enriched);
  if (projectId) {
    await saveRoomScan(projectId, enriched);
  }

  const rows = buildStructureSyncRows(enriched);
  const scans = await syncRoomScanRows(projectId, rows, { libraryOnly: !projectId });
  return { capture: enriched, scans };
}

/**
 * Upsert derived scan rows via room-scans API (fallback to legacy room-summary).
 *
 * @param {string} projectId
 * @param {object[]} rows
 * @returns {Promise<object[]>}
 */
export async function syncRoomScanRows(projectId, rows, opts = {}) {
  try {
    await postUserRoomScans(rows);
    if (opts.libraryOnly || !projectId) {
      return rows;
    }
    const result = await postProjectRoomScans(projectId, rows);
    return result.data || rows;
  } catch {
    if (!projectId) {
      return rows;
    }
    const active = rows.find((r) => r.scan_type === "room" && r.is_active) || rows[rows.length - 1];
    if (active) {
      const summary = {
        schema_version: "2.0",
        room_label: active.room_label,
        section: active.section,
        captured_at: active.captured_at,
        derived: active.derived,
      };
      await patchProjectRoomSummary(projectId, summary);
    }
    return rows;
  }
}

/**
 * Mark a room scan active in RDS.
 *
 * @param {string} projectId
 * @param {string} scanId
 * @returns {Promise<object>}
 */
export async function activateRoomScan(projectId, scanId) {
  const result = await setActiveRoomScan(projectId, scanId);
  return result.data;
}
