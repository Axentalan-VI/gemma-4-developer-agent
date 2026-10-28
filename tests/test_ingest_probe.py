"""Tests for filing a Kaggle run's zips into the ledger.

The thing worth protecting: a zip can contain either of two different things with
the same filename, and confusing them corrupts the comparison.

- `eval_ledger.zip` holds **real ledger rows**, written by `session_runner`, each
  already carrying its own `variant` and `bundle_hash`.
- `eval_results.zip` holds the **harness's** per-task results, which carry no
  variant or hash at all, so rows have to be rebuilt and stamped from the CLI.

`ingest_probe.py` was written for the second case, when a single-arm probe lost
everything but its results directory. Applied to a *paired* run it would stamp
every arm with one `--variant`/`--bundle-hash`, labelling v03's rows as v00 and
pooling them into the reference arm -- which is precisely the corruption the
`surrogate` flag exists to prevent elsewhere. So a file that is already a ledger
must be copied verbatim.
"""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from swegemma_lab.ledger import LEDGER_NAME  # noqa: E402

import ingest_probe  # noqa: E402


def _ledger_row(run_id, variant, bundle_hash, instance_id, resolved=False):
    return {
        "run_id": run_id, "variant": variant, "bundle_hash": bundle_hash,
        "seed": 1001, "concurrency": 12, "instance_id": instance_id,
        "resolved": resolved, "error": "", "tool_calls_used": 7,
        "wall_seconds": 12.5, "patch_sha": "", "patch_bytes": 10,
        "gold_hit": False, "gold_exact": False, "files_touched": 1,
        "task_list": "probe12.txt", "finished_at": 0.0,
        "max_tool_calls": 100, "max_model_len": 32768, "surrogate": False,
    }


def _zip_ledger(tmp_path, name, runs):
    """runs: {run_id: [row, ...]} zipped as runs/<run_id>/task_results.jsonl."""
    z = tmp_path / name
    with zipfile.ZipFile(z, "w") as zf:
        for run_id, rows in runs.items():
            body = "\n".join(json.dumps(r) for r in rows) + "\n"
            zf.writestr(f"runs/{run_id}/{LEDGER_NAME}", body)
    return z


def test_is_ledger_distinguishes_the_two_shapes(tmp_path):
    led = tmp_path / "a.jsonl"
    led.write_text(json.dumps(_ledger_row("r", "v00", "h", "t1")) + "\n", encoding="utf-8")
    assert ingest_probe.is_ledger(led)

    harness = tmp_path / "b.jsonl"
    harness.write_text(json.dumps({"instance_id": "t1", "resolved": True}) + "\n",
                       encoding="utf-8")
    assert not ingest_probe.is_ledger(harness)


def test_empty_file_is_not_a_ledger(tmp_path):
    p = tmp_path / "c.jsonl"
    p.write_text("", encoding="utf-8")
    assert not ingest_probe.is_ledger(p)


def test_paired_arms_keep_their_own_variant_and_hash(tmp_path, task_data):
    """The regression. Two arms in one zip must not be collapsed onto one variant."""
    zips = tmp_path / "zips"
    zips.mkdir()
    _zip_ledger(zips, "eval_ledger.zip", {
        "paired100_v00": [_ledger_row("paired100_v00", "v00_public_baseline", "aaa", "t1"),
                          _ledger_row("paired100_v00", "v00_public_baseline", "aaa", "t2")],
        "paired100_v03": [_ledger_row("paired100_v03", "v03_budget_guard", "bbb", "t1"),
                          _ledger_row("paired100_v03", "v03_budget_guard", "bbb", "t2")],
    })
    ledger = tmp_path / "ledger"
    rc = ingest_probe.main([
        "--zips", str(zips), "--ledger", str(ledger),
        "--tasks", str(ROOT / "data" / "tasks" / "tasks.jsonl"),
        # Deliberately wrong on the CLI: a real ledger must ignore these entirely.
        "--variant", "WRONG", "--bundle-hash", "WRONGHASH", "--write",
    ])
    assert rc == 0

    for run_id, variant, bh in (("paired100_v00", "v00_public_baseline", "aaa"),
                                ("paired100_v03", "v03_budget_guard", "bbb")):
        f = ledger / "runs" / run_id / LEDGER_NAME
        assert f.is_file(), f"{run_id} not filed"
        rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
        assert len(rows) == 2
        assert {r["variant"] for r in rows} == {variant}, "CLI variant leaked into a real ledger"
        assert {r["bundle_hash"] for r in rows} == {bh}
        assert all(r["max_tool_calls"] == 100 for r in rows), "budgets must survive"


