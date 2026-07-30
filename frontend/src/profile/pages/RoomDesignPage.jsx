import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Directory, Encoding, Filesystem } from "@capacitor/filesystem";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle,
  Download,
  Eye,
  GitBranch,
  Mic,
  Save,
  Scan,
  Sparkles,
  Wand2,
} from "lucide-react";
import { fetchProjectRoomScans, fetchUserRoomScans } from "../../api.js";
import OverlayProductList from "../../components/OverlayProductList.jsx";
import RoomFloorPlanMap from "../../components/RoomFloorPlanMap.jsx";
import { isNativePlatform } from "../../platform.js";
import { LIBRARY_SCOPE } from "../../services/roomScanFilesystem.js";
import {
  branchFromRevision,
  getActiveOverlays,
  loadDesignHistory,
  setActiveRevision,
} from "../../services/designHistory.js";
import {
  applyOverlaysToAR,
  previewDesignIntent,
  saveDesignPreview,
} from "../../services/roomDesignIntent.js";
import { generateAndAttachRoomPreview } from "../../services/roomPreviewImage.js";
import { openRoomARForScan, startSpeechRecognition } from "../../services/roomCapture.js";
import { findRoomFilesystemLocation } from "../../services/roomScanFilesystem.js";
import { buildRoomDxf } from "../../services/roomCadExport.js";
import { loadUserLibrary } from "../../services/roomScanStorage.js";

/**
 * Room design — Preview (cloud LLM) → Generate image → Save (device revision history).
 *
 * Works for project-linked scans and personal library scans.
 */
