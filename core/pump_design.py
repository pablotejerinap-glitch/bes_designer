"""
Pump selection and staging calculations for BES/ESP design.
Based on: Kermit Brown, "The Technology of Artificial Lift Methods", Vol. 2b, Ch. 4.5.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
from scipy.interpolate import interp1d

from core.models import (
    DesignObjectives,
    Fluid,
    PumpCurve,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)
from core.tdh import _sg_liquid, calculate_tdh

if TYPE_CHECKING:
    from catalogs.loader import CatalogManager


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
    from core.multiphase import calculate_pip

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

    candidates = [
        p for p in catalog_manager.get_pumps_by_casing(well.casing_id)
        if p.min_flow <= objectives.target_flow_rate <= p.max_flow
    ]

    results: list[dict] = []
    for pump in candidates:
        try:
            curve = catalog_manager.interpolate_pump_curve(pump, objectives.target_flow_rate)
        except ValueError:
            continue

        stages = calculate_stages(tdh_ft, pump, objectives.target_flow_rate)
        total_hp = calculate_motor_hp(pump, stages, objectives.target_flow_rate, sg)
        op_check = check_pump_operating_range(pump, objectives.target_flow_rate)

        warnings: list[str] = []
        if stages > pump.max_stages:
            warnings.append(
                f"Required {stages} stages exceeds pump max_stages={pump.max_stages}"
            )
        if not op_check["in_range"]:
            warnings.append("Flow rate outside pump operating range")

        results.append({
            "pump_model": pump.model,
            "pump_manufacturer": pump.manufacturer,
            "pump_od": pump.od,
            "stages": stages,
            "tdh_ft": tdh_ft,
            "head_per_stage": curve["head_per_stage"],
            "hp_per_stage": curve["hp_per_stage"],
            "efficiency": curve["efficiency"],
            "total_pump_hp": total_hp,
            "pip_psi": pip,
            "sg_liquid": sg,
            "operating_check": op_check,
            "tdh_breakdown": tdh_info,
            "warnings": warnings,
        })

    results.sort(key=lambda r: r["efficiency"], reverse=True)
    return results
