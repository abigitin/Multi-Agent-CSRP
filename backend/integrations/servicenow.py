from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.core.config import get_settings


@dataclass
class ServiceNowRecord:
    sys_id: str
    number: str
    short_description: str
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
    source_system: str = "servicenow"
    source_record_type: str = "incident"
    external_url: str | None = None
    raw_payload: str = "{}"
    opened_at: datetime | None = None
    updated_at: datetime | None = None


class ServiceNowClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def mode(self) -> str:
        return "live" if self._is_configured() else "dev_mock"

    def _is_configured(self) -> bool:
        return bool(
            self.settings.servicenow_instance_url
            and self.settings.servicenow_user
            and self.settings.servicenow_password
        )

    def fetch_records(self) -> list[ServiceNowRecord]:
        if self._is_configured():
            return self._fetch_remote_records()
        if self.settings.is_production:
            raise RuntimeError("ServiceNow credentials are required in production.")
        return self._load_mock_records(self.settings.servicenow_tickets_path)

    def _fetch_remote_records(self) -> list[ServiceNowRecord]:
        assert self.settings.servicenow_instance_url
        assert self.settings.servicenow_user
        assert self.settings.servicenow_password

        query = urlencode(
            {
                "sysparm_limit": 50,
                "sysparm_display_value": "true",
                "sysparm_fields": ",".join(
                    [
                        "sys_id",
                        "number",
                        "short_description",
                        "description",
                        "category",
                        "subcategory",
                        "impact",
                        "urgency",
                        "priority",
                        "assignment_group",
                        "caller_id",
                        "caller_id.email",
                        "email",
                        "state",
                        "opened_at",
                        "sys_updated_on",
                    ]
                ),
            }
        )
        url = f"{self.settings.servicenow_instance_url.rstrip('/')}/api/now/table/{self.settings.servicenow_table}?{query}"
        payload = self._request_json(url)
        records: list[ServiceNowRecord] = []
        for row in payload.get("result", []):
            records.append(
                ServiceNowRecord(
                    sys_id=str(row.get("sys_id") or row.get("number")),
                    number=str(row.get("number") or row.get("sys_id")),
                    short_description=str(row.get("short_description") or ""),
                    description=str(row.get("description") or ""),
                    category=row.get("category"),
                    subcategory=row.get("subcategory"),
                    impact=row.get("impact"),
                    urgency=row.get("urgency"),
                    priority=row.get("priority"),
                    assignment_group=_display_value(row.get("assignment_group")),
                    caller=_display_value(row.get("caller_id")),
                    caller_email=_email_value(row),
                    state=str(row.get("state") or "new"),
                    external_url=f"{self.settings.servicenow_instance_url.rstrip('/')}/nav_to.do?uri={self.settings.servicenow_table}.do?sys_id={row.get('sys_id')}",
                    raw_payload=json.dumps(row, default=str),
                )
            )
        return records

    def _load_mock_records(self, path: Path) -> list[ServiceNowRecord]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        records: list[ServiceNowRecord] = []
        for row in payload:
            records.append(
                ServiceNowRecord(
                    sys_id=str(row.get("sys_id") or row["id"]),
                    number=str(row.get("number") or row["id"]),
                    short_description=str(row.get("short_description") or row.get("customer_query") or ""),
                    description=str(row.get("description") or ""),
                    category=row.get("category"),
                    subcategory=row.get("subcategory"),
                    impact=row.get("impact"),
                    urgency=row.get("urgency"),
                    priority=row.get("priority"),
                    assignment_group=row.get("assignment_group"),
                    caller=row.get("caller"),
                    caller_email=row.get("caller_email") or row.get("email"),
                    state=str(row.get("state") or "new"),
                    external_url=row.get("external_url"),
                    raw_payload=json.dumps(row, default=str),
                )
            )
        return records

    def _request_json(self, url: str) -> dict[str, Any]:
        token = f"{self.settings.servicenow_user}:{self.settings.servicenow_password}".encode("utf-8")
        req = Request(url, headers={"Authorization": f"Basic {base64.b64encode(token).decode('ascii')}"})
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))


def _display_value(value: Any) -> str | None:
    if isinstance(value, dict):
        return str(value.get("display_value") or value.get("value") or "")
    if value is None:
        return None
    return str(value)


def _email_value(row: dict[str, Any]) -> str | None:
    caller = row.get("caller_id")
    if isinstance(caller, dict):
        for key in ("email", "display_value", "value"):
            value = caller.get(key)
            if isinstance(value, str) and "@" in value:
                return value
    for key in ("caller_id.email", "email"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return None
