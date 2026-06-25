"""Path tracing helpers for DEM screening."""

from __future__ import annotations

import math

import numpy as np

from .common import DEFAULT_FLOW_PATH_RISE_TOLERANCE_M

FLOW_PATH_LOCAL_SEARCH_RADIUS_CELLS = 5


def _trace_dem_descent_path(
    elev: np.ndarray,
    finite: np.ndarray,
    dist_m: np.ndarray,
    seed: tuple[int, int],
    dx_m: float,
    dy_m: float,
    reach_m: float,
) -> tuple[np.ndarray, list[tuple[int, int, float]]]:
    """Trace a DEM-only downstream path, allowing small rises to escape pits/flats."""
    h, w = elev.shape
    path = np.zeros_like(elev, dtype=bool)
    path_points: list[tuple[int, int, float]] = []
    visited: set[tuple[int, int]] = set()
    current = seed
    cumulative_m = 0.0

    for _ in range(h * w):
        r, c = current
        if current in visited or cumulative_m > reach_m:
            break
        visited.add(current)
        path[r, c] = True
        path_points.append((r, c, cumulative_m))
        current_elev = float(elev[r, c])
        best: tuple[float, float, float, int, int] | None = None

        for radius in range(1, FLOW_PATH_LOCAL_SEARCH_RADIUS_CELLS + 1):
            candidates: list[tuple[float, float, float, int, int]] = []
            for dr in range(-radius, radius + 1):
                for dc in range(-radius, radius + 1):
                    if dr == 0 and dc == 0:
                        continue
                    if max(abs(dr), abs(dc)) != radius:
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
                    score = (
                        slope
                        + max(dz, 0.0) * 0.02
                        + dist_m[nr, nc] / max(reach_m, 1.0) * 0.01
                    )
                    candidates.append((score, float(elev[nr, nc]), step_m, nr, nc))
            if candidates:
                best = min(candidates, key=lambda item: (item[0], item[1], item[2]))
                if best[1] <= current_elev or radius > 1:
                    break
        if best is None:
            break
        _, _, step_m, nr, nc = best
        cumulative_m += step_m
        current = (nr, nc)

    if not path_points:
        path_points = [(seed[0], seed[1], 0.0)]
        path[seed] = True
    return path, path_points


def _path_distance_fields(
    shape: tuple[int, int],
    path_points: list[tuple[int, int, float]],
    dx_m: float,
    dy_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return nearest distance to routed path and along-path station for each DEM cell."""
    h, w = shape
    rows = np.arange(h)[:, None]
    cols = np.arange(w)[None, :]
    nearest_path_dist = np.full(shape, np.inf, dtype=float)
    along_m = np.full(shape, np.inf, dtype=float)
    for pr, pc, palong in path_points:
        cell_dist = np.hypot((rows - pr) * dy_m, (cols - pc) * dx_m)
        closer = cell_dist < nearest_path_dist
        nearest_path_dist = np.where(closer, cell_dist, nearest_path_dist)
        along_m = np.where(closer, palong, along_m)
    return nearest_path_dist, along_m


