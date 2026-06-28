from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProviderStatus(BaseModel):
    name: str
    mode: str
    configured: bool
    detail: str


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    picture: str | None
    role: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GoogleAuthRequest(BaseModel):
    credential: str


class AuthResponse(BaseModel):
    user: UserOut
    access_token: str | None = None
    token_type: str = "bearer"


class SystemStatus(BaseModel):
    database: ProviderStatus
    llm: ProviderStatus
    pinecone: ProviderStatus
    servicenow: ProviderStatus
    mcp: ProviderStatus
    notifications: ProviderStatus


class AgentTraceOut(BaseModel):
    id: int
    ticket_id: str
    run_id: int | None
    agent_name: str
    thought_process: str
    confidence_score: float
    generated_draft: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketOut(BaseModel):
    id: str
    source_system: str
    source_record_type: str
    short_description: str
    customer_query: str
    description: str
    category: str | None
    subcategory: str | None
    impact: str | None
    urgency: str | None
    priority: str | None
    assignment_group: str | None
    caller: str | None
    caller_email: str | None
    state: str
    status: str
    assigned_agent: str | None
    external_url: str | None
    raw_payload: str
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class CitationOut(BaseModel):
    id: int
    ticket_id: str
    run_id: int
    source: str
    title: str
    url: str | None
    snippet: str
    score: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DraftOut(BaseModel):
    id: int
    ticket_id: str
    run_id: int
    content: str
    status: str
    edited_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApprovalOut(BaseModel):
    id: int
    ticket_id: str
    run_id: int
    draft_id: int | None
    status: str
    reviewer: str | None
    notes: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationOut(BaseModel):
    id: int
    ticket_id: str
    run_id: int | None
    channel: str
    recipient: str
    subject: str
    body: str
    status: str
    provider_mode: str
    provider_response: str
    error: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketRunOut(BaseModel):
    id: int
    ticket_id: str
    status: str
    next_step: str
    confidence_score: float
    llm_mode: str
    retrieval_mode: str
    servicenow_mode: str
    mcp_status: str
    guardrail_status: str
    created_at: datetime
    completed_at: datetime | None
    traces: list[AgentTraceOut] = []
    drafts: list[DraftOut] = []
    citations: list[CitationOut] = []
    approvals: list[ApprovalOut] = []
    notifications: list[NotificationOut] = []

    model_config = ConfigDict(from_attributes=True)


class TicketDetail(TicketOut):
    traces: list[AgentTraceOut] = []
    runs: list[TicketRunOut] = []


class SyncResult(BaseModel):
    inserted: int
    updated: int
    unchanged: int
    total: int
    mode: str
    source: str


class KnowledgeSyncResult(BaseModel):
    documents: int
    upserted: int
    mode: str
    source: str


class DraftUpdate(BaseModel):
    content: str
    edited_by: str = "reviewer"


class ApprovalCreate(BaseModel):
    run_id: int
    draft_id: int | None = None
    status: str
    reviewer: str = "reviewer"
    notes: str = ""


class ChatRequest(BaseModel):
    question: str
    run_id: int | None = None


class ChatSourceOut(BaseModel):
    title: str
    source: str
    snippet: str
    score: float


class ChatResponse(BaseModel):
    ticket_id: str
    run_id: int | None
    answer: str
    retrieval_mode: str
    sources: list[ChatSourceOut]


class RunResult(BaseModel):
    ticket: TicketOut
    run: TicketRunOut
    draft: str
    next_step: str
    llm_mode: str
    retrieval_mode: str
    servicenow_mode: str
    mcp_status: str
    guardrail_status: str
