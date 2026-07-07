import test from "node:test";
import assert from "node:assert/strict";
import { checkMinWidth, deriveRoomMetrics } from "./roomMetrics.js";

test("deriveRoomMetrics from walls", () => {
  const metrics = deriveRoomMetrics({
    schema_version: "1.0",
    surfaces: [
      { category: "wall", dimensions: { width: 3, height: 2.4 } },
      { category: "wall", dimensions: { width: 4, height: 2.4 } },
    ],
  });
  assert.equal(metrics.wall_count, 2);
  assert.equal(metrics.max_ceiling_height_m, 2.4);
  assert.ok(metrics.floor_area_sqm > 0);
});

test("checkMinWidth pass/fail", () => {
  assert.equal(checkMinWidth(0.9).pass, true);
  assert.equal(checkMinWidth(0.5).pass, false);
});
