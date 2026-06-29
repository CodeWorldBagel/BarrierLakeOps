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


# async def seed_manual(session: AsyncSession) -> None:
#     """從 catalog 種子 lake_states / lake_thresholds(僅當對應表為空)。"""
#     cat = load_catalog()
#     has_state = (await session.execute(select(func.count()).select_from(LakeState))).scalar()
#     has_thr = (await session.execute(select(func.count()).select_from(LakeThreshold))).scalar()
#     if not has_state:
#         for lk in cat.lakes:
#             rs = lk.reference_state
#             if rs is None:
#                 continue
#             session.add(
#                 LakeState(
#                     lake_id=lk.id, water_level_m=rs.water_level_m,
#                     storage_million_m3=rs.storage_million_m3, observed_at=rs.observed_at,
#                     note=rs.note, updated_by="系統匯入",
#                 )
#             )
#     if not has_thr:
#         for lk in cat.lakes:
#             th = lk.threshold
#             session.add(
#                 LakeThreshold(
#                     lake_id=lk.id, overflow_elevation_m=th.overflow_elevation_m,
#                     red_alert_headroom_m=th.red_alert_headroom_m,
#                     orange_alert_headroom_m=th.orange_alert_headroom_m,
#                     yellow_alert_headroom_m=th.yellow_alert_headroom_m, updated_by="系統匯入",
#                 )
#             )
#     await session.commit()


import math
import yaml


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


_DUPLICATE_DISTANCE_KM = 0.5
_NAME_SIMILARITY_THRESHOLD = 0.6


def _name_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    common = sum(1 for ch in shorter if ch in longer)
    return common / len(shorter)


def _make_geo_key(lon: float | None, lat: float | None, formed_at: str | None) -> str | None:
    if lon is None or lat is None or not formed_at:
        return None
    return f"{lon:.3f}_{lat:.3f}_{formed_at}"


def _make_lake_id(name_zh: str | None, formed_at: str | None) -> str:
    import re
    year = (formed_at or "")[:4] or "unknown"
    name = re.sub(r"堰塞湖", "", name_zh or "")
    name = re.sub(r"[()（）]", "", name).strip()
    return f"{name}-{year}"


def _find_duplicates(rows: list[dict]) -> list[dict]:
    warnings: list[dict] = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if a["lake_id"] == b["lake_id"]:
                continue
            if not a.get("formed_at") or a["formed_at"] != b.get("formed_at"):
                continue
            has_coords = not (a["lon"] is None or a["lat"] is None or b["lon"] is None or b["lat"] is None)
            dist = _haversine_km(a["lon"], a["lat"], b["lon"], b["lat"]) if has_coords else None
            name_sim = _name_similarity(a.get("name_zh", ""), b.get("name_zh", ""))
            close = (dist is not None and dist < _DUPLICATE_DISTANCE_KM)
            similar_name = name_sim >= _NAME_SIMILARITY_THRESHOLD and close
            if close or similar_name:
                reasons = []
                if close:
                    reasons.append(f"距離 {round(dist * 1000)} m")
                if similar_name:
                    reasons.append(f"名稱相似度 {round(name_sim * 100)}%")
                warnings.append({
                    "lake_id_a": a["lake_id"], "name_a": a["name_zh"],
                    "lake_id_b": b["lake_id"], "name_b": b["name_zh"],
                    "formed_at": a["formed_at"],
                    "distance_km": round(dist, 3) if dist is not None else None,
                    "source": "yaml_internal",
                    "reason": f"YAML 內部：formed_at 相同（{a['formed_at']}），{' / '.join(reasons)}",
                })
    return warnings


