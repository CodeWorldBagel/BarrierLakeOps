"""/lakes 路由 — Tool 0 / Tool 1。"""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas import ListLakesOutput, LakeStatusOutput, UpstreamWeatherOutput
from ..tools.get_lake_status import get_lake_status
from ..tools.get_upstream_weather import get_upstream_weather
from ..tools.list_lakes import list_lakes

router = APIRouter(tags=["lakes"])


@router.get("/lakes", response_model=ListLakesOutput)
async def list_lakes_endpoint(status_filter: str = "all") -> ListLakesOutput:
    """Tool 0:列出可查詢堰塞湖(catalog + data.moa,依風險排序)。"""
    return await list_lakes(status_filter=status_filter)


@router.get("/lakes/{lake_id}/status", response_model=LakeStatusOutput)
async def lake_status_endpoint(lake_id: str) -> LakeStatusOutput:
    """Tool 1:取得指定堰塞湖即時狀態。"""
    return await get_lake_status(lake_id)


@router.get("/lakes/{lake_id}/weather", response_model=UpstreamWeatherOutput)
async def lake_weather_endpoint(
    lake_id: str, hours_back: int = 24, hours_forward: int = 24
) -> UpstreamWeatherOutput:
    """Tool 2:上游集水區雨量與警戒。"""
    return await get_upstream_weather(lake_id, hours_back, hours_forward)
