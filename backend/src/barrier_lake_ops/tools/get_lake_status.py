"""Tool 1 — get_lake_status:堰塞湖即時狀態。

主資料源:data.moa(metadata);情境基準:catalog reference_state。
堰塞湖即時水位未開放於 open data → 明確降級 / 標註 stale(對應 AI 界線「失效降級」「模型透明」)。
"""

from __future__ import annotations

from sqlalchemy import select

from ..adapters import AdapterError
from ..adapters.moa import DATA_SOURCE as MOA_SOURCE
from ..adapters.moa import fetch_moa_lakes
from ..catalog import ReferenceState, load_catalog
from ..db.engine import SessionLocal
from ..db.models import LakeState, LakeThreshold
from ..db.models import LakeCatalog
from ..schemas import AlertLevel, DataSource, Freshness, LakeStatusOutput
from . import alert_from_headroom, compute_headroom

CATALOG_SOURCE = DataSource(
    source="BarrierLakeOps Lake Catalog",
    license="MIT(本專案設定檔)",
    attribution="警戒門檻、上游雨量站、下游 DEM 範圍由 catalog 維護",
    url="",
)



async def _lake_from_db(session, lake_id: str):
    """從 DB 組裝 catalog.Lake 相容物件（含 threshold/state override）。

    回傳 (lake, state_row, threshold_row)；找不到 lake_id 回傳 (None, None, None)。
    """
    from ..catalog import Lake, Location, Threshold, UpstreamWeather, ReferenceState
    from sqlalchemy import select

    row = (await session.execute(
        select(LakeCatalog).where(LakeCatalog.lake_id == lake_id)
    )).scalar_one_or_none()
    if row is None:
        return None, None, None

    st = (await session.execute(
        select(LakeState).where(LakeState.lake_id == lake_id)
    )).scalar_one_or_none()
    th = (await session.execute(
        select(LakeThreshold).where(LakeThreshold.lake_id == lake_id)
    )).scalar_one_or_none()

    threshold = Threshold(
        overflow_elevation_m=th.overflow_elevation_m if th else None,
        red_alert_headroom_m=th.red_alert_headroom_m if th else 20.0,
        orange_alert_headroom_m=th.orange_alert_headroom_m if th else 40.0,
        yellow_alert_headroom_m=th.yellow_alert_headroom_m if th else 70.0,
    )
    ref_state = None
    if st and (st.water_level_m is not None or st.storage_million_m3 is not None):
        ref_state = ReferenceState(
            water_level_m=st.water_level_m,
            storage_million_m3=st.storage_million_m3,
            observed_at=st.observed_at,
            note=st.note,
        )

    lake = Lake(
        id=row.lake_id,
        name_zh=row.name_zh,
        status=row.status,
        formed_at=row.formed_at,
        location=Location(centroid=[row.lon or 0.0, row.lat or 0.0]),
        threshold=threshold,
        upstream_weather=UpstreamWeather(cwa_stations=row.cwa_stations or []),
        downstream_dem_bbox=row.dem_bbox,
        moa_dataset_id=row.moa_dataset_id,
        reference_state=ref_state,
        note=row.note,
    )
    return lake, st, th

async def _db_overrides(lake_id: str):
    """DB 的水位 / 門檻覆寫(人工維護編輯)。DB 不可用或無資料 → (None, None),fallback catalog。"""
    try:
        async with SessionLocal() as s:
            st = (await s.execute(select(LakeState).where(LakeState.lake_id == lake_id))).scalar_one_or_none()
            th = (await s.execute(select(LakeThreshold).where(LakeThreshold.lake_id == lake_id))).scalar_one_or_none()
            return st, th
    except Exception:  # noqa: BLE001
        return None, None


