# Tool-Use C2-Extraction Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Phase-1 tool-use capability axis as a C2-extraction-in-obfuscated-code task that runs each model in a network-isolated Docker sandbox and reports both correctness and tool-utilization metrics.

**Architecture:** New inspect-ai tasks (`tool_use_c2`, `tool_use_c2_hard`) seed a synthetic obfuscated payload file into a `network_mode: none` Docker sandbox via `Sample.files`; the model uses `bash`/`python` tools to recover the C2 indicator. A new `tool_use_stats()` extraction reads `log.samples[].events` for tool-call counts, failures, turns, and per-`ModelEvent` token usage; a new `format_tooluse_markdown()` renders the tool-use table. Everything reuses the existing `eval_set` runner and `ERR`-not-`0.00` discipline.

**Tech Stack:** Python ≥3.11, inspect-ai 0.3.229 (`use_tools`, `bash`, `python`, docker sandbox, `eval_set`), Docker (runtime only), pytest (hermetic + docker-gated).

**Spec:** `docs/superpowers/specs/2026-05-30-tool-use-c2-benchmark-design.md`

---

## File Structure

New:
- `src/sca_eval/sandbox/compose.yaml` — isolated, no-egress sandbox service.
- `scripts/gen_c2_corpus.py` — deterministic authoring tool: writes payload files + jsonl from a fixed sample table (stdlib only). One-time/regeneration use; output is committed.
- `src/sca_eval/data/tool_use_c2.jsonl`, `tool_use_c2_hard.jsonl` — generated sample records.
- `src/sca_eval/data/payloads/*` — generated obfuscated payload files (one per sample).
- `tests/test_c2_dataset.py`, `tests/test_tooluse_extract.py`, `tests/test_tooluse_matrix.py` — hermetic.
- `tests/test_c2_sandbox.py` — docker-gated no-egress proof.

Modify:
- `src/sca_eval/datasets.py` — `_iter_records()` (DRY refactor) + `load_c2_dataset()`.
- `src/sca_eval/matrix.py` — `ToolUseStats` dataclass + `format_tooluse_markdown()`.
- `src/sca_eval/extract.py` — `tool_use_stats(log) -> ToolUseStats`.
- `src/sca_eval/tasks.py` — `COMPOSE_FILE`, `C2_TASKS`, `tool_use_c2`, `tool_use_c2_hard`, register in `TASKS`.
- `src/sca_eval/run.py` — write `out/tooluse.md`.
- `README.md` — run instructions + safety.

---

## Task 1: C2 dataset loader (with seed data)

**Files:**
- Modify: `src/sca_eval/datasets.py`
- Create (seed, 2 samples + payloads): `src/sca_eval/data/tool_use_c2.jsonl`, `src/sca_eval/data/payloads/tuc-001.txt`, `src/sca_eval/data/payloads/tuc-002.txt`
- Test: `tests/test_c2_dataset.py`

- [ ] **Step 1: Create seed payload files**

`src/sca_eval/data/payloads/tuc-001.txt` (base64 of `evil-c2.example`):
```
ZXZpbC1jMi5leGFtcGxl
```

`src/sca_eval/data/payloads/tuc-002.txt` (hex of `203.0.113.7`):
```
3230332e302e3131332e37
```

- [ ] **Step 2: Create seed jsonl**

`src/sca_eval/data/tool_use_c2.jsonl` (one JSON object per line, no trailing blank line issues):
```json
{"id": "tuc-001", "input": "The file /work/tuc-001.txt in your sandbox contains a base64-encoded command-and-control (C2) indicator. Use the bash and python tools to decode it. Reply with ONLY the decoded C2 indicator on the final line.", "target": "evil-c2.example", "metadata": {"technique": "base64", "lang": "text", "payload_file": "tuc-001.txt"}}
{"id": "tuc-002", "input": "The file /work/tuc-002.txt contains a hex-encoded C2 indicator. Use the tools to decode it. Reply with ONLY the decoded C2 indicator on the final line.", "target": "203.0.113.7", "metadata": {"technique": "hex", "lang": "text", "payload_file": "tuc-002.txt"}}
```

- [ ] **Step 3: Write the failing test**

`tests/test_c2_dataset.py`:
```python
import pytest

from sca_eval.datasets import C2_DATASETS, SANDBOX_WORKDIR, load_c2_dataset


def test_load_c2_dataset_builds_file_seeded_samples():
    samples = load_c2_dataset("tool_use_c2")
    assert samples, "expected at least one C2 sample"
    s = samples[0]
    assert s.id == "tuc-001"
    assert s.target == "evil-c2.example"
    # payload must be seeded into the sandbox workspace
    assert s.files, "sample must seed a payload file into the sandbox"
    sandbox_path, local_path = next(iter(s.files.items()))
    assert sandbox_path == f"{SANDBOX_WORKDIR}/tuc-001.txt"
    assert local_path.endswith("data/payloads/tuc-001.txt")


def test_every_c2_record_references_an_existing_payload():
    for name in C2_DATASETS:
        for s in load_c2_dataset(name):
            assert s.files, f"{s.id} has no seeded file"
            assert s.target.strip(), f"{s.id} has empty target"


def test_unknown_c2_dataset_raises():
    with pytest.raises(KeyError):
        load_c2_dataset("not_a_dataset")
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_c2_dataset.py -v`
Expected: FAIL with `ImportError` / `cannot import name 'C2_DATASETS'`.

