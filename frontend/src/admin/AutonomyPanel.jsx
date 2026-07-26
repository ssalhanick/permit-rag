import React, { useCallback, useEffect, useState } from "react";
import { listAgentAutonomy, setAgentAutonomy } from "../api.js";

const LEVELS = ["L0", "L1", "L2", "L3"];
const rank = (l) => LEVELS.indexOf(l);

/**
 * Dashboard v2 (Phase 5) — per-agent autonomy control. Each agent has a level
 * slider clamped to its ceiling (max_level); the backend rejects (409) anything
 * above the ceiling, so a control that could turn a filing agent all the way up
 * is not possible. The ceiling reason is shown alongside.
 */
export default function AutonomyPanel() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listAgentAutonomy();
      setRows(res.data?.agents || []);
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

  const change = async (row, level) => {
    setBusy(row.agent_name);
    try {
      await setAgentAutonomy(row.agent_name, level, row.scope || "default");
      await load();
    } catch (e) {
      setError(`${row.agent_name}: ${e.message}`);
    } finally {
      setBusy(null);
    }
  };

  if (loading) return <p>Loading…</p>;
  if (error) return <p style={{ color: "#b91c1c" }}>{error}</p>;
  if (rows.length === 0) return <p style={{ color: "#6b7280" }}>No registered agents.</p>;

  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
      <thead>
        <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
          <th>Agent</th><th>Scope</th><th>Level</th><th>Ceiling</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={`${r.agent_name}:${r.scope}`} style={{ borderBottom: "1px solid #f3f4f6" }}>
            <td>{r.agent_name}</td>
            <td>{r.scope}</td>
            <td>
              <select
                value={r.current_level}
                disabled={busy === r.agent_name}
                onChange={(e) => change(r, e.target.value)}
              >
                {LEVELS.map((l) => (
                  <option key={l} value={l} disabled={rank(l) > rank(r.max_level)}>
                    {l}
                  </option>
                ))}
              </select>
            </td>
            <td title="Level cannot exceed this ceiling" style={{ color: "#6b7280" }}>
              max {r.max_level}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
