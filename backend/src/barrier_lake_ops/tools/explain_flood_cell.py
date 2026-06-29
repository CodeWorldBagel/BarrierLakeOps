"""Single-point flood explanation tool."""

from __future__ import annotations

import numpy as np
from shapely.geometry import Point, shape

from ..adapters.dem import has_dem
from ..adapters.dem_models.common import (
    DEFAULT_DIRECTIONAL_RELATIVE_RADIUS,
    _load_window_min,
    load_dem_context,
)
from ..adapters.population import locate_point
from ..catalog import load_catalog_async
from .inundation_runtime import estimate_flood_dem_screening_runtime
from .inundation_runtime import resolve_breach_volume_million_m3

EXPLAIN_RELATIVE_HEIGHT_LIMIT_M = 15.0
EXPLAIN_FALLBACK_PATH_LENGTH_M = 18_000


async def explain_flood_cell(lake_id: str, lon: float, lat: float) -> dict:
    """查詢指定座標點的淹水狀況與原因(輕量單點查詢)。"""
    cat = await load_catalog_async()
    lake = cat.get(lake_id)

    clicked_location = locate_point(lon, lat)

    if lake is None or not has_dem(lake_id):
        return {
            "in_flood": False,
            "location": clicked_location,
            "elevation_m": None,
            "hand_relative_m": None,
            "distance_from_dam_m": None,
            "segment_id": None,
            "local_flood_h_m": None,
            "reason": "此堰塞湖無 DEM 資料,無法判斷淹水狀況。",
        }

    dem = load_dem_context(lake_id)

    if not dem.contains_lonlat(lon, lat):
        return {
            "in_flood": False,
            "location": clicked_location,
            "elevation_m": None,
            "hand_relative_m": None,
            "distance_from_dam_m": None,
            "segment_id": None,
            "local_flood_h_m": None,
            "reason": f"座標 ({lon:.4f}, {lat:.4f}) 超出此堰塞湖 DEM 範圍。",
        }

    row, col = dem.lonlat_to_row_col(lon, lat)

    elev_raw = float(dem.arr[row, col]) if not np.isnan(dem.arr[row, col]) else None

    local_min = _load_window_min(lake_id, DEFAULT_DIRECTIONAL_RELATIVE_RADIUS)
    relative_val = (
        float(dem.elev[row, col] - local_min[row, col])
        if np.isfinite(dem.elev[row, col])
        else None
    )

    clon, clat = lake.location.lon, lake.location.lat
    dist_m = dem.distance_from_centroid_m(lon, lat, (clon, clat))

    storage = resolve_breach_volume_million_m3(lake, "full", None)
    volume_m3 = storage * 1_000_000
    res = estimate_flood_dem_screening_runtime(lake_id, volume_m3, (clon, clat))

    geom = res.get("polygon", {}).get("geometry")
    if geom:
        flood_geom = shape(geom)
        point = Point(lon, lat)
        in_flood = bool(flood_geom.contains(point) or flood_geom.touches(point))
    else:
        in_flood = False

    depth_at_cell = None
    if in_flood and relative_val is not None and res.get("max_depth_m") is not None:
        depth_at_cell = max(
            0.0,
            min(
                float(res["max_depth_m"]),
                float(res["max_depth_m"]) - max(relative_val, 0.0) * 0.25,
            ),
        )

    segment_id = None

    if elev_raw is None:
        reason = "此格無 DEM 高程資料,無法判斷。"
    elif in_flood:
        reason = (
            f"位於淹水區內。相對谷底高程 {relative_val:.1f}m,低於此段洪水位;"
            f" 距壩 {dist_m/1000:.1f}km,估計水深約 {depth_at_cell:.1f}m。"
            if depth_at_cell is not None
            else f" 距壩 {dist_m/1000:.1f}km。"
        )
    else:
        if relative_val is not None and relative_val > EXPLAIN_RELATIVE_HEIGHT_LIMIT_M:
            reason = f"高於谷底 {relative_val:.1f}m,超出模型淹水上限(15m),不在淹水範圍內。"
        elif dist_m > res.get("path_length_m", EXPLAIN_FALLBACK_PATH_LENGTH_M):
            reason = f"距壩 {dist_m/1000:.1f}km,超出洪水抵達距離,不在淹水範圍內。"
        else:
            reason = (
                f"相對谷底高程 {relative_val:.1f}m,高於此段洪水位或無法從壩體連通抵達,"
                f" 不在淹水範圍內。"
            )

    return {
        "in_flood": in_flood,
        "location": clicked_location,
        "elevation_m": round(elev_raw, 1) if elev_raw is not None else None,
        "hand_relative_m": round(relative_val, 1) if relative_val is not None else None,
        "distance_from_dam_m": round(dist_m, 0),
        "segment_id": segment_id,
        "local_flood_h_m": round(depth_at_cell, 1) if in_flood else None,
        "reason": reason,
    }
