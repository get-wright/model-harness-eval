"""Pure aggregation of per-(model, task) results into a comparable matrix.

No inspect-ai imports here on purpose: this is the measurement core and must be
testable offline. EvalLog -> ModelResult extraction lives in extract.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelResult:
    model: str
    task: str
    accuracy: float | None     # None when the run failed (status != "success")
    samples: int
    input_tokens: int
    output_tokens: int
    duration_s: float
    cost_usd: float
    status: str = "success"    # "success" | "error" | "cancelled"

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ToolUseStats:
    """Per-(model, task) tool-utilization metrics derived from log events."""
    model: str
    task: str
    status: str
    samples: int
    correct: int
    tool_calls: int
    failed_tool_calls: int
    model_turns: int
    tool_loop_input_tokens: int | None   # None when any ModelEvent lacked usage
    tool_loop_output_tokens: int | None
    events_missing_usage: int

    @property
    def tool_loop_total_tokens(self) -> int | None:
        if self.tool_loop_input_tokens is None or self.tool_loop_output_tokens is None:
            return None
        return self.tool_loop_input_tokens + self.tool_loop_output_tokens


def build_matrix(results: list[ModelResult]) -> dict[str, dict[str, float | None]]:
    """model -> {task -> accuracy}. Last write wins on duplicate (model, task)."""
    matrix: dict[str, dict[str, float | None]] = {}
    for r in results:
        matrix.setdefault(r.model, {})[r.task] = r.accuracy
    return matrix


def format_markdown(matrix: dict[str, dict[str, float | None]]) -> str:
    """Primary accuracy table. Failed cells render 'ERR'; missing cells '-'."""
    if not matrix:
        return ""
    tasks = sorted({task for row in matrix.values() for task in row})
    header = "| model | " + " | ".join(tasks) + " |"
    divider = "| --- | " + " | ".join("---" for _ in tasks) + " |"
    lines = [header, divider]
    for model in sorted(matrix):
        cells = []
        for task in tasks:
            if task not in matrix[model]:
                cells.append(" - ")
            elif matrix[model][task] is None:
                cells.append("ERR")
            else:
                cells.append(f"{matrix[model][task]:.2f}")
        lines.append(f"| {model} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def format_details_markdown(results: list[ModelResult]) -> str:
    """Secondary table with every Phase-1 axis (spec §6)."""
    cols = ["model", "task", "status", "accuracy", "samples",
            "in_tok", "out_tok", "duration_s", "cost_usd"]
    lines = ["| " + " | ".join(cols) + " |",
             "| " + " | ".join("---" for _ in cols) + " |"]
    for r in sorted(results, key=lambda x: (x.model, x.task)):
        acc = "ERR" if r.accuracy is None else f"{r.accuracy:.2f}"
        lines.append(
            f"| {r.model} | {r.task} | {r.status} | {acc} | {r.samples} | "
            f"{r.input_tokens} | {r.output_tokens} | {r.duration_s:g} | "
            f"{r.cost_usd:g} |"
        )
    return "\n".join(lines) + "\n"


_TOOLUSE_COLS = [
    "model", "task", "status", "samples", "correct", "tool_calls", "failed",
    "turns", "loop_in_tok", "loop_out_tok", "tok/call", "calls/correct", "tok/correct",
]


def _ratio(numerator: int | None, denominator: int) -> str:
    """Safe divide -> '—' when undefined (zero denominator or missing numerator)."""
    if numerator is None or denominator == 0:
        return "—"
    return f"{numerator / denominator:.1f}"


def format_tooluse_markdown(stats: list["ToolUseStats"]) -> str:
    """Tool-utilization table. Failed runs render ERR; undefined ratios render '—'."""
    lines = ["| " + " | ".join(_TOOLUSE_COLS) + " |",
             "| " + " | ".join("---" for _ in _TOOLUSE_COLS) + " |"]
    for s in sorted(stats, key=lambda x: (x.model, x.task)):
        if s.status != "success":
            cells = [s.model, s.task, s.status, str(s.samples)] + ["ERR"] * 9
            lines.append("| " + " | ".join(cells) + " |")
            continue
        total = s.tool_loop_total_tokens
        loop_in = "—" if s.tool_loop_input_tokens is None else str(s.tool_loop_input_tokens)
        loop_out = "—" if s.tool_loop_output_tokens is None else str(s.tool_loop_output_tokens)
        cells = [
            s.model, s.task, s.status, str(s.samples), str(s.correct),
            str(s.tool_calls), str(s.failed_tool_calls), str(s.model_turns),
            loop_in, loop_out,
            _ratio(total, s.tool_calls),
            _ratio(s.tool_calls, s.correct),
            _ratio(total, s.correct),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
