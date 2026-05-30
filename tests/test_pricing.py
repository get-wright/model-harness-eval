from sca_eval.pricing import price_usd


def test_input_and_output_priced_separately():
    # Opus 4.8 rate card: $15 / 1M input, $75 / 1M output.
    # 1M input + 1M output = 15 + 75 = 90.
    assert price_usd("anthropic/claude-opus-4-8", 1_000_000, 1_000_000) == 90.0


def test_output_heavier_than_input():
    in_only = price_usd("anthropic/claude-opus-4-8", 1_000_000, 0)
    out_only = price_usd("anthropic/claude-opus-4-8", 0, 1_000_000)
    assert out_only > in_only


def test_self_hosted_open_model_prices_to_zero():
    # GLM/DeepSeek/Qwen run on our own GPUs -> no per-token API cost.
    assert price_usd("openai/qwen-3.6", 1_000_000, 1_000_000) == 0.0
