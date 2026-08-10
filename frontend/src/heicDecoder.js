/**
 * heicDecoder.js — HEIC/HEIF → JPEG, lazily loaded.
 * --------------------------------------------------
 * Isolated in its own module so it is the ONLY file that touches the decoder
 * dependency, and so Vite emits it as a separate chunk. avatarUtils.js reaches
 * it through a dynamic import that only fires when a HEIC actually fails native
 * decoding — which means Safari, iOS, and the Capacitor app (whose camera hands
 * back JPEG already) never download it.
 *
 * Licensing note: every maintained HEIC decoder in the JS ecosystem wraps
 * libheif and inherits its LGPL-3.0 license, while this project is MIT. Loading
 * it as a standalone, dynamically-imported chunk is the arrangement that keeps
 * it separable — do not let a bundler inline this into the main chunk.
 */

/**
 * Convert a HEIC/HEIF blob to a JPEG blob the browser can decode natively.
 *
 * @param {Blob} file
 * @returns {Promise<Blob>} a JPEG blob
 * @throws {Error} when the decoder is unavailable or the file is unreadable
 */
export async function decodeHeicToBlob(file) {
  const { heicTo } = await import("heic-to");
  return await heicTo({
    blob: file,
    type: "image/jpeg",
    // Quality only affects this intermediate JPEG — avatarUtils immediately
    // re-encodes the result to a 256px WebP, so it need not be conservative.
    quality: 0.92,
  });
}
