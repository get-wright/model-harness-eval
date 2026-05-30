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


@task
def code_comprehension_hard() -> Task:
    return Task(
        dataset=MemoryDataset(load_dataset("code_comprehension_hard")),
        solver=[
            system_message("Answer concisely. Reply with only the final answer."),
            generate(),
        ],
        scorer=includes(),
    )


@task
def security_reasoning_hard() -> Task:
    return Task(
        dataset=MemoryDataset(load_dataset("security_reasoning_hard")),
        solver=[generate()],
        scorer=verdict_match(),
    )


@task
def obfuscation_hard() -> Task:
    return Task(
        dataset=MemoryDataset(load_dataset("obfuscation_hard")),
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
    "code_comprehension_hard": code_comprehension_hard,
    "security_reasoning_hard": security_reasoning_hard,
    "obfuscation_hard": obfuscation_hard,
}


def all_tasks() -> list[Task]:
    return [factory() for factory in TASKS.values()]
