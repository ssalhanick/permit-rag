import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";
import { deleteQueryFromHistory, fetchQueryHistory } from "../../api.js";

/**
 * User query history list with expand, reload, copy, and delete actions.
 */
export default function ProfileHistoryPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [queries, setQueries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expandedQueryId, setExpandedQueryId] = useState(null);
  const [copyFeedback, setCopyFeedback] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");

  const loadQueries = async () => {
    setLoading(true);
    setActionError("");
    try {
      const res = await fetchQueryHistory();
      setQueries(res.data || []);
    } catch (err) {
      setActionError(`Failed to fetch query history: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user) {
      loadQueries();
    }
  }, [user]);

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
      setActionError(`Failed to delete query: ${err.message}`);
    }
  };

  const handleReloadQuery = (queryText, municipality) => {
    const params = new URLSearchParams();
    params.set("q", queryText);
    if (municipality) {
      params.set("m", municipality);
    }
    navigate(`/?${params.toString()}`);
  };

  const handleCopyAnswer = (text, e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopyFeedback("Answer copied to clipboard!");
    setTimeout(() => setCopyFeedback(""), 3000);
  };

  return (
    <section className="panel">
      <p className="muted">Review and reload your past RAG searches and LLM answers.</p>

      {actionError && (
        <div className="profile-flash profile-flash--error">{actionError}</div>
      )}
      {actionSuccess && (
        <div className="profile-flash profile-flash--success">{actionSuccess}</div>
      )}

      {loading ? (
        <p>Loading history...</p>
      ) : queries.length === 0 ? (
        <p className="muted">No search queries logged yet.</p>
      ) : (
        <div className="profile-history-list">
          {queries.map((q) => {
            const isExpanded = expandedQueryId === q.id;
            const dateStr = new Date(q.created_at).toLocaleString();
            return (
              <div
                key={q.id}
                className={`profile-history-card${isExpanded ? " profile-history-card--expanded" : ""}`}
                onClick={() => setExpandedQueryId(isExpanded ? null : q.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setExpandedQueryId(isExpanded ? null : q.id);
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <div className="profile-history-card-header">
                  <div>
                    <strong>{q.query_text}</strong>
                    <div className="muted profile-history-meta">
                      <span>{dateStr}</span>
                      {q.municipality && <span>Municipality: {q.municipality}</span>}
                    </div>
                  </div>
                  <div className="profile-history-actions" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => handleReloadQuery(q.query_text, q.municipality)}
                    >
                      Reload
                    </button>
                    <button
                      type="button"
                      className="secondary-button profile-btn-danger"
                      onClick={(e) => handleDeleteQuery(q.id, e)}
                    >
                      Delete
                    </button>
                  </div>
                </div>

                {isExpanded && (
                  <div className="profile-history-answer">
                    <div className="profile-history-answer-toolbar">
                      <strong>Answer output</strong>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={(e) => handleCopyAnswer(q.answer_text, e)}
                      >
                        Copy answer
                      </button>
                    </div>
                    {copyFeedback && <p className="profile-copy-feedback">{copyFeedback}</p>}
                    <pre className="profile-answer-pre">{q.answer_text}</pre>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
