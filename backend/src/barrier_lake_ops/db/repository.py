"""持久化操作:briefings 稽核 + chat 歷史。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import BriefingOutput
from .models import Briefing, ChatMessage, ChatSession


# --------------------------- briefings --------------------------- #
async def save_briefing(
    session: AsyncSession,
    *,
    output: BriefingOutput,
    audience: str,
    lake_id: str | None,
    input_context: dict[str, Any],
    model_used: str,
) -> Briefing:
    row = Briefing(
        lake_id=lake_id,
        audience=audience,
        status_color=output.status_color.value,
        headline=output.headline,
        key_facts=output.key_facts,
        recommended_actions=output.recommended_actions,
        natural_language=output.natural_language,
        ai_confidence=output.ai_confidence,
        data_sources_used=[ds.model_dump() for ds in output.data_sources_used],
        input_context=input_context,
        model_used=model_used,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_briefings(
    session: AsyncSession, *, lake_id: str | None = None, limit: int = 50
) -> list[Briefing]:
    stmt = select(Briefing).order_by(Briefing.created_at.desc()).limit(limit)
    if lake_id:
        stmt = stmt.where(Briefing.lake_id == lake_id)
    return list((await session.scalars(stmt)).all())


async def get_briefing(session: AsyncSession, briefing_id: uuid.UUID) -> Briefing | None:
    return await session.get(Briefing, briefing_id)


# --------------------------- chat --------------------------- #
async def create_chat_session(
    session: AsyncSession, *, lake_id: str | None
) -> ChatSession:
    row = ChatSession(lake_id=lake_id)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def add_chat_message(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    role: str,
    content: str | None = None,
    tool_name: str | None = None,
    tool_args: dict | None = None,
    tool_result: dict | None = None,
) -> ChatMessage:
    row = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        tool_name=tool_name,
        tool_args=tool_args,
        tool_result=tool_result,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_session_messages(
    session: AsyncSession, session_id: uuid.UUID
) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    return list((await session.scalars(stmt)).all())
