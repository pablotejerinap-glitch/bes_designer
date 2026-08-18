"""Servicio de análisis de sensibilidad.

Responde la pregunta «¿y si me equivoqué en este dato?». Hace variar **un
solo parámetro de entrada** dentro de un rango y muestra cómo responden la
potencia, las etapas, el rendimiento y el TDH del diseño óptimo.

Sirve para saber qué datos hay que medir bien y cuáles no importan tanto: si
mover el corte de agua un 20 % cambia el diseño por completo, ese dato hay
que medirlo; si no lo mueve, alcanza con una estimación.

No lee estado de ningún framework: los objetos del dominio se pasan por
argumento, y un callback opcional ``progress`` permite que una interfaz
muestre el avance sin que esta capa sepa nada de ella.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable
import warnings

import numpy as np

from bes.core.models import (
    DesignObjectives, Fluid, Reservoir, SurfaceConditions, WellGeometry,
)
from bes.recommender.recommendation_engine import generate_recommendations

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
    """Devuelve copias de (reservoir, fluid, objectives) con *param* cambiado.

    Usa ``dataclasses.replace`` y acota cada parámetro a su dominio válido.

    La advertencia de declinación del reservorio se silencia a propósito: una
    presión estática baja es un **punto legítimo del barrido**, no un error.
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
    """Barre un parámetro y devuelve las métricas del diseño óptimo en cada punto.

    Args:
        reservoir, fluid, well, surface, objectives: Entradas base del dominio.
        catalog: Catálogo de equipos cargado.
        param: Clave de ``PARAM_LABELS``, o sea qué parámetro variar.
        pct_range_pct: Semi-ancho del barrido alrededor del valor base [%].
        n_points: Cantidad de puntos a evaluar.
        progress: Callback opcional ``(índice, total, valor)`` para que la
            interfaz muestre el avance.

    Returns:
        dict con ``param``, ``param_label``, ``param_values`` (sólo los puntos
        viables), ``metrics`` (listas de HP / Etapas / Eficiencia (%) / TDH
        (ft), alineadas con ``param_values``) y ``n_points``.

        Los puntos inviables se saltean en silencio: en un barrido amplio es
        normal que algunos extremos no tengan diseño posible.
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
