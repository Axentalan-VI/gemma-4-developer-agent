# Progress — Gemma 4 Developer Agent

## Current status

**THE PAPER IS UNDER THE CAP AND FACT-CHECKED (2026-10-27).** The manuscript went
from **3,265 body words to 2,922** against an official 3,000 cap (2,981 on a naive
markdown split, 2,946 as rendered — under on every basis). More important than the
trim: an audit of every quantitative claim against primary sources produced **ten
corrections**, two of them serious enough to be `LESSONS.md` entries. §E had
claimed a pre-registered falsifier fired when `v08`'s MANIFEST says the registered
reading was `gold_hit`, which **rose** 18→24 — the favourable branch. And "3,199
teams hold a positive score" was the histogram total; 156 teams sit at 0.00, so the
figure is **3,043**. The paper is **still not submitted** — deadline 2026-11-12
23:59 UTC. Detail: `EXPERIMENTS.md` "PAPER — trimmed under the cap and
fact-checked", and the manuscript's own header.

**`v10_clamp_timecap` (ref 57693514) is still PENDING** 7 h after submission at
07:35 UTC, which is itself new — the four blanks before it returned COMPLETE.
**GPU 0.00 h used, 45.00 h remaining, and it expires 2026-10-31** (verified
2026-10-27 14:18 UTC). The gating item for spending any of it is unchanged and
untouched: re-derive `clean_n` in the current wheelhouse on a CPU kernel, because
~76% of a local run's rows are currently ungradeable.


