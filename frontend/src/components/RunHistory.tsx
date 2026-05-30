import { useEffect, useState, useCallback, Fragment } from "react";
import { getRuns, type RunRecord } from "../api/client";

/* ── helpers ────────────────────────────────────────────────────── */

function fmt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function duration(start: string, end: string | null): string {
  if (!end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  return `${Math.round(ms / 60_000)}m`;
}

/* ── sub-components ─────────────────────────────────────────────── */

const SEV_COLOUR: Record<string, { bg: string; text: string }> = {
  P1: { bg: "#450a0a", text: "#fca5a5" },
  P2: { bg: "#431407", text: "#fdba74" },
  P3: { bg: "#422006", text: "#fcd34d" },
  P4: { bg: "#052e16", text: "#86efac" },
};

function SeverityBadge({ value }: { value: string | null }) {
  if (!value) return <span style={{ color: "#475569" }}>—</span>;
  const c = SEV_COLOUR[value] ?? { bg: "#1e293b", text: "#94a3b8" };
  return (
    <span style={{
      background: c.bg, color: c.text,
      padding: "2px 8px", borderRadius: 9999,
      fontSize: 11, fontWeight: 600,
    }}>
      {value}
    </span>
  );
}

const STATUS_COLOUR: Record<string, string> = {
  completed:         "#4ade80",
  rejected:          "#f87171",
  awaiting_approval: "#fbbf24",
  running:           "#60a5fa",
};

function StatusChip({ status }: { status: RunRecord["status"] }) {
  const colour = STATUS_COLOUR[status] ?? "#94a3b8";
  const label: Record<RunRecord["status"], string> = {
    completed:         "Completed",
    rejected:          "Rejected",
    awaiting_approval: "Awaiting",
    running:           "Running",
  };
  return (
    <span style={{ color: colour, fontSize: 12, fontWeight: 500 }}>
      {label[status]}
    </span>
  );
}

/* ── expanded detail panel ─────────────────────────────────────── */

function DetailRow({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <tr style={{ borderBottom: "1px solid #0f172a" }}>
      <td style={{
        color: "#475569", padding: "8px 16px 8px 0",
        whiteSpace: "nowrap", verticalAlign: "top", fontSize: 12, width: 148,
      }}>
        {label}
      </td>
      <td style={{ color: "#cbd5e1", padding: "8px 0", lineHeight: 1.55, fontSize: 13 }}>
        {value}
      </td>
    </tr>
  );
}

function ExpandedRow({ run }: { run: RunRecord }) {
  return (
    <tr>
      <td colSpan={8} style={{ padding: 0 }}>
        <div style={{
          background: "#070d1a",
          borderLeft: "3px solid #1e40af",
          margin: "0 0 2px 0",
          padding: "16px 20px",
        }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <tbody>
              <DetailRow label="Run ID"          value={run.run_id} />
              <DetailRow label="Triage Notes"    value={run.triage_notes} />
              <DetailRow label="Root Cause"      value={run.root_cause} />
              <DetailRow label="RCA Summary"     value={run.rca_summary} />
              <DetailRow label="Recommended Fix" value={run.recommended_fix} />
              {run.affected_systems?.length > 0 && (
                <DetailRow
                  label="Affected Systems"
                  value={run.affected_systems.join(", ")}
                />
              )}
              <DetailRow label="Approver"       value={run.approver} />
              <DetailRow label="Approval Notes" value={run.approval_notes} />
            </tbody>
          </table>
        </div>
      </td>
    </tr>
  );
}

/* ── main component ─────────────────────────────────────────────── */

export default function RunHistory() {
  const [runs,       setRuns]       = useState<RunRecord[]>([]);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filter,     setFilter]     = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getRuns(100);
      setRuns(data);
    } catch {
      setError("Could not load run history — is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleRow = (id: string) =>
    setExpandedId((prev) => (prev === id ? null : id));

  const q = filter.trim().toLowerCase();
  const visible = q
    ? runs.filter(
        (r) =>
          r.incident_id.toLowerCase().includes(q) ||
          r.status.toLowerCase().includes(q) ||
          (r.severity ?? "").toLowerCase().includes(q) ||
          (r.approver ?? "").toLowerCase().includes(q)
      )
    : runs;

  /* ── render ── */
  return (
    <div style={{
      background: "#0f172a",
      border: "1px solid #1e293b",
      borderRadius: "12px",
      padding: "20px",
      marginTop: "20px",
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <p style={{
          margin: 0, fontSize: "11px", fontWeight: 600,
          color: "#4b5563", textTransform: "uppercase", letterSpacing: "0.08em",
          flexShrink: 0,
        }}>
          Run History
        </p>

        {/* Search filter */}
        <input
          type="text"
          placeholder="Filter by incident, severity, status…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{
            flex: 1, minWidth: 180, background: "#0a1628",
            border: "1px solid #1e293b", borderRadius: 6,
            color: "#94a3b8", fontSize: 12, padding: "4px 10px",
            outline: "none",
          }}
        />

        <button
          onClick={load}
          disabled={loading}
          style={{
            background: "none", border: "1px solid #1e293b",
            color: "#4b5563", borderRadius: 6, padding: "3px 10px",
            fontSize: 11, cursor: loading ? "not-allowed" : "pointer",
            flexShrink: 0,
          }}
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {/* Error */}
      {error && (
        <p style={{ color: "#f87171", fontSize: 13, margin: "0 0 12px 0" }}>{error}</p>
      )}

      {/* Empty */}
      {!loading && !error && visible.length === 0 && runs.length === 0 && (
        <p style={{ color: "#1f2937", fontSize: 13, textAlign: "center", padding: "24px 0" }}>
          No runs yet — start an incident above to see history here.
        </p>
      )}

      {/* No-match message when filter is active */}
      {!loading && !error && runs.length > 0 && visible.length === 0 && (
        <p style={{ color: "#374151", fontSize: 13, textAlign: "center", padding: "16px 0" }}>
          No runs match "{filter}"
        </p>
      )}

      {/* Table */}
      {visible.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #1e293b" }}>
                {["Incident", "Started", "Duration", "Severity", "Status", "Approver", "Email", ""].map(
                  (h) => (
                    <th key={h} style={{
                      textAlign: "left", padding: "0 12px 10px 0",
                      color: "#374151", fontSize: 11, fontWeight: 600,
                      whiteSpace: "nowrap",
                    }}>
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {visible.map((run) => {
                const isOpen = expandedId === run.run_id;
                return (
                  <Fragment key={run.run_id}>
                    <tr
                      key={run.run_id}
                      onClick={() => toggleRow(run.run_id)}
                      style={{
                        borderBottom: isOpen ? "none" : "1px solid #0f172a",
                        cursor: "pointer",
                        background: isOpen ? "#070d1a" : "transparent",
                        transition: "background 0.15s",
                      }}
                    >
                      {/* Incident ID */}
                      <td style={{ padding: "10px 12px 10px 0", color: "#e2e8f0", fontWeight: 500, whiteSpace: "nowrap" }}>
                        {run.incident_id}
                      </td>
                      {/* Started */}
                      <td style={{ padding: "10px 12px 10px 0", color: "#64748b", whiteSpace: "nowrap" }}>
                        {fmt(run.started_at)}
                      </td>
                      {/* Duration */}
                      <td style={{ padding: "10px 12px 10px 0", color: "#64748b", whiteSpace: "nowrap" }}>
                        {duration(run.started_at, run.completed_at)}
                      </td>
                      {/* Severity */}
                      <td style={{ padding: "10px 12px 10px 0" }}>
                        <SeverityBadge value={run.severity} />
                      </td>
                      {/* Status */}
                      <td style={{ padding: "10px 12px 10px 0" }}>
                        <StatusChip status={run.status} />
                      </td>
                      {/* Approver */}
                      <td style={{ padding: "10px 12px 10px 0", color: "#64748b", whiteSpace: "nowrap" }}>
                        {run.approver ?? "—"}
                      </td>
                      {/* Email sent */}
                      <td style={{ padding: "10px 12px 10px 0" }}>
                        {run.email_sent ? (
                          <span style={{ color: "#4ade80" }}>Sent</span>
                        ) : (
                          <span style={{ color: "#374151" }}>—</span>
                        )}
                      </td>
                      {/* Expand toggle */}
                      <td style={{ padding: "10px 0", color: "#374151", fontSize: 16, userSelect: "none" }}>
                        {isOpen ? "▲" : "▼"}
                      </td>
                    </tr>
                    {isOpen && <ExpandedRow run={run} />}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
