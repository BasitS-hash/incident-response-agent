interface Step {
  key: string;
  label: string;
}

const STEPS: Step[] = [
  { key: "intake",    label: "Intake"   },
  { key: "triage",   label: "Triage"   },
  { key: "rca",      label: "RCA"      },
  { key: "approval", label: "Approval" },
  { key: "notify",   label: "Notify"   },
];

function resolveActiveStep(state: Record<string, unknown>): string {
  if (state.email_sent)                                          return "notify";
  if (state.approved !== null && state.approved !== undefined)   return "notify";
  if (state.root_cause)                                          return "approval";
  if (state.severity)                                            return "rca";
  if (state.incident_id)                                         return "triage";
  return "intake";
}

interface Props {
  state: Record<string, unknown>;
  awaitingApproval: boolean;
  finished: boolean;
}

function CheckIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 11 11" fill="none" aria-hidden="true">
      <path
        d="M1.5 5.5L4 8L9.5 2.5"
        stroke="white"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function WorkflowStepper({ state, awaitingApproval, finished }: Props) {
  const active    = resolveActiveStep(state);
  const activeIdx = finished ? STEPS.length : STEPS.findIndex((s) => s.key === active);

  return (
    <div style={{ marginBottom: "32px", position: "relative", padding: "0 4px" }}>

      {/* Track — grey background */}
      <div style={{
        position: "absolute",
        top: 13,           /* half of 28px circle */
        left: "calc(14px + 4px)",
        right: "calc(14px + 4px)",
        height: 2,
        background: "#1e293b",
        zIndex: 0,
      }} />

      {/* Track — green progress fill */}
      <div style={{
        position: "absolute",
        top: 13,
        left: "calc(14px + 4px)",
        width: activeIdx > 0
          ? `calc(${(activeIdx / (STEPS.length - 1)) * 100}% - 28px)`
          : 0,
        height: 2,
        background: "#22c55e",
        zIndex: 0,
        transition: "width 0.5s ease",
      }} />

      {/* Step circles + labels */}
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        position: "relative",
        zIndex: 1,
      }}>
        {STEPS.map((step, idx) => {
          const done    = idx < activeIdx;
          const current = idx === activeIdx;
          const waiting = step.key === "approval" && awaitingApproval;

          const bg     = done ? "#22c55e" : current ? "#3b82f6" : "#0f172a";
          const border  = done ? "#22c55e" : current ? "#3b82f6" : "#334155";
          const lblClr  = done ? "#4ade80" : current ? "#f9fafb" : "#475569";

          return (
            <div
              key={step.key}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 8,
              }}
            >
              {/* Circle */}
              <div
                className={current ? "step-pulse" : undefined}
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: "50%",
                  background: bg,
                  border: `2px solid ${border}`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transition: "background 0.4s, border-color 0.4s",
                }}
              >
                {done && <CheckIcon />}
                {current && !waiting && (
                  <div style={{ width: 8, height: 8, borderRadius: "50%", background: "white" }} />
                )}
                {waiting && (
                  <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#fbbf24" }} />
                )}
              </div>

              {/* Label */}
              <span style={{
                fontSize: 11,
                color: lblClr,
                fontWeight: current ? 600 : 400,
                whiteSpace: "nowrap",
                transition: "color 0.3s",
              }}>
                {waiting ? "Awaiting..." : step.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
