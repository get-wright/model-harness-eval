# Tool-Use C2-Extraction Benchmark — Design

**Date:** 2026-05-30
**Type:** Capstone — Phase-1 capability axis implementation
**Parent spec:** `docs/superpowers/specs/2026-05-30-ai-augmented-sca-analysis-design.md`
**Status:** approved (brainstorming) — pending implementation plan

---

## 1. Goal

Implement the declared-but-unbuilt Phase-1 **tool-use** capability axis (parent spec §6,
row "Tool use") as a realistic malware-analysis task. A model is dropped into a
network-isolated Docker sandbox holding an obfuscated payload and must extract the
command-and-control (C2) indicator (domain / IP / URL) by **using tools** (`bash`,
`python`) to deobfuscate. The benchmark captures both:

- **Correctness** — did the model find the correct C2 indicator (primary accuracy).
- **Tool utilization** — how the model used tools: call count, failed calls, model
  turns, and tokens spent in the tool loop ("count tokens in tool use").

This reflects a real supply-chain-attack triage use case (find where compromised code
phones home) while staying inside the parent spec's independence safeguards.

## 2. Scope & Non-Goals

**In scope:** new Phase-1 capability task (easy + hard), synthetic obfuscated payload
corpus, Docker sandbox config, tool-use metric extraction, a tool-use results table,
hermetic tests + a docker-gated smoke test.

**Non-goals:**
- **No npm / no real ecosystem samples.** Parent spec §7.3: Phase-1 capability tasks are
  synthetic and ecosystem-independent so model ranking cannot be contaminated. Payloads
  are synthetic, *modeled on* documented incident techniques — not copied real malware.
- **No live C2.** C2 ground-truth values are non-routable fakes; the sandbox has no
  network. Nothing is ever contacted.
- **Not the agentic-tool survey (RQ2).** This task is the *bare-model* tool-use axis.
  RQ2 reuses the same task later through agentic harnesses; that is out of scope here.
- **Not dynamic install/runtime analysis (RQ3/§8).** This is static-extraction-in-sandbox:
  the C2 is always *statically recoverable* by decoding. No install lifecycle hooks, no
  runtime triggers, no sinkhole — none are needed because nothing executes against a
  network. A subset of hard samples *may* be solved faster by running the payload (see §6),
  but those payloads are authored in Python so the shipped `python3` runtime executes them;
  no foreign (JS/Node) runtime is ever required, and ground truth never depends on execution.

## 3. Architecture & Fit

```
run.py --tasks tool_use_c2 [tool_use_c2_hard]
   │
   ▼ eval_set(tasks, model=[...], sandbox=("docker", compose.yaml))
   │
   ├─ Sample: workspace seeded with payloads/<id>.<ext> via Sample.files
   │  solver: use_tools([bash, python]) + generate()  (multi-turn tool loop)
   │  limits: message_limit / token_limit / time_limit  (bound cost, force efficiency)
   │  scorer: match(location="any", ignore_case=True) vs C2 string
   │
   ▼ EvalLog (per sample: events = ModelEvent + ToolEvent + ...)
   │
   ├─ extract.summarize_log()      -> ModelResult   (existing: accuracy, tokens, cost)
   └─ extract.tool_use_stats()     -> ToolUseStats  (NEW: tool calls, fails, turns)
   │
   ▼ matrix.py
   ├─ format_markdown()         accuracy matrix (+ tool_use_c2 column)
   └─ format_tooluse_markdown() NEW tool-use table
```

The benchmark is one more task in the existing eval spine; it does not introduce a new
runner or scoring path. It adds (a) a file-seeding dataset loader, (b) a sandbox config,
(c) a second extraction producing tool-use stats, and (d) one new output table.

## 4. Components (purpose · interface · deps)

- **C2 dataset loader** — *purpose:* load C2 samples and seed each payload file into the
  sandbox. *interface:* `load_c2_dataset(name) -> list[Sample]` where each `Sample` has
  `files={sandbox_path: local_payload_path}`. Kept separate from the existing
  `load_dataset()` (which builds bare samples) so each function does one thing.
  *deps:* inspect-ai `Sample`, the `data/payloads/` files.
