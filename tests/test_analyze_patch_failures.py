"""Tests for the offline patch-failure taxonomy.

Two things here are easy to get silently wrong and both would corrupt a finding
rather than crash:

* **Diff parsing.** Three creation spellings occur in this corpus -- `---
  /dev/null`, `new file mode`, and a bare `@@ -0,0 +1,N @@` under an ordinary
  `--- a/path`. The gold patches use only the third, so a `created_files` that
  checks `/dev/null` alone reports **zero** gold creations and the "no gold
  patch creates a file" claim survives untested. 11 of 129 do.
* **Bucket precedence.** The buckets are only meaningful if they are a
  partition. A patch that is simultaneously scratch-polluting, overreaching and
  incomplete must land in exactly one bucket, and in a bucket the caller can
  predict from the documented order.

The scratch rule's last clause -- "a file the patch creates at the repository
root" -- is exact rather than heuristic, and `test_no_gold_patch_touches_the_
repo_root` is what makes it exact. If a future task set breaks that assumption
the rule must change, so the assertion is pinned to the real data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import analyze_patch_failures as apf  # noqa: E402
from swegemma_lab.tasks import (  # noqa: E402
    Task,
    edit_bodies,
    hunk_ranges,
    load_tasks,
    ranges_overlap,
)

TASKS = ROOT / "data" / "tasks" / "tasks.jsonl"


def diff(path: str, old: int, count: int, body: str = "+    x = 1\n") -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"index 0000000..1111111 100644\n"
        f"--- a/{path}\n+++ b/{path}\n"
        f"@@ -{old},{count} +{old},{count + 1} @@ def f():\n{body}"
    )


# --- hunk_ranges / ranges_overlap --------------------------------------------


def test_hunk_ranges_reads_the_preimage_side():
    assert hunk_ranges(diff("pkg/a.py", 10, 6)) == {"pkg/a.py": [(10, 15)]}


def test_hunk_ranges_defaults_an_omitted_count_to_one():
    d = "--- a/x.py\n+++ b/x.py\n@@ -42 +42,2 @@\n+pass\n"
    assert hunk_ranges(d) == {"x.py": [(42, 42)]}


def test_hunk_ranges_keeps_a_pure_insertion_as_its_anchor():
    """`-N,0` has no pre-image lines; dropping it would lose the commonest shape."""
    d = "--- a/x.py\n+++ b/x.py\n@@ -7,0 +8,3 @@\n+a\n+b\n+c\n"
    assert hunk_ranges(d) == {"x.py": [(7, 7)]}


def test_hunk_ranges_attributes_each_hunk_to_its_own_file():
    d = diff("a.py", 5, 2) + diff("b.py", 90, 4)
    assert hunk_ranges(d) == {"a.py": [(5, 6)], "b.py": [(90, 93)]}


def test_hunk_ranges_handles_a_deletion_via_the_minus_side():
    d = "--- a/gone.py\n+++ /dev/null\n@@ -1,3 +0,0 @@\n-a\n-b\n-c\n"
    assert hunk_ranges(d) == {"gone.py": [(1, 3)]}


def test_ranges_overlap_is_inclusive_and_takes_slack():
    assert ranges_overlap([(10, 20)], [(20, 30)])
    assert not ranges_overlap([(10, 20)], [(21, 30)])
    assert ranges_overlap([(10, 20)], [(23, 30)], slack=3)
    assert not ranges_overlap([(10, 20)], [], slack=99)


# --- created_files ------------------------------------------------------------


def test_created_files_sees_all_three_spellings():
    dev_null = "diff --git a/n.py b/n.py\n--- /dev/null\n+++ b/n.py\n@@ -0,0 +1,2 @@\n+a\n+b\n"
    mode = "diff --git a/m.py b/m.py\nnew file mode 100644\n--- a/m.py\n+++ b/m.py\n@@ -1 +1,2 @@\n+a\n"
    gold_style = "--- a/g.py\n+++ b/g.py\n@@ -0,0 +1,1 @@\n+a\n"
    assert apf.created_files(dev_null) == {"n.py"}
    assert apf.created_files(mode) == {"m.py"}
    assert apf.created_files(gold_style) == {"g.py"}


def test_created_files_does_not_bleed_a_creation_onto_the_next_file():
    d = ("diff --git a/n.py b/n.py\n--- /dev/null\n+++ b/n.py\n@@ -0,0 +1,1 @@\n+a\n"
         + diff("pkg/edited.py", 3, 2))
    assert apf.created_files(d) == {"n.py"}


def test_eleven_gold_patches_create_a_file_so_creation_alone_is_not_waste(task_data):
    """The opposite claim is written into `metrics.py` and is false."""
    tasks = load_tasks(TASKS)
    creators = [t.instance_id for t in tasks if apf.created_files(t.patch)]
    assert len(creators) == 11
    assert "rich_3930" in creators


def test_no_gold_patch_touches_the_repo_root(task_data):
    """What makes "created at the root" an exact scratch signal rather than a guess."""
    tasks = load_tasks(TASKS)
    assert [p for t in tasks for p in t.gold_files if "/" not in p] == []


# --- the scratch rule ---------------------------------------------------------


@pytest.mark.parametrize(
    "path,created,expected",
    [
        ("repro.py", True, True),
        ("repro.py", False, True),  # the lab stem heuristic, regardless of creation
        ("reproduce_issue.py", True, True),  # created at the root
        ("verify_fix.py", True, True),
        ("module_a.py", True, True),
        ("fastapi/routing.py", False, False),
        ("fastapi/temp_pydantic_v1_params.py", False, False),  # a real module
        ("fastapi/routing.py.orig", False, True),
        ("tmp/notes.py", False, True),
        ("docs/en/docs/index.md", False, False),
        ("scripts/prepare_release.py", True, False),  # gold creates exactly this
    ],
)
def test_scratch_rule(path, created, expected):
    assert apf.looks_like_scratch(path, created) is expected


# --- classification -----------------------------------------------------------

GOLD = diff("pkg/core.py", 100, 6)


def test_wrong_file():
    bucket, _ = apf.classify(diff("pkg/other.py", 100, 6), GOLD)
    assert bucket == "wrong_file"


def test_right_file_wrong_hunk():
    bucket, _ = apf.classify(diff("pkg/core.py", 900, 6), GOLD)
    assert bucket == "right_file_wrong_hunk"


def test_right_hunk_wrong_logic_is_the_fallback():
    bucket, facts = apf.classify(diff("pkg/core.py", 100, 6, "+    x = 2\n"), GOLD)
    assert bucket == "right_hunk_wrong_logic"
    assert facts["missed_gold_regions"] == 0


def test_incomplete_fix_when_gold_touches_more():
    gold2 = GOLD + diff("pkg/second.py", 10, 4)
    bucket, facts = apf.classify(diff("pkg/core.py", 100, 6), gold2)
    assert bucket == "incomplete_fix"
    assert facts["missed_gold_files"] == 1


def test_overreach_beats_incomplete_fix():
    """A patch that is both is reported as overreach -- the documented order."""
    gold2 = GOLD + diff("pkg/second.py", 10, 4)
    agent = diff("pkg/core.py", 100, 6) + diff("pkg/elsewhere.py", 1, 2)
    bucket, facts = apf.classify(agent, gold2)
    assert bucket == "overreach"
    assert facts["missed_gold_files"] == 1  # also incomplete, not reported as such


def test_test_edit_beats_everything_except_scratch():
    agent = diff("pkg/core.py", 100, 6) + diff("tests/test_core.py", 1, 2)
    assert apf.classify(agent, GOLD)[0] == "test_edit"


def test_scratch_pollution_has_top_precedence_in_pass_a():
    agent = diff("pkg/core.py", 100, 6) + diff("tests/test_core.py", 1, 2) + _new("repro.py")
    assert apf.classify(agent, GOLD)[0] == "scratch_pollution"


def test_pass_b_discounts_scratch_and_exposes_the_reasoning_bucket():
    agent = diff("pkg/core.py", 100, 6, "+    x = 2\n") + _new("repro.py")
    assert apf.classify(agent, GOLD)[0] == "scratch_pollution"
    assert apf.classify(agent, GOLD, discount_scratch=True)[0] == "right_hunk_wrong_logic"


def test_pass_b_names_a_patch_that_is_nothing_but_scratch():
    bucket, _ = apf.classify(_new("repro.py"), GOLD, discount_scratch=True)
    assert bucket == "no_source_edit"


def test_every_bucket_name_is_declared_in_a_precedence_tuple():
    assert set(apf.BUCKETS_DISCOUNTED) - {"no_source_edit"} <= set(apf.BUCKETS)
    assert apf.BUCKETS[-1] == apf.BUCKETS_DISCOUNTED[-1] == "right_hunk_wrong_logic"


def _new(path: str) -> str:
    return (f"diff --git a/{path} b/{path}\n--- /dev/null\n+++ b/{path}\n"
            f"@@ -0,0 +1,1 @@\n+print(1)\n")


# --- gold equivalence and the environment flag -------------------------------


def test_edit_bodies_ignores_position_and_context():
    a = "--- a/x.py\n+++ b/x.py\n@@ -10,3 +10,3 @@ def f():\n ctx\n-old\n+new\n"
    b = "--- a/x.py\n+++ b/x.py\n@@ -400,3 +400,3 @@ class K:\n other\n-old\n+new\n"
    assert edit_bodies(a) == edit_bodies(b) == {"x.py": (("-", "old"), ("+", "new"))}


def test_reproduced_gold_is_true_for_the_same_change_at_another_offset():
    gold = "--- a/x.py\n+++ b/x.py\n@@ -10,1 +10,1 @@\n-old\n+new\n"
    agent = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -11,1 +11,1 @@ ctx\n-old\n+new\n"
    assert apf.reproduced_gold(agent, gold)


def test_reproduced_gold_tolerates_extra_files_but_not_a_different_edit():
    gold = "--- a/x.py\n+++ b/x.py\n@@ -10,1 +10,1 @@\n-old\n+new\n"
    assert apf.reproduced_gold(gold + _new("repro.py"), gold)
    other = "--- a/x.py\n+++ b/x.py\n@@ -10,1 +10,1 @@\n-old\n+other\n"
    assert not apf.reproduced_gold(other, gold)


def test_reproduced_gold_is_false_on_an_empty_gold_patch():
    assert not apf.reproduced_gold(diff("pkg/core.py", 1, 2), "")


def _task(patch: str = "", test_patch: str = "") -> Task:
    return Task(instance_id="t", repo="r", base_commit="c", problem_statement="",
                patch=patch, test_patch=test_patch)


def test_env_mismatch_fires_on_the_known_signature():
    log = "E   TypeError: Router.__init__() got an unexpected keyword argument 'on_startup'"
    assert apf.env_mismatch(log, _task()) != ""


def test_env_mismatch_withholds_when_the_task_is_about_that_symbol():
    """Otherwise the task whose *subject* is `on_startup` is excused as drift."""
    log = "E   TypeError: Router.__init__() got an unexpected keyword argument 'on_startup'"
    assert apf.env_mismatch(log, _task(patch="+    on_startup=on_startup,\n")) == ""
    assert apf.env_mismatch(log, _task(test_patch="+ app = FastAPI(on_startup=[f])\n")) == ""


def test_env_mismatch_is_silent_on_an_ordinary_failure():
    assert apf.env_mismatch("E   assert 1 == 2", _task()) == ""
