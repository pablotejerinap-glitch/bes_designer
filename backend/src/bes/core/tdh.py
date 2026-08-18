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


def temp_at_depth(well: WellGeometry, depth: float, bottom_temp_f: float) -> float:
    """Temperatura a una profundidad, por perfil geotérmico lineal [°F].

    Los dos extremos del perfil son ``well.wellhead_temp`` arriba y la
    temperatura de fondo abajo. **La de fondo llega por parámetro, no vive en
    la geometría**: es la del reservorio (``Reservoir.reservoir_temp``), y
    tenerla duplicada en ``WellGeometry`` permitía cargar dos números distintos
    para la misma magnitud física.

    Args:
        well: Geometría del pozo — aporta ``wellhead_temp`` y ``total_depth``.
        depth: Profundidad de interés [ft].
        bottom_temp_f: Temperatura de fondo [°F], normalmente
            ``reservoir.reservoir_temp``.

    Returns:
        Temperatura a esa profundidad [°F].
    """
    if well.total_depth <= 0:
        return bottom_temp_f
    frac = max(0.0, min(depth / well.total_depth, 1.0))
    return well.wellhead_temp + frac * (bottom_temp_f - well.wellhead_temp)


_PC_SEGMENTS = 30


def _friction_loss_poettmann_carpenter(
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    pump_depth: float,
    sg: float,
    bottom_temp_f: float,
    n_segments: int = _PC_SEGMENTS,
) -> tuple[float, dict]:
    """Tubing friction head by Poettmann-Carpenter, in ft of produced liquid.

    Only the **friction** term of the P&C gradient is accumulated: the gravity
    term of the multiphase column is the physical counterpart of the
    vertical-lift head that :func:`calculate_tdh` already accounts for, so
    adding it would count the column twice. See
    :func:`bes.core.multiphase.poettmann_carpenter_components`.

    The friction gradient cannot be evaluated at a single representative point.
    Free gas expands as the pressure falls towards the surface, so the mixture
    velocity near the wellhead is several times what it is at the pump and the
    friction term — which goes with v² — is strongly weighted to the top of the
    string. This function therefore marches the tubing in ``n_segments``:

    1. start at the wellhead, where the pressure is known (THP);
    2. per segment, evaluate the P&C gradient at the segment mid-point
       (predictor step on the pressure, mid-point on the temperature);
    3. accumulate the **friction** contribution, and advance the pressure with
       the **total** gradient — the pressure profile in the tubing is governed
       by both terms, even though only friction goes into the TDH.

    Marching downward from the known wellhead pressure also removes the
    circularity: no estimate of the TDH is needed to compute the friction.

    Args:
        fluid: Fluid PVT and composition.
        well: Well geometry — tubing ID and the temperature profile.
        surface: Surface conditions — wellhead pressure (start of the march).
        objectives: Design objectives — target flow rate.
        pump_depth: Pump setting depth [ft TVD], i.e. the tubing length.
        sg: Produced-liquid specific gravity, for the psi → ft conversion.
        bottom_temp_f: Temperatura de fondo [°F] — el extremo inferior del
            perfil geotérmico, o sea ``reservoir.reservoir_temp``.
        n_segments: Number of integration segments. 30 keeps the result within
            a fraction of a foot of a much finer march.

    Returns:
        ``(friction_head_ft, diagnostics)``. The diagnostics carry the pressure
        at both ends of the string and the gradients at the wellhead and at the
        pump, which is what shows how much the expansion weights the top.

    Raises:
        ValueError: Propagated from the P&C correlation for a non-physical
            flow rate or tubing diameter.
    """
    from bes.core.multiphase import poettmann_carpenter_components

    def grad_at(p: float, t: float) -> dict:
        return poettmann_carpenter_components(
            q_liq=objectives.target_flow_rate,
            wc=fluid.water_cut,
            gor=fluid.gor,
            gas_sg=fluid.gas_sg,
            oil_api=fluid.oil_api,
            water_sg=fluid.water_sg,
            p=max(p, 14.7),
            t=t,
            pipe_id=well.tubing_id,
            angle=90.0,
        )

    dz = pump_depth / n_segments
    p = max(surface.wellhead_pressure_required, 14.7)
    p_start = p
    friction_psi = 0.0
    comps_top: dict = {}
    comps_bottom: dict = {}

    for i in range(n_segments):
        t_mid = temp_at_depth(well, (i + 0.5) * dz, bottom_temp_f)
        # Predictor: advance half a segment with the gradient at the segment
        # top, then evaluate the properties at that mid-point pressure.
        pred = grad_at(p, t_mid)
        comps = grad_at(p + pred["total"] * dz * 0.5, t_mid)

        friction_psi += comps["friction"] * dz
        p += comps["total"] * dz

        if i == 0:
            comps_top = comps
        comps_bottom = comps

    friction_ft = friction_psi * 2.31 / sg
    return friction_ft, {
        "pc_wellhead_pressure_psia": p_start,
        "pc_pump_discharge_pressure_psia": p,
        "pc_friction_psi": friction_psi,
        "pc_friction_gradient_top_psi_ft": comps_top.get("friction", 0.0),
        "pc_friction_gradient_bottom_psi_ft": comps_bottom.get("friction", 0.0),
        "pc_mixture_velocity_top_ft_s": comps_top.get("mixture_velocity", 0.0),
        "pc_mixture_velocity_bottom_ft_s": comps_bottom.get("mixture_velocity", 0.0),
        "pc_segments": n_segments,
    }


