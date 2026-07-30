import test from "node:test";
import assert from "node:assert/strict";
import { checkMinWidth, deriveRoomMetrics } from "./roomMetrics.js";

/**
 * Transform for a wall whose run direction is the given unit axis.
 *
 * Column-major 4x4: columns 0-2 are the local axes, column 3 the translation.
 */
function wallTransform([ax, ay, az], [tx, ty, tz]) {
  return [
    ax, ay, az, 0,
    0, 1, 0, 0,
    0, 0, 1, 0,
    tx, ty, tz, 1,
  ];
}

/** A 4m x 3m room: two 4m walls, two 3m walls, all 2.4m tall. */
function rectangularWalls() {
  return [
    {
      category: "wall",
      dimensions: { width: 4, height: 2.4, depth: 0.1 },
      transform_matrix: wallTransform([1, 0, 0], [0, 1.2, -1.5]),
    },
    {
      category: "wall",
      dimensions: { width: 4, height: 2.4, depth: 0.1 },
      transform_matrix: wallTransform([1, 0, 0], [0, 1.2, 1.5]),
    },
    {
      category: "wall",
      dimensions: { width: 3, height: 2.4, depth: 0.1 },
      transform_matrix: wallTransform([0, 0, 1], [-2, 1.2, 0]),
    },
    {
      category: "wall",
      dimensions: { width: 3, height: 2.4, depth: 0.1 },
      transform_matrix: wallTransform([0, 0, 1], [2, 1.2, 0]),
    },
  ];
}

test("wall_area_sqm sums wall faces; floor area is not derived from them", () => {
  const metrics = deriveRoomMetrics({
    schema_version: "1.0",
    surfaces: [
      { category: "wall", dimensions: { width: 3, height: 2.4 } },
      { category: "wall", dimensions: { width: 4, height: 2.4 } },
    ],
  });
  assert.equal(metrics.wall_count, 2);
  assert.equal(metrics.max_ceiling_height_m, 2.4);
  // 3*2.4 + 4*2.4
  assert.equal(metrics.wall_area_sqm, 16.8);
  // No floor surface and no transforms to fall back on — null, not wall area.
  assert.equal(metrics.floor_area_sqm, null);
  assert.equal(metrics.floor_area_source, null);
});

test("floor_area_sqm comes from the captured floor surface", () => {
  const metrics = deriveRoomMetrics({
    schema_version: "1.0",
    surfaces: [
      ...rectangularWalls(),
      // Thickness can land on any axis; the two largest extents are the face.
      { category: "floor", dimensions: { width: 4, height: 3, depth: 0.05 } },
    ],
  });
  assert.equal(metrics.floor_area_sqm, 12);
  assert.equal(metrics.floor_area_source, "floor_surface");
  // 2*(4*2.4) + 2*(3*2.4)
  assert.equal(metrics.wall_area_sqm, 33.6);
});

test("floor area falls back to the wall footprint when no floor was captured", () => {
  const metrics = deriveRoomMetrics({
    schema_version: "1.0",
    surfaces: rectangularWalls(),
  });
  assert.equal(metrics.floor_area_sqm, 12);
  assert.equal(metrics.floor_area_source, "wall_footprint");
});

test("footprint fallback needs at least three usable walls", () => {
  const metrics = deriveRoomMetrics({
    schema_version: "1.0",
    surfaces: rectangularWalls().slice(0, 2),
  });
  assert.equal(metrics.floor_area_sqm, null);
  assert.equal(metrics.floor_area_source, null);
});

test("doors and windows do not count as walls or floor", () => {
  const metrics = deriveRoomMetrics({
    schema_version: "1.0",
    surfaces: [
      { category: "wall", dimensions: { width: 3, height: 2.4 } },
      { category: "door", dimensions: { width: 0.9, height: 2.1 } },
      { category: "window", dimensions: { width: 1.2, height: 1.4 } },
    ],
  });
  assert.equal(metrics.wall_count, 1);
  assert.equal(metrics.wall_area_sqm, 7.2);
  assert.deepEqual(metrics.wall_lengths_m, [3]);
});

test("empty scan yields no areas", () => {
  const metrics = deriveRoomMetrics({ surfaces: [] });
  assert.equal(metrics.wall_count, 0);
  assert.equal(metrics.wall_area_sqm, 0);
  assert.equal(metrics.floor_area_sqm, null);
});

test("checkMinWidth pass/fail", () => {
  assert.equal(checkMinWidth(0.9).pass, true);
  assert.equal(checkMinWidth(0.5).pass, false);
});
