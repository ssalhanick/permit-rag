import test from "node:test";
import assert from "node:assert/strict";

import { avatarUrlFor, initialsFrom, sniffImageType } from "./avatarUtils.js";

// ── initialsFrom ──────────────────────────────────────────────

test("initialsFrom takes the first letter of each of the first two words", () => {
  assert.equal(initialsFrom("Alex Rivera"), "AR");
});

test("initialsFrom uses the first two letters of a single word", () => {
  assert.equal(initialsFrom("scott"), "SC");
});

test("initialsFrom splits auto-derived usernames on their separators", () => {
  // db.client._derive_username emits names like this, so "_" must read as a
  // word break rather than producing "SS" from the first two characters.
  assert.equal(initialsFrom("scott_salhanick"), "SS");
  assert.equal(initialsFrom("scott.salhanick"), "SS");
  assert.equal(initialsFrom("scott-salhanick"), "SS");
});

test("initialsFrom ignores the domain of an email", () => {
  assert.equal(initialsFrom("scott.s@example.com"), "SS");
  assert.equal(initialsFrom("qa@zzz.com"), "QA");
});

test("initialsFrom falls back to ? when there is nothing usable", () => {
  assert.equal(initialsFrom(""), "?");
  assert.equal(initialsFrom("   "), "?");
  assert.equal(initialsFrom(undefined), "?");
  assert.equal(initialsFrom(null), "?");
  assert.equal(initialsFrom("___"), "?");
});

test("initialsFrom never returns more than two characters", () => {
  for (const input of ["a", "Alex Rivera Smith", "x_y_z", "verylongsinglename"]) {
    assert.ok(initialsFrom(input).length <= 2, `too long for ${input}`);
  }
});

// ── avatarUrlFor ──────────────────────────────────────────────

const USER_ID = "11111111-2222-3333-4444-555555555555";

test("avatarUrlFor returns null when the user has no photo", () => {
  assert.equal(avatarUrlFor({ id: USER_ID, avatar_updated_at: null }), null);
  assert.equal(avatarUrlFor({ id: USER_ID }), null);
});

test("avatarUrlFor returns null without an id", () => {
  assert.equal(avatarUrlFor({ avatar_updated_at: "2026-08-10T12:00:00Z" }), null);
  assert.equal(avatarUrlFor(undefined), null);
  assert.equal(avatarUrlFor(null), null);
});

test("avatarUrlFor accepts either id or user_id", () => {
  // Project member rows key the id as user_id; /auth/me uses id.
  const stamp = "2026-08-10T12:00:00Z";
  assert.equal(
    avatarUrlFor({ id: USER_ID, avatar_updated_at: stamp }),
    avatarUrlFor({ user_id: USER_ID, avatar_updated_at: stamp }),
  );
});

test("avatarUrlFor stamps the URL so a replaced photo isn't served from cache", () => {
  const first = avatarUrlFor({ id: USER_ID, avatar_updated_at: "2026-08-10T12:00:00Z" });
  const second = avatarUrlFor({ id: USER_ID, avatar_updated_at: "2026-08-10T13:00:00Z" });
  assert.notEqual(first, second);
  assert.match(first, /\?v=\d+$/);
});

test("avatarUrlFor prefixes the API base so the native app resolves it", () => {
  const url = avatarUrlFor(
    { id: USER_ID, avatar_updated_at: "2026-08-10T12:00:00Z" },
    "https://api.example.com",
  );
  assert.ok(url.startsWith(`https://api.example.com/api/users/${USER_ID}/avatar`));
});

test("avatarUrlFor is same-origin relative when no base is given", () => {
  const url = avatarUrlFor({ id: USER_ID, avatar_updated_at: "2026-08-10T12:00:00Z" });
  assert.ok(url.startsWith(`/api/users/${USER_ID}/avatar`));
});

test("avatarUrlFor survives an unparseable timestamp", () => {
  const url = avatarUrlFor({ id: USER_ID, avatar_updated_at: "not-a-date" });
  assert.ok(url.includes("?v="));
  assert.ok(!url.includes("NaN"));
});

// ── sniffImageType ────────────────────────────────────────────
// Mirrors _sniff_image_mime in api/routes/auth.py; the HEIC brand check is the
// part most likely to be subtly wrong, so it gets the most cases.

const bytes = (...vals) => new Uint8Array(vals);
const ascii = (s) => Array.from(s, (c) => c.charCodeAt(0));
const pad = (arr, n = 16) =>
  new Uint8Array([...arr, ...new Array(Math.max(0, n - arr.length)).fill(0)]);

test("sniffImageType identifies JPEG", () => {
  assert.equal(sniffImageType(pad([0xff, 0xd8, 0xff, 0xe0])), "image/jpeg");
});

test("sniffImageType identifies PNG", () => {
  assert.equal(
    sniffImageType(pad([0x89, ...ascii("PNG"), 0x0d, 0x0a, 0x1a, 0x0a])),
    "image/png",
  );
});

test("sniffImageType identifies WebP", () => {
  const webp = pad([...ascii("RIFF"), 0, 0, 0, 0, ...ascii("WEBP")]);
  assert.equal(sniffImageType(webp), "image/webp");
});

test("sniffImageType identifies every HEIC brand", () => {
  const brands = [
    "heic", "heix", "hevc", "hevx", "heim", "heis", "hevm", "hevs", "mif1", "msf1",
  ];
  for (const brand of brands) {
    const heic = pad([0, 0, 0, 24, ...ascii("ftyp"), ...ascii(brand)]);
    assert.equal(sniffImageType(heic), "image/heic", `brand ${brand}`);
  }
});

test("sniffImageType rejects an ISO-BMFF file that is not HEIC", () => {
  // An MP4 shares the ftyp box structure but has a brand we must not accept.
  const mp4 = pad([0, 0, 0, 24, ...ascii("ftyp"), ...ascii("isom")]);
  assert.equal(sniffImageType(mp4), null);
});

test("sniffImageType rejects a RIFF container that is not WebP", () => {
  const wav = pad([...ascii("RIFF"), 0, 0, 0, 0, ...ascii("WAVE")]);
  assert.equal(sniffImageType(wav), null);
});

test("sniffImageType rejects non-images", () => {
  assert.equal(sniffImageType(pad(ascii("%PDF-1.7"))), null);
  assert.equal(sniffImageType(pad(ascii("#!/bin/sh"))), null);
  assert.equal(sniffImageType(new Uint8Array(0)), null);
});

test("sniffImageType accepts an ArrayBuffer as well as a Uint8Array", () => {
  const view = pad([0xff, 0xd8, 0xff, 0xe0]);
  assert.equal(sniffImageType(view.buffer), "image/jpeg");
});

test("sniffImageType still spots a JPEG in a short read", () => {
  assert.equal(sniffImageType(bytes(0xff, 0xd8, 0xff)), "image/jpeg");
  // Two bytes is not enough to be sure.
  assert.equal(sniffImageType(bytes(0xff, 0xd8)), null);
});
