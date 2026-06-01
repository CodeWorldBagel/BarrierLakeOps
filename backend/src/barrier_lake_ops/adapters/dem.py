"""DEM adapter — 讀前處理的 SRTM 高程格點,跑簡化「容量守恆」淹水模型。

資料源:SRTM 30m(NASA,公有領域),前處理見 scripts/prep_geo.py。
模型為 MVP 簡化版(bathtub fill-to-volume + 連通域),非工程級水文模型。
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from shapely.geometry import box, mapping
from shapely.ops import unary_union

from ..config import get_settings
from ..schemas import DataSource

SOURCE = DataSource(
    source="SRTM 30m 數值高程(NASA,公有領域)via opentopodata",
    license="Public Domain(NASA SRTM)",
    attribution="DEM: NASA SRTM 30m;生產環境建議改用國土測繪中心 20m DEM",
    url="https://www.opentopodata.org/datasets/srtm/",
)


@lru_cache
def _dem_dir() -> Path:
    return get_settings().data_dir / "dem"


def has_dem(lake_id: str) -> bool:
    return (_dem_dir() / f"{lake_id}.npy").exists()


def _load(lake_id: str):
    arr = np.load(_dem_dir() / f"{lake_id}.npy")
    meta = json.loads((_dem_dir() / f"{lake_id}.json").read_text(encoding="utf-8"))
    return arr, meta


def _window_min(arr: np.ndarray, radius: int = 6) -> np.ndarray:
    """鄰域最小值濾波(近似 HAND 的局部谷底高程)。inf 視為無資料。"""
    h, w = arr.shape
    out = np.full_like(arr, np.inf)
    for dr in range(-radius, radius + 1):
        r0, r1 = max(0, dr), min(h, h + dr)
        for dc in range(-radius, radius + 1):
            c0, c1 = max(0, dc), min(w, w + dc)
            shifted = np.full_like(arr, np.inf)
            shifted[r0:r1, c0:c1] = arr[r0 - dr : r1 - dr, c0 - dc : c1 - dc]
            out = np.minimum(out, shifted)
    return out


def _connected_to_min(mask: np.ndarray, seed: tuple[int, int]) -> np.ndarray:
    """保留與 seed 4-連通的淹水區(去除孤立低窪)。"""
    h, w = mask.shape
    out = np.zeros_like(mask)
    if not mask[seed]:
        return mask  # seed 不在 mask,退回原 mask
    stack = [seed]
    out[seed] = True
    while stack:
        r, c = stack.pop()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w and mask[nr, nc] and not out[nr, nc]:
                out[nr, nc] = True
                stack.append((nr, nc))
    return out


def estimate_flood(
    lake_id: str,
    volume_m3: float,
    centroid_lonlat: tuple[float, float],
    *,
    reach_km: float = 8.0,
) -> dict:
    """回傳 {polygon(GeoJSON), max_depth_m, arrival_minutes, cells, level_m}。

    簡化模型:在湖下游 reach_km 內,以容量推估的洪氾高度 H(上限 15m)淹沒
    谷底低地。距離限制避免把遠處不相干低地納入;H 上限避免窄谷被灌成不合理深度。
    """
    arr, meta = _load(lake_id)
    h, w = arr.shape
    minlon, minlat, maxlon, maxlat = meta["bbox"]
    elev = np.where(np.isnan(arr), np.inf, arr)

    midlat = (minlat + maxlat) / 2
    dlon = (maxlon - minlon) / (w - 1)
    dlat = (maxlat - minlat) / (h - 1)
    dx_m = dlon * 111_320 * math.cos(math.radians(midlat))
    dy_m = dlat * 110_540
    cell_area = abs(dx_m * dy_m)

    # 各格點到湖心距離(公尺),row0=北
    clon, clat = centroid_lonlat
    rows = np.arange(h)[:, None]
    cols = np.arange(w)[None, :]
    cell_lon = minlon + cols * dlon
    cell_lat = maxlat - rows * dlat
    dist_m = np.hypot(
        (cell_lon - clon) * 111_320 * math.cos(math.radians(midlat)),
        (cell_lat - clat) * 110_540,
    )
    in_reach = dist_m <= reach_km * 1000

    # 下游谷底基準:reach 內最低點(連通種子)
    masked_elev = np.where(in_reach, elev, np.inf)
    base = float(masked_elev.min())
    seed = tuple(np.argwhere(masked_elev == base)[0])

    # HAND-like:相對高度 = 各格高程 - 鄰域(約 1.5km)谷底高程
    # 沿河谷坡降淹沒,克服單一水平水位無法同時涵蓋上下游氾濫平原的問題。
    local_min = _window_min(elev, radius=6)
    relative = elev - local_min

    # 洪氾高度 H(由體積推估,上限 15m,下限 3m)
    vol_million = volume_m3 / 1_000_000
    flood_h = float(np.clip(2.0 + vol_million / 12.0, 3.0, 15.0))

    inundatable = in_reach & np.isfinite(elev) & (relative <= flood_h)
    mask = _connected_to_min(inundatable, seed)
    depth = np.where(mask, np.clip(flood_h - relative, 0, None), 0.0)
    max_depth = float(depth[mask].max()) if mask.any() else 0.0
    level = base + flood_h

    # row 0 = 北;cell (r,c) → lon/lat 範圍
    def cell_box(r: int, c: int):
        lon0 = minlon + (c - 0.5) * dlon
        lon1 = minlon + (c + 0.5) * dlon
        lat_center = maxlat - r * dlat  # row0=north
        lat0 = lat_center - dlat / 2
        lat1 = lat_center + dlat / 2
        return box(lon0, lat0, lon1, lat1)

    boxes = [cell_box(r, c) for r, c in np.argwhere(mask)]
    if not boxes:
        poly = {"type": "FeatureCollection", "features": []}
        return {"polygon": poly, "max_depth_m": 0.0, "arrival_minutes": None,
                "cells": 0, "level_m": round(level, 1)}

    merged = unary_union(boxes).simplify(dlon / 3, preserve_topology=True)

    # 抵達時間:湖心 → 最遠淹水格點 / 假設洪峰速度 4 m/s
    clon, clat = centroid_lonlat
    far = 0.0
    for r, c in np.argwhere(mask):
        plon = minlon + c * dlon
        plat = maxlat - r * dlat
        d = math.hypot(
            (plon - clon) * 111_320 * math.cos(math.radians(midlat)),
            (plat - clat) * 110_540,
        )
        far = max(far, d)
    arrival_min = int(far / 4.0 / 60) if far > 0 else None

    return {
        "polygon": {
            "type": "Feature",
            "geometry": mapping(merged),
            "properties": {"flood_level_m": round(level, 1), "max_depth_m": round(max_depth, 1)},
        },
        "max_depth_m": round(max_depth, 1),
        "arrival_minutes": arrival_min,
        "cells": int(mask.sum()),
        "level_m": round(level, 1),
    }
