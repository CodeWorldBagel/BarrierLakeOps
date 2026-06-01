"""data.moa adapter — 農業資料開放平臺「國有林堰塞湖資訊」(UnitId=a89)。

授權:政府資料開放授權條款 1.0。
回傳座標為 TWD97 TM2(EPSG:3826),於此 reproject 為 WGS84(lon/lat)。
"""

from __future__ import annotations

import logging
from functools import lru_cache

from pyproj import Transformer

from ..schemas import DataSource
from .http import fetch_json

logger = logging.getLogger("barrier_lake_ops.adapters.moa")

MOA_URL = "https://data.moa.gov.tw/Service/OpenData/DataFileService.aspx"
MOA_UNIT_ID = "a89"

DATA_SOURCE = DataSource(
    source="農業資料開放平臺 — 國有林堰塞湖資訊",
    license="政府資料開放授權條款 1.0",
    attribution="資料來源:農業部林業及自然保育署 / data.moa.gov.tw",
    url="https://data.moa.gov.tw/open_search.aspx?id=a89",
)


@lru_cache
def _transformer() -> Transformer:
    return Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)


def _to_wgs84(x: str | float, y: str | float) -> tuple[float | None, float | None]:
    try:
        lon, lat = _transformer().transform(float(x), float(y))
        return round(lon, 6), round(lat, 6)
    except Exception:  # noqa: BLE001
        return None, None


def _slugify(name: str, seq: str) -> str:
    return f"moa-{seq}"


def _map_status(raw: str | None) -> str:
    """data.moa『狀態』→ catalog 狀態語彙。"""
    s = (raw or "").strip()
    if "解除" in s:
        return "archived"
    if s in ("監測", "監測中", "持續監測"):
        return "monitoring"
    return "monitoring"


class MoaLake:
    """data.moa 一筆國有林堰塞湖(已正規化)。"""

    def __init__(self, raw: dict):
        seq = str(raw.get("序號", "")).strip()
        self.id = _slugify(raw.get("堰塞湖名稱", ""), seq)
        self.name = (raw.get("堰塞湖名稱") or "").strip()
        self.county = (raw.get("縣市") or "").strip()
        self.town = (raw.get("鄉鎮") or "").strip()
        self.formed_at = (raw.get("發生日期") or "").strip() or None
        self.event = (raw.get("事件") or "").strip()
        self.situation = (raw.get("目前狀況") or "").strip()
        self.status_raw = (raw.get("狀態") or "").strip()
        self.status = _map_status(self.status_raw)
        self.updated_at = (raw.get("更新日期") or "").strip() or None
        self.lon, self.lat = _to_wgs84(raw.get("X"), raw.get("Y"))


async def fetch_moa_lakes() -> list[MoaLake]:
    """取 data.moa 25 筆國有林堰塞湖。失敗時拋 AdapterError。"""
    data = await fetch_json(
        MOA_URL,
        params={"UnitId": MOA_UNIT_ID},
        ttl=6 * 3600,
        cache_key="moa_a89",
    )
    if not isinstance(data, list):
        from . import AdapterError

        raise AdapterError("data.moa 回應格式非預期")
    return [MoaLake(r) for r in data if (r.get("堰塞湖名稱") or "").strip()]
