# Plan: Google — The Gemma 4 Developer Agent

New project folder: `E:\Kaggle\Gemma 4 Developer Agent\`

## Context

[Google — The Gemma 4 Developer Agent](https://www.kaggle.com/competitions/gemma-4-developer-agent) closes **2026-12-02** ($65k). A separate [Paper Track](https://www.kaggle.com/competitions/gemma-4-developer-agent-paper) closes **2026-11-12** ($35k). Today is 2026-09-30. The account (`ahmedsherif382`) is entered in the main track with **0 submissions**.

You submit a `submission.zip` holding a **declarative** Google ADK agent config — no Python entrypoints. The harness (`swegemma`) runs it against SWE-bench-style tasks; the metric is **Resolution Rate** (hidden `test_patch` applied, `pytest` exits 0, JUnit XML clean).

Three facts define the opportunity:

1. **The board, re-read 2026-10-13** (`scripts/analyze_leaderboard.py`; the figures below replace "top 0.17 of 1037 teams", which was three weeks stale). The private set is **58 tasks**, so one task = **0.0172**. Top is **0.24** = 14/58 (2 teams of **2643**); we hold **0.13** = 8/58 at rank **785**, tied with 340 teams. The middle is a pile-up of byte-identical copied notebooks — 353 teams at 7 tasks, 340 at 8, 333 at 9 — and **that band is one task wide, i.e. genuine noise.** But the **gap to the top is 6 tasks (0.11), above our own 0.06 evidence threshold**, so the leaders are doing something real. Two distinct facts: the middle cannot be measured by submitting, and the top is nonetheless a reachable distance away.
2. **The scored budget is 60 min and 100 tool calls per task, and the field uses maybe a third of it.** Competitors report 8–10 turn workflows. `submit_patch` and `get_status` are free. That unused budget is the headroom.
3. **Context, not budget, is the binding constraint.** `max_model_len=32768`, ADK compaction at `token_threshold=14336` with `event_retention_size=5`. A long single-agent trajectory forgets its own reproduction output by turn ~7. So the budget cannot be spent in one context — it must be spent across **many short, disposable contexts.** This dictates the architecture.

Intended outcome: a measurement-first workflow that turns 0.13-by-copying into a genuine top-of-board score, plus a paper-track entry that falls out of the same work (**205 paper-track teams vs 2643 on the main track** as of 2026-10-13 — much better odds per entrant).

**Decisions already made:** scaffold + prompt engineering only (no LoRA training); **Kaggle free tier only** for compute; paper track **in scope**.

## The hard constraint

Local machine is an i7-1355U / 15.7 GB RAM / **MX550 with 2 GB VRAM** / **no Docker** / Windows 11 / Python 3.13. The 31B model **cannot run locally at all**, and the Docker sandbox backend is unavailable. So:

- **Local = authoring only:** YAML bundles, prompts, the offline validator, task analysis, statistics, paper.
- **Kaggle = all execution:** L4×4 accelerator, `sandbox='subprocess'`, 30 GPU-h/week, 9–12 h session cap. ~270 GPU-h nominal over 9 weeks; **plan to 200** and keep 25% slack.

A full 129-task run is ~21–30 GPU-h sequential. Getting it to ~3 h is the single most important engineering task in the project.

## What we already know (no need to re-derive)

Downloaded to the scratchpad and read: `HARNESS_README.md` (the authoritative 49 KB spec), the official starter notebook, the `sample_submission` bundle, `tasks.jsonl`, and five community notebooks.

- **`tasks.jsonl` = 129 tasks**, fields `instance_id, repo, base_commit, patch (GOLD), test_patch, problem_statement, hints_text, created_at`. `FAIL_TO_PASS`/`PASS_TO_PASS` absent; `hints_text` empty for all 129. Repos: fastapi 67, rich 48, requests 13, httpx 1.
- **We hold all 129 gold patches.** That is an offline metric oracle (see §3), not training data.
- **Model:** every agent must declare exactly `gemma-4-31b-it-qat-w4a16-ct`. vLLM TP=4, `tool_call_parser`/`reasoning_parser` = `gemma4`.
- **9 tools:** `run_command`, `submit_patch`, `get_status`, `read_file`, `edit_file`, `write_file`, `get_code_neighbors`, `search_similar_code`, `get_code_subgraph`.
- **The public 0.13–0.15 bundle:** root `swe_coder` with 6 tools + an `agent_tool` `code_analyzer` (read-only, `skip_summarization: true`), **no `eval_config.yaml`** (so it gets the full defaults), `temperature 0.2 / top_p 0.95 / top_k 40 / max_output_tokens 8192 / thinking_budget 4096 / include_thoughts false`, ~450-word 6-step prompt.
- **Harness mechanics that matter:** patch = `git add -N . && git diff --binary HEAD`, so any leftover file in `/workspace` ships; `write_file` rejects `/tmp`, so scratch needs a `run_command` heredoc; test files + `conftest.py`/`pytest.ini`/`pyproject.toml`/`setup.cfg`/`tox.ini` are force-reset before the hidden tests, so editing them never helps; the harness **auto-extracts the working tree even without `submit_patch`**, so reverting a plausible fix is fatal; 3 consecutive turns with no tool call ends the session; no ripgrep, no `tree`, offline.
- **`search_similar_code` does not embed free text** — it resolves against stored node keys and returns full node source, with reports of >100k chars against a 32k window. One bad call can destroy a trajectory.
- `1 submission/day`, 2 final submissions, team size 5.

## Phase 1 — Week 1: zero-GPU foundations

The highest-leverage work costs no GPU quota.

**1a. Harness reconnaissance — `notebooks/00_harness_recon.ipynb`, accelerator None.** Install the wheelhouse, then `inspect.getsource` the harness and dump `EvalConfig` defaults. This answers, for free, questions that would otherwise cost 20+ GPU-h of black-box probing:

- **What is the default `max_turns`?** The crippled sample exposes it as a real key. If the default is ~20 while `max_tool_calls` is 100, then **turns are the true ceiling** and raising them via `eval_config.yaml` is a one-line change — plausibly the single biggest lever in the competition.
- Can `eval_config.yaml` **raise** 60/100, or only lower them? (Currently unverified and load-bearing.)
- Do **sub-agent tool calls** count against the parent's 100? Determines whether the orchestrator topology of §4 is affordable.
- Does **`run_command` execution time** count against the 60 min? If a 200 s pytest burns wall budget, verify-repair loops cost 3× the model.
- Does the harness actually load `skills/`? Does it inject `hints_text`? Does ADK YAML support a declarative loop-exit/escalate?
- Can the sandbox accept **pre-extracted snapshots** and **shared per-repo venvs**?

**1b. Gold/null calibration → `clean-N`. CPU only.** Two model-free runs:
- **Gold:** inject each task's `patch` as the agent patch. Every task must resolve. Any that doesn't is **broken** and is excluded — it is pure variance in the denominator. Expect 5–15 casualties.
- **Null:** `swegemma eval --skip-agent-patch`. Every task must fail. Any that resolves is a free point that dilutes signal, and gets flagged.

Output `data/tasks/clean_N.txt` (N≈115–124). **Every number in the project is reported on clean-N, never on raw 129.**

**1c. Sandbox concurrency, Stage A. CPU only.** Reuse the gold run on a 16-task slice at C = 4, 8, 16, 32, sampling `MemAvailable`, `df /tmp`, and per-process RSS every 5 s. Finds the sandbox ceiling with no model in the picture.

**1d. The offline validator — `src/swegemma_lab/validate.py`.** Highest-ROI file in the repo: it prevents a submission that scores **0.00** on a path typo, with no GPU. Run as `pytest tests/test_bundles.py`, parameterized over every directory in `bundles/`. 14 checks:

1. Extension whitelist `{.yaml,.yml,.md,.txt,.py,.json,.safetensors}` — rejects `.gitkeep`, `.DS_Store`, `.ipynb_checkpoints`, extensionless `LICENSE`.
2. Exactly one `agent.yaml`/`root_agent.yaml` **at zip root, with no top-level directory prefix** (the "zipped the parent folder" bug = 0.00).
3. Unpacked < 3 GiB; warn above 100 MB.
4. `!include` resolution via a custom `SafeLoader` — missing targets **and** files unreachable from `agent.yaml`.
5. Every agent node declares exactly `gemma-4-31b-it-qat-w4a16-ct`.
6. Every `tools:` entry ∈ the 9 allowed names.
7. Agent graph: every `agent_tool`/`sub_agents` target exists, graph is **acyclic**.
8. Every `adapter:` ref has real files, `r`/`lora_alpha` ≤ 128, ≤ 8 adapters. *(This is exactly the `sample_submission` bug — it references `main_lora`/`tool_lora` which don't exist.)*
9. **ADK `{placeholder}` scan** — single-brace tokens in any instruction/`.md`/`SKILL.md` must be whitelisted state keys, else ADK `.format()` raises at runtime. Corollary: **every JSON example in a prompt must use doubled braces.** Most common silent-death bug in declarative ADK.
10. Prompt-vs-reality lint: error on `rg `, `tree `, `pip install`, or scratch writes into `/workspace`.
11. **Generalization lint** (see §3).
12. `eval_config.yaml` guard: has the `evaluation:` key; is not shipping local measurement values. Builder **excludes it by default**; `--ship-eval-config` to include.
13. **ADK dry-load** via `config_agent_utils.from_config('dist/v03/agent.yaml')` — strongest no-GPU check. Treat "model unreachable" as pass, parse/schema errors as hard failure.
14. Canonical listing + `bundle_hash` printed on every build.

**Windows zip gotchas:** use Python `zipfile` with `arcname` from `PurePosixPath`, **never `Compress-Archive`**. Pin `ZipInfo.date_time` and `external_attr` for reproducible hashes. `.gitattributes` → `* text=auto eol=lf`, and the builder forces LF (a stray `\r` breaks YAML scalars and changes the hash).

**1e. First submission by Oct 4: `v00_public_baseline` unmodified.** Anchors the local↔LB calibration map, and hedges the possibility that paper-track eligibility requires a main-track submission.

## Phase 2 — Make evaluation cheap

Three multiplicative levers take a run from ~25 GPU-h to ~3:

- **Continuous batching at C=12–16.** Decode is memory-bandwidth-bound, so weights amortize across the batch. ~8–10× aggregate throughput.
- **`enable_prefix_caching: true`** on the local vLLM. Every task shares the system prompt and every turn re-sends the growing conversation; without it you re-prefill O(context) per turn. **Worth ~2 GPU-h per run — ~50 GPU-h, a fifth of total quota, across the project.** Also `gpu_memory_utilization: 0.90`, `max_num_batched_tokens: 16384`, CUDA graphs on, and `enable_lora: false` for non-LoRA runs.
- **Amortize sandbox setup.** Extract needed snapshots once per session into `/tmp/swegemma/snap/<id>` in parallel and `cp -r` per task; build **one venv per repo**, not 129. `TMPDIR` on local SSD, never `/kaggle/working` (network-backed, awful for many small files). Patch the sandbox factory from the notebook if needed — the official starter already drives `Evaluator` programmatically.

**Stage B concurrency probe (1.5 GPU-h):** same 16-task slice at C = 4, 8, 16, 24, watching vLLM's `Running:`/`Pending:`/`GPU KV cache usage` and preemption counts. Knee minus 25%. Pin it in `runspec.json` and **never vary it between compared runs** — it is apparatus, not a tunable.

**The subtle risk is not RAM, it is vCPU contention corrupting the metric.** pytest is CPU-bound; at high C you starve vLLM and push tasks into the 60-min wall for reasons unrelated to the config under test, making runs non-comparable. **Fix: decouple the measurement budget from the scored budget.** Measure with `max_tool_calls: 100` (contention-independent) and `max_time_minutes: 180` (effectively off), with an external kill at 90 min logged as `error: harness_timeout`. Separately, verify wall-clock feasibility once per champion by replaying 8 tasks at `--concurrency 1` and requiring a single-stream projection < 45 min.

Also: a janitor thread `rm -rf`ing completed task dirs, and a disk watchdog that pauses launching below 10 GB free.

**Resumability across the 9 h cap.** Do **not** use `--shard-index/--num-shards` for resumption — the math breaks when a shard dies mid-task. Instead: an **append-only fsync'd ledger** `ledger/runs/<run_id>/task_results.jsonl` carrying `(bundle_hash, seed, concurrency, instance_id, resolved, error, tool_calls_used, wall_s, patch_sha)`; **resume = set difference** (`session_runner.py --resume` subtracts done ids and passes the rest as `--task-ids`); a **deadline guard** that stops launching at T−45 min and flushes. Two private Kaggle Datasets persist state: `swegemma-bundles` (variants + `runspec.json`) and `swegemma-runs` (the ledger; keep all traces and patches, `test_outputs/` only for failures). **Never discard a run** — every comparison pools all ledger runs by `bundle_hash`.

## Phase 3 — Statistical design

**The dominant variance is the agent's own stochasticity, not task sampling.** A byte-identical resubmission reportedly landed the same 0.10, but the same archive "can land 0.03 apart." So paired/McNemar is the right instinct but an insufficient tool — **McNemar on k=1 runs will produce false positives at exactly the effect sizes we care about.** Use it only as a secondary statistic.

**Estimator: k-sample paired proportions.** Each task has latent `p_i`; run each config k times over clean-N, estimate `p̂_i = resolved/k`, report `Δ̂ = mean_i(p̂_i^A − p̂_i^B)`. Only borderline tasks contribute variance, giving **SE(Δ̂) ≈ 0.030/√k**:

| k each | SE(Δ̂) | Detectable Δ (α=0.10, 80% power) | GPU-h for the pair |
|---|---|---|---|
| 1 | 0.030 | 0.064 | 6 |
| 2 | 0.021 | 0.045 | 12 |
| 4 | 0.015 | 0.032 | 24 |

Detecting +0.03 costs 24–48 GPU-h **per decision**. Unaffordable. Four moves fix it:

1. **One fixed, heavily-sampled reference.** Run `v00` at **k=4** once in W2 (12 GPU-h) and keep it forever. Candidates then need only k=2 → SE ≈ 0.026, detecting **Δ ≈ +0.055 for 6 GPU-h per candidate** (~4 candidates/week). When a candidate is adopted, its confirmations accumulate, so after two adoptions the new champion is already at k=4 for free.
2. **A/B *bundles*, not single knobs.** We can resolve ±0.05, so every experiment must be designed to move ~0.05. Group 5–10 mechanism-motivated changes under one written hypothesis and accept that per-item attribution is unknowable on free-tier compute. Only the paper needs clean single-item ablations, and those get scheduled deliberately in W5.
3. **Lower-variance surrogate metrics — the biggest untapped instrument.** Binary resolution is the noisiest possible readout, and **we hold all 129 gold patches.** Every run emits a **diagnostic panel**, not a scalar: gold-file hit rate (p≈0.45 not 0.15 → 2–3× smaller SE), gold-file exact-set rate, patch-non-empty rate (near-deterministic), patch-applies rate, contamination rate (touches `tests/`/`conftest.py`/etc.), **scratch-leak rate**, budget-use distributions (% hitting each cap), and a failure taxonomy from traces. Concretely: *"does the 60/100 budget bind?"* needs **one k=1 run**, not statistics — if mean tool calls used is 27 of 100, we have the answer and saved 40 GPU-h.
4. **Stratified `fast-48` for triage.** After the k=4 baseline, label tasks `always`/`borderline`/`never`. Build fast-48 = all borderline (~25) + 15 fixed random `never` (to catch newly unlocked task classes) + 8 `always` (regression tripwire). ~1.2 GPU-h/run. Report a reweighted estimate so subset and full numbers share one time series. **Caveat to write into the README: selecting on baseline outcome biases the level and inflates apparent effects, so fast-48 is for triage and kill decisions only; confirmation is always on clean-N.**

Plus **sequential stopping**: fixed shuffled task order, update a Beta-Binomial posterior every 20 paired tasks, abort if P(Δ>0) < 0.15. Kills clear losers at ~40% of a run.

**Measure the noise floor explicitly, once.** Report the SD of the k=4 reference's four rates on clean-N (expect 0.025–0.030), then subsample to n=60 and report it there (expect ~0.040–0.046). That second number is an empirical prediction of the leaderboard's noise floor and the quantitative explanation of the 0.13 pile-up. It costs nothing extra and it is the paper's headline result.

**Seed:** set it, but **verify it is even plumbed** ADK→vLLM (one task, same seed, twice, C=1, diff the traces — 15 min of GPU in W1). vLLM is not bitwise deterministic under continuous batching, so **build nothing on determinism.**

**Ship rule.** A candidate replaces the champion iff, pooling all ledger runs of both: (1) `Δ̂ > 0` on clean-N and `Δ̂/SE(Δ̂) > 1.28`; (2) `Δ̂_fastapi ≥ −0.02` **and** `Δ̂_rich ≥ −0.02`; (3) no diagnostic regression (patch-non-empty not lower, contamination and scratch-leak not higher); (4) validator green.
**Kill rule:** first k=1 fast-48 estimate below champion − 0.06 → abandoned, no second run.
**Fold rule:** `Δ̂ > 0` but not significant, mechanism-motivated and costless → fold into the next bundle rather than paying 6 GPU-h to prove +0.02.
**Leaderboard rule:** an LB delta below 0.06 never changes a decision. The LB exists to catch catastrophes (bundle fails to load → 0.00) and to build a local↔LB calibration set. Put the local estimate and CI in every submission message; after ~8 submissions, regress LB on local — a widening gap is the overfitting alarm.

## Phase 4 — Generalization guard

The public set is 90% fastapi+rich, and the competitor who wrote repo-specific rules scored **0.05 — below the naive baseline.** That is the most instructive data point available.

**Split by repo and always report both slices** (zero extra GPU — same run, different slicing). Dev: fastapi 67 + httpx 1. **Confirm: rich 48**, chosen because terminal rendering is maximally unlike DI/ASGI/pydantic. Audit: requests 13, touched at most twice and late, as the closest proxy for a small stdlib-adjacent unseen repo. `scripts/report.py` always prints `Δ_all / Δ_fastapi / Δ_rich / Δ_requests`.

**Validator lints:**
- **Repo-token blacklist** — any prompt/`SKILL.md` mention of `fastapi, starlette, pydantic, uvicorn, anyio, rich, textual, console, renderable, segment, requests, urllib3, httpx`, or any concrete repo path/symbol, is a **validator error**, overridable only by `# generic-ok: <reason>`.
- **Abstraction-level rule.** Permitted in prompts: pytest, git, Python tracebacks, the 9 tool signatures, harness mechanics. Forbidden: anything about a specific library.
- **Anti-laundering rule.** Prompt text may be derived **only from failure traces, never from gold patches.** Reading 60 gold patches and writing "check the dependency-resolution cache" into a prompt is overfitting with extra steps. Keep `data/gold/` out of the prompt-authoring workflow.
- **Skills encode procedures, not facts** — "how to run one test node," never "where this repo's tests live."

