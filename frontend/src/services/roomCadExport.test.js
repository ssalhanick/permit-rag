import test from "node:test";
import assert from "node:assert/strict";

import {
  buildRoomDxf,
  overlayRectsFromDesign,
  wallSegmentsFromCapture,
} from "./roomCadExport.js";

test("wallSegmentsFromCapture builds one segment per wall", () => {
  const capture = {
    surfaces: [
      { category: "wall", dimensions: { width: 2.5 } },
      { category: "wall", dimensions: { width: 3.0 } },
      { category: "floor", dimensions: { width: 4 } },
    ],
  };
  const segments = wallSegmentsFromCapture(capture);
  assert.equal(segments.length, 2);
  assert.equal(segments[0].x2 - segments[0].x1, 2.5);
});

test("overlayRectsFromDesign maps overlays to layers", () => {
  const surfaces = [
    { id: "w1", category: "wall" },
    { id: "w2", category: "wall" },
  ];
  const segments = [
    { x1: 0, y1: 0, x2: 2, y2: 0 },
    { x1: 2.1, y1: 0, x2: 5, y2: 0 },
  ];
  const rects = overlayRectsFromDesign(
    [{ type: "tile", surface_id: "w2" }],
    surfaces,
    segments,
  );
  assert.equal(rects[0].layer, "TILE");
});

test("buildRoomDxf includes WALLS layer and EOF", () => {
  const dxf = buildRoomDxf({
    capture: {
      surfaces: [{ category: "wall", dimensions: { width: 2 } }],
    },
    overlays: [{ type: "paint", surface_id: null }],
  });
  assert.ok(dxf.includes("WALLS"));
  assert.ok(dxf.includes("PAINT"));
  assert.ok(dxf.endsWith("EOF"));
});
