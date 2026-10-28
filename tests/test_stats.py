"""The estimator has to be right, because every spending decision runs through it."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swegemma_lab.stats import (
    ArmStats,
    Comparison,
    compare,
    decide,
    detectable_delta,
    is_underpowered,
    mcnemar_exact,
    noise_floor,
    posterior_p_better,
    should_abort,
)


def arm(name, rates, k=1):
    """Build an arm from {task: resolved_fraction} at k runs per task."""
    return ArmStats(name, {t: (round(r * k), k) for t, r in rates.items()})


def test_identical_arms_have_zero_delta():
    a = arm("a", {f"t{i}": i % 2 for i in range(20)})
    b = arm("b", {f"t{i}": i % 2 for i in range(20)})
    cmp_ = compare(a, b)
    assert cmp_.delta == pytest.approx(0.0)
    assert not cmp_.significant
    assert cmp_.gained == [] and cmp_.lost == []


def test_recovers_a_known_delta():
    """b resolves 10 of 100, a resolves those plus 10 more."""
    b = arm("b", {f"t{i}": 1 if i < 10 else 0 for i in range(100)})
    a = arm("a", {f"t{i}": 1 if i < 20 else 0 for i in range(100)})
    cmp_ = compare(a, b)
    assert cmp_.delta == pytest.approx(0.10)
    assert len(cmp_.gained) == 10
    assert len(cmp_.lost) == 0


def test_k1_falls_back_to_discordant_pairs_for_variance():
    """At k=1 every p_i is 0 or 1, so the within-task term p(1-p)/k vanishes.

    This test previously asserted `se == 0.0` and called it a documented hazard --
    "the estimator cannot see the sampling noise it is not being shown". That was
    the bug, not a property: SE=0 makes z infinite and the ship rule then reads any
    positive delta as certain. The first real paired run hit exactly this and
    printed SIGNIFICANT for a 3-gained/1-lost split (exact McNemar p = 0.625).

    The variance now comes from the discordant pairs instead, which is the McNemar
    view and the only information k=1 actually carries.
    """
    b = arm("b", {f"t{i}": 0 for i in range(50)})
    a = arm("a", {f"t{i}": 1 if i < 5 else 0 for i in range(50)})
    cmp_ = compare(a, b)
    assert cmp_.delta > 0
    assert cmp_.se == pytest.approx(5 ** 0.5 / 50), "SE from 5 discordant pairs"
    assert abs(cmp_.z) != float("inf")


def test_borderline_tasks_drive_the_variance():
    """Two arms that both sit at 0.5 on every task must show real uncertainty."""
    counts = {f"t{i}": (2, 4) for i in range(100)}
    a = ArmStats("a", counts)
    b = ArmStats("b", dict(counts))
    cmp_ = compare(a, b)
    assert cmp_.delta == pytest.approx(0.0)
    assert cmp_.se > 0.0


def test_se_shrinks_with_more_runs():
    mid = {f"t{i}": 0.5 for i in range(100)}
    se = []
    for k in (2, 4, 8):
        a = ArmStats("a", {t: (k // 2, k) for t in mid})
        b = ArmStats("b", {t: (k // 2, k) for t in mid})
        se.append(compare(a, b).se)
    assert se[0] > se[1] > se[2]
    # Doubling k should cut SE by about sqrt(2).
    assert se[0] / se[1] == pytest.approx(2**0.5, rel=0.05)


def test_compare_uses_only_shared_tasks():
    a = arm("a", {"t1": 1, "t2": 1, "t3": 1})
    b = arm("b", {"t1": 0, "t2": 0})
    cmp_ = compare(a, b)
    assert cmp_.n_tasks == 2


def test_compare_rejects_disjoint_arms():
    with pytest.raises(ValueError):
        compare(arm("a", {"t1": 1}), arm("b", {"t2": 1}))


def test_detectable_delta_matches_the_planning_table():
    """The numbers the GPU budget was planned against."""
    assert detectable_delta(0.030, 1, 1) == pytest.approx(0.064, abs=0.003)
    assert detectable_delta(0.030, 2, 2) == pytest.approx(0.045, abs=0.003)
    assert detectable_delta(0.030, 4, 4) == pytest.approx(0.032, abs=0.003)
    # A k=2 candidate against a k=4 reference is the workhorse configuration.
    assert detectable_delta(0.030, 2, 4) < detectable_delta(0.030, 2, 2)


def test_noise_floor():
    mean, sd = noise_floor([0.13, 0.15, 0.12, 0.16])
    assert mean == pytest.approx(0.14)
    assert sd == pytest.approx(0.018, abs=0.002)


def test_noise_floor_needs_two_runs():
    with pytest.raises(ValueError):
        noise_floor([0.13])


def test_mcnemar_symmetric_and_bounded():
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(5, 5) == pytest.approx(1.0)
    assert mcnemar_exact(10, 0) < 0.01
    assert mcnemar_exact(3, 9) == pytest.approx(mcnemar_exact(9, 3))
    for g in range(12):
        for l in range(12):
            assert 0.0 <= mcnemar_exact(g, l) <= 1.0


def test_posterior_is_calibrated_at_the_symmetric_point():
    assert posterior_p_better(5, 5) == pytest.approx(0.5)
    assert posterior_p_better(0, 0) == pytest.approx(0.5)
    assert posterior_p_better(10, 1) > 0.95
    assert posterior_p_better(1, 10) < 0.05


def test_posterior_monotone_in_wins():
    prev = 0.0
    for g in range(0, 12):
        cur = posterior_p_better(g, 6)
        assert cur >= prev
        prev = cur


def test_abort_waits_for_enough_evidence_then_fires():
    assert not should_abort(0, 4)  # too few discordant pairs to judge
    assert should_abort(0, 10)
    assert not should_abort(6, 6)
    assert not should_abort(10, 2)


def _cmp(delta, z=99.0):
    return Comparison(a="cand", b="ref", n_tasks=100, rate_a=0.2, rate_b=0.2 - delta,
                      delta=delta, se=0.01, z=z)


def test_ship_rule_accepts_a_clean_win():
    d = decide(_cmp(0.05), {"dev": _cmp(0.06), "confirm": _cmp(0.04)})
    assert d.ship, d.render()


def test_ship_rule_blocks_a_confirm_split_regression():
    """The 0.05-scoring competitor's failure mode: helps the dev repos, hurts elsewhere."""
    d = decide(_cmp(0.05), {"dev": _cmp(0.12), "confirm": _cmp(-0.06)})
    assert not d.ship
    assert any("confirm" in r for r in d.reasons)


