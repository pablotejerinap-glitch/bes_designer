"""
Pump selection and staging calculations for BES/ESP design.
Based on: Kermit Brown, "The Technology of Artificial Lift Methods", Vol. 2b, Ch. 4.5.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
from scipy.interpolate import interp1d

from bes.core import mechanical
from bes.core.housing import optimize_housings
from bes.core.models import (
    DesignObjectives,
    Fluid,
    PumpCurve,
    PumpHousing,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)
from bes.core.tdh import _sg_liquid, _sg_max, calculate_tdh, temp_at_depth

if TYPE_CHECKING:
    from bes.catalogs.loader import CatalogManager


#: Tolerancia para aceptar la viscosidad medida del crudo [°F].
#:
#: ``Fluid.oil_viscosity_dead`` viene medida a ``Fluid.viscosity_temp_ref``, que
#: no tiene por qué ser la temperatura de admisión. La viscosidad es exponencial
#: con la temperatura, así que usar un valor medido a otra temperatura como si
#: fuera el de admisión mete un error grande. Dentro de esta tolerancia se
#: acepta el dato; fuera, se lee la Fig. 4L(2) del libro a la temperatura de
#: admisión y se avisa.
VISCOSITY_TEMP_TOLERANCE_F = 5.0


def _viscosity_context(
    fluid: Fluid,
    well: WellGeometry,
    pump_setting_depth: float,
    bottom_temp_f: float,
) -> dict:
    """Viscosidad del crudo en la **admisión de la bomba** (Riling, pasos 2 a 5).

    Es una propiedad del pozo y del fluido, no de la bomba que se está
    probando, así que se evalúa **una sola vez** por diseño —igual que la
    fracción de gas— y viaja con todos los candidatos. Recalcularla por bomba
    sería trabajo de más y una oportunidad para que los candidatos no coincidan.

    **La temperatura es la de la admisión, no la de reservorio.** El paso 2 del
    procedimiento dice «a temperatura de reservorio», pero el encabezado de las
    Tablas 4.520 / 4.521 dice *«at pumping temperatures»*, y son cosas distintas:
    el fluido se enfría subiendo, y la viscosidad es exponencial con la
    temperatura. Se toma la del perfil geotérmico a la profundidad de la bomba,
    que es donde el fluido efectivamente entra — más conservador que reservorio.

    Args:
        fluid: Fluido producido.
        well: Geometría del pozo.
        pump_setting_depth: Profundidad de la admisión [ft].
        bottom_temp_f: Temperatura de fondo [°F] — ``reservoir.reservoir_temp``.

    Returns:
        Lo que devuelve :func:`bes.core.viscosity.evaluate_viscosity`, más
        ``intake_temp_f``. Con crudo liviano (≥ 28 °API) devuelve factores
        unitarios y ``is_viscous = False``.
    """
    from bes.core.viscosity import evaluate_viscosity

    t_intake = temp_at_depth(well, pump_setting_depth, bottom_temp_f)

    # El dato medido gana sobre la correlación, pero sólo si está a la
    # temperatura correcta. Fuera de la tolerancia no se usa: extrapolarlo
    # sería inventar.
    dead_oil_cp = None
    aviso_temp = None
    if fluid.oil_viscosity_dead and fluid.oil_viscosity_dead > 0:
        delta = abs(fluid.viscosity_temp_ref - t_intake)
        if delta <= VISCOSITY_TEMP_TOLERANCE_F:
            dead_oil_cp = fluid.oil_viscosity_dead
        else:
            aviso_temp = (
                f"La viscosidad medida ({fluid.oil_viscosity_dead:.1f} cp) está "
                f"referida a {fluid.viscosity_temp_ref:.0f} °F y la admisión de la "
                f"bomba está a {t_intake:.0f} °F ({delta:.0f} °F de diferencia). "
                f"No se usa el dato medido —la viscosidad varía exponencialmente "
                f"con la temperatura— y se lee la Fig. 4L(2) del libro a "
                f"{t_intake:.0f} °F. Para usar el dato, medirlo a temperatura "
                f"de admisión."
            )

    resultado = evaluate_viscosity(
        oil_api=fluid.oil_api,
        temp_f=t_intake,
        rs_scf_bbl=fluid.gor,
        # El rendimiento entra por bomba en _design_candidate; acá se pide el
        # de la tabla de 70 % sólo para poblar el diagnóstico del pozo.
        pump_efficiency_pct=70.0,
        dead_oil_cp=dead_oil_cp,
    )
    resultado["intake_temp_f"] = t_intake
    if aviso_temp:
        resultado["warnings"] = [aviso_temp, *resultado.get("warnings", [])]
    return resultado


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


def operating_frequency(
    surface: SurfaceConditions, objectives: DesignObjectives
) -> float:
    """Frequency the pump will actually run at [Hz].

    A fixed switchboard runs the pump at line frequency; a variable-speed drive
    does not, so ``DesignObjectives.design_frequency_hz`` overrides it when a
    VSD is part of the design. Everything hydraulic — the flow range, the head
    per stage, the power per stage — is evaluated at this frequency.

    Args:
        surface: Surface conditions, providing the grid frequency.
        objectives: Design objectives, providing the optional VSD frequency.

    Returns:
        Operating frequency [Hz].
    """
    return objectives.design_frequency_hz or surface.frequency


def select_housing(
    required_stages: int, housing_options: list[int], max_stages: int
) -> dict:
    """Elige la(s) carcasa(s) estándar que alojan *required_stages*.

    Envoltorio de conveniencia sobre
    :func:`bes.core.housing.optimize_housings` para quien solo tiene las
    longitudes disponibles (lista de etapas) y no necesita la verificación de
    presión: acá no hay dato de presión, así que la restricción no se aplica y
    el resultado es puramente geométrico.

    El flujo de diseño **no** usa esta función: llama directamente al
    optimizador para poder pasarle el head de shut-in y el límite de la
    carcasa, que es lo que convierte la presión en restricción dura.

    Args:
        required_stages: Etapas activas a alojar.
        housing_options: Longitudes disponibles, en etapas.
        max_stages: Máximo de etapas por carcasa (informativo; el óptimo ya
            respeta las longitudes del catálogo).

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
    selection = optimize_housings(
        required_stages=required_stages,
        housings=[PumpHousing(stages=s) for s in sizes],
        shutin_head_per_stage=0.0,     # sin dato de head → sin chequeo de presión
        sg_fluid=0.0,
        pump_pressure_limit_psi=0.0,
    )
    assert selection is not None      # sin límite de presión siempre hay solución
    return {
        "housing_size_stages": selection["housing_size_stages"],
        "dummy_stages": selection["dummy_stages"],
        "n_housings": selection["n_housings"],
        "housings": selection["housings"],
    }


