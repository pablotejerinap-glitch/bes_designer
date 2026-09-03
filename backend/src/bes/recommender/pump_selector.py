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
from bes.core.pump_design import (
    design_pump_by_model,
    design_pump_complete,
    operating_frequency,
)
from bes.core.electrical import electrical_design_complete
from bes.core.gas_handling import (
    GAS_SEPARATOR_BASE_FREQUENCY_HZ,
    GAS_SEPARATOR_HP,
    GAS_VOID_LIMIT_RADIAL,
    SEPARATOR_DEFAULT_EFFICIENCY,
    gas_handler_hp,
    total_intake_rate,
    gas_handler_power_at_frequency,
    select_gas_handling_strategy,
)
from bes.core.tdh import _sg_liquid
from bes.core.pvt import standing_rs, gas_z_factor, gas_bg, standing_bo, water_bw
from bes.recommender.ranking import bep_distance, ranking_key

if TYPE_CHECKING:
    from bes.catalogs.loader import CatalogManager

_BBL_TO_FT3 = 5.615

# Entradas de bombas que NO son de un proveedor comercial. Hoy solo
# «Brown (libro)»: I-300, I-42B y M-34 no salen de un catálogo sino de los
# ejemplos numerados de Kermit Brown Vol. 2b (1980), y son las anclas de
# validación del motor de cálculo. La regla de aparejo único no les aplica
# porque no existe un «motor Brown»: se les arma el aparejo con lo que haya.
#
# **Ya no están en el catálogo de la aplicación** (ago-2026): la app publica
# sólo bombas digitalizadas de catálogos reales, y los datos impresos se
# mudaron a `backend/tests/data/brown_pumps.json`. La excepción sobrevive
# porque los tests de validación contra el libro sí las inyectan, y sin ella
# no podrían armar el aparejo.
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
    # Consumo TOTAL del manejo de gas [hp] y cuántos equipos lo producen. Van
    # separados a propósito: con el consumo publicado por modelo (REDA: 3, 6 o
    # 14 hp) la cantidad ya no se puede despejar dividiendo por una constante.
    gas_handler_hp_total: float = 0.0,
    gas_handler_count: int = 0,
    gas_strategy: dict | None = None,
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
    if gas_strategy:
        if gas_strategy.get("switch_lift_method"):
            warnings.append(gas_strategy["verdict"])
        elif gas_strategy.get("strategy") in ("tandem", "agh"):
            warnings.append(gas_strategy["verdict"])
        warnings.extend(gas_strategy.get("warnings", []))

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
        gas_handler_hp=gas_handler_hp_total,
        # Zona operativa del método de incrementos. Sólo el camino de
        # pozos con gas los trae; el convencional deja 0.0.
        gas_q_representative_bpd=float(
            pump_dict.get("gas_q_representative_bpd") or 0.0),
        gas_q_intake_bpd=float(pump_dict.get("gas_q_intake_bpd") or 0.0),
        gas_q_discharge_bpd=float(pump_dict.get("gas_q_discharge_bpd") or 0.0),
        gas_handler_count=gas_handler_count,
        gas_strategy=str((gas_strategy or {}).get("strategy", "")),
        gas_fraction_at_pump=float((gas_strategy or {}).get("f_pump", 0.0)),
        switch_lift_method=bool((gas_strategy or {}).get("switch_lift_method", False)),
        gas_verdict=str((gas_strategy or {}).get("verdict", "")),
        # La escalera entera, no sólo su resumen: es lo que permite mostrar el
        # panel de manejo de gas también por el camino convencional, con los
        # mismos números y sin recalcular nada. Se copia para que el diseño no
        # comparta estado mutable con el selector.
        gas_feasibility=dict(gas_strategy or {}),
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


#: Fracción de gas libre en la admisión a partir de la cual el aparejo lleva
#: manejador de gas. Estaba escrito como un 0.10 suelto adentro del armado; se
#: nombra para poder decir que NO coincide con el umbral del dominio
#: (``gas_handling.GAS_FRACTION_SEPARATOR_REQUIRED``, que vale 0.05).
_GIP_PARA_SEPARADOR = 0.10


