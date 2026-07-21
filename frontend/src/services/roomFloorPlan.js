/**
 * roomFloorPlan.js — projects capture.json surfaces (transform_matrix + dimensions)
 * into a top-down 2D layout for RoomFloorPlanMap.jsx.
 *
 * Mirrors the column-major 4x4 transform convention used natively in
 * RoomARPresenter.swift's transformMatrix(from:) / RealityKit's simd_float4x4:
 * columns 0/1/2 are the local X/Y/Z basis vectors, column 3 is translation.
 */

/**
 * Transform a local-space point through a flattened 16-value column-major matrix.
 * Returns null if the matrix is missing/malformed.
 *
 * @param {number[] | undefined} matrixArray
 * @param {[number, number, number]} point
 * @returns {{ x: number, y: number, z: number } | null}
 */
export function applyTransform(matrixArray, [lx, ly, lz]) {
  if (!Array.isArray(matrixArray) || matrixArray.length !== 16) {
    return null;
  }
  const m = matrixArray;
  return {
    x: m[0] * lx + m[4] * ly + m[8] * lz + m[12],
    y: m[1] * lx + m[5] * ly + m[9] * lz + m[13],
    z: m[2] * lx + m[6] * ly + m[10] * lz + m[14],
  };
}

/**
 * Project one surface into a top-down (x, z) shape.
 * Walls/doors/windows/openings become a line segment along their local X axis;
 * floors become a 4-point rectangle spanning their local X/Z extents.
 *
 * @param {object} surface — capture.json surface { id, category, dimensions, transform_matrix }
 * @returns {{ id: string, category: string, kind: "line", x1: number, y1: number, x2: number, y2: number }
 *          | { id: string, category: string, kind: "polygon", points: [number, number][] }
 *          | null}
 */
export function projectSurfaceToPlan(surface) {
  const category = surface?.category;
  const width = surface?.dimensions?.width ?? 1;
  const depth = surface?.dimensions?.depth ?? 1;
  const matrix = surface?.transform_matrix;

  if (category === "floor") {
    const corners = [
      [-width / 2, 0, -depth / 2],
      [width / 2, 0, -depth / 2],
      [width / 2, 0, depth / 2],
      [-width / 2, 0, depth / 2],
    ].map((p) => applyTransform(matrix, p));
    if (corners.some((c) => !c)) {
      return null;
    }
    return {
      id: surface.id,
      category,
      kind: "polygon",
      points: corners.map((c) => [c.x, c.z]),
    };
  }

  const p1 = applyTransform(matrix, [-width / 2, 0, 0]);
  const p2 = applyTransform(matrix, [width / 2, 0, 0]);
  if (!p1 || !p2) {
    return null;
  }
  return {
    id: surface.id,
    category,
    kind: "line",
    x1: p1.x,
    y1: p1.z,
    x2: p2.x,
    y2: p2.z,
  };
}

/**
 * Axis-aligned bounding box over a set of projected shapes.
 *
 * @param {ReturnType<typeof projectSurfaceToPlan>[]} shapes
 * @returns {{ minX: number, maxX: number, minY: number, maxY: number }}
 */
export function boundsForShapes(shapes) {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  const consider = (x, y) => {
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  };
  for (const shape of shapes) {
    if (!shape) continue;
    if (shape.kind === "line") {
      consider(shape.x1, shape.y1);
      consider(shape.x2, shape.y2);
    } else if (shape.kind === "polygon") {
      shape.points.forEach(([x, y]) => consider(x, y));
    }
  }
  if (!Number.isFinite(minX)) {
    return { minX: 0, maxX: 1, minY: 0, maxY: 1 };
  }
  return { minX, maxX, minY, maxY };
}

/**
 * Build the full top-down layout for a capture's surfaces, grouped by category.
 * Floor surfaces are used when present (schema v1.0 captures from iOS 17+
 * devices); older captures without floor data fall back to the wall
 * footprint's bounding box so the map still renders a floor outline.
 *
 * @param {object[]} surfaces — capture.json "surfaces" array
 * @returns {{
 *   walls: ReturnType<typeof projectSurfaceToPlan>[],
 *   doors: ReturnType<typeof projectSurfaceToPlan>[],
 *   windows: ReturnType<typeof projectSurfaceToPlan>[],
 *   openings: ReturnType<typeof projectSurfaceToPlan>[],
 *   floors: ReturnType<typeof projectSurfaceToPlan>[],
 *   bounds: { minX: number, maxX: number, minY: number, maxY: number },
 * }}
 */
export function buildFloorPlanLayout(surfaces) {
  const byCategory = { wall: [], door: [], window: [], opening: [], floor: [] };
  for (const surface of surfaces || []) {
    const shape = projectSurfaceToPlan(surface);
    if (shape && byCategory[surface.category]) {
      byCategory[surface.category].push(shape);
    }
  }

  let floors = byCategory.floor;
  if (floors.length === 0 && byCategory.wall.length > 0) {
    const wallBounds = boundsForShapes(byCategory.wall);
    floors = [
      {
        id: "__fallback_floor",
        category: "floor",
        kind: "polygon",
        points: [
          [wallBounds.minX, wallBounds.minY],
          [wallBounds.maxX, wallBounds.minY],
          [wallBounds.maxX, wallBounds.maxY],
          [wallBounds.minX, wallBounds.maxY],
        ],
      },
    ];
  }

  const bounds = boundsForShapes([...byCategory.wall, ...floors]);

  return {
    walls: byCategory.wall,
    doors: byCategory.door,
    windows: byCategory.window,
    openings: byCategory.opening,
    floors,
    bounds,
  };
}
