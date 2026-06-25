"""Shared DEM data loading and raster/GeoJSON helpers for inundation models.

資料源:SRTM 30m(NASA,公有領域),前處理見 scripts/prep_geo.py。
This module intentionally contains only helpers shared by multiple model files.
Model entry points live in their own modules under dem_models/.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from shapely.geometry import box, mapping
from shapely.ops import unary_union

from ...config import get_settings
from ...schemas import DataSource

SOURCE = DataSource(
    source="SRTM 30m 數值高程(NASA,公有領域)via opentopodata",
    license="Public Domain(NASA SRTM)",
    attribution="DEM: NASA SRTM 30m;生產環境建議改用國土測繪中心 20m DEM",
    url="https://www.opentopodata.org/datasets/srtm/",
)


@dataclass(frozen=True)
class DemGridContext:
    arr: np.ndarray
    meta: dict
    elev: np.ndarray
    bbox: tuple[float, float, float, float]
    dlon: float
    dlat: float
    midlat: float
    dx_m: float
    dy_m: float
    cell_area_m2: float

    @property
    def shape(self) -> tuple[int, int]:
        return self.arr.shape

    def contains_lonlat(self, lon: float, lat: float) -> bool:
        minlon, minlat, maxlon, maxlat = self.bbox
        return minlon <= lon <= maxlon and minlat <= lat <= maxlat

    def lonlat_to_row_col(self, lon: float, lat: float) -> tuple[int, int]:
        h, w = self.shape
        minlon, _minlat, _maxlon, maxlat = self.bbox
        row = int(round((maxlat - lat) / self.dlat))
        col = int(round((lon - minlon) / self.dlon))
        return max(0, min(h - 1, row)), max(0, min(w - 1, col))

    def distance_from_centroid_m(
        self,
        lon: float,
        lat: float,
        centroid_lonlat: tuple[float, float],
    ) -> float:
        clon, clat = centroid_lonlat
        return math.hypot(
            (lon - clon) * 111_320 * math.cos(math.radians(self.midlat)),
            (lat - clat) * 110_540,
        )


DEFAULT_DAM_ANCHOR_RADIUS = 12
DEFAULT_DIRECTIONAL_RELATIVE_RADIUS = 6
# DEFAULT_DOWNSTREAM_BACKTRACK_CELLS = 2
DEFAULT_FLOW_PATH_RISE_TOLERANCE_M = 8.0
DEFAULT_FLOW_PATH_SEARCH_RADIUS_CELLS = 12
DEFAULT_FLOOD_H_MAX_M = 15.0
DEFAULT_FLOOD_H_SOLVER_STEPS = 28
DEFAULT_WINDOW_MIN_RADIUS = 6


@lru_cache
def _dem_dir() -> Path:
    return get_settings().data_dir / "dem"


def has_dem(lake_id: str) -> bool:
    dem_dir = _dem_dir()
    return (dem_dir / f"{lake_id}.npy").exists() and (dem_dir / f"{lake_id}.json").exists()


@lru_cache(maxsize=32)
def load_dem(lake_id: str):
    arr = np.load(_dem_dir() / f"{lake_id}.npy")
    meta = json.loads((_dem_dir() / f"{lake_id}.json").read_text(encoding="utf-8"))
    return arr, meta


def _load(lake_id: str):
    return load_dem(lake_id)


@lru_cache(maxsize=32)
def load_dem_context(lake_id: str) -> DemGridContext:
    arr, meta = load_dem(lake_id)
    h, w = arr.shape
    minlon, minlat, maxlon, maxlat = tuple(float(v) for v in meta["bbox"])
    elev = np.where(np.isnan(arr), np.inf, arr)
    midlat = (minlat + maxlat) / 2
    dlon = (maxlon - minlon) / (w - 1)
    dlat = (maxlat - minlat) / (h - 1)
    dx_m = dlon * 111_320 * math.cos(math.radians(midlat))
    dy_m = dlat * 110_540
    return DemGridContext(
        arr=arr,
        meta=meta,
        elev=elev,
        bbox=(minlon, minlat, maxlon, maxlat),
        dlon=dlon,
        dlat=dlat,
        midlat=midlat,
        dx_m=dx_m,
        dy_m=dy_m,
        cell_area_m2=abs(dx_m * dy_m),
    )


def clear_dem_cache() -> None:
    load_dem.cache_clear()
    load_dem_context.cache_clear()
    cache_clear = getattr(_dem_dir, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


def _window_min(arr: np.ndarray, radius: int = DEFAULT_WINDOW_MIN_RADIUS) -> np.ndarray:
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
        return mask
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
    """Return 8-connected floodable cells reachable from seed through traversable cells."""
    h, w = traversable.shape
    out = np.zeros_like(traversable, dtype=bool)
    if not (0 <= seed[0] < h and 0 <= seed[1] < w):
        return out
    if not traversable[seed]:
        return out
    stack = [seed]
    seen = np.zeros_like(traversable, dtype=bool)
    seen[seed] = True
    while stack:
        r, c = stack.pop()
        if floodable[r, c]:
            out[r, c] = True
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if not (0 <= nr < h and 0 <= nc < w):
                    continue
                if seen[nr, nc] or not traversable[nr, nc]:
                    continue
                if not floodable[nr, nc]:
                    continue
                seen[nr, nc] = True
                stack.append((nr, nc))
    return out


def _nearest_finite_cell(
    elev: np.ndarray,
    row: int,
    col: int,
    *,
    radius: int = DEFAULT_DAM_ANCHOR_RADIUS,
) -> tuple[int, int] | None:
    """Find the nearest finite DEM cell around a requested row/col."""
    h, w = elev.shape
    row = max(0, min(h - 1, row))
    col = max(0, min(w - 1, col))
    if np.isfinite(elev[row, col]):
        return row, col
    best: tuple[float, int, int] | None = None
    for rr in range(max(0, row - radius), min(h, row + radius + 1)):
        for cc in range(max(0, col - radius), min(w, col + radius + 1)):
            if not np.isfinite(elev[rr, cc]):
                continue
            d2 = float((rr - row) ** 2 + (cc - col) ** 2)
            if best is None or d2 < best[0]:
                best = (d2, rr, cc)
    return None if best is None else (best[1], best[2])


def _estimate_arrival_minutes(mask: np.ndarray, along_m: np.ndarray | None) -> int | None:
    if not mask.any() or along_m is None:
        return None
    values = along_m[mask]
    values = values[np.isfinite(values)]
    if values.size == 0:
        return None
    far_m = float(values.max())
    return int(far_m / 4.0 / 60) if far_m > 0 else None


def _downstream_flow_path_mask(
    elev: np.ndarray,
    finite: np.ndarray,
    seed: tuple[int, int],
    dist_m: np.ndarray,
    dx_m: float,
    dy_m: float,
    reach_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Approximate a downstream path by repeatedly selecting nearby lower DEM cells."""
    h, w = elev.shape
    path = np.zeros_like(elev, dtype=bool)
    along_m = np.full_like(elev, np.inf, dtype=float)
    current = seed
    visited: set[tuple[int, int]] = set()
    cumulative_m = 0.0

    for _ in range(h * w):
        r, c = current
        if current in visited or cumulative_m > reach_m:
            break
        visited.add(current)
        path[r, c] = True
        along_m[r, c] = cumulative_m
        current_elev = float(elev[r, c])
        best: tuple[float, float, float, int, int] | None = None
        for radius in range(1, DEFAULT_FLOW_PATH_SEARCH_RADIUS_CELLS + 1):
            candidates: list[tuple[float, float, float, int, int]] = []
            for dr in range(-radius, radius + 1):
                for dc in range(-radius, radius + 1):
                    if dr == 0 and dc == 0 or max(abs(dr), abs(dc)) != radius:
                        continue
                    nr, nc = r + dr, c + dc
                    if not (0 <= nr < h and 0 <= nc < w):
                        continue
                    if (nr, nc) in visited or not finite[nr, nc]:
                        continue
                    step_m = math.hypot(abs(dr) * dy_m, abs(dc) * dx_m)
                    if step_m <= 0 or cumulative_m + step_m > reach_m:
                        continue
                    dz = float(elev[nr, nc]) - current_elev
                    if dz > DEFAULT_FLOW_PATH_RISE_TOLERANCE_M:
                        continue
                    slope = dz / step_m
                    score = slope + max(dz, 0.0) * 0.02 + dist_m[nr, nc] / max(reach_m, 1.0) * 0.01
                    candidates.append((score, float(elev[nr, nc]), step_m, nr, nc))
            if candidates:
                best = min(candidates, key=lambda item: (item[0], item[1], item[2]))
                break
        if best is None:
            break
        _, _, step_m, nr, nc = best
        cumulative_m += step_m
        current = (nr, nc)
    return path, along_m


