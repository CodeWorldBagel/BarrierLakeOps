"""Tool 1 — get_lake_status:堰塞湖即時狀態。

主資料源:data.moa(metadata);情境基準:catalog reference_state。
堰塞湖即時水位未開放於 open data → 明確降級 / 標註 stale(對應 AI 界線「失效降級」「模型透明」)。
"""

from __future__ import annotations

from ..adapters import AdapterError
from ..adapters.moa import DATA_SOURCE as MOA_SOURCE
from ..adapters.moa import fetch_moa_lakes
from ..catalog import load_catalog
from ..schemas import AlertLevel, DataSource, Freshness, LakeStatusOutput
from . import alert_from_headroom, compute_headroom

CATALOG_SOURCE = DataSource(
    source="BarrierLakeOps Lake Catalog",
    license="MIT(本專案設定檔)",
    attribution="警戒門檻、上游雨量站、下游 DEM 範圍由 catalog 維護",
    url="",
)


async def get_lake_status(lake_id: str) -> LakeStatusOutput:
    cat = load_catalog()
    lake = cat.get(lake_id)

    if lake is not None:
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
