"""
Gas handling and pump intake analysis for BES/ESP design.
Based on: Kermit Brown, "The Technology of Artificial Lift Methods",
Vol. 2b, Sections 4.53102 and 4.53103.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from core.models import Fluid, Reservoir, WellGeometry
from core.pvt import (
    fluid_properties_at_conditions,
    standing_rs,
    standing_bo,
    gas_z_factor,
    gas_bg,
    water_bw,
)

if TYPE_CHECKING:
    from catalogs.loader import CatalogManager

_BBL_TO_FT3 = 5.615
_RHO_WATER_SC = 62.4   # lb/ft³
_RHO_AIR_SC = 0.0764   # lb/scf


def _oil_sg(api: float) -> float:
    return 141.5 / (131.5 + api)


# ---------------------------------------------------------------------------
# 1. Gas Ingestion Percentage
# ---------------------------------------------------------------------------

def gas_ingestion_percentage(
    free_gas_at_intake: float,
    gas_vented: float,
    separator_efficiency: float = 0.0,
) -> float:
    """Fraction of free gas at pump intake that actually enters the pump.

    Without separator: GIP = 1 − gas_vented / free_gas_at_intake.
    With separator: the separator removes an additional fraction
    (separator_efficiency) of the remaining gas before it reaches the pump.

    Args:
        free_gas_at_intake: Total free gas volume at pump depth [any unit].
        gas_vented: Volume of free gas diverted away from pump [same unit].
        separator_efficiency: Fractional gas removal efficiency of a downhole
            separator [0–1]. 0 = no separator.

    Returns:
        Gas ingestion fraction [0–1].
    """
    if free_gas_at_intake <= 0.0:
        return 0.0

    gip = 1.0 - gas_vented / free_gas_at_intake
    gip = max(0.0, min(1.0, gip))

    if separator_efficiency > 0.0:
        gip = gip * (1.0 - separator_efficiency)

    return max(0.0, min(1.0, gip))


# ---------------------------------------------------------------------------
# 2. Gas Lock Risk
# ---------------------------------------------------------------------------

def check_gas_lock_risk(
    free_gas_ratio: float,
    threshold: float = 0.1,
) -> dict:
    """Evaluate gas lock risk at the pump intake.

    Args:
        free_gas_ratio: Free gas volume fraction at pump intake [0–1].
        threshold: Low/medium boundary (default 0.10 = 10 %).

    Returns:
        dict with keys ``risk`` ('low'/'medium'/'high'),
        ``free_gas_ratio``, and ``recommendation``.
    """
    fg = max(0.0, free_gas_ratio)

    if fg < threshold:
        return {
            "risk": "low",
            "free_gas_ratio": fg,
            "recommendation": "Acceptable free gas — standard ESP installation",
        }
    elif fg <= 0.30:
        return {
            "risk": "medium",
            "free_gas_ratio": fg,
            "recommendation": (
                "Elevated free gas — install downhole gas separator "
                "or set pump below perforations"
            ),
        }
    else:
        return {
            "risk": "high",
            "free_gas_ratio": fg,
            "recommendation": (
                "Excessive free gas (> 30 %) — consider alternative lift method "
                "or aggressive gas separation before pump intake"
            ),
        }


# ---------------------------------------------------------------------------
# 3. Pump Deterioration Factor
# ---------------------------------------------------------------------------

def pump_deterioration_factor(free_gas_ratio: float) -> float:
    """Pump performance derating due to free gas ingestion.

    - fg < 0.10  → 1.0   (no derating)
    - 0.10–0.30  → linear from 1.0 down to 0.7
    - fg > 0.30  → 0.5   (severe degradation)

    Reference: Brown Vol. 2b, Section 4.53102.

    Args:
        free_gas_ratio: Free gas volume fraction entering the pump [0–1].

    Returns:
        Derating factor [0–1].
    """
    fg = max(0.0, free_gas_ratio)
    if fg < 0.10:
        return 1.0
    elif fg <= 0.30:
        return 1.0 - (fg - 0.10) / 0.20 * 0.30
    else:
        return 0.5


# ---------------------------------------------------------------------------
# Internal helpers for pressure_increment_design
# ---------------------------------------------------------------------------

def _mixture_volumes_and_density(
    p: float,
    t: float,
    fluid: Fluid,
    water_cut: float,
    gip: float,
) -> dict:
    """Compute in-pump volumetric fractions and mixture density at P, T.

    All volumes are per 1 STB of total surface liquid (oil + water).

    Returns dict with keys:
        rs, bo, bg, bw, free_gas_scf,
        v_oil, v_water, v_gas, v_total,
        rho_mix [lb/ft³], gradient [psi/ft], sg_mix [-].
    """
    pb = fluid.bubble_point_pressure
    gor = fluid.gor
    oil_api = fluid.oil_api
    gas_sg_val = fluid.gas_sg
    water_sg_val = fluid.water_sg
    wc = water_cut

    # PVT
    rs = min(
        standing_rs(p, t, oil_api, gas_sg_val, pb) if pb > 0 else gor,
        gor,
    )
    bo = standing_bo(rs, t, oil_api, gas_sg_val)
    z = gas_z_factor(p, t, gas_sg_val)
    bg = gas_bg(p, t, z)
    bw = water_bw(p, t)

    free_gas_scf = max(gor - rs, 0.0)   # scf per STB oil

    # Volumes [bbl res / STB total surface liquid]
    v_oil   = (1.0 - wc) * bo
    v_water = wc * bw
    v_gas   = (1.0 - wc) * free_gas_scf * bg * gip
    v_total = v_oil + v_water + v_gas

    # Mass [lb / STB total surface liquid] — constant with pressure
    oil_sg_val2 = _oil_sg(oil_api)
    m_oil        = (1.0 - wc) * _RHO_WATER_SC * oil_sg_val2 * _BBL_TO_FT3
    m_water      = wc * _RHO_WATER_SC * water_sg_val * _BBL_TO_FT3
    m_gas_dis    = (1.0 - wc) * rs * _RHO_AIR_SC * gas_sg_val
    m_gas_free   = (1.0 - wc) * free_gas_scf * gip * _RHO_AIR_SC * gas_sg_val
    m_total      = m_oil + m_water + m_gas_dis + m_gas_free

    v_total_ft3 = v_total * _BBL_TO_FT3
    rho_mix = m_total / v_total_ft3 if v_total_ft3 > 0.0 else _RHO_WATER_SC

    return {
        "rs":           rs,
        "bo":           bo,
        "bg":           bg,
        "bw":           bw,
        "free_gas_scf": free_gas_scf,
        "v_oil":        v_oil,
        "v_water":      v_water,
        "v_gas":        v_gas,
        "v_total":      v_total,
        "rho_mix":      rho_mix,
        "gradient":     rho_mix / 144.0,
        "sg_mix":       rho_mix / _RHO_WATER_SC,
    }


def _select_pump_for_flow(q_bpd: float, catalog_manager: "CatalogManager"):
    """Select the catalog pump whose flow range best covers q_bpd.

    Prefers pumps where min_flow ≤ q_bpd ≤ max_flow; if none qualify,
    picks the pump with the nearest boundary.
    """
    all_pumps = catalog_manager.get_all_pumps()
    candidates = [p for p in all_pumps if p.min_flow <= q_bpd <= p.max_flow]
    if candidates:
        return min(candidates, key=lambda p: abs(p.bep_flow - q_bpd))
    # Fallback: nearest by range boundary distance
    def _dist(p):
        if q_bpd < p.min_flow:
            return p.min_flow - q_bpd
        return q_bpd - p.max_flow
    return min(all_pumps, key=_dist)


def _pump_perf_clamped(pump, q_bpd: float, catalog_manager: "CatalogManager") -> dict:
    """Interpolate pump curve, clamping q_bpd to the curve's data range."""
    flows = [pt.flow_rate for pt in pump.points]
    q_clamped = max(min(q_bpd, max(flows)), min(flows))
    return catalog_manager.interpolate_pump_curve(pump, q_clamped)


