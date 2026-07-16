/**
 * roomDesignIntent.js — voice/text remodel intent → overlay patches.
 */

import {
  postDesignIntentByScan,
  postLibraryDesignIntent,
} from "../api.js";
import { saveRevision } from "./designHistory.js";
import { applyMaterial, startSpeechRecognition } from "./roomCapture.js";
import { MATERIAL_CATALOG } from "./materialCatalog.js";

/**
 * Preview design intent via cloud LLM (no device persistence).
 *
 * @param {object} opts
 * @returns {Promise<{ overlays: object[], explanation: string, productCandidates: object[], usage: object }>}
 */
export async function previewDesignIntent(opts) {
  const {
    projectId,
    scanId,
    utterance,
    roomLabel,
    roomDerived,
    surfaceHints,
    selectedSurfaceId,
    libraryMode = false,
  } = opts;

  const payload = {
    utterance,
    room_label: roomLabel,
    room_derived: roomDerived,
    surface_hints: surfaceHints,
    selected_surface_id: selectedSurfaceId,
  };

  const result = libraryMode
    ? await postLibraryDesignIntent(scanId, payload)
    : await postDesignIntentByScan(projectId, scanId, payload);

  return {
    overlays: result.data?.overlays || [],
    explanation: result.data?.explanation || "",
    productCandidates: result.data?.product_candidates || [],
    usage: result.data?.usage || { input_tokens: 0, output_tokens: 0, model: "unknown" },
  };
}

/**
 * Persist the last preview as a saved revision (no API call).
 *
 * @param {object} opts
 * @returns {Promise<object>}
 */
export async function saveDesignPreview(opts) {
  const {
    scope,
    structureId,
    roomId,
    utterance,
    explanation,
    overlays,
    parentRevisionId = null,
  } = opts;

  return saveRevision(scope, structureId, roomId, {
    utterance,
    explanation,
    overlays,
    parentRevisionId,
  });
}

/**
 * Apply overlays to native AR session (optional live preview).
 *
 * @param {object} opts
 * @returns {Promise<void>}
 */
export async function applyOverlaysToAR(opts) {
  const { projectId, structureId, roomId, overlays } = opts;
  for (const overlay of overlays || []) {
    try {
      await applyMaterial({
        projectId,
        structureId,
        roomId,
        surfaceId: overlay.surface_id,
        materialId: overlay.material_id,
        colorHex: overlay.color_hex,
        type: overlay.type,
        imageUrl: overlay.product_ref?.image_url || overlay.image_url,
        assetUrl: overlay.asset_url || null,
        productRef: overlay.product_ref,
      });
    } catch {
      // native AR may be unavailable on web
    }
  }
}

/**
 * Send utterance to design-intent API and persist overlays on device (legacy).
 *
 * @param {object} opts
 * @returns {Promise<{ overlays: object[], explanation: string, redesign: object }>}
 */
export async function applyDesignIntent(opts) {
  const preview = await previewDesignIntent({
    projectId: opts.projectId,
    scanId: opts.roomId,
    utterance: opts.utterance,
    roomLabel: opts.roomLabel,
    roomDerived: opts.roomDerived,
    surfaceHints: opts.surfaceHints,
    libraryMode: opts.libraryMode,
  });

  const redesign = await saveDesignPreview({
    scope: opts.scope || opts.projectId,
    structureId: opts.structureId,
    roomId: opts.roomId,
    utterance: opts.utterance,
    explanation: preview.explanation,
    overlays: preview.overlays,
  });

  await applyOverlaysToAR({
    projectId: opts.projectId || opts.scope,
    structureId: opts.structureId,
    roomId: opts.roomId,
    overlays: preview.overlays,
  });

  return {
    overlays: preview.overlays,
    explanation: preview.explanation,
    redesign,
    productCandidates: preview.productCandidates,
  };
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
