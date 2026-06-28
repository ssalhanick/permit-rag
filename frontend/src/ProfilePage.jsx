import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import {
  fetchQueryHistory,
  deleteQueryFromHistory,
  purgeDocumentAdmin,
  fetchDocuments,
  fetchProjects,
  shareDocumentToProject,
} from "./api.js";
import { formatAdminError, getStoredAdminToken } from "./documentAdminUtils.js";

export default function ProfilePage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState("history");
  const [queries, setQueries] = useState([]);
  const [docs, setDocs] = useState([]);
  const [userProjects, setUserProjects] = useState([]);
  
  const [loadingQueries, setLoadingQueries] = useState(false);
  const [loadingDocs, setLoadingDocs] = useState(false);
  
  const [expandedQueryId, setExpandedQueryId] = useState(null);
  const [copyFeedback, setCopyFeedback] = useState("");
  const [targetProjectForDoc, setTargetProjectForDoc] = useState({}); // { docUuid: projectId }
  const [docShareFeedback, setDocShareFeedback] = useState({}); // { docUuid: message }

  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");


  // Load queries
  const loadQueries = async () => {
    setLoadingQueries(true);
    try {
      const res = await fetchQueryHistory();
      setQueries(res.data || []);
    } catch (err) {
      setActionError("Failed to fetch query history: " + err.message);
    } finally {
      setLoadingQueries(false);
    }
  };

  // Load documents
  const loadDocuments = async () => {
    setLoadingDocs(true);
    try {
      const res = await fetchDocuments();
      setDocs(res.data || []);
    } catch (err) {
      setActionError("Failed to fetch documents: " + err.message);
    } finally {
      setLoadingDocs(false);
    }
  };

  // Load projects to copy documents to
  const loadProjects = async () => {
    try {
      const res = await fetchProjects();
      setUserProjects(res.data || []);
    } catch (err) {
      console.warn("Failed to load user projects", err);
    }
  };

  // Initial fetch based on active tab
  useEffect(() => {
    if (!user) return;
    setActionError("");
    setActionSuccess("");

    if (activeTab === "history") {
      loadQueries();
    } else if (activeTab === "documents") {
      loadDocuments();
      loadProjects();
    }
  }, [activeTab, user]);

  // Delete query
  const handleDeleteQuery = async (queryId, e) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this query from your history?")) {
      return;
    }
    try {
      await deleteQueryFromHistory(queryId);
      setActionSuccess("Query deleted from history.");
      setQueries((prev) => prev.filter((q) => q.id !== queryId));
    } catch (err) {
      setActionError("Failed to delete query: " + err.message);
    }
  };

  // Reload query in main search
  const handleReloadQuery = (queryText, municipality) => {
    const params = new URLSearchParams();
    params.set("q", queryText);
    if (municipality) {
      params.set("m", municipality);
    }
    navigate(`/?${params.toString()}`);
  };

  // Copy answer text to clipboard
  const handleCopyAnswer = (text, e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopyFeedback("Answer copied to clipboard!");
    setTimeout(() => setCopyFeedback(""), 3000);
  };

  // Copy document to project
  const handleShareDocToProject = async (docUuid, docId) => {
    const projectId = targetProjectForDoc[docUuid];
    if (!projectId) {
      setDocShareFeedback((prev) => ({ ...prev, [docUuid]: "Please select a project." }));
      return;
    }
    try {
      await shareDocumentToProject(projectId, docUuid);
      const proj = userProjects.find((p) => p.project_id === projectId);
      setDocShareFeedback((prev) => ({
        ...prev,
        [docUuid]: `Copied successfully to ${proj ? proj.name : "project"}.`,
      }));
      setTimeout(() => {
        setDocShareFeedback((prev) => {
          const updated = { ...prev };
          delete updated[docUuid];
          return updated;
        });
      }, 4000);
    } catch (err) {
      setDocShareFeedback((prev) => ({ ...prev, [docUuid]: "Failed: " + err.message }));
    }
  };

  // Delete/purge document
  const handlePurgeDocument = async (docId) => {
    if (!window.confirm(`Are you sure you want to delete and purge all chunks for document ${docId}?`)) {
      return;
    }
    const adminToken = getStoredAdminToken();
    if (!adminToken.trim()) {
      setActionError("Set X-Admin-Token on Upload or Documents page before purging.");
      return;
    }
    try {
      await purgeDocumentAdmin(docId, adminToken, "admin", user?.username || user?.user_id || "");
      setActionSuccess(`Document ${docId} purged successfully.`);
      loadDocuments();
    } catch (err) {
      setActionError("Failed to purge document: " + formatAdminError(err));
    }
  };


  // Filter documents to show those uploaded by user (admins can see all)
  const filteredDocs = docs.filter((d) => user.role === "admin" || d.uploaded_by === user.user_id);

  return (
    <main className="page">
      <div className="panel" style={{ display: "flex", alignItems: "center", gap: "20px", background: "linear-gradient(135deg, #1e293b, #0f172a)", color: "#f8fafc", padding: "24px" }}>
        <div style={{
          width: "60px",
          height: "60px",
          borderRadius: "50%",
          background: "linear-gradient(135deg, #3b82f6, #1d4ed8)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: "1.75rem",
          fontWeight: "700",
          textTransform: "uppercase",
          color: "#fff",
          boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)"
        }}>
          {user.username.slice(0, 2)}
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: "1.5rem", fontWeight: "600" }}>{user.username}</h1>
          <p className="muted" style={{ margin: "4px 0 0 0", color: "#94a3b8" }}>
            ID: <span style={{ fontFamily: "monospace", fontSize: "0.85rem" }}>{user.user_id}</span>
          </p>
          <span className="badge" style={{
            display: "inline-block",
            marginTop: "8px",
            padding: "2px 8px",
            borderRadius: "9999px",
            fontSize: "0.75rem",
            fontWeight: "600",
            textTransform: "uppercase",
            background: user.role === "admin" ? "#b91c1c" : "#2563eb",
            color: "#fff"
          }}>
            {user.role === "admin" ? "Admin" : "Member"}
          </span>
        </div>
      </div>

      {actionError && (
        <div className="panel error-msg" style={{ borderLeft: "4px solid #ef4444", background: "#fef2f2", color: "#b91c1c" }}>
          <strong>Error:</strong> {actionError}
        </div>
      )}

      {actionSuccess && (
        <div className="panel success-msg" style={{ borderLeft: "4px solid #10b981", background: "#ecfdf5", color: "#047857" }}>
          {actionSuccess}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: "2px solid #e2e8f0", marginBottom: "20px" }}>
        <button
          className="tab-button"
          onClick={() => setActiveTab("history")}
          style={{
            background: "none",
            border: "none",
            borderBottom: activeTab === "history" ? "3px solid #2563eb" : "3px solid transparent",
            color: activeTab === "history" ? "#2563eb" : "#64748b",
            fontWeight: "600",
            padding: "10px 20px",
            cursor: "pointer",
            fontSize: "0.95rem"
          }}
        >
          Query History
        </button>
        <button
          className="tab-button"
          onClick={() => setActiveTab("documents")}
          style={{
            background: "none",
            border: "none",
            borderBottom: activeTab === "documents" ? "3px solid #2563eb" : "3px solid transparent",
            color: activeTab === "documents" ? "#2563eb" : "#64748b",
            fontWeight: "600",
            padding: "10px 20px",
            cursor: "pointer",
            fontSize: "0.95rem"
          }}
        >
          My Documents
        </button>
      </div>

      {/* Tab Panels */}
      {activeTab === "history" && (
        <section className="panel">
          <h2>Your Query History</h2>
          <p className="muted">Review and reload your past RAG searches and LLM answers.</p>

          {loadingQueries ? (
            <p>Loading history...</p>
          ) : queries.length === 0 ? (
            <p className="muted">No search queries logged yet.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {queries.map((q) => {
                const isExpanded = expandedQueryId === q.id;
                const dateStr = new Date(q.created_at).toLocaleString();
                return (
                  <div
                    key={q.id}
                    className="history-card"
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
                        <strong style={{ fontSize: "1.05rem" }}>{q.query_text}</strong>
                        <div className="muted" style={{ fontSize: "0.8rem", marginTop: "4px" }}>
                          <span>{dateStr}</span>
                          {q.municipality && (
                            <span style={{ marginLeft: "12px" }}>📍 {q.municipality}</span>
                          )}
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: "8px" }} onClick={(e) => e.stopPropagation()}>
                        <button
                          className="secondary-button"
                          onClick={() => handleReloadQuery(q.query_text, q.municipality)}
                          style={{ padding: "4px 8px", fontSize: "0.8rem" }}
                        >
                          Reload
                        </button>
                        <button
                          className="secondary-button"
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
                          <strong>Answer Output:</strong>
                          <button
                            className="secondary-button"
                            onClick={(e) => handleCopyAnswer(q.answer_text, e)}
                            style={{ padding: "2px 8px", fontSize: "0.75rem" }}
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
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {activeTab === "documents" && (
        <section className="panel">
          <h2>My Uploaded Documents</h2>
          <p className="muted">Manage and share your custom RAG ordinance/permit compliance documents.</p>

          {loadingDocs ? (
            <p>Loading documents...</p>
          ) : filteredDocs.length === 0 ? (
            <p className="muted">No uploaded documents found.</p>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid #e2e8f0", textAlign: "left" }}>
                    <th style={{ padding: "8px" }}>Doc ID</th>
                    <th style={{ padding: "8px" }}>Jurisdiction</th>
                    <th style={{ padding: "8px" }}>Type</th>
                    <th style={{ padding: "8px" }}>Uploaded By</th>
                    <th style={{ padding: "8px" }}>Status</th>
                    <th style={{ padding: "8px" }}>Copy to Project</th>
                    <th style={{ padding: "8px" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDocs.map((d) => (
                    <tr key={d.id} style={{ borderBottom: "1px solid #e2e8f0" }}>
                      <td style={{ padding: "8px", fontWeight: "600" }}>{d.doc_id}</td>
                      <td style={{ padding: "8px" }}>{d.municipality}</td>
                      <td style={{ padding: "8px" }}>{d.doc_type}</td>
                      <td style={{ padding: "8px", fontSize: "0.8rem", color: "#64748b" }}>
                        {d.uploaded_by ? (d.uploaded_by === user.user_id ? "You" : d.uploaded_by.slice(0, 8)) : "System"}
                      </td>
                      <td style={{ padding: "8px" }}>
                        <span style={{
                          padding: "2px 6px",
                          borderRadius: "4px",
                          fontSize: "0.75rem",
                          background: d.document_status === "active" ? "#d1fae5" : "#fee2e2",
                          color: d.document_status === "active" ? "#065f46" : "#991b1b"
                        }}>
                          {d.document_status}
                        </span>
                      </td>
                      <td style={{ padding: "8px" }}>
                        <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                          <select
                            value={targetProjectForDoc[d.id] || ""}
                            onChange={(e) => setTargetProjectForDoc((prev) => ({ ...prev, [d.id]: e.target.value }))}
                            style={{ padding: "4px", fontSize: "0.8rem" }}
                          >
                            <option value="">-- Choose Project --</option>
                            {userProjects.map((p) => (
                              <option key={p.project_id} value={p.project_id}>
                                {p.name}
                              </option>
                            ))}
                          </select>
                          <button
                            className="secondary-button"
                            onClick={() => handleShareDocToProject(d.id, d.doc_id)}
                            style={{ padding: "4px 8px", fontSize: "0.8rem" }}
                          >
                            Copy
                          </button>
                        </div>
                        {docShareFeedback[d.id] && (
                          <div style={{ fontSize: "0.75rem", color: "#2563eb", marginTop: "4px" }}>
                            {docShareFeedback[d.id]}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: "8px" }}>
                        <button
                          className="secondary-button"
                          onClick={() => handlePurgeDocument(d.doc_id)}
                          style={{ padding: "4px 8px", fontSize: "0.8rem", background: "#fee2e2", color: "#991b1b" }}
                        >
                          Purge
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
