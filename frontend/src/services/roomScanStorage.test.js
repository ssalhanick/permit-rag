import test from "node:test";
import assert from "node:assert/strict";
import {
  getLatestRoomScan,
  loadRoomScans,
  saveRoomScan,
  scanStorageKey,
} from "./roomScanStorage.js";
import { buildRoomSummaryForSync } from "./roomMetrics.js";

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

test("saveRoomScan appends to manifest", () => {
  mockStorage();
  const scan = {
    schema_version: "1.0",
    room_label: "kitchen",
    surfaces: [{ category: "wall", dimensions: { width: 3, height: 2.4 } }],
  };
  saveRoomScan("proj-1", scan);
  const loaded = loadRoomScans("proj-1");
  assert.equal(loaded.length, 1);
  assert.equal(loaded[0].room_label, "kitchen");
  assert.ok(loaded[0].saved_at);
});

test("getLatestRoomScan returns most recent entry", () => {
  mockStorage();
  saveRoomScan("proj-2", { room_label: "first" });
  saveRoomScan("proj-2", { room_label: "second" });
  assert.equal(getLatestRoomScan("proj-2").room_label, "second");
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
