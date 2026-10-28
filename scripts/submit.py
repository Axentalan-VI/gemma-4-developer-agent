"""Build, validate and submit one variant. One submission per day, so this
refuses to spend the slot on a bundle that has not passed every offline check.

    python scripts/submit.py --variant v01_hygiene --note "local clean-N 0.21 (k=2)"

Two non-obvious requirements are enforced here rather than left to memory:

- **The uploaded file must be named exactly `submission.zip`.** Any other name
  gets a bare `400 Bad Request` from the API with no explanation. Cost us one
  confusing failure before we worked it out.
- The submission message always carries the `bundle_hash`, so a leaderboard
  score can be matched back to the exact bytes that produced it. Without that
  the local-to-LB calibration map is guesswork, and identical-bundle reruns
  cannot be told apart from real changes.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swegemma_lab.build import build_bundle, package_bundle, roundtrip_check  # noqa: E402
from swegemma_lab.validate import adk_dry_load, validate_bundle  # noqa: E402

COMPETITION = "gemma-4-developer-agent"
#: The API rejects anything else with an unexplained 400.
REQUIRED_NAME = "submission.zip"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", required=True)
    ap.add_argument("--note", default="", help="local estimate and CI, e.g. 'clean-N 0.214 (k=4, CI 0.17-0.26)'")
    ap.add_argument("--ship-eval-config", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="validate and package, but do not submit")
    args = ap.parse_args(argv)

    result = build_bundle(
        args.variant,
        bundles_dir=ROOT / "bundles",
        out_root=ROOT / "dist",
        ship_eval_config=args.ship_eval_config,
    )
    print(result.render())

    report = validate_bundle(result.out_dir)
    dry = adk_dry_load(result.out_dir)
    if dry is not None:
        report.findings.append(dry)
    print("\n" + report.render())
    if not report.ok:
        print("\nrefusing to spend the daily submission slot on an invalid bundle")
        return 1

    zip_path = package_bundle(result.out_dir, ROOT / "dist" / REQUIRED_NAME)
    rt = validate_bundle(roundtrip_check(zip_path, ROOT / "dist" / "_roundtrip"))
    print(f"\npackaged {zip_path} ({zip_path.stat().st_size:,} B); round-trip {'PASS' if rt.ok else 'FAIL'}")
    if not rt.ok:
        print(rt.render())
        return 2

    # Keep a hash-named archive too, so dist/ stays a readable record of what
    # was sent even though the upload itself must use the canonical name.
    shutil.copy(zip_path, ROOT / "dist" / f"{args.variant}.zip")

    message = f"{args.variant}; bundle_hash {result.bundle_hash[:16]}"
    if args.note:
        message += f"; {args.note}"
    print(f"\nmessage: {message}")

    if args.dry_run:
        print("--dry-run: not submitting")
        return 0

    cmd = ["kaggle", "competitions", "submit", "-c", COMPETITION, "-f", str(zip_path), "-m", message]
    print("+ " + " ".join(cmd))
    rc = subprocess.call(cmd)
    if rc == 0:
        print("\nsubmitted. Record the score against this bundle_hash in the MANIFEST.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
