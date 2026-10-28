"""Tests for inferring the private task count from the public leaderboard.

The headline claim -- that the private set holds 58 tasks -- is pinned to the
real 2026-10-13 snapshot, not to a fixture. This project has already shipped a
test that asserted a statistical bug as a feature, so a contract this load
bearing is checked against data that actually came off Kaggle.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swegemma_lab.leaderboard import (  # noqa: E402
    DisplayMode,
    Snapshot,
    fit_denominator,
    score_grid,
    tasks_for_score,
)

SNAPSHOT = ROOT / "data" / "leaderboard" / "public_lb_2026-10-13.json"


@pytest.fixture(scope="module")
def snap() -> Snapshot:
    return Snapshot.load(SNAPSHOT)


# --- the grid ---------------------------------------------------------------

def test_truncation_and_rounding_differ_where_it_matters():
    """11/58 = 0.1897: floor shows 0.18, round shows 0.19.

    This single value is what identifies the display convention, because the
    real board has 0.18 occupied by 141 teams and 0.19 occupied by none.
    """
    assert 0.18 in score_grid(58, DisplayMode.TRUNCATE)
    assert 0.19 not in score_grid(58, DisplayMode.TRUNCATE)
    assert 0.19 in score_grid(58, DisplayMode.ROUND)
    assert 0.18 not in score_grid(58, DisplayMode.ROUND)


def test_grid_excludes_zero_and_counts_every_task():
    grid = score_grid(58, DisplayMode.TRUNCATE)
    assert 0.0 not in grid
    assert max(grid) == 1.0


# --- the fit ----------------------------------------------------------------

def test_fit_is_unique_on_the_real_board(snap):
    """58 is the only denominator that explains the board exactly."""
    fit = fit_denominator(snap.occupied_scores(), search=range(20, 221))
    assert fit.denominators == [58]
    assert fit.mode is DisplayMode.TRUNCATE


def test_rounding_cannot_explain_the_real_board(snap):
    """Under round(), no denominator leaves every bin occupied.

    The nearest rounding fits start at n=93 and imply 8-10 empty bins between
    0.01 and 0.24, which 2643 teams would not leave empty. Recorded because it
    is the alternative a reader will reach for.
    """
    fit = fit_denominator(
        snap.occupied_scores(), search=range(20, 221), modes=(DisplayMode.ROUND,)
    )
    assert fit.denominators == []


def test_real_board_bins_are_consecutive_under_the_fit(snap):
    """k = 1..14 with no gaps -- the property that makes the fit unique."""
    scores = snap.occupied_scores()
    counts = sorted(tasks_for_score(s, 58) for s in scores)
    assert counts == list(range(1, 15))


# --- reading scores back as task counts ------------------------------------

def test_our_score_and_the_top_in_tasks(snap):
    assert tasks_for_score(0.13, 58) == 8
    assert tasks_for_score(0.24, 58) == 14
    assert snap.our_team["score"] == 0.13


def test_one_task_is_worth_more_than_the_evidence_threshold_claims():
    """1/58 = 0.0172, not the 0.0167 the docs carried from a ~60 guess."""
    assert round(1 / 58, 4) == 0.0172


# --- snapshot integrity -----------------------------------------------------

def test_snapshot_histogram_sums_to_team_count(snap):
    assert sum(snap.histogram.values()) == snap.teams == 2643


def test_snapshot_records_the_top_of_the_board(snap):
    assert max(snap.occupied_scores()) == 0.24
    assert snap.histogram["0.24"] == 2


def test_teams_tied_with_us(snap):
    assert snap.histogram["0.13"] == 340