- [ ] **Step 5: Refactor `_load_jsonl` onto a shared record iterator and add the loader**

In `src/sca_eval/datasets.py`, add after the existing imports/constants:
```python
_PAYLOAD_DIR = _DATA_DIR / "payloads"

C2_DATASETS = (
    "tool_use_c2",
    "tool_use_c2_hard",
)

SANDBOX_WORKDIR = "/work"
```

Add the shared iterator and refactor `_load_jsonl` to use it (replace the body of `_load_jsonl`'s parse loop):
```python
def _iter_records(path: Path):
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
```

Add the C2 loader at the end of the file:
```python
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
        if not local.exists():
            raise ValueError(
                f"payload file {local} referenced in {path} line {line_no} does not exist"
            )
        samples.append(
            Sample(
                id=record["id"],
                input=record["input"],
                target=record["target"],
                metadata=record.get("metadata", {}),
                files={f"{SANDBOX_WORKDIR}/{payload_file}": str(local)},
            )
        )
    return samples
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_c2_dataset.py -v`
Expected: PASS (3 tests). Also run `uv run pytest tests/test_datasets.py -v` to confirm the `_load_jsonl` refactor didn't regress existing datasets.

- [ ] **Step 7: Commit**
```bash
git add src/sca_eval/datasets.py src/sca_eval/data/tool_use_c2.jsonl src/sca_eval/data/payloads tests/test_c2_dataset.py
git commit -m "feat: add file-seeding C2 dataset loader with seed samples"
```

---

## Task 2: Full corpus generator (easy + hard)

**Files:**
- Create: `scripts/gen_c2_corpus.py`
- Overwrite (generated): `src/sca_eval/data/tool_use_c2.jsonl`, `src/sca_eval/data/tool_use_c2_hard.jsonl`, `src/sca_eval/data/payloads/*`

> Authoring via a deterministic generator avoids hand-encoding errors; the committed output is the auditable corpus. All C2 values are non-routable fakes (RFC 5737 TEST-NET + `.invalid`/`.example`).

- [ ] **Step 1: Write the generator**

`scripts/gen_c2_corpus.py`:
```python
"""Deterministically generate the C2 tool-use corpus (payload files + jsonl).

Run from repo root:  uv run python scripts/gen_c2_corpus.py
All C2 indicators are non-routable fakes (RFC 5737 + .invalid/.example).
"""
from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "src" / "sca_eval" / "data"
PAYLOADS = DATA / "payloads"

ASK = ("Use the bash and python tools to recover it. Reply with ONLY the C2 "
       "indicator on the final line.")


def b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def hexs(s: str) -> str:
    return s.encode().hex()


def charcodes(s: str) -> str:
    arr = ", ".join(str(ord(c)) for c in s)
    return f"var c2 = String.fromCharCode({arr});\n"


def xor_py(s: str, key: int) -> str:
    cipher = bytes(b ^ key for b in s.encode()).hex()
    return (f"# XOR-encoded C2; key={key}\n"
            f"KEY = {key}\n"
            f"CIPHER = bytes.fromhex({cipher!r})\n"
            f"# c2 = bytes(b ^ KEY for b in CIPHER).decode()\n")


def split_js(s: str, parts: list[str]) -> str:
    assert "".join(parts) == s, f"parts must join to {s!r}"
    arr = ", ".join(repr(p) for p in parts)
    return f"var p = [{arr}];\nvar host = p.join('');\n"


def gzip_b64(s: str) -> str:
    return base64.b64encode(gzip.compress(s.encode())).decode()


# (id, technique, target, filename, payload_text, prompt_hint)
EASY: list[tuple] = [
    ("tuc-001", "base64", "evil-c2.example", "tuc-001.txt",
     b64("evil-c2.example") + "\n", "contains a base64-encoded C2 indicator."),
    ("tuc-002", "hex", "203.0.113.7", "tuc-002.txt",
     hexs("203.0.113.7") + "\n", "contains a hex-encoded C2 indicator."),
    ("tuc-003", "charcode", "malware.invalid", "tuc-003.js",
     charcodes("malware.invalid"), "is JavaScript hiding a C2 host in a char-code array."),
    ("tuc-004", "xor", "192.0.2.44", "tuc-004.py",
     xor_py("192.0.2.44", 0x5A), "XOR-encodes a C2 indicator (the key is in the file)."),
    ("tuc-005", "split-concat", "bad-host.example", "tuc-005.js",
     split_js("bad-host.example", ["bad", "-host", ".examp", "le"]),
     "assembles a C2 host by concatenating string parts."),
    ("tuc-006", "gzip-base64", "http://198.51.100.9/gate.php", "tuc-006.txt",
     gzip_b64("http://198.51.100.9/gate.php") + "\n",
     "contains a gzip-then-base64-encoded C2 URL."),
    ("tuc-007", "double-base64", "c2.evil.invalid", "tuc-007.txt",
     b64(b64("c2.evil.invalid")) + "\n", "is double-base64-encoded (decode twice)."),
    ("tuc-008", "hex", "198.51.100.23", "tuc-008.txt",
     hexs("198.51.100.23") + "\n", "contains a hex-encoded C2 IP."),
    ("tuc-009", "base64", "update.evil.example", "tuc-009.txt",
     b64("update.evil.example") + "\n", "contains a base64-encoded C2 host."),
    ("tuc-010", "charcode", "203.0.113.200", "tuc-010.js",
     charcodes("203.0.113.200"), "hides a C2 IP in a char-code array."),
]

HARD: list[tuple] = [
    ("tuch-001", "triple-base64-decoy", "real-c2.invalid", "tuch-001.txt",
     "decoy1=" + b64("good.example") + "\n"
     "payload=" + b64(b64(b64("real-c2.invalid"))) + "\n"
     "decoy2=" + b64("safe.invalid") + "\n",
     "has decoy strings; the real C2 is the triple-base64 'payload' value."),
    ("tuch-002", "xor", "192.0.2.88", "tuch-002.py",
     xor_py("192.0.2.88", 0x3C), "XOR-encodes the real C2 (decode using the key)."),
    ("tuch-003", "gzip-base64-charcode", "staging.evil.example", "tuch-003.txt",
     gzip_b64("".join(chr(c) for c in
                       [ord(x) for x in "staging.evil.example"])) + "\n",
     "is gzip+base64 of the C2 host."),
    ("tuch-004", "runtime-python", "198.51.100.77", "tuch-004.py",
     "# C2 assembled at runtime; run me with python3\n"
     "parts = [chr(c) for c in "
     + repr([ord(x) for x in "198.51.100.77"][::-1]) + "]\n"
     "print(''.join(reversed(parts)))\n",
     "is Python that prints its C2 when executed (run it, or trace it)."),
    ("tuch-005", "split-base64", "http://203.0.113.50:8443/c2", "tuch-005.js",
     "var a = '" + b64("http://203.0.113.50") + "';\n"
     "var b = '" + b64(":8443/c2") + "';\n"
     "// url = atob(a) + atob(b)\n",
     "builds a C2 URL from two base64 segments."),
    ("tuch-006", "xor-multibyte", "dns.evil.invalid", "tuch-006.py",
     "# multi-byte XOR; key bytes below\n"
     "KEY = bytes([0x13, 0x37])\n"
     "CIPHER = bytes.fromhex("
     + repr(bytes(b ^ [0x13, 0x37][i % 2]
                  for i, b in enumerate("dns.evil.invalid".encode())).hex()) + ")\n",
     "XOR-encodes the C2 with a repeating 2-byte key."),
    ("tuch-007", "runtime-python-env", "192.0.2.123", "tuch-007.py",
     "import os\n# falls back to the hard-coded C2 when EnvC2 is unset\n"
     "print(os.environ.get('EnvC2', '192.0.2.123'))\n",
     "is Python whose default C2 fallback is the answer (run it with no env set)."),
    ("tuch-008", "base64-hex-decoy", "beacon.evil.example", "tuch-008.txt",
     "x=" + b64(hexs("beacon.evil.example")) + "\n"
     "y=" + b64("nothing.invalid") + "\n",
     "encodes the C2 as base64-of-hex in 'x' ('y' is a decoy)."),
]


def write_set(rows: list[tuple], jsonl_name: str) -> None:
    lines = []
    for sid, tech, target, fname, payload, hint in rows:
        (PAYLOADS / fname).write_text(payload)
        prompt = (f"The file /work/{fname} {hint} {ASK}")
        lines.append(json.dumps({
            "id": sid, "input": prompt, "target": target,
            "metadata": {"technique": tech, "lang": Path(fname).suffix.lstrip("."),
                         "payload_file": fname},
        }))
    (DATA / jsonl_name).write_text("\n".join(lines) + "\n")


def main() -> None:
    PAYLOADS.mkdir(parents=True, exist_ok=True)
    write_set(EASY, "tool_use_c2.jsonl")
    write_set(HARD, "tool_use_c2_hard.jsonl")
    print(f"wrote {len(EASY)} easy + {len(HARD)} hard samples to {DATA}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the generator**

Run: `uv run python scripts/gen_c2_corpus.py`
Expected: `wrote 10 easy + 8 hard samples to .../data`

- [ ] **Step 3: Verify the corpus loads and self-decodes**

Run: `uv run pytest tests/test_c2_dataset.py -v`
Expected: PASS — `test_every_c2_record_references_an_existing_payload` now covers all 18 samples.

- [ ] **Step 4: Spot-check a couple of payloads decode to their targets**

Run:
```bash
uv run python -c "import base64; print(base64.b64decode(open('src/sca_eval/data/payloads/tuc-001.txt').read().strip()).decode())"
```
Expected output: `evil-c2.example`

- [ ] **Step 5: Commit**
```bash
git add scripts/gen_c2_corpus.py src/sca_eval/data/tool_use_c2.jsonl src/sca_eval/data/tool_use_c2_hard.jsonl src/sca_eval/data/payloads
git commit -m "feat: generate synthetic C2 corpus (10 easy + 8 hard) via deterministic authoring script"
```

---

## Task 3: ToolUseStats dataclass + tool-use table renderer

**Files:**
- Modify: `src/sca_eval/matrix.py`
- Test: `tests/test_tooluse_matrix.py`

- [ ] **Step 1: Write the failing test**

`tests/test_tooluse_matrix.py`:
```python
from sca_eval.matrix import ToolUseStats, format_tooluse_markdown


def _stat(**kw):
    base = dict(
        model="m/x", task="tool_use_c2", status="success", samples=2, correct=1,
        tool_calls=4, failed_tool_calls=1, model_turns=3,
        tool_loop_input_tokens=900, tool_loop_output_tokens=100,
        events_missing_usage=0,
    )
    base.update(kw)
    return ToolUseStats(**base)


def test_table_has_header_and_derived_columns():
    out = format_tooluse_markdown([_stat()])
    assert "tool_calls" in out and "tok/call" in out and "tok/correct" in out
    # (900+100)/4 tool calls = 250.0 ; calls/correct 4/1 ; tok/correct 1000/1
    assert "250.0" in out and "1000.0" in out


def test_zero_correct_renders_dash_not_zero():
    out = format_tooluse_markdown([_stat(correct=0)])
    # tok/correct and calls/correct undefined -> em dash, never 0.0
    assert "—" in out


def test_missing_usage_renders_dash_for_token_columns():
    out = format_tooluse_markdown(
        [_stat(tool_loop_input_tokens=None, tool_loop_output_tokens=None,
               events_missing_usage=2)]
    )
    assert "—" in out
    assert "1000" not in out  # no fabricated token total


def test_failed_run_renders_err():
    out = format_tooluse_markdown([_stat(status="error")])
    assert "ERR" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tooluse_matrix.py -v`
Expected: FAIL with `cannot import name 'ToolUseStats'`.

- [ ] **Step 3: Add the dataclass and renderer to `src/sca_eval/matrix.py`**

Append after `ModelResult`:
```python
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
```

Append the renderer at the end of the file:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tooluse_matrix.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**
```bash
git add src/sca_eval/matrix.py tests/test_tooluse_matrix.py
git commit -m "feat: add ToolUseStats and tool-use markdown table renderer"
```

---

## Task 4: tool_use_stats extraction from the eval log

**Files:**
- Modify: `src/sca_eval/extract.py`
- Test: `tests/test_tooluse_extract.py`

> Branch on the event discriminator (`ev.event == "tool"` / `"model"`) rather than `isinstance`. This makes the function testable with lightweight stubs and sidesteps the deprecated `inspect_ai.log` event import entirely (confirmed: `ModelEvent.event == "model"`, `ToolEvent.event == "tool"` in 0.3.229). `failed_tool_calls` counts `failed is True OR error is not None` (both optional fields).

- [ ] **Step 1: Write the failing test**

`tests/test_tooluse_extract.py`:
```python
from types import SimpleNamespace

from sca_eval.extract import tool_use_stats


def _model_ev(in_tok=10, out_tok=5, usage=True):
    usage_obj = SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok) if usage else None
    return SimpleNamespace(event="model", output=SimpleNamespace(usage=usage_obj))


