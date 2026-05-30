"""Extract reports_data.json from the most-recent run's inspect-ai eval logs.

Source = the two complete sweeps of the current survey:
  logs/all-go     — Opencode Go open models  (6 deployments x 8 tasks)
  logs/all-zen5   — Opencode Zen closed models (5 deployments x 8 tasks)

Emits reports_data.json consumed by scripts/build_report.py:
  rows     — one per (model, task): dir, model, task, status, acc,
             intok, outtok, rtok, duration_s
  tooluse  — one per (model, C2 task): tool-utilization metrics
  samples  — one per (model, task, sample): target, answer, score

Run: uv run python scripts/extract_run_data.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from inspect_ai.log import read_eval_log

ROOT = Path(__file__).resolve().parent.parent
RUN_DIRS = ["all-go", "all-zen5"]
C2_TASKS = {"tool_use_c2", "tool_use_c2_hard"}
CORRECT = "C"


def _task(log) -> str:
    t = log.eval.task
    return t.split("/")[-1] if "/" in t else t


def _duration_s(log) -> float | None:
    s, c = log.stats.started_at, log.stats.completed_at
    if not s or not c:
        return None
    f = lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))  # noqa: E731
    return round(max(0.0, (f(c) - f(s)).total_seconds()), 1)


def _accuracy(log) -> float | None:
    res = getattr(log, "results", None)
    if not res or not res.scores:
        return None
    metrics = res.scores[0].metrics
    metric = metrics.get("accuracy") or next(iter(metrics.values()), None)
    return float(metric.value) if metric is not None else None


def _tokens(log) -> tuple[int, int, int]:
    usage = getattr(log.stats, "model_usage", None) or {}
    intok = sum(int(getattr(u, "input_tokens", 0) or 0) for u in usage.values())
    outtok = sum(int(getattr(u, "output_tokens", 0) or 0) for u in usage.values())
    rtok = sum(int(getattr(u, "reasoning_tokens", 0) or 0) for u in usage.values())
    return intok, outtok, rtok


def _score_value(sample) -> str:
    scores = getattr(sample, "scores", None) or {}
    for sc in scores.values():
        return str(getattr(sc, "value", "None"))
    return "None"


def _tool_loop(samples) -> dict:
    """Per-run tool-utilization, summed over a log's samples (None tokens if any
    ModelEvent lacks usage — never silently zeroed)."""
    tool_calls = failed = turns = correct = missing = 0
    in_tok = out_tok = 0
    for s in samples or []:
        for ev in (getattr(s, "events", None) or []):
            kind = getattr(ev, "event", None)
            if kind == "tool":
                tool_calls += 1
                if getattr(ev, "failed", None) is True or getattr(ev, "error", None) is not None:
                    failed += 1
            elif kind == "model":
                turns += 1
                usage = getattr(getattr(ev, "output", None), "usage", None)
                if usage is None:
                    missing += 1
                else:
                    in_tok += int(getattr(usage, "input_tokens", 0) or 0)
                    out_tok += int(getattr(usage, "output_tokens", 0) or 0)
        if _score_value(s) == CORRECT:
            correct += 1
    return {
        "samples": len(samples or []), "correct": correct,
        "tool_calls": tool_calls, "failed": failed, "turns": turns,
        "loop_in": None if missing else in_tok,
        "loop_out": None if missing else out_tok,
    }


def main() -> None:
    rows: list[dict] = []
    tooluse: list[dict] = []
    samples: list[dict] = []

    for d in RUN_DIRS:
        for f in sorted((ROOT / "logs" / d).glob("*.eval")):
            log = read_eval_log(str(f))  # full (need events + samples)
            model, task = log.eval.model, _task(log)
            intok, outtok, rtok = _tokens(log)
            rows.append({
                "dir": d, "model": model, "task": task, "status": log.status,
                "acc": _accuracy(log), "intok": intok, "outtok": outtok,
                "rtok": rtok, "duration_s": _duration_s(log),
            })
            for s in (log.samples or []):
                secs = getattr(s, "total_time", None)
                if secs is None:
                    secs = getattr(s, "working_time", None)
                samples.append({
                    "model": model, "task": task, "id": s.id,
                    "target": s.target,
                    "answer": (s.output.completion if s.output else "") or "",
                    "score": _score_value(s),
                    "secs": round(secs, 2) if secs is not None else None,
                })
            if task in C2_TASKS:
                tl = _tool_loop(log.samples)
                tooluse.append({
                    "dir": d, "model": model, "task": task,
                    "status": log.status, "duration_s": _duration_s(log), **tl,
                })

    (ROOT / "reports_data.json").write_text(json.dumps(
        {"rows": rows, "tooluse": tooluse, "samples": samples}, indent=1))
    print(f"wrote reports_data.json: {len(rows)} rows, {len(tooluse)} tool-use "
          f"rows, {len(samples)} samples from {RUN_DIRS}")


if __name__ == "__main__":
    main()
