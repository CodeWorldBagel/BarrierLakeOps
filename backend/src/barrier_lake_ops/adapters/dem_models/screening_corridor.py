"""Corridor sizing and volume-fill helpers for DEM screening."""

from __future__ import annotations

import heapq
import math

import numpy as np

from .common import DEFAULT_FLOOD_H_SOLVER_STEPS

SCREENING_MIN_WET_DEPTH_M = 0.25
SCREENING_RELATIVE_PRIORITY_WEIGHT = 6.0
SCREENING_PATH_PRIORITY_BONUS = -2.0
VOLUME_BASED_WIDTH_OFFSET_M = 250.0
VOLUME_BASED_WIDTH_SCALE_M = 70.0
VOLUME_BASED_WIDTH_MIN_M = 300.0
VOLUME_BASED_WIDTH_MAX_M = 1200.0
VALLEY_WIDTH_SEARCH_M = 4000.0
VALLEY_WIDTH_MIN_CANDIDATE_CELLS = 10
VALLEY_WIDTH_PERCENTILE = 90
CORRIDOR_WIDTH_MIN_M = 300.0
CORRIDOR_WIDTH_MAX_M = 4000.0
SCREENING_TARGET_PLACED_RATIO = 0.8
SCREENING_EXPANDED_WIDTH_CANDIDATES_M = (1500.0, 2500.0, 4000.0)
SCREENING_MIN_FRAGMENT_CELLS = 3


def _estimate_dem_valley_width(
    finite: np.ndarray,
    relative: np.ndarray,
    nearest_path_dist: np.ndarray,
    dist_m: np.ndarray,
    reach_m: float,
    max_h: float,
    volume_m3: float,
) -> tuple[float, float, float, str]:
    """Estimate first-pass corridor width from terrain, with volume formula fallback."""
    vol_million = max(volume_m3 / 1_000_000, 0.0)
    volume_based_width_m = float(
        np.clip(
            VOLUME_BASED_WIDTH_OFFSET_M
            + math.sqrt(vol_million) * VOLUME_BASED_WIDTH_SCALE_M,
            VOLUME_BASED_WIDTH_MIN_M,
            VOLUME_BASED_WIDTH_MAX_M,
        )
    )
    valley_width_search_m = VALLEY_WIDTH_SEARCH_M
    valley_width_candidates = (
        finite
        & np.isfinite(relative)
        & np.isfinite(nearest_path_dist)
        & (dist_m <= reach_m)
        & (nearest_path_dist <= valley_width_search_m)
        & (relative <= max_h)
    )
    candidate_distances = nearest_path_dist[valley_width_candidates]
    if candidate_distances.size >= VALLEY_WIDTH_MIN_CANDIDATE_CELLS:
        terrain_width_m = float(
            np.percentile(candidate_distances, VALLEY_WIDTH_PERCENTILE) * 2.0
        )
        width_basis = "dem_valley_p90"
    else:
        terrain_width_m = volume_based_width_m
        width_basis = "volume_fallback"
    base_width_m = float(
        np.clip(
            max(terrain_width_m, volume_based_width_m),
            CORRIDOR_WIDTH_MIN_M,
            CORRIDOR_WIDTH_MAX_M,
        )
    )
    return base_width_m, terrain_width_m, volume_based_width_m, width_basis


def _solve_screening_corridor_volume(
    traversable: np.ndarray,
    corridor: np.ndarray,
    relative: np.ndarray,
    path: np.ndarray,
    seed: tuple[int, int],
    cell_area: float,
    volume_m3: float,
    limit_h: float,
) -> tuple[float, np.ndarray, np.ndarray, float]:
    """Progressively fill reachable DEM cells from seed under a volume budget."""
    empty = np.zeros_like(relative, dtype=bool)
    empty_depth = np.zeros_like(relative, dtype=float)
    if not corridor.any() or volume_m3 <= 0 or cell_area <= 0:
        return 0.0, empty, empty_depth, 0.0

    h, w = relative.shape
    if not (0 <= seed[0] < h and 0 <= seed[1] < w) or not traversable[seed]:
        return 0.0, empty, empty_depth, 0.0

    candidate = traversable & corridor & (np.isfinite(relative)) & (relative <= limit_h)
    candidate |= path & traversable
    if not candidate[seed]:
        candidate[seed] = True

    min_wet_depth_m = SCREENING_MIN_WET_DEPTH_M
    min_cell_volume_m3 = max(cell_area * min_wet_depth_m, 1.0)
    wet_budget_m3 = max(volume_m3, min_cell_volume_m3)
    footprint = np.zeros_like(relative, dtype=bool)
    queued = np.zeros_like(relative, dtype=bool)
    heap: list[tuple[float, int, int, float]] = [(0.0, seed[0], seed[1], 0.0)]
    queued[seed] = True
    footprint_budget_m3 = 0.0

    while heap and footprint_budget_m3 < wet_budget_m3:
        _priority, r, c, travel_m = heapq.heappop(heap)
        if footprint[r, c] or not candidate[r, c]:
            continue
        footprint[r, c] = True
        footprint_budget_m3 += min_cell_volume_m3

        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if not (0 <= nr < h and 0 <= nc < w):
                    continue
                if queued[nr, nc] or not candidate[nr, nc]:
                    continue
                step_m = math.hypot(abs(dr), abs(dc))
                next_travel_m = travel_m + step_m
                rel_penalty = (
                    max(float(relative[nr, nc]), 0.0)
                    * SCREENING_RELATIVE_PRIORITY_WEIGHT
                )
                path_bonus = SCREENING_PATH_PRIORITY_BONUS if path[nr, nc] else 0.0
                priority = next_travel_m + rel_penalty + path_bonus
                heapq.heappush(heap, (priority, nr, nc, next_travel_m))
                queued[nr, nc] = True

    if not footprint.any():
        return 0.0, empty, empty_depth, 0.0

    high_depth = np.where(footprint, np.clip(limit_h - relative, 0, None), 0.0)
    high_depth = np.where(footprint & (high_depth <= 0), min_wet_depth_m, high_depth)
    high_volume = float(high_depth.sum() * cell_area)
    if high_volume <= volume_m3:
        return limit_h, footprint, high_depth, high_volume

    low = 0.0
    high = limit_h
    best_h = 0.0
    best_depth = empty_depth
    best_volume = 0.0
    for _ in range(DEFAULT_FLOOD_H_SOLVER_STEPS):
        mid = (low + high) / 2.0
        depth = np.where(footprint, np.clip(mid - relative, 0, None), 0.0)
        depth = np.where(footprint & (depth <= 0), min_wet_depth_m, depth)
        volume = float(depth.sum() * cell_area)
        if volume < volume_m3:
            low = mid
        else:
            high = mid
            best_h = mid
            best_depth = depth
            best_volume = volume
    if best_volume == 0.0:
        depth = np.where(footprint, min_wet_depth_m, 0.0)
        return min_wet_depth_m, footprint, depth, float(depth.sum() * cell_area)
    return best_h, footprint, best_depth, best_volume


