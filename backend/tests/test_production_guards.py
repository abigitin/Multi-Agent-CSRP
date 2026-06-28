import pytest

from backend.agents import llm
from backend.agents.workflow import _run_without_langgraph
from backend.core.config import Settings
from backend.core.auth import create_access_token
from backend.core.models import AppUser, Draft, Ticket, TicketRun
from backend.integrations.mail import MailClient
from backend.integrations.servicenow import ServiceNowClient


def test_production_requires_live_configuration() -> None:
    settings = Settings(
        app_env="production",
        database_url="",
        google_client_id=None,
        app_jwt_secret="change-me-local-dev-secret",
    )

    with pytest.raises(RuntimeError) as exc:
        settings.validate_production()

    message = str(exc.value)
    assert "DATABASE_URL" in message
    assert "GOOGLE_CLIENT_ID" in message
    assert "APP_JWT_SECRET" in message


def test_development_allows_service_now_mock() -> None:
    settings = Settings(app_env="development")
    client = ServiceNowClient()
    client.settings = settings

    assert client.mode() == "dev_mock"


def test_smtp_mode_requires_real_recipient(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        app_env="development",
        notification_mode="smtp",
        mail_from="imabir605@gmail.com",
        smtp_username="imabir605@gmail.com",
        smtp_password="secret",
    )
    client = MailClient()
    client.settings = settings

    result = client.send("", "subject", "body")

    assert result.status == "failed"
    assert "valid customer email" in result.error


def test_pinecone_defaults_match_integrated_embedding_index() -> None:
    settings = Settings()

    assert settings.pinecone_index == "customer-support"
    assert settings.pinecone_namespace == "__default__"
    assert settings.pinecone_embed_field == "text"
    assert settings.pinecone_integrated_embedding is True


def test_workflow_does_not_send_notification_before_human_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict]] = []

    class FakeMCP:
        def call_tool(self, tool_name: str, payload: dict) -> object:
            calls.append((tool_name, payload))
            if tool_name == "knowledge.search":
                return type(
                    "Result",
                    (),
                    {
                        "status": "ok",
                        "mode": "local",
                        "data": {
                            "documents": [
                                {
                                    "source": "runbook.md",
                                    "title": "Runbook",
                                    "text": "Apply the approved runbook and validate service recovery.",
                                    "score": 0.91,
                                }
                            ]
                        },
                    },
                )()
            return type("Result", (), {"status": "ok", "mode": "sqlite", "data": {}})()

    monkeypatch.setattr("backend.agents.workflow.generate_resolution", lambda query, chunks: "Use the cited runbook to resolve the incident.")
    monkeypatch.setattr("backend.agents.workflow.get_settings", lambda: Settings(groq_api_key=None))
    state = {
        "ticket_id": "INC1",
        "run_id": 1,
        "customer_query": "VPN dashboard timeout",
        "ticket_payload": {"caller_email": "customer@example.com"},
        "context_chunks": [],
        "evidence": [],
        "memory": [],
        "steps_taken": [],
        "current_draft": "",
        "next_step": "intake",
        "confidence_score": 0.0,
        "llm_mode": "disabled",
        "retrieval_mode": "local",
        "servicenow_mode": "dev_mock",
        "mcp_status": "ok",
        "guardrail_status": "pending",
        "guardrail_findings": [],
    }

    final_state = _run_without_langgraph(state, FakeMCP())

    assert final_state["next_step"] == "human_review"
    assert not any(tool_name.startswith("notification.") for tool_name, _ in calls)


def test_configured_groq_key_raises_instead_of_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenChat:
        def __init__(self, **kwargs: object) -> None:
            pass

        def invoke(self, messages: list[tuple[str, str]]) -> object:
            raise RuntimeError("bad api key")

    monkeypatch.setattr(llm, "get_settings", lambda: Settings(groq_api_key="wrong"))
    monkeypatch.setitem(__import__("sys").modules, "langchain_openai", type("Module", (), {"ChatOpenAI": BrokenChat})())

    with pytest.raises(RuntimeError, match="Groq-compatible LLM request failed"):
        llm.generate_resolution("issue", ["context"])


