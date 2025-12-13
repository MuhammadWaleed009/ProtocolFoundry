// cbt-frontend/src/lib/api.ts
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export type SessionMode = "human_optional" | "human_required" | "auto";

export type CreateSessionResponse = { thread_id: string };

export type RunRequest = {
  input_text: string;
  require_human_approval?: boolean;
};

export type RunResult =
  | { run_id: string; status: "COMPLETED" }
  | { run_id: string; status: "HALTED"; interrupts: any[] }
  | { run_id: string; status: "FAILED"; error?: string };

export type RunRecord = {
  run_id: string;
  thread_id: string;
  created_at: string;
  updated_at: string;
  status: "RUNNING" | "HALTED" | "COMPLETED" | "FAILED";
  require_human_approval: boolean;
  input_text: string;
  final_markdown?: string | null;
  final_data?: any;
  reviews?: any;
  supervisor?: any;
  human_edit?: any;
  pending_interrupt?: any;
  error?: string | null;
};

export type PendingApprovalResponse = {
  thread_id: string;
  pending: RunRecord | null;
};

export type LatestRunResponse = {
  thread_id: string;
  latest: RunRecord | null;
};

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${text ? ` - ${text}` : ""}`);
  }

  return (await res.json()) as T;
}

export function createSession(mode: SessionMode = "human_optional") {
  return http<CreateSessionResponse>(`/sessions`, {
    method: "POST",
    body: JSON.stringify({ mode }),
  });
}

export function runSession(thread_id: string, body: RunRequest) {
  return http<{ thread_id: string; require_human_approval: boolean; result: RunResult }>(
    `/sessions/${thread_id}/run`,
    { method: "POST", body: JSON.stringify(body) }
  );
}

export function pendingApproval(thread_id: string) {
  return http<PendingApprovalResponse>(`/sessions/${thread_id}/pending-approval`);
}

export function latestRun(thread_id: string) {
  return http<LatestRunResponse>(`/sessions/${thread_id}/latest-run`);
}

export function approve(
  thread_id: string,
  body: { approved: boolean; edited_text?: string | null; feedback?: string | null }
) {
  return http<{ thread_id: string; result: any }>(`/sessions/${thread_id}/approve`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
