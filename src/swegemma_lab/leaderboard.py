"""Infer the private task count from the shape of the public leaderboard.

The competition never publishes how many tasks the private set holds, and this
project carried "~60, so one task is worth 0.0167" as a community inference for
two weeks. It is inferable, and much more sharply than that.

The method needs no GPU and no private access. A team's score is
`resolved / n_tasks` displayed to two decimals, so only `n_tasks + 1` distinct
strings can ever appear on the board. With enough teams, every reachable low
score is occupied, and the *set of occupied strings* identifies `n_tasks`
because different denominators produce different grids. On the 2026-10-13 board
(2643 teams, 14 occupied positive bins) exactly one denominator in 20..220
reproduces the board with no empty bins: **58**.

Two assumptions carry it, and both are checkable rather than assumed:

* **The display truncates rather than rounds.** 11/58 is 0.1897, which floors to
  0.18 and rounds to 0.19. The board has 141 teams at 0.18 and nobody at 0.19,
  so truncation is observed, not posited.
* **Every reachable bin is occupied.** Under the fit, the occupied bins are
  exactly k = 1..14 with no gaps, which is what makes the answer unique. A
  rounding fit needs n >= 93 and leaves 8-10 bins empty among 2643 teams.

The honest caveat: this pins the *displayed grid*, so any n sharing 58's grid
would also fit -- here none does. It assumes all teams are scored on one task
set, and it cannot see tasks nobody has ever resolved. 58 is therefore a lower
bound that is also the unique exact fit, which is a much stronger statement than
"~60" but is still an inference from public aggregates.
"""

from __future__ import annotations

import enum
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

DECIMALS = 2
_SCALE = 10**DECIMALS


class DisplayMode(enum.Enum):
    """How the leaderboard turns a fraction into the string it shows."""

    TRUNCATE = "truncate"
    ROUND = "round"

    def apply(self, value: float) -> float:
        if self is DisplayMode.TRUNCATE:
            return math.floor(value * _SCALE) / _SCALE
        return round(value, DECIMALS)


def score_grid(n_tasks: int, mode: DisplayMode) -> set[float]:
    """Every positive score displayable when `n_tasks` tasks are graded.

    Zero is excluded: a 0.00 row is unresolvable between "no tasks passed" and
    "fewer tasks passed than the display can show", so it carries no
    information about the denominator.
    """
    if n_tasks < 1:
        raise ValueError(f"n_tasks must be >= 1, got {n_tasks}")
    return {mode.apply(k / n_tasks) for k in range(1, n_tasks + 1)}


def tasks_for_score(score: float, n_tasks: int) -> int:
    """How many tasks a displayed score corresponds to.

    Inverts the truncating display: the smallest k whose displayed value equals
    `score`. Raises if the score is not on the grid at all, because silently
    returning a nearest neighbour is how a wrong denominator survives.
    """
    for k in range(1, n_tasks + 1):
        if DisplayMode.TRUNCATE.apply(k / n_tasks) == score:
            return k
    raise ValueError(f"{score} is not on the n={n_tasks} grid")


@dataclass(frozen=True)
class Fit:
    """The denominators consistent with a board, under one display mode."""

    denominators: list[int]
    mode: DisplayMode | None
    unique: bool

    def render(self) -> str:
        if not self.denominators:
            return "no denominator explains this board"
        head = f"n = {self.denominators[0]}" if self.unique else f"n in {self.denominators}"
        return f"{head} ({self.mode.value if self.mode else '?'})"


def fit_denominator(
    occupied: Iterable[float],
    search: Sequence[int] | range = range(20, 221),
    modes: Sequence[DisplayMode] = (DisplayMode.TRUNCATE, DisplayMode.ROUND),
) -> Fit:
    """Find the task counts whose grid is *exactly* the occupied scores.

    Exact equality over the occupied range -- not mere containment -- is what
    makes the answer unique. Containment alone admits every large n, because a
    finer grid always covers a coarser one; requiring no empty bins is the
    constraint that 2643 teams actually justify.
    """
    occupied = sorted(set(occupied))
    if not occupied:
        return Fit([], None, False)
    lo, hi = occupied[0], occupied[-1]
    for mode in modes:
        hits = [
            n
            for n in search
            if {s for s in score_grid(n, mode) if lo <= s <= hi} == set(occupied)
        ]
        if hits:
            return Fit(hits, mode, len(hits) == 1)
    return Fit([], None, False)


@dataclass(frozen=True)
class Snapshot:
    """An aggregated public-leaderboard capture.

    Only the score histogram is kept, never the team roster: the histogram is
    all the inference reads, and republishing 2643 usernames is not this repo's
    business.
    """

    captured_utc: str
    competition: str
    teams: int
    our_team: dict
    histogram: dict[str, int]

    @classmethod
    def load(cls, path: Path) -> "Snapshot":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            captured_utc=raw["captured_utc"],
            competition=raw["competition"],
            teams=raw["teams"],
            our_team=raw["our_team"],
            histogram=raw["histogram"],
        )

    def occupied_scores(self) -> list[float]:
        """Positive scores someone actually holds, ascending."""
        return sorted(float(s) for s, c in self.histogram.items() if c and float(s) > 0)

    def teams_at_or_above(self, score: float) -> int:
        return sum(c for s, c in self.histogram.items() if float(s) >= score)
