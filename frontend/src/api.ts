import type {
  AppUser,
  Approval,
  AuthResponse,
  ChatResponse,
  KnowledgeSyncResult,
  NotificationOut,
  RunResult,
  SyncResult,
  SystemStatus,
  Ticket,
  TicketDetail,
  TicketRun,
  Draft,
} from "./types/api";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
let accessToken = localStorage.getItem("agenticai_access_token");

export function setAccessToken(token: string | null) {
  accessToken = token;
  if (token) {
    localStorage.setItem("agenticai_access_token", token);
  } else {
    localStorage.removeItem("agenticai_access_token");
  }
}

export function getAccessToken() {
  return accessToken;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { ...headers, ...init?.headers },
    ...init,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<T>;
}

export const api = {
  googleAuth: (credential: string) =>
    request<AuthResponse>("/auth/google", {
      method: "POST",
      body: JSON.stringify({ credential }),
    }),
  me: () => request<AppUser>("/auth/me"),
  logout: () => request<{ status: string }>("/auth/logout", { method: "POST" }),
  adminUsers: () => request<AppUser[]>("/admin/users"),
  approveUser: (id: number) => request<AppUser>(`/admin/users/${id}/approve`, { method: "POST" }),
  disableUser: (id: number) => request<AppUser>(`/admin/users/${id}/disable`, { method: "POST" }),
  deleteUser: (id: number) => request<AppUser>(`/admin/users/${id}`, { method: "DELETE" }),
  status: () => request<SystemStatus>("/system/status"),
  tickets: () => request<Ticket[]>("/tickets"),
  ticket: (id: string) => request<TicketDetail>(`/tickets/${id}`),
  runs: (id: string) => request<TicketRun[]>(`/tickets/${id}/runs`),
  run: (id: string) => request<RunResult>(`/tickets/${id}/runs`, { method: "POST" }),
  sync: () => request<SyncResult>("/servicenow/sync", { method: "POST" }),
  syncKnowledge: () => request<KnowledgeSyncResult>("/knowledge/sync", { method: "POST" }),
  updateDraft: (id: number, content: string) =>
    request<Draft>(`/drafts/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ content }),
    }),
  approve: (runId: number, draftId: number | null, status: string, notes = "") =>
    request<Approval>("/approvals", {
      method: "POST",
      body: JSON.stringify({
        run_id: runId,
        draft_id: draftId,
        status,
        notes,
      }),
    }),
  notifications: () => request<NotificationOut[]>("/notifications"),
  chat: (ticketId: string, question: string, runId: number | null) =>
    request<ChatResponse>(`/tickets/${ticketId}/chat`, {
      method: "POST",
      body: JSON.stringify({ question, run_id: runId }),
    }),
};