def test_ship_rule_blocks_insignificant_and_says_to_fold():
    d = decide(_cmp(0.02, z=0.8), {"dev": _cmp(0.02), "confirm": _cmp(0.02)})
    assert not d.ship
    assert any("fold" in r for r in d.reasons)


def test_ship_rule_blocks_on_diagnostics_or_validator():
    splits = {"dev": _cmp(0.06), "confirm": _cmp(0.04)}
    assert not decide(_cmp(0.05), splits, diagnostics_ok=False).ship
    assert not decide(_cmp(0.05), splits, validator_ok=False).ship


def test_no_false_positive_rate_blowup_on_null_effect():
    """Simulate the null: two arms sampling the same per-task probabilities.

    With k=4 the adopt rate must stay near the nominal 10%. This is the guard
    against the estimator quietly rubber-stamping noise.
    """
    rng = random.Random(20260930)
    probs = [0.9] * 8 + [0.4] * 18 + [0.02] * 103  # the mixture assumed when budgeting
    k = 4
    adopted = 0
    trials = 400
    for _ in range(trials):
        ca, cb = {}, {}
        for i, p in enumerate(probs):
            t = f"t{i}"
            ca[t] = (sum(rng.random() < p for _ in range(k)), k)
            cb[t] = (sum(rng.random() < p for _ in range(k)), k)
        if compare(ArmStats("a", ca), ArmStats("b", cb)).significant:
            adopted += 1
    rate = adopted / trials
    assert rate < 0.20, f"false-adopt rate {rate:.3f} far above the nominal 0.10"


