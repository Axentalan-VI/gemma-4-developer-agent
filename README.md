# Calibrate the Yardstick First

Companion repository to the Kaggle
[Gemma 4 Developer Agent Paper Track](https://www.kaggle.com/competitions/gemma-4-developer-agent-paper)
writeup *Calibrate the Yardstick First: Measurement Discipline for Agentic SWE
Benchmarks*.

The paper's claim is not that we built a better agent — we did not. It is that a
public leaderboard over a small hidden split can be too coarse to resolve what
its entrants are tuning, that moving the measurement in-house does not fix it on
its own, and that a benchmark harness has to be calibrated before it can rank
anything. This repository holds the protocol and the evidence behind that.

The manuscript is [`paper/MANUSCRIPT.md`](paper/MANUSCRIPT.md).

## The six components, and where each one lives

| Component | Implementation |
|---|---|
| **D0** recover the denominator from the public leaderboard | [`src/swegemma_lab/leaderboard.py`](src/swegemma_lab/leaderboard.py); board snapshots in [`data/leaderboard/`](data/leaderboard/) |
| **D1** gold/null calibration | [`scripts/calibrate.py`](scripts/calibrate.py); results are rows C001–C004 of [`EXPERIMENTS.md`](EXPERIMENTS.md) |
| **D2** prefer a lower-variance surrogate | `gold_hit` / `gold_exact` in [`src/swegemma_lab/metrics.py`](src/swegemma_lab/metrics.py) |
| **D3** pair, pool, and the k = 1 variance trap | [`src/swegemma_lab/stats.py`](src/swegemma_lab/stats.py) |
| **D4** price the experiment before running it | `detectable_delta` and `is_underpowered`, same file |
| **D5** pre-register the reading | the `MANIFEST.yaml` in each variant under [`bundles/`](bundles/) |

Supporting analysis: [`scripts/analyze_leaderboard.py`](scripts/analyze_leaderboard.py)
(D0 end to end), [`scripts/analyze_tasks.py`](scripts/analyze_tasks.py) (the task-set
shape that motivates D2), [`scripts/report.py`](scripts/report.py) (the three
metrics side by side, with the ship rule).

## The evidence

[`ledger/runs/`](ledger/runs/) holds **one row per task per run**. Every row
carries the `bundle_hash` of the configuration that produced it, so byte-identity
across runs is checkable rather than asserted, and repeated runs of one
configuration pool instead of competing.

`bundle_hash` is sha256 over sorted `(posix relpath, LF-normalised bytes)`.

The paper's headline comparison is the `cap60_v00` and `cap60_v08` runs: 36
paired tasks at the grader's real 60-minute budget, where one arm eliminated
every timeout (11 → 0, McNemar exact p = 0.00098) while resolution over the same
pairs gave **zero discordant pairs**, and so carried no information at any
sample size.

**One figure in the paper is not re-derivable here**, and the paper says so: the
73% / 76% test-log mismatch rates, whose raw `pytest` output was not committed.

## Running it

```bash
python -m pytest                        # 292 passed, 12 skipped
python scripts/analyze_leaderboard.py   # D0, from the committed snapshots
python scripts/analyze_tasks.py         # task-set shape (needs the task file)
python scripts/make_paper_figures.py    # regenerates the paper's three figures
```

Nine of those 12 skips need `data/tasks/tasks.jsonl` — the competition's own task
file, which includes its reference patches. **This repository does not
redistribute the organisers' data.** Download the competition data, place
`tasks.jsonl` at that path, and the suite reports **301 passed, 3 skipped** —
the figure the paper cites. Nothing is silently skipped: each skip prints the
reason and the fix.

Developed on CPython 3.13; `requirements.txt` covers the analysis path. Nothing
here needs a GPU — five of the six components are CPU-only by construction,
which is the point of the paper's reproducibility section.

## What is deliberately not here

- **`data/tasks/tasks.jsonl` and the agent traces.** Both carry the
  competition's own content — task statements, repository snapshots and
  reference patches. Redistributing them is not ours to do. The `.patch` files
  under `ledger/runs/*/patches/` are a different thing and are included: they
  are the agent's own output diffs, whose context lines quote only the public,
  MIT-licensed repositories under test.
- **Agent configurations that the paper does not cite**, and the operational
  tooling for running them on Kaggle. The main competition is live until
  2026-12-02; what is here is what the paper's claims rest on.
- **Vendored wheels.** 56 MB of ordinary PyPI packages, nothing you cannot fetch.
- **Working notes and forward plans.** This repository is the paper's evidence,
  not a project journal.

## Task-set facts behind D2

Computed by `scripts/analyze_tasks.py` over the 129 public tasks. These motivate
choosing gold-file localization as the lower-variance surrogate.

| | |
|---|---|
| Tasks | 129 (fastapi 67, rich 48, requests 13, httpx 1) |
| Reference patch touches exactly one file | **91 (71%)** |
| Reference patch churn, median / p90 | **12 / 128 lines** |
| Reference patches that create a new file | 0 |
| Reference patches touching a test or protected path | 0 |
| Reference patch file types | 100% `.py` |

After gold/null calibration the measurable set is **102 of 129** — 24 tasks fail
with the benchmark's own reference patch applied, and 3 pass with no patch at
all. That is the instrument's floor, and the paper treats it as a property to
measure and subtract rather than a bug to chase.

## Two rules this work holds itself to

**Reference patches are an offline metric oracle only.** All 129 are available
locally. Their sole sanctioned use is scoring localization after the fact.
Prompt text may be derived from failure traces, never from reference patches —
reading sixty of them and distilling them into instructions is overfitting with
extra steps.

**A surrogate is never the objective.** Localization carries the iteration loop
because it is cheap and lower-variance; resolution authorizes shipping, and the
ship rule in `stats.py` keys on resolution alone. Optimizing a surrogate is how
you win the surrogate.

## Layout

```
src/swegemma_lab/  leaderboard.py (D0), stats.py (D3, D4), metrics.py (D2),
                   validate.py, build.py, tasks.py
scripts/           CLI entry points
tests/             320 tests; conftest.py skips the 9 that need the task file
bundles/           authored agent configurations; each MANIFEST.yaml is a D5
                   pre-registration written before its run
ledger/runs/       one row per task per run, keyed by bundle_hash
data/leaderboard/  committed public-leaderboard snapshots (D0's input)
paper/             the manuscript, the generated submission text, the figures
kernels/           the two Kaggle notebooks behind cited results: the D1
                   calibration (CPU-only) and the headline paired run
EXPERIMENTS.md     per-run record, including the runs that failed
LESSONS.md         mistakes and their root causes
```

## Licence and citation

The writeup is released under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). If you use the
protocol, cite the writeup rather than this repository — it is the version of
record.