def calculate_tdh(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    pump_depth: float,
    pip: float,
    free_gas_fraction: float | None = None,
) -> dict:
    """Total Dynamic Head per Brown, Vol. 2b, Section 4.5324.

    TDH = Vertical Lift + Tubing Friction + Wellhead Pressure Head

    - Vertical Lift  = pump_depth − (PIP in ft of fluid head)
    - Wellhead Pressure Head = Pwh × 2.31 / SG_liquid
    - Tubing Friction — **the correlation depends on how much free gas the
      well carries at the pump intake**:

      * ``free_gas_fraction <= objectives.gas_fraction_pc_threshold`` →
        Hazen-Williams. The stream is essentially liquid and the single-phase
        equation applies.
      * above the threshold → Poettmann-Carpenter (friction term only). The
        gas-liquid mixture is lighter and much faster than the liquid alone,
        which the single-phase equation cannot represent.

    Only the friction term of P&C is substituted; the vertical lift and the
    wellhead head keep the produced-liquid SG. This is a deliberate hybrid: it
    preserves the three-term breakdown that the reports and the UI show. Be
    aware of what it leaves out — in a real gassy well the tubing column is
    also lighter than the liquid column, so the vertical-lift term computed
    here is conservative (it over-estimates the head the pump must develop).

    Args:
        reservoir: Reservoir properties (carried for API symmetry with other calcs).
        fluid: Fluid PVT and composition — provides SG for head conversions.
        well: Well geometry — tubing ID used for friction.
        surface: Surface conditions — wellhead pressure required.
        objectives: Design objectives — target flow rate and the gas-fraction
            threshold that selects the friction correlation.
        pump_depth: Pump setting depth [ft TVD].
        pip: Pump intake pressure [psi].
        free_gas_fraction: Free-gas volume fraction at the pump intake [0–1].
            Computed from the fluid at ``pip`` when omitted; pass it in when
            the caller already evaluated it (``design_pump_complete`` does, so
            it is computed once per design rather than once per candidate).

    Returns:
        dict with keys: ``tdh_ft``, ``vertical_lift_ft``, ``tubing_friction_ft``,
        ``wellhead_pressure_head_ft``, ``pip_head_ft``, ``sg_liquid``,
        ``pump_depth_ft``, ``pip_psi``, ``free_gas_fraction``,
        ``gas_fraction_threshold``, ``friction_method`` (``"hazen_williams"``
        or ``"poettmann_carpenter"``) and, only in the P&C case, the
        ``pc_*`` diagnostics of the converged gradient.
    """
    from bes.core.formulas import Formula, FormulaTrace
    trace = FormulaTrace()

    # La traza arranca en la IPR, que es el primer cálculo del diseño: de la
    # Pwf en las perforaciones sale el PIP, y de ahí todo lo que sigue.
    from bes.core.ipr import calculate_pwf_for_target_rate, ipr_trace
    try:
        pwf = calculate_pwf_for_target_rate(reservoir, objectives.target_flow_rate)
        for f in ipr_trace(reservoir, objectives.target_flow_rate, pwf):
            trace.items.append(Formula(**f))
    except ValueError:
        # Caudal objetivo por encima del AOF: el diseño falla más adelante con
        # su propio mensaje. Acá sólo se omite el tramo de la traza.
        pass

    sg = _sg_liquid(fluid)
    trace.add(
        "sg_liquid", "Gravedad específica del líquido producido",
        "SG = SG_o · (1 − WC) + SG_w · WC",
        {"SG_o": 141.5 / (131.5 + fluid.oil_api), "WC": fluid.water_cut,
         "SG_w": fluid.water_sg},
        sg, "-", "Brown Vol. 2b §4.5324",
        note="Ponderación por corte de agua. El catálogo publica la potencia "
             "para agua (SG = 1), por eso después se corrige por este valor.",
    )

    pip_head_ft = pip * 2.31 / sg
    trace.add(
        "pip_head", "Sumergencia — altura equivalente a la presión de admisión",
        "H_pip = PIP · 2.31 / SG",
        {"PIP": pip, "SG": sg}, pip_head_ft, "ft", "Brown Vol. 2b §4.5324",
        note="2.31 ft/psi es la columna de agua dulce; dividir por SG la lleva "
             "al fluido real. Es la altura que la bomba NO tiene que levantar.",
    )

    vertical_lift = pump_depth - pip_head_ft
    trace.add(
        "vertical_lift", "Elevación vertical neta",
        "H_vert = D_bomba − H_pip",
        {"D_bomba": pump_depth, "H_pip": pip_head_ft},
        vertical_lift, "ft", "Brown Vol. 2b §4.5324",
        note="Si el nivel de fluido queda por encima de la bomba, H_pip supera "
             "la profundidad y este término se vuelve negativo: la sumergencia "
             "ayuda en vez de estorbar (caso del ejemplo #2B).",
    )

    wellhead_pressure_head = surface.wellhead_pressure_required * 2.31 / sg
    trace.add(
        "wellhead_head", "Altura equivalente a la presión de boca de pozo",
        "H_wh = P_wh · 2.31 / SG",
        {"P_wh": surface.wellhead_pressure_required, "SG": sg},
        wellhead_pressure_head, "ft", "Brown Vol. 2b §4.5324",
    )

    if free_gas_fraction is None:
        from bes.core.gas_handling import free_gas_fraction_at_intake
        free_gas_fraction = free_gas_fraction_at_intake(
            fluid, pip, reservoir.reservoir_temp
        )

    threshold = objectives.gas_fraction_pc_threshold
    extra: dict = {}
    if free_gas_fraction > threshold:
        friction_method = "poettmann_carpenter"
        tubing_friction, extra = _friction_loss_poettmann_carpenter(
            fluid=fluid,
            well=well,
            surface=surface,
            objectives=objectives,
            pump_depth=pump_depth,
            sg=sg,
            bottom_temp_f=reservoir.reservoir_temp,
        )
        trace.add(
            "friction", "Pérdida por fricción en el tubing (Poettmann-Carpenter)",
            "H_fric = (dP/dz)_fricción · L · 2.31 / SG",
            {"(dP/dz)_fricción": extra.get("pc_friction_gradient_psi_ft", 0.0),
             "L": pump_depth, "SG": sg},
            tubing_friction, "ft",
            "Poettmann & Carpenter (1952); Brown Vol. 2b §4.5324",
            note=f"Se usa P&C porque la fracción de gas libre en la admisión "
                 f"({free_gas_fraction:.3f}) supera el umbral ({threshold:.2f}). "
                 f"Se toma SOLO el término de fricción: el de gravedad ya está "
                 f"contado en la elevación vertical.",
        )
    else:
        friction_method = "hazen_williams"
        tubing_friction = friction_loss_hazen_williams(
            q_bpd=objectives.target_flow_rate,
            pipe_id_in=well.tubing_id,
            length_ft=pump_depth,
        )
        trace.add(
            "friction", "Pérdida por fricción en el tubing (Hazen-Williams)",
            "H_fric = 0.2083 · (100/C)^1.852 · q^1.852 / d^4.8655 · L/100",
            {"C": 120.0, "q": objectives.target_flow_rate * 0.02917,
             "d": well.tubing_id, "L": pump_depth},
            tubing_friction, "ft", "Brown Vol. 2b §4.5324",
            note=f"Se usa Hazen-Williams porque la fracción de gas libre en la "
                 f"admisión ({free_gas_fraction:.3f}) no supera el umbral "
                 f"({threshold:.2f}): el flujo se trata como monofásico. "
                 f"q va en gpm y d en pulgadas.",
        )

    tdh = vertical_lift + tubing_friction + wellhead_pressure_head
    trace.add(
        "tdh", "TDH — Altura dinámica total",
        "TDH = H_vert + H_fric + H_wh",
        {"H_vert": vertical_lift, "H_fric": tubing_friction,
         "H_wh": wellhead_pressure_head},
        tdh, "ft", "Brown Vol. 2b §4.5324",
        note="Es la altura total que la bomba tiene que desarrollar.",
    )

    return {
        "formulas": trace.as_list(),
        "tdh_ft": tdh,
        "vertical_lift_ft": vertical_lift,
        "tubing_friction_ft": tubing_friction,
        "wellhead_pressure_head_ft": wellhead_pressure_head,
        "pip_head_ft": pip_head_ft,
        "sg_liquid": sg,
        "pump_depth_ft": pump_depth,
        "pip_psi": pip,
        "free_gas_fraction": free_gas_fraction,
        "gas_fraction_threshold": threshold,
        "friction_method": friction_method,
        **extra,
    }
