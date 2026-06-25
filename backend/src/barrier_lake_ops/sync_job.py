"""排程入口 — Zeabur cron service 執行此模組,定期收集村里 / 人口 → DB。

  uv run python -m barrier_lake_ops.sync_job

設計為「跑一次就結束」:Zeabur cron service 依排程(每日)觸發。
"""

from __future__ import annotations

import asyncio
import logging

from . import data_sync
from .db.engine import SessionLocal, init_models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("barrier_lake_ops.sync_job")


async def main() -> None:
    await init_models()
    async with SessionLocal() as session:
        await data_sync.ensure_dataset_rows(session)
        result = await data_sync.run_scheduled(session)
    logger.info("排程同步完成: %s", result)


if __name__ == "__main__":
    asyncio.run(main())
