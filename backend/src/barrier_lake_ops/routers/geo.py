"""/inundation、/population 路由 — Tool 3 / Tool 4。"""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas import (
    InundationInput,
    InundationOutput,
    PopulationInput,
    PopulationOutput,
)
from ..tools.estimate_inundation import estimate_inundation
from ..tools.get_affected_population import get_affected_population

router = APIRouter(tags=["geo"])


@router.post("/lakes/{lake_id}/inundation", response_model=InundationOutput)
async def inundation_endpoint(
    lake_id: str, body: InundationInput
) -> InundationOutput:
    """Tool 3:潰壩淹水範圍推估(真實 DEM + MVP 簡化模型)。"""
    return await estimate_inundation(
        lake_id,
        breach_scenario=body.breach_scenario,
        breach_volume_million_m3=body.breach_volume_million_m3,
    )


@router.post("/population", response_model=PopulationOutput)
async def population_endpoint(body: PopulationInput) -> PopulationOutput:
    """Tool 4:淹水範圍內村里 / 戶數 / 人口 / 弱勢。"""
    return await get_affected_population(body.polygon)
