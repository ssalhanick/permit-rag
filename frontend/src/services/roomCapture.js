/**
 * roomCapture.js — JS bridge to native RoomCapture Capacitor plugin.
 */

import { registerPlugin } from "@capacitor/core";
import { deriveRoomMetrics } from "./roomMetrics.js";

const RoomCapture = registerPlugin("RoomCapture", {
  web: () => import("../plugins/RoomCaptureWeb.js").then((m) => new m.RoomCaptureWeb()),
});

/**
 * Start native single-room scan; returns schema v1.0 JSON + derived metrics.
 *
 * @param {{ room_label?: string }} opts
 * @returns {Promise<object>}
 */
export async function startRoomCapture(opts = {}) {
  const result = await RoomCapture.startCapture({
    room_label: opts.room_label || "room",
  });
  const derived = deriveRoomMetrics(result);
  return {
    ...result,
    derived,
  };
}

/**
 * Start multi-room structure capture; returns schema v2.0 with rooms[].
 *
 * @param {{ structure_label?: string }} opts
 * @returns {Promise<object>}
 */
export async function startStructureCapture(opts = {}) {
  const result = await RoomCapture.startStructureCapture({
    structure_label: opts.structure_label || "Whole house",
  });
  const rooms = (result.rooms || []).map((room) => ({
    ...room,
    derived: room.derived || deriveRoomMetrics(room),
  }));
  return {
    ...result,
    rooms,
  };
}

/**
 * Open room-scoped AR design viewer for one room in a structure.
 *
 * @param {{ projectId: string, structureId: string, roomId: string, roomLabel?: string }} opts
 * @returns {Promise<object>}
 */
export async function openRoomAR(opts) {
  return RoomCapture.openRoomAR(opts);
}

/**
 * Resolve on-device capture path then open AR for a scan row.
 *
 * @param {object} scanRow
 * @param {{ scope: string, roomLabel?: string, selectedSurfaceId?: string }} opts
 * @returns {Promise<object>}
 */
export async function openRoomARForScan(scanRow, opts) {
  const { findRoomFilesystemLocation } = await import("./roomScanFilesystem.js");
  const location = await findRoomFilesystemLocation(opts.scope, scanRow);
  if (!location.capture?.surfaces?.length) {
    throw new Error("Room geometry not found on device. Re-scan this room.");
  }
  return openRoomAR({
    projectId: location.scope,
    structureId: location.structureId,
    roomId: location.roomId,
    roomLabel: opts.roomLabel || scanRow.room_label,
    selectedSurfaceId: opts.selectedSurfaceId,
  });
}

/**
 * Apply a material overlay in the native AR session.
 *
 * @param {object} opts
 * @returns {Promise<object>}
 */
export async function applyMaterial(opts) {
  return RoomCapture.applyMaterial({
    projectId: opts.projectId,
    structureId: opts.structureId,
    roomId: opts.roomId,
    surfaceId: opts.surfaceId,
    materialId: opts.materialId,
    colorHex: opts.colorHex,
    type: opts.type,
    imageUrl: opts.imageUrl,
    assetUrl: opts.assetUrl,
    productRef: opts.productRef,
  });
}

/**
 * Open the on-device QuickLook preview for a room's cached 3D model.
 * The model is exported at capture time; nothing to preview means the
 * capture predates this feature or export failed on-device.
 *
 * @param {string} roomId
 * @returns {Promise<{ previewed: boolean }>}
 */
export async function previewRoomModel(roomId) {
  return RoomCapture.previewRoomModel({ roomId });
}

/**
 * Start native speech recognition for design commands.
 *
 * @returns {Promise<{ transcript: string }>}
 */
export async function startSpeechRecognition() {
  return RoomCapture.startSpeechRecognition();
}

/**
 * Check if room capture is supported on this device.
 *
 * @returns {Promise<boolean>}
 */
export async function isRoomCaptureAvailable() {
  const status = await getRoomCaptureStatus();
  return status.available;
}

/**
 * Probe native room capture plugin with timeout and reason text.
 *
 * @returns {Promise<{ pluginLoaded: boolean, available: boolean, reason: string | null }>}
 */
export async function getRoomCaptureStatus() {
  const timeoutMs = 4000;
  try {
    const result = await Promise.race([
      RoomCapture.isAvailable(),
      new Promise((_, reject) => {
        setTimeout(() => reject(new Error("Room capture plugin timed out. Rebuild the iOS app.")), timeoutMs);
      }),
    ]);
    return {
      pluginLoaded: true,
      available: Boolean(result?.available),
      reason: result?.reason || null,
    };
  } catch (err) {
    return {
      pluginLoaded: false,
      available: false,
      reason: err?.message || "Room capture plugin unavailable.",
    };
  }
}
