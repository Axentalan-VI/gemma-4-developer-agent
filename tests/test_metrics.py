"""The diagnostic panel replaces a noisy scalar, so it has to be trustworthy."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swegemma_lab.metrics import (
    Panel,
    TaskOutcome,
    budget_verdict,
    build_panel,
    classify_error,
    load_outcomes,
)
from swegemma_lab.tasks import Task, load_tasks, patch_files

GOLD = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,3 @@
-old
+new
"""


def mktask(iid="t1", patch=GOLD):
    return Task(instance_id=iid, repo="r/r", base_commit="abc", problem_statement="p", patch=patch)


def test_patch_files_handles_both_header_styles():
    assert patch_files(GOLD) == {"src/app.py"}
    bare = "--- a/lib/x.py\n+++ b/lib/x.py\n@@ -1 +1 @@\n-a\n+b\n"
    assert patch_files(bare) == {"lib/x.py"}
    assert patch_files("") == frozenset()


def test_patch_files_ignores_dev_null():
    created = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+x\n"
    assert patch_files(created) == {"new.py"}


def test_localization_counts_a_hit_and_an_exact_set():
    tasks = {"t1": mktask("t1")}
    p = build_panel("a", [TaskOutcome("t1", resolved=False, patch=GOLD)], tasks)
    assert p.gold_file_hit == 1
    assert p.gold_file_exact == 1
    assert p.localization_rate == 1.0


def test_localization_hit_without_exact_set():
    """Touching the right file plus an extra one is a hit but not exact."""
    wide = GOLD + "diff --git a/src/other.py b/src/other.py\n@@ -1 +1 @@\n-a\n+b\n"
    p = build_panel("a", [TaskOutcome("t1", resolved=False, patch=wide)], {"t1": mktask("t1")})
    assert p.gold_file_hit == 1
    assert p.gold_file_exact == 0


def test_localization_miss():
    miss = "diff --git a/src/elsewhere.py b/src/elsewhere.py\n@@ -1 +1 @@\n-a\n+b\n"
    p = build_panel("a", [TaskOutcome("t1", resolved=False, patch=miss)], {"t1": mktask("t1")})
    assert p.gold_file_hit == 0


def test_detects_the_three_exact_waste_signals():
    """No gold patch creates a file, edits a test, or leaves scratch behind."""
    created = "diff --git a/n.py b/n.py\nnew file mode 100644\n--- /dev/null\n+++ b/n.py\n@@ -0,0 +1 @@\n+x\n"
    test_edit = "diff --git a/tests/test_x.py b/tests/test_x.py\n@@ -1 +1 @@\n-a\n+b\n"
    scratch = "diff --git a/repro.py b/repro.py\n@@ -1 +1 @@\n-a\n+b\n"
    tasks = {i: mktask(i) for i in ("a", "b", "c")}
    p = build_panel(
        "x",
        [
            TaskOutcome("a", resolved=False, patch=created),
            TaskOutcome("b", resolved=False, patch=test_edit),
            TaskOutcome("c", resolved=False, patch=scratch),
        ],
        tasks,
    )
    assert p.created_file == 1
    assert p.touched_protected == 1
    assert p.scratch_leak == 1
    assert p.waste_rate == 1.0


def test_clean_patch_shows_no_waste():
    p = build_panel("x", [TaskOutcome("t1", resolved=True, patch=GOLD)], {"t1": mktask("t1")})
    assert p.waste_rate == 0.0


def test_empty_patch_is_tracked():
    p = build_panel("x", [TaskOutcome("t1", resolved=False, patch="")], {"t1": mktask("t1")})
    assert p.non_empty == 0
    assert p.n == 1


def test_budget_verdict_detects_slack():
    """The question a single k=1 run can answer, saving tens of GPU-hours."""
    p = Panel(name="x", n=100, tool_calls=[25] * 100, exhausted_calls=0)
    assert "SLACK" in budget_verdict(p)


def test_budget_verdict_detects_binding():
    p = Panel(name="x", n=100, tool_calls=[100] * 100, exhausted_calls=100)
    assert "BINDS" in budget_verdict(p)


def test_budget_verdict_refuses_to_guess_without_data():
    assert "no tool-call data" in budget_verdict(Panel(name="x", n=10))


@pytest.mark.parametrize(
    "path,expected",
    [
        ("repro.py", True),
        ("repro2.py", True),
        ("tmp.py", True),
        ("src/debug.py", True),
        ("scratch_1.py", True),
        # A prefix match flagged these three real source files, which appear in
        # gold patches. temp_* is a normal module naming style.
        ("fastapi/temp_pydantic_v1_params.py", False),
        ("src/tempfile_utils.py", False),
        ("src/debugger.py", False),
        ("src/checks.py", False),
        ("repro.txt", False),
    ],
)
def test_scratch_detection_keys_on_the_whole_stem(path, expected):
    from swegemma_lab.tasks import is_scratch

    assert is_scratch(path) is expected


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Failed to apply agent patch: corrupt", "patch_apply_failed"),
        ("Agent session timed out after 3600s", "agent_timeout"),
        ("RateLimitError from proxy", "model_error"),
        ("container killed 137", "sandbox_error"),
        ("max_turns reached, budget exhausted", "budget_exhausted"),
        ("something entirely new", "other"),
        ("", "other"),
    ],
)
def test_error_taxonomy(message, expected):
    assert classify_error(message) == expected


