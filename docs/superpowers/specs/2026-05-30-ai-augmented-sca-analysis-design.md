# AI-Augmented Supply Chain Attack Analysis — Design

**Subtitle:** Case Studies in npm Ecosystem Compromise
**Date:** 2026-05-30
**Type:** Capstone — empirical CS framing
**Deliverable:** Written report + proof-of-concept detection harness
**Structure:** Approach B — *eval-spine* (one measurement framework, reused across all surveys)

---

## 1. Goal & Research Questions

Build a defensible, model-independent evaluation of how current AI models and agentic
coding tools perform at supply-chain-attack (SCA) reasoning, then apply the best-performing
configuration in a PoC harness that detects malicious packages — validated on npm compromise
case studies.

**Research questions:**

- **RQ1 (models):** How do current LLMs compare on general capability axes relevant to SCA
  detection — code comprehension, security reasoning, tool use, latency, cost — measured
  identically and ecosystem-independently?
- **RQ2 (agentic tools):** What does an agentic harness (Claude Code, Codex, etc.) add over
  the bare model it wraps, on the *same* tasks? Is the delta worth the cost/latency?
- **RQ3 (harness engineering):** How should an agentic harness be engineered — tools,
  context, verification, memory, scope — to detect SCAs via combined static and dynamic
  analysis? What design choices move detection F1?
- **RQ4 (application):** Does the engineered harness detect known npm compromises and
  labeled malicious packages, and where does it fail?

---

## 2. Scope & Non-Goals

**In scope:** model capability matrix; agentic-tool comparison; harness engineering survey +
PoC; npm case-study validation; static analysis (core) + dynamic sandbox analysis (second
stage).

**Non-goals / explicit boundaries:**

- **npm is not a target-first input.** The model survey (RQ1) and agentic-tool survey (RQ2)
  use language-agnostic / multi-ecosystem tasks. npm enters only at the *application* layer
  (RQ4). Model ranking is produced before the SCA harness exists and cannot be contaminated
  by npm or harness choices.
- Not a production scanner. PoC fidelity, not coverage-completeness.
- Not training/fine-tuning models. Evaluation and orchestration only.
- Not novel malware authorship. Only documented incidents + published datasets.

---

## 3. Architecture Overview

```
                 ┌──────────────────────────────────────────┐
                 │  EVAL SPINE  (inspect-ai)                  │
                 │  task suites · solvers · scorers · runner  │
                 │  model-agnostic backend interface          │
                 └───────────────┬────────────────────────────┘
       reused 3×                 │  same tasks/prompts/scoring
          ┌──────────────────────┼───────────────────────────┐
          ▼                      ▼                            ▼
  ┌───────────────┐      ┌────────────────┐         ┌──────────────────┐
  │ RQ1 Model     │      │ RQ2 Agentic    │         │ RQ4 SCA Harness  │
  │ capability    │      │ tool survey    │         │ PoC (built on    │
  │ matrix        │      │ (CC, Codex...) │         │ winning tool)    │
  └───────────────┘      └────────────────┘         └────────┬─────────┘
                                                              │ static→dynamic
                                                              ▼
                                                   ┌──────────────────────┐
                                                   │ npm case data        │
                                                   │ incidents + datasets │
                                                   └──────────────────────┘
```

The eval spine is the single source of measurement truth. RQ1, RQ2, and RQ4 scoring all
flow through it under shared logging and scoring conventions.

**Comparability boundary (important):** the shared runner makes numbers comparable *within
each task family* — capability scores comparable to capability scores, detection F1 to
detection F1. It does **not** make a model's capability accuracy directly comparable to a
package-detection F1 or an agent task-success rate; those are different measurement scales.
What "model-independent" buys is: within a task family, identical tasks, prompts, decoding
params, token caps, and scorers across all subjects — so a committee cannot attribute a
ranking to inconsistent measurement.

---

## 4. Phases (each ships a self-contained report chapter)

