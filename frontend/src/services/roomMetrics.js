/**
 * roomMetrics.js — derive permit-relevant scalars from RoomCapture JSON schema v1.0.
 */

import { newScanId } from "./scanIds.js";

/**
 * @typedef {{ category: string, dimensions?: { width?: number, height?: number, depth?: number } }} Surface
 */

/**
 * Compute derived room metrics from interchange-format scan.
 *
 * @param {{ surfaces?: Surface[], units?: string }} room
 * @returns {{ floor_area_sqm: number, max_ceiling_height_m: number, wall_count: number, wall_lengths_m: number[] }}
 */
export function deriveRoomMetrics(room) {
  const surfaces = room?.surfaces || [];
  const walls = surfaces.filter((s) => s.category === "wall");
  let floorArea = 0;
  const wallLengths = [];
  for (const wall of walls) {
    const w = wall.dimensions?.width ?? 0;
    const h = wall.dimensions?.height ?? 0;
    floorArea += w * h;
    if (w > 0) {
      wallLengths.push(Number(w.toFixed(2)));
    }
  }
  const heights = walls.map((w) => w.dimensions?.height ?? 0);
  const maxHeight = heights.length ? Math.max(...heights) : 0;
  return {
    floor_area_sqm: Number(floorArea.toFixed(2)),
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
