/**
 * roomMetrics.js — derive permit-relevant scalars from RoomCapture JSON schema v1.0.
 */

import { newScanId } from "./scanIds.js";

/**
 * @typedef {{ category: string, dimensions?: { width?: number, height?: number, depth?: number }, position?: { x?: number, y?: number, z?: number }, transform_matrix?: number[] }} Surface
 */

/**
 * Planar area of a surface bounding box: the product of its two largest extents.
 *
 * RoomPlan surfaces are flat, so one of width/height/depth is the thickness.
 * Taking the two largest extents gets the face area without depending on which
 * axis the thickness lands on for a given surface category.
 *
 * @param {{ width?: number, height?: number, depth?: number }} [dimensions]
 * @returns {number}
 */
function planarArea(dimensions) {
  const extents = [dimensions?.width, dimensions?.height, dimensions?.depth]
    .map((v) => (typeof v === "number" && v > 0 ? v : 0))
    .sort((a, b) => b - a);
  return extents[0] * extents[1];
}

/**
 * Footprint area from the bounding box of the wall endpoints in the ground plane.
 *
 * Fallback for iOS 16 captures, which carry no floor surface. Exact for
 * rectangular rooms and an over-estimate for L-shaped ones, so callers must
 * treat it as an estimate — see floor_area_source on deriveRoomMetrics.
 *
 * @param {Surface[]} walls
 * @returns {number | null}
 */
function wallFootprintArea(walls) {
  let minX = Infinity;
  let maxX = -Infinity;
  let minZ = Infinity;
  let maxZ = -Infinity;
  let usable = 0;

  for (const wall of walls) {
    const m = wall.transform_matrix;
    const width = wall.dimensions?.width ?? 0;
    if (!Array.isArray(m) || m.length < 16 || width <= 0) {
      continue;
    }
    // Column 0 of the transform is the wall's local x axis — its run direction.
    const half = width / 2;
    const cx = m[12];
    const cz = m[14];
    for (const sign of [-1, 1]) {
      const x = cx + sign * half * m[0];
      const z = cz + sign * half * m[2];
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minZ = Math.min(minZ, z);
      maxZ = Math.max(maxZ, z);
    }
    usable += 1;
  }

  if (usable < 3) {
    return null;
  }
  const area = (maxX - minX) * (maxZ - minZ);
  return area > 0 ? area : null;
}

/**
 * Compute derived room metrics from interchange-format scan.
 *
 * floor_area_sqm comes from the captured floor surface when present. When it
 * cannot be established it is null rather than a wrong number — every consumer
 * must handle that. wall_area_sqm is the paintable wall face area.
 *
 * @param {{ surfaces?: Surface[], units?: string }} room
 * @returns {{ floor_area_sqm: number | null, floor_area_source: string | null, wall_area_sqm: number, max_ceiling_height_m: number, wall_count: number, wall_lengths_m: number[] }}
 */
export function deriveRoomMetrics(room) {
  const surfaces = room?.surfaces || [];
  const walls = surfaces.filter((s) => s.category === "wall");
  const floors = surfaces.filter((s) => s.category === "floor");

  let wallArea = 0;
  const wallLengths = [];
  for (const wall of walls) {
    const w = wall.dimensions?.width ?? 0;
    const h = wall.dimensions?.height ?? 0;
    wallArea += w * h;
    if (w > 0) {
      wallLengths.push(Number(w.toFixed(2)));
    }
  }
  const heights = walls.map((w) => w.dimensions?.height ?? 0);
  const maxHeight = heights.length ? Math.max(...heights) : 0;

  let floorArea = null;
  let floorAreaSource = null;
  if (floors.length) {
    const summed = floors.reduce((total, floor) => total + planarArea(floor.dimensions), 0);
    if (summed > 0) {
      floorArea = summed;
      floorAreaSource = "floor_surface";
    }
  }
  if (floorArea === null) {
    const footprint = wallFootprintArea(walls);
    if (footprint !== null) {
      floorArea = footprint;
      floorAreaSource = "wall_footprint";
    }
  }

  return {
    floor_area_sqm: floorArea === null ? null : Number(floorArea.toFixed(2)),
    floor_area_source: floorAreaSource,
    wall_area_sqm: Number(wallArea.toFixed(2)),
    max_ceiling_height_m: Number(maxHeight.toFixed(2)),
    wall_count: walls.length,
    wall_lengths_m: wallLengths,
  };
}