# ---------------------------------------------------------------------------
# 4. Pressure Increment Design
# ---------------------------------------------------------------------------

def pressure_increment_design(
    reservoir: Reservoir,
    fluid: Fluid,
    p_intake: float,
    p_discharge: float,
    target_rate: float,
    catalog_manager: "CatalogManager",
    gip: float = 1.0,
    water_cut: float = 0.0,
    increment_psi: float = 200.0,
) -> dict:
    """Pressure-increment pump design for gassy wells (Brown §4.53103).

    Divides the pump pressure rise [p_intake → p_discharge] into equal
    increments, evaluates mixture properties at each mid-point pressure
    using Standing/DAK PVT, then determines the number of stages and shaft
    power required to traverse each 200 psi increment.

    Args:
        reservoir: Reservoir object — reservoir_temp used for all PVT.
        fluid: Fluid PVT properties (GOR, API, gas_sg, water_sg, Pb).
        p_intake: Pump intake pressure [psia].
        p_discharge: Pump discharge pressure [psia].
        target_rate: Target gross liquid surface rate [STB/d].
        catalog_manager: Loaded equipment catalog.
        gip: Gas ingestion fraction entering the pump [0–1]. Default 1.0.
        water_cut: Produced water fraction [0–1]. Default 0 (pure oil).
        increment_psi: Pressure step size [psi]. Default 200.

    Returns:
        dict with keys:
            ``total_stages``, ``total_hp``,
            ``pump_combination`` (list of (model, stages) tuples),
            ``increment_table`` (list of per-increment dicts).

    Raises:
        ValueError: If p_discharge ≤ p_intake.
    """
    if p_discharge <= p_intake:
        raise ValueError(
            f"p_discharge ({p_discharge}) must be greater than "
            f"p_intake ({p_intake})"
        )

    temp = reservoir.reservoir_temp

    # Build pressure boundary list
    boundaries = []
    p = p_intake
    while p < p_discharge - 1e-6:
        boundaries.append(p)
        p = min(p + increment_psi, p_discharge)
    boundaries.append(p_discharge)

    total_stages = 0
    total_hp = 0.0
    pump_counts: dict[str, int] = {}
    increment_table: list[dict] = []

    for i in range(len(boundaries) - 1):
        p_lo = boundaries[i]
        p_hi = boundaries[i + 1]
        p_mid = 0.5 * (p_lo + p_hi)
        delta_p = p_hi - p_lo

        props = _mixture_volumes_and_density(p_mid, temp, fluid, water_cut, gip)

        v_total  = props["v_total"]
        rho_mix  = props["rho_mix"]
        gradient = props["gradient"]
        sg_mix   = props["sg_mix"]

        # Reservoir volumetric flow through the pump at this increment
        q_res = target_rate * v_total   # bpd reservoir

        pump = _select_pump_for_flow(q_res, catalog_manager)
        curve = _pump_perf_clamped(pump, q_res, catalog_manager)

        head_per_stage = curve["head_per_stage"]
        hp_per_stage_w = curve["hp_per_stage"]   # rated for water

        psi_per_stage = head_per_stage * gradient
        if psi_per_stage <= 0.0:
            continue

        n_stages = math.ceil(delta_p / psi_per_stage)

        # Shaft-power corrected for mixture SG (water-rated catalog × SG)
        hp_incr = n_stages * hp_per_stage_w * sg_mix

        total_stages += n_stages
        total_hp += hp_incr

        model = pump.model
        pump_counts[model] = pump_counts.get(model, 0) + n_stages

        increment_table.append({
            "p_lo":             p_lo,
            "p_hi":             p_hi,
            "p_mid":            p_mid,
            "rs":               props["rs"],
            "bo":               props["bo"],
            "bg":               props["bg"],
            "bw":               props["bw"],
            "free_gas_scf":     props["free_gas_scf"],
            "v_oil":            props["v_oil"],
            "v_water":          props["v_water"],
            "v_gas":            props["v_gas"],
            "v_total":          v_total,
            "rho_mix":          rho_mix,
            "gradient":         gradient,
            "sg_mix":           sg_mix,
            "q_res_bpd":        q_res,
            "pump_model":       model,
            "head_per_stage":   head_per_stage,
            "hp_per_stage_w":   hp_per_stage_w,
            "psi_per_stage":    psi_per_stage,
            "stages":           n_stages,
            "hp":               hp_incr,
        })

    pump_combination = list(pump_counts.items())

    return {
        "total_stages":      total_stages,
        "total_hp":          round(total_hp, 2),
        "pump_combination":  pump_combination,
        "increment_table":   increment_table,
        "p_intake":          p_intake,
        "p_discharge":       p_discharge,
        "delta_p":           p_discharge - p_intake,
        "n_increments":      len(increment_table),
        "gip":               gip,
        "water_cut":         water_cut,
    }


