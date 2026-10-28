"""Publish the lab code and built bundles as a private Kaggle Dataset.

Kaggle notebooks cannot see this repo, so `src/`, `scripts/` and the built
bundles ride in as an attached dataset. A new experiment is then a dataset
version bump plus a re-run of the same kernel -- no notebook edits, and the
runspec that produced each result is captured alongside it.

    python scripts/push_dataset.py --init          # first time only
    python scripts/push_dataset.py -m "v01 hygiene, seed 1002"
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swegemma_lab.build import build_bundle, compute_bundle_hash, declares_eval_config  # noqa: E402
from swegemma_lab.validate import validate_bundle  # noqa: E402

OWNER = "ahmedsherif382"
SLUG = "swegemma-lab"
STAGE = ROOT / "dist" / "_dataset"


def stage(variants: list[str], runspec: dict) -> Path:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    for sub in ("src", "scripts"):
        shutil.copytree(
            ROOT / sub,
            STAGE / sub,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".ipynb_checkpoints"),
        )

    hashes = {}
    for v in variants:
        # Ask the MANIFEST whether this variant exists in order to carry
        # eval_config.yaml. Without this the file was silently stripped here --
        # so the PUBLISHED dataset held v08's bytes under v10's name, and a
        # local run of the v10 arm would have measured the clamp with no time
        # cap and recorded v08's bundle_hash in the ledger. Since the
        # 2026-10-21 guard in build.py this raises instead of lying, which is
        # how it was found; the fix is to pass the flag, not to catch it.
        ship = declares_eval_config(v, ROOT / "bundles")
        result = build_bundle(v, bundles_dir=ROOT / "bundles", out_root=STAGE / "bundles",
                              ship_eval_config=ship)
        report = validate_bundle(result.out_dir)
        if not report.ok:
            raise SystemExit(f"refusing to publish an invalid bundle:\n{report.render()}")
        if ship and not (result.out_dir / "eval_config.yaml").is_file():
            raise SystemExit(f"{v} declares ships_eval_config but the staged bundle has no "
                             "eval_config.yaml; refusing to publish the parent's bytes")
        hashes[v] = result.bundle_hash
        print(f"  {v}: {result.bundle_hash[:16]}  {len(result.files)} files"
              + ("  +eval_config" if ship else ""))

    for name in ("split_dev.txt", "split_confirm.txt", "split_audit.txt", "all_ids.txt",
                 "clean_n.txt", "clean_dev.txt", "clean_confirm.txt",
                 # Seed-1001 sample of clean_dev, 36 tasks. A 60-minute cap makes
                 # each wave cost an hour, so 5 waves would not fit a session.
                 "clean_dev36.txt",
                 # The 12 tasks probe_c12 ran, so the 100-call re-run is paired
                 # on identical tasks rather than merely similar ones.
                 "probe12.txt"):
        src = ROOT / "data" / "tasks" / name
        if src.is_file():
            (STAGE / "tasks").mkdir(exist_ok=True)
            shutil.copy(src, STAGE / "tasks" / name)

    # Vendored wheels, mirrored subdirectory for subdirectory. Kaggle GPU kernels
    # have no internet (this competition refuses it with the L4 accelerator), so
    # anything pip would fetch has to travel in the dataset.
    #
    #   vendor/test_deps/ -- inline_snapshot + dirty_equals, which session_runner
    #                        requires and stage_test_deps.py would fetch from PyPI.
    #   vendor/cp313/     -- cp313 builds of the 9 wheels the competition
    #                        wheelhouse ships only as cp312, after Kaggle moved the
    #                        GPU image to Python 3.13 on 2026-10-07. Same versions,
    #                        so this is a retag, not an upgrade.
    vendor = ROOT / "vendor"
    if vendor.is_dir():
        for sub in sorted(p for p in vendor.iterdir() if p.is_dir()):
            wheels = sorted(sub.glob("*.whl"))
            if not wheels:
                continue
            dst = STAGE / "vendor" / sub.name
            dst.mkdir(parents=True, exist_ok=True)
            for w in wheels:
                shutil.copy(w, dst / w.name)
            print(f"  vendor/{sub.name}: {len(wheels)} wheel(s)")

    runspec["bundle_hashes"] = hashes
    (STAGE / "runspec.json").write_text(json.dumps(runspec, indent=2), encoding="utf-8", newline="\n")
    return STAGE


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-m", "--message", default="update", help="dataset version note")
    ap.add_argument("--init", action="store_true", help="create the dataset instead of versioning it")
    ap.add_argument("--variant", action="append", default=None, help="repeatable; default = every bundle")
    ap.add_argument("--seed", type=int, default=1001)
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--task-list", default="all_ids.txt")
    ap.add_argument("--deadline-minutes", type=int, default=480)
    ap.add_argument("--dry-run", action="store_true", help="stage only, do not call the Kaggle API")
    args = ap.parse_args(argv)

    variants = args.variant or sorted(
        p.name for p in (ROOT / "bundles").iterdir() if p.is_dir() and not p.name.startswith("_")
    )
    runspec = {
        "variant": variants[0],
        "seed": args.seed,
        "concurrency": args.concurrency,
        "task_list": args.task_list,
        "deadline_minutes": args.deadline_minutes,
        "resume_run_id": None,
    }

    print(f"staging {len(variants)} variant(s)")
    stage(variants, runspec)

    meta = {
        "title": "swegemma lab",
        "id": f"{OWNER}/{SLUG}",
        "licenses": [{"name": "unknown"}],
    }
    (STAGE / "dataset-metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8", newline="\n")

    total = sum(p.stat().st_size for p in STAGE.rglob("*") if p.is_file())
    print(f"staged {STAGE} ({total:,} B)")
    if args.dry_run:
        return 0

    # `-r zip` archives each subdirectory for a fast single-shot upload, and
    # Kaggle extracts them on ingest, so the notebooks still see real paths like
    # /kaggle/input/swegemma-lab/scripts/inspect_harness.py. Verified against the
    # live dataset listing; switch to `--dir-mode skip` if that ever changes.
    cmd = (
        ["kaggle", "datasets", "create", "-p", str(STAGE), "-r", "zip"]
        if args.init
        else ["kaggle", "datasets", "version", "-p", str(STAGE), "-m", args.message, "-r", "zip"]
    )
    print("+ " + " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
