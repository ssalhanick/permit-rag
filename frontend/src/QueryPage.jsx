import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { fetchAnswer, fetchProjects, fetchQueryHistory, submitAnswerFeedback } from "./api.js";
import { useAuth } from "./context/AuthContext.jsx";
import {
  MessageSquare,
  Send,
  Mic,
  Plus,
  Search,
  Sparkles,
  ShieldAlert,
  FileText,
  Check,
  Copy,
  ThumbsUp,
  ThumbsDown,
  RotateCcw,
  Building2,
  HelpCircle,
  Wrench,
  BookOpen,
  Layers,
  ChevronRight,
  ExternalLink,
  Bot,
  User,
  Lightbulb,
  AlertOctagon
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

const PROMPT_SUGGESTIONS = [
  {
    icon: Building2,
    title: "Fence Setbacks",
    query: "What are the setback requirements for a residential privacy fence in Dallas?",
  },
  {
    icon: Wrench,
    title: "Water Heater Venting",
    query: "Do I need a permit to replace a gas water heater in Plano?",
  },
  {
    icon: Layers,
    title: "Electrical Outlet Spacing",
    query: "What is the maximum spacing for wall outlets in residential living rooms?",
  },
  {
    icon: BookOpen,
    title: "Deck Building Thresholds",
    query: "At what height does an outdoor deck require a building permit and railing?",
  },
];

export default function QueryPage() {
  const { user, activeProject } = useAuth();
  const location = useLocation();
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [activeAnswerId, setActiveAnswerId] = useState(null);
  const [historySearch, setHistorySearch] = useState("");
  const [copiedId, setCopiedId] = useState(null);

  const [projects, setProjects] = useState([]);

  // Manual project pick override
  const manualOverrideRef = useRef(false);
  const [activeProjectId, setActiveProjectIdState] = useState("");

  const chatContainerRef = useRef(null);
  const textareaRef = useRef(null);

  const setActiveProjectId = (id) => {
    manualOverrideRef.current = true;
    setActiveProjectIdState(id);
  };

  // Reactively track location params (e.g., /query?p=123) and active project
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const pParam = params.get("p") || params.get("project_id") || params.get("projectId");
    if (pParam) {
      manualOverrideRef.current = true;
      setActiveProjectIdState(pParam);
    } else if (!manualOverrideRef.current) {
      setActiveProjectIdState(activeProject?.id || "");
    }

    const q = params.get("q");
    if (q) setQuery(q);
  }, [location.search, activeProject?.id]);

  useEffect(() => {
    if (user) {
      fetchProjects()
        .then((res) => {
          const list = res.data || [];
          setProjects(list);
          if (activeProjectId && !list.some((p) => p.id === activeProjectId)) {
            setActiveProjectId("");
          }
        })
        .catch(() => {});
    } else {
      setProjects([]);
      setActiveProjectIdState("");
    }
  }, [user]);

  // Load persisted query history
  useEffect(() => {
    if (!user) {
      setHistory([]);
      setActiveAnswerId(null);
      return;
    }
    let cancelled = false;
    setHistoryLoading(true);
    fetchQueryHistory(activeProjectId || undefined)
      .then((res) => {
        if (cancelled) return;
        const items = (res.data || []).map((row) => ({
          id: row.id,
          createdAt: new Date(row.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          query: row.query_text,
          answer: row.answer_text,
          citations: row.citations,
          resolved_municipality: row.municipality,
          run_id: row.run_id,
        }));
        setHistory(items);
        setActiveAnswerId(items[0]?.id ?? null);
      })
      .catch(() => {
        if (!cancelled) setHistory([]);
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user, activeProjectId]);

  const canSubmit = useMemo(() => query.trim().length >= 3 && !loading, [query, loading]);

  const handleVoiceInput = async () => {
    try {
      const { startSpeechRecognition } = await import("./services/roomCapture.js");
      const res = await startSpeechRecognition();
      if (res.transcript) {
        setQuery(res.transcript);
      } else if (res.error && res.error !== "No speech detected") {
        const friendlyError =
          res.error === "not-allowed" || res.error === "permission-denied"
            ? "Microphone access denied. Please allow microphone access in your browser settings."
            : res.error === "network"
            ? "Voice input requires an active internet connection."
            : res.error === "no-speech"
            ? "No speech detected. Try speaking closer to your mic."
            : `Voice input failed: ${res.error}`;
        setError(friendlyError);
      }
    } catch (err) {
      setError(`Voice input not supported: ${err.message}`);
    }
  };

  const handleSubmit = async (event) => {
    if (event) event.preventDefault();
    if (!canSubmit) return;

    setLoading(true);
    setError("");

    const currentQueryText = query.trim();
    const payload = {
      query: currentQueryText,
      top_k: 8,
    };
    if (activeProjectId) {
      payload.project_id = activeProjectId;
    }
    const requestId = `answer-${Date.now()}`;

    try {
      const result = await fetchAnswer(payload, {
        "X-Client-Request-Id": requestId,
      });
      const data = result.data;
      const answerItem = {
        id: `${Date.now()}`,
        createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        query: currentQueryText,
        ...data,
      };
      setHistory((prev) => [answerItem, ...prev]);
      setActiveAnswerId(answerItem.id);
      setQuery(""); // Clear input on success
    } catch (requestError) {
      setError(requestError.message || "Unknown error occurred.");
      const isNetworkError = `${requestError.message || ""}`.toLowerCase().includes("failed to fetch");
      if (isNetworkError) {
        setError("Failed to connect to the compliance server. Check your network or API status.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const activeAnswer = useMemo(() => {
    if (!history.length) return null;
    if (!activeAnswerId) return history[0];
    return history.find((item) => item.id === activeAnswerId) || history[0];
  }, [history, activeAnswerId]);

  // Phase 5 feedback loop
  const [feedbackByRun, setFeedbackByRun] = useState({});

  const patchFeedback = (runId, patch) =>
    setFeedbackByRun((prev) => ({ ...prev, [runId]: { ...prev[runId], ...patch } }));

  const sendFeedback = async (runId, rating, comment) => {
    if (!runId) return;
    patchFeedback(runId, { sending: true, error: "" });
    try {
      await submitAnswerFeedback({ run_id: runId, rating, comment: comment || null });
      patchFeedback(runId, {
        rating,
        sending: false,
        showComment: rating === "down" && !comment,
        comment: comment || "",
      });
    } catch (err) {
      patchFeedback(runId, { sending: false, error: err.message || "Could not send feedback." });
    }
  };

  const handleCopyText = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2500);
  };

  const filteredHistory = history.filter((item) =>
    item.query.toLowerCase().includes(historySearch.toLowerCase())
  );

  const selectedProjectObj = projects.find((p) => p.id === activeProjectId);

  return (
    <div className="flex h-[calc(100vh-4rem)] max-w-[1600px] mx-auto overflow-hidden bg-slate-50/50 dark:bg-slate-950">
      {/* ── Left Sidebar (ChatGPT / Claude Style) ── */}
      <aside className="w-80 flex-shrink-0 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full shadow-sm hidden md:flex">
        {/* New Chat & Context Header */}
        <div className="p-4 border-b border-slate-100 dark:border-slate-800/80 space-y-3">
          <button
            type="button"
            onClick={() => {
              setActiveAnswerId(null);
              setQuery("");
            }}
            className="w-full py-2.5 px-4 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs flex items-center justify-center gap-2 shadow-sm transition-all"
          >
            <Plus className="w-4 h-4" /> New Compliance Query
          </button>

          {/* Project Selector Badge */}
          <div className="pt-1">
            <label className="block text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5 flex items-center justify-between">
              <span>Active Workspace Context</span>
              {selectedProjectObj && (
                <span className="text-blue-600 dark:text-blue-400 font-bold">{selectedProjectObj.municipality || "Universal"}</span>
              )}
            </label>
            <select
              value={activeProjectId || "none"}
              onChange={(e) => setActiveProjectId(e.target.value === "none" ? "" : e.target.value)}
              className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 font-medium"
            >
              <option value="none">🌐 Global Vault (No project context)</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  📁 {p.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* History Search */}
        <div className="px-3 pt-3 pb-1">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              value={historySearch}
              onChange={(e) => setHistorySearch(e.target.value)}
              placeholder="Search conversations..."
              className="w-full bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/70 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-800 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
        </div>

        {/* History Thread List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {historyLoading ? (
            <div className="py-8 text-center text-xs text-slate-400">Loading conversation history...</div>
          ) : filteredHistory.length > 0 ? (
            filteredHistory.map((item) => {
              const isActive = item.id === activeAnswer?.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActiveAnswerId(item.id)}
                  className={`w-full text-left p-2.5 rounded-xl text-xs transition-all flex flex-col gap-1 group ${
                    isActive
                      ? "bg-slate-900 dark:bg-slate-800 text-white font-medium shadow-sm"
                      : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800/50"
                  }`}
                >
                  <div className="flex items-center gap-2 truncate">
                    <MessageSquare className={`w-3.5 h-3.5 flex-shrink-0 ${isActive ? "text-blue-400" : "text-slate-400 group-hover:text-slate-600"}`} />
                    <span className="truncate">{item.query}</span>
                  </div>
                  <div className="flex items-center justify-between text-[10px] opacity-70 pl-5">
                    <span>{item.createdAt}</span>
                    {item.resolved_municipality && (
                      <span className="uppercase tracking-wider font-semibold text-[9px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300">
                        {item.resolved_municipality}
                      </span>
                    )}
                  </div>
                </button>
              );
            })
          ) : (
            <div className="py-8 text-center text-xs text-slate-400">
              {historySearch ? "No matching queries found." : "No prior conversations."}
            </div>
          )}
        </div>
      </aside>

      {/* ── Main Chat Area (ChatGPT Canvas Layout) ── */}
      <main className="flex-1 flex flex-col h-full overflow-hidden relative">
        {/* Top Header Bar */}
        <div className="px-6 py-3 border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md flex items-center justify-between z-10">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold shadow-sm">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-extrabold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                ToolTime AI Compliance Assistant
              </h2>
              <p className="text-[10px] text-slate-500 dark:text-slate-400">
                Grounding Engine v2.4 • Municipal Code & Ordinance RAG
              </p>
            </div>
          </div>

          {/* Project Mobile / Header Badge */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
              {selectedProjectObj ? `Workspace: ${selectedProjectObj.name}` : "Global Context"}
            </span>
          </div>
        </div>

        {/* Conversation Feed / Scroll Canvas */}
        <div ref={chatContainerRef} className="flex-1 overflow-y-auto p-4 sm:p-6 md:p-8 space-y-6">

          {!activeAnswer && history.length === 0 && !loading ? (
            /* ── Claude-style Welcome & Prompt Suggestions Hero ── */
            <div className="max-w-2xl mx-auto py-12 text-center space-y-8">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-500 text-white flex items-center justify-center mx-auto shadow-xl shadow-blue-500/20">
                <Sparkles className="w-8 h-8" />
              </div>
              <div className="space-y-2">
                <h1 className="text-3xl font-extrabold text-slate-900 dark:text-slate-100 tracking-tight">
                  Where should we start?
                </h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 max-w-md mx-auto">
                  Ask compliance questions regarding setbacks, electrical rules, plumbing vents, or permit requirements.
                </p>
              </div>

              {/* Prompt Chips */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-left">
                {PROMPT_SUGGESTIONS.map((s, idx) => {
                  const Icon = s.icon;
                  return (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => {
                        setQuery(s.query);
                        textareaRef.current?.focus();
                      }}
                      className="p-4 bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800/80 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm hover:shadow-md transition-all group"
                    >
                      <div className="flex items-center gap-2 font-bold text-xs text-slate-800 dark:text-slate-200 group-hover:text-blue-600 dark:group-hover:text-blue-400">
                        <Icon className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                        {s.title}
                      </div>
                      <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 line-clamp-2">
                        {s.query}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            /* ── Thread Message Display ── */
            <div className="max-w-3xl mx-auto space-y-6">
              {activeAnswer && (
                <>
                  {/* User Question Bubble */}
                  <div className="flex items-start justify-end gap-3">
                    <div className="bg-blue-600 text-white rounded-2xl rounded-tr-none px-4 py-3 shadow-md text-sm max-w-xl">
                      <p className="whitespace-pre-wrap">{activeAnswer.query}</p>
                    </div>
                    <div className="w-8 h-8 rounded-full bg-slate-900 text-white flex items-center justify-center text-xs font-bold flex-shrink-0">
                      <User className="w-4 h-4" />
                    </div>
                  </div>

                  {/* Assistant Answer Card Bubble */}
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs font-bold flex-shrink-0 shadow-md">
                      <Bot className="w-4 h-4" />
                    </div>

                    <div className="flex-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-tl-none p-5 sm:p-6 shadow-sm space-y-4">
                      {/* Answer Header */}
                      <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-slate-900 dark:text-slate-100">
                            {activeAnswer.how_to
                              ? "🔧 How-To Guide"
                              : activeAnswer.abstained
                              ? "⚠️ General Regulatory Guidance"
                              : "Compliance Analysis"}
                          </span>
                          {activeAnswer.resolved_municipality && (
                            <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-md bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800">
                              📍 {activeAnswer.resolved_municipality}
                            </span>
                          )}
                        </div>

                        <button
                          type="button"
                          onClick={() => handleCopyText(activeAnswer.answer, activeAnswer.id)}
                          className="text-xs text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 flex items-center gap-1 transition-colors"
                        >
                          {copiedId === activeAnswer.id ? (
                            <>
                              <Check className="w-3.5 h-3.5 text-emerald-500" />
                              <span className="text-emerald-600 font-semibold text-[11px]">Copied!</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-3.5 h-3.5" />
                              <span>Copy</span>
                            </>
                          )}
                        </button>
                      </div>

                      {/* Ungrounded Guidance Warning Banner */}
                      {activeAnswer.abstained && (
                        <div className="flex items-center gap-2 text-xs font-bold px-3.5 py-2.5 rounded-xl bg-amber-500/10 text-amber-800 dark:text-amber-300 border border-amber-500/30">
                          <AlertOctagon className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0" />
                          <span>General Knowledge Fallback (Unverified against specific local municipal code corpus)</span>
                        </div>
                      )}

                      {/* Persona Nudge */}
                      {activeAnswer.persona_nudge && (
                        <div className="flex gap-2.5 p-3 bg-blue-50/80 dark:bg-blue-950/40 border border-blue-200/80 dark:border-blue-800/60 text-blue-900 dark:text-blue-200 rounded-xl text-xs">
                          <Lightbulb className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" />
                          <span>{activeAnswer.persona_nudge}</span>
                        </div>
                      )}

                      {/* Educational Disclaimer */}
                      {activeAnswer.how_to && activeAnswer.educational_disclaimer && (
                        <div className="flex gap-2.5 p-3 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-amber-900 dark:text-amber-200 rounded-xl text-xs">
                          <HelpCircle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                          <span>{activeAnswer.educational_disclaimer}</span>
                        </div>
                      )}

                      {/* Main Answer Content */}
                      <div
                        className={`p-4 rounded-xl text-xs sm:text-sm leading-relaxed whitespace-pre-wrap ${
                          activeAnswer.abstained
                            ? "bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700/80 text-slate-900 dark:text-slate-100"
                            : "bg-slate-50/70 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800 text-slate-800 dark:text-slate-100"
                        }`}
                      >
                        {activeAnswer.answer}
                      </div>

                      {/* Interactive Clarification Multiple-Choice Chips */}
                      {(activeAnswer.clarifying_options || []).length > 0 && (
                        <div className="p-4 bg-slate-100/70 dark:bg-slate-800/90 border border-slate-200 dark:border-slate-700 rounded-xl space-y-3">
                          <div className="flex items-center gap-1.5 font-bold text-xs text-slate-800 dark:text-slate-200">
                            <Lightbulb className="w-4 h-4 text-blue-500" />
                            <span>Refine query with specific parameters:</span>
                          </div>
                          <div className="space-y-3 pt-1">
                            {activeAnswer.clarifying_options.map((opt, oIdx) => (
                              <div key={oIdx} className="space-y-1.5">
                                <span className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 block">
                                  {opt.label}
                                </span>
                                <div className="flex flex-wrap gap-2">
                                  {opt.choices.map((choice, cIdx) => (
                                    <button
                                      key={cIdx}
                                      type="button"
                                      onClick={() => {
                                        setQuery((prev) => (prev.trim() ? `${prev.trim()} (${choice})` : choice));
                                        textareaRef.current?.focus();
                                      }}
                                      className="px-3 py-1.5 text-xs rounded-full bg-white dark:bg-slate-900 hover:bg-blue-600 hover:text-white dark:hover:bg-blue-600 dark:hover:text-white border border-slate-200 dark:border-slate-700 font-medium transition-all shadow-sm flex items-center gap-1 cursor-pointer"
                                    >
                                      <span>+ {choice}</span>
                                    </button>
                                  ))}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* AHJ Disclaimer */}
                      {activeAnswer.ahj_disclaimer && (
                        <div className="flex gap-3 p-4 bg-amber-50/70 dark:bg-amber-950/30 border-l-4 border-amber-500 rounded-r-xl text-xs text-amber-900 dark:text-amber-200">
                          <ShieldAlert className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                          <div className="space-y-1">
                            <strong className="font-bold text-amber-950 dark:text-amber-100 block">
                              Authority Having Jurisdiction (AHJ) Notice
                            </strong>
                            <p className="leading-relaxed">{activeAnswer.ahj_disclaimer.text}</p>
                            {activeAnswer.ahj_disclaimer.learn_more_url && (
                              <a
                                href={activeAnswer.ahj_disclaimer.learn_more_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 mt-1 underline font-bold text-amber-900 dark:text-amber-100 hover:text-amber-700"
                              >
                                Verify with building department <ExternalLink className="w-3 h-3" />
                              </a>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Conflict Warnings */}
                      {activeAnswer.conflict_warnings?.length > 0 && (
                        <div className="p-4 bg-orange-50/70 dark:bg-orange-950/30 border-l-4 border-orange-500 rounded-r-xl text-xs text-orange-900 dark:text-orange-200 space-y-2">
                          <strong className="font-extrabold text-orange-950 dark:text-orange-100 block flex items-center gap-1.5">
                            <AlertOctagon className="w-4 h-4 text-orange-600" /> Regulatory Conflicts Detected
                          </strong>
                          <p className="text-[11px] text-orange-800 dark:text-orange-300">
                            The following topics have differing requirements across municipal or state levels.
                          </p>
                          <ul className="space-y-2 pt-1">
                            {activeAnswer.conflict_warnings.map((w, i) => (
                              <li key={i} className="bg-white/90 dark:bg-slate-900 p-3 rounded-lg border border-orange-200 dark:border-orange-900/60">
                                <span className="font-bold text-orange-950 dark:text-orange-100 block">{w.subject}</span>
                                <span className="text-[10px] text-slate-500 block mb-1">
                                  [{w.chunk_a_doc_id}, ch {w.chunk_a_index}] ({w.chunk_a_authority}) vs [{w.chunk_b_doc_id}, ch {w.chunk_b_index}] ({w.chunk_b_authority})
                                </span>
                                <p className="text-orange-900 dark:text-orange-200 mt-1">{w.detail}</p>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Source Citations */}
                      {(activeAnswer.citations || []).length > 0 && (
                        <div className="pt-3 border-t border-slate-100 dark:border-slate-800">
                          <h4 className="font-bold text-xs text-slate-700 dark:text-slate-300 mb-2">Verified Code Sources:</h4>
                          <div className="flex flex-wrap gap-2">
                            {activeAnswer.citations.map((citation, idx) => (
                              <span
                                key={idx}
                                className="inline-flex items-center gap-1 text-[11px] font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700"
                              >
                                <FileText className="w-3 h-3 text-blue-500" />
                                {citation.doc_id} (ch {citation.chunk_index})
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* How-to Videos */}
                      {(activeAnswer.media_refs || []).length > 0 && (
                        <div className="pt-3 border-t border-slate-100 dark:border-slate-800">
                          <h4 className="font-bold text-xs text-slate-700 dark:text-slate-300 mb-2">📺 Instructional Video References:</h4>
                          <ul className="space-y-2">
                            {activeAnswer.media_refs.map((m, i) => (
                              <li key={i} className="text-xs">
                                <a
                                  href={m.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-blue-600 dark:text-blue-400 hover:underline font-bold flex items-center gap-1"
                                >
                                  ▶ {m.title} <ExternalLink className="w-3 h-3" />
                                </a>
                                {m.relevance_note && (
                                  <span className="text-slate-500 dark:text-slate-400 text-[11px] block mt-0.5">{m.relevance_note}</span>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Feedback Rating Controls */}
                      {activeAnswer.run_id && (() => {
                        const fb = feedbackByRun[activeAnswer.run_id] || {};
                        return (
                          <div className="pt-3 border-t border-slate-100 dark:border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
                            <span className="text-slate-500 dark:text-slate-400">Was this response helpful?</span>
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                disabled={fb.sending}
                                onClick={() => sendFeedback(activeAnswer.run_id, "up", fb.comment)}
                                className={`p-1.5 rounded-lg border transition-colors flex items-center gap-1 text-xs font-semibold ${
                                  fb.rating === "up"
                                    ? "bg-emerald-50 dark:bg-emerald-950 border-emerald-500 text-emerald-700 dark:text-emerald-300"
                                    : "bg-slate-50 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-100"
                                }`}
                              >
                                <ThumbsUp className="w-3.5 h-3.5" /> Helpful
                              </button>
                              <button
                                type="button"
                                disabled={fb.sending}
                                onClick={() => sendFeedback(activeAnswer.run_id, "down", fb.comment)}
                                className={`p-1.5 rounded-lg border transition-colors flex items-center gap-1 text-xs font-semibold ${
                                  fb.rating === "down"
                                    ? "bg-rose-50 dark:bg-rose-950 border-rose-500 text-rose-700 dark:text-rose-300"
                                    : "bg-slate-50 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-100"
                                }`}
                              >
                                <ThumbsDown className="w-3.5 h-3.5" /> Issues
                              </button>
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {/* ── Bottom Floating Input Dock (ChatGPT / Claude Style) ── */}
        <div className="p-4 bg-gradient-to-t from-slate-50 dark:from-slate-950 via-slate-50/80 dark:via-slate-950/80 to-transparent">
          <div className="max-w-3xl mx-auto">
            <form
              onSubmit={handleSubmit}
              className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/80 rounded-2xl shadow-xl p-3 flex flex-col gap-2 transition-all focus-within:border-blue-500 dark:focus-within:border-blue-500"
            >
              <Textarea
                ref={textareaRef}
                id="query"
                name="query"
                rows={2}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about building codes, setback rules, or permit requirements... (Enter to send, Shift+Enter for newline)"
                className="w-full resize-none border-none focus-visible:ring-0 focus-visible:ring-offset-0 bg-transparent text-xs sm:text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 p-1"
                required
              />

              <div className="flex items-center justify-between pt-1 border-t border-slate-100 dark:border-slate-800">
                <div className="flex items-center gap-2 text-slate-400">
                  <button
                    type="button"
                    onClick={handleVoiceInput}
                    className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 rounded-xl transition-colors flex items-center gap-1.5 text-xs font-semibold"
                    title="Voice Input"
                  >
                    <Mic className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                    <span className="hidden sm:inline">Voice</span>
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-400 font-medium hidden sm:inline">
                    {query.trim().length} chars
                  </span>
                  <button
                    type="submit"
                    disabled={!canSubmit}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-xl text-xs font-extrabold flex items-center gap-1.5 shadow-md transition-all"
                  >
                    {loading ? (
                      <>Analyzing...</>
                    ) : (
                      <>
                        Send <Send className="w-3.5 h-3.5" />
                      </>
                    )}
                  </button>
                </div>
              </div>
            </form>

            {error && (
              <div className="mt-3 p-3 bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-800 text-rose-800 dark:text-rose-200 rounded-xl text-xs font-semibold flex items-center gap-2">
                <AlertOctagon className="w-4 h-4 text-rose-600 dark:text-rose-400 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
