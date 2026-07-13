import test from "node:test";
import assert from "node:assert/strict";

import {
  getActiveOverlays,
  migrateRedesignV1toV2,
  resolveScanFilesystemIds,
} from "./designHistory.js";

test("migrateRedesignV1toV2 wraps flat overlays", () => {
  const doc = {
    schema_version: "1.0",
    scan_id: "room-1",
    overlays: [{ type: "tile", material_id: "white_subway_tile" }],
  };
  const migrated = migrateRedesignV1toV2(doc);
  assert.equal(migrated.schema_version, "2.0");
  assert.equal(migrated.revisions.length, 1);
  assert.ok(migrated.active_revision_id);
});

test("migrateRedesignV1toV2 empty overlays yields empty revisions", () => {
  const migrated = migrateRedesignV1toV2({
    schema_version: "1.0",
    scan_id: "room-1",
    overlays: [],
  });
  assert.equal(migrated.revisions.length, 0);
  assert.equal(migrated.active_revision_id, null);
});

test("getActiveOverlays returns revision overlays", () => {
  const doc = {
    schema_version: "2.0",
    active_revision_id: "rev_a",
    revisions: [
      { id: "rev_a", overlays: [{ type: "paint" }] },
      { id: "rev_b", overlays: [{ type: "tile" }] },
    ],
  };
  const overlays = getActiveOverlays(doc);
  assert.equal(overlays[0].type, "paint");
});

test("resolveScanFilesystemIds uses synthetic structure for standalone", () => {
  const ids = resolveScanFilesystemIds({ id: "abc-123", parent_scan_id: null });
  assert.equal(ids.roomId, "abc-123");
  assert.equal(ids.structureId, "room_abc-123");
});

test("resolveScanFilesystemIds uses parent for structure child", () => {
  const ids = resolveScanFilesystemIds({
    id: "room-1",
    parent_scan_id: "struct-9",
  });
  assert.equal(ids.structureId, "struct-9");
  assert.equal(ids.roomId, "room-1");
});
