import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, X, Maximize2, Send, ArrowRight } from "lucide-react";
import { useAuth } from "../context/AuthContext.jsx";
import { fetchAnswer } from "../api.js";

export default function AiAssistantWidget() {
  const { user, activeProject } = useAuth();
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: `Hello! I'm your AI Permit & Construction Assistant. How can I help with ${
        activeProject?.name || "your project"
      } today?`,
    },
  ]);

  if (!user) return null;

  const handleSend = async (e) => {
    e?.preventDefault();
    if (!prompt.trim() || loading) return;

    const userText = prompt.trim();
    setPrompt("");
    setMessages((prev) => [...prev, { role: "user", content: userText }]);
    setLoading(true);

    try {
      const res = await fetchAnswer({
        query: userText,
        project_id: activeProject?.id || null,
        municipality: activeProject?.municipality || "Dallas",
      });

      const replyText =
        res.data?.answer ||
        res.data?.abstain_message ||
        "I've processed your query. Open full chat for complete citations.";

      setMessages((prev) => [...prev, { role: "assistant", content: replyText }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, I couldn't process that. Click full-screen to try in the main chat.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleExpandFullScreen = () => {
    setIsOpen(false);
    navigate("/query");
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 font-sans">
      {/* Expanded Popover Modal */}
      {isOpen && (
        <div className="mb-3 w-[360px] max-w-[calc(100vw-2rem)] h-[480px] max-h-[calc(100vh-6rem)] rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl flex flex-col overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 bg-slate-800/90 border-b border-slate-700">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg bg-blue-600/20 border border-blue-500/30 text-blue-400">
                <Sparkles className="w-4 h-4 animate-pulse" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-100 m-0 leading-tight">AI Assistant</h3>
                <p className="text-[11px] text-slate-400 m-0">
                  {activeProject?.name || "Permit & Code Guidance"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={handleExpandFullScreen}
                title="Open Full Screen Chat"
                className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-700/60 rounded-lg transition-colors"
              >
                <Maximize2 className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                title="Close"
                className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-700/60 rounded-lg transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Messages Body */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2.5 text-xs">
            {messages.map((m, idx) => (
              <div
                key={idx}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] px-3 py-2 rounded-xl text-slate-100 ${
                    m.role === "user"
                      ? "bg-blue-600 text-white rounded-br-none"
                      : "bg-slate-800 border border-slate-700/80 rounded-bl-none text-slate-200"
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="bg-slate-800 border border-slate-700 px-3 py-2 rounded-xl text-slate-400 text-xs flex items-center gap-2">
                  <Sparkles className="w-3.5 h-3.5 animate-spin text-blue-400" />
                  Analyzing building codes…
                </div>
              </div>
            )}
          </div>

          {/* Prompt Suggestions */}
          {messages.length <= 2 && (
            <div className="px-3 py-1.5 bg-slate-950/40 border-t border-slate-800 flex gap-1.5 overflow-x-auto">
              <button
                type="button"
                onClick={() => setPrompt("What permits do I need?")}
                className="text-[10px] text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 px-2 py-1 rounded-full whitespace-nowrap transition-colors"
              >
                What permits do I need?
              </button>
              <button
                type="button"
                onClick={() => setPrompt("Building code requirements")}
                className="text-[10px] text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 px-2 py-1 rounded-full whitespace-nowrap transition-colors"
              >
                Code requirements
              </button>
            </div>
          )}

          {/* Input Footer */}
          <form onSubmit={handleSend} className="p-2.5 bg-slate-950 border-t border-slate-800 flex gap-2">
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Ask a code or permit question…"
              className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-100 placeholder-slate-400 focus:outline-none focus:border-blue-500"
            />
            <button
              type="submit"
              disabled={!prompt.trim() || loading}
              className="p-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-xl transition-colors flex items-center justify-center shrink-0"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </form>
          
          <div className="bg-slate-950 px-3 py-1 border-t border-slate-900 text-center">
            <button
              type="button"
              onClick={handleExpandFullScreen}
              className="text-[10px] text-blue-400 hover:text-blue-300 inline-flex items-center gap-1 font-semibold"
            >
              Open Full AI Query Workspace <ArrowRight className="w-2.5 h-2.5" />
            </button>
          </div>
        </div>
      )}

      {/* Floating Trigger Button */}
      {!isOpen && (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="flex items-center gap-2.5 px-4 py-3 rounded-full bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white font-semibold text-xs shadow-xl shadow-blue-900/40 border border-blue-400/30 transition-all transform hover:scale-105 active:scale-95"
        >
          <Sparkles className="w-4 h-4 animate-pulse text-cyan-200" />
          <span>AI Assistant</span>
        </button>
      )}
    </div>
  );
}
