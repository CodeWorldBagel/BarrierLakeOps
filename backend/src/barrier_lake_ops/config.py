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

    # 資料庫 — 憑證不寫死在原始碼。正式環境由 Zeabur service 變數注入 DATABASE_URL;
    # 本機開發把含密碼的連線字串放進 gitignored backend/.env。預設留空,一律由 .env / 環境
    # 變數提供;未設時 db 層優雅降級(不阻擋非 DB 端點)。
    database_url: str = ""

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
        """SQLAlchemy async 用 asyncpg driver。

        未設 DATABASE_URL 時回傳一個「可被 create_async_engine 解析、但連不上」的
        佔位 URL,讓 engine 仍能於 import 期建立;實際連線失敗由 db 層優雅降級。
        """
        url = self.database_url
        if not url:
            return "postgresql+asyncpg://localhost/_unset"
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
