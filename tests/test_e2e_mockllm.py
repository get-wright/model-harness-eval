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
