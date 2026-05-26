import { useState, useRef, useEffect } from "react";
import { startIncident } from "../api/client";
import type { AgentEvent } from "../hooks/useAgentStream";

interface Message {
  role: "user" | "agent";
  content: string;
}

interface Props {
  onRunStarted: (run_id: string) => void;
  events: AgentEvent[];
  finished: boolean;
  onReset: () => void;
}

/**
 * Maps a single SSE event to a human-readable chat message.
 * `seen` is mutated in-place to track which milestones have already been emitted.
 * Returns null when no message should be added (duplicate or uninteresting event).
 */
function milestoneMessage(event: AgentEvent, seen: Set<string>): string | null {
  if (event.type === "STATE_SNAPSHOT") {
    const s = event.state;
    if (s.email_sent && !seen.has("notify")) {
      seen.add("notify");
      return "Notification sent. Workflow complete.";
    }
    if (s.root_cause && !seen.has("rca")) {
      seen.add("rca");
      return "RCA complete — root cause identified. Human approval required.";
    }
    if (s.severity && !seen.has("triage")) {
      seen.add("triage");
      return `Triage complete — severity: ${String(s.severity)}.`;
    }
    if (s.incident_id && !seen.has("intake")) {
      seen.add("intake");
      return `Intake complete — tracking ${String(s.incident_id)}.`;
    }
    return null;
  }
  if (event.type === "AWAITING_APPROVAL" && !seen.has("approval")) {
    seen.add("approval");
    return "Waiting for human approval. Review the RCA in the modal.";
  }
  if (event.type === "RUN_FINISHED" && !seen.has("finished")) {
    seen.add("finished");
    return "All done. Workflow finished successfully.";
  }
  if (event.type === "RUN_ERROR" && !seen.has("error")) {
    seen.add("error");
    return `Workflow error: ${event.message}`;
  }
  return null;
}

export default function ChatUI({ onRunStarted, events, finished, onReset }: Props) {
  const [messages, setMessages] = useState<Message[]>([
    { role: "agent", content: "Hello. Provide an incident ID to begin triage (e.g. INC-101)." },
  ]);
  const [input,   setInput]   = useState("");
  const [loading, setLoading] = useState(false);

  const bottomRef  = useRef<HTMLDivElement>(null);
  const milestones = useRef(new Set<string>());

  // Auto-scroll to bottom whenever messages or the typing indicator change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Convert incoming SSE events into human-readable chat messages
  useEffect(() => {
    if (events.length === 0) return;
    const newMessages: Message[] = [];
    for (const event of events) {
      const msg = milestoneMessage(event, milestones.current);
      if (msg) newMessages.push({ role: "agent", content: msg });
    }
    if (newMessages.length > 0) {
      setMessages((prev) => [...prev, ...newMessages]);
    }
  }, [events]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setInput("");
    setLoading(true);

    try {
      setMessages((prev) => [
        ...prev,
        { role: "agent", content: `Starting workflow for ${trimmed}...` },
      ]);
      const res = await startIncident(trimmed);
      onRunStarted(res.run_id);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "agent",
          content: "Could not reach the backend. Check that uvicorn is running on port 8000.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: "12px" }}>

      {/* ── Message list ──────────────────────────────────── */}
      <div style={{
        flex: 1,
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
        gap: "10px",
        paddingRight: "2px",
      }}>
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              alignSelf: m.role === "user" ? "flex-end" : "flex-start",
              background: m.role === "user" ? "#2563eb" : "#1e293b",
              color: "white",
              padding: "9px 13px",
              borderRadius: m.role === "user"
                ? "12px 12px 3px 12px"
                : "12px 12px 12px 3px",
              maxWidth: "85%",
              fontSize: "13.5px",
              lineHeight: 1.55,
            }}
          >
            {m.content}
          </div>
        ))}

        {/* Typing indicator — shown while waiting for the API */}
        {loading && (
          <div style={{
            alignSelf: "flex-start",
            background: "#1e293b",
            padding: "11px 16px",
            borderRadius: "12px 12px 12px 3px",
            display: "flex",
            gap: "5px",
            alignItems: "center",
          }}>
            <span className="typing-dot" style={dotStyle} />
            <span className="typing-dot" style={dotStyle} />
            <span className="typing-dot" style={dotStyle} />
          </div>
        )}

        {/* Scroll anchor */}
        <div ref={bottomRef} />
      </div>

      {/* ── Input area ───────────────────────────────────── */}
      {finished ? (
        <button onClick={onReset} style={resetBtnStyle}>
          + Start New Incident
        </button>
      ) : (
        <form onSubmit={handleSubmit} style={{ display: "flex", gap: "8px" }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Enter incident ID (e.g. INC-101)"
            disabled={loading}
            style={{
              flex: 1,
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: "8px",
              padding: "10px 14px",
              color: "white",
              fontSize: "14px",
              outline: "none",
              transition: "border-color 0.2s",
            }}
            onFocus={(e) => { e.currentTarget.style.borderColor = "#3b82f6"; }}
            onBlur={(e)  => { e.currentTarget.style.borderColor = "#334155"; }}
          />
          <button
            type="submit"
            disabled={loading}
            style={{
              background: loading ? "#1d4ed8" : "#3b82f6",
              border: "none",
              color: "white",
              padding: "10px 20px",
              borderRadius: "8px",
              cursor: loading ? "not-allowed" : "pointer",
              fontWeight: 600,
              fontSize: "14px",
              transition: "background 0.2s",
              whiteSpace: "nowrap",
            }}
          >
            {loading ? "Running..." : "Start"}
          </button>
        </form>
      )}
    </div>
  );
}

const dotStyle: React.CSSProperties = {
  width: 7,
  height: 7,
  background: "#64748b",
  borderRadius: "50%",
  display: "inline-block",
};

const resetBtnStyle: React.CSSProperties = {
  background: "transparent",
  border: "1px solid #1e293b",
  borderRadius: "8px",
  color: "#64748b",
  padding: "10px",
  fontSize: "14px",
  cursor: "pointer",
  width: "100%",
  transition: "border-color 0.2s, color 0.2s",
};
