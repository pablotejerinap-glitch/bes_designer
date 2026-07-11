"""Sensitivity-analysis service.

Extracted from ``ui/sensitivity_view.py``. Varies a single input parameter over
a range and reports how the optimal design's HP, stages, efficiency and TDH
respond. Reads no framework state: the base domain objects are passed in, and an
optional ``progress`` callback lets a UI show progress without this layer
knowing anything about Streamlit.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable
import warnings

import numpy as np

from core.models import (
    DesignObjectives, Fluid, Reservoir, SurfaceConditions, WellGeometry,
)
from recommender.recommendation_engine import generate_recommendations

# Parameters the user can sweep, with display labels shared by every front-end.
PARAM_LABELS: dict[str, str] = {
    "water_cut":        "Corte de agua (WC)",
    "gor":              "GOR (scf/STB)",
    "static_pressure":  "Presión de reservorio (psi)",
    "target_flow_rate": "Tasa objetivo (STB/d)",
}

DEFAULT_N_POINTS = 7


def base_value(
    reservoir: Reservoir, fluid: Fluid, objectives: DesignObjectives, param: str,
) -> float:
    """Current (base) value of the swept parameter."""
    return {
        "water_cut":        fluid.water_cut,
        "gor":              fluid.gor,
        "static_pressure":  reservoir.static_pressure,
        "target_flow_rate": objectives.target_flow_rate,
    }[param]


def sweep_range(base_val: float, param: str, pct_range_pct: float) -> tuple[float, float]:
    """Return the (lo, hi) sweep bounds, clamped to physically valid ranges."""
    lo = base_val * (1.0 - pct_range_pct / 100.0)
    hi = base_val * (1.0 + pct_range_pct / 100.0)
    if param == "water_cut":
        lo, hi = max(lo, 0.01), min(hi, 0.99)
    elif param in ("gor", "static_pressure", "target_flow_rate"):
        lo = max(lo, 1.0)
    return lo, hi


def sweep_values(
    base_val: float, param: str, pct_range_pct: float, n_points: int,
) -> np.ndarray:
    """Evenly spaced parameter values across the (clamped) sweep range."""
    lo, hi = sweep_range(base_val, param, pct_range_pct)
    return np.linspace(lo, hi, n_points)


def apply_param(
    reservoir: Reservoir,
    fluid: Fluid,
    objectives: DesignObjectives,
    param: str,
    value: float,
) -> tuple[Reservoir, Fluid, DesignObjectives]:
    """Return copies of (reservoir, fluid, objectives) with *param* = *value*.

    Uses ``dataclasses.replace`` and clamps each parameter to its valid domain.
    The reservoir-decline warning is suppressed (a low static pressure is a
    legitimate point of the sweep, not an error).
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        if param == "water_cut":
            fluid = replace(fluid, water_cut=float(np.clip(value, 0.0, 0.99)))
        elif param == "gor":
            fluid = replace(fluid, gor=max(0.0, float(value)))
        elif param == "static_pressure":
            reservoir = replace(reservoir, static_pressure=max(50.0, float(value)))
        elif param == "target_flow_rate":
            objectives = replace(objectives, target_flow_rate=max(10.0, float(value)))
    return reservoir, fluid, objectives


def run_sensitivity(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    catalog,
    param: str,
    *,
    pct_range_pct: float = 40.0,
    n_points: int = DEFAULT_N_POINTS,
    progress: Callable[[int, int, float], None] | None = None,
) -> dict:
    """Sweep *param* and return the optimal-design metrics at each point.

    Args:
        reservoir, fluid, well, surface, objectives: Base domain inputs.
        catalog: Loaded equipment catalog.
        param: Key from ``PARAM_LABELS``.
        pct_range_pct: Sweep half-width around the base value [%].
        n_points: Number of evaluation points.
        progress: Optional ``(index, total, value)`` callback for UI progress.

    Returns:
        dict with ``param``, ``param_label``, ``param_values`` (only feasible
        points), ``metrics`` (HP / Etapas / Eficiencia (%) / TDH (ft) lists,
        aligned with ``param_values``) and ``n_points``. Infeasible points are
        silently skipped.
    """
    values = sweep_values(base_value(reservoir, fluid, objectives, param), param, pct_range_pct, n_points)

    hp_vals: list[float] = []
    stage_vals: list[float] = []
    eff_vals: list[float] = []
    tdh_vals: list[float] = []
    valid_xs: list[float] = []

    for idx, val in enumerate(values):
        if progress is not None:
            progress(idx, n_points, float(val))
        try:
            res_v, flu_v, obj_v = apply_param(reservoir, fluid, objectives, param, val)
            recs = generate_recommendations(
                reservoir=res_v, fluid=flu_v, well=well,
                surface=surface, objectives=obj_v, catalog=catalog, n=1,
            )
            dr = recs["recommendations"][0]["design"]
            hp_vals.append(dr.motor_hp)
            stage_vals.append(float(dr.num_stages))
            eff_vals.append(dr.pump_efficiency * 100.0)
            tdh_vals.append(dr.total_head_required)
            valid_xs.append(float(val))
        except Exception:
            pass  # skip points where no feasible design exists

    return {
        "param":        param,
        "param_label":  PARAM_LABELS[param],
        "param_values": valid_xs,
        "metrics": {
            "HP":             hp_vals,
            "Etapas":         stage_vals,
            "Eficiencia (%)": eff_vals,
            "TDH (ft)":       tdh_vals,
        },
        "n_points": n_points,
    }
