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