def _parse_yaml_lakes(content: bytes) -> tuple[list[dict], list[dict], list[dict]]:
    """解析 lake_catalog YAML → (catalog_rows, threshold_rows, state_rows)。"""
    raw = yaml.safe_load(content.decode("utf-8"))
    defaults = raw.get("defaults", {}) or {}
    default_threshold = defaults.get("threshold", {}) or {}
    catalog_rows, threshold_rows, state_rows = [], [], []
    for lk in raw.get("lakes", []):
        loc = lk.get("location", {}) or {}
        centroid = loc.get("centroid") or []
        weather = lk.get("upstream_weather", {}) or {}
        lake_id = _make_lake_id(lk.get("name_zh"), lk.get("formed_at"))
        catalog_rows.append({
            "lake_id": lake_id,
            "name_zh": lk.get("name_zh", lk.get("id", "")),
            "status": "monitoring" if lk.get("status") in (None, "active") else lk.get("status"),
            "formed_at": lk.get("formed_at"),
            "lon": centroid[0] if len(centroid) > 1 else None,
            "lat": centroid[1] if len(centroid) > 1 else None,
            "cwa_stations": weather.get("cwa_stations") or [],
            "dem_bbox": lk.get("downstream_dem_bbox"),
            "moa_dataset_id": lk.get("moa_dataset_id"),
            "note": lk.get("note"),
            "geo_key": _make_geo_key(
                centroid[0] if len(centroid) > 1 else None,
                centroid[1] if len(centroid) > 1 else None,
                lk.get("formed_at"),
            ),
        })
        th = {**default_threshold, **(lk.get("threshold") or {})}
        if any(th.get(k) is not None for k in ("overflow_elevation_m", "red_alert_headroom_m")):
            threshold_rows.append({
                "lake_id": lake_id,
                "overflow_elevation_m": th.get("overflow_elevation_m"),
                "red_alert_headroom_m": th.get("red_alert_headroom_m", 20.0),
                "orange_alert_headroom_m": th.get("orange_alert_headroom_m", 40.0),
                "yellow_alert_headroom_m": th.get("yellow_alert_headroom_m", 70.0),
                "updated_by": "YAML 匯入",
            })
        rs = lk.get("reference_state") or {}
        if any(rs.get(k) is not None for k in ("water_level_m", "storage_million_m3")):
            state_rows.append({
                "lake_id": lake_id,
                "water_level_m": rs.get("water_level_m"),
                "storage_million_m3": rs.get("storage_million_m3"),
                "observed_at": rs.get("observed_at"),
                "note": rs.get("note"),
                "updated_by": "YAML 匯入",
            })
    return catalog_rows, threshold_rows, state_rows


async def upload_lake_catalog(
    session: AsyncSession,
    content: bytes,
    filename: str = "",
    force: bool = False,
    skip_ids: set[str] | None = None,
) -> dict:
    """解析 YAML → 重複檢查 → upsert lake_catalog → 更新 DatasetSync。"""
    from .db.models import LakeCatalog

    catalog_rows, threshold_rows, state_rows = _parse_yaml_lakes(content)
    if not catalog_rows:
        return {"imported": False, "count": 0, "warnings": [], "message": "YAML 解析後無任何堰塞湖資料"}

    if not force and not skip_ids:
        warnings = _find_duplicates(catalog_rows)
        if warnings:
            return {"imported": False, "count": 0, "warnings": warnings}

    if skip_ids:
        catalog_rows = [r for r in catalog_rows if r["lake_id"] not in skip_ids]
        kept = {r["lake_id"] for r in catalog_rows}
        threshold_rows = [r for r in threshold_rows if r["lake_id"] in kept]
        state_rows = [r for r in state_rows if r["lake_id"] in kept]

    if not catalog_rows:
        return {"imported": True, "count": 0, "warnings": [], "message": "略過全部重複項目，無資料匯入"}

    stmt = pg_insert(LakeCatalog).values(catalog_rows)
    update_cols = {
        c: stmt.excluded[c]
        for c in ("name_zh", "status", "formed_at", "lon", "lat",
                  "cwa_stations", "dem_bbox", "moa_dataset_id", "note", "geo_key")
    }
    await session.execute(stmt.on_conflict_do_update(index_elements=["lake_id"], set_=update_cols))

    if threshold_rows:
        th_stmt = pg_insert(LakeThreshold).values(threshold_rows)
        th_cols = {c: th_stmt.excluded[c] for c in
                   ("overflow_elevation_m", "red_alert_headroom_m",
                    "orange_alert_headroom_m", "yellow_alert_headroom_m", "updated_by")}
        await session.execute(th_stmt.on_conflict_do_update(index_elements=["lake_id"], set_=th_cols))

    if state_rows:
        st_stmt = pg_insert(LakeState).values(state_rows)
        st_cols = {c: st_stmt.excluded[c] for c in
                   ("water_level_m", "storage_million_m3", "observed_at", "note", "updated_by")}
        await session.execute(st_stmt.on_conflict_do_update(index_elements=["lake_id"], set_=st_cols))

    ts = _now()
    skipped = len(skip_ids) if skip_ids else 0
    suffix = f"（略過 {skipped} 筆重複）" if skipped else ""
    await _upsert_sync(
        session, "lakes_catalog",
        status="ok", last_run_at=ts, last_success_at=ts, last_changed_at=ts,
        row_count=len(catalog_rows),
        message=(filename or f"{len(catalog_rows)} 筆") + suffix,
    )
    await session.commit()
    return {"imported": True, "count": len(catalog_rows), "warnings": [],
            "message": f"已匯入 {len(catalog_rows)} 筆（含 {len(threshold_rows)} 筆門檻、{len(state_rows)} 筆狀態）{suffix}"}


