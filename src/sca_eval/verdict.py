"""Parse a model's security judgement strictly from its VERDICT line."""

from __future__ import annotations

import re

_VERDICT_LINE = re.compile(r"verdict\s*:\s*(vulnerable|safe)", re.IGNORECASE)


def parse_verdict(text: str) -> str:
    """Return 'vulnerable', 'safe', or 'unknown'.

    Only an explicit 'VERDICT: X' line is honored (last one wins). No loose
    substring matching — prose like 'not vulnerable' returns 'unknown', not a
    misclassification.
    """
    matches = _VERDICT_LINE.findall(text)
    if not matches:
        return "unknown"
    return matches[-1].lower()
