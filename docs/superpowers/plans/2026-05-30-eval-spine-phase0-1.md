# Eval Spine (Phase 0–1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible inspect-ai harness that runs language-agnostic capability tasks across many models and emits a comparable capability matrix (Phase 0 foundations + Phase 1 model survey from the design spec).

**Architecture:** A small Python package. Capability tasks are inspect-ai `@task`s backed by JSONL seed datasets. A pure-Python aggregation layer turns inspect-ai `EvalLog`s into a `ModelResult` table and renders a Markdown matrix plus a details table (accuracy, latency, token split, cost). A thin `run.py` wraps `eval_set()` to fan out tasks × models, honors the `success` boolean, and never lets an infra failure masquerade as a real `0.00` score. Model-correctness logic is unit-tested offline (pure functions); the inspect-ai integration is validated end-to-end against the `mockllm` provider so no paid API calls are needed in CI.

**Tech Stack:** Python ≥3.11, [inspect-ai](https://inspect.aisi.org.uk/) (pinned + `uv.lock` committed), pytest, uv (package manager). Real model runs:
- **Closed SOTA:** `anthropic/claude-opus-4-8`, `openai/gpt-5.5`.
- **Open SOTA (self-hosted via an OpenAI-compatible endpoint):** GLM-5.1, DeepSeek V4 Pro, Qwen 3.6.
- **Tests:** `mockllm/model` (no key, no network).

**Scope boundary:** This plan covers ONLY Phase 0–1 (eval spine + capability matrix). Capability axes implemented: code comprehension, security reasoning, obfuscation. The **tool-use** axis, the **agentic-tool survey** (Phase 2), the **SCA harness** (Phase 3), and **npm validation** (Phase 4) are out of scope and get their own plans. The npm corpus is NOT touched here (it stays quarantined per spec §6b).

---

### Task 1: Project scaffold + git init + pinned deps

**Files:**
- Create: `pyproject.toml`
- Create: `src/sca_eval/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`
- Create: `.gitignore`
- Create: `uv.lock` (generated, committed)

- [ ] **Step 1: Initialize the git repository**

This workspace is not yet a git repo (`git rev-parse --show-toplevel` → fatal). Every task ends in a commit, so init first. The empty remote `https://github.com/get-wright/model-harness-eval.git` is the origin.

Run:
```bash
git init -b main
git config user.name >/dev/null 2>&1 || git config user.name "capstone"
git config user.email >/dev/null 2>&1 || git config user.email "capstone@local"
git remote get-url origin >/dev/null 2>&1 || git remote add origin https://github.com/get-wright/model-harness-eval.git
```
Expected: `Initialized empty Git repository`; `origin` set. (Pushing to origin happens after the final review, not per task.)

- [ ] **Step 2: Write the failing smoke test**

`tests/test_smoke.py`:
```python
def test_package_imports():
    import sca_eval

    assert sca_eval.__version__ == "0.1.0"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sca_eval'`

- [ ] **Step 4: Create the package + config**

`pyproject.toml` (inspect-ai pinned to a minor range; exact build frozen in `uv.lock`):
```toml
[project]
name = "sca-eval"
version = "0.1.0"
description = "Model-independent capability eval spine for AI-augmented SCA analysis"
requires-python = ">=3.11"
dependencies = [
    "inspect-ai>=0.3,<0.4",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/sca_eval"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

`src/sca_eval/__init__.py`:
```python
__version__ = "0.1.0"
```

`tests/__init__.py`: (empty file)

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
logs/
out/
.code-review-graph/
```

- [ ] **Step 5: Install deps (locking) and run the test**

Run:
```bash
uv sync --extra dev        # creates/updates uv.lock with the resolved inspect-ai build
uv run pytest tests/test_smoke.py -v
```
Expected: PASS. Confirm `uv.lock` now exists (pins the exact inspect-ai version the rest of the plan depends on).

- [ ] **Step 6: Commit (including the lockfile)**

```bash
git add pyproject.toml uv.lock src/sca_eval/__init__.py tests/__init__.py tests/test_smoke.py .gitignore
git commit -m "chore: scaffold sca-eval package, init repo, pin deps"
```

---

### Task 2: Capability matrix aggregation (pure core)

The reusable measurement core. Pure Python — no inspect-ai imports — so fully testable offline. `ModelResult` carries the full Phase-1 axis set (accuracy, samples, input/output tokens, duration, cost) and a `status`; `accuracy` is `None` for a failed run so failures never render as a real `0.00`.

**Files:**
- Create: `src/sca_eval/matrix.py`
- Test: `tests/test_matrix.py`

- [ ] **Step 1: Write the failing test**

`tests/test_matrix.py`:
```python
from sca_eval.matrix import (
    ModelResult,
    build_matrix,
    format_markdown,
    format_details_markdown,
)


def _ok(model, task, accuracy, **kw):
    base = dict(samples=5, input_tokens=100, output_tokens=50,
                duration_s=10.0, cost_usd=0.0, status="success")
    base.update(kw)
    return ModelResult(model=model, task=task, accuracy=accuracy, **base)


def test_total_tokens_is_input_plus_output():
    r = _ok("m", "t", 0.5, input_tokens=100, output_tokens=50)
    assert r.total_tokens == 150


def test_build_matrix_groups_by_model_and_task():
    results = [
        _ok("anthropic/x", "obfuscation", 0.80),
        _ok("anthropic/x", "security", 0.60),
        _ok("openai/y", "obfuscation", 0.40),
    ]
    matrix = build_matrix(results)

    assert matrix["anthropic/x"]["obfuscation"] == 0.80
    assert matrix["anthropic/x"]["security"] == 0.60
    assert matrix["openai/y"]["obfuscation"] == 0.40
    assert "security" not in matrix["openai/y"]


def test_failed_run_keeps_none_accuracy_and_renders_as_err():
    results = [
        _ok("m1", "obfuscation", 0.5),
        ModelResult(model="m1", task="security", accuracy=None, samples=0,
                    input_tokens=0, output_tokens=0, duration_s=0.0,
                    cost_usd=0.0, status="error"),
    ]
    matrix = build_matrix(results)
    assert matrix["m1"]["security"] is None

    md = format_markdown(matrix)
    assert "ERR" in md          # failure is visible, never 0.00
    assert "0.50" in md


def test_format_markdown_has_one_row_per_model_and_task_columns():
    md = format_markdown(build_matrix([
        _ok("m1", "obfuscation", 0.5),
        _ok("m1", "security", 1.0),
    ]))
    assert "| model |" in md
    assert "obfuscation" in md and "security" in md
    assert "| m1 |" in md
    assert "0.50" in md and "1.00" in md


def test_details_table_reports_all_axes():
    md = format_details_markdown([
        _ok("m1", "obfuscation", 0.5, input_tokens=120, output_tokens=30,
            duration_s=12.5, cost_usd=0.0033),
    ])
    for header in ("status", "accuracy", "samples", "in_tok", "out_tok",
                   "duration_s", "cost_usd"):
        assert header in md
    assert "120" in md and "30" in md and "12.5" in md and "0.0033" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_matrix.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sca_eval.matrix'`

- [ ] **Step 3: Implement the aggregation core**

`src/sca_eval/matrix.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_matrix.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sca_eval/matrix.py tests/test_matrix.py
git commit -m "feat: capability matrix + details aggregation core"
```

---

### Task 3: Verdict parser (security-reasoning scorer logic)

The security-reasoning prompt requires a final `VERDICT: VULNERABLE|SAFE` line. Parsing is **strict**: only the explicit verdict line counts. No loose substring fallback — "not vulnerable" must never be scored as "vulnerable". Anything else is `unknown` (counted separately, never silently mapped to a label).

**Files:**
- Create: `src/sca_eval/verdict.py`
- Test: `tests/test_verdict.py`

- [ ] **Step 1: Write the failing test**

`tests/test_verdict.py`:
```python
from sca_eval.verdict import parse_verdict


def test_parses_explicit_verdict_line():
    assert parse_verdict("Reasoning...\nVERDICT: VULNERABLE") == "vulnerable"
    assert parse_verdict("VERDICT: SAFE") == "safe"


def test_verdict_line_is_case_insensitive():
    assert parse_verdict("verdict: vulnerable") == "vulnerable"


def test_negation_prose_is_not_misread():
    # The whole point: no substring fallback.
    assert parse_verdict("This code is not vulnerable at all.") == "unknown"
    assert parse_verdict("I think this is vulnerable to injection.") == "unknown"


def test_uses_last_verdict_line_when_several():
    assert parse_verdict("VERDICT: SAFE\n...rethinking...\nVERDICT: VULNERABLE") == "vulnerable"


def test_returns_unknown_when_no_verdict_line():
    assert parse_verdict("I am not sure about this code.") == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_verdict.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sca_eval.verdict'`

- [ ] **Step 3: Implement the strict parser**

`src/sca_eval/verdict.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_verdict.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sca_eval/verdict.py tests/test_verdict.py
git commit -m "feat: strict security-reasoning verdict parser"
```

---

### Task 4: Seed datasets + dataset loader

Three small, language-agnostic JSONL datasets (the npm corpus is NOT used). Each record: `id`, `input`, `target`, `metadata`. Tiny but real seeds, expandable later.

**Files:**
- Create: `src/sca_eval/data/code_comprehension.jsonl`
- Create: `src/sca_eval/data/security_reasoning.jsonl`
- Create: `src/sca_eval/data/obfuscation.jsonl`
- Create: `src/sca_eval/datasets.py`
- Test: `tests/test_datasets.py`

- [ ] **Step 1: Write the failing test**

`tests/test_datasets.py`:
```python
from sca_eval.datasets import load_dataset, DATASETS


def test_all_declared_datasets_load_and_are_nonempty():
    for name in DATASETS:
        samples = load_dataset(name)
        assert len(samples) >= 3, f"{name} should have >=3 seed samples"
        for s in samples:
            assert s.id, f"{name} sample missing id"
            assert isinstance(s.input, str) and s.input.strip()
            assert s.target, f"{name} sample {s.id} missing target"


def test_security_targets_are_valid_labels():
    for s in load_dataset("security_reasoning"):
        assert s.target in ("vulnerable", "safe")


def test_unknown_dataset_raises():
    import pytest

    with pytest.raises(KeyError):
        load_dataset("does_not_exist")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_datasets.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sca_eval.datasets'`

- [ ] **Step 3: Create the seed data files**

`src/sca_eval/data/code_comprehension.jsonl`:
```jsonl
{"id": "cc-001", "input": "What does this function return for input 5?\n\ndef f(n):\n    return n * (n + 1) // 2", "target": "15", "metadata": {"lang": "python"}}
{"id": "cc-002", "input": "What is the time complexity of this loop in Big-O?\n\nfor i in range(n):\n    for j in range(n):\n        total += i * j", "target": "O(n^2)", "metadata": {"lang": "python"}}
{"id": "cc-003", "input": "After this code runs, what is the value of x?\n\nlet x = [1,2,3].map(v => v * 2).filter(v => v > 2).length;", "target": "2", "metadata": {"lang": "javascript"}}
{"id": "cc-004", "input": "Does this function correctly reverse a string? Answer yes or no.\n\nfn rev(s: &str) -> String { s.chars().rev().collect() }", "target": "yes", "metadata": {"lang": "rust"}}
```

`src/sca_eval/data/security_reasoning.jsonl`:
```jsonl
{"id": "sr-001", "input": "Is this code vulnerable? Reply with reasoning then a final line 'VERDICT: VULNERABLE' or 'VERDICT: SAFE'.\n\nquery = \"SELECT * FROM users WHERE name = '\" + user_input + \"'\"", "target": "vulnerable", "metadata": {"cwe": "CWE-89"}}
{"id": "sr-002", "input": "Is this code vulnerable? Reply with reasoning then a final line 'VERDICT: VULNERABLE' or 'VERDICT: SAFE'.\n\ncursor.execute(\"SELECT * FROM users WHERE name = %s\", (user_input,))", "target": "safe", "metadata": {"cwe": "none"}}
{"id": "sr-003", "input": "Is this code vulnerable? Reply with reasoning then a final line 'VERDICT: VULNERABLE' or 'VERDICT: SAFE'.\n\nos.system(\"ping -c 1 \" + host)", "target": "vulnerable", "metadata": {"cwe": "CWE-78"}}
{"id": "sr-004", "input": "Is this code vulnerable? Reply with reasoning then a final line 'VERDICT: VULNERABLE' or 'VERDICT: SAFE'.\n\nsubprocess.run([\"ping\", \"-c\", \"1\", host], check=True)", "target": "safe", "metadata": {"cwe": "none"}}
```

`src/sca_eval/data/obfuscation.jsonl`:
```jsonl
{"id": "ob-001", "input": "This string is base64-encoded. Decode it and reply with ONLY the decoded text.\n\naGVsbG8gd29ybGQ=", "target": "hello world", "metadata": {"encoding": "base64"}}
{"id": "ob-002", "input": "Decode this hex-encoded ASCII string and reply with ONLY the decoded text.\n\n6361742f6574632f706173737764", "target": "cat/etc/passwd", "metadata": {"encoding": "hex"}}
{"id": "ob-003", "input": "This is ROT13. Reply with ONLY the decoded text.\n\nriny", "target": "eval", "metadata": {"encoding": "rot13"}}
{"id": "ob-004", "input": "What single JS function does this obfuscated call ultimately invoke? Reply with ONLY the function name.\n\nwindow[\"ev\"+\"al\"](payload)", "target": "eval", "metadata": {"encoding": "string-concat"}}
```

- [ ] **Step 4: Implement the loader**

`src/sca_eval/datasets.py`:
```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_datasets.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/sca_eval/data/ src/sca_eval/datasets.py tests/test_datasets.py
git commit -m "feat: seed capability datasets + loader"
```

---

### Task 5: inspect-ai tasks + custom security scorer

Wire the three datasets into inspect-ai `@task`s. Obfuscation uses built-in `match` (deterministic). Code comprehension uses `includes` (deterministic substring — keeps CI hermetic; upgrade to a pinned, calibrated `model_graded_qa` per spec §7 when real-model runs begin, see Out-of-Scope). Security reasoning uses a custom scorer built on the strict `parse_verdict`.

**Files:**
- Create: `src/sca_eval/scorers.py`
- Create: `src/sca_eval/tasks.py`
- Test: `tests/test_tasks.py`

- [ ] **Step 1: Write the failing test**

`tests/test_tasks.py`:
```python
from inspect_ai import Task

from sca_eval.tasks import TASKS, all_tasks


def test_task_registry_exposes_three_named_tasks():
    assert set(TASKS) == {"code_comprehension", "security_reasoning", "obfuscation"}


def test_each_factory_builds_a_task_with_a_nonempty_dataset():
    for name, factory in TASKS.items():
        task = factory()
        assert isinstance(task, Task)
        assert len(task.dataset) >= 3, f"{name} dataset too small"


def test_all_tasks_returns_one_task_per_registry_entry():
    tasks = all_tasks()
    assert len(tasks) == len(TASKS)
    assert all(isinstance(t, Task) for t in tasks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tasks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sca_eval.tasks'`

- [ ] **Step 3: Implement the custom scorer**

`src/sca_eval/scorers.py`:
```python
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
```

- [ ] **Step 4: Implement the tasks**

`src/sca_eval/tasks.py`:
```python
"""Capability tasks for the model survey (Phase 1).

Each task is language-agnostic and ecosystem-independent (no npm). Latency,
token, and cost axes are captured automatically from the eval log, not here.
"""

from __future__ import annotations

from collections.abc import Callable

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset
from inspect_ai.scorer import includes, match
from inspect_ai.solver import generate, system_message

from sca_eval.datasets import load_dataset
from sca_eval.scorers import verdict_match


@task
def code_comprehension() -> Task:
    return Task(
        dataset=MemoryDataset(load_dataset("code_comprehension")),
        solver=[
            system_message("Answer concisely. Reply with only the final answer."),
            generate(),
        ],
        scorer=includes(),  # deterministic; substring of target in completion
    )


@task
def security_reasoning() -> Task:
    return Task(
        dataset=MemoryDataset(load_dataset("security_reasoning")),
        solver=[generate()],
        scorer=verdict_match(),
    )


@task
def obfuscation() -> Task:
    return Task(
        dataset=MemoryDataset(load_dataset("obfuscation")),
        solver=[
            system_message("Reply with ONLY the requested decoded text or name."),
            generate(),
        ],
        scorer=match(location="any", ignore_case=True),
    )


TASKS: dict[str, Callable[[], Task]] = {
    "code_comprehension": code_comprehension,
    "security_reasoning": security_reasoning,
    "obfuscation": obfuscation,
}


def all_tasks() -> list[Task]:
    return [factory() for factory in TASKS.values()]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tasks.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/sca_eval/scorers.py src/sca_eval/tasks.py tests/test_tasks.py
git commit -m "feat: capability tasks + security verdict scorer"
```

---

### Task 6: EvalLog → ModelResult extraction (status-aware, mockllm-validated)

Extract per-(model, task) numbers from an `EvalLog`. This is the one module coupled to inspect-ai's log schema, so it is validated by a real end-to-end run against `mockllm/model` — no paid API. Crucially: a non-`success` log status produces a `ModelResult` with `accuracy=None` and the failing `status`, so an infra failure is **never** silently scored as `0.00`. Tokens are split input/output for the cost axis.

**Files:**
- Create: `src/sca_eval/extract.py`
- Test: `tests/test_extract_mockllm.py`

- [ ] **Step 1: Write the failing test**

`tests/test_extract_mockllm.py`:
```python
from inspect_ai import eval as inspect_eval

from sca_eval.extract import summarize_log
from sca_eval.matrix import ModelResult
from sca_eval.tasks import obfuscation


def test_summarize_log_extracts_a_sane_successful_modelresult():
    # Deterministic, hermetic: mockllm needs no API key and no network.
    logs = inspect_eval(obfuscation(), model="mockllm/model", display="none")
    assert len(logs) == 1

    result = summarize_log(logs[0])

    assert isinstance(result, ModelResult)
    assert result.status == "success"
    assert result.model == "mockllm/model"
    assert result.task == "obfuscation"
    assert result.samples >= 3
    assert result.accuracy is not None and 0.0 <= result.accuracy <= 1.0
    assert result.input_tokens >= 0 and result.output_tokens >= 0
    assert result.duration_s >= 0.0
    assert result.cost_usd == 0.0   # priced later in run.py
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_extract_mockllm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sca_eval.extract'`

- [ ] **Step 3: Implement the status-aware extractor**

`src/sca_eval/extract.py`:
```python
"""Turn an inspect-ai EvalLog into a flat ModelResult for the matrix.

Isolated here because it is the only module coupled to inspect-ai's log schema.
A non-'success' log is returned with accuracy=None and its status preserved, so
infrastructure failures are never confused with a genuine 0.00 score.
"""

from __future__ import annotations

from datetime import datetime

from inspect_ai.log import EvalLog

from sca_eval.matrix import ModelResult


def _primary_accuracy(log: EvalLog) -> float:
    results = getattr(log, "results", None)
    if not results or not results.scores:
        return 0.0
    metrics = results.scores[0].metrics
    metric = metrics.get("accuracy") or next(iter(metrics.values()), None)
    return float(metric.value) if metric is not None else 0.0


def _tokens(log: EvalLog) -> tuple[int, int]:
    usage = getattr(log.stats, "model_usage", None) or {}
    inp = sum(int(getattr(u, "input_tokens", 0) or 0) for u in usage.values())
    out = sum(int(getattr(u, "output_tokens", 0) or 0) for u in usage.values())
    return inp, out


def _duration_s(log: EvalLog) -> float:
    started, completed = log.stats.started_at, log.stats.completed_at
    if not started or not completed:
        return 0.0
    fmt = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    return max(0.0, (fmt(completed) - fmt(started)).total_seconds())


def _sample_count(log: EvalLog) -> int:
    return int(getattr(log.eval.dataset, "samples", 0) or 0)


def summarize_log(log: EvalLog) -> ModelResult:
    status = getattr(log, "status", "success")
    if status != "success":
        return ModelResult(
            model=log.eval.model, task=log.eval.task, accuracy=None,
            samples=_sample_count(log), input_tokens=0, output_tokens=0,
            duration_s=_duration_s(log), cost_usd=0.0, status=status,
        )
    inp, out = _tokens(log)
    return ModelResult(
        model=log.eval.model, task=log.eval.task,
        accuracy=_primary_accuracy(log), samples=_sample_count(log),
        input_tokens=inp, output_tokens=out, duration_s=_duration_s(log),
        cost_usd=0.0, status="success",
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_extract_mockllm.py -v`
Expected: PASS. If it fails on an attribute (`log.eval.dataset.samples`, `log.stats.started_at`, `u.input_tokens`, etc.), the installed inspect-ai schema differs — inspect the real object with `uv run python -c "from inspect_ai import eval; from sca_eval.tasks import obfuscation; l=eval(obfuscation(), model='mockllm/model', display='none')[0]; print(l.status); print(l.eval); print(l.stats)"` and adjust the field path. Do not guess; read the printed object.

- [ ] **Step 5: Commit**

```bash
git add src/sca_eval/extract.py tests/test_extract_mockllm.py
git commit -m "feat: status-aware EvalLog -> ModelResult extraction"
```

---

### Task 7: Cost pricing (input/output split) + run.py (eval_set fan-out, failure-honest, CLI)

Add a token→USD rate card that prices **input and output separately** (provider rates differ by large factors), and the runner that fans tasks × models through `eval_set()`, honors the `success` boolean, prices every successful row, and emits a failure report instead of silently zeroing failed runs.

**Files:**
- Create: `src/sca_eval/pricing.py`
- Create: `src/sca_eval/run.py`
- Test: `tests/test_pricing.py`
- Test: `tests/test_run_mockllm.py`

- [ ] **Step 1: Write the failing pricing test**

`tests/test_pricing.py`:
```python
from sca_eval.pricing import price_usd


def test_input_and_output_priced_separately():
    # Opus 4.8 rate card: $15 / 1M input, $75 / 1M output.
    # 1M input + 1M output = 15 + 75 = 90.
    assert price_usd("anthropic/claude-opus-4-8", 1_000_000, 1_000_000) == 90.0


def test_output_heavier_than_input():
    in_only = price_usd("anthropic/claude-opus-4-8", 1_000_000, 0)
    out_only = price_usd("anthropic/claude-opus-4-8", 0, 1_000_000)
    assert out_only > in_only


def test_self_hosted_open_model_prices_to_zero():
    # GLM/DeepSeek/Qwen run on our own GPUs -> no per-token API cost.
    assert price_usd("openai/qwen-3.6", 1_000_000, 1_000_000) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pricing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sca_eval.pricing'`

- [ ] **Step 3: Implement pricing (input/output split)**

`src/sca_eval/pricing.py`:
```python
"""Token -> USD pricing with separate input/output rates.

Rates are ($/1M input, $/1M output). They CHANGE — confirm against each
provider's pricing page on the run date before billing-grade reporting.
Models absent here (self-hosted open-weight: GLM, DeepSeek, Qwen) price to 0,
because their cost is GPU time, not per-token API billing.
"""

from __future__ import annotations

# (input_per_million_usd, output_per_million_usd)
_RATES: dict[str, tuple[float, float]] = {
    "anthropic/claude-opus-4-8": (15.0, 75.0),   # Anthropic Opus tier
    "openai/gpt-5.5": (10.0, 30.0),              # estimate — verify on OpenAI pricing page
}


def price_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    rate = _RATES.get(model)
    if rate is None:
        return 0.0
    in_rate, out_rate = rate
    cost = in_rate * input_tokens / 1_000_000 + out_rate * output_tokens / 1_000_000
    return round(cost, 6)
```

- [ ] **Step 4: Run the pricing test**

Run: `uv run pytest tests/test_pricing.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Write the failing runner test**

`tests/test_run_mockllm.py`:
```python
from sca_eval.run import run_survey


def test_run_survey_writes_matrix_and_details_for_mockllm(tmp_path):
    out = tmp_path / "matrix.md"
    matrix = run_survey(
        models=["mockllm/model"],
        task_names=["obfuscation", "security_reasoning"],
        log_dir=str(tmp_path / "logs"),
        out_path=str(out),
    )

    assert "mockllm/model" in matrix
    assert set(matrix["mockllm/model"]) == {"obfuscation", "security_reasoning"}

    assert out.exists()
    assert "| model |" in out.read_text()

    details = tmp_path / "details.md"
    assert details.exists()
    assert "cost_usd" in details.read_text()

    # mockllm succeeds -> no failure report written
    assert not (tmp_path / "FAILURES.md").exists()
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_run_mockllm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sca_eval.run'`

- [ ] **Step 7: Implement the runner + CLI**

`src/sca_eval/run.py`:
```python
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
```

- [ ] **Step 8: Run the runner test to verify it passes**

Run: `uv run pytest tests/test_run_mockllm.py -v`
Expected: PASS. (The `tmp_path` fixture guarantees a fresh, empty log dir for `eval_set`.)

- [ ] **Step 9: Commit**

```bash
git add src/sca_eval/pricing.py src/sca_eval/run.py tests/test_pricing.py tests/test_run_mockllm.py
git commit -m "feat: survey runner (failure-honest), input/output cost pricing, CLI"
```

---

### Task 8: README + full hermetic end-to-end

Document running with mockllm (CI) and real providers (new model set), and add one full-suite end-to-end test over all three tasks with mockllm.

**Files:**
- Create: `README.md`
- Test: `tests/test_e2e_mockllm.py`

- [ ] **Step 1: Write the failing end-to-end test**

`tests/test_e2e_mockllm.py`:
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

- [ ] **Step 2: Run test to verify it fails (or passes if plumbing is complete)**

Run: `uv run pytest tests/test_e2e_mockllm.py -v`
Expected: PASS if Tasks 1–7 are correct. If FAIL, fix the failing module before continuing — this is the integration gate.

- [ ] **Step 3: Write the README**

Create `README.md` with the content below. (Shown in a four-backtick block so its inner triple-backtick code fences render literally — copy the inner content verbatim into `README.md`.)

````markdown
# sca-eval — Capability Eval Spine (Phase 0–1)

Model-independent capability matrix for the AI-Augmented SCA Analysis capstone.
Runs language-agnostic tasks (code comprehension, security reasoning, obfuscation)
across any inspect-ai-supported model and emits a comparable Markdown matrix plus
a details table (accuracy, latency, token split, cost).

Design: `docs/superpowers/specs/2026-05-30-ai-augmented-sca-analysis-design.md`.
The npm corpus is quarantined (spec §6b) and is NOT used by this package.

## Setup

```bash
uv sync --extra dev   # installs the locked inspect-ai build from uv.lock
```

## Test (hermetic, no API keys)

```bash
uv run pytest -v      # uses mockllm/model; no network, no cost
```

## Run the survey (real models)

Closed SOTA — set provider keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`):

```bash
uv run python -m sca_eval.run \
  --models anthropic/claude-opus-4-8 openai/gpt-5.5 \
  --out out/matrix.md
```

Open SOTA (GLM-5.1, DeepSeek V4 Pro, Qwen 3.6) self-hosted via an
OpenAI-compatible endpoint (vLLM/Ollama) — set `OPENAI_BASE_URL` and pass the
served model names:

```bash
uv run python -m sca_eval.run \
  --models openai/glm-5.1 openai/deepseek-v4-pro openai/qwen-3.6 \
  --out out/matrix-open.md
```

Outputs: `out/matrix.md` (accuracy matrix), `out/details.md` (all axes:
samples, duration, input/output tokens, cost), `out/FAILURES.md` (only if a run
failed), and per-run logs in `logs/survey/`
(view with `uv run inspect view --log-dir logs/survey`).

## What this measures

Accuracy per task per model, plus latency, input/output tokens, and cost per run.
Failed/cancelled runs render `ERR`, never a fake `0.00`. Cost rates (per provider,
input/output split) live in `src/sca_eval/pricing.py` — verify them against
provider pricing pages on the run date. Self-hosted open models price to `0`.
````

- [ ] **Step 4: Run the full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS (test_smoke, test_matrix, test_verdict, test_datasets, test_tasks, test_extract_mockllm, test_pricing, test_run_mockllm, test_e2e_mockllm).

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_e2e_mockllm.py
git commit -m "docs: README + full-suite mockllm end-to-end test"
```

---

## Out of scope (future plans)

- **tool-use capability axis** — needs tool/sandbox infra; folded into the Phase 2 plan.
- **Phase 2** agentic-tool survey (Claude Code / Codex adapters + apples-to-apples controls).
- **Phase 3** SCA detection harness (static Semgrep + dynamic sandbox).
- **Phase 4** npm validation on the (still-quarantined) dev/test corpus.
- Upgrading `code_comprehension` from `includes()` to `model_graded_qa()` with a pinned,
  calibrated grader (spec §7) once real-model runs begin.
- Per-provider cost refinements: cached-input tokens and other provider-specific extras
  (current rate card splits input/output only).
