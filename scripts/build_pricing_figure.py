"""Build the pricing comparison figure used by reports/main.md.

Reports the total pay-as-you-go (PAYG) cost to run the entire benchmark
(all 8 tasks, every sample) once per deployment, on one common per-token basis:
each deployment's real input and output token counts (summed across all tasks,
read from reports_data.json) multiplied by its published per-token rate.

Rates confirmed on 2026-05-30. DeepSeek rates are the vendor's published PAYG
(api-docs.deepseek.com; deepseek-v4-pro at its current promotional price); the
other rates are the gateway's PAYG table.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "reports_data.json"
OUT = ROOT / "reports" / "fig_pricing.png"
CANONICAL_DIRS = {"all-go", "all-zen5"}

# Open-weight = publicly released weights. Qwen Max/Plus are proprietary API
# models, so they count as closed-weight (matching the report's taxonomy).
OPEN_WEIGHT = {"deepseek-v4-pro", "deepseek-v4-flash", "glm-5.1", "kimi-k2.6"}

# ($/1M input, $/1M output)
PAYG_RATES = {
    "gpt-5.3-codex": (1.75, 14.00), "gpt-5.4": (2.50, 15.00),
    "gpt-5.5": (5.00, 30.00), "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "glm-5.1": (1.40, 4.40), "kimi-k2.6": (0.95, 4.00),
    "qwen3.7-max": (2.50, 7.50), "qwen3.6-plus": (0.50, 3.00),
    "deepseek-v4-flash": (0.14, 0.28), "deepseek-v4-pro": (0.435, 0.87),
}
COLORS = {"open-weight": "#4c72b0", "closed-weight": "#dd8452"}


def base(model_id: str) -> str:
    return model_id.split("/")[-1]


def main() -> None:
    rows = json.loads(DATA.read_text())["rows"]
    tok: dict[str, list[int]] = {}
    for r in rows:
        if r["dir"] not in CANONICAL_DIRS:
            continue
        a = tok.setdefault(base(r["model"]), [0, 0])
        a[0] += r["intok"]
        a[1] += r["outtok"]

    costs = {}
    for m, (intok, outtok) in tok.items():
        rate = PAYG_RATES.get(m)
        if rate is None:
            continue
        costs[m] = rate[0] * intok / 1e6 + rate[1] * outtok / 1e6

    order = sorted(costs, key=lambda m: costs[m], reverse=True)
    vals = [costs[m] for m in order]
    bar_colors = [COLORS["open-weight" if m in OPEN_WEIGHT else "closed-weight"]
                  for m in order]

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.barh(order, vals, color=bar_colors)
    ax.invert_yaxis()
    ax.set_xlabel("total pay-as-you-go cost to run all 8 tasks (USD)")
    ax.set_title("Cost to run the full benchmark — pay-as-you-go token pricing")
    for i, v in enumerate(vals):
        ax.text(v, i, f" ${v:.3f}", va="center", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    handles = [plt.Line2D([0], [0], marker="s", linestyle="", color=c, label=p)
               for p, c in COLORS.items()]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=8)
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=130)
    plt.close(fig)
    print(f"wrote {OUT}: {len(order)} deployments, ${min(vals):.3f}-${max(vals):.3f}")


if __name__ == "__main__":
    main()
