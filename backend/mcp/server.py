from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.models import KnowledgeDocument, MemoryEntry, NotificationOutbox, Ticket
from backend.integrations.mail import MailClient
from backend.integrations.servicenow import ServiceNowClient
from backend.rag.confluence_loader import load_documents
from backend.rag.embeddings import embed_text
from backend.rag.pinecone_store import search as pinecone_search
from backend.rag.retriever import _cosine_similarity


@dataclass
class ToolResult:
    status: str
    mode: str
    data: dict[str, Any]


class MCPToolServer:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def call(self, tool_name: str, payload: dict[str, Any]) -> ToolResult:
        tools = {
            "servicenow.search_tickets": self.search_servicenow_tickets,
            "servicenow.get_ticket": self.get_servicenow_ticket,
            "knowledge.search": self.search_knowledge,
            "memory.read": self.read_memory,
            "memory.write": self.write_memory,
            "notification.queue": self.queue_notification,
            "notification.send_or_queue": self.queue_notification,
        }
        if tool_name not in tools:
            return ToolResult("error", "disabled", {"error": f"Unknown MCP tool {tool_name}"})
        return tools[tool_name](payload)

    def search_servicenow_tickets(self, payload: dict[str, Any]) -> ToolResult:
        mode = ServiceNowClient().mode()
        query = str(payload.get("query") or "").lower()
        tickets = list(self.db.scalars(select(Ticket).order_by(Ticket.created_at.desc())))
        rows = [
            _ticket_payload(ticket)
            for ticket in tickets
            if not query
            or query in ticket.customer_query.lower()
            or query in ticket.description.lower()
            or query in ticket.short_description.lower()
        ][: int(payload.get("limit") or 5)]
        return ToolResult("ok", mode, {"tickets": rows})

    def get_servicenow_ticket(self, payload: dict[str, Any]) -> ToolResult:
        mode = ServiceNowClient().mode()
        ticket = self.db.get(Ticket, str(payload.get("ticket_id") or ""))
        if not ticket:
            return ToolResult("not_found", mode, {"ticket": None})
        return ToolResult("ok", mode, {"ticket": _ticket_payload(ticket)})

    def search_knowledge(self, payload: dict[str, Any]) -> ToolResult:
        query = str(payload.get("query") or "")
        limit = int(payload.get("limit") or 4)
        if self.settings.pinecone_api_key:
            try:
                ranked = _pinecone_search(query, limit)
            except Exception as exc:
                return ToolResult("error", "pinecone", {"documents": [], "error": str(exc)})
            if ranked:
                return ToolResult("ok", "pinecone", {"documents": ranked[:limit]})
            if self.settings.is_production:
                return ToolResult("error", "pinecone", {"documents": [], "error": "Pinecone search returned no usable matches."})
        mode = "local" if not self.settings.is_production else "error"
        docs = _knowledge_documents(self.db)
        if not docs and self.settings.allow_dev_mocks:
            docs = _mock_documents()
        ranked = _rank_documents(query, docs)
        return ToolResult("ok", mode, {"documents": ranked[:limit]})

    def read_memory(self, payload: dict[str, Any]) -> ToolResult:
        ticket_id = payload.get("ticket_id")
        rows = list(
            self.db.scalars(
                select(MemoryEntry)
                .where(MemoryEntry.ticket_id == ticket_id if ticket_id else MemoryEntry.scope == "global")
                .order_by(MemoryEntry.created_at.desc())
            )
        )
        return ToolResult(
            "ok",
            "sqlite",
            {"entries": [{"key": row.key, "value": row.value, "scope": row.scope} for row in rows]},
        )

    def write_memory(self, payload: dict[str, Any]) -> ToolResult:
        entry = MemoryEntry(
            ticket_id=payload.get("ticket_id"),
            key=str(payload.get("key") or "note"),
            value=str(payload.get("value") or ""),
            scope=str(payload.get("scope") or "ticket"),
        )
        self.db.add(entry)
        self.db.flush()
        return ToolResult("ok", "sqlite", {"id": entry.id})

    def queue_notification(self, payload: dict[str, Any]) -> ToolResult:
        mail = MailClient()
        recipient = str(payload.get("recipient") or "")
        subject = str(payload.get("subject") or "Support ticket update")
        body = str(payload.get("body") or "")
        try:
            send_result = mail.send(recipient, subject, body)
        except RuntimeError as exc:
            send_result = None
            status = "failed"
            provider_mode = mail.mode()
            error = str(exc)
        else:
            status = send_result.status
            provider_mode = send_result.provider_mode
            error = send_result.error
        item = NotificationOutbox(
            ticket_id=str(payload["ticket_id"]),
            run_id=payload.get("run_id"),
            channel=str(payload.get("channel") or "email"),
            recipient=recipient,
            subject=subject,
            body=body,
            status=status,
            provider_mode=provider_mode,
            provider_response=send_result.response if send_result else "",
            error=error,
        )
        self.db.add(item)
        self.db.flush()
        return ToolResult("ok" if status in {"sent", "queued"} else "error", provider_mode, {"notification_id": item.id, "status": status, "error": error})


def _ticket_payload(ticket: Ticket) -> dict[str, Any]:
    return {
        "id": ticket.id,
        "short_description": ticket.short_description,
        "customer_query": ticket.customer_query,
        "description": ticket.description,
        "status": ticket.status,
        "priority": ticket.priority,
        "category": ticket.category,
        "caller": ticket.caller,
        "caller_email": ticket.caller_email,
    }


def _knowledge_documents(db: Session) -> list[dict[str, Any]]:
    rows = list(db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.updated_at.desc())))
    return [
        {
            "source": row.source,
            "title": row.title,
            "url": row.url,
            "text": row.text,
            "metadata": json.loads(row.metadata_json or "{}"),
        }
        for row in rows
    ]


def _mock_documents() -> list[dict[str, Any]]:
    return [
        {
            "source": doc["source"],
            "title": doc["source"],
            "url": None,
            "text": doc["text"],
            "metadata": {"mode": "mock"},
        }
        for doc in load_documents(get_settings().confluence_dir)
    ]


def _rank_documents(query: str, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    query_vector = embed_text(query)
    ranked: list[dict[str, Any]] = []
    for doc in docs:
        text = str(doc.get("text") or "")
        doc_tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
        lexical = len(query_tokens & doc_tokens) / max(len(query_tokens), 1)
        semantic = _cosine_similarity(query_vector, embed_text(text))
        score = (lexical * 0.45) + (semantic * 0.55)
        if score <= 0:
            continue
        ranked.append({**doc, "score": round(float(score), 4), "updated_at": datetime.utcnow().isoformat()})
    return sorted(ranked, key=lambda row: row["score"], reverse=True)


def _pinecone_search(query: str, limit: int) -> list[dict[str, Any]]:
    settings = get_settings()
    try:
        results = pinecone_search(query, limit)
    except Exception:
        if settings.is_production:
            raise
        return []
    return [
        {
            "source": doc.source,
            "title": doc.title,
            "url": doc.url,
            "text": doc.text,
            "metadata": doc.metadata,
            "score": doc.score,
            "updated_at": doc.updated_at,
        }
        for doc in results
        if doc.text
    ]
