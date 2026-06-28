from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.mcp.server import MCPToolServer, ToolResult


class MCPClient:
    def __init__(self, db: Session) -> None:
        self.settings = get_settings()
        self.server = MCPToolServer(db)

    def call_tool(self, tool_name: str, payload: dict[str, Any]) -> ToolResult:
        if self.settings.mcp_mode == "http":
            return self._call_http_tool(tool_name, payload)
        return self.server.call(tool_name, payload)

    def _call_http_tool(self, tool_name: str, payload: dict[str, Any]) -> ToolResult:
        body = json.dumps({"tool_name": tool_name, "payload": payload}).encode("utf-8")
        req = Request(
            f"{self.settings.mcp_base_url.rstrip('/')}/tools/call",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            if self.settings.is_production:
                raise RuntimeError(f"MCP HTTP call failed for {tool_name}: {exc}") from exc
            return self.server.call(tool_name, payload)
        return ToolResult(
            status=str(data.get("status") or "error"),
            mode=str(data.get("mode") or "http"),
            data=dict(data.get("data") or {}),
        )
