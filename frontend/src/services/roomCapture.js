/**
 * roomCapture.js — JS bridge to native RoomCapture Capacitor plugin.
 */

import { registerPlugin } from "@capacitor/core";
import { deriveRoomMetrics } from "./roomMetrics.js";

const RoomCapture = registerPlugin("RoomCapture", {
  web: () => import("../plugins/RoomCaptureWeb.js").then((m) => new m.RoomCaptureWeb()),
});

/**
 * Start native room scan; returns schema v1.0 JSON + derived metrics.
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
