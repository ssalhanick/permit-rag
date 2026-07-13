import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { deleteQueryFromHistory, fetchQueryHistory } from "../../api.js";
import { useProject } from "../ProjectContext.jsx";

/**
 * Project-scoped query history with search and reload into chat.
 */
export default function ProjectQueriesPage() {
  const { projectId } = useProject();
  const navigate = useNavigate();
  const [queries, setQueries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [expandedQueryId, setExpandedQueryId] = useState(null);
  const [copyFeedback, setCopyFeedback] = useState("");
  const [queryFilter, setQueryFilter] = useState("");

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError("");
      try {
        const res = await fetchQueryHistory(projectId);
        setQueries(res.data || []);
      } catch (err) {
        setError(err.message || "Failed to load query history.");
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId]);

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

  const handleReloadQuery = (queryText, municipality) => {
    const params = new URLSearchParams();
    params.set("q", queryText);
    if (municipality) {
      params.set("m", municipality);
    }
    params.set("p", projectId);
    navigate(`/?${params.toString()}`);
  };

  const handleDeleteQuery = async (queryId, e) => {
    e.stopPropagation();
    if (!window.confirm("Delete this query from history?")) {
      return;
    }
    try {
      await deleteQueryFromHistory(queryId);
      setSuccess("Query deleted.");
      setQueries((prev) => prev.filter((q) => q.id !== queryId));
    } catch (err) {
      setError(err.message || "Failed to delete query.");
    }
  };

  const handleCopyAnswer = (text, e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopyFeedback("Answer copied!");
    setTimeout(() => setCopyFeedback(""), 3000);
  };

  return (
    <div className="project-queries-page">
      {error && <div className="error-box">{error}</div>}
      {success && <div className="success-box">{success}</div>}

      <section className="panel">
        <p className="muted">Past questions and citations scoped to this project.</p>

        <div className="project-query-stats">
          <div className="project-query-stat">
            <strong>{filteredQueries.length}</strong>
            <span>Total queries</span>
          </div>
          <div className="project-query-stat">
            <strong>{avgLatency}ms</strong>
            <span>Avg latency</span>
          </div>
          <div className="project-query-stat">
            <strong>{munisQueried}</strong>
            <span>Jurisdictions</span>
          </div>
        </div>

        <input
          type="text"
          className="project-query-search"
          value={queryFilter}
          onChange={(e) => setQueryFilter(e.target.value)}
          placeholder="Search queries or answers…"
        />

        {loading ? (
          <p>Loading query history…</p>
        ) : filteredQueries.length === 0 ? (
          <p className="muted">No queries logged for this project yet.</p>
        ) : (
          <div className="project-query-list">
            {filteredQueries.map((q) => {
              const isExpanded = expandedQueryId === q.id;
              return (
                <article
                  key={q.id}
                  className={`project-query-card${isExpanded ? " project-query-card--expanded" : ""}`}
                  onClick={() => setExpandedQueryId(isExpanded ? null : q.id)}
                >
                  <div className="project-query-card-header">
                    <div>
                      <strong>{q.query_text}</strong>
                      <div className="project-query-meta">
                        <span>{new Date(q.created_at).toLocaleString()}</span>
                        {q.municipality && <span>{q.municipality}</span>}
                        {q.latency_ms && <span>{q.latency_ms}ms</span>}
                      </div>
                    </div>
                    <div className="project-query-actions" onClick={(e) => e.stopPropagation()}>
                      <button type="button" className="secondary-button" onClick={() => handleReloadQuery(q.query_text, q.municipality)}>
                        Open in chat
                      </button>
                      <button type="button" className="text-button delete-text" onClick={(e) => handleDeleteQuery(q.id, e)}>
                        Delete
                      </button>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="project-query-answer">
                      <div className="project-query-answer-header">
                        <strong>Answer</strong>
                        <button type="button" className="text-button" onClick={(e) => handleCopyAnswer(q.answer_text, e)}>
                          Copy
                        </button>
                      </div>
                      {copyFeedback && <p className="success-inline">{copyFeedback}</p>}
                      <pre>{q.answer_text}</pre>
                      {q.citations?.length > 0 && (
                        <div className="project-query-citations">
                          <strong>Citations</strong>
                          <ul>
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
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
