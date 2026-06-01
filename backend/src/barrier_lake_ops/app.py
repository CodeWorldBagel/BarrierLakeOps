"""FastAPI app — REST 介面(供 frontend 與其他系統消費)。

與 MCP(server.py)共用 ``tools/`` 內的純邏輯。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from . import __version__
from .config import get_settings
from .db import engine as db

settings = get_settings()
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("barrier_lake_ops")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動時建表(MVP:create_all;DB 不可用時降級,不阻擋非 DB 端點)
    await db.init_models()
    yield


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


from .routers import briefing, chat, geo, lakes  # noqa: E402

app.include_router(lakes.router)
app.include_router(geo.router)
app.include_router(briefing.router)
app.include_router(chat.router)
