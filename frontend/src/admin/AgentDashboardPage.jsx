import React, { useState } from "react";
import ActionQueue from "./ActionQueue.jsx";
import MetadataReviewPane from "./MetadataReviewPane.jsx";

const TABS = [
  { key: "queue", label: "Action Queue" },
  { key: "metadata", label: "Metadata Review" },
];

/**
 * Superadmin agent dashboard, v1 (Phase 3). Two slices this phase: the action
 * queue (landing) and the metadata review pane. The scorecard, trace explorer,
 * autonomy, and prompt tabs are Phase 5's dashboard v2. Gated by SuperadminRoute
 * (frontend) and by is_superadmin() on every backend route.
 */
export default function AgentDashboardPage() {
  const [tab, setTab] = useState("queue");

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "1.5rem" }}>
      <h1>Agent Dashboard</h1>
      <p style={{ color: "#6b7280" }}>Superadmin only · Phase 3 (action queue + metadata review)</p>

      <div style={{ display: "flex", gap: "0.5rem", borderBottom: "1px solid #e5e7eb", margin: "1rem 0" }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            style={{
              padding: "0.5rem 1rem",
              border: "none",
              borderBottom: tab === t.key ? "2px solid #3b6ea5" : "2px solid transparent",
              background: "none",
              fontWeight: tab === t.key ? 600 : 400,
              cursor: "pointer",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "queue" ? <ActionQueue /> : <MetadataReviewPane />}
    </div>
  );
}
