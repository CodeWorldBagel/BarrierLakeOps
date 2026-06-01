"""/chat 路由 — reference client 的 Chat Agent(SSE)+ 對話歷史。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ..agent.chat_agent import run_chat
from ..db.engine import get_session
from ..db.repository import get_session_messages
from ..schemas import ChatRequest

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat_endpoint(body: ChatRequest):
    """Chat Agent 多步調用 6 個 Tool,SSE 即時推送工具調用過程與最終摘要。"""
    return EventSourceResponse(
        run_chat(body.message, lake_id=body.lake_id, session_id=body.session_id)
    )


@router.get("/chat/sessions/{session_id}")
async def chat_history(
    session_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """讀取某 chat session 的對話歷史。"""
    try:
        sid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid session id") from exc
    msgs = await get_session_messages(session, sid)
    return {
        "session_id": session_id,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "tool_name": m.tool_name,
                "tool_args": m.tool_args,
                "tool_result": m.tool_result,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
        ],
    }
