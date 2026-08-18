"""TDH — Altura dinámica total que tiene que desarrollar la bomba.

TDH quiere decir *Total Dynamic Head*. Es **la pregunta central del diseño**:
¿cuánta altura de columna tiene que levantar la bomba para sacar el fluido del
pozo y entregarlo en superficie con la presión que se necesita?

Se descompone en tres términos que se suman::

    TDH = Elevación vertical + Fricción en el tubing + Altura de boca de pozo

Qué significa cada uno
----------------------
**Elevación vertical.** Lo que hay que levantar de verdad. No es toda la
profundidad de la bomba: el fluido ya viene con algo de presión propia (el
PIP), que equivale a una columna que la bomba NO tiene que levantar. Esa
columna se llama sumergencia::

    H_vert = profundidad_bomba − sumergencia
    sumergencia = PIP · 2.31 / SG

**Fricción en el tubing.** Lo que se pierde rozando contra las paredes de la
cañería. Cuanto más caudal y más angosto el tubing, más se pierde.

**Altura de boca de pozo.** El fluido no puede llegar arriba con presión cero:
tiene que entrar al separador. Esa presión se convierte a altura equivalente.

El 2.31 que aparece en todos lados
----------------------------------
Es la constante que pasa de presión a altura: **una columna de 2.31 pies de
agua dulce hace 1 psi**. Dividir por el SG la lleva al fluido real, que es más
pesado que el agua o más liviano según el caso.

Cuál correlación de fricción se usa
-----------------------------------
La decide la física, no el usuario. Se mira cuánto **gas libre** hay en la
admisión de la bomba:

    - poco gas  -> Hazen-Williams (fórmula monofásica, para líquido)
    - mucho gas -> Poettmann-Carpenter (multifásica), sólo el término de
      fricción

El umbral por defecto es 1 % de gas libre. Ver
``.claude/rules/domain.md``.

Contenido
---------
1. Fricción por Hazen-Williams (monofásica)
2. Fricción por Poettmann-Carpenter (multifásica), integrada por tramos
3. Temperatura a una profundidad dada (perfil geotérmico lineal)
4. El TDH completo, con su traza de fórmulas

Nomenclatura
------------
    TDH       Altura dinámica total                        [ft]
    H_vert    Elevación vertical neta                      [ft]
    H_fric    Pérdida por fricción en el tubing            [ft]
    H_wh      Altura equivalente a la presión de cabeza    [ft]
    H_pip     Sumergencia                                  [ft]
    PIP       Pump Intake Pressure: presión en la admisión [psia]
    Pwh       Presión requerida en boca de pozo            [psi]
    SG        Gravedad específica del líquido producido    [-]
    2.31      Pies de columna de agua dulce por psi        [ft/psi]

Referencia
----------
Brown, K.E. "The Technology of Artificial Lift Methods", Vol. 2b, §4.5324.
"""
from __future__ import annotations

from bes.core.models import DesignObjectives, Fluid, Reservoir, SurfaceConditions, WellGeometry


