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
