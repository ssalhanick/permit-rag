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
  try {
    const { available } = await RoomCapture.isAvailable();
    return Boolean(available);
  } catch {
    return false;
  }
}
