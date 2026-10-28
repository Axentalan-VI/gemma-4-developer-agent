# Paper-track outline — measurement methodology

**Internal working document** (for me and for future sessions), not a draft of
the paper itself. The manuscript will live in `paper/MANUSCRIPT.md`.

Created 2026-10-12. Thesis chosen this session; framing alternatives considered
and rejected are recorded in §7 so they are not relitigated.

---

## 0. Submission facts

| Fact | Value | Confidence |
|---|---|---|
| Deadline | **2026-11-12 23:59** | **verified 2026-10-13** — `kaggle competitions list` |
| Prize pool | $35,000 track pool | **verified 2026-10-13** — same source |
| Entrants | **205 teams** (main track: 2643) | **verified 2026-10-13** — same source |
| ~~We have not joined~~ **Joined** | `userHasEntered: True`, 206 teams | **verified 2026-10-13**, after the rules were accepted in a browser |
| `NOTE.md` (the only competition file) | *"Welcome! This is a Hackathon with no provided dataset."* | **read 2026-10-13** — 55 bytes, settles nothing |
| Format | Kaggle **Writeup**, **3,000 words maximum** | **VERIFIED 2026-10-27** — official overview, Submission Details: "Scope: 3,000 words maximum, reporting original, unpublished research." Read in a browser via Playwright |
| Judging | 5 criteria, each **0–5**, final score = **average of all five**: **Novelty, Quality, Relevance, Verifiability, Clarity**; **top 3** writeups win; rubric is never shared; ties broken by earliest entry | **VERIFIED 2026-10-27** — official overview. The third-party guess was right, including that **Quality** is scored as *generality* |
| Eligibility | Paper track does **not** require a main-track submission | **UNVERIFIED** — third-party; resolves README open question #5 |