def _select_gas_handler(
    catalog: "CatalogManager",
    well: "WellGeometry",
    objectives: "DesignObjectives",
    gip: float,
) -> dict | None:
    """Elige el manejador de gas, si el pozo lo justifica.

    Se incorpora cuando la fracción de gas libre en la admisión pasa
    :data:`_GIP_PARA_SEPARADOR`.

    **Ojo**: ese 10 % NO es el ``GAS_FRACTION_SEPARATOR_REQUIRED = 0.05`` del
    dominio, que es donde el separador pasa a ser obligatorio. El aparejo lo
    incorpora recién al 10 %, así que entre 5 % y 10 % el veredicto de gas pide
    separador y el aparejo no lo trae. Es una discrepancia heredada, se deja
    documentada en vez de cambiarla en silencio: mover el corte cambiaría el
    motor de todos los pozos de esa franja.

    Args:
        catalog: Catálogo de equipos.
        well: Geometría del pozo — el ID de casing limita el diámetro.
        objectives: Objetivos de diseño — el caudal.
        gip: Fracción de gas libre en la admisión [0-1].

    Returns:
        El manejador elegido, o ``None`` si el pozo no lo necesita o el
        catálogo no tiene uno que entre.
    """
    # Se ofrece un candidato en cuanto el gas pueda llegar a exigirlo: contra el
    # menor entre el criterio del usuario y lo que admite una bomba sin
    # separador (Takács, Fig. 4.25). Quien decide si se instala es la escalera,
    # no esta función — acá sólo se busca en el catálogo.
    if gip <= min(objectives.max_gip, GAS_VOID_LIMIT_RADIAL):
        return None
    # El catálogo declara el rango del separador en caudal TOTAL de mezcla
    # (líquido + gas), no en líquido: por el equipo pasa todo. Ver
    # gas_handling.total_intake_rate.
    return catalog.select_gas_handler(
        flow_bpd=total_intake_rate(objectives.target_flow_rate, gip),
        casing_id_in=well.casing_id,
        prefer_type="vortex",
    )


