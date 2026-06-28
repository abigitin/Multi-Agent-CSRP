from typing import Any, Literal, TypedDict


NextStep = Literal[
    "intake",
    "retrieval",
    "resolution",
    "evaluation",
    "guardrails",
    "human_review",
    "complete",
]


class StepTrace(TypedDict):
    agent_name: str
    thought_process: str
    confidence_score: float


class Evidence(TypedDict):
    source: str
    title: str
    url: str | None
    snippet: str
    score: float


class GraphState(TypedDict):
    ticket_id: str
    run_id: int
    customer_query: str
    ticket_payload: dict[str, Any]
    context_chunks: list[str]
    evidence: list[Evidence]
    memory: list[dict[str, str]]
    steps_taken: list[StepTrace]
    current_draft: str
    next_step: NextStep
    confidence_score: float
    llm_mode: str
    retrieval_mode: str
    servicenow_mode: str
    mcp_status: str
    guardrail_status: str
    guardrail_findings: list[str]
