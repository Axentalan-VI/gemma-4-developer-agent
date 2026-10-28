"""Ingest probe_ledger.zip / probe_results.zip downloaded from a Kaggle session.

    python scripts/ingest_probe.py --zips results/probe
    python scripts/ingest_probe.py --zips ~/Downloads --write

`kaggle kernels output` returns the last *committed* version, which for an
interactive session is whatever was last saved -- not what is live in the
session. On 2026-10-06 that returned a five-day-old 212-byte zip holding two
empty directories while the finished run sat in the browser. So the zips get
downloaded by hand from the session's Output panel, and this files them.

Accepts either shape, because the two zips are rooted differently:
  probe_ledger.zip   -> runs/<run_id>/task_results.jsonl
  probe_results.zip  -> <run_id>/{task_results.jsonl,patches/*.patch}

It refuses to overwrite an existing ledger run, since a ledger is append-only
evidence and a silent overwrite is how a measurement gets lost.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swegemma_lab.ledger import LEDGER_NAME, Row  # noqa: E402
from swegemma_lab.metrics import gold_overlap, load_outcomes  # noqa: E402
from swegemma_lab.tasks import load_tasks  # noqa: E402


def extract(zips: Path, dest: Path) -> list[Path]:
    found = sorted(zips.glob("*.zip"))
    if not found:
        raise SystemExit(f"no .zip files in {zips}")
    out: list[Path] = []
    for z in found:
        with zipfile.ZipFile(z) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            if not names:
                print(f"  {z.name}: EMPTY (only directory entries) -- skipping")
                print("    This is the signature of a stale committed version, not a")
                print("    failed download. Download from the session's Output panel.")
                continue
            target = dest / z.stem
            zf.extractall(target)
            print(f"  {z.name}: {len(names)} file(s) -> {target}")
            out.append(target)
    return out


def is_ledger(jsonl: Path) -> bool:
    """True if this file already holds ledger rows, not raw harness results.

    The two arrive under the same filename and look superficially alike, but a
    ledger row carries its own `variant` and `bundle_hash` while a harness result
    carries neither. The distinction is load-bearing: rebuilding rows from a real
    ledger would stamp every arm with one `--variant`, labelling one bundle's
    results as another's and pooling them into the wrong reference arm.
    """
    try:
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            return isinstance(row, dict) and "bundle_hash" in row and "variant" in row
    except (OSError, json.JSONDecodeError):
        return False
    return False  # empty file


def find_runs(where: Path) -> dict[str, Path]:
    """run_id -> directory holding task_results.jsonl, preferring a REAL ledger.

    Both zips of a paired run contain `<run_id>/task_results.jsonl`: the ledger zip
    holds rows already stamped with their arm's variant, hash and budgets, and the
    results zip holds the harness's own output, which carries none of that. Taking
    whichever `rglob` reaches first is a coin flip, and on the first paired run it
    came up wrong -- v03's twelve rows were filed as `v00_public_baseline` with
    v00's bundle_hash and `max_tool_calls=30`, which would have pooled both arms
    into the reference and made the comparison meaningless.

    So a real ledger always wins, regardless of walk order.
    """
    runs: dict[str, Path] = {}
    for jl in sorted(where.rglob(LEDGER_NAME)):
        d = jl.parent
        if d.name not in runs or (is_ledger(jl) and not is_ledger(runs[d.name] / LEDGER_NAME)):
            runs[d.name] = d
    return runs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--zips", required=True, help="directory holding the downloaded zips")
    ap.add_argument("--ledger", default=str(ROOT / "ledger"))
    ap.add_argument("--tasks", default=str(ROOT / "data" / "tasks" / "tasks.jsonl"))
    ap.add_argument("--variant", default="v00_public_baseline")
    ap.add_argument("--bundle-hash", default="6f3c38bf51665b0145c6106ba45a1c83816ca027e3718c39f12437ee8178ed28")
    ap.add_argument("--max-tool-calls", type=int, default=30,
                    help="the ceiling the run USED; probe_c12 used 30, not the grader's 100")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    staging = Path(args.zips) / "_extracted"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    print(f"extracting from {args.zips}")
    extract(Path(args.zips), staging)

    runs = find_runs(staging)
    if not runs:
        print()
        print("No task_results.jsonl found in any zip.")
        print("If the zips were empty, they came from a stale committed version:")
        print("  open the notebook, go to the Output panel, download the files there.")
        return 1

    tasks = {t.instance_id: t for t in load_tasks(args.tasks)}
    print()
    for run_id, d in sorted(runs.items()):
        dest = Path(args.ledger) / "runs" / run_id / LEDGER_NAME

        # A real ledger is copied verbatim. Its rows already carry the variant,
        # bundle_hash and budgets that session_runner recorded, and a paired run
        # has one set PER ARM -- so rebuilding them from a single --variant would
        # relabel one arm as the other.
        src = d / LEDGER_NAME
        if is_ledger(src):
            n = sum(1 for x in src.read_text(encoding="utf-8").splitlines() if x.strip())
            meta = set()
            for line in src.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    meta.add((r.get("variant"), str(r.get("bundle_hash"))[:16]))
            print(f"{run_id}: {n} ledger row(s) already stamped "
                  f"{sorted(meta)} -- copying verbatim")
            if dest.exists():
                print(f"  ledger already exists at {dest}; refusing to overwrite")
                continue
            if not args.write:
                print(f"  would copy {n} row(s) to {dest} (pass --write)")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dest)
            print(f"  wrote {dest}")
            continue

        outcomes = load_outcomes(d)
        n_patch = sum(1 for o in outcomes if not o.empty)
        n_res = sum(1 for o in outcomes if o.resolved)
        hits = sum(1 for o in outcomes if gold_overlap(o, tasks.get(o.instance_id))[0])
        print(f"{run_id}: {len(outcomes)} task(s), {n_res} resolved, "
              f"{n_patch} non-empty patch(es), {hits} gold-file hit(s)")

        dest = Path(args.ledger) / "runs" / run_id / LEDGER_NAME
        if dest.exists():
            print(f"  ledger already exists at {dest}; refusing to overwrite")
            continue
        rows = []
        for o in outcomes:
            hit, exact = gold_overlap(o, tasks.get(o.instance_id))
            rows.append(Row(
                run_id=run_id,
                variant=args.variant,
                bundle_hash=args.bundle_hash,
                seed=1001,
                concurrency=12 if "c12" in run_id else 2,
                instance_id=o.instance_id,
                resolved=o.resolved,
                error=o.error,
                tool_calls_used=o.tool_calls_used,
                wall_seconds=o.wall_seconds,
                patch_bytes=len(o.patch),
                task_list="clean_n.txt",
                gold_hit=hit,
                gold_exact=exact,
                files_touched=len(o.files),
                # Recorded so is_comparable keeps these probe rows out of any
                # reference arm. They share v00's bundle_hash and would
                # otherwise pool straight into it.
                max_tool_calls=args.max_tool_calls,
                max_model_len=32768,
            ))
        if not args.write:
            print(f"  would write {len(rows)} row(s) to {dest} (pass --write)")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w", encoding="utf-8", newline="\n") as fh:
            for r in rows:
                fh.write(r.to_json() + "\n")
        print(f"  wrote {len(rows)} row(s) to {dest}")

    patches = sorted(staging.rglob("*.patch"))
    print()
    print(f"{len(patches)} patch file(s) found")
    for p in patches:
        body = p.read_text(encoding="utf-8", errors="replace")
        files = sorted({ln[6:].strip() for ln in body.splitlines() if ln.startswith("+++ b/")})
        print(f"  {p.stem:28s} {len(body):6d} B  {files}")

    # PERSIST them, next to the rows they belong to. Listing them for a human to
    # read was not enough: `metrics.read_outcomes` looks for
    # <run_id>/patches/<instance_id>.patch, so without this every hygiene metric
    # (created file, protected path, scratch leak) is structurally uncomputable
    # and the panel reported a clean 0.0%. P005 was the case that exposed it --
    # 6 of its 7 patches were contaminated while the panel showed none.
    if patches and args.write:
        copied = 0
        for p in patches:
            # .../<run_id>/patches/<iid>.patch, so the run id is two levels up.
            run_id = p.parent.parent.name if p.parent.name == "patches" else p.parent.name
            dest = Path(args.ledger) / "runs" / run_id / "patches" / p.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
            copied += 1
        print(f"  persisted {copied} patch file(s) under {Path(args.ledger) / 'runs'}")
    elif patches:
        print("  (pass --write to persist these; hygiene metrics need them on disk)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
