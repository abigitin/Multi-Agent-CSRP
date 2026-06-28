from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from backend.core.config import get_settings


@dataclass
class KnowledgePage:
    id: str
    source: str
    title: str
    url: str
    text: str
    kind: str
    updated_at: str | None
    metadata: dict[str, str]


class AtlassianClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        return bool(
            self.settings.atlassian_base_url
            and self.settings.atlassian_email
            and self.settings.atlassian_api_token
        )

    def fetch_confluence_pages(self, limit: int = 25) -> list[KnowledgePage]:
        if not self.is_configured():
            return []
        assert self.settings.atlassian_base_url
        cql = self.settings.atlassian_confluence_cql or (
            f'space="{self.settings.atlassian_confluence_space}" and type=page order by lastmodified desc'
            if self.settings.atlassian_confluence_space
            else "type=page order by lastmodified desc"
        )
        params = urlencode(
            {
                "cql": cql,
                "limit": limit,
                "expand": "body.storage,version,space,_links",
            }
        )
        payload = self._request_json(
            f"{self.settings.atlassian_base_url.rstrip('/')}/wiki/rest/api/content/search?{params}"
        )
        pages: list[KnowledgePage] = []
        for row in payload.get("results", []):
            body = (((row.get("body") or {}).get("storage") or {}).get("value")) or ""
            pages.append(
                KnowledgePage(
                    id=str(row.get("id") or ""),
                    source="confluence",
                    title=str(row.get("title") or ""),
                    url=self._absolute_url(((row.get("_links") or {}).get("webui")) or ""),
                    text=_html_to_text(body),
                    kind="page",
                    updated_at=((row.get("version") or {}).get("when")),
                    metadata={
                        "space": str(((row.get("space") or {}).get("key")) or ""),
                        "title": str(row.get("title") or ""),
                    },
                )
            )
        return pages

    def fetch_jira_issues(self, limit: int = 25) -> list[KnowledgePage]:
        if not self.is_configured():
            return []
        project = self.settings.atlassian_jira_project
        if not project and not self.settings.atlassian_jira_jql:
            return []
        jql = self.settings.atlassian_jira_jql or f'project="{project}" ORDER BY updated DESC'
        params = urlencode(
            {
                "jql": jql,
                "maxResults": limit,
                "fields": ",".join(
                    [
                        "summary",
                        "description",
                        "status",
                        "priority",
                        "assignee",
                        "reporter",
                        "created",
                        "updated",
                        "issuetype",
                        "labels",
                    ]
                ),
            }
        )
        payload = self._request_json(
            f"{self.settings.atlassian_base_url.rstrip('/')}/rest/api/3/search?{params}"
        )
        issues: list[KnowledgePage] = []
        for row in payload.get("issues", []):
            fields = row.get("fields") or {}
            description = fields.get("description") or ""
            issues.append(
                KnowledgePage(
                    id=str(row.get("key") or ""),
                    source="jira",
                    title=str(fields.get("summary") or row.get("key") or ""),
                    url=self._absolute_url(f"/browse/{quote(str(row.get('key') or ''))}"),
                    text=_html_to_text(_stringify(description)),
                    kind="issue",
                    updated_at=fields.get("updated"),
                    metadata={
                        "project": str(project or ""),
                        "status": str((fields.get("status") or {}).get("name") or ""),
                        "priority": str((fields.get("priority") or {}).get("name") or ""),
                    },
                )
            )
        return issues

    def _request_json(self, url: str) -> dict[str, Any]:
        assert self.settings.atlassian_email
        assert self.settings.atlassian_api_token
        token = f"{self.settings.atlassian_email}:{self.settings.atlassian_api_token}".encode("utf-8")
        req = Request(
            url,
            headers={
                "Authorization": f"Basic {base64.b64encode(token).decode('ascii')}",
                "Accept": "application/json",
            },
        )
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _absolute_url(self, path: str) -> str:
        if not self.settings.atlassian_base_url:
            return path
        return f"{self.settings.atlassian_base_url.rstrip('/')}{path}"


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return " ".join(self.parts)


def _html_to_text(value: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(value)
    return parser.text() or value


def _stringify(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_stringify(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_stringify(v) for v in value)
    return str(value)

