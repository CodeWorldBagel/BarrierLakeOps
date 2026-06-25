"""/data 路由 — 資料同步狀態 + 人工維護編輯 + 手動同步 + 堰塞湖清單上傳。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .. import data_sync
from ..db.engine import get_session

router = APIRouter(prefix="/data", tags=["data"])


@router.get("/status")
async def data_status(session: AsyncSession = Depends(get_session)) -> dict:
    """資料同步頁:所有資料集狀態 + 人工維護(水位 / 門檻)現值。"""
    return await data_sync.get_status(session)


@router.post("/sync")
async def trigger_sync(session: AsyncSession = Depends(get_session)) -> dict:
    """手動觸發排程收集器(村里界 / 人口)。"""
    result = await data_sync.run_scheduled(session)
    return {"ok": True, "result": result}


class LakeStateIn(BaseModel):
    water_level_m: float | None = None
    storage_million_m3: float | None = None
    observed_at: str | None = None
    note: str | None = None


@router.patch("/lake-state/{lake_id}")
async def patch_lake_state(
    lake_id: str, body: LakeStateIn, session: AsyncSession = Depends(get_session)
) -> dict:
    """編輯堰塞湖水位(寫 DB + 記錄更新者 / 時間)。"""
    return await data_sync.update_lake_state(session, lake_id, body.model_dump(exclude_unset=True))


class LakeThresholdIn(BaseModel):
    overflow_elevation_m: float | None = None
    red_alert_headroom_m: float | None = None
    orange_alert_headroom_m: float | None = None
    yellow_alert_headroom_m: float | None = None


@router.patch("/lake-threshold/{lake_id}")
async def patch_lake_threshold(
    lake_id: str, body: LakeThresholdIn, session: AsyncSession = Depends(get_session)
) -> dict:
    """編輯警戒門檻(寫 DB + 記錄更新者 / 時間)。"""
    return await data_sync.update_lake_threshold(session, lake_id, body.model_dump(exclude_unset=True))


@router.post("/lakes/upload")
async def upload_lakes(file: UploadFile = File(...)) -> dict:
    """堰塞湖清單 YAML 上傳。後端解析入庫由組員實作;此處僅接收並回報尚未上線。"""
    content = await file.read()
    return {
        "accepted": True,
        "parsed": False,
        "filename": file.filename,
        "size": len(content),
        "message": "檔案已接收;YAML 解析入庫由組員實作,尚未上線。",
    }
