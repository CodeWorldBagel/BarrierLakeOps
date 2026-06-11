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

DEFAULT_DAM_ANCHOR_RADIUS = 1
DEFAULT_DIRECTIONAL_RELATIVE_RADIUS = 2
DEFAULT_DOWNSTREAM_BACKTRACK_CELLS = 6
DEFAULT_DOWNSTREAM_SEGMENT_M = 500.0
DEFAULT_FLOW_PATH_RISE_TOLERANCE_M =60.0
DEFAULT_FLOOD_H_MAX_M = 15.0
DEFAULT_FLOOD_H_SOLVER_STEPS = 24

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


def _reachable_floodable_from_seed_8(
    traversable: np.ndarray,
    floodable: np.ndarray,
    seed: tuple[int, int],
) -> np.ndarray:
    """從 seed 往外掃描 traversable 區,只標記其中 floodable 的格子。"""
    h, w = traversable.shape
    out = np.zeros_like(traversable)
    seen = np.zeros_like(traversable)
    if not traversable[seed]:
        return out

    stack = [seed]
    seen[seed] = True
    if floodable[seed]:
        out[seed] = True

    while stack:
        r, c = stack.pop()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if not (0 <= nr < h and 0 <= nc < w):
                    continue
                if seen[nr, nc] or not traversable[nr, nc]:
                    continue
                seen[nr, nc] = True
                if floodable[nr, nc]:
                    out[nr, nc] = True
                stack.append((nr, nc))
    return out


def _nearest_finite_cell(
    elev: np.ndarray,
    row: int,
    col: int,
    *,
    radius: int = DEFAULT_DAM_ANCHOR_RADIUS,
) -> tuple[int, int] | None:
    """找指定 cell 附近的有限高程 cell;優先最近,距離相同取較低高程。"""
    h, w = elev.shape
    r0, r1 = max(0, row - radius), min(h, row + radius + 1)
    c0, c1 = max(0, col - radius), min(w, col + radius + 1)
    rr, cc = np.where(np.isfinite(elev[r0:r1, c0:c1]))
    if len(rr) == 0:
        rr, cc = np.where(np.isfinite(elev))
        if len(rr) == 0:
            return None
        r_abs, c_abs = rr, cc
    else:
        r_abs, c_abs = rr + r0, cc + c0

    dist = np.hypot(r_abs - row, c_abs - col)
    score = dist * 10_000 + elev[r_abs, c_abs]
    pos = int(np.argmin(score))
    return int(r_abs[pos]), int(c_abs[pos])


def _capacity_limited_mask(
    mask: np.ndarray,
    depth: np.ndarray,
    relative: np.ndarray,
    along_m: np.ndarray,
    dist_m: np.ndarray,
    cell_area: float,
    target_volume_m3: float,
    *,
    segment_m: float = DEFAULT_DOWNSTREAM_SEGMENT_M,
) -> np.ndarray:
    """沿下游逐段填水,每段內再由低 relative 到高 relative 選格。"""
    rr, cc = np.where(mask & (depth > 0) & np.isfinite(along_m))
    if len(rr) == 0 or target_volume_m3 <= 0:
        return np.zeros_like(mask)

    volumes = depth[rr, cc] * cell_area
    total = float(volumes.sum())
    if total <= target_volume_m3:
        return mask & (depth > 0)

    segment = np.floor(np.maximum(along_m[rr, cc], 0.0) / max(segment_m, 1.0))
    order = np.lexsort((dist_m[rr, cc], relative[rr, cc], segment))
    selected = np.zeros_like(mask)
    used = 0.0
    for idx in order:
        r, c = int(rr[idx]), int(cc[idx])
        selected[r, c] = True
        used += float(volumes[idx])
        if used >= target_volume_m3:
            break
    return selected


def _downstream_flow_path_mask(
    traversable: np.ndarray,
    elev: np.ndarray,
    along_m: np.ndarray,
    seed: tuple[int, int],
    *,
    rise_tolerance_m: float = DEFAULT_FLOW_PATH_RISE_TOLERANCE_M,
) -> np.ndarray:
    """從 seed 往下游追蹤較低或近似等高的流經格。"""
    h, w = traversable.shape
    out = np.zeros_like(traversable)
    if not traversable[seed] or not np.isfinite(elev[seed]):
        return out

    stack = [seed]
    out[seed] = True
    while stack:
        r, c = stack.pop()
        current_elev = float(elev[r, c])
        current_along = float(along_m[r, c]) if np.isfinite(along_m[r, c]) else -np.inf
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if not (0 <= nr < h and 0 <= nc < w):
                    continue
                if out[nr, nc] or not traversable[nr, nc] or not np.isfinite(elev[nr, nc]):
                    continue
                next_along = float(along_m[nr, nc]) if np.isfinite(along_m[nr, nc]) else -np.inf
                if next_along + 1e-6 < current_along:
                    continue
                if float(elev[nr, nc]) > current_elev + rise_tolerance_m:
                    continue
                out[nr, nc] = True
                stack.append((nr, nc))
    return out


