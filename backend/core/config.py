from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./dev.db"
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    llm_provider: str = "groq-compatible"
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-120b"

    pinecone_api_key: str | None = None
    pinecone_index: str = "customer-support"
    pinecone_namespace: str = "__default__"
    pinecone_host: str | None = None
    pinecone_embed_field: str = "text"
    pinecone_integrated_embedding: bool = True

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    servicenow_instance_url: str | None = None
    servicenow_user: str | None = None
    servicenow_password: str | None = None
    servicenow_table: str = "incident"
    confluence_dir: Path = ROOT_DIR / "mock_data" / "confluence"
    servicenow_tickets_path: Path = ROOT_DIR / "mock_data" / "servicenow_tickets.json"

    atlassian_base_url: str | None = None
    atlassian_email: str | None = None
    atlassian_api_token: str | None = None
    atlassian_confluence_space: str | None = None
    atlassian_jira_project: str | None = None
    atlassian_confluence_cql: str | None = None
    atlassian_jira_jql: str | None = None

    mcp_mode: str = "in-process"
    mcp_base_url: str = "http://127.0.0.1:8100"
    notification_mode: str = "mock_outbox"
    mail_provider: str = "gmail_smtp"
    mail_from: str | None = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    auto_approval_threshold: float = 0.78
    google_client_id: str | None = None
    app_jwt_secret: str = "change-me-local-dev-secret"
    admin_emails: str = "abir27534@gmail.com"
    auth_token_expire_minutes: int = 720

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower().strip() == "production"

    @property
    def allow_dev_mocks(self) -> bool:
        return not self.is_production

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def servicenow_ready(self) -> bool:
        return bool(self.servicenow_instance_url and self.servicenow_user and self.servicenow_password)

    @property
    def atlassian_ready(self) -> bool:
        return bool(self.atlassian_base_url and self.atlassian_email and self.atlassian_api_token)

    @property
    def smtp_ready(self) -> bool:
        return bool(self.mail_from and self.smtp_username and self.smtp_password and self.smtp_host)

    def validate_production(self) -> None:
        if not self.is_production:
            return
        missing: list[str] = []
        if not self.database_url:
            missing.append("DATABASE_URL")
        if not self.google_client_id:
            missing.append("GOOGLE_CLIENT_ID")
        if not self.app_jwt_secret or self.app_jwt_secret == "change-me-local-dev-secret":
            missing.append("APP_JWT_SECRET")
        if self.notification_mode == "smtp" and not self.smtp_ready:
            missing.extend(["MAIL_FROM", "SMTP_USERNAME", "SMTP_PASSWORD"])
        if missing:
            unique = sorted(set(missing))
            raise RuntimeError("Production configuration is incomplete: " + ", ".join(unique))


@lru_cache
def get_settings() -> Settings:
    return Settings()