def test_load_outcomes_survives_a_torn_final_line(tmp_path):
    """A session killed at the 9-hour cap leaves a partial last line."""
    d = tmp_path / "run"
    (d / "patches").mkdir(parents=True)
    rows = [
        json.dumps({"instance_id": "t1", "resolved": True, "tool_calls": 12, "duration_seconds": 300}),
        json.dumps({"instance_id": "t2", "resolved": False, "tool_calls": 100, "error": "timeout"}),
        '{"instance_id": "t3", "resol',  # torn by SIGKILL mid-write
    ]
    (d / "task_results.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (d / "patches" / "t1.patch").write_text(GOLD, encoding="utf-8")

    out = load_outcomes(d)
    assert [o.instance_id for o in out] == ["t1", "t2"]
    assert out[0].patch == GOLD  # backfilled from patches/
    assert out[0].tool_calls_used == 12
    assert out[1].error == "timeout"


def test_load_outcomes_on_missing_dir_is_empty():
    assert load_outcomes("/definitely/not/here") == []


def test_panel_against_the_real_gold_patches(task_data):
    """End-to-end: replaying the gold patches must localize perfectly.

    This is the calibration check for the localization metric itself. If gold
    patches do not score 100% gold-file hit, the metric is broken, not the agent.
    """
    tasks = {t.instance_id: t for t in load_tasks(ROOT / "data" / "tasks" / "tasks.jsonl")}
    assert len(tasks) == 129
    outcomes = [TaskOutcome(iid, resolved=True, patch=t.patch) for iid, t in tasks.items()]
    p = build_panel("gold", outcomes, tasks)
    assert p.n == 129
    assert p.localization_rate == 1.0
    assert p.gold_file_exact == 129
    # The properties the prompts and metrics lean on.
    assert p.created_file == 0, "a gold patch creates a file; the 'never adds a file' rule is wrong"
    assert p.touched_protected == 0, "a gold patch edits a protected path"
    assert p.scratch_leak == 0


def test_budget_verdict_refuses_to_generalize_from_a_probe_ceiling():
    """probe_c12 was rendered at the default 100 while running at 30, which
    flipped the verdict to SLACK and nearly retired a line of work."""
    from swegemma_lab.metrics import Panel, budget_verdict

    p = Panel(name="probe", n=12, tool_calls=[29] * 6 + [30] * 6)
    out = budget_verdict(p, call_ceiling=30)
    assert "NO VERDICT" in out
    assert "not the grader's 100" in out
    assert "SLACK" not in out


def test_budget_verdict_still_answers_at_the_grader_ceiling():
    from swegemma_lab.metrics import Panel, budget_verdict

    slack = Panel(name="x", n=10, tool_calls=[12] * 10)
    assert "SLACK" in budget_verdict(slack)
    binds = Panel(name="y", n=10, tool_calls=[100] * 10, exhausted_calls=10)
    assert "BINDS" in budget_verdict(binds)


# --- A metric that could not be computed must not print as 0.0% -------------
#
# Added 2026-10-12. P005's pooled panel printed "leaked scratch file 0.0%" while
# the run's actual patches showed 6 of 7 contaminated. The panel builds from
# ledger rows, which carry no patch text, so the three waste metrics were
# structurally uncomputable -- and printed as a clean zero on the one metric
# that turned out to dominate the failure funnel. A disclaimer underneath a
# printed 0.0% is weaker than not printing a number.


def test_waste_metrics_render_as_unknown_when_patches_are_absent():
    p = Panel(name="arm", n=10, resolved=1, hygiene_known=False)
    out = p.render()
    assert "0.0%" not in out.split("-- waste")[1].split("-- budget")[0], out
    assert "n/a" in out
    assert "needs patches" in out


def test_waste_metrics_still_render_when_patches_were_seen():
    p = Panel(name="arm", n=10, resolved=1, scratch_leak=6, hygiene_known=True)
    waste = p.render().split("-- waste")[1].split("-- budget")[0]
    assert "60.0%" in waste, waste
    assert "n/a" not in waste


def test_hygiene_known_defaults_to_true_so_existing_callers_are_unchanged():
    assert Panel(name="a", n=1).hygiene_known is True


def test_waste_rate_is_none_when_unknown_rather_than_zero():
    """A caller doing arithmetic must not silently treat 'unknown' as 'none'."""
    assert Panel(name="a", n=10, hygiene_known=False).waste_rate is None
    assert Panel(name="a", n=10, scratch_leak=1).waste_rate == 0.1
