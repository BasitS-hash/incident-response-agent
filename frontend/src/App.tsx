import { useState } from "react";
import ChatUI from "./components/ChatUI";
import WorkflowStepper from "./components/WorkflowStepper";
import HITLApprovalModal from "./components/HITLApprovalModal";
import IncidentDetails from "./components/IncidentDetails";
import { useAgentStream } from "./hooks/useAgentStream";

export default function App() {
  const [sessionKey,   setSessionKey]   = useState(0);
  const [runId,        setRunId]        = useState<string | null>(null);
  const [approvalDone, setApprovalDone] = useState(false);

  const { state, events, awaitingApproval, approvalData, finished, streamError } =
    useAgentStream(runId);

  function handleApprovalDone() {
    setApprovalDone(true); // always close the modal — approve or reject
  }

  function handleReset() {
    setRunId(null);
    setApprovalDone(false);
    setSessionKey((k) => k + 1);
  }

  const isLoading = !!runId && !state.incident_id;

  return (
    <div style={{
      minHeight: "100vh",
      background: "#030712",
      color: "white",
      fontFamily: "'Inter', system-ui, sans-serif",
      padding: "32px 24px",
    }}>
      <div style={{ maxWidth: "1020px", margin: "0 auto" }}>

        {/* ── Header ─────────────────────────────────────── */}
        <div style={{
          marginBottom: "28px",
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
        }}>
          <div>
            <h1 style={{ margin: 0, fontSize: "20px", fontWeight: 700, letterSpacing: "-0.3px" }}>
              Incident Response Agent
            </h1>
            <p style={{ margin: "4px 0 0 0", color: "#6b7280", fontSize: "13px" }}>
              LangGraph · MCP · Mem0 · Langfuse · AG-UI
            </p>
          </div>

          {/* Run status chip */}
          {runId && (
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <div style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: finished ? "#22c55e" : "#3b82f6",
                boxShadow: finished ? "none" : "0 0 0 3px rgba(59,130,246,0.2)",
                transition: "background 0.4s",
              }} />
              <span style={{ fontSize: "12px", color: "#6b7280", fontFamily: "monospace" }}>
                {finished ? "complete" : "running"} · {runId.slice(0, 8)}
              </span>
            </div>
          )}
        </div>

        {/* ── Stream error banner ─────────────────────────── */}
        {streamError && (
          <div style={{
            background: "#450a0a",
            border: "1px solid #7f1d1d",
            borderRadius: "8px",
            padding: "10px 16px",
            marginBottom: "16px",
            color: "#fca5a5",
            fontSize: "13px",
          }}>
            {streamError}
          </div>
        )}

        {/* ── Workflow stepper ───────────────────────────── */}
        {runId && (
          <WorkflowStepper
            state={state}
            awaitingApproval={awaitingApproval && !approvalDone}
            finished={finished}
          />
        )}

        {/* ── Main two-column layout ─────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>

          {/* Chat panel */}
          <div style={{
            background: "#0f172a",
            border: "1px solid #1e293b",
            borderRadius: "12px",
            padding: "20px",
            height: "540px",
            display: "flex",
            flexDirection: "column",
          }}>
            <p style={{
              margin: "0 0 14px 0",
              fontSize: "11px",
              fontWeight: 600,
              color: "#4b5563",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
            }}>
              Chat
            </p>
            <ChatUI
              key={sessionKey}
              onRunStarted={setRunId}
              events={events}
              finished={finished}
              onReset={handleReset}
            />
          </div>

          {/* Live state panel */}
          <div style={{
            background: "#0f172a",
            border: "1px solid #1e293b",
            borderRadius: "12px",
            padding: "20px",
            height: "540px",
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}>
            <p style={{
              margin: 0,
              fontSize: "11px",
              fontWeight: 600,
              color: "#4b5563",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
            }}>
              Live State
            </p>

            {runId ? (
              <IncidentDetails state={state} loading={isLoading} />
            ) : (
              <div style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}>
                <p style={{ color: "#1f2937", fontSize: "13px", textAlign: "center", lineHeight: 1.7 }}>
                  Start an incident to see<br />live state updates here.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── HITL approval modal ────────────────────────────── */}
      {awaitingApproval && !approvalDone &&
       approvalData?.type === "AWAITING_APPROVAL" && (
        <HITLApprovalModal
          run_id={approvalData.run_id}
          rca_summary={approvalData.rca_summary}
          severity={approvalData.severity}
          root_cause={approvalData.root_cause}
          recommended_fix={approvalData.recommended_fix}
          onDone={handleApprovalDone}
        />
      )}
    </div>
  );
}
