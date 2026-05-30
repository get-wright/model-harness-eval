from types import SimpleNamespace

from sca_eval.extract import tool_use_stats


def _model_ev(in_tok=10, out_tok=5, usage=True):
    usage_obj = SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok) if usage else None
    return SimpleNamespace(event="model", output=SimpleNamespace(usage=usage_obj))


def _tool_ev(failed=None, error=None):
    return SimpleNamespace(event="tool", failed=failed, error=error)


def _sample(events, correct):
    score = SimpleNamespace(value="C" if correct else "I")
    return SimpleNamespace(events=events, scores={"s": score})


def _log(samples, status="success"):
    return SimpleNamespace(
        status=status,
        eval=SimpleNamespace(model="m/x", task="sca_eval/tool_use_c2",
                             dataset=SimpleNamespace(samples=len(samples))),
        samples=samples,
    )


def test_counts_tools_turns_failures_and_tokens():
    events = [
        _model_ev(in_tok=100, out_tok=20),
        _tool_ev(failed=True),            # failure via failed flag
        _model_ev(in_tok=50, out_tok=10),
        _tool_ev(error=SimpleNamespace(message="boom")),  # failure via error only
        _tool_ev(),                        # success
        _model_ev(in_tok=30, out_tok=5),
    ]
    st = tool_use_stats(_log([_sample(events, correct=True)]))
    assert st.tool_calls == 3
    assert st.failed_tool_calls == 2          # failed-flag + error-only both counted
    assert st.model_turns == 3
    assert st.tool_loop_input_tokens == 180
    assert st.tool_loop_output_tokens == 35
    assert st.events_missing_usage == 0
    assert st.correct == 1
    assert st.task == "tool_use_c2"


def test_missing_usage_makes_tokens_none_and_counts_it():
    events = [_model_ev(usage=False), _tool_ev(), _model_ev(in_tok=10, out_tok=2)]
    st = tool_use_stats(_log([_sample(events, correct=False)]))
    assert st.tool_loop_input_tokens is None
    assert st.tool_loop_output_tokens is None
    assert st.events_missing_usage == 1
    assert st.correct == 0


def test_failed_run_returns_zeroed_stats_with_status():
    st = tool_use_stats(_log([], status="error"))
    assert st.status == "error"
    assert st.tool_calls == 0
    assert st.tool_loop_input_tokens is None