**Two blocking actions, both needing a browser** (2026-10-13: Kaggle's pages are
JS-rendered and return only a `<title>` to every fetch tool available here, and
the competition's own `NOTE.md` returns **403** until the rules are accepted):

1. ~~Join the paper competition and accept its rules.~~ **DONE 2026-10-13.**
   `userHasEntered: True`. `NOTE.md` now downloads instead of returning 403, and
   contains nothing of use. **Joining did not unblock the facts below** — the
   obstacle is that Kaggle's pages are JS-rendered, not that they were
   unauthorized.
2. ~~Confirm the word cap, the five criteria and the submission mechanism.~~
   **DONE 2026-10-27, in a browser (Playwright), which this session finally had.**
   All three are now first-party and quoted verbatim below. The 3,000-word cap is
   official, so **the section plan in §2 stands unchanged.** Superseded text:

   The
   cap is corroborated by three independent third-party repositories, which is
   better than one search synthesis but is still not the official text. A
   3,000-word cap versus, say, 8 pages changes the structure below
   substantially. Everything else in this outline is cap-independent.

Do not treat the 1,500-word cap that appears in search results as relevant: it
belongs to a different Kaggle event ("Build and hack with Gemma 4.0") with its
own 0–30/0–30/0–20 scoring.

## 1. Thesis

> **In this competition nobody — including us — can tell whether their agent got
> better, because the evaluation instrument is coarser than the effects being
> made. We calibrate the instrument first, and report what that costs and buys.**

**Narrowed 2026-10-13, and quantified.** Reading the full leaderboard histogram
(2643 teams) shows the claim is true *of the region where almost everyone sits*
and false of the board as a whole, so the paper must say which. The private set
holds **58 tasks** (§D0), one task is worth **0.0172**, and **1,026 of 2,643
scored teams — 39% — sit within one task of 8/58**: 353 at 7, 340 at 8, 333 at 9.
(Corrected 2026-10-27: this line said 1,012, but its own components sum to 1,026.
Note also that 2,643 is the *scored* field; 150 of them sit at 0.00, so positive
scorers are 2,493. **The manuscript supersedes this paragraph** — it reports the
2026-10-19 snapshot, where the band is 1,094 of 3,199 = 34%.) Inside
that mode, a submission delta is indistinguishable from a re-draw, which is
exactly the thesis. But the top of the board is **14/58 = 0.24**, six tasks clear
of us and far outside any plausible noise band, so *somebody* has a real effect.

This is a better thesis than the one it replaces, for two reasons. It is
**quantitative** — a named fraction of a named population, not an impression of a
pile-up. And it is **falsifiable in the right direction**: it does not claim
agent quality is unmeasurable, it claims the *public leaderboard* cannot resolve
it at the scale the field is working at, while demonstrating that the same
leaderboard's own histogram reveals its resolution exactly. The paper must not
overstate it into "nobody is improving anything"; the 6-task gap is first-party
evidence against that, and stating so is the honest version.

Why this thesis and not a result-of-the-agent thesis: we have no agent that
beats the public baseline, and four submissions have produced no evidence of
improvement *or* harm. The measurement finding is the thing we actually have,
it is first-party, and it is the explanation for a visible public anomaly (19
teams tied at one score). It also needs no further GPU run to be true.

Mapping to the judging criteria, explicitly:

| Criterion | How this thesis scores |
|---|---|
| Novelty | The field is tuning prompts against a signal that cannot carry the tuning. Saying so quantitatively is new here. |
| Quality / generality | The protocol is benchmark-agnostic — it needs only a hidden test set, a small private split, and a reference solution. Nothing in it is fastapi- or Gemma-specific. |
| Relevance | Agentic SWE benchmarks are the field's main yardstick right now; a yardstick-calibration method is directly on-topic. |
| Verifiability | Strongest card. Every number has a committed source: the ledger, `bundle_hash`, 187 tests, four CPU-only calibration runs reproducible at 0 GPU-h. |
| Clarity | Served by one thesis rather than three. This is the reason the budget-anatomy material is demoted to a single section. |

## 2. Section plan and word budget

Total 3,000. Budget sums to 3,100; §§E and F are the trim targets.

**Revised 2026-10-13:** D0 adds ~140 words inside §D's 900, so §D must give up
~140 elsewhere. Cheapest cut is D1's run-by-run calibration-ladder table
(C001–C004), which Figure 2 already carries — keep the prose finding ("two of
four runs bought nothing because the instrument was not instrumented") and drop
the table. §B also gets shorter, not longer, because the histogram replaces two
paragraphs of third-party caveating with one sentence and one number.

| § | Section | Words | Depends on a pending run? |
|---|---|---|---|
| A | Abstract | 150 | no |
| B | The leaderboard cannot resolve what is being tuned | 450 | no |
| C | Why moving the measurement locally does not fix it | 400 | no |
| D | **The protocol** (the contribution) | 900 | no |
| | — of which D0 (leaderboard denominator), added 2026-10-13 | ~140 | no |
| E | What the protocol bought | 500 | **no longer** — fallback prose written, §9 |
| F | Generalization beyond this competition | 350 | no |
| G | Limitations | 250 | no |
| H | Reproducibility | 100 | no |

**No section now depends on a pending measurement.** §E previously did; its
fallback prose is written in full at §9 and ships as-is, with the k=4 reference
as an upgrade rather than a prerequisite. The paper is therefore off the critical
path of every GPU run — deliberately, because this deadline cannot be recovered
by compute, and because the rig has now failed twice on environment drift in
five days.

## 3. Evidence map

Every claim the paper will make, with its source and its status. **Nothing goes
into the manuscript that is not in this table.**

### §B — the leaderboard cannot resolve what is being tuned

| Claim | Source | Status |
|---|---|---|
| Top of public LB **0.24** (2 teams); **2643** teams; **340** tied with us at 0.13; we are rank **785** | `data/leaderboard/public_lb_2026-10-13.json`, committed snapshot | **first-party, verified 2026-10-13.** Replaces "0.17 / 1037 teams / ~19 tied", which was 3 weeks stale |
| Private set is **exactly 58 tasks**; one task = **0.0172** | §D0; `src/swegemma_lab/leaderboard.py`, 10 tests | **derived and uniquely determined** — no longer "inferred, label as such" |
| **1,012 of 2643 teams (38%) sit within one task of our 8/58** — 353 at 7, 340 at 8, 333 at 9 | same snapshot | first-party. **This is now §B's central number** |
| The gap from 8/58 to the top's 14/58 is **6 tasks (0.11)**, above our own 0.06 threshold | same snapshot | first-party. **Must be stated** — it bounds the thesis honestly |
| `v00_public_baseline` → **0.13** | `kaggle competitions submissions`, sub 56703353 | first-party, verified 2026-10-12 |
| `v01_hygiene` (11 prompt changes) → **0.08** | sub 56875884 | first-party |
| `v04_lean`, prompts **byte-identical to v00** by `diff`, differing only in sampling ceilings → **0.10** | sub 56910112; `bundles/v04_lean/` | first-party — **the strongest single data point** |
| Third parties reported 0.12 and 0.15 for the same public bundle content | `README.md:123-126`, `EXPERIMENTS.md:39` | **weak: n=3, self-reported, verified only by cell-hashing the generating notebooks, not by comparing archives.** Must carry this caveat. |
| Decision rule adopted: an LB delta below 0.06 is not evidence | `EXPERIMENTS.md:10`, project `CLAUDE.md` | our own rule, stated as such |

**Framing for §B, revised 2026-10-13:** lead with the **histogram** — 38% of 2643
teams inside a one-task band — because it is first-party, needs no trust in
anyone's self-report, and makes the thesis visible as a population fact rather
than an anecdote. Then `v04_lean` as the mechanism (byte-identical prompts, 0.10
vs 0.13, i.e. ±1 task on a re-draw). The third-party 0.12/0.15 triple is
third-rank corroboration, not the argument. Earlier drafts of this project's own
notes led with the triple; that is an over-read and the paper must not repeat it.

**And §B must state its own bound.** The 6-task gap to 0.24 is first-party
evidence that the leaderboard *does* resolve large effects. A §B that omits this
is cherry-picking, and a judge reading the public board will notice in one
glance. The honest sentence: the instrument resolves ~6 tasks, the field is
making changes worth ~1, and that ratio is the paper's subject.

### §C — why local measurement does not automatically fix it

| Claim | Source | Status |
|---|---|---|
| Binary resolution is the noisiest available readout; at p≈0.15 the SE is large relative to any realistic effect | `PLAN.md:117` | analytic |
| A local harness has its own floor: 18 of 129 tasks fail under the gold patch purely on dependency version drift | `README.md` cause table (18 tasks), `README.md:64-70` | measured, CPU-only |
| Concrete drift examples: `rich` asserts `guess_lexer(...) == "python"` where newer Pygments says `"ipython"`; `requests`' `test_header_no_return_chars` fails on newer urllib3 | `README.md:64-68` | measured |
| The grader's pinned wheel cache is private, so this is an accepted floor rather than a bug | `README.md:68-70` | reasoned |
| Therefore the instrument must be calibrated before it is used to rank anything | — | the paper's pivot |

### §D — the protocol (the contribution)

Six components (D0 added 2026-10-13). Each is a thing another team could adopt
tomorrow.

**D0. Recover the grader's denominator from the public leaderboard, 0
GPU-hours.** Before calibrating an instrument, establish its granularity — and a
public leaderboard hands it over for free, which appears not to be widely known.

A displayed score is `resolved / n_tasks` truncated to two decimals, so only
`n_tasks + 1` distinct strings can ever appear. With enough teams every reachable
low score is occupied, and the **set of occupied strings identifies `n_tasks`**,
because different denominators generate different grids. Requiring *exact*
equality over the occupied range — not mere containment, which every larger
denominator satisfies — makes the answer unique.

On the 2026-10-13 board, 2643 teams occupy 14 positive bins (0.01 … 0.24), and
**exactly one denominator in 20…220 reproduces them: 58**, as consecutive
k = 1…14 with no empty bins. Two checks make it an observation rather than a
posit:

- **The display truncates, and the board proves it.** 11/58 = 0.1897, which
  floors to 0.18 and rounds to 0.19. 141 teams hold 0.18; nobody holds 0.19.
- **Rounding cannot explain the board at all.** The nearest rounding fits start
  at n = 93 and require 8–10 bins between 0.01 and 0.24 to be empty, which 2643
  teams would not leave empty.

What it buys, concretely: one task is **0.0172**, so our 0.13 is **8 tasks** and
the top is **14**. Every leaderboard delta in the paper becomes an integer task
count instead of a ratio, which is what makes §B's argument legible. It also
retired two live hypotheses in this project's own notes for zero compute — "~60
tasks" and "a denominator of 100 also fits" — the latter excluded because n=100
would put ten unoccupied values on the grid.

Honest limits, which the paper states: this pins the *displayed grid*, so any
denominator sharing 58's grid would fit equally (none does here); it assumes one
task set for all teams; and it cannot see tasks nobody has ever resolved, so 58
is simultaneously a lower bound and the unique exact fit. **It settles the
denominator, not the variance** — D3's SD question is untouched by it.

Implementation: `src/swegemma_lab/leaderboard.py` (~110 lines),
`scripts/analyze_leaderboard.py`, 10 tests pinned to the committed snapshot
rather than to a fixture. Transfers to any benchmark with a public leaderboard,
a bounded task count and a rounded display — which is most of them.

**D1. Gold/null calibration, 0 GPU-hours.** Run the *gold* patch on every task
(upper bound: if the reference solution does not pass, the task is unmeasurable
locally) and the *empty* patch (lower bound: if nothing passes, the task is
degenerate). What survives is the measurable subset — `clean-N`.

| Run | Change | Gold | clean-N | Source |
|---|---|---|---|---|
| C001 | first calibration | 74/129 | 71 (discarded) | `README.md:51` |
| C002 | `--no-deps` staging | died at preflight | — | `README.md:52` |
| C003 | transitive resolve + pinned harness | 74/129, **bit-identical verdicts to C001** | 71 (discarded) | `README.md:53` |
| C004 | add `inline_snapshot`, `dirty_equals` | **105/129** | **102** | `README.md:54` |

- Accepted: gold 105/129 (81%), null 3/129, **clean-N = 102**, frozen in
  `data/tasks/clean_n.txt`.
- **clean-N composition: fastapi 60 + rich 42, requests 0, httpx 0.** The audit
  split vanishes under calibration — worth stating, because it means the
  generalization guard rests on rich-vs-fastapi alone.
- **The methodological point, and the most honest part of the paper:** C001 and
  C003 returned bit-for-bit identical verdicts on all 129 tasks, and the first
  diagnosis (that the harness's no-op `install_test_dependencies` was the whole
  story) was **wrong**. Capturing `test_output_tail` — i.e. instrumenting the
  failure rather than theorising about it — split 55 failures into 27
  `inline_snapshot`, 7 `dirty_equals`, and 18 genuine drift. Two of four runs
  bought nothing because the instrument was not instrumented.
  (`README.md:56-80`)

**D2. Lower-variance surrogate metrics.** Gold-file localization — did the
agent's patch touch a file the gold patch touched — needs **no test execution**,
works on all 129 tasks rather than 102, and sits near **p=0.45** rather than
p=0.15, which is where the variance reduction comes from.
Sources: `README.md:113-119`, `README.md:170-171` (71% of gold patches are
single-file, median 12 changed lines), `README.md:349-355` (how to read
localization and resolution together).
State plainly: localization carries the iteration loop; resolution stays
confirmatory on clean-N.

**D3. Paired, pooled estimation — and a variance trap worth publishing.**
- Pool every run of identical bytes by `bundle_hash` (sha256 over sorted
  `(posix relpath, LF-normalized bytes)`), so repeated runs of one config
  accumulate instead of competing.
- Compare arms **paired within task**, not between samples.
- **The trap:** our estimator computed the per-task variance as `p(1−p)/k`,
  which at **k=1 is identically zero**. It therefore reported `SE 0.0000`,
  `z = ±inf`, and printed **SIGNIFICANT** for a 3-gained/1-lost split whose
  exact McNemar p is **0.625**. Fixed by falling back to the discordant pairs,
  `sqrt(gained+lost)/n`. (`HANDOFF.md` §3, `src/swegemma_lab/stats.py`)
- **And the part that makes it a finding rather than a bug report:** a test
  named `test_deterministic_arms_have_zero_variance` **asserted the broken
  behaviour as a feature**, with a docstring describing it as "the degenerate
  case that makes single-run McNemar dangerous". 187 passing tests certified
  nothing, because the test encoded the wrong contract. This is the
  generalizable warning: a test suite cannot catch a wrong statistical contract.

**D4. Price the experiment before running it — and refuse to run the ones that
cannot answer.** The paired SE on this task set is ~0.030 per run, so the
smallest detectable delta at alpha=0.10 with 80% power is:

| k (per arm) | smallest detectable delta | what that costs |
|---|---|---|
| 1 | **0.064** | ~1.6 GPU-h |
| 2 | 0.045 | ~3 GPU-h |
| 4 | 0.032 | ~6 GPU-h |
| 8 | 0.023 | ~12 GPU-h |

Set against a design target of 0.05, **k=1 cannot see the effects anyone in this
competition is making**, and a single prompt change moves far less than 0.05 even
at k=4. This is the arithmetic that makes the leaderboard pile-up inevitable
rather than surprising, and it is the paper's most transferable artifact: it is
three lines of code (`stats.detectable_delta`), it needs no GPU, and it applies to
any agent benchmark with a binary per-task outcome.

The consequence we had to implement in our own tooling is the sharp end of it: a
ship rule that requires a significant positive resolution delta can only ever
return HOLD at affordable k, which silently conflates **"we measured and it did
not help"** with **"we could not measure"**. Our estimator now returns a third
verdict, `UNDERPOWERED`, keyed on whether the detectable delta exceeds the design
target. The first run it was applied to — our own only paired run — was
reclassified from HOLD to UNDERPOWERED. Any published agent A/B without this
distinction is reporting the first sentence while entitled only to the second.

**D5. Pre-register the reading before spending the compute.** Each bundle's
`MANIFEST.yaml` states, before the run, what each possible outcome would mean.
Worked example: `v04_lean` pre-registered "near 0.13 isolates the regression to
prompt length; near 0.08 means the prompt was not the cause." It returned
**0.10, between the two, and therefore discriminated nothing.** That is
reportable as a null *because* it was pre-registered; without pre-registration
0.10 would have been narrated into whichever story was wanted.

### §E — what the protocol bought

| Item | Value | Status |
|---|---|---|
| **The grader's denominator recovered: 58 tasks, uniquely** | retired "~60" and "100 also fits"; turned every LB delta into an integer task count | **derived 2026-10-13, 0 GPU-h** |
| **The thesis bounded before a judge could bound it** | the same histogram showing 38% of teams in a one-task band also shows a 6-task gap to the top, which an earlier draft would have omitted | 0 GPU-h |
| Measurable subset established at 102 tasks, versus 129 naive (would silently cap resolution at 81%) and versus the 71 we would have frozen had we stopped at C001/C003 | — | measured, 0 GPU-h |
| A false-significant result caught before it shipped (D3) | exact p 0.625 reported as SIGNIFICANT | measured |
| A planned experiment retired for 0 GPU-h: `max_tool_calls: 200`. The agent used 28–30 of a 30 ceiling and a median 96–97 of a 100 ceiling, so it expands to fill whatever it is given and raising the ceiling buys nothing | `HANDOFF.md` §2 finding 1; `probe_c12`, `paired100_*` ledgers | measured, n=12, k=1 |
| **k=4 reference on clean-N: the direct SD of four identical runs** | — | **PENDING.** The paper's quantitative headline if it lands; §E stands without it |

Honest framing: the first three items are process savings, not score gains. The
paper must not imply the protocol improved the agent — it did not. What it did
was stop three wrong conclusions from being published and one allocation from
being wasted.

### §F — generalization (the "quality" criterion)

The protocol transfers to any benchmark with: a hidden test set, a private split
small enough to be noise-dominated, and an available reference solution.

- **Gold/null calibration** needs only a reference solution — every SWE-bench
  derivative has one.
- **Surrogate metrics from the oracle** generalize wherever the reference
  solution has structure to compare against (files touched, symbols, call
  sites), independent of the task's test suite.
- **The k=1 variance trap** is latent in any paired agent A/B that reports a
  z-score, which is most of them.
- **Pre-registered readings** cost nothing and are the only defence against
  narrating a null.
- Nothing in the protocol depends on Gemma, ADK, fastapi, or this harness.

### §G — limitations (write these, do not let a judge find them)

| Limitation | Statement |
|---|---|
| We did not improve the agent | **Three** submissions, no evidence of improvement or harm. The paper is about the instrument, and says so. |
| **Others did improve their agents, and we cannot say how** | The top of the board is 6 tasks clear of us, which is outside any noise band we can construct. The paper's claim is about the *resolution of the public signal at the scale most teams work at*, not that agent quality is unmeasurable. **State this explicitly in §G** — it is the most obvious objection and the board is public. |
| The rig resolves 0/12 at the grader's real budget | **Settled 2026-10-13, no longer three unseparated causes.** P005 ran v00 at 100 calls / 60 min: 0/12, max wall 47.0 min so the cap never bound, and all 12 tasks gold-verified resolvable so the harness is not the cause. The agent, not the rig, is the limit. |
| A confirmed mechanism turned out not to be a cause | P006 removed the `code_analyzer` sub-agent that consumed 90–98% of the budget in failing tasks (Spearman −0.90). The intervention worked completely — `coder_call_share` 0.543→1.000 at z=+6.02, first edit moved from call ~20 to ~6 — and `gold_hit` was **5/12 both ways, McNemar p=1.00**. Reported as a null, and as this paper's best worked example that **process metrics are not outcome evidence**. |
| The noise estimate is weak | n=3, two points third-party and not archive-verified. |
| The private-set size is derived, not published | 58 tasks is a unique exact fit to the public histogram (§D0), not a published number. It pins the displayed grid; a denominator sharing that grid would fit equally, and none does in 20…220. Still an inference, but a far stronger one than the "~60" it replaces. |
| n=12 at k=1 for the behavioural observations | A paired SE of 0.17–0.19 means only a delta above ~0.24 would register. Nothing in §E item 3 is significant; it is reported as a direction with its n. |
| Seeds do not buy determinism | vLLM is not bitwise deterministic under continuous batching. Seeds are set and logged; nothing is built on them. |

### §H — reproducibility

The repo, `bundle_hash` for byte-identity, the ledger (one row per task per
run), 187 tests, and the fact that the entire calibration protocol (§D1) runs
**CPU-only at 0 GPU-hours** and is therefore reproducible by anyone without an
L4×4.

## 4. Figures / tables (max 3, clarity criterion)

1. **The leaderboard histogram, in tasks (replaces "our four LB scores",
   2026-10-13).** 2643 teams against resolved-task count on the 58-task grid,
   with the 7/8/9-task mode (1,012 teams) shaded, our 8 marked, and the top's 14
   marked. This single figure carries §B, §D0 and the thesis's own bound at once,
   and it is reproducible by anyone from a public download at 0 GPU-h. Our three
   own scores become three ticks on it rather than a figure of their own.
2. **The calibration ladder.** C001→C004: gold 74→105, clean-N 71→102, with the
   two no-change runs shown as no-change.
3. **Variance by metric.** Resolution at p≈0.15 versus localization at p≈0.45,
   SE against n. Justifies D2 quantitatively.

## 5. Drafting order

Write the sections that cannot change first, so a late GPU result cannot force a
rewrite: **D → B → C → F → G → H → E → A.** Abstract last.

## 6. Open questions to settle before prose

1. Confirm word cap, criteria, submission mechanism in a browser (§0) — **and
   join the competition at all**, which is a hard gate (`userHasEntered: False`).
   Deadline, prize pool and entrant count are now verified via the API; the cap
   and criteria are third-party-corroborated but still unofficial.
2. Decide whether to name the competition's undocumented harness behaviours
   (`agent.yml` never discovered, bare `{hints}` KeyError, `..` accepted in
   `!include` but rejected in `config_path`, sub-agent calls consuming the root
   budget). They are genuinely useful to other entrants and support the
   verifiability criterion, but they are a catalogue rather than a finding and
   the word cap is tight. **Leaning: one compact table in §H**, as evidence of
   depth rather than as a contribution.
3. Whether to report the budget-anatomy material at all given n=12 — currently
   one row in §E with its n attached. Do not promote it.

## 7. Framings considered and rejected

Recorded so they are not reopened.

- **"Agents expand to fill their budget; instructions do not bind mid-loop, only
  capability removal does."** Higher novelty, and the evidence is real
  (re-issue rate *rose* 0.410→0.485 under explicit anti-repeat rules; the
  harness's own `budget_warning` was ignored 11 consecutive times). Rejected as
  the thesis because it rests on n=12 at k=1 where nothing is significant, and
  making it defensible needs GPU runs that compete with the main-track deadline.
  Demoted to one row of §E and one sentence of §F.
- **Both, methodology as spine.** Rejected on the clarity criterion: 3,000 words
  across two theses treats neither properly.
- **An agent-architecture paper (the orchestrator/specialist topology).** This
  was `PLAN.md`'s original plan for the paper's centrepiece (E6). Rejected
  because the architecture is built but not measured to help, and a paper
  claiming an architecture works without the measurement is exactly the error
  this paper is about.

---

## 9. §E fallback prose — written 2026-10-12, ships as-is

**Why this exists.** §E ("what the protocol bought") was the one section gated on
a pending measurement, the k=4 reference. After the rig failed twice on
environment drift inside five days, a paper section waiting on it is a schedule
risk with no upside: the deadline is 2026-11-12 and cannot be recovered by
compute. So the section is written here in its no-k=4 form. **If the k=4
reference lands, it is an upgrade — replace the bracketed paragraph. If it never
lands, the paper is complete as written.**

Word count below: ~470, against §E's 500 budget.

---

### What the protocol bought

The protocol's value is not a better agent. We do not have one: three submissions
produced no evidence of improvement and no evidence of harm, and our best
leaderboard score remains the one we got by faithfully reproducing the public
baseline. What the protocol bought was the ability to know that — and, four
times, it stopped a wrong conclusion from being published.

**It established what was measurable at all, for zero GPU-hours.** Gold/null
calibration moved the usable task set from a naive 129 to a calibrated 102.
Without it, every resolution rate we reported would have carried a silent ceiling
of 81%, and 18 tasks that fail under the reference solution itself would have been
counted as agent failures. Two of the four calibration runs returned bit-identical
verdicts and bought nothing, which is itself the finding: the instrument had to be
instrumented — capturing the test output, not theorising about the cause — before
it produced a diagnosis.

**It caught a false positive that would have shipped.** Our paired estimator
computed per-task variance as p(1-p)/k, which at k=1 is identically zero. It
therefore reported SE = 0.0000, z = infinity, and printed SIGNIFICANT for a
3-gained/1-lost split whose exact McNemar p is 0.625. The failure was protected
by a passing test suite: a test named `test_deterministic_arms_have_zero_variance`
asserted the broken behaviour as a feature, with a docstring describing it as
"the degenerate case that makes single-run McNemar dangerous". 187 tests passed
throughout. A test suite cannot catch a wrong statistical contract, because the
contract is what the test encodes.

**It retired a planned experiment without running it.** The agent used 28-30 of a
30-call ceiling and a median 96-97 of a 100-call ceiling: it expands to fill
whatever budget it is given, so raising the ceiling buys no resolution. One
re-reading of traces already on disk killed a planned run, for zero GPU-hours.

**It read the grader's resolution off a public download.** The displayed score is
a truncated ratio, so the set of occupied leaderboard positions identifies the
denominator exactly: 58 tasks, the only value in 20-220 whose grid reproduces all
14 occupied bins as consecutive integers. One task is therefore 0.0172, and two
hypotheses we had been carrying - "about 60 tasks" and "100 also fits" - were
retired without running anything. It also bounded our own thesis: the same
histogram puts 38% of 2643 teams within one task of us, and the top six tasks
clear of us. The first number is the paper's argument; the second is the honest
limit on it, and we would not have had either from our own submissions.

**It showed that a confirmed mechanism is not a cause.** We found that in four of
five failing tasks the agent never attempted an edit at all, while a sub-agent
consumed 90-98% of a shared 100-call budget, with a -0.90 rank correlation
between that share and outcome quality. We removed the sub-agent. The
intervention worked exactly as designed - the coder's share of calls went from
0.543 to 1.000 at z = +6.02, and the first edit moved from call 20 to call 6 -
and the outcome did not move at all: 5 of 12 gold-file hits either way, McNemar
p = 1.00. The freed budget was simply absorbed by the coder's own repetition. A
process metric moved by six standard errors and bought nothing, which is the
sharpest form of this paper's argument we have.

**And it told us when our own measurements could not adjudicate.** Applying the
power arithmetic of D4 to our only paired run reclassified it from "no
improvement" to "not measured": at k=1 the detectable delta is 0.064 against a
design target of 0.05. That is the uncomfortable result, because it applies to
the whole field. Every agent A/B we have seen published at this scale reports the
first and is entitled only to the second.

> **[UPGRADE IF THE k=4 REFERENCE LANDS]** Replace this paragraph with the
> measured SD of four identical runs on clean-N, and the same figure subsampled
> to the **58**-task private-set size (§D0). The second number is a direct empirical
> prediction of the leaderboard's own noise floor and would let §B's argument
> rest on our own measurement rather than on third-party reports. Expected
> 0.025-0.030 and 0.040-0.046 respectively; **do not write these numbers as
> results until measured.**

---

### Note on §B if the k=4 reference never lands

§B now leads on the **leaderboard histogram** (first-party, 2643 teams, 38%
inside a one-task band), then `v04_lean` (first-party, prompts byte-identical to
the baseline by `diff`, scored 0.10 against the baseline's 0.13 — i.e. one task),
with the third-party 0.12/0.15 reports as third-rank corroboration. That argument
is already self-sufficient and needs no k=4 run — **more so since 2026-10-13**,
because the histogram is a population measurement rather than a sample of three. **Do not strengthen the third-party triple
to compensate** for a missing k=4 — two of its three points were verified only by
cell-hashing the generating notebooks, never by comparing archives, and
overstating it is precisely the error this paper is about.

---

## 10. The official rubric, verbatim (read 2026-10-27, first-party)

Read off the paper track's overview page in a browser. **This replaces every
third-party figure in §0.** Each criterion is scored **0 (lowest) to 5
(highest)** and the final score is the **average of all five**. The Paper Award
goes to the **three** submissions with the most points; the rubric evaluation is
**never shared**; ties go to whichever paper was entered first.

| Criterion | Official wording |
|---|---|
| **Novelty** | "Does the work provide new insights, deepen understanding, or highlight important properties of existing methods?" |
| **Quality** | "How general and universal is the Submission approach beyond the competition? Does your submission translate to other similar problems? How well does your method generalize?" |
| **Relevance** | "Is there significance and/or potential impact of the research on the field of software engineering and agentic learning?" |
| **Verifiability** | "Does the paper include sufficient information to understand how an innovation works; to understand how data was obtained, analyzed, and interpreted?" |
| **Clarity** | "Is the paper clearly presented and written?" |

**Scope:** "3,000 words maximum, reporting original, unpublished research."
**Non-archival:** submission here does not prevent submission elsewhere.
**Deadline:** share the writeup by **November 12, 2026 at 11:59pm UTC**, and
"**Any un-submitted or draft Writeups by the competition deadline will not be
considered by the Judges**" — a saved draft is not a submission.
**Prize:** Overall Best Paper **$15,000** (the $35,000 figure elsewhere in our
notes is the track pool, not one award).
**Mechanism:** Kaggle Writeup — "New Writeup", then a **Submit** button appears
top-right. Optionally a Public Project Link may carry an arXiv-ready LaTeX/Word
PDF instead, and it must not require a login or paywall. Code, if attached, must
be a **public** notebook in the Project Links field; a private resource attached
to a public writeup is made public after the deadline.

### What the rubric changes about our plan

Nothing structural — the 3,000-word budget in §2 is confirmed, so the section
plan stands. Three things are now targetable rather than guessed:

1. **"Quality" is literally generality.** §F is not a nice-to-have appendix; it
   is 20% of the score, and it is the criterion our thesis is weakest on, since
   everything we measured is one competition, one harness, one model. §F must
   argue transfer concretely, component by component, which the drafted version
   already does.
2. **"Verifiability" rewards exactly what this project has.** The ledger, one row
   per task per run, `bundle_hash` byte-identity, 302 passing tests, and a
   calibration protocol that runs **CPU-only at 0 GPU-hours** so a reader with no
   L4x4 can reproduce it. §H is 100 words in the budget and is worth more than
   that; consider taking words from §E.
3. **"Novelty" accepts negative and methodological results explicitly** — "deepen
   understanding, or highlight important properties of existing methods". Our
   strongest material is negative (nine nulls, a treatment that causes its own
   conditioning variable, a power function that ignored n, a metric whose
   environment silently broke). That is on-criterion, not a consolation prize.
