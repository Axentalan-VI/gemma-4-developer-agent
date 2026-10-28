"""clean-N decides the denominator of every later number, so its logic is tested.

The calibration runs themselves need the mounted competition data, but the
reconcile step is pure set logic and belongs under test here.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location("calibrate", ROOT / "scripts" / "calibrate.py")
calibrate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(calibrate)


def write(d: Path, rows: list[dict]) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "calibration.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8", newline="\n"
    )
    return d


def row(iid, resolved, mode, error="", repo="r/r"):
    return {
        "instance_id": iid,
        "repo": repo,
        "mode": mode,
        "resolved": resolved,
        "test_exit_code": 0 if resolved else 1,
        "error": error,
        "patch_chars": 100,
        "seconds": 1.0,
    }


def clean_n(tmp_path, gold_rows, null_rows):
    g = write(tmp_path / "gold", gold_rows)
    n = write(tmp_path / "null", null_rows)
    out = tmp_path / "out"
    calibrate.reconcile(g, n, out)
    ids = (out / "clean_n.txt").read_text(encoding="utf-8").split()
    excluded = json.loads((out / "excluded.json").read_text(encoding="utf-8"))
    return ids, excluded


def test_healthy_tasks_survive(tmp_path):
    ids, excluded = clean_n(
        tmp_path,
        [row("t1", True, "gold"), row("t2", True, "gold")],
        [row("t1", False, "null"), row("t2", False, "null")],
    )
    assert ids == ["t1", "t2"]
    assert excluded == []


def test_excludes_a_task_whose_gold_patch_fails(tmp_path):
    """Unscoreable: no agent can ever resolve it, so it only adds variance."""
    ids, excluded = clean_n(
        tmp_path,
        [row("t1", True, "gold"), row("t2", False, "gold", error="Failed to apply agent patch")],
        [row("t1", False, "null"), row("t2", False, "null")],
    )
    assert ids == ["t1"]
    assert len(excluded) == 1
    assert excluded[0]["instance_id"] == "t2"
    assert "unscoreable" in excluded[0]["reason"]
    assert "Failed to apply" in excluded[0]["gold_error"]


def test_excludes_a_task_that_resolves_with_no_patch(tmp_path):
    """A free point lifts every config equally and dilutes the signal between them."""
    ids, excluded = clean_n(
        tmp_path,
        [row("t1", True, "gold"), row("t2", True, "gold")],
        [row("t1", False, "null"), row("t2", True, "null")],
    )
    assert ids == ["t1"]
    assert "free point" in excluded[0]["reason"]


def test_a_task_can_fail_both_checks_and_is_excluded_once(tmp_path):
    ids, excluded = clean_n(
        tmp_path,
        [row("t1", False, "gold")],
        [row("t1", True, "null")],
    )
    assert ids == []
    assert len(excluded) == 1


def test_only_the_intersection_is_considered(tmp_path):
    """A partial run must not silently shrink clean-N to its own coverage."""
    ids, excluded = clean_n(
        tmp_path,
        [row("t1", True, "gold"), row("t2", True, "gold"), row("t3", True, "gold")],
        [row("t1", False, "null")],
    )
    assert ids == ["t1"]
    assert excluded == []  # t2/t3 are unmeasured, not broken


def test_later_row_wins_so_a_rerun_supersedes(tmp_path):
    """The ledger is append-only; re-running a task must override the old verdict."""
    ids, _ = clean_n(
        tmp_path,
        [row("t1", False, "gold"), row("t1", True, "gold")],
        [row("t1", False, "null")],
    )
    assert ids == ["t1"]


def test_missing_run_is_a_hard_error(tmp_path):
    write(tmp_path / "gold", [row("t1", True, "gold")])
    with pytest.raises(SystemExit):
        calibrate.reconcile(tmp_path / "gold", tmp_path / "absent", tmp_path / "out")
