"""FastAPI app — REST 介面(供 frontend 與其他系統消費)。

與 MCP(server.py)共用 ``tools/`` 內的純邏輯。
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from . import __version__
from .config import get_settings
from .db import engine as db
from .server import mcp

settings = get_settings()
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("barrier_lake_ops")

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class CSRFOriginGuard:
    """CSRF 防護(純 ASGI):對會改狀態的請求驗證來源。

    對 POST/PUT/PATCH/DELETE 檢查 ``Origin``(退回 ``Referer``)是否為允許來源,
    不符回 403。採 Fortify 建議之「Check HTTP Referer/Origin headers」——攻擊者
    無法在跨站偽造請求時竄改這兩個 header。

    另對「已授權的跨源前端」(Origin 在 CORS_ORIGINS 名單內)要求請求夾帶
    ``X-CSRF-Token`` 自訂 header(由前端 useCsrfToken 產生的每工作階段隨機 nonce):
    跨站偽造請求無法附加自訂 header(會觸發 CORS preflight 而被擋),
    與 Origin 檢查互為雙重防護。

    - 通過者原封不動轉交,不緩衝回應 → 不影響 /chat 的 SSE 串流。
    - 無 Origin/Referer 的非瀏覽器呼叫(MCP client、curl、伺服器間)放行:
      CSRF 僅發生於瀏覽器夾帶 ambient 憑證的情境。
    - 同源請求(Origin host == 請求自身 Host)放行:同源不構成 CSRF,
      讓後端自家的 /docs Swagger UI 等同源寫入可用。
    - /mcp 遠端 MCP 端點自有 session 驗證,豁免。
    """

    def __init__(self, app, allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed = set(allowed_origins)

    async def __call__(self, scope, receive, send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in _UNSAFE_METHODS
            and not scope["path"].startswith("/mcp")
        ):
            origin = self._origin(scope)
            if (
                origin is not None
                and origin not in self.allowed
                and not self._same_origin(scope, origin)
            ):
                await JSONResponse(
                    {"detail": "請求來源未授權(CSRF 防護)"}, status_code=403
                )(scope, receive, send)
                return
            # 已授權的跨源前端:再驗證自訂 header 存在(double-submit 之
            # custom-header 變體;跨站偽造無法附加自訂 header)
            if (
                origin is not None
                and origin in self.allowed
                and not self._same_origin(scope, origin)
                and not dict(scope["headers"]).get(b"x-csrf-token")
            ):
                await JSONResponse(
                    {"detail": "缺少 CSRF token(X-CSRF-Token header)"},
                    status_code=403,
                )(scope, receive, send)
                return
        await self.app(scope, receive, send)

    @staticmethod
    def _origin(scope) -> str | None:
        headers = dict(scope["headers"])  # list[(bytes, bytes)] → dict
        raw = headers.get(b"origin")
        if raw:
            return raw.decode("latin-1")
        referer = headers.get(b"referer")
        if referer:
            parts = urlsplit(referer.decode("latin-1"))
            if parts.scheme and parts.netloc:
                return f"{parts.scheme}://{parts.netloc}"
        return None

    @staticmethod
    def _same_origin(scope, origin: str) -> bool:
        """Origin 的 host[:port] 與請求自身 Host 相同 → 同源,放行。"""
        host = dict(scope["headers"]).get(b"host")
        return bool(host) and urlsplit(origin).netloc == host.decode("latin-1")

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
        except Exception as exc:  # noqa: BLE001
            logger.warning("資料同步 bootstrap 失敗(降級,不阻擋非 DB 端點): %s", exc)
        # 預載村里空間索引（從 DB 讀，避免首次請求時同步阻塞）
        try:
            from .adapters.population import prime_village_cache_from_db
            await asyncio.to_thread(prime_village_cache_from_db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("預載村里空間索引失敗(降級,首次請求時再載): %s", exc)
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

# CSRF 防護先加(=內層);CORS 後加(=外層),確保回應帶正確 CORS headers、
# 且 preflight OPTIONS 由 CORS 直接處理不進入 CSRF 檢查。
app.add_middleware(CSRFOriginGuard, allowed_origins=settings.cors_origin_list)

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
