"""Servicio del método de incrementos de presión para pozos con gas.

Orquesta el procedimiento de Kermit Brown Vol. 2b §4.53103 —el que resuelve la
bomba intervalo por intervalo desde la admisión hasta la descarga— y devuelve
**números crudos**: la tabla por intervalo y el resumen. El formato es problema
del front (``.claude/rules/architecture.md``).

Por qué existe esta capa: ``core.gas_handling`` sabe hacer la cuenta pero no
sabe de dónde salen las presiones de admisión y descarga. Acá se decide eso —
recorrido multifásico, o los valores que el usuario ya conoce— y se arma la
tabla que pide el capítulo 23 del procedimiento.
"""
from __future__ import annotations

from bes.core.gas_handling import (
    GAS_FRACTION_NEGLIGIBLE,
    SEPARATOR_DEFAULT_EFFICIENCY,
    check_gas_lock_risk,
    complete_gas_design,
    evaluate_gas_feasibility,
    free_gas_fraction_at_intake,
    increment_result_to_candidate,
    pressure_increment_design,
    recommend_gas_separator,
)
from bes.core.models import (
    DesignObjectives,
    Fluid,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)
from bes.core.tdh import _sg_liquid, _sg_max


def _unir_avisos(*listas) -> list[str]:
    """Junta listas de advertencias sin repetir y conservando el orden.

    Se repiten a propósito de un lado y del otro —la escalera de gas emite las
    suyas y el candidato hidráulico arrastra algunas de las mismas—, y mostrar
    dos veces el mismo aviso le resta peso a todos.
    """
    vistas: set[str] = set()
    salida: list[str] = []
    for lista in listas:
        for aviso in lista or []:
            if aviso not in vistas:
                vistas.add(aviso)
                salida.append(aviso)
    return salida


def _temp_at_depth(well: WellGeometry, depth: float, bottom_temp_f: float) -> float:
    """Temperatura del perfil geotérmico lineal a una profundidad [°F]."""
    if well.total_depth <= 0:
        return bottom_temp_f
    fraccion = min(max(depth / well.total_depth, 0.0), 1.0)
    return well.wellhead_temp + fraccion * (bottom_temp_f - well.wellhead_temp)


def _resolve_pump_depth(
    well: WellGeometry, objectives: DesignObjectives, pump_depth: float | None
) -> float:
    """Profundidad de asentamiento, con la misma convención que el diseño normal."""
    if pump_depth is not None:
        return pump_depth
    if getattr(well, "pump_setting_depth", None):
        return well.pump_setting_depth
    return max(well.perforations_top - objectives.safety_margin_depth, 100.0)


