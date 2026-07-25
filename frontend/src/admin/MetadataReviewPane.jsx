import React, { useCallback, useEffect, useState } from "react";
import { applyMetadataCorrection, listMetadataReview } from "../api.js";

/**
 * Metadata review pane — the validator's needs_review items, each carrying its
 * proposals and source-chunk citations (in the item's evidence JSONB). The
 * superadmin selects which proposed fields to accept, may edit any proposed
 * value inline (double-click it), and approves; the approve call writes the
 * chosen values through ingestion.governance (the single corpus writer) and
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
  const [edits, setEdits] = useState({}); // itemId -> { field -> edited string }
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

  // Editing a value implies you want to apply it, so also select the field.
  const setEdit = (itemId, fieldName, value) => {
    setEdits((prev) => ({ ...prev, [itemId]: { ...(prev[itemId] || {}), [fieldName]: value } }));
    setSelected((prev) => {
      const current = new Set(prev[itemId] || []);
      current.add(fieldName);
      return { ...prev, [itemId]: current };
    });
  };

  const approve = async (item) => {
    const proposals = item.evidence?.proposals || [];
    const chosen = selected[item.id] || new Set();
    const itemEdits = edits[item.id] || {};
    const body = { item_id: item.id };
    for (const p of proposals) {
      if (!chosen.has(p.field)) continue;
      const raw = itemEdits[p.field];
      body[p.field] = coerceValue(p, raw);
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
      <div style={S.toolbar}>
        <button type="button" style={S.btnGhost} onClick={load}>Refresh</button>
        <span style={S.muted}>{items.length} document(s) awaiting review</span>
        <span style={{ ...S.muted, marginLeft: "auto" }}>
          Tip: double-click a proposed value to edit it before approving.
        </span>
      </div>
      {error && <p style={S.error}>{error}</p>}
      {items.length === 0 ? (
        <p>No documents awaiting metadata review. 🎉</p>
      ) : (
        items.map((item) => (
          <ReviewCard
            key={item.id}
            item={item}
            selected={selected[item.id] || new Set()}
            itemEdits={edits[item.id] || {}}
            onToggle={(field) => toggle(item.id, field)}
            onEdit={(field, value) => setEdit(item.id, field, value)}
            onApprove={() => approve(item)}
            busy={busyId === item.id}
          />
        ))
      )}
    </div>
  );
}

function ReviewCard({ item, selected, itemEdits, onToggle, onEdit, onApprove, busy }) {
  const ev = item.evidence || {};
  const proposals = ev.proposals || [];
  return (
    <div style={S.card}>
      <div style={S.cardHead}>
        <strong style={S.docId}>{item.entity_id}</strong>
        <span style={S.kind}>{item.kind}</span>
      </div>
      {ev.completeness_failures?.length > 0 && (
        <div style={S.meta}>Missing: {ev.completeness_failures.join(", ")}</div>
      )}
      {ev.supersession_candidates?.length > 0 && (
        <div style={{ ...S.meta, color: "#d9822b" }}>
          Supersession family: {ev.supersession_candidates.join(", ")} — resolve manually
          (never auto-supersede).
        </div>
      )}

      {proposals.length === 0 ? (
        <p style={S.muted}>No auto-proposals — supply values manually.</p>
      ) : (
        <table style={S.table}>
          <colgroup>
            <col style={{ width: "52px" }} />
            <col style={{ width: "150px" }} />
            <col />
            <col style={{ width: "56px" }} />
            <col style={{ width: "220px" }} />
          </colgroup>
          <thead>
            <tr>
              <th style={S.th}>Apply</th>
              <th style={S.th}>Field</th>
              <th style={S.th}>Current → Proposed</th>
              <th style={S.th}>Conf.</th>
              <th style={S.th}>Citation</th>
            </tr>
          </thead>
          <tbody>
            {proposals.map((p) => (
              <tr key={p.field}>
                <td style={S.td}>
                  <input
                    type="checkbox"
                    checked={selected.has(p.field)}
                    onChange={() => onToggle(p.field)}
                  />
                </td>
                <td style={{ ...S.td, fontWeight: 600 }}>{p.field}</td>
                <td style={S.td}>
                  <div style={S.current}>{formatValue(p.current)}</div>
                  <div style={S.arrow}>
                    →{" "}
                    <EditableValue
                      field={p.field}
                      proposed={p.proposed}
                      edited={itemEdits[p.field]}
                      onEdit={(v) => onEdit(p.field, v)}
                    />
                  </div>
                </td>
                <td style={S.td}>{typeof p.confidence === "number" ? p.confidence.toFixed(2) : "—"}</td>
                <td style={S.tdCite}>
                  {p.citation?.chunk_index != null ? (
                    <span title={p.citation.excerpt || ""}>
                      chunk {p.citation.chunk_index}
                      {p.citation.excerpt ? `: “${p.citation.excerpt.slice(0, 60)}…”` : ""}
                    </span>
                  ) : (
                    <span style={S.error}>no citation</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={S.cardFoot}>
        <button type="button" style={S.btnPrimary} disabled={busy || proposals.length === 0} onClick={onApprove}>
          {busy ? "Applying…" : "Approve selected"}
        </button>
      </div>
    </div>
  );
}

/** Proposed value: shows as text, double-click to edit inline. */
function EditableValue({ field, proposed, edited, onEdit }) {
  const [editing, setEditing] = useState(false);
  const shown = edited !== undefined ? edited : toEditString(field, proposed);

  if (editing) {
    return (
      <input
        autoFocus
        style={S.editInput}
        value={shown}
        onChange={(e) => onEdit(e.target.value)}
        onBlur={() => setEditing(false)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === "Escape") setEditing(false);
        }}
      />
    );
  }
  return (
    <strong
      style={S.editable}
      title="Double-click to edit"
      onDoubleClick={() => setEditing(true)}
    >
      {shown || <span style={S.muted}>(empty)</span>}
    </strong>
  );
}

