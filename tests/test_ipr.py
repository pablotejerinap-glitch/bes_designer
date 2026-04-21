"""
Unit tests for core/ipr.py.

Numerical references:
  - Vogel Example #2A: Brown Vol. 2b p.70, Pr=2000 psi, Pwf=340 psi,
    qmax=1188 STB/d → q ≈ 1117 STB/d (book rounds intermediate steps).
  - Standing combined IPR continuity at Pb verified analytically.
"""

import numpy as np
import pytest

from core.models import DriveMechanism, IPRMethod, Reservoir
from core.ipr import (
    calculate_pwf_for_target_rate,
    combined_ipr,
    fetkovich_ipr,
    generate_ipr_curve,
    linear_ipr,
    vogel_ipr,
    vogel_qmax_from_test,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_reservoir(
    method: IPRMethod,
    pr: float = 2000.0,
    pb: float = 1500.0,
    pi: float = 1.0,
) -> Reservoir:
    return Reservoir(
        static_pressure=pr,
        bubble_point=pb,
        productivity_index=pi,
        ipr_method=method,
        reservoir_temp=160.0,
        drive_mechanism=DriveMechanism.SOLUTION_GAS,
        datum_depth=7500.0,
    )


# ---------------------------------------------------------------------------
# linear_ipr
# ---------------------------------------------------------------------------

class TestLinearIPR:
    def test_zero_drawdown(self):
        assert linear_ipr(pr=2000, pwf=2000, pi=1.5) == pytest.approx(0.0)

    def test_full_drawdown(self):
        assert linear_ipr(pr=2000, pwf=0, pi=1.5) == pytest.approx(3000.0)

    def test_typical_case(self):
        # q = 1.5 * (2000 - 1500) = 750 STB/d
        assert linear_ipr(pr=2000, pwf=1500, pi=1.5) == pytest.approx(750.0)

    def test_proportionality(self):
        q1 = linear_ipr(pr=3000, pwf=1000, pi=2.0)
        q2 = linear_ipr(pr=3000, pwf=2000, pi=2.0)
        assert q1 == pytest.approx(2.0 * q2)

    def test_negative_pi_raises(self):
        with pytest.raises(ValueError, match="pi"):
            linear_ipr(pr=2000, pwf=1000, pi=-1.0)

    def test_zero_pi_raises(self):
        with pytest.raises(ValueError, match="pi"):
            linear_ipr(pr=2000, pwf=1000, pi=0.0)

    def test_pwf_above_pr_raises(self):
        with pytest.raises(ValueError, match="pwf"):
            linear_ipr(pr=2000, pwf=2500, pi=1.0)


# ---------------------------------------------------------------------------
# vogel_ipr — including Example #2A from Kermit Brown Vol. 2b, p.70
# ---------------------------------------------------------------------------

class TestVogelIPR:
    def test_zero_drawdown(self):
        # Pwf = Pr → q = 0
        assert vogel_ipr(pr=2000, pwf=2000, qmax=1188) == pytest.approx(0.0)

    def test_full_drawdown(self):
        # Pwf = 0 → q = qmax
        assert vogel_ipr(pr=2000, pwf=0, qmax=1188) == pytest.approx(1188.0)

    def test_book_example_2a(self):
        """Brown Vol. 2b Example #2A: Pr=2000, Pwf=340, qmax=1188 → q≈1117 STB/d.

        Formula gives 1188 * (1 - 0.2*(340/2000) - 0.8*(340/2000)^2) = 1120.1.
        The ±1 % tolerance covers the book's intermediate rounding of qmax.
        """
        q = vogel_ipr(pr=2000, pwf=340, qmax=1188)
        assert q == pytest.approx(1117, rel=0.01)

    def test_monotonically_decreasing_with_pwf(self):
        pwf_values = [0, 400, 800, 1200, 1600, 2000]
        q_values = [vogel_ipr(pr=2000, pwf=p, qmax=1000) for p in pwf_values]
        assert q_values == sorted(q_values, reverse=True)

    def test_negative_qmax_raises(self):
        with pytest.raises(ValueError, match="qmax"):
            vogel_ipr(pr=2000, pwf=500, qmax=-100)

    def test_pwf_above_pr_raises(self):
        with pytest.raises(ValueError, match="pwf"):
            vogel_ipr(pr=2000, pwf=2500, qmax=1000)


# ---------------------------------------------------------------------------
# vogel_qmax_from_test
# ---------------------------------------------------------------------------

class TestVogelQmaxFromTest:
    def test_roundtrip(self):
        """qmax → vogel_ipr at test point → vogel_qmax_from_test → original qmax."""
        pr, qmax_true = 2000.0, 1188.0
        pwf_test = 500.0
        q_test = vogel_ipr(pr, pwf_test, qmax_true)
        qmax_calc = vogel_qmax_from_test(pr, pwf_test, q_test)
        assert qmax_calc == pytest.approx(qmax_true, rel=1e-6)

    def test_book_example_2a_derive_qmax(self):
        """If q=1117 at Pwf=340 and Pr=2000, recover qmax≈1188."""
        qmax = vogel_qmax_from_test(pr=2000, pwf_test=340, q_test=1117)
        assert qmax == pytest.approx(1188, rel=0.01)

    def test_zero_q_test_raises(self):
        with pytest.raises(ValueError, match="q_test"):
            vogel_qmax_from_test(pr=2000, pwf_test=500, q_test=0)

    def test_pwf_equal_to_pr_raises(self):
        with pytest.raises(ValueError, match="pwf_test"):
            vogel_qmax_from_test(pr=2000, pwf_test=2000, q_test=100)


# ---------------------------------------------------------------------------
# combined_ipr
# ---------------------------------------------------------------------------

class TestCombinedIPR:
    def test_above_pb_matches_linear(self):
        """Above bubble point the combined IPR must equal the linear IPR."""
        pr, pb, pi = 3000.0, 2000.0, 1.2
        for pwf in [2800, 2500, 2100, 2000]:
            assert combined_ipr(pr, pb, pwf, pi) == pytest.approx(
                linear_ipr(pr, pwf, pi), rel=1e-9
            )

    def test_continuity_at_pb(self):
        """q must be continuous at Pwf = Pb (no jump)."""
        pr, pb, pi = 3000.0, 2000.0, 1.2
        eps = 1e-4
        q_above = combined_ipr(pr, pb, pb + eps, pi)
        q_below = combined_ipr(pr, pb, pb - eps, pi)
        assert q_above == pytest.approx(q_below, abs=0.01)

    def test_zero_at_pr(self):
        assert combined_ipr(pr=3000, pb=2000, pwf=3000, pi=1.5) == pytest.approx(0.0)

    def test_aof_below_pb(self):
        """AOF = PI*(Pr-Pb) + PI*Pb/1.8 — verify at Pwf=0."""
        pr, pb, pi = 3000.0, 2000.0, 1.2
        expected_aof = pi * (pr - pb) + pi * pb / 1.8
        assert combined_ipr(pr, pb, 0.0, pi) == pytest.approx(expected_aof, rel=1e-9)

    def test_monotonically_decreasing_with_pwf(self):
        pr, pb, pi = 3000.0, 2000.0, 1.2
        pwf_values = np.linspace(0, pr, 30)
        q_values = [combined_ipr(pr, pb, pwf, pi) for pwf in pwf_values]
        # q increases as pwf decreases → reversed list is sorted ascending
        assert q_values == sorted(q_values, reverse=True)

    def test_negative_pi_raises(self):
        with pytest.raises(ValueError, match="pi"):
            combined_ipr(pr=3000, pb=2000, pwf=1000, pi=-1)

    def test_pb_above_pr_raises(self):
        with pytest.raises(ValueError, match="pb"):
            combined_ipr(pr=2000, pb=2500, pwf=1000, pi=1.0)


# ---------------------------------------------------------------------------
# fetkovich_ipr
# ---------------------------------------------------------------------------

class TestFetkovichIPR:
    def test_n1_equals_linear_scaled(self):
        """For n=1, Fetkovich becomes q = C*(Pr²-Pwf²), verify against manual calc."""
        pr, pwf, c, n = 2000.0, 1000.0, 1e-4, 1.0
        expected = c * (pr ** 2 - pwf ** 2)
        assert fetkovich_ipr(pr, pwf, c, n) == pytest.approx(expected, rel=1e-9)

    def test_zero_drawdown(self):
        assert fetkovich_ipr(pr=2000, pwf=2000, c=1e-4, n=0.8) == pytest.approx(0.0)

    def test_negative_c_raises(self):
        with pytest.raises(ValueError, match="c"):
            fetkovich_ipr(pr=2000, pwf=1000, c=-1e-4, n=1.0)

    def test_negative_n_raises(self):
        with pytest.raises(ValueError, match="n"):
            fetkovich_ipr(pr=2000, pwf=1000, c=1e-4, n=-0.5)

    def test_pwf_above_pr_raises(self):
        with pytest.raises(ValueError, match="pwf"):
            fetkovich_ipr(pr=2000, pwf=2500, c=1e-4, n=1.0)


# ---------------------------------------------------------------------------
# calculate_pwf_for_target_rate — round-trip consistency
# ---------------------------------------------------------------------------

class TestCalculatePwfForTargetRate:
    """For each method: compute Pwf from a target q, then re-compute q from that
    Pwf; the recovered q must match the original target within 0.5 STB/d."""

    def test_roundtrip_linear(self):
        res = make_reservoir(IPRMethod.LINEAR, pr=3000, pi=2.0)
        target = 1200.0
        pwf = calculate_pwf_for_target_rate(res, target)
        q_back = linear_ipr(pr=res.static_pressure, pwf=pwf, pi=res.productivity_index)
        assert q_back == pytest.approx(target, abs=0.5)

    def test_roundtrip_vogel(self):
        res = make_reservoir(IPRMethod.VOGEL, pr=2000, pi=1.5)
        target = 600.0
        pwf = calculate_pwf_for_target_rate(res, target)
        qmax = res.productivity_index * res.static_pressure / 1.8
        q_back = vogel_ipr(pr=res.static_pressure, pwf=pwf, qmax=qmax)
        assert q_back == pytest.approx(target, abs=0.5)

    def test_roundtrip_combined_above_pb(self):
        """Target rate achievable above Pb → should land in linear region."""
        res = make_reservoir(IPRMethod.COMBINED, pr=3000, pb=2000, pi=1.2)
        # q_b = 1.2 * (3000 - 2000) = 1200; choose target < q_b
        target = 800.0
        pwf = calculate_pwf_for_target_rate(res, target)
        assert pwf > res.bubble_point  # must still be above Pb
        q_back = combined_ipr(res.static_pressure, res.bubble_point, pwf, res.productivity_index)
        assert q_back == pytest.approx(target, abs=0.5)

    def test_roundtrip_combined_below_pb(self):
        """Target rate requiring Pwf below Pb → must enter Vogel region."""
        res = make_reservoir(IPRMethod.COMBINED, pr=3000, pb=2000, pi=1.2)
        target = 1500.0  # above q_b=1200, requires sub-Pb Pwf
        pwf = calculate_pwf_for_target_rate(res, target)
        assert pwf < res.bubble_point
        q_back = combined_ipr(res.static_pressure, res.bubble_point, pwf, res.productivity_index)
        assert q_back == pytest.approx(target, abs=0.5)

    def test_roundtrip_fetkovich(self):
        # AOF = c*(pr²)^n = 5e-4*(3000²)^0.8 ≈ 183 STB/d > target=50 ✓
        res = make_reservoir(IPRMethod.FETKOVICH, pr=3000)
        c, n = 5e-4, 0.8
        target = 50.0
        pwf = calculate_pwf_for_target_rate(res, target, fetkovich_c=c, fetkovich_n=n)
        q_back = fetkovich_ipr(pr=res.static_pressure, pwf=pwf, c=c, n=n)
        assert q_back == pytest.approx(target, abs=0.5)

    def test_target_above_aof_raises(self):
        res = make_reservoir(IPRMethod.LINEAR, pr=2000, pi=1.0)
        # AOF = 1.0 * 2000 = 2000; request more
        with pytest.raises(ValueError, match="AOF"):
            calculate_pwf_for_target_rate(res, target_rate=2500.0)

    def test_zero_target_raises(self):
        res = make_reservoir(IPRMethod.LINEAR)
        with pytest.raises(ValueError, match="target_rate"):
            calculate_pwf_for_target_rate(res, target_rate=0.0)

    def test_fetkovich_missing_c_raises(self):
        res = make_reservoir(IPRMethod.FETKOVICH)
        with pytest.raises(ValueError, match="fetkovich_c"):
            calculate_pwf_for_target_rate(res, target_rate=100.0)

    def test_linear_closed_form_exact(self):
        """Linear IPR has a closed-form inverse — result must be exact."""
        res = make_reservoir(IPRMethod.LINEAR, pr=2000, pi=2.0)
        target = 1000.0
        pwf = calculate_pwf_for_target_rate(res, target)
        # Pwf = Pr - q/PI = 2000 - 1000/2 = 1500
        assert pwf == pytest.approx(1500.0, abs=0.01)


# ---------------------------------------------------------------------------
# generate_ipr_curve
# ---------------------------------------------------------------------------

class TestGenerateIPRCurve:
    def test_shape(self):
        res = make_reservoir(IPRMethod.LINEAR)
        q, pwf = generate_ipr_curve(res, n_points=20)
        assert q.shape == (20,)
        assert pwf.shape == (20,)

    def test_pwf_monotonically_decreasing(self):
        """Pwf array must run from Pr down to 0."""
        res = make_reservoir(IPRMethod.VOGEL, pr=2000, pi=1.5)
        _, pwf = generate_ipr_curve(res, n_points=30)
        assert np.all(np.diff(pwf) <= 0)

    def test_q_monotonically_nondecreasing_linear(self):
        res = make_reservoir(IPRMethod.LINEAR, pr=3000, pi=2.0)
        q, _ = generate_ipr_curve(res, n_points=30)
        assert np.all(np.diff(q) >= 0)

    def test_q_monotonically_nondecreasing_vogel(self):
        res = make_reservoir(IPRMethod.VOGEL, pr=2000, pi=1.5)
        q, _ = generate_ipr_curve(res, n_points=50)
        assert np.all(np.diff(q) >= -1e-9)

    def test_q_monotonically_nondecreasing_combined(self):
        res = make_reservoir(IPRMethod.COMBINED, pr=3000, pb=2000, pi=1.2)
        q, _ = generate_ipr_curve(res, n_points=50)
        assert np.all(np.diff(q) >= -1e-9)

    def test_q_monotonically_nondecreasing_fetkovich(self):
        res = make_reservoir(IPRMethod.FETKOVICH, pr=3000)
        q, _ = generate_ipr_curve(res, n_points=30, fetkovich_c=1e-5, fetkovich_n=0.8)
        assert np.all(np.diff(q) >= -1e-9)

    def test_boundary_values_linear(self):
        """At Pwf=Pr, q must be 0; at Pwf=0, q must equal PI*Pr (AOF)."""
        res = make_reservoir(IPRMethod.LINEAR, pr=2000, pi=1.5)
        q, pwf = generate_ipr_curve(res, n_points=50)
        assert q[0] == pytest.approx(0.0, abs=1e-6)   # Pwf = Pr
        assert q[-1] == pytest.approx(1.5 * 2000, rel=1e-6)  # Pwf = 0

    def test_boundary_values_vogel(self):
        res = make_reservoir(IPRMethod.VOGEL, pr=2000, pi=1.8)
        q, pwf = generate_ipr_curve(res, n_points=50)
        assert q[0] == pytest.approx(0.0, abs=1e-6)
        expected_aof = 1.8 * 2000 / 1.8  # = PI*Pr/1.8 * ... = 2000
        assert q[-1] == pytest.approx(expected_aof, rel=1e-6)

    def test_combined_continuity_across_pb(self):
        """q must be C0-continuous at Pb (value match, not slope).

        The combined IPR has a kink (slope change) at Pb but no value jump.
        We verify this by evaluating the function directly at Pb ± 1e-4 psi,
        not via coarse array neighbors which would show a large finite-difference
        even for a perfectly continuous function.
        """
        pr, pb, pi = 3000.0, 2000.0, 1.2
        res = make_reservoir(IPRMethod.COMBINED, pr=pr, pb=pb, pi=pi)
        eps = 1e-4
        q_above = combined_ipr(pr, pb, pb + eps, pi)
        q_below = combined_ipr(pr, pb, pb - eps, pi)
        assert q_above == pytest.approx(q_below, abs=0.01)

    def test_fetkovich_missing_c_raises(self):
        res = make_reservoir(IPRMethod.FETKOVICH)
        with pytest.raises(ValueError, match="fetkovich_c"):
            generate_ipr_curve(res)