def friction_loss_hazen_williams(
    q_bpd: float,
    pipe_id_in: float,
    length_ft: float,
    c_factor: float = 120.0,
) -> float:
    """Pérdida de carga por fricción en el tubing — Hazen-Williams.

    Es la fórmula **monofásica**: vale cuando lo que sube por el tubing se puede
    tratar como líquido, o sea con poco gas libre::

        H_fric = 0.2083 · (100/C)^1.852 · q^1.852 / d^4.8655 · L/100

    Fijarse en los exponentes: la pérdida crece casi con el **cuadrado del
    caudal** y baja con la **quinta potencia del diámetro**. Por eso un tubing
    un poco más ancho reduce muchísimo la fricción.

    Args:
        q_bpd: Caudal [STB/d].
        pipe_id_in: Diámetro interior de la cañería [in].
        length_ft: Largo de la cañería [ft].
        c_factor: Coeficiente de rugosidad de Hazen-Williams
            (120 = acero de diseño, 130 = acero nuevo).

    Returns:
        Pérdida de carga total por fricción [ft].
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
    """Fricción en el tubing por Poettmann-Carpenter, en pies de líquido producido.

    Se acumula **sólo el término de fricción** del gradiente P&C. El término de
    gravedad de la columna multifásica es la contraparte física de la elevación
    vertical que :func:`calculate_tdh` ya contabiliza, así que sumarlo contaría
    la columna dos veces. Ver
    :func:`bes.core.multiphase.poettmann_carpenter_components`.

    Por qué se integra por tramos y no se evalúa en un punto
    --------------------------------------------------------
    El gas libre **se expande** a medida que la presión cae hacia la superficie.
    Cerca del cabezal la mezcla va varias veces más rápido que en la bomba, y
    el término de fricción va con v², así que la fricción está fuertemente
    cargada hacia el tope de la sarta. Evaluarla en un punto medio la
    subestima.

    Por eso esta función recorre el tubing en ``n_segments`` tramos:

        1. arranca en el cabezal, donde la presión se conoce (la de boca de
           pozo);
        2. en cada tramo evalúa el gradiente P&C en el punto medio (paso
           predictor sobre la presión, punto medio sobre la temperatura);
        3. acumula la contribución de **fricción**, y avanza la presión con el
           gradiente **total** — el perfil de presión del tubing lo gobiernan
           los dos términos, aunque al TDH sólo vaya la fricción.

    Bajar desde la presión conocida del cabezal además **saca la
    circularidad**: no hace falta estimar el TDH para calcular la fricción.

    Args:
        fluid: PVT y composición del fluido.
        well: Geometría del pozo — ID del tubing y perfil de temperatura.
        surface: Condiciones de superficie — presión de boca de pozo, que es
            donde arranca el recorrido.
        objectives: Objetivos de diseño — caudal buscado.
        pump_depth: Profundidad de la bomba [ft TVD], o sea el largo del
            tubing.
        sg: Gravedad específica del líquido producido, para pasar psi a ft.
        bottom_temp_f: Temperatura de fondo [°F] — el extremo inferior del
            perfil geotérmico, o sea ``reservoir.reservoir_temp``.
        n_segments: Cantidad de tramos de integración. Con 30 el resultado
            queda a una fracción de pie de un recorrido mucho más fino.

    Returns:
        ``(fricción_ft, diagnósticos)``. Los diagnósticos traen la presión en
        los dos extremos de la sarta y los gradientes en el cabezal y en la
        bomba, que es lo que muestra cuánto carga la expansión hacia el tope.

    Raises:
        ValueError: Propagado desde la correlación P&C si el caudal o el
            diámetro no son físicos.
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
    """Altura dinámica total (TDH) — Brown Vol. 2b, §4.5324.

    Es la función central del módulo::

        TDH = Elevación vertical + Fricción en tubing + Altura de boca de pozo

        Elevación vertical      = profundidad_bomba − (PIP en pies de columna)
        Altura de boca de pozo  = Pwh · 2.31 / SG_líquido
        Fricción                = ver abajo

    Qué correlación de fricción se usa
    ----------------------------------
    **Lo decide la cantidad de gas libre en la admisión**, no el usuario:

        - ``fracción_gas <= objectives.gas_fraction_pc_threshold``
          -> **Hazen-Williams**. Lo que sube es esencialmente líquido y vale la
          ecuación monofásica.
        - por encima del umbral
          -> **Poettmann-Carpenter**, sólo el término de fricción. La mezcla
          gas-líquido es más liviana y mucho más rápida que el líquido solo, y
          eso la ecuación monofásica no lo puede representar.

    Un híbrido deliberado, y lo que deja afuera
    -------------------------------------------
    Se sustituye **sólo** el término de fricción; la elevación vertical y la
    altura de cabeza siguen usando el SG del líquido. Es a propósito: conserva
    el desglose de tres términos que muestran la pantalla y los reportes.

    Pero hay que saber qué deja afuera: en un pozo con gas de verdad, la
    columna del tubing también es más liviana que la columna de líquido, así
    que la elevación vertical calculada acá es **conservadora** — sobreestima
    la altura que la bomba tiene que desarrollar.

    Args:
        reservoir: Propiedades del reservorio (se lleva por simetría de API con
            los otros cálculos).
        fluid: PVT y composición — aporta el SG para pasar presión a altura.
        well: Geometría del pozo — el ID del tubing entra en la fricción.
        surface: Condiciones de superficie — presión requerida en boca de pozo.
        objectives: Objetivos de diseño — caudal buscado y el umbral de
            fracción de gas que elige la correlación de fricción.
        pump_depth: Profundidad de asentamiento de la bomba [ft TVD].
        pip: Presión en la admisión de la bomba [psi].
        free_gas_fraction: Fracción volumétrica de gas libre en la admisión
            [0–1]. Si se omite se calcula del fluido a ``pip``; conviene
            pasarla cuando quien llama ya la evaluó (``design_pump_complete``
            lo hace, así se calcula una vez por diseño y no una por candidata).

    Returns:
        dict con ``tdh_ft``, ``vertical_lift_ft``, ``tubing_friction_ft``,
        ``wellhead_pressure_head_ft``, ``pip_head_ft``, ``sg_liquid``,
        ``pump_depth_ft``, ``pip_psi``, ``free_gas_fraction``,
        ``gas_fraction_threshold``, ``friction_method``
        (``"hazen_williams"`` o ``"poettmann_carpenter"``) y, sólo en el caso
        P&C, los diagnósticos ``pc_*`` del gradiente convergido.
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
        "sg_liquid",
        {"SG_o": 141.5 / (131.5 + fluid.oil_api), "WC": fluid.water_cut,
         "SG_w": fluid.water_sg},
        sg,
    )

    pip_head_ft = pip * 2.31 / sg
    trace.add("pip_head", {"PIP": pip, "SG": sg}, pip_head_ft)

    vertical_lift = pump_depth - pip_head_ft
    trace.add(
        "vertical_lift",
        {"D_bomba": pump_depth, "H_pip": pip_head_ft},
        vertical_lift,
        context=(
            "La sumergencia ayuda en vez de estorbar: el nivel de fluido queda "
            "por encima de la bomba (caso del ejemplo #2B)."
            if vertical_lift < 0 else ""
        ),
    )

    wellhead_pressure_head = surface.wellhead_pressure_required * 2.31 / sg
    trace.add(
        "wellhead_head",
        {"P_wh": surface.wellhead_pressure_required, "SG": sg},
        wellhead_pressure_head,
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
            "friccion_pc",
            {"(dP/dz)_fricción": extra.get("pc_friction_gradient_psi_ft", 0.0),
             "L": pump_depth, "SG": sg},
            tubing_friction,
            context=f"La fracción de gas libre en la admisión "
                    f"({free_gas_fraction:.3f}) supera el umbral "
                    f"({threshold:.2f}), así que la fricción se calcula con P&C.",
        )
    else:
        friction_method = "hazen_williams"
        tubing_friction = friction_loss_hazen_williams(
            q_bpd=objectives.target_flow_rate,
            pipe_id_in=well.tubing_id,
            length_ft=pump_depth,
        )
        trace.add(
            "friccion_hazen_williams",
            {"C": 120.0, "q": objectives.target_flow_rate * 0.02917,
             "d": well.tubing_id, "L": pump_depth},
            tubing_friction,
            context=f"La fracción de gas libre en la admisión "
                    f"({free_gas_fraction:.3f}) no supera el umbral "
                    f"({threshold:.2f}), así que el flujo en el tubing se "
                    f"trata como monofásico.",
        )

    tdh = vertical_lift + tubing_friction + wellhead_pressure_head
    trace.add(
        "tdh",
        {"H_vert": vertical_lift, "H_fric": tubing_friction,
         "H_wh": wellhead_pressure_head},
        tdh,
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
