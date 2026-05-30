"""Load seed capability datasets as inspect-ai Sample lists."""

from __future__ import annotations

import json
from pathlib import Path

from inspect_ai.dataset import Sample

_DATA_DIR = Path(__file__).parent / "data"

DATASETS = ("code_comprehension", "security_reasoning", "obfuscation")


def load_dataset(name: str) -> list[Sample]:
    if name not in DATASETS:
        raise KeyError(f"unknown dataset: {name!r} (known: {DATASETS})")
    path = _DATA_DIR / f"{name}.jsonl"
    samples: list[Sample] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        samples.append(
            Sample(
                id=record["id"],
                input=record["input"],
                target=record["target"],
                metadata=record.get("metadata", {}),
            )
        )
    return samples
