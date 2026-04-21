"""
Inflow Performance Relationship (IPR) calculations.

Implements linear, Vogel, Standing combined, and Fetkovich IPR methods
following Kermit Brown, "The Technology of Artificial Lift Methods",
Vol. 2b, Section 4.522 and Figure 4.55.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from core.models import IPRMethod, Reservoir


# ---------------------------------------------------------------------------
# Fundamental IPR functions
# ---------------------------------------------------------------------------

def linear_ipr(pr: float, pwf: float, pi: float) -> float:
    """Calculate flow rate using a constant productivity index (linear IPR).

    Valid for single-phase (undersaturated) flow, i.e. Pwf >= Pb.
    Formula: q = PI * (Pr - Pwf)

    Args:
        pr: Average reservoir pressure [psia].
        pwf: Flowing bottomhole pressure [psia]. Must satisfy 0 <= pwf <= pr.
        pi: Productivity index [STB/d/psi]. Must be > 0.

    Returns:
        Liquid flow rate [STB/d].

    Raises:
        ValueError: If pi <= 0 or pwf > pr.
    """
    if pi <= 0:
        raise ValueError(f"pi must be > 0, got {pi}")
    if pwf > pr:
        raise ValueError(f"pwf ({pwf}) cannot exceed pr ({pr})")
    return pi * (pr - pwf)


def vogel_ipr(pr: float, pwf: float, qmax: float) -> float:
    """Calculate flow rate using Vogel's IPR for solution-gas drive reservoirs.

    Applicable when Pwf < Pb (two-phase flow inside the reservoir).
    Formula: q/qmax = 1 - 0.2*(Pwf/Pr) - 0.8*(Pwf/Pr)^2

    Reference: Vogel, J.V., "Inflow Performance Relationships for Solution-Gas
    Drive Wells", JPT (1968).

    Args:
        pr: Average (or bubble-point) reservoir pressure used as reference [psia].
        pwf: Flowing bottomhole pressure [psia]. Must satisfy 0 <= pwf <= pr.
        qmax: Absolute open flow (AOF) potential at Pwf = 0 [STB/d]. Must be > 0.

    Returns:
        Liquid flow rate [STB/d].

    Raises:
        ValueError: If qmax <= 0 or pwf > pr.
    """
    if qmax <= 0:
        raise ValueError(f"qmax must be > 0, got {qmax}")
    if pwf > pr:
        raise ValueError(f"pwf ({pwf}) cannot exceed pr ({pr})")
    if pr == 0:
        return 0.0
    ratio = pwf / pr
    return qmax * (1.0 - 0.2 * ratio - 0.8 * ratio ** 2)


def vogel_qmax_from_test(pr: float, pwf_test: float, q_test: float) -> float:
    """Back-calculate Vogel AOF (qmax) from a single well test point.

    Inverts the Vogel equation to obtain qmax given one measured (Pwf, q) pair:
        qmax = q_test / [1 - 0.2*(Pwf_test/Pr) - 0.8*(Pwf_test/Pr)^2]

    Args:
        pr: Average reservoir pressure [psia].
        pwf_test: Measured flowing bottomhole pressure during the test [psia].
            Must satisfy 0 <= pwf_test < pr.
        q_test: Measured flow rate during the test [STB/d]. Must be > 0.

    Returns:
        Estimated AOF (qmax at Pwf = 0) [STB/d].

    Raises:
        ValueError: If q_test <= 0, pwf_test >= pr, or the Vogel denominator
            is non-positive (invalid test point).
    """
    if q_test <= 0:
        raise ValueError(f"q_test must be > 0, got {q_test}")
    if pwf_test >= pr:
        raise ValueError(
            f"pwf_test ({pwf_test}) must be < pr ({pr}) to have meaningful drawdown"
        )
    if pr <= 0:
        raise ValueError(f"pr must be > 0, got {pr}")
    ratio = pwf_test / pr
    denominator = 1.0 - 0.2 * ratio - 0.8 * ratio ** 2
    if denominator <= 0:
        raise ValueError(
            f"Vogel denominator is non-positive ({denominator:.6f}) for "
            f"pwf_test/pr = {ratio:.4f}. Test point is outside the valid range."
        )
    return q_test / denominator


def combined_ipr(pr: float, pb: float, pwf: float, pi: float) -> float:
    """Calculate flow rate using Standing's combined (composite) IPR.

    Stitches linear IPR above bubble-point and Vogel IPR below, with
    C0 continuity enforced at Pwf = Pb:

    - Pwf >= Pb:  q = PI * (Pr - Pwf)
    - Pwf < Pb:   q = q_b + (PI * Pb / 1.8) * [1 - 0.2*(Pwf/Pb) - 0.8*(Pwf/Pb)^2]
                  where q_b = PI * (Pr - Pb)

    Reference: Standing, M.B., "Inflow Performance Relationships for Damaged
    Wells Producing Under Solution-Gas Drive", JPT (1970).

    Args:
        pr: Average reservoir pressure [psia].
        pb: Bubble-point pressure [psia]. Must satisfy 0 <= pb <= pr.
        pwf: Flowing bottomhole pressure [psia]. Must satisfy 0 <= pwf <= pr.
        pi: Productivity index [STB/d/psi]. Must be > 0.

    Returns:
        Liquid flow rate [STB/d].

    Raises:
        ValueError: If pi <= 0, pwf > pr, or pb > pr.
    """
    if pi <= 0:
        raise ValueError(f"pi must be > 0, got {pi}")
    if pwf > pr:
        raise ValueError(f"pwf ({pwf}) cannot exceed pr ({pr})")
    if pb > pr:
        raise ValueError(f"pb ({pb}) cannot exceed pr ({pr})")

    if pwf >= pb:
        return pi * (pr - pwf)

    q_b = pi * (pr - pb)
    if pb == 0:
        return q_b
    ratio = pwf / pb
    vogel_below_pb = (pi * pb / 1.8) * (1.0 - 0.2 * ratio - 0.8 * ratio ** 2)
    return q_b + vogel_below_pb


def fetkovich_ipr(pr: float, pwf: float, c: float, n: float) -> float:
    """Calculate flow rate using Fetkovich's empirical backpressure IPR.

    Empirical equation that generalizes the backpressure test correlation,
    valid for two-phase flow.
    Formula: q = C * (Pr² - Pwf²)^n

    Args:
        pr: Average reservoir pressure [psia].
        pwf: Flowing bottomhole pressure [psia]. Must satisfy 0 <= pwf <= pr.
        c: Fetkovich deliverability coefficient [STB/d/psia^(2n)]. Must be > 0.
        n: Fetkovich flow exponent [-]. Must be > 0. Typically 0.5 <= n <= 1.0;
            n = 1 → Darcy (laminar) flow; n → 0.5 → fully turbulent flow.

    Returns:
        Liquid flow rate [STB/d].

    Raises:
        ValueError: If c <= 0, n <= 0, or pwf > pr.
    """
    if c <= 0:
        raise ValueError(f"c must be > 0, got {c}")
    if n <= 0:
        raise ValueError(f"n must be > 0, got {n}")
    if pwf > pr:
        raise ValueError(f"pwf ({pwf}) cannot exceed pr ({pr})")
    return c * (pr ** 2 - pwf ** 2) ** n


# ---------------------------------------------------------------------------
# Inverse solver: Pwf for a target rate
# ---------------------------------------------------------------------------

def calculate_pwf_for_target_rate(
    reservoir: Reservoir,
    target_rate: float,
    fetkovich_c: float | None = None,
    fetkovich_n: float = 1.0,
) -> float:
    """Find the flowing bottomhole pressure (Pwf) required to achieve a target rate.

    Inverts the IPR equation that corresponds to reservoir.ipr_method.
    The linear IPR has a closed-form inverse; all other methods use
    scipy.optimize.brentq with a bracket of [0, Pr].

    Args:
        reservoir: Reservoir object providing Pr, Pb, PI, and ipr_method.
        target_rate: Desired gross liquid flow rate [STB/d]. Must be > 0.
        fetkovich_c: Fetkovich coefficient C [STB/d/psia^(2n)]. Only required
            when reservoir.ipr_method is FETKOVICH.
        fetkovich_n: Fetkovich exponent n [-]. Defaults to 1.0.

    Returns:
        Required flowing bottomhole pressure Pwf [psia].

    Raises:
        ValueError: If target_rate > AOF (rate is not achievable), target_rate
            <= 0, or fetkovich_c is missing for the FETKOVICH method.
    """
    if target_rate <= 0:
        raise ValueError(f"target_rate must be > 0, got {target_rate}")

    pr = reservoir.static_pressure
    pb = reservoir.bubble_point
    pi = reservoir.productivity_index
    method = reservoir.ipr_method

    aof = _compute_aof(reservoir, fetkovich_c, fetkovich_n)
    if target_rate > aof:
        raise ValueError(
            f"target_rate {target_rate:.1f} STB/d exceeds the reservoir AOF "
            f"{aof:.1f} STB/d."
        )

    if method is IPRMethod.LINEAR:
        return pr - target_rate / pi

    if method is IPRMethod.VOGEL:
        qmax = pi * pr / 1.8
        def _res(pwf: float) -> float:
            return vogel_ipr(pr, pwf, qmax) - target_rate
        return brentq(_res, 0.0, pr, xtol=0.01)

    if method is IPRMethod.COMBINED:
        q_b = pi * (pr - pb)
        if target_rate <= q_b:
            # Rate can be achieved above bubble point — linear region
            return pr - target_rate / pi
        # Need to draw Pwf below Pb — use Vogel portion
        def _res(pwf: float) -> float:
            return combined_ipr(pr, pb, pwf, pi) - target_rate
        # Bracket: [0, Pb) — the entire sub-bubble-point range
        return brentq(_res, 0.0, pb * (1.0 - 1e-9), xtol=0.01)

    if method is IPRMethod.FETKOVICH:
        if fetkovich_c is None:
            raise ValueError(
                "fetkovich_c must be provided when ipr_method is FETKOVICH"
            )
        def _res(pwf: float) -> float:
            return fetkovich_ipr(pr, pwf, fetkovich_c, fetkovich_n) - target_rate
        return brentq(_res, 0.0, pr * (1.0 - 1e-9), xtol=0.01)

    raise ValueError(f"Unsupported IPR method: {method}")


# ---------------------------------------------------------------------------
# Curve generation
# ---------------------------------------------------------------------------

def generate_ipr_curve(
    reservoir: Reservoir,
    n_points: int = 50,
    fetkovich_c: float | None = None,
    fetkovich_n: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a complete IPR curve suitable for plotting.

    Evaluates the IPR from Pwf = Pr (zero draw-down, q = 0) to Pwf = 0
    (maximum draw-down, q = AOF), returning arrays ordered so that
    Pwf is monotonically decreasing and q is monotonically non-decreasing.

    Args:
        reservoir: Reservoir parameters (Pr, Pb, PI, ipr_method).
        n_points: Number of evaluation points. Defaults to 50.
        fetkovich_c: Fetkovich coefficient [STB/d/psia^(2n)]. Required only
            when ipr_method is FETKOVICH.
        fetkovich_n: Fetkovich exponent [-]. Defaults to 1.0.

    Returns:
        Tuple ``(q_array, pwf_array)`` where

        - ``q_array``   – flow rates [STB/d], shape ``(n_points,)``,
          monotonically non-decreasing (0 → AOF).
        - ``pwf_array`` – corresponding flowing BHP [psia], shape ``(n_points,)``,
          monotonically non-increasing (Pr → 0).

    Raises:
        ValueError: If fetkovich_c is missing for FETKOVICH method.
    """
    pr = reservoir.static_pressure
    pb = reservoir.bubble_point
    pi = reservoir.productivity_index
    method = reservoir.ipr_method

    pwf_array = np.linspace(pr, 0.0, n_points)

    if method is IPRMethod.LINEAR:
        q_array = np.array([linear_ipr(pr, pwf, pi) for pwf in pwf_array])

    elif method is IPRMethod.VOGEL:
        qmax = pi * pr / 1.8
        q_array = np.array([vogel_ipr(pr, pwf, qmax) for pwf in pwf_array])

    elif method is IPRMethod.COMBINED:
        q_array = np.array([combined_ipr(pr, pb, pwf, pi) for pwf in pwf_array])

    elif method is IPRMethod.FETKOVICH:
        if fetkovich_c is None:
            raise ValueError(
                "fetkovich_c must be provided when ipr_method is FETKOVICH"
            )
        q_array = np.array(
            [fetkovich_ipr(pr, pwf, fetkovich_c, fetkovich_n) for pwf in pwf_array]
        )

    else:
        raise ValueError(f"Unsupported IPR method: {method}")

    return q_array, pwf_array


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _compute_aof(
    reservoir: Reservoir,
    fetkovich_c: float | None,
    fetkovich_n: float,
) -> float:
    """Return the Absolute Open Flow potential (q at Pwf = 0) [STB/d]."""
    pr = reservoir.static_pressure
    pb = reservoir.bubble_point
    pi = reservoir.productivity_index
    method = reservoir.ipr_method

    if method is IPRMethod.LINEAR:
        return pi * pr
    if method is IPRMethod.VOGEL:
        # Derived from Vogel: at the tangent point near Pr, PI = 1.8 * qmax / Pr
        return pi * pr / 1.8
    if method is IPRMethod.COMBINED:
        # Linear contribution above Pb + Vogel maximum below Pb
        return pi * (pr - pb) + pi * pb / 1.8
    if method is IPRMethod.FETKOVICH:
        if fetkovich_c is None:
            raise ValueError("fetkovich_c required for FETKOVICH method")
        return fetkovich_ipr(pr, 0.0, fetkovich_c, fetkovich_n)
    raise ValueError(f"Unsupported IPR method: {method}")
