"""Anthropic client for the news-labelling jobs (news/label_batch.py, label_collect.py)."""

from __future__ import annotations

import functools

from common.config import get_settings


@functools.lru_cache(maxsize=1)
def get_client():
    import anthropic

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60.0, max_retries=2)
