"""Regenerate the Phase 0-1 evaluation report and its charts.

Single source of truth: reports_data.json (rebuilt by scripts/extract_run_data.py
from the most-recent run only). Deployments are labelled by class: open-weight
or closed (hosted).

Outputs (all under reports/):
  fig_easy_vs_hard.png, fig_heatmap.png, fig_thinking_cost.png, fig_efficiency.png,
  fig_tooluse.png, fig_duration.png, fig_pricing.png, agg.json, main.md

Run: uv run python scripts/extract_run_data.py && uv run python scripts/build_report.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "reports_data.json"
OUT = ROOT / "reports"

# The most-recent run: open-weight models + closed (hosted) models.
CANONICAL_DIRS = {"all-go", "all-zen5"}

# Capability axes (single-shot). Tool-use C2 tasks are reported separately (§3).
TASKS = [
    "code_comprehension", "obfuscation", "security_reasoning",
    "code_comprehension_hard", "obfuscation_hard", "security_reasoning_hard",
]
SHORT = {
    "code_comprehension": "cc", "obfuscation": "obf", "security_reasoning": "sec",
    "code_comprehension_hard": "cc-H", "obfuscation_hard": "obf-H",
    "security_reasoning_hard": "sec-H",
}
EASY = TASKS[:3]
HARD = TASKS[3:]
C2_TASKS = {"tool_use_c2", "tool_use_c2_hard"}

# Hosted/closed models; everything else is open-weight.
CLOSED_BASES = {"gpt-5.3-codex", "gpt-5.4", "gpt-5.5",
                "claude-opus-4-7", "claude-opus-4-8"}

PROVIDER_COLORS = {"open-weight": "#4c72b0", "closed": "#dd8452"}

# Pay-as-you-go per-token rates ($/1M input, $/1M output), confirmed on the run
# date (2026-05-30). DeepSeek rates are the vendor's published PAYG (deepseek-v4-pro
# at its current promotional price); the others are the gateway's PAYG table.
PAYG_RATES: dict[str, tuple[float, float] | None] = {
    "gpt-5.3-codex": (1.75, 14.00), "gpt-5.4": (2.50, 15.00),
    "gpt-5.5": (5.00, 30.00), "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "glm-5.1": (1.40, 4.40), "kimi-k2.6": (0.95, 4.00),
    "qwen3.7-max": (2.50, 7.50), "qwen3.6-plus": (0.50, 3.00),
    "deepseek-v4-flash": (0.14, 0.28), "deepseek-v4-pro": (0.435, 0.87),
}


def base_name(model_id: str) -> str:
    return model_id.split("/")[-1]


def provider(model_id: str) -> str:
    return "closed" if base_name(model_id) in CLOSED_BASES else "open-weight"


def disp(model_id: str) -> str:
    return f"{base_name(model_id)} ({provider(model_id)})"


def base_name_of(display: str) -> str:
    return display[: display.rfind(" (")]


# --------------------------------------------------------------------------- #
# Aggregate — capability axes
# --------------------------------------------------------------------------- #
def build_aggregate(rows: list[dict]) -> dict:
    canon = [r for r in rows if r["dir"] in CANONICAL_DIRS]
    models = sorted({disp(r["model"]) for r in canon})

    agg: dict[str, dict] = {m: {t: None for t in TASKS} for m in models}
    out_tokens: dict[str, list[int]] = {m: [] for m in models}
    rsn_tokens: dict[str, list[int]] = {m: [] for m in models}
    has_success: dict[str, bool] = {m: False for m in models}

    for r in canon:
        if r["task"] not in TASKS:
            continue
        m = disp(r["model"])
        if r["acc"] is not None:
            agg[m][r["task"]] = r["acc"]
            has_success[m] = True
            out_tokens[m].append(r["outtok"])
            rsn_tokens[m].append(r["rtok"])

    extra: dict[str, dict] = {}
    for m in models:
        easy = [agg[m][t] for t in EASY if agg[m][t] is not None]
        hard = [agg[m][t] for t in HARD if agg[m][t] is not None]
        ot, rt = out_tokens[m], rsn_tokens[m]
        extra[m] = {
            "easy": (sum(easy) / len(easy)) if easy else None,
            "hard": (sum(hard) / len(hard)) if hard else None,
            "mean_out": round(sum(ot) / len(ot)) if ot else 0,
            "mean_rsn": round(sum(rt) / len(rt)) if rt else 0,
            "provider": provider(base_name_of(m)),
            "status": "ok" if has_success[m] else "FAILED",
        }
    return {"agg": agg, "extra": extra, "models": models}


# --------------------------------------------------------------------------- #
# Tool-use — C2 extraction. Input and output tokens are kept STRICTLY separate
# (input is the transcript re-sent each turn; output is the model's generation).
# Everything is normalised per solved task (all deployments scored 1.00, so
# correct == samples == 18).
# --------------------------------------------------------------------------- #
def build_tooluse(tooluse: list[dict]) -> dict:
    by: dict[str, dict] = {}
    for r in tooluse:
        if r["dir"] not in CANONICAL_DIRS:
            continue
        m = disp(r["model"])
        d = by.setdefault(m, {
            "provider": provider(r["model"]), "samples": 0, "correct": 0,
            "tool_calls": 0, "failed": 0, "turns": 0,
            "in_tok": 0, "out_tok": 0, "missing_usage": False,
        })
        d["samples"] += r["samples"]
        d["correct"] += r["correct"]
        d["tool_calls"] += r["tool_calls"]
        d["failed"] += r["failed"]
        d["turns"] += r["turns"]
        if r["loop_in"] is None or r["loop_out"] is None:
            d["missing_usage"] = True
        else:
            d["in_tok"] += r["loop_in"]
            d["out_tok"] += r["loop_out"]

    for d in by.values():
        n = d["correct"] or 1
        d["acc"] = (d["correct"] / d["samples"]) if d["samples"] else None
        d["calls_per_solve"] = round(d["tool_calls"] / n, 1)
        d["turns_per_solve"] = round(d["turns"] / n, 1)
        d["out_per_solve"] = None if d["missing_usage"] else round(d["out_tok"] / n)
        d["in_per_solve"] = None if d["missing_usage"] else round(d["in_tok"] / n)
    return by


# --------------------------------------------------------------------------- #
# Per-sample latency (from sample.total_time; immune to inter-sample concurrency)
# --------------------------------------------------------------------------- #
def build_duration(samples: list[dict]) -> dict:
    acc: dict[str, dict[str, list[float]]] = {}
    for s in samples:
        if s.get("secs") is None:
            continue
        m = disp(s["model"])
        d = acc.setdefault(m, {"cap": [], "c2": []})
        d["c2" if s["task"] in C2_TASKS else "cap"].append(s["secs"])
    out: dict[str, dict] = {}
    for m, d in acc.items():
        mean = lambda xs: round(sum(xs) / len(xs), 1) if xs else None  # noqa: E731
        out[m] = {"cap": mean(d["cap"]), "c2": mean(d["c2"]),
                  "provider": provider(base_name_of(m))}
    return out


# --------------------------------------------------------------------------- #
# Pay-as-you-go cost of running the whole suite (all 8 tasks). Real token counts
# summed across every task x PAYG per-token rate. Models with no PAYG rate are
# carried as unpriceable (cost None) rather than guessed.
# --------------------------------------------------------------------------- #
def build_pricing(rows: list[dict]) -> dict:
    tok: dict[str, list[int]] = {}
    for r in rows:
        if r["dir"] not in CANONICAL_DIRS:
            continue
        m = disp(r["model"])
        a = tok.setdefault(m, [0, 0])
        a[0] += r["intok"]
        a[1] += r["outtok"]
    out: dict[str, dict] = {}
    for m, (intok, outtok) in tok.items():
        rate = PAYG_RATES.get(base_name_of(m))
        cost = None if rate is None else round(
            rate[0] * intok / 1e6 + rate[1] * outtok / 1e6, 4)
        out[m] = {"in_tok": intok, "out_tok": outtok, "cost": cost,
                  "free": rate == (0.0, 0.0), "provider": provider(base_name_of(m))}
    return out


# --------------------------------------------------------------------------- #
# Charts — capability
# --------------------------------------------------------------------------- #
def _ranked(extra: dict) -> list[str]:
    return sorted(extra, key=lambda m: (extra[m]["hard"] or -1, extra[m]["easy"] or -1),
                  reverse=True)


def _short(models: list[str]) -> list[str]:
    return [base_name_of(m) for m in models]


def chart_easy_vs_hard(extra: dict) -> None:
    ok = [m for m in _ranked(extra) if extra[m]["status"] == "ok"]
    easy = [extra[m]["easy"] for m in ok]
    hard = [extra[m]["hard"] for m in ok]
    x = range(len(ok))
    w = 0.4
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar([i - w / 2 for i in x], easy, w, label="easy set", color="#4c72b0")
    ax.bar([i + w / 2 for i in x], hard, w, label="hard set", color="#c44e52")
    ax.set_xticks(list(x))
    ax.set_xticklabels(_short(ok), rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("mean accuracy")
    ax.set_ylim(0, 1.05)
    ax.set_title("Capability accuracy, easy vs hard (deployments ranked by hard-set)")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "fig_easy_vs_hard.png", dpi=130)
    plt.close(fig)


def chart_heatmap(agg: dict, extra: dict) -> None:
    ok = [m for m in _ranked(extra) if extra[m]["status"] == "ok"]
    grid = [[agg[m][t] if agg[m][t] is not None else float("nan") for t in TASKS]
            for m in ok]
    fig, ax = plt.subplots(figsize=(9, 7))
    im = ax.imshow(grid, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(TASKS)))
    ax.set_xticklabels([SHORT[t] for t in TASKS])
    ax.set_yticks(range(len(ok)))
    ax.set_yticklabels(_short(ok), fontsize=8)
    for i, m in enumerate(ok):
        for j, t in enumerate(TASKS):
            v = agg[m][t]
            ax.text(j, i, "—" if v is None else f"{v:.2f}", ha="center",
                    va="center", fontsize=7)
    ax.set_title("Per-task capability accuracy")
    fig.colorbar(im, ax=ax, shrink=0.7, label="accuracy")
    fig.tight_layout()
    fig.savefig(OUT / "fig_heatmap.png", dpi=130)
    plt.close(fig)


def chart_thinking_cost(extra: dict) -> None:
    ok = sorted([m for m in extra if extra[m]["status"] == "ok"],
                key=lambda m: extra[m]["mean_out"], reverse=True)
    vals = [extra[m]["mean_out"] for m in ok]
    colors = [PROVIDER_COLORS[extra[m]["provider"]] for m in ok]
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.barh(_short(ok), vals, color=colors)
    ax.invert_yaxis()
    ax.set_xlabel("mean generated tokens per capability task")
    ax.set_title("Generation cost — mean output tokens per single-shot task")
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v:,}", va="center", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    _provider_legend(ax, "lower right")
    fig.tight_layout()
    fig.savefig(OUT / "fig_thinking_cost.png", dpi=130)
    plt.close(fig)


def chart_efficiency(extra: dict) -> None:
    ok = [m for m in extra if extra[m]["status"] == "ok" and extra[m]["hard"]]
    pts = [(extra[m]["mean_out"] or 1, extra[m]["hard"], m) for m in ok]
    xmin, xmax = min(p[0] for p in pts), max(p[0] for p in pts)
    mid = (xmin * xmax) ** 0.5
    fig, ax = plt.subplots(figsize=(12, 7))
    for x, y, m in pts:
        ax.scatter(x, y, s=70, color=PROVIDER_COLORS[extra[m]["provider"]],
                   edgecolor="black", linewidth=0.5, zorder=3)
    by_y: dict[float, list] = {}
    for x, y, m in sorted(pts, key=lambda p: p[0]):
        by_y.setdefault(round(y, 3), []).append((x, y, m))
    for group in by_y.values():
        for k, (x, y, m) in enumerate(group):
            right = x >= mid
            ax.annotate(base_name_of(m), (x, y), fontsize=8,
                        ha="right" if right else "left",
                        xytext=(-8 if right else 8, 10 if k % 2 == 0 else -14),
                        textcoords="offset points")
    _provider_legend(ax, "lower center", ncol=2)
    ax.set_xlabel("mean generated tokens per task (log scale)")
    ax.set_xscale("log")
    ax.set_xlim(xmin / 1.6, xmax * 1.7)
    ax.set_ylabel("hard-set accuracy")
    ax.set_title("Capability efficiency — hard-set accuracy vs generation cost")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "fig_efficiency.png", dpi=130)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Charts — tool-use & latency
# --------------------------------------------------------------------------- #
def _provider_legend(ax, loc, ncol=1) -> None:
    handles = [plt.Line2D([0], [0], marker="s", linestyle="", color=c, label=p)
               for p, c in PROVIDER_COLORS.items()]
    ax.legend(handles=handles, loc=loc, ncol=ncol, frameon=False, fontsize=8)


def chart_tooluse(tu: dict) -> None:
    """One clean axis: tool calls per solved task. Token spend lives in the table
    (input and output are different quantities and must not share a bar)."""
    order = sorted(tu, key=lambda m: tu[m]["calls_per_solve"], reverse=True)
    vals = [tu[m]["calls_per_solve"] for m in order]
    colors = [PROVIDER_COLORS[tu[m]["provider"]] for m in order]
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.barh(_short(order), vals, color=colors)
    ax.invert_yaxis()
    ax.set_xlabel("tool calls per solved task (bash / python invocations)")
    ax.set_title("Tool-use intensity — sandbox tool calls per solved C2 task")
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v}", va="center", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    _provider_legend(ax, "lower right")
    fig.tight_layout()
    fig.savefig(OUT / "fig_tooluse.png", dpi=130)
    plt.close(fig)


def chart_duration(dur: dict) -> None:
    """Per-sample wall-clock latency, single-shot vs tool-use, same units."""
    order = sorted(dur, key=lambda m: dur[m]["c2"] or 0, reverse=True)
    cap = [dur[m]["cap"] or 0 for m in order]
    c2 = [dur[m]["c2"] or 0 for m in order]
    x = range(len(order))
    w = 0.4
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar([i - w / 2 for i in x], cap, w, label="single-shot capability task",
           color="#8c8c8c")
    ax.bar([i + w / 2 for i in x], c2, w, label="multi-turn C2 tool-use task",
           color="#dd8452")
    ax.set_xticks(list(x))
    ax.set_xticklabels(_short(order), rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("mean wall-clock seconds per sample")
    ax.set_title("Per-sample latency — single-shot reasoning vs multi-turn tool use")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "fig_duration.png", dpi=130)
    plt.close(fig)


def chart_pricing(pr: dict) -> None:
    """Total pay-as-you-go cost to run the full suite, per model. Priceable
    models are bars; unpriceable ones (no PAYG rate) are noted, not invented."""
    priced = {m: d for m, d in pr.items() if d["cost"] is not None}
    order = sorted(priced, key=lambda m: priced[m]["cost"], reverse=True)
    vals = [priced[m]["cost"] for m in order]
    colors = [PROVIDER_COLORS[priced[m]["provider"]] for m in order]
    na = [base_name_of(m) for m in pr if pr[m]["cost"] is None]
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.barh(_short(order), vals, color=colors)
    ax.invert_yaxis()
    ax.set_xlabel("total pay-as-you-go cost to run all 8 tasks (USD)")
    title = "Cost to run the full benchmark — pay-as-you-go token pricing"
    if na:
        title += f"  (no PAYG rate: {', '.join(na)})"
    ax.set_title(title, fontsize=11)
    for i, (m, v) in enumerate(zip(order, vals)):
        label = " free" if priced[m]["free"] else f" ${v:.3f}"
        ax.text(v, i, label, va="center", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    _provider_legend(ax, "lower right")
    fig.tight_layout()
    fig.savefig(OUT / "fig_pricing.png", dpi=130)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Failures (data-driven)
# --------------------------------------------------------------------------- #
def build_fails(samples: list[dict]) -> list[list]:
    seen: dict[tuple, list] = {}
    for s in samples:
        if s["score"] in ("C", "None"):
            continue
        key = (disp(s["model"]), s["task"], s["id"])
        cand = [disp(s["model"]), s["task"], s["id"], s["target"], s["score"],
                (s["answer"] or "").strip()]
        if key not in seen or (cand[5] and not seen[key][5]):
            seen[key] = cand
    return list(seen.values())


def fail_table(fails, pred, limit=99, trunc=80, only_empty=False) -> str:
    """pred(task, sample_id, answer) selects rows."""
    out = []
    for m, t, i, tgt, score, ans in fails:
        if not pred(t, i, ans):
            continue
        if only_empty and ans:
            continue
        flat = " ".join(ans.split())  # collapse newlines/runs so the row stays intact
        a = (flat[:trunc] if flat else "*(empty)*").replace("|", "\\|")
        tg = str(tgt).replace("|", "\\|")
        out.append(f"| `{base_name_of(m)}` | {t}/{i} | `{tg}` | `{score}` | {a} |")
    return "\n".join(out[:limit]) or "| — | — | — | — | *(none)* |"


# --------------------------------------------------------------------------- #
# Report (analytical register)
# --------------------------------------------------------------------------- #
def cell(v) -> str:
    return "—" if v is None else f"{v:.2f}"


def write_report(agg, extra, tu, dur, pr, fails, models) -> None:
    ok = [m for m in _ranked(extra) if extra[m]["status"] == "ok"]
    L: list[str] = []
    A = L.append

    A("# Evaluating Language Models for Supply-Chain-Attack Analysis: A Capability and Tool-Use Survey")
    A("")
    A("**Phase 0–1 model survey — 2026-05-30**")
    A("")
    A("## Abstract")
    A("")
    A(f"We evaluate {len(ok)} model deployments on a model-independent benchmark "
      "for supply-chain-attack (SCA) reasoning, comprising six single-shot "
      "capability tasks across three language-agnostic axes (code comprehension, "
      "obfuscation, security reasoning), each in an easy and a deliberately hard "
      "variant, together with a tool-use benchmark in which the model must recover "
      "a command-and-control (C2) indicator from an obfuscated payload using shell "
      "and Python tools inside a network-isolated container. All deployments are "
      "exercised through a single harness (inspect-ai with deterministic scorers) "
      "under identical prompts and decoding parameters, so that scores are "
      "comparable within each task family. Deployments are grouped into two "
      "classes — open-weight models and closed (hosted) models (GPT-5.x, Claude "
      "Opus). We report accuracy, generation cost, tool-utilisation, per-sample "
      "latency, and pay-as-you-go monetary cost, and we separate input (context) "
      "from output (generation) tokens throughout, as the two diverge sharply in "
      "the multi-turn setting.")
    A("")
    A("---\n")

    # ---- 1. Method --------------------------------------------------------- #
    A("## 1. Method\n")
    A("### 1.1 Deployments\n")
    A("Table 1 lists the evaluated deployments, grouped by class. Prompts, "
      "scorers, and decoding parameters are held constant across all "
      "deployments.\n")
    A("**Table 1. Evaluated deployments.**\n")
    A("| Class | Deployments |")
    A("|---|---|")
    prov_models: dict[str, list[str]] = {}
    for m in models:
        prov_models.setdefault(extra[m]["provider"], []).append(base_name_of(m))
    A("| open-weight | " + ", ".join(sorted(prov_models.get("open-weight", []))) + " |")
    A("| closed (hosted) | " + ", ".join(sorted(prov_models.get("closed", []))) + " |")
    A("")
    A("### 1.2 Tasks and scoring\n")
    A("The three capability axes are scored deterministically: substring "
      "containment for code comprehension, case-insensitive matching for "
      "obfuscation, and a line-anchored verdict parser for security reasoning. "
      "The hard security set deliberately includes *safe traps* — defended code "
      "that superficially resembles a vulnerability — to probe false-positive "
      "bias rather than recall alone.\n")
    A("The tool-use task places an obfuscated payload in a Docker sandbox "
      "(`network_mode: none`); the model must recover the embedded C2 indicator "
      "using the `bash` and `python` tools and is scored by case-insensitive "
      "matching against the ground-truth indicator. The corpus is synthetic and "
      "modelled on documented incident techniques (layered base64, hexadecimal, "
      "character-code arrays, XOR, gzip, and runtime-computed assembly); all "
      "indicators are non-routable (RFC 5737 ranges and `.invalid`/`.example` "
      "domains), and no network egress is possible, so the benchmark is safe to "
      "re-run.\n")
    A("---\n")

    # ---- 2. Capability ----------------------------------------------------- #
    A("## 2. Single-shot capability\n")
    A("Figure 1 contrasts easy- and hard-set accuracy. The easy sets are largely "
      "saturated; the hard sets, in particular hard obfuscation and hard security "
      "reasoning, carry the discriminating signal.\n")
    A("![Figure 1](fig_easy_vs_hard.png)\n")
    A("*Figure 1. Mean accuracy on easy and hard capability sets, by deployment.*\n")
    A("![Figure 2](fig_heatmap.png)\n")
    A("*Figure 2. Per-task accuracy. Columns: `cc`/`obf`/`sec` (easy) and the "
      "`-H` hard variants.*\n")
    A("Generation cost varies by nearly two orders of magnitude across the field "
      "(Figure 3). Open-weight deployments emit explicit chain-of-thought tokens; "
      "the closed deployments do not expose reasoning tokens and report zero, so "
      "their true deliberation cost is understated here and the comparison should "
      "be read with that asymmetry in mind.\n")
    A("![Figure 3](fig_thinking_cost.png)\n")
    A("*Figure 3. Mean output tokens per single-shot capability task.*\n")
    A("![Figure 4](fig_efficiency.png)\n")
    A("*Figure 4. Hard-set accuracy against mean generation cost (log scale).*\n")
    A("**Table 2. Capability accuracy by task, ranked by hard-set mean.**\n")
    A("| deployment | class | " + " | ".join(SHORT[t] for t in TASKS) + " | easy | hard |")
    A("|---|---|" + "|".join("---" for _ in TASKS) + "|---|---|")
    for m in ok:
        A(f"| `{base_name_of(m)}` | {extra[m]['provider']} | "
          + " | ".join(cell(agg[m][t]) for t in TASKS)
          + f" | {extra[m]['easy']:.2f} | {extra[m]['hard']:.2f} |")
    A("")
    A("Three findings stand out. First, the field is compressed into a narrow "
      "hard-set band (0.85–0.96) with a hard ceiling at 0.96: no deployment "
      "exceeds it, and the spread is concentrated almost entirely in one column, "
      "hard obfuscation (`obf-H`, range 0.56–1.00). The other five axes are at or "
      "near saturation, so `obf-H` is effectively the only single-shot axis still "
      "doing discriminating work at this difficulty — a signal that the easy tier "
      "should be retired and the hard tier extended if the benchmark is to keep "
      "separating frontier models.\n")
    A("Second, within the open-weight field — where token accounting is directly "
      "comparable, unlike across providers — efficiency is not monotone in size. "
      "`qwen3.7-max` reaches the top hard-set score (0.96) at ~7.0k output tokens, "
      "strictly dominating `deepseek-v4-pro`, which spends ~10.3k tokens for a "
      "lower 0.93; `qwen3.6-plus` matches 0.96 at a higher cost. The Qwen pair "
      "therefore sits on the open-weight Pareto front, and raw generation volume "
      "is a poor predictor of hard-set accuracy.\n")
    A("Third, the closed deployments reach 0.85–0.93 at one to two orders of "
      "magnitude lower *reported* output cost, but this comparison is not "
      "trustworthy as a token-efficiency claim: the closed deployments do not "
      "expose reasoning tokens (Figure 3 shows them at zero), so their true "
      "deliberation is unmeasured. Token-count efficiency claims are accordingly "
      "withheld across classes; only the within-open-weight comparison above is "
      "sound (monetary cost, where rates differ by model, is treated separately "
      "in §4). A confound also "
      "depresses several easy-set scores (`gpt-5.5` and `claude-opus-4-8` at 0.50 "
      "on easy code comprehension) — these are scorer artefacts, not capability "
      "gaps, and are dissected in §5.3.\n")
    A("---\n")

    # ---- 3. Tool use ------------------------------------------------------- #
    A("## 3. Tool use: C2 extraction\n")
    A("In the tool-use benchmark the model operates as an agent: it inspects an "
      "obfuscated payload in the sandbox and recovers the C2 indicator through "
      "iterative `bash`/`python` calls. Because task success is uniform — every "
      "deployment achieved an accuracy of 1.00 on both the 10-sample easy and "
      "8-sample hard C2 sets — the informative dimension is *how* the indicator "
      "was recovered: the number of tool calls and the tokens consumed.\n")
    A("We report input and output tokens separately. In a multi-turn loop the "
      "growing transcript is re-sent on every turn, so input (context) tokens "
      "accumulate super-linearly with the number of turns and reflect protocol "
      "overhead rather than reasoning effort; output (generation) tokens measure "
      "the model's own production. Conflating the two is misleading, so they are "
      "tabulated independently and only output is used as an effort proxy.\n")
    A("![Figure 5](fig_tooluse.png)\n")
    A("*Figure 5. Tool calls per solved C2 task (lower is more economical).*\n")
    A("**Table 3. Tool-use profile, normalised per solved task (18 solves per "
      "deployment).**\n")
    A("| deployment | class | tool calls | model turns | output tok | input tok (context) |")
    A("|---|---|---|---|---|---|")
    for m in sorted(tu, key=lambda m: tu[m]["calls_per_solve"], reverse=True):
        d = tu[m]
        op = "—" if d["out_per_solve"] is None else f"{d['out_per_solve']:,}"
        ip = "—" if d["in_per_solve"] is None else f"{d['in_per_solve']:,}"
        A(f"| `{base_name_of(m)}` | {d['provider']} | {d['calls_per_solve']} | "
          f"{d['turns_per_solve']} | {op} | {ip} |")
    A("")
    A("The uniform 1.00 accuracy is itself the first result: at this difficulty "
      "the tool-use task is solved by every deployment, so success rate has zero "
      "discriminating power and the benchmark's agentic tier — like its easy "
      "single-shot tier — needs harder samples (deeper nesting, anti-analysis "
      "guards, multi-stage decoders) to separate models. What remains informative "
      "is the *process*.\n")
    A("Tool-call economy varies roughly three-fold, from 1.3 calls per solve "
      "(`gpt-5.3-codex`) to 3.6 (`deepseek-v4-pro`). This is not a free ordering: "
      "calls per solve is the dominant driver of tool-use latency (§5). "
      "`gpt-5.3-codex` recovers most indicators in roughly one inspect-then-decode "
      "step and finishes a C2 sample in ~5 s; `deepseek-v4-pro` nearly triples the "
      "call count through trial-and-error and is the slowest deployment on the "
      "task at ~23 s. Fewer calls is not unambiguously better — it reflects a "
      "willingness to one-shot a decode rather than verify intermediate output — "
      "but here the economical deployments are also the fastest, with no accuracy "
      "penalty, because the task is easy enough that verification buys nothing.\n")
    A("The separated token columns expose a divergence a summed metric would have "
      "hidden. Output generation is uniformly modest (69–792 tokens per solve), "
      "whereas input (context) tokens range from near-parity with output "
      "(`deepseek-v4-pro`, ~1:1) to a 20:1 ratio (`claude-opus-4-7`, 3,546 input "
      "vs 174 output). The high-ratio deployments are not doing more reasoning — "
      "they are re-billed for re-reading a large transcript on every turn. A "
      "naïve total-token cost would therefore have ranked `claude-opus-4-7` among "
      "the most expensive agents despite its generating the second-fewest tokens "
      "of any deployment; this is precisely why output is the only sound effort "
      "proxy and input is reported separately as protocol overhead. No deployment "
      "incurred a tool-call error, so robustness is not a differentiator here "
      "either.\n")
    A("---\n")

    # ---- 4. Cost ----------------------------------------------------------- #
    A("## 4. Cost\n")
    A("Figure 6 reports the total monetary cost of running the entire benchmark "
      "(all eight tasks, every sample) once per deployment, on a common "
      "pay-as-you-go (PAYG) per-token basis: each deployment's actual input and "
      "output token counts, summed across all tasks, multiplied by its published "
      "per-token rate. Unlike the token-*count* comparison of §2, monetary cost "
      "is comparable across the field because it is denominated in dollars, not "
      "tokens — a deployment that emits many cheap tokens can cost less than one "
      "that emits few expensive ones.\n")
    A("![Figure 6](fig_pricing.png)\n")
    A("*Figure 6. Total pay-as-you-go cost to run the full benchmark, per "
      "deployment (USD).*\n")
    A("**Table 4. Run cost on a pay-as-you-go basis (all 8 tasks).**\n")
    A("| deployment | class | input tok | output tok | rate in/out ($/1M) | run cost |")
    A("|---|---|---|---|---|---|")
    for m in sorted(pr, key=lambda m: pr[m]["cost"] if pr[m]["cost"] is not None else -1,
                    reverse=True):
        d = pr[m]
        rate = PAYG_RATES.get(base_name_of(m))
        rs = "—" if rate is None else f"{rate[0]:g} / {rate[1]:g}"
        cs = "n/a" if d["cost"] is None else (
            "free" if d["free"] else f"${d['cost']:.3f}")
        A(f"| `{base_name_of(m)}` | {d['provider']} | {d['in_tok']:,} | "
          f"{d['out_tok']:,} | {rs} | {cs} |")
    A("")
    A("The cost ranking does not track the capability ranking. The DeepSeek pair "
      "runs the whole suite for under 8 cents (`deepseek-v4-flash` ~$0.02, "
      "`deepseek-v4-pro` ~$0.07), an order of magnitude below the field, because "
      "their per-token rates are far lower even though they emit the most output "
      "tokens of any deployments. At the other end, the most expensive runs "
      "(`claude-opus-4-7` ~$0.52, `gpt-5.5` ~$0.50, `qwen3.7-max` ~$0.46) are "
      "driven by high per-token rates, and in Opus's case by large re-billed "
      "input context (§3). The capability leader `qwen3.7-max` is among the "
      "priciest to run; the top open-weight value is the DeepSeek pair, and the "
      "cheapest closed option is `gpt-5.3-codex` (~$0.08). One caveat carries over "
      "from §2: the closed deployments hide reasoning tokens, which are billed "
      "but unreported, so their true PAYG cost is somewhat higher than shown. "
      "DeepSeek rates are the vendor's published PAYG and include a promotional "
      "discount current on the run date.\n")
    A("---\n")

    # ---- 5. Latency -------------------------------------------------------- #
    A("## 5. Latency\n")
    A("Figure 7 reports mean per-sample wall-clock time, measured from each "
      "sample's recorded `total_time` (and therefore unaffected by inter-sample "
      "concurrency). Single-shot and tool-use samples are shown in the same units.\n")
    A("![Figure 7](fig_duration.png)\n")
    A("*Figure 7. Mean wall-clock seconds per sample: single-shot capability vs "
      "multi-turn tool use.*\n")
    A("**Table 5. Mean per-sample latency (seconds).**\n")
    A("| deployment | class | single-shot | tool-use |")
    A("|---|---|---|---|")
    for m in sorted(ok, key=lambda m: dur.get(m, {}).get("c2") or 0, reverse=True):
        c = dur.get(m, {})
        A(f"| `{base_name_of(m)}` | {extra[m]['provider']} | "
          f"{c.get('cap', '—')} | {c.get('c2', '—')} |")
    A("")
    A("Two regimes are visible, and they invert across classes. The closed "
      "deployments answer single-shot samples in 3–8 s and take 5–10 s on the "
      "multi-turn tool task, so tool use is their slower path. The open reasoners "
      "invert this: their explicit chain-of-thought makes single-shot samples "
      "expensive (up to ~58 s for `kimi-k2.6`), while the tool task — where each "
      "turn is short — completes in 8–23 s. Latency is thus governed less by the "
      "task than by whether a deployment front-loads long deliberation into a "
      "single turn.\n")
    A("This has a direct deployment consequence for an SCA triage pipeline. For "
      "high-volume single-shot classification, the closed models are decisively "
      "faster (sub-10 s vs tens of seconds); for an agentic decode loop the gap "
      "narrows or reverses, because the open reasoners' short per-turn time "
      "compounds favourably. One deployment is dominated in both regimes: "
      "`deepseek-v4-pro` is slow single-shot (33.8 s) *and* slowest on tool use "
      "(22.7 s), as its high call count (§3) compounds with slow per-turn "
      "generation — making it the weakest latency choice despite solving every "
      "task.\n")
    A("Each sample is subject to a hard 600 s `time_limit`; a run exceeding it is "
      "recorded as *cancelled* and reported as such rather than scored as "
      "incorrect. No deployment was cancelled in this run — the slowest C2 task "
      "completed in 68 s — so the cancellation path is documented for "
      "reproducibility but did not arise here.\n")
    A("---\n")

    # ---- 6. Failure analysis ---------------------------------------------- #
    A("## 6. Failure analysis\n")
    A("### 6.1 Refusals on malicious-looking inputs\n")
    A("The corpus includes inputs that resemble attacks (reverse shells, "
      "`rm -rf /`, `/etc/passwd`, `eval(atob(x))`). Outright content refusals "
      "were rare; Table 6 lists completions containing an explicit apology.\n")
    A("**Table 6. Explicit refusals.**\n")
    A("| deployment | sample | target | score | answer |")
    A("|---|---|---|---|---|")
    A(fail_table(fails, lambda t, i, ans: "sorry" in ans.lower(), trunc=120))
    A("")
    A("The more revealing pattern is a *split response to the same stressor*. On "
      "the most overtly malicious hard-obfuscation payloads (`obh-001` "
      "`eval(atob(x))`, `obh-005` `curl evil.sh | sh`, `obh-007` `/bin/sh`) two "
      "distinct failure modes appear. The Opus deployments and two open models "
      "(`glm-5.1`, `kimi-k2.6`) return *empty* completions (Table 7) — a "
      "safety reflex that suppresses output on strings that look like live attack "
      "code, even though decoding a string is itself harmless. The GPT "
      "deployments instead emit a confident but *wrong* answer on the same items "
      "(e.g. `gpt-5.3-codex` returns `zhala(atob(Hx))` for `obh-001` and "
      "`Kubernetes` for `obh-007`/`/bin/sh`), hallucinating rather than "
      "declining. Both modes cost "
      "accuracy on exactly the malware-analysis use case the benchmark targets, "
      "but they call for different mitigations: the suppression mode is an "
      "alignment-tax problem (the model can decode but won't), whereas the "
      "hallucination mode is a decoding-reliability problem.\n")
    A("**Table 7. Empty completions on high-salience payloads.**\n")
    A("| deployment | sample | target | score | answer |")
    A("|---|---|---|---|---|")
    A(fail_table(fails, lambda t, i, ans: t == "obfuscation_hard"
                 and i in ("obh-001", "obh-005", "obh-007"), limit=20, only_empty=True))
    A("")
    A("### 6.2 False-positive bias on safe code\n")
    A("This is the survey's most consequential safety finding. The hard security "
      "set embeds *safe traps* — defended code that superficially resembles a "
      "vulnerability — and `srh-004` (a correct `realpath`/`commonpath` "
      "containment check) defeats almost the entire field: 8 of 11 deployments, "
      "including every GPT and both Opus, return a `VULNERABLE` verdict (Table 8). "
      "Crucially, the failure is not a coin-flip under uncertainty. The models "
      "produce *fluent, internally consistent TOCTOU narratives* — citing a "
      "check-then-open race, recommending `openat`/`O_NOFOLLOW` — for code that is "
      "in fact safe. The justification quality makes the false positive more "
      "dangerous, not less: a human triager reading the explanation would likely "
      "be convinced. The bias is systematic and directional (toward flagging) and "
      "near-universal, with one clean exception — the two Qwen deployments, which "
      "scored 1.00 on hard security and are absent from Table 8. They are the only "
      "models that consistently certified the safe code as safe, which is also why "
      "they top the capability ranking (§2). For an SCA triage application this "
      "predicts a high, confident false-alarm rate on defended code from most of "
      "the field.\n")
    A("**Table 8. Misclassified safe traps.**\n")
    A("| deployment | sample | target | score | answer (truncated) |")
    A("|---|---|---|---|---|")
    A(fail_table(fails, lambda t, i, ans: t == "security_reasoning_hard"
                 and i in ("srh-004", "srh-008"), limit=20))
    A("")
    A("### 6.3 Scoring artefacts\n")
    A("Several apparent easy-set failures are scorer artefacts, not capability "
      "gaps, and they have a measurable effect on the headline numbers. The "
      "dominant case is `cc-002`: the substring scorer expects the literal "
      "`O(n^2)`, but most models answer with the Unicode superscript `O(n²)` — a "
      "correct answer marked wrong. Six deployments miss `cc-002` this way "
      "(Table 9), and they include the two models whose easy code-comprehension "
      "score is 0.50 (`gpt-5.5`, `claude-opus-4-8`); their true easy-set accuracy "
      "is therefore materially higher than Table 2 reports, and the easy tier is "
      "in practice fully saturated once the artefact is removed. This is a "
      "concrete false-negative rate for the deterministic scorer and the primary "
      "motivation for moving to a calibrated model-grader. `cc-004` is a "
      "second, distinct problem — a contestable ground truth where the "
      "'reference' answer is itself debatable — which a string scorer cannot "
      "adjudicate at all.\n")
    A("**Table 9. Scorer-induced misses on easy code comprehension.**\n")
    A("| deployment | sample | target | score | answer |")
    A("|---|---|---|---|---|")
    A(fail_table(fails, lambda t, i, ans: t == "code_comprehension"
                 and i in ("cc-002", "cc-003", "cc-004"), limit=20))
    A("")
    A("---\n")

    # ---- 7. Discussion ----------------------------------------------------- #
    A("## 7. Discussion\n")
    A("Reading the five result sections together, the discriminating signal in "
      "this survey is not accuracy. Easy single-shot and tool-use accuracy are "
      "both saturated, and hard-set accuracy is compressed into a 0.85–0.96 band; "
      "the axes that actually separate the field are hard obfuscation, the "
      "false-positive safety bias of §6.2, the process metrics (tool calls in §3 "
      "and latency in §5), and run cost (§4). A capability leaderboard built on "
      "accuracy alone would conclude these eleven deployments are interchangeable, "
      "which §6 shows they are not.\n")
    A("The clearest model-level conclusion is that the two Qwen deployments lead "
      "on the dimensions that matter: top hard-set accuracy, the open-weight "
      "efficiency front, and — uniquely — resistance to the safe-trap false "
      "positive. The closed deployments are fastest for single-shot triage but "
      "share the field-wide false-positive bias, and `gpt-5.x` additionally "
      "hallucinates rather than declines on high-salience payloads. `deepseek-v4-"
      "pro` solves everything but is latency-dominated in both regimes. On cost "
      "(§4) the ordering is different again: the DeepSeek pair runs the suite for "
      "cents while the capability leader `qwen3.7-max` is among the priciest, so "
      "the best accuracy and the best price are not the same model.\n")
    A("**Threats to validity.** (i) Cross-class token-count comparisons are "
      "unsound because the closed deployments hide reasoning tokens; only "
      "within-open-weight token claims are made (the §4 monetary cost is on the "
      "common pay-as-you-go basis but understates closed-model output, since "
      "hidden reasoning tokens are billed yet unreported). (ii) The deterministic "
      "scorers have a non-zero false-negative "
      "rate (§6.3), so easy-set accuracy is a lower bound. (iii) Per-axis sample "
      "counts are small (4 easy / 9 hard per capability axis; 18 C2 solves), so "
      "single-item differences move the means and the rankings within a 0.03 band "
      "should not be over-read. (iv) The corpus is synthetic; while modelled on "
      "documented incident techniques, it does not establish real-world malware "
      "performance. (v) A single run per (model, task) pair means run-to-run "
      "variance is unmeasured.\n")
    A("---\n")

    # ---- 8. Recommendation ------------------------------------------------- #
    A("## 8. Recommendation\n")
    A("**Best open-weight model: `qwen3.7-max`.** It is the only deployment that "
      "leads on every dimension the benchmark measures rather than trading one "
      "off against another: joint-top hard-set accuracy (0.96, tied only with its "
      "sibling `qwen3.6-plus`), a position on the open-weight efficiency front "
      "(~7.0k output tokens per task — *lower* cost than the larger "
      "`deepseek-v4-pro` for *higher* accuracy), and, decisively, it is one of "
      "only two deployments in the field that resisted the `srh-004` safe-trap "
      "false positive (§6.2). We prefer it over the equally accurate "
      "`qwen3.6-plus` because it is faster single-shot (19.2 s vs 32.2 s per "
      "sample) at lower generation cost. For an SCA pipeline that must run "
      "on-premises or audit its own weights, this is the clear pick. If run cost "
      "outweighs peak accuracy, `deepseek-v4-pro` is the value alternative — it "
      "solves every task at roughly a seventh of `qwen3.7-max`'s PAYG cost (§4), "
      "trading ~0.03 hard-set accuracy and the worst latency for the cheapest "
      "capable run in the field.\n")
    A("**Best closed model: `gpt-5.5`, with one caveat that applies to the whole "
      "closed field.** Among the closed deployments `gpt-5.5` has the highest "
      "hard-set accuracy (0.93) and the strongest hard-obfuscation result (1.00), "
      "making it the best closed choice for analytical quality. The caveat: every "
      "closed deployment — `gpt-5.x` and both Opus — exhibits the §6.2 "
      "false-positive bias, so none should be trusted to *certify code as safe* "
      "without a human check, and `gpt-5.x` additionally hallucinates on "
      "high-salience payloads (§6.1). If throughput rather than peak accuracy "
      "dominates — e.g. high-volume single-shot triage — prefer `gpt-5.4`, the "
      "fastest deployment in the field (2.7 s vs 7.6 s per sample, ~3x faster "
      "than `gpt-5.5`) and among the most tool-economical (1.6 calls per solve, "
      "behind only `gpt-5.3-codex` at 1.3), at a modest accuracy cost "
      "(0.86 hard).\n")
    A("**In short:** `qwen3.7-max` open, `gpt-5.5` closed for accuracy "
      "(`gpt-5.4` closed for speed) — and route any *safe-verdict* decision "
      "through a human reviewer regardless of model, since the false-positive "
      "bias is near-universal outside the Qwen pair.\n")
    A("---\n")
    A("*Generated by `scripts/build_report.py` from `reports_data.json` (rebuilt "
      "by `scripts/extract_run_data.py` from the most-recent run logs). "
      "Figures: `reports/fig_*.png`; aggregates: `reports/agg.json`.*")

    (OUT / "main.md").write_text("\n".join(L))


def main() -> None:
    d = json.loads(DATA.read_text())
    rows, samples = d["rows"], d["samples"]
    tooluse = d.get("tooluse", [])
    a = build_aggregate(rows)
    tu = build_tooluse(tooluse)
    dur = build_duration(samples)
    pr = build_pricing(rows)
    fails = build_fails(samples)

    OUT.mkdir(exist_ok=True)
    chart_easy_vs_hard(a["extra"])
    chart_heatmap(a["agg"], a["extra"])
    chart_thinking_cost(a["extra"])
    chart_efficiency(a["extra"])
    chart_tooluse(tu)
    chart_duration(dur)
    chart_pricing(pr)

    (OUT / "agg.json").write_text(json.dumps(
        {"agg": a["agg"], "extra": a["extra"], "tooluse": tu, "duration": dur,
         "pricing": pr, "fails": fails}, indent=1))
    write_report(a["agg"], a["extra"], tu, dur, pr, fails, a["models"])
    print(f"wrote {OUT/'main.md'} and 7 charts; {len(a['models'])} deployments")


if __name__ == "__main__":
    main()
