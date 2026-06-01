"""Async SQLAlchemy engine + session;啟動時建表。"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import get_settings
from .models import Base

logger = logging.getLogger("barrier_lake_ops.db")

_settings = get_settings()
engine = create_async_engine(_settings.async_database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_models() -> bool:
    """建立資料表(MVP 用 create_all;Alembic 留待後續)。回傳是否成功。"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("DB tables ready")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB init failed (持久化將降級): %s", exc)
        return False


async def ping() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
