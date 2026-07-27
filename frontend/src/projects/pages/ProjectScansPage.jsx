import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
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
import { Camera, Plus, AlertTriangle, CheckCircle } from "lucide-react";

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
      setMessage("Active room updated for AI chat context.");
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
    <div className="max-w-4xl mx-auto p-4 sm:p-6 space-y-6">
      {/* ── Breadcrumb Navigation ── */}
      <nav className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3 flex items-center gap-1.5">
        <Link to="/projects" className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
          Projects
        </Link>
        <span>/</span>
        <Link to={`/projects/${projectId}`} className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
          {project?.name || "Dashboard"}
        </Link>
        <span>/</span>
        <span className="text-slate-900 dark:text-slate-100 font-bold">Room Scans</span>
      </nav>

      {/* ── Page Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/80 text-blue-600 dark:text-blue-400 flex items-center justify-center flex-shrink-0 border border-blue-200/60 dark:border-blue-800/60">
            <Camera className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">
              Spatial Room Scans
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-300 mt-0.5">
              3D floor plans and room dimensions linked to drive spatial permit checks.
            </p>
          </div>
        </div>

        {canEdit && (
          <button
            type="button"
            className="tt-btn-secondary text-xs px-4 py-2.5 rounded-xl flex items-center gap-1.5 self-start sm:self-auto"
            onClick={() => setShowLinkModal(true)}
          >
            <Plus className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" /> Add from Library
          </button>
        )}
      </div>

      {error && (
        <div className="p-4 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded-xl text-xs font-semibold flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {message && (
        <div className="p-4 bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-200 rounded-xl text-xs font-semibold flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
          <span>{message}</span>
        </div>
      )}

      {/* ── Linked Scans Card Panel ── */}
      <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 sm:p-8 shadow-sm">
        <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-4">Linked Spatial Scans</h3>
        <ScanLibraryList
          scans={linkedScans}
          onSetActive={canEdit ? handleSetActive : null}
          onUnlink={canEdit ? handleUnlink : null}
          showActive
          emptyMessage="No scans linked to this project yet."
        />
      </div>

      {/* ── Capture New Scan Panel ── */}
      {canEdit && (
        <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 sm:p-8 shadow-sm space-y-4">
          <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">Capture New Spatial Scan</h3>
          <p className="text-xs text-slate-500 dark:text-slate-300">
            New scans save to your global library and link to this project automatically.
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
        </div>
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