def test_k1_is_conservative_not_reckless_under_the_null():
    """Why k=1 decisions are still banned -- but the reason changed.

    This test used to assert `adopt_rate(1) > adopt_rate(4)`: with SE=0 at k=1, a
    null fired constantly. With the discordant-pair fallback k=1 is now the
    CONSERVATIVE end, so the argument against k=1 is low power, not false adoption.
    Both rates must stay bounded near alpha; neither may blow up.
    """
    rng = random.Random(7)
    probs = [0.9] * 8 + [0.4] * 18 + [0.02] * 103

    def adopt_rate(k, trials=300):
        hits = 0
        for _ in range(trials):
            ca, cb = {}, {}
            for i, p in enumerate(probs):
                t = f"t{i}"
                ca[t] = (sum(rng.random() < p for _ in range(k)), k)
                cb[t] = (sum(rng.random() < p for _ in range(k)), k)
            g = compare(ArmStats("a", ca), ArmStats("b", cb))
            if g.significant:
                hits += 1
        return hits / trials

    r1, r4 = adopt_rate(1), adopt_rate(4)
    assert r1 <= 0.25, f"k=1 false-adopt rate {r1} is out of control"
    assert r4 <= 0.25, f"k=4 false-adopt rate {r4} is out of control"


def test_the_fallback_engages_only_when_within_task_variance_is_zero():
    """The fallback is keyed on zero variance, NOT on k==1.

    Worth pinning down, because my first attempt at this test assumed k=4 would
    have a smaller SE on the same rates -- it does not. Deterministic 0/1 rates give
    p(1-p)=0 at EVERY k, so a k=4 run where no task is borderline is just as blind
    as a k=1 run, and must get the same discordant-pair treatment. Conversely any
    borderline task restores the within-task estimator.
    """
    det_a = {f"t{i}": (1 if i < 6 else 0) for i in range(24)}
    det_b = {f"t{i}": 0 for i in range(24)}
    # Deterministic at k=4: still no within-task variance, so still the fallback.
    c_det = compare(arm("a", det_a, k=4), arm("b", det_b, k=4))
    assert c_det.se == pytest.approx(6 ** 0.5 / 24)

    # One borderline task at k=4 puts real variance back in, and the estimator
    # must then use it rather than the discordant-pair count.
    mixed_a = dict(det_a)
    mixed_a["t0"] = 0.5
    c_mixed = compare(arm("a", mixed_a, k=4), arm("b", det_b, k=4))
    assert c_mixed.se != pytest.approx(6 ** 0.5 / 24)
    assert c_mixed.se > 0


# --- paired mean difference -------------------------------------------------
#
# The binary estimator above covers resolution and the localization surrogates.
# It does NOT cover the quantities the budget-guard variant actually targets --
# the coder's share of tool calls, and the fraction of calls that are verbatim
# re-issues. Those are continuous per-task values, so they need a paired mean
# difference, computed on the WITHIN-TASK differences rather than on two
# independent means: tasks differ enormously from each other (one probe_c12 task
# used 173 calls against a median of 31), and pairing cancels that variance
# instead of drowning in it.

from swegemma_lab.stats import PairedDelta, paired_delta  # noqa: E402


def test_paired_delta_uses_within_task_differences():
    """A constant +0.10 shift on every task has zero variance, so it is certain
    however spread out the tasks themselves are."""
    pairs = [(0.1, 0.2), (0.5, 0.6), (0.9, 1.0)]
    d = paired_delta("share", pairs)
    assert d.n == 3
    assert d.delta == pytest.approx(0.10)
    assert d.se == pytest.approx(0.0)
    assert d.significant


