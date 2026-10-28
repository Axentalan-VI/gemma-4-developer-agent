# Lessons — Gemma 4 Developer Agent

Mistakes are fine; repeating them is the waste. Read this before similar tasks.

## 2026-10-01: Diagnosed a failure from exit codes instead of reading the output

- **What happened:** The first calibration run resolved only 74/129 gold patches.
  I inferred the cause from pytest exit codes and per-repo failure rates, built a
  confident story around `install_test_dependencies` being a no-op in subprocess
  mode, and shipped a fix. The fix changed **nothing** — run 3 was bit-for-bit
  identical, 129/129 same verdicts. The real cause was two absent test-only
  packages.
- **Why it happened:** `calibrate.py` recorded only `resolved`, `test_exit_code`
  and `error`, and **discarded `res.test_output`**. With no pytest output I could
  only guess, and the guess was plausible enough to act on. The moment I captured
  `test_output_tail`, the answer was one grep away: `ModuleNotFoundError: No
  module named 'inline_snapshot'`.
- **Time lost:** ~1.5 h and two Kaggle runs.
- **Next time:** **Capture the raw tool/test output on the first run, always.**
  When a verification step fails, the diagnostic is the output, not the status
  code. A plausible theory built on aggregates is not a diagnosis — if I cannot
  quote the error text, I have not found the cause.

## 2026-10-01: Used `--no-deps` on a dependency set that was not closed

- **What happened:** Staging installed repo test dependencies with
  `pip install --no-deps`, reasoning that the resolved wheel set was already the
  full closure. It was not. `pydantic` went in without a matching
  `pydantic-core`, leaving 2.41.4 against a pydantic requiring 2.46.4, and every
  `swegemma` import died with `SystemError`. I broke the harness while trying to
  fix the environment.
- **Why it happened:** I conflated "the packages the repos declare" with "the
  transitive closure of those packages". Only the former was resolvable from
  `/wheels`.
- **Time lost:** ~20 min (caught at the preflight gate, not in a full run).
- **Next time:** `--no-deps` is only safe for a set someone has already proven
  closed. When touching a shared environment, **pin what the tooling itself needs
  via a pip constraints file, then verify the tooling still imports** before
  doing anything else.

## 2026-10-01: Asserted a performance number I had not checked

- **What happened:** I added `--enable-prefix-caching` to the vLLM args and
  claimed it was worth "roughly 2 GPU-hours per run, ~50 GPU-h across the
  project" — a fifth of total quota. That figure appeared in the plan and in
  commit messages. On checking the wheelhouse, it ships **vLLM 0.19.1**, where
  the V1 engine enables prefix caching **by default**. The saving was already
  there; the flag bought nothing, and had it been retired it would have failed
  server startup and cost quota.
- **Why it happened:** I reasoned from how prefix caching works rather than
  checking what this build does. It was stated as fact, not as a hypothesis.
- **Time lost:** little directly, but it inflated the GPU budget justification in
  `PLAN.md`.
- **Next time:** Any claimed speedup is a **hypothesis until measured**. Check the
  installed version before asserting a flag's effect, and prefer a fallback
  (retry without the flag) over trusting that an option exists.

## 2026-10-01: Flattened paths and silently lost a third of the files

- **What happened:** The harness-recon script saved sources as
  `f"{pkg}__{path.name}"`. `google.adk` has dozens of `__init__.py` and
  `base_agent.py` under different subpackages, so **129 of 642 files silently
  overwrote each other**. It then cost a kernel run: I looked for `SessionTrace`,
  found it in the flattened `adk_eval_core__trace.py`, and wrote
  `from adk_eval_core.trace import ...` — but the real module is
  `adk_eval_core.tracing`, and the subpackage had been flattened away.
- **Why it happened:** No check that files-written matched files-found, and
  flattening destroys the very information (the import path) the archive existed
  to preserve.
- **Time lost:** ~30 min and one kernel run.
- **Next time:** When collecting files into a flat namespace, **encode the full
  relative path** and **assert the output count matches the input count**. A
  silent-loss bug is worse than a crash.

## Cross-cutting rules earned this week

1. **Gates pay for themselves immediately.** The calibration gate, the preflight
   import check and the harness integrity probe each caught a bad state for
   ~2 min of CPU. Without them a confidently wrong measurement regime would have
   consumed weeks of GPU quota. Build the gate before the thing it guards.
2. **A measurement instrument must be calibrated before it is trusted.** Feeding
   known-correct answers (gold patches) and known-empty answers through the
   scoring path is cheap and exposes exactly the problems that would otherwise
   look like model results.
3. **Prefer the metric that needs least machinery.** Gold-file localization needs
   no test execution and is therefore immune to the entire dependency problem
   that cost this week. I should have reached for it sooner.
4. **Read the source, not the docs.** `HARNESS_README.md` was wrong in three
   places, two of them 0.00-scoring. One CPU kernel reading 642 harness files
   settled more open questions than any amount of black-box probing would have.

## 2026-10-01: Resolved a Kaggle model mount one directory too high

- **What happened:** The first GPU run died ~90 s in. vLLM:
  `Invalid repository ID or local directory specified:
  '/kaggle/input/models/google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct'`.
  My notebook located the model by matching the instance name, but Kaggle mounts
  models at `<owner>/<model>/<framework>/<instance>/<version>` — the weights are
  one level deeper, in the numeric version directory. The matched path had no
  `config.json`.
- **Why it happened:** I matched on a *name* when the thing I actually needed was
  a *property* ("the directory containing `config.json`"). The official starter
  notebook hardcodes `.../2`, and I generalized the wrong half of it: I removed
  the hardcoded version without replacing it with a real test.
- **Time lost:** ~20 min and one GPU run (small, because Stage A is 4 tasks).
- **Next time:** **Locate a resource by a property that proves it is the right
  one**, not by a name that merely looks right. For a model directory that means
  anchoring on `config.json` or `*.safetensors`, and asserting it before use.
  Cheap assertions next to the discovery would have failed in the notebook's
  third cell instead of after GPU allocation.

## 2026-10-01: Kaggle accelerator type cannot be set from kernel-metadata.json

- **What happened:** The probe requested `enable_gpu: true` and was given
  **2 x Tesla T4 (15 GB) with 4 CPUs**, not the 4 x L4 (96 GB) the competition
  harness targets. The notebook's gate flagged it, but only after allocation.
- **Why it happened:** `enable_gpu` is a boolean. There is no field for GPU type,
  so a CLI push cannot express "L4 x4"; it has to be set once in the browser,
  after which it persists across later pushes.
- **Time lost:** none directly — the model-path bug killed the run first — but it
  would have been the next failure.
- **What to do next time:** For any GPU kernel, **set the accelerator in the
  browser once and verify it in the run's own output** before trusting a number
  from it. Print `nvidia-smi` as the first cell. Note that T4 is Turing (7.5)
  while W4A16 compressed-tensors needs Ampere (8.0+), so T4 is an architecture
  mismatch for this model, not merely a smaller card.

## 2026-10-01: Kaggle CLI log download fails on Windows encoding

- **What happened:** `kaggle kernels output` wrote a 0-byte log and errored with
  `'charmap' codec can't encode character '\u2588'` — vLLM's progress-bar blocks
  hitting the Windows default code page. The run looked like it had produced
  nothing.
- **Fix:** `PYTHONUTF8=1 PYTHONIOENCODING=utf-8` before the CLI call. Use
  `--force` to re-download once a truncated copy exists locally.
- **Time lost:** ~10 min of misreading an empty log as an empty run.
- **Next time:** Always export `PYTHONUTF8=1` when pulling Kaggle logs on
  Windows. A 0-byte log is an encoding failure, not an empty run.

## 2026-10-01: Claimed a fix was deployed when it was only committed

- **What happened:** I fixed the model-path bug in the probe notebook, copied it
  into `kernels/`, validated the JSON, and committed it — then told the user the
  fix was "pushed and ready". It was not: I never ran `kaggle kernels push`. The
  user re-ran the notebook, it finished, and the output was **byte-identical** to
  the previous failed run (same SHA, still the old code path).
- **Why it happened:** I treated `git commit` as the deploy step. For Kaggle
  there are three distinct publish actions — `git commit`, `kaggle datasets
  version` (lab code) and `kaggle kernels push` (notebook) — and committing
  none of the latter two changes what actually runs. I also stated the
  deployment as fact instead of verifying it.
- **Time lost:** one wasted user-initiated run, plus the confusion of a
  "finished" run that silently executed stale code.
- **Next time:** **Deploy, then verify the deployment, then report.** After any
  push, confirm the remote actually changed — a new version number in the push
  output, or a marker string from the new code appearing in the next run's log.
  Identical output size or hash across runs means nothing re-ran. Never describe
  something as pushed without having run the push in that same turn.

## 2026-10-01: Planned the GPU budget against the wrong quota

- **What happened:** The whole GPU budget in `PLAN.md` was built on
  **30 GPU-h/week**, taken from Kaggle's general documentation. `kaggle quota`
  reports this account actually has **45 GPU-h/week** (plus 20 TPU-h). Every
  per-experiment cost/benefit I computed was against a budget 33% too small.
- **Why it happened:** I took a platform-wide figure from a web search as an
  account fact, when a first-party command reports the real number. The same
  mistake shape as the prefix-caching claim: asserting from general knowledge
  instead of checking the specific system.
- **Time lost:** none directly, but it made the plan more conservative than
  necessary and could have cut real experiments.
- **Next time:** **`kaggle quota` before planning any GPU budget**, and re-check
  it when reporting usage. More generally: when a number governs a plan, find
  the command that reports it rather than the doc that describes it.

## 2026-10-01: Kaggle CLI 2.2.4 adds commands worth knowing

- `kaggle quota` — used/remaining/refresh for GPU and TPU. The only reliable
  source for the weekly budget.
- `kaggle kernels logs <kernel>` — exists, but returned nothing for a *running*
  kernel, and it takes no `-p` flag.
- **There is still no `kernels cancel`.** A runaway kernel cannot be stopped from
  the CLI; it runs to completion or to the session cap. So cap per-task budgets
  *inside* the notebook, because that is the only brake available.
