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


def build_matrix(results: list[ModelResult]) -> dict[str, dict[str, float | None]]:
    """model -> {task -> accuracy}. Last write wins on duplicate (model, task)."""
    matrix: dict[str, dict[str, float | None]] = {}
    for r in results:
        matrix.setdefault(r.model, {})[r.task] = r.accuracy
    return matrix


def format_markdown(matrix: dict[str, dict[str, float | None]]) -> str:
    """Primary accuracy table. Failed cells render 'ERR'; missing cells '-'."""
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
