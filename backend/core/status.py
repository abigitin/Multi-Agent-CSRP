from backend.core.config import get_settings
from backend.core.schemas import ProviderStatus, SystemStatus
from backend.integrations.mail import MailClient


def get_system_status() -> SystemStatus:
    settings = get_settings()
    database_mode = "sqlite" if settings.database_url.startswith("sqlite") else "external"
    servicenow_ready = settings.servicenow_ready
    mail = MailClient()
    return SystemStatus(
        database=ProviderStatus(
            name="database",
            mode=database_mode,
            configured=True,
            detail="SQLite active; SQL Server migration target remains schema-compatible.",
        ),
        llm=ProviderStatus(
            name="llm",
            mode="live" if settings.groq_api_key else "disabled",
            configured=bool(settings.groq_api_key),
            detail=(
                f"{settings.llm_provider} model {settings.groq_model}"
                if settings.groq_api_key
                else "No Groq-compatible API key configured; deterministic draft fallback is used."
            ),
        ),
        pinecone=ProviderStatus(
            name="pinecone",
            mode="live" if settings.pinecone_api_key else "disabled",
            configured=bool(settings.pinecone_api_key),
            detail=(
                f"Index {settings.pinecone_index} namespace {settings.pinecone_namespace}"
                if settings.pinecone_api_key
                else "No Pinecone key configured; local retrieval is used."
            ),
        ),
        servicenow=ProviderStatus(
            name="servicenow",
            mode="live" if servicenow_ready else "dev_mock" if settings.allow_dev_mocks else "error",
            configured=servicenow_ready,
            detail=(
                f"Live table {settings.servicenow_table}"
                if servicenow_ready
                else "Credentials missing; dev mock ServiceNow JSON is the active source."
            ),
        ),
        mcp=ProviderStatus(
            name="mcp",
            mode=settings.mcp_mode,
            configured=settings.mcp_mode in {"in-process", "http"},
            detail=(
                f"HTTP MCP endpoint {settings.mcp_base_url}"
                if settings.mcp_mode == "http"
                else "MCP tool surface is available in-process for backend orchestration."
            ),
        ),
        notifications=ProviderStatus(
            name="notifications",
            mode=mail.mode(),
            configured=settings.notification_mode == "mock_outbox" or settings.smtp_ready,
            detail=(
                f"SMTP email from {settings.mail_from}"
                if settings.notification_mode == "smtp" and settings.smtp_ready
                else "Notifications are persisted to local dev outbox; no real email is sent."
            ),
        ),
    )
