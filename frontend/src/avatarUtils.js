/**
 * avatarUtils.js — Profile photo helpers (pure; no React, no API client).
 * ------------------------------------------------------------------------
 * Everything here is deliberately dependency-free so it can be tested under
 * `node --test`, which is the only frontend test runner in this repo (there is
 * no jsdom and no component-render setup). Anything needing the DOM lives in
 * resizeImageToSquare, which the tests skip and the manual pass covers.
 */

/** Formats the file picker offers. Bare extensions matter: Chrome has no MIME
 *  mapping for .heic, so a MIME-only accept list greys those files out. */
export const AVATAR_ACCEPT =
  ".jpg,.jpeg,.png,.webp,.heic,.heif,image/jpeg,image/png,image/webp,image/heic,image/heif";

/** Matches MAX_AVATAR_BYTES in api/routes/auth.py — the server re-checks. */
export const MAX_AVATAR_BYTES = 512 * 1024;

const HEIC_BRANDS = new Set([
  "heic", "heix", "hevc", "hevx", "heim", "heis", "hevm", "hevs", "mif1", "msf1",
]);

/** Thrown when an image cannot be decoded, so the UI can show a format-specific
 *  message instead of a generic failure. */
export class AvatarDecodeError extends Error {
  constructor(message) {
    super(message);
    this.name = "AvatarDecodeError";
  }
}

/**
 * Two-letter initials for the fallback avatar.
 *
 * Accepts a username or an email; for an email only the local part is used, so
 * "scott.s@example.com" yields "SS" rather than something with the domain in it.
 *
 * @param {string} [nameOrEmail]
 * @returns {string} 1-2 uppercase characters, or "?" when there is nothing to use
 */
export function initialsFrom(nameOrEmail) {
  const raw = String(nameOrEmail ?? "").trim();
  if (!raw) {
    return "?";
  }
  const local = raw.split("@")[0];
  // Auto-derived usernames use "_", ".", and "-" as separators (db.client
  // ._derive_username), so treat those the same as spaces.
  const words = local.split(/[\s._-]+/).filter(Boolean);
  if (words.length === 0) {
    return "?";
  }
  const letters =
    words.length === 1 ? words[0].slice(0, 2) : words[0][0] + words[1][0];
  return letters.toUpperCase();
}

/**
 * URL for a user's profile photo, or null when they have none.
 *
 * The ?v= stamp is what makes a replaced photo appear immediately: the response
 * carries Cache-Control: max-age=300, so without a changing URL the browser
 * would keep showing the old image for five minutes.
 *
 * @param {{id?: string, user_id?: string, avatar_updated_at?: string|null}} [user]
 * @param {string} [baseUrl] - API origin; "" means same-origin
 * @returns {string|null}
 */
export function avatarUrlFor(user, baseUrl = "") {
  const id = user?.id || user?.user_id;
  if (!id || !user?.avatar_updated_at) {
    return null;
  }
  const stamp = Date.parse(user.avatar_updated_at);
  const version = Number.isNaN(stamp) ? user.avatar_updated_at : stamp;
  return `${baseUrl}/api/users/${id}/avatar?v=${encodeURIComponent(version)}`;
}

/**
 * Identify an image from its leading bytes. Mirrors _sniff_image_mime in
 * api/routes/auth.py.
 *
 * The browser's own File.type is not good enough: Chrome reports "" for .heic
 * because it has no MIME mapping for the extension, and any caller can lie
 * about it anyway.
 *
 * @param {Uint8Array|ArrayBuffer} bytes - at least the first 12 bytes
 * @returns {string|null} a MIME type, or null if unrecognized
 */