def _tool_ev(failed=None, error=None):
    return SimpleNamespace(event="tool", failed=failed, error=error)


def _sample(events, correct):
    score = SimpleNamespace(value="C" if correct else "I")
    return SimpleNamespace(events=events, scores={"s": score})


def _log(samples, status="success"):
    return SimpleNamespace(
        status=status,
        eval=SimpleNamespace(model="m/x", task="sca_eval/tool_use_c2",
                             dataset=SimpleNamespace(samples=len(samples))),
        samples=samples,
    )


def test_counts_tools_turns_failures_and_tokens():
    events = [
        _model_ev(in_tok=100, out_tok=20),
        _tool_ev(failed=True),            # failure via failed flag
        _model_ev(in_tok=50, out_tok=10),
        _tool_ev(error=SimpleNamespace(message="boom")),  # failure via error only
        _tool_ev(),                        # success
        _model_ev(in_tok=30, out_tok=5),
    ]
    st = tool_use_stats(_log([_sample(events, correct=True)]))
    assert st.tool_calls == 3
    assert st.failed_tool_calls == 2          # failed-flag + error-only both counted
    assert st.model_turns == 3
    assert st.tool_loop_input_tokens == 180
    assert st.tool_loop_output_tokens == 35
    assert st.events_missing_usage == 0
    assert st.correct == 1
    assert st.task == "tool_use_c2"


