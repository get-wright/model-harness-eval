"""Build the pricing comparison figure used by reports/main.md.

The values are copied from the OpenCode Go and Zen docs on 2026-05-30.
Go uses a subscription quota, so the figure reports estimated monthly requests
inside the documented $60 monthly usage limit. Zen uses pay-as-you-go token
pricing, so the figure reports input and output dollars per 1M tokens.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "fig_pricing.png"

GO_MONTHLY_REQUESTS = {
    "DeepSeek V4 Flash": 158_150,
    "DeepSeek V4 Pro": 17_150,
    "GLM-5.1": 4_300,
    "Kimi K2.6": 5_750,
    "Qwen3.6 Plus": 16_300,
    "Qwen3.7 Max": 4_770,
}

ZEN_TOKEN_PRICES = {
    "gpt-5.3-codex": (1.75, 14.00),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.5": (5.00, 30.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
}


def main() -> None:
    fig, (ax_go, ax_zen) = plt.subplots(1, 2, figsize=(14, 6))

    go_items = sorted(GO_MONTHLY_REQUESTS.items(), key=lambda item: item[1])
    go_names = [name for name, _ in go_items]
    go_vals = [value for _, value in go_items]
    ax_go.barh(go_names, go_vals, color="#4c72b0")
    ax_go.set_xlabel("estimated requests per month")
    ax_go.set_title("OpenCode Go subscription capacity")
    ax_go.grid(axis="x", alpha=0.25)
    for i, value in enumerate(go_vals):
        ax_go.text(value, i, f" {value:,}", va="center", fontsize=8)

    zen_items = sorted(ZEN_TOKEN_PRICES.items(), key=lambda item: item[1][1])
    zen_names = [name for name, _ in zen_items]
    zen_input = [value[0] for _, value in zen_items]
    zen_output = [value[1] for _, value in zen_items]
    x = range(len(zen_items))
    width = 0.38
    ax_zen.bar([i - width / 2 for i in x], zen_input, width, label="input", color="#55a868")
    ax_zen.bar([i + width / 2 for i in x], zen_output, width, label="output", color="#c44e52")
    ax_zen.set_xticks(list(x))
    ax_zen.set_xticklabels(zen_names, rotation=35, ha="right", fontsize=8)
    ax_zen.set_ylabel("$ per 1M tokens")
    ax_zen.set_title("OpenCode Zen pay-as-you-go rates")
    ax_zen.grid(axis="y", alpha=0.25)
    ax_zen.legend(frameon=False)

    fig.suptitle("Pricing comparison from OpenCode docs", fontsize=14)
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    main()
