"""6 個 Tool 的純邏輯 — MCP(server.py)與 REST(app.py)共用。

每個 tool 為 async 函式,輸入/輸出對應 schemas.py。
"""

from __future__ import annotations

from ..catalog import Lake, Threshold
from ..schemas import AlertLevel

# 風險排序用權重(高 → 低)
ALERT_RANK = {
    AlertLevel.red: 4,
    AlertLevel.orange: 3,
    AlertLevel.yellow: 2,
    AlertLevel.green: 1,
    AlertLevel.unknown: 0,
}


def alert_from_headroom(headroom_m: float | None, th: Threshold) -> AlertLevel:
    """headroom(距溢流公尺數)越小越危險。"""
    if headroom_m is None:
        return AlertLevel.unknown
    if headroom_m <= th.red_alert_headroom_m:
        return AlertLevel.red
    if headroom_m <= th.orange_alert_headroom_m:
        return AlertLevel.orange
    if headroom_m <= th.yellow_alert_headroom_m:
        return AlertLevel.yellow
    return AlertLevel.green


def compute_headroom(lake: Lake) -> float | None:
    rs = lake.reference_state
    ovf = lake.threshold.overflow_elevation_m
    if rs and rs.water_level_m is not None and ovf is not None:
        return round(ovf - rs.water_level_m, 2)
    return None
