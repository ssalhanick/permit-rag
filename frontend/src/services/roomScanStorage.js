/**
 * roomScanStorage.js — on-device scan manifest (Filesystem on native, localStorage on web).
 */

import { isNativePlatform } from "../platform.js";
import {
  LIBRARY_SCOPE,
  listLibraryStructures,
  listProjectStructures,
  saveRoomScanFile,
  saveStructureScan,
  useFilesystemStorage,
} from "./roomScanFilesystem.js";

const STORAGE_PREFIX = "permit_rag_room_scans_";
const LIBRARY_KEY = "permit_rag_scan_library";

/**
 * Build localStorage key for a project's scan manifest.
 *
 * @param {string} projectId
 * @returns {string}
 */
export function scanStorageKey(projectId) {
  return `${STORAGE_PREFIX}${projectId}`;
}

/**
 * Load manifest from localStorage (web fallback).
 *
 * @param {string} projectId
 * @returns {object[]}
 */
function loadLocalManifest(projectId) {
  if (!projectId || typeof localStorage === "undefined") {
    return [];
  }
  const raw = localStorage.getItem(scanStorageKey(projectId));
  if (!raw) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/**
 * Save manifest to localStorage (web fallback).
 *
 * @param {string} projectId
 * @param {object[]} manifest
 */
function saveLocalManifest(projectId, manifest) {
  localStorage.setItem(scanStorageKey(projectId), JSON.stringify(manifest));
}

/**
 * Load all saved scans for a project.
 *
 * @param {string} projectId
 * @returns {Promise<object[]> | object[]}
 */
export function loadRoomScans(projectId) {
  if (useFilesystemStorage()) {
    return listProjectStructures(projectId).then((structures) => {
      const singles = loadLocalManifest(projectId).filter((s) => s.scan_type === "room");
      return [...structures, ...singles];
    });
  }
  return loadLocalManifest(projectId);
}

/**
 * Append a scan entry to the project manifest.
 *
 * @param {string} projectId
 * @param {object} scan
 * @returns {Promise<object> | object}
 */
export async function saveRoomScan(projectId, scan) {
  const entry = {
    id: scan.room_id || scan.id || scan.structure_id || `scan_${Date.now()}`,
    saved_at: new Date().toISOString(),
    ...scan,
  };

  if (scan.scan_type === "structure" || scan.rooms?.length) {
    entry.scan_type = "structure";
    entry.structure_id = scan.structure_id || entry.id;
    if (useFilesystemStorage()) {
      await saveStructureScan(projectId, entry);
      return entry;
    }
    const manifest = loadLocalManifest(projectId);
    manifest.push(entry);
    saveLocalManifest(projectId, manifest);
    return entry;
  }

  entry.scan_type = "room";
  if (useFilesystemStorage()) {
    const saved = await saveRoomScanFile(projectId, entry);
    entry.structure_id = saved.structureId;
    entry.room_id = saved.roomId;
    const manifest = loadLocalManifest(projectId);
    manifest.push(entry);
    saveLocalManifest(projectId, manifest);
    return entry;
  }
  const manifest = loadLocalManifest(projectId);
  manifest.push(entry);
  saveLocalManifest(projectId, manifest);
  return entry;
}

/**
 * Return the most recent scan for a project.
 *
 * @param {string} projectId
 * @returns {Promise<object | null> | object | null}
 */
export async function getLatestRoomScan(projectId) {
  const scans = await Promise.resolve(loadRoomScans(projectId));
  const list = Array.isArray(scans) ? scans : [];
  return list.length ? list[list.length - 1] : null;
}

/**
 * Find a room slice inside a structure scan.
 *
 * @param {object} structure
 * @param {string} roomId
 * @returns {object | null}
 */
export function getRoomFromStructure(structure, roomId) {
  const rooms = structure?.rooms || [];
  return rooms.find((r) => r.room_id === roomId) || null;
}

/**
 * Load the user's personal scan library from device storage.
 *
 * @returns {Promise<object[]>}
 */
export async function loadUserLibrary() {
  if (useFilesystemStorage()) {
    const library = await listLibraryStructures();
    const local = loadLocalManifest(LIBRARY_KEY);
    return [...library, ...local.filter((s) => s.scan_type === "room")];
  }
  return loadLocalManifest(LIBRARY_KEY);
}

/**
 * Save a scan to the user's personal library (not tied to a project).
 *
 * @param {object} scan
 * @returns {Promise<object>}
 */
export async function saveToUserLibrary(scan) {
  const entry = {
    id: scan.room_id || scan.id || scan.structure_id || `scan_${Date.now()}`,
    saved_at: new Date().toISOString(),
    ...scan,
  };
  if (scan.scan_type === "structure" || scan.rooms?.length) {
    entry.scan_type = "structure";
    entry.structure_id = scan.structure_id || entry.id;
    if (useFilesystemStorage()) {
      await saveStructureScan(LIBRARY_SCOPE, entry);
    } else {
      const manifest = loadLocalManifest(LIBRARY_KEY);
      manifest.push(entry);
      saveLocalManifest(LIBRARY_KEY, manifest);
    }
    return entry;
  }
  entry.scan_type = "room";
  if (useFilesystemStorage()) {
    const saved = await saveRoomScanFile(LIBRARY_SCOPE, entry);
    entry.structure_id = saved.structureId;
    entry.room_id = saved.roomId;
    const manifest = loadLocalManifest(LIBRARY_KEY);
    manifest.push(entry);
    saveLocalManifest(LIBRARY_KEY, manifest);
  } else {
    const manifest = loadLocalManifest(LIBRARY_KEY);
    manifest.push(entry);
    saveLocalManifest(LIBRARY_KEY, manifest);
  }
  return entry;
}
