import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { API_BASE_URL, DEFAULT_BASE_URL, fetchAnswer, fetchHealth, fetchProjects } from "./api.js";
import { useAuth } from "./context/AuthContext.jsx";
import AddressAutocomplete from "./components/AddressAutocomplete.jsx";

// shadcn component imports
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const DEFAULT_FORM = {
  query: "",
  municipality: "",
  address: "",
  top_k: 5,
};

const QUICK_TESTS = [
  {
    query: "What are the setback requirements for a residential fence in Dallas?",
    municipality: "dallas",
    top_k: 10,
  },
  {
    query: "Do I need a permit for electrical work in Texas?",
    municipality: "",
    top_k: 10,
  },
  {
    query: "What are the ADA accessibility requirements for commercial buildings?",
    municipality: "",
    top_k: 10,
  },
  {
    query: "What is the stormwater management plan requirement for construction sites?",
    municipality: "",
    top_k: 10,
  },
  {
    query: "What are the building permit requirements in Plano?",
    municipality: "plano",
    top_k: 10,
  },
  {
    query: "What are the fire sprinkler requirements for new construction in Dallas?",
    municipality: "dallas",
    top_k: 10,
  },
  {
    query: "What is the maximum building height allowed in a residential zone?",
    municipality: "dallas",
    top_k: 10,
  },
];

