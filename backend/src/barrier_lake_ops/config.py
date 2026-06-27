"""集中式設定 — 從 backend/.env 讀取(與 frontend/.env 各自獨立)。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目錄。本機(editable)= 套件 parents[2];Zeabur(非 editable 安裝)時
# 套件在 site-packages,故優先用「含 lake_catalog.yaml 的工作目錄」,避免找不到資料檔。
_PKG_DIR = Path(__file__).resolve().parents[2]


def _find_root() -> Path:
    for c in (Path.cwd(), _PKG_DIR):
        if (c / "lake_catalog.yaml").exists():
            return c
    return _PKG_DIR


BACKEND_DIR = _find_root()


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
    database_url: str = "postgresql://barrierlake:barrierlake@db:5432/barrierlake"

    # 本地資料 / 快取
    cache_dir: Path = BACKEND_DIR / ".cache"
    data_dir: Path = BACKEND_DIR / "data"

    # MinIO（正式環境設定；留空則 fallback 到本地 data_dir/dem/）
    minio_endpoint: str = ""
    minio_username: str = "minio"       # = MINIO_USERNAME (Zeabur 暴露名稱)
    minio_password: str = ""            # = MINIO_PASSWORD
    minio_default_bucket: str = "barrier-lake-dem"  # = MINIO_DEFAULT_BUCKET
    minio_secure: bool = False

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
