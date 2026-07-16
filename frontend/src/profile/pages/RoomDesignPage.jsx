import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Directory, Encoding, Filesystem } from "@capacitor/filesystem";
import { fetchProjectRoomScans, fetchUserRoomScans } from "../../api.js";
import OverlayProductList from "../../components/OverlayProductList.jsx";
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
    <div className="room-design-page">
      <section className="panel">
        <p className="muted">
          <Link to={backLink}>← Back to scans</Link>
        </p>
        <h2>Design — {scanRow?.room_label || "Room"}</h2>
        <p className="muted">
          Preview calls the cloud model. Save stores the last preview on this device only.
        </p>

        {error && <div className="error-box">{error}</div>}
        {message && <div className="profile-flash profile-flash--success">{message}</div>}

        <textarea
          className="room-design-input room-design-textarea"
          rows={3}
          placeholder='e.g. "white subway tile on backsplash wall"'
          value={utterance}
          onChange={(e) => setUtterance(e.target.value)}
        />

        <div className="room-scan-actions">
          <button type="button" className="primary-button" onClick={handlePreview} disabled={busy}>
            {busy ? "Working…" : "Preview"}
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={handleSave}
            disabled={busy || !preview}
          >
            Save
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={handleGenerateImage}
            disabled={busy || !preview}
          >
            Generate image
          </button>
          {isNativePlatform() && (
            <button type="button" className="secondary-button" onClick={handleMic} disabled={busy}>
              Mic
            </button>
          )}
          {isNativePlatform() && (
            <button type="button" className="secondary-button" onClick={handleOpenAR}>
              Open AR
            </button>
          )}
          <button type="button" className="secondary-button" onClick={handleExportDxf} disabled={busy}>
            Export DXF
          </button>
        </div>

        {tokenTotal != null && (
          <p className="muted room-design-token-usage">
            Last preview: {tokenTotal} tokens ({preview.usage.model})
          </p>
        )}

        {preview && (
          <>
            <p className="room-design-explanation">{preview.explanation}</p>
            {generatedPreviewSrc && (
              <figure className="room-design-generated">
                <img src={generatedPreviewSrc} alt="Generated room redesign preview" />
                <figcaption className="muted">
                  Generative preview — also pushed to AR as asset texture when native.
                </figcaption>
              </figure>
            )}
            <OverlayProductList overlays={preview.overlays} />
          </>
        )}

        {revisions.length > 0 && (
          <section className="room-design-history" aria-label="Revision history">
            <h3>Saved revisions</h3>
            <ul className="room-design-history-list">
              {revisions.map((rev) => (
                <li
                  key={rev.id}
                  className={rev.id === history?.active_revision_id ? "active-revision" : ""}
                >
                  <div className="room-design-history-meta">
                    <strong>{rev.utterance?.slice(0, 60) || "Revision"}</strong>
                    <span className="muted">
                      {new Date(rev.created_at).toLocaleString()}
                      {rev.id === history?.active_revision_id ? " · active" : ""}
                    </span>
                  </div>
                  <div className="room-scan-actions">
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => handleActivateRevision(rev.id)}
                    >
                      Set active
                    </button>
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => handleBranch(rev.id)}
                    >
                      Branch
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}
      </section>
    </div>
  );
}
