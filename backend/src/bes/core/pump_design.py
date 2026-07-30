"""
Pump selection and staging calculations for BES/ESP design.
Based on: Kermit Brown, "The Technology of Artificial Lift Methods", Vol. 2b, Ch. 4.5.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
from scipy.interpolate import interp1d

from bes.core.models import (
    DesignObjectives,
    Fluid,
    PumpCurve,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)
from bes.core.tdh import _sg_liquid, _sg_max, calculate_tdh

if TYPE_CHECKING:
    from bes.catalogs.loader import CatalogManager


# ---------------------------------------------------------------------------
# Hydraulic Institute viscosity-correction table (Brown Vol. 2b / HI standard)
# Reference viscosities [cSt], correction factors for flow (CQ), head (CH),
# and efficiency (CE) at best-efficiency-point conditions.
# ---------------------------------------------------------------------------
_HI_CST = np.array([1.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0])
_HI_CQ  = np.array([1.00, 1.00, 0.98, 0.97, 0.95,  0.92,  0.88,  0.82])
_HI_CH  = np.array([1.00, 0.99, 0.97, 0.94, 0.89,  0.83,  0.76,  0.67])
_HI_CE  = np.array([1.00, 0.98, 0.95, 0.90, 0.81,  0.72,  0.62,  0.50])


def _interp_curve(pump: PumpCurve, flow_bpd: float, attr: str) -> float:
    """Linear interpolation of one pump-curve attribute at *flow_bpd*."""
    flows = np.array([p.flow_rate for p in pump.points])
    values = np.array([getattr(p, attr) for p in pump.points])
    return float(interp1d(flows, values, kind="linear", bounds_error=True)(flow_bpd))


def calculate_stages(tdh_ft: float, pump: PumpCurve, flow_bpd: float) -> int:
    """Number of pump stages required to develop *tdh_ft* at *flow_bpd*.

    Uses ceiling so the pump always meets or exceeds the required TDH.

    Args:
        tdh_ft: Required total dynamic head [ft].
        pump: PumpCurve instance from the catalog.
        flow_bpd: Operating flow rate [STB/d].

    Returns:
        Stage count (integer ≥ 1).
    """
    head_per_stage = _interp_curve(pump, flow_bpd, "head_per_stage")
    return math.ceil(tdh_ft / head_per_stage)


def calculate_motor_hp(
    pump: PumpCurve,
    stages: int,
    flow_bpd: float,
    sg_fluid: float,
) -> float:
    """Total shaft power required from the ESP motor [hp].

    Catalog hp/stage values are rated for water (SG = 1.0). Multiplying by
    *sg_fluid* converts to the actual produced-fluid power requirement.

    Args:
        pump: PumpCurve instance.
        stages: Number of installed stages.
        flow_bpd: Operating flow rate [STB/d].
        sg_fluid: Produced liquid specific gravity.

    Returns:
        Required shaft power [hp].
    """
    hp_per_stage = _interp_curve(pump, flow_bpd, "hp_per_stage")
    return stages * hp_per_stage * sg_fluid


def check_pump_operating_range(pump: PumpCurve, flow_bpd: float) -> dict:
    """Evaluate whether *flow_bpd* is within the pump's recommended range.

    Returns:
        dict with bool flags ``in_range``, ``near_min``, ``near_max``,
        ``near_bep`` (within ±15 % of BEP), and a string ``recommendation``.
    """
    in_range = pump.min_flow <= flow_bpd <= pump.max_flow
    near_min = flow_bpd < pump.min_flow * 1.10
    near_max = flow_bpd > pump.max_flow * 0.90
    near_bep = abs(flow_bpd - pump.bep_flow) / pump.bep_flow <= 0.15

    if not in_range:
        rec = "Flow outside recommended operating range — select a different pump"
    elif near_bep:
        rec = "Operating near BEP — optimal efficiency"
    elif near_min:
        rec = "Operating near minimum flow — risk of recirculation and gas locking"
    elif near_max:
        rec = "Operating near maximum flow — risk of overload and reduced head"
    else:
        rec = "Operating within acceptable range"

    return {
        "in_range": in_range,
        "near_min": near_min,
        "near_max": near_max,
        "near_bep": near_bep,
        "recommendation": rec,
    }


def apply_viscosity_correction(
    pump: PumpCurve,
    flow: float,
    head: float,
    hp: float,
    viscosity_ssu: float,
) -> dict:
    """Apply Hydraulic Institute viscosity correction to water-based pump data.

    For fluids at or below water viscosity (≤ 20 SSU) all correction factors
    are unity and the input values are returned unchanged.

    SSU → cSt conversion uses ASTM D2161 formulas:
      - SSU < 100 : cSt = 0.226·SSU − 195/SSU
      - SSU ≥ 100 : cSt = 0.220·SSU − 135/SSU

    Args:
        pump: PumpCurve context (not interpolated here; passed for completeness).
        flow: Water-based operating flow [STB/d].
        head: Water-based head per stage [ft/stage].
        hp: Water-based power per stage [hp/stage].
        viscosity_ssu: Kinematic viscosity [Saybolt Universal Seconds].

    Returns:
        dict with ``q_factor``, ``h_factor``, ``e_factor``, ``hp_factor``
        and corrected values ``corrected_flow``, ``corrected_head``,
        ``corrected_hp``.
    """
    if viscosity_ssu <= 20.0:
        return {
            "q_factor": 1.0,
            "h_factor": 1.0,
            "e_factor": 1.0,
            "hp_factor": 1.0,
            "corrected_flow": flow,
            "corrected_head": head,
            "corrected_hp": hp,
        }

    # ASTM D2161 SSU → cSt
    if viscosity_ssu < 100.0:
        cst = 0.226 * viscosity_ssu - 195.0 / viscosity_ssu
    else:
        cst = 0.220 * viscosity_ssu - 135.0 / viscosity_ssu

    cst = float(np.clip(cst, _HI_CST[0], _HI_CST[-1]))

    CQ = float(interp1d(_HI_CST, _HI_CQ, kind="linear")(cst))
    CH = float(interp1d(_HI_CST, _HI_CH, kind="linear")(cst))
    CE = float(interp1d(_HI_CST, _HI_CE, kind="linear")(cst))

    # Power scales as (CQ·CH)/CE because lower efficiency requires more shaft power
    hp_factor = CQ * CH / CE

    return {
        "q_factor": CQ,
        "h_factor": CH,
        "e_factor": CE,
        "hp_factor": hp_factor,
        "corrected_flow": flow * CQ,
        "corrected_head": head * CH,
        "corrected_hp": hp * hp_factor,
    }


def select_housing(
    required_stages: int, housing_options: list[int], max_stages: int
) -> dict:
    """Elige la(s) carcasa(s) estándar que alojan *required_stages*.

    Las carcasas vienen en longitudes discretas (``housing_options``, en
    etapas). Se cubre el número de etapas activas con la menor capacidad total
    posible (mínimo exceso) y, a igualdad, el menor número de carcasas. Las
    etapas que sobran para completar la carcasa son **etapas ciegas (dummy)**.
    Si se necesita más de una carcasa (``required > max_stages``) es un arreglo
    en tándem.

    Returns:
        dict con ``housing_size_stages`` (capacidad total instalada),
        ``dummy_stages`` (= capacidad − activas), ``n_housings`` y
        ``housings`` (lista ``[(capacidad, cantidad)]`` de mayor a menor).
    """
    sizes = sorted({int(h) for h in housing_options if h and h > 0})
    if not sizes or required_stages <= 0:
        return {
            "housing_size_stages": max(required_stages, 0),
            "dummy_stages": 0,
            "n_housings": 1,
            "housings": [(max(required_stages, 0), 1)],
        }
    max_size = sizes[-1]
    cap = required_stages + max_size
    INF = float("inf")
    dp = [INF] * (cap + 1)
    prev = [-1] * (cap + 1)
    dp[0] = 0
    for t in range(1, cap + 1):
        for s in sizes:
            if t - s >= 0 and dp[t - s] + 1 < dp[t]:
                dp[t] = dp[t - s] + 1
                prev[t] = s
    total = next((t for t in range(required_stages, cap + 1) if dp[t] < INF), None)
    if total is None:  # fallback defensivo: apilar la carcasa más grande
        n = math.ceil(required_stages / max_size)
        total = n * max_size
        return {
            "housing_size_stages": total,
            "dummy_stages": total - required_stages,
            "n_housings": n,
            "housings": [(max_size, n)],
        }
    counts: dict[int, int] = {}
    t = total
    while t > 0:
        s = prev[t]
        counts[s] = counts.get(s, 0) + 1
        t -= s
    housings = sorted(counts.items(), key=lambda kv: -kv[0])
    return {
        "housing_size_stages": total,
        "dummy_stages": total - required_stages,
        "n_housings": sum(counts.values()),
        "housings": housings,
    }


def _design_candidate(
    catalog_manager: "CatalogManager",
    pump: PumpCurve,
    objectives: DesignObjectives,
    tdh_ft: float,
    sg: float,
    pip: float,
    tdh_info: dict,
    sg_max: float | None = None,
) -> dict | None:
    """Hydraulic design for one catalog pump at the objectives' target flow.

    Shared by :func:`design_pump_complete` (looped over every casing/flow
    candidate) and :func:`design_pump_by_model` (a single named pump).
    Returns ``None`` if the target flow falls outside the pump's own curve
    data (a hard bound — interpolation cannot extrapolate).

    ``sg`` es el SG de la mezcla → **HP operativo**. ``sg_max`` es el SG del
    fluido más pesado → **HP máximo** (sobre el que se dimensiona el motor);
    si se omite, se toma igual a ``sg``.
    """
    try:
        curve = catalog_manager.interpolate_pump_curve(pump, objectives.target_flow_rate)
    except ValueError:
        return None

    stages = calculate_stages(tdh_ft, pump, objectives.target_flow_rate)
    total_hp = calculate_motor_hp(pump, stages, objectives.target_flow_rate, sg)
    sg_max = sg if sg_max is None else sg_max
    motor_hp_max = calculate_motor_hp(pump, stages, objectives.target_flow_rate, sg_max)
    op_check = check_pump_operating_range(pump, objectives.target_flow_rate)

    warnings: list[str] = []
    # Cuántas bombas iguales en serie (tándem) hacen falta para alojar las etapas.
    # Una sola carcasa se limita a pump.max_stages; en serie se apilan y suman
    # etapas sin cambiar el diseño hidráulico (mismo caudal → mismo head/etapa,
    # HP/etapa, eficiencia y TDH; sólo se reparten las etapas entre carcasas).
    pumps_in_series = max(1, math.ceil(stages / pump.max_stages)) if pump.max_stages else 1
    if stages > pump.max_stages:
        warnings.append(
            f"Required {stages} stages exceeds pump max_stages={pump.max_stages}"
        )
        per_housing = math.ceil(stages / pumps_in_series)
        warnings.append(
            f"Recomendación: instalar {pumps_in_series} bombas {pump.model} en serie "
            f"(tándem) para alcanzar las {stages} etapas requeridas "
            f"(≈{per_housing} etapas por carcasa, dentro del máximo de "
            f"{pump.max_stages}). El diseño hidráulico no cambia: al ir en serie el "
            f"caudal es el mismo, por lo que head/etapa, HP/etapa, eficiencia y TDH "
            f"son idénticos; sólo se reparten las etapas entre las carcasas."
        )
    if not op_check["in_range"]:
        warnings.append("Flow rate outside pump operating range")

    # Selección de carcasa(s) estándar y etapas ciegas (dummy) para completarla.
    housing = select_housing(stages, pump.housing_options, pump.max_stages)
    if housing["dummy_stages"] > 0:
        warnings.append(
            f"Se instalarán {housing['dummy_stages']} etapas ciegas (dummy) para "
            f"completar la(s) carcasa(s) de {housing['housing_size_stages']} etapas "
            f"(activas: {stages})."
        )

    # Verificación de presión sobre la carcasa (housing burst, Brown §4.5451):
    # el peor caso es a caudal cero (shut-in), donde el head por etapa es máximo.
    # Se aproxima el shut-in por el head máximo de la curva de catálogo, se apila
    # por el nº de etapas y se expresa como presión del fluido (psi = ft·SG/2.31).
    shutin_head = max(
        (pt.head_per_stage for pt in pump.points), default=curve["head_per_stage"]
    )
    max_housing_pressure_psi = shutin_head * stages * sg / 2.31
    housing_limit = float(pump.housing_pressure_limit_psi or 0.0)
    housing_pressure_ok = housing_limit <= 0.0 or max_housing_pressure_psi <= housing_limit
    if not housing_pressure_ok:
        warnings.append(
            f"Presión sobre la carcasa ≈{max_housing_pressure_psi:.0f} psi (shut-in) "
            f"supera el límite del housing {housing_limit:.0f} psi. Usar carcasa de "
            f"alta presión o repartir las etapas en tándem."
        )

    return {
        "pump_model": pump.model,
        "pump_manufacturer": pump.manufacturer,
        "pump_od": pump.od,
        "stages": stages,
        "housing_size_stages": housing["housing_size_stages"],
        "dummy_stages": housing["dummy_stages"],
        "n_housings": housing["n_housings"],
        "housings": housing["housings"],
        "max_housing_pressure_psi": max_housing_pressure_psi,
        "housing_pressure_limit_psi": housing_limit,
        "housing_pressure_ok": housing_pressure_ok,
        "tdh_ft": tdh_ft,
        "head_per_stage": curve["head_per_stage"],
        "hp_per_stage": curve["hp_per_stage"],
        "efficiency": curve["efficiency"],
        "total_pump_hp": total_hp,
        "motor_hp_max": motor_hp_max,
        "pip_psi": pip,
        "sg_liquid": sg,
        "operating_check": op_check,
        "tdh_breakdown": tdh_info,
        "warnings": warnings,
    }


def design_pump_complete(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    pump_setting_depth: float,
    catalog_manager: "CatalogManager",
) -> list[dict]:
    """Full ESP pump design workflow: TDH → stage count → HP for every compatible pump.

    Steps:
    1. Calculate PIP via multiphase pressure traverse (Hagedorn-Brown).
    2. Calculate TDH from PIP, well geometry, and surface conditions.
    3. Filter catalog pumps by casing clearance and flow range.
    4. For each candidate: interpolate curve, compute stages + HP, check range.
    5. Return candidates sorted by efficiency (descending).

    Args:
        reservoir: Reservoir properties.
        fluid: Fluid PVT and composition.
        well: Well geometry.
        surface: Surface infrastructure and power supply.
        objectives: Production targets and design constraints.
        pump_setting_depth: Pump intake depth [ft TVD].
        catalog_manager: Loaded equipment catalog.

    Returns:
        List of design-candidate dicts, best efficiency first. Each dict
        contains: ``pump_model``, ``pump_manufacturer``, ``pump_od``,
        ``stages``, ``tdh_ft``, ``head_per_stage``, ``hp_per_stage``,
        ``efficiency``, ``total_pump_hp``, ``pip_psi``, ``sg_liquid``,
        ``operating_check``, ``tdh_breakdown``, ``warnings``.
    """
    from bes.core.multiphase import calculate_pip

    pip = calculate_pip(
        reservoir=reservoir,
        fluid=fluid,
        well=well,
        pump_setting_depth=pump_setting_depth,
        target_rate=objectives.target_flow_rate,
    )

    tdh_info = calculate_tdh(
        reservoir, fluid, well, surface, objectives, pump_setting_depth, pip
    )
    tdh_ft = tdh_info["tdh_ft"]
    sg = _sg_liquid(fluid)
    sg_max = _sg_max(fluid)

    candidates = [
        p for p in catalog_manager.get_pumps_by_casing(well.casing_id)
        if p.min_flow <= objectives.target_flow_rate <= p.max_flow
    ]

    results: list[dict] = []
    for pump in candidates:
        cand = _design_candidate(
            catalog_manager, pump, objectives, tdh_ft, sg, pip, tdh_info, sg_max
        )
        if cand is not None:
            results.append(cand)

    results.sort(key=lambda r: r["efficiency"], reverse=True)
    return results


def design_pump_by_model(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    pump_setting_depth: float,
    catalog_manager: "CatalogManager",
    pump_model: str,
) -> dict:
    """Hydraulic design for exactly one user-chosen catalog pump.

    Unlike :func:`design_pump_complete`, this bypasses the casing/flow-range
    prefilter used for auto-recommendation — the user is deliberately
    overriding the algorithm's choice, so a pump outside the usual
    "recommended range" heuristic is still allowed. The pump's own curve
    data remains a hard bound (raises if the target flow falls outside it),
    and OD-vs-casing clearance is still enforced as a physical constraint.

    Args:
        reservoir: Reservoir properties.
        fluid: Fluid PVT and composition.
        well: Well geometry.
        surface: Surface infrastructure and power supply.
        objectives: Production targets and design constraints.
        pump_setting_depth: Pump intake depth [ft TVD].
        catalog_manager: Loaded equipment catalog.
        pump_model: Catalog model name of the user-chosen pump.

    Returns:
        A single design-candidate dict, same shape as one element of
        :func:`design_pump_complete`'s return list.

    Raises:
        ValueError: If ``pump_model`` is unknown, the pump's OD doesn't fit
            the casing, or the target flow falls outside the pump's curve.
    """
    from bes.core.multiphase import calculate_pip

    pump = next((p for p in catalog_manager.get_all_pumps() if p.model == pump_model), None)
    if pump is None:
        raise ValueError(f"pump_model '{pump_model}' no existe en el catálogo")
    if pump.od >= well.casing_id:
        raise ValueError(
            f"La bomba {pump_model} (OD {pump.od}\") no entra en el casing "
            f"(ID {well.casing_id}\")"
        )

    pip = calculate_pip(
        reservoir=reservoir,
        fluid=fluid,
        well=well,
        pump_setting_depth=pump_setting_depth,
        target_rate=objectives.target_flow_rate,
    )
    tdh_info = calculate_tdh(
        reservoir, fluid, well, surface, objectives, pump_setting_depth, pip
    )
    tdh_ft = tdh_info["tdh_ft"]
    sg = _sg_liquid(fluid)
    sg_max = _sg_max(fluid)

    cand = _design_candidate(
        catalog_manager, pump, objectives, tdh_ft, sg, pip, tdh_info, sg_max
    )
    if cand is None:
        raise ValueError(
            f"El caudal objetivo ({objectives.target_flow_rate:.0f} STB/d) está "
            f"fuera del rango de curva de la bomba {pump_model}"
        )
    return cand
