"""Custom inspect-ai scorer for the security-reasoning task."""

from __future__ import annotations

from inspect_ai.scorer import (
    CORRECT,
    INCORRECT,
    NOANSWER,
    Score,
    Target,
    accuracy,
    scorer,
    stderr,
)
from inspect_ai.solver import TaskState

from sca_eval.verdict import parse_verdict


def verdict_score_value(predicted: str, expected: str) -> str:
    """Map a parsed verdict to an inspect-ai score value.

    'unknown' (model emitted no VERDICT line) is NOANSWER, not INCORRECT, so a
    format failure is distinguishable from a wrong label in metric breakdowns
    (both still count as 0.0 in accuracy).
    """
    if predicted == "unknown":
        return NOANSWER
    return CORRECT if predicted == expected else INCORRECT


@scorer(metrics=[accuracy(), stderr()])
def verdict_match():
    """Score the model's security verdict against the target label."""

    async def score(state: TaskState, target: Target) -> Score:
        predicted = parse_verdict(state.output.completion)
        expected = target.text.strip().lower()
        return Score(
            value=verdict_score_value(predicted, expected),
            answer=predicted,
            explanation=f"predicted={predicted!r} expected={expected!r}",
        )

    return score
