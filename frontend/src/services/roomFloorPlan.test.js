import test from "node:test";
import assert from "node:assert/strict";

import {
  applyTransform,
  boundsForShapes,
  buildFloorPlanLayout,
  projectSurfaceToPlan,
} from "./roomFloorPlan.js";

// Identity matrix (column-major, matches simd_float4x4 / RoomARPresenter.swift).
const IDENTITY = [
  1, 0, 0, 0,
  0, 1, 0, 0,
  0, 0, 1, 0,
  0, 0, 0, 1,
];

// Translated 2m along +x, 3m along +z.
const TRANSLATED = [
  1, 0, 0, 0,
  0, 1, 0, 0,
  0, 0, 1, 0,
  2, 0, 3, 1,
];

test("applyTransform returns null for missing/malformed matrices", () => {
  assert.equal(applyTransform(undefined, [0, 0, 0]), null);
  assert.equal(applyTransform([1, 2, 3], [0, 0, 0]), null);
});

test("applyTransform applies identity as a passthrough", () => {
  const result = applyTransform(IDENTITY, [1, 2, 3]);
  assert.deepEqual(result, { x: 1, y: 2, z: 3 });
});

test("applyTransform applies translation", () => {
  const result = applyTransform(TRANSLATED, [0, 0, 0]);
  assert.deepEqual(result, { x: 2, y: 0, z: 3 });
});

test("projectSurfaceToPlan builds a centered line segment for a wall", () => {
  const wall = {
    id: "room-wall-0",
    category: "wall",
    dimensions: { width: 4, height: 2.4, depth: 0.1 },
    transform_matrix: TRANSLATED,
  };
  const shape = projectSurfaceToPlan(wall);
  assert.equal(shape.kind, "line");
  assert.equal(shape.x1, 2 - 2);
  assert.equal(shape.x2, 2 + 2);
  assert.equal(shape.y1, 3);
  assert.equal(shape.y2, 3);
});

test("projectSurfaceToPlan builds a 4-point polygon for a floor", () => {
  const floor = {
    id: "room-floor-0",
    category: "floor",
    dimensions: { width: 4, height: 0.02, depth: 3 },
    transform_matrix: IDENTITY,
  };
  const shape = projectSurfaceToPlan(floor);
  assert.equal(shape.kind, "polygon");
  assert.equal(shape.points.length, 4);
  assert.deepEqual(shape.points, [
    [-2, -1.5],
    [2, -1.5],
    [2, 1.5],
    [-2, 1.5],
  ]);
});

test("projectSurfaceToPlan returns null without a valid transform_matrix", () => {
  assert.equal(projectSurfaceToPlan({ category: "wall", dimensions: { width: 1 } }), null);
});

test("boundsForShapes computes a bounding box over lines and polygons", () => {
  const bounds = boundsForShapes([
    { kind: "line", x1: -2, y1: 0, x2: 2, y2: 0 },
    { kind: "polygon", points: [[-1, -1], [1, 3]] },
  ]);
  assert.deepEqual(bounds, { minX: -2, maxX: 2, minY: -1, maxY: 3 });
});

test("buildFloorPlanLayout uses real floor surfaces when present", () => {
  const surfaces = [
    { id: "w0", category: "wall", dimensions: { width: 4 }, transform_matrix: IDENTITY },
    { id: "f0", category: "floor", dimensions: { width: 4, depth: 3 }, transform_matrix: IDENTITY },
  ];
  const layout = buildFloorPlanLayout(surfaces);
  assert.equal(layout.walls.length, 1);
  assert.equal(layout.floors.length, 1);
  assert.equal(layout.floors[0].id, "f0");
});

test("buildFloorPlanLayout falls back to the wall bounding box when no floor surface exists", () => {
  const surfaces = [
    { id: "w0", category: "wall", dimensions: { width: 4 }, transform_matrix: IDENTITY },
    { id: "w1", category: "wall", dimensions: { width: 3 }, transform_matrix: TRANSLATED },
  ];
  const layout = buildFloorPlanLayout(surfaces);
  assert.equal(layout.floors.length, 1);
  assert.equal(layout.floors[0].id, "__fallback_floor");
  assert.equal(layout.floors[0].kind, "polygon");
});

test("buildFloorPlanLayout skips surfaces with unrecognized categories", () => {
  const layout = buildFloorPlanLayout([
    { id: "x0", category: "furniture", dimensions: { width: 1 }, transform_matrix: IDENTITY },
  ]);
  assert.equal(layout.walls.length, 0);
  assert.equal(layout.floors.length, 0);
});