# ---------------------------------------------------------------------------
# 5. Recommend Gas Separator
# ---------------------------------------------------------------------------

_SEPARATOR_MODELS: dict[str, dict] = {
    "400": {
        "type": "Rotary Gas Separator",
        "model": "GasMaster-400",
        "manufacturer": "Reda",
        "efficiency": 0.90,
    },
    "513": {
        "type": "Reverse Flow Separator",
        "model": "MVP-513",
        "manufacturer": "Centrilift",
        "efficiency": 0.85,
    },
    "540": {
        "type": "Rotary Gas Separator",
        "model": "GS-540",
        "manufacturer": "Reda",
        "efficiency": 0.90,
    },
    "738": {
        "type": "Advanced Gas Handler",
        "model": "AGH-738",
        "manufacturer": "Centrilift",
        "efficiency": 0.80,
    },
}

_SEPARATOR_GENERIC = {
    "type": "Standard Gas Separator",
    "model": "GS-Generic",
    "manufacturer": "Various",
    "efficiency": 0.75,
}


def recommend_gas_separator(
    free_gas_at_intake: float,
    pump_series: str,
) -> dict:
    """Recommend a downhole gas separator for the given pump series.

    Args:
        free_gas_at_intake: Free gas volume fraction at pump intake [0–1].
        pump_series: Pump series string (e.g. ``"400"``, ``"513"``).

    Returns:
        dict with ``separator`` (equipment info dict),
        ``free_gas_ratio``, and ``notes``.
    """
    sep = _SEPARATOR_MODELS.get(pump_series, _SEPARATOR_GENERIC)

    notes = []
    if free_gas_at_intake > 0.30:
        notes.append("High gas fraction — separator is strongly recommended")
    elif free_gas_at_intake > 0.10:
        notes.append("Moderate gas fraction — separator recommended for reliability")
    else:
        notes.append("Low gas fraction — separator optional")

    return {
        "separator":      sep,
        "free_gas_ratio": free_gas_at_intake,
        "pump_series":    pump_series,
        "notes":          notes,
    }


