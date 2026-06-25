"""DEM adapter facade and public model exports."""

from __future__ import annotations

from .dem_models.common import SOURCE, has_dem
from .dem_models.dem_screening import estimate_flood_dem_screening
from .dem_models.mvp import estimate_flood

__all__ = [
    "SOURCE",
    "estimate_flood",
    "estimate_flood_dem_screening",
    "has_dem",
]

# Shared raster/GeoJSON helpers live in dem_models/common.py.
# Deprecated/paused model references live in dem_models/directional.py,
# dem_models/seed_fill.py, and dem_models/v2.py.