def _flood_mask_depth_volume(
    traversable: np.ndarray,
    relative: np.ndarray,
    seed: tuple[int, int],
    flood_h: float,
    cell_area: float,
) -> tuple[np.ndarray, np.ndarray, float]:
    """用指定 flood_h 產生可達淹水格、深度與估算體積。"""
    floodable = traversable & np.isfinite(relative) & (relative <= flood_h)
    mask = _reachable_floodable_from_seed_8(traversable, floodable, seed)
    depth = np.where(mask, np.clip(flood_h - relative, 0, None), 0.0)
    return mask, depth, float(depth.sum() * cell_area)


def _solve_flood_h_for_volume(
    traversable: np.ndarray,
    relative: np.ndarray,
    seed: tuple[int, int],
    cell_area: float,
    target_volume_m3: float,
    *,
    max_h: float = DEFAULT_FLOOD_H_MAX_M,
    steps: int = DEFAULT_FLOOD_H_SOLVER_STEPS,
) -> tuple[float, np.ndarray, np.ndarray, float]:
    """以容量反推 flood_h;若 max_h 仍裝不下,回傳 max_h 的結果。"""
    empty = np.zeros_like(traversable, dtype=bool)
    empty_depth = np.zeros_like(relative, dtype=float)
    if target_volume_m3 <= 0 or cell_area <= 0:
        return 0.0, empty, empty_depth, 0.0

    high_mask, high_depth, high_volume = _flood_mask_depth_volume(
        traversable, relative, seed, max_h, cell_area
    )
    if high_volume <= target_volume_m3:
        return max_h, high_mask, high_depth, high_volume

    low = 0.0
    high = max_h
    best_h = high
    best_mask = high_mask
    best_depth = high_depth
    best_volume = high_volume
    for _ in range(steps):
        mid = (low + high) / 2.0
        mask, depth, volume = _flood_mask_depth_volume(
            traversable, relative, seed, mid, cell_area
        )
        if volume < target_volume_m3:
            low = mid
        else:
            high = mid
            best_h = mid
            best_mask = mask
            best_depth = depth
            best_volume = volume

    return best_h, best_mask, best_depth, best_volume





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
    east_m = (cell_lon - clon) * 111_320 * math.cos(math.radians(midlat))
    north_m = (cell_lat - clat) * 110_540
    dist_m = np.hypot(east_m, north_m)
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


def _estimate_downstream_candidate(
    lake_id: str,
    volume_m3: float,
    centroid_lonlat: tuple[float, float],
    *,
    reach_km: float,
) -> dict:
    """共用的下游候選淹水格計算;是否容量裁切由呼叫端決定。"""
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

    clon, clat = centroid_lonlat
    rows = np.arange(h)[:, None]
    cols = np.arange(w)[None, :]
    cell_lon = minlon + cols * dlon
    cell_lat = maxlat - rows * dlat
    east_m = (cell_lon - clon) * 111_320 * math.cos(math.radians(midlat))
    north_m = (cell_lat - clat) * 110_540
    dist_m = np.hypot(east_m, north_m)
    in_reach = dist_m <= reach_km * 1000

    dam_row = int(round((maxlat - clat) / dlat))
    dam_col = int(round((clon - minlon) / dlon))
    dam_row = max(0, min(h - 1, dam_row))
    dam_col = max(0, min(w - 1, dam_col))
    seed = _nearest_finite_cell(elev, dam_row, dam_col)

    local_min = _window_min(elev, radius=DEFAULT_DIRECTIONAL_RELATIVE_RADIUS)
    relative = elev - local_min

    if seed is None:
        return {
            "mask": np.zeros_like(elev, dtype=bool),
            "flow_path": np.zeros_like(elev, dtype=bool),
            "depth": np.zeros_like(elev, dtype=float),
            "relative": relative,
            "local_min": local_min,
            "along_m": dist_m,
            "dist_m": dist_m,
            "cell_area": cell_area,
            "flood_h": 0.0,
            "target_volume_m3": volume_m3,
            "estimated_volume_m3": 0.0,
            "level": 0.0,
            "bbox": (minlon, minlat, maxlon, maxlat),
            "shape": (h, w),
            "dlon": dlon,
            "dlat": dlat,
            "midlat": midlat,
            "centroid": (clon, clat),
        }

    target_lonlat = ((minlon + maxlon) / 2, (minlat + maxlat) / 2)
    target_east_m = (target_lonlat[0] - clon) * 111_320 * math.cos(math.radians(midlat))
    target_north_m = (target_lonlat[1] - clat) * 110_540
    target_dist_m = math.hypot(target_east_m, target_north_m)
    if target_dist_m > 0:
        flow_east = target_east_m / target_dist_m
        flow_north = target_north_m / target_dist_m
        along_m = east_m * flow_east + north_m * flow_north
        downstream = along_m >= -max(abs(dx_m), abs(dy_m)) * DEFAULT_DOWNSTREAM_BACKTRACK_CELLS
    else:
        along_m = dist_m
        downstream = np.ones_like(in_reach, dtype=bool)

    traversable = in_reach & downstream & np.isfinite(elev)
    traversable[seed] = True
    flood_h, mask, depth, estimated_volume_m3 = _solve_flood_h_for_volume(
        traversable, relative, seed, cell_area, volume_m3
    )
    flow_path = _downstream_flow_path_mask(traversable, elev, along_m, seed)
    if mask.any():
        base = float(np.nanmin(local_min[mask]))
    else:
        dam_elev = float(elev[seed])
        base = float(local_min[seed]) if np.isfinite(local_min[seed]) else dam_elev

    return {
        "mask": mask,
        "flow_path": flow_path,
        "depth": depth,
        "relative": relative,
        "local_min": local_min,
        "along_m": along_m,
        "dist_m": dist_m,
        "cell_area": cell_area,
        "flood_h": flood_h,
        "target_volume_m3": volume_m3,
        "estimated_volume_m3": estimated_volume_m3,
        "level": base + flood_h,
        "bbox": (minlon, minlat, maxlon, maxlat),
        "shape": (h, w),
        "dlon": dlon,
        "dlat": dlat,
        "midlat": midlat,
        "centroid": (clon, clat),
    }


