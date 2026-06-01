"""FastMCP server — 把 6 個 Tool 以 MCP 介面暴露(與 REST 共用同一份 tools/ 邏輯)。

啟動:
  uv run barrier-lake-ops              # stdio(供 Claude Desktop / Cursor 掛載)
  uv run barrier-lake-ops --http       # HTTP transport
"""

from __future__ import annotations

import sys

from fastmcp import FastMCP

from .schemas import BriefingAudience
from .tools.compose_briefing import compose_briefing as _compose
from .tools.estimate_inundation import estimate_inundation as _inundation
from .tools.get_affected_population import get_affected_population as _population
from .tools.get_lake_status import get_lake_status as _status
from .tools.get_upstream_weather import get_upstream_weather as _weather
from .tools.list_lakes import list_lakes as _list

mcp = FastMCP("BarrierLakeOps")


@mcp.tool
async def list_lakes(status_filter: str = "all") -> dict:
    """列出可查詢的堰塞湖(catalog + data.moa),依風險排序。status_filter: all|active|monitoring。"""
    return (await _list(status_filter)).model_dump()


@mcp.tool
async def get_lake_status(lake_id: str) -> dict:
    """取得指定堰塞湖水位、蓄水量、距溢流 headroom、警戒等級。"""
    return (await _status(lake_id)).model_dump()


@mcp.tool
async def get_upstream_weather(lake_id: str, hours_back: int = 24, hours_forward: int = 24) -> dict:
    """取得堰塞湖上游集水區鄰近雨量站觀測與警戒(CWA)。"""
    return (await _weather(lake_id, hours_back, hours_forward)).model_dump()


@mcp.tool
async def estimate_inundation(
    lake_id: str, breach_scenario: str = "full", breach_volume_million_m3: float | None = None
) -> dict:
    """推估潰壩淹水範圍(真實 DEM + MVP 簡化模型),輸出 GeoJSON 與深度/抵達時間。"""
    return (await _inundation(lake_id, breach_scenario, breach_volume_million_m3)).model_dump()


@mcp.tool
async def get_affected_population(polygon: dict) -> dict:
    """計算淹水 GeoJSON polygon 範圍內村里、戶數、人口與老幼弱勢。"""
    return (await _population(polygon)).model_dump()


@mcp.tool
async def compose_briefing(
    context: dict, audience: str = "command_center", lake_id: str | None = None
) -> dict:
    """彙整 Tool 0–4 回傳,生成結構化態勢摘要。audience: command_center|public|media|multi_lake_overview。"""
    aud = audience if audience in BriefingAudience._value2member_map_ else "command_center"
    return (await _compose(context, aud, lake_id)).model_dump()


def main() -> None:
    if "--http" in sys.argv:
        mcp.run(transport="http", host="0.0.0.0", port=8001)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
