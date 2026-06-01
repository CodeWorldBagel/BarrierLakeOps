"""CWA adapter — 中央氣象署 Opendata。

- O-A0002-001:自動雨量站即時觀測(主)。
- F-D0047-091:鄉鎮天氣預報 12 小時降雨機率(best-effort 補強)。
授權:政府資料開放授權條款 1.0。
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache

from ..config import get_settings
from ..schemas import DataSource
from . import AdapterError
from .http import fetch_json

logger = logging.getLogger("barrier_lake_ops.adapters.cwa")

BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
OBS_DATASET = "O-A0002-001"
FC_DATASET = "F-D0047-091"

SOURCE_OBS = DataSource(
    source="中央氣象署 Opendata O-A0002-001(自動雨量站觀測)",
    license="政府資料開放授權條款 1.0",
    attribution="資料來源:交通部中央氣象署",
    url="https://opendata.cwa.gov.tw/dataset/observation/O-A0002-001",
)
SOURCE_FC = DataSource(
    source="中央氣象署 Opendata F-D0047-091(鄉鎮天氣預報)",
    license="政府資料開放授權條款 1.0",
    attribution="資料來源:交通部中央氣象署",
    url="https://opendata.cwa.gov.tw/dataset/forecast/F-D0047-091",
)


@lru_cache
def _settings():
    return get_settings()


def _f(v) -> float | None:
    try:
        x = float(v)
        return x if x >= 0 else None  # CWA 用 -99/-990 表示無資料
    except (TypeError, ValueError):
        return None


def _haversine_km(lon1, lat1, lon2, lat2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _wgs84(geo: dict) -> tuple[float | None, float | None]:
    for c in geo.get("Coordinates", []):
        if c.get("CoordinateName") == "WGS84":
            return _f(c.get("StationLongitude")), _f(c.get("StationLatitude"))
    return None, None


class RainObs:
    def __init__(self, st: dict):
        self.id = st.get("StationId", "")
        self.name = st.get("StationName", "")
        self.county = (st.get("GeoInfo", {}) or {}).get("CountyName")
        self.town = (st.get("GeoInfo", {}) or {}).get("TownName")
        self.lon, self.lat = _wgs84(st.get("GeoInfo", {}) or {})
        self.obs_time = (st.get("ObsTime", {}) or {}).get("DateTime")
        re = st.get("RainfallElement", {}) or {}
        self.now = _f((re.get("Now") or {}).get("Precipitation"))
        self.r1h = _f((re.get("Past1hr") or {}).get("Precipitation"))
        self.r3h = _f((re.get("Past3hr") or {}).get("Precipitation"))
        self.r24h = _f((re.get("Past24hr") or {}).get("Precipitation"))


async def fetch_rain_obs() -> list[RainObs]:
    key = _settings().cwa_api_key
    if not key:
        raise AdapterError("缺少 CWA_API_KEY")
    data = await fetch_json(
        f"{BASE}/{OBS_DATASET}",
        params={"Authorization": key, "format": "JSON"},
        ttl=600,
        cache_key="cwa_obs_O-A0002-001",
    )
    if not data.get("success") in ("true", True):
        raise AdapterError("CWA 觀測回應 success != true")
    stations = (data.get("records", {}) or {}).get("Station", [])
    out = [RainObs(s) for s in stations]
    return [o for o in out if o.lon is not None and o.lat is not None]


def nearest_stations(
    lon: float, lat: float, stations: list[RainObs], *, k: int = 5, max_km: float = 25.0
) -> list[RainObs]:
    scored = [
        (_haversine_km(lon, lat, s.lon, s.lat), s) for s in stations
    ]
    scored = [(d, s) for d, s in scored if d <= max_km]
    scored.sort(key=lambda x: x[0])
    return [s for _, s in scored[:k]]


async def fetch_town_pop_max(county: str | None, town: str | None) -> float | None:
    """best-effort:抓鄉鎮未來 24h 最大 12 小時降雨機率(%)。失敗回 None。"""
    if not (county and town):
        return None
    key = _settings().cwa_api_key
    try:
        data = await fetch_json(
            f"{BASE}/{FC_DATASET}",
            params={"Authorization": key, "format": "JSON",
                    "ElementName": "12小時降雨機率"},
            ttl=3600,
            cache_key="cwa_fc_F-D0047-091_pop",
        )
        locs = (data.get("records", {}) or {}).get("Locations", [])
        for grp in locs:
            for loc in grp.get("Location", []):
                if loc.get("LocationName") == town:
                    for el in loc.get("WeatherElement", []):
                        if el.get("ElementName") == "12小時降雨機率":
                            vals = []
                            for t in el.get("Time", [])[:2]:  # 未來約 24h
                                for ev in t.get("ElementValue", []):
                                    v = _f(ev.get("ProbabilityOfPrecipitation"))
                                    if v is not None:
                                        vals.append(v)
                            return max(vals) if vals else None
        return None
    except Exception as exc:  # noqa: BLE001
        logger.info("forecast PoP best-effort failed: %s", exc)
        return None