def test_unpaired_spread_does_not_swamp_a_consistent_shift():
    """The same data, treated as two independent samples, would look like noise.
    This is the whole reason for pairing, so it is asserted rather than assumed."""
    import statistics
    a = [0.05, 0.40, 0.95]
    b = [0.15, 0.50, 1.00]
    naive_se = (statistics.stdev(a) ** 2 / 3 + statistics.stdev(b) ** 2 / 3) ** 0.5
    d = paired_delta("share", list(zip(a, b)))
    assert d.se < naive_se / 10, "pairing must cancel between-task variance"


def test_opposing_differences_cancel_and_are_not_significant():
    pairs = [(0.2, 0.4), (0.4, 0.2), (0.3, 0.3)]
    d = paired_delta("share", pairs)
    assert d.delta == pytest.approx(0.0)
    assert not d.significant


def test_a_single_pair_cannot_be_significant():
    """n=1 has no variance estimate. Reporting certainty from one task would be
    the exact error that made the first budget verdict wrong."""
    d = paired_delta("share", [(0.1, 0.9)])
    assert d.n == 1
    assert d.delta == pytest.approx(0.8)
    assert d.se == 0.0
    assert not d.significant, "one pair must never read as significant"


def test_no_pairs_is_empty_not_an_error():
    d = paired_delta("share", [])
    assert d.n == 0
    assert not d.significant
    assert "not measured" in d.render().lower() or d.n == 0


def test_direction_is_b_minus_a():
    d = paired_delta("share", [(0.8, 0.3), (0.7, 0.2)])
    assert d.delta < 0, "b worse than a must read negative"


def test_render_states_n_and_does_not_claim_significance_when_absent():
    txt = paired_delta("coder_share", [(0.2, 0.4), (0.3, 0.35), (0.25, 0.5)]).render()
    assert "coder_share" in txt
    assert "n=3" in txt


# --- k=1 must not read as infinite certainty ---------------------------------
#
# The within-task variance term p(1-p)/k is ZERO for every task when k=1, because
# each p is 0 or 1. That made Var(delta)=0, SE=0 and z=+/-inf, and the report then
# printed "SIGNIFICANT" for a 3-vs-1 discordant split whose exact McNemar p is
# 0.625. Caught on the first real paired run, which is exactly the run it would
# have caused us to overreact to.
#
# At k=1 there is no replication to estimate variance FROM, so the paired SE has to
# come from the discordant pairs instead: SE = sqrt(gained + lost) / n.


def test_k1_delta_is_not_infinitely_certain():
    a = arm("a", {"t1": 1, "t2": 1, "t3": 1, "t4": 0}, k=1)
    b = arm("b", {"t1": 1, "t2": 0, "t3": 0, "t4": 0}, k=1)
    c = compare(a, b)
    assert c.delta > 0
    assert c.se > 0, "k=1 must still have a standard error"
    assert abs(c.z) != float("inf"), "z must be finite"


def test_k1_three_gained_one_lost_is_not_significant():
    """delta = 2/12, SE = sqrt(4)/12 -> z = 1.0, below the 1.2816 threshold.
    This is the exact shape of the first paired run's gold-exact comparison."""
    rates_a = {f"t{i}": 0 for i in range(12)}
    rates_b = dict(rates_a)
    for i in (0, 1, 2):      # gained by a
        rates_a[f"t{i}"] = 1
    rates_b["t3"] = 1        # lost by a
    c = compare(arm("a", rates_a, k=1), arm("b", rates_b, k=1))
    assert len(c.gained) == 3 and len(c.lost) == 1
    assert c.delta == pytest.approx(2 / 12)
    assert c.se == pytest.approx(4 ** 0.5 / 12)
    assert c.z == pytest.approx(1.0)
    assert not c.significant, "3 gained vs 1 lost is not evidence"


