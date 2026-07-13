/**
 * roomPreviewImage.test.js — stamp asset_url on overlays.
 */

import test from "node:test";
import assert from "node:assert/strict";
import {
  generatedPreviewRelativePath,
  stampAssetUrl,
} from "./roomPreviewImage.js";

test("stampAssetUrl sets asset_url on each overlay", () => {
  const stamped = stampAssetUrl(
    [{ type: "tile", product_ref: { image_url: "https://x" } }],
    "room_scans/library/s/rooms/r/generated_preview.png",
  );
  assert.equal(stamped[0].asset_url, "room_scans/library/s/rooms/r/generated_preview.png");
  assert.equal(stamped[0].product_ref.image_url, "https://x");
});

test("generatedPreviewRelativePath nests under room folder", () => {
  const path = generatedPreviewRelativePath("library", "struct1", "room1");
  assert.equal(path, "room_scans/library/struct1/rooms/room1/generated_preview.png");
});
