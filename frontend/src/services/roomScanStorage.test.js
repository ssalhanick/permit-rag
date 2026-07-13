import test from "node:test";
import assert from "node:assert/strict";
import {
  getLatestRoomScan,
  loadRoomScans,
  saveRoomScan,
  scanStorageKey,
} from "./roomScanStorage.js";
import { buildRoomSummaryForSync, buildStructureSyncRows, buildComplianceChecks } from "./roomMetrics.js";

const mockStorage = () => {
  const store = new Map();
  globalThis.localStorage = {
    getItem: (key) => store.get(key) ?? null,
    setItem: (key, value) => store.set(key, value),
    removeItem: (key) => store.delete(key),
  };
};

test("scanStorageKey is project-scoped", () => {
  assert.equal(scanStorageKey("abc-123"), "permit_rag_room_scans_abc-123");
});

test("saveRoomScan appends to manifest", async () => {
  mockStorage();
  const scan = {
    schema_version: "1.0",
    room_label: "kitchen",
    surfaces: [{ category: "wall", dimensions: { width: 3, height: 2.4 } }],
  };
  await saveRoomScan("proj-1", scan);
  const loaded = await Promise.resolve(loadRoomScans("proj-1"));
  assert.equal(loaded.length, 1);
  assert.equal(loaded[0].room_label, "kitchen");
  assert.ok(loaded[0].saved_at);
});

test("getLatestRoomScan returns most recent entry", async () => {
  mockStorage();
  await saveRoomScan("proj-2", { room_label: "first" });
  await saveRoomScan("proj-2", { room_label: "second" });
  const latest = await getLatestRoomScan("proj-2");
  assert.equal(latest.room_label, "second");
});

test("buildRoomSummaryForSync excludes raw surfaces", () => {
  const summary = buildRoomSummaryForSync({
    schema_version: "1.0",
    room_label: "bath",
    captured_at: "2026-07-11T10:00:00Z",
    units: "meters",
    surfaces: [
      { category: "wall", dimensions: { width: 2, height: 2.4 } },
      { category: "door", dimensions: { width: 0.9, height: 2 } },
    ],
  });
  assert.equal(summary.room_label, "bath");
  assert.equal(summary.derived.wall_count, 1);
  assert.equal(summary.surfaces, undefined);
});

test("buildStructureSyncRows creates structure and room rows", () => {
  const structureId = "00000000-0000-4000-8000-000000000001";
  const roomId = "00000000-0000-4000-8000-000000000002";
  const rows = buildStructureSyncRows({
    structure_id: structureId,
    structure_label: "House",
    captured_at: "2026-07-12T10:00:00Z",
    rooms: [
      {
        room_id: roomId,
        label: "Kitchen",
        section: "kitchen",
        surfaces: [{ category: "wall", dimensions: { width: 3, height: 2.4 } }],
        is_active: true,
      },
    ],
  });
  assert.equal(rows.length, 2);
  assert.equal(rows[0].scan_type, "structure");
  assert.equal(rows[1].scan_type, "room");
  assert.equal(rows[1].is_active, true);
});

test("buildComplianceChecks flags low ceiling", () => {
  const checks = buildComplianceChecks({
    wall_lengths_m: [1.0],
    max_ceiling_height_m: 2.0,
  });
  assert.ok(checks.some((c) => c.id === "ceiling_height" && !c.pass));
});
