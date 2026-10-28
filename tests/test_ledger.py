"""The ledger is the only thing standing between a 9-hour session kill and a lost week."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swegemma_lab.ledger import (
    Ledger,
    Row,
    iter_with_deadline,
    pool_by_bundle,
    read_all,
    read_rows,
    runs_per_bundle,
)
from swegemma_lab.stats import ArmStats, compare


def mkrow(iid, resolved=True, run_id="r1", bundle="h1", **kw):
    return Row(
        run_id=run_id,
        variant="v00",
        bundle_hash=bundle,
        seed=1001,
        concurrency=12,
        instance_id=iid,
        resolved=resolved,
        **kw,
    )


def test_append_and_read_roundtrip(tmp_path):
    led = Ledger(tmp_path, "r1")
    led.append(mkrow("t1"))
    led.append(mkrow("t2", resolved=False, error="timeout"))
    rows = read_rows(led.path)
    assert [r.instance_id for r in rows] == ["t1", "t2"]
    assert rows[1].error == "timeout"
    assert rows[0].resolved is True


def test_resume_is_a_set_difference(tmp_path):
    led = Ledger(tmp_path, "r1")
    for i in (1, 2, 5):
        led.append(mkrow(f"t{i}"))
    assert led.remaining([f"t{i}" for i in range(1, 7)]) == ["t3", "t4", "t6"]


def test_resume_preserves_requested_order(tmp_path):
    """Task order is fixed and shuffled once, for sequential stopping."""
    led = Ledger(tmp_path, "r1")
    led.append(mkrow("b"))
    assert led.remaining(["c", "b", "a"]) == ["c", "a"]


def test_torn_final_line_is_dropped_not_fatal(tmp_path):
    led = Ledger(tmp_path, "r1")
    led.append(mkrow("t1"))
    with led.path.open("a", encoding="utf-8") as fh:
        fh.write('{"run_id": "r1", "instance_id": "t2", "resol')  # SIGKILL mid-write
    rows = read_rows(led.path)
    assert [r.instance_id for r in rows] == ["t1"]
    assert led.remaining(["t1", "t2"]) == ["t2"]  # t2 gets retried, correctly


def test_unknown_fields_are_ignored(tmp_path):
    """A newer writer adding a column must not break an older reader."""
    led = Ledger(tmp_path, "r1")
    led.path.write_text(
        '{"run_id":"r1","variant":"v","bundle_hash":"h","seed":1,"concurrency":1,'
        '"instance_id":"t1","resolved":true,"some_future_column":42}\n',
        encoding="utf-8",
    )
    rows = read_rows(led.path)
    assert len(rows) == 1 and rows[0].instance_id == "t1"


def test_read_all_spans_runs(tmp_path):
    for run in ("r1", "r2"):
        led = Ledger(tmp_path, run)
        led.append(mkrow("t1", run_id=run))
    assert len(read_all(tmp_path)) == 2
    assert read_all(tmp_path / "nope") == []


def test_pooling_counts_runs_per_task(tmp_path):
    """Three runs of one bundle must become (resolved, 3) per task."""
    for run, resolved in (("r1", True), ("r2", False), ("r3", True)):
        led = Ledger(tmp_path, run)
        led.append(mkrow("t1", resolved=resolved, run_id=run))
    pooled = pool_by_bundle(read_all(tmp_path))
    assert pooled["h1"]["t1"] == (2, 3)


def test_pooling_separates_different_bundles(tmp_path):
    """An accidental prompt edit changes the hash, so it cannot be averaged in."""
    led = Ledger(tmp_path, "r1")
    led.append(mkrow("t1", bundle="hA"))
    led.append(mkrow("t1", bundle="hB", resolved=False))
    pooled = pool_by_bundle(read_all(tmp_path))
    assert pooled["hA"]["t1"] == (1, 1)
    assert pooled["hB"]["t1"] == (0, 1)


def test_runs_per_bundle(tmp_path):
    led = Ledger(tmp_path, "r1")
    led.append(mkrow("t1", bundle="hA"))
    led.append(mkrow("t2", bundle="hA"))
    led.append(mkrow("t1", bundle="hB"))
    rpb = runs_per_bundle(read_all(tmp_path))
    assert rpb["hA"] == {"r1"} and rpb["hB"] == {"r1"}


def test_ledger_feeds_the_estimator_end_to_end(tmp_path):
    """The whole point: accumulated runs turn straight into a comparison."""
    tasks = [f"t{i}" for i in range(40)]
    for run in ("a1", "a2"):
        led = Ledger(tmp_path, run)
        for i, t in enumerate(tasks):
            led.append(mkrow(t, resolved=i < 12, run_id=run, bundle="cand"))
    for run in ("b1", "b2"):
        led = Ledger(tmp_path, run)
        for i, t in enumerate(tasks):
            led.append(mkrow(t, resolved=i < 6, run_id=run, bundle="ref"))

    pooled = pool_by_bundle(read_all(tmp_path))
    cmp_ = compare(ArmStats("cand", pooled["cand"]), ArmStats("ref", pooled["ref"]))
    assert cmp_.n_tasks == 40
    assert cmp_.k_a == 2 and cmp_.k_b == 2
    assert cmp_.delta == (12 - 6) / 40
    assert len(cmp_.gained) == 6


def test_runspec_is_recorded_beside_the_results(tmp_path):
    led = Ledger(tmp_path, "r1")
    led.write_runspec({"variant": "v01_hygiene", "seed": 1002, "concurrency": 12})
    import json

    spec = json.loads((led.dir / "runspec.json").read_text(encoding="utf-8"))
    assert spec["variant"] == "v01_hygiene"


def test_deadline_guard_stops_launching_early():
    ids = [f"t{i}" for i in range(100)]
    # Deadline already inside the reserve window, so nothing may launch.
    assert list(iter_with_deadline(ids, deadline_minutes=10, stop_launching_before_end=45)) == []
    # Plenty of headroom, so everything launches.
    assert len(list(iter_with_deadline(ids, deadline_minutes=600, stop_launching_before_end=45))) == 100
