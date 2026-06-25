"""資料同步:收集器、bootstrap、狀態查詢、人工維護寫入。

分層:
- 排程資料(村里界 / 戶數人口):目前由 prep_geo 產出的本機檔載入 DB(`_load_village_features`
  即未來換成 live 下載的接縫);收集器可由排程或手動觸發。
- 即時(CWA)/靜態(DEM):資訊列,不跑收集器。
- 堰塞湖清單:由組員的 YAML 上傳寫入(此處保留 upload 狀態列)。
- 人工維護(水位 / 門檻):由 API 編輯寫入 lake_states / lake_thresholds 並記錄時間。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .catalog import load_catalog
from .config import get_settings
from .db.models import DatasetSync, LakeState, LakeThreshold, Village

logger = logging.getLogger("barrier_lake_ops.data_sync")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# 頁面顯示的資料集清單(分組依 kind)
DATASETS = [
    {"key": "cwa_rainfall", "label": "上游雨量觀測", "source": "中央氣象署 CWA", "kind": "live"},
    {"key": "cwa_forecast", "label": "鄉鎮天氣預報", "source": "中央氣象署 CWA", "kind": "live"},
    {"key": "lakes_catalog", "label": "堰塞湖清單 + 狀態", "source": "手動上傳 YAML", "kind": "upload"},
    {"key": "population", "label": "村里戶數 / 人口", "source": "內政部戶政司", "kind": "scheduled"},
    {"key": "villages", "label": "村里界", "source": "內政部國土測繪中心", "kind": "scheduled"},
    {"key": "dem", "label": "DEM 高程", "source": "NASA SRTM 30m", "kind": "static"},
]
_META = {d["key"]: d for d in DATASETS}


def _load_village_features() -> list[dict]:
    """收集器的資料來源:prep_geo 產出的本機檔(村里界 + 人口)。"""
    d = get_settings().data_dir / "villages"
    gj = json.loads((d / "villages.geojson").read_text(encoding="utf-8"))
    pop = json.loads((d / "population.json").read_text(encoding="utf-8"))
    rows: list[dict] = []
    for feat in gj.get("features", []):
        props = feat.get("properties", {})
        code = props.get("villcode")
        if not code:
            continue
        p = pop.get(code, {})
        rows.append(
            {
                "village_code": str(code),
                "county": props.get("county"),
                "town": props.get("town"),
                "village": props.get("village"),
                "geometry": feat.get("geometry"),
                "households": int(p.get("households", 0) or 0),
                "population": int(p.get("population", 0) or 0),
                "elderly_65plus": int(p.get("elderly_65plus", 0) or 0),
                "children_under6": int(p.get("children_under6", 0) or 0),
            }
        )
    return rows


async def _upsert_sync(session: AsyncSession, key: str, **fields) -> None:
    meta = _META.get(key, {})
    base = {
        "key": key,
        "label": meta.get("label", key),
        "source": meta.get("source"),
        "kind": meta.get("kind", "scheduled"),
    }
    base.update(fields)
    stmt = pg_insert(DatasetSync).values(**base)
    update_cols = {k: stmt.excluded[k] for k in base if k != "key"}
    await session.execute(
        stmt.on_conflict_do_update(index_elements=["key"], set_=update_cols)
    )


async def ensure_dataset_rows(session: AsyncSession) -> None:
    """確保每個資料集都有一列(live/static/upload 為資訊列)。"""
    existing = set((await session.execute(select(DatasetSync.key))).scalars())
    info = {
        "live": ("ok", "查詢時即時抓取(CWA),不進排程。"),
        "static": ("ok", "地形不變,一次處理。"),
        "upload": ("pending", "由組員的 YAML 上傳寫入。"),
        "manual": ("ok", "應變中心可即時編輯。"),
        "scheduled": ("pending", "等待首次收集。"),
    }
    for d in DATASETS:
        if d["key"] in existing:
            continue
        status, message = info.get(d["kind"], ("pending", None))
        await _upsert_sync(session, d["key"], status=status, message=message)
    # 清掉已不在 registry 的舊狀態列(例如移除的 alert_threshold)
    keys = [d["key"] for d in DATASETS]
    await session.execute(delete(DatasetSync).where(DatasetSync.key.notin_(keys)))
    await session.commit()


def _collect_rows_sync() -> tuple[list[dict], str]:
    """取得村里界 + 人口列:優先 data.gov.tw 即時下載,失敗則 fallback 本機預處理檔。"""
    try:
        from . import live_sources

        return live_sources.fetch_village_rows()
    except Exception as exc:  # noqa: BLE001
        logger.warning("live 下載失敗,改用本機預處理檔: %s", exc)
        return _load_village_features(), "本機預處理檔(live 下載失敗)"


async def collect_villages(session: AsyncSession) -> int:
    """收集村里界 + 人口 → villages 表;更新 villages / population 同步狀態。

    阻塞 I/O(下載 22MB ZIP + 解析 shapefile)以 ``to_thread`` 包起,避免卡事件迴圈。
    """
    started = _now()
    await _upsert_sync(session, "villages", status="running", last_run_at=started)
    await _upsert_sync(session, "population", status="running", last_run_at=started)
    await session.commit()
    try:
        rows, source = await asyncio.to_thread(_collect_rows_sync)
        if rows:
            stmt = pg_insert(Village).values(rows)
            cols = {c: stmt.excluded[c] for c in rows[0] if c != "village_code"}
            await session.execute(
                stmt.on_conflict_do_update(index_elements=["village_code"], set_=cols)
            )
        ts = _now()
        for key in ("villages", "population"):
            await _upsert_sync(
                session, key, status="ok", last_run_at=ts, last_success_at=ts,
                last_changed_at=ts, row_count=len(rows), message=source,
            )
        await session.commit()
        return len(rows)
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        for key in ("villages", "population"):
            await _upsert_sync(session, key, status="error", message=str(exc)[:300])
        await session.commit()
        raise


async def seed_manual(session: AsyncSession) -> None:
    """從 catalog 種子 lake_states / lake_thresholds(僅當對應表為空)。"""
    cat = load_catalog()
    has_state = (await session.execute(select(func.count()).select_from(LakeState))).scalar()
    has_thr = (await session.execute(select(func.count()).select_from(LakeThreshold))).scalar()
    if not has_state:
        for lk in cat.lakes:
            rs = lk.reference_state
            if rs is None:
                continue
            session.add(
                LakeState(
                    lake_id=lk.id, water_level_m=rs.water_level_m,
                    storage_million_m3=rs.storage_million_m3, observed_at=rs.observed_at,
                    note=rs.note, updated_by="系統匯入",
                )
            )
    if not has_thr:
        for lk in cat.lakes:
            th = lk.threshold
            session.add(
                LakeThreshold(
                    lake_id=lk.id, overflow_elevation_m=th.overflow_elevation_m,
                    red_alert_headroom_m=th.red_alert_headroom_m,
                    orange_alert_headroom_m=th.orange_alert_headroom_m,
                    yellow_alert_headroom_m=th.yellow_alert_headroom_m, updated_by="系統匯入",
                )
            )
    await session.commit()


async def _seed_villages_from_files(session: AsyncSession) -> None:
    """啟動快速種子:用本機預處理檔(避免 22MB live 下載拖慢啟動;live 留給排程/手動)。"""
    rows = _load_village_features()
    if rows:
        stmt = pg_insert(Village).values(rows)
        cols = {c: stmt.excluded[c] for c in rows[0] if c != "village_code"}
        await session.execute(
            stmt.on_conflict_do_update(index_elements=["village_code"], set_=cols)
        )
    ts = _now()
    for key in ("villages", "population"):
        await _upsert_sync(
            session, key, status="ok", last_run_at=ts, last_success_at=ts,
            last_changed_at=ts, row_count=len(rows), message="啟動種子(本機檔);排程改 live 下載",
        )
    await session.commit()


async def bootstrap(session: AsyncSession) -> None:
    """啟動時:確保狀態列;DB 空則種子村里(本機檔,快)+ 人工維護。全程 defensive。"""
    try:
        await ensure_dataset_rows(session)
        cnt = (await session.execute(select(func.count()).select_from(Village))).scalar()
        if not cnt:
            await _seed_villages_from_files(session)
        await seed_manual(session)
    except Exception as exc:  # noqa: BLE001
        logger.warning("data_sync bootstrap 降級: %s", exc)


async def run_scheduled(session: AsyncSession) -> dict:
    """排程 / 手動觸發:跑收集器,回傳結果摘要。"""
    n = await collect_villages(session)
    return {"villages": n}


def _state_dict(s: LakeState) -> dict:
    return {
        "lake_id": s.lake_id, "water_level_m": s.water_level_m,
        "storage_million_m3": s.storage_million_m3, "observed_at": s.observed_at,
        "note": s.note, "updated_by": s.updated_by,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _threshold_dict(t: LakeThreshold) -> dict:
    return {
        "lake_id": t.lake_id, "overflow_elevation_m": t.overflow_elevation_m,
        "red_alert_headroom_m": t.red_alert_headroom_m,
        "orange_alert_headroom_m": t.orange_alert_headroom_m,
        "yellow_alert_headroom_m": t.yellow_alert_headroom_m,
        "updated_by": t.updated_by,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


async def get_status(session: AsyncSession) -> dict:
    rows = (await session.execute(select(DatasetSync))).scalars().all()
    order = {d["key"]: i for i, d in enumerate(DATASETS)}
    rows = sorted(rows, key=lambda r: order.get(r.key, 999))
    datasets = [
        {
            "key": r.key, "label": r.label, "source": r.source, "kind": r.kind,
            "status": r.status, "row_count": r.row_count, "message": r.message,
            "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
            "last_success_at": r.last_success_at.isoformat() if r.last_success_at else None,
            "last_changed_at": r.last_changed_at.isoformat() if r.last_changed_at else None,
        }
        for r in rows
    ]
    states = (await session.execute(select(LakeState))).scalars().all()
    thresholds = (await session.execute(select(LakeThreshold))).scalars().all()
    return {
        "datasets": datasets,
        "lake_states": [_state_dict(s) for s in states],
        "lake_thresholds": [_threshold_dict(t) for t in thresholds],
    }


async def update_lake_state(session: AsyncSession, lake_id: str, data: dict, updated_by: str = "應變中心") -> dict:
    keys = ("water_level_m", "storage_million_m3", "observed_at", "note")
    vals = {k: data[k] for k in keys if k in data}
    vals["updated_by"] = updated_by
    stmt = pg_insert(LakeState).values(lake_id=lake_id, **vals)
    await session.execute(
        stmt.on_conflict_do_update(index_elements=["lake_id"], set_={**vals, "updated_at": _now()})
    )
    await _upsert_sync(session, "lake_water_level", status="ok", last_changed_at=_now())
    await session.commit()
    row = (await session.execute(select(LakeState).where(LakeState.lake_id == lake_id))).scalar_one()
    return _state_dict(row)


async def update_lake_threshold(session: AsyncSession, lake_id: str, data: dict, updated_by: str = "應變中心") -> dict:
    keys = ("overflow_elevation_m", "red_alert_headroom_m", "orange_alert_headroom_m", "yellow_alert_headroom_m")
    vals = {k: data[k] for k in keys if k in data}
    vals["updated_by"] = updated_by
    stmt = pg_insert(LakeThreshold).values(lake_id=lake_id, **vals)
    await session.execute(
        stmt.on_conflict_do_update(index_elements=["lake_id"], set_={**vals, "updated_at": _now()})
    )
    await _upsert_sync(session, "alert_threshold", status="ok", last_changed_at=_now())
    await session.commit()
    row = (await session.execute(select(LakeThreshold).where(LakeThreshold.lake_id == lake_id))).scalar_one()
    return _threshold_dict(row)


async def fetch_lake_overrides(session: AsyncSession, lake_id: str):
    """供 get_lake_status 用:DB 的水位 / 門檻覆寫(無則回 None,呼叫端 fallback catalog)。"""
    st = (await session.execute(select(LakeState).where(LakeState.lake_id == lake_id))).scalar_one_or_none()
    th = (await session.execute(select(LakeThreshold).where(LakeThreshold.lake_id == lake_id))).scalar_one_or_none()
    return st, th
