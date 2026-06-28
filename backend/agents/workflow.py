from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy.orm import Session

from backend.agents.llm import generate_resolution
from backend.agents.state import Evidence, GraphState, NextStep
from backend.core.config import get_settings
from backend.core.models import AgentTrace, Approval, Citation, Draft, Ticket, TicketRun
from backend.mcp import MCPClient


def build_initial_state(ticket: Ticket, run: TicketRun, mcp: MCPClient) -> GraphState:
    ticket_result = mcp.call_tool("servicenow.get_ticket", {"ticket_id": ticket.id})
    memory_result = mcp.call_tool("memory.read", {"ticket_id": ticket.id})
    return {
        "ticket_id": ticket.id,
        "run_id": run.id,
        "customer_query": ticket.customer_query,
        "ticket_payload": ticket_result.data.get("ticket") or {},
        "context_chunks": [],
        "evidence": [],
        "memory": memory_result.data.get("entries", []),
        "steps_taken": [],
        "current_draft": "",
        "next_step": "intake",
        "confidence_score": 0.0,
        "llm_mode": "live" if get_settings().groq_api_key else "disabled",
        "retrieval_mode": "local",
        "servicenow_mode": ticket_result.mode,
        "mcp_status": "ok",
        "guardrail_status": "pending",
        "guardrail_findings": [],
    }


def run_ticket_workflow(db: Session, ticket: Ticket) -> tuple[GraphState, TicketRun]:
    settings = get_settings()
    run = TicketRun(
        ticket_id=ticket.id,
        status="running",
        next_step="intake",
        llm_mode="live" if settings.groq_api_key else "disabled",
        servicenow_mode="pending",
        mcp_status=settings.mcp_mode,
    )
    db.add(run)
    db.flush()
    mcp = MCPClient(db)
    state = build_initial_state(ticket, run, mcp)
    runner = _compile_graph(mcp)
    try:
        final_state = runner.invoke(state) if hasattr(runner, "invoke") else runner(state)
    except Exception:
        run.status = "failed"
        run.next_step = "human_review"
        run.guardrail_status = "needs_review"
        run.completed_at = datetime.utcnow()
        db.commit()
        raise
    _persist_state(db, ticket, run, final_state)
    return final_state, run


def _compile_graph(mcp: MCPClient):
    try:
        from langgraph.graph import END, StateGraph

        graph = StateGraph(GraphState)
        graph.add_node("intake", _intake)
        graph.add_node("retrieval", lambda state: _retrieval(state, mcp))
        graph.add_node("resolution", _resolution)
        graph.add_node("evaluation", _evaluation)
        graph.add_node("guardrails", _guardrails)
        graph.add_node("human_review", _human_review)
        graph.set_entry_point("intake")
        graph.add_edge("intake", "retrieval")
        graph.add_edge("retrieval", "resolution")
        graph.add_edge("resolution", "evaluation")
        graph.add_edge("evaluation", "guardrails")
        graph.add_edge("guardrails", "human_review")
        graph.add_edge("human_review", END)
        return graph.compile()
    except Exception:
        return lambda state: _run_without_langgraph(state, mcp)


def _run_without_langgraph(state: GraphState, mcp: MCPClient) -> GraphState:
    for node in (
        _intake,
        lambda item: _retrieval(item, mcp),
        _resolution,
        _evaluation,
        _guardrails,
    ):
        state = node(state)
    return _human_review(state)


def _intake(state: GraphState) -> GraphState:
    payload = state["ticket_payload"]
    issue_type = payload.get("category") or _classify_issue(state["customer_query"])
    thought = (
        f"Normalized ticket {state['ticket_id']} as {issue_type}; "
        f"ServiceNow mode is {state['servicenow_mode']}."
    )
    return _append_step({**state, "next_step": "retrieval"}, "intake_agent", thought, 0.86)


def _retrieval(state: GraphState, mcp: MCPClient) -> GraphState:
    result = mcp.call_tool("knowledge.search", {"query": state["customer_query"], "limit": 8})
    if result.status == "error" and get_settings().is_production:
        raise RuntimeError(str(result.data.get("error") or "Knowledge retrieval failed."))
    documents = result.data.get("documents", [])
    evidence: list[Evidence] = [
        {
            "source": str(doc.get("source") or "unknown"),
            "title": str(doc.get("title") or doc.get("source") or "Knowledge source"),
            "url": doc.get("url"),
            "snippet": str(doc.get("text") or "")[:700],
            "score": float(doc.get("score") or 0.0),
        }
        for doc in documents
    ]
    chunks = [f"[{item['title']}] {item['snippet']}" for item in evidence]
    confidence = 0.82 if chunks else 0.35
    return _append_step(
        {
            **state,
            "context_chunks": chunks,
            "evidence": evidence,
            "retrieval_mode": result.mode,
            "next_step": "resolution",
        },
        "retrieval_agent",
        f"Retrieved {len(chunks)} evidence chunks via MCP knowledge.search in {result.mode} mode.",
        confidence,
    )


