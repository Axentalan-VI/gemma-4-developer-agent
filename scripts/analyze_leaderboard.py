"""Read the public leaderboard's shape: how many tasks, how wide the board is.

Answers the questions the project kept guessing at -- how large is the private
set, what is one task worth, and how far is the top from us -- from public
aggregates at 0 GPU-hours. See `swegemma_lab.leaderboard` for the method and
its caveats.

    python scripts/analyze_leaderboard.py
    python scripts/analyze_leaderboard.py --snapshot data/leaderboard/<other>.json

Refresh the snapshot with:

    kaggle competitions leaderboard gemma-4-developer-agent --download -p <dir>

then aggregate it to a histogram; the roster is deliberately not committed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swegemma_lab.leaderboard import (  # noqa: E402
    DisplayMode,
    Snapshot,
    fit_denominator,
    tasks_for_score,
)

DEFAULT = ROOT / "data" / "leaderboard" / "public_lb_2026-10-19.json"
EVIDENCE_THRESHOLD = 0.06  # the project's own rule; see CLAUDE.md


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", type=Path, default=DEFAULT)
    args = ap.parse_args()

    snap = Snapshot.load(args.snapshot)
    scores = snap.occupied_scores()
    fit = fit_denominator(scores)

    print(f"--- {snap.competition} @ {snap.captured_utc} ---")
    print(f"  teams scored      : {snap.teams}")
    print(f"  occupied bins     : {len(scores)}  ({scores[0]} .. {scores[-1]})")
    print(f"  private task count: {fit.render()}")

    if not fit.unique:
        print("\n  Fit is not unique -- do not quote a task count from this snapshot.")
        return 1

    n = fit.denominators[0]
    top, ours = scores[-1], float(snap.our_team["score"])
    print(f"  one task is worth : {1 / n:.4f}")

    print("\n--- the board in tasks ---")
    for s in reversed(scores):
        k = tasks_for_score(s, n)
        at = snap.teams_at_or_above(s)
        mark = "  <-- us" if abs(s - ours) < 1e-9 else ""
        print(f"  {s:>5.2f} = {k:3d}/{n} tasks | {snap.histogram[f'{s:.2f}']:4d} teams | {at:4d} at or above{mark}")

    gap = top - ours
    print(f"\n--- where we stand ---")
    print(f"  rank {snap.our_team['rank']} of {snap.teams} with {ours:.2f} "
          f"= {tasks_for_score(ours, n)}/{n} tasks ({snap.histogram[f'{ours:.2f}']} teams tied)")
    print(f"  top is {top:.2f} = {tasks_for_score(top, n)}/{n}; "
          f"gap {gap:.2f} = {tasks_for_score(top, n) - tasks_for_score(ours, n)} tasks")
    verdict = "ABOVE" if gap > EVIDENCE_THRESHOLD else "below"
    print(f"  that gap is {verdict} this project's {EVIDENCE_THRESHOLD} evidence threshold")
    if gap > EVIDENCE_THRESHOLD:
        print("  => the distance to the top is a real effect, not leaderboard noise.")
    print("\n  Display convention observed:", fit.mode.value if fit.mode else "?")
    print("  (11/58 = 0.1897 -> 0.18 floors, 0.19 rounds; the board shows 0.18.)")
    assert fit.mode is DisplayMode.TRUNCATE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
