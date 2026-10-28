# Calibrate the Yardstick First: Measurement Discipline for Agentic SWE Benchmarks

**Status:** all eight sections drafted, trimmed under the cap, and fact-checked
against primary sources. Started 2026-10-13; trimmed and corrected **2026-10-27**.
**SUBMITTED 2026-10-28** as a Kaggle Writeup on the paper track, with the
card, both figures and a public project link. Edits remain open until the
deadline, **2026-11-12 23:59 UTC**.

**Rule for this file:** nothing enters the body that is not in the outline's §3
evidence map, and every external number carries the date it was verified.

**Two numbers in the body track the repo and go stale silently:** the suite size
(§D3 and §H, currently **301 passed, 3 skipped** in the published repository,
292 of them without the competition's task file) and the three word counts above.
Both are asserted by `tests/test_export_paper.py` or re-derived by
`scripts/export_paper.py`; re-run both before submitting.

### Length, against the official 3,000-word cap

| counting basis | body |
|---|---|
| alphanumeric tokens (prose words) | **2,922** |
| naive whitespace split of the markdown (scores `\|` and `=` as words) | **2,981** |
| as rendered, without table pipes and heading marks | **2,947** |

The rubric says only "3,000 words maximum" and does not define the count, so the
paper is under the cap on every basis we could construct. Em-dashes are set
closed, Chicago style, so a naive counter does not score them as separate words.
This header is not part of the submission and is excluded from all three
figures. All three are re-derivable: `python scripts/export_paper.py`, which
also writes `paper/SUBMISSION.md`, the exact text to paste into the Writeup.

### The 2026-10-27 accuracy pass

Every quantitative claim was audited against the repo's primary sources — the
ledger rows, `src/swegemma_lab/stats.py`, the bundle MANIFESTs and the committed
leaderboard snapshots — and re-derived where it could be recomputed. Ten
corrections resulted, each verified before it was applied:

- **3,199 teams are *scored*; only 3,043 score positively.** The snapshot
  histogram carries 156 teams at 0.00. The paper said "3,199 hold a positive
  score" in §B and used 3,199 for the positive positions in §D0. The 1,094 / 34%
  band is unaffected: it is a share of the whole scored field.
- **§E claimed a pre-registered falsifier fired. It did not.** `v08`'s registered
  falsifier (`bundles/v08_decode_clamp/MANIFEST.yaml`) was *`gold_hit` falling by
  more than the timeout rate improved*. `gold_hit` **rose, 18 → 24**, which is the
  favourable branch; `gold_exact` appears nowhere in the pre-registration. §E now
  reports the registered branch as passed and the two unregistered readings that
  went the other way. This was the worst error in the draft: a measurement-
  discipline paper misreporting its own pre-registration.
- **McNemar 0.3125 → 0.625.** 0.3125 is the one-sided tail; `mcnemar_exact(3,1)`
  returns **0.625**, and every other p-value in the paper is two-sided. The wrong
  figure is repo-wide (a `stats.py` comment, `LESSONS.md`, `OUTLINE.md` and two
  test docstrings still carry it) — fix those next.
- **Two runs had been conflated.** The 76% mismatch rate is P009's `cap60_v00`
  (26/34); the byte-identical-to-gold pair is P008's, where the rate was 73%
  (75/103). §G now attributes both.
- **`SE_UNIT` = 0.030 was never measured on a 129-task run.** The largest task
  list ever executed is 60. It is rescaled by 1/√n from a 12-task replication whose
  two byte-identical runs differed by SD 0.118. §D4 now states that provenance
  instead of asserting a measured 129-task SE, and §G no longer contradicts it.
- **Five of the six components are GPU-free, not four.** §D and the abstract said
  four while §H said five; only D2 needs an accelerator.
- **p ≈ 0.15 is the grader's rate, not ours.** Local resolution runs far lower
  (1/36, 2/60, 3/60). §C and §D2 now distinguish them, which the paper's own rule
  against conflating grader and local harness demands.
- **The headline paired comparison is 36 fastapi tasks only.** `clean_dev36.txt`
  is 36/36 `fastapi/fastapi`. Now disclosed in §F's honest-limit paragraph.
- **The mismatch rate is not re-derivable from this repo.** `ledger/runs/clamp_*`
  and `cap60_*` carry `runspec.json` and `task_results.jsonl` only — no `patches/`
  and no test logs, unlike `analyzer_*`. §H no longer claims every figure is
  re-derivable. (`HANDOFF.md` §4 still overstates this and needs the same fix.)
- **Four smaller ones.** v01's eleven items are not all prompt edits; v04 landed
  *between* the arms, not "exactly between" (6 tasks against 8 and 5); §G's "~0.24"
  is now **0.209**, the figure `detectable_delta` actually returns at n = 12, k = 1;
  and §D1 no longer says the run that produced the diagnosis "bought nothing" — the
  second identical run is precisely the one that captured the test output.

Cross-section duplication removed in the same pass: the third-party score triple
(the caveat survives in §G), and the "floor moved underneath us" finding, which was
told at full length in §E, §F and §G and now lives in §G with cross-references.

**Verification note, 2026-10-21.** §B and §D both report the **2026-10-19**
committed snapshot (3,199 teams), not the 2026-10-13 one the outline was written
against. D0's derivation was re-run on the newer board and is unchanged: a unique
truncating fit at **n = 58**, **no** exact rounding fit in 20..220, nearest
rounding containments at n = 93 (8 empty interior positions) and n = 98-100 (10).
§B's central figure is recomputed, not carried over: the one-task band is
**1,094 of 3,199 = 34%**. Do not reuse the outline's "1,012 of 2,643 = 38%" — its
own components sum to 1,026, so that line carries an arithmetic slip as well as a
stale snapshot.

**The rubric is official as of 2026-10-27** (`paper/OUTLINE.md` §10, read
first-party in a browser): 3,000 words maximum; five criteria each 0–5 —
**Novelty, Quality, Relevance, Verifiability, Clarity** — final score the average
of all five; top three win; the rubric is never shared.
---

## Abstract

A public leaderboard over a small hidden split can be too coarse to resolve what
its entrants are tuning. On the benchmark we study the private split is 58
tasks, so one task is 0.0172, and **34% of the 3,199 scored teams sit within a
single task of our own score**—while two of our own submissions with
byte-identical prompts landed two tasks apart. Measuring in-house does not fix
it: binary resolution is the noisiest available readout, and the local harness
has a floor of its own—**24 of 129 tasks fail under the benchmark's own
reference solution**. We give a six-component calibration protocol, five
components free of GPU time; it caught four errors in our own instrument,
including a calibration that expired silently and a power calculation that
omitted sample size. In our final comparison the one retained intervention
eliminated **every** timeout (11 of 36 to 0, p = 0.001) while resolution over
the same paired tasks gave **zero discordant pairs**. We claim no improved
agent—only a yardstick worth trusting.

## The leaderboard cannot resolve what is being tuned

A public leaderboard looks like a measurement because it is a number. On this
board its resolution is one task, and almost nobody's changes are worth one
task.

On the committed snapshot of **2026-10-19**, 3,199 teams are scored, 3,043 of
them positively, across 14 occupied positive positions. Converted to task counts
by D0: 353 teams resolve exactly 8 of 58, 312 resolve 7, and 429 resolve 9.
**One third of the entire field—1,094 teams, 34%—sits within a single task of
our own score.** A change worth one task moves a team through a third of the
population; a change worth less than one task cannot alter the displayed string
at all, and so is not merely noisy but invisible.

Our own submissions show what that invisibility costs a team that is iterating.
The unmodified public baseline scored **0.13**—8 tasks. `v01_hygiene`, eleven
mechanism-motivated changes, mostly prompt edits, scored **0.08**—5 tasks, three
*worse*. The informative one is `v04_lean`, **byte-identical to v00** in its
prompt files by `diff` and differing only in sampling ceilings: it scored
**0.10**, 6 tasks. Two submissions giving the model the same instructions landed
two tasks apart—as measurements of prompt quality they say nothing, and as a
re-draw of the same hand they bound how much of a leaderboard delta belongs to
what the entrant changed.

**The instrument is not broken, and this section has to say so.** The top of the
board holds 0.24—14 tasks, **six above us**—far outside the one-task spread just
described, and the leaderboard resolves that difference perfectly well. The
asymmetry is this paper's subject: **the instrument resolves about six tasks,
while the field is making changes worth about one.** Tuning inside that gap is
reading noise and calling it progress.

## Why moving the measurement locally does not fix it

The obvious response is to stop submitting and measure at home. It is the right
move, and by itself it does not work, for two compounding reasons.

The first is the readout. Resolution is a Bernoulli outcome per task, and at the
grader's own rate of p ≈ 0.15 its standard error swamps any effect a prompt
change plausibly produces; our local rate is lower still, which only makes it
worse. Pairing helps, but detecting a 0.05 difference still needs more samples
than a free-tier allocation buys (D4)—so we refused those runs rather than
running them and over-reading the result.

The second is that the local instrument has a floor of its own, and it is not
small. Running the competition's **own reference patches** against its **own
test patches**, with no agent at all, 105 of 129 tasks pass: **24 fail with the
correct answer applied.** The dominant diagnosed cause is dependency version
drift—`rich` asserts that `guess_lexer(...)` returns `"python"` where a newer
Pygments returns `"ipython"`. Eighteen tasks were classified as drift and three
collection errors left unclassified, which does not close against the 24: that
classification was made at an earlier gold pass rate and has not been re-run. We
report the gap rather than smooth it.

![Gold/null calibration over 129 tasks](https://raw.githubusercontent.com/Axentalan-VI/gemma-4-developer-agent/main/paper/figures/gallery_1_calibration.png)

This floor is not a bug to be fixed. The grader's pinned wheel cache is private
and the public wheels directory holds only 41 distinct packages, so the
environment in which those 24 tasks pass cannot be reconstructed. The floor is a
property of our instrument, to be measured and subtracted—not eliminated.

The consequence is this paper's pivot. An uncalibrated local harness reports a
failure for three different reasons—the agent was wrong, the environment
drifted, or the task was never winnable here—and one resolution rate cannot
distinguish them. **Before a harness can rank anything, it has to be told what
its own zero is.**

## The protocol

Six components. Each is independently adoptable, and five of the six cost no GPU
time at all.

### D0—Recover the denominator from the public leaderboard

A public leaderboard gives away its own granularity for free.

A displayed score is `resolved / n_tasks` truncated to two decimals, so only
`n_tasks + 1` strings can ever appear. Once enough teams have submitted that
every reachable low score is occupied, the *set* of occupied strings identifies
`n_tasks`. Uniqueness requires **exact equality** over the occupied range, not
containment: a finer grid always covers a coarser one, so containment admits
every larger denominator.

On the 2026-10-19 board, 3,043 teams occupy 14 positive positions from 0.01 to
0.24, and exactly one denominator in 20…220 reproduces them—**58**, as
consecutive counts k = 1…14 with no gaps. Two properties confirm the model
rather than assume it. The display truncates—11/58 = 0.1897 floors to 0.18 and
rounds to 0.19, and 355 teams hold 0.18 while none holds 0.19—and rounding
cannot fit the board at all, its nearest solutions needing eight to ten interior
positions empty from n = 93 up, which a field of 3,199 would not leave empty.

One task is therefore 0.0172 and every leaderboard figure becomes an integer: we
hold 8, the best score 14. The method settles the denominator only, not the
variance, and cannot see tasks nobody has resolved (§G).

### D1—Gold/null calibration

Run the reference solution on every task, and run the empty patch. Gold is an
upper bound—a task whose own reference does not pass cannot be measured locally,
whatever the agent does. Null is a lower bound: a task passing with no change is
degenerate. What survives both is the measurable subset—of the 129 public tasks,
105 passed gold and 3 passed null, leaving a frozen working set of **102**.
Skipping the step would have put a silent 81% ceiling on every rate we reported,
and charged the agent 24 tasks no agent could pass.

The methodological content is in *how* that number was reached. Two of four
calibration runs returned bit-for-bit identical verdicts and moved the
measurable set not at all, because we were theorising about the cause of failure
instead of capturing it. The second of them was the first to record the tail of
each failing test run, which split 55 failures into 27 missing one test-only
dependency, 7 missing another, and 18 genuine version drift; the first two were
recoverable and moved the measurable set from 71 to 102, and the third is the
floor. **The instrument had to be instrumented before it produced a diagnosis.**

### D2—Prefer a lower-variance surrogate

Binary resolution is the noisiest readout available: the grader scores near p ≈
0.15 and our harness lower. Gold-file localization—did the agent's patch touch a
file the reference patch touched—needs no test execution, applies to all 129
tasks rather than 102, and sits near p ≈ 0.45. It also suits these tasks: 71% of
reference patches touch a single file, median 12 changed lines.

The discipline that must accompany it: **localization carries the iteration
loop, resolution authorizes shipping, and the two are never swapped.**
Optimizing a surrogate is how you win the surrogate.

### D3—Pair, pool, and do not trust a z-score at k = 1

Pool every run of byte-identical configuration under one hash, so repeated runs
accumulate rather than compete; compare arms paired within task.

The trap is worth publishing because we fell into it. Our estimator computed
per-task variance as p(1−p)/k, which at k = 1 is identically zero. It reported
SE = 0.0000, z = ±∞, and printed SIGNIFICANT for a three-gained / one-lost split
whose exact two-sided McNemar p-value is 0.625; the fix is to fall back to the
discordant pairs. What makes it a finding rather than a bug report is that a
passing test named `test_deterministic_arms_have_zero_variance` asserted the
broken behaviour as a feature. The suite passed throughout, and passes at 301
tests today. **A test suite cannot catch a wrong statistical contract, because
the contract is what the tests encode.**

### D4—Price the experiment; refuse what cannot answer

The paired standard error is ≈0.030 per run on the 129-task scale—rescaled by
1/√n from two byte-identical 12-task runs whose results differed by SD 0.118,
not measured on a 129-task replication. On that constant, and the same scaling,
the smallest detectable difference at 80% power is:

| samples per arm | on all 129 tasks | the same design on 60 | on 36 |
|---|---|---|---|
| 1 | 0.064 | 0.093 | 0.121 |
| 2 | 0.045 | 0.066 | 0.085 |
| 4 | 0.032 | 0.047 | 0.060 |

Against a design target of 0.05, **one sample per arm cannot see the effects
this field is making—and on a 60-task subset, neither can two.** The right-hand
columns are not decoration: pricing a subset with the full set's standard error
is exactly the error our own implementation made, in the flattering direction
(§G). The arithmetic needs no GPU and makes §B's pile-up inevitable.

The consequence for tooling is sharp. A rule demanding a significant positive
difference can only return "hold" at affordable sample sizes, silently merging
*we measured and it did not help* with *we could not measure*. Our estimator
returns a third verdict, `underpowered`, and the first run we applied it to was
reclassified. Any A/B lacking that distinction reports the first sentence while
entitled only to the second.

### D5—Pre-register the reading before spending compute

Each configuration records, before its run, what each possible outcome would
mean. Our leanest variant pre-registered that a score near the baseline would
blame an earlier regression on prompt length, and one near the weak arm would
clear it. It returned a value between the two, and so discriminated nothing.
That is reportable as a null *because* it was pre-registered; without it the
same number would have been narrated into whichever story was already preferred.

## What the protocol bought

Four things, in order.

**D0 turned a ratio into a count.** Knowing the denominator is 58 made the gap
to the top six tasks rather than 0.11—arguable where 0.11 is not.

**D1 found the floor, then caught it moving.** The first calibration showed 24
of 129 tasks failing with the reference solution applied; re-running it caught
that floor shifting underneath us (§G). For weeks we had been ranking candidate
agents against a metric whose zero had moved.

**D5 stopped us over-reading a favourable run.** We pre-registered that the
intervention would be falsified if localization fell by more than the timeout
rate improved. It did not fall—it rose, 18 to 24—so the registered branch says
ship. Two readings we had *not* registered went the other way: the stricter
localization measure fell, and the prior run's significant localization gain did
not replicate (p = 0.21 against p = 0.019). We report both.

**And the payoff, in one comparison.** At the grader's real per-task budget our
one retained intervention eliminated **every** timeout—11 of 36 tasks to 0,
McNemar p = 0.00098, none lost—while resolution over the same 36 paired tasks
gave **zero discordant pairs**, and so no information at any sample size.
Without D1 and D2 we would have reported the resolution null; without D0 and D4,
neither, never having sized the run. The protocol did not make our agent better;
it told us which of our two numbers to believe.

![Four metrics, two arms, 36 paired tasks](https://raw.githubusercontent.com/Axentalan-VI/gemma-4-developer-agent/main/paper/figures/gallery_2_paired.png)

## Generalization

Nothing in the protocol depends on Gemma, on ADK, on fastapi, or on this
harness. It applies wherever the test set is hidden, the private split is small
enough to be noise-dominated, and a reference solution exists—which describes
every SWE-bench derivative and most agentic benchmarks built since. Each
component also transfers on its own terms, which matters because a protocol
adopted whole is a protocol adopted by nobody.

**D0, recovering the denominator,** needs only a public leaderboard with enough
occupants to fill its low scores: arithmetic on displayed strings, costing
nothing. Any competition displaying a truncated or rounded ratio leaks its
granularity the same way.

**D1, gold/null calibration,** needs only the reference solution, which every
SWE-bench derivative ships. Run the reference, run the empty patch, and the gap
between them is the band inside which the instrument can say anything—the
cheapest component, and the one most often skipped. It saved us twice over (§C,
§G).

**D2, preferring a lower-variance surrogate,** generalizes wherever the
reference solution has structure to compare against: files touched, symbols
changed, call sites edited. None of that executes the task's test suite, which
is what makes it affordable on every task rather than a sample. The surrogate is
domain-specific; the selection rule is not—take the readout with the highest
base rate that still tracks the objective, and verify the tracking.

**D3, the k = 1 variance trap,** is latent in any paired agent A/B reporting a
z-score, which is most we have read: one sample per arm cannot separate a real
effect from a re-draw, yet still prints a number that looks like evidence.

**D4 and D5, pricing the experiment and pre-registering the reading,** cost no
compute. Pricing refuses experiments that cannot answer their own question—and
is where our own instrument failed (§G). Pre-registration is the only defence we
found against narrating a null into a finding.

**The honest limit.** Everything here comes from one competition, one harness,
one quantized model, and a task mix dominated by two repositories: our
calibrated set is 60 fastapi and 42 rich tasks, none from the benchmark's other
two, and the paired run behind our headline comparison used 36 fastapi tasks
only. The protocol's *components* are general by construction—arithmetic,
calibration and study design. Our *evidence that they help* is not. We claim the
first, not the second.

## Limitations

**We did not improve the agent.** Eight submissions, three of which scored
(0.13, 0.08, 0.10), and no evidence of improvement or harm. This paper is about
the instrument.

**Others did improve theirs, and we cannot say how.** The top of the public
board is six tasks clear of us, far outside any noise band we can construct. Our
claim concerns the resolution of the public signal *at the scale most teams work
at*, not that agent quality is unmeasurable. It is the first objection a reader
will raise, so we raise it first.

**Our own instrument broke, and the protocol is only why we noticed.** In a late
paired run, two tasks produced—in both arms—patches whose change bodies were
byte-identical to the reference solution, and all four were scored unresolved.
73% of that run's test logs aborted during collection on a version mismatch
between the installed web framework and the task snapshots, and 76% in the run
after it. Our gold calibration had been run once, weeks earlier, against a
different dependency set, and its *task list* was thereafter treated as a
standing property of the environment. It was not: a calibration has a shelf
life, and ours expired silently.

**Our own power calculation erred in the flattering direction.** Our
detectable-delta function omitted the task-set size, while the standard error it
used was on the 129-task scale. Every design we priced was
smaller, so every one was priced as more sensitive than it was—0.064 reported
for a 12-task design whose true figure is 0.209—and at one common design the
ship/hold verdict flips. Two of our own tests asserted the wrong values as
correct.

**A confirmed mechanism turned out not to be a cause.** We removed a sub-agent
consuming 90–98% of the budget in failing tasks (Spearman −0.90). The
intervention worked completely—the coder's call share went 0.543 → 1.000, z =
+6.02—and localization was 5/12 in *both* arms, p = 1.00. Process metrics are
not outcome evidence.

**Four smaller ones, stated rather than buried.** Our noise estimate rests on
three reported scores for one bundle, two of them third-party and not
archive-verified. The private-set size is derived, not published—58 is the
unique exact fit to the public histogram, which pins the displayed grid but
remains an inference. Our behavioural observations are n = 12 at k = 1, where
only a delta above 0.209 would register, and are reported as directions with
their n. And seeds do not buy determinism: the inference server is not bitwise
reproducible under continuous batching.

## Reproducibility

The repository carries the protocol, not just its outputs. Every bundle has a
content hash, so byte-identity across runs is checkable rather than asserted,
and the ledger holds one row per task per run—so almost every figure here is
re-derivable without rerunning anything. The exception is the mismatch rate,
whose raw pytest output is not committed. The statistical machinery has 301
passing tests, including the ones that now assert the two contracts we got
wrong.

The part that matters for anyone wanting to repeat this: **the whole calibration
protocol is CPU-only and costs zero GPU-hours.** D0 is arithmetic on a public
leaderboard, D1 needs the reference solutions the benchmark already ships, and
D4 and D5 are a spreadsheet and a paragraph written before a run. Only D2's
surrogate and the paired comparisons need an accelerator: a reader with no GPU
can reproduce the five components that caught all four of our instrument errors.
