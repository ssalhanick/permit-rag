import React, { useCallback, useEffect, useState } from "react";
import { applyMetadataCorrection, listMetadataReview } from "../api.js";

/**
 * Metadata review pane — the validator's needs_review items, each carrying its
 * proposals and source-chunk citations (in the item's evidence JSONB). The
 * superadmin selects which proposed fields to accept and approves; the approve
 * call writes through ingestion.governance (the single corpus writer) and
 * resolves the item.
 *
 * Every proposal shows its citation, so approval is never a blind click — the
 * whole point of the review surface (docs/agent_architecture.md).
 */
export default function MetadataReviewPane() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState({}); // itemId -> Set of field names
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listMetadataReview({ status: "open" });
      setItems(res.data?.items || []);
    } catch (err) {
      setError(err.message || "Failed to load metadata review queue.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggle = (itemId, fieldName) => {
    setSelected((prev) => {
      const current = new Set(prev[itemId] || []);
      current.has(fieldName) ? current.delete(fieldName) : current.add(fieldName);
      return { ...prev, [itemId]: current };
    });
  };

  const approve = async (item) => {
    const proposals = item.evidence?.proposals || [];
    const chosen = selected[item.id] || new Set();
    const body = { item_id: item.id };
    for (const p of proposals) {
      if (!chosen.has(p.field)) continue;
      if (p.field === "subject_tags") body.subject_tags = p.proposed;
      else body[p.field] = p.proposed;
    }
    const hasField = ["effective_date", "doc_type", "authority_level", "subject_tags"]
      .some((f) => body[f] !== undefined);
    if (!hasField) {
      setError("Select at least one proposed field to apply.");
      return;
    }
    setBusyId(item.id);
    setError(null);
    try {
      await applyMetadataCorrection(item.entity_id, body);
      await load();
    } catch (err) {
      setError(err.message || "Apply failed.");
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <p>Loading…</p>;

  return (
    <div>
      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1rem" }}>
        <button type="button" onClick={load}>Refresh</button>
        <span style={{ color: "#6b7280" }}>{items.length} document(s) awaiting review</span>
      </div>
      {error && <p style={{ color: "#b00020" }}>{error}</p>}
      {items.length === 0 ? (
        <p>No documents awaiting metadata review. 🎉</p>
      ) : (
        items.map((item) => (
          <ReviewCard
            key={item.id}
            item={item}
            selected={selected[item.id] || new Set()}
            onToggle={(field) => toggle(item.id, field)}
            onApprove={() => approve(item)}
            busy={busyId === item.id}
          />
        ))
      )}
    </div>
  );
}

function ReviewCard({ item, selected, onToggle, onApprove, busy }) {
  const ev = item.evidence || {};
  const proposals = ev.proposals || [];
  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, padding: "1rem", marginBottom: "1rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <strong>{item.entity_id}</strong>
        <span style={{ color: "#6b7280", fontSize: "0.85rem" }}>{item.kind}</span>
      </div>
      {ev.completeness_failures?.length > 0 && (
        <div style={{ fontSize: "0.85rem", color: "#6b7280", marginTop: "0.25rem" }}>
          Missing: {ev.completeness_failures.join(", ")}
        </div>
      )}
      {ev.supersession_candidates?.length > 0 && (
        <div style={{ fontSize: "0.85rem", color: "#d9822b", marginTop: "0.25rem" }}>
          Supersession family: {ev.supersession_candidates.join(", ")} — resolve manually (never auto-supersede).
        </div>
      )}

      {proposals.length === 0 ? (
        <p style={{ fontSize: "0.9rem" }}>No auto-proposals — supply values manually.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "0.75rem", fontSize: "0.9rem" }}>
          <thead>
            <tr style={{ textAlign: "left", color: "#6b7280" }}>
              <th>Apply</th><th>Field</th><th>Current → Proposed</th><th>Conf.</th><th>Citation</th>
            </tr>
          </thead>
          <tbody>
            {proposals.map((p) => (
              <tr key={p.field} style={{ borderTop: "1px solid #f0f0f0" }}>
                <td>
                  <input type="checkbox" checked={selected.has(p.field)}
                    onChange={() => onToggle(p.field)} />
                </td>
                <td>{p.field}</td>
                <td>
                  <span style={{ color: "#6b7280" }}>{JSON.stringify(p.current)}</span>
                  {" → "}
                  <strong>{JSON.stringify(p.proposed)}</strong>
                </td>
                <td>{typeof p.confidence === "number" ? p.confidence.toFixed(2) : "—"}</td>
                <td>
                  {p.citation?.chunk_index != null ? (
                    <span title={p.citation.excerpt || ""}>
                      chunk {p.citation.chunk_index}
                      {p.citation.excerpt ? `: “${p.citation.excerpt.slice(0, 60)}…”` : ""}
                    </span>
                  ) : (
                    <span style={{ color: "#b00020" }}>no citation</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ marginTop: "0.75rem" }}>
        <button type="button" disabled={busy || proposals.length === 0} onClick={onApprove}>
          {busy ? "Applying…" : "Approve selected"}
        </button>
      </div>
    </div>
  );
}