def run_gas_increment_design(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    catalog_manager,
    *,
    pump_depth: float | None = None,
    increment_psi: float = 200.0,
    p_intake: float | None = None,
    p_discharge: float | None = None,
    vent_gas_pct: float = 0.0,
    apply_deterioration: bool = False,
    apply_viscosity: bool = True,
    fixed_pump_model: str | None = None,
    pvt_table=None,
) -> dict:
    """Diseño por incrementos de presión, listo para mostrar.

    Cuando ``p_intake`` y ``p_discharge`` vienen dados se usan tal cual —es el
    caso de reproducir un ejemplo del libro, donde las presiones están
    impresas—. Si no, se calculan con el recorrido multifásico completo
    (``complete_gas_design``).

    Args:
        reservoir, fluid, well, surface, objectives: Entradas del dominio.
        catalog_manager: Catálogo cargado.
        pump_depth: Profundidad de la admisión [ft]. Por defecto, tope de
            punzados menos el margen de seguridad.
        increment_psi: Tamaño del escalón de presión [psi]. **Configurable**:
            cuanto más chico, mejor representa el cambio real del fluido.
        p_intake: Presión de admisión [psia]. ``None`` = calcularla.
        p_discharge: Presión de descarga [psia]. ``None`` = calcularla.
        vent_gas_pct: Fracción del gas libre venteada por el anular [0–1].
        apply_deterioration: Degrada la altura por gas libre (Brown §4.53102).
        apply_viscosity: Corrección de Riling por intervalo (§4.53112).
        fixed_pump_model: Fija el modelo de bomba en vez de seleccionarlo.
        pvt_table: :class:`bes.core.pvt.PVTTable` de laboratorio.

    Returns:
        dict con ``increments`` (la tabla del §23), ``summary`` (el resumen),
        ``gas`` (riesgo por gas y separador) y ``warnings``. Todo en números
        crudos.

    Raises:
        ValueError: Si la descarga no supera a la admisión, o si ninguna bomba
            del catálogo entra en el casing.
    """
    depth = _resolve_pump_depth(well, objectives, pump_depth)
    t_pump = _temp_at_depth(well, depth, reservoir.reservoir_temp)

    gas_ctx: dict = {}
    if p_intake is None or p_discharge is None:
        # Recorrido completo: PIP por el anular, descarga por el tubing.
        gas_ctx = complete_gas_design(
            reservoir=reservoir,
            fluid=fluid,
            well=well,
            pump_depth=depth,
            target_rate=objectives.target_flow_rate,
            catalog_manager=catalog_manager,
            vent_gas_pct=vent_gas_pct,
            wellhead_pressure=surface.wellhead_pressure_required,
            apply_deterioration=apply_deterioration,
            fixed_pump_model=fixed_pump_model,
        )
        p_intake = p_intake if p_intake is not None else gas_ctx["pip"]
        p_discharge = (
            p_discharge if p_discharge is not None else gas_ctx["p_discharge"]
        )
        gip = gas_ctx["gip"]
    else:
        # Presiones dadas (caso del libro): el gas venteado es el único dato
        # que hace falta para saber cuánto entra a la bomba.
        gip = 1.0 - vent_gas_pct

    diseno = pressure_increment_design(
        reservoir=reservoir,
        fluid=fluid,
        p_intake=p_intake,
        p_discharge=p_discharge,
        target_rate=objectives.target_flow_rate,
        catalog_manager=catalog_manager,
        gip=gip,
        water_cut=fluid.water_cut,
        increment_psi=increment_psi,
        apply_deterioration=apply_deterioration,
        fixed_pump_model=fixed_pump_model,
        casing_id=well.casing_id,
        apply_viscosity=apply_viscosity,
        pvt_table=pvt_table,
    )

    # --- Gas: riesgo y separador -----------------------------------------
    if gas_ctx:
        fg_intake = gas_ctx["free_gas_ratio_at_intake"]
        riesgo = gas_ctx["gas_lock_risk"]
        separador = gas_ctx["separator_recommendation"]
    else:
        fg_intake = free_gas_fraction_at_intake(fluid, p_intake, t_pump)
        riesgo = check_gas_lock_risk(fg_intake * gip)
        separador = recommend_gas_separator(fg_intake, diseno["pump_series"])

    avisos = [
        *diseno["selection_warnings"],
        *diseno["pvt_warnings"],
        *diseno["viscosity_warnings"],
    ]

    return {
        "increments": diseno["increment_table"],
        "summary": {
            "p_intake":            p_intake,
            "p_discharge":         p_discharge,
            "delta_p":             diseno["delta_p"],
            "increment_psi":       increment_psi,
            "n_increments":        diseno["n_increments"],
            "target_oil_rate":     objectives.target_flow_rate * (1.0 - fluid.water_cut),
            "target_liquid_rate":  objectives.target_flow_rate,
            "q_mix_intake_bpd":    diseno["q_mix_intake_bpd"],
            "q_mix_discharge_bpd": diseno["q_mix_discharge_bpd"],
            "q_mix_max_bpd":       diseno["q_mix_max_bpd"],
            "q_mix_min_bpd":       diseno["q_mix_min_bpd"],
            "mass_rate_lbm_d":     diseno["mass_rate_lbm_d"],
            "total_stages":        diseno["total_stages"],
            "total_stages_exact":  diseno["total_stages_exact"],
            "total_stages_longhand": diseno["total_stages_longhand"],
            "total_hp":            diseno["total_hp"],
            "pump_model":          diseno["pump_model"],
            "pump_manufacturer":   diseno["pump_manufacturer"],
            "pump_series":         diseno["pump_series"],
            "pump_setting_depth":  depth,
            "pump_intake_temp_f":  t_pump,
            "pvt_source":          diseno["pvt_source"],
            "gip":                 gip,
        },
        "gas": {
            "free_gas_fraction_at_intake": fg_intake,
            "risk":                        riesgo,
            "separator":                   separador,
        },
        "warnings": avisos,
        # Traza de fórmulas del método (bes.core.formulas). El aparejo completo
        # la lleva dentro de DesignResult.formulas; acá, que es sólo hidráulica,
        # viaja al costado.
        "formulas": diseno["formulas"],
    }


# ===========================================================================
# Diseño COMPLETO por el método de incrementos: del pozo al aparejo
# ===========================================================================

