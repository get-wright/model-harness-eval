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


def test_run_survey_writes_failures_md_when_a_log_fails(tmp_path):
    from unittest.mock import MagicMock, patch

    fake_log = MagicMock()
    fake_log.status = "error"
    fake_log.eval.model = "openai/gpt-5.5"
    fake_log.eval.task = "obfuscation"
    fake_log.eval.dataset.samples = 0
    fake_log.stats.started_at = None
    fake_log.stats.completed_at = None

    with patch("sca_eval.run.eval_set", return_value=(False, [fake_log])):
        run_survey(
            models=["openai/gpt-5.5"],
            task_names=["obfuscation"],
            log_dir=str(tmp_path / "logs"),
            out_path=str(tmp_path / "matrix.md"),
        )

    failures = (tmp_path / "FAILURES.md").read_text()
    assert "openai/gpt-5.5" in failures and "status=error" in failures
    assert "ERR" in (tmp_path / "matrix.md").read_text()


def test_run_survey_synthesizes_err_for_unstarted_pair(tmp_path):
    from unittest.mock import patch

    # eval_set returns NO logs for the requested pair.
    with patch("sca_eval.run.eval_set", return_value=(False, [])):
        matrix = run_survey(
            models=["openai/gpt-5.5"],
            task_names=["obfuscation"],
            log_dir=str(tmp_path / "logs"),
            out_path=str(tmp_path / "matrix.md"),
        )

    assert matrix["openai/gpt-5.5"]["obfuscation"] is None   # ERR, not "-"
    assert "ERR" in (tmp_path / "matrix.md").read_text()
    assert "obfuscation" in (tmp_path / "FAILURES.md").read_text()


def test_success_log_without_scores_is_reported_as_failure(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import patch

    # A 'success' log that produced no scores -> accuracy None -> must be ERR
    # in the matrix AND listed in FAILURES.md (not a silent unexplained ERR).
    log = SimpleNamespace(
        status="success",
        results=None,
        eval=SimpleNamespace(
            model="mockllm/model",
            task="sca_eval/obfuscation",
            dataset=SimpleNamespace(samples=4),
        ),
        stats=SimpleNamespace(
            started_at=None, completed_at=None, model_usage={},
        ),
    )

    with patch("sca_eval.run.eval_set", return_value=(True, [log])):
        matrix = run_survey(
            models=["mockllm/model"],
            task_names=["obfuscation"],
            log_dir=str(tmp_path / "logs"),
            out_path=str(tmp_path / "matrix.md"),
        )

    assert matrix["mockllm/model"]["obfuscation"] is None
    assert "ERR" in (tmp_path / "matrix.md").read_text()
    assert "obfuscation" in (tmp_path / "FAILURES.md").read_text()


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
