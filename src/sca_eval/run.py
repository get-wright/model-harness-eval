"""Fan capability tasks across models via eval_set() and emit the matrix.

Honors eval_set()'s success boolean and each log's status: failed/cancelled
runs are written to a FAILURES report and rendered 'ERR' in the matrix — never
as a genuine 0.00 score.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from inspect_ai import eval_set

from sca_eval.extract import summarize_log
from sca_eval.matrix import (
    ModelResult,
    build_matrix,
    format_details_markdown,
    format_markdown,
)
from sca_eval.pricing import price_usd
from sca_eval.tasks import TASKS


def _failures_report(results: list[ModelResult]) -> str:
    failed = [r for r in results if r.status != "success"]
    lines = ["# Run failures", "",
             "These (model, task) runs did NOT succeed and are shown as ERR in the",
             "matrix (never as a real 0.00 score).", ""]
    for r in failed:
        lines.append(f"- {r.model} / {r.task}: status={r.status}")
    return "\n".join(lines) + "\n"


def run_survey(
    models: list[str],
    task_names: list[str],
    log_dir: str = "logs/survey",
    out_path: str = "out/matrix.md",
) -> dict[str, dict[str, float | None]]:
    tasks = [TASKS[name]() for name in task_names]

    success, logs = eval_set(
        tasks=tasks,
        model=models,
        log_dir=log_dir,
        retry_attempts=3,
        retry_wait=30,
    )

    results: list[ModelResult] = []
    for log in logs:
        r = summarize_log(log)
        if r.status == "success":
            r = replace(r, cost_usd=price_usd(r.model, r.input_tokens, r.output_tokens))
        results.append(r)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    matrix = build_matrix(results)
    out.write_text(format_markdown(matrix))
    (out.parent / "details.md").write_text(format_details_markdown(results))

    failed = [r for r in results if r.status != "success"]
    if not success or failed:
        (out.parent / "FAILURES.md").write_text(_failures_report(results))
        print(f"WARNING: eval_set success={success}, {len(failed)} failed run(s). "
              f"See {out.parent / 'FAILURES.md'}. Failed cells render ERR, not 0.00.")

    return matrix


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the capability model survey.")
    parser.add_argument("--models", nargs="+", required=True,
                        help="inspect-ai model ids, e.g. anthropic/claude-opus-4-8")
    parser.add_argument("--tasks", nargs="+", default=list(TASKS), choices=list(TASKS))
    parser.add_argument("--log-dir", default="logs/survey")
    parser.add_argument("--out", default="out/matrix.md")
    args = parser.parse_args()

    matrix = run_survey(args.models, args.tasks, args.log_dir, args.out)
    print(format_markdown(matrix))


if __name__ == "__main__":
    main()
