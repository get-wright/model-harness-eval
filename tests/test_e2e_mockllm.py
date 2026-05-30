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
