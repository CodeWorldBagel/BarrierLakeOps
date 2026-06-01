"""共用 OpenAI client。"""

from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI

from ..config import get_settings


@lru_cache
def get_client() -> AsyncOpenAI | None:
    s = get_settings()
    if not s.openai_api_key:
        return None
    return AsyncOpenAI(api_key=s.openai_api_key)


def get_model() -> str:
    return get_settings().openai_model
