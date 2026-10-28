"""Tests for the paper's figures.

These check the *claims* the figures make, not their pixels. A figure is a
number the reader cannot audit, so the two that carry arguments -- the card's
one-task band and the calibration split -- are asserted against the committed
snapshot and against the paper's own text, so a figure cannot quietly disagree
with the manuscript it ships beside.

Rendering is not exercised here: it needs a writable output directory and
costs a second per figure, and what would go wrong in it is layout, which an
assertion cannot see anyway. Look at the PNG instead.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

pytest.importorskip("matplotlib", reason="figures are optional tooling")

import make_paper_figures as mpf  # noqa: E402
from swegemma_lab.leaderboard import Snapshot  # noqa: E402

MANUSCRIPT = ROOT / "paper" / "MANUSCRIPT.md"


@pytest.fixture(scope="module")
def snapshot() -> Snapshot:
    return Snapshot.load(mpf.SNAPSHOT)


def test_the_band_reproduces_the_papers_headline(snapshot):
    """The card's hero number is the paper's, derived not transcribed."""
    by_k, band, total, pct = mpf.band_around(snapshot)
    assert band == [7, 8, 9]
    assert total == 1094
    assert pct == 34
    assert by_k[mpf.OUR_K] == 353


def test_every_positive_score_maps_to_a_distinct_task_count(snapshot):
    """If two scores collided, the histogram would silently lose teams."""
    by_k, _, _, _ = mpf.band_around(snapshot)
    positive = [c for s, c in snapshot.histogram.items() if float(s) > 0 and c]
    assert len(by_k) == len(positive)
    assert sum(by_k.values()) == sum(positive)
    assert sorted(by_k) == list(range(1, 15))


def test_the_card_states_the_band_the_manuscript_states():
    """The figure and the prose must not drift apart."""
    text = MANUSCRIPT.read_text(encoding="utf-8")
    assert "1,094" in text and "34%" in text


def test_the_calibration_segments_account_for_every_task():
    """102 + 3 + 24 = 129: a figure that drops a task is worse than no figure."""
    assert sum(n for _, n, _, _ in mpf.CALIBRATION) == 129


def test_the_paired_figure_matches_the_experiment_log():
    """P009's four rows, as EXPERIMENTS.md records them."""
    log = (ROOT / "EXPERIMENTS.md").read_text(encoding="utf-8")
    row = re.search(r"\|\s*\*\*timed out\*\*\s*\|\s*\*\*11/36\*\*\s*\|\s*\*\*0/36\*\*", log)
    assert row, "the 11/36 -> 0/36 row moved; re-check the figure against the log"
    assert [(n, a, b) for n, a, b, _, _ in mpf.PAIRED] == [
        ("timed out", 11, 0),
        ("gold-file hit", 18, 24),
        ("gold file exact", 6, 4),
        ("resolved", 1, 1),
    ]


def test_only_the_timeout_result_is_marked_significant():
    """The figure must not promote a null. Three of the four p-values are > 0.2."""
    significant = [name for name, _, _, _, sig in mpf.PAIRED if sig]
    assert significant == ["timed out"]
