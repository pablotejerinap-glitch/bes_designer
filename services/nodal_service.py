"""Nodal-analysis service.

Extracted from the inline logic in ``app.py`` (Análisis Nodal section). Produces
raw numeric metrics and comparison-table data so that any front-end (Streamlit
today, FastAPI/React tomorrow) only has to format and render.

Figure construction stays in ``ui/plots.py`` (framework-agnostic Plotly
builders); this service covers the *data* side only.
"""
from __future__ import annotations

from dataclasses import replace

from core.models import Fluid, PumpCurve, Reservoir, SurfaceConditions, WellGeometry
from core.nodal_analysis import compare_methods, find_operating_point

# Canonical multiphase-correlation labels, shared by every front-end.
NODAL_METHOD_LABELS: dict[str, str] = {
    "hagedorn_brown":      "Hagedorn-Brown",
    "beggs_brill":         "Beggs-Brill",
    "duns_ros":            "Duns & Ros",
    "poettmann_carpenter": "Poettmann & Carpenter",
}


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
    method: str,
    pump: PumpCurve | None,
    stages: int | None,
    pump_depth: float | None,
) -> dict[str, float]:
    result = find_operating_point(
        reservoir, fluid, well, surface,
        method=method, pump=pump, stages=stages, pump_depth=pump_depth,
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


def _comparison_rows(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    pump: PumpCurve | None,
    stages: int | None,
    pump_depth: float | None,
) -> list[dict]:
    cmp_results = compare_methods(
        reservoir, fluid, well, surface,
        pump=pump, stages=stages, pump_depth=pump_depth,
    )
    rows: list[dict] = []
    for m_key, m_label in NODAL_METHOD_LABELS.items():
        res = cmp_results[m_key]
        q_n = res["natural_flow"]["q"] if res["natural_flow"] else 0.0
        q_p = res["pump_flow"]["q"]    if res["pump_flow"]    else 0.0
        pwf = res["pump_flow"]["pwf"]  if res["pump_flow"]    else 0.0
        rows.append({
            "method_key":      m_key,
            "method_label":    m_label,
            "q_natural":       q_n,
            "q_pump":          q_p,
            "incremental":     q_p - q_n,
            "pwf_operating":   pwf,
            "pump_efficiency": res["pump_efficiency"],
        })
    return rows


def run_nodal_analysis(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    *,
    method: str = "hagedorn_brown",
    pr_decline_pct: float = 0.0,
    compare_all: bool = False,
    pump: PumpCurve | None = None,
    stages: int | None = None,
    pump_depth: float | None = None,
) -> dict:
    """Run a nodal analysis and return raw numeric results.

    Args:
        reservoir, fluid, well, surface: Domain inputs.
        method: Multiphase correlation key (see ``NODAL_METHOD_LABELS``).
        pr_decline_pct: Reservoir-pressure decline to simulate [%].
        compare_all: If True, evaluate all four correlations for the table.
        pump, stages, pump_depth: Optional pump context (from the top design).

    Returns:
        dict with keys ``reservoir_eff`` (the effective Reservoir after decline),
        ``pr_decline_pct``, ``has_pump``, ``method``, ``mode`` ("single"|"compare"),
        and either ``metrics`` (single mode) or ``comparison`` (compare mode).
        All values are raw numbers — formatting is the front-end's job.
    """
    reservoir_eff = apply_reservoir_decline(reservoir, pr_decline_pct)

    out: dict = {
        "reservoir_eff":  reservoir_eff,
        "pr_decline_pct": pr_decline_pct,
        "has_pump":       pump is not None,
        "method":         method,
        "compare_all":    compare_all,
    }

    if compare_all:
        out["mode"] = "compare"
        out["comparison"] = _comparison_rows(
            reservoir_eff, fluid, well, surface, pump, stages, pump_depth,
        )
    else:
        out["mode"] = "single"
        out["metrics"] = _single_metrics(
            reservoir_eff, fluid, well, surface, method, pump, stages, pump_depth,
        )

    return out