- `kernels output` returns nothing while a kernel is running, so progress is not
  observable mid-run. Print timestamps and stage markers early if you want to
  reconstruct where a run got to.

## 2026-10-05: A failed GPU kernel idled out the full 12-hour session cap

- **What happened:** The L4 probe failed at vLLM startup after ~6 minutes, then
  **held the session for the full 720 minutes** before being cancelled. Roughly
  12 of 45 weekly GPU-hours spent on nothing. The notebook used
  `subprocess.call(...)` with no timeout and no check of the return code, so
  after the failure it simply ran on.
- **Why it happened:** Two gaps compounding. `subprocess.call` returns a code
  rather than raising, so a failed stage looked like a completed one; and there
  is **no `kaggle kernels cancel`**, so nothing outside the notebook could stop
  it. I had treated the per-task budget caps as sufficient, but they only bound
  the agent loop — not startup, and not the notebook itself.
- **Time lost:** ~12 GPU-hours, and four days before anyone looked.
- **Next time:** **Every GPU stage gets `subprocess.run(timeout=...)` and a hard
  `assert rc == 0`.** An in-notebook timeout is the only brake that exists. Also
  print a stage marker with a timestamp before and after each stage, because
  `kernels output` returns nothing while a kernel runs and the only way to
  reconstruct where it got to is the log it already wrote.

## 2026-10-05: vLLM OOMs at startup on 4xL4 with the default max_num_seqs

- **What happened:** `RuntimeError: CUDA out of memory occurred when warming up
  sampler with 256 dummy requests.` The model loaded fine across 4 x L4 (23 GB
  each), the KV cache allocated at 55,616 tokens, CUDA graph capture began — and
  then the sampler warm-up died.
- **Why it happened:** vLLM sizes its sampler warm-up from `max_num_seqs`, which
  defaults to 256. The engine's own log said the real ceiling was **10.49x
  concurrency at 32k context**, so 256 concurrent sequences were never
  reachable; the default simply does not fit a 31B W4A16 model on this hardware.
- **Fix:** pass `--max-num-seqs 32` via `VllmConfig.extra_args` (there is no
  field for it). Kept out of the optional-flag fallback, because unlike
  `--enable-prefix-caching` this one is *required* for startup to succeed.