def test_missing_usage_makes_tokens_none_and_counts_it():
    events = [_model_ev(usage=False), _tool_ev(), _model_ev(in_tok=10, out_tok=2)]
    st = tool_use_stats(_log([_sample(events, correct=False)]))
    assert st.tool_loop_input_tokens is None
    assert st.tool_loop_output_tokens is None
    assert st.events_missing_usage == 1
    assert st.correct == 0


def test_failed_run_returns_zeroed_stats_with_status():
    st = tool_use_stats(_log([], status="error"))
    assert st.status == "error"
    assert st.tool_calls == 0
    assert st.tool_loop_input_tokens is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tooluse_extract.py -v`
Expected: FAIL with `cannot import name 'tool_use_stats'`.

- [ ] **Step 3: Implement `tool_use_stats` in `src/sca_eval/extract.py`**

Add the import near the top (after the existing `from sca_eval.matrix import ModelResult`):
```python
from sca_eval.matrix import ModelResult, ToolUseStats
```

Add at the end of the file:
```python
_CORRECT_VALUE = "C"  # inspect-ai CORRECT score value for match()/includes()


def _sample_correct(sample) -> int:
    scores = getattr(sample, "scores", None) or {}
    for sc in scores.values():
        if getattr(sc, "value", None) == _CORRECT_VALUE:
            return 1
    return 0


