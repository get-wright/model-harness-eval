from sca_eval.matrix import (
    ModelResult,
    build_matrix,
    format_markdown,
    format_details_markdown,
)


def _ok(model, task, accuracy, **kw):
    base = dict(samples=5, input_tokens=100, output_tokens=50,
                duration_s=10.0, cost_usd=0.0, status="success")
    base.update(kw)
    return ModelResult(model=model, task=task, accuracy=accuracy, **base)


def test_total_tokens_is_input_plus_output():
    r = _ok("m", "t", 0.5, input_tokens=100, output_tokens=50)
    assert r.total_tokens == 150


def test_build_matrix_groups_by_model_and_task():
    results = [
        _ok("anthropic/x", "obfuscation", 0.80),
        _ok("anthropic/x", "security", 0.60),
        _ok("openai/y", "obfuscation", 0.40),
    ]
    matrix = build_matrix(results)

    assert matrix["anthropic/x"]["obfuscation"] == 0.80
    assert matrix["anthropic/x"]["security"] == 0.60
    assert matrix["openai/y"]["obfuscation"] == 0.40
    assert "security" not in matrix["openai/y"]


def test_failed_run_keeps_none_accuracy_and_renders_as_err():
    results = [
        _ok("m1", "obfuscation", 0.5),
        ModelResult(model="m1", task="security", accuracy=None, samples=0,
                    input_tokens=0, output_tokens=0, duration_s=0.0,
                    cost_usd=0.0, status="error"),
    ]
    matrix = build_matrix(results)
    assert matrix["m1"]["security"] is None

    md = format_markdown(matrix)
    assert "ERR" in md          # failure is visible, never 0.00
    assert "0.50" in md


def test_format_markdown_has_one_row_per_model_and_task_columns():
    md = format_markdown(build_matrix([
        _ok("m1", "obfuscation", 0.5),
        _ok("m1", "security", 1.0),
    ]))
    assert "| model |" in md
    assert "obfuscation" in md and "security" in md
    assert "| m1 |" in md
    assert "0.50" in md and "1.00" in md


def test_details_table_reports_all_axes():
    md = format_details_markdown([
        _ok("m1", "obfuscation", 0.5, input_tokens=120, output_tokens=30,
            duration_s=12.5, cost_usd=0.0033),
    ])
    for header in ("status", "accuracy", "samples", "in_tok", "out_tok",
                   "duration_s", "cost_usd"):
        assert header in md
    assert "120" in md and "30" in md and "12.5" in md and "0.0033" in md


def test_empty_matrix_renders_empty_string():
    assert format_markdown({}) == ""


def test_build_matrix_last_write_wins_on_duplicate_pair():
    results = [
        _ok("m1", "obfuscation", 0.30),
        _ok("m1", "obfuscation", 0.90),  # same (model, task) -> overwrites
    ]
    matrix = build_matrix(results)
    assert matrix["m1"]["obfuscation"] == 0.90
