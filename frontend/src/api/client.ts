import axios from "axios";

// All requests go to the FastAPI backend — never directly to Anthropic/Mem0/Langfuse.
// API keys live only in backend/.env and are never exposed to the browser.
const BASE_URL = "";

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
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
