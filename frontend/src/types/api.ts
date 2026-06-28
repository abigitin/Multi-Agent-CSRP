export type ProviderStatus = {
  name: string;
  mode: string;
  configured: boolean;
  detail: string;
};

export type SystemStatus = {
  database: ProviderStatus;
  llm: ProviderStatus;
  pinecone: ProviderStatus;
  servicenow: ProviderStatus;
  mcp: ProviderStatus;
  notifications: ProviderStatus;
};

export type AppUser = {
  id: number;
  email: string;
  name: string;
  picture: string | null;
  role: "admin" | "user";
  status: "pending" | "approved" | "deleted";
  created_at: string;
  updated_at: string;
};

export type AuthResponse = {
  user: AppUser;
  access_token: string | null;
  token_type: string;
};

export type Ticket = {
  id: string;
  source_system: string;
  source_record_type: string;
  short_description: string;
  customer_query: string;
  description: string;
  category: string | null;
  subcategory: string | null;
  impact: string | null;
  urgency: string | null;
  priority: string | null;
  assignment_group: string | null;
  caller: string | null;
  caller_email: string | null;
  state: string;
  status: string;
  assigned_agent: string | null;
  external_url: string | null;
  raw_payload: string;
  created_at: string;
  updated_at: string | null;
};

export type AgentTrace = {
  id: number;
  ticket_id: string;
  run_id: number | null;
  agent_name: string;
  thought_process: string;
  confidence_score: number;
  generated_draft: string;
  timestamp: string;
};

export type Draft = {
  id: number;
  ticket_id: string;
  run_id: number;
  content: string;
  status: string;
  edited_by: string | null;
  created_at: string;
  updated_at: string;
};

export type Citation = {
  id: number;
  ticket_id: string;
  run_id: number;
  source: string;
  title: string;
  url: string | null;
  snippet: string;
  score: number;
  created_at: string;
};

export type Approval = {
  id: number;
  ticket_id: string;
  run_id: number;
  draft_id: number | null;
  status: string;
  reviewer: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
};

export type NotificationOut = {
  id: number;
  ticket_id: string;
  run_id: number | null;
  channel: string;
  recipient: string;
  subject: string;
  body: string;
  status: string;
  provider_mode: string;
  provider_response: string;
  error: string;
  created_at: string;
};

export type TicketRun = {
  id: number;
  ticket_id: string;
  status: string;
  next_step: string;
  confidence_score: number;
  llm_mode: string;
  retrieval_mode: string;
  servicenow_mode: string;
  mcp_status: string;
  guardrail_status: string;
  created_at: string;
  completed_at: string | null;
  traces: AgentTrace[];
  drafts: Draft[];
  citations: Citation[];
  approvals: Approval[];
  notifications: NotificationOut[];
};

export type TicketDetail = Ticket & {
  traces: AgentTrace[];
  runs: TicketRun[];
};

export type RunResult = {
  ticket: Ticket;
  run: TicketRun;
  draft: string;
  next_step: string;
  llm_mode: string;
  retrieval_mode: string;
  servicenow_mode: string;
  mcp_status: string;
  guardrail_status: string;
};

export type SyncResult = {
  inserted: number;
  updated: number;
  unchanged: number;
  total: number;
  mode: string;
  source: string;
};

export type KnowledgeSyncResult = {
  documents: number;
  upserted: number;
  mode: string;
  source: string;
};

export type ChatSource = {
  title: string;
  source: string;
  snippet: string;
  score: number;
};

export type ChatResponse = {
  ticket_id: string;
  run_id: number | null;
  answer: string;
  retrieval_mode: string;
  sources: ChatSource[];
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};
