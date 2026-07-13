import React, { useEffect, useState } from "react";
import { isNativePlatform } from "../platform.js";
import { getRoomCaptureStatus } from "../services/roomCapture.js";
import { captureAndSyncRoom } from "../services/roomScanSync.js";
import { getLatestRoomScan } from "../services/roomScanStorage.js";

/**
 * RoomScanPanel — mobile room capture entry point on project detail.
 *
 * @param {{ project: object, canEdit: boolean, onSynced: (summary: object) => void }} props
 */
export default function RoomScanPanel({ project, canEdit, onSynced }) {
  const [status, setStatus] = useState({
    pluginLoaded: false,
    available: false,
    reason: isNativePlatform() ? "Checking device support…" : null,
  });
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [localScan, setLocalScan] = useState(null);

  useEffect(() => {
    let active = true;
    (async () => {
      if (!isNativePlatform()) {
        return;
      }
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
    if (project?.id) {
      setLocalScan(getLatestRoomScan(project.id));
    }
  }, [project?.id, project?.room_summary]);

  const summary = project?.room_summary;
  const derived = summary?.derived || localScan?.derived;

  const handleScan = async () => {
    if (!project?.id || !canEdit) {
      return;
    }
    setScanning(true);
    setError("");
    try {
      const { summary: synced } = await captureAndSyncRoom(project.id, {
        room_label: project.name || "room",
      });
      setLocalScan(getLatestRoomScan(project.id));
      onSynced?.(synced);
    } catch (err) {
      setError(err.message || "Room scan failed.");
    } finally {
      setScanning(false);
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
    return "Scan room walls on-device. Only derived measurements sync — no mesh leaves your phone.";
  })();

  if (!isNativePlatform()) {
    return (
      <section className="room-scan-panel" aria-label="Room scan">
        <h3>Room Scan</h3>
        <p className="muted">{statusMessage}</p>
        {derived && <RoomScanMetrics derived={derived} capturedAt={summary?.captured_at} />}
      </section>
    );
  }

  return (
    <section className="room-scan-panel" aria-label="Room scan">
      <h3>Room Scan</h3>
      <p className="muted">{statusMessage}</p>

      {canEdit && (
        <button
          type="button"
          className="secondary-button room-scan-button"
          onClick={handleScan}
          disabled={scanning}
        >
          {scanning ? "Scanning…" : "Scan Room"}
        </button>
      )}

      {error && <div className="error-box">{error}</div>}
      {derived && <RoomScanMetrics derived={derived} capturedAt={summary?.captured_at || localScan?.captured_at} />}
    </section>
  );
}

/**
 * @param {{ derived: object, capturedAt?: string }} props
 */
function RoomScanMetrics({ derived, capturedAt }) {
  return (
    <dl className="kickoff-summary room-scan-metrics">
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
      <div className="kickoff-summary-row">
        <dt>Wall surface area (est.)</dt>
        <dd>{derived.floor_area_sqm} m²</dd>
      </div>
      {derived.wall_lengths_m?.length > 0 && (
        <div className="kickoff-summary-row">
          <dt>Wall lengths</dt>
          <dd>{derived.wall_lengths_m.join(", ")} m</dd>
        </div>
      )}
    </dl>
  );
}