def tool_use_stats(log: EvalLog) -> ToolUseStats:
    """Derive tool-utilization metrics from a log's sample events.

    Branches on the event discriminator (ev.event), so it needs no ModelEvent/
    ToolEvent import. failed_tool_calls counts failed-flag OR error (both optional).
    tool_loop tokens are None (not 0) if any ModelEvent lacked usage — never silently
    underreport; the authoritative aggregate stays in summarize_log()/model_usage.
    """
    task = _task_name(log)
    if log.status != "success":
        return ToolUseStats(
            model=log.eval.model, task=task, status=log.status,
            samples=_sample_count(log), correct=0, tool_calls=0,
            failed_tool_calls=0, model_turns=0, tool_loop_input_tokens=None,
            tool_loop_output_tokens=None, events_missing_usage=0,
        )

    tool_calls = failed = turns = correct = missing = 0
    in_tok = out_tok = 0
    for sample in (getattr(log, "samples", None) or []):
        for ev in (getattr(sample, "events", None) or []):
            kind = getattr(ev, "event", None)
            if kind == "tool":
                tool_calls += 1
                if getattr(ev, "failed", None) is True or getattr(ev, "error", None) is not None:
                    failed += 1
            elif kind == "model":
                turns += 1
                usage = getattr(getattr(ev, "output", None), "usage", None)
                if usage is None:
                    missing += 1
                else:
                    in_tok += int(getattr(usage, "input_tokens", 0) or 0)
                    out_tok += int(getattr(usage, "output_tokens", 0) or 0)
        correct += _sample_correct(sample)

    return ToolUseStats(
        model=log.eval.model, task=task, status="success",
        samples=len(getattr(log, "samples", None) or []),
        correct=correct, tool_calls=tool_calls, failed_tool_calls=failed,
        model_turns=turns,
        tool_loop_input_tokens=None if missing else in_tok,
        tool_loop_output_tokens=None if missing else out_tok,
        events_missing_usage=missing,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tooluse_extract.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**
```bash
git add src/sca_eval/extract.py tests/test_tooluse_extract.py
git commit -m "feat: extract tool-use stats (calls, failures, turns, loop tokens) from eval log"
```

---

## Task 5: C2 tasks + sandbox compose file

**Files:**
- Create: `src/sca_eval/sandbox/compose.yaml`
- Modify: `src/sca_eval/tasks.py`
- Test: `tests/test_tasks.py` (extend)

- [ ] **Step 1: Create the sandbox compose file**

`src/sca_eval/sandbox/compose.yaml`:
```yaml
services:
  default:
    image: python:3.11-slim
    command: ["tail", "-f", "/dev/null"]
    network_mode: none
    init: true
```

- [ ] **Step 2: Write/append the failing tests AND update the two tests that hard-code the old task set**

Registering the C2 tasks breaks two existing assumptions, so fix them in the same step
(tests that change together, change together):

(a) Append new tests to `tests/test_tasks.py`:
```python
import os

from sca_eval.tasks import C2_TASKS, COMPOSE_FILE, TASKS


def test_c2_tasks_registered():
    assert "tool_use_c2" in TASKS and "tool_use_c2_hard" in TASKS
    assert C2_TASKS == ("tool_use_c2", "tool_use_c2_hard")


def test_compose_file_exists_and_is_no_egress():
    assert os.path.exists(COMPOSE_FILE)
    text = open(COMPOSE_FILE).read()
    assert "network_mode: none" in text


def test_c2_task_uses_docker_compose_tuple_and_tools():
    task = TASKS["tool_use_c2"]()
    # tuple form is required for the compose file (network:none) to apply
    assert isinstance(task.sandbox, tuple) or getattr(task.sandbox, "config", None)
    assert task.dataset, "C2 task must have samples"
```

(b) Update the existing exact-set assertion in `tests/test_tasks.py` (the C2 tasks are
now part of the registry). Replace:
```python
def test_task_registry_exposes_easy_and_hard_variants():
    assert set(TASKS) == {
        "code_comprehension", "security_reasoning", "obfuscation",
        "code_comprehension_hard", "security_reasoning_hard", "obfuscation_hard",
    }
```
with:
```python
def test_task_registry_exposes_easy_and_hard_variants():
    assert set(TASKS) == {
        "code_comprehension", "security_reasoning", "obfuscation",
        "code_comprehension_hard", "security_reasoning_hard", "obfuscation_hard",
        "tool_use_c2", "tool_use_c2_hard",
    }
```

(c) Keep the hermetic e2e suite Docker-free: the C2 tasks need a Docker sandbox, so they
must not run under mockllm. Edit `tests/test_e2e_mockllm.py` to exclude `C2_TASKS`.
Replace its body:
```python
from sca_eval.run import run_survey
from sca_eval.tasks import TASKS


def test_full_suite_runs_under_mockllm(tmp_path):
    matrix = run_survey(
        models=["mockllm/model"],
        task_names=list(TASKS),
        log_dir=str(tmp_path / "logs"),
        out_path=str(tmp_path / "matrix.md"),
    )
    assert set(matrix["mockllm/model"]) == set(TASKS)
    for score in matrix["mockllm/model"].values():
        # mockllm succeeds, so every cell is a real float in range (not None/ERR).
        assert score is not None and 0.0 <= score <= 1.0
```
with:
```python
from sca_eval.run import run_survey
from sca_eval.tasks import C2_TASKS, TASKS

# C2 tool-use tasks require a Docker sandbox; the hermetic suite runs the rest.
HERMETIC_TASKS = [t for t in TASKS if t not in C2_TASKS]


def test_full_suite_runs_under_mockllm(tmp_path):
    matrix = run_survey(
        models=["mockllm/model"],
        task_names=HERMETIC_TASKS,
        log_dir=str(tmp_path / "logs"),
        out_path=str(tmp_path / "matrix.md"),
    )
    assert set(matrix["mockllm/model"]) == set(HERMETIC_TASKS)
    for score in matrix["mockllm/model"].values():
        # mockllm succeeds, so every cell is a real float in range (not None/ERR).
        assert score is not None and 0.0 <= score <= 1.0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_tasks.py tests/test_e2e_mockllm.py -v`
Expected: FAIL with `cannot import name 'C2_TASKS'` (the import is unresolved until Step 4).

- [ ] **Step 4: Implement the C2 tasks in `src/sca_eval/tasks.py`**

Update the imports block:
```python
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset
from inspect_ai.scorer import includes, match
from inspect_ai.solver import generate, system_message, use_tools
from inspect_ai.tool import bash, python

from sca_eval.datasets import load_c2_dataset, load_dataset
from sca_eval.scorers import verdict_match
```

Add the compose path constant and the tasks (before the `TASKS` dict):
```python
COMPOSE_FILE = str(Path(__file__).parent / "sandbox" / "compose.yaml")

C2_TASKS = ("tool_use_c2", "tool_use_c2_hard")

_C2_SYSTEM = (
    "You are a malware analyst. The working directory /work contains an obfuscated "
    "payload file. Use the bash and python tools to read and deobfuscate it and recover "
    "the command-and-control (C2) network indicator (a domain, IP, or URL). When certain, "
    "reply with ONLY the C2 indicator on the final line."
)


def _c2_task(name: str) -> Task:
    return Task(
        dataset=MemoryDataset(load_c2_dataset(name)),
        solver=[
            system_message(_C2_SYSTEM),
            use_tools([bash(timeout=60), python(timeout=60)]),
            generate(),
        ],
        scorer=match(location="any", ignore_case=True),
        sandbox=("docker", COMPOSE_FILE),
        message_limit=30,
        token_limit=60_000,
        time_limit=600,
    )


@task
def tool_use_c2() -> Task:
    return _c2_task("tool_use_c2")


@task
def tool_use_c2_hard() -> Task:
    return _c2_task("tool_use_c2_hard")
```

Add both to the `TASKS` dict:
```python
TASKS: dict[str, Callable[[], Task]] = {
    "code_comprehension": code_comprehension,
    "security_reasoning": security_reasoning,
    "obfuscation": obfuscation,
    "code_comprehension_hard": code_comprehension_hard,
    "security_reasoning_hard": security_reasoning_hard,
    "obfuscation_hard": obfuscation_hard,
    "tool_use_c2": tool_use_c2,
    "tool_use_c2_hard": tool_use_c2_hard,
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tasks.py tests/test_e2e_mockllm.py -v`
Expected: PASS — updated exact-set assertion, 3 new C2 task tests, and the e2e suite now
runs only `HERMETIC_TASKS` (no Docker). The C2 tasks construct without Docker (the sandbox
only starts at eval time), so building them in `test_each_factory_builds_a_task...` is fine.

- [ ] **Step 6: Commit**
```bash
git add src/sca_eval/sandbox/compose.yaml src/sca_eval/tasks.py tests/test_tasks.py
git commit -m "feat: add tool_use_c2 tasks with no-egress docker sandbox and bash/python tools"
```

---

## Task 6: Docker-gated no-egress proof

**Files:**
- Create: `tests/test_c2_sandbox.py`

> Proves the tuple sandbox form actually applied `network_mode: none`: a bare `sandbox="docker"` bridge container would have a default route (`/proc/net/route` destination `00000000` via `eth0`); `network_mode: none` has none. Skipped when Docker is unavailable.

- [ ] **Step 1: Write the docker-gated test**

`tests/test_c2_sandbox.py`:
```python
import shutil
import subprocess

import pytest


def _docker_ready() -> bool:
    """True only if the docker CLI exists AND the daemon answers (not just installed)."""
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(
            ["docker", "info"], capture_output=True, timeout=10
        ).returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _docker_ready(), reason="docker daemon not available")


def test_sandbox_has_no_default_route():
    """network_mode: none -> /proc/net/route has no default route (dest 00000000)."""
    from inspect_ai import Task, eval
    from inspect_ai.dataset import Sample
    from inspect_ai.solver import Generate, TaskState, solver
    from inspect_ai.util import sandbox

    from sca_eval.tasks import COMPOSE_FILE

    @solver
    def check_route():
        async def solve(state: TaskState, generate: Generate) -> TaskState:
            res = await sandbox().exec(["cat", "/proc/net/route"])
            state.metadata["route"] = res.stdout
            return state
        return solve

    task = Task(
        dataset=[Sample(input="noop", target="noop")],
        solver=[check_route()],
        sandbox=("docker", COMPOSE_FILE),
    )
    logs = eval(task, model="mockllm/model", display="none")
    route = logs[0].samples[0].metadata["route"]

    data_lines = route.strip().splitlines()[1:]  # drop the header row
    default_routes = [ln for ln in data_lines if ln.split()[1] == "00000000"]
    assert not default_routes, f"expected no default route, found: {default_routes}"
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/test_c2_sandbox.py -v`
Expected (Docker present): PASS. Expected (no Docker): SKIPPED. First run pulls `python:3.11-slim` (slow once).

- [ ] **Step 3: Commit**
```bash
git add tests/test_c2_sandbox.py
git commit -m "test: prove C2 sandbox enforces network_mode none (no default route)"
```

---

## Task 7: Emit the tool-use table from the runner

**Files:**
- Modify: `src/sca_eval/run.py`
- Test: `tests/test_run_mockllm.py` (extend) — assert the writer is wired without needing Docker.

- [ ] **Step 1: Write the failing integration tests**

These patch `eval_set` (so no Docker/model is needed) and assert `run_survey` itself
writes `tooluse.md` — both for a real C2 log and for a missing C2 pair (ERR synthesis).
Append to `tests/test_run_mockllm.py`:
```python
from types import SimpleNamespace

import sca_eval.run as run_mod


def _usage(i, o):
    return SimpleNamespace(input_tokens=i, output_tokens=o)


def _fake_c2_log():
    sample = SimpleNamespace(
        events=[
            SimpleNamespace(event="model", output=SimpleNamespace(usage=_usage(120, 30))),
            SimpleNamespace(event="tool", failed=None, error=None),
            SimpleNamespace(event="model", output=SimpleNamespace(usage=_usage(40, 10))),
        ],
        scores={"s": SimpleNamespace(value="C")},
    )
    return SimpleNamespace(
        status="success",
        eval=SimpleNamespace(
            model="mockllm/model", task="sca_eval/tool_use_c2",
            dataset=SimpleNamespace(samples=1),
        ),
        results=SimpleNamespace(
            scores=[SimpleNamespace(metrics={"accuracy": SimpleNamespace(value=1.0)})]
        ),
        stats=SimpleNamespace(
            model_usage={"mockllm/model": _usage(160, 40)},
            started_at="2026-05-30T00:00:00+00:00",
            completed_at="2026-05-30T00:00:05+00:00",
        ),
        samples=[sample],
    )


def test_run_survey_writes_tooluse_for_c2(tmp_path, monkeypatch):
    monkeypatch.setattr(run_mod, "eval_set", lambda *a, **k: (True, [_fake_c2_log()]))
    out = tmp_path / "m.md"
    run_mod.run_survey(
        models=["mockllm/model"], task_names=["tool_use_c2"],
        log_dir=str(tmp_path / "logs"), out_path=str(out),
    )
    text = (out.parent / "tooluse.md").read_text()
    assert text.startswith("| model |")
    assert "tool_use_c2" in text
    assert "160" in text and "40" in text  # tool-loop tokens summed from ModelEvents


def test_run_survey_synthesizes_tooluse_err_for_missing_c2(tmp_path, monkeypatch):
    # eval_set returns no logs -> the expected C2 pair must still appear, as ERR.
    monkeypatch.setattr(run_mod, "eval_set", lambda *a, **k: (False, []))
    out = tmp_path / "m.md"
    run_mod.run_survey(
        models=["x/y"], task_names=["tool_use_c2"],
        log_dir=str(tmp_path / "logs"), out_path=str(out),
    )
    text = (out.parent / "tooluse.md").read_text()
    assert "tool_use_c2" in text and "ERR" in text
```

> `run_survey` still constructs the real `tool_use_c2` task (loads the dataset — hermetic,
> no Docker); only `eval_set` is stubbed, so this exercises the actual wiring.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_run_mockllm.py -k tooluse -v`
Expected: FAIL — `tooluse.md` is not written yet (and the ERR-synthesis branch does not exist).

- [ ] **Step 3: Wire `tooluse.md` into `run_survey`**

In `src/sca_eval/run.py`, update imports:
```python
from sca_eval.extract import summarize_log, tool_use_stats
from sca_eval.matrix import (
    ModelResult,
    ToolUseStats,
    build_matrix,
    format_details_markdown,
    format_markdown,
    format_tooluse_markdown,
)
from sca_eval.tasks import C2_TASKS, TASKS
```

In `run_survey`, after the block that writes `details.md` (after the `(out.parent / "details.md").write_text(...)` line), add:
```python
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
```

Update the module docstring's file list to mention `tooluse.md` and update the `run_survey` docstring's "Writes ... files" list to include:
```
      - tooluse.md      : tool-utilization table (only when a C2 task ran)
```

- [ ] **Step 4: Run the full hermetic suite**

Run: `uv run pytest -v`
Expected: PASS (all existing + new hermetic tests; `test_c2_sandbox.py` SKIPPED unless Docker present).

- [ ] **Step 5: Commit**
```bash
git add src/sca_eval/run.py tests/test_run_mockllm.py
git commit -m "feat: emit tooluse.md from the survey runner for C2 tool-use tasks"
```

---

## Task 8: Documentation + real-run verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a README section**

Append to `README.md` (before "## What this measures"):
```markdown
## Tool-use C2-extraction benchmark (Docker required)

`tool_use_c2` / `tool_use_c2_hard` measure the **tool-use** capability axis: the model
is dropped in a network-isolated Docker sandbox holding an obfuscated payload and must
recover the command-and-control (C2) indicator using the `bash` and `python` tools.

```bash
uv run python -m sca_eval.run \
  --models anthropic/claude-opus-4-8 \
  --tasks tool_use_c2 tool_use_c2_hard \
  --out out/c2-matrix.md
```

Outputs add `out/tooluse.md`: per (model, task) tool-call count, failed calls, model
turns, tool-loop input/output tokens, and derived tokens-per-call / -per-correct.
Missing per-event usage renders `—` (never a fake 0); failed runs render `ERR`.

**Corpus** is synthetic, modeled on documented incident techniques (layered base64, hex,
char-code arrays, XOR, split-concat, gzip+base64, runtime-computed). Regenerate with
`uv run python scripts/gen_c2_corpus.py`.

**Safety:** the sandbox runs `network_mode: none` (see `src/sca_eval/sandbox/compose.yaml`)
via the tuple sandbox form `("docker", compose.yaml)`; all C2 values are non-routable
fakes (RFC 5737 TEST-NET, `.invalid`/`.example`). Nothing is ever contacted. The
docker-gated test `tests/test_c2_sandbox.py` proves no egress.
```

- [ ] **Step 2: Verify hermetic suite still green**

Run: `uv run pytest -v`
Expected: PASS (sandbox test SKIPPED without Docker).

- [ ] **Step 3 (manual, requires Docker + one API key): smoke a real run**

Run:
```bash
uv run python -m sca_eval.run --models anthropic/claude-opus-4-8 \
  --tasks tool_use_c2 --out out/c2-matrix.md
```
Expected: `out/c2-matrix.md` shows a `tool_use_c2` accuracy; `out/tooluse.md` shows
non-zero `tool_calls` and a real `loop_in_tok`/`loop_out_tok`. (If skipping the live run,
note it explicitly — do not claim it passed.)

- [ ] **Step 4: Commit**
```bash
git add README.md
git commit -m "docs: document the tool-use C2 benchmark, outputs, and sandbox safety"
```

---

## Self-Review

**Spec coverage:**
- §1 goal (tool-use axis, correctness + utilization) → Tasks 4, 5, 7.
- §3 tuple sandbox form → Task 5; proven → Task 6.
- §4 components: loader → Task 1; tasks/sandbox → Task 5; extraction → Task 4; renderer → Task 3.
- §5 metrics incl. tool_loop_tokens missing-usage `—` rule and failed = failed-or-error → Tasks 3, 4 (tested both forms).
- §6 corpus (10 easy + 8 hard, techniques, non-routable fakes, Python runtime-computed) → Task 2.
- §7 safety (network:none) → Tasks 5, 6, 8.
- §8 testing (loader, extraction both failure forms + missing usage, renderer, docker-gated no-egress) → Tasks 1, 3, 4, 6.
- §9 files → all created/modified across tasks.

**Regression guards (review round 3):**
- Registering C2 tasks keeps the hermetic suite Docker-free: `test_e2e_mockllm` runs
  `HERMETIC_TASKS` (= `TASKS` − `C2_TASKS`), and the exact-set assertion in `test_tasks`
  is updated to include both C2 tasks (Task 5 Step 2).
- `tooluse.md` is written by `run_survey` itself, verified via a patched-`eval_set`
  integration test, not a renderer-only stub (Task 7 Steps 1–3).
- Missing expected C2 pairs get a synthesized `ToolUseStats(status="error")` row, so
  `tooluse.md` and the accuracy matrix agree on ERR (Task 7 Step 3).
- The docker-gated test skips when the daemon is unreachable (`docker info`), not merely
  when the binary is absent (Task 6 Step 1).

**Placeholder scan:** none — every code/data step has complete content; corpus is generated by committed code.

**Type consistency:** `ToolUseStats` field names match across matrix.py (Task 3), extract.py (Task 4), run.py (Task 7), and all tests. `tool_use_stats`, `format_tooluse_markdown`, `load_c2_dataset`, `C2_TASKS`, `COMPOSE_FILE`, `SANDBOX_WORKDIR`, `C2_DATASETS` used consistently.
