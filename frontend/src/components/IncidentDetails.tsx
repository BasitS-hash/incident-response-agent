interface Props {
  state: Record<string, unknown>;
  loading: boolean;
}

const FIELDS = [
  { label: "Incident ID",      key: "incident_id"      },
  { label: "Title",            key: "title"             },
  { label: "Severity",         key: "severity"          },
  { label: "Affected Systems", key: "affected_systems"  },
  { label: "Root Cause",       key: "root_cause"        },
  { label: "Recommended Fix",  key: "recommended_fix"   },
  { label: "Email Sent",       key: "email_sent"        },
];

function SkeletonRow({ width = 120 }: { width?: number }) {
  return (
    <tr>
      <td style={{ padding: "10px 16px 10px 0", whiteSpace: "nowrap" }}>
        <div className="skeleton" style={{ width: 72, height: 11 }} />
      </td>
      <td style={{ padding: "10px 0" }}>
        <div className="skeleton" style={{ width, height: 11 }} />
      </td>
    </tr>
  );
}

function SeverityBadge({ value }: { value: string }) {
  const colours: Record<string, { bg: string; text: string }> = {
    P1: { bg: "#450a0a", text: "#fca5a5" },
    P2: { bg: "#431407", text: "#fdba74" },
    P3: { bg: "#422006", text: "#fcd34d" },
    P4: { bg: "#052e16", text: "#86efac" },
  };
  const c = colours[value] ?? { bg: "#1e293b", text: "#94a3b8" };
  return (
    <span style={{
      background: c.bg,
      color: c.text,
      padding: "2px 8px",
      borderRadius: 9999,
      fontSize: 12,
      fontWeight: 600,
    }}>
      {value}
    </span>
  );
}

export default function IncidentDetails({ state, loading }: Props) {
  /* ── Loading skeleton ─────────────────────────────────── */
  if (loading) {
    return (
      <div style={{ background: "#0a1628", borderRadius: 10, padding: "16px" }}>
        <div className="skeleton" style={{ width: 100, height: 13, marginBottom: 16 }} />
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <tbody>
            <SkeletonRow width={80}  />
            <SkeletonRow width={200} />
            <SkeletonRow width={40}  />
            <SkeletonRow width={220} />
          </tbody>
        </table>
      </div>
    );
  }

  /* ── Empty ────────────────────────────────────────────── */
  if (!state.incident_id) return null;

  /* ── Populated ────────────────────────────────────────── */
  return (
    <div style={{ background: "#0a1628", borderRadius: 10, padding: "16px" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <tbody>
          {FIELDS.map(({ label, key }) => {
            const val = state[key];
            if (val === undefined || val === null || val === "" || val === false) return null;

            const displayRaw = Array.isArray(val) ? val.join(", ") : String(val);
            const display =
              key === "severity" ? (
                <SeverityBadge value={displayRaw} />
              ) : key === "email_sent" ? (
                <span style={{ color: "#4ade80" }}>
                  Sent
                </span>
              ) : (
                displayRaw
              );

            return (
              <tr key={key} style={{ borderBottom: "1px solid #0f172a" }}>
                <td style={{
                  color: "#475569",
                  padding: "9px 16px 9px 0",
                  whiteSpace: "nowrap",
                  verticalAlign: "top",
                  fontSize: 12,
                }}>
                  {label}
                </td>
                <td style={{
                  color: "#e2e8f0",
                  padding: "9px 0",
                  lineHeight: 1.55,
                }}>
                  {display}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
