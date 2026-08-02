import React, { useCallback, useEffect, useState } from "react";
import {
  approveDocumentPetition,
  approveOverlayPetition,
  listPendingDocumentPetitions,
  listPendingOverlayPetitions,
  rejectDocumentPetition,
  rejectOverlayPetition,
} from "../api.js";

/**
 * Staff review queue for the two tiered-trust petition types (document-upload
 * plan): Type 1 ordinance petitions and Type 3 historic/conservation/HOA
 * overlay petitions. Both backends (document_petitions.py, overlays.py)
 * already existed, properly gated behind _require_admin_auth — this pane was
 * the missing frontend half; review previously meant curl/Postman.
 */
export default function PetitionReviewPane() {
  const [documents, setDocuments] = useState([]);
  const [overlays, setOverlays] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [docsRes, overlaysRes] = await Promise.all([
        listPendingDocumentPetitions(),
        listPendingOverlayPetitions(),
      ]);
      setDocuments(docsRes.data || []);
      setOverlays(overlaysRes.data || []);
    } catch (err) {
      setError(err.message || "Failed to load petition queues.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleDocumentDecision = async (docId, decision) => {
    setBusyId(docId);
    setError(null);
    try {
      await (decision === "approve" ? approveDocumentPetition(docId) : rejectDocumentPetition(docId));
      await load();
    } catch (err) {
      setError(err.message || `Failed to ${decision} ${docId}.`);
    } finally {
      setBusyId(null);
    }
  };

  const handleOverlayDecision = async (overlayId, decision) => {
    setBusyId(overlayId);
    setError(null);
    try {
      await (decision === "approve" ? approveOverlayPetition(overlayId) : rejectOverlayPetition(overlayId));
      await load();
    } catch (err) {
      setError(err.message || `Failed to ${decision} overlay.`);
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <p>Loading…</p>;

  return (
    <div>
      <div style={S.toolbar}>
        <button type="button" style={S.btnGhost} onClick={load}>Refresh</button>
      </div>
      {error && <p style={S.error}>{error}</p>}

      <h3 style={S.sectionHead}>Ordinance petitions ({documents.length})</h3>
      {documents.length === 0 ? (
        <p style={S.muted}>No ordinance petitions awaiting review.</p>
      ) : (
        documents.map((d) => (
          <div key={d.doc_id} style={S.card}>
            <div style={S.cardHead}>
              <strong>{d.doc_id}</strong>
              <span style={S.muted}>{d.municipality} · {d.doc_type}</span>
            </div>
            {d.subject_tags?.length > 0 && (
              <div style={S.meta}>Tags: {d.subject_tags.join(", ")}</div>
            )}
            <div style={S.cardFoot}>
              <button
                type="button"
                style={S.btnPrimary}
                disabled={busyId === d.doc_id}
                onClick={() => handleDocumentDecision(d.doc_id, "approve")}
              >
                {busyId === d.doc_id ? "Working…" : "Approve into corpus"}
              </button>
              <button
                type="button"
                style={S.btnDanger}
                disabled={busyId === d.doc_id}
                onClick={() => handleDocumentDecision(d.doc_id, "reject")}
              >
                Reject
              </button>
            </div>
          </div>
        ))
      )}

      <h3 style={S.sectionHead}>Overlay petitions ({overlays.length})</h3>
      {overlays.length === 0 ? (
        <p style={S.muted}>No overlay petitions awaiting review.</p>
      ) : (
        overlays.map((o) => (
          <div key={o.id} style={S.card}>
            <div style={S.cardHead}>
              <strong>{o.name}</strong>
              <span style={S.muted}>{o.overlay_type} · {o.jurisdiction_id || "unspecified jurisdiction"}</span>
            </div>
            {o.notes && <div style={S.meta}>{o.notes}</div>}
            <div style={S.cardFoot}>
              <button
                type="button"
                style={S.btnPrimary}
                disabled={busyId === o.id}
                onClick={() => handleOverlayDecision(o.id, "approve")}
                title="Approves the petitioner's default-buffer boundary as-is; refining the geometry is not yet in this UI"
              >
                {busyId === o.id ? "Working…" : "Approve default boundary"}
              </button>
              <button
                type="button"
                style={S.btnDanger}
                disabled={busyId === o.id}
                onClick={() => handleOverlayDecision(o.id, "reject")}
              >
                Reject
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

// ── styles (matches MetadataReviewPane.jsx's inline-style convention) ──────
const BORDER = "1px solid rgba(148,163,184,0.35)";
const S = {
  toolbar: { display: "flex", gap: "0.75rem", alignItems: "center", marginBottom: "1rem" },
  sectionHead: { marginTop: "1.5rem", marginBottom: "0.5rem" },
  muted: { color: "#94a3b8", fontSize: "0.85rem" },
  error: { color: "#ef4444" },
  card: { border: BORDER, borderRadius: 10, padding: "1rem 1.25rem", marginBottom: "0.85rem" },
  cardHead: { display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "1rem" },
  meta: { fontSize: "0.85rem", color: "#94a3b8", margin: "0.4rem 0" },
  cardFoot: { marginTop: "0.75rem", display: "flex", gap: "0.5rem" },
  btnPrimary: { padding: "8px 18px", background: "#2f6feb", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: "0.9rem" },
  btnDanger: { padding: "8px 18px", background: "transparent", color: "#ef4444", border: "1px solid #ef4444", borderRadius: 6, cursor: "pointer", fontSize: "0.9rem" },
  btnGhost: { padding: "6px 14px", background: "transparent", color: "inherit", border: BORDER, borderRadius: 6, cursor: "pointer" },
};
