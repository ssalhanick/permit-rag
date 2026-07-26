import React, { useCallback, useEffect, useState } from "react";
import { confirmAgentCorrection, listAgentCorrections } from "../api.js";

const AGENTS = [
  "retriever", "answer_generator", "prompt_router", "guardrail", "manager", "media_curator",
];

/**
 * Dashboard v2 (Phase 5) — the Performance Review (#24) confirm queue. Each row
 * is an unconfirmed attribution the reviewer either accepts as-is or re-assigns
 * before confirming. Confirming is the human sign-off that turns the attribution
 * into training data (docs/agent_architecture.md, "never silent blame").
 */
export default function CorrectionQueue() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [reassign, setReassign] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listAgentCorrections({ confirmed: false });
      setRows(res.data?.corrections || []);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const confirm = async (row) => {
    setBusyId(row.id);
    try {
      await confirmAgentCorrection(row.id, reassign[row.id] || null);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "#b91c1c" }}>{error}</p>;
  if (rows.length === 0)
    return <p style={{ color: "#6b7280" }}>No unconfirmed attributions. 🎉</p>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {rows.map((r) => (
        <div key={r.id} style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: "0.75rem" }}>
          <div style={{ fontSize: "0.85rem", color: "#6b7280" }}>
            run {r.run_id || "—"} · confidence{" "}
            {r.attribution_confidence == null ? "—" : Number(r.attribution_confidence).toFixed(2)}
          </div>
          <div style={{ margin: "0.25rem 0" }}>
            Attributed to:{" "}
            <strong>{r.attributed_agent || "unassigned (needs a human)"}</strong>
          </div>
          {r.notes && (
            <div style={{ fontSize: "0.85rem", whiteSpace: "pre-wrap", color: "#374151" }}>{r.notes}</div>
          )}
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "0.5rem" }}>
            <label style={{ fontSize: "0.85rem" }}>
              Re-assign:{" "}
              <select
                value={reassign[r.id] || r.attributed_agent || ""}
                onChange={(e) => setReassign((m) => ({ ...m, [r.id]: e.target.value }))}
              >
                <option value="">(keep)</option>
                {AGENTS.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </label>
            <button type="button" onClick={() => confirm(r)} disabled={busyId === r.id}>
              {busyId === r.id ? "Confirming…" : "Confirm"}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
