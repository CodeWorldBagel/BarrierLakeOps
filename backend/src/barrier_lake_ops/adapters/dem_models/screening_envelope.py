"""Envelope geometry and mask helpers for DEM screening."""

from __future__ import annotations

import math

import numpy as np
from shapely.geometry import mapping, shape

from .common import _reachable_floodable_from_seed_8

ENVELOPE_HEIGHT_MARGIN_M = 3.0
ENVELOPE_BUFFER_MIN_M = 90.0
ENVELOPE_BUFFER_MAX_M = 300.0
ENVELOPE_BUFFER_CORRIDOR_RATIO = 0.08
FLOW_CORRIDOR_MIN_M = 450.0
FLOW_CORRIDOR_MAX_M = 1200.0
FLOW_CORRIDOR_WIDTH_RATIO = 0.2


def _dilate_mask_8(mask: np.ndarray, iterations: int) -> np.ndarray:
    """Expand a raster mask by a small 8-neighbor buffer without wrapping edges."""
    out = mask.copy()
    h, w = out.shape
    for _ in range(max(0, iterations)):
        prev = out.copy()
        for dr in (-1, 0, 1):
            r_src0 = max(0, -dr)
            r_src1 = min(h, h - dr)
            r_dst0 = max(0, dr)
            r_dst1 = min(h, h + dr)
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                c_src0 = max(0, -dc)
                c_src1 = min(w, w - dc)
                c_dst0 = max(0, dc)
                c_dst1 = min(w, w + dc)
                out[r_dst0:r_dst1, c_dst0:c_dst1] |= prev[
                    r_src0:r_src1, c_src0:c_src1
                ]
    return out


def _build_screening_envelope_mask(
    *,
    mask: np.ndarray,
    path: np.ndarray,
    traversable: np.ndarray,
    relative: np.ndarray,
    nearest_path_dist: np.ndarray,
    seed: tuple[int, int],
    flood_h: float,
    valley_h_m: float,
    corridor_width_m: float,
    max_h: float,
    dx_m: float,
    dy_m: float,
) -> tuple[np.ndarray, float, float, int, float]:
    """Build a conservative impact envelope from capacity mask and flow corridor."""
    envelope_h_m = float(
        min(
            max_h,
            max(
                flood_h + ENVELOPE_HEIGHT_MARGIN_M,
                valley_h_m + ENVELOPE_HEIGHT_MARGIN_M,
            ),
        )
    )
    envelope_buffer_m = float(
        min(
            ENVELOPE_BUFFER_MAX_M,
            max(
                ENVELOPE_BUFFER_MIN_M,
                corridor_width_m * ENVELOPE_BUFFER_CORRIDOR_RATIO,
            ),
        )
    )
    cell_step_m = max(min(abs(dx_m), abs(dy_m)), 1.0)
    envelope_buffer_cells = max(1, int(math.ceil(envelope_buffer_m / cell_step_m)))
    flow_corridor_width_m = float(
        min(
            FLOW_CORRIDOR_MAX_M,
            max(FLOW_CORRIDOR_MIN_M, corridor_width_m * FLOW_CORRIDOR_WIDTH_RATIO),
        )
    )

    expanded_mask = _dilate_mask_8(mask, envelope_buffer_cells)
    flow_corridor = (
        traversable
        & (nearest_path_dist <= flow_corridor_width_m)
        & ((relative <= envelope_h_m) | path)
    )
    envelope_candidate = (
        (expanded_mask | flow_corridor)
        & traversable
        & ((relative <= envelope_h_m) | mask | path)
    )
    envelope_mask = _reachable_floodable_from_seed_8(
        traversable, envelope_candidate | mask, seed
    )
    if int(envelope_mask.sum()) <= int(mask.sum()):
        relaxed_flow_corridor = traversable & (
            nearest_path_dist <= flow_corridor_width_m
        )
        envelope_mask = _reachable_floodable_from_seed_8(
            traversable, relaxed_flow_corridor | mask | path, seed
        )
    return (
        envelope_mask | mask,
        envelope_h_m,
        envelope_buffer_m,
        envelope_buffer_cells,
        flow_corridor_width_m,
    )


def _union_polygon_geometry(envelope_polygon: dict, capacity_polygon: dict) -> None:
    """Ensure the displayed envelope geometry covers the capacity polygon."""
    capacity_geom = capacity_polygon.get("geometry")
    envelope_geom = envelope_polygon.get("geometry")
    if capacity_geom and envelope_geom:
        envelope_polygon["geometry"] = mapping(
            shape(envelope_geom).union(shape(capacity_geom))
        )