- **C2 tasks** — *purpose:* the tool-use eval. *interface:* `tool_use_c2()`,
  `tool_use_c2_hard()` `@task`s — `use_tools([bash, python]) + generate()`, per-sample
  limits, `match` scorer, and **`sandbox=("docker", <abs path to compose.yaml>)`** (tuple
  form — bare `"docker"` ignores the compose file and the no-egress guarantee is *not*
  applied; verified against inspect-ai 0.3.229). *deps:* loader, sandbox config.
- **Sandbox config** — *purpose:* isolated, no-egress execution. *interface:*
  `src/sca_eval/sandbox/compose.yaml` — a compose service on `python:3.11-slim` (provides
  `python3` + `bash` + coreutils, the entire toolset; every sample is solvable with it),
  `network_mode: none`, no host volume mounts, ephemeral. Referenced by the tasks via the
  tuple sandbox form above. *deps:* Docker at runtime.
- **Tool-use extraction** — *purpose:* derive utilization metrics from the log.
  *interface:* `tool_use_stats(log) -> ToolUseStats` reading `log.samples[].events`
  (count `ToolEvent`, `ToolEvent` where `failed` is true, assistant `ModelEvent` turns,
  and per-`ModelEvent` `output.usage` for tool-loop tokens — see §5).
  **Import `ToolEvent` / `ModelEvent` from `inspect_ai.event`, not `inspect_ai.log`**
  (the latter is deprecated since 0.3.137 and removed in 0.4). *deps:* inspect-ai log
  schema (isolated in `extract.py`, like `summarize_log`).
- **Tool-use table** — *purpose:* render utilization. *interface:*
  `format_tooluse_markdown(stats) -> str` in `matrix.py`. *deps:* none (pure).

## 5. Metrics

Primary (into the accuracy matrix, parent §6):
- **C2 accuracy** — fraction of samples where the extracted C2 matches target.

Tool-use table (new `out/tooluse.md`), per (model, task):
- `tool_calls` — total `ToolEvent`s.
- `failed_tool_calls` — `ToolEvent`s where `failed` is true (the `failed` bool field;
  `error` carries the detail).
- `model_turns` — assistant generations (`ModelEvent` count = tool-loop length).
- `tool_loop_tokens` — **the "count tokens in tool use" metric, defined precisely:**
  the sum of per-`ModelEvent` `output.usage.input_tokens` and `output.usage.output_tokens`
  across every `ModelEvent` in the sample. inspect-ai exposes no automatic "tool-loop
  tokens" field, so this is event-derived. Because tools are enabled from the first
  generation, this sum is the total token cost of the entire multi-turn tool loop; we
  report it as `tool_loop_input_tokens` + `tool_loop_output_tokens`. It is derived
  per-event (not from `log.stats.model_usage`) so it can be divided by `tool_calls` and
  `model_turns` for per-call / per-turn cost.
- `duration_s`, `cost_usd` — existing.
- Derived: `tokens_per_correct`, `tool_calls_per_correct`, `tokens_per_tool_call`
  (undefined / "—" when the denominator is zero, never a fake 0 — consistent with
  existing ERR handling).

Failure taxonomy is preserved: a run that errors or hits a limit renders `ERR`, never a
genuine `0.00` (matches existing `extract.py`/`matrix.py` discipline).

## 6. Sample Corpus (synthetic, modeled on real incidents)

Each sample: an obfuscated payload file whose hidden C2 indicator must be recovered.
Technique families (mirroring documented incidents, not copied from them):

| Technique | Modeled on | Hidden how |
|-----------|-----------|------------|
| Layered base64 | event-stream / flatmap-stream | C2 base64-encoded 1–3× |
| Hex / `\x` escapes | common JS/Python droppers | C2 as hex byte string |
| Char-code array | JS `String.fromCharCode([...])` | C2 as int array |
| XOR + embedded key | generic packers | C2 XORed, key in file |
| Split-and-concat | obfuscated assembly | domain split across parts |
| gzip + base64 blob | compressed stagers | C2 in compressed blob |

- **C2 ground truth uses non-routable fakes only:** RFC 5737 TEST-NET (`192.0.2.x`,
  `198.51.100.x`, `203.0.113.x`), and `.invalid` / `.example` TLDs.