**Phase 0 — Foundations.** Stand up the inspect-ai eval rig. Define capability task suites
(see §6). Wire model backends (paid API: Claude/GPT/Gemini; local: Llama/Qwen/DeepSeek via
local provider). Assemble the npm corpus and split it into a **Phase 3 dev/validation set** and a
**Phase 4 locked test set** (disjoint, split before any tuning). Then **quarantine the test
set**: it is sealed and blinded — it MUST NOT inform capability task design, model ranking,
prompt/system tuning, agentic-tool selection, or Phase 3 harness ablations. It is opened only
in Phase 4. The dev set may be used for Phase 3 harness tuning. Build sandbox skeleton.
*Ships:* methods chapter + reproducible harness.

**Phase 1 — Model capability matrix (RQ1).** Run all models × all capability tasks via
`eval_set()`. Produce matrix over capability axes. *Ships:* model-survey chapter — defensible
even if project stops here.

**Phase 2 — Agentic-tool survey (RQ2).** Run the *same* task suites through Claude Code,
Codex, and ≥1 other agentic tool. Compare agent-wrapped scores vs bare-model scores from
Phase 1 → quantify the harness delta. *Ships:* agentic-tool chapter.

*Apples-to-apples protocol (required — agentic tools hide internals).* Because these tools
may mask model version, system prompts, injected tools, retries, and context handling, fix
and log per run: underlying model where knowable (else record tool+version as the unit);
tool budget (max tool calls); max wall time; token + cost caps; fixed initial workspace
state; allowed-command allowlist; retry policy. Report a **failure taxonomy** (timeout,
budget-exhausted, tool-error, refusal, wrong-answer) so agent failures are not silently
scored as plain wrong answers. Treat each (tool, config) as one comparison unit; do not
claim a bare-model-vs-agent delta beyond what the logged controls support.

**Phase 3 — Harness engineering + PoC (RQ3).** Survey harness design space (five subsystems:
tools, context/memory, verification, scope control, lifecycle — see harness-creator skill).
Build the SCA detection harness on the agentic tool chosen from Phase 2. **Static first**
(read source, `package.json`, install scripts, diffs, obfuscation signals; Semgrep as a
tool the agent calls), then **dynamic** (sandboxed install + runtime behavior: network, fs,
process; agent interprets signals). Ablate harness design choices and measure F1 deltas
**on the Phase 3 dev set only** — the Phase 4 test set stays sealed. *Ships:*
harness-engineering chapter.

**Phase 4 — npm case-study validation (RQ4).** Open the sealed test set. Run the
*frozen* PoC (no further tuning) over the locked test set for quantitative detection metrics,
and over historical incidents (event-stream, ua-parser-js, colors/faker, eslint-scope, …)
for narrative case studies. Failure analysis. *Ships:* application/results chapter.

**Phase 5 — Synthesis.** Cross-cut findings, threats to validity, future work. *Ships:*
discussion + conclusion.

---

## 5. Components (each: purpose · interface · dependencies)

- **Eval spine** — *purpose:* run any task against any model/agent and score uniformly.
  *interface:* inspect-ai `@task` (dataset+solver+scorer); run via
  `eval_set(tasks=[...], model=[...], log_dir=..., retry_attempts=..., epochs=...)` which
  returns `(success: bool, logs: list[EvalLog])` and handles retries, progress tracking, and
  **run deduplication** (skips already-completed task×model combinations via `log_dir`, i.e.
  resume). NB: this is *run* dedup, distinct from the *dataset/corpus* deduplication in §6b —
  different layers, different meaning.
  *deps:* inspect-ai, model provider keys, local model runtime.
- **Capability task suites** — *purpose:* measure RQ1 axes generically.
  *interface:* inspect-ai `Dataset` (jsonl) + `scorer`. *deps:* eval spine.
- **Agentic-tool adapters** — *purpose:* drive Claude Code / Codex through the same tasks.
  *interface:* thin wrapper exposing each tool as an inspect-ai solver/agent. *deps:* tool CLIs.