def gas_method_applies(
    fluid: Fluid,
    pip: float,
    temp_f: float,
    threshold: float,
    free_gas_fraction: float | None = None,
) -> dict:
    """¿Corresponde el método por incrementos, o alcanza el convencional?

    El criterio **no es nuevo**: es el mismo umbral de gas libre en la admisión
    que el proyecto ya usa para decidir si la pérdida de carga se calcula con
    gradiente constante (Hazen-Williams) o con un modelo multifásico
    (``DesignObjectives.gas_fraction_pc_threshold``, 1 % por defecto, alineado
    con ``gas_handling.GAS_FRACTION_NEGLIGIBLE``). La lógica es la misma en los
    dos casos: por encima de ese punto, suponer un fluido de volumen constante
    deja de valer — y el método convencional supone exactamente eso al diseñar
    la bomba con un único caudal.

    Args:
        fluid: Fluido producido.
        pip: Presión de admisión de la bomba [psia].
        temp_f: Temperatura en la admisión [°F].
        threshold: Fracción de gas libre por encima de la cual el volumen deja
            de poder tratarse como constante.
        free_gas_fraction: La fracción, si el llamador ya la tiene. El camino
            convencional la calcula una sola vez —antes del TDH, porque es la
            que elige la correlación de fricción— y la arrastra en el
            candidato; volver a calcularla acá abriría la puerta a que la
            decisión del método se tome sobre un número distinto del que se
            usó para diseñar. Si es ``None`` se calcula.

    Returns:
        dict con ``applies`` (bool), ``free_gas_fraction``, ``threshold`` y
        ``reason`` (texto citable).
    """
    f_g = (
        free_gas_fraction_at_intake(fluid, pip, temp_f)
        if free_gas_fraction is None
        else float(free_gas_fraction)
    )
    aplica = f_g > threshold

    if aplica:
        motivo = (
            f"Gas libre en la admisión {f_g:.2%}, por encima del umbral "
            f"{threshold:.2%} de gas despreciable: el volumen de mezcla cambia "
            f"con la presión a lo largo de la bomba, así que se diseña por "
            f"incrementos de presión (Brown Vol. 2b §4.53103) en vez de con un "
            f"caudal único. Este umbral decide únicamente el MÉTODO de cálculo; "
            f"si el pozo es viable con bombeo electrosumergible lo resuelve la "
            f"escalera de manejo de gas, que es otra verificación."
        )
    else:
        motivo = (
            f"Gas libre en la admisión {f_g:.2%}, por debajo del umbral "
            f"{threshold:.2%}: el volumen se puede tratar como constante y "
            f"vale el diseño convencional con un solo caudal."
        )

    return {
        "applies": aplica,
        "free_gas_fraction": f_g,
        "threshold": threshold,
        "negligible_reference": GAS_FRACTION_NEGLIGIBLE,
        "reason": motivo,
    }