def test_approval_sends_notification_after_human_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.api import routes

    calls: list[tuple[str, dict]] = []

    class FakeDB:
        def __init__(self) -> None:
            self.ticket = Ticket(
                id="INC1",
                customer_query="VPN issue",
                short_description="VPN issue",
                description="VPN issue",
                state="2",
                status="needs_review",
                caller_email="customer@example.com",
            )
            self.run = TicketRun(id=10, ticket_id="INC1", status="completed", next_step="human_review")
            self.draft = Draft(id=20, ticket_id="INC1", run_id=10, content="Approved response")
            self.added: list[object] = []

        def get(self, model: type, identity: object) -> object | None:
            if model is TicketRun and identity == 10:
                return self.run
            if model is Ticket and identity == "INC1":
                return self.ticket
            if model is Draft and identity == 20:
                return self.draft
            return None

        def add(self, item: object) -> None:
            self.added.append(item)

        def commit(self) -> None:
            pass

        def refresh(self, item: object) -> None:
            pass

    class FakeMCPClient:
        def __init__(self, db: object) -> None:
            pass

        def call_tool(self, tool_name: str, payload: dict) -> object:
            calls.append((tool_name, payload))
            return type("Result", (), {"status": "ok", "mode": "mock_outbox", "data": {"status": "queued"}})()

    db = FakeDB()
    monkeypatch.setattr(routes, "MCPClient", FakeMCPClient)
    approved_user = AppUser(
        id=1,
        google_sub="sub",
        email="approved@example.com",
        name="Approved",
        role="user",
        status="approved",
    )

    approval = routes.create_approval(
        routes.ApprovalCreate(run_id=10, draft_id=20, status="approved", reviewer="reviewer"),
        db,
        approved_user,
    )

    assert approval.status == "approved"
    assert db.ticket.status == "resolved"
    assert calls == [
        (
            "notification.send_or_queue",
            {
                "ticket_id": "INC1",
                "run_id": 10,
                "channel": "email",
                "recipient": "customer@example.com",
                "cc": ["approved@example.com"],
                "subject": "Update for support ticket INC1",
                "body": "Approved response",
            },
        )
    ]


def test_access_token_rechecks_deleted_user_status(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException
    from backend.core import auth

    approved_user = AppUser(
        id=5,
        google_sub="sub",
        email="approved@example.com",
        name="Approved",
        role="user",
        status="approved",
    )
    deleted_user = AppUser(
        id=5,
        google_sub="sub",
        email="approved@example.com",
        name="Approved",
        role="user",
        status="deleted",
    )
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(app_jwt_secret="test-secret"))
    token = create_access_token(approved_user)

    class Request:
        headers = {"Authorization": f"Bearer {token}"}

    class DB:
        def get(self, model: type, identity: int) -> AppUser:
            return deleted_user

    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(Request(), DB())

    assert exc.value.status_code == 403


def test_disabled_user_cannot_access_with_existing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException
    from backend.core import auth

    approved_user = AppUser(
        id=5,
        google_sub="sub",
        email="approved@example.com",
        name="Approved",
        role="user",
        status="approved",
    )
    disabled_user = AppUser(
        id=5,
        google_sub="sub",
        email="approved@example.com",
        name="Approved",
        role="user",
        status="disabled",
    )
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(app_jwt_secret="test-secret"))
    token = create_access_token(approved_user)

    class Request:
        headers = {"Authorization": f"Bearer {token}"}

    class DB:
        def get(self, model: type, identity: int) -> AppUser:
            return disabled_user

    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(Request(), DB())

    assert exc.value.status_code == 403


def test_admin_can_approve_pending_user() -> None:
    from backend.api import routes

    pending_user = AppUser(
        id=2,
        google_sub="pending-sub",
        email="pending@example.com",
        name="Pending",
        role="user",
        status="pending",
    )
    admin_user = AppUser(
        id=1,
        google_sub="admin-sub",
        email="abir27534@gmail.com",
        name="Admin",
        role="admin",
        status="approved",
    )

    class DB:
        def get(self, model: type, identity: int) -> AppUser:
            return pending_user

        def commit(self) -> None:
            pass

        def refresh(self, item: object) -> None:
            pass

    result = routes.approve_user(2, DB(), admin_user)

    assert result.status == "approved"


def test_admin_can_disable_approved_user() -> None:
    from backend.api import routes

    approved_user = AppUser(
        id=2,
        google_sub="approved-sub",
        email="approved@example.com",
        name="Approved",
        role="user",
        status="approved",
    )
    admin_user = AppUser(
        id=1,
        google_sub="admin-sub",
        email="abir27534@gmail.com",
        name="Admin",
        role="admin",
        status="approved",
    )

    class DB:
        def get(self, model: type, identity: int) -> AppUser:
            return approved_user

        def commit(self) -> None:
            pass

        def refresh(self, item: object) -> None:
            pass

    result = routes.disable_user(2, DB(), admin_user)

    assert result.status == "disabled"
