# Experiments — Gemma 4 Developer Agent

Never delete rows. A failed run is information, and several rows below were worth
more than the successes.

**Metric note.** There is no CV here. "Local" is resolution rate on
`clean-N = 102` (`data/tasks/clean_n.txt`), reported as a paired k-sample
estimate with SE ≈ 0.030/√k (`src/swegemma_lab/stats.py`). Public LB is a single
noisy draw on the **58-task** private set (pinned 2026-10-13, T004): three runs
of *identical bytes* scored 0.12 / 0.13 / 0.15, which are **7, 8 and 9 tasks** of
58, so **an LB delta below 0.06 is not evidence.** The converse now matters too:
a delta **above** 0.06 is evidence, and the top of the board is 6 tasks clear of
us.

## Calibration runs (CPU only, 0 GPU-h)

These validate the instrument rather than a config.

| ID | Date | Change | Gold resolved | Null resolved | clean-N | Run time | Notes |
|---|---|---|---|---|---|---|---|
| C001 | 2026-10-01 | First gold/null calibration | 74/129 (57%) | 3/129 | 71 | ~50 min | **Failed its gate.** Discarded. Diagnosed (wrongly) as `install_test_dependencies` being a no-op in subprocess mode. |
| C002 | 2026-10-01 | Stage repo deps via competition `setup.py` resolution, `--no-deps` | — | — | — | ~2 min | **Died at preflight.** `--no-deps` left `pydantic-core` 2.41.4 against a pydantic wanting 2.46.4; every `swegemma` import raised `SystemError`. |
| C003 | 2026-10-01 | Transitive resolve + pin harness packages via pip constraints | 74/129 (57%) | 3/129 | 71 | ~55 min | **Bit-for-bit identical to C001** — 129/129 same verdicts. Proved the dep-staging theory wrong. First run to capture `test_output_tail`, which gave the real diagnosis. |
| C004 | 2026-10-01 | Add `inline_snapshot`, `dirty_equals` + 5 other test-only packages | **105/129 (81%)** | 3/129 | **102** | ~55 min | **Accepted.** +31 tasks. clean-N frozen. |

**C004 gold resolution by repo:** fastapi 62/67 (93%), rich 42/48 (88%),
requests 1/13 (8%), httpx 0/1 (0%).

**Remaining 24 failures are all dependency version drift**, with no missing
modules left — e.g. rich asserts `guess_lexer(...) == "python"` and a newer
Pygments answers `"ipython"`; requests' `test_header_no_return_chars` fails on
newer urllib3. The grader's pinned wheel cache is in a private dataset, so this
is accepted as a floor.

**clean-N composition: fastapi 60 + rich 42, requests 0, httpx 0.** The audit
split is absent; the generalization guard rests on rich-vs-fastapi.

## Agent configurations

| ID | Date | Change vs parent | Local (clean-N) | k | Public LB | GPU-h | Notes |
|---|---|---|---|---|---|---|---|
| E001 | 2026-09-30 | `v00_public_baseline` — faithful reproduction of the public 0.13–0.15 bundle. Root coder (6 tools) + read-only `code_analyzer` AgentTool; no `eval_config.yaml`, so grader defaults apply. `bundle_hash 6f3c38bf51665b01` | not yet measured | 0 | **0.13** | 0 | Reference arm. Scored exactly as predicted, confirming the whole submission path. Third parties reported 0.12 and 0.15 for the same content. |
| E002 | 2026-10-06 | `v01_hygiene` — 11 mechanism-motivated changes vs E001: `py_compile` after every edit; scratch to `/tmp` via heredoc; never-revert protocol with `/tmp/best.patch`; corrected `search_similar_code` usage (symbol keys, not prose); `read_file` over `sed`; separate analyzer sampling; `max_output_tokens` 8192→12288 with `thinking_budget` 4096→2048. `bundle_hash b590d16060ecbfd7` | **blocked, no GPU** | 0 | **pending** (ref 56875884) | 0 | Submitted *without* a local measurement, which the ship rule forbids — justified only because no L4x4 allocation has been granted since 2026-10-05 and the leaderboard is the one open channel. Expected +0.02 to +0.05; the noise floor is ±0.017, so read the result accordingly. Risk: it is *longer* than E001, and the one community A/B suggests shorter prompts win. |
| P001 | 2026-10-06 | **probe_c12** — first run ever to serve a request. v00 on L4x4 at the grader's context (tp=4, 32768), 12 tasks, **probe budgets: 30 calls / 10 min** | 2/12 (17%) at probe budgets — **not comparable** | 1 | n/a | **0.79** | **Completed, rc=0, 13.2 min wall; vLLM up in 2m39s.** First patches ever observed: **6/12 produced a patch**, 3/12 gold-file hit, **0/12 gold-file exact**. Pure waste, both exact rules: **4/12 created a new file, 4/12 leaked a scratch file** — which is *why* exact-set is 0, since any extra path makes `files != gold_files`. Errors: 2 sandbox, 1 timeout, 1 budget_exhausted. Also 12x `ensurepip unavailable in sandbox`: the per-task venv has no pip. **The printed budget verdict was wrong** — rendered against the default 100-call ceiling while the run used 30, so "median 29 of 100, SLACK" was really median 29 of 30 (97% of its budget) and the taxonomy's 1 budget_exhausted contradicted it. Fixed; `budget_verdict` now refuses to generalize from a non-grader ceiling. The budget question remains **open**. |
| E003 | 2026-10-06 | `v02_context_budget` — v01's 11 items with the sampling corrected from P001's evidence. Coder `max_output_tokens` 12288→4096 (input ceiling 28,672), analyzer 3072→2048 (30,720). `bundle_hash 5f62c0069564810c` | not yet measured | 0 | not submitted | 0 | First bundle to validate with **zero warnings**. Fixes a failure that loses whole tasks rather than degrading them, so the size of the effect depends on how often a trajectory exceeds the ceiling — unknown until the distribution is measured. Deliberately no predicted delta. |
| E009 | 2026-10-06 | `v03_budget_guard` — v02 plus the first change derived from per-call behaviour. Analyzer gets the budget discipline the coder already had: a stated ceiling of 8 calls, answer-on-the-8th with CONFIDENCE low, absolute no-repeat rule for commands and file reads, and the fact that its calls are the coder's. Coder told the analyzer spends its 100, to call it at most once, never to re-run it, and that `get_status` is free. `bundle_hash 5d9e0acc8a81cc73` | not yet measured | 0 | not submitted | 0 | Validates PASS with no findings. **The central risk is evidenced, not hypothetical:** the harness injected a `budget_warning` into the analyzer's tool responses **11 consecutive times** in `fastapi_11355` and it re-issued the same grep every time, so instructions bind weakly on this model mid-loop. A hard per-sub-agent cap is **not expressible** in this competition's declarative format — `eval_config.yaml` budgets are session-global, `LoopAgent.max_iterations` does not apply to an `AgentTool`, and no Python may ship. The only enforced lever is the sub-agent's `tools` list; removing `run_command` would make the observed loop structurally impossible at the cost of the analyzer's text search, and is deliberately held back as the next variant. **Measure the re-issue rate and the coder's call share, not only the score.** |
| E002-LB | 2026-10-07 | leaderboard result for `v01_hygiene` | n/a | 0 | **0.08** | 0 | **A regression from v00's 0.13.** -0.05 is just under the 0.06 this project treats as the threshold for LB evidence, so it is the most likely reading rather than a proven one -- but it is the worst of five observations on this competition and in the direction v01's MANIFEST warned about. v01 is 2.6x v00's prompt bytes. |
| E010 | 2026-10-07 | `v04_lean` — v00's prompts **byte-identical**, plus only the split sampling ceilings (coder 4096 / analyzer 2048). The deliberate retreat v01's MANIFEST pre-committed to. `bundle_hash 2c62746873d98cb2` | not yet measured | 0 | **submitted, pending** | 0 | Single-knob by design, which this project normally avoids -- justified because the knob is **not prompt text**, and isolating prompt length requires holding the prompt at v00's bytes. Validates PASS, no findings. **The informative comparison is against v01's 0.08, not against v00's 0.13:** near 0.13 isolates the regression to prompt length; near 0.08 means the prompt was not the cause and something in sampling or the submission path is, which would matter far more. |
| E010-LB | 2026-10-12 | leaderboard result for `v04_lean` | n/a | 0 | **0.10** | 0 | **It discriminated nothing**, which is itself the result. Its MANIFEST pre-registered the reading: near 0.13 would isolate the v01 regression to prompt length, near 0.08 would mean the prompt was not the cause. It landed between. With v00 0.13, v04 0.10 and v01 0.08, every pairwise gap is under the 0.06 this project treats as the evidence threshold, and v04's prompts are byte-identical to v00's. The defensible conclusion is not that these bundles differ in quality but that **the leaderboard cannot resolve effects of the size we are making** -- so stop spending submissions on it and clear the local ship rule first. |
| E012 | 2026-10-12 | `v05_no_analyzer` — **removes the `code_analyzer` AgentTool entirely**, and with it `sub_agents/code_analyzer.yaml`, `prompts/analyzer.md` and `configs/sampling_analyzer.yaml`. Single-item ablation against `v04_lean`: the `agent_tool` block deleted plus the one prompt bullet that referenced it, `diff` against v00's prompt showing exactly one deleted line. `bundle_hash 5f47540cdfb9bf01` | not yet measured | 0 | not submitted | 0 | Validates PASS, no findings; zip round-trip PASS. **Supersedes the plan recorded in E009's row.** E009 said to remove `run_command` from the analyzer; T001 measured two reasons not to. (1) The loop is not specific to `run_command` — three of twelve tasks already loop on `read_file`, one 75 times — so removing one tool displaces the loop instead of ending it. (2) `search_similar_code` is **not** a free-text search: `HARNESS_README.md:497` states the sandbox has no live embedding server, so the query resolves against node keys and the caller must already know a symbol name; with CALLS-only graph tools that miss async, a stripped analyzer would be near-blind on the fastapi 60 of clean-N. Removing the AgentTool instead keeps `run_command` **with the coder**, so the agent loses no capability and only the sub-agent spending 63% of the budget stops existing. **Expected delta is uncertain in sign** — read gold-file hit, not resolution. **Upside is bounded and was not stated when this row was written:** 3 of 12 tasks never called `submit_patch`, so **9 of 12 produced a patch and still failed** and budget exhaustion explains at most a quarter of observed failures; the other three-quarters are patch quality, which this bundle does not touch. Its own `rejected_alternative` argument also cuts against it — if loops migrate between tools they can migrate between agents, and the coder keeps `run_command`. Read **re-issue rate and calls-by-author**, not just the rates. Both limits are now in the MANIFEST. |

## Planned

**ID note.** The configuration table and the planned table disagree on `E003`:
it is `v02_context_budget` above and "k=4 reference run" below. The config table
is authoritative, since those IDs are referenced from `MANIFEST.yaml` files and
from the ledger. Planned run IDs should be renumbered when they are executed.

| ID | Change | Expected | Cost |
|---|---|---|---|
| E003 | k=4 reference run of E001 on clean-N → strata, `fast-48`, empirical noise floor | reference | ~12 GPU-h |
| E004 | Measure E002 at k=2 against the E003 reference | +0.02 to +0.05 | ~6 GPU-h |
| E005 | Orchestrator + specialist sub-agents (context isolation) | +0.03 to +0.08 | ~6–10 GPU-h |
| E006 | `LoopAgent` verify-repair, `max_iterations` 2–3 | +0.02 to +0.06 | ~6 GPU-h |
| E008 | Budget-ceiling probe: ship `max_tool_calls: 200`, read realised counts from traces | answers an open question | 1 submission |

## probe_c12 trace analysis (2026-10-06, 0 extra GPU-h)

Twelve traces, 57 artifacts, ingested with `scripts/ingest_probe.py`. Everything
below is from data already paid for.

**The 30-call budget was fully saturated.** Tool calls used, per task:
29, 30, 30, 15, 29, 30, 18, 29, 28, 30, 30, 29. Excluding the two tasks that
died early on `ContextWindowExceededError`, **10 of 10 used 28-30 of 30**, and
one failed with an explicit `Agent exceeded tool call budget (30 calls)`. So the
"BUDGET IS SLACK" line was not merely mis-scaled, it was backwards. What 100
does is still unmeasured, but 30 is demonstrably a hard constraint.

**Half the tasks produced no patch at all** (6/12). Four of those used 28-30
calls and still emitted nothing; two died on the context window. That is the
dominant failure, ahead of wrong-place fixes.

**Scratch leaks contaminate the metric but did not cost resolution.** `repro.py`
appears in 5 of 7 patches, and three patches contain *nothing but* a repro
script. But both resolved tasks (`fastapi_11194`, `fastapi_13537`) leaked
`repro.py` and still resolved, because the hidden tests do not care about an
extra top-level file. So the leak drives `gold_exact` to 0/12 and inflates the
waste rate without directly costing score. **Correction to the earlier read:
this is a measurement contaminant first and a score problem second.**

**The two context-window deaths had by far the highest tokens per call**
(11,099 and 11,600, against 5,400-8,800 elsewhere), consistent with the
analyzer flooding its own context rather than with slow growth.

**One pathological task.** `fastapi_14258`: 178 steps and 1,566,017 prompt
tokens against a median of 36 steps and ~210,000, took 10.1 min, and produced
only `repro.py`. Steps are not tool calls, so a loop can run long inside the
call budget.

**Prefix caching reports zero reuse: `total_cached_tokens` is 0 on all twelve
traces**, across 3.9M prompt tokens. Either it is off or litellm is not passing
`cached_tokens` through. Unresolved, and worth one explicit check: if real, it is
a large throughput lever.

## Per-call trace mining (2026-10-06, 0 extra GPU-h)

The section above read the ledger. This one reads the **structured `tool_calls`
field** in the same twelve traces, which the first version of
`scripts/analyze_traces.py` could not see (see `LESSONS.md`). It changes the
diagnosis, so the section above is kept but is no longer the operative read.

**The read-only `code_analyzer` sub-agent consumes most of the call budget.**
Of 491 tool calls, **259 (53%) were made by `code_analyzer`, not by the root
coder.** Per task, coder calls vs sub-agent calls out of a 30-call budget:

| task | coder | analyzer | resolved | outcome |
|---|---|---|---|---|
| fastapi_13537 | **25** | 6 | **yes** | — |
| fastapi_14258 | 152 | 21 | no | session timeout (see below) |
| fastapi_13713 | 14 | 19 | no | — |
| fastapi_11194 | 9 | 23 | **yes** | — |
| fastapi_14099 | 8 | 22 | no | — |
| fastapi_12942 | 7 | 25 | no | — |
| fastapi_13920 | 5 | 26 | no | — |
| fastapi_14262 | 5 | 26 | no | — |
| fastapi_14246 | 4 | 28 | no | — |
| fastapi_11355 | **1** | 30 | no | budget exhausted |
| fastapi_13786 | **1** | 18 | no | context window |
| fastapi_13207 | **1** | 15 | no | context window |

**In 4 of 12 tasks the root coder got 1 to 4 calls before the budget was gone.**
`fastapi_11355` is the clean case: the coder made exactly **one** call —
invoking `code_analyzer` — and the analyzer then ran
`grep -rn "get_type_hints" .` **verbatim 14 times in a row**, exhausting all 30
calls. The coder never read a line of source. This is the mechanism behind "half
the tasks produced no patch": not truncation, **starvation**.

**The looping is verbatim, and it is mostly the analyzer's.** Identical
re-issues (same tool, byte-identical arguments): analyzer **94 of 259 calls
(36%)**; coder 141 of 232, but 134 of those are one pathological task, so the
coder excluding it is ~9%.

**This refutes the premise of the planned 100-call run.** That run asked whether
the four empty-patch tasks were merely truncated at 30. They were not — they were
starved by a sub-agent re-issuing one command. Raising the ceiling to 100 lets
the analyzer loop 100 times instead of 30. The run may still be worth doing for
cost calibration, but question 1 is answered for 0 GPU-h, and the answer is no.

**`v02_context_budget` fixes the second problem, not the first.** Both context
deaths are sub-agent floods (15 of 16 and 18 of 19 calls were the analyzer's,
`read_file` repeated 17 and 14 times consecutively). v00 ships one
`sampling.yaml` at `max_output_tokens: 8192` for *both* agents, and the error is
exact: `requested 8192 output tokens and your prompt contains at least 24577
input tokens, for a total of at least 32769` — one token over. v02's split
ceilings (4096 coder / 2048 analyzer) raise the input headroom and should remove
those two deaths. **Nothing in v02 limits how much budget the analyzer may
spend**, which is now the larger defect.

**The ledger's `tool_calls_used` undercounts, by 2 normally and by 143 once.**
`fastapi_14258` is recorded as 30 calls; the trace holds **173**, including 135
`edit_file` calls, an unbroken run of **82**, and 134 verbatim re-issues of the
same failing edit. The 30-call budget did not stop it — the 10-minute timeout
did. So the call budget is **not reliably enforced**, and any plan that treats it
as a hard bound is resting on the timeout instead.

**Candidate changes this evidence supports**, in order of expected effect:

| Change | Rationale |
|---|---|
| Cap or remove `code_analyzer` | It spends 53% of the budget and loops 36% of the time. The only task with a high coder share resolved. |
| Forbid re-issuing an identical command | 235 of 491 calls were verbatim repeats. A prompt rule costs nothing. |
| Keep v02's split sampling ceilings | Addresses the two context deaths directly, with the arithmetic verified. |

The resolution correlation is **n=2 and not evidence**: `fastapi_13537` had the
highest coder share and resolved, but `fastapi_11194` resolved on 9 coder calls.
The starvation mechanism is established; its effect size is not.

### The three graph tools are never called (probe_c12 traces, 0 GPU-h)

**Correction.** An earlier version of this section claimed tool names were not
recoverable from the traces and reported 2 calls across 12 traces. That was
wrong, and wrong for a sloppy reason: I inspected `steps[0]` -- a *system* step
with a `message` key -- and generalized the schema from it. Agent steps that
carry tool calls have **no `message` key at all**; the call is a structured
`tool_calls` list with `function_name`, `arguments` and per-call
`usage.prompt_tokens`. The real count is **491 calls**. `analyze_traces.py`
reads the structured field and `tests/test_analyze_traces.py` pins the schema.