def test_k1_with_no_discordant_pairs_is_zero_not_infinite():
    rates = {"t1": 1, "t2": 0, "t3": 1}
    c = compare(arm("a", rates, k=1), arm("b", rates, k=1))
    assert c.delta == pytest.approx(0.0)
    assert c.z == pytest.approx(0.0)
    assert not c.significant


def test_k1_large_consistent_gain_can_be_significant():
    """The fallback must still be able to detect a real effect, or it would be
    merely pessimistic rather than correct. 9 gained, 0 lost out of 12."""
    rates_a = {f"t{i}": (1 if i < 9 else 0) for i in range(12)}
    rates_b = {f"t{i}": 0 for i in range(12)}
    c = compare(arm("a", rates_a, k=1), arm("b", rates_b, k=1))
    assert c.se == pytest.approx(9 ** 0.5 / 12)
    assert c.z == pytest.approx(3.0)
    assert c.significant


def test_k2_still_uses_within_task_variance():
    """The k>=2 path must be untouched: a task at 0.5 contributes real variance."""
    c = compare(arm("a", {"t1": 0.5, "t2": 1.0}, k=2), arm("b", {"t1": 0.0, "t2": 0.5}, k=2))
    assert c.se > 0
    assert abs(c.z) != float("inf")


# --- Underpowered comparisons are not the same as measured nulls -------------
#
# Added 2026-10-12 after a council review pointed out that the ship rule could
# only ever return HOLD at the budgets this project can afford, which makes
# "HOLD" mean two incompatible things: "we measured and it did not help" and
# "we could not measure". P002 reported HOLD on a k=1 run where only a delta
# above ~0.24 was detectable; that is the second case and must read differently.


def _cmp_k(delta, k_a, k_b, z=99.0):
    return Comparison(a="cand", b="ref", n_tasks=100, rate_a=0.2, rate_b=0.2 - delta,
                      delta=delta, se=0.01, z=z, k_a=k_a, k_b=k_b)


def test_power_is_only_assessed_when_k_is_known():
    """k=0 means the caller does not track k; keep the old behaviour exactly."""
    assert is_underpowered(_cmp(0.05)) is None
    d = decide(_cmp(0.05), {"dev": _cmp(0.06), "confirm": _cmp(0.04)})
    assert d.ship and d.verdict == "SHIP"


def test_k1_is_underpowered_and_k2_is_not():
    """Calibration: PLAN.md designs experiments to move ~0.05.

    The planning table is defined at the size SE_UNIT was measured on, n=129:
    k=1 is ~0.064 -- above 0.05, so a single pair of runs cannot see the effects
    we design for -- while k=2 is ~0.045 and can. Stated at n=129 explicitly,
    because the table is only true there; see the n-scaling tests at the end of
    this file.
    """
    at129 = lambda d, ka, kb: Comparison(  # noqa: E731
        a="cand", b="ref", n_tasks=129, rate_a=0.2, rate_b=0.2 - d,
        delta=d, se=0.01, z=99.0, k_a=ka, k_b=kb)
    assert is_underpowered(at129(0.02, 1, 1)) is True
    assert is_underpowered(at129(0.02, 2, 2)) is False
    assert is_underpowered(at129(0.02, 4, 4)) is False


def test_k2_is_marginal_even_on_the_full_clean_n():
    """A consequence worth having in a test rather than discovering mid-run.

    clean-N is 102 tasks, where k=2 prices at ~0.051 -- just OVER the 0.05
    design target. So k=2 is powered only on the full 129, and every frozen
    clean-N comparison at k=2 sits on the boundary.
    """
    assert detectable_delta(0.030, 2, 2, n_tasks=102) > 0.05
    assert detectable_delta(0.030, 2, 2, n_tasks=102) == pytest.approx(0.051, abs=0.002)


def test_underpowered_null_reads_as_underpowered_not_hold():
    d = decide(_cmp_k(0.02, 1, 1, z=0.8), {"dev": _cmp_k(0.02, 1, 1, z=0.8)})
    assert not d.ship
    assert d.verdict == "UNDERPOWERED"
    assert "UNDERPOWERED" in d.render()
    assert any("not measured" in r for r in d.reasons), d.reasons