async def sync_dem_to_minio(lake_ids: list[str]) -> None:
    """背景任務：對指定 lake_id 清單，從 DB dem_bbox 抓 SRTM 高程並上傳 MinIO。

    與 prep_dem_from_db.py 相同策略：
    - 有 dem_bbox → 直接用
    - 無 dem_bbox 但有 lon/lat → 自動追下游路徑推算 bbox
    - 兩者皆無 → 跳過
    只處理 MinIO 尚未有 .npy 的湖。
    """
    import io
    import numpy as np
    from .adapters.dem_models.common import has_dem, _minio_client
    from .adapters.dem_models.bbox_derive import normalize_bbox, derive_downstream_bbox
    from .db.models import LakeCatalog
    from .db.engine import SessionLocal

    s = get_settings()
    if not s.minio_endpoint:
        logger.info("[dem_sync] MINIO_ENDPOINT 未設定，跳過")
        return

    async with SessionLocal() as session:
        rows = (await session.execute(
            select(LakeCatalog.lake_id, LakeCatalog.dem_bbox, LakeCatalog.lon, LakeCatalog.lat)
            .where(LakeCatalog.lake_id.in_(lake_ids))
        )).all()

    # 解析 bbox：有設定用設定值，否則從 lon/lat 推算
    to_fetch: list[tuple[str, list[float]]] = []
    for row in rows:
        lake_id = row.lake_id
        if has_dem(lake_id):
            continue
        bbox = normalize_bbox(row.dem_bbox)
        if bbox is None and row.lon is not None and row.lat is not None:
            logger.info(f"[dem_sync] {lake_id} 無 dem_bbox，嘗試從 lon/lat 推算")
            try:
                bbox = await asyncio.to_thread(
                    derive_downstream_bbox, float(row.lon), float(row.lat), lake_id=lake_id
                )
            except Exception as e:
                logger.warning(f"[dem_sync] {lake_id} bbox 推算失敗: {e}")
        if bbox is None:
            logger.info(f"[dem_sync] {lake_id} 無法取得 bbox，跳過")
            continue
        to_fetch.append((lake_id, bbox))

    if not to_fetch:
        logger.info("[dem_sync] 無需補充 DEM")
        return

    logger.info(f"[dem_sync] 開始補充 {len(to_fetch)} 個湖的 DEM")
    client = _minio_client()
    bucket = s.minio_default_bucket
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info(f"[dem_sync] 建立 MinIO bucket: {bucket}")
    GRID = 40

    # bbox_derive 的 _fetch_elevation_grid 用 sync httpx + time.sleep；以 to_thread 包起
    def _fetch_and_upload(lake_id: str, bbox: list[float]) -> None:
        import time
        import httpx as _httpx
        minlon, minlat, maxlon, maxlat = bbox
        lons = [minlon + (maxlon - minlon) * i / (GRID - 1) for i in range(GRID)]
        lats = list(reversed([minlat + (maxlat - minlat) * j / (GRID - 1) for j in range(GRID)]))
        elev: list[list] = [[None] * GRID for _ in range(GRID)]
        points = [(j, i, lats[j], lons[i]) for j in range(GRID) for i in range(GRID)]
        with _httpx.Client(timeout=30) as http:
            for k in range(0, len(points), 100):
                batch = points[k: k + 100]
                locs = "|".join(f"{p[2]:.6f},{p[3]:.6f}" for p in batch)
                resp = http.get("https://api.opentopodata.org/v1/srtm30m", params={"locations": locs})
                resp.raise_for_status()
                for p, res in zip(batch, resp.json()["results"]):
                    elev[p[0]][p[1]] = res.get("elevation")
                time.sleep(1.1)

        arr = np.array(
            [[(v if v is not None else float("nan")) for v in row] for row in elev],
            dtype="float32",
        )
        meta = {"bbox": bbox, "shape": [GRID, GRID], "row0": "north",
                "source": "SRTM 30m (NASA, public domain) via opentopodata"}

        npy_buf = io.BytesIO()
        np.save(npy_buf, arr)
        npy_buf.seek(0)
        npy_size = npy_buf.getbuffer().nbytes
        json_bytes = json.dumps(meta).encode()

        client.put_object(bucket, f"{lake_id}.npy",
                          npy_buf, npy_size, content_type="application/octet-stream")
        client.put_object(bucket, f"{lake_id}.json",
                          io.BytesIO(json_bytes), len(json_bytes), content_type="application/json")

    for lake_id, bbox in to_fetch:
        try:
            await asyncio.to_thread(_fetch_and_upload, lake_id, bbox)
            logger.info(f"[dem_sync] {lake_id} 上傳完成")
        except Exception as e:
            logger.warning(f"[dem_sync] {lake_id} 失敗: {e}")


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
        # await seed_manual(session)
    except Exception as exc:  # noqa: BLE001
        logger.warning("data_sync bootstrap 降級: %s", exc)


async def run_scheduled(session: AsyncSession) -> dict:
    """排程 / 手動觸發:跑收集器 + 補充缺少的 DEM,回傳結果摘要。"""
    n = await collect_villages(session)

    from .db.models import LakeCatalog
    rows = (await session.execute(
        select(LakeCatalog.lake_id).where(LakeCatalog.dem_bbox.isnot(None))
    )).scalars().all()
    asyncio.create_task(sync_dem_to_minio(list(rows)))

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