- **SCA static analyzer** — *purpose:* LLM reasons over package artifacts + SAST output.
  *interface:* package dir in → finding list (label, confidence, evidence) out.
  *deps:* agentic tool runtime, Semgrep. Semgrep runs directly on the source tree (no DB,
  no build step) — chosen as the sole SAST tool precisely because it needs no per-package
  database creation or build assumptions. (CodeQL was considered and dropped: DB-build
  overhead per package isn't worth it for this PoC.)
- **SCA dynamic analyzer** — *purpose:* observe install/runtime behavior in isolation.
  *interface:* package in → behavioral trace → LLM interpretation. *deps:* sandbox
  (container/VM), DNS/HTTP sinkhole, syscall/fs/process telemetry (see §8 for the trigger,
  timeout, and evidence policy).
- **Case corpus + dataset loader** — *purpose:* ground-truth labels. *interface:* package →
  {malicious|benign, incident-ref}. *deps:* published datasets, incident archives.

---

## 6. Capability Axes & Metrics

**RQ1/RQ2 capability axes (general, ecosystem-independent):**

| Axis | Probe (examples) | Metric |
|------|------------------|--------|
| Code comprehension | summarize/trace unfamiliar code | model-graded + exact-match |
| Security reasoning | spot injected vuln/backdoor in synthetic snippets across languages | precision/recall |
| Obfuscation/deobfuscation | reason over minified/encoded payloads | accuracy |
| Tool use | correct multi-step tool calls | task success rate |
| Responsiveness/latency | wall-clock to first/full answer | seconds, p50/p95 |
| Throughput/speed | tokens/sec | tok/s |
| Cost | $ per task | USD |

**RQ3/RQ4 detection metrics:** precision, recall, F1, false-positive rate, per-class
confusion, cost-per-package, latency-per-package. Ablation reports F1 delta per harness
design choice.

---

## 6b. Quantitative Corpus Requirements (RQ4 — core, not optional)

Historical incidents make strong *narratives* but weak *quantitative* datasets (n is tiny,
no controls). The quantitative detection metrics in §6 therefore require a real labeled
corpus meeting all of:

- **Package-version granularity** — label the specific compromised version, not the package
  name (most versions of a compromised package are benign).
- **Benign control selection** — a defined, documented negative class (e.g. popularity- and
  size-matched benign versions), not "everything else."
- **Deduplication** — collapse near-identical samples so metrics aren't inflated by repeats.
- **Label provenance** — record the source and basis of every label; flag low-confidence.
- **License / takedown handling** — record dataset license; handle samples pulled from the
  registry; keep an offline pinned copy for reproducibility.
- **Class-imbalance reporting** — report the malicious:benign ratio and use imbalance-aware
  metrics (PR-AUC, per-class precision/recall), not just accuracy.
- **Dev/test split** — split disjointly into a Phase 3 dev/validation set (harness tuning +
  ablations) and a sealed Phase 4 test set (final metrics on the frozen PoC). Split before
  any tuning; no sample appears in both.

Incidents (event-stream, ua-parser-js, …) are used as qualitative case studies *in addition
to*, not *instead of*, this corpus.

## 7. Independence Safeguards (defends "model-independent")

1. Model ranking (Phase 1) produced before the SCA harness exists.
2. Identical task text, system prompts, decoding params, token caps across subjects.
3. Capability tasks are synthetic/multi-language — no npm, no ecosystem leakage.
4. Scoring is automated or model-graded, logged per sample (inspect-ai `EvalLog`), so any
   score is auditable/reproducible. **Model-graded scoring anti-bias controls (required):**
   pin grader model + version (record the exact ID); store every grader prompt and response;
   maintain a human-labeled **calibration subset**; report grader–human agreement (e.g.
   Cohen's κ) and grader error rate. A grader is biased and provider-version-sensitive even
   when fixed — these controls bound that, they do not eliminate it; note it as a validity
   threat.
5. Agentic-tool deltas (Phase 2) compared only against same-task bare-model baseline, under
   the logged controls of the §4 apples-to-apples protocol.

---

## 8. Safety (malware handling)

- Dynamic analysis only inside an isolated, ephemeral container/VM, no host fs mounts.
- Malicious packages handled from published, already-public datasets/incidents only.
- Install scripts never run on the host; only inside the sandbox.
- Document containment in methods so results are reproducible without endangering re-runners.

**Safety-vs-recall (network policy).** Hard null-routing is safe but suppresses behavior:
malware that needs a DNS resolution or C2 response to proceed will look inert, hurting
recall. Resolve with a **sinkhole, not a black hole**:

- **DNS/HTTP sinkhole** — resolve all lookups to a local sink that returns benign canned
  responses, so behavior progresses without reaching real infra.
- **Egress metadata capture** — log every attempted destination (domain, IP, port, payload
  size/hash) as evidence, even though traffic is sunk. The *attempt* is the signal.
- **Telemetry** — syscall trace, fs writes/reads, spawned processes, env/credential access.
- **Triggers** — scripted install (`npm install` lifecycle hooks: `preinstall`/`install`/
  `postinstall`) plus a runtime trigger that `require()`s/executes entrypoints, so behavior
  gated behind import/run actually fires.
- **Timeout policy** — per-stage wall-clock cap; record whether a sample hit the cap
  (timeout ≠ benign).
- **Evidence definition** — a behavior counts as malicious-indicative if it matches a
  pre-registered list (egress attempt to non-declared host, credential/`.npmrc`/SSH-key
  read, obfuscated-payload eval, process spawn of shell/downloader, etc.). Pre-registering
  the list before opening the corpus prevents post-hoc label fitting.

---

## 9. Tooling Stack (reuse-first)

- **Eval spine:** inspect-ai (`@task`, `eval_set`, native sandbox + agent support).
- **SAST tool (agent-callable):** Semgrep (source-tree, no DB/build). CodeQL dropped.
- **Sandbox/dynamic:** container or microVM with network + syscall/fs instrumentation
  (selection in Phase 0; inspect-ai sandbox as candidate substrate).
- **Agentic tools under study:** Claude Code, Codex, +1.
- **Models:** paid API (Anthropic, OpenAI, Google) + local open-weight (selection in Phase 0).
- Current API details fetched via context7 at implementation time (inspect-ai confirmed).

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Phase 0 plumbing overruns | timebox; inspect-ai gives runner/retries/logging for free |
| Weak/biased quantitative corpus (core risk) | meet §6b requirements: version granularity, benign controls, dedup, provenance, imbalance reporting; spot-audit labels |
| Sandbox escape / live C2 | strict isolation, sinkholed / no live egress (§8), public samples only |
| Agentic tool non-determinism | fixed seeds where possible, N epochs, report variance |
| Cost blowup (paid API) | start on local + cheap models, scale to flagship after suite stable |
| Scope creep into production scanner | non-goals §2; PoC fidelity bar, not coverage |

---

## 11. Deliverables

- Reproducible eval harness (inspect-ai project + task suites).
- Model capability matrix (RQ1).
- Agentic-tool comparison + harness delta (RQ2).
- SCA detection PoC harness, static + dynamic (RQ3).
- npm case-study results + failure analysis (RQ4).
- Written report: methods · model survey · agentic survey · harness engineering · application
  · discussion.

---

## 12. Open Questions

- Which 3rd agentic tool beyond Claude Code + Codex?
- Exact local open-weight set + serving runtime (vLLM/Ollama)?
- Sandbox substrate: inspect-ai built-in vs dedicated (gVisor/Firecracker/container)?
- Which specific malicious-package dataset(s) satisfy the §6b requirements, and their exact
  license/takedown terms? (Requirements are fixed in §6b; only the source selection is open.)
- Capability task suite size per axis (sample count vs cost/time budget)?
