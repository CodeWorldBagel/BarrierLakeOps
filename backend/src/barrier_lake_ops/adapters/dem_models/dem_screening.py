"""DEM-derived valley corridor screening model."""

from __future__ import annotations

import math

import numpy as np
from .common import (
    DEFAULT_DAM_ANCHOR_RADIUS,
    DEFAULT_DIRECTIONAL_RELATIVE_RADIUS,
    DEFAULT_FLOOD_H_MAX_M,
    _flood_result_from_mask,
    _load_window_min,
    _nearest_finite_cell,
    _reachable_floodable_from_seed_8,
    load_dem_context,
)
from .screening_corridor import SCREENING_EXPANDED_WIDTH_CANDIDATES_M
from .screening_corridor import SCREENING_MIN_FRAGMENT_CELLS
from .screening_corridor import SCREENING_TARGET_PLACED_RATIO
from .screening_corridor import _estimate_dem_valley_width
from .screening_corridor import _solve_screening_corridor_volume
from .screening_envelope import _build_screening_envelope_mask
from .screening_envelope import _union_polygon_geometry
from .screening_path import _path_distance_fields
from .screening_path import _trace_dem_descent_path


def estimate_flood_dem_screening(
    lake_id: str,
    volume_m3: float,
    centroid_lonlat: tuple[float, float],
    *,
    reach_km: float = 20.0,
    max_h: float = DEFAULT_FLOOD_H_MAX_M,
) -> dict:
    """DEM-only screening model for downstream impact envelopes.

    Uses only the dam/lake coordinate, DEM, and released volume. It derives a
    steepest-descent path from the DEM, builds a valley corridor around that
    path using local relative height, then solves a volume-conserving flood
    height inside the reachable corridor.
    """
    dem = load_dem_context(lake_id)
    arr = dem.arr
    h, w = dem.shape
    minlon, minlat, maxlon, maxlat = dem.bbox
    elev = dem.elev
    midlat = dem.midlat
    dlon = dem.dlon
    dlat = dem.dlat
    dx_m = dem.dx_m
    dy_m = dem.dy_m
    cell_area = dem.cell_area_m2

    clon, clat = centroid_lonlat
    rows = np.arange(h)[:, None]
    cols = np.arange(w)[None, :]
    cell_lon = minlon + cols * dlon
    cell_lat = maxlat - rows * dlat
    x_m = (cell_lon - clon) * 111_320 * math.cos(math.radians(midlat))
    y_m = (cell_lat - clat) * 110_540
    dist_m = np.hypot(x_m, y_m)
    finite = np.isfinite(elev)

    dam_row = int(round((maxlat - clat) / dlat))
    dam_col = int(round((clon - minlon) / dlon))
    dam_row = max(0, min(h - 1, dam_row))
    dam_col = max(0, min(w - 1, dam_col))
    seed = _nearest_finite_cell(elev, dam_row, dam_col, radius=max(DEFAULT_DAM_ANCHOR_RADIUS, 5))

    empty_ctx = {
        "bbox": (minlon, minlat, maxlon, maxlat),
        "dlon": dlon,
        "dlat": dlat,
        "midlat": midlat,
        "centroid": centroid_lonlat,
        "level": 0.0,
        "along_m": dist_m,
        "flow_path": np.zeros_like(elev, dtype=bool),
    }
    if seed is None or volume_m3 <= 0 or cell_area <= 0:
        empty = np.zeros_like(elev, dtype=bool)
        res = _flood_result_from_mask(empty_ctx, empty, np.zeros_like(elev, dtype=float))
        return {**res, "envelope": res["polygon"], "volume_placed_m3": 0.0, "warnings": ["DEM 資料不足或潰壩體積為 0"]}

    reach_m = reach_km * 1000
    path, path_points = _trace_dem_descent_path(
        elev, finite, dist_m, seed, dx_m, dy_m, reach_m
    )

    original_path = path.copy()
    if len(path_points) > 1:
        dense_path = np.zeros_like(path)
        dense_points: list[tuple[int, int, float]] = []
        for idx, (r1, c1, along1) in enumerate(path_points):
            if idx == 0:
                dense_path[r1, c1] = True
                dense_points.append((r1, c1, along1))
                continue

            r0, c0, along0 = path_points[idx - 1]
            dr = r1 - r0
            dc = c1 - c0
            steps = max(abs(dr), abs(dc), 1)
            for step in range(1, steps + 1):
                frac = step / steps
                rr = int(round(r0 + dr * frac))
                cc = int(round(c0 + dc * frac))
                if not (0 <= rr < h and 0 <= cc < w) or not finite[rr, cc]:
                    continue
                along = along0 + (along1 - along0) * frac
                if dense_points and dense_points[-1][0] == rr and dense_points[-1][1] == cc:
                    continue
                dense_path[rr, cc] = True
                dense_points.append((rr, cc, along))

        if dense_points:
            path = dense_path
            path_points = dense_points
    path_gap_filled_cells = int((path & ~original_path).sum())

    nearest_path_dist, along_m = _path_distance_fields(elev.shape, path_points, dx_m, dy_m)

    local_min = _load_window_min(lake_id, DEFAULT_DIRECTIONAL_RELATIVE_RADIUS)
    relative = elev - local_min
    relative = np.where(path, 0.0, relative)
    vol_million = max(volume_m3 / 1_000_000, 0.0)
    valley_h_m = float(np.clip(4.0 + vol_million / 20.0, 6.0, max_h))
    (
        base_corridor_width_m,
        terrain_width_m,
        volume_based_width_m,
        width_basis,
    ) = _estimate_dem_valley_width(
        finite, relative, nearest_path_dist, dist_m, reach_m, max_h, volume_m3
    )
    target_placed_ratio = SCREENING_TARGET_PLACED_RATIO
    candidate_widths: list[float] = []
    for width in (base_corridor_width_m, *SCREENING_EXPANDED_WIDTH_CANDIDATES_M):
        width = float(max(width, base_corridor_width_m))
        if not any(abs(width - existing) < 1.0 for existing in candidate_widths):
            candidate_widths.append(width)


    def evaluate_width(width_m: float) -> dict:
        traversable = (
            finite
            & (dist_m <= reach_m)
            & np.isfinite(relative)
            & np.isfinite(along_m)
            & (nearest_path_dist <= width_m)
        )
        traversable[seed] = True
        corridor_seed = traversable & ((relative <= valley_h_m) | path)
        corridor = _reachable_floodable_from_seed_8(traversable, corridor_seed, seed)
        if not corridor.any():
            corridor = _reachable_floodable_from_seed_8(traversable, traversable, seed)

        flood_h, mask, depth, placed_m3 = _solve_screening_corridor_volume(
            traversable, corridor, relative, path, seed, cell_area, volume_m3, max_h
        )
        envelope_mask = _reachable_floodable_from_seed_8(
            traversable,
            corridor & ((relative <= max(valley_h_m, flood_h)) | path),
            seed,
        )
        placed_ratio = placed_m3 / volume_m3 if volume_m3 > 0 else 0.0
        return {
            "width_m": width_m,
            "traversable": traversable,
            "corridor": corridor,
            "flood_h": flood_h,
            "mask": mask,
            "depth": depth,
            "placed_m3": placed_m3,
            "placed_ratio": placed_ratio,
            "envelope_mask": envelope_mask,
        }

    def remove_tiny_screening_fragments(
        mask_in: np.ndarray,
        keep_mask: np.ndarray,
        *,
        min_cells: int = SCREENING_MIN_FRAGMENT_CELLS,
    ) -> tuple[np.ndarray, int]:
        """Remove only tiny display fragments; keep anything on the routed path."""
        out = mask_in.copy()
        seen = np.zeros_like(mask_in, dtype=bool)
        removed = 0
        hh, ww = mask_in.shape
        for sr, sc in np.argwhere(mask_in):
            sr_i, sc_i = int(sr), int(sc)
            if seen[sr_i, sc_i]:
                continue
            stack = [(sr_i, sc_i)]
            seen[sr_i, sc_i] = True
            cells: list[tuple[int, int]] = []
            touches_keep = False
            while stack:
                r, c = stack.pop()
                cells.append((r, c))
                touches_keep = touches_keep or bool(keep_mask[r, c])
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = r + dr, c + dc
                    if not (0 <= nr < hh and 0 <= nc < ww):
                        continue
                    if seen[nr, nc] or not mask_in[nr, nc]:
                        continue
                    seen[nr, nc] = True
                    stack.append((nr, nc))
            if len(cells) < min_cells and not touches_keep:
                for r, c in cells:
                    out[r, c] = False
                removed += len(cells)
        return out, removed

    attempts = [evaluate_width(width) for width in candidate_widths]
    selected = attempts[-1]
    for attempt in attempts:
        if attempt["placed_ratio"] >= target_placed_ratio:
            selected = attempt
            break

    corridor_width_m = float(selected["width_m"])
    flood_h = float(selected["flood_h"])
    mask = selected["mask"]
    depth = selected["depth"]
    (
        envelope_mask,
        envelope_h_m,
        envelope_buffer_m,
        envelope_buffer_cells,
        flow_corridor_width_m,
    ) = _build_screening_envelope_mask(
        mask=mask,
        path=path,
        traversable=selected["traversable"],
        relative=relative,
        nearest_path_dist=nearest_path_dist,
        seed=seed,
        flood_h=flood_h,
        valley_h_m=valley_h_m,
        corridor_width_m=corridor_width_m,
        max_h=max_h,
        dx_m=dx_m,
        dy_m=dy_m,
    )
    mask, removed_mask_fragment_cells = remove_tiny_screening_fragments(mask, path)
    envelope_mask, removed_envelope_fragment_cells = remove_tiny_screening_fragments(envelope_mask, path)
    envelope_mask = envelope_mask | mask
    depth = np.where(mask, depth, 0.0)
    placed_m3 = float(depth.sum() * cell_area)
    placed_ratio = placed_m3 / volume_m3 if volume_m3 > 0 else 0.0

    if mask.any():
        base = float(np.nanmin(local_min[mask]))
    else:
        base = float(elev[seed]) if np.isfinite(elev[seed]) else 0.0

    ctx = {
        "bbox": (minlon, minlat, maxlon, maxlat),
        "dlon": dlon,
        "dlat": dlat,
        "midlat": midlat,
        "centroid": centroid_lonlat,
        "level": base + flood_h,
        "along_m": along_m,
        "flow_path": path,
    }
    capacity_result = _flood_result_from_mask(ctx, mask, depth)
    envelope_depth = np.where(envelope_mask, np.maximum(depth, 0.1), 0.0)
    envelope_result = _flood_result_from_mask(ctx, envelope_mask, envelope_depth)
    _union_polygon_geometry(envelope_result["polygon"], capacity_result["polygon"])

    warnings: list[str] = []
    used_envelope_as_polygon = False
    expanded_corridor = corridor_width_m > base_corridor_width_m + 1.0
    if expanded_corridor:
        warnings.append(
            f"DEM screening corridor 已由 {base_corridor_width_m:.0f}m 自動擴展至 {corridor_width_m:.0f}m"
        )
    if placed_ratio < target_placed_ratio:
        warnings.append(
            f"DEM screening corridor 擴展後仍容量不足,僅容納 {placed_m3/1e6:.1f}/{volume_m3/1e6:.0f}M m³;"
            "主圖層保留容量守恆結果,envelope 僅供保守參考"
        )
    elif placed_ratio < 0.95:
        warnings.append(
            f"DEM screening corridor 可容納約 {placed_ratio:.0%} 釋出量,仍低於完整體積;請保守解讀"
        )
    if len(path_points) < 3:
        warnings.append("DEM 下游流路過短,可能受 DEM 邊界或局部窪地影響")

    result = capacity_result
    return {
        **result,
        "envelope": envelope_result["polygon"],
        "capacity_polygon": capacity_result["polygon"],
        "capacity_max_depth_m": capacity_result["max_depth_m"],
        "capacity_arrival_minutes": capacity_result["arrival_minutes"],
        "volume_placed_m3": placed_m3,
        "volume_placed_ratio": round(placed_ratio, 4),
        "used_envelope_as_polygon": used_envelope_as_polygon,
        "expanded_corridor": expanded_corridor,
        "base_corridor_width_m": round(base_corridor_width_m, 0),
        "volume_based_corridor_width_m": round(volume_based_width_m, 0),
        "terrain_corridor_width_m": round(terrain_width_m, 0),
        "corridor_width_basis": width_basis,
        "corridor_attempts": [
            {
                "width_m": round(float(attempt["width_m"]), 0),
                "volume_placed_ratio": round(float(attempt["placed_ratio"]), 4),
                "volume_placed_m3": round(float(attempt["placed_m3"]), 0),
            }
            for attempt in attempts
        ],
        "warnings": warnings,
        "corridor_width_m": round(corridor_width_m, 0),
        "valley_h_m": round(valley_h_m, 1),
        "envelope_h_m": round(envelope_h_m, 1),
        "envelope_buffer_m": round(envelope_buffer_m, 0),
        "envelope_buffer_cells": envelope_buffer_cells,
        "flow_corridor_width_m": round(flow_corridor_width_m, 0),
        "path_length_m": round(path_points[-1][2], 0),
        "path_gap_filled_cells": path_gap_filled_cells,
        "tiny_fragment_cells_removed": removed_mask_fragment_cells + removed_envelope_fragment_cells,
    }
