"""MVP bathtub-fill inundation model."""

from __future__ import annotations

import numpy as np
from shapely.geometry import box, mapping
from shapely.ops import unary_union

from .common import (
    DEFAULT_WINDOW_MIN_RADIUS,
    _connected_to_min,
    _estimate_arrival_minutes,
    _load_window_min,
    _nearest_finite_cell,
    load_dem_context,
)


def estimate_flood(
    lake_id: str,
    volume_m3: float,
    centroid_lonlat: tuple[float, float],
    *,
    reach_km: float = 20.0,
) -> dict:
    """回傳 {polygon(GeoJSON), max_depth_m, arrival_minutes, cells, level_m}。

    簡化模型:在湖下游 reach_km 內,以容量推估的洪氾高度 H(上限 15m)淹沒
    谷底低地。距離限制避免把遠處不相干低地納入;H 上限避免窄谷被灌成不合理深度。
    """
    dem = load_dem_context(lake_id)
    h, w = dem.shape
    minlon, _minlat, _maxlon, maxlat = dem.bbox
    elev = dem.elev

    # 各格點到湖心距離(公尺),row0=北
    clon, clat = centroid_lonlat
    rows = np.arange(h)[:, None]
    cols = np.arange(w)[None, :]
    cell_lon = minlon + cols * dem.dlon
    cell_lat = maxlat - rows * dem.dlat
    x_m = (cell_lon - clon) * dem.dx_m / dem.dlon
    y_m = (cell_lat - clat) * dem.dy_m / dem.dlat
    dist_m = np.hypot(x_m, y_m)
    in_reach = dist_m <= reach_km * 1000

    # Seed from the dam centroid instead of the lowest point in reach.
    dam_row, dam_col = dem.lonlat_to_row_col(clon, clat)
    seed_rc = _nearest_finite_cell(elev, dam_row, dam_col)
    if seed_rc is None:
        seed_rc = (dam_row, dam_col)
    seed = seed_rc
    base = float(elev[seed]) if np.isfinite(elev[seed]) else float(np.nanmin(dem.arr))

    # HAND-like:相對高度 = 各格高程 - 鄰域谷底高程
    # 沿河谷坡降淹沒,克服單一水平水位無法同時涵蓋上下游氾濫平原的問題。
    local_min = _load_window_min(lake_id, DEFAULT_WINDOW_MIN_RADIUS)
    relative = elev - local_min

    # 洪氾高度 H(由體積推估,上限 15m,下限 3m)
    vol_million = volume_m3 / 1_000_000
    flood_h = float(np.clip(2.0 + vol_million / 12.0, 3.0, 15.0))

    inundatable = in_reach & np.isfinite(elev) & (relative <= flood_h)
    if not inundatable[seed] and inundatable.any():
        rr, cc = np.where(inundatable)
        score = np.hypot(rr - dam_row, cc - dam_col) * 10_000 + relative[rr, cc]
        pos = int(np.argmin(score))
        seed = (int(rr[pos]), int(cc[pos]))
    mask = _connected_to_min(inundatable, seed)
    depth = np.where(mask, np.clip(flood_h - relative, 0, None), 0.0)
    max_depth = float(depth[mask].max()) if mask.any() else 0.0
    level = base + flood_h

    # row 0 = 北;cell (r,c) → lon/lat 範圍
    def cell_box(r: int, c: int):
        lon0 = minlon + (c - 0.5) * dem.dlon
        lon1 = minlon + (c + 0.5) * dem.dlon
        lat_center = maxlat - r * dem.dlat  # row0=north
        lat0 = lat_center - dem.dlat / 2
        lat1 = lat_center + dem.dlat / 2
        return box(lon0, lat0, lon1, lat1)

    boxes = [cell_box(r, c) for r, c in np.argwhere(mask)]
    if not boxes:
        poly = {"type": "FeatureCollection", "features": []}
        return {"polygon": poly, "max_depth_m": 0.0, "arrival_minutes": None,
                "cells": 0, "level_m": round(level, 1)}

    merged = unary_union(boxes).simplify(dem.dlon / 3, preserve_topology=True)

    # MVP has no routed flow path, so use the centroid distance matrix as along_m.
    arrival_min = _estimate_arrival_minutes(mask, dist_m)

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