export default function RoomDesignPage({ libraryMode = false }) {
  const { projectId, scanId } = useParams();
  const [scanRow, setScanRow] = useState(null);
  const [filesystemLocation, setFilesystemLocation] = useState(null);
  const [history, setHistory] = useState(null);
  const [capture, setCapture] = useState(null);
  const [utterance, setUtterance] = useState("");
  const [preview, setPreview] = useState(null);
  const [generatedPreviewSrc, setGeneratedPreviewSrc] = useState(null);
  const [branchParentId, setBranchParentId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [selectedSurfaceId, setSelectedSurfaceId] = useState(null);

  const scope = libraryMode ? LIBRARY_SCOPE : projectId;
  const fsIds = filesystemLocation
    ? {
        scope: filesystemLocation.scope,
        structureId: filesystemLocation.structureId,
        roomId: filesystemLocation.roomId,
      }
    : null;

  const refresh = useCallback(async () => {
    if (!scanId) {
      return;
    }
    setError("");
    try {
      let row = null;
      if (libraryMode) {
        const [cloudRes, local] = await Promise.all([
          fetchUserRoomScans(),
          Promise.resolve(loadUserLibrary()),
        ]);
        const rows = cloudRes.data?.length ? cloudRes.data : local;
        row = rows.find((r) => r.id === scanId || r.room_id === scanId);
      } else if (projectId) {
        const result = await fetchProjectRoomScans(projectId);
        row = (result.data || []).find((r) => r.id === scanId);
      }
      if (!row) {
        setError("Scan not found.");
        return;
      }
      setScanRow(row);
      const located = await findRoomFilesystemLocation(scope, row);
      setFilesystemLocation(located);
      const [hist, cap] = await Promise.all([
        loadDesignHistory(located.scope, located.structureId, located.roomId),
        Promise.resolve(located.capture),
      ]);
      setHistory(hist);
      setCapture(cap);
    } catch (err) {
      setError(err.message || "Failed to load scan.");
    }
  }, [scanId, projectId, libraryMode, scope]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!isNativePlatform() || !scanId) {
      return;
    }
    let listener;
    const setupListener = async () => {
      const { registerPlugin } = await import("@capacitor/core");
      const RoomCapture = registerPlugin("RoomCapture");
      listener = await RoomCapture.addListener("onARSpeechCommand", async (data) => {
        if (data.roomId !== scanId) {
          return;
        }
        try {
          const result = await previewDesignIntent({
            projectId,
            scanId,
            utterance: data.transcript,
            selectedSurfaceId: data.selectedSurfaceId,
            roomLabel: scanRow?.room_label || "Room",
            roomDerived: scanRow?.derived,
            surfaceHints: (capture?.surfaces || []).map((s) => ({
              id: s.id,
              category: s.category,
            })),
            libraryMode,
          });
          
          await applyOverlaysToAR({
            projectId: data.projectId,
            structureId: data.structureId,
            roomId: data.roomId,
            overlays: result.overlays,
          });

          setPreview({
            utterance: data.transcript,
            explanation: result.explanation,
            overlays: result.overlays,
            usage: result.usage,
          });
          setUtterance(data.transcript);
        } catch (err) {
          console.error("AR dictation command failed:", err);
        }
      });
    };
    setupListener();
    return () => {
      if (listener) {
        listener.remove();
      }
    };
  }, [scanId, projectId, libraryMode, scanRow, capture]);

  const handlePreview = async () => {
    if (!utterance.trim() || !scanRow || !fsIds) {
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await previewDesignIntent({
        projectId,
        scanId: scanRow.id,
        utterance: utterance.trim(),
        roomLabel: scanRow.room_label,
        roomDerived: scanRow.derived,
        surfaceHints: (capture?.surfaces || []).map((s) => ({
          id: s.id,
          category: s.category,
        })),
        libraryMode,
      });
      setPreview({
        utterance: utterance.trim(),
        explanation: result.explanation,
        overlays: result.overlays,
        usage: result.usage,
      });
      setGeneratedPreviewSrc(null);
      if (isNativePlatform()) {
        await applyOverlaysToAR({
          projectId: fsIds.scope,
          structureId: fsIds.structureId,
          roomId: fsIds.roomId,
          overlays: result.overlays,
        });
      }
    } catch (err) {
      setError(err.message || "Preview failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleGenerateImage = async () => {
    if (!preview || !fsIds) {
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      let sourceImageB64 = null;
      if (isNativePlatform()) {
        try {
          const { Camera, CameraResultType, CameraSource } = await import("@capacitor/camera");
          const photo = await Camera.getPhoto({
            quality: 70,
            resultType: CameraResultType.Base64,
            source: CameraSource.Prompt,
            width: 1024,
          });
          sourceImageB64 = photo.base64String || null;
        } catch {
          // optional photo — continue text-only generation
        }
      }
      const generated = await generateAndAttachRoomPreview({
        utterance: preview.utterance,
        roomLabel: scanRow?.room_label,
        overlays: preview.overlays,
        sourceImageB64,
        scope: fsIds.scope,
        structureId: fsIds.structureId,
        roomId: fsIds.roomId,
        projectId: fsIds.scope,
        applyToAr: isNativePlatform(),
      });
      setPreview({
        ...preview,
        overlays: generated.overlays,
      });
      setGeneratedPreviewSrc(generated.previewSrc);
      const provider = generated.meta?.mock ? "mock" : generated.meta?.provider;
      setMessage(`Room image ready (${provider}). Save to keep on this revision.`);
    } catch (err) {
      setError(err.message || "Image generation failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleMic = async () => {
    if (!isNativePlatform() || busy) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const speech = await startSpeechRecognition();
      const transcript = speech?.transcript?.trim();
      if (!transcript) {
        throw new Error("No speech detected.");
      }
      setUtterance(transcript);
    } catch (err) {
      setError(err.message || "Speech input failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleSave = async () => {
    if (!preview || !fsIds) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const next = await saveDesignPreview({
        scope: fsIds.scope,
        structureId: fsIds.structureId,
        roomId: fsIds.roomId,
        utterance: preview.utterance,
        explanation: preview.explanation,
        overlays: preview.overlays,
        parentRevisionId: branchParentId,
      });
      setHistory(next);
      setPreview(null);
      setGeneratedPreviewSrc(null);
      setBranchParentId(null);
      setMessage("Saved.");
    } catch (err) {
      setError(err.message || "Save failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleOpenAR = async () => {
    if (!scanRow || !fsIds) {
      return;
    }
    setError("");
    setBusy(true);
    try {
      // Open AR only reads redesign.json — persist current preview first.
      if (preview?.overlays?.length) {
        const next = await saveDesignPreview({
          scope: fsIds.scope,
          structureId: fsIds.structureId,
          roomId: fsIds.roomId,
          utterance: preview.utterance,
          explanation: preview.explanation,
          overlays: preview.overlays,
          parentRevisionId: branchParentId,
        });
        setHistory(next);
        setPreview(null);
        setGeneratedPreviewSrc(null);
        setBranchParentId(null);
        setMessage("Saved preview for AR.");
      }
      await openRoomARForScan(scanRow, {
        scope,
        roomLabel: scanRow.room_label,
        selectedSurfaceId,
      });
    } catch (err) {
      setError(err.message || "AR unavailable.");
    } finally {
      setBusy(false);
    }
  };

  const handleActivateRevision = async (revisionId) => {
    if (!fsIds) {
      return;
    }
    setBusy(true);
    try {
      const next = await setActiveRevision(fsIds.scope, fsIds.structureId, fsIds.roomId, revisionId);
      setHistory(next);
      setMessage("Active revision updated.");
    } catch (err) {
      setError(err.message || "Could not activate revision.");
    } finally {
      setBusy(false);
    }
  };

  const handleBranch = async (revisionId) => {
    if (!fsIds) {
      return;
    }
    setBusy(true);
    try {
      const next = await branchFromRevision(fsIds.scope, fsIds.structureId, fsIds.roomId, revisionId);
      setHistory(next);
      setBranchParentId(revisionId);
      const rev = (next.revisions || []).find((r) => r.id === revisionId);
      if (rev?.utterance) {
        setUtterance(rev.utterance === "(imported)" ? "" : rev.utterance);
      }
      setPreview(null);
      setMessage("Branching from selected revision — edit and Preview.");
    } catch (err) {
      setError(err.message || "Branch failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleExportDxf = async () => {
    if (!capture || !fsIds) {
      setError("Capture geometry not found on device.");
      return;
    }
    const overlays = preview?.overlays || getActiveOverlays(history || {});
    const dxf = buildRoomDxf({ capture, overlays });
    const filename = `room_${fsIds.roomId.slice(0, 8)}.dxf`;
    try {
      const path = `exports/${filename}`;
      await Filesystem.writeFile({
        path,
        data: dxf,
        directory: Directory.Cache,
        encoding: Encoding.UTF8,
      });
      const uri = await Filesystem.getUri({ path, directory: Directory.Cache });
      if (isNativePlatform()) {
        const { Share } = await import("@capacitor/share");
        await Share.share({
          title: "Room DXF export",
          url: uri.uri,
          dialogTitle: "Share DXF",
        });
      } else {
        const blob = new Blob([dxf], { type: "application/dxf" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename;
        anchor.click();
        URL.revokeObjectURL(url);
      }
      setMessage("DXF export ready.");
    } catch (err) {
      setError(err.message || "DXF export failed.");
    }
  };

  const backLink = libraryMode
    ? "/profile/room-scans"
    : `/projects/${projectId}/scans`;

  const revisions = history?.revisions || [];
  const tokenTotal = preview?.usage
    ? preview.usage.input_tokens + preview.usage.output_tokens
    : null;

  return (
    <div className="max-w-4xl mx-auto p-4 sm:p-6 space-y-6">
      <nav className="text-xs font-semibold text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
        <Link
          to={backLink}
          className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors flex items-center gap-1"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to scans
        </Link>
      </nav>

      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/80 text-blue-600 dark:text-blue-400 flex items-center justify-center flex-shrink-0 border border-blue-200/60 dark:border-blue-800/60">
          <Wand2 className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">
            Design — {scanRow?.room_label || "Room"}
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-300 mt-0.5">
            Preview calls the cloud model. Save stores the last preview on this device only.
          </p>
        </div>
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

      <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 sm:p-8 shadow-sm">
        <RoomFloorPlanMap
          surfaces={capture?.surfaces}
          selectedSurfaceId={selectedSurfaceId}
          onSelectSurface={setSelectedSurfaceId}
        />
      </div>

      <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 sm:p-8 shadow-sm space-y-4">
        <textarea
          className="w-full box-border rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500"
          rows={3}
          placeholder='e.g. "white subway tile on backsplash wall"'
          value={utterance}
          onChange={(e) => setUtterance(e.target.value)}
        />

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="tt-btn-primary flex items-center gap-1.5 text-xs px-4 py-2.5 rounded-xl"
            onClick={handlePreview}
            disabled={busy}
          >
            <Eye className="w-3.5 h-3.5" />
            {busy ? "Working…" : "Preview"}
          </button>
          <button
            type="button"
            className="tt-btn-secondary flex items-center gap-1.5 text-xs px-4 py-2.5 rounded-xl"
            onClick={handleSave}
            disabled={busy || !preview}
          >
            <Save className="w-3.5 h-3.5" />
            Save
          </button>
          <button
            type="button"
            className="tt-btn-secondary flex items-center gap-1.5 text-xs px-4 py-2.5 rounded-xl"
            onClick={handleGenerateImage}
            disabled={busy || !preview}
          >
            <Sparkles className="w-3.5 h-3.5" />
            Generate image
          </button>
          {isNativePlatform() && (
            <button
              type="button"
              className="tt-btn-secondary flex items-center gap-1.5 text-xs px-4 py-2.5 rounded-xl"
              onClick={handleMic}
              disabled={busy}
            >
              <Mic className="w-3.5 h-3.5" />
              Mic
            </button>
          )}
          {isNativePlatform() && (
            <button
              type="button"
              className="tt-btn-secondary flex items-center gap-1.5 text-xs px-4 py-2.5 rounded-xl"
              onClick={handleOpenAR}
            >
              <Scan className="w-3.5 h-3.5" />
              {selectedSurfaceId ? "Open AR here" : "Open AR"}
            </button>
          )}
          <button
            type="button"
            className="tt-btn-secondary flex items-center gap-1.5 text-xs px-4 py-2.5 rounded-xl"
            onClick={handleExportDxf}
            disabled={busy}
          >
            <Download className="w-3.5 h-3.5" />
            Export DXF
          </button>
        </div>

        {tokenTotal != null && (
          <p className="text-xs text-slate-400 dark:text-slate-500">
            Last preview: {tokenTotal} tokens ({preview.usage.model})
          </p>
        )}
      </div>

      {preview && (
        <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 sm:p-8 shadow-sm space-y-4">
          <p className="text-sm text-slate-700 dark:text-slate-200 leading-relaxed">{preview.explanation}</p>
          {generatedPreviewSrc && (
            <figure className="space-y-2">
              <img
                src={generatedPreviewSrc}
                alt="Generated room redesign preview"
                className="w-full rounded-xl border border-slate-200 dark:border-slate-700"
              />
              <figcaption className="text-xs text-slate-400 dark:text-slate-500">
                Generative preview — also pushed to AR as asset texture when native.
              </figcaption>
            </figure>
          )}
          <OverlayProductList overlays={preview.overlays} />
        </div>
      )}

      {revisions.length > 0 && (
        <div
          className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 sm:p-8 shadow-sm"
          aria-label="Revision history"
        >
          <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-4 flex items-center gap-2">
            <GitBranch className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            Saved revisions
          </h3>
          <ul className="space-y-2">
            {revisions.map((rev) => {
              const isActive = rev.id === history?.active_revision_id;
              return (
                <li
                  key={rev.id}
                  className={`flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 p-3 rounded-xl border ${
                    isActive
                      ? "border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-950/40"
                      : "border-slate-200 dark:border-slate-700"
                  }`}
                >
                  <div>
                    <strong className="block text-sm text-slate-900 dark:text-slate-100">
                      {rev.utterance?.slice(0, 60) || "Revision"}
                    </strong>
                    <span className="text-xs text-slate-400 dark:text-slate-500">
                      {new Date(rev.created_at).toLocaleString()}
                      {isActive ? " · active" : ""}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs font-semibold">
                    <button
                      type="button"
                      className="text-blue-600 dark:text-blue-400 hover:underline"
                      onClick={() => handleActivateRevision(rev.id)}
                    >
                      Set active
                    </button>
                    <button
                      type="button"
                      className="text-blue-600 dark:text-blue-400 hover:underline"
                      onClick={() => handleBranch(rev.id)}
                    >
                      Branch
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