Actual tool use across 491 calls:

| tool | calls |
|---|---|
| `run_command` | 190 |
| `edit_file` | 143 |
| `read_file` | 120 |
| `code_analyzer` | 14 |
| `write_file` | 13 |
| `submit_patch` | 9 |
| `get_status` | 2 |
| **`search_similar_code`** | **0** |
| **`get_code_neighbors`** | **0** |
| **`get_code_subgraph`** | **0** |

**The agent never touches the three code-graph tools.** Not once in 491 calls,
on any of the 12 tasks. It navigates entirely with `run_command` (grep),
`read_file` and `edit_file`.

This retires a line of reasoning rather than confirming one. Two of v01's
eleven items -- `fix-search-similar-code-usage` and `async-blind-graph-tools` --
exist to correct the *misuse* of tools that are never used, and all three
bundles still carry four mentions of them in prompt text. Given the one
community A/B suggesting short prompts beat long rule-laden ones, that is
measurable bloat buying provably nothing. E011 (code-graph tool value) can also
be cancelled: the answer is already in hand, and detaching a tool the agent
ignores cannot change a score.

Caveat on scope: 12 tasks, all fastapi, under a 30-call ceiling. A starved agent
may skip exploratory tools it would otherwise reach for, so the 100-call run
should re-check this before the prompt text is deleted.


## P002 — paired 100-call run (launched 2026-10-06)

| field | value |
|---|---|
| kernel | `ahmedsherif382/swegemma-paired-eval`, **batch** (not interactive) |
| arms | `v00_public_baseline` (`6f3c38bf51665b01`) and `v03_budget_guard` (`5d9e0acc8a81cc73`) |
| tasks | `probe12.txt` — the same 12 `probe_c12` ran, so the comparison is paired within task |
| budgets | `max_tool_calls=100` (the grader's), `max_time_minutes=30` (**not** the grader's 60) |
| concurrency | 12, matching `probe_c12` |
| cost estimate | ~1.6 GPU-h, worst case ~2.2, against 40.04 h remaining |
| status | **FAILED — 0.76 GPU-h, zero rows.** See below. |

**Why batch.** `probe_c12` was an interactive session, so `/kaggle/working` was
never published and `kaggle kernels output` served a five-day-stale zip. A batch
run commits its output. The notebook also archives after **every arm**, so a
failure in arm 2 cannot lose arm 1, and echoes every ledger row to stdout so
`scripts/recover_from_log.py` can rebuild the run from the log alone.

**What it answers.** Per-task cost at 100 calls — the k=4 reference plan is priced
off 30-call numbers and underprices it ~3x — and whether v03 moves the two
quantities it targets: the coder's share of tool calls (47% baseline) and the
verbatim re-issue rate (235 of 491 calls). Also whether v03's sampling ceilings
remove the two `ContextWindowExceededError` deaths.

**What it does not answer: resolution rate.** Twelve tasks at k=1 cannot separate
a +0.05 effect from noise. Nothing from this run is a score.

**Deliberate deviation.** `max_time_minutes=30` against the grader's 60, to bound
the tail: `fastapi_14258` looped to 173 calls and 1.57M prompt tokens and was
stopped only by the time cap. The ledger row does **not** record the time cap, so
a task lost to it is indistinguishable from one lost legitimately — but both arms
get the same cap and the comparison is paired, so it cannot favour either arm.

**Confound, stated plainly.** v03 contains v02's sampling ceilings *and* the
budget-guard prompts, so a v00-vs-v03 delta cannot be attributed to either alone.
This is the project's standing whole-bundle-A/B policy (project `CLAUDE.md`,
"Deliberate deviations"), accepted because a single-knob run costs the same GPU
hours and would land inside the noise.

### P002 attempt 1 failed before the agent ran (2026-10-06)

`eval_results.zip` held exactly two entries — `paired100_v00/` and
`paired100_v03/`, both **zero bytes**, created **34 seconds apart**. That gap is
the diagnosis: both arms died immediately, so no slow-failure theory applies.

**Cause:** `session_runner.py` returns 4 unless `inline_snapshot` and
`dirty_equals` are importable, and the generated kernel satisfied that gate
neither by staging nor by `--allow-missing-test-deps`. The results directory is
created *before* every validation gate, which is why two empty directories are
the only trace. The gate is correct — probe_c12 lost 5 of 12 tasks to pytest
collection errors from exactly these packages — so the fix is to satisfy it, not
to bypass it.

**Why the documented fix was unavailable:** `scripts/stage_test_deps.py` fetches
from PyPI, and this competition refuses internet with the L4 accelerator.

**Fix (attempt 2):** the wheels are vendored in `vendor/test_deps`, shipped in the
lab dataset by `push_dataset.py`, and installed offline with
`pip --no-index --no-deps`. `--no-deps` is load-bearing: `inline_snapshot`
declares `pytest>=8.3.4` and `rich>=13.7.1`, and letting pip satisfy those would
upgrade packages the per-task venvs inherit — a newer Pygments is already a known
cause of benchmark failures. `dirty_equals` declares no required deps.
The kernel now verifies by **import**, not by pip's exit code, and asserts
**before** vLLM loads, so this class of failure costs seconds rather than an
allocation.

### P002 attempt 2: redesigned for interactive execution (2026-10-07)

**New constraint, from the user and now the governing one: batch GPU runs do not
work on this account.** A `kernels push` with `enable_gpu` queues and is then
cancelled; opening the notebook and running it by hand works. Two attempts
confirmed it.

That inverts the design. The first attempt was written as a *batch* kernel
specifically to avoid the interactive-output problem that lost `probe_c12` — but
batch does not run here, so interactive is the only path and the lost output is a
constraint to engineer around, not a mistake to avoid.

So the log is now the primary record rather than a fallback:

- `session_runner` prints every row behind `LEDGER_ROW ` (`session_runner.py:64`).
- The kernel reprints each arm's rows **as soon as that arm finishes**, so a
  session lost at 50 minutes still banks arm 1.
- The final cell prints a `=== COPY FROM HERE ===` block rebuilt from the ledger
  *files*, so it is complete even if a subprocess's captured stdout was truncated.
- `scripts/recover_from_log.py --write` reads it back. **Verified before shipping**
  against the 12 real `probe_c12` rows rendered in exactly that block format:
  12 rows recovered, failure signatures classified.

Quick Save plus the Output panel remains the better path when available, because
it also recovers patches and traces, which the log does not carry. The log is the
floor; the zips are the ceiling.

### P002 attempt 3: root cause found — the batch image is Python 3.13 (2026-10-07)

Pushed version 3 went to RUNNING and then ERROR in **14 seconds**. An ERROR run,
unlike a cancelled one, **commits its log**, which is the first batch log this
project has ever retrieved — and it settles the batch question mechanically:

```
GPUs 4  total 90.0 GB  compute cap 8.9        <- correct hardware, L4x4
running Python tag cp313; wheelhouse tags ['cp310','cp312','cp38','cp39']
AssertionError  (preflight, cell 3)
```

**The L4x4 batch image runs Python 3.13; the interactive image runs 3.12.** The
wheelhouse ships cp312, so a pushed run cannot install vLLM at all. The
accelerator was never the variable — the **execution mode** is. This explains
every observation at once:

| Attempt | Mode | Python | Outcome |
|---|---|---|---|
| 1 | interactive (run by hand) | 3.12 | passed the tag check, died later on `session_runner`'s import gate |
| 2 | batch | — | ~1.07 GPU-h then cancelled, no log |
| 3 | batch | **3.13** | ERROR at 14 s, log retrieved, cause identified |

So "queues for a long time then gets cancelled" is what a structurally impossible
run looks like from the CLI, and the only measuring mode is **interactive**.

**Cost of the diagnosis:** ~1.8 GPU-h across attempts 2 and 3, of which attempt 3
cost 14 seconds. The preflight assert — written for the T4 failure a day earlier —
is what kept attempt 3 from costing an allocation.

**Corrected:** `CLAUDE.md`'s hardware table said "T4x2 dead, L4 gives Python 3.12".
The wrong half was load-bearing, because it made batch-on-L4 look safe. The table
now splits L4x4 by execution mode, and the preflight assert's own message says to
run interactively and why.

### Correction: the coder's call share is worse than the aggregate said (2026-10-07)

The per-call section above reports "259 of 491 calls (53%) were the analyzer's",
i.e. a **47% aggregate** coder share. That number is right but misleading, and the
per-task view is the one the paired estimator uses:

| statistic | coder's share of tool calls |
|---|---|
| aggregate (all calls pooled) | 47.3% |
| **per-task mean** | **28.9%** |
| per-task median | ~19% |

The aggregate is dominated by two outliers: `fastapi_13537` (80.6%) and
`fastapi_14258` (87.9%, the runaway that issued 135 `edit_file` calls). Strip
those and the typical task gives the coder **3-28%** of the budget:

    11355 3.2%  13786 5.3%  13207 6.2%  14246 12.5%  13920 16.1%
    14262 16.1% 12942 21.9% 14099 26.7% 11194 28.1%  13713 42.4%

So **9 of 12 tasks gave the root coder under 29% of the calls**, and the
starvation finding is stronger than first reported, not weaker. Pooling calls
across tasks weights each task by how many calls it made, which is exactly
backwards when the pathology under study *is* making too many calls.

`scripts/analyze_traces.py --compare` therefore pairs within task, and
`stats.paired_delta` averages the per-task differences. Baselines to beat, from
probe_c12: **coder_call_share 0.289, reissue_rate 0.399** — but both were
computed over *emitted* calls and are **not comparable to anything measured after
2026-10-12**, when the denominator was corrected to calls that actually spent
budget (`analyze_traces.reconcile`). Re-derive them from the traces before using
them as a baseline.

### P002 attempt 4: the blocker is torch, not Python (2026-10-07)

The run reached `COMPLETE` for the first time — in 3 minutes, having run nothing.
Both arms failed identically:

```
ImportError: vllm/_C.abi3.so: undefined symbol: _ZN3c1013MessageLoggerC1EPKciib
```

That is a **libtorch C++ symbol**. `abi3` pins the *Python* ABI, not the C++ one.
The wheel's own metadata gives the answer outright:

| | |
|---|---|
| wheelhouse `vllm-0.19.1` declares | `torch==2.10.0` |
| Kaggle image ships | **torch 2.11.0+cu128** |
| `Requires-Python` | `<3.14,>=3.10` — **3.13 is supported** |

**So Python 3.13 was never the blocker.** The cp313 overlay was necessary but
addressed the wrong axis; torch being one minor version off is what breaks the
link. Everything upstream now works: L4×4, 41/41 wheels resolved, harness
preflight PASS.

**The check that lied:** the gate ran `import vllm`, which succeeds because
`_C.abi3.so` loads lazily. It now runs `import vllm._C`, which forces the native
library to load — two seconds, and it reaches the real failure.

**Fix, in flight:** `kernels/12_fetch_torch` is a **CPU kernel with internet** that
downloads `torch-2.10.0+cu128-cp313` (917 MB, confirmed present) plus its pinned
`nvidia-*` deps, and the GPU kernel consumes that kernel's output via
`kernel_sources`. This costs no GPU quota and no local bandwidth. Internet is only
forbidden *with the premium accelerator*, which is exactly why the split works —
the pattern this project's `CLAUDE.md` already prescribed.

First attempt at the fetch failed cleanly and cost nothing: `--index-url` pointed
only at the PyTorch index, where the `nvidia-*` deps do not exist, so pip resolved
torch and then died on `nvidia-cuda-nvrtc-cu12==12.8.93`. Needs
`--extra-index-url https://pypi.org/simple` as well.

## P002 MEASURED — the first paired run that ran (2026-10-07)

