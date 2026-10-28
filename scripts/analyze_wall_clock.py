"""Where does a task's wall clock actually go?

    python scripts/analyze_wall_clock.py --arm graph_v00 --arm graph_v06 \
        --results <dir containing results/<arm>/traces>

Reads ATIF traces plus the ledger rows and decomposes per-task elapsed time. No
GPU, no test execution: everything here is already on disk.

Why this exists. P007 established that **wall clock, not the 100-call budget, is
the binding constraint** -- resolution is 0.143 among tasks that finish against
0.050 overall. This script answers the follow-up question, and the answer is not
the intuitive one:

* **Per-step latency is set by DECODE, not prefill.** Pooled over 120 task-runs,
  corr(completion tokens per step, seconds per step) = **+0.968**. The same
  correlation for *prompt* tokens is **negative** (-0.44), because terse tasks
  get through more steps and so accumulate more context.
* So `total_prompt_tokens` is a **misleading** cost proxy even though it is 97%
  of all tokens processed. Tasks that time out had *fewer* prompt tokens
  (286k vs 842k median) because they never got as far.
* Verbosity is not bought quality. Binning tasks by completion tokens per step,
  seconds per step rises 10.6 -> 58.4 while `gold_hit` *falls* 10/15 -> 7/15.

The practical consequence: the lever on wall clock is **tokens generated per
step** (`thinking_budget`, `max_output_tokens`, and prompt pressure toward terse
steps), not context size and not the tool mix -- the run_command mix is near
identical between tasks that finish and tasks that time out (grep 55% vs 60%).

Caveat to keep attached to any number here: this is a cross-task correlation, so
a task that rambles may simply be a harder task. The *timing* half is mechanical
(decode is sequential, so tokens cost seconds); the *quality* half only shows
that verbosity does not help, not that forcing terseness is free.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson r, written out to keep this script dependency-free."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((a - mx) ** 2 for a in xs) ** 0.5
    sy = sum((b - my) ** 2 for b in ys) ** 0.5
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / (sx * sy)


def collect(arm: str, results: Path) -> list[dict]:
    """One record per task: per-step decode, prefill, latency and outcome."""
    ledger = ROOT / "ledger" / "runs" / arm / "task_results.jsonl"
    rows = {r["instance_id"]: r for r in (json.loads(l) for l in ledger.open(encoding="utf-8"))}
    out = []
    for path in sorted((results / arm / "traces").glob("trace_*.json")):
        row = rows.get(path.stem.replace("trace_", ""))
        if row is None:
            continue
        trace = json.loads(path.read_text(encoding="utf-8"))
        steps = [s for s in trace["steps"] if s["source"] == "agent" and s.get("metrics")]
        wall = row.get("wall_seconds") or 0
        if not steps or not wall:
            continue
        fm = trace["final_metrics"]
        out.append(
            dict(
                instance_id=row["instance_id"],
                steps=len(steps),
                sec_per_step=wall / len(steps),
                completion_per_step=fm["total_completion_tokens"] / len(steps),
                prompt_per_step=fm["total_prompt_tokens"] / len(steps),
                wall_minutes=wall / 60,
                timed_out="timeout" in (row.get("error") or ""),
                gold_hit=bool(row["gold_hit"]),
                resolved=bool(row["resolved"]),
            )
        )
    return out


def report(arm: str, recs: list[dict]) -> None:
    dec = [r["completion_per_step"] for r in recs]
    pre = [r["prompt_per_step"] for r in recs]
    sec = [r["sec_per_step"] for r in recs]
    print(f"\n== {arm}  n={len(recs)}")
    print(f"   corr(completion/step, sec/step) = {pearson(dec, sec):+.3f}   <- decode, the driver")
    print(f"   corr(prompt    /step, sec/step) = {pearson(pre, sec):+.3f}   <- prefill")

    for flag in (True, False):
        g = [r for r in recs if r["timed_out"] is flag]
        if not g:
            continue
        med = lambda k: st.median(r[k] for r in g)  # noqa: E731
        print(f"   {'TIMED OUT' if flag else 'COMPLETED':9s} n={len(g):3d}"
              f" | steps {med('steps'):5.0f} | sec/step {med('sec_per_step'):5.1f}"
              f" | completion/step {med('completion_per_step'):5.0f}"
              f" | prompt/step {med('prompt_per_step'):7,.0f}")

    recs = sorted(recs, key=lambda r: r["completion_per_step"])
    q = len(recs) // 4
    print("   by verbosity quartile (does spending tokens buy quality?)")
    for i, label in enumerate(("Q1 terse", "Q2", "Q3", "Q4 verbose")):
        g = recs[i * q:(i + 1) * q] if i < 3 else recs[3 * q:]
        print(f"     {label:11s} completion/step {st.median(r['completion_per_step'] for r in g):6.0f}"
              f" | sec/step {st.median(r['sec_per_step'] for r in g):5.1f}"
              f" | gold_hit {sum(r['gold_hit'] for r in g):2d}/{len(g)}"
              f" | resolved {sum(r['resolved'] for r in g)}/{len(g)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", action="append", required=True,
                    help="ledger run_id, repeatable (e.g. --arm graph_v00)")
    ap.add_argument("--results", type=Path, required=True,
                    help="directory holding results/<arm>/traces")
    args = ap.parse_args()

    pooled: list[dict] = []
    for arm in args.arm:
        recs = collect(arm, args.results)
        if not recs:
            print(f"no traces matched for {arm} under {args.results}", file=sys.stderr)
            continue
        report(arm, recs)
        pooled += recs

    if len(pooled) > len(args.arm):
        dec = [r["completion_per_step"] for r in pooled]
        pre = [r["prompt_per_step"] for r in pooled]
        sec = [r["sec_per_step"] for r in pooled]
        print(f"\n== POOLED n={len(pooled)}")
        print(f"   corr(completion/step, sec/step) = {pearson(dec, sec):+.3f}")
        print(f"   corr(prompt    /step, sec/step) = {pearson(pre, sec):+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
