"""Tests for the paper's word-count export.

The thing that is easy to get silently wrong here is the *boundary*: if
`split_header` guesses, the drafting header (status, word budget, the audit
trail) is submitted as part of the paper and the count that gates submission is
measured on the wrong text. So the separator is required, not inferred.

The three counting bases exist because the rubric states a 3,000-word cap and
does not define the count. They must stay ordered `prose <= rendered <= naive`
for "under the cap on every basis" to mean anything -- if a change ever makes
`prose` the largest, the pessimistic basis is no longer pessimistic and the
compliance claim is void. That ordering is asserted against the real manuscript,
not a fixture, which is also what keeps the live paper under the cap.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_paper as ep  # noqa: E402


def test_split_header_requires_the_separator():
    with pytest.raises(ValueError, match="no header separator"):
        ep.split_header("# Title\n\nbody with no rule\n")


def test_split_header_drops_the_drafting_header():
    header, body = ep.split_header("# T\n\nstatus: drafting\n---\n\n## Abstract\n\nx\n")
    assert "status: drafting" in header
    assert "status: drafting" not in body
    assert body.startswith("## Abstract")


def test_title_comes_from_the_header_not_the_body():
    """Kaggle takes the title separately, so it must survive the header strip."""
    header, body = ep.split_header(ep.MANUSCRIPT.read_text(encoding="utf-8"))
    assert ep.title_of(header).startswith("Calibrate the Yardstick First")
    assert not body.startswith("# ")


def test_title_is_empty_when_there_is_no_h1():
    assert ep.title_of("no heading here\n") == ""


def test_prose_ignores_table_pipes_and_rules():
    body = "| a | b |\n|---|---|\n| 1 | 2 |\n"
    assert ep.count_prose(body) == 4          # a b 1 2
    assert ep.count_naive(body) > ep.count_prose(body)


def test_prose_ignores_fenced_code():
    assert ep.count_prose("one two\n```\nthree four five\n```\n") == 2


def test_rendered_drops_layout_tokens_only():
    body = "## Head\n\n| a |\n"
    assert ep.count_rendered(body) == 2        # Head, a
    assert ep.count_naive(body) == 5           # ##, Head, |, a, |


def test_sections_are_in_document_order():
    body = "## One\n\nx\n\n## Two\n\ny z\n"
    assert [t for t, _ in ep.sections(body)] == ["One", "Two"]


def test_section_counts_sum_to_the_body_count():
    _, body = ep.split_header(ep.MANUSCRIPT.read_text(encoding="utf-8"))
    assert sum(n for _, n in ep.sections(body)) == ep.count_prose(body)


def test_the_live_manuscript_is_under_the_cap_on_every_basis():
    _, body = ep.split_header(ep.MANUSCRIPT.read_text(encoding="utf-8"))
    basis = ep.counts(body)
    over = {k: v for k, v in basis.items() if v > ep.WORD_CAP}
    assert not over, f"over the {ep.WORD_CAP}-word cap: {over}"


def test_the_paper_states_one_suite_size_consistently():
    """The paper cites the suite size in two places (§D3 and §H).

    The suite size is a number in the body that tracks the repo, so it goes
    stale silently -- and the realistic way it goes wrong is one site being
    updated and the other not, which leaves the paper contradicting itself in
    front of a Verifiability grader. This does not check the figure against the
    live suite: `def test_` is not a reliable proxy for the collected count
    here (243 against 316), and shelling out to `--collect-only` inside the
    suite buys little. It checks that the paper agrees with itself.
    """
    _, body = ep.split_header(ep.MANUSCRIPT.read_text(encoding="utf-8"))
    import re
    cited = set(re.findall(r"(?:passes at|machinery has)\s+(\d{3})", body))
    assert len(cited) == 1, f"the paper cites conflicting suite sizes: {cited}"


def test_naive_is_the_pessimistic_basis():
    """If this inverts, "under the cap on every basis" stops being a guarantee."""
    _, body = ep.split_header(ep.MANUSCRIPT.read_text(encoding="utf-8"))
    b = ep.counts(body)
    assert b["prose"] <= b["rendered"] <= b["naive"]
