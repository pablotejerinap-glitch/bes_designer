"""
Top-N pump selector for BES/ESP recommendation engine.

Calls the existing hydraulic (pump_design) and electrical design modules,
orders every qualifying candidate by strict engineering criteria
(BEP distance → efficiency → required power; see recommender/ranking.py),
and returns the best N results as DesignResult objects. The manufacturer
plays no role in the ordering.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from bes.core.models import (
    DesignObjectives,
    DesignResult,
    Fluid,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)
from bes.core.pump_design import design_pump_by_model, design_pump_complete
from bes.core.electrical import electrical_design_complete
from bes.core.tdh import _sg_liquid
from bes.core.pvt import standing_rs, gas_z_factor, gas_bg, standing_bo, water_bw
from bes.recommender.ranking import bep_distance, ranking_key

if TYPE_CHECKING:
    from bes.catalogs.loader import CatalogManager

_BBL_TO_FT3 = 5.615


def _parse_awg(size_str: str) -> int:
    """Convert cable-size string (e.g. '#4') to an integer AWG number."""
    try:
        return int(size_str.replace("#", "").strip())
    except (ValueError, AttributeError):
        return 4  # conservative fallback


def _gip_fraction_at_pip(
    fluid: Fluid,
    pip: float,
    bottom_temp: float,
    pump_setting_depth: float,
    well: "WellGeometry",
) -> float:
    """Estimate free-gas volume fraction at the pump intake pressure."""
    pb = fluid.bubble_point_pressure
    gor = fluid.gor
    wc = fluid.water_cut
    t = bottom_temp

    rs = min(
        standing_rs(pip, t, fluid.oil_api, fluid.gas_sg, pb) if pb > 0 else gor,
        gor,
    )
    free_gas = max(gor - rs, 0.0)

    z = gas_z_factor(pip, t, fluid.gas_sg)
    bg = gas_bg(pip, t, z)
    bo = standing_bo(rs, t, fluid.oil_api, fluid.gas_sg)
    bw = water_bw(pip, t)

    v_oil = (1.0 - wc) * bo
    v_water = wc * bw
    v_gas = (1.0 - wc) * free_gas * bg
    v_total = v_oil + v_water + v_gas

    return v_gas / v_total if v_total > 0.0 else 0.0


def _build_design_result(
    pump_dict: dict,
    pump_obj,
    elec: dict,
    pump_setting_depth: float,
    well: "WellGeometry",
    surface: "SurfaceConditions",
    target_rate: float,
    gip: float,
    gas_handler: dict | None = None,
    sensor: dict | None = None,
) -> DesignResult:
    """Assemble a DesignResult from pump and electrical design dicts."""
    cable_awg = _parse_awg(elec["cable"]["cable_size"])
    system_eff = min(
        pump_dict["efficiency"] * 0.92,   # pump × typical motor efficiency
        0.99,
    )

    seal = elec.get("seal")
    seal_warning = elec.get("seal_warning")
    warnings = list(pump_dict.get("warnings", []))
    if seal_warning:
        warnings.append(seal_warning)
    if elec.get("cooling_warning"):
        warnings.append(elec["cooling_warning"])
    if elec.get("controller_warning"):
        warnings.append(elec["controller_warning"])

    return DesignResult(
        pump_manufacturer=pump_dict["pump_manufacturer"],
        pump_series=pump_obj.series,
        pump_model=pump_dict["pump_model"],
        pump_od=pump_dict["pump_od"],
        num_stages=pump_dict["stages"],
        pump_setting_depth=pump_setting_depth,
        intake_pressure=pump_dict["pip_psi"],
        total_head_required=pump_dict["tdh_ft"],
        head_per_stage=pump_dict["head_per_stage"],
        hp_per_stage=pump_dict["hp_per_stage"],
        pump_efficiency=pump_dict["efficiency"],
        total_pump_hp=pump_dict["total_pump_hp"],
        motor_manufacturer=elec["motor"]["manufacturer"],
        motor_model=elec["motor"]["model"],
        motor_hp=float(elec["motor"]["hp_rating"]),
        motor_voltage=float(elec["motor"]["voltage"]),
        motor_amperage=float(elec["motor"]["amperage"]),
        motor_od=float(elec["motor"]["od_inches"]),
        motor_length=float(elec["motor"]["length_ft"]),
        cable_type=elec["cable"]["cable_type"],
        cable_awg=cable_awg,
        cable_voltage_drop=elec["cable_voltage_drop_v"],
        surface_voltage_required=elec["surface_voltage_v"],
        transformer_kva=float(elec["transformer"]["total_kva"]),
        system_efficiency=system_eff,
        flow_rate_achieved=target_rate,
        operating_frequency=surface.frequency,
        gip_fraction=max(0.0, min(1.0, gip)),
        warnings=warnings,
        alternatives=[],
        housing_size_stages=int(pump_dict.get("housing_size_stages", 0)),
        dummy_stages=int(pump_dict.get("dummy_stages", 0)),
        n_housings=int(pump_dict.get("n_housings", 1)),
        max_housing_pressure_psi=float(pump_dict.get("max_housing_pressure_psi", 0.0)),
        housing_pressure_limit_psi=float(pump_dict.get("housing_pressure_limit_psi", 0.0)),
        housing_pressure_ok=bool(pump_dict.get("housing_pressure_ok", True)),
        fluid_velocity_ft_s=float(elec.get("fluid_velocity_ft_s", 0.0)),
        cooling_ok=bool(elec.get("cooling_ok", True)),
        motor_hp_max=float(pump_dict.get("motor_hp_max", pump_dict["total_pump_hp"])),
        controller_manufacturer=(elec["controller"]["manufacturer"] if elec.get("controller") else ""),
        controller_model=(elec["controller"]["model"] if elec.get("controller") else ""),
        controller_type=(elec["controller"]["type"] if elec.get("controller") else ""),
        seal_manufacturer=(seal["manufacturer"] if seal else ""),
        seal_model=(seal["model"] if seal else ""),
        seal_type=(seal["type"] if seal else ""),
        seal_thrust_capacity_lbs=(float(seal["thrust_capacity_lbs"]) if seal else 0.0),
        axial_thrust_lbs=float(elec.get("axial_thrust_lbs", 0.0)),
        gas_handler_manufacturer=(gas_handler["manufacturer"] if gas_handler else ""),
        gas_handler_model=(gas_handler["model"] if gas_handler else ""),
        gas_handler_type=(gas_handler["type"] if gas_handler else ""),
        gas_handler_efficiency=(
            float(gas_handler["max_efficiency"])
            if gas_handler and gas_handler.get("max_efficiency") else 0.0
        ),
        sensor_manufacturer=(sensor["manufacturer"] if sensor else ""),
        sensor_model=(sensor["model"] if sensor else ""),
    )


def select_top_n_pumps(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    catalog: "CatalogManager",
    n: int = 3,
) -> list[DesignResult]:
    """Select the top N ESP pump designs ordered by engineering criteria.

    Steps:
    1. Run full hydraulic design for all catalog pumps that fit the well.
    2. Order candidates by the strict engineering key (BEP distance →
       efficiency → required power; recommender/ranking.py). No weights,
       no provider dimension — the manufacturer is informational only.
    3. Run electrical design (motor + cable + transformer) for the top N.
    4. Return the results as DesignResult dataclass instances.

    Args:
        reservoir: Reservoir properties.
        fluid: Fluid PVT and composition.
        well: Well geometry.
        surface: Surface conditions and power supply.
        objectives: Production targets.
        catalog: Loaded equipment catalog.
        n: Maximum number of designs to return.

    Returns:
        List of DesignResult objects in engineering-criteria order
        (closest to BEP first).

    Raises:
        ValueError: If no qualifying pumps are found in the catalog.
    """
    # Pump sits safety_margin_depth above the top perforation (Brown §4.532).
    # Floor at 100 ft guards against absurd margins producing a surface pump.
    pump_setting_depth = max(
        well.perforations_top - objectives.safety_margin_depth,
        100.0,
    )

    pump_candidates = design_pump_complete(
        reservoir=reservoir,
        fluid=fluid,
        well=well,
        surface=surface,
        objectives=objectives,
        pump_setting_depth=pump_setting_depth,
        catalog_manager=catalog,
    )

    if not pump_candidates:
        raise ValueError(
            "No qualifying pump candidates found for the given well conditions."
        )

    # Build a lookup from model name → PumpCurve object
    pump_lookup = {p.model: p for p in catalog.get_all_pumps()}

    # Order all candidates by the strict engineering key:
    # (1) BEP distance asc, (2) efficiency desc, (3) required power asc.
    ranked: list[tuple[tuple, dict, object]] = []
    for cand in pump_candidates:
        pump_obj = pump_lookup.get(cand["pump_model"])
        if pump_obj is None:
            continue
        key = ranking_key(
            bep_dist=bep_distance(pump_obj, objectives.target_flow_rate),
            efficiency=cand["efficiency"],
            total_pump_hp=cand["total_pump_hp"],
        )
        ranked.append((key, cand, pump_obj))

    ranked.sort(key=lambda x: x[0])

    # Ensamblar en orden de ranking hasta juntar *n* diseños FACTIBLES. No se
    # trunca a n antes de ensamblar: un candidato mejor rankeado puede no
    # ensamblar (p. ej. su motor sobre HP-máximo exige un cable que no entra en
    # el casing), y en ese caso hay que seguir bajando en el ranking en vez de
    # devolver menos diseños (o ninguno).
    bottom_temp = well.bottom_hole_temp
    results: list[DesignResult] = []

    for _key, cand, pump_obj in ranked:
        if len(results) >= n:
            break
        try:
            dr = _assemble_design(
                cand, pump_obj, well, surface, fluid, objectives, catalog,
                pump_setting_depth, bottom_temp,
            )
        except (ValueError, KeyError, StopIteration, TypeError):
            continue
        results.append(dr)

    return results


def _assemble_design(
    cand: dict,
    pump_obj,
    well: "WellGeometry",
    surface: "SurfaceConditions",
    fluid: "Fluid",
    objectives: "DesignObjectives",
    catalog: "CatalogManager",
    pump_setting_depth: float,
    bottom_temp: float,
) -> DesignResult:
    """Electrical design + gas handler + sensor + ``DesignResult`` assembly
    for one already hydraulically-designed candidate.

    Shared by :func:`select_top_n_pumps` (which catches failures per
    candidate and skips to the next-best alternative) and
    :func:`select_pump_by_model` (which lets failures raise — a manually
    chosen pump has no fallback candidate to try instead).
    """
    elec = electrical_design_complete(
        # El motor se dimensiona sobre el HP MÁXIMO (fluido más pesado, Brown
        # §4.5325), no sobre el operativo, para que no se sobrecargue durante
        # el arranque/desgasificado o produciendo agua.
        motor_hp=cand.get("motor_hp_max", cand["total_pump_hp"]),
        pump_od=cand["pump_od"],
        well=well,
        fluid=fluid,
        catalog_manager=catalog,
        pump_depth=pump_setting_depth,
        tdh_ft=cand["tdh_ft"],
        sg_fluid=_sg_liquid(fluid),
        pump_series=pump_obj.series,
        flow_bpd=objectives.target_flow_rate,
        use_vsd=objectives.use_vsd,
    )

    gip = _gip_fraction_at_pip(
        fluid=fluid,
        pip=cand["pip_psi"],
        bottom_temp=bottom_temp,
        pump_setting_depth=pump_setting_depth,
        well=well,
    )

    # Gas handler recommended only when free gas at intake is non-trivial.
    gas_handler = None
    if gip > 0.10:
        gas_handler = catalog.select_gas_handler(
            flow_bpd=objectives.target_flow_rate,
            casing_id_in=well.casing_id,
            prefer_type="vortex",
        )

    # Downhole sensor: always recommend a model covering well conditions.
    sensor = catalog.select_sensor(
        intake_pressure_psi=cand["pip_psi"],
        bottom_temp_f=bottom_temp,
        motor_voltage=float(elec["motor"]["voltage"]),
    )

    return _build_design_result(
        pump_dict=cand,
        pump_obj=pump_obj,
        elec=elec,
        pump_setting_depth=pump_setting_depth,
        well=well,
        surface=surface,
        target_rate=objectives.target_flow_rate,
        gip=gip,
        gas_handler=gas_handler,
        sensor=sensor,
    )


def select_pump_by_model(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    catalog: "CatalogManager",
    pump_model: str,
) -> DesignResult:
    """Assemble the complete ESP design for one user-chosen catalog pump.

    Mirrors ``select_top_n_pumps``'s per-candidate assembly (electrical
    design, gas handler, sensor selection) but for exactly the requested
    pump, bypassing the ranking entirely — this is a manual override of the
    recommendation engine's choice, not a ranked alternative.

    Args:
        reservoir: Reservoir properties.
        fluid: Fluid PVT and composition.
        well: Well geometry.
        surface: Surface conditions and power supply.
        objectives: Production targets.
        catalog: Loaded equipment catalog.
        pump_model: Catalog model name of the user-chosen pump.

    Returns:
        A single ``DesignResult`` for the requested pump.

    Raises:
        ValueError: If the pump doesn't exist, doesn't fit the casing, or
            the design cannot be completed at the target conditions.
    """
    pump_setting_depth = max(
        well.perforations_top - objectives.safety_margin_depth,
        100.0,
    )

    cand = design_pump_by_model(
        reservoir=reservoir,
        fluid=fluid,
        well=well,
        surface=surface,
        objectives=objectives,
        pump_setting_depth=pump_setting_depth,
        catalog_manager=catalog,
        pump_model=pump_model,
    )
    pump_obj = next(p for p in catalog.get_all_pumps() if p.model == pump_model)

    return _assemble_design(
        cand, pump_obj, well, surface, fluid, objectives, catalog,
        pump_setting_depth, well.bottom_hole_temp,
    )
