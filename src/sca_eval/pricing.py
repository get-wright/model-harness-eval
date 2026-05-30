"""Token -> USD pricing with separate input/output rates.

Rates are ($/1M input, $/1M output). They CHANGE — confirm against each
provider's pricing page on the run date before billing-grade reporting.
Models absent here (self-hosted open-weight: GLM, DeepSeek, Qwen) price to 0,
because their cost is GPU time, not per-token API billing.
"""

from __future__ import annotations

# (input_per_million_usd, output_per_million_usd)
_RATES: dict[str, tuple[float, float]] = {
    "anthropic/claude-opus-4-8": (15.0, 75.0),   # Anthropic Opus tier
    "openai/gpt-5.5": (10.0, 30.0),              # estimate — verify on OpenAI pricing page
}


def price_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    rate = _RATES.get(model)
    if rate is None:
        return 0.0
    in_rate, out_rate = rate
    cost = in_rate * input_tokens / 1_000_000 + out_rate * output_tokens / 1_000_000
    return round(cost, 6)