Two private-set risks worth designing for now: if the unseen repos are **larger**, the 150-line `read_file` cap and 32k window bind much harder (argues for the orchestrator of §5, and against anything assuming small codebases); and `graphs`/`embeddings` quality on unseen repos is unknown, so **prefer `git grep -n`, which cannot fail**, over `search_similar_code`/`get_code_subgraph`.

## Phase 5 — Ranked experiment backlog

**Tier 1 — best Δ per GPU-h**

- **E4. `max_turns` / budget ceiling.** If 1a shows a low default, ship `evaluation: {max_turns: 200}`. **2 GPU-h on fast-48; expected +0.02 to +0.05.** Best ratio in the project; a no-op if the ceilings really are hard, and we learn that for free.
- **E5. Bundle `v01_hygiene` — waste elimination.** ~7 items, none individually measurable, all cheap. **6 GPU-h (k=2); expected +0.02 to +0.05.**
  - **`python -m py_compile <file>` after every `edit_file`.** `edit_file`'s whitespace-flexible tier can silently mis-indent, and in Python that is a guaranteed zero. One call catches every syntax error — the highest-value single instruction in the bundle.
  - Scratch to `/tmp` only, via `run_command` heredoc (`write_file` rejects `/tmp`).
  - **Never revert.** The harness grades the working tree even without `submit_patch`, so an agent that decides its fix was wrong and `git checkout`s leaves an empty diff = certain zero. Instead `git diff > /tmp/best.patch` before each refinement and restore on regression. Highest-consequence rule in the prompt.
  - **Drop `search_similar_code` entirely.** Low value over `git grep -n`, total tail risk against a 32k window. If kept: `k=1`, bare symbol names, and only inside a disposable sub-agent.
  - Raise `max_output_tokens` to 12288 (or cut `thinking_budget` to 2048). At 8192/4096, a thinking overrun truncates mid-tool-call → malformed call → wasted turn. Likely a latent bug in the bundle 19 teams are running.
  - `read_file` paging discipline: `git grep -n 'def <name>\|class <name>'` to locate, then an explicit window starting 10 lines early. (`run_command` truncates at 5k chars, so `sed -n` is strictly worse than `read_file`'s 10k.)
  - Doubled braces in all prompts.
- **E6. Orchestrator + specialist sub-agents — the structural bet.** Root is a thin orchestrator holding only `AgentTool`s + `submit_patch` + `get_status`, so its context never nears 14336 and it never forgets the plan. Specialists: `localizer` (read-only → returns **only** file:line ranges + a one-paragraph hypothesis, its search spew dying with its context), `reproducer` (writes repro to `/tmp`, returns traceback tail ≤1500 chars), `patcher` (the only agent that mutates `/workspace`), `verifier` (targeted tests + `py_compile` + `git status --porcelain` → PASS/FAIL + hygiene report). Failure modes: information bottleneck (mitigate with exact line ranges, not prose), tool-call multiplication (gated on 1a), latency against the 60-min wall (hence the decoupling in §2), ADK placeholder KeyErrors (validator check 9). **6–10 GPU-h; expected +0.03 to +0.08.** Also the centerpiece of the paper.
- **E7. `LoopAgent` verify-repair, `max_iterations: 3`.** The agent can't see the hidden tests but can see that the repro no longer fails, existing tests still pass, and the file compiles. Most failures at p≈0.15 are "produced nothing" / "produced something broken" / "fixed the wrong place," and this attacks the first two. Treat declarative early-exit as **unverified** (1a); safe fallback `max_iterations: 2`. **6 GPU-h; expected +0.02 to +0.06.**

**Tier 2**

- **E8. Sampling sweep.** `thinking_budget ∈ {1024, 4096, 8192}` × `temperature ∈ {0.2, 0.6}` on fast-48. **Note `temperature 0.0` is probably wrong** — greedy decoding can trap the agent re-issuing the same failing `edit_file` forever, and because it *is* calling tools the 3-nudge rule never fires, so it burns the whole budget. Keep 0.2–0.4 for shipping; reserve 0.0 for single-stream replay debugging. **5 GPU-h; ±0.02.**
- **E9. Best-of-2 localization** — two independent `localizer` calls, disagreement itself a signal. **4 GPU-h; +0.01 to +0.03.**
- **E10. `skills/` vs monolithic prompt** — gated on 1a confirming skills load. **4 GPU-h; ±0.02.**
- **E11. Code-graph tool value** — attach/detach the graph tools. CALLS-edges only, **miss async functions entirely** (fatal for fastapi/httpx). **3 GPU-h; ±0.015.**

**Tier 3, leftover quota only**

- **E12. Adaptive second attempt** — on final verify failure, restore baseline and re-attempt from a different hypothesis, keeping the better patch. Uses the genuinely unused half of the budget. **8 GPU-h; 0 to +0.04, high variance.**
- **E13. Best-of-N candidate patches — deprioritized.** There is **no oracle** for selection (only "existing tests pass," "repro passes," "patch is minimal" — a weak selector), and `ParallelAgent` patchers would race on one `/workspace`. One candidate plus three repair iterations (E7) dominates on the same budget.
- **E14. LoRA — out of scope, by decision, and the analysis supports it:** QLoRA on a 31B W4A16 base needs quantization-matched training and 30–60 GPU-h we don't have, and the only data is 129 gold patches from four repos, which is precisely the §4 trap. But `max_loras=8, max_lora_rank=128` is an explicit invitation, so it is the main "what if the field does this" risk. Manage it with a **W6 checkpoint**: if the LB top has jumped to 0.30+, someone trained an adapter, and the W7–W8 contingency goes to the lowest-risk target — a tool-format-adherence adapter distilled from our own successful traces, which is repo-agnostic by construction. Otherwise it stays future work in the paper, where it costs nothing.

## Phase 6 — Project layout

```
E:\Kaggle\Gemma 4 Developer Agent\
  PLAN.md  README.md  requirements.txt  .gitignore  .gitattributes  pytest.ini
  bundles\
    _shared\  prompts\{orchestrator,localizer,reproducer,patcher,verifier}.md
              configs\{sampling_t02.yaml,sampling_t00_debug.yaml,...}
              skills\{pytest_targeting,git_navigation,patch_hygiene}\SKILL.md
    v00_public_baseline\   v01_hygiene\   v02_orchestrator\   v03_orch_loop\
                           # each with MANIFEST.yaml
  src\swegemma_lab\  validate.py  build.py  ledger.py  metrics.py  stats.py
                     traces.py  tasks.py
  scripts\  00_inspect_harness.py  build_bundle.py  validate_bundle.py
            make_subsets.py  session_runner.py  report.py
            push_dataset.py  push_kernel.py
  notebooks\ 00_harness_recon.ipynb  01_gold_calibration.ipynb
             02_concurrency_probe.ipynb  10_run_eval.ipynb  90_paper_figures.ipynb
  kernels\10_run_eval\kernel-metadata.json
  tests\ test_bundles.py  test_stats.py
  data\tasks\{tasks.jsonl,clean_N.txt,fast48.txt,strata.json}   data\gold\
  ledger\    dist\    paper\
```

Mirrors the `src/ scripts/ notebooks/ tests/` shape already used in `E:\Kaggle\Build with Gemma - Boston`.

**Variants are directories, not git branches** — they must be diffed and run side by side. `build.py --variant v03` **copies** `_shared` + variant overrides into `dist/v03/` (no symlinks: Windows + zip), so local validation and Kaggle execution share one code path. Each `MANIFEST.yaml` records parent variant, one-line hypothesis, changed files, expected Δ, measured Δ — simultaneously the lab notebook and the paper's appendix.

**`bundle_hash` = sha256 over sorted `(relpath, LF-normalized bytes)`**, stored in every ledger row. Makes byte-identity provable and lets runs of one config pool correctly.

**Kaggle CLI.** `kernel-metadata.json` uses `"id": "ahmedsherif382/swegemma-run-eval"`, `enable_gpu: true`, `enable_internet: true`, `competition_sources: ["gemma-4-developer-agent"]`, and `dataset_sources` for the wheelhouse, bundles and runs datasets.

```
kaggle kernels push -p "E:\Kaggle\Gemma 4 Developer Agent\kernels\10_run_eval"
kaggle kernels status ahmedsherif382/swegemma-run-eval
kaggle kernels output ahmedsherif382/swegemma-run-eval -p ledger\incoming
kaggle datasets version -p dist_dataset -m "v03 orch+loop, seed 1003" --dir-mode zip
kaggle competitions submit -c gemma-4-developer-agent -f dist\v03.zip \
  -m "v03 orchestrator+loop; local clean-N 0.214 (k=4, 95% CI 0.17-0.26)"
```

**Likely wrinkle to verify in W1:** `enable_gpu: true` selects "a GPU" and probably cannot request L4×4 specifically. If so the runbook is: push via CLI, set accelerator = L4×4 in the browser once, then "Save & Run All" — the setting persists across later pushes.

**Parameterize runs without editing the notebook.** `10_run_eval.ipynb` reads `runspec.json` (`{variant, seed, task_list, concurrency, deadline_minutes, resume_run_id}`) from the bundles dataset. A new experiment is a **dataset version bump plus a re-run of the same kernel** — no notebook edits, no drift, and the runspec lands in the ledger.

## Timeline and GPU-hour budget

200 GPU-h planned of ~270 nominal. A 3 h run never needs sharding within a 9 h session.

| Week | Dates | GPU-h | Work | Milestone |
|---|---|---|---|---|
| W1 | Sep 30 – Oct 6 | **6** | 1a–1d (all CPU). Concurrency Stage B (1.5 h). Seed-plumbing check (0.5 h). `v00` k=1 on clean-N (3 h) — should land ≈0.13. | **Submit `v00` by Oct 4.** clean-N frozen, validator green. |
| W2 | Oct 7 – 13 | **28** | Reference k=4 on clean-N (12 h) → strata, fast-48, **noise floor**. `v01_hygiene` k=2. `v02_orchestrator` k=2. E4 on fast-48. | Noise floor published. First ship/no-ship decisions. |
| W3 | Oct 14 – 20 | **28** | Topology ablation on fast-48, 4 arms at k=2 (10 h); winner k=3 on clean-N (9 h). E7. | Champion v2. |
| W4 | Oct 21 – 27 | **28** | Champion to k=4. Trace-driven prompt/skills refinement (E10). Held-out-repo gate on rich. E8 sweep. | Champion v3, generalization table drafted. |
| W5 | Oct 28 – Nov 3 | **28** | **Freeze paper experiments Nov 2.** Fill ablation cells to k=3; the clean single-item ablations the paper needs. | All paper numbers final. |
| W6 | Nov 4 – 10 | **10** | Write the paper. GPU only for missing cells. **LoRA decision checkpoint.** | Paper drafted. |
| W7 | Nov 11 – 17 | **25** | **Submit paper Nov 12.** Back to main track: E9, E12, riskier bets. | Paper submitted. |
| W8 | Nov 18 – 24 | **28** | Two finalist bundles at k=4 each on clean-N (24 h). Head-to-head + repo slices. | Finalists chosen. |
| W9 | Nov 25 – Dec 2 | **20** | Confirmation runs. Wall-clock feasibility replay at C=1. Pick the 2 finals. ~8 h emergency reserve. | **Final submissions by Dec 1.** |

**Paper track is near-free.** Deliverable *"Measuring declarative agent configurations under budget"*, with contributions that are all byproducts: the CPU-only gold/null calibration protocol; **quantified run-to-run variance showing single-run LB deltas below ~0.06 are indistinguishable from noise** — the direct explanation of the 0.13 pile-up; a declarative-topology ablation with held-out-repo generalization; a trace-derived failure taxonomy; and gold-patch localization as a lower-variance surrogate for resolution rate. The rule that keeps it free: **the paper's ablation table *is* the main track's experiment backlog** — never run a separate experiment for the paper, just log enough metadata per run that it becomes a table row.

**Final-submission selection.** With 2 slots and SE ≈ 0.046 on the private set, do **not** take the top two by point estimate — they'll be minor variants of each other. Take the two highest-posterior-mean configs that are **mechanistically different** (e.g. orchestrator+loop, and flat-agent+hygiene), hedging the possibility that context isolation behaves differently on larger unseen repos.

## Verification

- `pytest tests/` green locally: the 14 validator checks over every bundle, plus `stats.py` estimator unit tests against synthetic data with known Δ.
- `python scripts/build_bundle.py --variant v00_public_baseline` reproduces the public bundle **byte-for-byte** (matching `bundle_hash`) — proves the builder and zip path are correct before any variant is trusted.
- `notebooks/00_harness_recon.ipynb` runs on CPU and prints the real `EvalConfig` defaults; every "unverified" item in §1a is answered in writing in `README.md`.
- `notebooks/01_gold_calibration.ipynb`: gold run resolves ~100% of clean-N, null run resolves ~0%. Those two numbers are the instrument's calibration; if they don't hold, nothing downstream is trustworthy.
- `v00` on Kaggle lands ≈0.13 locally **and** ≈0.13 on the leaderboard — end-to-end confirmation that the local harness predicts the grader.
- A deliberate byte-identical rerun of one bundle at a different seed reproduces the claimed ±0.03 swing, confirming the noise model.

## Open items to resolve in W1 (all currently unverified, all load-bearing)

1. Default `max_turns`, and whether `eval_config.yaml` can **raise** 60/100 rather than only lower them.
2. Whether sub-agent tool calls count against the parent's 100 budget.
3. Whether `run_command` execution time counts against the 60-min wall (if yes, E7 uses `max_iterations: 2`).
4. Whether the harness loads `skills/` and injects `hints_text` (empty in all 129 public tasks, but possibly present privately).
5. Whether ADK YAML supports a declarative loop-exit/escalate.
6. Whether `seed` is plumbed ADK→vLLM at all.
7. Whether paper-track eligibility requires a main-track submission or a minimum score — assume it might, which is a second reason to ship `v00` by Oct 4.
8. Whether `kernel-metadata.json` can request L4×4, or whether that needs one browser click per kernel.
