/**
 * roomPreviewImage.js — generative room preview → device asset_url.
 */

import { Directory, Filesystem } from "@capacitor/filesystem";
import { postRoomPreviewImage } from "../api.js";
import { isNativePlatform } from "../platform.js";
import { roomBasePath } from "./roomScanFilesystem.js";
import { applyOverlaysToAR } from "./roomDesignIntent.js";

/**
 * Relative path for the generated preview image on device.
 *
 * @param {string} scope
 * @param {string} structureId
 * @param {string} roomId
 * @returns {string}
 */
export function generatedPreviewRelativePath(scope, structureId, roomId) {
  return `${roomBasePath(scope, structureId, roomId)}/generated_preview.png`;
}

/**
 * Write base64 image bytes to Directory.Data (native) or return data URL (web).
 *
 * @param {string} relativePath
 * @param {string} imageBase64
 * @param {string} mimeType
 * @returns {Promise<{ assetUrl: string, previewSrc: string }>}
 */
export async function persistGeneratedPreview(relativePath, imageBase64, mimeType) {
  const previewSrc = `data:${mimeType};base64,${imageBase64}`;
  if (!isNativePlatform()) {
    return { assetUrl: previewSrc, previewSrc };
  }
  const parent = relativePath.split("/").slice(0, -1).join("/");
  try {
    await Filesystem.mkdir({ path: parent, directory: Directory.Data, recursive: true });
  } catch {
    // may already exist
  }
  await Filesystem.writeFile({
    path: relativePath,
    data: imageBase64,
    directory: Directory.Data,
  });
  return { assetUrl: relativePath, previewSrc };
}

/**
 * Stamp asset_url onto every overlay patch.
 *
 * @param {object[]} overlays
 * @param {string} assetUrl
 * @returns {object[]}
 */
export function stampAssetUrl(overlays, assetUrl) {
  return (overlays || []).map((row) => ({ ...row, asset_url: assetUrl }));
}

/**
 * Call commerce image API, save on device, stamp overlays, optionally push to AR.
 *
 * @param {object} opts
 * @returns {Promise<{ overlays: object[], previewSrc: string, assetUrl: string, meta: object }>}
 */
export async function generateAndAttachRoomPreview(opts) {
  const {
    utterance,
    roomLabel,
    overlays,
    sourceImageB64 = null,
    scope,
    structureId,
    roomId,
    projectId,
    applyToAr = true,
  } = opts;

  const result = await postRoomPreviewImage({
    utterance,
    room_label: roomLabel,
    overlays,
    source_image_b64: sourceImageB64,
  });
  const imageBase64 = result.data?.image_base64;
  const mimeType = result.data?.mime_type || "image/png";
  if (!imageBase64) {
    throw new Error("No image returned from preview generator.");
  }

  const relativePath = generatedPreviewRelativePath(scope, structureId, roomId);
  const { assetUrl, previewSrc } = await persistGeneratedPreview(
    relativePath,
    imageBase64,
    mimeType,
  );
  const stamped = stampAssetUrl(overlays, assetUrl);

  if (applyToAr && isNativePlatform()) {
    await applyOverlaysToAR({
      projectId: projectId || scope,
      structureId,
      roomId,
      overlays: stamped,
    });
  }

  return {
    overlays: stamped,
    previewSrc,
    assetUrl,
    meta: {
      provider: result.data?.provider,
      model: result.data?.model,
      mock: result.data?.mock,
      prompt: result.data?.prompt,
    },
  };
}
