"""
Engineering-criteria ranking for BES/ESP design alternatives.

Replaces the former weighted-score system (efficiency 40 % / flexibility
30 % / provider 30 %) with a strict, physically-meaningful ordering that
requires no arbitrary weights:

    1. Distance to BEP   — |q_op − q_BEP| / q_BEP  (ascending)
    2. Pump efficiency   — hydraulic efficiency at the operating point (descending)
    3. Required power    — total pump shaft HP (ascending)

The ordering is lexicographic: criterion 2 only breaks ties in criterion 1,
and criterion 3 only breaks ties in the first two. There are no weights,
no 0–10 scales, and no provider/brand dimension — the manufacturer is
informational only.

Engineering basis (Brown, Vol. 2b, §4.5325): the pump should be selected so
the design rate falls as close as possible to its best-efficiency point;
operating far from BEP increases axial thrust and wear and reduces run life.
Efficiency at the operating point and required shaft power follow directly
from the catalog performance curve.

BEP-distance classification (display only, never used for ordering):
    <= 10 %  → "optimo"     (very close to BEP)
    <= 25 %  → "aceptable"  (moderately away from BEP)
    >  25 %  → "alejado"    (far from BEP; verify with manufacturer)
These thresholds classify the same physical quantity used by criterion 1;
they mirror the practice of keeping the operating point well inside the
manufacturer's recommended range, whose half-width for the catalog pumps
is of the order of 20–40 % of the BEP flow.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bes.core.models import PumpCurve

# Classification thresholds on |q − q_BEP| / q_BEP (fractions)
BEP_OPTIMAL_MAX = 0.10
BEP_ACCEPTABLE_MAX = 0.25

# Classification → UI label (Spanish) and indicator
CLASSIFICATION_LABELS: dict[str, str] = {
    "optimo": "Muy cerca del BEP",
    "aceptable": "Moderadamente alejado del BEP",
    "alejado": "Alejado del BEP",
}
CLASSIFICATION_INDICATORS: dict[str, str] = {
    "optimo": "✅",
    "aceptable": "⚠",
    "alejado": "❌",
}


def bep_distance(pump: "PumpCurve", flow: float) -> float:
    """Relative distance from the operating flow to the pump's BEP flow.

    distance = |flow − bep_flow| / bep_flow

    A value of 0.0 means the pump operates exactly at its best-efficiency
    point; 0.10 means the operating rate deviates 10 % from the BEP rate.

    Args:
        pump: PumpCurve catalog object (provides ``bep_flow``).
        flow: Operating flow rate [STB/d]. Must be > 0.

    Returns:
        Dimensionless relative distance [>= 0].

    Raises:
        ValueError: If flow <= 0 or the pump has no positive BEP flow.
    """
    if flow <= 0:
        raise ValueError(f"flow must be > 0, got {flow}")
    if pump.bep_flow <= 0:
        raise ValueError(f"pump.bep_flow must be > 0, got {pump.bep_flow}")
    return abs(flow - pump.bep_flow) / pump.bep_flow


def ranking_key(
    bep_dist: float,
    efficiency: float,
    total_pump_hp: float,
) -> tuple[float, float, float]:
    """Sort key implementing the strict engineering ordering.

    Sorting a list of candidates ascending by this key orders them by:
    (1) closeness to BEP, (2) higher efficiency, (3) lower required power.

    Args:
        bep_dist: Relative BEP distance from :func:`bep_distance`.
        efficiency: Pump hydraulic efficiency at the operating point [0–1].
        total_pump_hp: Total pump shaft power requirement [hp].

    Returns:
        Tuple usable directly as a ``sort`` key (no weights involved).
    """
    return (bep_dist, -efficiency, total_pump_hp)


def classify_bep_distance(bep_dist: float) -> str:
    """Classify a BEP distance for display purposes (never for ordering).

    Args:
        bep_dist: Relative BEP distance [>= 0].

    Returns:
        One of ``"optimo"`` (<= 10 %), ``"aceptable"`` (<= 25 %),
        ``"alejado"`` (> 25 %).
    """
    if bep_dist <= BEP_OPTIMAL_MAX:
        return "optimo"
    if bep_dist <= BEP_ACCEPTABLE_MAX:
        return "aceptable"
    return "alejado"
