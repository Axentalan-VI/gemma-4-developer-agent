"""Calibrate the measurement instrument. CPU only, zero GPU quota.

Phase 2 verification never touches the model: `verify_task` takes the patch as a
plain string. So the entire grading path runs with no vLLM at all, which makes
the two runs that decide whether any later number means anything free.

  gold -- feed each task its own `patch`. Every task MUST resolve. One that does
          not is broken: it can never be scored, so it is pure variance in the
          denominator of every future run.
  null -- feed the empty patch. Every task MUST fail. One that resolves is a
          free point that lifts every config equally and dilutes the signal
          between them.

The surviving intersection is **clean-N**, and every number in this project is
reported on clean-N rather than on the raw 129.

    python scripts/calibrate.py --mode gold --out results/gold
    python scripts/calibrate.py --mode null --out results/null
    python scripts/calibrate.py --reconcile results/gold results/null
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def _evaluator(mode: str, config):
    """Evaluator with Phase 1 replaced by a constant, so no model is needed.

    Subclassing rather than reimplementing keeps snapshot resolution, wheel
    staging, container bootstrap and verification exactly as the grader runs
    them. A hand-rolled verification path would calibrate the wrong thing.
    """
    from swegemma.evaluate import Evaluator

    class CalibrationEvaluator(Evaluator):
        async def _run_agent_sandbox(self, task, snapshot_path, *args, **kwargs):
            # The third element is the SessionTrace. There is no trajectory to
            # trace here, and save_trace_artifact returns early on None
            # (verification.py:46), so we return None rather than import
            # SessionTrace -- one less module path to get wrong on a Kaggle run.
            return (task.patch if mode == "gold" else ""), None, None

    return CalibrationEvaluator(config)


def run(mode: str, data_dir: Path, out_dir: Path, task_ids: list[str] | None, limit: int | None) -> int:
    from swegemma.config import EvalConfig
    from swegemma.models import load_tasks

    tasks = load_tasks(data_dir / "tasks.jsonl")
    if task_ids:
        wanted = set(task_ids)
        tasks = [t for t in tasks if t.instance_id in wanted]
    if limit:
        tasks = tasks[:limit]
    print(f"{mode}: {len(tasks)} tasks")

    out_dir.mkdir(parents=True, exist_ok=True)
    config = EvalConfig(
        tasks_path=data_dir / "tasks.jsonl",
        snapshots_dir=data_dir / "snapshots",
        results_dir=out_dir,
        submission_dir=data_dir / "sample_submission",  # never compiled: Phase 1 is stubbed
        models={},
        sandbox="subprocess",
        wheels_dir=data_dir / "wheels",
        graph_dir=str(data_dir / "graphs"),
        embeddings_dir=str(data_dir / "embeddings"),
        # Phase 2 only, so agent budgets are irrelevant. The command timeout is
        # not: some of these test suites are slow and 300s can truncate them.
        timeout_seconds=600,
        skip_agent_patch=(mode == "null"),
        verbose=False,
    )

    ev = _evaluator(mode, config)
    ledger = out_dir / "calibration.jsonl"
    done: set[str] = set()
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["instance_id"])
            except Exception:
                pass
        print(f"  resuming: {len(done)} already done")

    todo = [t for t in tasks if t.instance_id not in done]
    expected = mode == "gold"
    for i, task in enumerate(todo, 1):
        t0 = time.perf_counter()
        try:
            res = asyncio.run(ev.evaluate_task(task=task, task_index=i, total_tasks=len(todo)))
            row = {
                "instance_id": task.instance_id,
                "repo": task.repo,
                "mode": mode,
                "resolved": bool(res.resolved),
                "test_exit_code": getattr(res, "test_exit_code", None),
                "error": (getattr(res, "error", "") or "")[:400],
                "patch_chars": len(getattr(res, "agent_patch", "") or ""),
                # Keep the pytest tail. Without it a failure is only an exit
                # code, and diagnosing exit=2 (collection error) versus exit=1
                # (tests failed) from the outside costs another run.
                "test_output_tail": (getattr(res, "test_output", "") or "")[-2500:],
                "seconds": round(time.perf_counter() - t0, 1),
            }
        except Exception as exc:  # a crash is a datum, not a reason to lose the run
            row = {
                "instance_id": task.instance_id,
                "repo": task.repo,
                "mode": mode,
                "resolved": False,
                "test_exit_code": None,
                "error": f"{type(exc).__name__}: {exc}"[:400],
                "patch_chars": -1,
                "test_output_tail": "",
                "seconds": round(time.perf_counter() - t0, 1),
            }
        with ledger.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        flag = "ok " if row["resolved"] == expected else "BAD"
        print(
            f"  [{i}/{len(todo)}] {flag} {task.instance_id:22s} "
            f"resolved={str(row['resolved']):5s} {row['seconds']:6.1f}s {row['error'][:70]}"
        )

    rows = [json.loads(x) for x in ledger.read_text(encoding="utf-8").splitlines() if x.strip()]
    agree = sum(1 for r in rows if r["resolved"] == expected)
    print(f"\n{mode}: {agree}/{len(rows)} behaved as required ({agree / max(1, len(rows)):.1%})")
    return 0


def reconcile(gold_dir: Path, null_dir: Path, out: Path) -> int:
    """Intersect the two runs into clean-N and account for every exclusion."""

    def rows(d: Path) -> dict[str, dict]:
        f = d / "calibration.jsonl"
        if not f.is_file():
            raise SystemExit(f"missing {f}")
        acc: dict[str, dict] = {}
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                acc[r["instance_id"]] = r
        return acc

    g, n = rows(gold_dir), rows(null_dir)
    shared = sorted(set(g) & set(n))
    print(f"gold {len(g)} rows, null {len(n)} rows, {len(shared)} in both")

    clean: list[str] = []
    excluded: list[dict] = []
    for iid in shared:
        gold_ok = g[iid]["resolved"] is True
        null_ok = n[iid]["resolved"] is False
        if gold_ok and null_ok:
            clean.append(iid)
            continue
        reason = (
            "gold patch does not resolve (task is unscoreable)"
            if not gold_ok
            else "resolves with an empty patch (free point)"
        )
        excluded.append(
            {
                "instance_id": iid,
                "repo": g[iid]["repo"],
                "reason": reason,
                "gold_error": g[iid]["error"],
                "null_error": n[iid]["error"],
            }
        )

    print(f"\nclean-N = {len(clean)} of {len(shared)}")
    if excluded:
        print(f"excluded {len(excluded)}:")
        for e in excluded:
            print(f"  {e['instance_id']:22s} {e['reason']}")
            if e["gold_error"]:
                print(f"      gold: {e['gold_error'][:150]}")

    out.mkdir(parents=True, exist_ok=True)
    (out / "clean_n.txt").write_text("\n".join(clean) + "\n", encoding="utf-8", newline="\n")
    (out / "excluded.json").write_text(
        json.dumps(excluded, indent=2), encoding="utf-8", newline="\n"
    )
    print(f"\nwrote {out / 'clean_n.txt'} and {out / 'excluded.json'}")
    print("\nEvery future number is reported on clean-N. If gold did not resolve at")
    print("close to 100%, the instrument is miscalibrated and nothing downstream is")
    print("trustworthy yet -- fix that before spending a single GPU-hour.")
    return 0


def preflight() -> int:
    """Import everything and print where it came from, before any work starts.

    A wrong module path otherwise costs a whole kernel run to discover, and the
    harness is not installable locally, so this is the only cheap place to catch
    it. Run as the first cell of the notebook.
    """
    ok = True
    for mod, name in (
        ("swegemma.config", "EvalConfig"),
        ("swegemma.models", "load_tasks"),
        ("swegemma.evaluate", "Evaluator"),
        ("swegemma.harness.verification", "verify_task"),
    ):
        try:
            m = __import__(mod, fromlist=[name])
            obj = getattr(m, name)
            print(f"  ok   {mod}.{name}  <- {getattr(m, '__file__', '?')}")
            del obj
        except Exception as exc:
            ok = False
            print(f"  FAIL {mod}.{name}: {type(exc).__name__}: {exc}")
    print("")
    print("preflight:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--mode", choices=("gold", "null"))
    ap.add_argument("--data-dir", default="/kaggle/input/competitions/gemma-4-developer-agent")
    ap.add_argument("--out", default="results/calib")
    ap.add_argument("--task-ids", nargs="*")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--reconcile", nargs=2, metavar=("GOLD_DIR", "NULL_DIR"))
    ap.add_argument("--clean-out", default="data/tasks")
    ap.add_argument("--preflight", action="store_true", help="check imports only, then exit")
    args = ap.parse_args(argv)

    if args.preflight:
        return preflight()
    if args.reconcile:
        return reconcile(Path(args.reconcile[0]), Path(args.reconcile[1]), Path(args.clean_out))
    if not args.mode:
        ap.error("--mode is required unless --reconcile or --preflight is given")
    return run(args.mode, Path(args.data_dir), Path(args.out), args.task_ids, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
