"""Build the pricing comparison figure used by reports/main.md.

The values are copied from the OpenCode pricing docs on 2026-05-30.
The figure labels the billing units, not the product routes: one side uses
estimated monthly requests inside the documented $60 subscription usage limit,
and the other uses pay-as-you-go input/output dollars per 1M tokens.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "fig_pricing.png"

MONTHLY_REQUESTS = {
    "DeepSeek V4 Flash": 158_150,
    "DeepSeek V4 Pro": 17_150,
    "GLM-5.1": 4_300,
    "Kimi K2.6": 5_750,
    "Qwen3.6 Plus": 16_300,
    "Qwen3.7 Max": 4_770,
}

TOKEN_PRICES = {
    "gpt-5.3-codex": (1.75, 14.00),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.5": (5.00, 30.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
}


def main() -> None:
    fig, (ax_requests, ax_tokens) = plt.subplots(1, 2, figsize=(14, 6))

    request_items = sorted(MONTHLY_REQUESTS.items(), key=lambda item: item[1])
    request_names = [name for name, _ in request_items]
    request_vals = [value for _, value in request_items]
    ax_requests.barh(request_names, request_vals, color="#4c72b0")
    ax_requests.set_xlabel("estimated requests per month")
    ax_requests.set_title("Subscription request capacity")
    ax_requests.grid(axis="x", alpha=0.25)
    for i, value in enumerate(request_vals):
        ax_requests.text(value, i, f" {value:,}", va="center", fontsize=8)

    token_items = sorted(TOKEN_PRICES.items(), key=lambda item: item[1][1])
    token_names = [name for name, _ in token_items]
    token_input = [value[0] for _, value in token_items]
    token_output = [value[1] for _, value in token_items]
    x = range(len(token_items))
    width = 0.38
    ax_tokens.bar([i - width / 2 for i in x], token_input, width, label="input", color="#55a868")
    ax_tokens.bar([i + width / 2 for i in x], token_output, width, label="output", color="#c44e52")
    ax_tokens.set_xticks(list(x))
    ax_tokens.set_xticklabels(token_names, rotation=35, ha="right", fontsize=8)
    ax_tokens.set_ylabel("$ per 1M tokens")
    ax_tokens.set_title("Pay-as-you-go token rates")
    ax_tokens.grid(axis="y", alpha=0.25)
    ax_tokens.legend(frameon=False)

    fig.suptitle("Pricing comparison using documented billing units", fontsize=14)
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    main()