Kernel `swegemma-paired-eval` v9, L4×4, both arms `rc=0`, 12/12 tasks each, 35.2 +
15.6 min of agent time. `max_tool_calls=100` (grader's), `max_time_minutes=30`,
concurrency 12. Ledger: `paired100_v00`, `paired100_v03`.

| | v00 | v03 | paired delta | z |
|---|---|---|---|---|
| **resolved** | **0/12** | **0/12** | 0.000 | — |
| gold-file hit | 6/12 | 5/12 | −0.083 | −0.45 |
| gold-file exact | 2/12 | 4/12 | +0.167 | +1.00 |
| non-empty patch | 8/12 | 6/12 | — | — |
| coder call share | 0.344 | 0.412 | +0.068 | +0.50 |
| **re-issue rate** | 0.410 | **0.485** | **+0.075** | +0.83 |
| tool calls (mean) | 86.7 | 76.8 | −9.9 | −0.61 |
| wall (mean) | **24.4 min** | **7.8 min** | — | — |
| context-window deaths | 3 | 1 | — | — |
| budget exhausted | 0 | 2 | — | — |

**Nothing is significant.** n=12 at k=1; the paired SE is 0.17-0.19 on the
localization metrics, so only a delta above ~0.24 would register. Every row above
is "not measured", not "no effect". `report.py` returns HOLD.

### Three findings that do not depend on significance

**1. The agent expands to fill whatever budget it is given.** probe_c12 at a
30-call ceiling used 28-30 calls; this run at a 100-call ceiling used a **median of
96-97**, with 3 of 12 hitting the ceiling exactly. The budget question is now
answered: **raising the ceiling does not buy resolution, it just gets consumed.**
That retires E008 (ship `max_tool_calls: 200`) as a likely dead end, and it means
the 30-call probe was not meaningfully "budget-starved" relative to the grader.

**2. `v03_budget_guard` did not reduce the re-issue rate — it rose**, 0.410 →
0.485. The MANIFEST named this as the central risk and said to measure the
re-issue rate rather than the score; the risk materialised. Prompt rules do not
bind this model mid-loop, which is consistent with the harness's own
`budget_warning` being ignored 11 consecutive times in probe_c12. **The remaining
lever is capability removal, not instruction** — the `tools` list is the only thing
the harness enforces.

**3. v03 is ~3x faster and halves the context deaths.** Mean wall 24.4 → 7.8 min
and context-window deaths 3 → 1, which is the sampling-ceiling change doing exactly
what it was predicted to do. It also doubled gold-exact (2 → 4), consistent with
tighter patches and fewer scratch leaks. None of this is resolution, but at ~1/3 the
wall time per task it **changes the price of every future run** — a k=4 reference on
102 tasks is far cheaper with v03's ceilings than with v00's.

### The uncomfortable number

**0 resolved in both arms**, against probe_c12's 2/12 at a 30-call ceiling. Three
candidate explanations, not yet separated:
- **Noise.** n=12, and 2/12 vs 0/12 is one or two tasks.
- **The 30-minute time cap.** v00's mean wall was 24.4 min against a 30-min cap, so
  slow tasks were likely truncated; probe_c12's cap was 10 min but its budget was
  30 calls, so it never ran long.
- **The environment changed.** This run installs torch 2.10.0 over Kaggle's new
  image, which probe_c12 did not. Resolution comparisons across that change are
  confounded and should not be treated as a time series.

The cheapest discriminator is to re-run v03 alone with `max_time_minutes=60` (the
grader's own cap) and see whether resolution appears. v03 costs ~8 min/task-arm, so
that is roughly 1.6 GPU-h.

## T001 — per-author call anatomy of the v00 arm (2026-10-12, 0 GPU-h)

No new compute. `scripts/analyze_traces.py` re-read the twelve `paired100_v00`
traces already on disk. It is listed here because it **changed what gets built**,
which is the only test of whether an instrument is worth having.

```
python -X utf8 scripts/analyze_traces.py --traces results/eval_v9/results/paired100_v00/traces
```

| Quantity | Value |
|---|---|
| tool calls across 12 traces | 1,040 |
| calls by author — **`code_analyzer`** | **657 (63%)** |
| calls by author — `swe_coder` | 383 (37%) |
| `code_analyzer` invocations | **19** |
| implied cost per invocation | **~35 calls**, against a per-task budget of 100 |
| `run_command` | 535 (51% of all calls) |
| `read_file` | 299 |
| tasks that never called `submit_patch` | **3 of 12** |

**Finding 1 — the analyzer is not a consultation, it is where the budget goes.**
Nineteen invocations consumed 657 of 1,040 calls. Sub-agent calls are the root's
calls (one shared context per task), so the coder is left working on the
remainder. Three tasks never reached `submit_patch` at all, and a task that
produces no patch cannot resolve.

**Finding 2 — the loop is not specific to `run_command`, which killed the
planned v05.** Worst single-tool repeat counts per task:

| Task | Loop | Re-issues | Calls |
|---|---|---|---|
| `fastapi_12942` | 99× `run_command` | 90 | 106 |
| `fastapi_13920` | 76× `run_command` | 76 | 99 |
| `fastapi_14262` | **75× `read_file`** | 78 | 95 |
| `fastapi_11355` | 71× `run_command` | 1 | 98 |
| `fastapi_13713` | **26× `read_file`** | 21 | 98 |
| `fastapi_13207` | **14× `read_file`** | 11 | 16 |
| `fastapi_11194` | 117× `submit_patch` | 130 | 224 |

Three tasks loop on `read_file`, not `run_command`. So the pathology is "loop on
whatever tool is in hand", and stripping one tool from the analyzer displaces the
loop rather than removing it — it would still hold `read_file` and three graph
tools. This is why E012 removes the AgentTool instead of its `run_command`;
the full argument, including why `search_similar_code` cannot substitute for
`grep`, is in `bundles/v05_no_analyzer/MANIFEST.yaml` under `rejected_alternative`.

**Loose end worth a look:** `fastapi_11194` called `submit_patch` 117 times.
`HARNESS_README.md:346-348` says the harness breaks out of the agent loop as soon
as `submit_patch` has been called and the agent emits a final response, so 117
calls is either a free tool being re-called before any final response or a
misreading of the termination rule. `submit_patch` does not count against the
budget, so it costs nothing directly — but it is 224 steps spent on one task.

## P003 — resolve60: can the rig resolve anything at all? (launched 2026-10-12)

**RESULT: FAILED in 14 seconds. It did not answer the question.** rc=1, 0.23
GPU-h, kernel `ahmedsherif382/swegemma-resolve-check` (batch, COMPLETE, so the
output committed).

```
ModuleNotFoundError: No module named 'swegemma.models.discovery'
  session_runner.py:126 in start_server
    from swegemma.models.discovery import validate_single_declared_model
```

**Root cause: the competition republished the wheelhouse on 2026-10-09 14:43**,
between P002 (2026-10-07, where this exact import worked) and P003. The dataset's
`adk_submission` wheel is dated the same day. `swegemma.models` still exists --
the notebook's preflight resolved `swegemma.models.load_tasks` from
`/usr/local/lib/python3.13/dist-packages/swegemma/models/__init__.py` and
printed PASS -- but the `discovery` submodule under it is gone. The import is
unchanged since the runner was first written (`ee517a7`) and is the same one the
**official starter notebook** uses, so this is an upstream API change, not our
bug.

**The gate failed to gate.** The preflight checked
`swegemma.evaluate.Evaluator`, which still imports fine, while `session_runner`
needs four more symbols. A gate that checks a *different* symbol from the one
the script needs is not a gate. Fixed: the generated preflight now imports
exactly what `start_server()` imports, and on failure retries each import alone
so the log names the API that moved. Cost of the lesson: 0.23 GPU-h, versus the
0.76 GPU-h the same class of mistake cost on 2026-10-07.

**What this invalidates.** `CLAUDE.md` asserted the wheelhouse was "built
2026-09-30, never updated". That is false as of 2026-10-09 and has been
corrected. More importantly the environment-pinning note said pinning makes the
stack "stop moving between arms" -- it pins the *image*, and the wheelhouse is a
*dataset*, so it was never covered. **No pin available to us freezes the
wheelhouse.** Any paired comparison spanning a republication is confounded, and
`kernels pull -m` on this kernel reported `docker_image: ""`, i.e. even the image
pin did not register on a freshly created kernel.

**The resolve question is still open.** 0/12 versus 2/12 remains unexplained, and
the next run must re-ask it. Cost to retry once the API is fixed: unchanged, ~1.0-1.5
GPU-h.

**Follow-up launched, 0 GPU-h:** `kernels/13_harness_api` (CPU, internet off)
reads the wheels as zip archives without installing anything and reports which
module now defines `validate_single_declared_model`, plus the new
`swegemma/models/__init__.py` verbatim. Installing the stack to find out would
have needed the GPU image.

One arm (`v00_public_baseline`), the twelve `probe_c12` tasks, 100 tool calls, and
**`max_time_minutes=60` — the grader's own cap** instead of the 30 that P002
deviated to. Generated by `scripts/make_eval_kernel.py --config resolve60`.

**This is not a comparison and yields no delta.** It answers one binary question
that invalidates every comparison until it is settled: `probe_c12` resolved 2/12
at a 30-call ceiling, and P002 resolved **0/12 on both arms** at 100 calls. Three
causes are not separated — noise at n=12, truncation by the 30-minute cap (v00
averaged 24.4 min against it, and the ledger row does not record whether a task
hit the cap), and the torch 2.10.0 upgrade that landed between the two runs.

Pre-registered reading, before the result is known:

- **Non-zero resolution** → the rig measures and the 30-minute cap was the
  culprit. Proceed to re-price and buy E003, the k=4 reference.
- **0/12 with wall times well under 60 min** → the cap was *not* the culprit, and
  `probe_c12`'s 2/12 is the observation needing explanation. Do not buy E003.

Deviation from HANDOFF.md step 3's cost note: it proposed pricing this off v03's
7.8 min/task-arm for ~1.6 GPU-h, but the arm run is **v00**, whose measured mean
is 24.4 min. v00 was chosen anyway because it is the arm the 0.13 leaderboard
number belongs to, so a non-zero result here is comparable to something.

## P004 — where the harness API went (2026-10-12, **0 GPU-h**, CPU kernel)

Three pushes of `kernels/13_harness_api`, each finishing in under a minute on a
**CPU** kernel with internet off. It **installs nothing** — it opens all 165
visible wheels as zip archives — so it cannot fail on dependency resolution and
spends no GPU quota. Installing the stack to answer the same question would have
needed the GPU image and about five minutes of an allocation.

**The answer.**

| Finding | Detail |
|---|---|
| Distributions in the wheelhouse | `swegemma-0.2.11`, `adk_submission-0.2.13` (both dated 2026-10-09) |
| `swegemma/models/` now contains | **only** `__init__.py` and `task.py` — exporting `Task`, `TaskResult`, `EvaluationResult`, `load_tasks`, `extract_test_files_from_patch` |
| `swegemma/models/discovery.py` | **gone** |
| `validate_single_declared_model` | **defined nowhere in any of the 165 wheels** — renamed, not relocated |
| `adk_submission/discovery.py` | **new**, 31,161 B, and holds the replacement |
| The replacement | **`discover_declared_models(submission_dir, normalize_fn=None, ...)`**, alongside `validate_directory(submission_dir, limits=None, ...)` |
| Import path | re-exported at top level: `from adk_submission import discover_declared_models` |

So the harness moved submission discovery out of `swegemma` and into
`adk_submission`, which is where `discover_adapters` already lived — the import
`session_runner` does on the very next line.

**The fix for `scripts/session_runner.py` `start_server()`** (not yet applied;
the return shape still needs one runtime print to confirm):

```python
# was: from swegemma.models.discovery import validate_single_declared_model
from adk_submission import discover_adapters, discover_declared_models
...
declared = discover_declared_models(bundle)   # then enforce exactly one
```

`validate_single_declared_model` both discovered *and* asserted singularity; the
new function only discovers, so **the "exactly one declared model" check is now
ours to make**. That matters: the competition requires every agent and sub-agent
to declare `gemma-4-31b-it-qat-w4a16-ct`, and the old call was what enforced it.
Do not drop the assertion while porting.

**Also worth noting:** `adk_submission.discovery` exposes `discover_skills` and a
`SkillRegistry`, which bears on the long-open question of whether `skills/`
actually loads (PLAN.md E10). Not pursued here.

**Method note, recorded because it generalises:** searching for the symbol by
name returned nothing and would have ended the investigation at "it is gone".
What found the answer was searching **by behaviour** — every `def` in the two
distributions whose name matches `declared|model|validate` — which surfaced
`discover_declared_models` immediately. When a name search comes back empty on
a rename, search the shape of the thing instead.

## S001 — the ship rule could only ever say HOLD (2026-10-12, 0 GPU-h)

Not a run. A correction to the instrument, prompted by an adversarial review of
the session's own decisions, and recorded here because it **re-labels a result
already in this file**.

**The defect.** `stats.decide` ships a bundle only on a significant positive
resolution delta. At the `k` this project can afford, that condition is
unreachable: the single-run paired SE is ~0.030, so the smallest detectable delta
is 0.064 at k=1 and 0.045 at k=2, against `PLAN.md`'s design target of 0.05. A
rule whose only reachable output is HOLD is not conservative, it is **vacuous** —
and worse, it prints the same word for two incompatible findings:

- "we measured this change and it did not help"
- "we could not measure this change at all"

**The fix.** `stats.is_underpowered` compares the detectable delta against the
design target; `decide` returns a third verdict, `UNDERPOWERED`, and never ships
on it. Hard gates (validator, diagnostics) still outrank power, because a broken
validator is a fact rather than an under-sampled one. A significant result at low
power also returns UNDERPOWERED, with the reason naming the winner's curse — the
sign is real, the magnitude is not. 7 new tests; suite 191 → 198.

**What it re-labels. P002's `HOLD` was really `UNDERPOWERED`.** Re-running
`report.py` on the unchanged ledger rows now prints:

```
UNDERPOWERED
  - UNDERPOWERED: k=1 vs k=1 detects only +0.064 against a design target of
    +0.050, so this null means 'not measured', not 'no effect'.
  Localization read: gold_hit -0.0833 (z=-0.45, not significant).
  The surrogate is underpowered too, so this run ranked nothing.
  Spend the next allocation on k, not on another bundle.
```

That last line is the operative one, and it is an indictment of this session's
own plan: the correct response to P002 was to buy `k`, and what was built instead
was another bundle (E012). The instrument now says so in its own output, which is
the only reason it will be believed next time.

**Metric split made explicit.** `gold_hit` carries the iteration loop — it ranks
bundles, needs no test execution, covers all 129 tasks, and at p≈0.45 detects a
change 2–3× smaller for the same spend. `resolved` authorizes shipping and
nothing else does. The split is not new; what is new is that the k=1 case no
longer masquerades as a measured null on either metric.

**Not changed, deliberately:** the ship rule still keys on `resolved`. Promoting
localization to the ship metric was considered and rejected — `report.py`'s own
docstring had the argument already: optimizing a surrogate is how you win the
surrogate. Localization informs the next change; it never authorizes replacing
the champion.

## P005 — resolve60, second attempt (launched 2026-10-12)

Same run shape as P003, which died in 14 s on the moved harness API. What changed
between them is the port, not the experiment.

| Field | Value |
|---|---|
| Kernel | `ahmedsherif382/swegemma-resolve-check` v2, L4×4, batch |
| Arm | `v00_public_baseline` only — the arm the 0.13 leaderboard number belongs to |
| Tasks | `probe12.txt`, 12 tasks, **all 12 verified in clean-N** |
| Budgets | 100 tool calls, **`max_time_minutes=60`** (the grader's own cap) |
| Lab dataset | version published 2026-10-12 12:01:45 UTC, carrying the ported runner |
| **Wheelhouse version at launch** | **2026-10-09 14:43:19 UTC** |
| Cost estimate | ~1.0–1.5 GPU-h of 44.77 available |

The wheelhouse row is new and is now required for every run. It is the variable
that silently broke P003, and a comparison spanning a republication is confounded
in a way the ledger cannot otherwise show.

**What changed since P003**

- `session_runner.start_server` imports
  `adk_submission.discover_declared_models` instead of the deleted
  `swegemma.models.discovery.validate_single_declared_model`, and
  `_single_declared_model` re-adds the exactly-one-model assertion the old call
  used to provide. 4 tests; suite 198 → 202.
- The notebook's preflight gate mirrors `start_server`'s import list exactly,
  including the new symbol. The earlier version of that gate still imported the
  **deleted** symbol — it would have failed the very run it exists to protect,
  which is a neat illustration of why "mirror the imports" has to be mechanical
  rather than remembered.
- The dataset was re-published. The kernel executes the *dataset's* copy of
  `session_runner`, so the local fix alone would have changed nothing.

**Pre-registered reading, recorded before the result is known.** Unchanged from
P003, because the question is unchanged:

- **Non-zero resolution** → the rig measures, the 30-minute cap in P002 was the
  culprit, and the k=4 reference can be priced and bought.
- **0/12 with wall times well under 60 min** → the cap was *not* the culprit.
  Since all 12 tasks are gold-verified resolvable and the harness demonstrably
  passes them under the gold patch (C004), that outcome would point at the agent
  rather than the rig, and `probe_c12`'s 2/12 becomes the observation needing
  explanation.

**This is a binary rig check, not a comparison, so the UNDERPOWERED verdict in
`stats.decide` does not apply to it.** "Does the rig resolve anything at all" is
answerable at k=1; "is bundle A better than bundle B" is not. Do not read a
resolution *rate* off this run.

### P005 RESULT — 0/12 at the grader's full budget, and the cap was not the cause

**Completed, rc=0, ~2.02 GPU-h** (quota 0.23 → 2.25 h). Batch, so the output
committed: ledger, 7 patches and 12 traces all came home.

| | value |
|---|---|
| **resolved** | **0 / 12** |
| gold-file hit | 3 / 12 (25%) |
| gold-file exact | 1 / 12 (8.3%) |
| produced a patch | 7 / 12 (58%) |
| **created a new file** | **6 / 12 (50%)** |
| **leaked a scratch file** | **4 / 12 (33%)** |
| tool calls | median 99; **5 of 12 hit the 100 ceiling** |
| wall | median 25.9 min, **max 47.0 min against a 60 min cap** |

**The pre-registered reading resolves to the second branch.** No task reached 60
minutes, so the time cap was not binding — and resolution is still 0. Since all
12 tasks are in `clean-N` and C004 passes every one of them under the gold patch,
**the harness is not the problem and neither was the cap.** This is about the
agent.

**But P002's 30-minute cap *was* a real confound, just not the cause.** 4 of 12
tasks exceeded 30 minutes here (34.9, 40.2, 32.6, 47.0), so a third of that run
was being truncated. Removing the confound did not change the outcome.

**The failure funnel, which is the actual finding.** Computed from the 7
recovered patches, classifying any `repro*.py` / `verify*.py` as scratch:

| Outcome | n | tasks |
|---|---|---|
| produced **no patch at all** | 5 | 11355, 14099, 14246, 14258, 14262 |
| patch with **no source change** (scratch only) | 2 | 13207, 13713 |
| source change **+ leaked scratch** | 4 | 11194, 12942, 13786, 13920 |
| **clean, source-only patch** | **1** | 13537 |

So **7 of 12 could not possibly have resolved**, whatever the fix quality — they
either submitted nothing or submitted only a reproduction script. Exactly **one
task in twelve produced the kind of patch a human would call an attempt**, and it
failed too.

**What this does to the budget story.** It cuts both ways and the honest version
is mixed:

- **For it:** 4 of the 5 no-patch tasks burned all 100 calls. That is budget
  exhaustion producing nothing, and it is the single largest identified bucket —
  **4 of 12, i.e. a third**, slightly more than the "at most a quarter" written
  into v05's MANIFEST from P002's 3/12 figure.
- **Against it:** the other 7 tasks did not fail for want of budget. 13537
  produced a clean patch in **17 calls and 11 minutes** and still failed.
  `14258` stopped at 21 calls without calling `submit_patch` at all.

So `v05_no_analyzer` plausibly addresses ~a third of failures, and **patch
production and hygiene own most of the rest.**

**The prompt forbids exactly what the agent did.** `prompts/system.md` says
"Scratch files go to /tmp only. Anything left in /workspace becomes part of your
patch." Half the tasks created a new file anyway. This is the third independent
confirmation that **instructions do not bind this model mid-loop** (the others:
`budget_warning` ignored 11 times running, and v03's anti-repeat rules raising
the re-issue rate). It is also reproduced across runs — `probe_c12` recorded 4/12
created-file and 4/12 scratch-leak — so unlike the rate metrics, this is not n=12
noise. It is a stable mechanism.

**THE GATE FIRES AGAINST BUYING k=4.** HANDOFF step 3 said: *"Do not run anything
else until this returns a non-zero resolution, because a rig that resolves
nothing cannot rank bundles."* It returned zero. **Therefore do not buy the k=4
resolution reference.** The money question is no longer "which bundle is better"
but "why does this agent submit a usable patch only 1 time in 12".

**Two tooling bugs found while reading this run, both now fixed:**

1. **`ingest_probe.py` listed the patches and never saved them.** Its own
   docstring promised `<run_id>/{task_results.jsonl,patches/*.patch}`; only the
   jsonl was written. `metrics.read_outcomes` looks for
   `<run_id>/patches/<iid>.patch`, so **every hygiene metric was structurally
   uncomputable for every ingested run in this project's history.**
2. **`Panel.render` printed `0.0%` for metrics it could not compute.** The pooled
   panel therefore read `created a new file 0.0%` and `leaked scratch file 0.0%`
   for P005 — a clean bill of health on the metric that dominates its failures.
   Panels now carry `hygiene_known` and print `n/a (needs patches)`, and
   `waste_rate` returns `None` rather than 0.0 so no caller can treat "not
   measured" as "no waste". With the patches persisted, the same run's panel now
   reports 50% created-file and 33% scratch-leak.

**Estimate miss, recorded per §13:** estimated ~1.0–1.5 GPU-h, actual **2.02**
(+35%). The estimate was priced off P002's 24.4 min mean per task-arm, but
lifting the cap from 30 to 60 let the slow tail run longer — which is precisely
what the run was for. Price a cap-lifting run off the cap, not off the previous
run's mean.

## T002 — the call-count contradiction, and the funnel's mechanism (2026-10-12, 0 GPU-h)

Two trusted sources disagreed about P005: the ledger recorded
`tool_calls_used=100` for `fastapi_13713`, `analyze_traces` counted **565** tool
calls. A backlog item had carried the same suspicion since 2026-10-06 (30 logged
vs 173 in trace) under the heading "the ledger undercounts".

**The ledger was right, and so was the trace.** The harness increments its
counter only inside `check_budget(count_tool_call=True)`
(`swegemma__context.py:542`). Four classes of emitted call never reach that line:

| Class | Why it is not charged | P005 total |
|---|---|---|
| `submit_patch`, `get_status` | `@budget_gated(count_tool_call=False)` (`swegemma__execution.py:71,101`) | 161 |
| AgentTool invocation (`code_analyzer`) | not a budget_gated harness tool; the sub-agent's *own* calls do charge | 17 |
| malformed call | ADK rejects a missing mandatory argument before the tool runs | 33 |
| refused after the cap | `check_budget` returns the BudgetExceeded string **before** incrementing | 312 |

`analyze_traces.reconcile` models this and reproduces `tool_calls_used`
**exactly for all 12 tasks** (1424 emitted → 901 charged), asserted as a golden
test against the real ledger. **The backlog item is closed as not-a-bug.**

### Budget exhaustion does not end the episode

`fastapi_13713` emitted 310 refused calls plus 146 free `submit_patch` calls
*after* its budget was gone, which is why it ran 47 minutes. The cap bounds
charged work, not wall clock. `HARNESS_README`'s claim that the first
`submit_patch` terminates the task is **wrong**: the tool sets
`ctx.patch_submitted` and its own docstring says only the final submission is
evaluated, so an agent can submit 146 times for free.

### The ranking instrument was reading its own noise

`coder_call_share`, `reissue_rate`, `n_calls` and `workspace_writes` — the four
metrics `--compare` ranks bundles with — denominated on *emitted* calls:

- `fastapi_13713` scored `reissue_rate` **0.837**, almost all of it refused and
  free calls made after exhaustion. A bundle that happens to spin longer after
  its budget dies would have looked worse at identical in-budget behaviour.
- `fastapi_13207` reported `workspace_writes` **29** when **3** writes happened.
  The other 26 were the *same* malformed `edit_file` (missing `old_string`),
  rejected by ADK 26 times over.

All four now denominate on charged calls; `n_calls` is renamed `counted_calls`
so the change is visible. probe_c12's recorded 0.289 / 0.399 are **not
comparable** to anything measured after today.

### The funnel has a mechanism, and it is the sub-agent

Joining the corrected per-task metrics with the 7 recovered patches:

| Outcome | n | sub-agent share of charged calls | re-issue rate | first charged edit |
|---|---|---|---|---|
| clean source-only patch | 1 | **0.00** | 0.00 | call 5 |
| source change + leaked scratch | 4 | 0.44 | 0.29 | 1, 11, 15, 81 |
| patch with no source change | 2 | 0.55 | 0.22 | 17, 62 |
| **no patch at all** | **5** | **0.91** | **0.62** | **never** |

Spearman(sub-agent share, outcome quality) = **−0.90** over 12 tasks.

**The decisive fact: in 4 of the 5 no-patch tasks the agent never called
`write_file` or `edit_file` once in 100 charged calls.** The fifth
(`fastapi_14246`) attempted exactly one edit — after its budget was exhausted,
so it was refused. These tasks did not fix the bug badly; **they never attempted
a fix.** The sub-agent consumed 90–98% of the budget re-issuing near-identical
calls (`fastapi_11355`: a 100-call unbroken run of `run_command`) and the coder
never got a turn.

This **upgrades the previous handoff's n=1 hint to a 12-task gradient** and is
now the mechanistic case for `v05_no_analyzer`. Two caveats that must travel
with it:

1. **Observational, not causal.** Heavy analyzer use could be a *symptom* of a
   hard task rather than its cause. What argues against pure difficulty: a
   re-issue rate of 0.62 is repetition, not exploration, and "no edit attempted
   in 100 calls" is not a difficulty-shaped failure.
2. **All 12 tasks are fastapi**, so this does not establish the mechanism on the
   private set.

`fastapi_14258` is a **separate bug**: it stopped at 21 charged calls, never
called `submit_patch` at all, and quit while 79 calls of budget remained. A
premature-stop failure is not a budget failure and needs its own fix.

## T003 — why `fastapi_14258` quit with 79 calls unspent (2026-10-12, 0 GPU-h)

The one P005 task that did not burn its budget. It stopped at **21 charged
calls** of 100, never called `submit_patch`, and was filed as a possible
"premature stop — thought it was done". **It is not that.** From the trace's
last seven steps:

| Step | Source | Completion tokens | Content |
|---|---|---|---|
| 27 | agent (`final`) | 106 | `<\|tool_call>call:grep -rn "class FastAPIError" fastapi/ \| head -20<\|"\|><tool_call\|>` |
| 28 | harness | — | `continuation_nudge`: *"Your previous response reached the token limit before the tool call finished closing"* |
| 29 | agent (`final`) | **25** | the identical malformed string |
| 30–33 | | **25** each | nudge, identical string, nudge, identical string — then the episode ends |

**The agent emitted malformed tool-call token syntax**, so the harness parsed no
tool call at all and classified the step as a final answer. Seven such emissions
in this task; **none anywhere else in the run.**

**The harness's nudge misdiagnoses it, and the misdiagnosis is what makes it
fatal.** The nudge blames the token limit, but the completion was **25 tokens**
against a 32,768-token context with a prompt of ~5,200 — **nothing was
truncated**. So the model is told to "split the change into smaller incremental
edits" when its actual error was malformed special-token output, and it re-emits
the identical 25-token string three times until the harness gives up. 79 calls
of budget are left unspent.

**Nudges themselves are normal: 11 of 12 tasks get 1–4 of them.** Only this one
enters a loop, and the distinguishing feature is the malformed emission, not the
nudge count.

### No action, deliberately

- **Sampling is already conservative** — `temperature: 0.2`, `top_p: 0.95`,
  `top_k: 40`. A malformed special token at T=0.2 is a model quirk, not a
  high-temperature artifact, so dropping the temperature further is a guess with
  a loop risk attached.
- **The nudge text is the harness's, not ours.** We ship YAML and prompts; we
  cannot correct a harness-generated message.
- **n=1.** One task in twelve is ~8%, but the 95% interval on 1/12 runs roughly
  from 0.2% to 38%, so the rate is barely bounded. Against 7 of 12 blocked on
  patch hygiene, with a known lever, this does not compete for attention.

**Recorded rather than fixed.** Watch for it: if a future run shows a second
nudge-loop death, the rate estimate firms up and it becomes worth a lever. The
cheap detector is a `final`-event step whose message contains `<|tool_call`.

## P006 — does removing `code_analyzer` let the agent edit? (launched 2026-10-13)

**Arms:** `v00_public_baseline` (`6f3c38bf51665b01`) then `v05_no_analyzer`
(`5f47540cdfb9bf01`), **both in one session**. 12 `probe_c12` tasks,
`max_tool_calls=100`, `max_time_minutes=60`, concurrency 12, 80-min subprocess
backstop per arm. Kernel `kernels/14_analyzer_ab`, run ids `analyzer_v00` /
`analyzer_v05`. Queued 2026-10-13 ~09:20 UTC.

**Hypothesis (from T002).** The sub-agent starves the coder: in 4 of the 5
P005 no-patch tasks the agent never called `write_file`/`edit_file` once in 100
charged calls, the sub-agent took 90–98% of the budget, and
Spearman(sub-agent share, outcome quality) = −0.90. `v05` deletes the sub-agent
and gives its tools to the coder, so capability is unchanged.

**The read is `gold_hit`**, because a task that never edits has no files and
scores 0 by construction. `resolved` comes free from the same run and is
reported, but still authorises shipping on its own — `gold_hit` only ranks.

| Quantity | `resolve60_v00` (P005) |
|---|---|
| `gold_hit` | 3 / 12 = **0.250** |
| `gold_exact` | 1 / 12 |
| `resolved` | 0 / 12 |

**Power, fixed before the run.** `se_unit` ≈ 0.030 on 129 tasks → ≈ **0.098** on
12, so at k=1 vs k=1 the detectable delta is **~0.24**, about 3 of 12 tasks
flipping. The mechanism targets 5 tasks. **A one-task move (+0.08) is not
distinguishable from noise and must not be read as a result.**

**Decision rule, fixed before the run.**

- `gold_hit` **+0.25 or more** → mechanism real; buy a confirming arm, then read
  `resolved`.
- `gold_hit` **flat** → heavy analyzer use was a symptom of hard tasks, not a
  cause. **Retire v05; do not tune it.**
- `gold_hit` up **but the coder's own re-issue rate rises** to absorb the freed
  budget → the pathology relocated. Retire it. This is v05's own
  `rejected_alternative` argument turned against itself.

### Why both arms, at double the cost

The first design was one `v05` arm paired against P005's rows — same tasks,
caps and pinned image, with the wheelhouse checked at `lastUpdated 2026-10-09
14:43:19` on 2026-10-12. Identical power for half the quota.

**It was abandoned at launch.** Re-checking on 2026-10-13 showed the wheelhouse
**republished 2026-10-12 19:51:31**, hours after the check cleared it — the
third republication of this competition. Pairing across it would have been
confounded invisibly. Same-session arms cannot be. See `LESSONS.md`.

A CPU re-probe (`kernels/13_harness_api`, **0 GPU-h**, run 09:17:19) confirms
the republication did **not** move the harness API: `swegemma-0.2.11` and
`adk_submission-0.2.13` unchanged, `adk_submission/discovery.py` still 31,161 B,
`discover_declared_models` and `validate_directory` still present. The probe
names only those two wheels, so it **cannot** clear the other ~163 — which is
itself the argument for same-session arms. Recorded in
`reference/harness_facts/wheelhouse_2026-10-13.txt`.

**Cost:** estimated **~4.0–5.0 GPU-h** (P005 cost 2.02 for one arm at this exact
shape), against 42.75 h remaining — ~11% of the weekly budget. Priced against
the cap, not a previous run's mean. **Result pending.**

### P006 RESULT — the mechanism was real, and removing it changed nothing (2026-10-13)

**Cost 4.35 GPU-h** (2.25 → 6.60 used), inside the 4.0–5.0 estimate. 24 rows,
both arms, one session. **Verdict: retire `v05_no_analyzer`**, per the rule
fixed before launch.

**The intervention worked exactly as designed.** This is not a void test:

| Process metric (paired, within task, n=12) | v00 | v05 | delta | z |
|---|---|---|---|---|
| `coder_call_share` | 0.543 | **1.000** | **+0.457** | **+6.02** |
| `reissue_rate` | 0.224 | **0.374** | **+0.151** | **+1.87** |
| `counted_calls` | 80.25 | 82.67 | +2.42 | +0.22 |
| `workspace_writes` | 4.50 | 5.25 | +0.75 | +0.49 |

`code_analyzer` calls in the v05 arm: **0 of 1509** — every call made by
`swe_coder`. First charged edit moved from a median of ~20 calls to **~6**, and
the `never` disappeared: in v00's arm one task still never attempted an edit, in
v05's arm **every task did**. The starvation T002 identified was genuinely
removed.

**And the outcome did not move at all.**

| Outcome, same session, paired | v00 | v05 |
|---|---|---|
| `gold_hit` | **5 / 12 = 0.417** | **5 / 12 = 0.417** |
| paired movement | — | **1 gained, 1 lost, net 0** |
| McNemar exact | — | **p = 1.00** |
| posterior P(v05 better) | — | **0.50** |
| `resolved` | 0 / 12 | 0 / 12 |

Pooling v00 across k=3 agrees: `gold_hit` +0.028 (z=+0.55, n.s.), `gold_exact`
−0.028 (z=−0.61, n.s.). Detectable delta was **0.209** and the hypothesis
predicted +0.25 to +0.42, so **this is a genuine null against its own
prediction**, not a failure to measure. `stats.decide` returns UNDERPOWERED on
*resolution* — correctly, since both arms are 0/12 — which is why `gold_hit`
was pre-registered as the read.

**What this means, stated carefully.** The −0.90 Spearman correlation between
sub-agent share and outcome quality was **a symptom of task difficulty, not a
cause of failure.** Hard tasks drew heavy analysis; removing the analyzer did
not make them tractable. T002 flagged this confound explicitly and the run
resolved it the unfavourable way.

**The pathology relocated, exactly as the bundle's own MANIFEST warned.**
`reissue_rate` rose significantly (+0.151) as the coder absorbed the freed
budget with its own repetition. Two new pathologies appeared that v00 never
showed: `fastapi_12942` emitted **174 `submit_patch` calls** in a loop (190 free
calls, budget untouched by them), and `fastapi_14262` emitted **136 malformed
`edit_file` calls** against 0–5 in any v00 task. `MANIFEST.yaml`'s
"THE MECHANISM MAY RELOCATE RATHER THAN DISAPPEAR" risk is now measured, not
hypothetical.

### The same-session design prevented a false positive, measured

v00's own `gold_hit` was **3/12 in P005 and 5/12 in P006** — identical
`bundle_hash 6f3c38bf51665b01`, identical tasks, identical caps, **two tasks of
swing on identical bytes**. `noise_floor` over the two: mean 0.333, **SD 0.118**,
which validates the pre-run arithmetic (`se_unit` ≈ 0.098 on 12 tasks).

**Had the cheap design shipped — one v05 arm paired against P005's rows — it
would have read 0.417 vs 0.250 = +0.167 and looked like a promising effect.** It
is noise. The extra ~2 GPU-h bought the correct answer instead of a false
positive, which is the strongest available argument for never pairing across
sessions. See `LESSONS.md` 2026-10-13.

## T004 — the grader's denominator, read off the public leaderboard (2026-10-13, 0 GPU-h)

**Why this ran at all:** the session-start routine says verify every number
against its live source before writing it. Four numbers in this project's state
files had not been re-read since **2026-09-30** — and all four were wrong.

### What was stale

| Claim carried in `PLAN.md`, `README.md`, `PROGRESS.md`, `CLAUDE.md`, `paper/OUTLINE.md` | Live value, 2026-10-13 |
|---|---|
| Top of leaderboard **0.17** | **0.24** (2 teams) |
| **1037** teams | **2643** teams |
| **~19** teams tied with us at 0.13 | **340** |
| Private set **~60** tasks, one task = 0.0167 | **58** tasks, one task = **0.0172** |
| "the whole visible board is about **4 tasks** wide" | the board spans **14 tasks**; the *mode* is ~1 task wide |
| "**Four** submissions scored" (`PROGRESS.md`) | **three** — 0.13, 0.08, 0.10 |

Our row: `Ahmed_Sherif382`, rank **785 of 2643**, score **0.13**, 3 submissions,
last 2026-10-07. Source: `kaggle competitions leaderboard ... --download`,
aggregated to `data/leaderboard/public_lb_2026-10-13.json` (histogram only; the
2643-name roster is deliberately not committed).

### The method, and why the answer is unique

A displayed score is `resolved / n_tasks` truncated to 2 dp, so only `n_tasks+1`
strings can ever appear. With 2643 teams every reachable low bin is occupied, so
the **set** of occupied strings identifies `n_tasks`. Requiring *exact equality*
over the occupied range — not containment, which every larger denominator
trivially satisfies — leaves one answer:

**n = 58 is the only denominator in 20…220 that reproduces the 14 occupied bins
as consecutive k = 1…14 with no gaps.**

Two independent confirmations, neither assumed:

- **The display truncates.** 11/58 = 0.1897 → floors to **0.18**, rounds to 0.19.
  141 teams hold 0.18; **nobody holds 0.19.**
- **Rounding cannot fit at all.** Under `round()` the nearest fits start at
  n = 93 and demand 8–10 empty bins between 0.01 and 0.24. 2643 teams would not
  leave them empty. `test_rounding_cannot_explain_the_real_board` pins this.

Two hypotheses retired for 0 GPU-h: "~60 tasks" and `README`'s "a denominator of
100 also fits (12, 13, 15)". n=100 is excluded because it would put 0.02, 0.04,
0.07, 0.09, 0.11, 0.14, 0.16, 0.19, 0.21 and 0.23 on the grid — **all ten
unoccupied.**

### The board in tasks

| Score | Tasks | Teams | At or above |
|---|---|---|---|
| 0.24 | 14/58 | 2 | 2 |
| 0.22 | 13/58 | 8 | 10 |
| 0.20 | 12/58 | 28 | 38 |
| 0.18 | 11/58 | 141 | 179 |
| 0.17 | 10/58 | 258 | 437 |
| 0.15 | 9/58 | 333 | 770 |
| **0.13** | **8/58** | **340** | **1110 ← us, rank 785** |
| 0.12 | 7/58 | 353 | 1463 |
| 0.10 | 6/58 | 319 | 1782 |
| 0.08 | 5/58 | 256 | 2038 |
| 0.06 | 4/58 | 160 | 2198 |
| 0.05 | 3/58 | 142 | 2340 |
| 0.03 | 2/58 | 100 | 2440 |
| 0.01 | 1/58 | 53 | 2493 |

### What it changes

1. **The thesis survives but must narrow.** **1,012 of 2643 teams (38%) sit
   within one task of our 8** — 353/340/333 at 7/8/9. Inside that mode a
   submission delta *is* a re-draw, which is the paper's whole argument, now a
   population fact instead of an impression.
2. **And it must state its own bound.** The gap from 8 to the top's 14 is **6
   tasks = 0.11, above this project's own 0.06 evidence threshold.** For the
   first time this project has leaderboard evidence of a *real* effect — someone
   else's. "Nobody can tell whether their agent got better" is true of the middle
   and false of the top, and a judge with the public board open will see that in
   one glance.
3. **It is a new protocol component (§D0),** not just a correction: 0 GPU-h,
   needs only a public download, and transfers to any benchmark with a bounded
   task count and a rounded display.
4. **It does not touch the variance question.** The grid fit settles the
   denominator; the SD of identical runs is still unmeasured, and only a k≥4
   reference would measure it. Do not let the two be conflated.

**Code:** `src/swegemma_lab/leaderboard.py`, `scripts/analyze_leaderboard.py`,
`tests/test_leaderboard.py` (10 tests, pinned to the committed snapshot rather
than a fixture). Suite 213 → 223, and → **227** once v06 existed, because
`tests/test_bundles.py` parameterizes over every bundle directory.

## T005 — v00 is wall-clock bound in the current environment (2026-10-13, 0 GPU-h)

Found while re-reading P006's ledger rows per task rather than as a summary.
**It contradicts what `HANDOFF.md` and `PROGRESS.md` both said**, which was that
the 60-minute cap never binds.

| Run | Bundle | Median wall | Max wall | Tasks ≥59.5 min | Tasks at 100 calls | Wheelhouse |
|---|---|---|---|---|---|---|
| `resolve60_v00` (P005, 2026-10-12 13:42Z) | v00 | **25.9** | 47.0 | **0**/12 | 5/12 | 10-09 |
| `analyzer_v00` (P006, 2026-10-13 11:03Z) | v00 | **60.4** | 60.5 | **6**/12 | 2/12 | 10-12 |
| `analyzer_v05` (P006, 2026-10-13 11:52Z) | v05 | 35.3 | 45.6 | 0/12 | 3/12 | 10-12 |

Six of twelve v00 tasks were terminated by `Agent exceeded session timeout`.

**It is not a concurrency artifact.** All three runs record `concurrency: 12`
and `max_model_len: 32768`, and P006's two arms ran 49 minutes apart, not
simultaneously. **It is not a bundle change** — `analyzer_v00` and
`resolve60_v00` are the same bundle bytes.

**What it most likely is:** the 2026-10-12 19:51:31 wheelhouse republication sits
between the two runs, and summed task wall went 287.7 → 636.5 min, a **2.3×
slowdown on identical bytes.** This is the confound `CLAUDE.md` already warns
about, now with a measured magnitude.

### Why it matters beyond bookkeeping

1. **"No task hit the cap" is true of P005 only**, and that sentence was load
   bearing: it is the stated reason P005's 0/12 could not be blamed on the cap.
   For P005 the reasoning holds. **For P006 it does not**, and P006's v00 arm is
   half-truncated. P006's *comparison* survives untouched, because both arms ran
   in one session under one cap and the pairing is per task.
2. **"Do not ship `max_tool_calls: 200`" was settled on the wrong run.** It was
   settled because the cap bounds charged work and not wall clock — true of v00,
   where **time** is what binds. In v05's topology time does **not** bind (max
   45.6 of 60) and **calls do** (3 of 12 at exactly 100). The conclusion does not
   transfer to a topology that frees the clock. Still do not ship 200 blind, but
   it is reopened for a no-sub-agent topology, not closed.
3. **The sub-agent is a wall-clock sink, not just a call sink.** v00 summed 636.5
   min against v05's 371.2 for the same 12 tasks — v05 is **1.7× faster** — while
   the AgentTool invocation itself is charged as *one* call. A budget metric
   denominated in calls cannot see this at all.

**Also corrected:** the funnel "5 of 12 produced no patch" belongs to P005. In
both P006 arms **11 of 12 produced a patch** and `gold_exact` was 1/12 on each.
The invariant across all three runs is sharper and worse: **tasks that produce a
real code change still resolve 0.** Fix quality, not patch production, is the
live bottleneck.

## E013 — v06_graph_coder: give the root coder the graph tools (submitted 2026-10-13)

`bundle_hash 01edeb6c0ae48adf`, submission **57145400**, status PENDING at
13:41Z. Validator PASS (2 warnings, both identical to v00's). Dataset published
13:45:07Z.

**The one lever:** `search_similar_code` and `get_code_neighbors` added to the
**root** coder, which has never had them — in v00 only the read-only
`code_analyzer` holds them. `read_file` returns ≤150 lines / 10,000 chars per
charged call; `search_similar_code(query, k)` returns the **full source** of the
top-k symbols in one charged call. Step 2 of the prompt is rewritten
symbol-first, because v00's step 2 prescribes "`code_analyzer` first, then grep"
and would otherwise route the agent around the new capability. `diff` against v00
is 2 added tool lines plus that one step; every other prompt byte is identical.
`get_code_subgraph` deliberately omitted (unbounded edge list).

**Pre-registered reading** is in the MANIFEST and is not restated here, except
for the part most likely to be ignored: **count `ContextWindowExceededError`
before reading any other metric.** v06 pipes symbol source into the root context,
whose input ceiling is 32768 − 8192 = 24,576, and a prompt of 24,577 has already
killed a task non-retryably in this project. The leaderboard null band is **7–10
tasks**; only 11+ (0.18) would be evidence on its own.

**Deliberately NOT also lowering `max_output_tokens`**, though the validator
warns about it: v04_lean already tested sampling ceilings alone (0.10), and
moving both axes at once would make a flat result uninterpretable. If context
deaths rose, the follow-up is v06 with a lower root ceiling.

**Honest weakness, written before the result:** T005 shows 5 of 12 tasks produce
a real code change and none resolve, so *fix quality* is the likelier bottleneck
and v06 targets *localization*. v06 is the cheapest untried capability change,
not the best-targeted one. A flat gold_hit confirms the "right file, wrong fix"
hypothesis and is a real result.

## E014 — v07_verify_repair: make running the tests structural (built 2026-10-13, not submitted)

`bundle_hash c04a425bdfb3bb3b`, validator PASS (2 warnings, same two v00 raises),
zip round-trip PASS, 6 files / 5,774 B. Suite 227 → 231. **Queued for the
2026-10-14 slot, and gated on v06 scoring first** (see the confound below).

**What it targets.** The only invariant that has held across all three
60-minute runs: **tasks that produce a real code change still resolve 0.** Both
P006 arms produced 11 of 12 patches; v00 reached `gold_hit` 5/12 and `resolved`
0/12. Localization (v06) and budget waste (v05, retired at p=1.00) have been
addressed without moving the outcome. Fix *quality* is what is left.

v00's prompt already orders a reproduce-and-verify loop in steps 3 and 5 and it
does not happen. So this bundle makes it **structural** rather than instructed:

| | tools |
|---|---|
| `editor` (stage 1) | `read_file`, `search_similar_code`, `get_code_neighbors`, `edit_file`, `get_status` |
| `verifier` (stage 2) | `run_command`, `read_file`, `edit_file`, `get_status`, `submit_patch`, `include_contents: none` |

The editor **has no shell**, so it physically cannot run tests and cannot burn
budget in a grep/pytest loop; the verifier owns `run_command` outright and gets
a **fresh context** with `{problem_description}` templated in, reading `git diff`
rather than recalling 100 turns.

### Why `LoopAgent` was rejected — a hard mechanical finding

`compile_submission` is called **without `callback_registry`**
(`swegemma__agent_runner.py:334`), so it defaults to `None` and **a submission
has no callbacks available at all.** A `LoopAgent` stops early only on a
sub-agent `escalate` event (`google.adk__loop_agent.py:103`), which requires one.

So a `LoopAgent` would run **exactly** `max_iterations` passes with no early
exit — and because the evaluated patch is the **final state of the working tree**
(`HARNESS_README` 8.1: automatic unsubmitted-patch recovery diffs the tree even
if `submit_patch` is never called), a later pass is free to overwrite a fix that
already worked. We resolve ~8 of 58 private tasks, so that is a live risk to real
tasks. **A verify-repair *loop* is not safely expressible in this format.** Only
a single verify *pass* is.

### Two things recorded because they are uncomfortable

1. **Budget starvation is not mitigated, only asked for.** The two stages share
   one 100-call budget and a per-stage cap is not expressible (v03 established
   this). Only prompt text asks the editor to stop early — and "prompt text does
   not bind" is this bundle's own premise. Removing `run_command` bounds the
   *kind* of loop available, not the *number* of calls; T002 saw a 75×
   `read_file` loop, still reachable. **First diagnostic: the verifier's share of
   charged calls.** Near zero means the stage existed on paper only, and the fix
   is a shorter tool list, not a better prompt. Downside is bounded by the
   automatic patch recovery: the floor is ~"v00 without reproduction", not zero.
2. **Confounded with v06 by necessity.** The editor holds v06's two graph tools
   because grep lived inside `run_command`; removing the shell leaves it with no
   text search otherwise. v07 is therefore v06's lever **plus** the topology
   change, and is only readable in sequence — which is why it must not be
   submitted until v06 has scored.

**Pre-registered leaderboard reading:** v00 = 8/58. **6–10 tasks is the null
band**; 11+ is evidence; **5 or fewer means starvation fired**, not that
verification is a bad idea. A 0.00 most likely means the grader rejected a
`SequentialAgent` root — the first non-`LlmAgent` root this project has shipped —
and that reading must be checked before any conclusion about verification.

**Note on the local metric:** `gold_hit` is nearly blind to this mechanism. A
verifier repairing a wrong fix inside a file the editor already touched moves
`resolved` without moving `gold_hit`. Only the leaderboard can see the intended
effect, which is a genuine measurement gap and is stated in the MANIFEST.

## P007 — v00 vs v06 at n=60, 30-minute cap (launched 2026-10-14)

**Launched 10:19 UTC**, kernel `ahmedsherif382/swegemma-graph-ab`, status
`RUNNING` and drawing quota (6.60 → 6.76 GPU-h within 5 min, so it is genuinely
on the GPU and not queued). Expected ~6 GPU-h of the 38.40 that **expire
2026-10-17**.

| field | value |
|---|---|
| arms | `v00_public_baseline`, `v06_graph_coder` |
| tasks | 60, `data/tasks/clean_dev.txt` (fastapi) |
| cap | **30 min** per task (halved from P005/P006's 60 to buy n) |
| calls | 100 (the grader's budget) |
| concurrency | 12 |
| expected rows | 120 |
| wheelhouse `lastUpdated` | **2026-10-12 19:51:31**, verified in the same minute as the push |
| per-arm subprocess timeout | 175 min |

**Why it was launched now rather than held.** The previous handoff left this as
an open call: hold the run until v06's leaderboard score arrives and could
redirect the spend, or spend it. v06 was still `PENDING` **20.7 h** after
submission, so the information that was supposed to redirect the spend was not
arriving, while the quota expires in 3 days and does not carry over. The call
resolved itself.

**Why the comparison is clean.** Same session, one cap, paired per task, and the
wheelhouse stamp is unchanged since P006 — so the 2.3× slowdown T005 found
across the 2026-10-12 republication cannot straddle these two arms.

**What it can and cannot rank.** It ranks **v06 only**. `gold_hit` is nearly
blind to v07's mechanism, because repairing a wrong fix inside a file already
touched moves `resolved` without moving `gold_hit`.

| shape | n | paired SE | detectable delta |
|---|---|---|---|
| P006's 12 tasks @ 60 min | 12 | ~0.17 | ~0.42 |
| **P007, 60 tasks @ 30 min** | **60** | **~0.065** | **~0.16** |

**The cap is not neutral, and the direction of its bias is known in advance:**
at 30 min most tasks are truncated, which *favours* v06's efficiency claim. So a
**null here is strong against v06**, and a positive is weaker than it looks.
**Not comparable to P005/P006 as a time series** — different cap.

**One gate added before launching** (`scripts/make_eval_kernel.py`,
`BUNDLE_GATE_CELL`): assert every arm's bundle is present in the *published*
lab dataset, and that it exposes `agent.yaml`/`root_agent.yaml` rather than only
`agent.yml`, placed **before** the torch install. `push_dataset.py` is a
separate publish action from `git commit`, so a bundle can be committed and
still be absent from the dataset — in which case arm 2 would have failed only
*after* arm 1 spent ~3 GPU-h. The gate costs milliseconds. Verified against the
real bundle layout locally before the push.

### P007 RESULT — v06 rejected: identical quality, significantly more timeouts (read 2026-10-19)

**The run completed on 2026-10-14 and its output sat unread for five days.** Both
arms committed in full — 60 rows each, `surrogate: false`, one session, one cap —
and `kaggle kernels output` returned them intact on 2026-10-19 at **0 GPU-h**.
The 6 GPU-h was already spent; only the reading was missing. Rows are banked at
`ledger/runs/graph_v0{0,6}/`.

| metric | v00 | v06 | delta | gained / lost | McNemar p |
|---|---|---|---|---|---|
| `resolved` | **3/60** = 0.050 | **3/60** = 0.050 | +0.0000 | 0 / 0 | 1.000 |
| `gold_hit` | 36/60 = 0.600 | 31/60 = 0.517 | −0.0833 | 5 / 10 | 0.302 |
| `gold_exact` | 12/60 = 0.200 | 10/60 = 0.167 | −0.0333 | 5 / 7 | 0.774 |
| **timed out (30 min)** | **22/60** | **35/60** | **+13** | **17 / 4** | **0.0072** |

**The verdict is a rejection, and the pre-registration makes it a strong one.**
P007's MANIFEST and kernel markdown both stated in advance that the 30-minute cap
*favours* v06's efficiency claim, so "a null here is strong against v06". The
result is worse than null: the **only** significant effect v06 produced in 120
task-runs is **more timeouts**, at p=0.0072.

**The same three tasks resolved in both arms** — `fastapi_14372`, `fastapi_14873`,
`fastapi_15589`, zero discordant pairs. At this scale resolution is a property of
the task, not of the bundle.

#### The capability hypothesis is closed, and a selection trap nearly reopened it

Splitting by whether a task finished looks like it vindicates v06:

| | gold_hit if timed out | gold_hit if completed |
|---|---|---|
| v00 | 0.409 (n=22) | 0.711 (n=38) |
| v06 | 0.343 (n=35) | **0.760** (n=25) |

That 0.760 > 0.711 reads as "the graph tools help whenever the agent gets to
finish, and the cap is what hides it". **It is an artifact.** v06 has 25
completers against v00's 38, so its completer set is the more heavily selected —
and therefore easier — subset. Conditioning on an outcome the treatment changes
is not a subgroup analysis.

Restricting instead to the **21 tasks that completed in both arms**, which is the
only selection-free comparison available, the effect vanishes exactly:

| metric (n=21, completed in both) | v00 | v06 | gained / lost |
|---|---|---|---|
| `gold_hit` | 16/21 = 0.762 | 16/21 = 0.762 | 1 / 1 |
| `gold_exact` | 6/21 = 0.286 | 6/21 = 0.286 | 2 / 2 |
| `resolved` | 3/21 = 0.143 | 3/21 = 0.143 | 0 / 0 |

**Identical on all three.** So v06's graph tools do not change outcome quality at
all; they only cost wall clock. v06 is strictly dominated — same quality, more
time — and is retired. **`search_similar_code` / `get_code_neighbors` on the root
coder is a dead lever; do not revisit it.**

#### What P007 actually found, which was not what it was built to test

**Wall clock is the dominant loss channel, and it is not a cap artifact.**
Resolution is **3/21 = 0.143** among tasks that finish and **3/60 = 0.050**
overall; `gold_hit` roughly halves on a timeout (0.41 vs 0.71 in v00). 39 of 60
tasks timed out in at least one arm. The budget that binds is **time**, and no
bundle in the queue targets it — v06 spent more of it, and v07 adds a second
agent pass that can only spend more again.

Two caveats, both load-bearing. The cap here is **30 min against the grader's
60**, so the absolute timeout rate overstates the grader's; but P006 independently
put v00 at **6/12 hitting a 60-minute cap**, so time binds there too. And
`resolved` remains **UNDERPOWERED** at k=1 (detectable +0.064 against a 0.050
target), so the flat resolution reading is "not measured", not "no effect" — the
timeout finding, at p=0.0072, is the part that is measured.

#### The context-death hypothesis is refuted

E013 pre-registered `ContextWindowExceededError` as v06's main risk and v06's
MANIFEST named it the primary one. Across 60 v06 task-runs the error taxonomy is
**35 × `agent exceeded session timeout` and nothing else** — **zero** context
deaths. The right risk was wall clock, and it was listed second.

## E012-LB — v05_no_analyzer on the private set (attempted 2026-10-14, DEFERRED)

**Not submitted. `400 Bad Request`, cause narrowed to the 24 h window or the
`PENDING` v06 — see `LESSONS.md` 2026-10-14.** Packaging was verified sound
(validator PASS, round-trip PASS, correct filename, `testzip()` clean) and
nothing registered server-side.

**Decision recorded:** the user chose on 2026-10-14 to spend the slot on v05
despite its MANIFEST's `retired:` block. The retirement stands as a **local**
verdict and is not withdrawn; what it does not cover is the **private repo
mix**, since all 12 tasks in P006 were fastapi while the private 58 are believed
to be other repos. v05 was chosen over v07 because **v07's `fixer` carries v06's
`search_similar_code`/`get_code_neighbors`**, so v07 cannot be read until v06
scores, whereas v05 is unconfounded with v06 and is a **single clean lever
against an already-scored parent**: its `configs/sampling.yaml` is
**byte-identical to v04_lean's** (verified by `diff`), so v05 vs v04 isolates
exactly one change — the removal of the `code_analyzer` AgentTool.

**Pre-registered reading, fixed before the attempt** (parent v04 = 0.10 = 6/58;
1 task = 0.0172; the 0.06 threshold ≈ 3.5 tasks):

| v05 result | reading |
|---|---|
| ≤2 tasks (≤0.03) | **hurts** — retire permanently |
| 3–9 tasks (0.05–0.15) | **null band** — no information; the local verdict stands |
| ≥10 tasks (≥0.17) | **helps on a non-fastapi mix** — the local null was repo-specific |

Do **not** read it against v00's 8 tasks as clean: v05 inherits v04's sampling
ceilings, so that comparison mixes two changes.

### E013 status check — v06's PENDING is anomalous, not a grader backlog (2026-10-14, 0 GPU-h)

v06 (ref 57145400, submitted **2026-10-13 13:41:36 UTC**) was still `PENDING`
at **2026-10-14 10:27 UTC**, i.e. **20.8 h**. The obvious benign explanation is
a backed-up grader. **The leaderboard refutes it.** From the
2026-10-14T10:14 snapshot, counting teams by the date of their last *scored*
submission:

| last scored submission | teams |
|---|---|
| 2026-10-12 | 338 |
| 2026-10-13 | 156 |
| **2026-10-14** | **2** |

So the grader scored 156 teams' 2026-10-13 submissions and has already scored
two from today. **It is running normally; ours specifically is not coming back.**

Two candidate causes, unseparated:

1. **The evaluation is genuinely slow for this bundle.** v06's
   `search_similar_code` returns the **full source** of the top-k symbols in one
   call, into a root context with a 24,576-token input ceiling. Its own MANIFEST
   pre-registers `ContextWindowExceededError` as the main risk, and a 24,577-token
   prompt has already killed a task non-retryably. Many slow context deaths
   across 58 tasks could stretch the run.
2. **The submission is stuck** in a state that never resolves.

**Why this matters beyond v06:** if a `PENDING` submission blocks new ones — one
of the two live explanations for the 2026-10-14 `400` — then a permanently stuck
v06 blocks **every** future submission, not just today's. That converts a
one-day loss into an open-ended one and would need the competition's forum or
Kaggle support rather than anything in this repo.

**P007 partially covers the information loss.** It is running v06 locally right
now at n=60, so `context_window_deaths` from its ledger will test cause 1
directly, independently of whether the leaderboard ever answers.

**Do not resubmit v06** to force it. That would spend another slot on a bundle
whose first copy may still land, and duplicate submissions cannot be told apart
on the board.

## E013-LB — v06 completed evaluation and produced no score at all (2026-10-19, 0 GPU-h)

v06 (ref **57145400**, submitted 2026-10-13 13:41:36 UTC) now reports status
`COMPLETE` with a **blank** `publicScore`, six days on. This is a new failure
mode for this project and it must not be read as "pending".

Three facts pin it:

1. `kaggle competitions submissions --csv` shows `SubmissionStatus.COMPLETE` with
   an empty score field, where v01 and v04 carry `0.08` and `0.10`.
2. The live leaderboard row for this team reads `SubmissionCount: 4` and
   `LastSubmissionDate 2026-10-13 13:41:36` — v06's own timestamp — while the
   displayed score is still **0.13**, i.e. v00's.
3. Submitting v07 on 2026-10-19 **succeeded**, with no `400`.

So **a scoreless submission does not block the queue** — which retires the
open-ended-loss worry E013 raised. What it cost was one slot and the information.

**The cause is unresolved and only one candidate now has evidence.** E013 listed
"the evaluation is genuinely slow for this bundle" as cause 1 and context death
as the mechanism. P007 refutes the mechanism (zero context deaths) and supports
the cause by a different route: v06 timed out on **35 of 60** tasks against v00's
22, at p=0.0072. A bundle slow enough to time out locally on 58% of tasks is the
best available explanation for an evaluation that finished without a score.

**Operational rule this adds:** the submission slot is not a free sample if the
bundle is slow. Cost a bundle's wall clock locally *before* spending a slot on it.

## T006 — the board after six days: we fell 617 places without moving (2026-10-19, 0 GPU-h)

Live snapshot, `kaggle competitions leaderboard --download`, 2026-10-19T09:01Z.
The denominator refit is still **unique at n=58**, so one task remains 0.0172.

| | 2026-10-13 | **2026-10-19** |
|---|---|---|
| teams scored | 2643 | **3199** (+556) |
| our rank | 785 | **1402** |
| our score | 0.13 = 8/58 | **0.13 = 8/58** (unchanged) |
| teams tied with us | 340 | 353 |
| top | 0.24 = 14/58 (2 teams) | **0.24 = 14/58** (2 teams) |
| teams at 0.22 = 13 tasks | 8 | **29** |
| teams at 0.20 = 12 tasks | 28 | **115** |
| teams at or above 0.18 | 179 | **501** |

**The ceiling has not moved and the field underneath it has.** The top is still
14/58, but the population at 12–13 tasks grew ~4× in six days. Standing still
costs rank: 785 → 1402 on an unchanged score.

**Six submission days were spent for nothing** (2026-10-14 … 2026-10-18), on top
of the six the previous handoff already recorded. The last scored submission
remains v00's **0.13** from 2026-09-30.

## E014-LB — v07_verify_repair submitted (2026-10-19, ref 57390543)

`bundle_hash c04a425bdfb3bb3b`, validator PASS (2 sampling warnings, both
pre-existing and accepted), zip round-trip PASS, 231 tests green.

**Why the "do not submit v07 before v06 scores" rule was lifted rather than
broken.** Its stated purpose was attributability — v06 and v07 are confounded by
necessity, so only sequence separates them. v06 will never score (E013-LB), so
there is no score for v07's to be confounded with, and the rule has no referent.
Waiting longer converts a certain daily loss into no information.

**Pre-registered reading, revised by P007.** The MANIFEST's null band is 6–10
tasks and ≤5 means budget starvation fired. P007 adds a *sharper* prior than the
MANIFEST had: wall clock is the binding budget, and v07 adds a second agent pass,
so **the most likely failure mode is now timeout, not call starvation** — and the
worst case is v06's, a `COMPLETE` with no score. A blank score is therefore
**evidence about v07's speed**, not a grader fault. `0.00` still most likely means
the grader rejected a `SequentialAgent` root, the first non-`LlmAgent` root we
have shipped; check that before anything else.

## T007 — where the wall clock goes: decode, not prefill, not tools (2026-10-19, 0 GPU-h)

P007 established that **time** is the binding budget. T007 answers where it goes,
from the 120 ATIF traces already on disk. Instrument:
`scripts/analyze_wall_clock.py`. **The answer is not the intuitive one, and two
plausible hypotheses were tested and killed first.**

### The finding

**Per-step latency is set by how much the model generates, and by almost nothing
else.** Pooled over 120 task-runs:

| relationship | Pearson r |
|---|---|
| **completion tokens per step vs seconds per step** | **+0.968** |
| prompt tokens per step vs seconds per step | **−0.437** |

That is the strongest relationship this project has measured. Decode is
sequential, so generated tokens cost seconds almost deterministically; prefill is
parallel and effectively free by comparison. The prompt correlation is
*negative* because terse tasks get through more steps and so accumulate more
context — context size is a **consequence** of making progress, not a cause of
slowness.

Split by outcome, v00 (the same picture holds for v06):

| | steps | sec/step | completion/step | prompt/step |
|---|---|---|---|---|
| timed out (n=22) | 36 | **50.6** | **712** | 7,551 |
| completed (n=38) | 95 | **16.5** | **212** | 8,691 |

**Prompt tokens per step are the same in both (7.5k vs 8.7k). Completion tokens
per step differ 3.4×, and seconds per step differ 3.1×.** The ratio closes: 50.6
s/step × 36 steps ≈ the 30-minute cap.

### Verbosity buys nothing

Binning all tasks by completion tokens per step, time rises 5.5× while quality
does not improve — in v00 it *falls*:

| quartile | completion/step | sec/step | gold_hit | resolved |
|---|---|---|---|---|
| Q1 terse | 129 | **10.6** | **10/15** | 1/15 |
| Q2 | 227 | 16.6 | 10/15 | 1/15 |
| Q3 | 392 | 29.3 | 9/15 | 0/15 |
| Q4 verbose | 904 | **58.4** | **7/15** | 1/15 |

`enable_thinking: true`, so these completions are mostly reasoning tokens.
**Long reasoning per step is, on this evidence, pure cost.**

### Two hypotheses tested and killed

Recording both, because each was plausible enough to have been built on:

1. **"Context growth is the cost driver."** It is the obvious reading — prompt
   tokens are **97%** of all tokens processed (37.1M vs 1.1M in v00), prefix
   caching is **off** (`cached_tokens: 0` on every step), and a single task
   re-prefills up to 2.68M tokens. **Refuted.** Tasks that timed out had *fewer*
   prompt tokens (286k vs 842k median) because they never got as far, and the
   prompt/step correlation with latency is negative. `total_prompt_tokens` is a
   misleading cost proxy despite dominating the token count.
2. **"Our own `concurrency: 12` starves tasks."** This mattered because, if true,
   the local timeout rate would be an artifact of the rig and would not transfer
   to the grader — it would undercut P007's whole conclusion. **Not supported.**
   Reconstructing concurrency at each task's midpoint from `finished_at` minus
   `wall_seconds`, timed-out tasks ran at median concurrency **9** against
   completed tasks' **11** — i.e. slightly *less* contention, the wrong
   direction. Also killed: the tool mix, which is near identical between the two
   groups (`grep` 60.3% of `run_command` in timed-out tasks vs 55.1% in
   completed; broad whole-suite `pytest` is 1.1%).

### What this licenses, and what it does not

**Licensed:** the lever on wall clock is **tokens generated per step** —
`thinking_budget`, `max_output_tokens`, and prompt pressure toward terse steps.
Not context size, not the tool list, not the topology. This is the first lever
this project has that is aimed at the constraint actually known to bind.

**Not licensed:** a causal claim that forcing terseness is free. This is a
cross-task correlation, and a task where the model rambles may simply be a harder
task. The *timing* half is mechanical and safe to rely on (tokens cost seconds).
The *quality* half establishes only that verbosity does not help — not that
clamping it preserves quality. **That is exactly what the next run must test**,
and it is a single-knob test, which this project normally avoids and here should
not.

**Note against the obvious shortcut:** v01 lowered `thinking_budget` 4096→2048
and v04 lowered `max_output_tokens`, and both scored below v00. Neither is
evidence against this finding — v01 bundled 11 changes, v04 moved a ceiling with
no mechanism in mind, and neither was measured locally at all. The distinction
now available is a *measured mechanism* and a target: the Q1 regime, ~130
completion tokens per step at ~10.6 s/step.

## T008 — v07 also scored nothing: the submission channel itself is now suspect (2026-10-20)

**v07 (ref 57390543) returned `COMPLETE` with a blank `publicScore`**, the second
consecutive blank. E013-LB's explanation for v06 — that a measurably slow bundle
stretched its evaluation — **does not survive a second case**, because v07 is
structurally unrelated to v06.

### The pattern

| sub | date | bundle | score |
|---|---|---|---|
| 56703353 | 2026-09-30 | v00_public_baseline | **0.13** |
| 56875884 | 2026-10-06 | v01_hygiene | **0.08** |
| 56910112 | 2026-10-07 | v04_lean | **0.10** |
| 57145400 | 2026-10-13 | v06_graph_coder | **blank** |
| 57390543 | 2026-10-19 | v07_verify_repair | **blank** |

**Everything before 2026-10-08 scored. Everything since is blank.**

### The grader is not the problem

From the live leaderboard (2026-10-20), counting teams by the date of their last
*scored* submission: **698 teams scored on 2026-10-19** — the same day as v07 —
and 9 already on 2026-10-20. 3289 teams are now scored. The grader is running
normally; ours specifically are not coming back.

Our own leaderboard row reads `SubmissionCount: 5` with
`LastSubmissionDate 2026-10-19 09:04:17` — v07's exact timestamp — while the
displayed score is still **0.13**, i.e. v00's. So the board *registers* the
submission and does not score it.

### Four candidate causes tested and eliminated

Each was checked before spending anything:

1. **Our packaging or submit path changed.** **No.** `git log` on
   `scripts/submit.py`, `scripts/build_bundle.py` and the validator shows the
   last change on **2026-10-06**, which is the code that produced all three
   *scored* submissions. The zip round-trip check also passes on every build.
2. **Organizer `generation_constraints` rejecting our sampling.**
   `compile_submission` raises `SubmissionValidationError` on generation-parameter
   violations, and the grader may pass constraints where our local runs pass
   `None` — so this would be invisible locally and was the strongest candidate.
   **Dead:** v06 and v07 both use sampling **byte-identical to v00's**
   (temperature 0.2, top_p 0.95, top_k 40, `max_output_tokens` 8192,
   `thinking_budget` 4096), and v00 scored 0.13 with exactly those. Note also
   that v01 and v04 *did* move these knobs and both scored.
3. **The grader rejects a non-`LlmAgent` root** (v07's `SequentialAgent`), which
   v07's own MANIFEST pre-registered as the first thing to check. **Not
   supported:** `SequentialAgent` is explicitly wired into the compiler —
   `adk_submission__compiler.py:19` imports it and `:146` passes
   `sequential_agent_cls=SequentialAgent` into `AgentClassFactory`.
4. **A dangling `!include` in v06**, which drops `configs/sampling_analyzer.yaml`
   while keeping `sub_agents/code_analyzer.yaml`. **No:** its analyzer points at
   `../configs/sampling.yaml`, which exists, and P007 ran the bundle for 60 tasks.

So no bundle-specific cause survives, and the two blanked bundles have nothing
structural in common. **One systemic change after 2026-10-07 is more parsimonious
than two coincidental faults in unrelated bundles** — but that is a parsimony
argument, not evidence, and it is explicitly not established.

The competition forum could settle it, and **is not reachable from here**:
`kaggle forums topics list gemma-4-developer-agent` returns **403**, and only
site-wide forums are listed by `kaggle forums list`.

### E015 — the control submission (2026-10-20, ref 57430290)

**Submitted `v00_public_baseline`, byte-identical to sub 56703353 which scored
0.13 on 2026-09-30** — `bundle_hash 6f3c38bf51665b01`, confirmed by `--dry-run`
before sending. This spends the slot on diagnosis rather than progress,
deliberately, because two slots have already produced zero information and a
third ambiguous result is the worst available outcome.

**Pre-registered reading, and it is decisive either way:**

| outcome | conclusion | next move |
|---|---|---|
| **scores 0.13** | the channel works; the fault is **bundle-specific**, and v06/v07 each broke it for reasons we have not identified | resume shipping, but **keep a plain `LlmAgent` root** and treat any novel topology as suspect until one scores |
| **blank** | the channel is **broken for this account**; every submission since 2026-10-08 was worthless and so is every future one | stop spending slots entirely; escalate via the competition forum / Kaggle support in a browser, since no API here reaches it |

**Why `v05_no_analyzer` was not used for this instead**, although it would have
been information-positive: a blank on v05 could not distinguish "channel broken"
from "v05 broken", which is the exact ambiguity that has already wasted two
slots. A control has to be known-good bytes or it is not a control.

**Do not read the control's score as a v00 re-measurement.** Three runs of
identical v00 bytes have scored 0.12 / 0.13 / 0.15 by third-party report, so the
informative content here is **scored vs blank**, not the value.

## E016 — v08_decode_clamp: clamp the thinking budget (built 2026-10-20)

`bundle_hash 26354b2d0153378d`, validator PASS, round-trip PASS, 235 tests.
**Single knob vs v00: `thinking_budget` 4096 → 1024.** `diff -r` against v00
reports one differing file and, ignoring comments, one differing line. Prompts,
`agent.yaml`, the sub-agent, temperature, top_p, top_k and `max_output_tokens`
are byte-identical.

**The value is picked from the per-step distribution, not chosen round.** Over
8,422 observed agent steps in P007:

| percentile | completion tokens on that step |
|---|---|
| p50 | **40** |
| p75 | 186 |
| p90 | 625 |
| p95 | 1,199 |
| p99 | 4,123 |
| max | 8,192 |

The distribution is skewed enough that a clamp at **1024 touches only 6.1% of
steps while removing ~29.6% of total decode** (upper bound). 512 would remove
~46% but truncates 12% of steps, and 256 touches 20%; both were rejected because
v01's sampling notes record that hitting the output cap mid-tool-call leaves an
unclosed call and burns the turn.

**Why `thinking_budget` and not `max_output_tokens`.** It bounds rumination only
and cannot truncate a tool call, avoiding that failure mode; and
`max_output_tokens` is a *reservation* whose input ceiling is `32768 − value`, so
moving it would also change the context budget, making the experiment two changes.

**A deliberate single-knob experiment**, against this project's standing rule to
group changes. Justified because the knob is not prompt text and the mechanism is
specific: grouping would make a flat result uninterpretable, and T007 licenses
the timing half while leaving the quality half genuinely open.

## P008 — v00 vs v08 at n=60, 30-minute cap (launched 2026-10-20 14:51 UTC)

Kernel `ahmedsherif382/swegemma-clamp-ab`, generated from a new `clamp_v08`
config in `scripts/make_eval_kernel.py`. **Estimated ~6 GPU-h of 45.00, which
expire 2026-10-24.**

| field | value |
|---|---|
| arms | `v00_public_baseline`, `v08_decode_clamp` |
| tasks | 60, `data/tasks/clean_dev.txt` (fastapi) |
| cap | 30 min per task |
| calls | 100 (the grader's budget) |
| concurrency | 12 |
| expected rows | 120 |
| wheelhouse `lastUpdated` | **2026-10-12 19:51:31**, read in the same minute as the push — unchanged since P007, so the environment is stable across both runs |
| lab dataset | republished 2026-10-20 14:50:27 with v08 in it, *before* the push |

### The primary endpoint is the timeout rate, and that is a power argument

In P007, at this exact shape:

| endpoint | result | verdict |
|---|---|---|
| `resolved` | 3/60 vs 3/60, **zero** discordant pairs | UNDERPOWERED — ranked nothing |
| `gold_hit` | 36/60 vs 31/60, 5 / 10 | null, p=0.302 |
| **timeout rate** | **22/60 vs 35/60, 17 / 4** | **p=0.0072** |

The timeout rate is the only endpoint this project has ever moved detectably at
affordable k. `resolved` is still reported and still the only thing that
authorizes shipping — but this run is not sized for it, and saying so in advance
is the difference between a designed experiment and a hopeful one.

### Why 30 minutes and not the grader's 60 — arithmetic, not preference

KV on L4×4 is **55,616 tokens**, i.e. max ~10.5× concurrency at full context, so
concurrency cannot rise above 12 to buy waves; it would only add preemption.
60 tasks at concurrency 12 is therefore **5 waves**:

| cap | waves | per arm (+25 min load) | two arms | fits a 9–12 h session? |
|---|---|---|---|---|
| 60 min (the grader's) | 5 | 325 min | **10.8 h** | **no, and with no margin** |
| **30 min** | 5 | **175 min** | **5.8 h** | yes — P007's proven shape |

Splitting the arms across two sessions is not an option: identical v00 bytes
scored `gold_hit` 3/12 and 5/12 in two different sessions.

### The cap's bias runs OPPOSITE to P007's, and is pre-registered

P007's 30-minute cap *favoured* v06's efficiency claim, which is why its null was
a strong rejection. Here the same cap **favours v08**, which is the faster arm by
construction. So **a positive result is weaker than it looks, and a null is
strong against v08.** Stated now so it cannot be discovered afterwards.

Timeouts are known to bind at the grader's cap too — P006 put v00 at 6/12 hitting
60 minutes — so this is a mechanism check at a tighter cap, not a claim about the
grader's absolute rate. **Not comparable to P005/P006/P007 as a time series.**
P007's v00 arm ran this same shape, so it is a useful consistency check on the
environment, but the comparison that counts is the two arms inside this session.

### Confirmed on the GPU, not queued (14:59 UTC)

Status `RUNNING` and quota moved **45.00 → 44.97 h** within 8 minutes of the
push. Both halves matter: a *queued* session gives no warning and looks
identical to a running one in `kernels status` alone, so the quota draw is the
only positive evidence that an allocation was actually granted. It sat `QUEUED`
with 0.00 h drawn for the first ~7 minutes, which is normal allocation latency
rather than the self-block failure mode.

Expected finish ~21:00 UTC (5.8 h). **A watcher is polling for the terminal
state, because the last run's output sat unread for five days** — see LESSONS.md
2026-10-19. Fetch with `kaggle kernels output ahmedsherif382/swegemma-clamp-ab`
the moment it is terminal; a batch run commits `/kaggle/working` even on ERROR,
so an errored run is still worth fetching.

### Why this was launched while the submission channel is broken

The two are independent. Local measurement needs no leaderboard, the quota
expires **2026-10-24** and does not carry over, and if the channel turns out to be
broken then local measurement is the *only* channel left. Holding the run would
have risked losing it for nothing. Submitting v08 is a separate decision and is
blocked on E015.

### P008 RESULT — the clamp works mechanically, and it is the first intervention to move an outcome (2026-10-20)

**Completed 20:17 UTC, fetched immediately.** 120 rows, both arms, one session,
`surrogate: false`. Banked at `ledger/runs/clamp_v0{0,8}/`.

**Cost 10.57 GPU-h against a ~6 GPU-h estimate — a 1.76× overrun.** 34.43 h
remain of the window expiring 2026-10-24. See LESSONS.md.

#### Outcomes, paired within this session

| metric | v00 | v08 | delta | gained / lost | McNemar p |
|---|---|---|---|---|---|
| **timed out (30 min)** | **26/60** | **16/60** | **−0.167** | 6 / 16 | **0.0525** |
| **`gold_hit`** | 29/60 = 0.483 | **40/60 = 0.667** | **+0.183** | 15 / 4 | **0.0192** |
| `gold_exact` | 11/60 = 0.183 | 13/60 = 0.217 | +0.033 | 9 / 7 | 0.804 |
| `resolved` | 2/60 = 0.033 | 3/60 = 0.050 | +0.017 | 1 / 0 | 1.000 |

The pre-registered **primary endpoint moved in the predicted direction** and
`gold_hit` moved up substantially. **`resolved` moved by one task**, which is
nothing, and `stats.decide` returns **UNDERPOWERED** with an explicit
winner's-curse warning: at k=1 vs k=2 it detects only +0.055, so "confirm at
k≥2 before shipping".

#### The mechanism is confirmed, and precisely

The clamp bit exactly where it was designed to, and nowhere else. Per-step
completion tokens:

| | v00 | v08 |
|---|---|---|
| agent steps | 4,065 | **5,366** (+32%) |
| total completion tokens | 1,093,451 | **969,016** (−11%) |
| p50 | 38 | 37 |
| p90 | 614 | 581 |
| p99 | **4,132** | **1,308** |
| steps > 2048 | **114** | **11** (−90%) |
| steps > 4096 | **60** | **6** (−90%) |

**The agent got ~1,300 more productive steps out of less total decode**, because
the extreme tail collapsed while the median step was untouched (38 → 37). That is
the intervention working as specified rather than a general slowdown or
truncation. Completion tokens per step on completed tasks fell 239 → 181, and on
the verbose quartile 794 → 465 with seconds/step 72.4 → 37.2.

**T007 independently replicated** in this fresh session: corr(completion/step,
sec/step) = **+0.929** and **+0.932** in the two arms, with prompt/step again
*negative* (−0.44, −0.59). And the verbosity-buys-nothing pattern reappeared in
the v00 arm (gold_hit 10/15 terse → 4/15 verbose).

**`max_output_tokens` is the residual cap, as pre-registered.** Both arms still
show a max of 8,192, and v08 retains 6 steps above 4,096 — those are long in
*visible* output, which `thinking_budget` cannot touch. The MANIFEST called this
out in advance; it bounds how much more this knob can buy.

#### Four caveats, none of which the headline should be read without

1. **The cap favours v08, and this was pre-registered.** A 30-minute cap rewards
   the faster arm, and v08 is faster by construction, so **the timeout gain is
   partly true by design.** The `gold_hit` gain is less exposed to this, because
   it is a quality measure, but tasks that finish have more chance to localize —
   so the two endpoints are not independent.
2. **Multiplicity.** Four endpoints were tested. `gold_hit` at p=0.0192 would
   **not** survive a strict Bonferroni correction (α = 0.0125 for four tests),
   and the primary endpoint at p=0.0525 does not reach 0.05 uncorrected. The
   honest statement is "consistent, directionally strong, not yet decisive".
3. **The v00 baseline is unstable between sessions, and badly.** Identical v00
   bytes on the identical 60 tasks at the identical cap scored `gold_hit`
   **36/60 (P007)** and **29/60 (P008)** — a swing of **0.117**, which is most of
   the effect being claimed. The paired within-session design is exactly what
   cancels this, so the comparison stands; but **the magnitude should not be
   trusted**, and v08's 0.667 against P007's v00 0.600 would have been only
   +0.067.
4. **Resolution, the only metric that authorizes shipping, did not move.** 2/60
   to 3/60. Localization up with resolution flat is the same pattern the project
   has had since P005: the agent finds the right file and still fixes it wrongly.
   **The clamp buys completion and localization, and there is no evidence yet
   that it buys resolution.**

#### Verdict

**The mechanism is established and the bundle is not yet shippable.** This is the
first intervention in the project to move an outcome metric at all — P006's moved
a process metric and bought nothing, P007's moved nothing. But the ship rule keys
on `resolved`, `resolved` moved by one task, and the run is UNDERPOWERED for it.

Pre-registered next step, which the ship rule itself names: **spend the next
allocation on k, not on another bundle.** A second v08 arm against a second v00
arm in one session would take `resolved` to k=2 vs k=3 and test whether the
`gold_hit` gain replicates at all, which caveat 3 makes the open question.

### E015 RESULT — the control came back BLANK: the submission channel is broken for this account (2026-10-21)

**`v00_public_baseline`, byte-identical to the submission that scored 0.13 on
2026-09-30, returned `COMPLETE` with a blank `publicScore`.** Ref 57430290,
submitted 2026-10-20 08:46 UTC, terminal by 2026-10-21.

This was the pre-registered decisive outcome and it resolves T008's open
question. **Three consecutive blanks — v06, v07, and now bytes that have
previously scored — and the fault is not in any bundle.**

| sub | date | bundle | score |
|---|---|---|---|
| 56703353 | 2026-09-30 | v00_public_baseline | **0.13** |
| 56875884 | 2026-10-06 | v01_hygiene | 0.08 |
| 56910112 | 2026-10-07 | v04_lean | 0.10 |
| 57145400 | 2026-10-13 | v06_graph_coder | blank |
| 57390543 | 2026-10-19 | v07_verify_repair | blank |
| **57430290** | **2026-10-20** | **v00_public_baseline (CONTROL)** | **blank** |

**The grader is demonstrably healthy.** From the live leaderboard (2026-10-21),
counting teams by the date of their last *scored* submission: **641 teams scored
on 2026-10-20**, the day the control was submitted, and **87 on 2026-10-21**.
3,367 teams are now scored. Our own row registers `SubmissionCount: 6` with
`LastSubmissionDate 2026-10-20 08:46:01` — the control's exact timestamp — while
the displayed score is still **0.13**, i.e. v00's original from 2026-09-30.

So submissions are **accepted, registered, processed to `COMPLETE`, and not
scored**, specifically for this account, while thousands of others score normally.

#### What this retroactively invalidates

- **v06 and v07 were never evidence about those bundles.** E013-LB's reading —
  that v06's blank reflected a slow bundle — is **withdrawn**. P007's local
  rejection of v06 stands on its own rows and is unaffected; only the
  leaderboard inference is void.
- **Two submission slots and v07's entire test were spent on a dead channel.**
- **The project has had no working leaderboard signal since 2026-10-07.** The last
  scored submission is v04's 0.10; the last *informative* one is v00's 0.13.

#### What it does not change

Local measurement is untouched — it never used the leaderboard. P007, T007 and
P008 all stand. **This makes local measurement the only channel the project has**,
which raises rather than lowers the value of the remaining GPU window.

#### Required action, and it cannot be done from here

Escalation needs a browser. `kaggle forums topics list gemma-4-developer-agent`
returns **403**, and `kaggle forums list` shows only site-wide forums, so the
competition's discussion board is unreachable from the CLI. The competition
overview is JS-rendered and returns only a `<title>` to every tool available here.

**What to report, with the evidence already gathered:** three submissions
(57145400, 57390543, 57430290) reaching `COMPLETE` with no `publicScore`, the
last being bytes identical to 56703353 which scored 0.13; and 641 teams scored on
the same day the control was not.

**Until it is fixed, do not spend submission slots.** They are not free samples;
they return nothing. v08 in particular must not be submitted — it is the
best-motivated bundle the project has and a blank would waste it while telling us
nothing.

## T010 — the blanks are "Notebook Timeout", and the cause is dated (2026-10-21)

**CORRECTION TO E015 RESULT.** That entry concluded "the submission channel is
broken for this account" and recommended escalating to Kaggle support. **The
conclusion that the fault is not in any bundle stands. The mechanism was wrong,
and so was the recommended action.**

The Kaggle submissions **UI** shows all three failures as **`Notebook Timeout`**.
The CSV API reports only `SubmissionStatus.COMPLETE` with an empty `publicScore`,
which is why eight days of diagnosis never saw the real status. **The API hides
the failure reason the UI displays.**

So submissions are not being skipped or mis-scored. **They are running out of
time**, which is a specific, attributable and fixable cause — not an account
fault needing support.

### The cause is dated, and was measured locally before it was seen remotely

| | before | after |
|---|---|---|
| **wheelhouse republished 2026-10-12 19:51:31** | | |
| submissions | v00 **0.13** (09-30), v01 0.08 (10-06), v04 0.10 (10-07) | v06 (10-13), v07 (10-19), v00 CONTROL (10-20) — **all Notebook Timeout** |
| T005, identical v00 bytes | median task wall **25.9** min, 0/12 at the 60-min cap, summed **287.7** min | median **60.4**, 6/12 at the cap, summed **636.5** min |

**Every submission before the republication scored; every one after has timed
out.** T005 independently measured a **2.3× slowdown on identical bytes** across
exactly that boundary, five days before the first timeout was understood. The
wheelhouse arrives as `dataset_sources`, so no pin of ours holds it still and
this will not revert on its own.

The control remains the load-bearing evidence: the same bytes that scored 0.13
now time out, so no property of any bundle explains it.

### The fix was available all along and had never been tried

`HARNESS_README` §7.1: a submission may ship **`eval_config.yaml`** with
`evaluation.max_time_minutes`, default **60**. Our own `build.py` and
`validate.py` have supported it since the start — and **all nine prior bundles
set `ships_eval_config: false`.** The one lever aimed at the thing that is
failing had never been used.

### A trap found while building v09, worth more than the bundle

`build_bundle` **deletes `eval_config.yaml` unless `--ship-eval-config` is
passed** (`build.py:114`). Built without the flag, v09 packages to
`bundle_hash 6f3c38bf51665b01` — **v00's exact hash**. It would have shipped
plain v00, timed out again, and read as "the cap does not work" when the cap was
never shipped. Verified by building both ways and diffing the hash. **Always
confirm `eval_config.yaml` is inside `dist/submission.zip` before submitting.**

## E017 — v09_timecap submitted (2026-10-21, ref 57472801)

`bundle_hash 7b3fbfb99f0458db`, validator PASS, round-trip PASS, zip contents
verified to contain `eval_config.yaml` parsing to
`{'evaluation': {'max_time_minutes': 30}}`.

**v00 bytes plus one new file.** `diff -r` against v00 shows no differing file
and exactly one extra. Paired with a bundle of known score precisely so that the
eval_config is the only thing that could be new — the same discipline that made
the 2026-10-20 control decisive.

**Why 30:** pre-slowdown v00 ran at a 25.9-minute median with zero of 12 tasks
reaching the 60-minute cap, and *in that regime the grader finished and scored
us*. 30 restores that per-task envelope with margin. It is anchored to a figure
known to have worked, not derived — the grader's total runtime limit is
undocumented and its evaluation concurrency unknown, so 58 × 30 cannot be turned
into a bound.

**This submission is not trying to beat 0.13; it is trying to produce a score at
all.** Full pre-registered readings in the MANIFEST. In short: any score confirms
the hypothesis and restores the channel, after which v08 + the same cap should
score higher, since v08 cuts the long-decode tail that drives tasks into the cap.
A fourth timeout means per-task time is not the binding limit — escalate rather
than submit another variation.

### The validator's warning is now inverted, deliberately left alone

`max_time_minutes=30 throws away part of the 60-minute budget` fires on this
bundle. That warning assumes more time is always better. **Under a Notebook
Timeout the opposite holds: unused budget is what makes the run finish.** Left as
a warning rather than silenced, because it is right in general and wrong only
while the grader is slow.

## P009 — FAILED, zero rows: the weight load overran its own deadline (2026-10-21)

`swegemma-cap60-ab`, v00 vs v08 at the grader's 60-minute cap, 36 tasks, L4x4.
Status COMPLETE, **both arms `rc=1`, 0 of the expected 72 ledger rows.** Cost
~0.4 h wall; quota reads 11.70 h used / 33.30 h remaining at 14:40 UTC.

**Nothing about the clamp was measured. P008 remains the only clamp evidence.**

### Chain of causation, read off the log

1. `10:30:51` v00 arm starts vLLM, tp=4.
2. `Loading safetensors checkpoint shards: 1/1 [17:38<00:00]` — **the single
   shard took 1,059.16 s**, against **89.78 s** for the same file on 2026-10-01
   (`results/probe_final/swegemma-concurrency-probe.log:147`). An **11.8x**
   collapse in read throughput out of `/kaggle/input`, to ~16 MB/s.
3. Weight load (1,060 s) + dynamo transform (24 s) + profiling overran our
   **`startup_timeout=60 * 20`**, so `adk_submission` raised
   `ServerStartupError: Inference server did not become healthy within 1200s`
   and killed the engine.
4. `start_server` **retried**, because its only guard was `if not extra: raise`.
   The killed engine had not released its memory: the retry saw
   **15.1 of 22.03 GiB free** per GPU and died on `gpu_memory_utilization=0.9`.
5. The v08 arm then started on GPUs with **1.31 GiB free** and failed in 2.3 min
   across three further attempts.

Step 3 is the failure; steps 4–5 are why it cost the whole session instead of
one arm.

### Both defects were ours, and are fixed

`startup_timeout=60 * 20` was **our parameter, not an ADK constant** — the
handoff-era assumption that the 1200 s was imposed on us was wrong. Now
`_startup_timeout_s(spec)`, default **45 min**, overridable per runspec.

The retry is now `_should_retry_without_extra_args(extra, message, elapsed_s)`:
it fires only for a *fast* failure (<= 120 s) with extra args, since vLLM
rejects an unknown flag during argument parsing before opening a shard. A
readiness timeout is never retried — the GPUs still hold the dead engine.
Six tests; suite **245 passed**.

### The load collapse is under 19 hours old, so it is NOT the submission timeouts

Dated from the logs rather than inferred:

| when | event | cold startup |
|---|---|---|
| 2026-10-01 13:59 | concurrency probe | weights **89.78 s** |
| **2026-10-20 15:05** | **P008 arm 1 (cold)** | **5 min 29 s** start -> healthy |
| 2026-10-20 17:42 | P008 arm 2 (page cache warm) | 2 min 45 s |
| **2026-10-21 10:30** | **P009 arm 1** | **17 min 38 s on the shard alone**, never healthy |

**This retires the reading in the first draft of this entry.** The 2026-10-20
control submission (08:46 UTC) timed out, and that same afternoon the model
loaded cold in 5.5 minutes. A load tax that did not exist on 10-20 cannot
explain timeouts on 10-13, 10-19 and 10-20. **The wheelhouse-boundary account of
the submission timeouts stands, unweakened.**

What is new is a *separate, fresher* fault: `/kaggle/input` read throughput
collapsed ~11.8x at some point in the 19 hours between 2026-10-20 17:42 and
2026-10-21 10:30. Nothing we control pins it and it may well be transient.

The one place the two could meet is **v09 itself**, submitted 08:04 UTC today,
inside the window where the collapse was already possible. So if v09 times out,
that is now ambiguous between "per-task time is not the binding limit" and "the
grader paid a load tax today" -- and `max_time_minutes` is per-task agent
wall-clock (`HARNESS_README` line 540: `agent_elapsed_seconds`), which a one-off
model load sits outside. **A v09 timeout is therefore weaker evidence against
the cap than the MANIFEST's pre-registered reading assumes. Re-submit the same
bytes before escalating.**

## E018 — council verdict, five premises refuted, v10 built (2026-10-21)

Five-advisor LLM council on "is the current architecture worth improving".
Unanimous verdict: "the failure is verification, add a verify gate."
**The fact-check refuted the unanimity.** Full detail in `HANDOFF.md` §2.

Refuted, each against a live source:

1. **The verify gate is already shipped, twice.** `v00/prompts/system.md` steps
   3+5 mandate repro → `py_compile` → rerun → nearest pytest. `v01_hygiene`
   strengthened it (`:40` "Verify, every single time"; `:50` "Spend it on
   verification and repair") and **scored 0.08, the worst of three**.
   `bundles/v07_verify_repair/` is the structural version and was already
   submitted 10-19.
2. **"0/12 locally" was never evidence.** P(0 of 12 | the grader's own
   8/58 = 0.1379) = **0.169**. Four advisors' cases rested on a 1-in-6 draw.
3. **The drift floor does not explain local vs grader.** All 60 tasks in
   `clean_dev.txt` are a subset of `clean_n.txt`, the 102 that pass with the
   reference patch. Zero drift tasks were in the run.
4. **The GPU cliff was misframed.** Quota refreshes 45 h weekly; ~270 GPU-h
   across the 42 days.
5. **Multi-candidate self-select is impossible.** `candidate_count` is absent
   from `GENERATION_PARAM_FIELDS`
   (`reference/harness_facts/source/adk_submission__limits.py:227-239`), schema
   `extra="forbid"`.

### New measurement, 0 GPU-h, from 120 P008 traces

The agent **already verifies** after its last edit in 34/60 (v00) and 38/60
(v08). Among submitting tasks: verified 22 → 2 resolved (v00) and 27 → 3 (v08);
**not** verified 13 → 0 and 19 → 0. All 5 resolved came from verifiers; 0 of 32
non-verifiers resolved anything.

**Not a causal result.** This is a subgroup split on a variable the agent's own
competence moves — the same trap that once made v06 look better. Verifiers
localized far better *before* verifying (gold_hit 0.818 vs 0.385). The asymmetry
is real and large; the cause is not established.

Local vs grader, reconciled: restricted to tasks finishing inside the 30-min cap,
v00 resolved 1/31 = 3.2% (P(≤1 | 0.138) = 0.060), v08 2/42 = 4.8% (p = 0.058).
Suggestive of ~3x local understatement, not conclusive.

**Decode is the one untried knob class.** `temperature: 0.2 / top_p: 0.95 /
top_k: 40` is byte-identical in **all ten bundles**.

## E019 — v10_clamp_timecap built, not submitted (2026-10-21)

`bundle_hash 9033b8826a9add43` = `v08_decode_clamp` bytes + v09's
`eval_config.yaml` (`max_time_minutes: 30`). `diff -r` against v08 shows one
added file and only MANIFEST differing. Validator PASS (3 warnings, one of them
the deliberately inverted budget warning), zip round-trip PASS,
`eval_config.yaml` confirmed inside `dist/submission.zip`.

**Ships on the timeout mechanism, not a resolution gain.** v08's resolution
effect was 2/60 → 3/60, p = 1.000. Stated in the MANIFEST so no later reader can
mistake a score for confirmation that the clamp improves patch quality.

Not submitted: today's slot went to v09, and v10 waits on v09's branch — v09 is
the cap-without-clamp control, so without its score v10 is uninterpretable.

### The near-miss, caught by a dry-run

`ships_eval_config: true` was a **decorative MANIFEST field that no code read**.
A dry-run of v10 without `--ship-eval-config` packaged 5 files under
**26354b2d0153378d — v08's exact hash**, which on the leaderboard would read as
"the cap does not work" when no cap was shipped. The same near-miss had already
happened with v09 (E016) and the field was left unenforced. `build_bundle` now
**raises**; 3 new tests, 4 existing ones moved off the old unsafe contract.
Suite **252 passed, 2 skipped**.

## T011 — how the applying patches are wrong (2026-10-21, 0 GPU-h)

**Only 44 of 103 applied patches were ever graded.** On the other 59, pytest
aborted during collection — zero tests executed — so the recorded outcome could
not depend on the patch. That is the finding; the taxonomy of failure *shapes*
is secondary to it, because for three fifths of the corpus there is no failure
to classify.

Instrument: `scripts/analyze_patch_failures.py`, deterministic, CPU-only, over
P008's 120 ledger rows, 103 agent patches and 109 pytest logs plus the 129 gold
patches. Gold patches used strictly as an offline oracle; no gold text went
anywhere near a prompt, and the script prints none.

### The measurement blockage, which must be fixed before any other reading

| | clamp_v00 | clamp_v08 |
|---|---|---|
| applied patches | 46 / 60 | 57 / 60 |
| **collection aborted (no test ran)** | **26** | **33** |
| graded | 20 | 24 |
| resolution among graded | 2/20 | 3/24 |
| log carries the starlette mismatch | 34 / 46 | 41 / 57 |
| graded **and** env-clean | 8 | 10 |

The mismatch is one error: `TypeError: Router.__init__() got an unexpected
keyword argument 'on_startup'`, raised from `fastapi/routing.py` itself — the
installed starlette is newer than the fastapi snapshot, so **every module that
constructs `FastAPI()` explodes at import**. 75 of 103 logs carry it on a task
whose gold and test patches never mention the symbol.

It is not the agent's doing, by three independent checks:

1. It fires on tasks where the agent produced **no patch at all**
   (`fastapi_14246`, `fastapi_14099`, `fastapi_14978`).
2. The traceback is inside `fastapi/routing.py`, and in **71 of those 75 runs
   the agent never touched that file at all** (4 did, so the frame alone is not
   proof on its own — hence checks 1 and 3).
3. **8 patches reproduced the gold fix line for line and all 8 scored
   unresolved** — `fastapi_14492`, `14786`, `14791`, `14303` (v00), `14492`,
   `14786`, `14791`, `14430` (v08). Byte-equal change bodies to gold via
   `tasks.edit_bodies`. Every one has the mismatch in its log. `14492` and
   `14786` carry no extra file whatsoever: the agent's diff is the gold diff.

**This refutes E018's third refutation.** "Zero drift tasks in the run" was
inferred from `clean_dev.txt ⊂ clean_n.txt`; `clean_n` was calibrated in an
earlier environment and **the wheelhouse has republished since**. Set
membership was treated as a property of the environment when it is a property
of a past environment.

Local resolution among graded env-clean tasks is 5/18. **Do not read that as a
corrected rate**: a task that hits the mismatch can never resolve and the flag
is read from the same log that decides the outcome, so the subset is selected
toward resolvable tasks. It says the local metric understates. It does not say
by how much.

### The taxonomy

Buckets are assigned by one documented precedence order, so they partition the
corpus and answer "the most actionable thing wrong with this patch", not "how
often does mechanism X occur". Pooled, applied-and-failed, n = 98:

| bucket | hygiene-first | scratch discounted | graded + env-clean |
|---|---|---|---|
| `scratch_pollution` | **59** | — | — |
| `test_edit` | 0 | 0 | 0 |
| `no_source_edit` | — | 19 | 3 |
| `wrong_file` | 6 | 13 | 1 |
| `right_file_wrong_hunk` | 5 | 7 | 0 |
| `overreach` | 1 | 2 | 1 |
| `incomplete_fix` | 11 | 20 | 3 |
| `right_hunk_wrong_logic` (fallback) | 16 | **37** | **5** |

Three readings, in descending confidence:

- **`test_edit` is 0 of 103.** The prompt's prohibition on editing tests is
  obeyed perfectly. Not a hypothesis worth another bundle.
- **The modal reasoning failure is right-place-wrong-content**, 37 of 98 and 5
  of the 13 env-clean failures. `fastapi_14258` is the shape: the agent inserted
  a guard at gold's exact line 1393 and raised `FastAPIError` where the hidden
  test asserts an `AssertionError` with a specific message. Localization is
  largely solved — `right_file_wrong_hunk` is 7 of 98 — and content is not.
- **Scope is right and verbosity is not.** Median source files touched 1 against
  gold's 1; median patch 1,806 / 2,016 bytes against gold's 1,194 / 1,489.

### Scratch pollution: the rate replicates, the consequence does not

P001 saw 4 of 12 patches leak a scratch file. At n=103 the rate is **higher**:
62 of 103 applied patches (60%) carry one, 53 of them a literal root `repro.py`.

But P001's attached claim — "which alone breaks the grade" — is **false in this
harness**. **3 of the 5 resolved rows leaked a scratch file**, and
`fastapi_14873` resolved in *both* arms with a patch containing **nothing but
`repro.py`** (gold edits `fastapi/routing.py`; the agent edited no source at
all). A stray root file is wasted work and wasted tokens. It is not fatal.

That last case is also an audit finding: at least one `clean_dev` task passes
its hidden tests at the base commit, so 2 of the 5 local "resolved" rows are
free passes. Genuine local fixes are 1/60 (v00) and 2/60 (v08), not 2 and 3.

### What this does NOT support

- **Not** evidence for or against the model-ceiling hypothesis. The ceiling
  predicts exactly `right_hunk_wrong_logic` dominance, and so does an agent that
  cannot self-check — the shape is shared, and at n=13 env-clean failures
  nothing here discriminates them.
- **Not** a reason to ship a hygiene prompt rule for score. Scratch leakage is
  60% and non-fatal; the only measured cost is tokens.
- **Not** a per-mechanism frequency table. Precedence is not incidence: 59
  patches land in `scratch_pollution` and most of them *also* miss a gold hunk.
- **Not** a claim that 59 ungraded runs would have resolved. They would have been
  graded. Most would still have failed.
- **Not** transferable to the grader. Every environment number here is about the
  **local** subprocess harness on P008's wheelhouse. The grader's 8/58 is
  evidence its own environment works better; how much better is unmeasured.
- `right_hunk_wrong_logic` means the agent met gold's hunk *ranges*, which
  include diff context, so "the right neighbourhood", not "the right statement".
  The bucket is deliberately generous.

### Consequence

The next local run is worth less than its GPU cost until the environment is
fixed, because ~57% of its rows will be unreadable. Recommended before any
further measurement, in order: (1) re-derive `clean_n` **in the current
wheelhouse** on a CPU kernel — pin the starlette/fastapi pairing or drop the
ungradeable tasks; (2) re-run `analyze_patch_failures.py` on the P009 cap-60
rows once they land, to confirm the rate is environmental and not P008-specific;
(3) only then spend a paired GPU allocation on decode.

Suite after this work: **297 passed, 3 skipped** (the tree already carried
another session's `bundles/v11_greedy` and its tests; baseline for this change
was 259 passed, 3 skipped).

## P009 RESULT — the clamp eliminates timeouts at the grader's real cap (2026-10-21, read 2026-10-27)

`swegemma-cap60-ab` v2, after the startup fix in `17bacb5`. **36 rows per arm, 72
total, the full run** — the row count was checked before anything was analysed,
because v1 of this kernel returned 0 rows and still reported COMPLETE.

v00 (`6f3c38bf51665b01`) vs v08 (`26354b2d0153378d`), paired, one session,
`max_tool_calls=100`, concurrency 12, **60-minute cap — the grader's real cap**,
which is the whole point: P008's 30-minute cap favoured the faster arm by
construction and could not settle this.

| metric | v00 | v08 | gained / lost | McNemar exact |
|---|---|---|---|---|
| **timed out** | **11/36** | **0/36** | 0 / 11 | **p = 0.00098** |
| `gold_hit` | 18/36 | 24/36 | +11 / −5 | p = 0.210 |
| `gold_exact` | 6/36 | 4/36 | +2 / −4 | p = 0.688 |
| `resolved` | 1/36 | 1/36 | **+0 / −0** | p = 1.000 |

Wall clock: median **37.7 → 28.7** min, summed **1,405 → 1,075** min (**−23%**).

### What this establishes

**The clamp's effect on timeouts is real, large, and survives the honest cap.**
Every one of the 11 cap-hitters converted and none was lost. p = 0.00098 is the
strongest result this project has produced, and it is **immune to the
environment fault below**, because wall clock and cap-hitting are measured from
the run itself and never touch `pytest`.

This answers the question P008 left open and answers it in the clamp's favour.
It also retires the worry that the 30-minute cap was doing all the work: at 60
minutes, where the cap no longer favours v08, the effect is *larger* (11→0 here
versus 26→16 there).

### What this does NOT establish, and the part that bites

**`gold_hit` did not replicate as significant.** P008 read 29→40 at p=0.0192;
here it is 18→24 at **p=0.210**. Same direction, no significance at n=36. The
handoff's open question — "does the `gold_hit` gain replicate at all?" — resolves
to **direction yes, significance no.** Do not quote P008's p-value as if it
stood up.

**`gold_exact` moved the wrong way** (6→4, p=0.688). Non-significant, but it is
the reading pre-registered as able to falsify the knob, so it is recorded.

**`resolved` carried zero information.** 1/36 in both arms with **zero discordant
pairs** — a paired test with no discordance has no power at any n. The n-aware
detectable delta here is **0.121** (≈4.3 of 36 tasks) against a 0.05 design
target, so this was **UNDERPOWERED** on resolution before it started.

### The environment fault is confirmed outside P008

T011 asked whether the starlette/fastapi mismatch was P008-specific. It is not:
**26 of 34** `cap60_v00` test logs carry
`TypeError: Router.__init__() got an unexpected keyword argument 'on_startup'`
— **76%**. That is the mechanical reason `resolved` is 1/36 with zero
discordance: three quarters of these tasks cannot be graded at all, whatever the
patch says.

So the two metrics that survived this run are precisely the two that need no test
execution — timeouts and `gold_hit`. That is not a coincidence, and it is the
original argument for adopting a localization co-primary.

### Decision taken

**v10_clamp_timecap submitted 2026-10-27 (ref 57693514)** = the clamp plus the
30-minute cap. v09 (4096 + the same cap) was the fourth blank, and v09 carried
the **slow** arm: P009 shows that arm hits the cap on 11 of 36 tasks and burns
23% more total wall clock. The cap alone was never the untested half — the clamp
was. This deviates from the plan's "escalate, do not submit a fifth variation"
branch, which was written before this result; the deviation was put to the user
and taken deliberately, and the escalation proceeds in parallel since it costs
no submission slot.

## PAPER — trimmed under the cap and fact-checked (2026-10-27, 0 GPU-h)

The manuscript was **3,265 body words against an official 3,000 cap**. It is now
**2,922** prose words (2,981 on a naive whitespace split of the markdown, 2,946 as
rendered) — under the cap on every basis we could construct, since the rubric
says only "3,000 words maximum" and does not define the count. Counts are
reproducible: the per-section counter is in the scratchpad and the three figures
are recorded in `paper/MANUSCRIPT.md`'s header.

Trimming was done in five passes with exact-match, asserted replacements, §D as
the designated donor (1,010 → 946) and §§F/G/H protected as the sections the
rubric pays most. Three cross-section duplications were removed rather than
polished away: the third-party score triple (its caveat survives in §G), the
"floor moved underneath us" finding (told at full length in three sections, now
in §G with cross-references), and §E's D4 bullet (said in §D4, §G and §E's own
payoff sentence).

**The accuracy audit mattered more than the trim.** Every quantitative claim was
checked against primary sources — ledger rows, `stats.py`, bundle MANIFESTs,
committed leaderboard snapshots — and recomputed where possible. Ten corrections,
each verified before it was applied:

| # | claim as drafted | correct | source |
|---|---|---|---|
| 1 | "3,199 teams hold a positive score" (§B, §D0) | **3,043**; 156 teams sit at 0.00 | `public_lb_2026-10-19.json` |
| 2 | the pre-registered falsifier "fired" (§E) | it did **not** — registered on `gold_hit`, which **rose** 18→24 | `v08_decode_clamp/MANIFEST.yaml` |
| 3 | McNemar p = 0.3125 (§D3) | **0.625**; 0.3125 is the one-sided tail | `mcnemar_exact(3,1)` |
| 4 | 76% mismatch "that run's" (§E, §G) | 76% is P009; the byte-identical pair is P008 at **73%** | T011, P009 |
| 5 | SE ≈0.030 "measured on the full 129-task set" (§D4) | never run at 129 (max 60); rescaled 1/√n from a 12-task replication, SD 0.118 | every `runspec.json` |
| 6 | "four of the six cost no GPU time" | **five**; only D2 needs an accelerator | §H already said five |
| 7 | resolution "sits near p ≈ 0.15" (§C, §D2) | that is the **grader's** rate; local is 1/36–3/60 | all ledger runs |
| 8 | headline comparison repo mix undisclosed (§F) | `clean_dev36.txt` is **36/36 fastapi** | `tasks.jsonl` |
| 9 | "every figure is re-derivable" (§H) | `clamp_*`/`cap60_*` carry **no** `patches/` or test logs | `ledger/runs/` |
| 10 | four smaller: v01's "eleven prompt edits"; v04 "exactly between"; §G's ~0.24; §D1's "bought nothing" | not all prompt edits; 6 vs 8 and 5; **0.209**; the second identical run *is* the one that produced the diagnosis | E002, E004, `detectable_delta`, C003 |

Two of these are recorded in `LESSONS.md` as mistakes rather than edits: #2 and
#1. #2 is the serious one — a measurement-discipline paper misreporting its own
pre-registration, written in the very section that describes pre-registration.

The one-sided 0.3125 was **repo-wide**, not just in the paper: 7 occurrences
across `LESSONS.md` (1), `paper/OUTLINE.md` (3), `src/swegemma_lab/stats.py` (1)
and `tests/test_stats.py` (2). All corrected to 0.625 in the same pass, with the
provenance recorded at the canonical source, so the repo and the paper now agree.
None was an assertion, and the suite is unchanged at **302 passed, 3 skipped**.

### The word count is now re-derivable (2026-10-27, 0 GPU-h)

The count that gates submission was being produced by hand and got it wrong
twice, in a paper whose §H claims every figure in it is re-derivable. So it is
now a committed instrument rather than a scratch calculation:
`scripts/export_paper.py` strips the drafting header, reports the three counting
bases, writes `paper/SUBMISSION.md` (the exact text to paste into the Writeup,
with the title field in a leading comment), and `--check` exits non-zero if any
basis is over the cap.

| basis | body | margin |
|---|---|---|
| prose (alphanumeric tokens) | 2,922 | +78 |
| naive whitespace split of the markdown | 2,981 | +19 |
| as rendered, no table pipes or heading marks | 2,947 | +53 |

`tests/test_export_paper.py` adds 12 tests, and three of them are the point
rather than coverage:

- **the live manuscript is under the cap on every basis** — the compliance claim
  is asserted, not remembered;
- **`prose <= rendered <= naive`** — if that ever inverts, the pessimistic basis
  is no longer pessimistic and "under the cap on every basis" means nothing;
- **the paper cites one suite size consistently** — §D3 and §H both quote it, and
  the realistic failure is updating one and not the other, which leaves the paper
  contradicting itself in front of a Verifiability grader.

`split_header` raises rather than guessing where the body starts: a silent guess
would submit the drafting header, which contains the word budget and the whole
audit trail.

**Two numbers in the body track the repo and will go stale again:** the suite
size and the three word counts. Both are now checked, and the manuscript header
says to re-run before submitting. Writing these tests moved the suite 302 → 314,
which immediately invalidated the paper's "302 passing tests" in two places — a
small live demonstration of the drift the paper is about. Now 314 everywhere.

Also corrected this session: `paper/OUTLINE.md`'s "1,012 of 2643 teams — 38%"
band, whose own components sum to **1,026** (353 + 340 + 333) on the 2026-10-13
snapshot, and whose 2,643 is the *scored* field — 150 sit at 0.00, so positive
scorers are 2,493. The manuscript supersedes that paragraph anyway, reporting the
2026-10-19 board at 1,094 of 3,199 = 34%.

Suite: **314 passed, 3 skipped.**
