/**
 * designHistory.js — device-only redesign.json v2 revision history.
 */

import { loadRedesign, readJson, roomBasePath, writeJson, findRoomFilesystemLocation } from "./roomScanFilesystem.js";
import { newScanId } from "./scanIds.js";

/**
 * Resolve filesystem structureId + roomId from a scan row.
 *
 * @param {object} scanRow
 * @returns {{ structureId: string, roomId: string }}
 */
export function resolveScanFilesystemIds(scanRow) {
  const roomId = scanRow.id || scanRow.room_id;
  const structureId = scanRow.parent_scan_id || scanRow.structure_id || `room_${roomId}`;
  return { structureId, roomId };
}

/**
 * Migrate v1 flat overlays into a single v2 revision.
 *
 * @param {object} doc
 * @returns {object}
 */
export function migrateRedesignV1toV2(doc) {
  if (!doc || doc.schema_version === "2.0") {
    return doc;
  }
  const overlays = doc.overlays || [];
  if (!overlays.length) {
    return {
      schema_version: "2.0",
      scan_id: doc.scan_id,
      active_revision_id: null,
      revisions: [],
      updated_at: doc.updated_at || new Date().toISOString(),
    };
  }
  const revId = `rev_${newScanId()}`;
  return {
    schema_version: "2.0",
    scan_id: doc.scan_id,
    active_revision_id: revId,
    revisions: [
      {
        id: revId,
        parent_revision_id: null,
        created_at: doc.updated_at || new Date().toISOString(),
        utterance: "(imported)",
        explanation: "Migrated from v1 overlays",
        overlays,
      },
    ],
    updated_at: new Date().toISOString(),
  };
}

/**
 * @param {object} doc
 * @returns {object[]}
 */
export function getActiveOverlays(doc) {
  const migrated = migrateRedesignV1toV2(doc);
  if (!migrated.active_revision_id) {
    return [];
  }
  const rev = (migrated.revisions || []).find((r) => r.id === migrated.active_revision_id);
  return rev?.overlays || [];
}

/**
 * Load redesign history, migrating v1 on read.
 *
 * @param {string} scope
 * @param {string} structureId
 * @param {string} roomId
 * @returns {Promise<object>}
 */
export async function loadDesignHistory(scope, structureId, roomId) {
  const raw = await loadRedesign(scope, structureId, roomId);
  const doc = migrateRedesignV1toV2(raw);
  if (doc.schema_version === "2.0" && raw.schema_version !== "2.0") {
    await writeJson(
      `${roomBasePath(scope, structureId, roomId)}/redesign.json`,
      doc,
    );
  }
  return doc;
}

/**
 * Persist a new saved revision and set it active.
 *
 * @param {string} scope
 * @param {string} structureId
 * @param {string} roomId
 * @param {{ utterance: string, explanation: string, overlays: object[], parentRevisionId?: string | null }} payload
 * @returns {Promise<object>}
 */
export async function saveRevision(scope, structureId, roomId, payload) {
  const doc = await loadDesignHistory(scope, structureId, roomId);
  const revId = `rev_${newScanId()}`;
  const revision = {
    id: revId,
    parent_revision_id: payload.parentRevisionId || null,
    created_at: new Date().toISOString(),
    utterance: payload.utterance,
    explanation: payload.explanation,
    overlays: payload.overlays,
  };
  const next = {
    ...doc,
    schema_version: "2.0",
    scan_id: doc.scan_id || roomId,
    active_revision_id: revId,
    revisions: [...(doc.revisions || []), revision],
    updated_at: new Date().toISOString(),
  };
  await writeJson(`${roomBasePath(scope, structureId, roomId)}/redesign.json`, next);
  return next;
}

/**
 * Set active revision without creating a new one (branch target / history pick).
 *
 * @param {string} scope
 * @param {string} structureId
 * @param {string} roomId
 * @param {string} revisionId
 * @returns {Promise<object>}
 */
export async function setActiveRevision(scope, structureId, roomId, revisionId) {
  const doc = await loadDesignHistory(scope, structureId, roomId);
  const exists = (doc.revisions || []).some((r) => r.id === revisionId);
  if (!exists) {
    throw new Error("Revision not found.");
  }
  const next = {
    ...doc,
    active_revision_id: revisionId,
    updated_at: new Date().toISOString(),
  };
  await writeJson(`${roomBasePath(scope, structureId, roomId)}/redesign.json`, next);
  return next;
}

/**
 * Alias for setActiveRevision — user branches from a prior revision.
 *
 * @param {string} scope
 * @param {string} structureId
 * @param {string} roomId
 * @param {string} revisionId
 * @returns {Promise<object>}
 */
export async function branchFromRevision(scope, structureId, roomId, revisionId) {
  return setActiveRevision(scope, structureId, roomId, revisionId);
}

/**
 * Load room capture.json from device storage.
 *
 * @param {string} scope
 * @param {string} structureId
 * @param {string} roomId
 * @returns {Promise<object | null>}
 */
export async function loadRoomCapture(scope, structureId, roomId, scanRow = null) {
  if (scanRow) {
    const located = await findRoomFilesystemLocation(scope, scanRow);
    return located.capture;
  }
  return readJson(`${roomBasePath(scope, structureId, roomId)}/capture.json`);
}
