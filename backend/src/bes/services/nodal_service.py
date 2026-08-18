"""Nodal-analysis service.

Extracted from the inline logic in ``app.py`` (Análisis Nodal section). Produces
raw numeric metrics and comparison-table data so that any front-end (Streamlit
today, FastAPI/React tomorrow) only has to format and render.

Figure construction stays in ``ui/plots.py`` (framework-agnostic Plotly
builders); this service covers the *data* side only.
"""
from __future__ import annotations

from dataclasses import replace

from bes.core.models import Fluid, PumpCurve, Reservoir, SurfaceConditions, WellGeometry
from bes.core.nodal_analysis import METHOD_KEY, METHOD_LABEL, find_operating_point

# Única correlación multifásica del simulador (ver bes.core.multiphase).
NODAL_METHOD_KEY = METHOD_KEY
NODAL_METHOD_LABEL = METHOD_LABEL


def apply_reservoir_decline(reservoir: Reservoir, pr_decline_pct: float) -> Reservoir:
    """Return a Reservoir with static pressure declined by ``pr_decline_pct`` %.

    The bubble point is clamped to the new (lower) static pressure. When the
    decline is zero (or negative) the original reservoir is returned unchanged.
    This is the single source of truth for the decline simulation used by both
    the metrics service and the plot builders in the view.
    """
    if pr_decline_pct <= 0:
        return reservoir
    pr_new = reservoir.static_pressure * (1.0 - pr_decline_pct / 100.0)
    pb_new = min(reservoir.bubble_point, pr_new)
    return replace(reservoir, static_pressure=pr_new, bubble_point=pb_new)


def _single_metrics(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    pump: PumpCurve | None,
    stages: int | None,
    pump_depth: float | None,
) -> dict[str, float]:
    result = find_operating_point(
        reservoir, fluid, well, surface,
        pump=pump, stages=stages, pump_depth=pump_depth,
    )
    nat = result["natural_flow"]
    pmp = result["pump_flow"]
    q_nat = nat["q"] if nat else 0.0
    q_pmp = pmp["q"] if pmp else 0.0
    pwf_op = pmp["pwf"] if pmp else (nat["pwf"] if nat else 0.0)
    return {
        "q_natural":        q_nat,
        "q_pump":           q_pmp,
        "incremental_rate": result["incremental_rate"],
        "pwf_operating":    pwf_op,
        "pump_efficiency":  result["pump_efficiency"],
    }


def run_nodal_analysis(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    *,
    pr_decline_pct: float = 0.0,
    pump: PumpCurve | None = None,
    stages: int | None = None,
    pump_depth: float | None = None,
) -> dict:
    """Run a nodal analysis and return raw numeric results.

    Las pérdidas de carga se calculan siempre por Poettmann & Carpenter.

    Args:
        reservoir, fluid, well, surface: Domain inputs.
        pr_decline_pct: Reservoir-pressure decline to simulate [%].
        pump, stages, pump_depth: Optional pump context (from the top design).

    Returns:
        dict with keys ``reservoir_eff`` (the effective Reservoir after decline),
        ``pr_decline_pct``, ``has_pump``, ``method`` and ``metrics``.
        All values are raw numbers — formatting is the front-end's job.
    """
    reservoir_eff = apply_reservoir_decline(reservoir, pr_decline_pct)

    return {
        "reservoir_eff":  reservoir_eff,
        "pr_decline_pct": pr_decline_pct,
        "has_pump":       pump is not None,
        "method":         NODAL_METHOD_KEY,
        "metrics": _single_metrics(
            reservoir_eff, fluid, well, surface, pump, stages, pump_depth,
        ),
    }
