import os

from inspect_ai import Task

from sca_eval.tasks import C2_TASKS, COMPOSE_FILE, TASKS, all_tasks


def test_task_registry_exposes_easy_and_hard_variants():
    assert set(TASKS) == {
        "code_comprehension", "security_reasoning", "obfuscation",
        "code_comprehension_hard", "security_reasoning_hard", "obfuscation_hard",
        "tool_use_c2", "tool_use_c2_hard",
    }


def test_each_factory_builds_a_task_with_a_nonempty_dataset():
    for name, factory in TASKS.items():
        task = factory()
        assert isinstance(task, Task)
        assert len(task.dataset) >= 3, f"{name} dataset too small"


def test_all_tasks_returns_one_task_per_registry_entry():
    tasks = all_tasks()
    assert len(tasks) == len(TASKS)
    assert all(isinstance(t, Task) for t in tasks)


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
