import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { isNativePlatform } from "../platform.js";
import { fetchProjectRoomScans } from "../api.js";
import { openRoomARForScan } from "../services/roomCapture.js";
import { buildComplianceChecks } from "../services/roomMetrics.js";
import { LIBRARY_SCOPE } from "../services/roomScanFilesystem.js";
import {
  activateRoomScan,
  captureAndSyncRoom,
  captureAndSyncStructure,
} from "../services/roomScanSync.js";
import { getRoomFromStructure, loadRoomScans } from "../services/roomScanStorage.js";

/**
 * RoomScanPanel — structure/room capture, master plan room list, design entry links.
 *
 * @param {{ project?: object, canEdit: boolean, libraryMode?: boolean, onSynced: (summary: object) => void }} props
 */
export default function RoomScanPanel({ project, canEdit, libraryMode = false, onSynced }) {
  const navigate = useNavigate();
  const [status, setStatus] = useState({
    pluginLoaded: false,
    available: false,
    reason: isNativePlatform() ? "Checking device support…" : null,
  });
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [cloudScans, setCloudScans] = useState([]);
  const [localStructures, setLocalStructures] = useState([]);
  const [selectedStructureId, setSelectedStructureId] = useState(null);
  const [activeRoomId, setActiveRoomId] = useState(null);

  const refreshScans = useCallback(async () => {
    if (libraryMode || !project?.id) {
      return;
    }
    const local = await Promise.resolve(loadRoomScans(project.id));
    setLocalStructures((local || []).filter((s) => s.scan_type === "structure" || s.rooms?.length));
    try {
      const result = await fetchProjectRoomScans(project.id);
      const rows = result.data || [];
      setCloudScans(rows);
      const active = rows.find((r) => r.scan_type === "room" && r.is_active);
      if (active) {
        setActiveRoomId(active.id);
        if (active.parent_scan_id) {
          setSelectedStructureId(active.parent_scan_id);
        }
      }
    } catch {
      setCloudScans([]);
    }
  }, [project?.id, libraryMode]);

  useEffect(() => {
    let active = true;
    (async () => {
      if (!isNativePlatform()) {
        return;
      }
      const { getRoomCaptureStatus } = await import("../services/roomCapture.js");
      const next = await getRoomCaptureStatus();
      if (active) {
        setStatus(next);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    refreshScans();
  }, [refreshScans, project?.room_summary, libraryMode]);

  const projectId = libraryMode ? null : project?.id;

  const selectedStructure =
    localStructures.find((s) => (s.structure_id || s.id) === selectedStructureId) ||
    localStructures[0] ||
    null;
  const structureId = selectedStructure?.structure_id || selectedStructure?.id;
  const rooms = selectedStructure?.rooms || [];
  const cloudRoomRows = cloudScans.filter(
    (r) => r.scan_type === "room" && r.parent_scan_id === structureId,
  );
  const standaloneCloudRooms = cloudScans.filter(
    (r) => r.scan_type === "room" && !r.parent_scan_id,
  );

  const activeStandalone =
    standaloneCloudRooms.find((r) => r.id === activeRoomId) ||
    standaloneCloudRooms.find((r) => r.is_active) ||
    null;

  const activeRoom =
    rooms.find((r) => r.room_id === activeRoomId) ||
    (cloudRoomRows.find((r) => r.is_active)
      ? {
          room_id: cloudRoomRows.find((r) => r.is_active)?.id,
          label: cloudRoomRows.find((r) => r.is_active)?.room_label,
          derived: cloudRoomRows.find((r) => r.is_active)?.derived,
        }
      : rooms[0]) ||
    (activeStandalone
      ? {
          room_id: activeStandalone.id,
          label: activeStandalone.room_label,
          derived: activeStandalone.derived,
        }
      : null);

  const derived = activeRoom?.derived || project?.room_summary?.derived;
  const compliance = derived ? buildComplianceChecks(derived) : [];

  const designPathForScan = (scanId) => {
    if (libraryMode) {
      return `/profile/room-scans/${scanId}/design`;
    }
    return `/projects/${project?.id}/scans/${scanId}/design`;
  };

  const handleScanRoom = async () => {
    if ((!libraryMode && !project?.id) || !canEdit) {
      return;
    }
    setScanning(true);
    setError("");
    try {
      const { scans } = await captureAndSyncRoom(projectId, {
        room_label: "Room",
        is_active: !libraryMode,
      });
      const active = scans.find((s) => s.is_active) || scans[scans.length - 1];
      if (active?.id) {
        setActiveRoomId(active.id);
        navigate(designPathForScan(active.id));
      }
      if (!libraryMode) {
        await refreshScans();
      }
      onSynced?.({
        schema_version: "2.0",
        room_label: active?.room_label,
        derived: active?.derived,
        captured_at: active?.captured_at,
      });
    } catch (err) {
      setError(err.message || "Room scan failed.");
    } finally {
      setScanning(false);
    }
  };

  const handleScanStructure = async () => {
    if ((!libraryMode && !project?.id) || !canEdit) {
      return;
    }
    setScanning(true);
    setError("");
    try {
      const { capture, scans } = await captureAndSyncStructure(projectId, {
        structure_label: project?.name || "Whole house",
      });
      if (!libraryMode) {
        setSelectedStructureId(capture.structure_id);
        const firstRoom = capture.rooms?.[0];
        if (firstRoom) {
          setActiveRoomId(firstRoom.room_id);
        }
        await refreshScans();
      }
      const active = scans.find((s) => s.is_active && s.scan_type === "room");
      onSynced?.({
        schema_version: "2.0",
        room_label: active?.room_label,
        derived: active?.derived,
        captured_at: active?.captured_at,
      });
    } catch (err) {
      setError(err.message || "Structure scan failed.");
    } finally {
      setScanning(false);
    }
  };

  const handleSetActiveRoom = async (roomId) => {
    setActiveRoomId(roomId);
    if (!project?.id) {
      return;
    }
    try {
      await activateRoomScan(project.id, roomId);
      await refreshScans();
      const row = cloudScans.find((r) => r.id === roomId) || cloudRoomRows.find((r) => r.id === roomId);
      const room = getRoomFromStructure(selectedStructure, roomId);
      onSynced?.({
        schema_version: "2.0",
        room_label: row?.room_label || room?.label,
        derived: row?.derived || room?.derived,
        captured_at: row?.captured_at,
      });
    } catch (err) {
      setError(err.message || "Could not set active room.");
    }
  };

  const handleOpenAR = async (room) => {
    if (!room?.room_id) {
      return;
    }
    const row = cloudScans.find((r) => r.id === room.room_id) || {
      id: room.room_id,
      room_id: room.room_id,
      room_label: room.label || room.room_label,
      parent_scan_id: structureId || null,
      structure_id: structureId || null,
    };
    const activeScope = libraryMode ? LIBRARY_SCOPE : project?.id;
    setError("");
    try {
      await openRoomARForScan(row, {
        scope: activeScope,
        roomLabel: room.label || room.room_label,
      });
    } catch (err) {
      setError(err.message || "AR viewer unavailable.");
    }
  };

  const statusMessage = (() => {
    if (!isNativePlatform()) {
      return "Room capture runs on the iOS/Android app with LiDAR.";
    }
    if (!canEdit) {
      return "Owner or editor role required to scan rooms.";
    }
    if (!status.pluginLoaded) {
      return status.reason || "Room capture plugin not loaded. Rebuild with npm run build:mobile && npx cap sync ios.";
    }
    if (!status.available) {
      return status.reason || "This device does not support RoomPlan scanning.";
    }
    return "Scan a single room to start designing. Full geometry stays on your phone.";
  })();

  return (
    <section className="room-scan-panel" aria-label="Room scan">
      <h3>Room Scan</h3>
      <p className="muted">{statusMessage}</p>

      {canEdit && isNativePlatform() && (
        <div className="room-scan-actions">
          <button
            type="button"
            className="primary-button room-scan-button"
            onClick={handleScanRoom}
            disabled={scanning}
          >
            {scanning ? "Scanning…" : "Scan Single Room"}
          </button>
          <button
            type="button"
            className="secondary-button room-scan-button room-scan-button--muted"
            onClick={handleScanStructure}
            disabled={scanning}
          >
            {scanning ? "Scanning…" : "Scan House"}
          </button>
        </div>
      )}
      {canEdit && isNativePlatform() && (
        <p className="muted room-scan-advanced-hint">Scan House is advanced — multi-room whole house capture.</p>
      )}

      {error && <div className="error-box">{error}</div>}

      {standaloneCloudRooms.length > 0 && rooms.length === 0 && (
        <div className="room-scan-master">
          <h4>Room scans</h4>
          <ul className="room-scan-room-list">
            {standaloneCloudRooms.map((row) => (
              <li key={row.id} className={row.id === activeRoomId ? "active-room" : ""}>
                <button type="button" className="link-button" onClick={() => handleSetActiveRoom(row.id)}>
                  {row.room_label}
                  {row.is_active ? " (active)" : ""}
                </button>
                <Link to={designPathForScan(row.id)} className="secondary-button room-design-button">
                  Design
                </Link>
                {isNativePlatform() && (
                  <button
                    type="button"
                    className="secondary-button room-design-button"
                    onClick={() =>
                      handleOpenAR({
                        room_id: row.id,
                        label: row.room_label,
                      })
                    }
                  >
                    AR
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {selectedStructure && rooms.length > 0 && !libraryMode && (
        <div className="room-scan-master">
          <h4>Master scan — {selectedStructure.structure_label || "Whole house"}</h4>
          <p className="muted">{rooms.length} room(s) delineated</p>
          <ul className="room-scan-room-list">
            {rooms.map((room) => (
              <li key={room.room_id} className={room.room_id === activeRoomId ? "active-room" : ""}>
                <button type="button" className="link-button" onClick={() => handleSetActiveRoom(room.room_id)}>
                  {room.label || room.room_label}
                  {room.room_id === activeRoomId ? " (active)" : ""}
                </button>
                <Link to={designPathForScan(room.room_id)} className="secondary-button room-design-button">
                  Design
                </Link>
                {isNativePlatform() && (
                  <button
                    type="button"
                    className="secondary-button room-design-button"
                    onClick={() => handleOpenAR(room)}
                  >
                    AR
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {derived && !libraryMode && (
        <>
          <RoomScanMetrics
            derived={derived}
            capturedAt={project?.room_summary?.captured_at}
            roomLabel={activeRoom?.label || activeRoom?.room_label || project?.room_summary?.room_label}
          />
          {compliance.length > 0 && <ComplianceCards checks={compliance} />}
        </>
      )}
    </section>
  );
}

/**
 * @param {{ derived: object, capturedAt?: string, roomLabel?: string }} props
 */
function RoomScanMetrics({ derived, capturedAt, roomLabel }) {
  // Scans synced before floor/wall area were split carry wall area under the
  // old floor_area_sqm name and no wall_area_sqm — keep showing those as walls.
  const legacy = derived.wall_area_sqm == null;
  const wallArea = legacy ? derived.floor_area_sqm : derived.wall_area_sqm;
  const floorArea = legacy ? null : derived.floor_area_sqm;

  return (
    <dl className="kickoff-summary room-scan-metrics">
      {roomLabel && (
        <div className="kickoff-summary-row">
          <dt>Active room</dt>
          <dd>{roomLabel}</dd>
        </div>
      )}
      {capturedAt && (
        <div className="kickoff-summary-row">
          <dt>Last scan</dt>
          <dd>{new Date(capturedAt).toLocaleString()}</dd>
        </div>
      )}
      <div className="kickoff-summary-row">
        <dt>Walls detected</dt>
        <dd>{derived.wall_count}</dd>
      </div>
      <div className="kickoff-summary-row">
        <dt>Max ceiling height</dt>
        <dd>{derived.max_ceiling_height_m} m</dd>
      </div>
      {wallArea != null && (
        <div className="kickoff-summary-row">
          <dt>Wall surface area (est.)</dt>
          <dd>{wallArea} m²</dd>
        </div>
      )}
      {floorArea != null && (
        <div className="kickoff-summary-row">
          <dt>Floor area{derived.floor_area_source === "wall_footprint" ? " (est.)" : ""}</dt>
          <dd>{floorArea} m²</dd>
        </div>
      )}
      {derived.wall_lengths_m?.length > 0 && (
        <div className="kickoff-summary-row">
          <dt>Wall lengths</dt>
          <dd>{derived.wall_lengths_m.join(", ")} m</dd>
        </div>
      )}
    </dl>
  );
}

/**
 * @param {{ checks: { id: string, pass: boolean, message: string }[] }} props
 */
function ComplianceCards({ checks }) {
  return (
    <div className="room-compliance-cards" aria-label="Compliance checks">
      <h4>Compliance checks</h4>
      <ul>
        {checks.map((check) => (
          <li key={check.id} className={check.pass ? "pass" : "fail"}>
            {check.message}
          </li>
        ))}
      </ul>
    </div>
  );
}