/**
 * Build derived summary payload for PATCH /room-summary (no raw surfaces).
 *
 * @param {object} captureResult
 * @returns {object}
 */
export function buildRoomSummaryForSync(captureResult) {
  const derived = deriveRoomMetrics(captureResult);
  return {
    schema_version: captureResult.schema_version || "1.0",
    scan_type: captureResult.scan_type || "room",
    room_label: captureResult.room_label || "room",
    section: captureResult.section || null,
    captured_at: captureResult.captured_at || new Date().toISOString(),
    units: captureResult.units || "meters",
    derived,
  };
}

/**
 * Build A+C sync rows for a structure scan (derived only).
 *
 * @param {object} structureScan
 * @returns {object[]}
 */
export function buildStructureSyncRows(structureScan) {
  const structureId = structureScan.structure_id || structureScan.id;
  const capturedAt = structureScan.captured_at || new Date().toISOString();
  const rows = [
    {
      id: structureId,
      scan_type: "structure",
      parent_scan_id: null,
      room_label: structureScan.structure_label || "Whole house",
      section: null,
      captured_at: capturedAt,
      derived: {
        room_count: (structureScan.rooms || []).length,
        schema_version: structureScan.schema_version || "2.0",
      },
      structure_label: structureScan.structure_label || "Whole house",
      is_active: false,
    },
  ];
  for (const room of structureScan.rooms || []) {
    rows.push({
      id: room.room_id,
      scan_type: "room",
      parent_scan_id: structureId,
      room_label: room.label || room.room_label || "Room",
      section: room.section || null,
      captured_at: capturedAt,
      derived: room.derived || deriveRoomMetrics(room),
      is_active: Boolean(room.is_active),
    });
  }
  if (!rows.some((r) => r.is_active) && rows.length > 1) {
    rows[1].is_active = true;
  }
  return rows;
}

/**
 * Build A+C sync row for a single room scan.
 *
 * @param {object} captureResult
 * @param {{ is_active?: boolean, parent_scan_id?: string }} opts
 * @returns {object}
 */
export function buildRoomScanSyncRow(captureResult, opts = {}) {
  const summary = buildRoomSummaryForSync(captureResult);
  return {
    id: captureResult.room_id || captureResult.id || newScanId(),
    scan_type: "room",
    parent_scan_id: opts.parent_scan_id || null,
    room_label: summary.room_label,
    section: summary.section,
    captured_at: summary.captured_at,
    derived: summary.derived,
    is_active: opts.is_active !== false,
  };
}

/**
 * Compliance checks for a derived room payload.
 *
 * @param {object} derived
 * @returns {{ id: string, pass: boolean, message: string }[]}
 */
export function buildComplianceChecks(derived) {
  const checks = [];
  const lengths = derived?.wall_lengths_m || [];
  if (lengths.length) {
    const minWidth = Math.min(...lengths);
    checks.push({
      id: "min_width",
      ...checkMinWidth(minWidth),
    });
  }
  if (derived?.max_ceiling_height_m != null) {
    const pass = derived.max_ceiling_height_m >= 2.1;
    checks.push({
      id: "ceiling_height",
      pass,
      message: pass
        ? `Ceiling height ${derived.max_ceiling_height_m}m meets typical 2.1m minimum.`
        : `Ceiling height ${derived.max_ceiling_height_m}m may be below typical 2.1m minimum.`,
    });
  }
  return checks;
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
