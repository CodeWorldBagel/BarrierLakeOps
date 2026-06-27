"""載入 / 驗證 lake_catalog.yaml,並提供查詢。

Lake Catalog 是本元件「不綁定單一事件」的核心:新增堰塞湖只需加一筆 YAML 設定。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .config import BACKEND_DIR, get_settings

CATALOG_PATH = BACKEND_DIR / "lake_catalog.yaml"


class Threshold(BaseModel):
    overflow_elevation_m: float | None = None
    red_alert_headroom_m: float = 20.0
    orange_alert_headroom_m: float = 40.0
    yellow_alert_headroom_m: float = 70.0


class Location(BaseModel):
    centroid: list[float]  # [lon, lat]

    @property
    def lon(self) -> float:
        return self.centroid[0]

    @property
    def lat(self) -> float:
        return self.centroid[1]


class UpstreamWeather(BaseModel):
    cwa_stations: list[str] = Field(default_factory=list)


class ReferenceState(BaseModel):
    """發表 demo 情境基準快照(非即時監測值,輸出會明確標註 stale)。

    堰塞湖即時水位未開放於 open data;此為 submission 主案例情境的文件化基準。
    """

    water_level_m: float | None = None
    storage_million_m3: float | None = None
    observed_at: str | None = None
    note: str | None = None


class Lake(BaseModel):
    id: str
    name_zh: str
    status: str = "monitoring"
    formed_at: str | None = None
    location: Location
    threshold: Threshold = Field(default_factory=Threshold)
    upstream_weather: UpstreamWeather = Field(default_factory=UpstreamWeather)
    downstream_dem_bbox: list[float] | None = None  # [min_lon,min_lat,max_lon,max_lat]
    moa_dataset_id: str | None = None
    reference_state: ReferenceState | None = None
    note: str | None = None
    geo_key: str | None = None  # DEM 檔案對應 key(通常為原始英文 id)


class Catalog(BaseModel):
    lakes: list[Lake]

    def get(self, lake_id: str) -> Lake | None:
        return next((lk for lk in self.lakes if lk.id == lake_id), None)

    def filter(self, status_filter: str = "all") -> list[Lake]:
        if status_filter == "all":
            return list(self.lakes)
        return [lk for lk in self.lakes if lk.status == status_filter]


def _make_lake_id(name_zh: str | None, formed_at: str | None) -> str:
    import re
    year = (formed_at or "")[:4] or "unknown"
    name = re.sub(r"堰塞湖", "", name_zh or "")
    name = re.sub(r"[()（）]", "", name).strip()
    return f"{name}-{year}"


def _merge_defaults(raw: dict[str, Any]) -> dict[str, Any]:
    defaults = raw.get("defaults", {}) or {}
    default_threshold = defaults.get("threshold", {}) or {}
    lakes = []
    for lk in raw.get("lakes", []):
        th = {**default_threshold, **(lk.get("threshold") or {})}
        if not lk.get("id"):
            lk = {**lk, "id": _make_lake_id(lk.get("name_zh"), lk.get("formed_at"))}
        lakes.append({**lk, "threshold": th})
    return {"lakes": lakes}


def _read_catalog(path: str | None = None) -> Catalog:
    p = Path(path) if path else CATALOG_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return Catalog.model_validate(_merge_defaults(raw))


@lru_cache
def _load_catalog_cached(path: str | None = None) -> Catalog:
    return _read_catalog(path)


def load_catalog(path: str | None = None) -> Catalog:
    if get_settings().environment in {"development", "test", "testing"}:
        return _read_catalog(path)
    return _load_catalog_cached(path)


async def load_catalog_async(path: str | None = None) -> Catalog:
    """DB-first: 從 lake_catalog / lake_thresholds / lake_states 重建 Catalog。
    DB 無資料或連線失敗時 fallback 本地 YAML。
    """
    try:
        from .db.engine import SessionLocal
        from .db.models import LakeCatalog, LakeState, LakeThreshold
        from sqlalchemy import select

        async with SessionLocal() as s:
            db_rows = (await s.execute(select(LakeCatalog))).scalars().all()
            if not db_rows:
                return load_catalog(path)
            thr_rows = {
                r.lake_id: r
                for r in (await s.execute(select(LakeThreshold))).scalars().all()
            }
            st_rows = {
                r.lake_id: r
                for r in (await s.execute(select(LakeState))).scalars().all()
            }

        lakes: list[Lake] = []
        for row in db_rows:
            th = thr_rows.get(row.lake_id)
            threshold = Threshold(
                overflow_elevation_m=th.overflow_elevation_m if th else None,
                red_alert_headroom_m=th.red_alert_headroom_m if th else 20.0,
                orange_alert_headroom_m=th.orange_alert_headroom_m if th else 40.0,
                yellow_alert_headroom_m=th.yellow_alert_headroom_m if th else 70.0,
            )
            st = st_rows.get(row.lake_id)
            reference_state = (
                ReferenceState(
                    water_level_m=st.water_level_m,
                    storage_million_m3=st.storage_million_m3,
                    observed_at=st.observed_at,
                    note=st.note,
                ) if st else None
            )
            lakes.append(
                Lake(
                    id=row.lake_id,
                    name_zh=row.name_zh,
                    status=row.status,
                    formed_at=row.formed_at,
                    location=Location(centroid=[row.lon or 0.0, row.lat or 0.0]),
                    threshold=threshold,
                    upstream_weather=UpstreamWeather(
                        cwa_stations=row.cwa_stations or []
                    ),
                    downstream_dem_bbox=row.dem_bbox,
                    moa_dataset_id=row.moa_dataset_id,
                    reference_state=reference_state,
                    note=row.note,
                    geo_key=row.geo_key,
                )
            )
        return Catalog(lakes=lakes)
    except Exception:  # noqa: BLE001
        return load_catalog(path)


def clear_catalog_cache() -> None:
    _load_catalog_cached.cache_clear()
