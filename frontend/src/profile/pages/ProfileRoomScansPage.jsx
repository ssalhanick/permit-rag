import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import RoomScanPanel from "../../components/RoomScanPanel.jsx";
import ScanLibraryList from "../../components/ScanLibraryList.jsx";
import { fetchUserRoomScans } from "../../api.js";
import { loadUserLibrary } from "../../services/roomScanStorage.js";
import { isNativePlatform } from "../../platform.js";

/**
 * User scan library — all captures live here first; link to projects from project pages.
 */
export default function ProfileRoomScansPage() {
  const [cloudScans, setCloudScans] = useState([]);
  const [localScans, setLocalScans] = useState([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [cloudRes, local] = await Promise.all([
        fetchUserRoomScans(),
        Promise.resolve(loadUserLibrary()),
      ]);
      setCloudScans(cloudRes.data || []);
      setLocalScans(local || []);
    } catch (err) {
      setError(err.message || "Failed to load scan library.");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const displayScans = cloudScans.length ? cloudScans : localScans;

  return (
    <div className="profile-room-scans-page">
      <section className="panel scan-library-hero">
        <h2>My Room Scan Library</h2>
        <p className="muted">
          All scans live in your personal library first. Link houses or rooms to projects when you are ready.
          Full geometry stays on your {isNativePlatform() ? "phone" : "device"} — only measurements sync to the cloud.
        </p>
        <div className="profile-quick-links">
          <Link to="/projects" className="profile-quick-link-card">
            <strong>Projects</strong>
            <span>Add scans to a project workspace</span>
          </Link>
        </div>
      </section>

      {error && <div className="profile-flash profile-flash--error">{error}</div>}
      {message && <div className="profile-flash profile-flash--success">{message}</div>}

      <section className="panel">
        <h3>Capture</h3>
        <RoomScanPanel
          libraryMode
          canEdit
          onSynced={() => {
            setMessage("Scan saved to your library.");
            refresh();
          }}
        />
      </section>

      <section className="panel">
        <h3>Your scans ({displayScans.length})</h3>
        <ScanLibraryList
          scans={displayScans}
          emptyMessage="No scans yet. Use Scan Single Room above."
          designHref={(scanId) => `/profile/room-scans/${scanId}/design`}
        />
      </section>
    </div>
  );
}
