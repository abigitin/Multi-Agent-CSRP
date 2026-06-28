from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
import smtplib

from backend.core.config import get_settings


@dataclass
class MailSendResult:
    status: str
    provider_mode: str
    response: str = ""
    error: str = ""


class MailClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def mode(self) -> str:
        if self.settings.notification_mode == "smtp":
            return "smtp" if self.settings.smtp_ready else "error"
        return "mock_outbox"

    def send(self, recipient: str, subject: str, body: str) -> MailSendResult:
        if self.settings.notification_mode != "smtp":
            return MailSendResult("queued", "mock_outbox", response="Stored in local outbox.")
        if not self.settings.smtp_ready:
            message = "SMTP settings are incomplete."
            if self.settings.is_production:
                raise RuntimeError(message)
            return MailSendResult("failed", "smtp", error=message)
        if not recipient or "@" not in recipient:
            message = "A valid customer email recipient is required before sending."
            if self.settings.is_production:
                raise RuntimeError(message)
            return MailSendResult("failed", "smtp", error=message)

        email = EmailMessage()
        email["From"] = self.settings.mail_from
        email["To"] = recipient
        email["Subject"] = subject
        email.set_content(body)
        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(str(self.settings.smtp_username), str(self.settings.smtp_password))
                smtp.send_message(email)
        except Exception as exc:
            if self.settings.is_production:
                raise RuntimeError(f"SMTP send failed: {exc}") from exc
            return MailSendResult("failed", "smtp", error=str(exc))
        return MailSendResult("sent", "smtp", response="SMTP message accepted.")