// ── value helpers ────────────────────────────────────────────

function formatValue(v) {
  if (Array.isArray(v)) return v.join(", ");
  if (v === null || v === undefined) return "—";
  return String(v);
}

function toEditString(field, proposed) {
  if (field === "subject_tags") return (proposed || []).join(", ");
  return proposed == null ? "" : String(proposed);
}

/** Turn the edited string (or untouched proposal) into the API payload value. */
function coerceValue(p, raw) {
  if (raw === undefined) return p.proposed; // untouched — already the right type
  if (p.field === "subject_tags") {
    return raw.split(",").map((s) => s.trim()).filter(Boolean);
  }
  return raw.trim();
}

// ── styles ───────────────────────────────────────────────────

const BORDER = "1px solid rgba(148,163,184,0.35)";
const S = {
  toolbar: { display: "flex", gap: "0.75rem", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap" },
  muted: { color: "#94a3b8", fontSize: "0.85rem" },
  error: { color: "#ef4444" },
  card: { border: BORDER, borderRadius: 10, padding: "1rem 1.25rem", marginBottom: "1.25rem" },
  cardHead: { display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "1rem", marginBottom: "0.5rem" },
  docId: { fontSize: "1.05rem", wordBreak: "break-all" },
  kind: { color: "#94a3b8", fontSize: "0.8rem", whiteSpace: "nowrap" },
  meta: { fontSize: "0.85rem", color: "#94a3b8", margin: "0.15rem 0" },
  table: { width: "100%", borderCollapse: "collapse", marginTop: "0.75rem", fontSize: "0.9rem", tableLayout: "fixed" },
  th: { textAlign: "left", color: "#94a3b8", fontWeight: 500, padding: "6px 12px", borderBottom: BORDER },
  td: { padding: "10px 12px", verticalAlign: "top", borderBottom: BORDER, wordBreak: "break-word" },
  tdCite: { padding: "10px 12px", verticalAlign: "top", borderBottom: BORDER, wordBreak: "break-word", color: "#94a3b8", fontSize: "0.82rem" },
  current: { color: "#94a3b8", marginBottom: 4, wordBreak: "break-word" },
  arrow: { wordBreak: "break-word" },
  editable: { borderBottom: "1px dashed rgba(148,163,184,0.6)", cursor: "text" },
  editInput: { width: "100%", boxSizing: "border-box", padding: "5px 8px", fontFamily: "inherit", fontSize: "0.9rem", color: "inherit", background: "rgba(148,163,184,0.12)", border: BORDER, borderRadius: 5 },
  cardFoot: { marginTop: "0.85rem" },
  btnPrimary: { padding: "8px 18px", background: "#2f6feb", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: "0.9rem" },
  btnGhost: { padding: "6px 14px", background: "transparent", color: "inherit", border: BORDER, borderRadius: 6, cursor: "pointer" },
};
