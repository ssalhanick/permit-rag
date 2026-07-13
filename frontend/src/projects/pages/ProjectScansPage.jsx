import React, { useCallback, useEffect, useState } from "react";
import RoomScanPanel from "../../components/RoomScanPanel.jsx";
import ScanLibraryList from "../../components/ScanLibraryList.jsx";
import LinkScansModal from "../../components/LinkScansModal.jsx";
import {
  fetchProjectRoomScans,
  fetchUserRoomScans,
  setActiveRoomScan,
  unlinkScanFromProject,
} from "../../api.js";
import { useProject } from "../ProjectContext.jsx";

/**
 * Project room scans — linked scans + add from user library + capture.
 */
export default function ProjectScansPage() {
  const { project, canEdit, projectId, setProject } = useProject();
  const [linkedScans, setLinkedScans] = useState([]);
  const [libraryScans, setLibraryScans] = useState([]);
  const [showLinkModal, setShowLinkModal] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [linkedRes, libraryRes] = await Promise.all([
        fetchProjectRoomScans(projectId),
        fetchUserRoomScans(),
      ]);
      setLinkedScans(linkedRes.data || []);
      setLibraryScans(libraryRes.data || []);
    } catch (err) {
      setError(err.message || "Failed to load scans.");
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleSetActive = async (scanId) => {
    try {
      await setActiveRoomScan(projectId, scanId);
      setMessage("Active room updated for chat context.");
      await refresh();
    } catch (err) {
      setError(err.message || "Could not set active room.");
    }
  };

  const handleUnlink = async (scanId) => {
    if (!window.confirm("Remove this scan from the project? It stays in your library.")) {
      return;
    }
    try {
      await unlinkScanFromProject(projectId, scanId);
      setMessage("Scan removed from project.");
      await refresh();
    } catch (err) {
      setError(err.message || "Could not unlink scan.");
    }
  };

  return (
    <div className="project-scans-page">
      {error && <div className="error-box">{error}</div>}
      {message && <div className="success-box">{message}</div>}

      <section className="panel">
        <div className="dashboard-section-header">
          <h3>Linked scans</h3>
          {canEdit && (
            <button type="button" className="secondary-button" onClick={() => setShowLinkModal(true)}>
              Add from library
            </button>
          )}
        </div>
        <ScanLibraryList
          scans={linkedScans}
          onSetActive={canEdit ? handleSetActive : null}
          onUnlink={canEdit ? handleUnlink : null}
          showActive
          emptyMessage="No scans on this project yet."
        />
      </section>

      {canEdit && (
        <section className="panel">
          <h3>Capture new scan</h3>
          <p className="muted">
            New scans save to your library and link to this project automatically.
          </p>
          <RoomScanPanel
            project={project}
            canEdit={canEdit}
            onSynced={async (summary) => {
              setProject((prev) => (prev ? { ...prev, room_summary: summary } : prev));
              setMessage("Scan saved to library and linked to project.");
              await refresh();
            }}
          />
        </section>
      )}

      {showLinkModal && (
        <LinkScansModal
          projectId={projectId}
          libraryScans={libraryScans}
          linkedScanIds={new Set(linkedScans.map((s) => s.id))}
          onClose={() => setShowLinkModal(false)}
          onLinked={async () => {
            setShowLinkModal(false);
            setMessage("Scans linked to project.");
            await refresh();
          }}
        />
      )}
    </div>
  );
}
