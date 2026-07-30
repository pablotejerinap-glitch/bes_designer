"""
TDH (Total Dynamic Head) calculations for BES/ESP pump design.
Based on: Kermit Brown, "The Technology of Artificial Lift Methods", Vol. 2b, Ch. 4.5.
"""
from __future__ import annotations

from bes.core.models import DesignObjectives, Fluid, Reservoir, SurfaceConditions, WellGeometry


def friction_loss_hazen_williams(
    q_bpd: float,
    pipe_id_in: float,
    length_ft: float,
    c_factor: float = 120.0,
) -> float:
    """Hazen-Williams friction head loss in production tubing.

    Args:
        q_bpd: Flow rate [STB/d].
        pipe_id_in: Pipe inner diameter [in].
        length_ft: Pipe length [ft].
        c_factor: H-W roughness coefficient (120 = design steel, 130 = new steel).

    Returns:
        Total friction head loss [ft].
    """
    q_gpm = q_bpd * 42.0 / 1440.0
    return (
        0.2083
        * (100.0 / c_factor) ** 1.852
        * q_gpm ** 1.852
        / pipe_id_in ** 4.8655
        * length_ft / 100.0
    )


def _sg_liquid(fluid: Fluid) -> float:
    """Liquid mixture specific gravity at surface conditions (oil + water)."""
    sg_oil = 141.5 / (131.5 + fluid.oil_api)
    return sg_oil * (1.0 - fluid.water_cut) + fluid.water_sg * fluid.water_cut


def _sg_max(fluid: Fluid) -> float:
    """SG del fluido más pesado (agua o petróleo desgasificado).

    Es el que define el **HP máximo** del motor (Brown §4.5325): durante el
    arranque/desgasificado o produciendo agua antes de estabilizar, la bomba
    puede mover el fluido más pesado, exigiendo la mayor potencia.
    """
    sg_oil = 141.5 / (131.5 + fluid.oil_api)
    return max(fluid.water_sg, sg_oil)


def calculate_tdh(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    pump_depth: float,
    pip: float,
) -> dict:
    """Total Dynamic Head per Brown, Vol. 2b, Section 4.5324.

    TDH = Vertical Lift + Tubing Friction + Wellhead Pressure Head

    - Vertical Lift  = pump_depth − (PIP in ft of fluid head)
    - Tubing Friction = Hazen-Williams loss from pump depth to surface
    - Wellhead Pressure Head = Pwh × 2.31 / SG_liquid

    Args:
        reservoir: Reservoir properties (carried for API symmetry with other calcs).
        fluid: Fluid PVT and composition — provides SG for head conversions.
        well: Well geometry — tubing ID used for friction.
        surface: Surface conditions — wellhead pressure required.
        objectives: Design objectives — target flow rate for friction calculation.
        pump_depth: Pump setting depth [ft TVD].
        pip: Pump intake pressure [psi].

    Returns:
        dict with keys: ``tdh_ft``, ``vertical_lift_ft``, ``tubing_friction_ft``,
        ``wellhead_pressure_head_ft``, ``pip_head_ft``, ``sg_liquid``,
        ``pump_depth_ft``, ``pip_psi``.
    """
    sg = _sg_liquid(fluid)

    pip_head_ft = pip * 2.31 / sg
    vertical_lift = pump_depth - pip_head_ft

    tubing_friction = friction_loss_hazen_williams(
        q_bpd=objectives.target_flow_rate,
        pipe_id_in=well.tubing_id,
        length_ft=pump_depth,
    )

    wellhead_pressure_head = surface.wellhead_pressure_required * 2.31 / sg

    tdh = vertical_lift + tubing_friction + wellhead_pressure_head

    return {
        "tdh_ft": tdh,
        "vertical_lift_ft": vertical_lift,
        "tubing_friction_ft": tubing_friction,
        "wellhead_pressure_head_ft": wellhead_pressure_head,
        "pip_head_ft": pip_head_ft,
        "sg_liquid": sg,
        "pump_depth_ft": pump_depth,
        "pip_psi": pip,
    }
