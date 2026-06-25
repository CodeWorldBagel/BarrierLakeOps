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
from .tools.estimate_inundation import explain_flood_cell as _explain_cell
from .tools.get_affected_population import get_affected_population as _population
from .tools.get_lake_status import get_lake_status as _status
from .tools.get_upstream_weather import get_upstream_weather as _weather
from .tools.list_lakes import list_lakes as _list

# 安全守則同步至 AGENT.md;透過 MCP `instructions` 傳遞給掛載的 client(Claude / Cursor 等),
# 確保護欄不依賴本專案內建 reference client 的 system prompt。
INSTRUCTIONS = (
    "你是台灣『堰塞湖跨部會態勢』作戰助手,服務災害應變中心人員。"
    "只能透過本元件提供的工具取得資料,不得用工具以外的知識編造數字,也不得進行通用網路搜尋補資料。"
    "必須區分觀測值與模型估算:淹水(estimate_inundation)為 MVP 簡化模型需註明;水位若為情境基準快照需說明非即時;"
    "資料若標示 stale/unavailable 需如實指出。"
    "你只提供研判與建議,不得宣稱已發送撤離簡訊、致電消防或觸發警報——對外通知一律由人類執行,"
    "撤離決策保留給人類指揮官。請用繁體中文,先呈現關鍵數據再給建議。完整守則見 AGENT.md。"
)

mcp = FastMCP("BarrierLakeOps", instructions=INSTRUCTIONS)


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
    lake_id: str,
    breach_scenario: str = "full",
    breach_volume_million_m3: float | None = None,
    model_variant: str = "mvp",
) -> dict:
    """推估潰壩淹水範圍。model_variant: mvp(預設,向下相容)|dem_screening(DEM-only 下游流路+谷地約束+體積守恆)"""
    return (
        await _inundation(lake_id, breach_scenario, breach_volume_million_m3, model_variant)
    ).model_dump()


@mcp.tool
async def explain_flood_cell(lake_id: str, lon: float, lat: float) -> dict:
    """查詢指定經緯度座標為何在(或不在)潰壩淹水範圍內,供地圖點擊互動或 LLM 解說使用。"""
    return await _explain_cell(lake_id, lon, lat)


@mcp.tool
async def get_affected_population(polygon: dict) -> dict:
    """計算淹水 GeoJSON polygon 範圍內村里、戶數、人口與老幼弱勢。"""
    return (await _population(polygon)).model_dump()


@mcp.tool
async def compose_briefing(
    context: dict, audience: str = "command_center", lake_id: str | None = None
) -> dict:
    """彙整 Tool 0–4 回傳,生成結構化態勢摘要(寫入稽核軌跡)。audience: command_center|public|media|multi_lake_overview。

    ⚠ 僅提供研判輔助;不下達或建議自動撤離,撤離決策保留給人類指揮官。"""
    aud = audience if audience in BriefingAudience._value2member_map_ else "command_center"
    return (await _compose(context, aud, lake_id)).model_dump()


def main() -> None:
    if "--http" in sys.argv:
        mcp.run(transport="http", host="0.0.0.0", port=8001)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