**THE COUNCIL REFUTED FIVE OF OUR OWN PREMISES (2026-10-21).** A five-advisor
LLM council ran on "is the current architecture worth improving". It was
unanimous — "the failure is verification, add a verify gate" — and the
fact-check refuted the unanimity. **The verify gate is already shipped twice**:
v00's prompt mandates it, v01 strengthened it and scored **0.08, the worst of
three**, and v07 is the structural version, already submitted. **"0/12 locally"
was never evidence** (P = 0.169 at the grader's own rate). The drift floor does
not explain local-vs-grader. The GPU cliff was misframed — quota refreshes
weekly. Multi-candidate decode is schema-illegal. Full detail: `EXPERIMENTS.md`
E018, `HANDOFF.md` §2.

**Measured, 0 GPU-h, from 120 traces: the agent already verifies in ~60% of
submitting tasks, and all 5 resolved tasks came from verifiers while 0 of 32
non-verifiers resolved anything.** Not causal — the split is confounded by
competence (verifiers localized 0.818 vs 0.385 *before* verifying). The problem
is compliance and self-test correctness, not a missing instruction.

**`v10_clamp_timecap` is built and not submitted** (`9033b8826a9add43`, E019):
v08's clamp plus v09's 30-minute cap. It waits on v09, which is the
cap-without-clamp control. A dry-run without `--ship-eval-config` packaged
**v08's exact hash** — `ships_eval_config` was a decorative field no code read,
and `build_bundle` now refuses. **The user chose the next GPU run: greedy
(temperature 0.0) vs 0.2, with `resolved` primary.** Decode is the only knob
class never varied in ten bundles. **Paper deprioritised by the user today.**


**P009 LOST ITS SESSION TO TWO OF OUR OWN BUGS, AND IS RE-RUNNING (2026-10-21).**
The cap-60 question — does the decode clamp still help at the grader's real
60-minute cap, where the cap no longer favours the faster arm? — is **still
unanswered.** P009 returned COMPLETE with both arms `rc=1` and **zero of 72
rows**.

Cause: the safetensors shard took **1,059 s** to read out of `/kaggle/input`
against **89.78 s** on 2026-10-01, overran our own `startup_timeout=60 * 20`,
and the engine was killed; `start_server` then retried onto GPUs that still held
the dead engine's memory (15.1 GiB free of 22.03, then 1.31) and failed four more
times. **Both defects were ours** — the 1,200 s was our argument, not an ADK
constant, and the retry branched on our configuration (`if not extra: raise`)
rather than on the failure. Fixed in `17bacb5`: `_startup_timeout_s` (45 min,
per-runspec override) and `_should_retry_without_extra_args`, which never retries
after a readiness timeout. Suite **245 passed**. Re-run pushed as kernel
version 2, RUNNING.

**The load collapse is under 19 hours old and does NOT explain the submission
timeouts.** P008 loaded cold in **5 min 29 s** at 2026-10-20 15:05 (and warm in
2 min 45 s at 17:42), hours *after* the 08:46 control submission had already
timed out. So the wheelhouse-boundary account below stands. What is new is a
separate, fresher ~11.8× collapse in Kaggle input throughput, which nothing we
control pins and which may be transient. The one place the two could meet is
**v09 itself**, submitted 08:04 UTC today: `max_time_minutes` is a *per-task
agent* budget (`HARNESS_README` line 540), so a one-off model load sits outside
it. **A v09 timeout is therefore weaker evidence against the cap than its
MANIFEST pre-registered — re-submit the same bytes before escalating.**


**SUBMISSIONS ARE FAILING WITH "NOTEBOOK TIMEOUT", AND THE CAUSE IS DATED
(2026-10-21).** Corrects the earlier reading in this file, which said the channel
was broken for this account and recommended escalating to Kaggle support. **The
part that stands is that no bundle is at fault**; the mechanism was wrong.

The Kaggle **UI** shows all three failures as `Notebook Timeout`. The CSV API
reports only `COMPLETE` with a blank score, which is why eight days of diagnosis
never saw it — **the API hides the failure reason the UI displays.** Submissions
are not being skipped; they are running out of time.

**The boundary is the 2026-10-12 19:51:31 wheelhouse republication.** Every
submission before it scored (v00 0.13, v01 0.08, v04 0.10); every one after has
timed out (v06, v07, and the byte-identical v00 control). T005 had already
measured a **2.3× slowdown on identical v00 bytes** across exactly that boundary
— median task wall 25.9 → 60.4 min, summed 287.7 → 636.5 — five days before the
first timeout was understood. The wheelhouse arrives as `dataset_sources`, so no
pin of ours holds it still.

**The fix had been available all along and never tried.** `HARNESS_README` §7.1
lets a submission ship `eval_config.yaml` with `evaluation.max_time_minutes`
(default 60); `build.py` and `validate.py` have supported it since the start, and
all nine prior bundles set `ships_eval_config: false`. **v09_timecap** (ref
57472801, `7b3fbfb99f0458db`) is v00's bytes plus exactly that one file, capped
at 30 min — the pre-slowdown envelope in which the grader demonstrably finished.
It is not trying to beat 0.13; it is trying to produce a score at all.

**Escalation is no longer the next step** unless v09 also times out.

**(superseded) THE SUBMISSION CHANNEL IS BROKEN FOR THIS ACCOUNT, confirmed by control
(2026-10-21).** `v00_public_baseline`, byte-identical to the submission that
scored 0.13 on 2026-09-30, came back `COMPLETE` with a **blank** score
(ref 57430290). That is three consecutive blanks — v06, v07, and now known-good
bytes. **The grader is healthy**: 641 teams scored on 2026-10-20, the day our
control was submitted, and 87 on 2026-10-21. Our row registers 6 submissions
with the control's exact timestamp and still displays v00's 0.13.

Consequences: **v06's and v07's blanks were never evidence about those bundles**
(E013-LB's slow-bundle reading is withdrawn; P007's *local* rejection of v06
stands on its own rows). The project has had **no working leaderboard signal
since 2026-10-07**. **Do not spend submission slots** until it is fixed, and
above all do not submit v08. **Escalation needs a browser** — the competition
forum returns 403 from the CLI and the overview page is JS-rendered. This is the
project's top open item and it cannot be closed from inside the repo.

**P008 is the first intervention in this project to move an outcome metric
(2026-10-20).** `v08_decode_clamp` — v00 with `thinking_budget` 4096 -> 1024, one
knob — cut timeouts **26/60 -> 16/60** (6 gained / 16 lost, McNemar p=0.0525) and
raised `gold_hit` **29/60 -> 40/60** (15 / 4, p=0.0192) on 60 paired fastapi
tasks in one session. The mechanism is confirmed precisely: p99 completion tokens
per step fell **4,132 -> 1,308** and steps over 2048 fell **114 -> 11**, while the
*median* step was untouched (38 -> 37) — so the extreme tail collapsed rather than
everything being truncated, and the agent got **~1,300 more steps out of 11% less
total decode**.

**It is not shippable, for four reasons recorded with the result.** The 30-minute
cap *favours* v08 by construction (pre-registered); four endpoints were tested so
`gold_hit`'s p=0.0192 would not survive Bonferroni; `resolved` — the only metric
that authorizes shipping — moved by **one task** (2/60 -> 3/60) and
`stats.decide` returns **UNDERPOWERED** with a winner's-curse warning; and most
seriously, **identical v00 bytes scored `gold_hit` 36/60 in P007 and 29/60 in
P008** on the same tasks at the same cap, a swing of 0.117 that is most of the
claimed effect. Pairing cancels that for the comparison, so the result stands,
but **the magnitude is not trustworthy**.

**The bottleneck is wall clock, measured rather than inferred
(P007, read 2026-10-19).** v06_graph_coder is rejected and retired: across 120
paired task-runs its *only* significant effect was timing out more often — 35 of
60 tasks against v00's 22 (17 gained, 4 lost, McNemar **p=0.0072**). On the 21
tasks that completed in **both** arms, the only selection-free comparison
available, v00 and v06 are **exactly equal** on every metric: `gold_hit` 16/21,
`gold_exact` 6/21, `resolved` 3/21. The graph tools on the root coder change
nothing about fix quality and cost time, so that lever is dead.

**Resolution is 0.143 among tasks that finish and 0.050 overall.** 39 of 60 tasks
timed out in at least one arm, and `gold_hit` roughly halves on a timeout (0.41
vs 0.71). The local cap was 30 min against the grader's 60, so that rate
overstates the grader's — but P006 independently put v00 at 6/12 hitting a
60-minute cap, so **time binds at the grader too**. Nothing in the bundle queue
targets it: v06 spent more, and v07 adds a second agent pass that can only spend
more again.

**Three capability/topology hypotheses are now closed by measurement**, which is
the real progress of the last three runs: the sub-agent as budget sink (P006 —
mechanism removed, outcome unmoved), the root coder's missing graph tools (P007 —
exactly zero effect on completers), and context-window death as a failure mode
(P007 — **zero** occurrences in 60 v06 runs, against its MANIFEST's primary risk).
The agent's problem is not what tools it holds or how its graph is shaped.

**The leaderboard has not moved for us since 2026-09-30 and the field is moving.**
Live 2026-10-19: 3199 teams scored, we are rank **1402** with 0.13 = 8/58, down
from 785 on 2026-10-13 **on an unchanged score**. The top is still 0.24 = 14/58
(2 teams), but the population at 12–13 tasks grew about 4× in six days (0.20:
28 → 115 teams; 0.22: 8 → 29). The 6-task gap to the top is still above this
project's 0.06 evidence threshold, so it remains a real effect.

**BOTH recent submissions scored nothing, and the submission channel itself is
now the open question (T008, 2026-10-20).** v06 (57145400) and v07 (57390543)
both report `COMPLETE` with a **blank** `publicScore`. Everything submitted
before 2026-10-08 scored (v00 0.13, v01 0.08, v04 0.10); everything since is
blank. **The grader is fine** — 698 teams scored on 2026-10-19, the same day as
v07, and 9 already on 2026-10-20. Our leaderboard row registers 5 submissions
with v07's exact timestamp and still shows v00's 0.13.

The earlier v06-specific explanation — that a measurably slow bundle stretched
its evaluation — **does not survive a second case**, because v07 is structurally
unrelated. Four candidate causes were checked and eliminated: our packaging
(unchanged since 2026-10-06, the code that produced all three scored
submissions), organizer `generation_constraints` (v06 and v07 use sampling
byte-identical to v00's, which scored), rejection of a non-`LlmAgent` root
(`SequentialAgent` is explicitly wired into the compiler at
`adk_submission__compiler.py:146`), and a dangling `!include` in v06 (its path
resolves, and P007 ran it for 60 tasks). One systemic change after 2026-10-07 is
more parsimonious than two coincidental faults — **but that is parsimony, not
evidence.**

**A control is in flight: E015, ref 57430290**, `v00_public_baseline` byte-identical
to the submission that scored 0.13 on 2026-09-30. **Scores 0.13 ⇒ the channel
works and the fault is bundle-specific; blank ⇒ the channel is broken for this
account and no further submission is worth sending.** Read it as *scored vs
blank*, not as a v00 re-measurement.

**Twelve submission days have now been wasted**, six before 2026-10-13 and six
after. Each is a free 58-task sample of the real metric — with the caveat P007
adds, that it is only free if the bundle is fast enough to finish.

Measurement infrastructure is built and calibrated: `clean-N = 102` of 129 public
tasks, frozen in `data/tasks/clean_n.txt`. **231 tests pass in ~5 s with no GPU.**
GPU **45.00 h of 45.00 remaining, refreshing 2026-10-24** — a full untouched
window, and P007's 6 GPU-h was recovered for free from a batch run's committed
output five days after it finished.

## Last session (2026-10-27)

**Paper track, 0 GPU-h.** Chosen over a GPU run deliberately: the paper deadline
(2026-11-12) is 16 days out, the main deadline is 36, and the local resolution
metric is still broken, so GPU spend would buy unreadable rows.

- **Trimmed the manuscript 3,265 → 2,922 body words** in five asserted
  exact-match passes, §D as the designated donor (1,010 → 946) and §§F/G/H
  protected as the sections the rubric pays most. Removed three cross-section
  duplications rather than polishing them: the third-party score triple, the
  "floor moved" finding (told three times, now §G with cross-references), and
  §E's D4 bullet. Em-dashes set closed so a naive word counter does not score
  them as words. All three counting bases are recorded in the manuscript header.
- **Audited every number in the paper against primary sources** and fixed ten
  errors. The two worst: a misreported pre-registration (§E) and a histogram
  total read as a positive-score count (§B, §D0, twice in the paper's most
  quotable sentence). Full table in `EXPERIMENTS.md`.
- **Corrected the one-sided McNemar p repo-wide.** `mcnemar_exact(3,1)` returns
  **0.625** two-sided; 0.3125 is the one-sided tail and appeared in 7 places
  across `LESSONS.md`, `paper/OUTLINE.md`, `stats.py` and `tests/test_stats.py`.
  All corrected, provenance noted at the canonical source. No assertions
  involved; suite unchanged at 302 passed, 3 skipped.
- **Verified live:** quota, submissions, wheelhouse `lastUpdated`
  (2026-10-12 19:51:31, unchanged — P006–P009 still mutually comparable), tests.

**What was learned**

- A pre-registration is a file, not a memory. I narrated the *concept* of D5 from
  an outcome that went the wrong way, without re-reading which branch had been
  registered — in the section describing D5.
- When prose quotes a number the repo also computes, get it by calling the code.
  `leaderboard.py` filters `> 0` correctly; the sentence did not.
- `ledger/runs/clamp_*` and `cap60_*` carry **no** `patches/` and no test logs, so
  the 73%/76% mismatch rates and the byte-identical-gold finding are **not**
  re-derivable from this repo. `HANDOFF.md` §4 had claimed "the 103 patches behind
  T011" live there. They do not exist anywhere in the tree.

**Open issues**

- v10 still PENDING; nothing can be concluded from it yet.
- `clean_n` is still stale. No GPU spend is justified until it is re-derived.
- The paper is drafted, not submitted. That is the single highest-value remaining
  action and it costs no compute.

## Last session (2026-10-19)

- **Recovered P007 from a finished run nobody had read.** It completed
  2026-10-14 and its output sat untouched for five days. Because it was a
  **batch** run, `/kaggle/working` was committed and `kaggle kernels output`
  returned all 120 rows intact at **0 GPU-h**. Banked at
  `ledger/runs/graph_v0{0,6}/`.
- **Read it, and rejected v06.** Identical quality, significantly more timeouts.
  Full numbers in EXPERIMENTS.md "P007 RESULT"; MANIFEST carries a `retired:`
  block.
- **Caught a selection-bias trap in my own first reading of it.** Splitting by
  "did the task finish" made v06 look better (gold_hit 0.760 vs 0.711). That
  split variable is *downstream of the treatment* — v06 causes the timeouts — so
  it compares an easier subset against a harder one. Restricting to the 21 tasks
  that completed in both arms collapsed the effect to exactly zero. Recorded in
  LESSONS.md; it is this project's eighth wrong-contract number.
- **Established that v06's submission scored nothing at all**, not merely late,
  and that a scoreless `COMPLETE` does not block the queue.
- **Refreshed the leaderboard** and found rank 785 → 1402 on an unchanged score.
  The 2026-10-13 snapshot that `analyze_leaderboard.py` defaults to is now
  stale; pass `--snapshot` or refresh it.
- **Submitted v07_verify_repair** (ref 57390543) after establishing that the
  rule gating it on v06's score had lost its referent.
- **What broke / open issues:**
  - The v06 blank score has no confirmed cause, only a well-evidenced candidate.
  - `data/leaderboard/` has no 2026-10-19 snapshot committed yet; the live one
    was built in the scratchpad.
  - **No bundle in the queue targets wall clock**, which is now the measured
    binding constraint. v07, already submitted, pushes the wrong way on it.
  - `resolved` remains UNDERPOWERED at k=1 (detectable +0.064 vs a 0.050
    target), so every flat resolution reading means "not measured".

## Last session (2026-10-20)

- **v07 also scored nothing**, and that kills yesterday's explanation. v06's
  blank had been attributed to that bundle being slow; v07 is structurally
  unrelated, so one bundle's slowness cannot account for both. Everything
  submitted before 2026-10-08 scored; everything since is blank. **The grader is
  healthy** — 698 teams scored on 2026-10-19 and 43 on 2026-10-20. T008 records
  four candidate causes checked and eliminated.
- **Control submitted (E015, ref 57430290):** `v00_public_baseline`, bytes
  identical to the submission that scored 0.13. Read it as **scored vs blank**.
  As of 14:42 UTC it was still `PENDING` and **not yet due** — the scoring queue
  is ~7.5 h behind (the latest scored submission today was sent at 07:08 UTC,
  ours at 08:46), so six hours pending is normal, not a third blank.
- **Built `v08_decode_clamp` (E016)** — `thinking_budget` 4096 → 1024, single
  knob, `bundle_hash 26354b2d0153378d`. The value comes from the per-step
  completion distribution (p50=40, p90=625, p99=4,123), where a clamp at 1024
  touches 6.1% of steps and removes ~29.6% of decode.
- **Ran P008 and read it the moment it finished** — the fix for the mistake that
  cost five days last week. A watcher polled for the terminal state and the
  output was fetched at 20:17 UTC. **Result: the first outcome movement this
  project has recorded** (see Current status). **It cost 10.57 GPU-h against my
  stated ~6** — a 1.76x overrun, because the estimate priced wall-clock waves and
  quoted them as GPU-hours. On L4x4, budget ~2 GPU-h per wall hour. Recorded in
  LESSONS.md.
- **Launched P008** (`swegemma-clamp-ab`, estimated ~6 GPU-h, actual 10.57):
  v00 vs v08, 60 tasks, 30-min cap, one session. Primary endpoint is the
  **timeout rate**, which is the only endpoint this project has moved detectably
  at affordable k. The 30-min cap is forced by KV arithmetic, and its bias
  **favours v08** — the opposite of P007's — which is pre-registered.
- **Untracked `.vscode/settings.json`**, which `git add -A` had swept into the
  v08 commit. It is machine-specific editor state; `.vscode/` is now ignored.
- **What broke / open issues:**
  - **The submission channel is the project's biggest open risk.** If E015 comes
    back blank, no submission is worth sending and the forum must be reached in a
    browser (the CLI returns 403 for competition forums).
  - P008 was still `QUEUED` with 0 GPU drawn ~5 min after the push. Normal for
    allocation, but **self-blocking looks identical** — confirm it left the queue
    before assuming it ran.
  - v08 is unsubmitted and must stay so until E015 reports.

## Next steps (prioritized 2026-10-19 — supersedes both older "Next steps" sections below)

The two older lists further down are kept as dated records. They are stale:
their top items are hypotheses P006 and P007 have since closed.

1. ~~**Diagnose where the wall clock goes, from P007's traces.**~~ **DONE
   2026-10-19 — T007, 0 GPU-h.** It is **decode**: pooled over 120 task-runs,
   corr(completion tokens per step, seconds per step) = **+0.968**, while the
   same correlation for *prompt* tokens is **negative** (−0.44). Timed-out tasks
   generate 712 completion tokens per step against completed tasks' 212, and run
   at 50.6 s/step against 16.5. Prompt tokens per step are the same in both.
   Verbosity buys no quality: across verbosity quartiles time rises 10.6 → 58.4
   s/step while `gold_hit` falls 10/15 → 7/15. Two hypotheses were tested and
   killed — context growth (prompt tokens are 97% of all tokens but correlate
   *negatively* with latency) and our own `concurrency: 12` (timed-out tasks had
   *less* contention, median 9 vs 11). Instrument:
   `scripts/analyze_wall_clock.py`.

   **So the next bundle is specified, and it is the first one aimed at the
   constraint known to bind:** clamp tokens generated per step
   (`thinking_budget` / `max_output_tokens`) toward the Q1 regime of ~130
   completion tokens per step, changing nothing else. It must be a **single-knob**
   test, which this project normally avoids and here should not, because T007
   licenses the timing half mechanically but *not* the claim that clamping
   preserves quality — that is precisely what is unknown. Note v01 and v04 both
   moved these ceilings and scored below v00; neither is evidence against this,
   since v01 bundled 11 changes and v04 had no mechanism in mind, and neither was
   measured locally.

2. **Spend the remaining GPU window on `k` for v08, not on another bundle** —
   `stats.decide`'s own instruction. **34.43 GPU-h remain and expire
   2026-10-24.** Budget at **~2 GPU-h per wall hour** (P008 cost 10.57 for 5.3 h
   wall; the earlier ~6 estimate priced waves and quoted them as GPU-hours).
   Two shapes, and the choice is a real one:
   - **Replicate P008's shape** (60 tasks, 30-min cap, ~10.6 GPU-h) -> takes v08
     to k=2 and directly tests whether the `gold_hit` gain replicates. Attacks
     the **worst** caveat, the unstable v00 baseline.
   - **Run at the grader's 60-min cap** on ~36 tasks (3 waves, ~13.6 GPU-h) ->
     tests whether the gain survives when the cap no longer favours v08. Attacks
     the caveat that matters for the **leaderboard**, since the grader runs 60
     min and P006 put v00 at 6/12 hitting it.
   Both fit the window (24.2 of 34.43 h). Replication before generalisation is
   the conventional order, but the 60-min question is the one that decides
   whether this bundle is worth anything on the grader.

3. **BLOCKED ON THE CONTROL (E015, ref 57430290) — read it before submitting
   anything.** The 2026-10-20 slot went to the control, not to a bundle. If it
   comes back **blank**, stop submitting entirely and escalate; building bundles
   is pointless until the channel is known to work. If it **scores**, resume at
   the item below and keep a plain `LlmAgent` root.

   **Then: build the T007 decode-clamp bundle and
   ship that if it is ready; otherwise ship `v05_no_analyzer`.** The decode clamp
   is the better-motivated of the two — it targets the mechanism T007 measured,
   where v05 targets a sink whose cost is presumably decode anyway. Both are
   speed plays; only one slot exists per day.

   **Submit `v05_no_analyzer`** (`5f47540cdfb9bf01`, built,
   validated, never submitted). **P007 reframes it from a null into the one
   speed candidate already in hand.** T005 measured the `code_analyzer`
   sub-agent as a **wall-clock sink** — 636.5 vs 371.2 summed minutes — while
   being charged as a single tool call, and P006 found removing it changed
   outcomes not at all *at n=12, which was underpowered*. If time is what binds,
   deleting a wall-clock sink should raise the completion rate and therefore
   resolution, through a mechanism that did not exist in P006's reading.
   Run `python scripts/push_dataset.py` first if it is also to be measured.
   0 GPU-h. Note it inherits v04's sampling ceilings, so it is not clean against
   v00.

3. **Spend the GPU window on power, not on another bundle.** 45.00 h, refreshing
   **2026-10-24** and not carrying over. `stats.decide` has returned
   UNDERPOWERED on `resolved` for every run this project has done, so another
   k=1 A/B ranks nothing however good the bundle is. Two defensible shapes, and
   the choice is open:
   - **k=2 at the grader's real 60-minute cap**, which measures the thing that
     actually ships and makes timeout rates comparable to P006; or
   - **k=1 at 60 min on a larger task set**, which buys localization power and
     a clean timeout baseline but still cannot adjudicate `resolved`.
   **Do not reuse P007's 30-minute cap for anything meant to generalise**, and
   do not compare new rows against P007's — different cap, not a time series.

4. **Keep every submission day.** Twelve are gone. ~44 remain, one per day.
   After v05: a **no-sub-agent topology with `max_tool_calls: 200`** (T005
   reopened this for that topology specifically, where calls bind and time does
   not). With the P007 caveat: **cost a bundle's wall clock locally first** — a
   slow bundle can return `COMPLETE` with a blank score, as v06 did, which
   spends the slot and buys nothing.

5. **Commit a 2026-10-19 leaderboard snapshot** and point
   `analyze_leaderboard.py`'s default at it, or make the default refuse to run
   on a snapshot older than a few days. It silently printed 6-day-stale numbers
   this session.

6. **Paper, secondary** (due 2026-11-12). §D is banked. P007 adds a genuinely
   publishable methodological result: a treatment that *causes* the conditioning
   variable, where the naive subgroup read reverses the sign of the conclusion.
   Order B → C → F → G → H → E → A. Still blocked on reading the word cap and
   five criteria off the JS-rendered overview page in a browser.

## Last session (2026-10-12)

**Done.**
- Launched **P003 `resolve60`** — the gating rig check. **It failed in 14 s**
  (`ModuleNotFoundError: swegemma.models.discovery`) and answered nothing, for
  0.23 GPU-h. Required parameterising `scripts/make_eval_kernel.py`: run shapes
  are now named entries in `CONFIGS`, each owning its arms, caps and kernel id,
  so generating one cannot overwrite another's Kaggle history. Verified
  behaviour-preserving — regenerating `paired100` leaves its metadata
  byte-identical and changes only the `run_id` indirection.
- **Diagnosed it and found the replacement API for 0 GPU-h (P004).** The
  competition **republished the wheelhouse 2026-10-09 14:43**; the wheelhouse is
  a *dataset*, so no pin of ours freezes it. A new CPU kernel
  (`kernels/13_harness_api`) reads all 165 wheels as zip archives without
  installing anything: `validate_single_declared_model` is gone from every wheel,
  and `adk_submission` has gained `discovery.py` exposing
  `discover_declared_models`. Corrected two false claims in `CLAUDE.md` and made
  the preflight gate mirror `start_server()`'s imports exactly.
- **T001**, 0 GPU-h: re-read the P002 v00 traces per author. **657 of 1,040 calls
  (63%) belong to `code_analyzer`, from 19 invocations** — ~35 calls each against
  a 100-call budget shared with the coder. 3 of 12 tasks never called
  `submit_patch`.
- **Built `v05_no_analyzer`** (E012), validator PASS, `bundle_hash
  5f47540cdfb9bf01`. Not submitted.
- **Chose the paper thesis and wrote `paper/OUTLINE.md`** — measurement
  methodology, with a full evidence map and the rejected framings recorded.
- **Applied the Asana backlog** that had been queued since 2026-10-06 (connector
  was offline for two sessions, available now). Six stale tasks closed with
  result comments, four filed, paper moved to In progress.
- **S001: fixed a vacuous ship rule** after an adversarial review of the
  session's own decisions. `stats.decide` demanded a significant positive
  resolution delta, which is unreachable at any affordable `k` (detectable delta
  0.064 at k=1, 0.045 at k=2, against a 0.05 design target), so HOLD was carrying
  both "did not help" and "could not measure". Added the `UNDERPOWERED` verdict;
  suite 191 → 198. **This re-labels P002: its HOLD was really UNDERPOWERED**, and
  `report.py` now says the operative thing out loud — "this run ranked nothing;
  spend the next allocation on k, not on another bundle."
- **Bounded v05's claims in its MANIFEST.** 9 of 12 tasks submitted a patch and
  still failed, so budget exhaustion caps this bundle's upside at ~a quarter of
  observed failures; and its own loop-migration argument cuts against it, since
  the coder keeps `run_command`.
- **Un-gated the paper.** §E's fallback prose is written (464 words of a 500
  budget) with the k=4 reference as an upgrade, and the power arithmetic is now a
  protocol component in its own right.
- **Ported the moved harness API and published it.** `session_runner` uses
  `adk_submission.discover_declared_models`; `_single_declared_model` re-adds the
  exactly-one-model rule the deleted harness call used to enforce. Also fixed the
  preflight gate added earlier the same day, which still imported the *deleted*
  symbol and would have failed the run it exists to protect. Dataset republished
  and verified before launching.
- **Ran P005 (~2.02 GPU-h): the first clean run at the grader's real budget.**
  Result and funnel above.
- **Fixed two measurement bugs P005 exposed.** `ingest_probe` listed patch files
  and never saved them, so **every hygiene metric was structurally uncomputable
  on every ingested run in this project's history**; and `Panel` printed `0.0%`
  for metrics it could not compute, giving a clean bill of health on scratch
  leakage while half the tasks were creating files. Panels now print
  `n/a (needs patches)` and `waste_rate` returns `None`. Suite 202 → 206.

**Learned.**
- **A decision rule's reachable outputs matter as much as its correctness.** The
  ship rule could only ever say HOLD, and I had been reading that as evidence of
  no effect. The right response to P002 was to buy `k`; what the session did
  instead was build another bundle. See `LESSONS.md`.
- **When a critique is right about the problem it is not automatically right
  about the remedy.** The reviewers wanted the ship metric switched to
  localization because it is affordable; `report.py`'s own docstring already had
  the rebuttal — optimizing a surrogate wins the surrogate. The fix belonged in
  what the verdict *means*, not what it keys on.
- **The planned v05 was wrong, and checking cost five minutes.** HANDOFF
  specified removing `run_command` from the analyzer. Two facts killed it: the
  loop is not specific to `run_command` (three tasks loop on `read_file`, one 75
  times, so removal displaces it), and `search_similar_code` is **not** a
  free-text search — `HARNESS_README.md:497`, no live embedding server, the query
  resolves against node keys. v05 removes the AgentTool instead, which keeps
  `grep` with the coder and loses the agent no capability. See `LESSONS.md`.
- Paper-track entry reportedly does **not** require a main-track submission,
  which resolves README open question #5 — **unverified**, Kaggle's pages are
  JS-rendered and could not be read programmatically.

**Open issues.**
- **`scripts/session_runner.py` has a broken import** and no GPU run can succeed
  until it is fixed *and the dataset re-pushed* — the kernel runs the dataset's
  copy, not the repo's. The resolve question is still unanswered.
- The paper's format facts (~3,000-word Writeup, five 0–5 criteria) are
  **unverified** and need a browser check.
- `resolve-check`'s `kernels pull -m` reported `docker_image: ""`, which by this
  project's own rule means the environment pin did not register. Harmless for a
  single-arm run (the pin buys stability *between* arms) but must be re-checked
  before any paired run.
- Two findings from T001 unexplained: `fastapi_11194` called `submit_patch` 117
  times against a harness that documents immediate termination, and ledger
  `tool_calls_used` undercounts (30 logged vs 173 in trace). Both filed in Asana.

**Next steps (prioritised).**
1. Fix `session_runner`'s import to `adk_submission.discover_declared_models`,
   keeping the "exactly one declared model" assertion the old call made, push the
   dataset, and re-launch `resolve60` unchanged otherwise.
2. If it resolves: re-price and buy E003, the k=4 reference on clean-N.
3. Draft the paper sections that cannot change (D -> B -> C -> F -> G -> H).
4. **Buy `k` before building another bundle** — the instrument now says this in
   its own output. A k=1 run ranks nothing, on resolution or on localization.
5. Measure v05 locally. **Do not submit it on the hypothesis**, and read
   re-issue rate and calls-by-author rather than only the rates.
6. Attack patch quality, which is ~3/4 of observed failures and which no bundle
   so far has touched.

## The agent starves its own coder (2026-10-06)

The operative finding, and it cost 0 extra GPU-h. Mining the twelve `probe_c12`
traces call by call shows that **259 of 491 tool calls were made by the
read-only `code_analyzer` sub-agent, not by the root coder** — and sub-agent
calls draw on the root agent's single budget. In 4 of 12 tasks the coder got
**1 to 4 calls** before the budget was gone. `fastapi_11355` is the clean case:
the coder made exactly one call, invoking the analyzer, which then ran
`grep -rn "get_type_hints" .` **verbatim 14 times in a row** until all 30 calls
were spent. The coder never read a line of source.

So the dominant failure — half the tasks produced no patch — is **starvation,
not truncation**. Three consequences:

1. **The paired 100-call run's main question is already answered, for free.** It
   asked whether the four empty-patch tasks were merely truncated at 30 calls.
   They were not. At 100 the analyzer loops 100 times instead of 30.
2. **`v02_context_budget` fixes the second-order problem.** Its split sampling
   ceilings do address the two `ContextWindowExceededError` deaths — both of
   which are sub-agent floods — and the arithmetic checks out (v00 ships one
   `sampling.yaml` at 8192 output for both agents, and the error is exactly one
   token over: 24577 input + 8192 output = 32769). But nothing in v02 limits how
   much budget the analyzer may spend.
3. **The call budget is not reliably enforced.** `fastapi_14258` is logged at 30
   calls; the trace holds **173**, with 135 `edit_file` calls, an unbroken run of
   82, and 134 verbatim re-issues of one failing edit. The 10-minute timeout
   stopped it, not the budget.

Full table and the candidate changes are in `EXPERIMENTS.md`. The resolution
correlation is n=2 and is **not** treated as evidence; the mechanism is
established, its effect size is not.

## Colab: cannot measure, can still be useful (2026-10-06)

Settled by arithmetic, not opinion, so it does not get re-litigated. Weights
plus overhead take ~26 GB across 4 GPUs (~19–20 GB on one, without TP buffers);
the grader's 32,768-token context needs 39 GB more of KV at 1.21 MB/token.
Derived from our own engine log: 55,616 KV tokens on 92 GB.

| Host | VRAM | Loads weights | Context |
|---|---|---|---|
| Kaggle L4×4 | 92 GB | yes | 55,616 |
| Colab free T4 | 16 GB | **no** | — |
| Colab Pro L4 | 22.5 GB | barely | ~2k |
| Colab Pro A100 | 40 GB | yes | ~12–17k of 32,768 |

A100 is the only tier that loads it, and its context sits **below** the 14,336
compaction threshold, so the agent's memory behaviour would differ from the
grader's. **No Colab tier can produce a comparable number.**

What Colab *can* do is **surrogate mode** — a small tool-calling model served
under the competition's model name, exercising the bundle, agent graph, tool
loop and patch extraction. `start_server` already aliased the declared name onto
whatever is served, so the bundle stays byte-identical and still validates.
`notebooks/04_colab_surrogate.ipynb` runs it in fail-fast stages; stage 2 (can
the wheelhouse install at all) is the gate, because the Kaggle T4 failure was a
cp312-vs-3.13 mismatch and Colab could repeat it.

The safety property mattered more than the feature: a surrogate run uses a
byte-identical bundle and therefore the **real** `bundle_hash`, so its rows
would have pooled straight into the reference arm. Rows now carry
`surrogate=True`, `pool_by_bundle` drops them by default, and a non-`gemma4`
parser without `--surrogate` is refused — the wrong parser emits zero tool calls
and looks exactly like a model that will not act.

## Last session (2026-10-06)

**Done**

- Submitted `v01_hygiene` (ref 56875884, pending). This **bypasses the ship
  rule** in `stats.py`, which requires a significant local delta first; it is
  recorded as a deliberate deviation in the MANIFEST and in `EXPERIMENTS.md`,
  justified only by the hardware block.
- Wired gold-file localization into a first-class report, `scripts/report.py`.
- Closed the gap that would have made it useless: the gold-overlap flags are now
  computed at write time and stored on the ledger row.
- 135 tests passing (18 new).

**Learned**

- **The co-primary metric was not actually recoverable.** `metrics.py` computed
  gold-file overlap from the patch text, but patches live in the swegemma
  results directory, which does not reliably come back from a Kaggle session,
  while the ledger always does. A metric that can only be computed where the
  data is ephemeral is not a metric. Now stored per row.
- `metrics.load_outcomes` read the ledger's `wall_seconds` as `0.0`, because it
  only looked for `duration_seconds` / `wall_s`. Silent, and it would have made
  every wall-clock figure in a re-read panel zero.
- On a synthetic ledger with a true +0.05 effect, resolution at k=2 vs k=4 gave
  z=+0.30 while localization gave z=+2.01. The surrogate's whole case,
  demonstrated rather than asserted.

**Open**

- Still no L4x4. Three hours of queue on *both* L4 and T4 points at something
  account- or region-level rather than L4 scarcity, since T4 is normally
  plentiful. Worth checking the Kaggle account page for a verification notice.
- Quota moved 2.48 → 3.06 h with no kernel `lastRunTime` change, which is most
  likely an interactive session: those consume quota and persist no output.

## Last session (2026-10-01)

**Done**

- Harness recon on a CPU kernel: captured all 642 harness source files for 0 GPU-h.
  Found three errors in the shipped `HARNESS_README.md`, two of which score 0.00.
- Built and calibrated the eval instrument over four CPU runs: 74 → 74 → 105
  gold resolutions, landing on `clean-N = 102`.
- Shipped `v00_public_baseline` → **0.13**.
- Built `v01_hygiene` (11 mechanism-motivated changes) — built and validated,
  not yet measured.
- 116 tests passing; `session_runner.py` ready but never yet run on GPU.

**Learned** (see `LESSONS.md` for the mistakes)

- `install_test_dependencies` is a no-op in subprocess mode, which is the only
  backend Kaggle offers. But that was *not* the binding constraint — two absent
  test-only packages (`inline_snapshot`, `dirty_equals`) were, costing 34 tasks,
  because one collection error aborts the whole pytest invocation.
- The remaining 24 failures are **dependency version drift** and are irreducible:
  the grader's pinned wheel cache is in a private dataset. `/wheels` holds only
  41 distinct packages.
- Consequence: **gold-file localization is co-primary metric.** It needs no test
  execution, works on all 129 tasks, and sits near p=0.45 vs p=0.15.

**Open issues**

- `clean-N` is fastapi 60 + rich 42. **requests 0 and httpx 0** — the audit split
  is gone, so the generalization guard now rests on rich-vs-fastapi only.
- Whether `eval_config.yaml` can *raise* the 60 min / 100 call ceiling is still
  unknown and not answerable from the public wheelhouse. Needs a probe submission.
- `session_runner.py` has never run. Its concurrency, deadline guard and vLLM
  startup are untested against real GPU.

## Measurement is blocked on a dependency ABI, not on quota (2026-10-07)

38 GPU-h are available and **nothing has been measured**. Four attempts, and the
diagnosis moved each time — recorded in full because three of the four
intermediate conclusions were wrong:

| # | Symptom | Conclusion drawn | Correct? |
|---|---|---|---|
| 1 | two empty result dirs, 34 s apart | unmet `inline_snapshot`/`dirty_equals` gate | **yes** — fixed by vendoring the wheels |
| 2 | batch queued then cancelled | "batch does not work on this account" | **no** — it was an image rollover |
| 3 | `cp313` vs cp312 wheelhouse | "pin the environment to get 3.12 back" | **no** — `original` pins today's image |
| 4 | `vllm/_C.abi3.so: undefined symbol` | **torch 2.11.0 vs the required 2.10.0** | believed correct; fix in flight |

**The actual blocker.** Wheelhouse `vllm-0.19.1` declares `torch==2.10.0`;
Kaggle's image ships `torch 2.11.0+cu128`. `abi3` pins the Python ABI, not the
C++ one, so the prebuilt vLLM will not link against the image's libtorch. Its
`Requires-Python` is `<3.14,>=3.10`, so **Python 3.13 was never the problem** —
the cp313 overlay was necessary but fixed a different axis.

**Everything upstream of that now works**, which is real progress: L4×4 allocated,
41/41 wheels resolved against the cp313 overlay, harness preflight PASS, test-dep
staging self-heals by following the actual import chain.

**Fix in flight.** `kernels/12_fetch_torch` — a **CPU kernel with internet** —
downloads `torch-2.10.0+cu128-cp313` (917 MB) and its pinned `nvidia-*` deps; the
GPU kernel consumes that kernel's output via `kernel_sources`. No GPU quota, no
local bandwidth. Internet is forbidden only *with* the premium accelerator, which
is precisely why the split works.

**What this episode cost and what it bought.** ~4 GPU-h of the week's 45, all of
it on environment rather than on the agent. In exchange, five gates now fail in
seconds instead of after an allocation: Python/wheel satisfiability, torch
version, `vllm._C` linkage, the test-dep import chain, and the harness preflight.
The project's instruments got better; its measurements did not advance.

## Next steps (prioritized)

Reordered 2026-10-06 by the trace finding: the cheapest remaining wins need no
GPU, and the run that was set up is no longer the top item.

1. ~~Build `v03_budget_guard`.~~ **Done 2026-10-06** — E009,
   `bundle_hash 5d9e0acc8a81cc73`, validates PASS with no findings, not yet
   submitted. **A hard per-sub-agent cap turned out not to be expressible** in
   the declarative format: `eval_config.yaml`'s budgets are session-global,
   `LoopAgent.max_iterations` does not apply to an `AgentTool`, and no Python may
   ship. So v03 is the prompt-level version, and its central risk is evidenced
   rather than hypothetical — the harness injected a `budget_warning` into the
   analyzer's responses **11 consecutive times** in `fastapi_11355` and it
   re-issued the same grep every time. **Decision pending:** whether to also
   remove `run_command` from the analyzer's `tools` list, which is the only
   *enforced* lever and would make the observed loop structurally impossible, at
   the cost of the analyzer's only text-search capability.
2. **Paired 100-call run on the same 12 tasks** (~1.0-1.6 GPU-h) — kept, with its
   purpose narrowed. Question 1 (were the empty-patch tasks truncated?) is
   answered: no. What it still buys is **per-task cost at the grader's budget**,
   which the k=4 reference plan needs and currently underprices by ~3x, and a
   check that v02's ceilings remove the two context deaths. Arms should be v00
   and `v03`, not v00 and v02, if v03 exists by then.
3. **k=4 reference run** of `v00` on clean-N (~12 GPU-h, repriced after step 2)
   → strata, `fast-48`, empirical noise floor. The paper's headline number.
4. **Measure the best variant** at k=2 against that reference.
5. Probe the budget ceiling with one submission declaring `max_tool_calls: 200`
   (E008) — now lower value than it looked, because the trace shows the existing
   ceiling is not reliably enforced anyway (`fastapi_14258`: 173 calls logged as
   30). Worth one submission, not priority.
6. Start the paper (due 2026-11-12). Substance in hand: the CPU-only calibration
   protocol, the measured noise floor, the dependency-drift floor, the catalogue
   of undocumented harness behaviour, and now a per-call anatomy of where an
   agent's budget actually goes — which is a result in its own right.

## Asana updates pending (2026-10-19 — connector not available this session)

No Asana MCP tools were present in this session and it is non-interactive, so
OAuth could not be run. Apply these when the connector is back (project
`1219068188815270`):

- **Close** "P007: v00 vs v06 at n=60" — result: v06 **rejected**. Identical
  quality on the 21 tasks completing in both arms (gold_hit 16/21 both), only
  significant effect is more timeouts (35/60 vs 22/60, McNemar p=0.0072).
  Link EXPERIMENTS.md "P007 RESULT". 6 GPU-h, recovered at 0 GPU-h.
- **Close** "Submit v07_verify_repair" — done 2026-10-19, ref 57390543, PENDING.
- **Close** "Read v06's leaderboard score" — resolved as *no score exists*:
  `COMPLETE` with a blank `publicScore` after six days. A scoreless submission
  does not block the queue.
- **Add to Done** "T007: locate the wall-clock cost" — decode, r=+0.968,
  `scripts/analyze_wall_clock.py`.
- **Add to To do (next slot)** "v08: clamp generated tokens per step toward
  ~130 completion tok/step, single knob" — the first bundle aimed at the
  measured binding constraint.
- **Add to Backlog** "Commit a fresh leaderboard snapshot weekly" — the default
  snapshot silently printed 6-day-stale numbers this session.
- **Add to Backlog** "Cost a bundle's wall clock locally before spending a
  submission slot" — v06 spent a slot and returned no score.
- **Comment on the project**: rank 785 → **1402** of 3199 on an unchanged 0.13;
  the field at 12–13 tasks grew ~4× in six days while the top stayed 14/58.

## Decisions & rationale

- **Kaggle-only execution** — local GPU is an MX550 2 GB with no Docker, so the
  31B model cannot run here at all (2026-09-30).
- **No LoRA training** — only data is 129 gold patches from 4 repos, which is
  the overfitting trap that scored a competitor 0.05. Revisit only if the LB top
  jumps past 0.30 (2026-09-30).
- **Paper track in scope** — 76 entrants vs 1037, and its ablation table *is* the
  main track's experiment backlog, so it costs no extra runs (2026-09-30).
  *Counts refreshed 2026-10-13: **205 paper-track vs 2643 main-track teams**. The
  ratio holds, so the decision stands; the original figures are left as written
  because they are the rationale as it was made.*
- **Measurement budgets ≠ scored budgets** — keep the real 100-call ceiling, but
  disable the wall clock locally, so CPU contention under concurrency cannot fail
  a task for reasons unrelated to the config under test (2026-09-30).
- **Accept the 24-task version-drift floor** — chasing parity with a private
  wheel cache is unbounded with no verification signal (2026-10-01).
- **Localization promoted to co-primary** — immune to the test-environment
  problem entirely (2026-10-01).

## Asana updates pending (2026-10-12, connector dropped mid-session)

The connector worked earlier in this session and then returned "not connected".
Applied before it dropped: the import-fix task closed, `resolve60` moved to In
progress, and two new tasks filed ("Buy k before building another bundle",
"Attack patch quality"). **Still to apply:**

- **`resolve60` → Done**, with the P005 result: 0/12 at the grader's full budget,
  the funnel (5 no patch / 2 scratch-only / 4 contaminated / 1 clean), and 50%
  created-file, 33% scratch-leak.
- **E003 (k=4 reference) → stays blocked, and the reason changes.** It was
  waiting on hardware, then on `resolve60` returning non-zero. It returned zero,
  so buying it would purchase four samples of zero for ~6 GPU-h. Re-block it on
  the patch-quality work.
- **"Attack patch quality" → In progress and promoted to top priority**, with the
  funnel as its evidence and the structural candidates (remove `write_file`;
  a verify step that reverts stray paths before `submit_patch`).
- **New Backlog task: "Re-ingest historical runs to recover hygiene metrics"** —
  `ingest_probe` never persisted patches, so every past run's created-file,
  protected-path and scratch-leak figures are missing rather than zero. Recoverable
  only where the results zips survive.

## Asana updates applied 2026-10-12 (earlier backlog, cleared)

The block that sat here from 2026-10-06 has been **applied**; the connector was
available again this session. What was queued and what happened to it:

| Queued item | Outcome |
|---|---|
| New task: v03 — cap or remove `code_analyzer` | **Superseded.** v03 capped it with prompt rules and was measured not to work. Filed instead as "v05_no_analyzer: remove the code_analyzer AgentTool". |
| Paired 100-call run: rewrite description, arms v00 vs v03 | **Overtaken** — the run happened (P002). Its successor `resolve60` is filed as its own task. |
| New Backlog: ledger `tool_calls_used` undercounts | filed |
| New Backlog: check whether prefix caching is actually on | filed |
| Close the trace-mining task | already closed |
| Move "diagnose the GPU allocation block" out of In progress | **closed** with a comment: the block was transient; the real cause was the Python 3.13 image rollover |

Also closed with result comments, having gone stale: E002 (v01 LB result, 0.08),
E004 (measure v01 at k=2 — retired, v01 abandoned), E007 (eval_config budget
probe — retired for free by the budget-anatomy finding), "capture the exact L4
save-and-run error" (superseded by the CLI push path), and the Colab surrogate
task (answered without Colab).

## Asana

**Project:** [Gemma 4 Developer Agent](https://app.asana.com/1/1219060299047277/project/1219068188815270)
(gid `1219068188815270`) — created 2026-10-01, synced with this file.

Sections: Milestones / Backlog / To do / In progress / Waiting-blocked / Done.
Two milestones: **paper track 2026-11-12**, **final submission 2026-12-02**.

Asana holds status, priorities and deadlines. Technical detail stays here and in
`EXPERIMENTS.md` / `LESSONS.md` rather than being copied over, per workspace
`CLAUDE.md` §12.

Still to create: a **"Project ideas / planned"** project for the other ~18
folders in `e:\Kaggle` (tracked as a Backlog task).

**Synced 2026-10-06.** Board now reads:

| Section | Tasks |
|---|---|
| In progress | E007 budget probe (due 10-07); diagnose the GPU allocation block |
| To do | paper manuscript (due 11-05) |
| Waiting / blocked | E003, E004, concurrency probe, CPU verification pass, E002 LB result, GitHub MCP |
| Done | localization report, + 6 earlier |

Four tasks moved to *Waiting / blocked* in one go, which is the honest shape of
the project right now: everything on the critical path needs an L4x4 and none
has been granted since 2026-10-05. The two items in *In progress* are the only
work that does not. E003's due date was left at 10-08 rather than pushed out,
because moving it would hide the slip.

## Time spent (rough)

| Task | Time |
|---|---|
| Research, plan, competition recon | ~3 h |
| Validator + builder + stats + metrics + ledger (116 tests) | ~4 h |
| Harness recon + reading harness source | ~1.5 h |
| Eval calibration (4 runs + diagnosis) | ~3 h |
| Localization report + ledger durability | ~1 h |
| Paper thesis, evidence map, outline | ~1 h |
| P003 failure diagnosis + API probe (0 GPU-h) | ~1 h |
| **GPU-hours used** | **0.23 h** of 45/week this week; 44.77 h remaining (`kaggle quota`, 2026-10-12) |

Against the 9-week timeline we are at the end of week 1 of ~10% setup, which is
on schedule — but with 0 GPU-h spent, the model-side work has not started.

## Last session (2026-10-12, continued — T002)

**Done.** Settled the call-count contradiction that was blocking the v05
decision, and it turned into the mechanism behind P005's funnel. 0 GPU-h.

- **The ledger was never wrong.** `tool_calls_used` counts calls that *spend
  budget*; `analyze_traces` counted calls *emitted*. The harness increments only
  in `check_budget(count_tool_call=True)` (`swegemma__context.py:542`) and four
  classes never reach it: free tools (`submit_patch`, `get_status`), AgentTool
  invocations, calls ADK rejects for a missing argument, and anything emitted
  after the cap — the gate returns the error string *before* incrementing.
  `analyze_traces.reconcile` reproduces all 12 rows exactly (1424 emitted → 901
  charged) under a golden test against the real ledger. The 2026-10-06 backlog
  item is **closed as not-a-bug**.
- **Budget exhaustion does not end the episode.** `fastapi_13713` emitted 310
  refused plus 146 free `submit_patch` calls after its budget was gone — hence
  47 minutes of wall clock. The cap bounds charged work, not time.
- **Fixed a metric that its own subject could inflate.** The four `--compare`
  metrics divided by emitted calls, so post-exhaustion spinning drove them:
  13713 scored `reissue_rate` 0.837, and 13207 reported 29 workspace writes
  against 3 real ones (26 were one malformed `edit_file` retried 26 times). All
  four now denominate on charged calls; `n_calls` → `counted_calls` so the
  change is loud. probe_c12's recorded 0.289/0.399 are flagged non-comparable.
- **Added `first_edit`** — the charged-call index of the first edit attempt. It
  is what exposed "never attempted a fix" and every `never` in the panel lines
  up with a no-patch outcome.
- **Asana synced**, connector working again: closed the undercount item and the
  `resolve60` task with result comments, strengthened the v05 task, and filed
  three new Backlog items (14258's premature stop; free malformed-call retries;
  `HARNESS_README`'s wrong claim that `submit_patch` terminates the task).

**Learned.** Two entries in `LESSONS.md`: when two instruments disagree, compare
their *definitions* before opening a bug — the increment site was three lines and
six days away; and a rate whose denominator the pathology inflates can score
worse behaviour as better.

**Also closed (T003).** `fastapi_14258`'s unspent budget is explained: it
emitted malformed tool-call token syntax, the harness parsed no call, and its
`continuation_nudge` misdiagnosed the cause as a token limit on a 25-token
completion — so the model re-emitted the identical string until the episode
ended. 7 emissions in that task, none elsewhere. Closed with **no action**:
temperature is already 0.2, the nudge text is the harness's, and n=1 barely
bounds the rate.

**Open issues.** The analyzer gradient is observational and fastapi-only; only
measuring `v05` can test it.

## Next steps (prioritized)

1. **Attack patch hygiene structurally. 0 GPU-h to build.** Still the largest
   untouched share: 7 of 12 could not have resolved regardless of fix quality,
   and prompt text demonstrably does not bind this model mid-loop. Remove
   `write_file` from the coder, or add a `LoopAgent` verify step that runs
   `git status --porcelain` and reverts stray paths before `submit_patch`.
2. **Draft the paper. 0 GPU-h, 31 days.** T002 is a strong worked example for
   its own argument: two trusted numbers, neither wrong, and a metric corrupted
   by its subject. Confirm the word cap and judging criteria in a browser first.
3. **Measure `v05_no_analyzer` at k>=2.** Premise is now much better supported.
   Read gold-file hit, re-issue rate and calls-by-author: if the coder's own
   re-issue rate rises to absorb the freed budget, retire the bundle.
4. **Re-ingest historical runs** to recover hygiene metrics never computed.

## Decisions & rationale (continued)

- **Closed the "ledger undercounts" bug as not-a-bug** — the two numbers measure
  different things and the model now reproduces the ledger exactly (2026-10-12).
- **Renamed `n_calls` to `counted_calls` rather than silently redefining it** —
  this project has already published three wrong statistics; a rename makes stale
  values fail loudly instead of comparing quietly (2026-10-12).
- **Kept `resolved` as the ship metric** despite the analyzer gradient being far
  easier to move. Optimising a surrogate wins the surrogate (unchanged).
- **Did not spend today's submission.** v05 is still unmeasured locally and the
  board cannot resolve the effect; the open call from the last handoff stays
  open (2026-10-12).

## Last session (2026-10-13 — P006)

**Done.** Ran the project's pivotal experiment and got a clean negative.
**4.35 GPU-h**, inside the 4.0–5.0 estimate (the first run this project has
priced correctly).

- **P006: `v05_no_analyzer` is retired.** Both arms, one session, 12 tasks. The
  intervention worked perfectly — `coder_call_share` 0.543 → **1.000** (z=+6.02),
  **0 of 1509** calls by the sub-agent, first charged edit from ~call 20 to
  **~6**, and the "never attempted an edit" task gone. **And `gold_hit` did not
  move: 5/12 both arms, 1 gained, 1 lost, McNemar p=1.00.** Resolution 0/12 both.
- **So the −0.90 correlation was a symptom of task difficulty, not a cause.**
  T002 wrote that confound down as a caveat and the run resolved it the
  unfavourable way. The detectable delta was 0.209 against a predicted
  +0.25–0.42, so this is a true null, not a failure to measure.
- **The pathology relocated, as the bundle's own MANIFEST predicted.**
  `reissue_rate` rose **+0.151** (z=+1.87) as the coder absorbed the freed
  budget, plus two loops v00 never showed: 174 `submit_patch` calls in one task,
  136 malformed `edit_file` in another.
- **The same-session design prevented a measured false positive.** v00's own
  `gold_hit` was 3/12 in P005 and **5/12 in P006 on identical bytes** — SD 0.118,
  matching the pre-run `se_unit` ≈ 0.098. The abandoned cheap design (pairing
  v05 against P005's rows) would have read **+0.167 and looked promising.**
- **Corrected a claim from the previous day:** patch hygiene is not the top
  priority for resolution. `gold_exact` dies on any stray file but `gold_hit`
  uses intersection, and pytest never collects a stray `repro.py`. Leaks cost
  `gold_exact` only — a metric we neither ship nor rank on.
- The wheelhouse was **republished again** (2026-10-12 19:51, third time). A
  0 GPU-h CPU probe confirmed the harness API survived it.

**Learned.** `LESSONS.md`: a confirmed mechanism is not a cause — test whether
the intervention moves the *outcome*, never whether it moves the process metric
it was built to move; and freed budget does not stay freed.

**Open issues.** Nothing is known to improve on v00. Four bundles have now been
measured or scored and none beats 0.13. The analyzer hypothesis is closed.

## Next steps (prioritized, revised 2026-10-13)

1. **Draft the paper. 0 GPU-h, 30 days.** Now the strongest item by a wide
   margin, and P006 makes it much better: a mechanistically-confirmed
   intervention that moved every process metric and no outcome metric is a
   better worked example than anything the outline had.
2. **Decide what, if anything, is still worth measuring.** The analyzer path is
   closed, hygiene is a `gold_exact`-only lever, and prompts do not bind this
   model mid-loop. State this honestly rather than building another bundle.
3. **Keep v00 as the submission.** It holds 0.13 and nothing has beaten it.
4. **Re-ingest historical runs** to recover hygiene metrics never computed.

## Decisions & rationale (continued, 2026-10-13)

- **Retired `v05_no_analyzer` rather than tuning it** — the pre-committed rule
  said a flat `gold_hit` means the mechanism was a symptom. Honouring a rule
  fixed before seeing the number is the whole point of fixing it.
- **Ran both arms in one session at double the cost** — the wheelhouse was
  republished hours after the check that cleared the cheaper design. The 2 extra
  GPU-h demonstrably bought the correct answer instead of a +0.167 false positive.

## Last session (2026-10-13, continued — T004, T005, E013; priority switched to score)

**Priority changed mid-session at the user's direction: main-track score first,
paper secondary.** The paper's §D was drafted before the switch and is banked
complete in `paper/MANUSCRIPT.md` (~900 words); nothing else of it is written.

**Done.**
- **T004 — re-read the live leaderboard for the first time since 2026-09-30 and
  found four cited numbers stale**, plus a finding. Top is **0.24** not 0.17;
  **2643** teams not 1037; **340** tied with us not ~19; the private set is
  **58 tasks exactly** not "~60"; and we had recorded "four submissions scored"
  where the API reports **three**. We are rank **785 of 2643**.
  - **Method (new, reusable, 0 GPU-h):** a displayed score is `resolved/58`
    truncated to 2 dp, so the *set* of occupied bins identifies the denominator.
    n=58 is the only value in 20...220 reproducing all 14 occupied bins as
    consecutive k=1...14 with no gaps. Truncation is observed, not assumed
    (11/58 = 0.1897 -> 0.18; 141 teams hold 0.18, **none** holds 0.19).
  - **Strategic consequence, which cuts both ways.** 1,012 of 2643 teams (38%)
    sit within one task of our 8, so the middle of the board genuinely cannot be
    measured by submitting — but the gap to the top is **6 tasks (0.11), above
    our own 0.06 threshold**. For the first time this project has leaderboard
    evidence of a real effect. It is somebody else's.
  - New module `src/swegemma_lab/leaderboard.py` + `scripts/analyze_leaderboard.py`
    + 10 tests pinned to a committed snapshot. Suite **213 -> 223**.
- **T005 — v00 is wall-clock bound in the current environment**, contradicting
  what this file and `HANDOFF.md` both said. 6 of 12 v00 tasks hit the 60-minute
  cap in P006 (median wall 60.4 min) against 0 of 12 and 25.9 min in P005, on
  identical bytes, across the 2026-10-12 wheelhouse republication. Reopens
  `max_tool_calls` **for a no-sub-agent topology only**, where calls bind and
  time does not.
- **E013 — built and submitted `v06_graph_coder`** (`01edeb6c0ae48adf`, sub
  57145400, PENDING). Gives the **root** coder `search_similar_code` +
  `get_code_neighbors`, which only the sub-agent has ever had, and rewrites step
  2 symbol-first so the capability is actually reachable. Pre-registered null
  band 7-10 tasks. **First submission since 2026-10-07** — six submission-days
  had been left unused.
- **Staged the `graph_v06` paired run but did not launch it.** 60 fastapi tasks,
  2 arms, 30-min cap, one session, **~6 GPU-h** (16% of the 38.40 h remaining).
  Sized for power against the project's own D4 arithmetic: detectable gold_hit
  delta ~0.16 versus ~0.42 for P006's 12-task shape. Notebook generates, all
  cells compile, pin verified, lab dataset republished 13:45:07Z with v06 in it.

**Learned.**
- An external number without a capture date is not a verified number; four of
  ours had propagated file-to-file for two weeks.
- A conclusion of the form *X is not the limit* expires, because the limits move
  with the dependency stack. Record the environment stamp alongside it.
- The sub-agent is a **wall-clock** sink (636.5 vs 371.2 summed minutes) while
  being charged as one call. Measure a suspected waste in every currency the
  harness charges in.
- Corrected: "5 of 12 produced no patch" is P005 only. Both P006 arms produced
  **11 of 12** patches. The real invariant is that tasks producing a real code
  change still resolve **0** — fix quality, not patch production.

**Open / broke.**
- v06's score was PENDING at session end. Nothing is known about it.
- The `graph_v06` run is deliberately unlaunched pending that score, because a
  very low result would mean measuring a *different* v06 (lower
  `max_output_tokens`), not this one.

## Next steps (prioritized, revised 2026-10-13 — score first)

1. **Read v06's leaderboard score, in tasks, not as a ratio.** 7-10 tasks is the
   pre-registered null band; 11+ (0.18) is evidence. **Before anything else,
   check for `ContextWindowExceededError`** if it came back low — v06 adds root
   context pressure against a 24,576-token input ceiling.
2. **Then launch or redirect the staged run.** `kaggle kernels push -p
   kernels/15_graph_ab` (~6 GPU-h). Re-check the wheelhouse `lastUpdated` **in
   the same minute** as the push. If v06 scored low on context deaths, change the
   root ceiling first and measure that instead.
3. **Use every submission day.** One per day, ~50 left, and six were wasted. Each
   is a free 58-task sample of the real metric; local runs cost GPU-h and resolve
   0/12. Queue: v05_no_analyzer (built, never submitted, untested on the private
   repo mix), and a no-sub-agent topology with a raised call budget (T005).
4. **Target fix quality, not navigation.** The invariant across all three runs is
   that real code changes resolve 0. A `LoopAgent` verify-repair stage is
   expressible declaratively (`max_iterations` 1...500) and has never been built.
5. **Paper, secondary.** §D is banked. Order B -> C -> F -> G -> H -> E -> A.

## Decisions & rationale (continued, 2026-10-13 second half)

- **Submitted v06 without also lowering `max_output_tokens`**, despite a
  validator warning naming that exact risk. v04_lean already tested sampling
  ceilings alone; moving both axes would make a flat result uninterpretable. The
  pre-registered response to a context-death rise is a *follow-up* bundle.
- **Sized the staged run for power rather than realism** — 60 tasks at a 30-min
  cap over 12 tasks at 60 min. n buys power faster than per-task realism for a
  *ranking* question, and the cap is shared and paired so it cannot favour an
  arm. Stated in the kernel markdown: the shortened cap **favours** v06's
  efficiency claim, so a null is strong against v06 and a positive is weak.
- **Did not launch it the same session.** A free 58-task sample arrives in hours
  and could redirect which bundle is worth 6 GPU-h. Unused quota expires
  2026-10-17, but spending it on a run the next result would invalidate is worse
  than losing it.
