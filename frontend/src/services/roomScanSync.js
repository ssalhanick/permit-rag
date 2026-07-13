/**
 * roomScanSync.js — capture → local save → derived summary API sync.
 */

import { patchProjectRoomSummary } from "../api.js";
import { startRoomCapture } from "./roomCapture.js";
import { buildRoomSummaryForSync } from "./roomMetrics.js";
import { saveRoomScan } from "./roomScanStorage.js";

/**
 * Run native room capture, persist full scan locally, sync derived summary only.
 *
 * @param {string} projectId
 * @param {{ room_label?: string }} opts
 * @returns {Promise<{ capture: object, summary: object }>}
 */
export async function captureAndSyncRoom(projectId, opts = {}) {
  const capture = await startRoomCapture(opts);
  if (capture.error) {
    throw new Error(capture.error);
  }
  if (!capture.surfaces?.length) {
    throw new Error("No surfaces detected — scan again with walls visible.");
  }

  saveRoomScan(projectId, capture);
  const summary = buildRoomSummaryForSync(capture);
  await patchProjectRoomSummary(projectId, summary);
  return { capture, summary };
}
