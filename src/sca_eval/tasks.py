"""Capability tasks for the model survey (Phase 1).

Each task is language-agnostic and ecosystem-independent (no npm). Latency,
token, and cost axes are captured automatically from the eval log, not here.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset
from inspect_ai.scorer import includes, match
from inspect_ai.solver import generate, system_message, use_tools
from inspect_ai.tool import bash, python

from sca_eval.datasets import load_c2_dataset, load_dataset
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


def all_tasks() -> list[Task]:
    return [factory() for factory in TASKS.values()]
