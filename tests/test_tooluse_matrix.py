from sca_eval.matrix import ToolUseStats, format_tooluse_markdown


def _stat(**kw):
    base = dict(
        model="m/x", task="tool_use_c2", status="success", samples=2, correct=1,
        tool_calls=4, failed_tool_calls=1, model_turns=3,
        tool_loop_input_tokens=900, tool_loop_output_tokens=100,
        events_missing_usage=0,
    )
    base.update(kw)
    return ToolUseStats(**base)


def test_table_has_header_and_derived_columns():
    out = format_tooluse_markdown([_stat()])
    assert "tool_calls" in out and "tok/call" in out and "tok/correct" in out
    # (900+100)/4 tool calls = 250.0 ; calls/correct 4/1 ; tok/correct 1000/1
    assert "250.0" in out and "1000.0" in out


def test_zero_correct_renders_dash_not_zero():
    out = format_tooluse_markdown([_stat(correct=0)])
    # tok/correct and calls/correct undefined -> em dash, never 0.0
    assert "—" in out


def test_missing_usage_renders_dash_for_token_columns():
    out = format_tooluse_markdown(
        [_stat(tool_loop_input_tokens=None, tool_loop_output_tokens=None,
               events_missing_usage=2)]
    )
    assert "—" in out
    assert "1000" not in out  # no fabricated token total


def test_failed_run_renders_err():
    out = format_tooluse_markdown([_stat(status="error")])
    assert "ERR" in out
