import React, { useEffect, useMemo, useRef, useState } from "react";
import { fetchAnswer, fetchProjects, fetchQueryHistory } from "./api.js";
import { useAuth } from "./context/AuthContext.jsx";
import RoomScansHomePromo from "./components/RoomScansHomePromo.jsx";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export default function QueryPage() {
  const { user, activeProject } = useAuth();
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [activeAnswerId, setActiveAnswerId] = useState(null);

  const [projects, setProjects] = useState([]);

  // The project selector here defaults to the navbar's active project, but a
  // manual pick on this page is a local override — it doesn't change the
  // navbar or the user's persisted active_project_id.
  const initialOverride = new URLSearchParams(window.location.search).get("p");
  const manualOverrideRef = useRef(Boolean(initialOverride));
  const [activeProjectId, setActiveProjectIdState] = useState(initialOverride || "");

  const setActiveProjectId = (id) => {
    manualOverrideRef.current = true;
    setActiveProjectIdState(id);
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q");
    if (q) setQuery(q);
  }, []);

  // Track the navbar's active project until the user manually overrides it here.
  useEffect(() => {
    if (!manualOverrideRef.current) {
      setActiveProjectIdState(activeProject?.id || "");
    }
  }, [activeProject?.id]);

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

  // Load persisted query history, scoped to the active project (or all of the
  // user's history when no project is selected).
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
          createdAt: new Date(row.created_at).toLocaleTimeString(),
          query: row.query_text,
          answer: row.answer_text,
          citations: row.citations,
          resolved_municipality: row.municipality,
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
            ? "Microphone access denied. Click the 🔒 lock icon in your address bar, set Microphone to 'Allow', and try again."
            : res.error === "network"
            ? "Voice input requires an internet connection."
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
    event.preventDefault();
    setLoading(true);
    setError("");

    const payload = {
      query: query.trim(),
      // top_k 8 (was 5): more chunks clear the 0.74 grounding floor, so the UI
      // abstains less often than the low-k default did.
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
        createdAt: new Date().toLocaleTimeString(),
        query: payload.query,
        ...data,
      };
      setHistory((prev) => [answerItem, ...prev]);
      setActiveAnswerId(answerItem.id);
      setQuery(""); // Clear input on success
    } catch (requestError) {
      setError(requestError.message || "Unknown error.");
      const isNetworkError = `${requestError.message || ""}`.toLowerCase().includes("failed to fetch");
      if (isNetworkError) {
        setError(
          "Failed to fetch. Check API server, URL/port, and CORS allowlist.",
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const activeAnswer = useMemo(() => {
    if (!history.length) return null;
    if (!activeAnswerId) return history[0];
    return history.find((item) => item.id === activeAnswerId) || history[0];
  }, [history, activeAnswerId]);

  return (
    <div className="query-page-layout px-4 max-w-7xl mx-auto py-8">
      <aside className="query-page-sidebar space-y-6">
          <Card className="shadow-sm p-4">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Project Context</CardTitle>
              <CardDescription>Select workspace context for location</CardDescription>
            </CardHeader>
            <CardContent>
              {projects.length > 0 ? (
                <Select
                  value={activeProjectId || "none"}
                  onValueChange={(val) => setActiveProjectId(val === "none" ? "" : val)}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="-- No project context --" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">-- No project context --</SelectItem>
                    {projects.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <p className="text-sm text-slate-500">No projects found. Create one in Projects tab.</p>
              )}
            </CardContent>
          </Card>

          <Card className="shadow-sm p-4">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Query History</CardTitle>
              <CardDescription>Previous questions</CardDescription>
            </CardHeader>
            <CardContent className="px-2 max-h-[400px] overflow-y-auto">
              {historyLoading ? (
                <p className="text-sm text-slate-500 text-center py-6">Loading…</p>
              ) : history.length ? (
                <div className="space-y-2">
                  {history.map((item) => {
                    const isActive = item.id === activeAnswer?.id;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => setActiveAnswerId(item.id)}
                        className={`w-full text-left p-3 rounded-lg border text-sm transition-all ${
                          isActive
                            ? "bg-slate-900 border-slate-900 text-white font-medium shadow-sm"
                            : "bg-background border-slate-200 hover:bg-slate-50 text-slate-700"
                        }`}
                      >
                        <div className="truncate font-medium">{item.query}</div>
                        <div className="flex justify-between items-center mt-1 text-[10px] text-slate-400">
                          <span>{item.createdAt}</span>
                          {item.resolved_municipality && (
                            <span className="uppercase bg-slate-100 px-1.5 py-0.5 rounded font-semibold text-slate-600">
                              {item.resolved_municipality}
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-slate-500 text-center py-6">
                  {activeProjectId ? "No queries yet for this project." : "No queries yet."}
                </p>
              )}
            </CardContent>
          </Card>
        </aside>

        <main className="query-page-main space-y-6">
          <RoomScansHomePromo />

          <Card className="shadow-md p-4">
            <CardHeader>
              <CardTitle className="text-2xl font-bold">Municipality Ordinance Searching</CardTitle>
              <CardDescription>
                Ask questions about building codes and receive instant, cited regulatory compliance answers.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="query">Your Compliance Question</Label>
                  <div className="relative">
                    <Textarea
                      id="query"
                      name="query"
                      rows={3}
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="E.g., What are the setback requirements for a residential fence in Dallas?"
                      className="resize-none pr-12"
                      required
                    />
                    <button
                      type="button"
                      onClick={handleVoiceInput}
                      className="absolute right-3 bottom-3 p-2 bg-emerald-950 hover:bg-emerald-900 border border-emerald-800 text-emerald-100 rounded-full text-lg leading-none transition-colors"
                      title="Speak your question"
                      aria-label="Speak your question"
                    >
                      🎙
                    </button>
                  </div>
                </div>

                <div className="pt-2">
                  <Button type="submit" disabled={!canSubmit} className="w-full md:w-auto px-8">
                    {loading ? "Analyzing..." : "Search Codes"}
                  </Button>
                </div>
              </form>

              {error && (
                <div className="mt-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm font-medium">
                  {error}
                </div>
              )}
            </CardContent>
          </Card>

          {activeAnswer && (
            <Card className="p-4">
              <CardHeader>
                <CardTitle className="text-xl">
                  {activeAnswer.abstained ? "No confident answer found" : "Generated Compliance Answer"}
                </CardTitle>
                {activeAnswer.resolved_municipality && (
                  <CardDescription className="text-blue-600 font-medium">
                    📍 Auto-detected Jurisdiction: {activeAnswer.resolved_municipality.toUpperCase()}
                  </CardDescription>
                )}
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Clarification nudge (Phase 4): no persona was set, answered neutrally */}
                {activeAnswer.persona_nudge && (
                  <div className="flex gap-3 p-3 bg-blue-50 border border-blue-200 text-blue-800 rounded-lg text-sm">
                    <span className="text-base">💡</span>
                    <span>{activeAnswer.persona_nudge}</span>
                  </div>
                )}

                <div
                  className={`p-4 border rounded-lg whitespace-pre-wrap leading-relaxed text-sm ${
                    activeAnswer.abstained
                      ? "bg-blue-50 border-blue-200 text-blue-900"
                      : "bg-slate-50 border-slate-200 text-slate-800"
                  }`}
                >
                  {activeAnswer.answer}
                </div>

                {/* AHJ Disclaimer */}
                {activeAnswer.ahj_disclaimer && (
                  <div className="flex gap-3 p-4 bg-amber-50 border-l-4 border-amber-500 rounded-r-lg text-sm text-amber-800">
                    <span className="text-lg">⚠️</span>
                    <div className="space-y-1">
                      <strong className="font-semibold text-amber-900 block">Authority Having Jurisdiction (AHJ) Notice</strong>
                      <p>{activeAnswer.ahj_disclaimer.text}</p>
                      {activeAnswer.ahj_disclaimer.learn_more_url && (
                        <a
                          href={activeAnswer.ahj_disclaimer.learn_more_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-block mt-1 underline font-semibold text-amber-900 hover:text-amber-700"
                        >
                          Verify with building department →
                        </a>
                      )}
                    </div>
                  </div>
                )}

                {/* Conflict Warnings */}
                {activeAnswer.conflict_warnings?.length > 0 && (
                  <div className="p-4 bg-orange-50 border-l-4 border-orange-500 rounded-r-lg text-sm text-orange-800 space-y-2">
                    <strong className="font-semibold text-orange-900 block">⚠️ Regulatory Conflicts Detected</strong>
                    <p className="text-xs text-orange-700">
                      The following topics have differing requirements across municipal or state levels. Verify with your AHJ.
                    </p>
                    <ul className="space-y-2 pt-2">
                      {activeAnswer.conflict_warnings.map((w, i) => (
                        <li key={i} className="bg-white/80 p-3 rounded border border-orange-200">
                          <span className="font-bold text-orange-950 block">{w.subject}</span>
                          <span className="text-[10px] text-slate-500 block mb-1">
                            [{w.chunk_a_doc_id}, chunk {w.chunk_a_index}] ({w.chunk_a_authority}) vs [{w.chunk_b_doc_id}, chunk {w.chunk_b_index}] ({w.chunk_b_authority})
                          </span>
                          <p className="text-orange-900 mt-1">{w.detail}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Citations List — hidden on an abstain (no citations) */}
                {(activeAnswer.citations || []).length > 0 && (
                <div className="pt-4 border-t border-slate-100">
                  <h4 className="font-semibold text-sm text-slate-700 mb-2">Source Citations:</h4>
                  <div className="flex flex-wrap gap-2">
                    {(activeAnswer.citations || []).map((citation) => {
                      const citationKey = `${citation.doc_id}-${citation.chunk_index}`;
                      return (
                        <Button
                          key={citationKey}
                          variant="secondary"
                          size="sm"
                          className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 cursor-default"
                        >
                          📁 {citation.doc_id} (ch {citation.chunk_index})
                        </Button>
                      );
                    })}
                  </div>
                </div>
                )}
              </CardContent>
            </Card>
          )}
        </main>
    </div>
  );
}
