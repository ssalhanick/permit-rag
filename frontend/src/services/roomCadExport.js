/**
 * roomCadExport.js — ASCII DXF export for room walls + overlay layers.
 */

/**
 * Format a number for DXF coordinate output.
 *
 * @param {number} value
 * @returns {string}
 */
function fmt(value) {
  return Number(value).toFixed(4);
}

/**
 * Build 2D wall segments from capture surfaces (axis-aligned layout).
 *
 * @param {object} capture
 * @returns {{ x1: number, y1: number, x2: number, y2: number }[]}
 */
export function wallSegmentsFromCapture(capture) {
  const walls = (capture?.surfaces || []).filter((s) => s.category === "wall");
  const segments = [];
  let cursorX = 0;
  for (const wall of walls) {
    const length = wall.dimensions?.width ?? 1;
    segments.push({
      x1: cursorX,
      y1: 0,
      x2: cursorX + length,
      y2: 0,
    });
    cursorX += length + 0.1;
  }
  return segments;
}

/**
 * Build overlay rectangles mapped to wall segments by surface_id index.
 *
 * @param {object[]} overlays
 * @param {object[]} surfaces
 * @param {{ x1: number, y1: number, x2: number, y2: number }[]} segments
 * @returns {{ layer: string, x1: number, y1: number, x2: number, y2: number }[]}
 */
export function overlayRectsFromDesign(overlays, surfaces, segments) {
  const wallSurfaces = surfaces.filter((s) => s.category === "wall");
  const rects = [];
  for (const overlay of overlays || []) {
    const layer = (overlay.type || "OVERLAY").toUpperCase();
    let idx = wallSurfaces.findIndex((s) => s.id === overlay.surface_id);
    if (idx < 0) {
      idx = 0;
    }
    const seg = segments[idx] || segments[0];
    if (!seg) {
      continue;
    }
    rects.push({
      layer,
      x1: seg.x1,
      y1: 0.05,
      x2: seg.x2,
      y2: 0.35,
    });
  }
  return rects;
}

/**
 * Emit a minimal ASCII DXF with WALLS + overlay layers.
 *
 * @param {{ capture: object, overlays: object[] }} opts
 * @returns {string}
 */
export function buildRoomDxf({ capture, overlays }) {
  const surfaces = capture?.surfaces || [];
  const segments = wallSegmentsFromCapture(capture);
  const overlayRects = overlayRectsFromDesign(overlays, surfaces, segments);
  const layers = new Set(["WALLS"]);
  overlayRects.forEach((r) => layers.add(r.layer));

  const lines = [
    "0",
    "SECTION",
    "2",
    "HEADER",
    "0",
    "ENDSEC",
    "0",
    "SECTION",
    "2",
    "TABLES",
    "0",
    "TABLE",
    "2",
    "LAYER",
    "70",
    String(layers.size),
  ];

  for (const layer of layers) {
    lines.push("0", "LAYER", "2", layer, "70", "0", "62", layer === "WALLS" ? "7" : "3", "6", "CONTINUOUS");
  }

  lines.push("0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES");

  for (const seg of segments) {
    lines.push(
      "0", "LINE", "8", "WALLS",
      "10", fmt(seg.x1), "20", fmt(seg.y1), "30", "0.0",
      "11", fmt(seg.x2), "21", fmt(seg.y2), "31", "0.0",
    );
  }

  for (const rect of overlayRects) {
    lines.push(
      "0", "LWPOLYLINE", "8", rect.layer, "90", "4", "70", "1",
      "10", fmt(rect.x1), "20", fmt(rect.y1),
      "10", fmt(rect.x2), "20", fmt(rect.y1),
      "10", fmt(rect.x2), "20", fmt(rect.y2),
      "10", fmt(rect.x1), "20", fmt(rect.y2),
    );
  }

  lines.push("0", "ENDSEC", "0", "EOF");
  return lines.join("\n");
}