function App() {
  const { user } = useAuth();
  const initialSessionId = useMemo(() => `web-${Date.now()}`, []);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);
  const [activeAnswerId, setActiveAnswerId] = useState(null);
  const [activeSourceKey, setActiveSourceKey] = useState(null);
  const [debugLogs, setDebugLogs] = useState([]);
  const [sessionId, setSessionId] = useState(initialSessionId);
  const [healthState, setHealthState] = useState({ status: "idle", detail: "" });
  const [projects, setProjects] = useState([]);
  const [activeProjectId, setActiveProjectId] = useState("");
  const [activeResultsTab, setActiveResultsTab] = useState("answer");

  // Prefill search query if reloading from profile page or project dashboard
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q");
    const m = params.get("m");
    const p = params.get("p");
    if (q) {
      setForm((prev) => ({
        ...prev,
        query: q,
        municipality: m || "",
      }));
    }
    if (p) {
      setActiveProjectId(p);
    }
  }, []);

  useEffect(() => {
    if (user) {
      fetchProjects()
        .then((res) => setProjects(res.data || []))
        .catch(() => {});
    } else {
      setProjects([]);
      setActiveProjectId("");
    }
  }, [user]);

  const canSubmit = useMemo(() => form.query.trim().length >= 3 && !loading, [form.query, loading]);

  const pushDebugLog = (log) => {
    setDebugLogs((prev) => [log, ...prev].slice(0, 20));
  };

  const debugHeaders = useMemo(
    () => ({
      "X-Client-Session-Id": sessionId,
    }),
    [sessionId],
  );

  const checkHealth = async () => {
    setHealthState({ status: "loading", detail: "" });
    const requestId = `health-${Date.now()}`;
    try {
      const result = await fetchHealth({
        ...debugHeaders,
        "X-Client-Request-Id": requestId,
      });
      pushDebugLog({
        type: "health",
        requestId,
        ok: true,
        status: result.status,
        elapsedMs: result.elapsedMs,
        detail: JSON.stringify(result.data),
        createdAt: new Date().toLocaleTimeString(),
      });
      setHealthState({
        status: "ok",
        detail: `API healthy (${result.elapsedMs} ms)`,
      });
    } catch (requestError) {
      const message = requestError?.message || "Health check failed.";
      pushDebugLog({
        type: "health",
        requestId,
        ok: false,
        status: requestError?.meta?.status || "network",
        elapsedMs: requestError?.meta?.elapsedMs || 0,
        detail: message,
        createdAt: new Date().toLocaleTimeString(),
      });
      setHealthState({ status: "error", detail: message });
    }
  };

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({
      ...prev,
      [name]: name === "top_k" ? Number(value) : value,
    }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");

    const payload = {
      query: (form.query || "").trim(),
      top_k: Number(form.top_k),
      municipality: (form.municipality || "").trim() || null,
      address: (form.address || "").trim() || null,
      min_similarity: 0.0,
    };
    if (activeProjectId) {
      payload.project_id = activeProjectId;
    }
    const requestId = `answer-${Date.now()}`;

    try {
      const result = await fetchAnswer(payload, {
        ...debugHeaders,
        "X-Client-Request-Id": requestId,
      });
      const data = result.data;
      const answerItem = {
        id: `${Date.now()}`,
        createdAt: new Date().toLocaleTimeString(),
        query: payload.query,
        municipality: payload.municipality,
        top_k: payload.top_k,
        ...data,
      };
      setHistory((prev) => [answerItem, ...prev]);
      setActiveAnswerId(answerItem.id);
      setActiveResultsTab("answer");
      const firstChunk = answerItem.chunks?.[0];
      setActiveSourceKey(firstChunk ? `${firstChunk.doc_id}-${firstChunk.chunk_index}` : null);
      pushDebugLog({
        type: "answer",
        requestId,
        ok: true,
        status: result.status,
        elapsedMs: result.elapsedMs,
        detail: `chunks=${data.num_chunks} top_similarity=${data.diagnostics?.top_similarity?.toFixed(3) || "n/a"}`,
        createdAt: new Date().toLocaleTimeString(),
      });
    } catch (requestError) {
      setError(requestError.message || "Unknown error.");
      const isNetworkError = `${requestError.message || ""}`.toLowerCase().includes("failed to fetch");
      if (isNetworkError) {
        setError(
          "Failed to fetch. Check API server, URL/port, and CORS allowlist (API_CORS_ALLOW_ORIGINS).",
        );
      }
      pushDebugLog({
        type: "answer",
        requestId,
        ok: false,
        status: requestError?.meta?.status || "network",
        elapsedMs: requestError?.meta?.elapsedMs || 0,
        detail: requestError.message || "Unknown error.",
        createdAt: new Date().toLocaleTimeString(),
      });
    } finally {
      setLoading(false);
    }
  };

  const handleQuickTest = (test) => {
    setForm({
      ...DEFAULT_FORM,
      query: test.query,
      municipality: test.municipality,
      top_k: test.top_k,
    });
  };

  const activeAnswer = useMemo(() => {
    if (!history.length) {
      return null;
    }
    if (!activeAnswerId) {
      return history[0];
    }
    return history.find((item) => item.id === activeAnswerId) || history[0];
  }, [history, activeAnswerId]);

  const sourceChunkMap = useMemo(() => {
    const map = new Map();
    if (!activeAnswer?.chunks) {
      return map;
    }
    for (const chunk of activeAnswer.chunks) {
      map.set(`${chunk.doc_id}-${chunk.chunk_index}`, chunk);
    }
    return map;
  }, [activeAnswer]);

  const activeSourceChunk = useMemo(() => {
    if (!activeAnswer?.chunks?.length) {
      return null;
    }
    if (activeSourceKey && sourceChunkMap.has(activeSourceKey)) {
      return sourceChunkMap.get(activeSourceKey);
    }
    return activeAnswer.chunks[0];
  }, [activeAnswer, activeSourceKey, sourceChunkMap]);

  if (!user) {
    return (
      <div className="flex items-center justify-center min-h-[calc(100vh-100px)] p-4">
        <Card className="w-full max-w-md p-6 text-center border-slate-200 shadow-lg">
          <CardHeader>
            <CardTitle className="text-3xl font-extrabold tracking-tight text-slate-900">Ask permit_rag</CardTitle>
            <CardDescription className="text-slate-500 mt-2">
              Please sign in to search municipal ordinances, check building code compliance, and get cited RAG answers.
            </CardDescription>
          </CardHeader>
          <CardContent className="mt-4">
            <Link to="/auth">
              <Button size="lg" className="w-full">
                Sign In / Register
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="query-page-layout">
      <aside className="query-page-sidebar space-y-6">
          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Project Context</CardTitle>
              <CardDescription>Select workspace for LangSmith tracking</CardDescription>
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

          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Query History</CardTitle>
              <CardDescription>Previous questions in this session</CardDescription>
            </CardHeader>
            <CardContent className="px-2 max-h-[400px] overflow-y-auto">
              {history.length ? (
                <div className="space-y-2">
                  {history.map((item) => {
                    const isActive = item.id === activeAnswer?.id;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => {
                          setActiveAnswerId(item.id);
                          const firstChunk = item.chunks?.[0];
                          setActiveSourceKey(firstChunk ? `${firstChunk.doc_id}-${firstChunk.chunk_index}` : null);
                        }}
                        className={`w-full text-left p-3 rounded-lg border text-sm transition-all ${
                          isActive
                            ? "bg-slate-900 border-slate-900 text-white font-medium shadow-sm"
                            : "bg-background border-slate-200 hover:bg-slate-50 text-slate-700"
                        }`}
                      >
                        <div className="truncate font-medium">{item.query}</div>
                        <div className="flex justify-between items-center mt-1 text-[10px] text-slate-400">
                          <span>{item.createdAt}</span>
                          {item.municipality && (
                            <span className="uppercase bg-slate-100 px-1.5 py-0.5 rounded font-semibold text-slate-600">
                              {item.municipality}
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-slate-500 text-center py-6">No queries yet.</p>
              )}
            </CardContent>
          </Card>
        </aside>

        <div className="query-page-main space-y-6">
          <Card className="shadow-md">
            <CardHeader>
              <CardTitle className="text-2xl font-bold flex items-center gap-2">
                <span>permit_rag</span>
                <span className="text-xs font-normal text-slate-400">Session: {sessionId}</span>
              </CardTitle>
              <CardDescription>
                Ask questions about building codes and receive instant, cited regulatory compliance answers.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {/* Quick Tests */}
              <div className="mb-6">
                <span className="text-xs font-semibold text-slate-500 block mb-2">Quick Test Queries:</span>
                <div className="flex flex-wrap gap-2">
                  {QUICK_TESTS.map((test, index) => (
                    <Button
                      key={index}
                      variant="outline"
                      size="sm"
                      onClick={() => handleQuickTest(test)}
                      className="text-xs h-7 px-3 bg-slate-50 hover:bg-slate-100"
                    >
                      Q{index + 1}
                    </Button>
                  ))}
                </div>
              </div>

              {/* Main Form */}
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="query">Your Compliance Question</Label>
                  <Textarea
                    id="query"
                    name="query"
                    rows={3}
                    value={form.query}
                    onChange={handleChange}
                    placeholder="E.g., What are the setback requirements for a residential fence in Dallas?"
                    className="resize-none"
                    required
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="municipality">Municipality (Optional override)</Label>
                    <Input
                      id="municipality"
                      name="municipality"
                      value={form.municipality}
                      onChange={handleChange}
                      placeholder="e.g., dallas"
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="top_k">Max Source Chunks (Top K)</Label>
                    <Input
                      id="top_k"
                      name="top_k"
                      type="number"
                      min={1}
                      max={50}
                      value={form.top_k}
                      onChange={handleChange}
                    />
                  </div>

                  <div className="space-y-2 md:col-span-1">
                    <Label htmlFor="address">Project Address (Optional - auto-resolves city)</Label>
                    <AddressAutocomplete
                      id="address"
                      value={form.address}
                      onChange={(val) => setForm((prev) => ({ ...prev, address: val }))}
                      onSelect={({ address, municipality }) => {
                        setForm((prev) => ({
                          ...prev,
                          address,
                          municipality: prev.municipality || municipality || "",
                        }));
                      }}
                    />
                  </div>
                </div>

                <div className="pt-2">
                  <Button type="submit" disabled={!canSubmit} className="w-full md:w-auto px-8">
                    {loading ? "Analyzing..." : "Ask permit_rag"}
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

          {/* Results Tabs */}
          {activeAnswer && (
            <Tabs
              value={activeResultsTab}
              onValueChange={setActiveResultsTab}
              orientation="horizontal"
              className="query-results-tabs w-full"
            >
              <TabsList className="query-results-tablist w-full">
                <TabsTrigger value="answer">Answer & Citations</TabsTrigger>
                <TabsTrigger value="sources">Source Chunks</TabsTrigger>
                <TabsTrigger value="diagnostics">Diagnostics</TabsTrigger>
                <TabsTrigger value="debug">Developer Logs</TabsTrigger>
              </TabsList>

              {/* Tab 1: Answer */}
              <TabsContent value="answer" className="mt-4 space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-xl">Generated Compliance Answer</CardTitle>
                    {activeAnswer.resolved_municipality && (
                      <CardDescription className="text-blue-600 font-medium">
                        📍 Auto-detected Jurisdiction: {activeAnswer.resolved_municipality.toUpperCase()}
                      </CardDescription>
                    )}
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg whitespace-pre-wrap text-slate-800 leading-relaxed text-sm">
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

                    {/* Citations List */}
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
                              onClick={() => {
                                setActiveSourceKey(citationKey);
                                setActiveResultsTab("sources");
                              }}
                              className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700"
                            >
                              📁 {citation.doc_id} (ch {citation.chunk_index})
                            </Button>
                          );
                        })}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>

              {/* Tab 2: Source Chunks */}
              <TabsContent value="sources" className="mt-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-xl">Retrieved Source Chunks</CardTitle>
                    <CardDescription>
                      Review the specific legal code passages retrieved from database embeddings.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                      
                      {/* Left list */}
                      <div className="md:col-span-1 space-y-2 max-h-[400px] overflow-y-auto pr-2">
                        {(activeAnswer.chunks || []).map((chunk) => {
                          const chunkKey = `${chunk.doc_id}-${chunk.chunk_index}`;
                          const isSelected = activeSourceChunk
                            ? `${activeSourceChunk.doc_id}-${activeSourceChunk.chunk_index}` === chunkKey
                            : false;
                          const isFiltered = chunk.filtered_out === true;
                          return (
                            <button
                              key={chunkKey}
                              type="button"
                              onClick={() => setActiveSourceKey(chunkKey)}
                              className={`w-full text-left p-3 rounded-lg border text-xs transition-all ${
                                isSelected
                                  ? "bg-slate-900 border-slate-900 text-white font-medium shadow-sm"
                                  : isFiltered
                                  ? "opacity-50 border-dashed border-slate-200 hover:bg-slate-50 text-slate-400"
                                  : "bg-slate-50 border-slate-200 hover:bg-slate-100 text-slate-700"
                              }`}
                            >
                              <div className="font-semibold truncate">{chunk.doc_id}</div>
                              <div className="flex justify-between items-center mt-1.5 text-[10px]">
                                <span>Chunk {chunk.chunk_index}</span>
                                <span className="font-mono bg-white/20 px-1 py-0.25 rounded">
                                  Score: {(chunk.reranked_score ?? chunk.similarity)?.toFixed(3)}
                                </span>
                              </div>
                            </button>
                          );
                        })}
                      </div>

                      {/* Right Detail Viewer */}
                      <div className="md:col-span-2 bg-slate-50 border border-slate-200 rounded-lg p-4">
                        {activeSourceChunk ? (
                          <div className="space-y-4">
                            <div>
                              <h3 className="text-base font-bold text-slate-800">{activeSourceChunk.doc_id}</h3>
                              <div className="flex flex-wrap gap-2 mt-1.5">
                                <span className="text-[10px] uppercase font-bold px-2 py-0.5 bg-blue-100 text-blue-800 rounded">
                                  {activeSourceChunk.municipality}
                                </span>
                                <span className="text-[10px] uppercase font-bold px-2 py-0.5 bg-slate-200 text-slate-800 rounded">
                                  {activeSourceChunk.authority_level}
                                </span>
                                <span className="text-[10px] uppercase font-bold px-2 py-0.5 bg-purple-100 text-purple-800 rounded">
                                  {activeSourceChunk.doc_type}
                                </span>
                                <span className="text-[10px] uppercase font-bold px-2 py-0.5 bg-green-100 text-green-800 rounded">
                                  {activeSourceChunk.document_status}
                                </span>
                              </div>
                            </div>
                            <div className="p-3 bg-white border border-slate-200 rounded-md overflow-x-auto">
                              <pre className="text-xs text-slate-700 whitespace-pre-wrap leading-relaxed font-sans">
                                {activeSourceChunk.content}
                              </pre>
                            </div>
                          </div>
                        ) : (
                          <p className="text-slate-500 text-center py-20 text-sm">Select a chunk to view details.</p>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>

              {/* Tab 3: Diagnostics */}
              <TabsContent value="diagnostics" className="mt-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-xl">Evaluation & RAG Metrics</CardTitle>
                    <CardDescription>
                      Performance measurements and database retrieval stats.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Metric</TableHead>
                          <TableHead>Value</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        <TableRow>
                          <TableCell className="font-medium">Top Vector Similarity</TableCell>
                          <TableCell className="font-mono text-sm">
                            {activeAnswer.diagnostics.top_similarity?.toFixed(4)}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell className="font-medium">Mean Vector Similarity</TableCell>
                          <TableCell className="font-mono text-sm">
                            {activeAnswer.diagnostics.mean_similarity?.toFixed(4)}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell className="font-medium">Unique Source Documents</TableCell>
                          <TableCell>{activeAnswer.diagnostics.unique_doc_count}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell className="font-medium">Retrieval Latency</TableCell>
                          <TableCell className="font-mono">{activeAnswer.latency_retrieval_ms} ms</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell className="font-medium">LLM Generation Latency</TableCell>
                          <TableCell className="font-mono">{activeAnswer.latency_generation_ms} ms</TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              </TabsContent>

              {/* Tab 4: Debug Logs */}
              <TabsContent value="debug" className="mt-4 space-y-4">
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <div>
                      <CardTitle className="text-xl">Developer & API Logs</CardTitle>
                      <CardDescription>Verify request details and server responses.</CardDescription>
                    </div>
                    <Button variant="outline" size="sm" onClick={checkHealth}>
                      {healthState.status === "loading" ? "..." : "Check API Health"}
                    </Button>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {healthState.detail && (
                      <div className={`p-3 rounded text-xs font-semibold ${
                        healthState.status === "ok" ? "bg-green-50 text-green-800 border border-green-200" : "bg-red-50 text-red-800 border border-red-200"
                      }`}>
                        {healthState.detail}
                      </div>
                    )}

                    <div className="space-y-2">
                      <span className="text-xs font-semibold text-slate-500 block">Session History Logs (Last 20 Requests):</span>
                      {debugLogs.length ? (
                        <div className="space-y-2 max-h-[300px] overflow-y-auto">
                          {debugLogs.map((log, i) => (
                            <div
                              key={i}
                              className={`p-3 rounded-lg border text-xs font-mono flex flex-col gap-1 ${
                                log.ok ? "bg-green-50/50 border-green-200 text-green-950" : "bg-red-50/50 border-red-200 text-red-950"
                              }`}
                            >
                              <div className="flex justify-between items-center">
                                <span className="font-bold">[{log.type.toUpperCase()}]</span>
                                <span>{log.createdAt}</span>
                              </div>
                              <div>ID: {log.requestId}</div>
                              <div>Status: {log.status} in {log.elapsedMs} ms</div>
                              <div className="text-[10px] text-slate-500 mt-1 truncate">{log.detail}</div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-400 italic">No session logs captured yet.</p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          )}
        </div>
    </div>
  );
}

export default App;
