/**
 * mobileUpload.js — Camera / filesystem helpers for native upload.
 */

import { Camera, CameraResultType, CameraSource } from "@capacitor/camera";
import { isNativePlatform } from "../platform.js";
import { classifyAssetSize } from "./assetLifecycle.js";

/**
 * Capture photo via native camera when on device.
 *
 * @returns {Promise<{ blob: Blob, name: string, size_class: string } | null>}
 */
export async function capturePhotoForUpload() {
  if (!isNativePlatform()) {
    return null;
  }
  const photo = await Camera.getPhoto({
    quality: 85,
    resultType: CameraResultType.Uri,
    source: CameraSource.Camera,
  });
  if (!photo.path && !photo.webPath) {
    return null;
  }
  const webPath = photo.webPath || photo.path;
  const resp = await fetch(webPath);
  const blob = await resp.blob();
  return {
    blob,
    name: `site-photo-${Date.now()}.jpg`,
    size_class: classifyAssetSize(blob.size),
  };
}

/**
 * Pick file from native gallery/files when on device.
 *
 * @returns {Promise<{ blob: Blob, name: string, size_class: string } | null>}
 */
export async function pickImageForUpload() {
  if (!isNativePlatform()) {
    return null;
  }
  const photo = await Camera.getPhoto({
    quality: 90,
    resultType: CameraResultType.Uri,
    source: CameraSource.Photos,
  });
  const webPath = photo.webPath || photo.path;
  if (!webPath) {
    return null;
  }
  const resp = await fetch(webPath);
  const blob = await resp.blob();
  return {
    blob,
    name: photo.path?.split("/").pop() || `upload-${Date.now()}.jpg`,
    size_class: classifyAssetSize(blob.size),
  };
}
