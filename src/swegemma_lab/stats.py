"""Decide whether a config change is real or noise.

The naive approach -- run once, compare resolution rates -- cannot work here.
At p around 0.15 the binomial SE over 129 tasks is about 0.031, and the private
set is smaller still, so the whole leaderboard from 0.13 to 0.17 sits inside one
standard error. Worse, the dominant variance is not task sampling but the
agent's own stochasticity: identical archives have reportedly scored 0.03 apart.

So we pair on tasks *and* average over repeated runs, and we spend most of our
statistical power on surrogate metrics that are far less noisy than a binary
resolve. See `docs/statistics.md`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

#: One-sided z for alpha = 0.10. We accept a 10% false-adopt rate because the
#: cost of adopting a neutral change is near zero while the cost of missing a
#: real +0.05 is a whole week of quota.
Z_ALPHA = 1.2816
Z_POWER = 0.8416  # 80% power


@dataclass(frozen=True)
class ArmStats:
    """Per-task resolve fractions for one configuration, pooled over runs."""

    name: str
    #: instance_id -> (resolved_count, run_count)
    counts: Mapping[str, tuple[int, int]]

    @property
    def tasks(self) -> frozenset[str]:
        return frozenset(self.counts)

    @property
    def k_min(self) -> int:
        return min((n for _, n in self.counts.values()), default=0)

    def rate(self, task: str) -> float:
        r, n = self.counts[task]
        return r / n if n else 0.0

    @property
    def resolution_rate(self) -> float:
        if not self.counts:
            return 0.0
        return sum(self.rate(t) for t in self.counts) / len(self.counts)


@dataclass
class Comparison:
    a: str
    b: str
    n_tasks: int
    rate_a: float
    rate_b: float
    delta: float
    se: float
    z: float
    #: Tasks a resolves and b does not, and vice versa. Discordance is what
    #: actually carries the signal; concordant tasks contribute nothing.
    gained: list[str] = field(default_factory=list)
    lost: list[str] = field(default_factory=list)
    k_a: int = 0
    k_b: int = 0

    @property
    def significant(self) -> bool:
        return self.z > Z_ALPHA

    def ci95(self) -> tuple[float, float]:
        h = 1.96 * self.se
        return self.delta - h, self.delta + h

    def render(self) -> str:
        lo, hi = self.ci95()
        verdict = "SIGNIFICANT" if self.significant else "not significant"
        return "\n".join(
            [
                f"{self.a} (k={self.k_a}) vs {self.b} (k={self.k_b}) on {self.n_tasks} paired tasks",
                f"  rate: {self.rate_a:.4f} vs {self.rate_b:.4f}",
                f"  delta: {self.delta:+.4f}  SE {self.se:.4f}  z {self.z:+.2f}  95% CI [{lo:+.4f}, {hi:+.4f}]",
                f"  {verdict} at one-sided alpha=0.10",
                f"  discordant: +{len(self.gained)} gained, -{len(self.lost)} lost",
            ]
        )


def compare(a: ArmStats, b: ArmStats) -> Comparison:
    """Paired k-sample proportion comparison of arm *a* against baseline *b*.

    Var(delta) = (1/N^2) * sum_i [ p_i(1-p_i)/k_a + q_i(1-q_i)/k_b ]

    Only borderline tasks contribute, which is why SE shrinks much faster than a
    naive binomial calculation over all tasks would suggest.
    """
    shared = sorted(a.tasks & b.tasks)
    if not shared:
        raise ValueError(f"no tasks in common between {a.name!r} and {b.name!r}")

    n = len(shared)
    pa = sum(a.rate(t) for t in shared) / n
    pb = sum(b.rate(t) for t in shared) / n

    var = 0.0
    gained: list[str] = []
    lost: list[str] = []
    for t in shared:
        ra, ka = a.counts[t]
        rb, kb = b.counts[t]
        p = ra / ka if ka else 0.0
        q = rb / kb if kb else 0.0
        if ka:
            var += p * (1 - p) / ka
        if kb:
            var += q * (1 - q) / kb
        if p > q:
            gained.append(t)
        elif q > p:
            lost.append(t)
    delta = pa - pb

    # The within-task term p(1-p)/k is identically ZERO at k=1, because each p is
    # 0 or 1. Taking that at face value gave SE=0 and z=+/-inf, and the report then
    # called a 3-gained/1-lost split "SIGNIFICANT" when its exact McNemar p is
    # 0.625. Caught on the first real paired run -- the run it would have made us
    # overreact to. (0.625 is the TWO-SIDED value this function returns, which is
    # the project's convention everywhere; notes here and in four other files
    # quoted 0.3125, the one-sided tail, until 2026-10-27.)
    #
    # At k=1 there is no replication to estimate variance from, so the information
    # lives entirely in the DISCORDANT pairs, which is the McNemar view:
    #   delta = (gained - lost) / n,  SE = sqrt(gained + lost) / n
    # Use `mcnemar_exact` for a p-value when the count is small; this SE keeps `z`
    # on the same scale as the k>=2 path so one ship rule can read both.
    if var > 0:
        se = math.sqrt(var) / n
    else:
        discordant = len(gained) + len(lost)
        se = math.sqrt(discordant) / n if discordant else 0.0
    z = delta / se if se > 0 else 0.0

    return Comparison(
        a=a.name,
        b=b.name,
        n_tasks=n,
        rate_a=pa,
        rate_b=pb,
        delta=delta,
        se=se,
        z=z,
        gained=gained,
        lost=lost,
        k_a=a.k_min,
        k_b=b.k_min,
    )


def mcnemar_exact(gained: int, lost: int) -> float:
    """Two-sided exact McNemar p-value on discordant counts.

    Reported as a secondary statistic only. On k=1 runs it treats the agent's
    own sampling noise as if it were a treatment effect, which produces false
    positives at exactly the effect sizes we care about.
    """
    n = gained + lost
    if n == 0:
        return 1.0
    lo = min(gained, lost)
    tail = sum(math.comb(n, i) for i in range(lo + 1)) / (2**n)
    return min(1.0, 2 * tail)


#: The task-set size SE_UNIT was measured on. The paired SE scales as
#: 1/sqrt(n), so pricing a smaller run without rescaling overstates its
#: sensitivity -- see detectable_delta.
SE_UNIT_N = 129


def detectable_delta(se_unit: float, k_a: int, k_b: int, n_tasks: int = SE_UNIT_N) -> float:
    """Smallest delta detectable at alpha=0.10 with 80% power.

    *se_unit* is the single-run paired SE, empirically about 0.030 **on the 129
    public tasks** -- so it is calibrated at one specific task-set size, and the
    paired SE scales as 1/sqrt(n). *n_tasks* rescales it to the run you are
    actually pricing.

    This argument was missing until 2026-10-21, and the omission ran the wrong
    way every time: every run this project has priced used fewer than 129 tasks,
    so every one was priced as more sensitive than it was. At k=1 the function
    reported 0.064 for a 12-task run whose real figure is 0.209. The verdict
    flips at k=2 on 60 tasks -- 0.045 (looks powered, SHIP/HOLD available)
    against a true 0.066 (cannot see the 0.05 design target) -- and `decide`
    keys on exactly that, so it would have authorized a ship on a run that could
    not have detected the effect. Defaults to the calibration size so an
    unqualified call still reproduces the documented table.
    """
    if k_a <= 0 or k_b <= 0:
        raise ValueError("k must be positive")
    if n_tasks <= 0:
        raise ValueError("n_tasks must be positive")
    se_at_n = se_unit * math.sqrt(SE_UNIT_N / n_tasks)
    se = se_at_n * math.sqrt(1 / k_a + 1 / k_b) / math.sqrt(2)
    return (Z_ALPHA + Z_POWER) * se


def noise_floor(rates: Sequence[float]) -> tuple[float, float]:
    """(mean, sample SD) of repeated runs of one identical config.

    The SD is the honest answer to 'is this leaderboard move real?'. Subsample to
    the private set size to predict the leaderboard's own noise floor.
    """
    n = len(rates)
    if n < 2:
        raise ValueError("need at least 2 runs")
    mean = sum(rates) / n
    var = sum((r - mean) ** 2 for r in rates) / (n - 1)
    return mean, math.sqrt(var)


# --- Sequential stopping ------------------------------------------------------


def posterior_p_better(gained: int, lost: int, prior: float = 1.0) -> float:
    """P(delta > 0) under a Beta(prior, prior) model on the discordance split.

    Conditioning on discordant pairs, each is a Bernoulli draw for "a wins", so
    P(delta>0) = P(theta > 0.5 | gained, lost) with a Beta posterior. Used to
    abandon clear losers partway through a run instead of paying for all of it.
    """
    a = gained + prior
    b = lost + prior
    if gained + lost == 0:
        return 0.5
    # Regularized incomplete beta via the symmetry P(theta>0.5) = I_{0.5}(b, a).
    return _betainc_half(b, a)


def _betainc_half(a: float, b: float) -> float:
    """I_0.5(a, b), the regularized incomplete beta at x=0.5.

    Integer-parameter case only, which is all we need: both arguments are counts
    plus an integer prior.
    """
    ai, bi = int(round(a)), int(round(b))
    n = ai + bi - 1
    # I_0.5(a,b) = sum_{j=a}^{n} C(n,j) 0.5^n  for integer a,b.
    return sum(math.comb(n, j) for j in range(ai, n + 1)) / (2**n)


def should_abort(gained: int, lost: int, threshold: float = 0.15) -> bool:
    """True once the candidate is unlikely enough to be better to stop paying."""
    if gained + lost < 8:
        return False  # too early to judge
    return posterior_p_better(gained, lost) < threshold


# --- The ship rule ------------------------------------------------------------


@dataclass(frozen=True)
class ShipDecision:
    ship: bool
    reasons: list[str]
    #: SHIP, HOLD, or UNDERPOWERED. `ship` is true only for SHIP, so a caller
    #: that only reads the boolean keeps its old, conservative behaviour.
    verdict: str = "HOLD"

    def render(self) -> str:
        return "\n".join([self.verdict, *(f"  - {r}" for r in self.reasons)])


#: Single-run paired SE on the 129 public tasks. Empirical, not assumed.
SE_UNIT = 0.030


#: The smallest delta this project designs experiments to move (PLAN.md: "we can
#: resolve +/-0.05, so every experiment must be designed to move ~0.05"). Below
#: this, a null result means "not measured" rather than "no effect".
PLAUSIBLE_EFFECT = 0.05


def is_underpowered(
    overall: Comparison,
    se_unit: float = SE_UNIT,
    plausible_effect: float = PLAUSIBLE_EFFECT,
) -> bool | None:
    """Could this comparison have detected an effect worth shipping?

    Returns None when k is not tracked (k <= 0), so callers that never set it
    keep their previous behaviour rather than silently acquiring a new verdict.

    This exists because without it the ship rule has one failure mode for two
    different situations. At k=1 the detectable delta is ~0.064 against a design
    target of 0.05, so EVERY k=1 run returns "not significant" whatever the
    bundle does -- and that is indistinguishable, in the output, from having
    measured a real null. P002 reported HOLD on exactly such a run.
    """
    if overall.k_a <= 0 or overall.k_b <= 0:
        return None
    return detectable_delta(se_unit, overall.k_a, overall.k_b, overall.n_tasks) > plausible_effect


def decide(
    overall: Comparison,
    per_split: Mapping[str, Comparison],
    diagnostics_ok: bool = True,
    validator_ok: bool = True,
    split_floor: float = -0.02,
    se_unit: float = SE_UNIT,
    plausible_effect: float = PLAUSIBLE_EFFECT,
) -> ShipDecision:
    """Encode the ship rule so the decision is mechanical, not a judgement call.

    Made mechanical deliberately: after staring at a run for an hour, every
    result looks like it is probably an improvement.

    `overall` must be the **resolution** comparison. A surrogate such as
    gold-file localization informs the next change; it never authorizes
    replacing the champion, because optimizing a surrogate wins the surrogate.
    """
    reasons: list[str] = []
    ok = True

    if overall.delta <= 0:
        ok = False
        reasons.append(f"delta {overall.delta:+.4f} is not positive")
    elif not overall.significant:
        ok = False
        reasons.append(
            f"delta {overall.delta:+.4f} has z={overall.z:+.2f} < {Z_ALPHA}; "
            "fold the change into the next bundle rather than paying to prove it alone"
        )
    else:
        reasons.append(f"delta {overall.delta:+.4f} significant at z={overall.z:+.2f}")

    for name, cmp_ in sorted(per_split.items()):
        if cmp_.delta < split_floor:
            ok = False
            reasons.append(f"regresses the {name} split by {cmp_.delta:+.4f} (floor {split_floor:+.2f})")
        else:
            reasons.append(f"{name} split {cmp_.delta:+.4f}")

    # Hard gates. These are not measurement problems, so they outrank power:
    # a broken validator is a fact, not an insufficiently sampled one.
    hard_fail = False
    if not diagnostics_ok:
        ok = False
        hard_fail = True
        reasons.append("diagnostic panel regressed (empty-patch, contamination or scratch-leak worse)")
    if not validator_ok:
        ok = False
        hard_fail = True
        reasons.append("bundle validator reported errors")

    under = is_underpowered(overall, se_unit, plausible_effect)
    if under and not hard_fail:
        mde = detectable_delta(se_unit, overall.k_a, overall.k_b, overall.n_tasks)
        if overall.significant:
            # Significance and power are different things. A detection at low
            # power is real in sign and unreliable in magnitude.
            reasons.append(
                f"significant at low power: k={overall.k_a} vs k={overall.k_b} detects only "
                f"{mde:+.3f}, so this {overall.delta:+.4f} is likely inflated (winner's curse). "
                f"Confirm at k>=2 before shipping"
            )
        else:
            reasons.append(
                f"UNDERPOWERED: k={overall.k_a} vs k={overall.k_b} detects only {mde:+.3f} "
                f"against a design target of {plausible_effect:+.3f}, so this null means "
                f"'not measured', not 'no effect'. Read the localization panel for direction"
            )
        return ShipDecision(ship=False, reasons=reasons, verdict="UNDERPOWERED")

    return ShipDecision(ship=ok, reasons=reasons, verdict="SHIP" if ok else "HOLD")


@dataclass(frozen=True)
class PairedDelta:
    """A paired mean difference on a continuous per-task quantity.

    The binary estimators above cover resolution and the localization surrogates.
    They do not cover what the budget-guard variant actually targets: the coder's
    share of tool calls, and the fraction of calls that are verbatim re-issues.

    Those are computed WITHIN task and then averaged, never as a difference of two
    independent means. Tasks differ enormously from one another -- one probe_c12
    task used 173 tool calls against a median of 31 -- so an unpaired estimate
    spends all its power on between-task variance that pairing cancels outright.
    """

    name: str
    n: int
    mean_a: float
    mean_b: float
    delta: float  # b - a; negative means b is lower
    se: float
    z: float

    @property
    def significant(self) -> bool:
        # n < 2 has no variance estimate at all, so it can never be significant.
        # Reporting certainty from a single task is the error that made the first
        # budget verdict wrong, and it is cheap to make structurally impossible.
        return self.n >= 2 and self.se > 0 and abs(self.z) >= Z_ALPHA

    def render(self) -> str:
        if self.n == 0:
            return f"  {self.name}: not measured (no paired tasks)"
        body = (f"  {self.name}: {self.mean_a:.3f} -> {self.mean_b:.3f}  "
                f"delta {self.delta:+.3f}  n={self.n}")
        if self.n < 2:
            return body + "  (one task; no variance estimate, not a result)"
        if self.se == 0:
            return body + "  (identical on every task)"
        return (body + f"  SE {self.se:.3f}  z={self.z:+.2f}  "
                + ("SIGNIFICANT" if self.significant else "not significant"))


def paired_delta(name: str, pairs: Sequence[tuple[float, float]]) -> PairedDelta:
    """Mean within-pair difference (b - a) with its standard error.

    *pairs* is one (a, b) per task, for tasks measured under both arms. Tasks
    present in only one arm must be dropped by the caller rather than imputed:
    a missing task usually means that arm crashed on it, which is informative in
    its own right and must not be averaged away.
    """
    diffs = [b - a for a, b in pairs]
    n = len(diffs)
    if n == 0:
        return PairedDelta(name, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
    mean_a = sum(a for a, _ in pairs) / n
    mean_b = sum(b for _, b in pairs) / n
    delta = sum(diffs) / n
    if n < 2:
        return PairedDelta(name, n, mean_a, mean_b, delta, 0.0, 0.0)
    var = sum((d - delta) ** 2 for d in diffs) / (n - 1)
    se = math.sqrt(var / n)
    z = delta / se if se > 0 else 0.0
    return PairedDelta(name, n, mean_a, mean_b, delta, se, z)
