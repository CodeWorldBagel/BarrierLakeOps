"""Derive a downstream DEM bounding box from a lake centroid.

Used by both the offline prep script and the runtime MinIO sync task.
"""

from __future__ import annotations

import math
import time

import httpx
import numpy as np

_RADIUS_DEG = 0.18       # ~20 km search box
_REACH_KM = 20.0
_PADDING_DEG = 0.04
_RISE_TOLERANCE_M = 8.0
_GRID = 40


def normalize_bbox(value: object) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        bbox = [float(v) for v in value]
    except (TypeError, ValueError):
        return None
    minlon, minlat, maxlon, maxlat = bbox
    if minlon >= maxlon or minlat >= maxlat:
        return None
    return bbox


def _fetch_elevation_grid(bbox: list[float], grid: int = _GRID) -> np.ndarray:
    minlon, minlat, maxlon, maxlat = bbox
    lons = [minlon + (maxlon - minlon) * i / (grid - 1) for i in range(grid)]
    lats = list(reversed([minlat + (maxlat - minlat) * j / (grid - 1) for j in range(grid)]))
    elev: list[list] = [[None] * grid for _ in range(grid)]
    points = [(j, i, lats[j], lons[i]) for j in range(grid) for i in range(grid)]
    with httpx.Client(timeout=30) as client:
        for k in range(0, len(points), 100):
            batch = points[k: k + 100]
            locs = "|".join(f"{p[2]:.6f},{p[3]:.6f}" for p in batch)
            resp = client.get(
                "https://api.opentopodata.org/v1/srtm30m",
                params={"locations": locs},
            )
            resp.raise_for_status()
            for p, res in zip(batch, resp.json()["results"]):
                elev[p[0]][p[1]] = res.get("elevation")
            time.sleep(1.1)
    return np.array(
        [[(v if v is not None else np.nan) for v in row] for row in elev],
        dtype="float32",
    )


def _nearest_finite_cell(
    elev: np.ndarray, row: int, col: int, radius: int = 5
) -> tuple[int, int] | None:
    h, w = elev.shape
    best: tuple[float, int, int] | None = None
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            rr, cc = row + dr, col + dc
            if not (0 <= rr < h and 0 <= cc < w) or not np.isfinite(elev[rr, cc]):
                continue
            cand = (math.hypot(dr, dc), rr, cc)
            if best is None or cand < best:
                best = cand
    return None if best is None else (best[1], best[2])


def _trace_downstream(
    elev: np.ndarray,
    bbox: list[float],
    centroid_lonlat: tuple[float, float],
) -> list[tuple[int, int]]:
    h, w = elev.shape
    minlon, minlat, maxlon, maxlat = bbox
    midlat = (minlat + maxlat) / 2
    dlon = (maxlon - minlon) / (w - 1)
    dlat = (maxlat - minlat) / (h - 1)
    dx_m = abs(dlon * 111_320 * math.cos(math.radians(midlat)))
    dy_m = abs(dlat * 110_540)
    reach_m = _REACH_KM * 1000

    clon, clat = centroid_lonlat
    start_r = max(0, min(h - 1, int(round((maxlat - clat) / dlat))))
    start_c = max(0, min(w - 1, int(round((clon - minlon) / dlon))))
    finite = np.isfinite(elev)
    seed = _nearest_finite_cell(elev, start_r, start_c)
    if seed is None:
        return []

    path: list[tuple[int, int]] = []
    visited: set[tuple[int, int]] = set()
    current = seed
    cumulative_m = 0.0
    for _ in range(h * w):
        r, c = current
        if current in visited or cumulative_m > reach_m:
            break
        visited.add(current)
        path.append(current)
        current_elev = float(elev[r, c])
        best = None
        for radius in range(1, 6):
            candidates = []
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
                    if dz > _RISE_TOLERANCE_M:
                        continue
                    slope = dz / step_m
                    candidates.append((slope + max(dz, 0.0) * 0.02, float(elev[nr, nc]), step_m, nr, nc))
            if candidates:
                best = min(candidates, key=lambda item: (item[0], item[1], item[2]))
                if best[1] <= current_elev or radius > 1:
                    break
        if best is None:
            break
        _, _, step_m, nr, nc = best
        cumulative_m += step_m
        current = (nr, nc)
    return path


def derive_downstream_bbox(
    lon: float, lat: float, *, lake_id: str = ""
) -> list[float] | None:
    """Derive a downstream bounding box from a lake centroid using SRTM DEM.

    Returns [minlon, minlat, maxlon, maxlat] or None if derivation fails.
    Blocks on network I/O — wrap with asyncio.to_thread when calling from async code.
    """
    search_bbox = [
        lon - _RADIUS_DEG, lat - _RADIUS_DEG,
        lon + _RADIUS_DEG, lat + _RADIUS_DEG,
    ]
    elev = _fetch_elevation_grid(search_bbox)
    path = _trace_downstream(elev, search_bbox, (lon, lat))
    if len(path) < 2:
        if lake_id:
            print(f"[dem-bbox] {lake_id}: downstream path too short; skipped")
        return None

    minlon, minlat, maxlon, maxlat = search_bbox
    h, w = elev.shape
    dlon = (maxlon - minlon) / (w - 1)
    dlat = (maxlat - minlat) / (h - 1)
    lons = [minlon + c * dlon for _, c in path]
    lats = [maxlat - r * dlat for r, _ in path]
    derived = [
        max(minlon, min(lons) - _PADDING_DEG),
        max(minlat, min(lats) - _PADDING_DEG),
        min(maxlon, max(lons) + _PADDING_DEG),
        min(maxlat, max(lats) + _PADDING_DEG),
    ]
    if lake_id:
        print(f"[dem-bbox] {lake_id}: derived dem_bbox={derived}")
    return derived
