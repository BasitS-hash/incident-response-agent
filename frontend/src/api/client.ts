import axios from "axios";

// All requests go to the FastAPI backend — never directly to Anthropic/Mem0/Langfuse.
// API keys live only in backend/.env and are never exposed to the browser.
const BASE_URL = "";

// Optional API key — set VITE_API_KEY in frontend/.env.local to enable auth.
// If blank the backend runs in dev mode (no key required).
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: {
    "Content-Type": "application/json",
    ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
  },
});

export interface IncidentStartResponse {
  run_id: string;
  status: string;
  state: Record<string, unknown>;
}

export interface ApprovalRequest {
  approved: boolean;
  approver: string;
  notes?: string;
}

export interface ApprovalResponse {
  run_id: string;
  status: string;
  email_sent: boolean;
}

export async function startIncident(
  incident_id: string,
  recipients?: string[]
): Promise<IncidentStartResponse> {
  const { data } = await apiClient.post<IncidentStartResponse>("/incident", {
    incident_id,
    recipients,
  });
  return data;
}

export async function submitApproval(
  run_id: string,
  payload: ApprovalRequest
): Promise<ApprovalResponse> {
  const { data } = await apiClient.post<ApprovalResponse>(
    `/approve/${run_id}`,
    payload
  );
  return data;
}

export function createEventStream(run_id: string): EventSource {
  return new EventSource(`${BASE_URL}/stream/${run_id}`);
}

export async function searchIncidents(q: string) {
  const { data } = await apiClient.get("/incidents/search", { params: { q } });
  return data.results as Array<{ memory: string }>;
}

export interface RunRecord {
  run_id: string;
  incident_id: string;
  started_at: string;
  completed_at: string | null;
  status: "running" | "awaiting_approval" | "completed" | "rejected";
  severity: string | null;
  affected_systems: string[];
  triage_notes: string | null;
  root_cause: string | null;
  rca_summary: string | null;
  recommended_fix: string | null;
  approved: 0 | 1 | null;
  approver: string | null;
  approval_notes: string | null;
  email_sent: 0 | 1;
}

export async function getRuns(limit = 100): Promise<RunRecord[]> {
  const { data } = await apiClient.get<{ runs: RunRecord[]; total: number }>(
    "/runs",
    { params: { limit } }
  );
  return Array.isArray(data?.runs) ? data.runs : [];
}

export async function getRun(run_id: string): Promise<RunRecord> {
  const { data } = await apiClient.get<RunRecord>(`/runs/${run_id}`);
  return data;
}
