from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.database import get_db, init_db
from backend.mcp.server import MCPToolServer


class ToolCallRequest(BaseModel):
    tool_name: str
    payload: dict[str, Any] = {}


app = FastAPI(title="Customer Support MCP Tool Service")


@app.on_event("startup")
def on_startup() -> None:
    get_settings().validate_production()
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": get_settings().mcp_mode}


@app.post("/tools/call")
def call_tool(payload: ToolCallRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    result = MCPToolServer(db).call(payload.tool_name, payload.payload)
    return {"status": result.status, "mode": result.mode, "data": result.data}
