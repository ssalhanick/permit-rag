import React, { useCallback, useEffect, useState } from "react";
import { listAgentActionItems, resolveAgentActionItem } from "../api.js";

const SEVERITY_COLOR = {
  critical: "#b00020",
  high: "#d9822b",
  medium: "#3b6ea5",
  low: "#6b7280",
};

/**
 * The action queue — every open agent_action_items row, most severe first.
 * A superadmin resolves or dismisses inline with a note. This is the landing
 * slice of the Phase 3 dashboard; the metadata review pane is its sibling.
 */
export default function ActionQueue() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("open");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listAgentActionItems({ status });
      setItems(res.data?.items || []);
    } catch (err) {
      setError(err.message || "Failed to load action items.");
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (item, nextStatus) => {
    setBusyId(item.id);
    try {
      const note = window.prompt(`Note for ${nextStatus} (optional):`, "") || null;
      await resolveAgentActionItem(item.id, { status: nextStatus, note });
      await load();
    } catch (err) {
      setError(err.message || "Action failed.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", marginBottom: "1rem" }}>
        <label>
          Status:{" "}
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="open">open</option>
            <option value="acknowledged">acknowledged</option>
            <option value="resolved">resolved</option>
            <option value="dismissed">dismissed</option>
          </select>
        </label>
        <button type="button" onClick={load}>Refresh</button>
        <span style={{ color: "#6b7280" }}>{items.length} item(s)</span>
      </div>

      {error && <p style={{ color: "#b00020" }}>{error}</p>}
      {loading ? (
        <p>Loading…</p>
      ) : items.length === 0 ? (
        <p>No {status} action items. 🎉</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {items.map((item) => (
            <li
              key={item.id}
              style={{
                border: "1px solid #e5e7eb",
                borderLeft: `4px solid ${SEVERITY_COLOR[item.severity] || "#6b7280"}`,
                borderRadius: 6,
                padding: "0.75rem 1rem",
                marginBottom: "0.75rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}>
                <div>
                  <strong>{item.title}</strong>
                  <div style={{ fontSize: "0.85rem", color: "#6b7280" }}>
                    {item.source_agent} · {item.kind} · {item.severity}
                    {item.blocking ? " · blocking" : ""}
                    {item.entity_id ? ` · ${item.entity_type}:${item.entity_id}` : ""}
                  </div>
                  {item.proposed_action && (
                    <div style={{ fontSize: "0.85rem", marginTop: "0.25rem" }}>
                      Proposed: {item.proposed_action}
                    </div>
                  )}
                </div>
                {status === "open" || status === "acknowledged" ? (
                  <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
                    <button type="button" disabled={busyId === item.id}
                      onClick={() => act(item, "resolved")}>Resolve</button>
                    <button type="button" disabled={busyId === item.id}
                      onClick={() => act(item, "dismissed")}>Dismiss</button>
                  </div>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