export function sniffImageType(bytes) {
  const b = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  if (b.length < 12) {
    // Only JPEG is identifiable in under 12 bytes.
    if (b.length >= 3 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) {
      return "image/jpeg";
    }
    return null;
  }
  const ascii = (start, end) => String.fromCharCode(...b.slice(start, end));

  if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) {
    return "image/jpeg";
  }
  if (ascii(0, 8) === "\x89PNG\r\n\x1a\n") {
    return "image/png";
  }
  if (ascii(0, 4) === "RIFF" && ascii(8, 12) === "WEBP") {
    return "image/webp";
  }
  // HEIC/HEIF is ISO-BMFF: a 4-byte box length, then "ftyp", then the brand.
  if (ascii(4, 8) === "ftyp" && HEIC_BRANDS.has(ascii(8, 12))) {
    return "image/heic";
  }
  return null;
}

/**
 * Decode any accepted image into an ImageBitmap.
 *
 * HEIC is the awkward case. Safari (macOS and iOS) decodes it natively, and the
 * Capacitor camera hands back JPEG already, so the only browsers that need the
 * WASM decoder are desktop Chrome/Firefox/Edge — which is why it is behind a
 * dynamic import. Vite emits it as its own chunk, so users uploading a JPEG
 * never download it.
 */
async function decodeToBitmap(file) {
  // "from-image" honours the EXIF orientation tag. Without it, portrait photos
  // taken on an iPhone render rotated 90 degrees.
  try {
    return await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    /* fall through */
  }

  const head = new Uint8Array(await file.slice(0, 16).arrayBuffer());
  if (sniffImageType(head) === "image/heic") {
    const { decodeHeicToBlob } = await import("./heicDecoder.js");
    const converted = await decodeHeicToBlob(file);
    return await createImageBitmap(converted, { imageOrientation: "from-image" });
  }

  // Older engines reject the options bag itself; retry without it before
  // giving up. Orientation may be wrong here, but a usable photo beats none.
  try {
    return await createImageBitmap(file);
  } catch {
    throw new AvatarDecodeError("Couldn't read that image. Try a JPG or PNG.");
  }
}

function canvasToBlob(canvas, type, quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        // Safari has historically ignored the requested type and returned a
        // PNG, which would blow past the size cap. Treat that as a failure so
        // the caller falls back to JPEG explicitly.
        if (!blob || blob.type !== type) {
          reject(new AvatarDecodeError(`Browser could not encode ${type}.`));
          return;
        }
        resolve(blob);
      },
      type,
      quality,
    );
  });
}

function drawSquare(bitmap, size, { background = null } = {}) {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (background) {
    // JPEG has no alpha; without this, a transparent PNG becomes a black square.
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, size, size);
  }
  // Center-crop to a square so non-square photos aren't distorted by the
  // circular CSS mask every avatar slot applies.
  const side = Math.min(bitmap.width, bitmap.height);
  const sx = (bitmap.width - side) / 2;
  const sy = (bitmap.height - side) / 2;
  ctx.drawImage(bitmap, sx, sy, side, side, 0, 0, size, size);
  return canvas;
}

/**
 * Resize an image to a square thumbnail, ready to upload.
 *
 * This is the load-bearing function of the whole feature: it bounds the upload
 * size, normalizes HEIC/PNG/JPEG down to one stored format, and strips EXIF
 * (including GPS coordinates) as a side effect of re-encoding. The backend can
 * stay free of Pillow and libheif because this runs first.
 *
 * @param {Blob} file
 * @param {{size?: number, quality?: number}} [options]
 * @returns {Promise<Blob>} a WebP (or JPEG, on browsers that can't encode WebP)
 * @throws {AvatarDecodeError} when the image can't be decoded or encoded
 */
export async function resizeImageToSquare(file, { size = 256, quality = 0.85 } = {}) {
  const bitmap = await decodeToBitmap(file);
  try {
    try {
      return await canvasToBlob(drawSquare(bitmap, size), "image/webp", quality);
    } catch {
      // Redraw on white rather than reusing the canvas: the WebP attempt kept
      // transparency, which JPEG would render black.
      return await canvasToBlob(
        drawSquare(bitmap, size, { background: "#ffffff" }),
        "image/jpeg",
        quality,
      );
    }
  } finally {
    bitmap.close?.();
  }
}
