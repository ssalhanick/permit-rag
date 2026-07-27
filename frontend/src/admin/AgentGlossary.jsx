import React, { useCallback, useEffect, useState } from "react";
import { fetchAgentGlossary } from "../api.js";

// Static fallback data in case the API call fails or runs offline
const FALLBACK_GLOSSARY = [
  {
    name: "manager",
    display_name: "Pipeline Manager / Orchestrator",
    category: "Control & Safety",
    tier: "cheap",
    execution_mode: "Hybrid (Deterministic State Machine + Delegation)",
    autonomy_ceiling: "L3",
    description: "Central orchestrator for the multi-wave /query/answer RAG pipeline. Coordinates intent routing, query deconstruction, retrieval, grounding checks, answer generation, and citation verification across 5 waves.",
    dependencies: {
      calls: [
        "permit_classifier", "jurisdiction_resolver", "project_context",
        "query_deconstructor", "retriever", "conflict_detector",
        "mini_rag_conflicts", "prompt_router", "budget_governor",
        "answer_generator", "citation_verifier", "media_curator", "guardrail"
      ],
      called_by: ["api/routes/query.py (/query/answer)"]
    },
    inputs: ["query", "top_k", "municipality", "address", "project_id", "chunk_ids"],
    outputs: ["ManagerResult (ArtifactRefs, answer text, citations, conflict warnings, media links, abstain status)"],
    metrics: ["routing_accuracy", "plan_length", "replan_rate", "react_iterations"],
    governance_rules: ["Bounded at MAX_ITERATIONS = 6", "Must never import commerce/, forms/, or bids/ directly"]
  },
  {
    name: "budget_governor",
    display_name: "Budget & Token Governor",
    category: "Control & Safety",
    tier: "cheap",
    execution_mode: "Deterministic",
    autonomy_ceiling: "L3",
    description: "Tracks token usage and dollar budgets across agent runs. Enforces tier degradation (e.g. Sonnet -> Haiku) and context trimming when token/cost caps are approached.",
    dependencies: {
      calls: [],
      called_by: ["manager", "rag.agent_runtime"]
    },
    inputs: ["agent_name", "context chunks", "budget_limits"],
    outputs: ["Degraded chunk sets", "Tier overrides", "Token usage accounting"],
    metrics: ["budget_trips", "degradation_rate"],
    governance_rules: ["Deterministic execution", "Cannot be bypassed by non-superadmins"]
  },
  {
    name: "prompt_router",
    display_name: "Prompt Router & Persona Composer",
    category: "Control & Safety",
    tier: "cheap",
    execution_mode: "Deterministic Fragment Lookup",
    autonomy_ceiling: "L3",
    description: "Assembles persona-tailored system prompts (DIY homeowner, contractor, architect, inspector, research) and jurisdiction-specific regulatory fragments dynamically.",
    dependencies: {
      calls: ["rag/prompts/ fragment library"],
      called_by: ["manager"]
    },
    inputs: ["persona", "jurisdiction", "intent", "experience", "project_notes"],
    outputs: ["RoutedPrompt (composed system prompt string, max_tokens, persona, fragment_ids)"],
    metrics: ["fragment_selection_accuracy", "persona_appropriateness", "default_to_research_rate"],
    governance_rules: ["Defaults to 'research' persona when user persona is missing/unknown"]
  },
  {
    name: "guardrail",
    display_name: "Output & Truncation Guardrail",
    category: "Control & Safety",
    tier: "cheap",
    execution_mode: "Deterministic Rules",
    autonomy_ceiling: "L3",
    description: "Monitors output generation for truncation, incomplete answers, and untrusted external media URLs. Filters out unverified domains.",
    dependencies: {
      calls: [],
      called_by: ["manager"]
    },
    inputs: ["GenerationResult", "query", "entity_id", "media_refs"],
    outputs: ["Truncation status", "Sanitized media_refs list"],
    metrics: ["guard_trip_rate"],
    governance_rules: ["Non-fatal check; logs warnings without throwing 500 errors"]
  },
  {
    name: "answer_generator",
    display_name: "Compliance Answer Generator",
    category: "Answer Synthesis",
    tier: "mid",
    execution_mode: "LLM-backed (Claude Sonnet / Haiku)",
    autonomy_ceiling: "L3",
    description: "Synthesizes formal municipal building compliance answers grounded exclusively in retrieved code chunks with required inline citations [doc_id, chunk_index].",
    dependencies: {
      calls: ["rag.agent_runtime"],
      called_by: ["manager"]
    },
    inputs: ["user query", "passing retrieved chunks", "RoutedPrompt", "project_context"],
    outputs: ["GenerationResult (answer string, citations list, model, token usage, latency)"],
    metrics: ["faithfulness", "answer_relevancy", "citation_density"],
    governance_rules: ["Must include at least one valid inline citation", "Never cite superseded documents as sole source"]
  },
  {
    name: "permit_classifier",
    display_name: "Permit Type Classifier",
    category: "Domain & Context",
    tier: "cheap",
    execution_mode: "Deterministic NLI & Heuristics",
    autonomy_ceiling: "L3",
    description: "Classifies the required permit categories (building, electrical, plumbing, mechanical, zoning, fire, energy, demolition) relevant to the user query.",
    dependencies: {
      calls: [],
      called_by: ["manager"]
    },
    inputs: ["query text"],
    outputs: ["List of permit category strings"],
    metrics: ["permit_type_f1"],
    governance_rules: ["Non-blocking; defaults to empty list [] on error"]
  },
  {
    name: "jurisdiction_resolver",
    display_name: "Jurisdiction & Geocoding Resolver",
    category: "Domain & Context",
    tier: "cheap",
    execution_mode: "Deterministic GIS & Geocoding",
    autonomy_ceiling: "L3",
    description: "Geocodes project addresses or parses location names to identify the governing municipality (Dallas, Fort Worth, Plano, Frisco, McKinney).",
    dependencies: {
      calls: ["GIS address geocoding"],
      called_by: ["manager"]
    },
    inputs: ["address string or site description"],
    outputs: ["Municipality name string"],
    metrics: ["municipality_accuracy"],
    governance_rules: ["Precedence: explicit request > project kickoff > geocoded address"]
  },
  {
    name: "conflict_detector",
    display_name: "Municipal Code Conflict Detector",
    category: "Domain & Context",
    tier: "cheap",
    execution_mode: "Deterministic Rule Matching",
    autonomy_ceiling: "L3",
    description: "Detects conflicts or contradictory regulations between retrieved municipal ordinances and state/federal building standards.",
    dependencies: {
      calls: [],
      called_by: ["manager"]
    },
    inputs: ["list of retrieved chunks"],
    outputs: ["list of ConflictWarning items"],
    metrics: ["detection_precision", "false_alarm_rate"],
    governance_rules: ["Must surface ConflictWarning rather than silently resolving code differences"]
  },
  {
    name: "citation_verifier",
    display_name: "Citation & Grounding Verifier",
    category: "Control & Safety",
    tier: "mid",
    execution_mode: "Hybrid (Deterministic Span Match + LLM Entailment)",
    autonomy_ceiling: "L3",
    description: "Verifies that every statement and citation in the generated compliance answer is backed by source chunks. Flags hallucinated or unsupported citations.",
    dependencies: {
      calls: ["rag.agent_runtime"],
      called_by: ["manager"]
    },
    inputs: ["generated answer text", "citations list", "source chunks"],
    outputs: ["Verification report", "unsupported_citations list", "claim precision/recall"],
    metrics: ["claim_precision", "claim_recall"],
    governance_rules: ["Runs in Wave 5 post-generation; flags hallucinated claims without blocking response delivery"]
  },
  {
    name: "query_deconstructor",
    display_name: "Compound Query Deconstructor",
    category: "Domain & Context",
    tier: "cheap",
    execution_mode: "Hybrid (Deterministic Gating + Single-shot LLM)",
    autonomy_ceiling: "L3",
    description: "Deconstructs complex multi-part building queries into individual sub-questions to allow targeted parallel retrievals across different code sections.",
    dependencies: {
      calls: ["rag.retriever"],
      called_by: ["manager"]
    },
    inputs: ["complex query text"],
    outputs: ["sub_questions list"],
    metrics: ["sub_question_coverage", "filter_precision"],
    governance_rules: ["Gated deterministically: simple queries bypass LLM deconstruction"]
  },
  {
    name: "permit_strategy",
    display_name: "Permit Strategy & Fee Planner",
    category: "Domain & Context",
    tier: "cheap",
    execution_mode: "Hybrid (Deterministic Calculation + LLM Guidance Note)",
    autonomy_ceiling: "L3",
    description: "Plans required permit filing sequences, estimates filing fees, and outlines submittal prerequisites for construction projects.",
    dependencies: {
      calls: ["db/client.py"],
      called_by: ["api/routes/projects.py", "manager"]
    },
    inputs: ["project_id", "municipality", "permit_types"],
    outputs: ["PermitPlan (permit list, submission order, fee estimates, strategy notes)"],
    metrics: ["permit_set_f1"],
    governance_rules: ["Calculations are deterministic; only the strategy note uses an LLM"]
  },
  {
    name: "mini_rag_conflicts",
    display_name: "Project Upload Conflict Detector",
    category: "Domain & Context",
    tier: "cheap",
    execution_mode: "Deterministic Comparison",
    autonomy_ceiling: "L3",
    description: "Compares user-uploaded project documents (architectural drawings, contractor specs) against city municipal code chunks to identify project discrepancies.",
    dependencies: {
      calls: [],
      called_by: ["manager"]
    },
    inputs: ["corpus chunks", "user project chunks"],
    outputs: ["upload_conflicts list"],
    metrics: ["detection_precision"],
    governance_rules: ["Non-blocking check; flags project vs code differences as warnings"]
  },
  {
    name: "project_context",
    display_name: "Project Context & Fact Loader",
    category: "Domain & Context",
    tier: "cheap",
    execution_mode: "Deterministic DB Lookup",
    autonomy_ceiling: "L3",
    description: "Loads project facts, site location, kickoff specs, active room scans, and user preferences into the active pipeline session.",
    dependencies: {
      calls: ["db/client.py"],
      called_by: ["manager"]
    },
    inputs: ["project_id"],
    outputs: ["project_context dict / ArtifactRef"],
    metrics: ["fact_coverage"],
    governance_rules: ["Runs in Wave 1; cached in ArtifactStore per session"]
  },
  {
    name: "design_intent",
    display_name: "Design Intent & Spec Parser",
    category: "Domain & Context",
    tier: "cheap",
    execution_mode: "LLM Structured Extraction",
    autonomy_ceiling: "L2",
    description: "Parses unstructured architectural notes, room scan specs, and construction goals into a structured design intent schema for compliance checking.",
    dependencies: {
      calls: ["rag.agent_runtime"],
      called_by: ["api/routes/projects.py"]
    },
    inputs: ["room scan specs", "architectural notes"],
    outputs: ["Structured design intent overlay"],
    metrics: ["schema_validity", "overlay_precision"],
    governance_rules: ["Validated against Pydantic schema before saving"]
  },
  {
    name: "media_curator",
    display_name: "Instructional Media & DIY Linker",
    category: "Domain & Context",
    tier: "cheap",
    execution_mode: "Deterministic Mapping + Semantic Search",
    autonomy_ceiling: "L3",
    description: "Curates verified step-by-step instructional video tutorials, official guides, and timestamped media links for DIY homeowner queries.",
    dependencies: {
      calls: ["db/client.py"],
      called_by: ["manager"]
    },
    inputs: ["query", "persona ('diy')", "jurisdiction", "permit_types"],
    outputs: ["media_refs list (title, URL, channel, timestamp)"],
    metrics: ["link_liveness", "relevance", "zero_unsourced_urls"],
    governance_rules: ["Runs on DIY persona paths; all URLs checked against guardrail allowlists"]
  },
  {
    name: "metadata_validator",
    display_name: "Corpus Metadata Validator",
    category: "Governance & Maintenance",
    tier: "mid",
    execution_mode: "Hybrid (Deterministic Schema Check + LLM Sampling)",
    autonomy_ceiling: "L1",
    description: "Audits corpus document metadata (effective_date, doc_type, authority_level, subject_tags) against chunk text. Generates proposals for human review in the dashboard queue.",
    dependencies: {
      calls: ["rag.agent_runtime", "ingestion.governance"],
      called_by: ["ingestion scripts", "admin action queue"]
    },
    inputs: ["Corpus document rows", "sampled chunks"],
    outputs: ["ValidationReport", "action_items proposals"],
    metrics: ["enum_precision", "date_extraction_accuracy", "tag_vocab_compliance"],
    governance_rules: ["L1 Autonomy (Human-in-the-loop): Cannot edit corpus directly. Writes proposals to action queue; human approval in Metadata Review Pane invokes ingestion.governance."]
  }
];

