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


def test_summarize_log_failure_yields_none_accuracy_not_zero():
    from types import SimpleNamespace

    log = SimpleNamespace(
        status="error",
        eval=SimpleNamespace(
            model="openai/gpt-5.5",
            task="sca_eval/obfuscation",
            dataset=SimpleNamespace(samples=10),
        ),
        stats=SimpleNamespace(started_at=None, completed_at=None),
    )
    result = summarize_log(log)
    assert result.status == "error"
    assert result.accuracy is None      # never a fake 0.0
    assert result.task == "obfuscation"
    assert result.input_tokens == 0 and result.output_tokens == 0