def _pump_max_efficiency_pct(pump: PumpCurve) -> float:
    """Rendimiento máximo de catálogo de la bomba, **en porcentaje**.

    El dominio guarda el rendimiento como **fracción** en [0, 1]
    (``PumpPerformancePoint.efficiency``), pero las Tablas 4.520 / 4.521 se
    indexan por porcentaje —son «la tabla del 60 %» y «la del 70 %»—. Esta
    función es el único lugar donde se hace la conversión, para que la unidad
    no se cruce en silencio: pasar 0.7 donde va 70 hace que la tabla se acote
    al extremo y devuelva factores que parecen razonables pero no lo son.
    """
    return max((pt.efficiency for pt in pump.points), default=0.0) * 100.0


def _design_flow_for(
    pump: PumpCurve,
    objectives: DesignObjectives,
    viscosity: dict | None,
) -> float:
    """Caudal contra el que se busca esta bomba en su curva de agua [STB/d].

    Con crudo liviano es el caudal pedido. Con crudo pesado es el equivalente
    en agua ``Q_pedido / C_Q``, que es mayor: la bomba entrega menos caudal con
    el crudo que con agua, así que hay que ir a buscarla más arriba en su curva.

    El factor depende del rendimiento máximo de catálogo de **esta** bomba
    —es lo que decide entre la Tabla 4.520 y la 4.521—, así que el equivalente
    es distinto para cada candidata.
    """
    if viscosity is None or not viscosity.get("is_viscous"):
        return objectives.target_flow_rate

    from bes.core.viscosity import viscosity_factors

    eff_max = _pump_max_efficiency_pct(pump)
    if eff_max <= 0:
        return objectives.target_flow_rate

    cq = viscosity_factors(viscosity["design_ssu"], eff_max)["capacity_factor"] / 100.0
    return objectives.target_flow_rate / cq if cq > 0 else objectives.target_flow_rate


