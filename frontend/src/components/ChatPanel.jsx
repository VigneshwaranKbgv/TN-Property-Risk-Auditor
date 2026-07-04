/**
 * ChatPanel.jsx
 * Follow-up Q&A with the property advisor LLM via SSE streaming.
 */

import { useState, useRef, useEffect } from "react";
import { streamChat } from "../api/client";

export default function ChatPanel({ riskMetrics }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    const question = input.trim();
    if (!question || streaming) return;

    const userMsg = { role: "user", content: question };
    const historyForApi = messages.slice(-6); // Keep last 6 turns

    setMessages((prev) => [
      ...prev,
      userMsg,
      { role: "assistant", content: "" }, // Placeholder for streaming
    ]);
    setInput("");
    setStreaming(true);

    try {
      const reader = await streamChat(question, riskMetrics, historyForApi);
      const decoder = new TextDecoder("utf-8");
      let accumulated = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        // Parse SSE lines: "data: <content>\n\n"
        const lines = chunk.split("\n");
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const token = line.slice(6);
            if (token === "[DONE]") break;
            // Un-escape newlines
            accumulated += token.replace(/\\n/g, "\n");
          }
        }

        // Update the last (assistant) message with accumulated text
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: accumulated,
          };
          return updated;
        });
      }
    } catch (err) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content: `⚠ Error: ${err.message}`,
        };
        return updated;
      });
    } finally {
      setStreaming(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col h-72 border border-slate-700/60 rounded-xl overflow-hidden bg-slate-900/60 backdrop-blur-sm">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-slate-700/50 bg-slate-800/50">
        <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        <span className="text-xs font-semibold text-slate-300 uppercase tracking-widest">
          Property Advisor AI
        </span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 scrollbar-thin scrollbar-thumb-slate-600">
        {messages.length === 0 && (
          <p className="text-slate-500 text-sm italic text-center mt-6">
            Ask anything about this property's risk assessment...
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`
                max-w-[85%] px-3 py-2 rounded-xl text-sm leading-relaxed whitespace-pre-wrap
                ${
                  msg.role === "user"
                    ? "bg-indigo-600 text-white rounded-br-none"
                    : "bg-slate-700/80 text-slate-200 rounded-bl-none"
                }
              `}
            >
              {msg.content}
              {streaming &&
                msg.role === "assistant" &&
                i === messages.length - 1 && (
                  <span className="inline-block w-1.5 h-4 ml-0.5 bg-indigo-400 animate-pulse rounded-sm align-middle" />
                )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex items-center gap-2 px-3 py-2 border-t border-slate-700/50 bg-slate-800/30">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={streaming}
          placeholder="Ask anything about this property..."
          className="
            flex-1 bg-slate-800 text-slate-100 placeholder-slate-500 text-sm
            px-3 py-2 rounded-lg border border-slate-600/50
            focus:outline-none focus:ring-2 focus:ring-indigo-500/60
            disabled:opacity-50 disabled:cursor-not-allowed
            transition-all duration-200
          "
        />
        <button
          onClick={sendMessage}
          disabled={streaming || !input.trim()}
          className="
            p-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500
            disabled:opacity-40 disabled:cursor-not-allowed
            transition-all duration-200 text-white
          "
          aria-label="Send message"
        >
          {streaming ? (
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth={4} />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}
