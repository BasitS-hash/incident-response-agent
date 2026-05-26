import { useState } from "react";
import { submitApproval } from "../api/client";

interface Props {
  run_id: string;
  rca_summary: string;
  severity: string;
  root_cause: string;
  recommended_fix: string;
  onDone: (approved: boolean) => void;
}

export default function HITLApprovalModal({
  run_id, rca_summary, severity, root_cause, recommended_fix, onDone,
}: Props) {
  const [approver, setApprover] = useState("");
  const [notes,    setNotes]    = useState("");
  const [loading,  setLoading]  = useState(false);

  async function handleDecision(approved: boolean) {
    if (!approver.trim()) {
      alert("Please enter your name before approving.");
      return;
    }
    setLoading(true);
    try {
      await submitApproval(run_id, { approved, approver, notes });
      onDone(approved);
    } catch {
      alert("Approval submission failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  const severityColor: Record<string, string> = {
    P1: "#ef4444", P2: "#f97316", P3: "#eab308", P4: "#22c55e",
  };

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50,
    }}>
      <div style={{
        background: "#1f2937", border: "1px solid #374151", borderRadius: "12px",
        padding: "32px", maxWidth: "600px", width: "90%", color: "white",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "20px" }}>
          <h2 style={{ margin: 0 }}>Human Review Required</h2>
          <span style={{
            background: severityColor[severity] ?? "#6b7280",
            padding: "2px 10px", borderRadius: "9999px", fontSize: "13px", fontWeight: 700,
          }}>{severity}</span>
        </div>

        <Section label="Root Cause"     value={root_cause}     />
        <Section label="RCA Summary"    value={rca_summary}    />
        <Section label="Recommended Fix" value={recommended_fix} />

        <input
          placeholder="Your name (approver)"
          value={approver}
          onChange={(e) => setApprover(e.target.value)}
          style={inputStyle}
        />
        <textarea
          placeholder="Optional notes..."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          style={{ ...inputStyle, resize: "vertical" }}
        />

        <div style={{ display: "flex", gap: "12px", marginTop: "20px" }}>
          <button
            onClick={() => handleDecision(true)}
            disabled={loading}
            style={btnStyle("#22c55e")}
          >
            {loading ? "Submitting..." : "Approve & Send Notification"}
          </button>
          <button
            onClick={() => handleDecision(false)}
            disabled={loading}
            style={btnStyle("#ef4444")}
          >
            Reject — Re-run RCA
          </button>
        </div>
      </div>
    </div>
  );
}

function Section({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ marginBottom: "16px" }}>
      <div style={{ fontSize: "11px", color: "#9ca3af", textTransform: "uppercase", marginBottom: "4px" }}>
        {label}
      </div>
      <div style={{ background: "#111827", padding: "10px 14px", borderRadius: "6px", fontSize: "14px", lineHeight: 1.6 }}>
        {value || "—"}
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%", background: "#111827", border: "1px solid #374151",
  borderRadius: "6px", padding: "10px 14px", color: "white",
  fontSize: "14px", marginTop: "8px", boxSizing: "border-box",
};

function btnStyle(bg: string): React.CSSProperties {
  return {
    flex: 1, background: bg, border: "none", color: "white",
    padding: "12px", borderRadius: "8px", fontSize: "14px",
    fontWeight: 600, cursor: "pointer",
  };
}
