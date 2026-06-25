"""Shared runtime helpers for inundation tools."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from typing import Any

from ..adapters.dem import estimate_flood_dem_screening

DEFAULT_STORAGE_MILLION_M3 = 20.0
PARTIAL_BREACH_VOLUME_RATIO = 0.5


def resolve_breach_volume_million_m3(
    lake: Any,
    breach_scenario: str,
    override: float | None,
) -> float:
    if override is not None:
        return override
    storage = (
        lake.reference_state.storage_million_m3 if lake.reference_state else None
    ) or DEFAULT_STORAGE_MILLION_M3
    return storage if breach_scenario == "full" else storage * PARTIAL_BREACH_VOLUME_RATIO


@lru_cache(maxsize=64)
def _estimate_flood_dem_screening_cached(
    lake_id: str,
    volume_m3: float,
    centroid_lon: float,
    centroid_lat: float,
) -> dict:
    return estimate_flood_dem_screening(lake_id, volume_m3, (centroid_lon, centroid_lat))


def estimate_flood_dem_screening_runtime(
    lake_id: str,
    volume_m3: float,
    centroid_lonlat: tuple[float, float],
) -> dict:
    res = _estimate_flood_dem_screening_cached(
        lake_id,
        float(volume_m3),
        float(centroid_lonlat[0]),
        float(centroid_lonlat[1]),
    )
    return deepcopy(res)


def clear_inundation_runtime_cache() -> None:
    _estimate_flood_dem_screening_cached.cache_clear()
