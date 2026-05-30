"""Load seed capability datasets as inspect-ai Sample lists."""

from __future__ import annotations

import json
from pathlib import Path

from inspect_ai.dataset import Sample

_DATA_DIR = Path(__file__).parent / "data"

DATASETS = (
    "code_comprehension",
    "security_reasoning",
    "obfuscation",
    "code_comprehension_hard",
    "security_reasoning_hard",
    "obfuscation_hard",
)


def _load_jsonl(path: Path) -> list[Sample]:
    """Parse a JSONL Sample file, reporting file + line number on bad data."""
    samples: list[Sample] = []
    for line_no, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed JSON in {path} line {line_no}: {exc}") from exc
        try:
            samples.append(
                Sample(
                    id=record["id"],
                    input=record["input"],
                    target=record["target"],
                    metadata=record.get("metadata", {}),
                )
            )
        except KeyError as exc:
            raise ValueError(
                f"missing required key {exc} in {path} line {line_no}"
            ) from exc
    return samples


def load_dataset(name: str) -> list[Sample]:
    if name not in DATASETS:
        raise KeyError(f"unknown dataset: {name!r} (known: {DATASETS})")
    return _load_jsonl(_DATA_DIR / f"{name}.jsonl")