def _flood_result_from_mask(ctx: dict, mask: np.ndarray, depth: np.ndarray) -> dict:
    """把 mask/depth 轉成既有 estimate_flood 相容輸出。"""
    minlon, minlat, maxlon, maxlat = ctx["bbox"]
    dlon = ctx["dlon"]
    dlat = ctx["dlat"]
    midlat = ctx["midlat"]
    clon, clat = ctx["centroid"]
    level = float(ctx["level"])

    max_depth = float(depth[mask].max()) if mask.any() else 0.0

    def cell_box(r: int, c: int):
        lon0 = minlon + (c - 0.5) * dlon
        lon1 = minlon + (c + 0.5) * dlon
        lat_center = maxlat - r * dlat
        lat0 = lat_center - dlat / 2
        lat1 = lat_center + dlat / 2
        return box(lon0, lat0, lon1, lat1)

    boxes = [cell_box(r, c) for r, c in np.argwhere(mask)]
    if not boxes:
        poly = {"type": "FeatureCollection", "features": []}
        return {
            "polygon": poly,
            "max_depth_m": 0.0,
            "arrival_minutes": None,
            "cells": 0,
            "level_m": round(level, 1),
        }

    merged = unary_union(boxes).simplify(dlon / 3, preserve_topology=True)
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
            "properties": {
                "flood_level_m": round(level, 1),
                "max_depth_m": round(max_depth, 1),
            },
        },
        "max_depth_m": round(max_depth, 1),
        "arrival_minutes": arrival_min,
        "cells": int(mask.sum()),
        "level_m": round(level, 1),
    }


def estimate_flood_impact_area(
    lake_id: str,
    volume_m3: float,
    centroid_lonlat: tuple[float, float],
    *,
    reach_km: float = 15.0,
) -> dict:
    """測試版:回傳未經容量裁切的可能下游影響範圍,包含水流經過格。"""
    ctx = _estimate_downstream_candidate(
        lake_id,
        volume_m3,
        centroid_lonlat,
        reach_km=reach_km,
    )
    mask = ctx["mask"] | ctx["flow_path"]
    depth = np.where(ctx["mask"], ctx["depth"], 0.0)
    return _flood_result_from_mask(ctx, mask, depth)


def estimate_flood_directional(
    lake_id: str,
    volume_m3: float,
    centroid_lonlat: tuple[float, float],
    *,
    reach_km: float = 15.0,
) -> dict:
    """實驗版:容量限制後的下游淹水範圍。"""
    ctx = _estimate_downstream_candidate(
        lake_id,
        volume_m3,
        centroid_lonlat,
        reach_km=reach_km,
    )
    mask = _capacity_limited_mask(
        ctx["mask"],
        ctx["depth"],
        ctx["relative"],
        ctx["along_m"],
        ctx["dist_m"],
        ctx["cell_area"],
        volume_m3,
    )
    depth = np.where(mask, ctx["depth"], 0.0)
    return _flood_result_from_mask(ctx, mask, depth)