- **Next time:** read the engine's own capacity line (`Maximum concurrency for
  N tokens per request`) and set `max_num_seqs` near it. When a library suggests
  two knobs in an error message, the one matching its own reported ceiling is
  usually the right one.

## 2026-10-05: Self-inflicted queue jam - Kaggle allows only 2 batch GPU sessions

- **What happened:** The notebook sat in the queue for hours and never started,
  with nothing of the user's visibly running. Pushing a different accelerator
  revealed the real error: **`Maximum batch GPU session count of 2 reached.`**
  Every `kernels push` queues a batch GPU session, and I had pushed probe v5,
  v6, v7 and smoke v1, v2 — filling both slots with queued sessions that then
  blocked each other *and* every later push.
- **Why it happened:** I treated `kernels push` as "update the code" when it is
  really "update the code **and enqueue a GPU session**". With a 2-session cap
  and no `kernels cancel`, repeated pushes are self-blocking: each retry made
  the jam worse rather than retrying anything. I also mis-diagnosed it twice, as
  Kaggle refusing the allocation and then as global L4 scarcity, because
  `status QUEUED` looks identical in all three cases.
- **Time lost:** most of a day, plus 2.12 GPU-h on a run whose log was discarded.
- **Next time:**
  - **Never push twice without a terminal state in between.** One queued session
    is the budget; two is the hard cap.
  - The cap error is only visible on a *refused* push — a queued session gives no
    warning. So if a run stays QUEUED with nothing else of yours running,
    **suspect the session cap first**, and clear sessions in the browser (there
    is no CLI cancel).
  - Fix code locally, run the test suite, and push **once**.

## 2026-10-05: A terminal kernel status does not mean the GPU session was released

- **What happened:** I checked all four kernels, saw `ERROR` /
  `CANCEL_ACKNOWLEDGED` / `COMPLETE`, and told the user nothing was holding a
  GPU slot. A push minutes later was refused with
  `Maximum batch GPU session count of 2 reached` — with only one of my pushes
  queued, so a second slot was held by something no status call reported.
- **Why it happened:** I treated `kernels status` as a session-occupancy check.
  It reports the *last run's outcome*, not whether a batch session is still
  allocated. A cancelled run can leave its slot held, and nothing in the CLI
  lists sessions.
- **Consequence:** two wrong statements to the user in consecutive turns, and a
  refused push.
- **Next time:** **the only reliable occupancy test is attempting a push** —
  success means a slot was free, refusal names the cap. Do not infer occupancy
  from status. And since there is no CLI cancel, clearing stuck sessions is
  always a browser action by the user.

## 2026-10-05: The wheelhouse is Python-3.12-only, and the accelerator picks the image

- **What happened:** The T4 smoke run completed and failed with
  `ImportError: vllm/_C.abi3.so: undefined symbol: _ZN3c1013MessageLoggerC1EPKciib`
  — a PyTorch `c10` symbol, i.e. vLLM's compiled extension linked against a
  different libtorch. The real cause was upstream: **the T4 image runs Python
  3.13 while the competition wheelhouse is built for cp312.** Nine compiled
  wheels were rejected outright; vLLM's abi3 extension loaded anyway and then
  could not resolve its torch symbols.
- **How it was found:** comparing the `/usr/local/lib/python3.XX/` paths in the
  two runs' own logs — the L4 run is 3.12 throughout, the T4 run is 3.13.
- **Consequence:** **T4 is not a fallback for this competition.** Not because of
  compute capability (we never got far enough to test Turing vs Ampere), but
  because the accelerator choice silently changes the Python version of the
  image, and the wheelhouse only matches one of them. L4 x4 is required.
- **Next time:** **compare `sys.version_info` to the wheel tags before
  installing.** A 10-second check replaces a 9.5-minute run. Added as a cell in
  03 that asserts with the explanation. More generally: when a prebuilt
  dependency set exists, the environment that set was built for is a hard
  constraint, not a preference — check it first.

## 2026-10-06: Backslashes and newlines die in a heredoc-piped patch script

- **What happened:** patching files with `python - <<'PY' ... PY` mangled escape
  sequences twice in one session. `\n` inside a Python string literal landed in
  the file as a real newline, producing an unterminated f-string; `kernels\00_`
  became `kernels` + NUL + `0_`, so the match silently failed. This is the same
  class of failure as the three notebook `SyntaxError`s already recorded above —
  the fourth occurrence.
- **Why it happened (root cause):** a patch script that contains escape
  sequences has *two* layers of escaping, the shell's and Python's, and reasoning
  about both at once is unreliable. Separately: the assert-then-write pattern
  means one failed match discards every other edit in the script, so a third of
  the work vanished without an error pointing at it.
- **Time lost:** ~15 min.
- **What to do next time:** **never put a backslash or `\n` in a heredoc-piped
  patch script.** Use the `Edit` tool for anything containing an escape, or write
  the script to a file first. If a patch script must do several edits, apply and
  write each one independently so one bad match cannot roll back the rest. Also:
  normalize CRLF before matching — `README.md` was CRLF while `PROGRESS.md` was
  LF, and the same pattern matched one and not the other.

## 2026-10-06: max_output_tokens is a reservation, and it loses whole tasks

- **What happened:** the first run in this project to actually serve a request
  (`probe_c12`, L4x4, grader config) failed two tasks with
  `ContextWindowExceededError: maximum context length is 32768 tokens. However,
  you requested 8192 output tokens and your prompt contains at least 24577 input
  tokens, for a total of at least 32769`. Over by **one token**.
- **Why it happened (root cause):** `max_output_tokens` is not a cap on what the
  model writes, it is a **reservation litellm sends on every request**, and vLLM
  refuses the call when `input + reservation > max_model_len`. So the real input
  ceiling is `32768 - max_output_tokens`: 24,576 for v00, and only 20,480 for
  v01, which *raised* the reservation to 12,288. Worse, the retry plugin
  classifies this as **non-retryable**, so the task is lost outright rather than
  degraded. Both failures were inside `agent_tool.py` — the **analyzer**
  sub-agent, which holds the three flood-prone tools and emits a fixed ~250-word
  report, so its large reservation bought nothing at all.
- **Also learned:** compaction does not bound this. The threshold is 14,336
  tokens and the prompt still reached 24,577, so either compaction does not
  apply to a nested AgentTool runner or it fires too late to help.
- **Time lost:** ~47 GPU-minutes, and the run was cancelled before producing the
  prompt-size distribution that would let the ceiling be set from data.
- **What to do next time:** **set every output budget to the smallest the
  agent's job needs, and derive the input ceiling before shipping.** Now
  enforced offline in `validate.py`: an input ceiling at or below the compaction
  threshold is an error, and one below the largest prompt ever observed
  (`OBSERVED_PROMPT_PEAK`) is a warning. v00 raises two warnings, v01 one, v02
  none. More generally: when a knob sounds like a limit, check whether the
  client sends it as a request — a reservation and a cap behave oppositely under
  pressure.

## 2026-10-06: A cancelled Kaggle kernel destroys everything but the log

- **What happened:** `probe_c12` served requests, ran the agent loop and hit
  real failures. It was then cancelled, and `kernels output` returned **nothing**
  — no ledger, no patches, no results. The only surviving record was log text
  pasted out of the browser, which is how the finding above was recovered at all.
- **Why it happened (root cause):** two compounding mistakes. Kaggle discards
  `/kaggle/working` for a cancelled kernel, *and* `session_runner.py` wrote the
  ledger only after the chunk loop finished, so there was nothing on disk to
  save even in principle.
- **Time lost:** the analysis survived; the measurement did not.
- **What to do next time:** **treat stdout as the durable store, because it is
  the only thing that survives.** Every ledger row is now echoed behind
  `LEDGER_ROW ` and the ledger is flushed after every chunk plus in a `finally`,
  so a hard kill costs at most one chunk. `scripts/recover_from_log.py` rebuilds
  a ledger from pasted log text and extracts failure signatures even when no row
  was written — a run that produces no data can still produce a diagnosis.

## 2026-10-06: A default argument inverted a result and nearly killed a work item

- **What happened:** `probe_c12` printed *"BUDGET IS SLACK: median 29 of 100
  calls used, only 0% exhausted. More budget cannot help."* The run had been
  configured with `max_tool_calls: 30`. The real reading is median 29 of 30 —
  **97% of the budget it was given** — i.e. the opposite conclusion. I was one
  step from retiring the budget-ceiling experiment (E007/E008) on the strength
  of it.
- **Why it happened (root cause):** `build_panel` and `budget_verdict` both
  default `call_ceiling=100`, and `session_runner` called them without passing
  the ceiling the run actually used. So `exhausted_calls` counted tasks at
  >= 100 (none, by construction) and the verdict's `med < ceiling * 0.4` test
  compared 29 against 40 instead of against 12.
- **What should have caught it:** the panel's own error taxonomy printed
  `1 budget_exhausted` three lines above `0% exhausted`. The output contradicted
  itself and I read the summary rather than the detail.
- **Time lost:** none directly; the cost would have been a wrong decision.
- **What to do next time:** **a function that interprets a run must be given the
  run's own parameters, never a default.** `budget_verdict` now refuses to
  return a verdict at all when the ceiling is not the grader's 100, because an
  agent truncated at 30 calls and an agent satisfied at 30 calls are
  indistinguishable from the outside. More generally: when two numbers in one
  report disagree, the aggregate is the one that is wrong — and a default
  argument is the first place to look.

## 2026-10-06: `kernels output` returns the last *committed* version, not the live session

- **What happened:** `probe_c12` finished (rc=0, 12 tasks) and wrote
  `probe_ledger.zip` and `probe_results.zip` to `/kaggle/working`. Pulling with
  `kaggle kernels output` returned a **212-byte zip holding two empty directory
  entries dated 2026-10-01** — five days stale — plus a 0-byte log, and no
  `probe_ledger.zip` at all.
- **Why it happened (root cause):** the run was an **interactive** session.
  `/kaggle/working` is only published when a version is saved, so the CLI served
  the last committed version while the finished run's files sat in the browser.
  `lastRunTime` did update to today, which makes the staleness easy to miss:
  the kernel genuinely ran today, but its *output* is from Oct 1.
- **How to tell the difference:** read the zip's **entry timestamps**, not the
  download's. A zip of only directory entries is the signature.
- **Time lost:** ~10 min, and briefly concluding the data was destroyed when it
  was not.
- **What to do next time:** for an interactive session, download from the
  session's **Output panel** in the browser, or print the data to stdout and
  copy it — `scripts/recover_from_log.py` exists for exactly that, and
  `scripts/ingest_probe.py` files hand-downloaded zips and refuses to overwrite
  an existing ledger run. Also: an interactive session **consumes quota and
  persists nothing**, which explains the earlier unexplained 2.48 -> 2.96 h
  jump with no kernel `lastRunTime` change.

## 2026-10-06: A regex over the wrong field undercounted 491 tool calls as 2

- **What happened:** `scripts/analyze_traces.py` matched tool names with a regex
  over `step["message"]` and reported **2 tool calls across 12 traces**, while
  the ledger recorded 28-30 per task. It exited 0 and printed a clean table.
- **Why it happened (root cause):** the schema was assumed, not read. An agent
  step that carries tool calls has **no `message` key at all** — the call is a
  structured `tool_calls` list and the result is in `observation`. Only system,
  user and final-answer steps have `message`. So the regex matched prose and
  nothing else. `steps_of` was even annotated `-> list[dict]` while returning a
  tuple, which is the tell that the file was never genuinely exercised.
- **Why it was nearly invisible:** an empty tool column reads exactly like an
  agent that never called a tool — one of the hypotheses the script exists to
  test. A wrong answer in the shape of a plausible answer, not an error.
- **Time lost:** ~20 min, but the near-miss was far more expensive: the finding
  it was hiding (a sub-agent eating 53% of the call budget) refutes the premise
  of a ~1.6 GPU-h run that was already set up and about to be launched.
- **What to do next time:** **dump one real record's key set before writing any
  parser.** `Counter((s["source"], tuple(sorted(s.keys()))) for s in steps)` took
  one command and would have shown the two different step shapes immediately.
  Then build the test fixtures from the real schema, not from the parser's
  assumptions. Corollary, which caught two further bugs here: **verify a new
  report against data whose answer you already know from another source.** The
  scratch-leak column read 0 against traces known to have leaked a file in 4 of
  12 tasks, because the argument key is `filepath`, not `path`.
- **Also:** use `python -X utf8`, not `PYTHONUTF8=1`, when the command may carry
  `-I` — `-I` implies `-E` and discards the environment variable. Traces contain
  emoji from issue text and cp1252 dies on them.

## 2026-10-06: Five of twelve probe verdicts were environment artifacts

- **What happened:** reading `probe_c12`'s saved `test_outputs/` locally showed
  five tasks failing pytest **collection** with
  `ModuleNotFoundError: No module named 'dirty_equals'` or `'inline_snapshot'`
  — the exact two packages the C004 calibration had already identified, which
  moved clean-N from 71 to 102. One of them, `fastapi_14262`, had touched the
  gold file, so it is a plausible **false negative**: scored unresolved for an
  environment reason, not a wrong patch.
- **Why it happened (root cause):** `session_runner.py` never staged test
  dependencies. Only `notebooks/01_gold_calibration.ipynb` did, so the lesson
  from C004 was encoded in the calibration path and **not** in the path that
  spends GPU quota. The sandbox cannot self-repair either: its venv is built
  without pip — `ensurepip unavailable in sandbox, creating venv without pip`
  appeared twelve times, once per task — so `install_test_dependencies` has
  nothing to install with. The packages must already be in the interpreter the
  sandbox inherits.
- **Time lost:** none yet, but the whole measurement would have been biased
  downward, and the bias looks exactly like a weak agent.
- **What to do next time:** **a calibration finding is not applied until it is
  enforced on the path that spends the budget.** `session_runner.py` now refuses
  to start when `inline_snapshot` or `dirty_equals` are missing, overridable
  with `--allow-missing-test-deps` to accept the floor knowingly. More
  generally: when one code path validates the instrument and another uses it,
  check that the fix lives in both — the calibration notebook passing proves
  nothing about the runner.

## 2026-10-06: Launched a GPU run without reading the script's own preflight gates

- **What happened:** `P002` burned **0.76 GPU-h** and produced two empty
  directories. `eval_results.zip` contained exactly two entries,
  `paired100_v00/` and `paired100_v03/`, both zero bytes, created **34 seconds
  apart**. No ledger, no patches, no task rows.
- **Why it happened (root cause):** `session_runner.py` refuses to run (`return
  4`) unless `inline_snapshot` and `dirty_equals` are importable — the two
  packages C004 measured as moving clean-N from 71 to 102 — and tells you to run
  `scripts/stage_test_deps.py` or pass `--allow-missing-test-deps`. The kernel I
  generated did **neither**. Both arms created their results directory (which
  happens *before* every validation gate) and exited seconds later.
- **The compounding factor:** `stage_test_deps.py` cannot be used in that kernel
  at all, because it fetches from PyPI and this competition refuses internet with
  the L4 accelerator. So the obvious fix was also unavailable, and nothing in the
  kernel said so.
- **What should have caught it:** reading `session_runner.py`'s argparse list to
  the end. I read enough of it to build the command line and stopped — the
  `--allow-missing-test-deps` flag was *visible in the output I had already
  printed* and I did not ask what it was for.
- **Time lost:** 0.76 GPU-h and a round trip, with the real cost being that the
  measurement still has not happened.
- **What to do next time:**
  1. **Before spending quota on a script, read every one of its preflight gates
     and satisfy them explicitly.** A gate that exits 4 with a clear message is
     the cheap failure; the expensive part was reaching it on a GPU.
  2. **Put every gate the remote script enforces into the notebook, ahead of the
     expensive step.** The kernel now checks the imports itself and asserts
     *before* vLLM spends 2.5 minutes loading 26 GB, so the same mistake costs
     seconds instead of an allocation.
  3. **A 34-second gap between two sibling directory timestamps is diagnostic.**
     It said "both arms failed immediately" and ruled out every slow-failure
     theory before any log was read. Read zip entry timestamps, always.
  4. **Do not "fix" a test environment casually to clear a gate.** Letting pip
     satisfy `inline_snapshot`'s `pytest>=8.3.4` and `rich>=13.7.1` would upgrade
     packages the per-task venvs inherit, and a newer Pygments is already a known
     cause of benchmark failures. Installed with `--no-deps` for that reason.

## 2026-10-07: Batch GPU runs are dead because the BATCH IMAGE is Python 3.13

- **What happened:** every `kernels push` with `enable_gpu` sat in QUEUED for a
  long time and was then cancelled. Opening the same notebook in the browser and
  running it by hand starts and runs normally. Two attempts, same result. The
  user reported this directly; I had been designing *against* it, having written
  a batch kernel specifically to avoid the interactive output problem.
- **Why it matters more than it looks:** I had the causality backwards. I treated
  "interactive" as the mistake that lost `probe_c12`, so the fix was "use batch".
  But batch does not run here at all, which makes interactive the *only* path and
  the lost output a constraint to engineer around rather than a mistake to avoid.
  Two attempts and ~0.8 GPU-h went into the wrong half of that.
- **Root cause of the lost output, restated correctly:** an interactive session
  publishes `/kaggle/working` only on an explicit save, so `kernels output`
  returns a stale zip or nothing. That is not a user error. It is a property of
  the only execution mode available.
- **Time lost:** ~0.8 GPU-h across two attempts, plus a round trip.
- **What to do next time:** **make the log a complete record, always.**
  `session_runner` already prints every row behind `LEDGER_ROW `; the eval kernel
  now reprints them after *each arm* (so a session lost at 50 minutes still banks
  arm 1) and again at the end inside a `=== COPY FROM HERE ===` block, rebuilt
  from the ledger files rather than from captured stdout.
  `scripts/recover_from_log.py --write` reads it back — verified against 12 real
  `probe_c12` rows in exactly that block format before shipping, not after.
- **Generalizable:** when a platform affordance keeps failing, check whether it
  works *at all* on this account before building more infrastructure on top of
  it. And when the user says "it works if I do X", X is data about the
  environment, not a preference to talk them out of.

### Resolved the same day: the cause was the Python version, not the queue

The entry above first blamed Kaggle's queue, because that is what it looked like
from outside. The real cause came out of the first batch log we ever managed to
retrieve, and it is mechanical:

```
GPUs 4  total 90.0 GB  compute cap 8.9          <- correct hardware
running Python tag cp313; wheelhouse tags ['cp310','cp312','cp38','cp39']
AssertionError
```

**The L4x4 batch image runs Python 3.13; the interactive one runs 3.12.** The
wheelhouse ships cp312, so a pushed run cannot install vLLM and dies in **14
seconds** on the preflight assert. The accelerator was never the variable — the
*execution mode* was. "Queued for a long time then cancelled" is what a
structurally impossible run looks like from the CLI.

- **What this corrects:** `CLAUDE.md` said "T4x2 is dead, L4 gives Python 3.12".
  Half right, and the wrong half was load-bearing: it made batch-on-L4 look safe.
  The hardware table now splits L4x4 by execution mode.
- **What went right:** the preflight assert, copied forward from the T4 failure,
  caught it for 14 seconds of quota instead of an hour. A check that fires on an
  unrelated-looking failure months later is the cheapest code in the project.
- **What to do next time:** when a platform behaviour looks like scheduling
  flakiness, **get one real log before theorising.** Two attempts and ~1.8 GPU-h
  went into queue theories; the log settled it in one line. An ERROR run commits
  its log even when a cancelled one does not, so an error is more informative
  than a cancellation and worth preferring.

### Corrected again, hours later: it was a Kaggle image rollover, not batch vs interactive

The interactive run then failed the **same** assert with `cp313`. So the
batch-vs-interactive conclusion above was wrong too, and this is the second
correction of one lesson in a day — worth stating plainly rather than quietly
editing.

**What actually happened:** Kaggle rolled the GPU image to Python 3.13 between
2026-10-06 14:07 UTC (this assert passing) and 2026-10-07 09:44 UTC (it failing),
in **both** modes. I saw a batch run fail where an interactive run had succeeded
*hours earlier*, and read a mode difference into what was a time difference.

**Why I got it wrong:** the two observations were not a controlled comparison —
they differed in mode *and* in time, and I attributed the difference to the
variable I was already thinking about. The user's "it works if I run it manually"
was true **when they said it** and I generalized it into a standing property of
the platform.

**The fix:** pin the environment —
`"docker_image_pinning_type": "original"` in `kernel-metadata.json`, which the CLI
reads and validates. Confirmed it took via `kernels pull -m`: `docker_image` went
from `""` to a concrete `gcr.io/...@sha256:` digest.

**What to do next time:**
- **Two observations that differ in more than one way explain nothing.** Before
  attributing a failure to the variable you happen to be holding, ask what else
  changed — here, the clock.
- **Pin the environment of any notebook whose dependencies are prebuilt**, from
  the start. A prebuilt wheelhouse means the image is a hard version constraint,
  and an unpinned image is a dependency that changes without warning.
- **The preflight assert is the hero of this whole episode.** It caught the
  rollover twice, for 14 seconds each time, and its message is what told the user
  what to do without a round trip. Write the diagnosis INTO the assert.

### Recurrence, 2026-10-07: backticks inside a double-quoted `git commit -m`

Fifth instance of the same class. `git commit -m "... it does not ship `executing`"`
ran `executing` as a command and substituted the empty result, so the commit
message lost a word (`bash: executing: command not found`). The rule above said
"never put a backslash or newline in a heredoc-piped script"; it was too narrow.

**The rule, generalized: never put shell-special characters in a double-quoted
argument.** Backticks, `$`, `!` and `\` are all live inside `"..."`. Use a
single-quoted heredoc (`<<'MSG'`) for every commit message and every file body,
which is what the rest of this session did and why only this one was damaged.

## 2026-10-07: `import vllm` succeeding does not mean vLLM works

- **What happened:** after the cp313 overlay resolved all 41 wheels, the eval run
  reached `COMPLETE` for the first time — in 3 minutes, having run nothing. Both
  arms failed with
  `ImportError: vllm/_C.abi3.so: undefined symbol: _ZN3c1013MessageLoggerC1EPKciib`.
- **Why it happened (root cause):** `_ZN3c1013MessageLogger...` is a **libtorch
  C++ symbol**. `abi3` pins the *Python* ABI, not the C++ one, so a vLLM compiled
  against one torch does not link against another. torch is **not in the
  wheelhouse** — it comes from the Kaggle image, and Kaggle changed the image. The
  cp-tag work was necessary but nowhere near sufficient: it fixed which Python the
  wheels declare, not which libtorch they were compiled against.
- **The check that lied:** my gate ran `import vllm` and it printed `0.19.1`
  happily, because `_C.abi3.so` loads **lazily**. I had written that check one
  commit after warning myself not to trust pip's exit code, and then trusted a
  shallower signal for the same reason — "it reported success" rather than "it did
  the thing".
- **Time lost:** ~3 GPU-minutes for the run itself, but it invalidated a
  conclusion ("the rig is recoverable") that I had already written into
  `CLAUDE.md`, `EXPERIMENTS.md` and three commit messages.
- **What to do next time:**
  1. **Verify a native dependency by loading its native part.** `import vllm._C`
     is the two-second check that reaches the real failure; the gate now does it.
  2. **A prebuilt wheel pins its whole C++ world, not just its Python version.**
     When a prebuilt stack and a host image disagree, enumerate *every* axis they
     can disagree on — Python tag, libtorch ABI, CUDA version, glibc — before
     declaring the problem solved on the first one found.
  3. **Be suspicious of a success that arrives too fast.** Three minutes for two
     arms of twelve tasks was impossible on its face, and that was visible before
     any log was read.

## 2026-10-07: `--platform` is exact, and `kernels output` has no file filter

Two small things from building the torch-fetch kernel, both of which cost a cycle.

- **`pip download --platform` is an exact allow-list, not a minimum.** pip does not
  infer that a `manylinux_2_28` host can run a `manylinux_2_12` wheel. torch's own
  wheel is `manylinux_2_28`, but its `nvidia-*` deps are tagged across the whole
  ladder — `nvidia_cuda_nvrtc_cu12 12.8.93` is
  `manylinux2010_x86_64.manylinux_2_12_x86_64` — so pip reported
  `No matching distribution found ... (from versions: none)` for a wheel that
  plainly exists. **Pass every acceptable tag**; `--platform` is repeatable.
  Related: with two indexes visible, `torch==2.10.0` matches both the PyPI build
  and the PyTorch index's `2.10.0+cu128` and pip refuses outright, so a
  cross-download of a `+local` build must name the local version.
- **`kaggle kernels output` downloads EVERY output file and takes no filter.** The
  torch-fetch kernel's output is several GB of wheels, and pulling it "to read the
  log" started dragging all of them over a home connection. Killed at 31 MB. The
  log is not separately addressable, so: **do not pull the output of a kernel whose
  job is to produce large files.** Read the browser log, or rely on the kernel's
  own asserts — a COMPLETE status on a notebook that ends in
  `assert have_torch, ...` already proves the artifact exists, which is why that
  assert was written in the first place.

## 2026-10-07: The paired estimator reported infinite certainty at k=1

- **What happened:** the first real paired run's report printed
  `delta +0.1667  SE 0.0000  z +inf` and **SIGNIFICANT** for the gold-exact metric.
  The true picture is 3 tasks gained against 1 lost, whose exact McNemar p is
  **0.625** — not evidence of anything.
- **Why it happened (root cause):** `stats.compare` estimates variance as
  `sum p_i(1-p_i)/k`. At k=1 every `p_i` is 0 or 1, so **every term is exactly
  zero**, giving SE=0 and `z = delta/0 -> inf`. The estimator was structurally
  blind to the only kind of uncertainty a k=1 run has.
- **The damning part:** a test named `test_deterministic_arms_have_zero_variance`
  asserted `se == 0.0`, and its own docstring called it "the degenerate case that
  makes single-run McNemar dangerous". **I had documented the bug as a feature and
  pinned it with a test**, so the suite protected it. 183 tests passing meant
  nothing here, because the test encoded the wrong contract.
- **Time lost:** none directly — but it would have reported a non-result as
  significant on the one run the whole project has been waiting for, and the ship
  rule keys on exactly this number.
- **What to do next time:**
  1. **At k=1 the information lives entirely in the discordant pairs.** SE is now
     `sqrt(gained + lost) / n`, which gives z=1.00 for 3-vs-1 — correctly
     unremarkable — while still detecting 9-vs-0 at z=3.0.
  2. **The fallback is keyed on zero variance, not on `k == 1`.** A k=4 run where no
     task is borderline is just as blind, which I got wrong in my first attempt at
     the replacement test and had to correct.
  3. **A test that documents a hazard in its docstring is a bug report, not a
     specification.** When a docstring says "this is dangerous", that is the thing
     to fix, not to assert. Grep the suite for tests that describe known-bad
     behaviour approvingly.
  4. **Never let a statistic be infinite.** An infinite z is always a bug; no amount
     of data justifies it. Worth an assertion in the estimator itself.

## 2026-10-12: A handoff's "open judgement call" was a lookup, not a judgement

- **What happened:** `HANDOFF.md` specified v05 as "remove `run_command` from
  `code_analyzer`", and flagged one open call: that it costs the analyzer its
  only text-search capability, with the alternative being to remove the
  `code_analyzer` AgentTool entirely. It said "decide before building". I was
  about to decide it as a judgement — weighing a capability loss against a loop
  fix — which is how it was framed. Two cheap checks instead settled it as a
  matter of fact, and they pointed the opposite way to the plan.
- **Why it happened (root cause):** the trade-off was stated in terms of a
  capability (`grep`) whose substitute I had never actually read the spec for.
  `HARNESS_README.md:497` says `search_similar_code` runs with **no live
  embedding server**, so the query resolves against node keys and suffixes and
  the caller must already pass a symbol name. It is not a text search at all, so
  "the analyzer keeps a search tool" was false. Separately, one run of
  `analyze_traces.py` over traces **already on disk** showed three of twelve
  tasks looping on `read_file` rather than `run_command` — one of them 75 times —
  so removing `run_command` would displace the loop, not end it.
- **Time lost:** none. Both checks took about five minutes, and they prevented
  building a bundle with a documented evasion path and a near-blind sub-agent.
- **What to do next time:**
  1. **When a handoff flags an open judgement call, first ask which fact would
     settle it.** A call framed as a trade-off often rests on an unverified
     property of one side. Look it up before weighing anything.
  2. **Read the tool's spec, not its name.** `search_similar_code` sounds like
     semantic search and is symbol-key matching in this sandbox. Three of this
     project's worst time sinks were shallow checks passing on the strength of a
     name (`import vllm`, pip's exit code, matching version strings); this is the
     same error in the design phase rather than the environment phase.
  3. **Re-read traces before buying new ones.** The evidence that redirected the
     whole bundle cost 0 GPU-h and was sitting in `results/eval_v9/`. Ask what
     the data on disk already answers before proposing a run.
  4. **Record the rejected alternative in the MANIFEST, with its evidence.** The
     next session will otherwise re-propose the plan the handoff recorded, since
     a handoff is the first thing read and this reasoning would be invisible.

## 2026-10-12: The wheelhouse is not frozen, and the gate checked the wrong symbol

- **What happened:** P003 (`resolve60`) was launched to settle whether the local
  rig can resolve anything at the grader's 60-minute cap. It died **14 seconds**
  into the allocation on `ModuleNotFoundError: No module named
  'swegemma.models.discovery'` — an import that had worked in P002 five days
  earlier, that has been in `session_runner.py` since it was written, and that
  the **official starter notebook** still uses. Cost 0.23 GPU-h and answered
  nothing.
- **Why it happened (two root causes, and the second is the expensive one):**
  1. **The competition republished the wheelhouse on 2026-10-09 14:43**, between
     P002 and P003, and the harness API moved. `swegemma.models` still exists;
     the `discovery` submodule under it does not. I had written in `CLAUDE.md`
     that the wheelhouse was "built 2026-09-30, never updated" and had been
     treating the dependency stack as frozen. **It is a Kaggle dataset, and
     `dataset_sources` always resolves to the latest version — no pin of ours
     covers it.** `docker_image_pinning_type` pins the image only, so the note
     claiming the pin makes the stack "stop moving between arms" was wrong about
     its own scope.
  2. **The preflight gate checked `swegemma.evaluate.Evaluator`**, which still
     imports fine, so it printed PASS — while `session_runner` needs four more
     symbols. The gate was *adjacent to* the dependency rather than being it. The
     project already learned "read every preflight gate before spending quota on
     it" on 2026-10-07 at a cost of 0.76 GPU-h; this is the same lesson from the
     other side — **having a gate is worthless if it asserts the wrong thing**.
- **Time lost:** 0.23 GPU-h and the session's one measurement. Cheap only because
  the failure was immediate; had the import sat deeper in the run it would have
  cost the whole allocation.
- **What to do next time:**
  1. **A gate must import exactly what the script imports.** The generated
     preflight now mirrors `start_server()`'s import list verbatim and, on
     failure, retries each import alone so the log names the symbol that moved
     instead of just saying the harness is broken.
  2. **Record the wheelhouse's `lastUpdated` with every run.**
     `kaggle datasets list -s gemma-4-developer-agent-wheelhouse --user metric`.
     Any paired comparison spanning a republication is confounded and the ledger
     cannot show it.
  3. **Diagnose a packaging question without installing anything.**
     `kernels/13_harness_api` reads the wheels as **zip archives** on a CPU
     kernel — 0 GPU-h, seconds, cannot fail on dependency resolution. Installing
     the stack to find out where a symbol went would have needed the GPU image.
  4. **When an import that used to work stops working, suspect upstream before
     suspecting the install.** The instinct was "the cp313 overlay broke
     something"; the overlay does not contain `swegemma` at all, and one check of
     the dataset's `lastUpdated` gave the real answer.
  5. **A claim about the environment needs a date and a re-check, not just a
     source.** "Never updated" was accurate when written and false five days
     later, and nothing in the repo would have flagged the change.

## 2026-10-12: A decision rule whose only reachable answer is "no"

- **What happened:** the ship rule in `stats.decide` requires a significant
  positive resolution delta before a bundle replaces the champion. An
  adversarial review of the session's own decisions pointed out the arithmetic:
  the single-run paired SE is ~0.030, so the smallest detectable delta is 0.064
  at k=1 and 0.045 at k=2, against a design target of 0.05. **At every `k` this
  project can afford, the rule can only return HOLD.** It had been returning HOLD
  and I had been reading that as "the change did not help".
- **Why it happened (root cause):** the rule was written to be conservative, and
  it is — but conservatism and vacuity look identical from the outside. One word,
  `HOLD`, was carrying two incompatible findings: "we measured and it did not
  help" and "we could not measure". Nothing in the output distinguished them, so
  P002's result was filed as a null when it was an absence of measurement. I then
  made a bundle decision on the strength of that misreading.
- **Time lost:** no GPU-hours directly, but it is the reason the session built
  another bundle instead of buying `k` — which is the more expensive error, and
  one the instrument should have prevented rather than concealed.
- **What to do next time:**
  1. **Ask what a rule's reachable outputs are, not just whether it is correct.**
     A gate that cannot fire, or can only fire one way, is not a safeguard. Write
     the power arithmetic down next to the threshold.
  2. **Never let one verdict mean "no" and "don't know".** `UNDERPOWERED` is now
     a distinct verdict, it never ships, and it prints the instruction that
     follows from it: spend the next allocation on `k`, not on another bundle.
  3. **A statistic that cannot be false is a bug, like a statistic that is
     infinite.** This is the second time this estimator has had that shape — the
     k=1 variance bug was the first. When adding a threshold, test both the case
     that passes and the case that *cannot* pass.
  4. **Resist the obvious fix.** The reviewers' recommendation was to switch the
     ship metric to localization, which is affordable. `report.py`'s own
     docstring already contained the counter-argument: optimizing a surrogate is
     how you win the surrogate. The right change was to fix what the verdict
     *means*, not what it keys on. **When a critique is right about the problem,
     it is not automatically right about the remedy.**
  5. **A 63%-style statistic bounds nothing on its own.** The analyzer consumed
     63% of the call budget, but 9 of 12 tasks submitted a patch and still
     failed, so budget could explain at most a quarter of the failures. Before
     acting on a waste figure, compute the largest share of the outcome it could
     possibly explain.

## 2026-10-12: Every hygiene metric in this project had always been zero

- **What happened:** reading P005 I noticed the panel said `leaked scratch file
  0.0%` and `created a new file 0.0%`. Both were false. Pulling the run's own
  patches apart by hand showed **50% created a new file and 33% leaked a scratch
  file**, and that these are the dominant failure mode: 7 of 12 tasks could not
  possibly have resolved because they submitted nothing or submitted only a
  reproduction script.
- **Why it happened (root cause, two layers):**
  1. `ingest_probe.py` **listed** the patch files for a human to read and never
     wrote them to disk. Its own docstring promised
     `<run_id>/{task_results.jsonl,patches/*.patch}`; only the jsonl was written.
     `metrics.read_outcomes` reads `<run_id>/patches/<iid>.patch`, so the inputs
     to every hygiene metric were missing **for every ingested run this project
     has ever done**.
  2. `Panel.render` formatted those uncomputable counts with the same `pct()`
     helper as everything else, so "no data" rendered as a confident `0.0%`.
     There was a caveat line printed *below* the panel, and `panel_for`'s
     docstring even claimed this was "said plainly in the output rather than
     silently reported as zero" — the intent was right and the implementation
     leaked the zero anyway.
- **Time lost:** none this session, but the cost is retrospective and large: the
  waste metrics were part of the ship rule's diagnostic gate, and they had been
  reporting perfection on the one dimension where the agent was failing worst.
  `probe_c12` had recorded 4/12 created-file and 4/12 scratch-leak back on
  2026-10-06 from the runner's own panel, and that signal was then lost every
  time a run was ingested.
- **What to do next time:**
  1. **A zero on a metric is a claim. Check it can be produced.** Before trusting
     any 0.0%, ask what the non-zero path would have required and confirm that
     path exists. Three of this project's worst errors are now a confident value
     printed where there was no measurement: `SE 0.0000` at k=1, `0.0%` here, and
     a `budget_verdict` rendered against the wrong ceiling.
  2. **Never render "unknown" with the same formatter as "zero".** `Panel` now
     carries `hygiene_known` and prints `n/a (needs patches)`, and `waste_rate`
     returns `None` instead of 0.0 so arithmetic cannot silently absorb it.
  3. **A disclaimer under a number does not undo the number.** The caveat line
     existed and I had read it and still mis-read the panel. Suppress the figure
     instead of annotating it.
  4. **When a script's docstring promises an output, test that the output
     exists.** This one promised a `patches/` directory for weeks.

## 2026-10-12: Price a cap-lifting run off the cap, not the old mean

- **What happened:** estimated P005 at ~1.0–1.5 GPU-h; it cost **2.02** (+35%).
- **Why it happened (root cause):** the estimate was priced off P002's measured
  24.4 min mean per task-arm. But the entire point of P005 was to **lift the time
  cap from 30 to 60 minutes**, which frees exactly the slow tail that the old
  mean had been truncating. 4 of 12 tasks then ran past 30 minutes (max 47.0), so
  the mean had to rise. The estimate used a number the experiment was designed to
  invalidate.
- **Time lost:** no harm done — the run was worth it and the quota held — but a
  35% miss on a run I had priced confidently.
- **What to do next time:** when a run changes a *limit*, price it against the new
  limit and the share of tasks expected to reach it, not against the previous
  run's central tendency. A cap that binds is a censored distribution: its mean
  tells you nothing about what lies beyond the cap.

## 2026-10-12: "Two sources disagree" was neither source being wrong

- **What happened:** the ledger said `fastapi_13713` used 100 tool calls;
  `analyze_traces` counted 565. The discrepancy was filed on 2026-10-06 as
  "the ledger `tool_calls_used` undercounts" and sat in the backlog for six
  days, blocking a bundle decision, because one of two trusted numbers had to
  be a bug. Neither was. They measure different things: emitted calls vs calls
  that spend budget, and the harness charges neither free tools, nor AgentTool
  invocations, nor calls ADK rejects, nor anything emitted after the cap.
- **Why it happened (root cause):** the discrepancy was recorded as a *defect*
  rather than as a *question about definitions*, so the obvious next move —
  read the increment site, `swegemma__context.py:542`, which is 3 lines — was
  never made. The whole reconciliation cost under an hour and no GPU.
- **Time lost:** ~6 days of a blocked decision; the diagnosis itself was ~1 h.
- **What to do next time:** when two instruments disagree, **first write down
  what each one claims to count**, then read the code that produces each
  number. Do not open a bug until the definitions are known to match. And note
  which way the error would have cut: the undercount story would have had us
  ship `max_tool_calls: 200` to "fix" a cap that was never the binding limit.

## 2026-10-12: A metric can be ruined by the pathology it exists to detect

- **What happened:** the four metrics that rank bundles divided by *emitted*
  calls. `fastapi_13713` therefore scored `reissue_rate` 0.837 — driven by 310
  refused and 146 free calls it made *after* its budget was exhausted — and
  `fastapi_13207` reported 29 workspace writes when 3 writes happened, the
  other 26 being one malformed `edit_file` retried 26 times.
- **Why it happened (root cause):** the denominator was chosen when "a call is
  a call" was still true, and was never revisited after the agent started
  spinning past its cap. The metric's denominator was itself a function of the
  pathology, so worse behaviour could register as a better score.
- **Time lost:** none directly — caught before a bundle was ranked on it. The
  exposure was real: `v05` was about to be judged by these numbers.
- **What to do next time:** for any rate, ask what makes the denominator grow
  and whether the thing under study grows it. Prefer a denominator the agent
  cannot inflate. Rename the field when its definition changes, so stale
  recorded values fail loudly instead of comparing silently.

## 2026-10-13: A precondition verified yesterday is not verified today

- **What happened:** I designed a cost-saving measurement — one `v05` arm
  paired against P005's existing `v00` rows — on the strength of a check that
  the wheelhouse had not been republished since 2026-10-09. That check was real
  and it passed, at ~14:45 on 2026-10-12. Re-running it immediately before
  launch on 2026-10-13 showed the wheelhouse republished at **2026-10-12
  19:51:31**, about five hours after I cleared it. The whole design was invalid.
  Had I launched on yesterday's check, I would have spent ~2.2 GPU-h producing a
  delta confounded by a dependency-stack change, **with nothing in the ledger to
  record that it happened** — the most expensive kind of wrong number, because
  it looks exactly like a right one.
- **Why it happened (root cause):** I treated a verified fact as durable. The
  wheelhouse is a *dataset* arriving via `dataset_sources`, which always
  resolves to latest, and `docker_image_pinning_type` pins only the image — so
  its stability is not a property anything of ours controls. A fact about a
  mutable external resource has a shelf life, and mine was hours.
- **Time lost:** none, because the re-check happened. ~20 min to redesign.
  The near-miss was ~2.2 GPU-h of silently useless data.
- **What to do next time:** re-verify a time-sensitive precondition **in the
  same minute as the irreversible action**, not in the same session. Better,
  design so the precondition cannot bind: **both arms of a comparison run in
  one session**, which is immune to republication by construction and cost
  ~2 GPU-h more. Buy structural immunity over a verified assumption when the
  price is a small fraction of the budget. This is the third time the wheelhouse
  has moved mid-competition (2026-10-09, 2026-10-12), so expect a fourth.
- **The generalisation worth keeping:** the cheap design was cheap *because* it
  reused an old arm. Every reuse of an earlier measurement inherits that
  measurement's environment, so "free" comparisons are never free — they are
  borrowing against an assumption you did not re-test.

## 2026-10-13: A confirmed mechanism is not a cause

- **What happened:** T002 found that in 4 of 5 failing tasks the agent never
  attempted an edit while a sub-agent consumed 90–98% of the budget, with
  Spearman(sub-agent share, outcome quality) = −0.90 over 12 tasks. `v05`
  removed that sub-agent. P006 (4.35 GPU-h) confirmed the intervention worked
  perfectly — `coder_call_share` 0.543 → 1.000 at z=+6.02, zero analyzer calls,
  first edit moving from call ~20 to ~6, and the "never edited" task gone — and
  `gold_hit` did not move at all: 5/12 both arms, 1 gained, 1 lost, McNemar
  p=1.00. Resolution stayed 0/12.
- **Why it happened (root cause):** the correlation was a *symptom* of task
  difficulty. Hard tasks attract heavy analysis; removing the analysis does not
  make them tractable. T002 wrote this confound down explicitly as a caveat, and
  the experiment resolved it the unfavourable way. The error would have been
  skipping the experiment and writing the mechanism up as causal.
- **Time lost:** none wasted — 4.35 GPU-h bought a clean answer to the
  project's central question, which is what the quota is for. The near-miss was
  *believing* it: the narrative was coherent, quantitative, and wrong.
- **What to do next time:** when a process metric correlates with an outcome,
  ask what else would produce that correlation **before** building the fix, and
  state the confound in the hypothesis. Then test whether the intervention moves
  the *outcome*, never whether it moves the process metric it was designed to
  move. A mechanism you can confirm is still only a mechanism; `coder_call_share`
  moving by +0.457 is proof the bundle works, not proof the bundle helps.
- **The corollary that cost the most to learn here:** freed budget does not stay
  freed. `reissue_rate` rose +0.151 (z=+1.87) as the coder absorbed the budget
  with its own repetition, and two new loops appeared that v00 never showed
  (174 `submit_patch` calls in one task, 136 malformed `edit_file` in another).
  Removing a wasteful component redistributes waste unless something structural
  stops it. The bundle's own MANIFEST predicted this; believe such warnings.

## 2026-10-13: Four load-bearing numbers went stale for two weeks, unnoticed

- **What happened:** the live leaderboard had not been read since **2026-09-30**.
  Every state file in the project — `PLAN.md`, `README.md`, `PROGRESS.md`,
  `CLAUDE.md`, `paper/OUTLINE.md` — still said "top 0.17, ~19 of 1037 teams tied
  at 0.13, private set ~60 tasks, the visible board is ~4 tasks wide". The live
  values are **0.24, 340 of 2643, 58 tasks, and a 14-task span**. `PROGRESS.md`
  also said "four submissions scored" where `kaggle competitions submissions`
  reports **three**. The paper's §B evidence map had the stale figures marked
  "observed", which is the worst case: a wrong number wearing a verification
  label.
- **Why it happened (root cause):** these numbers were verified *once*, at
  project start, and then cited from file to file. Each citation looked sourced
  because the previous file sourced it. Nothing in the session-start routine
  re-reads an *external* fact that is already written down — the routine checks
  `git status`, the state files and Asana, all of which faithfully reproduced the
  stale value. A fast-moving competition (1037 → 2643 teams in two weeks) makes
  every external number perishable, and none of ours carried a capture date.
- **Time lost:** none this session — the check took ~10 minutes and the stale
  figures had not yet reached a submitted artifact. The real cost is
  counterfactual and large: the paper was two steps from being drafted on them,
  and a judge with the public leaderboard open would have found the error
  immediately. A paper arguing for measurement discipline, built on a three-week
  memory of someone else's number, fails on its own thesis.
- **What to do next time:** before citing any external number, re-read it and
  **write the capture date next to it**. A number without a date is not a
  verified number. Prefer committing the raw aggregate — the snapshot now lives
  at `data/leaderboard/public_lb_2026-10-13.json` — so the next session diffs
  against evidence rather than against prose.
- **The part worth more than the correction:** the stale number was hiding a
  *finding*. Pulling the full histogram to re-check "top is 0.17" is what exposed
  that the denominator is recoverable exactly (58 tasks, unique fit) and that the
  gap to the top is 6 tasks and therefore **real by our own 0.06 rule**. The
  routine check produced the session's best result. Do not treat verification as
  overhead to be minimised; it is where the cheap findings are.
- **The inversion to remember:** this project's standing instinct is "an LB delta
  below 0.06 is not evidence", and it was applied so thoroughly that nobody asked
  whether a delta *above* 0.06 had appeared. A threshold is two-sided. Scepticism
  pointed only downward stops being scepticism.

## 2026-10-13: Which constraint binds is a property of the environment, not the bundle

- **What happened:** `HANDOFF.md` and `PROGRESS.md` both stated that the
  60-minute session cap never binds, citing P005's max wall of 47.0 min. Reading
  P006's rows per task instead of as a summary showed **6 of 12 v00 tasks
  terminated by `Agent exceeded session timeout`**, with a median wall of 60.4
  min against P005's 25.9 — on **identical bundle bytes**, same
  `concurrency: 12`, same `max_model_len`, arms 49 minutes apart rather than
  simultaneous. Summed task wall went 287.7 → 636.5 min, a 2.3× slowdown.
- **Why it happened (root cause):** the 2026-10-12 19:51:31 wheelhouse
  republication sits between the two runs, and the project already knew the
  wheelhouse is a *dataset* that no pin of ours can freeze. The error was not
  failing to know that; it was **writing a resource conclusion as if it were a
  property of the agent.** "The cap never binds" is a claim about the agent, the
  hardware and the dependency stack jointly, and only one of those three was
  being tracked.
- **Time lost:** none — the finding came out of a 5-minute re-read. But it had
  already propagated into a *decision*: "do not ship `max_tool_calls: 200`" was
  marked **settled** on the reasoning that the cap bounds charged work and not
  wall clock. That is true of v00, where time binds. In v05's topology time does
  not bind (max 45.6 of 60) and calls do (3 of 12 at exactly 100), so the
  conclusion never transferred to the topology it would actually be shipped on.
- **What to do next time:** when recording which resource is binding, **record
  the environment stamp with it** — wheelhouse `lastUpdated`, concurrency,
  `max_model_len` — and re-derive it per run rather than inheriting it. Prefer
  "in P005's environment the cap did not bind" to "the cap does not bind". A
  conclusion of the form *X is not the limit* expires, because the limits move.
- **The structural half of it:** the sub-agent is a **wall-clock** sink, not only
  a call sink. v00 summed 636.5 min against v05's 371.2 for the same 12 tasks,
  while an `AgentTool` invocation is charged as **one** call. A budget metric
  denominated in tool calls is blind to this by construction — the same shape of
  error as the 2026-10-12 lesson about a denominator the pathology inflates.
  **When a component is suspected of waste, measure it in every currency the
  harness charges in: calls, wall clock and context.**

## 2026-10-14: a bare `400` on submit has a SECOND cause, and it is not the filename

- **What happened:** `scripts/submit.py --variant v05_no_analyzer` returned
  `400 Client Error: Bad Request` from `CreateSubmission`. This file already
  records a bare `400` as meaning *the file was not named `submission.zip`*, so
  the first instinct was to hunt the packaging. The packaging was fine:
  validator PASS with no findings, zip round-trip PASS, the archive named
  `submission.zip` containing exactly `agent.yaml`, `configs/sampling.yaml`,
  `prompts/system.md`, `testzip()` clean, 2,551 B. Nothing registered
  server-side — `competitions submissions` showed no new row, so it was a clean
  rejection and not a partial submit.
- **Why it happened (root cause, narrowed not proven):** the previous
  submission (v06, ref 57145400) went in at **2026-10-13 13:41 UTC** and was
  still `PENDING` **20.7 h later**. So the attempt sat inside 24 h of it. Two
  candidates remain and they are not yet separated:
    1. the daily limit is a **rolling 24 h window**, not a calendar-day reset; or
    2. a **`PENDING` submission blocks** a new one.
  Both predict the same fix (wait) but different waits: (1) clears at 13:41 UTC,
  (2) clears only when v06 finally scores.
- **Time lost:** ~15 min, and one planned submission deferred.
- **What to do next time:**
  - **Do not read a bare `400` as the filename bug.** Check the packaging, then
    check the clock against the last submission's timestamp, then check whether
    anything is still `PENDING`.
  - **Retrying just after the 24 h mark is the free experiment that separates
    the two causes.** If it succeeds while v06 is still `PENDING`, the limit is
    a rolling window and this project's "tomorrow's submission is free" is
    wrong — the correct statement is "free 24 h after the last one".
  - **`HANDOFF.md` has been saying "today's submission is spent; tomorrow's is
    free".** That is calendar-day reasoning and it mis-predicted here. Plan
    submissions off the **last submission's UTC timestamp**, not the date.
  - The error body would have settled this immediately, but the sanctioned
    submit path swallows it and reaching the API directly is a live-transaction
    call. Prefer the clock check over trying to extract the body.

## 2026-10-19: A finished GPU run sat unread for five days

- **What happened:** P007 (v00 vs v06, n=60, ~6 GPU-h) was launched 2026-10-14
  and **completed**. Its output was never fetched. Five days later
  `kaggle kernels output` returned all 120 rows intact at **0 GPU-h** — both
  arms, `surrogate: false`, one session. The measurement existed the whole time;
  only the reading was missing. In those five days the quota window rolled over
  (2026-10-17), six submission slots expired unused, and the team fell from rank
  785 to 1402 on an unchanged score.
- **Why it happened (root cause):** the session that launched the run ended with
  the launch. `HANDOFF.md` recorded P007 as "launched" and listed reading it
  under a step gated on *v06's leaderboard score arriving first* — and that score
  never arrived, so the gate never opened. **A dependency on an external event
  was placed in front of work that had no dependency on it.**
- **Time lost:** 5 days of wall clock; 0 GPU-h (the run's output persisted
  because it was a **batch** run, which commits `/kaggle/working` even on error).
  Had it been interactive, 6 GPU-h would have been unrecoverable.
- **What to do next time:**
  - **Fetch a run's output the moment it reaches a terminal state, before
    anything else.** Reading banked rows is 0 GPU-h and cannot be scooped.
  - **Never gate the reading of work already paid for on an event outside our
    control.** Order next steps by *what blocks them*, and put unblocked work
    first. A step whose precondition is "someone else's system responds" belongs
    last, with an explicit "if it has not arrived, proceed anyway".
  - `HANDOFF.md` should record a launched run as **"launched — fetch output
    first thing"**, not as an item in a priority list where it can be outranked.

## 2026-10-19: Conditioning on an outcome the treatment changes is not a subgroup analysis

- **What happened:** reading P007, v06 looked vindicated once tasks were split by
  whether they finished — `gold_hit` 0.760 for v06's completers against 0.711 for
  v00's, i.e. "the tools help whenever the agent gets to finish, and the 30-minute
  cap is hiding it". That reading was drafted before being checked. It is
  **selection bias**: v06's whole measurable effect is *causing* timeouts (35/60
  vs 22/60, p=0.0072), so it has 25 completers to v00's 38, and its completer set
  is the more heavily selected and therefore easier subset.
- **Why it happened (root cause):** the split variable (`timed out`) is
  **downstream of the treatment**. Conditioning on it compares non-comparable
  populations. The direction of the bias even flattered the hypothesis under test,
  which is exactly when a result feels most convincing.
- **Time lost:** ~10 min, caught before it reached any state file.
- **What to do next time:**
  - **Before splitting a paired comparison by any variable, ask whether the
    treatment can move that variable.** If it can, the split is invalid.
  - The valid repair is to restrict to units where the mediator is **equal in
    both arms** — here the 21 tasks that completed in both. Doing so collapsed
    the effect to *exactly* nothing: 16/21 vs 16/21 `gold_hit`, 6/21 vs 6/21
    `gold_exact`, 3/21 vs 3/21 `resolved`.
  - This is the project's **eighth** instance of a confident number computed
    against the wrong contract. The pattern is now: a plausible number appeared,
    and nobody asked what population it described.

## 2026-10-19: A submission can complete and score nothing

- **What happened:** v06 (ref 57145400) reports `COMPLETE` with a **blank**
  `publicScore` six days after submission. Not pending, not rejected, not 0.00 —
  blank. The previous session recorded it as `PENDING` and treated a stuck
  submission as possibly blocking every future one.
- **Why it happened (root cause):** unresolved, but only one candidate has
  evidence. P007 shows v06 timing out on 35 of 60 tasks against v00's 22
  (p=0.0072), so the bundle is measurably slow; a slow bundle is the best
  available explanation for an evaluation that finished without a score. The
  mechanism E013 pre-registered — `ContextWindowExceededError` — is **refuted**:
  zero context deaths across 60 v06 task-runs.
- **Time lost:** one submission slot, plus the six days of waiting the gate caused.
- **What to do next time:**
  - **A scoreless `COMPLETE` does not block the queue** — v07 submitted fine on
    2026-10-19. Do not defer submissions over it.
  - **Cost a bundle's wall clock locally before spending a slot on it.** The
    submission slot is only a free 58-task sample if the bundle can finish.
  - Treat a blank score as **evidence about the bundle's speed**, not a grader
    fault, and record it against the `bundle_hash` like any other outcome.

## 2026-10-20: A one-off anomaly was explained away instead of controlled for

- **What happened:** v06 came back `COMPLETE` with a blank score. A plausible,
  well-evidenced story was available — P007 had just measured v06 timing out on
  35 of 60 tasks — so the blank was written up as "measured slowness is the best
  available explanation" and the next bundle was submitted on top of it. v07 then
  came back blank too, and it is structurally unrelated to v06, which kills that
  explanation. **Two slots and seven days produced zero information.**
- **Why it happened (root cause):** a bundle-specific explanation was accepted for
  a *channel-level* symptom without a control. The explanation was attractive
  precisely because the session had just measured the mechanism it invoked, which
  made a coincidence look like a cause. Nothing checked whether a **known-good**
  submission would still score.
- **Time lost:** 2 submission slots, and the 7 days between them.
- **What to do next time:**
  - **When a result is missing rather than bad, suspect the channel before the
    content.** A wrong score is evidence about the bundle; *no* score is first
    evidence about the pipeline.
  - **The control is known-good bytes, nothing else.** Re-submitting a *new*
    bundle cannot separate "channel broken" from "this bundle broken" — which is
    the ambiguity that wasted both slots. `v00_public_baseline` is the control
    because it has actually scored.
  - **Two data points of the same anomaly is the trigger, not the third.** The
    first blank was defensible to explain; submitting again without a control
    was not.
  - Check the grader is healthy independently before blaming it: count teams on
    the live leaderboard by the date of their last *scored* submission. 698 teams
    scored on the same day ours did not.

## 2026-10-20: A GPU run cost 1.76x the estimate, because the estimate priced wall clock not GPU-hours

- **What happened:** P008 was budgeted and announced at **~6 GPU-h** and consumed
  **10.57**. The shape was deliberately copied from P007 — 60 tasks, 2 arms,
  30-min cap, concurrency 12 — and P007's own recorded cost was ~6 GPU-h, so the
  estimate looked like arithmetic rather than a guess. It was not.
- **Why it happened (root cause):** the estimate was built from **wall-clock
  waves** (5 waves x 30 min + 25 min load, x2 arms = 5.8 h) and then quoted as
  GPU-hours, as though 1 wall hour costs 1 GPU-hour. P008 ran 14:59-20:17 UTC =
  **5.3 h wall for 10.57 GPU-h, a ratio of ~2.0.** The wave arithmetic was right;
  the unit conversion was missing. P007's ~6 GPU-h for a similar shape implied a
  ratio nearer 1.3, which is what made the wrong unit look validated — that
  figure should have been checked against its own wall time before being reused.
- **Time lost:** no time, but **4.6 GPU-h of a 45 h window that expires
  2026-10-24 and does not carry over** — about 44% of one run.
- **What to do next time:**
  - **Estimate wall hours, then multiply.** On Kaggle L4x4, budget
    **~2 GPU-h per wall hour** until a second data point says otherwise. State
    both numbers, so the conversion is visible and checkable.
  - **The session cap is in wall hours and the quota is in GPU-hours.** They are
    different units and the same run is measured against both. P008 fit the
    session cap comfortably (5.3 h of 9-12) while costing nearly twice its quota
    budget; checking only the first is how this was missed.
  - **Do not reuse a previously recorded cost without recomputing its ratio.**
    Re-derive from that run's actual wall time and actual quota draw.

## 2026-10-21: The control settled it, and the first blank should have triggered one

- **What happened:** the 2026-10-20 control — `v00_public_baseline`, bytes
  identical to a submission that scored 0.13 — came back `COMPLETE` with a blank
  score, while 641 other teams scored that same day. So the submission channel is
  broken for this account, and **v06's and v07's blanks were never about those
  bundles at all.** Three slots and v07's whole test were spent on a dead channel
  across 8 days.
- **Why it happened (root cause):** the first blank arrived with a ready-made,
  well-evidenced bundle-specific story (v06 had just been measured timing out on
  35/60 tasks), so it was explained rather than controlled. The explanation was
  *more* persuasive because the mechanism it invoked had genuinely been measured
  that same session — which is exactly the trap. A second bundle then went out on
  top of an unverified channel.
- **Time lost:** 3 submission slots, 8 days of leaderboard signal, and v07
  remains untested.
- **What to do next time:**
  - **One missing result is enough to trigger a control.** Not two, not three.
    A *wrong* score is evidence about the bundle; **no score is evidence about
    the pipeline** until a control says otherwise.
  - **The control must be bytes that have already produced the expected output.**
    Anything else cannot separate "channel broken" from "this input broken".
  - **Check the shared dependency is healthy before blaming your own input** —
    here, counting other teams' scored submissions by date took one command and
    would have falsified the backlog theory on day one.
  - When a plausible cause appears in the same session that a symptom does, treat
    the coincidence as a reason for *more* scepticism, not less.

## 2026-10-21: The API hid the failure reason the UI was showing all along

- **What happened:** three submissions returned `SubmissionStatus.COMPLETE` with
  an empty `publicScore` from `kaggle competitions submissions --csv`. Eight days
  went into diagnosing that, ending in "the channel is broken for this account,
  escalate to Kaggle support". A screenshot of the submissions page showed every
  one of them labelled **`Notebook Timeout`** — a specific, fixable cause that
  had been displayed the whole time.
- **Why it happened (root cause):** the CSV API exposes `status` and
  `publicScore` but **not the failure reason**, and `COMPLETE` + blank was read
  as "finished, no score" when it actually meant "finished the attempt, which
  failed". Every subsequent inference was built on a status string that had
  already discarded the answer. The investigation was thorough but ran entirely
  inside one impoverished view.
- **Time lost:** 8 days, 3 submission slots, and a wrong escalation plan.
- **What to do next time:**
  - **When a status is unexpectedly empty, look at the same object in the UI
    before theorising.** A one-line ask for a screenshot would have cost nothing
    on day one. The API is a convenience, not the system of record.
  - **A blank field is not data; it is a missing view.** Treat "the API returned
    nothing here" as "I have not looked yet".
  - Note what the control DID buy: it correctly ruled out every bundle, and that
    conclusion survived the correction intact. A good control is robust to
    getting the mechanism wrong.
  - **Cross-check a remote symptom against local measurements by date.** T005 had
    measured the 2.3x slowdown across the 2026-10-12 wheelhouse republication
    five days before the first timeout was understood. The submission record
    splits on the same date. Nobody put the two together because they lived in
    different files.

## 2026-10-21: a timeout we set ourselves, and a retry that guaranteed failure

- **What happened:** P009 returned zero rows. The vLLM weight load took 1,059 s
  (11.8x the 89.78 s baseline of 2026-10-01), overran a 1,200 s readiness
  timeout, and was killed; `start_server` then retried onto GPUs that still held
  the dead engine's memory (15.1 GiB free of 22.03, then 1.31), so all four
  later attempts failed within minutes. Both arms lost.
- **Why it happened (root cause):** two of our own defects, compounding.
  1. `startup_timeout=60 * 20` was a hardcoded guess at how long a load takes.
     It was read as an ADK constraint; it was **our argument**, one line below
     `gpu_memory_utilization`.
  2. The retry's guard was `if not extra: raise` — "were optional flags
     passed", which is a question about *our* configuration, not about the
     failure. It therefore fired on a readiness timeout, the one case where a
     retry is certain to fail, because a killed CUDA process does not hand back
     its memory.
- **Time lost:** ~0.4 h wall, ~1.5 GPU-h, and the session P009 was supposed to
  be; the cap-60 question is still unanswered with 3 days left in the window.
- **What to do next time:**
  - **A retry must branch on the failure, not on the configuration.** Ask "could
    this error be the thing the retry fixes?" — not "did I pass the flag the
    retry would remove?".
  - **A retry after a CUDA process dies needs the memory back first.** Verify
    free VRAM before re-starting, or do not re-start.
  - **Before calling a limit external, grep for it.** Two sessions reasoned
    about ADK's 1200 s; it was ours all along.
  - **An environment timing constant is not a constant.** Kaggle input
    throughput moved 11.8x in 20 days and nothing we can pin holds it. Give
    deadlines headroom and log the measured rate every run.

**Adds to the meta-lesson (now eleven):** a guard passed while the real thing was
broken. This time the guard was a retry that "worked" — it ran, it was reached,
it was even logged — and it converted a one-arm failure into a whole-session one.

## 2026-10-21: three fifths of the eval rows were never graded, and nobody looked

- **What happened:** T011 (offline, 0 GPU-h) read P008's pytest logs for the
  first time. On **59 of 103** applied patches pytest aborted during collection,
  so no test ran; 75 of 103 logs carry one starlette/fastapi version mismatch.
  **8 patches reproduced the gold fix line for line and all 8 scored
  unresolved.** Every local resolution number from P008 — and the "~3x local
  understatement" reasoning built on it — rests on a denominator that is 57%
  unmeasurable.
- **Why it happened (root cause):** `clean_n.txt` (the 102 tasks that pass with
  the reference patch) was calibrated in an *earlier* wheelhouse. E018 then
  refuted the drift hypothesis with `clean_dev.txt ⊂ clean_n.txt` — reading a
  past environment's set membership as a present property of the environment,
  of exactly the artefact this project already knows republishes without notice.
  Contributing: the pipeline writes `test_outputs/*.log` on every task and no
  script had ever opened one. `resolved` was trusted; the evidence of *why* it
  was false sat unread on disk through nine bundles.
- **Time lost:** not this session's — **nine bundles and roughly five eval
  sessions** of GPU spend whose rows were partly unreadable, plus an LLM council
  reasoning about patch quality from them.
- **What to do next time:**
  - **Read the rawest artefact once, early.** The diagnostic panel summarised
    patches and ledger rows; the pytest logs, the only artefact that says *why*
    a task failed, were never parsed. A 0-GPU-h read would have caught this in
    week one.
  - **Any set derived by running code is stamped with the environment that ran
    it.** Date it, record the wheelhouse `lastUpdated` beside it, and re-derive
    it before using it to refute anything.
  - **Count how many of your rows are measurable before interpreting them.**
    "Graded / applied" belongs in every run's summary, next to the resolution
    rate.
  - **A patch identical to gold that scores 0 is the cheapest possible
    environment canary.** Check for it after every run.

**Adds to the meta-lesson (now thirteen, counting `HANDOFF.md` §5's twelve):** a
shallow check passed while the real thing was broken — this time the check was a
*set inclusion* that was true as written and meaningless as used.

## 2026-10-27: Wrote that a pre-registered falsifier fired, when it had not

- **What happened:** The paper's §E said D5 "cost us our own preferred
  conclusion" — that the reading registered to falsify the v08 clamp had fired,
  because `gold_exact` moved the wrong way. `bundles/v08_decode_clamp/
  MANIFEST.yaml` says otherwise. The registered falsifier is **`gold_hit`
  falling by more than the timeout rate improved**, and P009 measured `gold_hit`
  **rising, 18 → 24**. That is the *favourable* registered branch. `gold_exact`
  appears nowhere in the pre-registration; the only text calling it the
  falsifier was written in `EXPERIMENTS.md` on 2026-10-27, after the result.
- **Why it happened (root cause):** I reconstructed the pre-registration from
  memory of the *outcome* rather than re-reading the file. A reading that went
  the wrong way was available, and pre-registration is a concept I could narrate
  without checking which branch had actually been written down. This is exactly
  the failure D5 exists to prevent, committed in the section describing D5.
- **Time lost:** none externally — a fact-check caught it before submission. The
  cost would have been a measurement-discipline paper caught misreporting its own
  pre-registration, in front of judges scoring Verifiability.
- **What to do next time:** **A pre-registration is a file, not a memory.** Quote
  the registered branch verbatim beside the outcome before writing either one.
  And when an unregistered reading goes the wrong way, report it *as*
  unregistered — that is still honest and costs nothing.

## 2026-10-27: Read a histogram total as a positive-score count

- **What happened:** The paper said "3,199 teams hold a positive score" in §B and
  used 3,199 for the positive positions in §D0. The snapshot's histogram sums to
  3,199 **including 156 teams at 0.00**, so positive scorers are **3,043**.
- **Why it happened (root cause):** `leaderboard.py` gets this right —
  `occupied_scores()` filters `float(s) > 0` and the `score_grid` docstring says
  why. The prose was written from the `teams` field instead of from the function
  that the rest of the argument runs on. Correct code, wrong number in the text.
- **Time lost:** ~15 min to find and fix; it had survived two drafts and sat in
  the paper's single most quotable sentence, twice.
- **What to do next time:** When prose quotes a number the repo also computes,
  **get it by calling the code**, not by reading a neighbouring field. If the
  analysis filters something, the sentence must filter it too.

**Adds to the meta-lesson (now fifteen):** a shallow check passed while the real
thing was broken — this time a remembered pre-registration and a total mistaken
for a subtotal, both in a paper arguing that instruments must be calibrated
before they are trusted.
