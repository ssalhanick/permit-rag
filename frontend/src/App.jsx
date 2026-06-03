import React, { useMemo, useState } from "react";
import { API_BASE_URL, DEFAULT_BASE_URL, fetchAnswer, fetchHealth } from "./api.js";

const DEFAULT_FORM = {
  query: "",
  municipality: "",
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
      query: form.query.trim(),
      top_k: Number(form.top_k),
      municipality: form.municipality.trim() || null,
      min_similarity: 0.0,
    };
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

  return (
    <main className="page">
      <section className="panel">
        <h1>permit_rag</h1>
        <p className="muted">First interaction flow: ask question and get cited answer.</p>
        <p className="muted">API base: {API_BASE_URL}</p>
        <p className="muted">Default API base: {DEFAULT_BASE_URL}</p>
        <p className="muted">Session ID: {sessionId}</p>
        <p className="muted">Quick test set (7): click one to auto-fill.</p>

        <div className="debug-toolbar">
          <button type="button" className="secondary-button" onClick={checkHealth}>
            {healthState.status === "loading" ? "Checking API..." : "Check API health"}
          </button>
          <button type="button" className="secondary-button" onClick={() => setSessionId(`web-${Date.now()}`)}>
            New session ID
          </button>
        </div>
        {healthState.detail ? <p className="muted">{healthState.detail}</p> : null}

        <div className="quick-tests">
          {QUICK_TESTS.map((test, index) => (
            <button
              key={`${index + 1}`}
              type="button"
              className="quick-test-button"
              onClick={() => handleQuickTest(test)}
            >
              Q{index + 1}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="form">
          <label htmlFor="query">Question</label>
          <textarea
            id="query"
            name="query"
            rows={4}
            value={form.query}
            onChange={handleChange}
            placeholder="What are the setback requirements for a residential fence in Dallas?"
            required
          />

          <div className="row">
            <div>
              <label htmlFor="municipality">Municipality (optional)</label>
              <input
                id="municipality"
                name="municipality"
                value={form.municipality}
                onChange={handleChange}
                placeholder="dallas"
              />
            </div>
            <div>
              <label htmlFor="top_k">Top K</label>
              <input
                id="top_k"
                name="top_k"
                type="number"
                min={1}
                max={50}
                value={form.top_k}
                onChange={handleChange}
              />
            </div>
          </div>

          <button type="submit" disabled={!canSubmit}>
            {loading ? "Asking..." : "Ask permit_rag"}
          </button>
        </form>

        {error ? <p className="error">{error}</p> : null}
      </section>

      {history.length ? (
        <section className="panel">
          <h2>Chat History</h2>
          <ul className="history-list">
            {history.map((item) => {
              const isActive = item.id === activeAnswer?.id;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`history-item ${isActive ? "history-item-active" : ""}`}
                    onClick={() => {
                      setActiveAnswerId(item.id);
                      const firstChunk = item.chunks?.[0];
                      setActiveSourceKey(firstChunk ? `${firstChunk.doc_id}-${firstChunk.chunk_index}` : null);
                    }}
                  >
                    <span>{item.query}</span>
                    <small>
                      {item.createdAt}
                      {item.municipality ? ` - ${item.municipality}` : ""}
                    </small>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {activeAnswer ? (
        <section className="panel">
          <h2>Answer</h2>
          <div className="answer-text">{activeAnswer.answer}</div>

          <h3>Citations</h3>
          <ul className="citation-list">
            {(activeAnswer.citations || []).map((citation) => {
              const citationKey = `${citation.doc_id}-${citation.chunk_index}`;
              return (
                <li key={citationKey}>
                  <button
                    type="button"
                    className="citation-link"
                    onClick={() => setActiveSourceKey(citationKey)}
                  >
                    [{citation.doc_id}, chunk {citation.chunk_index}]
                  </button>{" "}
                  - {citation.found_in_context ? "in retrieved context" : "not found in context"}
                </li>
              );
            })}
          </ul>

          <h3>Diagnostics</h3>
          <ul>
            <li>top similarity: {activeAnswer.diagnostics.top_similarity?.toFixed(3)}</li>
            <li>mean similarity: {activeAnswer.diagnostics.mean_similarity?.toFixed(3)}</li>
            <li>unique source docs: {activeAnswer.diagnostics.unique_doc_count}</li>
            <li>retrieval latency: {activeAnswer.latency_retrieval_ms} ms</li>
            <li>generation latency: {activeAnswer.latency_generation_ms} ms</li>
          </ul>
        </section>
      ) : null}

      {activeAnswer ? (
        <section className="panel">
          <h2>Source Chunk Viewer</h2>
          <p className="muted">Click a citation or pick a chunk below.</p>

          <div className="source-grid">
            <ul className="source-list">
              {(activeAnswer.chunks || []).map((chunk) => {
                const chunkKey = `${chunk.doc_id}-${chunk.chunk_index}`;
                const active = activeSourceChunk
                  ? `${activeSourceChunk.doc_id}-${activeSourceChunk.chunk_index}` === chunkKey
                  : false;
                return (
                  <li key={chunkKey}>
                    <button
                      type="button"
                      className={`source-item ${active ? "source-item-active" : ""}`}
                      onClick={() => setActiveSourceKey(chunkKey)}
                    >
                      [{chunk.doc_id}, chunk {chunk.chunk_index}] ({chunk.similarity?.toFixed(3)})
                    </button>
                  </li>
                );
              })}
            </ul>

            {activeSourceChunk ? (
              <article className="source-detail">
                <h3>
                  {activeSourceChunk.doc_id} - chunk {activeSourceChunk.chunk_index}
                </h3>
                <p className="meta">
                  {activeSourceChunk.municipality} | {activeSourceChunk.authority_level} |{" "}
                  {activeSourceChunk.doc_type} | {activeSourceChunk.document_status}
                </p>
                <pre>{activeSourceChunk.content}</pre>
              </article>
            ) : (
              <p>No source chunk available.</p>
            )}
          </div>
        </section>
      ) : null}

      <section className="panel">
        <h2>Debug Logs</h2>
        <p className="muted">
          If you see `Failed to fetch`, usually API is down, wrong URL/port, or browser blocked CORS.
        </p>
        {debugLogs.length ? (
          <ul className="debug-list">
            {debugLogs.map((log) => (
              <li key={`${log.requestId}-${log.createdAt}`} className={log.ok ? "debug-ok" : "debug-error"}>
                <strong>{log.type.toUpperCase()}</strong> [{log.requestId}] {log.status} in {log.elapsedMs} ms -{" "}
                {log.detail}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No debug logs yet.</p>
        )}
      </section>
    </main>
  );
}

export default App;