- **Easy set (~10):** single-technique, single C2, decode-only.
- **Hard set (~8):** multi-layer; **decoy** C2 strings present; env/path-keyed assembly;
  and a *runtime-computed* lever where the C2 is assembled by code at execution time.
  Those runtime-computed payloads are written in **Python** so the shipped `python3`
  executes them directly — the model can run or statically trace them; either path
  recovers the same ground truth. No sample requires a JS/Node runtime: JS-*style*
  techniques (e.g. `String.fromCharCode([...])` arrays) are inert data the model decodes
  arithmetically with `python`, not code it must run.

Payloads live as real files in `src/sca_eval/data/payloads/` so reviewers can audit
every sample. The jsonl record references the payload filename, instruction, target C2,
and `metadata` (`technique`, `lang`, `payload_file`).

## 7. Safety (parent spec §8)

- `network_mode: none` in the compose file, applied via the **tuple sandbox form**
  `("docker", compose.yaml)` — the sandbox cannot reach any network; C2 values are
  non-routable fakes regardless. The docker-gated smoke test (§8) asserts the compose
  file is actually in effect, so this guarantee is proven, not assumed.
- No host filesystem mounts; container is ephemeral (torn down per sample/run).
- Payloads are inert synthetic snippets that, at most, print a fake string; nothing is
  installed and nothing executes against a network.
- Containment documented in README so re-runners are safe by default.

## 8. Testing (TDD)

Hermetic (no Docker, no API keys — runnable in CI / `uv run pytest`):
- **Loader test:** every C2 sample has a target, a referenced payload file that exists,
  and a well-formed `files` mapping; bad records raise with file+line context.
- **Tool-use extraction test:** build a synthetic `EvalLog` with known `ToolEvent` /
  `ModelEvent` sequences (incl. an errored tool call) → assert exact `tool_calls`,
  `failed_tool_calls`, `model_turns`.
- **Table rendering test:** `format_tooluse_markdown` shape, ERR/"—" handling, zero-correct
  derived metrics.

Docker-gated (skipped via `pytest.mark.skipif` when Docker is unavailable):
- **Compose-active / no-egress assertion:** prove the tuple sandbox form actually applied
  the compose file — execute a network attempt inside the sandbox (e.g.
  `python3 -c "socket.create_connection(('192.0.2.1',80),timeout=3)"`) and assert it
  fails with an unreachable/blocked error. A bare `sandbox="docker"` (no compose) would
  let egress through and fail this test — that is the point of the assertion.
- **Smoke test:** one sample end-to-end with a tiny model, asserting tool-use events are
  recorded and `tool_use_stats` returns non-zero `tool_calls`.

Real run (documented, not in CI): cross-model survey requires Docker + provider keys,
same as existing real-model runs.

## 9. Files

New:
- `src/sca_eval/data/tool_use_c2.jsonl`, `tool_use_c2_hard.jsonl`
- `src/sca_eval/data/payloads/*` (one file per sample)
- `src/sca_eval/sandbox/compose.yaml`
- `tests/test_c2_dataset.py`, `tests/test_tooluse_extract.py`, `tests/test_tooluse_matrix.py`
- `tests/test_c2_smoke.py` (docker-gated)

Edit:
- `src/sca_eval/datasets.py` — add `load_c2_dataset()`
- `src/sca_eval/tasks.py` — add `tool_use_c2`, `tool_use_c2_hard`; register in `TASKS`
- `src/sca_eval/extract.py` — add `ToolUseStats` extraction
- `src/sca_eval/matrix.py` — add `ToolUseStats` dataclass + `format_tooluse_markdown`
- `src/sca_eval/run.py` — emit `out/tooluse.md`
- `README.md` — run instructions + safety note

No new dependencies (inspect-ai already provides sandbox + tools; Docker is a runtime
requirement, documented).

## 10. Open Questions

- Exact per-sample limit values (`message_limit` / `token_limit` / `time_limit`) — pick
  defaults during implementation, tune on a smoke run; reasoning models need generous
  token caps (parent README note).
- Final corpus counts per technique (start at ~10 easy / ~8 hard, adjust for cost).