def test_existing_ledger_run_is_never_overwritten(tmp_path, task_data):
    zips = tmp_path / "zips"
    zips.mkdir()
    _zip_ledger(zips, "eval_ledger.zip",
                {"paired100_v00": [_ledger_row("paired100_v00", "v00_public_baseline", "aaa", "t1")]})
    ledger = tmp_path / "ledger"
    dest = ledger / "runs" / "paired100_v00" / LEDGER_NAME
    dest.parent.mkdir(parents=True)
    dest.write_text("SENTINEL\n", encoding="utf-8")

    ingest_probe.main(["--zips", str(zips), "--ledger", str(ledger),
                       "--tasks", str(ROOT / "data" / "tasks" / "tasks.jsonl"), "--write"])
    assert dest.read_text(encoding="utf-8") == "SENTINEL\n", "append-only evidence was overwritten"


def test_dry_run_writes_nothing(tmp_path, task_data):
    zips = tmp_path / "zips"
    zips.mkdir()
    _zip_ledger(zips, "eval_ledger.zip",
                {"paired100_v00": [_ledger_row("paired100_v00", "v00_public_baseline", "aaa", "t1")]})
    ledger = tmp_path / "ledger"
    ingest_probe.main(["--zips", str(zips), "--ledger", str(ledger),
                       "--tasks", str(ROOT / "data" / "tasks" / "tasks.jsonl")])
    assert not (ledger / "runs" / "paired100_v00" / LEDGER_NAME).exists()


def test_a_real_ledger_wins_over_harness_results_for_the_same_run(tmp_path, task_data):
    """Both zips contain `<run_id>/task_results.jsonl`, and the harness one carries
    no variant. If that copy wins, every arm gets stamped with one --variant.

    This actually happened on the first paired run: v03's rows were filed as
    v00_public_baseline with v00's bundle_hash and max_tool_calls=30, because
    find_runs took whichever directory rglob reached first.
    """
    zips = tmp_path / "zips"
    zips.mkdir()
    # Real ledger, rooted at runs/<run_id>/
    _zip_ledger(zips, "eval_ledger.zip",
                {"paired100_v03": [_ledger_row("paired100_v03", "v03_budget_guard", "bbb", "t1")]})
    # Harness results for the SAME run_id, rooted at <run_id>/ and with no variant.
    with zipfile.ZipFile(zips / "eval_results.zip", "w") as zf:
        zf.writestr(f"paired100_v03/{LEDGER_NAME}",
                    json.dumps({"instance_id": "t1", "resolved": True,
                                "patch": "", "tool_calls_used": 5}) + "\n")

    ledger = tmp_path / "ledger"
    ingest_probe.main(["--zips", str(zips), "--ledger", str(ledger),
                       "--tasks", str(ROOT / "data" / "tasks" / "tasks.jsonl"),
                       "--variant", "WRONG", "--write"])
    rows = [json.loads(x) for x in
            (ledger / "runs" / "paired100_v03" / LEDGER_NAME).read_text(encoding="utf-8").splitlines()
            if x.strip()]
    assert {r["variant"] for r in rows} == {"v03_budget_guard"}, "harness copy won over the ledger"
    assert {r["max_tool_calls"] for r in rows} == {100}, "budgets were overwritten by CLI defaults"