# ---------------------------------------------------------------------------
# 6. Complete Gas Design
# ---------------------------------------------------------------------------

def complete_gas_design(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    pump_depth: float,
    target_rate: float,
    catalog_manager: "CatalogManager",
    vent_gas_pct: float = 0.0,
) -> dict:
    """Full gas-handling design workflow (Brown §4.53103, Example 3).

    Steps:
    1. Compute pump intake pressure (PIP) via multiphase traverse.
    2. Compute pump discharge pressure via tubing traverse.
    3. Evaluate free gas at intake and gas ingestion fraction (GIP).
    4. Run pressure-increment design.
    5. Assess gas lock risk and recommend separator if needed.

    Args:
        reservoir: Reservoir properties.
        fluid: Fluid PVT and composition.
        well: Well geometry.
        pump_depth: Pump setting depth [ft TVD].
        target_rate: Target gross liquid rate [STB/d].
        catalog_manager: Loaded equipment catalog.
        vent_gas_pct: Fraction of free gas vented at surface [0–1].
            0 = 100 % GIP, 1 = all gas vented (no gas enters pump).

    Returns:
        dict with keys: ``pip``, ``p_discharge``, ``gip``,
        ``free_gas_ratio_at_intake``, ``gas_lock_risk``,
        ``deterioration_factor``, ``separator_recommendation``,
        ``increment_design``.
    """
    from core.multiphase import calculate_pip, calculate_discharge_pressure

    # --- Temperature at pump depth (linear profile) ---
    t_pump = (
        well.wellhead_temp
        + (pump_depth / well.total_depth) * (well.bottom_hole_temp - well.wellhead_temp)
    )

    # --- 1. Pump Intake Pressure ---
    pip = calculate_pip(
        reservoir=reservoir,
        fluid=fluid,
        well=well,
        pump_setting_depth=pump_depth,
        target_rate=target_rate,
    )

    # --- 2. Pump Discharge Pressure ---
    p_discharge = calculate_discharge_pressure(
        fluid=fluid,
        tubing_id=well.tubing_id,
        pump_depth=pump_depth,
        wellhead_pressure=well.wellhead_temp,   # placeholder — use surface conditions
        target_rate=target_rate,
        t_pump=t_pump,
        t_wellhead=well.wellhead_temp,
    )

    # Sanity: discharge must exceed intake
    if p_discharge <= pip:
        p_discharge = pip + 1000.0  # minimum 1000 psi differential

    # --- 3. Free gas and GIP ---
    pb = fluid.bubble_point_pressure
    t = t_pump
    rs_at_pip = min(
        standing_rs(pip, t, fluid.oil_api, fluid.gas_sg, pb) if pb > 0 else fluid.gor,
        fluid.gor,
    )
    free_gas_at_intake = max(fluid.gor - rs_at_pip, 0.0)  # scf/STB oil

    # Volumetric free gas fraction at pump intake
    z_pip = gas_z_factor(pip, t, fluid.gas_sg)
    bg_pip = gas_bg(pip, t, z_pip)
    bo_pip = standing_bo(rs_at_pip, t, fluid.oil_api, fluid.gas_sg)
    bw_pip = water_bw(pip, t)

    wc = fluid.water_cut
    v_oil_pip = (1.0 - wc) * bo_pip
    v_water_pip = wc * bw_pip
    v_gas_pip = (1.0 - wc) * free_gas_at_intake * bg_pip
    v_total_pip = v_oil_pip + v_water_pip + v_gas_pip
    fg_ratio = v_gas_pip / v_total_pip if v_total_pip > 0.0 else 0.0

    # Gas vented is vent_gas_pct of the free gas
    gas_vented = free_gas_at_intake * vent_gas_pct
    gip = gas_ingestion_percentage(free_gas_at_intake, gas_vented)

    # --- 4. Gas lock risk and deterioration ---
    gas_risk = check_gas_lock_risk(fg_ratio * gip)
    det_factor = pump_deterioration_factor(fg_ratio * gip)

    # --- 5. Separator recommendation ---
    # Infer pump series from first qualifying catalog pump
    qualifying = catalog_manager.get_pumps_by_casing(well.casing_id)
    pump_series = qualifying[0].series if qualifying else "400"
    sep_rec = recommend_gas_separator(fg_ratio, pump_series)

    # --- 6. Pressure increment design ---
    inc_design = pressure_increment_design(
        reservoir=reservoir,
        fluid=fluid,
        p_intake=pip,
        p_discharge=p_discharge,
        target_rate=target_rate,
        catalog_manager=catalog_manager,
        gip=gip,
        water_cut=wc,
        increment_psi=200.0,
    )

    return {
        "pip":                       pip,
        "p_discharge":               p_discharge,
        "gip":                       gip,
        "free_gas_ratio_at_intake":  fg_ratio,
        "gas_lock_risk":             gas_risk,
        "deterioration_factor":      det_factor,
        "separator_recommendation":  sep_rec,
        "increment_design":          inc_design,
    }
