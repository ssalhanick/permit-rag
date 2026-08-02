import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { deleteQueryFromHistory, fetchQueryHistory } from "../../api.js";
import { useProject } from "../ProjectContext.jsx";
import { MessageSquare, Search, Copy, Check, Trash2, ExternalLink, Zap, MapPin, Clock, AlertTriangle, CheckCircle } from "lucide-react";

/**
 * Project-scoped query history with search and reload into chat.
 */
export default function ProjectQueriesPage() {
  const { project, projectId } = useProject();
  const navigate = useNavigate();
  const [queries, setQueries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [expandedQueryId, setExpandedQueryId] = useState(null);
  const [copiedId, setCopiedId] = useState(null);
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
    navigate(`/query?${params.toString()}`);
  };

  const handleDeleteQuery = async (queryId, e) => {
    e.stopPropagation();
    if (!window.confirm("Delete this query from history?")) {
      return;
    }
    try {
      await deleteQueryFromHistory(queryId);
      setSuccess("Query deleted successfully.");
      setQueries((prev) => prev.filter((q) => q.id !== queryId));
    } catch (err) {
      setError(err.message || "Failed to delete query.");
    }
  };

  const handleCopyAnswer = (text, id, e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2500);
  };

  return (
    <div className="max-w-4xl mx-auto p-4 sm:p-6 space-y-6">
      {/* ── Breadcrumb Navigation ── */}
      <nav className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3 flex items-center gap-1.5">
        <Link to="/projects" className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
          Projects
        </Link>
        <span>/</span>
        <Link to={`/projects/${projectId}`} className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">
          {project?.name || "Dashboard"}
        </Link>
        <span>/</span>
        <span className="text-slate-900 dark:text-slate-100 font-bold">Query History</span>
      </nav>

      {/* ── Page Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950/80 text-blue-600 dark:text-blue-400 flex items-center justify-center flex-shrink-0 border border-blue-200/60 dark:border-blue-800/60">
            <MessageSquare className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">
              Project Compliance Logs
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-300 mt-0.5">
              Historical regulatory queries, AI responses, and citations generated in this workspace.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => navigate(`/query?p=${projectId}`)}
          className="tt-btn-primary text-xs px-4 py-2.5 rounded-xl flex items-center gap-1.5 self-start sm:self-auto shadow-sm"
        >
          <MessageSquare className="w-3.5 h-3.5" /> Start New Query
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 rounded-xl text-xs font-semibold flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="p-4 bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-200 rounded-xl text-xs font-semibold flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
          <span>{success}</span>
        </div>
      )}

      {/* ── Stats Summary Grid ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-4 shadow-sm flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400 flex items-center justify-center font-bold">
            <MessageSquare className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xl font-extrabold text-slate-900 dark:text-slate-100">{filteredQueries.length}</div>
            <div className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Total Queries</div>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-4 shadow-sm flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400 flex items-center justify-center font-bold">
            <Zap className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xl font-extrabold text-slate-900 dark:text-slate-100">{avgLatency}ms</div>
            <div className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Avg Latency</div>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-4 shadow-sm flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-purple-50 dark:bg-purple-950 text-purple-600 dark:text-purple-400 flex items-center justify-center font-bold">
            <MapPin className="w-4 h-4" />
          </div>
          <div>
            <div className="text-sm font-extrabold text-slate-900 dark:text-slate-100 capitalize truncate max-w-[160px]">
              {munisQueried}
            </div>
            <div className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Jurisdictions</div>
          </div>
        </div>
      </div>

      {/* ── Main Queries Card Panel ── */}
      <div className="bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 sm:p-8 shadow-sm space-y-4">
        {/* Search Bar */}
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3.5 top-3 text-slate-400" />
          <input
            type="text"
            className="w-full bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl pl-10 pr-4 py-2 text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={queryFilter}
            onChange={(e) => setQueryFilter(e.target.value)}
            placeholder="Search queries, citations, or answer text..."
          />
        </div>

        {loading ? (
          <p className="text-sm text-slate-500 dark:text-slate-400 py-4">Loading query history...</p>
        ) : filteredQueries.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400 py-6 text-center">
            {queryFilter ? "No matching queries found." : "No queries logged for this project yet."}
          </p>
        ) : (
          <div className="space-y-3 pt-2">
            {filteredQueries.map((q) => {
              const isExpanded = expandedQueryId === q.id;
              return (
                <article
                  key={q.id}
                  className={`bg-slate-50/60 dark:bg-slate-900/60 border rounded-2xl p-4 transition-all cursor-pointer ${
                    isExpanded
                      ? "border-blue-500 shadow-md ring-1 ring-blue-500/20"
                      : "border-slate-200 dark:border-slate-700/80 hover:border-slate-300 dark:hover:border-slate-600"
                  }`}
                  onClick={() => setExpandedQueryId(isExpanded ? null : q.id)}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="space-y-1">
                      <strong className="text-xs sm:text-sm font-bold text-slate-900 dark:text-slate-100 block">
                        {q.query_text}
                      </strong>
                      <div className="flex items-center gap-3 text-[10px] text-slate-500 dark:text-slate-400">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3 text-slate-400" />
                          {new Date(q.created_at).toLocaleString()}
                        </span>
                        {q.municipality && (
                          <span className="uppercase font-bold text-blue-600 dark:text-blue-400">
                            📍 {q.municipality}
                          </span>
                        )}
                        {q.latency_ms && <span>⏱ {q.latency_ms}ms</span>}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-end sm:self-auto" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        className="tt-btn-secondary text-xs px-3 py-1.5 rounded-lg flex items-center gap-1"
                        onClick={() => handleReloadQuery(q.query_text, q.municipality)}
                      >
                        <ExternalLink className="w-3 h-3 text-blue-500" /> Open in Chat
                      </button>
                      <button
                        type="button"
                        className="p-1.5 text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/50 rounded-lg transition-colors"
                        onClick={(e) => handleDeleteQuery(q.id, e)}
                        title="Delete query log"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-700/80 space-y-3">
                      <div className="flex items-center justify-between">
                        <strong className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                          AI Answer Summary
                        </strong>
                        <button
                          type="button"
                          className="text-xs font-semibold text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 flex items-center gap-1"
                          onClick={(e) => handleCopyAnswer(q.answer_text, q.id, e)}
                        >
                          {copiedId === q.id ? (
                            <>
                              <Check className="w-3.5 h-3.5 text-emerald-500" />
                              <span className="text-emerald-600">Copied!</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-3.5 h-3.5" />
                              <span>Copy Answer</span>
                            </>
                          )}
                        </button>
                      </div>

                      <pre className="p-3 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl text-xs text-slate-800 dark:text-slate-200 leading-relaxed font-sans whitespace-pre-wrap">
                        {q.answer_text}
                      </pre>

                      {q.citations?.length > 0 && (
                        <div className="pt-2">
                          <strong className="text-[11px] font-bold text-slate-600 dark:text-slate-400 block mb-1.5">
                            Citations Used:
                          </strong>
                          <div className="flex flex-wrap gap-1.5">
                            {q.citations.map((cit, idx) => (
                              <span
                                key={idx}
                                className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300"
                              >
                                📁 {cit.doc_id} (ch {cit.chunk_index})
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