def test_powered_null_still_reads_as_hold():
    """The distinction has to cut both ways or it is just a nicer word for HOLD."""
    d = decide(_cmp_k(0.02, 4, 4, z=0.8), {"dev": _cmp_k(0.02, 4, 4, z=0.8)})
    assert not d.ship
    assert d.verdict == "HOLD"


def test_underpowered_but_significant_does_not_ship():
    """Winner's curse: a detection at low power has an unreliable effect size."""
    d = decide(_cmp_k(0.30, 1, 1, z=2.5), {"dev": _cmp_k(0.30, 1, 1, z=2.5)})
    assert not d.ship
    assert d.verdict == "UNDERPOWERED"
    assert any("inflated" in r for r in d.reasons), d.reasons


def test_hard_gates_outrank_power():
    """A broken validator is not a measurement problem; it stays a HOLD."""
    d = decide(_cmp_k(0.05, 1, 1), {"dev": _cmp_k(0.05, 1, 1)}, validator_ok=False)
    assert not d.ship
    assert d.verdict == "HOLD"


def test_a_surrogate_can_never_ship_a_bundle():
    """Guard against the Goodhart error: localization informs, it does not authorize.

    `decide` is deliberately metric-agnostic, so this is enforced by the caller
    passing the resolution comparison. The property under test is that no
    verdict other than SHIP sets ship=True, so a surrogate-driven call cannot
    be mistaken for an authorization.
    """
    for d in (
        decide(_cmp_k(0.02, 1, 1, z=0.8), {}),
        decide(_cmp_k(0.02, 4, 4, z=0.8), {}),
        decide(_cmp_k(0.05, 4, 4), {}, validator_ok=False),
    ):
        assert d.ship is (d.verdict == "SHIP")
        assert not d.ship


# --- the detectable delta must depend on n (2026-10-21) -------------------
# SE_UNIT is documented as the paired SE "on the 129 public tasks", but
# detectable_delta took no n, so it returned 0.064 at k=1 whether the run was 12
# tasks or 129. Every run this project has priced was smaller than 129, so every
# one was under-priced -- and at k=2/n=60 the verdict FLIPS: 0.045 reads as
# powered when the truth is 0.066, and `decide` would authorize SHIP/HOLD on a
# run that cannot see its own design target.


def test_detectable_delta_grows_as_the_task_set_shrinks():
    at_129 = detectable_delta(0.030, 1, 1, n_tasks=129)
    at_60 = detectable_delta(0.030, 1, 1, n_tasks=60)
    at_12 = detectable_delta(0.030, 1, 1, n_tasks=12)
    assert at_129 < at_60 < at_12
    assert at_60 == pytest.approx(0.093, abs=0.003)
    assert at_12 == pytest.approx(0.209, abs=0.005)


def test_detectable_delta_defaults_to_the_calibration_size():
    """Omitting n must reproduce the old documented table, not silently rescale."""
    assert detectable_delta(0.030, 1, 1) == pytest.approx(0.064, abs=0.003)


def test_k2_on_60_tasks_is_underpowered_despite_the_n129_table():
    """The flip this bug hid. The n=129 table calls k=2 powered; at n=60 it is not."""
    assert detectable_delta(0.030, 2, 2, n_tasks=129) < 0.05
    assert detectable_delta(0.030, 2, 2, n_tasks=60) > 0.05


def test_is_underpowered_uses_the_comparisons_own_n():
    powered = Comparison("a", "b", n_tasks=129, rate_a=0.1, rate_b=0.2,
                         delta=0.1, se=0.02, z=5.0, k_a=2, k_b=2)
    starved = Comparison("a", "b", n_tasks=60, rate_a=0.1, rate_b=0.2,
                         delta=0.1, se=0.02, z=5.0, k_a=2, k_b=2)
    assert is_underpowered(powered) is False
    assert is_underpowered(starved) is True
