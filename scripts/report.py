"""Read the ledger and answer: did this bundle beat the champion?

    python scripts/report.py                                  # inventory + panels
    python scripts/report.py --arm v01_hygiene --baseline v00_public_baseline
    python scripts/report.py --arm v01_hygiene --baseline v00 --metric gold_hit

Every number comes from rows already on disk, so this costs no GPU and can be
run as often as you like. Nothing here launches anything.

Two metrics are reported side by side, not one:

* **resolved** is the competition metric and the noisiest readout available. At
  p around 0.15 the single-run paired SE is about 0.030, so a +0.03 change costs
  24 to 48 GPU-hours to resolve.
* **gold_hit** -- the agent's patch touched at least one file the gold patch
  touched -- sits near p=0.45 and is far more deterministic, so it detects a
  change 2 to 3 times smaller for the same spend. It needs no test execution and
  no hidden tests, only the 129 gold patches we already hold.

Read them together. Localization up with resolution flat means the agent is
finding the right file and fixing it wrongly, which is a different problem from
localization flat with resolution down. A change that moves neither has not been
measured, whatever the leaderboard says.

**Which metric decides what** (revised 2026-10-12, after a council review):

* **`gold_hit` carries the iteration loop.** It is what ranks candidate bundles
  between runs, because it is the only readout this project can actually afford
  to move: it needs no test execution, works on all 129 tasks rather than the
  102 of clean-N, and at p=0.45 detects a change 2-3x smaller for the same
  spend.
* **`resolved` authorizes shipping, and nothing else does.** The ship rule in
  `stats.decide` always keys on it. Localization is a triage instrument and a
  diagnosis; optimizing a surrogate is how you win the surrogate.

That split is the whole point and the two halves must not be swapped. What
changed is not the ship metric but the admission that at k=1 `resolved` cannot
adjudicate at all: the detectable delta is ~0.064 against a design target of
0.05, so every k=1 run returns "not significant" whatever the bundle does.
`stats.decide` now reports that as **UNDERPOWERED** rather than HOLD, because
"we could not measure" and "we measured and it did not help" are different
findings and the old rule printed the same word for both. P002 was the first
case and was recorded as HOLD.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swegemma_lab.ledger import (  # noqa: E402
    POOLABLE,
    Row,
    is_comparable,
    pool_by_bundle,
    read_all,
    runs_per_bundle,
)
from swegemma_lab.metrics import Panel, TaskOutcome, build_panel  # noqa: E402
from swegemma_lab.stats import (  # noqa: E402
    ArmStats,
    Comparison,
    compare,
    decide,
    is_underpowered,
    noise_floor,
)
from swegemma_lab.tasks import Task, load_tasks, split_of  # noqa: E402

#: Which pooled metrics get a comparison block. Order is the reading order.
REPORTED = ("resolved", "gold_hit", "gold_exact")

_METRIC_LABEL = {
    "resolved": "resolution rate (competition metric)",
    "gold_hit": "gold-file hit (localization, lower variance)",
    "gold_exact": "gold-file exact set (localization, strict)",
}


def resolve_arm(name: str, rows: list[Row]) -> tuple[str, str]:
    """Accept a variant name or a bundle_hash prefix; return (hash, label).

    Resolving to the *hash* rather than the name is the point: two runs of the
    same variant name can have different bytes, and pooling those together is
    the silent failure the hash exists to prevent. So a variant name that spans
    more than one hash is an error here, not an average.
    """
    hashes = {r.bundle_hash for r in rows if r.variant == name}
    if not hashes:
        hashes = {r.bundle_hash for r in rows if r.bundle_hash.startswith(name)}
    if not hashes:
        known = sorted({r.variant for r in rows})
        raise SystemExit(f"no ledger rows for {name!r}; known variants: {', '.join(known) or '(none)'}")
    if len(hashes) > 1:
        listed = "\n".join(f"    {h}" for h in sorted(hashes))
        raise SystemExit(
            f"{name!r} spans {len(hashes)} distinct bundle hashes, which must not be pooled:\n"
            f"{listed}\n  Name one of them explicitly."
        )
    h = hashes.pop()
    variants = sorted({r.variant for r in rows if r.bundle_hash == h})
    return h, f"{'/'.join(variants)}@{h[:16]}"


def arm_stats(
    rows: list[Row], bundle: str, label: str, metric: str, keep: set[str] | None
) -> ArmStats:
    pooled = pool_by_bundle(rows, metric=metric).get(bundle, {})
    if keep is not None:
        pooled = {i: c for i, c in pooled.items() if i in keep}
    return ArmStats(name=label, counts=pooled)


def panel_for(rows: list[Row], bundle: str, label: str, tasks: dict[str, Task]) -> Panel:
    """Diagnostic panel rebuilt from ledger rows alone.

    The patch text is not in the ledger, so the gold-overlap counts come from the
    stored flags rather than being recomputed. Everything that needs the diff
    itself -- created files, protected paths, scratch leaks -- is left at zero
    here and only appears in the runner's own panel, which has the patches in
    hand. Said plainly in the output rather than silently reported as zero.
    """
    outcomes = [
        TaskOutcome(
            instance_id=r.instance_id,
            resolved=r.resolved,
            error=r.error,
            tool_calls_used=r.tool_calls_used,
            wall_seconds=r.wall_seconds,
            turns=r.turns,
        )
        for r in rows
        if r.bundle_hash == bundle
    ]
    incomparable = [r for r in rows if r.bundle_hash == bundle and not is_comparable(r)]
    if incomparable and len(incomparable) == len([r for r in rows if r.bundle_hash == bundle]):
        ceilings = sorted({r.max_tool_calls for r in incomparable if r.max_tool_calls})
        label = f"{label}  [NOT A RESULT: probe at {ceilings or 'surrogate'} calls]"
    panel = build_panel(label, outcomes, tasks)
    # build_panel saw no patches, so overwrite the three it could not compute
    # from the stored flags...
    panel.gold_file_hit = sum(1 for r in rows if r.bundle_hash == bundle and r.gold_hit)
    panel.gold_file_exact = sum(1 for r in rows if r.bundle_hash == bundle and r.gold_exact)
    panel.non_empty = sum(1 for r in rows if r.bundle_hash == bundle and r.patch_bytes > 0)
    # ...and mark the ones no flag can stand in for. Without this the panel
    # prints "leaked scratch file 0.0%", which is what it did for P005 while 6
    # of that run's 7 patches were contaminated -- a false clean reading on the
    # metric that dominated its failure funnel.
    panel.hygiene_known = False
    return panel


def splits_of(tasks: dict[str, Task]) -> dict[str, set[str]]:
    """instance_ids grouped by generalization split, plus by repo.

    Both, because they answer different questions: the split decides shipping
    (does it hold up on rich, which is nothing like fastapi), and the repo
    breakdown is what tells you *why* when a split moves.
    """
    out: dict[str, set[str]] = {}
    for iid, t in tasks.items():
        out.setdefault(f"split:{split_of(t.repo)}", set()).add(iid)
        out.setdefault(f"repo:{t.repo}", set()).add(iid)
    return out


def comparisons_by_split(
    rows: list[Row],
    a_hash: str,
    a_label: str,
    b_hash: str,
    b_label: str,
    metric: str,
    groups: dict[str, set[str]],
    keep: set[str] | None,
    min_tasks: int = 5,
) -> dict[str, Comparison]:
    out: dict[str, Comparison] = {}
    for name, ids in sorted(groups.items()):
        sel = ids if keep is None else ids & keep
        if len(sel) < min_tasks:
            continue  # a 1-task slice is a number, not a measurement
        a = arm_stats(rows, a_hash, a_label, metric, sel)
        b = arm_stats(rows, b_hash, b_label, metric, sel)
        if not (a.tasks & b.tasks):
            continue
        out[name] = compare(a, b)
    return out


def inventory(rows: list[Row]) -> str:
    runs = runs_per_bundle(rows)
    lines = ["Ledger inventory", ""]
    if not rows:
        return "Ledger is empty: no runs recorded yet.\n\nNothing to report. Run scripts/session_runner.py first."
    # Listed with probes included, or a ledger holding only probe runs would
    # print an empty inventory and look like an empty ledger. They are labelled
    # instead, which is the honest rendering: the rows exist and are excluded.
    pooled = pool_by_bundle(rows, include_surrogate=True)
    bad = [r for r in rows if not is_comparable(r)]
    if bad:
        lines.insert(1, f"  {len(bad)} of {len(rows)} row(s) are NOT comparable and are excluded")
        lines.insert(2, "  from every delta below (probe budgets or surrogate weights).")
        lines.insert(3, "")
    for h in sorted(pooled, key=lambda k: -len(pooled[k])):
        variants = sorted({r.variant for r in rows if r.bundle_hash == h})
        counts = pooled[h]
        k_min = min((n for _, n in counts.values()), default=0)
        k_max = max((n for _, n in counts.values()), default=0)
        k = f"k={k_min}" if k_min == k_max else f"k={k_min}-{k_max} (uneven)"
        hrows = [r for r in rows if r.bundle_hash == h]
        tag = ""
        if not any(is_comparable(r) for r in hrows):
            ceilings = sorted({r.max_tool_calls for r in hrows if r.max_tool_calls})
            if any(r.surrogate for r in hrows):
                tag = "  [SURROGATE -- excluded]"
            else:
                tag = f"  [PROBE, {ceilings or '?'} calls -- excluded]"
        lines.append(
            f"  {h[:16]}  {'/'.join(variants):24s} {len(counts):4d} tasks  {k}  "
            f"{len(runs.get(h, ())):2d} run(s){tag}"
        )
    return "\n".join(lines)


def noise_block(rows: list[Row], bundle: str, keep: set[str] | None) -> str | None:
    """Run-to-run SD of one identical bundle: the empirical noise floor.

    This is the number that explains the leaderboard pile-up, and it costs
    nothing beyond having run the same bytes more than once. Reported per arm
    because it is a property of the configuration, not of the comparison.
    """
    per_run: dict[str, list[bool]] = {}
    for r in rows:
        if r.bundle_hash != bundle:
            continue
        if keep is not None and r.instance_id not in keep:
            continue
        per_run.setdefault(r.run_id, []).append(bool(r.resolved))
    rates = [sum(v) / len(v) for v in per_run.values() if v]
    if len(rates) < 2:
        return None
    mean, sd = noise_floor(rates)
    spread = max(rates) - min(rates)
    return "\n".join(
        [
            f"  noise floor: {len(rates)} runs of identical bytes, mean {mean:.4f}, "
            f"SD {sd:.4f}, spread {spread:.4f}",
            f"    Any delta below about {2 * sd:.3f} is indistinguishable from "
            "rerunning the same bundle.",
        ]
    )


def render_metric_block(
    metric: str,
    overall: Comparison,
    per_group: dict[str, Comparison],
) -> str:
    lines = [f"--- {_METRIC_LABEL.get(metric, metric)} ---", "", overall.render(), ""]
    for name, cmp_ in sorted(per_group.items()):
        lines.append(f"  {name:28s} {cmp_.delta:+.4f}  (n={cmp_.n_tasks}, z={cmp_.z:+.2f})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--ledger", default=str(ROOT / "ledger"), help="ledger root (holds runs/)")
    ap.add_argument("--tasks", default=str(ROOT / "data" / "tasks" / "tasks.jsonl"))
    ap.add_argument(
        "--task-list",
        default=str(ROOT / "data" / "tasks" / "clean_n.txt"),
        help="restrict to these instance_ids; every headline number is on clean-N",
    )
    ap.add_argument("--all-tasks", action="store_true", help="do not restrict to the task list")
    ap.add_argument("--arm", help="candidate: variant name or bundle_hash prefix")
    ap.add_argument("--baseline", help="reference arm to compare against")
    ap.add_argument(
        "--metric",
        choices=POOLABLE,
        help="apply the ship rule to this metric instead of resolved (not advised)",
    )
    ap.add_argument("--split-floor", type=float, default=-0.02)
    args = ap.parse_args(argv)

    rows = read_all(args.ledger)
    tasks = {t.instance_id: t for t in load_tasks(args.tasks)}

    keep: set[str] | None = None
    if not args.all_tasks and Path(args.task_list).is_file():
        keep = {
            ln.strip()
            for ln in Path(args.task_list).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        }
    scope = "all tasks" if keep is None else f"clean-N ({len(keep)} tasks)"

    print(inventory(rows))
    print()
    print(f"Scope: {scope}")
    if not rows:
        return 0

    if not (args.arm and args.baseline):
        for h in sorted({r.bundle_hash for r in rows}):
            label = f"{'/'.join(sorted({r.variant for r in rows if r.bundle_hash == h}))}@{h[:16]}"
            sel = [r for r in rows if keep is None or r.instance_id in keep]
            print()
            print(panel_for(sel, h, label, tasks).render())
            print("  (waste metrics read n/a above: they need the patch text, which the ledger")
            print("   does not carry. Use the run's own panel, or scripts/ingest_probe.py --write)")
        print()
        print("Pass --arm and --baseline for a comparison and a ship decision.")
        return 0

    a_hash, a_label = resolve_arm(args.arm, rows)
    b_hash, b_label = resolve_arm(args.baseline, rows)
    if a_hash == b_hash:
        raise SystemExit(f"--arm and --baseline are the same bundle ({a_hash[:16]}); nothing to compare")

    sel_rows = [r for r in rows if keep is None or r.instance_id in keep]
    groups = splits_of(tasks)

    print()
    for h, label in ((a_hash, a_label), (b_hash, b_label)):
        print(panel_for(sel_rows, h, label, tasks).render())
        nb = noise_block(sel_rows, h, keep)
        if nb:
            print(nb)
        print()

    ship_metric = args.metric or "resolved"
    overall_by_metric: dict[str, Comparison] = {}
    splits_by_metric: dict[str, dict[str, Comparison]] = {}
    for metric in REPORTED:
        a = arm_stats(sel_rows, a_hash, a_label, metric, keep)
        b = arm_stats(sel_rows, b_hash, b_label, metric, keep)
        if not (a.tasks & b.tasks):
            print(f"--- {_METRIC_LABEL[metric]} --- no paired tasks\n")
            continue
        overall_by_metric[metric] = compare(a, b)
        splits_by_metric[metric] = comparisons_by_split(
            sel_rows, a_hash, a_label, b_hash, b_label, metric, groups, keep
        )
        print(render_metric_block(metric, overall_by_metric[metric], splits_by_metric[metric]))
        print()

    if ship_metric not in overall_by_metric:
        raise SystemExit(f"cannot decide on {ship_metric}: the two arms share no paired tasks")

    overall = overall_by_metric[ship_metric]
    # The ship rule's split floor applies to the generalization splits only. A
    # per-repo slice can be 1 task wide, and failing a bundle on one task is how
    # you end up chasing noise with a rule that looks rigorous.
    gates = {k: v for k, v in splits_by_metric[ship_metric].items() if k.startswith("split:")}
    decision = decide(overall, gates, split_floor=args.split_floor)

    print("=== ship rule ===")
    if args.metric and args.metric != "resolved":
        print(f"  NOTE: applied to {args.metric}, not the competition metric. Surrogate only.")
    print(f"  (diagnostics and validator are not checked here -- run the validator separately)")
    print(decision.render())

    # An UNDERPOWERED verdict is an instruction, not a shrug: it says the
    # headline could not adjudicate, so read the surrogate for direction. Print
    # that read here rather than leaving the human to find it, and state
    # whether the surrogate was itself powered -- a localization null at k=1 is
    # just as uninformative as a resolution null at k=1.
    if decision.verdict == "UNDERPOWERED":
        loc_cmp = overall_by_metric.get("gold_hit")
        print()
        if loc_cmp is None:
            print("  No localization comparison available: the arms share no paired tasks on gold_hit.")
        else:
            loc_under = is_underpowered(loc_cmp)
            print(
                f"  Localization read: gold_hit {loc_cmp.delta:+.4f} (z={loc_cmp.z:+.2f}, "
                f"{'significant' if loc_cmp.significant else 'not significant'})."
            )
            if loc_under:
                print(
                    "  The surrogate is underpowered too, so this run ranked nothing. Spend the "
                    "next allocation on k, not on another bundle."
                )
            elif loc_cmp.significant:
                print(
                    "  The surrogate IS powered and moved: that is a direction to act on, and it "
                    "still does not ship the bundle."
                )
            else:
                print(
                    "  The surrogate is powered and did not move: the likeliest reading is that "
                    "this change does nothing to localization."
                )

    # The interesting case is a surrogate that moves while the headline does
    # not: that is a diagnosis, and it is also the signal the ship rule is
    # designed to ignore. Say both things, so neither gets lost.
    res = overall_by_metric.get("resolved")
    loc = overall_by_metric.get("gold_hit")
    if res is not None and loc is not None and loc.significant and not res.significant:
        print()
        print(
            f"  Diagnosis: localization improved {loc.delta:+.4f} (z={loc.z:+.2f}) while "
            f"resolution moved {res.delta:+.4f} (z={res.z:+.2f}, not significant)."
        )
        print(
            "  The agent is reaching the right file more often and still not fixing it, so the "
            "next change belongs in the repair loop, not in localization. This does not ship the "
            "bundle -- the ship rule keys on resolution -- but it is a reason to keep the change "
            "and fold it into the next one rather than discarding it."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