def housing_and_mechanical_checks(
    catalog_manager: "CatalogManager",
    pump: PumpCurve,
    stages: int,
    sg: float,
    hp_per_stage: float,
    head_per_stage: float,
    vertical_lift_ft: float,
    bottom_temp_f: float,
    warnings: list[str],
    strict: bool = False,
) -> dict | None:
    """Carcasas + verificación mecánica para una bomba con un conteo de etapas.

    Es la parte del diseño que **no depende de cómo se contaron las etapas**:
    una vez que se sabe qué bomba y cuántas etapas, la optimización de carcasas
    y las verificaciones de eje y cojinete son las mismas venga el conteo del
    TDH convencional o del método por incrementos de presión. Por eso vive acá
    afuera y la llaman los dos caminos — no hay una segunda implementación.

    Devuelve ``None`` cuando la bomba no se puede armar (ninguna combinación de
    carcasas aguanta la presión, o el eje/cojinete no dan), que es la señal de
    «probá la siguiente». Con ``strict=True`` levanta ``ValueError`` explicando
    el motivo, para cuando el usuario eligió la bomba a mano.

    Args:
        catalog_manager: Catálogo cargado (aporta la ficha de la serie).
        pump: Bomba, **ya escalada a la frecuencia de operación**.
        stages: Etapas activas requeridas.
        sg: Gravedad específica de la mezcla (Pem).
        hp_per_stage: HP por etapa de la curva, calibrado para agua.
        head_per_stage: Altura por etapa en el punto de operación [ft].
        vertical_lift_ft: Elevación hasta boca de pozo, Ho [ft], para la carga
            axial sobre el cojinete.
        bottom_temp_f: Temperatura de fondo [°F] — ata el tope de etapas.
        warnings: Lista de avisos, **se modifica in situ**.
        strict: Levantar en vez de devolver ``None``.

    Returns:
        dict con las claves de carcasa (``housing_*``, ``dummy_stages``,
        ``n_housings``, ``max_housing_pressure_psi``) y las mecánicas
        (``shaft_check``, ``bearing_check``, ``bearing_load_lbs``,
        ``staging_ceiling``), listo para volcar en el candidato. O ``None``.

    Raises:
        ValueError: Sólo con ``strict=True``.
    """
    # Cuántas bombas iguales en serie (tándem) hacen falta para alojar las etapas.
    # Una sola carcasa se limita a pump.max_stages; en serie se apilan y suman
    # etapas sin cambiar el diseño hidráulico (mismo caudal → mismo head/etapa,
    # HP/etapa, eficiencia y TDH; sólo se reparten las etapas entre carcasas).
    pumps_in_series = max(1, math.ceil(stages / pump.max_stages)) if pump.max_stages else 1
    if pump.max_stages and stages > pump.max_stages:
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

    # Optimización automática de carcasas (bes.core.housing). La verificación de
    # presión (housing burst, Brown §4.5451) es restricción DURA dentro de la
    # búsqueda: el peor caso es a caudal cero (shut-in), donde el head por etapa
    # es máximo, y se aproxima por el head máximo de la curva de catálogo.
    shutin_head = max(
        (pt.head_per_stage for pt in pump.points), default=head_per_stage
    )
    housing_limit = float(pump.housing_pressure_limit_psi or 0.0)
    housing = optimize_housings(
        required_stages=stages,
        housings=pump.housings,
        shutin_head_per_stage=shutin_head,
        sg_fluid=sg,
        pump_pressure_limit_psi=housing_limit,
    )
    if housing is None:
        msg = (
            f"Ninguna combinación de carcasas de la bomba {pump.model} aloja las "
            f"{stages} etapas sin superar la presión admisible "
            f"({housing_limit:.0f} psi) a caudal cero."
        )
        if strict:
            raise ValueError(msg)
        return None

    if housing["dummy_stages"] > 0:
        warnings.append(
            f"Se instalarán {housing['dummy_stages']} etapas ciegas (dummy) para "
            f"completar la(s) carcasa(s) de {housing['housing_size_stages']} etapas "
            f"(activas: {stages})."
        )
    if not housing["pressure_verified"]:
        warnings.append(
            f"El catálogo no publica la presión admisible de la carcasa de "
            f"{pump.model}: la verificación de presión no pudo realizarse."
        )

    # --- Verificación mecánica: eje y cojinete (bes.core.mechanical) ---
    # Los datos son de la SERIE, no del modelo. Una serie sin ficha en el
    # catálogo deja las verificaciones sin realizar, nunca aprobadas.
    series = catalog_manager.get_pump_series(pump.series)
    frequency = float(pump.catalog_frequency_hz or 60.0)

    hp_shaft = mechanical.shaft_power(hp_per_stage, stages, sg)
    shaft_check = mechanical.verify_shaft(hp_shaft, series, frequency)
    if not shaft_check["ok"]:
        if strict:
            raise ValueError(f"{pump.model}: {shaft_check['note']}")
        return None
    if shaft_check["shaft_type"] == "high_strength":
        warnings.append(shaft_check["note"])
    elif not shaft_check["verified"]:
        warnings.append(shaft_check["note"])

    bearing_check = mechanical.verify_bearing_staging(
        stages, bottom_temp_f, series
    )
    if not bearing_check["ok"]:
        if strict:
            raise ValueError(f"{pump.model}: {bearing_check['note']}")
        return None
    if bearing_check["bearing_type"] == "high_load":
        warnings.append(bearing_check["note"])
    elif not bearing_check["verified"]:
        warnings.append(bearing_check["note"])

    # Carga axial sobre el cojinete de la sección sellante (cátedra pág. 140):
    # Ho es la elevación que la bomba levanta hasta boca de pozo.
    area = mechanical.shaft_area_in2(series) if series else 0.0
    bearing_load = mechanical.bearing_load_tl(vertical_lift_ft, sg, area)

    ceilings = mechanical.staging_ceiling(
        hp_per_stage=hp_per_stage,
        shutin_head_per_stage=shutin_head,
        pem=sg,
        bottom_hole_temp_f=bottom_temp_f,
        housing_limit_psi=housing_limit,
        series=series,
        frequency_hz=frequency,
    )

    return {
        "housing_size_stages": housing["housing_size_stages"],
        "dummy_stages": housing["dummy_stages"],
        "n_housings": housing["n_housings"],
        "housings": housing["housings"],
        "max_housing_pressure_psi": housing["max_housing_pressure_psi"],
        "housing_pressure_limit_psi": housing["housing_pressure_limit_psi"],
        "housing_pressure_ok": housing["pressure_ok"],
        "housing_detail": housing["detail"],
        "housing_rationale": housing["rationale"],
        "housing_pressure_verified": housing["pressure_verified"],
        "shaft_check": shaft_check,
        "bearing_check": bearing_check,
        "bearing_load_lbs": bearing_load,
        "staging_ceiling": ceilings,
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
    strict: bool = False,
    bottom_temp_f: float = 0.0,
    viscosity: dict | None = None,
    extra_warnings: list[str] | None = None,
) -> dict | None:
    """Hydraulic design for one catalog pump at the objectives' target flow.

    Shared by :func:`design_pump_complete` (looped over every casing/flow
    candidate) and :func:`design_pump_by_model` (a single named pump).
    Returns ``None`` when the pump cannot be designed for this well, which
    happens for two reasons:

    - the target flow falls outside the pump's own curve data (a hard bound —
      interpolation cannot extrapolate);
    - no arrangement of the pump's housings keeps every housing within its
      burst-pressure rating (:func:`bes.core.housing.optimize_housings`).

    ``strict=True`` raises a descriptive ``ValueError`` instead of returning
    ``None``. The auto-recommendation path wants a silent skip — an unsuitable
    pump is simply not offered — whereas a user who named a pump deserves to
    be told *why* it does not work.

    ``sg`` es el SG de la mezcla → **HP operativo**. ``sg_max`` es el SG del
    fluido más pesado → **HP máximo** (sobre el que se dimensiona el motor);
    si se omite, se toma igual a ``sg``.

    Corrección por viscosidad
    -------------------------
    ``viscosity`` es lo que devuelve :func:`_viscosity_context`. Con crudo
    liviano no cambia nada. Con crudo pesado (< 28 °API) **toda la bomba se
    diseña contra su curva de agua en el punto equivalente**::

        Q_agua = Q_pedido / C_Q        H_agua = TDH_pedido / C_H

    Es decir: para entregar lo que el pozo pide moviendo el crudo, la bomba
    tiene que dar *más* con agua. Se divide, no se multiplica — multiplicar es
    el error clásico y subdimensiona el equipo.

    Los factores dependen del **rendimiento máximo de catálogo de esta bomba**,
    que es lo que las Tablas 4.520 / 4.521 usan para elegir entre la de 60 % y
    la de 70 %. Ese rendimiento es un dato de la bomba, no del punto de
    operación, así que se conoce de entrada: la corrección **no necesita
    iterarse**, cierra en una pasada. Ver ``docs/CRUDOS_VISCOSOS.md`` §12.
    """
    q_design = objectives.target_flow_rate
    h_design = tdh_ft
    visc_detail: dict | None = None

    if viscosity is not None and viscosity.get("is_viscous"):
        from bes.core.viscosity import viscosity_factors, water_equivalent_duty

        # Rendimiento MÁXIMO de catálogo: es lo que define de qué tabla se lee
        # («pumps of 60 % / 70 % maximum efficiency»), no el rendimiento del
        # punto de operación.
        eff_max = _pump_max_efficiency_pct(pump)
        if eff_max <= 0:
            if strict:
                raise ValueError(
                    f"La bomba {pump.model} no publica rendimiento en su curva, "
                    f"así que no se puede entrar a las tablas de corrección por "
                    f"viscosidad."
                )
            return None

        factors = viscosity_factors(viscosity["design_ssu"], eff_max)
        duty = water_equivalent_duty(q_design, h_design, factors, sg)
        q_design = duty["q_water"]
        h_design = duty["h_water"]
        visc_detail = {
            **duty,
            "pump_max_efficiency_pct": eff_max,
            "design_ssu": viscosity["design_ssu"],
            "intake_temp_f": viscosity.get("intake_temp_f"),
            "q_required": objectives.target_flow_rate,
            "h_required": tdh_ft,
            "water_cut_correction": viscosity.get("water_cut_correction"),
            # De-duplicado conservando el orden: el contexto del pozo ya corrió
            # las tablas con un rendimiento genérico para el diagnóstico, así que
            # los avisos de rango de viscosidad vienen repetidos.
            "warnings": list(dict.fromkeys(
                [*viscosity.get("warnings", []), *factors["warnings"]]
            )),
        }

    try:
        curve = catalog_manager.interpolate_pump_curve(pump, q_design)
    except ValueError:
        if strict:
            detalle = (
                f" (equivalente en agua del caudal pedido de "
                f"{objectives.target_flow_rate:.0f} STB/d con crudo viscoso)"
                if visc_detail else ""
            )
            raise ValueError(
                f"El caudal de diseño ({q_design:.0f} STB/d){detalle} está "
                f"fuera del rango de curva de la bomba {pump.model}"
            ) from None
        return None

    # Traza de fórmulas del diseño. Arranca con las del TDH —que ya se
    # calcularon en el paso anterior— para que quede la secuencia completa,
    # desde el SG del fluido hasta la potencia al eje, en orden de ejecución.
    from bes.core.formulas import Formula, FormulaTrace
    trace = FormulaTrace()
    for f in (tdh_info or {}).get("formulas", []):
        trace.items.append(Formula(**f))

    # --- Corrección por viscosidad: la traza, antes de usar los valores -----
    if visc_detail is not None:
        trace.add(
            "visc_q_water", "Caudal equivalente en agua",
            "Q_agua = Q_pedido / C_Q",
            {"Q_pedido": visc_detail["q_required"],
             "C_Q": visc_detail["capacity_factor"] / 100.0},
            visc_detail["q_water"], "STB/d", "Brown Vol. 2b §4.53112 (Riling), Tabla 4.52x",
            note=f"El crudo es de {viscosity['oil_api']:.1f} °API y en la admisión "
                 f"({visc_detail['intake_temp_f']:.0f} °F) da "
                 f"{visc_detail['design_ssu']:.0f} SSU. La bomba entrega sólo el "
                 f"{visc_detail['capacity_factor']:.1f} % de su caudal de agua, así "
                 f"que hay que buscarla contra un caudal MAYOR. Se divide, no se "
                 f"multiplica. El factor sale de la tabla de {visc_detail['pump_max_efficiency_pct']:.0f} % "
                 f"de rendimiento máximo, que es el de esta bomba.",
        )
        trace.add(
            "visc_h_water", "Altura equivalente en agua",
            "H_agua = TDH_pedido / C_H",
            {"TDH_pedido": visc_detail["h_required"],
             "C_H": visc_detail["head_factor"] / 100.0},
            visc_detail["h_water"], "ft", "Brown Vol. 2b §4.53112 (Riling), Tabla 4.52x",
            note="Mismo criterio que el caudal: la bomba desarrolla menos altura con "
                 "el crudo que con agua, así que se la busca contra una altura mayor.",
        )

    stages = calculate_stages(h_design, pump, q_design)
    trace.add(
        "stages", "Cantidad de etapas",
        "N = TDH / H_etapa",
        {"TDH": h_design, "H_etapa": curve["head_per_stage"]},
        stages, "etapas", "Brown Vol. 2b §4.5325",
        note=f"H_etapa se interpola de la curva de catálogo de la {pump.model} "
             f"al caudal de diseño ({q_design:,.0f} STB/d). "
             f"El resultado se redondea hacia arriba: no se instalan fracciones."
             + ("" if visc_detail is None else
                " Con crudo viscoso el TDH y el caudal que entran acá son los "
                "EQUIVALENTES EN AGUA, porque la curva de catálogo es de agua."),
    )

    total_hp = calculate_motor_hp(pump, stages, q_design, sg)
    trace.add(
        "shaft_hp", "Potencia al eje de la bomba",
        "HP = N · HP_etapa · SG",
        {"N": stages, "HP_etapa": curve["hp_per_stage"], "SG": sg},
        total_hp, "hp", "Brown Vol. 2b §4.5325",
        note="HP_etapa del catálogo está calibrada para agua (SG = 1); "
             "multiplicar por el SG del fluido da la potencia real.",
    )
    sg_max = sg if sg_max is None else sg_max
    motor_hp_max = calculate_motor_hp(pump, stages, q_design, sg_max)

    # La potencia sube por el rendimiento degradado. El factor de la tabla ya
    # viene como «× γ_o», y calculate_motor_hp ya multiplicó por SG (= γ_o), así
    # que acá sólo entra el porcentaje: multiplicar de nuevo por γ_o lo contaría
    # dos veces.
    if visc_detail is not None:
        chp = visc_detail["hp_factor"] / 100.0
        hp_agua = total_hp
        total_hp *= chp
        motor_hp_max *= chp
        trace.add(
            "visc_hp", "Potencia corregida por viscosidad",
            "HP_crudo = HP_agua · C_HP",
            {"HP_agua": hp_agua, "C_HP": chp},
            total_hp, "hp", "Brown Vol. 2b §4.53112 (Riling), Tabla 4.52x",
            note=f"El rendimiento de la bomba cae de "
                 f"{visc_detail['pump_max_efficiency_pct']:.1f} % a "
                 f"{visc_detail['degraded_efficiency'] * 100:.1f} % con este crudo, "
                 f"y la potencia sube en consecuencia. El γ_o de la columna del "
                 f"libro ya está incluido en HP_agua vía el SG.",
        )

    op_check = check_pump_operating_range(pump, q_design)

    warnings: list[str] = list(visc_detail["warnings"]) if visc_detail else []
    # Avisos del pozo, no de esta bomba: llegan calculados una sola vez y
    # viajan con todos los candidatos (igual que el gas y la viscosidad).
    if extra_warnings:
        warnings = [*extra_warnings, *warnings]
    if not op_check["in_range"]:
        warnings.append("Flow rate outside pump operating range")

    # Carcasas + verificación mecánica. Es la MISMA función que usa el camino
    # por incrementos de presión: una vez conocidas la bomba y las etapas, esta
    # parte no depende de cómo se contaron esas etapas.
    mech = housing_and_mechanical_checks(
        catalog_manager=catalog_manager,
        pump=pump,
        stages=stages,
        sg=sg,
        hp_per_stage=curve["hp_per_stage"],
        head_per_stage=curve["head_per_stage"],
        vertical_lift_ft=float(tdh_info.get("vertical_lift_ft", 0.0)),
        bottom_temp_f=bottom_temp_f,
        warnings=warnings,
        strict=strict,
    )
    if mech is None:
        return None

    return {
        **mech,
        "formulas": trace.as_list(),
        "pump_model": pump.model,
        "pump_manufacturer": pump.manufacturer,
        "pump_od": pump.od,
        "stages": stages,
        "tdh_ft": tdh_ft,
        "head_per_stage": curve["head_per_stage"],
        "hp_per_stage": curve["hp_per_stage"],
        "efficiency": curve["efficiency"],
        "total_pump_hp": total_hp,
        "motor_hp_max": motor_hp_max,
        "pip_psi": pip,
        "sg_liquid": sg,
        # La bomba YA escalada a la frecuencia de operación. El recomendador la
        # usa para la distancia al BEP: buscarla de nuevo en el catálogo daría
        # el BEP de 60 Hz y ordenaría mal a otra frecuencia.
        "pump_curve": pump,
        "operating_frequency_hz": pump.catalog_frequency_hz,
        "operating_check": op_check,
        "tdh_breakdown": tdh_info,
        # Propiedades del pozo/fluido, no de la bomba: se calculan una vez y
        # viajan con cada candidato para que el recomendador no las recalcule.
        "free_gas_fraction": tdh_info.get("free_gas_fraction", 0.0),
        "friction_method": tdh_info.get("friction_method", "hazen_williams"),
        # Corrección por viscosidad (Riling §4.53112). ``None`` con crudo
        # liviano — el diseño corrió contra la curva de agua sin tocar.
        "viscosity_correction": visc_detail,
        # Caudal y altura contra los que se buscó en el catálogo. Con crudo
        # liviano coinciden con los pedidos; con crudo pesado son los
        # equivalentes en agua, que son mayores.
        "design_flow_rate": q_design,
        "design_head_ft": h_design,
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
    2. Evaluate the free-gas fraction at the intake — it decides whether the
       tubing friction uses Hazen-Williams or Poettmann-Carpenter.
    3. Calculate TDH from PIP, well geometry, and surface conditions.
    4. Filter catalog pumps by casing clearance and flow range.
    5. For each candidate: interpolate curve, compute stages + HP, check range.
    6. Return candidates sorted by efficiency (descending).

    The gas fraction is evaluated **once here**, before the TDH, and travels
    down with every candidate: it is a property of the well and the fluid, not
    of the pump being tried, so recomputing it per candidate would be both
    wasteful and a chance for the candidates to disagree.

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
    from bes.core.affinity import pump_at_frequency
    from bes.core.gas_handling import free_gas_fraction_at_intake
    from bes.core.multiphase import calculate_pip

    pip = calculate_pip(
        reservoir=reservoir,
        fluid=fluid,
        well=well,
        pump_setting_depth=pump_setting_depth,
        target_rate=objectives.target_flow_rate,
    )

    free_gas_fraction = free_gas_fraction_at_intake(
        fluid, pip, reservoir.reservoir_temp
    )

    tdh_info = calculate_tdh(
        reservoir, fluid, well, surface, objectives, pump_setting_depth, pip,
        free_gas_fraction=free_gas_fraction,
    )
    tdh_ft = tdh_info["tdh_ft"]
    sg = _sg_liquid(fluid)
    sg_max = _sg_max(fluid)

    # La curva se lleva a la frecuencia real ANTES de filtrar: a 50 Hz el rango
    # operativo de cada bomba se corre un 17 % hacia abajo, así que filtrar con
    # los rangos de catálogo (60 Hz) armaría una lista de candidatas equivocada.
    frequency = operating_frequency(surface, objectives)
    candidates = [
        pump_at_frequency(p, frequency)
        for p in catalog_manager.get_pumps_by_casing(well.casing_id)
    ]

    # Viscosidad en la admisión: propiedad del pozo y del fluido, se evalúa una
    # sola vez y viaja con todos los candidatos (igual que la fracción de gas).
    viscosity = _viscosity_context(
        fluid, well, pump_setting_depth, reservoir.reservoir_temp
    )

    # ¿El método IPR elegido sigue siendo válido en el punto de diseño? El caso
    # que importa es el lineal por debajo de la burbuja: la recta de Darcy
    # sobreestima el aporte del pozo y hay que decirlo.
    from bes.core.ipr import calculate_pwf_for_target_rate, ipr_validity_warning
    aviso_ipr = ipr_validity_warning(
        reservoir, calculate_pwf_for_target_rate(reservoir, objectives.target_flow_rate)
    )
    avisos_pozo = [aviso_ipr] if aviso_ipr else []

    # El prefiltro por rango de caudal va contra el caudal EQUIVALENTE EN AGUA,
    # que es contra el que después se busca en la curva. Filtrar con el caudal
    # pedido dejaría afuera bombas que sí sirven —con crudo viscoso el
    # equivalente en agua es mayor, así que el rango útil se corre hacia arriba.
    # El equivalente depende del rendimiento de cada bomba, así que se calcula
    # por candidata, no una vez para todas.
    candidates = [
        p for p in candidates
        if p.min_flow <= _design_flow_for(p, objectives, viscosity) <= p.max_flow
    ]

    results: list[dict] = []
    for pump in candidates:
        cand = _design_candidate(
            catalog_manager, pump, objectives, tdh_ft, sg, pip, tdh_info, sg_max,
            bottom_temp_f=reservoir.reservoir_temp,
            viscosity=viscosity,
            extra_warnings=avisos_pozo,
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
    from bes.core.affinity import pump_at_frequency
    from bes.core.gas_handling import free_gas_fraction_at_intake
    from bes.core.multiphase import calculate_pip

    pump = next((p for p in catalog_manager.get_all_pumps() if p.model == pump_model), None)
    if pump is None:
        raise ValueError(f"pump_model '{pump_model}' no existe en el catálogo")
    pump = pump_at_frequency(pump, operating_frequency(surface, objectives))
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
    free_gas_fraction = free_gas_fraction_at_intake(
        fluid, pip, reservoir.reservoir_temp
    )
    tdh_info = calculate_tdh(
        reservoir, fluid, well, surface, objectives, pump_setting_depth, pip,
        free_gas_fraction=free_gas_fraction,
    )
    tdh_ft = tdh_info["tdh_ft"]
    sg = _sg_liquid(fluid)
    sg_max = _sg_max(fluid)

    cand = _design_candidate(
        catalog_manager, pump, objectives, tdh_ft, sg, pip, tdh_info, sg_max,
        strict=True, bottom_temp_f=reservoir.reservoir_temp,
        viscosity=_viscosity_context(
            fluid, well, pump_setting_depth, reservoir.reservoir_temp
        ),
    )
    assert cand is not None   # strict=True convierte todo fallo en ValueError
    return cand