def _solve_flood_h_for_volume(
    candidate: np.ndarray,
    relative: np.ndarray,
    cell_area: float,
    volume_m3: float,
    *,
    max_h: float = DEFAULT_FLOOD_H_MAX_M,
) -> tuple[float, np.ndarray, np.ndarray, float]:
    empty = np.zeros_like(candidate, dtype=bool)
    empty_depth = np.zeros_like(relative, dtype=float)
    if not candidate.any() or volume_m3 <= 0 or cell_area <= 0:
        return 0.0, empty, empty_depth, 0.0

    high_depth = np.where(candidate, np.clip(max_h - relative, 0, None), 0.0)
    high_volume = float(high_depth.sum() * cell_area)
    if high_volume <= volume_m3:
        return max_h, candidate.copy(), high_depth, high_volume

    low = 0.0
    high = max_h
    best_h = 0.0
    best_mask = empty
    best_depth = empty_depth
    best_volume = 0.0
    for _ in range(DEFAULT_FLOOD_H_SOLVER_STEPS):
        mid = (low + high) / 2.0
        depth = np.where(candidate, np.clip(mid - relative, 0, None), 0.0)
        volume = float(depth.sum() * cell_area)
        if volume < volume_m3:
            low = mid
        else:
            high = mid
            best_h = mid
            best_mask = candidate & (relative <= mid)
            best_depth = depth
            best_volume = volume
    return best_h, best_mask, best_depth, best_volume


