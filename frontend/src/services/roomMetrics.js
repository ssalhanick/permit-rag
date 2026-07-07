/**
 * roomMetrics.js — derive permit-relevant scalars from RoomCapture JSON schema v1.0.
 */

/**
 * @typedef {{ category: string, dimensions?: { width?: number, height?: number, depth?: number } }} Surface
 */

/**
 * Compute derived room metrics from interchange-format scan.
 *
 * @param {{ surfaces?: Surface[], units?: string }} room
 * @returns {{ floor_area_sqm: number, max_ceiling_height_m: number, wall_count: number }}
 */
export function deriveRoomMetrics(room) {
  const surfaces = room?.surfaces || [];
  const walls = surfaces.filter((s) => s.category === "wall");
  let floorArea = 0;
  for (const wall of walls) {
    const w = wall.dimensions?.width ?? 0;
    const h = wall.dimensions?.height ?? 0;
    floorArea += w * h;
  }
  const heights = walls.map((w) => w.dimensions?.height ?? 0);
  const maxHeight = heights.length ? Math.max(...heights) : 0;
  return {
    floor_area_sqm: Number(floorArea.toFixed(2)),
    max_ceiling_height_m: Number(maxHeight.toFixed(2)),
    wall_count: walls.length,
  };
}

/**
 * Rule-based egress width check (no LLM).
 *
 * @param {number} widthMeters
 * @param {number} minMeters
 * @returns {{ pass: boolean, message: string }}
 */
export function checkMinWidth(widthMeters, minMeters = 0.81) {
  const pass = widthMeters >= minMeters;
  return {
    pass,
    message: pass
      ? `Width ${widthMeters}m meets minimum ${minMeters}m.`
      : `Width ${widthMeters}m below minimum ${minMeters}m.`,
  };
}
