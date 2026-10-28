"""Tests for the ledger-only reporting path.

The thing worth protecting here is that localization survives the trip home.
The patches live in the swegemma results directory, which does not always come
back from a Kaggle session; the ledger always does. So the gold-overlap flags
have to be computed at write time and stored, and `report.py` has to be able to
rebuild the panel from rows alone.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from swegemma_lab.ledger import Ledger, Row, pool_by_bundle, read_all  # noqa: E402
from swegemma_lab.metrics import TaskOutcome, build_panel, gold_overlap  # noqa: E402
from swegemma_lab.tasks import Task  # noqa: E402

import report  # noqa: E402


DIFF_A = """diff --git a/pkg/core.py b/pkg/core.py
--- a/pkg/core.py
+++ b/pkg/core.py
@@ -1,1 +1,1 @@
-x = 1
+x = 2
"""

DIFF_B = """diff --git a/pkg/other.py b/pkg/other.py
--- a/pkg/other.py
+++ b/pkg/other.py
@@ -1,1 +1,1 @@
-y = 1
+y = 2
"""

GOLD = DIFF_A


def task(iid: str = "t1", repo: str = "fastapi/fastapi", patch: str = GOLD) -> Task:
    return Task(instance_id=iid, repo=repo, base_commit="deadbeef", problem_statement="p", patch=patch)


# --- gold_overlap -------------------------------------------------------------


def test_gold_overlap_hit_and_exact_when_files_match():
    o = TaskOutcome(instance_id="t1", resolved=False, patch=DIFF_A)
    assert gold_overlap(o, task()) == (True, True)


def test_gold_overlap_hit_but_not_exact_when_patch_is_a_superset():
    o = TaskOutcome(instance_id="t1", resolved=False, patch=DIFF_A + DIFF_B)
    assert gold_overlap(o, task()) == (True, False)


def test_gold_overlap_misses_the_wrong_file():
    o = TaskOutcome(instance_id="t1", resolved=False, patch=DIFF_B)
    assert gold_overlap(o, task()) == (False, False)


def test_empty_patch_is_neither_a_hit_nor_exact():
    o = TaskOutcome(instance_id="t1", resolved=False, patch="")
    assert gold_overlap(o, task()) == (False, False)


def test_unknown_task_is_not_counted_as_a_miss():
    """No gold reference is absence of evidence, not a failed localization."""
    o = TaskOutcome(instance_id="t1", resolved=False, patch=DIFF_A)
    assert gold_overlap(o, None) == (False, False)


def test_build_panel_agrees_with_gold_overlap():
    outcomes = [
        TaskOutcome("t1", False, DIFF_A),
        TaskOutcome("t2", False, DIFF_B),
        TaskOutcome("t3", False, DIFF_A + DIFF_B),
    ]
    tasks = {"t1": task("t1"), "t2": task("t2"), "t3": task("t3")}
    p = build_panel("x", outcomes, tasks)
    assert (p.gold_file_hit, p.gold_file_exact) == (2, 1)


# --- pooling ------------------------------------------------------------------


def _row(**kw):
    base = dict(
        run_id="r0",
        variant="v",
        bundle_hash="h" * 64,
        seed=1,
        concurrency=1,
        instance_id="t1",
        resolved=False,
    )
    base.update(kw)
    return Row(**base)


def test_pool_by_bundle_defaults_to_resolved():
    rows = [_row(resolved=True), _row(run_id="r1", resolved=False)]
    assert pool_by_bundle(rows)["h" * 64]["t1"] == (1, 2)


def test_pool_by_bundle_can_pool_localization():
    rows = [_row(gold_hit=True), _row(run_id="r1", gold_hit=True)]
    pooled = pool_by_bundle(rows, metric="gold_hit")
    assert pooled["h" * 64]["t1"] == (2, 2)
    # and the default metric is unaffected by the same rows
    assert pool_by_bundle(rows)["h" * 64]["t1"] == (0, 2)


def test_pool_by_bundle_rejects_an_unknown_metric():
    with pytest.raises(ValueError, match="metric must be one of"):
        pool_by_bundle([_row()], metric="wall_seconds")


def test_old_rows_without_the_new_fields_still_parse(tmp_path):
    """Rows written before gold_hit existed must not break the reader."""
    d = tmp_path / "runs" / "legacy"
    d.mkdir(parents=True)
    (d / "task_results.jsonl").write_text(
        '{"run_id":"legacy","variant":"v00","bundle_hash":"abc","seed":1,'
        '"concurrency":1,"instance_id":"t1","resolved":true}\n',
        encoding="utf-8",
    )
    rows = read_all(tmp_path)
    assert len(rows) == 1
    assert rows[0].gold_hit is False
    assert rows[0].files_touched == 0


# --- report.py ----------------------------------------------------------------


def _ledger(tmp_path, specs):
    """specs: [(variant, hash_char, [(iid, resolved, gold_hit), ...], n_runs)]"""
    root = tmp_path / "ledger"
    for variant, ch, outcomes, n_runs in specs:
        for i in range(n_runs):
            led = Ledger(root, f"{variant}-r{i}")
            for iid, resolved, hit in outcomes:
                led.append(
                    _row(
                        run_id=f"{variant}-r{i}",
                        variant=variant,
                        bundle_hash=ch * 64,
                        instance_id=iid,
                        resolved=resolved,
                        gold_hit=hit,
                        gold_exact=hit,
                        patch_bytes=100,
                    )
                )
    return root


def test_resolve_arm_accepts_a_variant_name_and_a_hash_prefix(tmp_path):
    root = _ledger(tmp_path, [("v00", "a", [("t1", True, True)], 1)])
    rows = read_all(root)
    assert report.resolve_arm("v00", rows)[0] == "a" * 64
    assert report.resolve_arm("aaaa", rows)[0] == "a" * 64


def test_resolve_arm_refuses_to_pool_one_name_across_two_hashes(tmp_path):
    """The whole point of hashing: an unnoticed prompt edit must not average in."""
    root = _ledger(tmp_path, [("v00", "a", [("t1", True, True)], 1), ("v00", "b", [("t1", False, True)], 1)])
    rows = read_all(root)
    with pytest.raises(SystemExit, match="spans 2 distinct bundle hashes"):
        report.resolve_arm("v00", rows)


def test_resolve_arm_rejects_an_unknown_name(tmp_path):
    root = _ledger(tmp_path, [("v00", "a", [("t1", True, True)], 1)])
    with pytest.raises(SystemExit, match="no ledger rows"):
        report.resolve_arm("nope", read_all(root))


def test_panel_from_rows_uses_the_stored_localization_flags(tmp_path):
    root = _ledger(
        tmp_path,
        [("v00", "a", [("t1", True, True), ("t2", False, True), ("t3", False, False)], 1)],
    )
    rows = read_all(root)
    tasks = {i: task(i) for i in ("t1", "t2", "t3")}
    p = report.panel_for(rows, "a" * 64, "v00", tasks)
    assert p.n == 3
    assert p.resolved == 1
    assert p.gold_file_hit == 2  # from the rows, not from patches we do not have


def test_noise_block_needs_two_runs(tmp_path):
    one = _ledger(tmp_path / "one", [("v00", "a", [("t1", True, True)], 1)])
    assert report.noise_block(read_all(one), "a" * 64, None) is None
    two = _ledger(tmp_path / "two", [("v00", "a", [("t1", True, True)], 2)])
    assert "noise floor" in report.noise_block(read_all(two), "a" * 64, None)


def test_report_runs_end_to_end_and_refuses_to_ship_a_flat_result(tmp_path):
    """Verdict is UNDERPOWERED, not HOLD, and that is correct for this fixture.

    The fixture is 10 tasks at k=2. Since 2026-10-21 `detectable_delta` scales
    with n, so this design prices at ~0.162 against a 0.05 target -- it could
    not have seen the effect, which is precisely what UNDERPOWERED means. It read
    HOLD until then only because the power calculation ignored n, i.e. this test
    was asserting that bug as a feature. Both verdicts refuse to ship; the
    distinction is whether we measured a null or failed to measure.
    """
    outcomes_a = [(f"t{i}", i < 2, i < 5) for i in range(10)]
    outcomes_b = [(f"t{i}", i < 2, i < 5) for i in range(10)]
    root = _ledger(tmp_path, [("v00", "a", outcomes_a, 2), ("v01", "b", outcomes_b, 2)])
    tasks_file = tmp_path / "tasks.jsonl"
    import json

    tasks_file.write_text(
        "\n".join(
            json.dumps(
                {
                    "instance_id": f"t{i}",
                    "repo": "fastapi/fastapi",
                    "base_commit": "x",
                    "problem_statement": "p",
                    "patch": GOLD,
                }
            )
            for i in range(10)
        ),
        encoding="utf-8",
    )
    r = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "report.py"),
            "--ledger", str(root),
            "--tasks", str(tasks_file),
            "--all-tasks",
            "--arm", "v01",
            "--baseline", "v00",
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "resolution rate (competition metric)" in r.stdout
    assert "gold-file hit (localization" in r.stdout
    # Identical arms: delta is exactly zero, so the ship rule must refuse.
    assert "UNDERPOWERED" in r.stdout, "10 tasks at k=2 prices at ~0.162; it measured nothing"
    assert "HOLD" not in r.stdout
    assert "is not positive" in r.stdout


def test_report_refuses_to_compare_a_bundle_against_itself(tmp_path, task_data):
    root = _ledger(tmp_path, [("v00", "a", [("t1", True, True)], 1)])
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "report.py"), "--ledger", str(root),
         "--all-tasks", "--arm", "v00", "--baseline", "aaaa"],
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    assert "same bundle" in r.stderr


def test_report_on_an_empty_ledger_says_so_rather_than_failing(tmp_path, task_data):
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "report.py"), "--ledger", str(tmp_path / "nope")],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "Ledger is empty" in r.stdout


# --- surrogate isolation ------------------------------------------------------
#
# A surrogate run serves different weights behind the same declared model name,
# so its bundle is byte-identical and its bundle_hash is the real one. If those
# rows pooled, a pipeline test on a 4B model would silently move the reference
# arm it appears to belong to. These tests exist to keep that from happening.


def test_surrogate_rows_are_excluded_from_pooling_by_default():
    rows = [_row(resolved=True), _row(run_id="r1", resolved=False, surrogate=True)]
    pooled = pool_by_bundle(rows)
    assert pooled["h" * 64]["t1"] == (1, 1), "the surrogate row must not be counted"


def test_surrogate_rows_can_be_inspected_on_request():
    rows = [_row(resolved=True), _row(run_id="r1", resolved=False, surrogate=True)]
    pooled = pool_by_bundle(rows, include_surrogate=True)
    assert pooled["h" * 64]["t1"] == (1, 2)


def test_an_all_surrogate_bundle_pools_to_nothing():
    """The arm must vanish, not appear with a plausible-looking rate."""
    rows = [_row(resolved=True, surrogate=True), _row(run_id="r1", resolved=True, surrogate=True)]
    assert pool_by_bundle(rows) == {}


def test_surrogate_flag_survives_a_ledger_round_trip(tmp_path):
    led = Ledger(tmp_path, "run0")
    led.append(_row(surrogate=True, model_served="/models/qwen3-4b"))
    back = read_all(tmp_path)
    assert back[0].surrogate is True
    assert back[0].model_served == "/models/qwen3-4b"


def test_report_ignores_a_surrogate_only_arm(tmp_path):
    """report.py must say the arm is unknown rather than charting fake numbers."""
    root = tmp_path / "ledger"
    led = Ledger(root, "surrogate-run")
    for i in range(5):
        led.append(
            _row(
                run_id="surrogate-run",
                variant="v00",
                bundle_hash="a" * 64,
                instance_id=f"t{i}",
                resolved=True,
                gold_hit=True,
                surrogate=True,
            )
        )
    rows = read_all(root)
    assert pool_by_bundle(rows) == {}
    assert "Ledger inventory" in report.inventory(rows)
