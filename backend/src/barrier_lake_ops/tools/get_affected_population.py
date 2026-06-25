"""Tool 4 — get_affected_population:淹水範圍內村里、戶數、人口與弱勢。"""

from __future__ import annotations

from ..adapters.population import (
    SOURCE_BOUNDARY,
    SOURCE_POP,
    intersect_population,
    villages_from_db_rows,
)
from ..schemas import (
    AffectedVillage,
    PopulationOutput,
    VulnerableEstimate,
)


async def _db_villages():
    """DB 的村里界(排程收集器寫入)。DB 空 / 不可用 → None,呼叫端 fallback 本機檔。"""
    try:
        from sqlalchemy import select

        from ..db.engine import SessionLocal
        from ..db.models import Village

        async with SessionLocal() as s:
            rows = (await s.execute(select(Village))).scalars().all()
        return villages_from_db_rows(rows) if rows else None
    except Exception:  # noqa: BLE001
        return None


async def get_affected_population(polygon: dict) -> PopulationOutput:
    res = intersect_population(polygon, await _db_villages())
    return PopulationOutput(
        affected_villages=[AffectedVillage(**v) for v in res["affected_villages"]],
        total_households=res["total_households"],
        total_population=res["total_population"],
        vulnerable_estimate=VulnerableEstimate(
            elderly_65plus=res["elderly_65plus"],
            children_under6=res["children_under6"],
        ),
        data_sources=[SOURCE_BOUNDARY, SOURCE_POP],
    )
