"""Build, validate and package one bundle variant.

    python scripts/build_bundle.py --variant v00_public_baseline
    python scripts/build_bundle.py --variant v01_hygiene --zip --strict

Exits non-zero if validation found errors, so this is safe to gate a submission on.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swegemma_lab.build import build_bundle, package_bundle, roundtrip_check  # noqa: E402
from swegemma_lab.validate import adk_dry_load, validate_bundle  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", required=True, help="directory name under bundles/")
    ap.add_argument("--zip", action="store_true", help="also write dist/<variant>.zip and round-trip check it")
    ap.add_argument("--ship-eval-config", action="store_true", help="include eval_config.yaml in the bundle")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    ap.add_argument("--expect-hash", help="fail unless bundle_hash equals this value")
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
    print()
    print(report.render())

    if args.expect_hash and result.bundle_hash != args.expect_hash:
        print(f"\nERROR hash mismatch: expected {args.expect_hash}, got {result.bundle_hash}")
        return 3

    if args.zip:
        if not report.ok:
            print("\nrefusing to package a bundle with errors")
            return 1
        zip_path = package_bundle(result.out_dir, ROOT / "dist" / f"{args.variant}.zip")
        extracted = roundtrip_check(zip_path, ROOT / "dist" / "_roundtrip")
        rt = validate_bundle(extracted)
        print(f"\npackaged {zip_path} ({zip_path.stat().st_size:,} B)")
        print(f"round-trip: {'PASS' if rt.ok else 'FAIL'}")
        if not rt.ok:
            print(rt.render())
            return 2

    if not report.ok:
        return 1
    if args.strict and report.warnings:
        print("\n--strict: warnings present")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
