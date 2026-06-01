"""共用 HTTP 取用 + 檔案快取(降低外部 API 限流風險)。"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import get_settings
from . import AdapterError

logger = logging.getLogger("barrier_lake_ops.adapters")

_settings = get_settings()
_TIMEOUT = httpx.Timeout(20.0)


def _cache_path(key: str) -> Path:
    _settings.cache_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return _settings.cache_dir / f"{h}.json"


def _read_cache(key: str, ttl: int) -> Any | None:
    p = _cache_path(key)
    if not p.exists():
        return None
    try:
        blob = json.loads(p.read_text(encoding="utf-8"))
        if time.time() - blob["_ts"] <= ttl:
            return blob["data"]
    except Exception:  # noqa: BLE001
        return None
    return None


def _write_cache(key: str, data: Any) -> None:
    try:
        _cache_path(key).write_text(
            json.dumps({"_ts": time.time(), "data": data}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("cache write failed: %s", exc)


async def fetch_json(
    url: str,
    *,
    params: dict | None = None,
    ttl: int = 3600,
    cache_key: str | None = None,
    allow_stale_on_error: bool = True,
) -> Any:
    """取 JSON;先看快取,過期則打網路。網路失敗時可回退到過期快取。

    全部失敗 → 拋 AdapterError,呼叫端負責降級。
    """
    key = cache_key or f"{url}?{json.dumps(params, sort_keys=True)}"
    cached = _read_cache(key, ttl)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        _write_cache(key, data)
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_json failed for %s: %s", url, exc)
        if allow_stale_on_error:
            stale = _read_cache(key, ttl=10**9)  # 任意舊都接受
            if stale is not None:
                logger.info("serving stale cache for %s", url)
                return stale
        raise AdapterError(f"外部資料源不可用: {url} ({exc})") from exc
