"""Load seed capability datasets as inspect-ai Sample lists."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from inspect_ai.dataset import Sample

_DATA_DIR = Path(__file__).parent / "data"
_PAYLOAD_DIR = _DATA_DIR / "payloads"

DATASETS = (
    "code_comprehension",
    "security_reasoning",
    "obfuscation",
    "code_comprehension_hard",
    "security_reasoning_hard",
    "obfuscation_hard",
)

C2_DATASETS = (
    "tool_use_c2",
    "tool_use_c2_hard",
)

SANDBOX_WORKDIR = "/work"


def _iter_records(path: Path) -> Iterator[tuple[int, dict]]:
    """Yield (line_no, record) for each non-blank JSONL line; report file+line on bad JSON."""
    for line_no, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            yield line_no, json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed JSON in {path} line {line_no}: {exc}") from exc


def _load_jsonl(path: Path) -> list[Sample]:
    """Parse a JSONL Sample file, reporting file + line number on bad data."""
    samples: list[Sample] = []
    for line_no, record in _iter_records(path):
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


def load_c2_dataset(name: str) -> list[Sample]:
    """Load a C2 tool-use dataset, seeding each payload file into the sandbox.

    Each sample carries files={"/work/<payload>": <local path>} so the model must
    use tools to read and deobfuscate the payload inside the container.
    """
    if name not in C2_DATASETS:
        raise KeyError(f"unknown C2 dataset: {name!r} (known: {C2_DATASETS})")
    path = _DATA_DIR / f"{name}.jsonl"
    samples: list[Sample] = []
    for line_no, record in _iter_records(path):
        try:
            payload_file = record["metadata"]["payload_file"]
        except KeyError as exc:
            raise ValueError(
                f"missing metadata.payload_file in {path} line {line_no}"
            ) from exc
        local = _PAYLOAD_DIR / payload_file
        try:
            local.resolve().relative_to(_PAYLOAD_DIR.resolve())
        except ValueError:
            raise ValueError(
                f"payload_file {payload_file!r} escapes payloads dir in {path} line {line_no}"
            )
        if not local.exists():
            raise ValueError(
                f"payload file {local} referenced in {path} line {line_no} does not exist"
            )
        try:
            samples.append(
                Sample(
                    id=record["id"],
                    input=record["input"],
                    target=record["target"],
                    metadata=record.get("metadata", {}),
                    files={f"{SANDBOX_WORKDIR}/{payload_file}": str(local)},
                )
            )
        except KeyError as exc:
            raise ValueError(
                f"missing required key {exc} in {path} line {line_no}"
            ) from exc
    return samples