def _flood_mask_depth_volume(
    traversable: np.ndarray,
    relative: np.ndarray,
    seed: tuple[int, int],
    cell_area: float,
    volume_m3: float,
) -> tuple[float, np.ndarray, np.ndarray, float]:
    candidate = _reachable_floodable_from_seed_8(traversable, traversable, seed)
    return _solve_flood_h_for_volume(candidate, relative, cell_area, volume_m3)


def _cell_box(meta: dict, r: int, c: int):
    minlon, _minlat, _maxlon, maxlat = meta["bbox"]
    dlon = meta["dlon"]
    dlat = meta["dlat"]
    lon0 = minlon + (c - 0.5) * dlon
    lon1 = minlon + (c + 0.5) * dlon
    lat_center = maxlat - r * dlat
    lat0 = lat_center - dlat / 2
    lat1 = lat_center + dlat / 2
    return box(lon0, lat0, lon1, lat1)


def _flood_result_from_mask(ctx: dict, mask: np.ndarray, depth: np.ndarray) -> dict:
    boxes = [_cell_box(ctx, int(r), int(c)) for r, c in np.argwhere(mask)]
    level = float(ctx.get("level", 0.0))
    if not boxes:
        poly = {"type": "FeatureCollection", "features": []}
        return {
            "polygon": poly,
            "max_depth_m": 0.0,
            "arrival_minutes": None,
            "cells": 0,
            "level_m": round(level, 1),
        }

    dlon = float(ctx["dlon"])
    merged = unary_union(boxes).simplify(dlon / 3, preserve_topology=True)
    max_depth = float(depth[mask].max()) if mask.any() else 0.0
    arrival_min = _estimate_arrival_minutes(mask, ctx.get("along_m"))
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
