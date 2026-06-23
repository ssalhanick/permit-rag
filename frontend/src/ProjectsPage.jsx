import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import {
  fetchProjects,
  createProject,
  deleteProject,
  transferProjectOwnership,
  fetchProjectMembers,
  addProjectMember,
  removeProjectMember,
  fetchProjectDocuments,
  fetchQueryHistory,
  deleteQueryFromHistory,
} from "./api.js";

export default function ProjectsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [selectedProj, setSelectedProj] = useState(null);
  const [members, setMembers] = useState([]);
  const [docs, setDocs] = useState([]);
  
  // Detail tabs: "docs" | "queries" | "members"
  const [activeDetailTab, setActiveDetailTab] = useState("docs");
  const [queries, setQueries] = useState([]);
  const [loadingQueries, setLoadingQueries] = useState(false);
  const [expandedQueryId, setExpandedQueryId] = useState(null);
  const [copyFeedback, setCopyFeedback] = useState("");
  const [queryFilter, setQueryFilter] = useState("");
  
  // Form states
  const [newProjForm, setNewProjForm] = useState({ name: "", description: "", municipality: "" });
  const [newMemberForm, setNewMemberForm] = useState({ userId: "", role: "viewer" });
  const [transferOwnerId, setTransferOwnerId] = useState("");
  
  // Loading & error states
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadQueries = async () => {
    if (!selectedProj) return;
    setLoadingQueries(true);
    try {
      const res = await fetchQueryHistory(selectedProj.id);
      setQueries(res.data || []);
    } catch (err) {
      setError("Failed to fetch query history: " + err.message);
    } finally {
      setLoadingQueries(false);
    }
  };

  useEffect(() => {
    if (selectedProj && activeDetailTab === "queries") {
      loadQueries();
    }
  }, [selectedProj, activeDetailTab]);

  const handleReloadQuery = (queryText, municipality, projectId) => {
    const params = new URLSearchParams();
    params.set("q", queryText);
    if (municipality) {
      params.set("m", municipality);
    }
    if (projectId) {
      params.set("p", projectId);
    }
    navigate(`/?${params.toString()}`);
  };

  const handleDeleteQuery = async (queryId, e) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this query from your history?")) {
      return;
    }
    try {
      await deleteQueryFromHistory(queryId);
      setSuccess("Query deleted from history.");
      setQueries((prev) => prev.filter((q) => q.id !== queryId));
    } catch (err) {
      setError("Failed to delete query: " + err.message);
    }
  };

  const handleCopyAnswer = (text, e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopyFeedback("Answer copied to clipboard!");
    setTimeout(() => setCopyFeedback(""), 3000);
  };
  const filteredQueries = queries.filter((q) => {
    const term = queryFilter.toLowerCase();
    return (
      q.query_text.toLowerCase().includes(term) ||
      (q.answer_text && q.answer_text.toLowerCase().includes(term))
    );
  });

  const totalLatency = filteredQueries.reduce((acc, q) => acc + (q.latency_ms || 0), 0);
  const avgLatency = filteredQueries.length > 0 ? Math.round(totalLatency / filteredQueries.length) : 0;

  const uniqueMunis = Array.from(new Set(filteredQueries.map((q) => q.municipality).filter(Boolean)));
  const munisQueried = uniqueMunis.length > 0 ? uniqueMunis.join(", ") : "None";

  const loadProjects = async () => {
    if (!user) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetchProjects();
      setProjects(res.data || []);
      if (res.data && res.data.length > 0) {
        // Keep selection or pick first
        const currentSelected = selectedProj 
          ? res.data.find(p => p.id === selectedProj.id) 
          : res.data[0];
        if (currentSelected) {
          selectProject(currentSelected);
        } else {
          selectProject(res.data[0]);
        }
      } else {
        setSelectedProj(null);
        setMembers([]);
        setDocs([]);
      }
    } catch (err) {
      setError(err.message || "Failed to load projects.");
    } finally {
      setLoading(false);
    }
  };

  const selectProject = async (proj) => {
    setSelectedProj(proj);
    setError("");
    setSuccess("");
    setTransferOwnerId("");
    setNewMemberForm({ userId: "", role: "viewer" });
    setExpandedQueryId(null);
    setQueryFilter("");
    try {
      const [membersRes, docsRes] = await Promise.all([
        fetchProjectMembers(proj.id),
        fetchProjectDocuments(proj.id)
      ]);
      setMembers(membersRes.data || []);
      setDocs(docsRes.data || []);
    } catch (err) {
      setError(`Failed to fetch project details: ${err.message}`);
    }
  };

  useEffect(() => {
    loadProjects();
  }, [user]);

  // Find user's role in the active project
  const myMemberRecord = members.find(m => m.user_id === user.id);
  const myRole = selectedProj?.owner_user_id === user.id ? "owner" : (myMemberRecord?.role || "viewer");
  const isOwner = myRole === "owner";
  const canManage = isOwner;

  const handleCreateProject = async (e) => {
    e.preventDefault();
    setActionLoading(true);
    setError("");
    setSuccess("");
    try {
      const res = await createProject({
        name: newProjForm.name,
        description: newProjForm.description || null,
        municipality: newProjForm.municipality || null
      });
      setNewProjForm({ name: "", description: "", municipality: "" });
      setSuccess(`Project "${res.data.name}" created successfully!`);
      // Reload and select new
      const currentList = await fetchProjects();
      setProjects(currentList.data || []);
      const createdProj = currentList.data.find(p => p.id === res.data.id);
      if (createdProj) {
        selectProject(createdProj);
      }
    } catch (err) {
      setError(err.message || "Failed to create project.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteProject = async () => {
    if (!selectedProj) return;
    if (!window.confirm(`Are you sure you want to delete project "${selectedProj.name}"? This cannot be undone.`)) {
      return;
    }
    setActionLoading(true);
    setError("");
    setSuccess("");
    try {
      await deleteProject(selectedProj.id);
      setSuccess(`Project deleted.`);
      setSelectedProj(null);
      await loadProjects();
    } catch (err) {
      setError(err.message || "Failed to delete project.");
      setActionLoading(false);
    }
  };

  const handleAddMember = async (e) => {
    e.preventDefault();
    if (!selectedProj) return;
    setActionLoading(true);
    setError("");
    setSuccess("");
    try {
      await addProjectMember(selectedProj.id, newMemberForm.userId, newMemberForm.role);
      setSuccess("Member added to project!");
      setNewMemberForm({ userId: "", role: "viewer" });
      const membersRes = await fetchProjectMembers(selectedProj.id);
      setMembers(membersRes.data || []);
    } catch (err) {
      setError(err.message || "Failed to add member.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleRemoveMember = async (userId, username) => {
    if (!selectedProj) return;
    if (!window.confirm(`Remove collaborator "${username}" from project?`)) {
      return;
    }
    setActionLoading(true);
    setError("");
    setSuccess("");
    try {
      await removeProjectMember(selectedProj.id, userId);
      setSuccess("Collaborator removed.");
      const membersRes = await fetchProjectMembers(selectedProj.id);
      setMembers(membersRes.data || []);
    } catch (err) {
      setError(err.message || "Failed to remove member.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleTransferOwnership = async (e) => {
    e.preventDefault();
    if (!selectedProj) return;
    if (!window.confirm("Are you sure you want to transfer ownership? You will lose owner controls!")) {
      return;
    }
    setActionLoading(true);
    setError("");
    setSuccess("");
    try {
      await transferProjectOwnership(selectedProj.id, transferOwnerId);
      setSuccess("Project ownership transferred successfully!");
      setTransferOwnerId("");
      await loadProjects();
    } catch (err) {
      setError(err.message || "Failed to transfer ownership.");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <main className="page project-page">
      <div className="project-grid">
        {/* Sidebar: Projects List */}
        <section className="panel project-list-panel">
          <h3>My Projects</h3>
          {loading && <p>Loading projects...</p>}
          {!loading && projects.length === 0 && <p className="muted">No projects found.</p>}
          <ul className="project-list-items">
            {projects.map((p) => {
              const active = selectedProj && selectedProj.id === p.id;
              return (
                <li key={p.id}>
                  <button
                    type="button"
                    className={`project-list-item-btn ${active ? "active" : ""}`}
                    onClick={() => selectProject(p)}
                  >
                    <strong>{p.name}</strong>
                    {p.municipality && <span className="muni-badge">{p.municipality}</span>}
                  </button>
                </li>
              );
            })}
          </ul>

          <hr style={{ margin: "20px 0", borderColor: "#f1f5f9" }} />

          {/* Create Project Form */}
          <h4>New Project</h4>
          <form onSubmit={handleCreateProject} className="form mini-form">
            <div>
              <label htmlFor="projName">Project Name</label>
              <input
                id="projName"
                value={newProjForm.name}
                onChange={(e) => setNewProjForm({ ...newProjForm, name: e.target.value })}
                placeholder="e.g. Backyard Pool"
                required
              />
            </div>
            <div>
              <label htmlFor="projDesc">Description</label>
              <textarea
                id="projDesc"
                rows={2}
                value={newProjForm.description}
                onChange={(e) => setNewProjForm({ ...newProjForm, description: e.target.value })}
                placeholder="Brief summary..."
              />
            </div>
            <div>
              <label htmlFor="projMuni">Default Municipality</label>
              <input
                id="projMuni"
                value={newProjForm.municipality}
                onChange={(e) => setNewProjForm({ ...newProjForm, municipality: e.target.value })}
                placeholder="e.g. dallas"
              />
            </div>
            <button type="submit" disabled={actionLoading} className="secondary-button" style={{ width: "100%" }}>
              Create Project
            </button>
          </form>
        </section>

        {/* Main Panel: Selected Project Detail */}
        <section className="panel project-detail-panel">
          {selectedProj ? (
            <>
              <div className="project-detail-header">
                <h2>{selectedProj.name}</h2>
                <span className="role-badge">Role: {myRole.toUpperCase()}</span>
              </div>
              <p className="project-description">{selectedProj.description || "No description provided."}</p>

              <div className="project-meta-grid">
                <div>
                  <strong>Default Jurisdiction: </strong>
                  <span>{selectedProj.municipality || "None (Global search)"}</span>
                </div>
                <div>
                  <strong>Project ID: </strong>
                  <code style={{ fontSize: "0.8rem", background: "#f1f5f9", padding: "2px 4px", borderRadius: "4px" }}>
                    {selectedProj.id}
                  </code>
                </div>
              </div>

              {error && <div className="error-box" style={{ marginTop: "14px" }}>{error}</div>}
              {success && <div className="success-box" style={{ marginTop: "14px" }}>{success}</div>}

              {/* Tabs selector */}
              <div style={{ display: "flex", borderBottom: "2px solid #e2e8f0", marginBottom: "20px" }}>
                <button
                  type="button"
                  onClick={() => setActiveDetailTab("docs")}
                  style={{
                    background: "none",
                    border: "none",
                    borderBottom: activeDetailTab === "docs" ? "3px solid #2563eb" : "3px solid transparent",
                    color: activeDetailTab === "docs" ? "#2563eb" : "#64748b",
                    fontWeight: "600",
                    padding: "10px 20px",
                    cursor: "pointer",
                    fontSize: "0.95rem"
                  }}
                >
                  Shared Documents ({docs.length})
                </button>
                <button
                  type="button"
                  onClick={() => setActiveDetailTab("queries")}
                  style={{
                    background: "none",
                    border: "none",
                    borderBottom: activeDetailTab === "queries" ? "3px solid #2563eb" : "3px solid transparent",
                    color: activeDetailTab === "queries" ? "#2563eb" : "#64748b",
                    fontWeight: "600",
                    padding: "10px 20px",
                    cursor: "pointer",
                    fontSize: "0.95rem"
                  }}
                >
                  Query History
                </button>
                <button
                  type="button"
                  onClick={() => setActiveDetailTab("members")}
                  style={{
                    background: "none",
                    border: "none",
                    borderBottom: activeDetailTab === "members" ? "3px solid #2563eb" : "3px solid transparent",
                    color: activeDetailTab === "members" ? "#2563eb" : "#64748b",
                    fontWeight: "600",
                    padding: "10px 20px",
                    cursor: "pointer",
                    fontSize: "0.95rem"
                  }}
                >
                  Collaborators ({members.length + 1})
                </button>
              </div>

              {/* Tab Panel: Docs */}
              {activeDetailTab === "docs" && (
                <div className="project-section" style={{ marginTop: 0, paddingTop: 0, border: "none" }}>
                  <h3>Shared Documents ({docs.length})</h3>
                  <p className="muted">These regulatory documents are bound to this project workspace.</p>
                  {docs.length === 0 ? (
                    <p className="muted" style={{ fontStyle: "italic" }}>No documents shared yet. Go to the "Documents" browser tab to share.</p>
                  ) : (
                    <table className="doc-table">
                      <thead>
                        <tr>
                          <th>Doc ID</th>
                          <th>Municipality</th>
                          <th>Status</th>
                          <th>Type</th>
                        </tr>
                      </thead>
                      <tbody>
                        {docs.map((d) => (
                          <tr key={d.id}>
                            <td>
                              <strong>{d.doc_id}</strong>
                            </td>
                            <td>{d.municipality}</td>
                            <td>{d.document_status}</td>
                            <td>{d.doc_type}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}

              {/* Tab Panel: Queries (History) */}
              {activeDetailTab === "queries" && (
                <div className="project-section" style={{ marginTop: 0, paddingTop: 0, border: "none" }}>
                  <h3>Project Query History</h3>
                  <p className="muted">Review past questions and citations scoped to this project.</p>

                  {/* Stats Cards */}
                  <div style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                    gap: "12px",
                    marginBottom: "20px"
                  }}>
                    <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "12px", textAlign: "center" }}>
                      <div style={{ fontSize: "1.5rem", fontWeight: "700", color: "#2563eb" }}>{filteredQueries.length}</div>
                      <div style={{ fontSize: "0.75rem", color: "#64748b", fontWeight: "600", textTransform: "uppercase", marginTop: "4px" }}>Total Queries</div>
                    </div>
                    <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "12px", textAlign: "center" }}>
                      <div style={{ fontSize: "1.5rem", fontWeight: "700", color: "#10b981" }}>{avgLatency}ms</div>
                      <div style={{ fontSize: "0.75rem", color: "#64748b", fontWeight: "600", textTransform: "uppercase", marginTop: "4px" }}>Avg Latency</div>
                    </div>
                    <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "12px", textAlign: "center" }}>
                      <div style={{ fontSize: "1rem", fontWeight: "700", color: "#6366f1", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", padding: "4px 0" }}>{munisQueried}</div>
                      <div style={{ fontSize: "0.75rem", color: "#64748b", fontWeight: "600", textTransform: "uppercase", marginTop: "4px" }}>Jurisdictions</div>
                    </div>
                  </div>

                  {/* Search Bar */}
                  <div style={{ marginBottom: "16px" }}>
                    <input
                      type="text"
                      value={queryFilter}
                      onChange={(e) => setQueryFilter(e.target.value)}
                      placeholder="🔍 Search queries or answers..."
                      style={{
                        padding: "8px 12px",
                        fontSize: "0.9rem",
                        borderRadius: "6px",
                        border: "1px solid #cbd5e1"
                      }}
                    />
                  </div>

                  {loadingQueries ? (
                    <p>Loading project query history...</p>
                  ) : filteredQueries.length === 0 ? (
                    <p className="muted" style={{ fontStyle: "italic" }}>No queries logged for this project yet.</p>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                      {filteredQueries.map((q) => {
                        const isExpanded = expandedQueryId === q.id;
                        const dateStr = new Date(q.created_at).toLocaleString();
                        return (
                          <div
                            key={q.id}
                            style={{
                              border: "1px solid #e2e8f0",
                              borderRadius: "8px",
                              padding: "12px 16px",
                              cursor: "pointer",
                              background: isExpanded ? "#f8fafc" : "#fff",
                              transition: "all 0.2s"
                            }}
                            onClick={() => setExpandedQueryId(isExpanded ? null : q.id)}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                              <div>
                                <strong style={{ fontSize: "1.05rem", color: "#1e293b" }}>{q.query_text}</strong>
                                <div style={{ fontSize: "0.8rem", color: "#64748b", marginTop: "4px", display: "flex", gap: "12px" }}>
                                  <span>📅 {dateStr}</span>
                                  {q.municipality && <span>📍 {q.municipality}</span>}
                                  {q.latency_ms && <span>⏱️ {q.latency_ms}ms</span>}
                                </div>
                              </div>
                              <div style={{ display: "flex", gap: "8px" }} onClick={(e) => e.stopPropagation()}>
                                <button
                                  type="button"
                                  onClick={() => handleReloadQuery(q.query_text, q.municipality, q.project_id)}
                                  style={{ padding: "4px 8px", fontSize: "0.8rem", background: "#3b82f6" }}
                                >
                                  Open in Chat
                                </button>
                                <button
                                  type="button"
                                  onClick={(e) => handleDeleteQuery(q.id, e)}
                                  style={{ padding: "4px 8px", fontSize: "0.8rem", background: "#fee2e2", color: "#991b1b" }}
                                >
                                  Delete
                                </button>
                              </div>
                            </div>

                            {isExpanded && (
                              <div style={{ marginTop: "12px", borderTop: "1px solid #e2e8f0", paddingTop: "12px" }}>
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                                  <strong style={{ fontSize: "0.9rem", color: "#475569" }}>Answer Output:</strong>
                                  <button
                                    type="button"
                                    onClick={(e) => handleCopyAnswer(q.answer_text, e)}
                                    style={{ padding: "2px 8px", fontSize: "0.75rem", background: "#475569" }}
                                  >
                                    Copy Answer
                                  </button>
                                </div>
                                {copyFeedback && <p style={{ color: "#059669", fontSize: "0.8rem", margin: "4px 0" }}>{copyFeedback}</p>}
                                <pre style={{
                                  background: "#0f172a",
                                  color: "#f1f5f9",
                                  padding: "12px",
                                  borderRadius: "6px",
                                  fontSize: "0.85rem",
                                  whiteSpace: "pre-wrap",
                                  overflowX: "auto",
                                  margin: 0
                                }}>
                                  {q.answer_text}
                                </pre>

                                {q.citations && q.citations.length > 0 && (
                                  <div style={{ marginTop: "12px" }}>
                                    <strong style={{ fontSize: "0.85rem", color: "#475569", display: "block", marginBottom: "6px" }}>Citations:</strong>
                                    <ul style={{ margin: 0, paddingLeft: "18px", fontSize: "0.8rem", color: "#475569" }}>
                                      {q.citations.map((cit, idx) => (
                                        <li key={idx}>
                                          <strong>{cit.doc_id}</strong> (chunk {cit.chunk_index})
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* Tab Panel: Members */}
              {activeDetailTab === "members" && (
                <div className="project-section" style={{ marginTop: 0, paddingTop: 0, border: "none" }}>
                  <h3>Collaborators ({members.length + 1})</h3>
                  <table className="doc-table">
                    <thead>
                      <tr>
                        <th>Collaborator</th>
                        <th>Email</th>
                        <th>Role</th>
                        {canManage && <th>Action</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {/* Owner row */}
                      <tr>
                        <td>
                          <strong>Creator (Owner)</strong>
                        </td>
                        <td>-</td>
                        <td><span className="badge badge-owner">Owner</span></td>
                        {canManage && <td>-</td>}
                      </tr>
                      {/* Other members */}
                      {members.map((m) => (
                        <tr key={m.user_id}>
                          <td>{m.username} {m.user_id === user.id && "(You)"}</td>
                          <td>{m.email}</td>
                          <td>
                            <span className={`badge badge-${m.role}`}>
                              {m.role}
                            </span>
                          </td>
                          {canManage && (
                            <td>
                              <button
                                type="button"
                                className="text-button delete-text"
                                onClick={() => handleRemoveMember(m.user_id, m.username)}
                                disabled={actionLoading}
                              >
                                Remove
                              </button>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {/* Add Member Form (Owner only) */}
                  {canManage && (
                    <form onSubmit={handleAddMember} className="form inline-form" style={{ marginTop: "12px", display: "flex", gap: "8px", alignItems: "flex-end" }}>
                      <div style={{ flex: 1 }}>
                        <label htmlFor="newMemberId">Add Member (User UUID)</label>
                        <input
                          id="newMemberId"
                          value={newMemberForm.userId}
                          onChange={(e) => setNewMemberForm({ ...newMemberForm, userId: e.target.value })}
                          placeholder="Paste user UUID here"
                          required
                        />
                      </div>
                      <div style={{ width: "120px" }}>
                        <label htmlFor="newMemberRole">Role</label>
                        <select
                          id="newMemberRole"
                          value={newMemberForm.role}
                          onChange={(e) => setNewMemberForm({ ...newMemberForm, role: e.target.value })}
                        >
                          <option value="viewer">viewer</option>
                          <option value="editor">editor</option>
                        </select>
                      </div>
                      <button type="submit" disabled={actionLoading} className="secondary-button" style={{ height: "36px" }}>
                        Add
                      </button>
                    </form>
                  )}
                </div>
              )}

              {/* Advanced Operations (Owner only) */}
              {isOwner && (
                <div className="project-section danger-zone" style={{ marginTop: "32px", borderTop: "1px solid #fee2e2", paddingTop: "20px" }}>
                  <h4 style={{ color: "#991b1b", margin: "0 0 10px" }}>Danger Zone</h4>
                  
                  {/* Transfer Ownership */}
                  <form onSubmit={handleTransferOwnership} className="form inline-form" style={{ display: "flex", gap: "8px", alignItems: "flex-end", marginBottom: "14px" }}>
                    <div style={{ flex: 1 }}>
                      <label htmlFor="transferId" style={{ color: "#991b1b" }}>Transfer Ownership (New Owner UUID)</label>
                      <input
                        id="transferId"
                        value={transferOwnerId}
                        onChange={(e) => setTransferOwnerId(e.target.value)}
                        placeholder="Paste new owner's user UUID"
                        required
                      />
                    </div>
                    <button type="submit" disabled={actionLoading} className="primary-button" style={{ background: "#dc2626" }}>
                      Transfer
                    </button>
                  </form>

                  {/* Delete Project */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <strong style={{ color: "#991b1b" }}>Delete Project Workspace</strong>
                      <p className="muted" style={{ margin: "4px 0 0", fontSize: "0.85rem" }}>
                        Permanently delete project and revoke collaborator access. This cannot be undone.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={handleDeleteProject}
                      disabled={actionLoading}
                      className="primary-button"
                      style={{ background: "#dc2626" }}
                    >
                      Delete Project
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div style={{ display: "flex", height: "100%", alignItems: "center", justifyContent: "center", minHeight: "300px" }}>
              <p className="muted" style={{ fontSize: "1.1rem" }}>Select a project or create a new one to get started.</p>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
