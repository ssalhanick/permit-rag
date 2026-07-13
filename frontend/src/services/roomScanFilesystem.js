/**
 * roomScanFilesystem.js — durable on-device scan storage via Capacitor Filesystem.
 */

import { Directory, Encoding, Filesystem } from "@capacitor/filesystem";
import { isNativePlatform } from "../platform.js";

const ROOT = "room_scans";
export const LIBRARY_SCOPE = "library";

/**
 * @param {string} scope projectId or library scope
 * @param {string} structureId
 * @returns {string}
 */
export function structureBasePath(scope, structureId) {
  return `${ROOT}/${scope}/${structureId}`;
}

/**
 * @param {string} scope projectId or library scope
 * @param {string} structureId
 * @param {string} roomId
 * @returns {string}
 */
export function roomBasePath(scope, structureId, roomId) {
  return `${structureBasePath(scope, structureId)}/rooms/${roomId}`;
}

/**
 * @returns {boolean}
 */
export function useFilesystemStorage() {
  return isNativePlatform();
}

/**
 * Ensure parent directories exist for a file path.
 *
 * @param {string} filePath
 */
async function ensureParentDir(filePath) {
  const parts = filePath.split("/");
  parts.pop();
  let current = "";
  for (const part of parts) {
    current = current ? `${current}/${part}` : part;
    try {
      await Filesystem.mkdir({ path: current, directory: Directory.Data, recursive: true });
    } catch {
      // directory may already exist
    }
  }
}

/**
 * Write JSON to app data directory.
 *
 * @param {string} path
 * @param {object} data
 */
export async function writeJson(path, data) {
  await ensureParentDir(path);
  await Filesystem.writeFile({
    path,
    data: JSON.stringify(data, null, 2),
    directory: Directory.Data,
    encoding: Encoding.UTF8,
  });
}

/**
 * Read JSON from app data directory.
 *
 * @param {string} path
 * @returns {Promise<object | null>}
 */
export async function readJson(path) {
  try {
    const result = await Filesystem.readFile({
      path,
      directory: Directory.Data,
      encoding: Encoding.UTF8,
    });
    return JSON.parse(result.data);
  } catch {
    return null;
  }
}

/**
 * Persist structure scan v2.0 and per-room capture slices.
 *
 * @param {string} projectId
 * @param {object} structureScan
 * @returns {Promise<object>}
 */
export async function saveStructureScan(scope, structureScan) {
  const structureId = structureScan.structure_id || structureScan.id;
  const base = structureBasePath(scope, structureId);
  await writeJson(`${base}/structure.json`, structureScan);

  const rooms = structureScan.rooms || [];
  for (const room of rooms) {
    const roomId = room.room_id;
    const roomPath = roomBasePath(scope, structureId, roomId);
    await writeJson(`${roomPath}/capture.json`, {
      schema_version: structureScan.schema_version || "2.0",
      scan_type: "room",
      room_id: roomId,
      room_label: room.label,
      section: room.section,
      captured_at: structureScan.captured_at,
      units: structureScan.units || "meters",
      surfaces: room.surfaces || [],
      derived: room.derived,
    });
    await writeJson(`${roomPath}/redesign.json`, {
      schema_version: "1.0",
      scan_id: roomId,
      overlays: [],
    });
  }
  return structureScan;
}

/**
 * Save standalone room scan v1.0 under a synthetic structure id.
 *
 * @param {string} projectId
 * @param {object} roomScan
 * @returns {Promise<object>}
 */
export async function saveRoomScanFile(scope, roomScan) {
  const roomId = roomScan.room_id || roomScan.id || `room_${Date.now()}`;
  const structureId =
    roomScan.parent_scan_id ||
    roomScan.parent_structure_id ||
    roomScan.structure_id ||
    `room_${roomId}`;
  const base = roomBasePath(scope, structureId, roomId);
  await writeJson(`${base}/capture.json`, { ...roomScan, room_id: roomId });
  await writeJson(`${base}/redesign.json`, {
    schema_version: "1.0",
    scan_id: roomId,
    overlays: [],
  });
  return { structureId, roomId, capture: roomScan };
}

/**
 * Load redesign overlays for a room.
 *
 * @param {string} projectId
 * @param {string} structureId
 * @param {string} roomId
 * @returns {Promise<object>}
 */
export async function loadRedesign(scope, structureId, roomId) {
  const path = `${roomBasePath(scope, structureId, roomId)}/redesign.json`;
  return (await readJson(path)) || { schema_version: "1.0", scan_id: roomId, overlays: [] };
}

