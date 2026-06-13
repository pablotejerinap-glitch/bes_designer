"""
Equipment scoring functions for BES/ESP recommendation engine.

All scores are on a 0–10 scale (10 = best). Overall score is a
weighted average of individual dimension scores.

Reference: Brown, "The Technology of Artificial Lift Methods",
Vol. 2b, Section 4.5325 (selection criteria).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import PumpCurve

# Default scoring weights
DEFAULT_WEIGHTS: dict[str, float] = {
    "efficiency": 0.40,
    "flexibility": 0.30,
    "provider": 0.30,
}


def efficiency_score(efficiency: float) -> float:
    """Convert pump hydraulic efficiency to a 0–10 score.

    Linear mapping: 0 % efficiency → 0, 100 % efficiency → 10.

    Args:
        efficiency: Pump hydraulic efficiency [0–1].

    Returns:
        Score [0–10].
    """
    return max(0.0, min(10.0, efficiency * 10.0))


def flexibility_score(pump: "PumpCurve", flow: float) -> float:
    """Score how close the operating point is to the pump's BEP.

    10 = operating exactly at BEP (maximum flexibility and reliability).
    0 = operating at the edge of the recommended range.

    The half-range of the recommended flow window is used as the
    normalisation denominator, so the score decreases linearly from BEP
    toward min_flow / max_flow.

    Args:
        pump: PumpCurve object from the catalog.
        flow: Actual operating flow rate [STB/d].

    Returns:
        Score [0–10].
    """
    half_range = (pump.max_flow - pump.min_flow) / 2.0
    if half_range <= 0.0:
        return 10.0
    deviation = abs(flow - pump.bep_flow) / half_range
    return max(0.0, min(10.0, 10.0 * (1.0 - deviation)))


def provider_score(manufacturer: str, preferred: str | None = None) -> float:
    """Score a design by manufacturer (provider) preference.

    When no provider is preferred, every design scores full marks so the
    dimension does not bias the ranking. When a preferred provider is given,
    designs from that manufacturer score 10 and the rest score 5 (a moderate
    nudge, not a veto — efficiency and flexibility can still prevail).

    Args:
        manufacturer: Manufacturer of the design's pump.
        preferred: Preferred manufacturer name (case-insensitive). Empty or
            ``None`` means no preference.

    Returns:
        Score [0–10].
    """
    if not preferred or not preferred.strip():
        return 10.0
    return 10.0 if manufacturer.strip().lower() == preferred.strip().lower() else 5.0


def overall_score(
    metrics: dict[str, float],
    weights: dict[str, float] | None = None,
) -> float:
    """Weighted average of individual dimension scores.

    Args:
        metrics: Dict of dimension name → score (0–10).
        weights: Dict of dimension name → weight. Defaults to
            ``DEFAULT_WEIGHTS`` (efficiency 40 %, flexibility 30 %,
            provider 30 %).

    Returns:
        Weighted overall score [0–10].
    """
    w = weights if weights is not None else DEFAULT_WEIGHTS
    total_w = sum(w.get(k, 0.0) for k in metrics)
    if total_w <= 0.0:
        return 0.0
    return sum(metrics[k] * w.get(k, 0.0) for k in metrics) / total_w
