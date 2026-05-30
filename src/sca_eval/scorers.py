"""Custom inspect-ai scorer for the security-reasoning task."""

from __future__ import annotations

from inspect_ai.scorer import Score, accuracy, scorer, stderr

from sca_eval.verdict import parse_verdict


@scorer(metrics=[accuracy(), stderr()])
def verdict_match():
    """Score 'C' when the model's parsed verdict equals the target label.

    An 'unknown' verdict (no VERDICT line) scores 'I' and is surfaced in the
    explanation/answer so unknowns are distinguishable from wrong labels.
    """

    async def score(state, target):
        predicted = parse_verdict(state.output.completion)
        expected = target.text.strip().lower()
        correct = predicted == expected
        return Score(
            value="C" if correct else "I",
            answer=predicted,
            explanation=f"predicted={predicted!r} expected={expected!r}",
        )

    return score
