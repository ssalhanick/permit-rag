import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";
import { deleteQueryFromHistory, fetchQueryHistory } from "../../api.js";
import {
  MessageSquare,
  RotateCcw,
  Trash2,
  Copy,
  Check,
  Search,
  Calendar,
  MapPin,
  ChevronDown,
  ChevronUp,
  Sparkles
} from "lucide-react";

/**
 * Modernized User Query History page with search, expand, copy, reload & delete actions.
 */
export default function ProfileHistoryPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [queries, setQueries] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [expandedQueryId, setExpandedQueryId] = useState(null);
  const [copyFeedbackId, setCopyFeedbackId] = useState(null);
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
      setTimeout(() => setActionSuccess(""), 3000);
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
    navigate(`/query?${params.toString()}`);
  };

  const handleCopyAnswer = (text, id, e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopyFeedbackId(id);
    setTimeout(() => setCopyFeedbackId(null), 2500);
  };

  const filteredQueries = queries.filter(
    (q) =>
      q.query_text?.toLowerCase().includes(search.toLowerCase()) ||
      q.answer_text?.toLowerCase().includes(search.toLowerCase()) ||
      q.municipality?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-4 sm:p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200 dark:border-slate-800">
        <div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            Query History
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Review, inspect, reload, or manage your past AI compliance searches and answers.
          </p>
        </div>

        {/* Search Bar */}
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search past queries or answers..."
            className="w-full pl-9 pr-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {actionError && (
        <div className="p-3 bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 rounded-xl text-xs font-semibold">
          {actionError}
        </div>
      )}
      {actionSuccess && (
        <div className="p-3 bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 rounded-xl text-xs font-semibold">
          {actionSuccess}
        </div>
      )}

      {loading ? (
        <div className="py-12 text-center text-xs text-slate-400 animate-pulse">
          Loading query history...
        </div>
      ) : filteredQueries.length === 0 ? (
        <div className="py-16 text-center bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-8 space-y-3">
          <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-400 flex items-center justify-center mx-auto">
            <MessageSquare className="w-6 h-6" />
          </div>
          <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">
            {search ? "No matching queries found" : "No search history yet"}
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 max-w-sm mx-auto">
            {search
              ? "Try adjusting your search keywords."
              : "When you perform AI code lookups, your history will appear here for easy reference."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredQueries.map((q) => {
            const isExpanded = expandedQueryId === q.id;
            const dateStr = new Date(q.created_at).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
              year: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            });

            return (
              <div
                key={q.id}
                className={`bg-white dark:bg-slate-900 border transition-all rounded-2xl overflow-hidden ${
                  isExpanded
                    ? "border-blue-500/80 shadow-md ring-1 ring-blue-500/20"
                    : "border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 shadow-sm"
                }`}
              >
                {/* Header Row */}
                <div
                  onClick={() => setExpandedQueryId(isExpanded ? null : q.id)}
                  className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 cursor-pointer select-none"
                >
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <div className="p-2 rounded-xl bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 shrink-0 mt-0.5">
                      <Sparkles className="w-4 h-4" />
                    </div>
                    <div className="space-y-1 min-w-0">
                      <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100 leading-snug">
                        {q.query_text}
                      </h4>
                      <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500 dark:text-slate-400">
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3 h-3 text-slate-400" />
                          {dateStr}
                        </span>
                        {q.municipality && (
                          <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-semibold">
                            <MapPin className="w-3 h-3 text-blue-500" />
                            {q.municipality}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Actions & Chevron */}
                  <div
                    className="flex items-center gap-2 self-end sm:self-center shrink-0"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      type="button"
                      onClick={() => handleReloadQuery(q.query_text, q.municipality)}
                      className="px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 text-xs font-semibold flex items-center gap-1.5 transition-colors"
                      title="Reload in AI Assistant"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      <span>Reload</span>
                    </button>

                    <button
                      type="button"
                      onClick={(e) => handleDeleteQuery(q.id, e)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors"
                      title="Delete entry"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>

                    <div className="p-1 text-slate-400">
                      {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </div>
                  </div>
                </div>

                {/* Expanded Answer Body */}
                {isExpanded && (
                  <div className="px-4 pb-4 pt-2 border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                        AI Output & Citations
                      </span>
                      <button
                        type="button"
                        onClick={(e) => handleCopyAnswer(q.answer_text, q.id, e)}
                        className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1 font-semibold"
                      >
                        {copyFeedbackId === q.id ? (
                          <>
                            <Check className="w-3.5 h-3.5 text-emerald-500" />
                            <span className="text-emerald-500">Copied!</span>
                          </>
                        ) : (
                          <>
                            <Copy className="w-3.5 h-3.5" />
                            <span>Copy Answer</span>
                          </>
                        )}
                      </button>
                    </div>

                    <div className="p-3.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs sm:text-sm text-slate-800 dark:text-slate-200 whitespace-pre-wrap leading-relaxed">
                      {q.answer_text}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
