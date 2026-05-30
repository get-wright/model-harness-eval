# sca-eval — Capability Eval Spine (Phase 0–1)

Model-independent capability matrix for the AI-Augmented SCA Analysis capstone.
Runs language-agnostic tasks (code comprehension, security reasoning, obfuscation)
across any inspect-ai-supported model and emits a comparable Markdown matrix plus
a details table (accuracy, latency, token split, cost).

Design: `docs/superpowers/specs/2026-05-30-ai-augmented-sca-analysis-design.md`.
The npm corpus is quarantined (spec §6b) and is NOT used by this package.

## Setup

```bash
uv sync --extra dev   # installs the locked inspect-ai build from uv.lock
```

## Test (hermetic, no API keys)

```bash
uv run pytest -v      # uses mockllm/model; no network, no cost
```

## Run the survey (real models)

Closed SOTA — set provider keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`):

```bash
uv run python -m sca_eval.run \
  --models anthropic/claude-opus-4-8 openai/gpt-5.5 \
  --out out/matrix.md
```

Open SOTA (GLM-5.1, DeepSeek V4 Pro, Qwen 3.6) self-hosted via an
OpenAI-compatible endpoint (vLLM/Ollama) — set `OPENAI_BASE_URL` and pass the
served model names:

```bash
uv run python -m sca_eval.run \
  --models openai/glm-5.1 openai/deepseek-v4-pro openai/qwen-3.6 \
  --out out/matrix-open.md
```

Outputs: `out/matrix.md` (accuracy matrix), `out/details.md` (all axes:
samples, duration, input/output tokens, cost), `out/FAILURES.md` (only if a run
failed), and per-run logs in `logs/survey/`
(view with `uv run inspect view --log-dir logs/survey`).

## What this measures

Accuracy per task per model, plus latency, input/output tokens, and cost per run.
Failed/cancelled runs render `ERR`, never a fake `0.00`. Cost rates (per provider,
input/output split) live in `src/sca_eval/pricing.py` — verify them against
provider pricing pages on the run date. Self-hosted open models price to `0`.
