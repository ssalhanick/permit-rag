import React, { useEffect, useState } from "react";
import { getAgentScorecard, getFeedbackSummary } from "../api.js";

/**
 * Dashboard v2 (Phase 5) — per-agent scorecard + answer-feedback summary.
 * Read-only rollup over the trace store: calls, deterministic-hit-rate, error
 * rate, latency, plus the thumbs up/down totals from the feedback loop.
 */
export default function AgentScorecard() {
  const [days, setDays] = useState(7);
  const [agents, setAgents] = useState([]);
  const [feedback, setFeedback] = useState({ up: 0, down: 0 });
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    setLoading(true);
    Promise.all([getAgentScorecard({ days }), getFeedbackSummary({ days })])
      .then(([score, fb]) => {
        if (!live) return;
        setAgents(score.data?.agents || []);
        setFeedback(fb.data?.feedback || { up: 0, down: 0 });
        setError(null);
      })
      .catch((e) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [days]);

  const pct = (v) => (v == null ? "—" : `${Math.round(Number(v) * 100)}%`);
  const num = (v) => (v == null ? "—" : Math.round(Number(v)));

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "0.75rem" }}>
        <label>
          Window:{" "}
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={1}>1 day</option>
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
          </select>
        </label>
        <span style={{ color: "#6b7280" }}>
          Answer feedback: 👍 {feedback.up} · 👎 {feedback.down}
        </span>
      </div>

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
      {loading ? (
        <p>Loading…</p>
      ) : agents.length === 0 ? (
        <p style={{ color: "#6b7280" }}>No agent traces in this window.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th>Agent</th><th>Calls</th><th>Det. rate</th><th>Err. rate</th>
              <th>p50 ms</th><th>p95 ms</th><th>Cost $</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => (
              <tr key={a.agent_name} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td>{a.agent_name}</td>
                <td>{num(a.calls)}</td>
                <td>{pct(a.deterministic_rate)}</td>
                <td>{pct(a.error_rate)}</td>
                <td>{num(a.p50_latency_ms)}</td>
                <td>{num(a.p95_latency_ms)}</td>
                <td>{a.cost_usd == null ? "—" : Number(a.cost_usd).toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
