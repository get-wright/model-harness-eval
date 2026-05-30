"""Fan capability tasks across models via eval_set() and emit the matrix.

Honors eval_set()'s success boolean and each log's status: failed/cancelled
runs are written to a FAILURES report and rendered 'ERR' in the matrix — never
as a genuine 0.00 score.

Output files written under Path(out_path).parent:
  - <out_path>      : accuracy matrix (Markdown)
  - details.md      : all axes (samples, duration, tokens, cost)
  - tooluse.md      : tool-utilization table (only when a C2 task ran)
  - FAILURES.md     : only when eval_set reports failure or any run failed
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from inspect_ai import eval_set

from sca_eval.extract import summarize_log, tool_use_stats
from sca_eval.matrix import (
    ModelResult,
    ToolUseStats,
    build_matrix,
    format_details_markdown,
    format_markdown,
    format_tooluse_markdown,
)
from sca_eval.pricing import price_usd
from sca_eval.tasks import C2_TASKS, TASKS


def _failures_report(failed: list[ModelResult]) -> str:
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
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict[str, dict[str, float | None]]:
    """Run the survey and return the accuracy matrix.

    Writes files under Path(out_path).parent:
      - <out_path>      : accuracy matrix (Markdown)
      - details.md      : all axes (samples, duration, tokens, cost)
      - tooluse.md      : tool-utilization table (only when a C2 task ran)
      - FAILURES.md     : only when eval_set reports failure or any run failed

    max_tokens / temperature are passed through to the model. Reasoning models
    (e.g. GLM, Qwen) spend tokens on hidden reasoning before emitting the answer
    that scorers read, so set max_tokens generously or answers truncate to empty
    (a false NOANSWER/ERR). None leaves the provider default.
    """
    tasks = [TASKS[name]() for name in task_names]

    success, logs = eval_set(
        tasks=tasks,
        model=models,
        log_dir=log_dir,
        retry_attempts=3,
        retry_wait=30,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    results: list[ModelResult] = []
    for log in logs:
        r = summarize_log(log)
        if r.status == "success":
            r = replace(r, cost_usd=price_usd(r.model, r.input_tokens, r.output_tokens))
        results.append(r)

    # Any requested (model, task) that produced no log at all (e.g. provider
    # rejected the model id before any run) is a failure, not a blank. Synthesize
    # an ERR row so it shows in the matrix and FAILURES.md, never as "-".
    expected = {(m, t) for m in models for t in task_names}
    found = {(r.model, r.task) for r in results}
    for model, task in sorted(expected - found):
        results.append(ModelResult(
            model=model, task=task, accuracy=None, samples=0,
            input_tokens=0, output_tokens=0, duration_s=0.0,
            cost_usd=0.0, status="error",
        ))

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    matrix = build_matrix(results)
    out.write_text(format_markdown(matrix))
    (out.parent / "details.md").write_text(format_details_markdown(results))

    # Tool-use utilization table for any C2 (tool-use) task in this run.
    c2_task_names = [t for t in task_names if t in C2_TASKS]
    if c2_task_names:
        tu_stats = [s for s in (tool_use_stats(log) for log in logs)
                    if s.task in C2_TASKS]
        # Symmetric to the ERR ModelResult synthesis above: any expected C2
        # (model, task) that produced no log gets an ERR row so tooluse.md never
        # silently drops a pair the accuracy matrix shows as ERR.
        tu_found = {(s.model, s.task) for s in tu_stats}
        for model, task_name in sorted(
            {(m, t) for m in models for t in c2_task_names} - tu_found
        ):
            tu_stats.append(ToolUseStats(
                model=model, task=task_name, status="error", samples=0, correct=0,
                tool_calls=0, failed_tool_calls=0, model_turns=0,
                tool_loop_input_tokens=None, tool_loop_output_tokens=None,
                events_missing_usage=0,
            ))
        (out.parent / "tooluse.md").write_text(format_tooluse_markdown(tu_stats))

    # Anything that renders ERR in the matrix (failed status OR a successful run
    # that somehow produced no score) must also appear in FAILURES.md.
    failed = [r for r in results if r.status != "success" or r.accuracy is None]
    if not success or failed:
        (out.parent / "FAILURES.md").write_text(_failures_report(failed))
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
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="max generation tokens; set high for reasoning models")
    parser.add_argument("--temperature", type=float, default=None)
    args = parser.parse_args()

    matrix = run_survey(args.models, args.tasks, args.log_dir, args.out,
                        max_tokens=args.max_tokens, temperature=args.temperature)
    print(format_markdown(matrix))


if __name__ == "__main__":
    main()
