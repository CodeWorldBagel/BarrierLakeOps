"""Tool 4 — get_affected_population:淹水範圍內村里、戶數、人口與弱勢。"""

from __future__ import annotations

from ..adapters.population import (
    SOURCE_BOUNDARY,
    SOURCE_POP,
    intersect_population,
)
from ..schemas import (
    AffectedVillage,
    PopulationOutput,
    VulnerableEstimate,
)


async def get_affected_population(polygon: dict) -> PopulationOutput:
    res = intersect_population(polygon)
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
