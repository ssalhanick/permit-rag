import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import RoomScanPanel from "../../components/RoomScanPanel.jsx";
import ScanLibraryList from "../../components/ScanLibraryList.jsx";
import { fetchUserRoomScans } from "../../api.js";
import { loadUserLibrary } from "../../services/roomScanStorage.js";
import { isNativePlatform } from "../../platform.js";
import { Layers, Camera, FolderPlus, ArrowRight, ShieldCheck } from "lucide-react";

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
    <div className="p-4 sm:p-6 space-y-6 max-w-6xl mx-auto">
      {/* Hero Banner */}
      <div className="bg-gradient-to-r from-slate-900 to-blue-950 text-white rounded-2xl p-6 shadow-md border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-2 max-w-2xl">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/20 text-blue-300 text-xs font-semibold border border-blue-400/30">
            <Layers className="w-3.5 h-3.5 text-blue-400" />
            3D Spatial & Mesh Vault
          </div>
          <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight text-white">
            Room Scan Library
          </h2>
          <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
            All room captures and LIDAR meshes live in your library first. Link spaces to projects anytime.
            Full geometry stays secure on your {isNativePlatform() ? "phone" : "local device"}.
          </p>
        </div>

        <div className="shrink-0">
          <Link
            to="/projects"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-lg transition-all"
          >
            <span>Project Workspaces</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 rounded-xl text-xs font-semibold">
          {error}
        </div>
      )}
      {message && (
        <div className="p-3 bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 rounded-xl text-xs font-semibold">
          {message}
        </div>
      )}

      {/* Capture Section */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-4">
        <div className="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 pb-3">
          <Camera className="w-4 h-4 text-blue-600 dark:text-blue-400" />
          <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 m-0">
            Room Capture & Scanning Tool
          </h3>
        </div>
        <RoomScanPanel
          libraryMode
          canEdit
          onSynced={() => {
            setMessage("Scan saved to your library.");
            refresh();
          }}
        />
      </div>

      {/* Scans List Section */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 m-0">
              Captured Spaces ({displayScans.length})
            </h3>
          </div>
          <span className="text-xs text-slate-400 font-medium">
            {cloudScans.length ? "Cloud Synced" : "Local Devices"}
          </span>
        </div>

        <ScanLibraryList
          scans={displayScans}
          emptyMessage="No room scans recorded yet. Use the scanner above to capture a space."
          designHref={(scanId) => `/profile/room-scans/${scanId}/design`}
        />
      </div>
    </div>
  );
}