def _estrategia_de_gas(
    catalog: "CatalogManager",
    well: "WellGeometry",
    objectives: "DesignObjectives",
    gip: float,
    gas_handler: dict | None,
    vent_fraction: float = 0.0,
) -> dict:
    """Cuántos separadores hacen falta, o si hay que cambiar de método.

    Arma el tándem con **tipos distintos** —un rotativo y un vórtex, que es lo
    que indica Takács (pág. 195)— y no con dos iguales apilados: cada tipo
    rinde mejor en un rango distinto de fracción de vacío.

    Si el catálogo no tiene con qué armar el tándem, el escalón simplemente no
    se ofrece y la escalera se detiene donde llegue.
    """
    # El manejador avanzado (AGH) es el cuarto escalón y se busca SIEMPRE, haya
    # o no separador: es la única respuesta que el catálogo REDA ofrece por
    # debajo de 2000 bpd, donde no entra ningún separador de vórtice.
    q_mezcla = total_intake_rate(objectives.target_flow_rate, gip)
    agh = catalog.select_gas_handler(
        flow_bpd=q_mezcla,
        casing_id_in=well.casing_id,
        prefer_type="agh",
        require_separation=False,
    )
    if agh is not None and agh.get("type") != "agh":
        agh = None
    agh_gvf = float(agh["max_gvf"]) if agh and agh.get("max_gvf") else None

    if gas_handler is None:
        estrategia = select_gas_handling_strategy(
            gip, single_efficiency=None, max_gip=objectives.max_gip,
            vent_fraction=vent_fraction,
            agh_max_gvf=agh_gvf,
            agh_model=(agh.get("model") if agh else None),
        )
        estrategia["equipos"] = [agh] if estrategia.get("uses_agh") and agh else []
        return estrategia

    eta_simple = gas_handler.get("max_efficiency") or SEPARATOR_DEFAULT_EFFICIENCY

    # --- El segundo equipo del tándem ---------------------------------------
    #
    # Takács (pág. 195) documenta la mayor capacidad de manejo de gas para un
    # tándem de **tipos distintos**, así que ése es el primer intento. Pero el
    # catálogo no publica el rango de caudal de ningún separador rotativo —REDA
    # los lista sólo en las tablas de armado, con longitud, peso y número de
    # parte—, de modo que ``select_gas_handler`` nunca los puede ofrecer y el
    # escalón de tándem quedaba **inalcanzable**: los pozos de entre 30 y 55 %
    # de gas en la admisión, que son justamente los que lo necesitan, se
    # quedaban sin diseño posible.
    #
    # Por eso el segundo equipo se busca en tres pasos, y el arreglo obtenido
    # se declara en las advertencias del diseño:
    #
    #   1. otro tipo                  -> es lo que documenta la bibliografía
    #   2. mismo tipo, otro modelo    -> extrapolación de la composición
    #   3. el mismo modelo repetido   -> último recurso
    #
    # El día que aparezca una hoja de datos de un rotativo con su rango, el
    # paso 1 resuelve solo y los otros dos dejan de usarse.
    otro_tipo = "rotary" if gas_handler.get("type") == "vortex" else "vortex"
    segundo = catalog.select_gas_handler(
        flow_bpd=q_mezcla,
        casing_id_in=well.casing_id,
        prefer_type=otro_tipo,
    )
    arreglo_tandem = "tipos distintos"
    if segundo is None or segundo.get("model") == gas_handler.get("model"):
        otros = [
            g for g in catalog.get_all_gas_handlers()
            if g.get("type") != "agh"
            and g.get("model") != gas_handler.get("model")
            and g.get("min_flow_bpd") is not None
            and g.get("max_flow_bpd") is not None
            and float(g["min_flow_bpd"]) <= q_mezcla <= float(g["max_flow_bpd"])
            and float(g.get("od_inches") or 0.0) < well.casing_id
        ]
        if otros:
            segundo = otros[0]
            arreglo_tandem = (
                "tipos distintos"
                if segundo.get("type") != gas_handler.get("type")
                else "mismo tipo, modelos distintos"
            )
        else:
            segundo = gas_handler
            arreglo_tandem = "el mismo modelo repetido"

    tandem_etas = [
        eta_simple,
        segundo.get("max_efficiency") or SEPARATOR_DEFAULT_EFFICIENCY,
    ]
    tandem_modelos = [gas_handler.get("model", "?"), segundo.get("model", "?")]
    equipos = [gas_handler, segundo]

    estrategia = select_gas_handling_strategy(
        gip,
        single_efficiency=eta_simple,
        tandem_efficiencies=tandem_etas,
        vent_fraction=vent_fraction,
        max_gip=objectives.max_gip,
        single_model=gas_handler.get("model"),
        tandem_models=tandem_modelos,
        agh_max_gvf=agh_gvf,
        agh_model=(agh.get("model") if agh else None),
    )
    # Los equipos concretos, en el orden en que se apilan. Hacen falta acá
    # afuera porque el consumo lo publica el catálogo POR MODELO: un tándem de
    # un vórtex de 14 hp y un rotativo sin dato no consume "2 × algo".
    #
    # El AGH va ARRIBA del separador, no en su lugar: el catálogo dice que
    # «can also be installed in series above rotary or vortex-type gas
    # separators» (pág. 393). Se recorta después a n_separators + el AGH.
    if estrategia.get("uses_agh") and agh is not None:
        equipos = equipos[: max(0, int(estrategia.get("n_separators", 0)))] + [agh]
    # El arreglo del tándem se declara: la composición de eficiencias en serie
    # está documentada para tipos distintos, y cualquier otro arreglo es una
    # extrapolación que el usuario tiene que poder ver.
    if estrategia.get("strategy") == "tandem" and arreglo_tandem != "tipos distintos":
        estrategia.setdefault("warnings", []).append(
            f"El tándem se armó con {arreglo_tandem} "
            f"({' + '.join(tandem_modelos)}). Takács (Fig. 4.25, pág. 195) "
            f"documenta la mayor capacidad de manejo de gas para un tándem de "
            f"TIPOS DISTINTOS; el catálogo no publica el rango de caudal de "
            f"ningún separador rotativo, así que no hay con qué armarlo. La "
            f"eficiencia compuesta de este arreglo es por lo tanto una "
            f"extrapolación y probablemente optimista: dos equipos que separan "
            f"por el mismo principio no se complementan como dos de principios "
            f"distintos."
        )
    # Sólo se declara si el diseño REALMENTE apila dos equipos: publicar cómo
    # se habría armado un tándem que no se usó hace leer "el mismo modelo
    # repetido" en un pozo que lleva un solo separador.
    # Se mide por CANTIDAD de separadores, no por el nombre del escalón: el
    # escalón "agh" apila el manejador ARRIBA del tándem, así que también lo
    # lleva y también hay que declarar cómo se armó.
    es_tandem = int(estrategia.get("n_separators") or 0) >= 2
    estrategia["arreglo_tandem"] = arreglo_tandem if es_tandem else None
    estrategia["tandem_arrangement"] = arreglo_tandem if es_tandem else None
    estrategia["equipos"] = equipos
    return estrategia


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
    # --- Manejador de gas ---------------------------------------------------
    # Se elige ANTES del diseño eléctrico, y no después, porque el separador va
    # montado en el mismo eje y su consumo lo tiene que mover el mismo motor:
    # si se eligiera el motor primero, quedaría 2 hp corto.
    #
    # La fracción de gas libre en la admisión ya viene calculada de
    # design_pump_complete (se evalúa una sola vez, antes del TDH, porque es la
    # que decide la correlación de fricción). Acá sólo se lee.
    gip = cand.get("free_gas_fraction")
    if gip is None:
        from bes.core.gas_handling import free_gas_fraction_at_intake
        gip = free_gas_fraction_at_intake(fluid, cand["pip_psi"], bottom_temp)

    gas_handler = _select_gas_handler(catalog, well, objectives, gip)

    # --- Escalera de manejo de gas: ninguno → simple → tándem → otro método --
    # Takács (pág. 195, Fig. 4.25): el mayor manejo de gas de la tecnología BES
    # lo da un tándem de separadores de TIPOS DISTINTOS. Si ni con eso el gas
    # en la bomba baja del límite, no hay equipo que lo resuelva y corresponde
    # cambiar de método de levantamiento.
    estrategia_gas = _estrategia_de_gas(catalog, well, objectives, gip, gas_handler)

    # Cuántos separadores lleva el aparejo. **Lo decide la escalera y sólo la
    # escalera.**
    #
    # Antes acá había un piso de 1 cuando ``_select_gas_handler`` devolvía un
    # equipo, con lo que el aparejo podía traer un separador instalado —y
    # consumiendo potencia— mientras el veredicto decía «viable sin separador».
    # Eran dos decisiones con cortes distintos (10 % el armado, ``max_gip`` la
    # escalera) y en pantalla se leían como una contradicción. Ahora
    # ``_select_gas_handler`` sólo **ofrece** un candidato y la escalera decide
    # si se usa, cuántos y de qué tipo.
    n_separadores = int(estrategia_gas.get("n_separators") or 0)

    # Lo que efectivamente cuelga del eje: los separadores recortados a esa
    # cuenta, más el manejador avanzado si la escalera llegó hasta ahí. El AGH
    # se instala ARRIBA del separador, no en su lugar (catálogo REDA, pág. 393).
    equipos_gas = list(estrategia_gas.get("equipos") or [])
    if gas_handler is not None and not equipos_gas:
        equipos_gas = [gas_handler]
    if estrategia_gas.get("uses_agh"):
        separadores = [e for e in equipos_gas if e.get("type") != "agh"]
        agh_eq = [e for e in equipos_gas if e.get("type") == "agh"]
        equipos_gas = separadores[:n_separadores] + agh_eq
    else:
        equipos_gas = equipos_gas[:n_separadores]

    # El consumo escala con la frecuencia al cubo (Takács ec. 4.31): va en el
    # mismo eje que la bomba, así que gira a su misma velocidad. Sin esto un
    # pozo a 50 Hz cargaba al motor con el consumo de 60 Hz.
    #
    # El consumo base sale del CATÁLOGO, modelo por modelo (REDA lo publica a
    # 60 Hz: 3 hp el VGSA D20-60, 6 el S20-90, 14 el S70-150). No es un valor
    # único de aparejo: un tándem suma los dos equipos que efectivamente se
    # apilan, no dos veces el mismo número.
    frecuencia = operating_frequency(surface, objectives)
    separator_hp = sum(
        gas_handler_power_at_frequency(
            gas_handler_hp(eq),
            frecuencia,
            float(eq.get("hp_frequency_hz") or GAS_SEPARATOR_BASE_FREQUENCY_HZ),
        )
        for eq in equipos_gas
    )

    elec = electrical_design_complete(
        # El motor se dimensiona sobre el HP MÁXIMO (fluido más pesado, Brown
        # §4.5325), no sobre el operativo, para que no se sobrecargue durante
        # el arranque/desgasificado o produciendo agua.
        #
        # Más el consumo del separador de gas, si el aparejo lleva uno: el
        # motor mueve la bomba Y el separador.
        motor_hp=cand.get("motor_hp_max", cand["total_pump_hp"]) + separator_hp,
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
        # Si no hubo separador pero sí manejador avanzado, el equipo que se
        # reporta es el AGH: es lo que efectivamente va en la sarta.
        # Sólo se reporta el equipo si el aparejo efectivamente lo lleva. El
        # candidato que devolvió _select_gas_handler no basta: la escalera pudo
        # haber decidido no instalarlo, y publicar su modelo con cero potencia
        # hacía aparecer en la ficha un separador que no está montado.
        gas_handler=(equipos_gas[0] if equipos_gas else None),
        gas_handler_hp_total=separator_hp,
        gas_handler_count=len(equipos_gas),
        gas_strategy=estrategia_gas,
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