const CATEGORIES = ["All", "Control & Safety", "Answer Synthesis", "Domain & Context", "Governance & Maintenance"];

export default function AgentGlossary() {
  const [agents, setAgents] = useState(FALLBACK_GLOSSARY);
  const [search, setSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [expandedAgent, setExpandedAgent] = useState("manager");
  const [loading, setLoading] = useState(false);

  const loadGlossary = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchAgentGlossary();
      if (res.data?.agents && res.data.agents.length > 0) {
        setAgents(res.data.agents);
      }
    } catch {
      // Fallback data is already loaded in state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGlossary();
  }, [loadGlossary]);

  const filteredAgents = agents.filter((a) => {
    const matchesCategory = selectedCategory === "All" || a.category === selectedCategory;
    const q = search.toLowerCase();
    const matchesSearch =
      !q ||
      a.name.toLowerCase().includes(q) ||
      a.display_name.toLowerCase().includes(q) ||
      a.description.toLowerCase().includes(q) ||
      (a.metrics && a.metrics.some((m) => m.toLowerCase().includes(q)));
    return matchesCategory && matchesSearch;
  });

  const totalCount = agents.length;
  const deterministicCount = agents.filter((a) => a.execution_mode.includes("Deterministic")).length;
  const llmCount = agents.filter((a) => a.execution_mode.includes("LLM") || a.execution_mode.includes("Hybrid")).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Overview Banner */}
      <div
        style={{
          background: "linear-gradient(135deg, #1e293b 0%, #0f172a 100%)",
          color: "#f8fafc",
          padding: "1.25rem 1.5rem",
          borderRadius: "8px",
          boxShadow: "0 4px 12px rgba(0, 0, 0, 0.1)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: "1.25rem", fontWeight: 600 }}>System Agent Glossary</h2>
            <p style={{ margin: "0.25rem 0 0 0", color: "#94a3b8", fontSize: "0.875rem" }}>
              Architectural map of all registered agents, operational roles, execution modes, and dependencies.
            </p>
          </div>
          <div style={{ display: "flex", gap: "1rem" }}>
            <div style={{ textAlign: "center", background: "rgba(255,255,255,0.06)", padding: "0.5rem 1rem", borderRadius: "6px" }}>
              <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "#38bdf8" }}>{totalCount}</div>
              <div style={{ fontSize: "0.75rem", color: "#94a3b8" }}>Total Agents</div>
            </div>
            <div style={{ textAlign: "center", background: "rgba(255,255,255,0.06)", padding: "0.5rem 1rem", borderRadius: "6px" }}>
              <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "#4ade80" }}>{deterministicCount}</div>
              <div style={{ fontSize: "0.75rem", color: "#94a3b8" }}>Deterministic</div>
            </div>
            <div style={{ textAlign: "center", background: "rgba(255,255,255,0.06)", padding: "0.5rem 1rem", borderRadius: "6px" }}>
              <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "#c084fc" }}>{llmCount}</div>
              <div style={{ fontSize: "0.75rem", color: "#94a3b8" }}>LLM / Hybrid</div>
            </div>
          </div>
        </div>
      </div>

      {/* Execution Pipeline Map */}
      <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "1.25rem" }}>
        <h3 style={{ margin: "0 0 0.75rem 0", fontSize: "1rem", color: "#334155" }}>
          Manager 5-Wave Execution Pipeline
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: "0.75rem" }}>
          {[
            { wave: "Wave 1: Context & Intent", agents: ["permit_classifier", "jurisdiction_resolver", "project_context"] },
            { wave: "Wave 2: Query & Retrieval", agents: ["query_deconstructor", "retriever"] },
            { wave: "Wave 3: Grounding & Conflicts", agents: ["conflict_detector", "mini_rag_conflicts", "budget_governor"] },
            { wave: "Wave 4: Routing & Synthesis", agents: ["prompt_router", "answer_generator", "media_curator"] },
            { wave: "Wave 5: Audit & Safety", agents: ["citation_verifier", "guardrail"] },
          ].map((w, idx) => (
            <div
              key={idx}
              style={{
                background: "#f8fafc",
                border: "1px solid #cbd5e1",
                borderRadius: "6px",
                padding: "0.75rem",
                fontSize: "0.825rem",
              }}
            >
              <div style={{ fontWeight: 600, color: "#1e293b", marginBottom: "0.5rem", borderBottom: "1px solid #e2e8f0", paddingBottom: "0.25rem" }}>
                {w.wave}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                {w.agents.map((ag) => (
                  <button
                    key={ag}
                    onClick={() => setExpandedAgent(ag)}
                    style={{
                      textAlign: "left",
                      background: expandedAgent === ag ? "#e0f2fe" : "#ffffff",
                      border: expandedAgent === ag ? "1px solid #0284c7" : "1px solid #e2e8f0",
                      borderRadius: "4px",
                      padding: "0.25rem 0.5rem",
                      fontSize: "0.775rem",
                      fontFamily: "monospace",
                      color: expandedAgent === ag ? "#0369a1" : "#475569",
                      cursor: "pointer",
                    }}
                  >
                    {ag}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Controls: Search & Category Filters */}
      <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap", alignItems: "center" }}>
        <input
          type="text"
          placeholder="Search agents by name, function, or metric..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            flex: "1 1 300px",
            padding: "0.5rem 0.875rem",
            borderRadius: "6px",
            border: "1px solid #cbd5e1",
            fontSize: "0.9rem",
          }}
        />
        <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap" }}>
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              style={{
                padding: "0.4rem 0.75rem",
                borderRadius: "20px",
                border: "none",
                fontSize: "0.8rem",
                fontWeight: selectedCategory === cat ? 600 : 400,
                background: selectedCategory === cat ? "#3b82f6" : "#e2e8f0",
                color: selectedCategory === cat ? "#ffffff" : "#475569",
                cursor: "pointer",
              }}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Agent List Cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {filteredAgents.length === 0 ? (
          <div style={{ padding: "2rem", textAlign: "center", color: "#64748b" }}>
            No agents found matching your query.
          </div>
        ) : (
          filteredAgents.map((agent) => {
            const isExpanded = expandedAgent === agent.name;
            const isLlm = agent.execution_mode.includes("LLM") || agent.execution_mode.includes("Hybrid");

            return (
              <div
                key={agent.name}
                style={{
                  background: "#ffffff",
                  border: isExpanded ? "1px solid #3b82f6" : "1px solid #e2e8f0",
                  borderRadius: "8px",
                  overflow: "hidden",
                  boxShadow: isExpanded ? "0 4px 12px rgba(59, 130, 246, 0.08)" : "0 1px 3px rgba(0, 0, 0, 0.05)",
                  transition: "all 0.15s ease",
                }}
              >
                {/* Header Row */}
                <div
                  onClick={() => setExpandedAgent(isExpanded ? null : agent.name)}
                  style={{
                    padding: "0.875rem 1.25rem",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    cursor: "pointer",
                    background: isExpanded ? "#f8fafc" : "#ffffff",
                    borderBottom: isExpanded ? "1px solid #e2e8f0" : "none",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                    <code style={{ fontSize: "0.95rem", fontWeight: 700, color: "#1e293b", background: "#f1f5f9", padding: "0.2rem 0.5rem", borderRadius: "4px" }}>
                      {agent.name}
                    </code>
                    <span style={{ fontSize: "0.95rem", fontWeight: 600, color: "#334155" }}>
                      {agent.display_name}
                    </span>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span
                      style={{
                        fontSize: "0.75rem",
                        padding: "0.2rem 0.5rem",
                        borderRadius: "12px",
                        fontWeight: 500,
                        background: isLlm ? "#f3e8ff" : "#dcfce7",
                        color: isLlm ? "#7e22ce" : "#15803d",
                      }}
                    >
                      {agent.execution_mode.split(" ")[0]}
                    </span>
                    <span style={{ fontSize: "0.75rem", padding: "0.2rem 0.5rem", borderRadius: "12px", background: "#f1f5f9", color: "#475569", fontWeight: 500 }}>
                      Ceiling: {agent.autonomy_ceiling}
                    </span>
                    <span style={{ fontSize: "1rem", color: "#94a3b8", marginLeft: "0.25rem" }}>
                      {isExpanded ? "▲" : "▼"}
                    </span>
                  </div>
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div style={{ padding: "1.25rem", fontSize: "0.875rem", color: "#334155", display: "flex", flexDirection: "column", gap: "1rem" }}>
                    <div>
                      <strong style={{ color: "#1e293b", display: "block", marginBottom: "0.25rem" }}>Role & Description:</strong>
                      <p style={{ margin: 0, color: "#475569", lineHeight: "1.45" }}>{agent.description}</p>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1rem" }}>
                      {/* Dependencies */}
                      <div style={{ background: "#f8fafc", padding: "0.75rem", borderRadius: "6px", border: "1px solid #f1f5f9" }}>
                        <strong style={{ color: "#1e293b", display: "block", marginBottom: "0.375rem" }}>Calling Hierarchy & Dependencies:</strong>
                        <div style={{ fontSize: "0.8rem" }}>
                          <div style={{ marginBottom: "0.375rem" }}>
                            <span style={{ color: "#64748b" }}>Called By: </span>
                            {agent.dependencies?.called_by?.map((c) => (
                              <code key={c} style={{ background: "#e2e8f0", padding: "0.1rem 0.3rem", borderRadius: "3px", marginRight: "0.25rem" }}>{c}</code>
                            )) || <em>None</em>}
                          </div>
                          <div>
                            <span style={{ color: "#64748b" }}>Delegates To: </span>
                            {agent.dependencies?.calls?.length > 0 ? (
                              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem", marginTop: "0.25rem" }}>
                                {agent.dependencies.calls.map((c) => (
                                  <code key={c} style={{ background: "#e0f2fe", color: "#0369a1", padding: "0.1rem 0.35rem", borderRadius: "3px" }}>{c}</code>
                                ))}
                              </div>
                            ) : (
                              <em>None (Terminal/Leaf Agent)</em>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Inputs & Outputs */}
                      <div style={{ background: "#f8fafc", padding: "0.75rem", borderRadius: "6px", border: "1px solid #f1f5f9" }}>
                        <strong style={{ color: "#1e293b", display: "block", marginBottom: "0.375rem" }}>Inputs & Outputs:</strong>
                        <div style={{ fontSize: "0.8rem" }}>
                          <div style={{ marginBottom: "0.375rem" }}>
                            <span style={{ color: "#64748b" }}>Inputs: </span>
                            {agent.inputs?.map((i) => (
                              <code key={i} style={{ background: "#e2e8f0", padding: "0.1rem 0.3rem", borderRadius: "3px", marginRight: "0.25rem" }}>{i}</code>
                            ))}
                          </div>
                          <div>
                            <span style={{ color: "#64748b" }}>Outputs: </span>
                            {agent.outputs?.map((o) => (
                              <code key={o} style={{ background: "#fef3c7", color: "#92400e", padding: "0.1rem 0.3rem", borderRadius: "3px", marginRight: "0.25rem" }}>{o}</code>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Metrics & Rules */}
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1rem" }}>
                      <div>
                        <strong style={{ color: "#1e293b", display: "block", marginBottom: "0.25rem" }}>Evaluator Metrics Tracked:</strong>
                        <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap" }}>
                          {agent.metrics && agent.metrics.length > 0 ? (
                            agent.metrics.map((m) => (
                              <span key={m} style={{ background: "#f1f5f9", border: "1px solid #cbd5e1", padding: "0.15rem 0.5rem", borderRadius: "4px", fontSize: "0.775rem", fontFamily: "monospace" }}>
                                {m}
                              </span>
                            ))
                          ) : (
                            <span style={{ color: "#94a3b8", fontSize: "0.8rem" }}>No direct metrics evaluated</span>
                          )}
                        </div>
                      </div>

                      <div>
                        <strong style={{ color: "#1e293b", display: "block", marginBottom: "0.25rem" }}>Governance & Operational Rules:</strong>
                        <ul style={{ margin: 0, paddingLeft: "1.2rem", color: "#475569", fontSize: "0.8rem" }}>
                          {agent.governance_rules?.map((rule, idx) => (
                            <li key={idx}>{rule}</li>
                          )) || <li>Follows default pipeline safety protocol</li>}
                        </ul>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
