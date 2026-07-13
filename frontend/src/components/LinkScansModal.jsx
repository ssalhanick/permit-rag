import React, { useState } from "react";
import { linkScansToProject } from "../api.js";

/**
 * Modal to attach library scans to a project.
 */
export default function LinkScansModal({
  projectId,
  libraryScans,
  linkedScanIds,
  onClose,
  onLinked,
}) {
  const [selected, setSelected] = useState(new Set());
  const [activeId, setActiveId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const available = libraryScans.filter((s) => !linkedScanIds.has(s.id));

  const toggle = (scanId) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(scanId)) {
        next.delete(scanId);
      } else {
        next.add(scanId);
      }
      return next;
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selected.size) {
      setError("Select at least one scan.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const scanIds = Array.from(selected);
      const roomIds = scanIds.filter((id) => {
        const row = libraryScans.find((s) => s.id === id);
        return row?.scan_type === "room";
      });
      await linkScansToProject(
        projectId,
        scanIds,
        activeId || roomIds[0] || null,
      );
      onLinked?.();
    } catch (err) {
      setError(err.message || "Failed to link scans.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div className="modal-panel" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <h3>Add scans from your library</h3>
        <p className="muted">Pick houses, rooms, or individual scans to attach to this project.</p>
        {error && <div className="error-box">{error}</div>}
        {available.length === 0 ? (
          <p className="muted">Everything in your library is already on this project.</p>
        ) : (
          <form onSubmit={handleSubmit}>
            <ul className="link-scans-list">
              {available.map((scan) => (
                <li key={scan.id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={selected.has(scan.id)}
                      onChange={() => toggle(scan.id)}
                    />
                    <span>
                      {scan.scan_type === "structure"
                        ? scan.structure_label || scan.room_label
                        : scan.room_label}
                      <small className="muted"> ({scan.scan_type})</small>
                    </span>
                  </label>
                  {scan.scan_type === "room" && selected.has(scan.id) && (
                    <label className="link-scans-active">
                      <input
                        type="radio"
                        name="activeScan"
                        checked={activeId === scan.id}
                        onChange={() => setActiveId(scan.id)}
                      />
                      Active for chat
                    </label>
                  )}
                </li>
              ))}
            </ul>
            <div className="modal-actions">
              <button type="button" className="secondary-button" onClick={onClose}>
                Cancel
              </button>
              <button type="submit" className="primary-button" disabled={busy}>
                {busy ? "Linking…" : "Add to project"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
