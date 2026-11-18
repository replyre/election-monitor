"""LLM token and cost accounting: every Anthropic call writes an llm_usage row,
succeeded or not, because an un-billed failure is still money spent.
"""

from __future__ import annotations

from dataclasses import dataclass

from common.config import get_settings
from common.logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class Usage:
    model: str
    purpose: str
    input_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    is_batch: bool = False
    request_id: str | None = None

    def total_tokens(self) -> int:
        return self.input_tokens + self.cached_tokens + self.cache_write_tokens + self.output_tokens


def price_for(model: str) -> tuple[float, float]:
    """(input, output) USD per million tokens for a model id."""
    p = get_settings().prices
    name = (model or "").lower()
    if "haiku" in name:
        return p.haiku_in, p.haiku_out
    return p.sonnet_in, p.sonnet_out


def estimate_cost(usage: Usage) -> float:
    """Cost in USD. Cached reads bill at ~10% of the input rate; batch work is
    half price (LLD 13)."""
    prices = get_settings().prices
    rate_in, rate_out = price_for(usage.model)

    cost = (
        usage.input_tokens * rate_in
        + usage.cached_tokens * rate_in * prices.cache_read_multiplier
        + usage.cache_write_tokens * rate_in * prices.cache_write_multiplier
        + usage.output_tokens * rate_out
    ) / 1_000_000

    if usage.is_batch:
        cost *= prices.batch_discount
    return round(cost, 6)


def record(usage: Usage, user_id: int | None = None) -> float:
    """Write the llm_usage row. Returns the cost."""
    from common.db import execute

    cost = estimate_cost(usage)
    try:
        execute(
            "INSERT INTO llm_usage (user_id, model, purpose, input_tokens, cached_tokens, "
            "cache_write_tokens, output_tokens, cost_usd, is_batch, request_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (user_id, usage.model, usage.purpose, usage.input_tokens, usage.cached_tokens,
             usage.cache_write_tokens, usage.output_tokens, cost, usage.is_batch, usage.request_id),
        )
    except Exception as exc:
        # Never fail a user's request because accounting failed - but say so.
        log.error("could not record llm_usage (%s): %s", usage.purpose, exc)
    return cost
