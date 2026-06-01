"""/briefing 路由 — Tool 5 + 持久化稽核(briefings)。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent.openai_client import get_model
from ..db.engine import get_session
from ..db.repository import get_briefing, list_briefings, save_briefing
from ..schemas import ComposeBriefingInput
from ..tools.compose_briefing import compose_briefing

router = APIRouter(tags=["briefing"])


def _record(row) -> dict:
    return {
        "id": str(row.id),
        "lake_id": row.lake_id,
        "audience": row.audience,
        "status_color": row.status_color,
        "headline": row.headline,
        "key_facts": row.key_facts,
        "recommended_actions": row.recommended_actions,
        "natural_language": row.natural_language,
        "ai_confidence": row.ai_confidence,
        "data_sources_used": row.data_sources_used,
        "model_used": row.model_used,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.post("/briefing")
async def briefing_endpoint(
    body: ComposeBriefingInput, session: AsyncSession = Depends(get_session)
) -> dict:
    """Tool 5:生成態勢摘要,並寫入 briefings 稽核(含輸入快照)。"""
    out = await compose_briefing(body.context, body.audience.value, body.lake_id)
    row = await save_briefing(
        session,
        output=out,
        audience=body.audience.value,
        lake_id=body.lake_id,
        input_context=body.context,
        model_used=get_model(),
    )
    rec = _record(row)
    rec["briefing"] = out.model_dump()
    return rec


@router.get("/lakes/{lake_id}/briefings")
async def list_lake_briefings(
    lake_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """某湖的歷史簡報清單(稽核軌跡)。"""
    rows = await list_briefings(session, lake_id=lake_id)
    return {"lake_id": lake_id, "total": len(rows), "briefings": [_record(r) for r in rows]}


@router.get("/briefings/{briefing_id}")
async def get_briefing_detail(
    briefing_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """重播單份簡報 + 驅動它的輸入快照(可追溯)。"""
    try:
        bid = uuid.UUID(briefing_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid briefing id") from exc
    row = await get_briefing(session, bid)
    if row is None:
        raise HTTPException(status_code=404, detail="briefing not found")
    rec = _record(row)
    rec["input_context"] = row.input_context
    return rec
