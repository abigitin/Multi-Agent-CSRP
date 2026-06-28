from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.agents.llm import generate_incident_chat_answer
from backend.agents.workflow import run_ticket_workflow
from backend.core.auth import (
    create_access_token,
    create_or_update_user,
    get_current_admin,
    get_current_user,
    verify_google_credential,
)
from backend.core.database import get_db
from backend.core.models import AppUser, Approval, Draft, NotificationOutbox, Ticket, TicketRun
from backend.core.schemas import (
    ApprovalCreate,
    ApprovalOut,
    AuthResponse,
    ChatRequest,
    ChatResponse,
    ChatSourceOut,
    DraftOut,
    DraftUpdate,
    GoogleAuthRequest,
    KnowledgeSyncResult,
    NotificationOut,
    RunResult,
    SyncResult,
    SystemStatus,
    TicketDetail,
    TicketOut,
    TicketRunOut,
    UserOut,
)
from backend.core.status import get_system_status
from backend.integrations.servicenow import ServiceNowClient, ServiceNowRecord
from backend.mcp import MCPClient
from backend.rag.knowledge_sync import sync_knowledge_base


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/google", response_model=AuthResponse)
def google_auth(payload: GoogleAuthRequest, db: Session = Depends(get_db)) -> AuthResponse:
    identity = verify_google_credential(payload.credential)
    user = create_or_update_user(db, identity)
    token = create_access_token(user) if user.status == "approved" else None
    return AuthResponse(user=user, access_token=token)


@router.get("/auth/me", response_model=UserOut)
def auth_me(user: AppUser = Depends(get_current_user)) -> AppUser:
    return user


@router.post("/auth/logout")
def auth_logout() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/admin/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
) -> list[AppUser]:
    users = list(db.scalars(select(AppUser)))
    status_rank = {"pending": 0, "approved": 1, "disabled": 2, "deleted": 3}
    users.sort(
        key=lambda user: (
            status_rank.get(user.status, 99),
            -user.created_at.timestamp(),
        )
    )
    return users


