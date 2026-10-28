"""Print the public task set's real shape, and write the repo-split task lists.

Run this before designing any prompt. Several widely-repeated community claims
about this dataset are computed-at-runtime in notebooks that ship no outputs, so
the numbers were never actually published.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swegemma_lab.tasks import (  # noqa: E402
    churn,
    count_hunks,
    is_protected,
    load_tasks,
    split_of,
    summarize,
)


def main() -> int:
    tasks = load_tasks(ROOT / "data" / "tasks" / "tasks.jsonl")
    print(summarize(tasks).render())

    print("\n--- gold patch file types ---")
    ext = Counter(f.rsplit(".", 1)[-1] if "." in f else "(none)" for t in tasks for f in t.gold_files)
    print("  " + ", ".join(f"{e} {c}" for e, c in ext.most_common(8)))

    print("\n--- test_patch ---")
    with_tp = [t for t in tasks if t.test_patch.strip()]
    print(f"  non-empty: {len(with_tp)}/{len(tasks)}")
    only_tests = [t for t in with_tp if t.test_files and all(is_protected(f) for f in t.test_files)]
    print(f"  touches only protected/test paths: {len(only_tests)}/{len(with_tp)}")
    overlap = [t for t in tasks if t.gold_files & t.test_files]
    print(f"  shares a file with the gold patch: {len(overlap)}")

    print("\n--- files per gold patch ---")
    nf = Counter(len(t.gold_files) for t in tasks)
    print("  " + ", ".join(f"{k} file(s): {v}" for k, v in sorted(nf.items())))

    print("\n--- hunks per gold patch ---")
    nh = Counter(min(count_hunks(t.patch), 6) for t in tasks)
    print("  " + ", ".join(f"{'6+' if k == 6 else k} hunk(s): {v}" for k, v in sorted(nh.items())))

    print("\n--- largest and smallest gold patches ---")
    ranked = sorted(((sum(churn(t.patch)), len(t.gold_files), t.instance_id) for t in tasks), reverse=True)
    for c, n, i in ranked[:5]:
        print(f"  {c:5d} lines  {n} file(s)  {i}")
    print("  ...")
    for c, n, i in ranked[-5:]:
        print(f"  {c:5d} lines  {n} file(s)  {i}")

    print("\n--- problem statement length by split ---")
    for split in ("dev", "confirm", "audit"):
        lens = sorted(len(t.problem_statement) for t in tasks if split_of(t.repo) == split)
        if lens:
            print(f"  {split:8s} n={len(lens):3d}  p50={lens[len(lens) // 2]:5d}  max={lens[-1]:5d}")

    out = ROOT / "data" / "tasks"
    for split in ("dev", "confirm", "audit"):
        ids = [t.instance_id for t in tasks if split_of(t.repo) == split]
        (out / f"split_{split}.txt").write_text("\n".join(ids) + "\n", encoding="utf-8", newline="\n")
    (out / "all_ids.txt").write_text("\n".join(t.instance_id for t in tasks) + "\n", encoding="utf-8", newline="\n")
    print(f"\nwrote split_{{dev,confirm,audit}}.txt and all_ids.txt to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
