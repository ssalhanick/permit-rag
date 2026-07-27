import React, { useState } from "react";
import ActionQueue from "./ActionQueue.jsx";
import MetadataReviewPane from "./MetadataReviewPane.jsx";
import DocumentMetadataTable from "./DocumentMetadataTable.jsx";
import AgentScorecard from "./AgentScorecard.jsx";
import AutonomyPanel from "./AutonomyPanel.jsx";
import CorrectionQueue from "./CorrectionQueue.jsx";
import AgentGlossary from "./AgentGlossary.jsx";

const TABS = [
  { key: "queue", label: "Action Queue" },
  { key: "glossary", label: "Agent Glossary" },
  { key: "scorecard", label: "Scorecard" },
  { key: "corrections", label: "Corrections" },
  { key: "autonomy", label: "Autonomy" },
  { key: "metadata", label: "Metadata Review" },
  { key: "documents", label: "Documents" },
];

/**
 * Superadmin agent dashboard. Phase 3 shipped the action queue + metadata
 * review; Phase 5's dashboard v2 adds the Scorecard (per-agent trace rollup +
 * answer feedback), the Corrections confirm-queue (Performance Review #24
 * sign-off), the Autonomy control panel, and the Agent Glossary. Gated by
 * SuperadminRoute (frontend) and by is_superadmin() on every backend route.
 */
export default function AgentDashboardPage() {
  const [tab, setTab] = useState("queue");

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "1.5rem" }}>
      <h1>Agent Dashboard</h1>
      <p style={{ color: "#6b7280" }}>Superadmin only · glossary · scorecard · corrections · autonomy · queue</p>

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

      {tab === "queue" && <ActionQueue />}
      {tab === "glossary" && <AgentGlossary />}
      {tab === "scorecard" && <AgentScorecard />}
      {tab === "corrections" && <CorrectionQueue />}
      {tab === "autonomy" && <AutonomyPanel />}
      {tab === "metadata" && <MetadataReviewPane />}
      {tab === "documents" && <DocumentMetadataTable />}
    </div>
  );
}