def _apply_overrides(lake, st, th):
    lake = lake.model_copy(deep=True)
    if st is not None:
        rs = lake.reference_state or ReferenceState()
        if st.water_level_m is not None:
            rs.water_level_m = st.water_level_m
        if st.storage_million_m3 is not None:
            rs.storage_million_m3 = st.storage_million_m3
        if st.observed_at is not None:
            rs.observed_at = st.observed_at
        if st.note is not None:
            rs.note = st.note
        lake.reference_state = rs
    if th is not None:
        t = lake.threshold
        if th.overflow_elevation_m is not None:
            t.overflow_elevation_m = th.overflow_elevation_m
        if th.red_alert_headroom_m is not None:
            t.red_alert_headroom_m = th.red_alert_headroom_m
        if th.orange_alert_headroom_m is not None:
            t.orange_alert_headroom_m = th.orange_alert_headroom_m
        if th.yellow_alert_headroom_m is not None:
            t.yellow_alert_headroom_m = th.yellow_alert_headroom_m
    return lake


async def get_lake_status(lake_id: str) -> LakeStatusOutput:
    # Try DB first
    try:
        async with SessionLocal() as s:
            lake, st, th = await _lake_from_db(s, lake_id)
    except Exception:  # noqa: BLE001
        lake = None

    if lake is not None:
        return _status_from_catalog(lake)

    # fallback: YAML catalog（開發期 DB 未上傳時仍可運作）
    cat = load_catalog()
    lake = cat.get(lake_id)

    if lake is not None:
        st, th = await _db_overrides(lake_id)
        if st is not None or th is not None:
            lake = _apply_overrides(lake, st, th)
        return _status_from_catalog(lake)

    # 不在 catalog → 嘗試 data.moa metadata
    try:
        moa = {lk.id: lk for lk in await fetch_moa_lakes()}
    except AdapterError:
        moa = {}
    ml = moa.get(lake_id)
    if ml is not None:
        return LakeStatusOutput(
            lake_id=ml.id,
            name=ml.name,
            water_level_m=None,
            overflow_threshold_m=None,
            headroom_m=None,
            alert_level=AlertLevel.unknown,
            last_updated=ml.updated_at,
            freshness=Freshness.unavailable,
            note=(
                f"{ml.county}{ml.town} · 事件:{ml.event} · 目前狀況:{ml.situation[:60]}"
                + " | 即時水位未開放於 open data,僅提供 metadata。"
            ),
            data_sources=[MOA_SOURCE],
        )

    # 都查不到
    return LakeStatusOutput(
        lake_id=lake_id,
        name=lake_id,
        alert_level=AlertLevel.unknown,
        freshness=Freshness.unavailable,
        note="查無此堰塞湖(不在 Lake Catalog,也不在 data.moa 清單)。",
        data_sources=[],
    )


def _status_from_catalog(lake) -> LakeStatusOutput:
    rs = lake.reference_state
    headroom = compute_headroom(lake)
    alert = alert_from_headroom(headroom, lake.threshold)

    sources = [CATALOG_SOURCE, MOA_SOURCE]
    if rs is not None:
        # 有情境基準快照(如主案例馬太鞍)
        return LakeStatusOutput(
            lake_id=lake.id,
            name=lake.name_zh,
            water_level_m=rs.water_level_m,
            storage_million_m3=rs.storage_million_m3,
            overflow_threshold_m=lake.threshold.overflow_elevation_m,
            headroom_m=headroom,
            alert_level=alert,
            last_updated=rs.observed_at,
            freshness=Freshness.stale,
            note=rs.note,
            data_sources=sources,
        )

    # 無快照:僅有門檻設定
    return LakeStatusOutput(
        lake_id=lake.id,
        name=lake.name_zh,
        water_level_m=None,
        overflow_threshold_m=lake.threshold.overflow_elevation_m,
        headroom_m=None,
        alert_level=AlertLevel.unknown,
        freshness=Freshness.unavailable,
        note="即時水位未開放於 open data;catalog 僅提供溢流門檻設定。",
        data_sources=sources,
    )
