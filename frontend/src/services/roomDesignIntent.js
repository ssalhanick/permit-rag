/**
 * roomDesignIntent.js — voice/text remodel intent → overlay patches.
 */

import { postDesignIntent } from "../api.js";
import { saveRedesignOverlays } from "./roomScanFilesystem.js";
import { applyMaterial, startSpeechRecognition } from "./roomCapture.js";
import { MATERIAL_CATALOG } from "./materialCatalog.js";

/**
 * Send utterance to design-intent API and persist overlays on device.
 *
 * @param {object} opts
 * @returns {Promise<{ overlays: object[], explanation: string, redesign: object }>}
 */
export async function applyDesignIntent(opts) {
  const {
    projectId,
    structureId,
    roomId,
    utterance,
    roomLabel,
    roomDerived,
    surfaceHints,
  } = opts;

  const result = await postDesignIntent(projectId, structureId, roomId, {
    utterance,
    room_label: roomLabel,
    room_derived: roomDerived,
    surface_hints: surfaceHints,
  });
  const overlays = result.data?.overlays || [];
  const explanation = result.data?.explanation || "";

  const redesign = await saveRedesignOverlays(projectId, structureId, roomId, overlays);

  for (const overlay of overlays) {
    try {
      await applyMaterial({
        projectId,
        structureId,
        roomId,
        surfaceId: overlay.surface_id,
        materialId: overlay.material_id,
        colorHex: overlay.color_hex,
        type: overlay.type,
      });
    } catch {
      // native AR may be unavailable on web
    }
  }

  return { overlays, explanation, redesign };
}

/**
 * Capture speech and apply resulting design intent.
 *
 * @param {object} opts
 * @returns {Promise<{ transcript: string, overlays: object[] }>}
 */
export async function applySpeechDesignIntent(opts) {
  const speech = await startSpeechRecognition();
  const transcript = speech?.transcript?.trim();
  if (!transcript) {
    throw new Error("No speech detected.");
  }
  const result = await applyDesignIntent({ ...opts, utterance: transcript });
  return { transcript, overlays: result.overlays };
}

/**
 * List bundled materials for manual picker UI.
 *
 * @returns {object[]}
 */
export function listMaterials() {
  return MATERIAL_CATALOG;
}
