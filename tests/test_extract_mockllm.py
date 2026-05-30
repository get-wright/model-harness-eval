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