/**
 * Merge overlay patches into redesign.json.
 *
 * @param {string} projectId
 * @param {string} structureId
 * @param {string} roomId
 * @param {object[]} overlays
 * @returns {Promise<object>}
 */
export async function saveRedesignOverlays(scope, structureId, roomId, overlays) {
  const path = `${roomBasePath(scope, structureId, roomId)}/redesign.json`;
  const current = await loadRedesign(scope, structureId, roomId);
  const merged = {
    ...current,
    overlays: [...(current.overlays || []), ...overlays],
    updated_at: new Date().toISOString(),
  };
  await writeJson(path, merged);
  return merged;
}

/**
 * List structure manifests stored for a scope (reads structure.json files).
 *
 * @param {string} scope projectId or library scope
 * @returns {Promise<object[]>}
 */
export async function listProjectStructures(scope) {
  const projectPath = `${ROOT}/${scope}`;
  try {
    const listing = await Filesystem.readdir({ path: projectPath, directory: Directory.Data });
    const structures = [];
    for (const entry of listing.files || []) {
      if (entry.type !== "directory") {
        continue;
      }
      const structure = await readJson(`${projectPath}/${entry.name}/structure.json`);
      if (structure) {
        structures.push(structure);
      }
    }
    return structures;
  } catch {
    return [];
  }
}

/**
 * List scans in the user's personal on-device library.
 *
 * @returns {Promise<object[]>}
 */
export async function listLibraryStructures() {
  return listProjectStructures(LIBRARY_SCOPE);
}

/**
 * Discover on-disk capture path for a room scan (handles legacy structureId layouts).
 *
 * @param {string} scope projectId or library scope
 * @param {object} scanRow
 * @returns {Promise<{ scope: string, structureId: string, roomId: string, capture: object | null }>}
 */
export async function findRoomFilesystemLocation(scope, scanRow) {
  const roomId = scanRow?.id || scanRow?.room_id;
  if (!roomId) {
    return { scope, structureId: "", roomId: "", capture: null };
  }

  const structureCandidates = [
    scanRow.structure_id,
    scanRow.parent_scan_id,
    `room_${roomId}`,
  ].filter(Boolean);

  const scopes = scope === LIBRARY_SCOPE ? [LIBRARY_SCOPE] : [scope, LIBRARY_SCOPE];

  for (const activeScope of scopes) {
    for (const structureId of [...new Set(structureCandidates)]) {
      const roomIdVariations = [...new Set([roomId, roomId.toLowerCase(), roomId.toUpperCase()])];
      const structureIdVariations = [...new Set([structureId, structureId.toLowerCase(), structureId.toUpperCase()])];

      for (const sId of structureIdVariations) {
        for (const rId of roomIdVariations) {
          const capture = await readJson(`${roomBasePath(activeScope, sId, rId)}/capture.json`);
          if (capture?.surfaces?.length) {
            return { scope: activeScope, structureId: sId, roomId: rId, capture };
          }
        }
      }
    }
    const discovered = await discoverRoomLocation(activeScope, roomId);
    if (discovered) {
      return { scope: activeScope, ...discovered };
    }
  }

  const fallbackStructureId =
    scanRow.parent_scan_id || scanRow.structure_id || `room_${roomId}`;
  return {
    scope,
    structureId: fallbackStructureId,
    roomId,
    capture: null,
  };
}

/**
 * Scan scope directories for any structure folder containing this roomId.
 *
 * @param {string} scope
 * @param {string} roomId
 * @returns {Promise<{ structureId: string, roomId: string, capture: object } | null>}
 */
async function discoverRoomLocation(scope, roomId) {
  const projectPath = `${ROOT}/${scope}`;
  try {
    const listing = await Filesystem.readdir({ path: projectPath, directory: Directory.Data });
    const roomIdVariations = [...new Set([roomId, roomId.toLowerCase(), roomId.toUpperCase()])];
    for (const entry of listing.files || []) {
      if (entry.type !== "directory") {
        continue;
      }
      for (const rId of roomIdVariations) {
        const capture = await readJson(`${roomBasePath(scope, entry.name, rId)}/capture.json`);
        if (capture?.surfaces?.length) {
          return { structureId: entry.name, roomId: rId, capture };
        }
      }
    }
  } catch {
    // scope directory may not exist yet
  }
  return null;
}