@router.post("/admin/users/{user_id}/approve", response_model=UserOut)
def approve_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
) -> AppUser:
    user = db.get(AppUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.status == "deleted":
        raise HTTPException(status_code=400, detail="Deleted users cannot be approved")
    user.status = "approved"
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


@router.post("/admin/users/{user_id}/disable", response_model=UserOut)
def disable_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
) -> AppUser:
    user = db.get(AppUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.email == admin.email:
        raise HTTPException(status_code=400, detail="Admin cannot disable own account")
    user.status = "disabled"
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


@router.delete("/admin/users/{user_id}", response_model=UserOut)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
) -> AppUser:
    user = db.get(AppUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.email == admin.email:
        raise HTTPException(status_code=400, detail="Admin cannot delete own account")
    user.status = "deleted"
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


@router.get("/system/status", response_model=SystemStatus)
def system_status(user: AppUser = Depends(get_current_user)) -> SystemStatus:
    return get_system_status()


@router.get("/tickets", response_model=list[TicketOut])
def list_tickets(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> list[Ticket]:
    return list(db.scalars(select(Ticket).order_by(Ticket.created_at.desc())))


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
def get_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> Ticket:
    ticket = db.scalar(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .options(
            selectinload(Ticket.traces),
            selectinload(Ticket.runs).selectinload(TicketRun.traces),
            selectinload(Ticket.runs).selectinload(TicketRun.drafts),
            selectinload(Ticket.runs).selectinload(TicketRun.citations),
            selectinload(Ticket.runs).selectinload(TicketRun.approvals),
            selectinload(Ticket.runs).selectinload(TicketRun.notifications),
        )
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    ticket.runs.sort(key=lambda run: run.created_at, reverse=True)
    return ticket


@router.post("/servicenow/sync", response_model=SyncResult)
def sync_servicenow(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> SyncResult:
    return _sync_servicenow_records(db)


def _sync_servicenow_records(db: Session) -> SyncResult:
    client = ServiceNowClient()
    try:
        records = client.fetch_records()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    inserted = updated = unchanged = 0
    for item in records:
        changed = _upsert_ticket(db, item)
        if changed == "inserted":
            inserted += 1
        elif changed == "updated":
            updated += 1
        else:
            unchanged += 1
    db.commit()
    return SyncResult(
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        total=inserted + updated + unchanged,
        mode=client.mode(),
        source="servicenow" if client.mode() == "live" else "mock_servicenow_json",
    )


@router.post("/mock/servicenow/sync", response_model=SyncResult)
def sync_servicenow_legacy(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> SyncResult:
    return _sync_servicenow_records(db)


@router.post("/knowledge/sync", response_model=KnowledgeSyncResult)
def sync_knowledge(user: AppUser = Depends(get_current_user)) -> dict[str, int | str]:
    try:
        return sync_knowledge_base()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/tickets/{ticket_id}/runs", response_model=RunResult)
def create_ticket_run(
    ticket_id: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> RunResult:
    return _create_ticket_run(ticket_id, db)


def _create_ticket_run(ticket_id: str, db: Session) -> RunResult:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    try:
        state, run = run_ticket_workflow(db, ticket)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    loaded_run = _load_run(db, run.id)
    return RunResult(
        ticket=ticket,
        run=loaded_run,
        draft=state["current_draft"],
        next_step=state["next_step"],
        llm_mode=state["llm_mode"],
        retrieval_mode=state["retrieval_mode"],
        servicenow_mode=state["servicenow_mode"],
        mcp_status=state["mcp_status"],
        guardrail_status=state["guardrail_status"],
    )


@router.post("/tickets/{ticket_id}/run", response_model=RunResult)
def create_ticket_run_legacy(
    ticket_id: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> RunResult:
    return _create_ticket_run(ticket_id, db)


@router.get("/tickets/{ticket_id}/runs", response_model=list[TicketRunOut])
def list_ticket_runs(
    ticket_id: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> list[TicketRun]:
    return list(
        db.scalars(
            select(TicketRun)
            .where(TicketRun.ticket_id == ticket_id)
            .options(
                selectinload(TicketRun.traces),
                selectinload(TicketRun.drafts),
                selectinload(TicketRun.citations),
                selectinload(TicketRun.approvals),
                selectinload(TicketRun.notifications),
            )
            .order_by(TicketRun.created_at.desc())
        )
    )


@router.get("/runs/{run_id}", response_model=TicketRunOut)
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> TicketRun:
    return _load_run(db, run_id)


@router.patch("/drafts/{draft_id}", response_model=DraftOut)
def update_draft(
    draft_id: int,
    payload: DraftUpdate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> Draft:
    draft = db.get(Draft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft.content = payload.content
    draft.edited_by = user.email
    draft.status = "edited"
    draft.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(draft)
    return draft


@router.post("/approvals", response_model=ApprovalOut)
def create_approval(
    payload: ApprovalCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> Approval:
    run = db.get(TicketRun, payload.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    status = payload.status.lower().strip()
    if status not in {"approved", "rejected", "changes_requested"}:
        raise HTTPException(status_code=400, detail="Invalid approval status")
    draft = _draft_for_approval(db, run, payload.draft_id)
    ticket = db.get(Ticket, run.ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if status == "approved":
        mcp = MCPClient(db)
        result = mcp.call_tool(
            "notification.send_or_queue",
            {
                "ticket_id": run.ticket_id,
                "run_id": run.id,
                "channel": "email",
                "recipient": ticket.caller_email or "",
                "cc": [user.email],
                "subject": f"Update for support ticket {run.ticket_id}",
                "body": draft.content,
            },
        )
        if result.status == "error":
            db.rollback()
            run.next_step = "human_review"
            run.guardrail_status = "reviewed"
            ticket.status = "needs_review"
            db.commit()
            raise HTTPException(
                status_code=503,
                detail=str(result.data.get("error") or "Notification failed after approval."),
            )
    approval = Approval(
        ticket_id=run.ticket_id,
        run_id=run.id,
        draft_id=draft.id,
        status=status,
        reviewer=user.email,
        notes=payload.notes,
    )
    run.next_step = "complete" if status == "approved" else "human_review"
    run.guardrail_status = "reviewed"
    draft.status = "approved" if status == "approved" else status
    draft.edited_by = user.email
    draft.updated_at = datetime.utcnow()
    ticket.status = "resolved" if status == "approved" else "needs_review"
    ticket.assigned_agent = "reviewer"
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> list[NotificationOutbox]:
    return list(
        db.scalars(select(NotificationOutbox).order_by(NotificationOutbox.created_at.desc()).limit(50))
    )


@router.post("/tickets/{ticket_id}/chat", response_model=ChatResponse)
def chat_about_ticket(
    ticket_id: str,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> ChatResponse:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    run = _select_chat_run(db, ticket_id, payload.run_id)
    mcp = MCPClient(db)
    query = " ".join(
        item
        for item in (
            ticket.customer_query,
            ticket.short_description,
            payload.question,
            run.drafts[0].content if run and run.drafts else "",
        )
        if item
    )
    result = mcp.call_tool("knowledge.search", {"query": query, "limit": 6})
    if result.status == "error":
        raise HTTPException(status_code=503, detail=str(result.data.get("error") or "Knowledge search failed."))
    sources = [
        ChatSourceOut(
            title=str(item.get("title") or item.get("source") or "Knowledge source"),
            source=str(item.get("source") or "unknown"),
            snippet=str(item.get("text") or "")[:700],
            score=float(item.get("score") or 0.0),
        )
        for item in result.data.get("documents", [])
    ]
    incident_context = _incident_chat_context(ticket, run)
    knowledge_context = [f"[{source.title}] {source.snippet}" for source in sources]
    try:
        answer = generate_incident_chat_answer(payload.question, incident_context, knowledge_context)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatResponse(
        ticket_id=ticket.id,
        run_id=run.id if run else None,
        answer=answer,
        retrieval_mode=result.mode,
        sources=sources,
    )


def _load_run(db: Session, run_id: int) -> TicketRun:
    run = db.scalar(
        select(TicketRun)
        .where(TicketRun.id == run_id)
        .options(
            selectinload(TicketRun.traces),
            selectinload(TicketRun.drafts),
            selectinload(TicketRun.citations),
            selectinload(TicketRun.approvals),
            selectinload(TicketRun.notifications),
        )
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def _draft_for_approval(db: Session, run: TicketRun, draft_id: int | None) -> Draft:
    if draft_id:
        draft = db.get(Draft, draft_id)
        if not draft or draft.run_id != run.id:
            raise HTTPException(status_code=404, detail="Draft not found for this run")
        return draft
    draft = db.scalar(select(Draft).where(Draft.run_id == run.id).order_by(Draft.updated_at.desc()))
    if not draft:
        raise HTTPException(status_code=400, detail="A generated draft is required before approval")
    return draft


def _select_chat_run(db: Session, ticket_id: str, run_id: int | None) -> TicketRun | None:
    if run_id is None:
        return None
    if run_id:
        run = db.scalar(
            select(TicketRun)
            .where(TicketRun.id == run_id, TicketRun.ticket_id == ticket_id)
            .options(
                selectinload(TicketRun.drafts),
                selectinload(TicketRun.citations),
                selectinload(TicketRun.traces),
            )
        )
        if not run:
            raise HTTPException(status_code=404, detail="Run not found for this ticket")
        return run


def _incident_chat_context(ticket: Ticket, run: TicketRun | None) -> str:
    lines = [
        f"Incident id: {ticket.id}",
        f"Short description: {ticket.short_description}",
        f"Description: {ticket.description or ticket.customer_query}",
        f"Category: {ticket.category or 'unknown'}",
        f"Priority: {ticket.priority or 'unknown'}",
        f"State: {ticket.state}",
        f"Status: {ticket.status}",
        f"Assignment group: {ticket.assignment_group or 'unknown'}",
    ]
    if run:
        lines.extend(
            [
                f"Selected run id: {run.id}",
                f"Run status: {run.status}",
                f"Guardrail status: {run.guardrail_status}",
                f"Confidence: {run.confidence_score:.2f}",
            ]
        )
        if run.drafts:
            lines.append(f"Generated or edited resolution draft:\n{run.drafts[0].content}")
        if run.citations:
            lines.append(
                "Run citations:\n"
                + "\n".join(f"- {citation.title} ({citation.source}): {citation.snippet}" for citation in run.citations[:6])
            )
    else:
        lines.append("No generated resolution run is available yet for this incident.")
    return "\n".join(lines)


def _upsert_ticket(db: Session, item: ServiceNowRecord) -> str:
    ticket = db.get(Ticket, item.sys_id)
    if ticket:
        next_customer_query = item.short_description or item.description
        next_status = ticket.status if ticket.status not in {"new", "in_progress"} else _map_servicenow_state(item.state)
        next_assigned_agent = item.assignment_group or ticket.assigned_agent
        values = {
            "source_system": item.source_system,
            "source_record_type": item.source_record_type,
            "short_description": item.short_description,
            "customer_query": next_customer_query,
            "description": item.description,
            "category": item.category,
            "subcategory": item.subcategory,
            "impact": item.impact,
            "urgency": item.urgency,
            "priority": item.priority,
            "assignment_group": item.assignment_group,
            "caller": item.caller,
            "caller_email": item.caller_email,
            "state": item.state,
            "status": next_status,
            "assigned_agent": next_assigned_agent,
            "external_url": item.external_url,
            "raw_payload": item.raw_payload,
        }
        if all(getattr(ticket, key) == value for key, value in values.items()):
            return "unchanged"
        for key, value in values.items():
            setattr(ticket, key, value)
        ticket.updated_at = datetime.utcnow()
        return "updated"
    db.add(
        Ticket(
            id=item.sys_id,
            source_system=item.source_system,
            source_record_type=item.source_record_type,
            short_description=item.short_description,
            customer_query=item.short_description or item.description,
            description=item.description,
            category=item.category,
            subcategory=item.subcategory,
            impact=item.impact,
            urgency=item.urgency,
            priority=item.priority,
            assignment_group=item.assignment_group,
            caller=item.caller,
            caller_email=item.caller_email,
            state=item.state,
            status=_map_servicenow_state(item.state),
            assigned_agent=item.assignment_group,
            external_url=item.external_url,
            raw_payload=item.raw_payload,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    return "inserted"


def _map_servicenow_state(state: str) -> str:
    normalized = state.lower().strip()
    if normalized in {"6", "7", "resolved", "closed"}:
        return "resolved"
    if normalized in {"3", "4", "5", "work in progress", "on hold"}:
        return "in_progress"
    return "new"
