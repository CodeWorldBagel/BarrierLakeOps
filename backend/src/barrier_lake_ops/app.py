"""FastAPI app — REST 介面(供 frontend 與其他系統消費)。

與 MCP(server.py)共用 ``tools/`` 內的純邏輯。
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from . import __version__
from .config import get_settings
from .db import engine as db
from .server import mcp

settings = get_settings()
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("barrier_lake_ops")

# 遠端 MCP:把同一份 6 工具以 streamable-HTTP 掛在 /mcp,讓 Claude / Cursor 等可一鍵接入。
# http_app 自帶 session-manager lifespan,需與 FastAPI 的建表 lifespan 合併執行。
mcp_app = mcp.http_app(path="/")


async def _daily_sync_loop() -> None:
    """每日自動收集(村里 / 人口 → DB)。獨立 Zeabur cron service 亦可改跑
    ``python -m barrier_lake_ops.sync_job``;此 in-app 排程確保部署即生效。"""
    from . import data_sync

    while True:
        await asyncio.sleep(24 * 3600)
        try:
            async with db.SessionLocal() as session:
                await data_sync.run_scheduled(session)
        except Exception as exc:  # noqa: BLE001
            logger.warning("每日同步失敗(降級): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp_app.lifespan(app):
        # 啟動時建表(MVP:create_all;DB 不可用時降級,不阻擋非 DB 端點)
        await db.init_models()
        # 資料同步 bootstrap:確保狀態列、DB 空則種子村里 + 人工維護(內部 defensive)
        try:
            from . import data_sync

            async with db.SessionLocal() as _session:
                await data_sync.bootstrap(_session)
        except Exception:  # noqa: BLE001
            pass
        # 預載村里空間索引（從 DB 讀，避免首次請求時同步阻塞）
        try:
            from .adapters.population import prime_village_cache_from_db
            await asyncio.to_thread(prime_village_cache_from_db)
        except Exception:  # noqa: BLE001
            pass
        _sync_task = asyncio.create_task(_daily_sync_loop())
        try:
            yield
        finally:
            _sync_task.cancel()


app = FastAPI(
    title="BarrierLakeOps API",
    version=__version__,
    description="堰湖態勢跨部會研判元件 — REST 介面。6 個 Tool 與 MCP 共用同一份邏輯。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    """健康檢查(含 DB 連線)。"""
    db_ok = await db.ping()
    return {
        "status": "ok",
        "version": __version__,
        "environment": settings.environment,
        "db_connected": db_ok,
        "cwa_key_configured": bool(settings.cwa_api_key),
        "openai_key_configured": bool(settings.openai_api_key),
    }


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """直接造訪根網址時,導向 Swagger API 文件。"""
    return RedirectResponse(url="/docs")


@app.get("/info", tags=["meta"])
async def info() -> dict:
    return {
        "name": "BarrierLakeOps API",
        "version": __version__,
        "docs": "/docs",
        "tools": [
            "list_lakes",
            "get_lake_status",
            "get_upstream_weather",
            "estimate_inundation",
            "get_affected_population",
            "compose_briefing",
        ],
    }


from .routers import briefing, chat, data, geo, lakes  # noqa: E402

app.include_router(lakes.router)
app.include_router(geo.router)
app.include_router(briefing.router)
app.include_router(chat.router)
app.include_router(data.router)

# 遠端 MCP endpoint(streamable-HTTP):https://<api-host>/mcp
app.mount("/mcp", mcp_app)
