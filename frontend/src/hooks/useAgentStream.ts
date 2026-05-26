import { useEffect, useRef, useState } from "react";
import { createEventStream } from "../api/client";

export type AgentEvent =
  | { type: "RUN_STARTED"; run_id: string }
  | { type: "STATE_SNAPSHOT"; state: Record<string, unknown> }
  | { type: "AWAITING_APPROVAL"; run_id: string; rca_summary: string; severity: string; root_cause: string; recommended_fix: string }
  | { type: "RUN_FINISHED"; run_id: string }
  | { type: "RUN_ERROR"; message: string };

export function useAgentStream(run_id: string | null) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [state, setState] = useState<Record<string, unknown>>({});
  const [awaitingApproval, setAwaitingApproval] = useState(false);
  const [approvalData, setApprovalData] = useState<AgentEvent | null>(null);
  const [finished, setFinished] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!run_id) {
      // Clear everything when the run is reset so stale modal state doesn't leak
      setEvents([]);
      setState({});
      setAwaitingApproval(false);
      setApprovalData(null);
      setFinished(false);
      setStreamError(null);
      return;
    }

    // Reset all state for the new run
    setEvents([]);
    setState({});
    setAwaitingApproval(false);
    setApprovalData(null);
    setFinished(false);
    setStreamError(null);

    const es = createEventStream(run_id);
    esRef.current = es;

    es.onmessage = (e) => {
      const event: AgentEvent = JSON.parse(e.data);
      setEvents((prev) => [...prev, event]);

      if (event.type === "STATE_SNAPSHOT") {
        setState(event.state);
      }
      if (event.type === "AWAITING_APPROVAL") {
        setAwaitingApproval(true);
        setApprovalData(event);
      }
      if (event.type === "RUN_FINISHED" || event.type === "RUN_ERROR") {
        setFinished(true);
        es.close();
      }
    };

    es.onerror = () => {
      setStreamError("Lost connection to workflow stream. Refresh to retry.");
      es.close();
    };

    return () => es.close();
  }, [run_id]);

  return { events, state, awaitingApproval, approvalData, finished, streamError };
}
