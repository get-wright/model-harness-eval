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

## Tool-use C2-extraction benchmark (Docker required)

`tool_use_c2` / `tool_use_c2_hard` measure the **tool-use** capability axis: the model
is dropped in a network-isolated Docker sandbox holding an obfuscated payload and must
recover the command-and-control (C2) indicator using the `bash` and `python` tools.

```bash
uv run python -m sca_eval.run \
  --models anthropic/claude-opus-4-8 \
  --tasks tool_use_c2 tool_use_c2_hard \
  --out out/c2-matrix.md
```

Outputs add `out/tooluse.md`: per (model, task) tool-call count, failed calls, model
turns, tool-loop input/output tokens, and derived tokens-per-call / -per-correct.
Missing per-event usage renders `—` (never a fake 0); failed runs render `ERR`.

**Corpus** is synthetic, modeled on documented incident techniques (layered base64, hex,
char-code arrays, XOR, split-concat, gzip+base64, runtime-computed). Regenerate with
`uv run python scripts/gen_c2_corpus.py`.

**Safety:** the sandbox runs `network_mode: none` (see `src/sca_eval/sandbox/compose.yaml`)
via the tuple sandbox form `("docker", compose.yaml)`; all C2 values are non-routable
fakes (RFC 5737 TEST-NET, `.invalid`/`.example`). Nothing is ever contacted. The
docker-gated test `tests/test_c2_sandbox.py` proves no egress.

## What this measures

Accuracy per task per model, plus latency, input/output tokens, and cost per run.
Failed/cancelled runs render `ERR`, never a fake `0.00`. Cost rates (per provider,
input/output split) live in `src/sca_eval/pricing.py` — verify them against
provider pricing pages on the run date. Self-hosted open models price to `0`.
