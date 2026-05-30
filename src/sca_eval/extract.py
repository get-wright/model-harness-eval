"""Turn an inspect-ai EvalLog into a flat ModelResult for the matrix.

Isolated here because it is the only module coupled to inspect-ai's log schema.
A non-'success' log is returned with accuracy=None and its status preserved, so
infrastructure failures are never confused with a genuine 0.00 score.
"""

from __future__ import annotations

from datetime import datetime

from inspect_ai.log import EvalLog

from sca_eval.matrix import ModelResult


def _task_name(log: EvalLog) -> str:
    # log.eval.task is the registry name, e.g. "sca_eval/obfuscation".
    # Strip the package prefix so the task name matches the bare function name.
    task = log.eval.task
    return task.split("/")[-1] if "/" in task else task


def _primary_accuracy(log: EvalLog) -> float | None:
    results = getattr(log, "results", None)
    if not results or not results.scores:
        return None
    metrics = results.scores[0].metrics
    metric = metrics.get("accuracy")
    if metric is None:
        metric = next(iter(metrics.values()), None)
    return float(metric.value) if metric is not None else None


def _tokens(log: EvalLog) -> tuple[int, int]:
    usage = getattr(log.stats, "model_usage", None) or {}
    inp = sum(int(getattr(u, "input_tokens", 0) or 0) for u in usage.values())
    out = sum(int(getattr(u, "output_tokens", 0) or 0) for u in usage.values())
    return inp, out


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _duration_s(log: EvalLog) -> float:
    started, completed = log.stats.started_at, log.stats.completed_at
    if not started or not completed:
        return 0.0
    return max(0.0, (_parse_ts(completed) - _parse_ts(started)).total_seconds())


def _sample_count(log: EvalLog) -> int:
    return int(getattr(log.eval.dataset, "samples", 0) or 0)


def summarize_log(log: EvalLog) -> ModelResult:
    status = log.status
    if status != "success":
        return ModelResult(
            model=log.eval.model, task=_task_name(log), accuracy=None,
            samples=_sample_count(log), input_tokens=0, output_tokens=0,
            duration_s=_duration_s(log), cost_usd=0.0, status=status,
        )
    inp, out = _tokens(log)
    return ModelResult(
        model=log.eval.model, task=_task_name(log),
        accuracy=_primary_accuracy(log), samples=_sample_count(log),
        input_tokens=inp, output_tokens=out, duration_s=_duration_s(log),
        cost_usd=0.0, status="success",
    )