def run_gas_design_complete(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    catalog_manager,
    *,
    pump_depth: float | None = None,
    increment_psi: float = 200.0,
    vent_gas_pct: float = 0.0,
    apply_deterioration: bool = False,
    apply_viscosity: bool = True,
    fixed_pump_model: str | None = None,
    pvt_table=None,
    max_candidates: int = 12,
):
    """Diseño BES **completo** por el método de incrementos de presión.

    Termina en un aparejo físicamente seleccionable —bomba, carcasas, motor,
    sello, cable, transformador, VSD—, no en «X etapas e Y hp». El armado usa
    :func:`bes.recommender.pump_selector.assemble_design`, la misma función que
    el camino convencional, así que la regla de no mezclar fabricantes y los
    criterios de margen del motor y del cable son los que ya están.

    Una sola bomba para toda la sarta (Brown §4.53103 paso 6). Si esa bomba no
    puede completar el aparejo —el caso típico es un proveedor sin motores en
    catálogo— se baja al siguiente candidato, ordenado por distancia al BEP
    contra el caudal de mezcla representativo. Es el mismo patrón de
    ``select_top_n_pumps``.

    Las dos rutas al TDH
    --------------------
    El aparejo se dimensiona con el **TDH equivalente del método**,
    ``Σ ΔPᵢ/gradienteᵢ``, que es coherente con las etapas que el propio método
    contó. El TDH convencional de tres términos se calcula igual y viaja en el
    resultado como ``tdh_conventional_ft``: son dos rutas independientes a la
    misma magnitud física y pueden discrepar, así que se publican las dos en
    vez de elegir una en silencio.

    Args:
        reservoir, fluid, well, surface, objectives: Entradas del dominio.
        catalog_manager: Catálogo cargado.
        pump_depth: Profundidad de admisión [ft]. Por defecto, tope de punzados
            menos el margen de seguridad.
        increment_psi: Escalón de presión [psi].
        vent_gas_pct: Fracción de gas libre venteada por el anular [0–1].
        apply_deterioration: Degrada la altura por gas libre (Brown §4.53102).
        apply_viscosity: Corrección de Riling por intervalo.
        fixed_pump_model: Fija la bomba; sin fallback si no ensambla.
        pvt_table: PVT de laboratorio.
        max_candidates: Cuántas bombas probar antes de rendirse.

    Returns:
        dict con ``design`` (:class:`DesignResult`), ``candidate`` (el dict
        intermedio), ``increment`` (el resultado por intervalos completo),
        ``method`` y ``warnings``.

    Raises:
        ValueError: Si ninguna bomba del catálogo completa el aparejo.
    """
    from bes.core.multiphase import calculate_discharge_pressure, calculate_pip
    from bes.core.pump_design import operating_frequency
    from bes.core.tdh import calculate_tdh
    from bes.recommender.pump_selector import assemble_design
    from bes.recommender.ranking import bep_distance

    depth = _resolve_pump_depth(well, objectives, pump_depth)
    t_pump = _temp_at_depth(well, depth, reservoir.reservoir_temp)
    target = objectives.target_flow_rate

    # --- Presiones: admisión por el anular, descarga por el tubing --------
    pip = calculate_pip(
        reservoir=reservoir, fluid=fluid, well=well,
        pump_setting_depth=depth, target_rate=target,
    )
    p_discharge = calculate_discharge_pressure(
        fluid=fluid, tubing_id=well.tubing_id, pump_depth=depth,
        wellhead_pressure=surface.wellhead_pressure_required,
        target_rate=target, t_pump=t_pump, t_wellhead=well.wellhead_temp,
    )
    if p_discharge <= pip:
        raise ValueError(
            f"La presión de descarga calculada ({p_discharge:.0f} psia) no "
            f"supera a la de admisión ({pip:.0f} psia): con estas condiciones "
            f"el pozo no necesita bomba, o los datos de superficie no cierran."
        )

    # --- Gas y TDH convencional (referencia para auditar) -----------------
    decision = gas_method_applies(
        fluid, pip, t_pump, objectives.gas_fraction_pc_threshold
    )

    # --- ¿La bomba aguanta este gas? --------------------------------------
    # El separador se elige del catálogo ANTES de diseñar, porque su eficiencia
    # decide si el pozo es viable. Si el modelo no publica eficiencia se supone
    # la conservadora por defecto y queda declarado en el veredicto.
    # Se usa LA MISMA escalera que el camino convencional
    # (``pump_selector._estrategia_de_gas``): ninguno → simple → tándem →
    # manejador avanzado → cambiar de método. Antes acá se evaluaba sólo el
    # separador simple, así que un pozo que el camino convencional resolvía con
    # tándem o con AGH, éste lo declaraba inviable.
    from bes.recommender.pump_selector import _estrategia_de_gas, _select_gas_handler

    gip_admision = decision["free_gas_fraction"]
    separador = _select_gas_handler(catalog_manager, well, objectives, gip_admision)
    factibilidad = _estrategia_de_gas(
        catalog_manager, well, objectives, gip_admision, separador,
        vent_fraction=vent_gas_pct,
    )
    if not factibilidad["viable"]:
        raise ValueError(factibilidad["verdict"])
    tdh_info = calculate_tdh(
        reservoir, fluid, well, surface, objectives, depth, pip,
        free_gas_fraction=decision["free_gas_fraction"],
    )

    gip = 1.0 - vent_gas_pct
    sg = _sg_liquid(fluid)
    sg_max = _sg_max(fluid)

    frequency = operating_frequency(surface, objectives)

    def _correr(modelo: str | None) -> dict:
        return pressure_increment_design(
            reservoir=reservoir, fluid=fluid,
            p_intake=pip, p_discharge=p_discharge, target_rate=target,
            catalog_manager=catalog_manager, gip=gip,
            water_cut=fluid.water_cut, increment_psi=increment_psi,
            apply_deterioration=apply_deterioration,
            fixed_pump_model=modelo, casing_id=well.casing_id,
            apply_viscosity=apply_viscosity, pvt_table=pvt_table,
            frequency=frequency,
        )

    # Primera corrida: selección automática. Además de dar un diseño, fija el
    # caudal de mezcla representativo contra el que se ordenan los suplentes.
    primera = _correr(fixed_pump_model)
    q_rep = primera["q_representative_bpd"]

    if fixed_pump_model:
        orden = [primera["pump_model"]]
    else:
        # Suplentes ordenados por distancia al BEP contra el caudal de mezcla,
        # el mismo criterio que usa el recomendador convencional.
        from bes.core.affinity import pump_at_frequency
        candidatas = [
            pump_at_frequency(p, frequency)
            for p in catalog_manager.get_pumps_by_casing(well.casing_id)
        ]
        candidatas.sort(key=lambda p: bep_distance(p, q_rep))
        orden = [primera["pump_model"]] + [
            p.model for p in candidatas[:max_candidates]
            if p.model != primera["pump_model"]
        ]

    motivos: list[str] = []
    for modelo in orden:
        inc = primera if modelo == primera["pump_model"] else _correr(modelo)
        cand = increment_result_to_candidate(
            inc=inc, sg=sg, tdh_info=tdh_info,
            bottom_temp_f=reservoir.reservoir_temp,
            catalog_manager=catalog_manager, sg_max=sg_max,
            extra_warnings=[decision["reason"]],
        )
        if cand is None:
            motivos.append(f"{modelo}: no hay arreglo de carcasas o falla el eje/cojinete")
            continue
        try:
            design = assemble_design(
                cand, inc["pump_curve"], well, surface, fluid, objectives,
                catalog_manager, depth, reservoir.reservoir_temp,
            )
            # --- Un solo número para cada magnitud --------------------------
            #
            # ``assemble_design`` vuelve a correr la escalera por su cuenta, y
            # lo hace sobre una fracción distinta: el candidato por incrementos
            # lleva la del PRIMER TRAMO —promediada entre sus dos extremos—,
            # mientras que la decisión de manejo de gas se tomó sobre la de la
            # ADMISIÓN. Las dos son legítimas y miden cosas distintas, pero
            # publicarlas juntas mostraba hasta cuatro porcentajes para lo que
            # el usuario lee como dos magnitudes: en el Ejemplo #3B, 79.2 % y
            # 75.1 % de gas en la admisión, y 48.8 % y 43.0 % en la bomba.
            #
            # Manda la escalera que efectivamente eligió el aparejo. Es la que
            # se evaluó en la admisión, que es donde ambas magnitudes están
            # definidas, y la que produjo el veredicto que se muestra al lado.
            design.gip_fraction = float(factibilidad["f_intake"])
            design.gas_fraction_at_pump = float(factibilidad["f_pump"])
            if factibilidad.get("formulas"):
                design.formulas = [
                    *[f for f in design.formulas
                      if f.get("step") != "escalera_gas"],
                    *factibilidad["formulas"],
                ]
        except (ValueError, KeyError, StopIteration, TypeError) as exc:
            motivos.append(f"{modelo}: no se pudo completar el aparejo ({exc})")
            continue

        return {
            "design": design,
            "candidate": cand,
            "increment": inc,
            "method": decision,
            "feasibility": factibilidad,
            "pump_setting_depth": depth,
            "pump_intake_temp_f": t_pump,
            "tdh_conventional_ft": tdh_info["tdh_ft"],
            "tdh_increment_ft": inc["tdh_equivalent_ft"],
            # Las del cálculo hidráulico MÁS las de la escalera de manejo de
            # gas. Iban sólo las primeras, y por eso la advertencia de MODO
            # EJEMPLO —la que avisa que ``max_gip`` está en 100 % y que el
            # resultado NO es el criterio con que la herramienta diseñaría el
            # pozo— nunca llegaba a la pantalla: vive en la escalera. Es
            # justamente la que no puede faltar, porque sin ella un resultado
            # de modo ejemplo se lee como un diseño real.
            "warnings": _unir_avisos(cand["warnings"], factibilidad.get("warnings")),
            "rejected": motivos,
            # Las dos condiciones de la escalera, como cuentas auditables. El
            # camino convencional las agrega en ``_build_design_result``; acá el
            # diseño se arma con ``assemble_design``, que no ve la escalera, así
            # que se enganchan sobre el resultado ya construido.
            "ladder_formulas": factibilidad.get("formulas") or [],
        }

    raise ValueError(
        "Ninguna bomba del catálogo completa el aparejo para este pozo con gas. "
        "Motivos por candidata: " + " · ".join(motivos)
    )