def _resolution(state: GraphState) -> GraphState:
    draft = generate_resolution(state["customer_query"], state["context_chunks"])
    draft = _clean_draft_text(draft)
    if state["evidence"]:
        draft = f"{draft}\n\nSources:\n" + "\n".join(
            f"Source {index}: {item['title']} ({item['source']})"
            for index, item in enumerate(state["evidence"][:8], start=1)
        )
    draft = _clean_draft_text(draft)
    return _append_step(
        {**state, "current_draft": draft, "next_step": "evaluation"},
        "resolution_agent",
        f"Generated a customer-ready draft using {state['llm_mode']} LLM mode.",
        0.8 if state["context_chunks"] else 0.55,
    )


def _evaluation(state: GraphState) -> GraphState:
    has_citations = bool(state["evidence"])
    draft_len = len(state["current_draft"].strip())
    confidence = 0.45
    if draft_len > 120:
        confidence += 0.2
    if has_citations:
        confidence += 0.25
    if state["llm_mode"] == "live":
        confidence += 0.05
    confidence = min(confidence, 0.95)
    return _append_step(
        {**state, "confidence_score": confidence, "next_step": "guardrails"},
        "evaluation_agent",
        f"Evaluated draft confidence at {confidence:.2f}; citations present={has_citations}.",
        confidence,
    )


def _guardrails(state: GraphState) -> GraphState:
    findings: list[str] = list(state["guardrail_findings"])
    if not state["evidence"]:
        findings.append("No citations found for the generated response.")
    if _contains_pii(state["current_draft"]):
        findings.append("Potential PII detected in draft.")
    if "Sources:" not in state["current_draft"]:
        findings.append("Draft does not include explicit source references.")
    if len(state["current_draft"].strip()) < 80:
        findings.append("Draft is too short for customer-ready communication.")
    passed = not findings and state["confidence_score"] >= get_settings().auto_approval_threshold
    next_step: NextStep = "human_review"
    status = "ready_for_review" if passed else "needs_review"
    thought = (
        "Guardrails passed; queued for human review before customer delivery."
        if passed
        else "Guardrails require review: " + "; ".join(findings)
    )
    return _append_step(
        {
            **state,
            "guardrail_status": status,
            "guardrail_findings": findings,
            "next_step": next_step,
        },
        "guardrail_agent",
        thought,
        0.92 if passed else 0.55,
    )


def _human_review(state: GraphState) -> GraphState:
    return _append_step(
        {**state, "next_step": "human_review"},
        "approval_agent",
        "Queued for human review because confidence or guardrail status did not meet automation policy.",
        0.66,
    )


def _append_step(
    state: GraphState, agent_name: str, thought_process: str, confidence_score: float
) -> GraphState:
    return {
        **state,
        "steps_taken": [
            *state["steps_taken"],
            {
                "agent_name": agent_name,
                "thought_process": thought_process,
                "confidence_score": confidence_score,
            },
        ],
    }


def _persist_state(db: Session, ticket: Ticket, run: TicketRun, state: GraphState) -> None:
    run.status = "completed"
    run.next_step = state["next_step"]
    run.confidence_score = state["confidence_score"]
    run.llm_mode = state["llm_mode"]
    run.retrieval_mode = state["retrieval_mode"]
    run.servicenow_mode = state["servicenow_mode"]
    run.mcp_status = state["mcp_status"]
    run.guardrail_status = state["guardrail_status"]
    run.completed_at = datetime.utcnow()
    ticket.status = "needs_review"
    ticket.assigned_agent = state["next_step"]

    for step in state["steps_taken"]:
        db.add(
            AgentTrace(
                ticket_id=ticket.id,
                run_id=run.id,
                agent_name=step["agent_name"],
                thought_process=step["thought_process"],
                confidence_score=step["confidence_score"],
                generated_draft=state["current_draft"],
            )
        )

    draft = Draft(
        ticket_id=ticket.id,
        run_id=run.id,
        content=state["current_draft"],
        status="needs_review",
    )
    db.add(draft)
    db.flush()

    for item in state["evidence"]:
        db.add(
            Citation(
                ticket_id=ticket.id,
                run_id=run.id,
                source=item["source"],
                title=item["title"],
                url=item["url"],
                snippet=item["snippet"],
                score=item["score"],
            )
        )

    db.add(
        Approval(
            ticket_id=ticket.id,
            run_id=run.id,
            draft_id=draft.id,
            status="pending",
            reviewer=None,
            notes="; ".join(state["guardrail_findings"]),
        )
    )
    db.commit()
    db.refresh(ticket)
    db.refresh(run)


def _classify_issue(query: str) -> str:
    lowered = query.lower()
    if "vpn" in lowered:
        return "Network Access"
    if "mail" in lowered or "email" in lowered:
        return "Messaging"
    if "billing" in lowered:
        return "Billing Operations"
    if "printer" in lowered:
        return "End User Computing"
    return "General Support"


def _contains_pii(text: str) -> bool:
    return bool(re.search(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{16}\b", text))


def _clean_draft_text(text: str) -> str:
    cleaned = text.replace("**", "")
    cleaned = re.sub(r"(?m)^\s*[-*]\s+", "", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
