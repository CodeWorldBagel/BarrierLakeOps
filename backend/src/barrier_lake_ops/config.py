"""集中式設定 — 從 backend/.env 讀取(與 frontend/.env 各自獨立)。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目錄(本檔 = backend/src/barrier_lake_ops/config.py)
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 對外服務
    port: int = 8000
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    # 中央氣象署(Tool 2)
    cwa_api_key: str = ""
    cwa_member_tier: str = "general"

    # OpenAI(Tool 5 + Chat)
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1"

    # 延伸選項
    ncdr_token: str = ""

    # 資料庫
    database_url: str = "postgresql://barrierlake:barrierlake@localhost:5432/barrierlake"

    # 本地資料 / 快取
    cache_dir: Path = BACKEND_DIR / ".cache"
    data_dir: Path = BACKEND_DIR / "data"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def async_database_url(self) -> str:
        """SQLAlchemy async 用 asyncpg driver。"""
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
