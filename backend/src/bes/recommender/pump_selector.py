"""Selector de las N mejores bombas para el motor de recomendación.

Llama a los módulos de diseño que ya existen —el hidráulico
(``core/pump_design.py``) y el eléctrico (``core/electrical.py``)—, ordena
todas las candidatas que califican por criterios estrictos de ingeniería
(distancia al BEP → rendimiento → potencia requerida, ver
``recommender/ranking.py``) y devuelve las mejores N como objetos
``DesignResult``.

**El fabricante no juega ningún papel en el orden.** Sí juega en el armado:
bomba, motor y sello salen del mismo proveedor (ver
``.claude/rules/domain.md``), y si ese proveedor no tiene con qué, la bomba
se descarta y se prueba la siguiente.
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

# Entradas del catálogo de bombas que NO son un proveedor comercial. Hoy solo
# «Brown (libro)»: I-300, I-42B y M-34 no salen de un catálogo sino de los
# ejemplos numerados de Kermit Brown Vol. 2b (1980), y son las anclas de
# validación del motor de cálculo. La regla de aparejo único no les aplica
# porque no existe un «motor Brown»: se les arma el aparejo con lo que haya.
_NO_ES_PROVEEDOR = {"Brown (libro)"}


def _aparejo_manufacturer(pump_manufacturer: str) -> str | None:
    """Fabricante al que hay que atarse para armar el aparejo.

    Devuelve ``None`` —sin restricción— para las bombas que no vienen de un
    proveedor comercial. Para todo el resto devuelve el fabricante de la bomba,
    de modo que motor y sello salgan de ahí y de ningún otro lado.
    """
    return None if pump_manufacturer in _NO_ES_PROVEEDOR else pump_manufacturer


def _resolve_pump_depth(well: "WellGeometry", objectives: "DesignObjectives") -> float:
    """Profundidad de succión: la cargada a mano, o la calculada por margen.

    Si ``well.pump_setting_depth`` viene cargada, manda esa: es una instalación
    existente o un caso del libro, donde la profundidad viene dada. Si no, la
    bomba se asienta ``safety_margin_depth`` por encima del tope de punzados
    (Brown §4.532), con un piso de 100 ft para que un margen absurdo no la
    saque a la superficie.
    """
    if well.pump_setting_depth is not None:
        return float(well.pump_setting_depth)
    return max(well.perforations_top - objectives.safety_margin_depth, 100.0)


def _parse_awg(size_str: str) -> int:
    """Convert cable-size string (e.g. '#4') to an integer AWG number."""
    try:
        return int(size_str.replace("#", "").strip())
    except (ValueError, AttributeError):
        return 4  # conservative fallback


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
    gas_fraction_threshold: float = 0.10,
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
    warnings.extend(elec.get("cable_warnings") or [])
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
        operating_frequency=float(
            pump_dict.get("operating_frequency_hz", surface.frequency)
        ),
        gip_fraction=max(0.0, min(1.0, gip)),
        warnings=warnings,
        formulas=pump_dict.get("formulas", []),
        alternatives=[],
        friction_method=str(pump_dict.get("friction_method", "hazen_williams")),
        gas_fraction_threshold=float(gas_fraction_threshold),
        housing_size_stages=int(pump_dict.get("housing_size_stages", 0)),
        dummy_stages=int(pump_dict.get("dummy_stages", 0)),
        n_housings=int(pump_dict.get("n_housings", 1)),
        max_housing_pressure_psi=float(pump_dict.get("max_housing_pressure_psi", 0.0)),
        housing_pressure_limit_psi=float(pump_dict.get("housing_pressure_limit_psi", 0.0)),
        housing_pressure_ok=bool(pump_dict.get("housing_pressure_ok", True)),
        housing_detail=list(pump_dict.get("housing_detail", [])),
        housing_rationale=str(pump_dict.get("housing_rationale", "")),
        housing_pressure_verified=bool(pump_dict.get("housing_pressure_verified", False)),
        shaft_check=dict(pump_dict.get("shaft_check", {})),
        bearing_check=dict(pump_dict.get("bearing_check", {})),
        bearing_load_lbs=float(pump_dict.get("bearing_load_lbs", 0.0)),
        staging_ceiling=dict(pump_dict.get("staging_ceiling", {})),
        fluid_velocity_ft_s=float(elec.get("fluid_velocity_ft_s", 0.0)),
        cooling_ok=bool(elec.get("cooling_ok", True)),
        motor_hp_max=float(pump_dict.get("motor_hp_max", pump_dict["total_pump_hp"])),
        controller_manufacturer=(elec["controller"]["manufacturer"] if elec.get("controller") else ""),
        controller_model=(elec["controller"]["model"] if elec.get("controller") else ""),
        controller_type=(elec["controller"]["type"] if elec.get("controller") else ""),
        seal_manufacturer=(seal["manufacturer"] if seal else ""),
        seal_model=(seal["model"] if seal else ""),
        seal_type=(seal["type"] if seal else ""),
        # 0.0 significa «no publicada»: ni Wood Group ni REDA imprimen la
        # capacidad de empuje por modelo, la dan en gráficos contra temperatura.
        seal_thrust_capacity_lbs=float(
            (seal or {}).get("thrust_capacity_lbs") or 0.0
        ),
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
    """Elige los N mejores diseños BES, ordenados por criterios de ingeniería.

    Los pasos:

        1. Correr el diseño hidráulico completo para todas las bombas del
           catálogo que entren en el pozo.
        2. Ordenar las candidatas por la clave estricta de ingeniería
           (distancia al BEP → rendimiento → potencia requerida). Sin pesos y
           sin dimensión de proveedor: el fabricante es sólo informativo.
        3. Correr el diseño eléctrico (motor + cable + transformador) para las
           N primeras.
        4. Devolver los resultados como instancias de ``DesignResult``.

    Args:
        reservoir: Propiedades del reservorio.
        fluid: PVT y composición del fluido.
        well: Geometría del pozo.
        surface: Condiciones de superficie y alimentación eléctrica.
        objectives: Objetivos de producción.
        catalog: Catálogo de equipos cargado.
        n: Cantidad máxima de diseños a devolver.

    Returns:
        Lista de ``DesignResult`` en orden de criterios de ingeniería, con la
        más cercana al BEP primero.

    Raises:
        ValueError: Si no se encuentra ninguna bomba que califique.
    """
    pump_setting_depth = _resolve_pump_depth(well, objectives)

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

    # Order all candidates by the strict engineering key:
    # (1) BEP distance asc, (2) efficiency desc, (3) required power asc.
    #
    # La bomba viene con el candidato ya escalada a la frecuencia de operación:
    # el BEP se corre con la frecuencia (Q ∝ N), así que releerla del catálogo
    # ordenaría por el BEP de 60 Hz aunque el pozo corra a 50.
    ranked: list[tuple[tuple, dict, object]] = []
    for cand in pump_candidates:
        pump_obj = cand.get("pump_curve")
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
    bottom_temp = reservoir.reservoir_temp
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


def assemble_design(
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
    """Armado del aparejo a partir de un candidato ya diseñado hidráulicamente.

    Punto de entrada público de :func:`_assemble_design`, para que el camino de
    diseño por incrementos de presión (pozos con gas) use **el mismo** armado
    que el convencional: motor, sello, cable, transformador, VSD, manejador de
    gas y sensor, con la regla de un solo fabricante incluida.
    """
    return _assemble_design(
        cand, pump_obj, well, surface, fluid, objectives, catalog,
        pump_setting_depth, bottom_temp,
    )


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
    """Arma el aparejo completo de una candidata ya diseñada hidráulicamente.

    Hace el diseño eléctrico, elige el manejador de gas y el sensor, y ensambla
    el ``DesignResult``.

    **El aparejo se arma con un solo fabricante** (ver
    ``_aparejo_manufacturer``): bomba, motor y sello del mismo proveedor. El
    cable y los accesorios quedan exentos.

    La comparten :func:`select_top_n_pumps` —que atrapa las fallas por candidata
    y salta a la siguiente mejor alternativa— y :func:`select_pump_by_model`,
    que **deja que la falla se propague**: una bomba elegida a mano no tiene
    candidata de reemplazo que probar, así que corresponde avisar el motivo en
    vez de seguir en silencio.
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
        # NO MEZCLAR FABRICANTES: el motor y el sello tienen que salir del mismo
        # proveedor que la bomba. Si ese proveedor no tiene con qué, la bomba se
        # descarta —select_top_n_pumps la saltea, select_pump_by_model levanta el
        # error— en vez de armar un aparejo mixto en silencio.
        manufacturer=_aparejo_manufacturer(pump_obj.manufacturer),
        bottom_temp_f=bottom_temp,
    )

    # La fracción de gas libre en la admisión ya viene calculada de
    # design_pump_complete (se evalúa una sola vez, antes del TDH, porque es la
    # que decide la correlación de fricción). Acá sólo se lee.
    gip = cand.get("free_gas_fraction")
    if gip is None:
        from bes.core.gas_handling import free_gas_fraction_at_intake
        gip = free_gas_fraction_at_intake(fluid, cand["pip_psi"], bottom_temp)

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
        gas_fraction_threshold=objectives.gas_fraction_pc_threshold,
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
    """Arma el diseño BES completo para UNA bomba elegida por el usuario.

    Hace lo mismo que el armado por candidata de :func:`select_top_n_pumps`
    (diseño eléctrico, manejador de gas, sensor) pero exactamente para la bomba
    pedida, salteando el ordenamiento por completo — es un override manual de la
    elección del motor de recomendación, no una alternativa rankeada.

    Args:
        reservoir: Propiedades del reservorio.
        fluid: PVT y composición del fluido.
        well: Geometría del pozo.
        surface: Condiciones de superficie y alimentación eléctrica.
        objectives: Objetivos de producción.
        catalog: Catálogo de equipos cargado.
        pump_model: Nombre del modelo de catálogo que eligió el usuario.

    Returns:
        Un solo ``DesignResult`` para la bomba pedida.

    Raises:
        ValueError: Si la bomba no existe, no entra en el casing, o el diseño
            no se puede completar en las condiciones pedidas.
    """
    pump_setting_depth = _resolve_pump_depth(well, objectives)

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
        pump_setting_depth, reservoir.reservoir_temp,
    )
