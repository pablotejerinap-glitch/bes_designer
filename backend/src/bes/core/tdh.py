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
4. De dónde salió el PIP: el tramo de la traza que reconstruye el recorrido
   por el anular (``_traza_pip``)
5. El TDH completo, con su traza de fórmulas

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

import math

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


#: Rugosidad absoluta del acero comercial [ft]. Es el valor de manual para
#: cañería de acero al carbono; el tubing nuevo puede ser algo más liso, pero
#: adoptar el más liso sería optimista para un cálculo de proyecto, igual que
#: con el C = 120 de Hazen-Williams.
RUGOSIDAD_ACERO_FT = 0.00015

#: Reynolds por debajo del cual el flujo es laminar y f = 64/Re.
RE_LAMINAR = 2000.0

#: Reynolds por encima del cual vale el ajuste de Swamee-Jain.
RE_TURBULENTO = 4000.0

_CP_A_LB_FT_S = 6.7197e-4   # 1 cp en lbm/(ft·s)
_BBL_A_FT3 = 5.615
_G_FT_S2 = 32.174


def friction_loss_darcy_weisbach(
    q_bpd: float,
    pipe_id_in: float,
    length_ft: float,
    density_lb_ft3: float,
    viscosity_cp: float,
    roughness_ft: float = RUGOSIDAD_ACERO_FT,
) -> dict:
    """Pérdida de carga por fricción — Darcy-Weisbach, con Reynolds.

    Es la alternativa a :func:`friction_loss_hazen_williams` **que sí contempla
    la viscosidad del fluido**::

        h_f = f · (L/d) · v² / (2·g)

    donde el factor de fricción ``f`` depende del régimen:

        Re < 2000   ->  f = 64 / Re                  (laminar, Poiseuille)
        Re > 4000   ->  f = ajuste de Swamee-Jain    (turbulento)

    Por qué hace falta
    ------------------
    Hazen-Williams se estableció sobre ensayos con **agua** en régimen
    turbulento, y su único parámetro libre —el coeficiente C— describe la
    rugosidad de la cañería, no el fluido que circula. En un crudo pesado el
    flujo deja de ser turbulento y la fórmula no puede seguirlo: en el caso de
    14 °API de §3.4.5 el Reynolds cae a 363, muy por debajo de 2000, y allí el
    factor de fricción crece **linealmente con la viscosidad**, comportamiento
    que ninguna potencia fija del caudal reproduce. La diferencia medida en ese
    pozo es de 1 740 pies sobre un TDH de 3 793, y **del lado no conservador**.

    En crudos livianos las dos coinciden dentro del 2 %, de modo que esto no
    corrige un error general sino uno acotado al extremo viscoso.

    La zona de transición
    ---------------------
    Entre 2000 y 4000 no hay una ley: el régimen es inestable y ninguna de las
    dos expresiones vale. Se interpola linealmente en ``log(Re)`` entre el
    laminar en 2000 y el turbulento en 4000, **y se declara** con la bandera
    ``transicion``. Es una convención de ingeniería, no un resultado: lo que
    importa es que el valor quede acotado entre los dos regímenes y que quien
    lea el resultado sepa que ahí la incerteza es mayor.

    Args:
        q_bpd: Caudal de líquido [bbl/d]. Debe ser > 0.
        pipe_id_in: Diámetro interior de la cañería [in]. Debe ser > 0.
        length_ft: Largo de la cañería [ft]. Debe ser >= 0.
        density_lb_ft3: Densidad del líquido [lb/ft³]. Debe ser > 0.
        viscosity_cp: Viscosidad dinámica del líquido [cp]. Debe ser > 0.
        roughness_ft: Rugosidad absoluta de la pared [ft].

    Returns:
        dict con ``head_ft`` (pérdida [ft]), ``reynolds``, ``friction_factor``,
        ``velocity_ft_s``, ``regimen`` (``"laminar"`` / ``"transicion"`` /
        ``"turbulento"``) y ``transicion`` (bool).

    Raises:
        ValueError: Si algún argumento no es positivo.

    Referencia:
        Darcy-Weisbach; factor turbulento por Swamee, P. K. y Jain, A. K.
        (1976), «Explicit equations for pipe-flow problems», Journal of the
        Hydraulics Division, ASCE, 102(HY5), 657-664 — ajuste explícito de la
        ecuación implícita de Colebrook-White.
    """
    if q_bpd <= 0:
        raise ValueError(f"q_bpd must be > 0, got {q_bpd}")
    if pipe_id_in <= 0:
        raise ValueError(f"pipe_id_in must be > 0, got {pipe_id_in}")
    if length_ft < 0:
        raise ValueError(f"length_ft must be >= 0, got {length_ft}")
    if density_lb_ft3 <= 0:
        raise ValueError(f"density_lb_ft3 must be > 0, got {density_lb_ft3}")
    if viscosity_cp <= 0:
        raise ValueError(f"viscosity_cp must be > 0, got {viscosity_cp}")

    d_ft = pipe_id_in / 12.0
    area_ft2 = math.pi / 4.0 * d_ft ** 2
    v = q_bpd * _BBL_A_FT3 / 86400.0 / area_ft2          # ft/s
    mu = viscosity_cp * _CP_A_LB_FT_S                     # lbm/(ft·s)
    re = density_lb_ft3 * v * d_ft / mu

    def _turbulento(reynolds: float) -> float:
        # Swamee-Jain, ajuste explícito de Colebrook-White.
        return 0.25 / (
            math.log10(roughness_ft / (3.7 * d_ft) + 5.74 / reynolds ** 0.9) ** 2
        )

    if re < RE_LAMINAR:
        f, regimen = 64.0 / re, "laminar"
    elif re > RE_TURBULENTO:
        f, regimen = _turbulento(re), "turbulento"
    else:
        f_lam = 64.0 / RE_LAMINAR
        f_tur = _turbulento(RE_TURBULENTO)
        peso = (math.log(re) - math.log(RE_LAMINAR)) / (
            math.log(RE_TURBULENTO) - math.log(RE_LAMINAR)
        )
        f, regimen = f_lam + peso * (f_tur - f_lam), "transicion"

    return {
        "head_ft": f * (length_ft / d_ft) * v ** 2 / (2.0 * _G_FT_S2),
        "reynolds": re,
        "friction_factor": f,
        "velocity_ft_s": v,
        "regimen": regimen,
        "transicion": regimen == "transicion",
    }


def liquid_mixture_viscosity(
    oil_viscosity_cp: float,
    water_cut: float,
    temp_f: float,
) -> dict:
    """Viscosidad del líquido producido — promedio por fracción volumétrica.

    Es la que gobierna la fricción en la tubería cuando el flujo es monofásico::

        mu_l = mu_o · (1 − Wc) + mu_w · Wc

    Por lo que sube por el tubing no circula petróleo sino petróleo **y** agua,
    y la diferencia entre una y otra viscosidad es de órdenes de magnitud: un
    crudo pesado puede andar en los 200 cp y el agua no llega a 1. Con corte de
    agua alto —el caso de la mayoría de los pozos de esta aplicación— tratar la
    mezcla con la viscosidad del petróleo sobrestimaría groseramente la pérdida.

    Lo que este modelo NO captura
    -----------------------------
    **Es una cota inferior**, y conviene tenerlo presente antes de apoyarse en
    el resultado. Cuando el petróleo es la fase continua —esto es, por debajo
    del punto de inversión— la mezcla forma una emulsión agua-en-petróleo cuya
    viscosidad es **varias veces mayor** que la de cualquiera de las dos fases
    por separado, no un promedio entre ellas. Riling (Brown §4.53112) da para
    ese efecto factores de 2 a 3 con cortes de agua entre 20 y 40 %, y de 5 a 6
    entre 55 y 75 %, pero **no entrega una correlación** que permita calcularlos,
    y el punto de inversión tampoco figura como dato en ninguna de las fuentes
    del proyecto.

    Adoptar un valor medio de esos rangos sería inventar el dato. Se prefiere
    el promedio volumétrico, que es la primera aproximación estándar, y se
    **declara** que en el régimen de emulsión la viscosidad real es mayor y la
    fricción calculada queda en consecuencia subestimada. Es el mismo criterio
    con que el paso 5 del procedimiento de crudos viscosos se informa como no
    realizado.

    Args:
        oil_viscosity_cp: Viscosidad del petróleo a las condiciones de
            evaluación [cp]. Debe ser > 0.
        water_cut: Corte de agua [fracción 0–1].
        temp_f: Temperatura de evaluación [°F].

    Returns:
        dict con ``viscosity_cp`` (la de la mezcla), ``oil_cp``, ``water_cp``,
        ``emulsion_posible`` (``True`` cuando el petróleo podría ser la fase
        continua) y ``warnings``.

    Raises:
        ValueError: Si la viscosidad del petróleo no es positiva o el corte de
            agua cae fuera de [0, 1].
    """
    from bes.core.pvt import water_viscosity

    if oil_viscosity_cp <= 0:
        raise ValueError(
            f"oil_viscosity_cp must be > 0, got {oil_viscosity_cp}"
        )
    if not 0.0 <= water_cut <= 1.0:
        raise ValueError(f"water_cut must be in [0, 1], got {water_cut}")

    mu_w = water_viscosity(temp_f)
    mu_l = oil_viscosity_cp * (1.0 - water_cut) + mu_w * water_cut

    avisos: list[str] = []
    # Con petróleo como fase continua la emulsión manda; el corte de inversión
    # no es un dato del proyecto, así que se avisa en todo el rango en que la
    # fase continua podría ser el petróleo en lugar de fijar una frontera.
    emulsion = water_cut > 0.0 and oil_viscosity_cp > mu_w * 2.0
    if emulsion:
        avisos.append(
            f"La viscosidad de la mezcla ({mu_l:.1f} cp) se calculó como "
            f"promedio por fracción volumétrica entre el petróleo "
            f"({oil_viscosity_cp:.1f} cp) y el agua ({mu_w:.2f} cp). Es una "
            f"COTA INFERIOR: si el petróleo resulta la fase continua, la "
            f"emulsión agua en petróleo es varias veces más viscosa que ese "
            f"promedio —Riling da factores de 2 a 3 entre 20 y 40 % de corte "
            f"de agua, y de 5 a 6 entre 55 y 75 %—, pero no publica una "
            f"correlación ni el punto de inversión, de modo que el efecto no "
            f"se modela. La pérdida de carga por fricción queda, en esa "
            f"medida, subestimada."
        )

    return {
        "viscosity_cp": mu_l,
        "oil_cp": oil_viscosity_cp,
        "water_cp": mu_w,
        "emulsion_posible": emulsion,
        "warnings": avisos,
    }


def _viscosidad_de_la_mezcla(
    fluid: Fluid,
    well: WellGeometry,
    pump_depth: float,
    bottom_temp_f: float,
    pip: float,
) -> dict | None:
    """Viscosidad del líquido en la admisión, para el término de fricción.

    Reúne los dos ingredientes que :func:`liquid_mixture_viscosity` necesita:
    la viscosidad del petróleo vivo y el corte de agua.

    La del petróleo sale de la **misma cadena** que emplea la corrección de la
    curva de la bomba —las láminas 4L(2) y 4L(1) del libro, leídas a
    temperatura de reservorio y con el gas efectivamente disuelto a la presión
    de admisión—, de modo que un mismo pozo no puede tener dos viscosidades
    distintas según qué parte del cálculo la pida.

    Returns:
        Lo que devuelve :func:`liquid_mixture_viscosity`, o ``None`` si la
        viscosidad no se pudo establecer. Devolver ``None`` y no un valor por
        defecto es deliberado: sin viscosidad el llamador se queda con
        Hazen-Williams, que es el comportamiento previo, en lugar de calcular
        un Reynolds sobre un número inventado.
    """
    from bes.core.viscosity import crude_viscosity_ssu

    try:
        from bes.core.pump_design import _rs_en_la_admision
        rs = _rs_en_la_admision(fluid, pip, bottom_temp_f)
        medida = (
            fluid.oil_viscosity_dead
            if fluid.oil_viscosity_dead is not None
            and fluid.viscosity_temp_ref is not None
            and abs(fluid.viscosity_temp_ref - bottom_temp_f) <= 5.0
            else None
        )
        mu_o = crude_viscosity_ssu(
            oil_api=fluid.oil_api,
            temp_f=bottom_temp_f,
            rs_scf_bbl=rs,
            dead_oil_cp=medida,
        )["mu_live_cp"]
    except (ValueError, KeyError):
        return None

    if mu_o <= 0:
        return None
    return liquid_mixture_viscosity(mu_o, fluid.water_cut, bottom_temp_f)


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

#: Cómo se lee cada método en un mensaje.
_NOMBRE_METODO = {
    "poettmann_carpenter": "Poettmann-Carpenter (multifásico)",
    "hazen_williams": "Hazen-Williams (monofásico)",
}


def _aviso_metodo_forzado(
    elegido: str,
    metodo_fisica: str,
    free_gas_fraction: float,
    threshold: float,
) -> str:
    """Redacta el aviso de cuando la elección del usuario contradice la física.

    El método de pérdida de carga lo elige el usuario, pero la fracción de gas
    libre en la admisión dice cuál correspondería. Cuando no coinciden **se
    respeta la elección y se avisa**: corregirla en silencio escondería que el
    resultado no es el que la física pide, y no avisar repetiría el error que ya
    tuvo el proyecto (pozos con hasta 10 % de gas diseñados como monofásicos).

    Args:
        elegido: Método que eligió el usuario.
        metodo_fisica: Método que corresponde por la fracción de gas.
        free_gas_fraction: Fracción volumétrica de gas libre en la admisión.
        threshold: Umbral con el que se compara.

    Returns:
        El aviso, listo para ``DesignResult.warnings``.
    """
    if elegido == "hazen_williams":
        return (
            f"Se eligió {_NOMBRE_METODO[elegido]} para la pérdida de carga, "
            f"pero en la admisión hay {free_gas_fraction:.1%} de gas libre "
            f"—más del {threshold:.0%} a partir del cual la corriente deja de "
            f"ser prácticamente líquida—. La fricción calculada con un "
            f"gradiente de líquido constante queda SUBESTIMADA; correspondería "
            f"{_NOMBRE_METODO[metodo_fisica]}."
        )
    return (
        f"Se eligió {_NOMBRE_METODO[elegido]} para la pérdida de carga, pero en "
        f"la admisión hay apenas {free_gas_fraction:.1%} de gas libre —por "
        f"debajo del {threshold:.0%}—, así que la corriente es prácticamente "
        f"líquida y bastaba {_NOMBRE_METODO[metodo_fisica]}. El resultado es "
        f"válido; la elección no era necesaria."
    )



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


def _traza_pip(
    trace,
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    objectives: DesignObjectives,
    pump_depth: float,
    pip: float,
    pwf: float,
) -> None:
    """Agrega a la traza de dónde salió el PIP.

    El PIP le entra a :func:`calculate_tdh` como dato ya calculado, así que la
    traza lo mostraba apareciendo de la nada: la sumergencia arrancaba con un
    número que nadie podía auditar. Acá se publica el eslabón que faltaba, que
    es :func:`bes.core.multiphase.calculate_pip`::

        Pwf (del IPR)  ->  recorrido por el anular  ->  PIP

    El recorrido se integra con **Poettmann & Carpenter**, que es la única
    correlación multifásica del proyecto, así que primero se emite la cadena
    completa de P&C —área, caudales de fondo, velocidades, densidad de la
    mezcla, factor de fricción y los dos términos del gradiente— evaluada **en
    la admisión**, y después la integración y el PIP.

    Un punto y no los veinte: los tramos resuelven todos la misma cadena, y
    veinte copias de diez fórmulas taparían el resto de la traza. Se elige la
    admisión porque es el extremo que el diseño usa.

    Args:
        trace: :class:`bes.core.formulas.FormulaTrace` en construcción.
        reservoir: Reservorio — aporta la temperatura de fondo del perfil.
        fluid: Fluido — PVT, GOR y corte de agua.
        well: Geometría — ID de casing (el anular) y profundidad de las
            perforaciones, que son los dos extremos del recorrido.
        objectives: Objetivos — el caudal con el que se hizo el recorrido.
        pump_depth: Profundidad de la admisión [ft TVD].
        pip: Presión en la admisión ya calculada [psia].
        pwf: Presión de fondo fluyente en las perforaciones [psia].
    """
    from bes.core.formulas import Formula
    from bes.core.multiphase import PIP_TRAVERSE_SEGMENTS, poettmann_carpenter_trace

    largo = well.perforations_bottom - pump_depth
    delta_p = pwf - pip
    t_admision = temp_at_depth(well, pump_depth, reservoir.reservoir_temp)

    cadena = poettmann_carpenter_trace(
        q_liq=objectives.target_flow_rate,
        wc=fluid.water_cut,
        gor=fluid.gor,
        oil_api=fluid.oil_api,
        gas_sg=fluid.gas_sg,
        water_sg=fluid.water_sg,
        pipe_id=well.casing_id,
        p=pip,
        t=t_admision,
    )
    cadena[0]["context"] = (
        f"Cadena de Poettmann & Carpenter con la que se recorre el ANULAR "
        f"(ID de casing {well.casing_id:.3f} in) desde las perforaciones hasta "
        f"la bomba. Se muestra evaluada en la admisión: {pip:,.1f} psia y "
        f"{t_admision:.1f} °F. Los otros tramos del recorrido resuelven la "
        f"misma cadena a su propia presión y temperatura."
    )
    for f in cadena:
        trace.items.append(Formula(**f))

    # El sumatorio queda en símbolos, pero Δz sí se sustituye: es un dato de
    # entrada del recorrido, no el resultado de la propia cuenta.
    trace.add(
        "pip_recorrido",
        {"Δz": largo / PIP_TRAVERSE_SEGMENTS},
        delta_p,
        context=(
            f"Recorrido ascendente de {well.perforations_bottom:,.0f} ft "
            f"(perforaciones) a {pump_depth:,.0f} ft (admisión), o sea "
            f"{largo:,.0f} ft en {PIP_TRAVERSE_SEGMENTS} tramos de "
            f"{largo / PIP_TRAVERSE_SEGMENTS:,.1f} ft, con "
            f"{objectives.target_flow_rate:,.0f} STB/d de líquido."
        ),
    )
    trace.add("pip_admision", {"Pwf": pwf, "Δp_anular": delta_p}, pip)
    if largo > 0:
        trace.add(
            "pip_gradiente_promedio",
            {"Δp_anular": delta_p, "D_perf": well.perforations_bottom,
             "D_bomba": pump_depth},
            delta_p / largo,
        )


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
    La elige el usuario con ``objectives.pressure_loss_method``. Si no eligió
    —``None``, el default— **lo decide la cantidad de gas libre en la
    admisión**, que es el comportamiento histórico:

        - ``fracción_gas <= objectives.gas_fraction_pc_threshold``
          -> **Hazen-Williams**. Lo que sube es esencialmente líquido y vale la
          ecuación monofásica.
        - por encima del umbral
          -> **Poettmann-Carpenter**, sólo el término de fricción. La mezcla
          gas-líquido es más liviana y mucho más rápida que el líquido solo, y
          eso la ecuación monofásica no lo puede representar.

    Con un método elegido a mano se usa ese método, y si la física pedía el
    otro el resultado sale con un **aviso** (``pressure_loss_warnings``): el
    usuario manda, pero enterado. Lo que sigue sin poder elegirse es el
    **umbral** ``gas_fraction_pc_threshold`` — una cosa es elegir el método y
    otra mover el corte con que se lo elige solo.

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
    pwf = None
    try:
        pwf = calculate_pwf_for_target_rate(reservoir, objectives.target_flow_rate)
        for f in ipr_trace(reservoir, objectives.target_flow_rate, pwf):
            trace.items.append(Formula(**f))
    except ValueError:
        # Caudal objetivo por encima del AOF: el diseño falla más adelante con
        # su propio mensaje. Acá sólo se omite el tramo de la traza.
        pass

    # De la Pwf al PIP: el recorrido por el anular. El PIP entra por parámetro
    # ya calculado, así que la traza tiene que reconstruir de dónde salió — si
    # no, la sumergencia arranca con un número sin origen.
    #
    # La condición no es cosmética: el tramo se publica sólo si el PIP es
    # coherente con haber subido desde las perforaciones (0 < PIP < Pwf). Un
    # caso de prueba puede pasarle a esta función un PIP impreso del libro que
    # no salga del recorrido, y atribuírselo sería mentir sobre la cuenta.
    if pwf is not None and 0.0 < pip < pwf:
        _traza_pip(trace, reservoir, fluid, well, objectives, pump_depth, pip, pwf)

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
    # Qué correlación corresponde POR LA FÍSICA, y qué eligió el usuario. Si no
    # eligió nada manda la física, que es el comportamiento histórico.
    metodo_fisica = (
        "poettmann_carpenter" if free_gas_fraction > threshold
        else "hazen_williams"
    )
    elegido = objectives.pressure_loss_method
    if elegido == "poettmann_carpenter":
        # Restricción DURA: el método se levantó con tubing de 2, 2½ y 3 pulg,
        # y elegirlo a mano para otra cañería es pedir un número fuera del
        # rango de la correlación. Los otros tres límites del envelope avisan;
        # éste no, porque el formulario ya no deja elegir otra cosa y llegar
        # acá significa que alguien salteó el contrato.
        from bes.core.multiphase import (
            PC_TUBING_OD_LABELS, tubing_od_is_pc_range,
        )
        if not tubing_od_is_pc_range(well.tubing_od):
            raise ValueError(
                f"Poettmann-Carpenter sólo es aplicable a tubing de 2, 2½ y "
                f"3 pulg (OD {', '.join(PC_TUBING_OD_LABELS)} in). El pozo "
                f"tiene {well.tubing_od:.3f} in: elegí otra cañería o dejá "
                f"que la correlación la decida la fracción de gas."
            )
    metodo = elegido or metodo_fisica
    avisos_metodo: list[str] = []
    if elegido is not None and elegido != metodo_fisica:
        avisos_metodo.append(_aviso_metodo_forzado(
            elegido, metodo_fisica, free_gas_fraction, threshold
        ))

    extra: dict = {}
    if metodo == "poettmann_carpenter":
        friction_method = "poettmann_carpenter"
        # La RGL es la magnitud en la que está declarado el límite de gas del
        # método (1500 scf/bbl). Se emite acá —y no en la verificación del
        # envelope— para que quede en la traza del diseño, que es donde el
        # profesor la va a buscar.
        from bes.core.multiphase import (
            PC_MAX_GLR_SCF_BBL, gas_liquid_ratio,
        )
        wor = fluid.water_cut / (1.0 - fluid.water_cut)
        rgl = gas_liquid_ratio(fluid.gor, fluid.water_cut)
        trace.add(
            "pc_rgl", {"GOR": fluid.gor, "WOR": wor}, rgl,
            context=(
                f"Dentro del rango del método (hasta "
                f"{PC_MAX_GLR_SCF_BBL:,.0f} scf/bbl)."
                if rgl < PC_MAX_GLR_SCF_BBL else
                f"FUERA del rango del método, que vale hasta "
                f"{PC_MAX_GLR_SCF_BBL:,.0f} scf/bbl."
            ),
        )
        tubing_friction, extra = _friction_loss_poettmann_carpenter(
            fluid=fluid,
            well=well,
            surface=surface,
            objectives=objectives,
            pump_depth=pump_depth,
            sg=sg,
            bottom_temp_f=reservoir.reservoir_temp,
        )
        # El gradiente que se muestra es el PROMEDIO del recorrido
        # (Δp_fricción / L), no el de un punto: la fricción se integró tramo
        # por tramo y el gas la carga hacia el cabezal. Se calcula desde
        # `pc_friction_psi`, que es la integral que efectivamente se acumuló,
        # así que la sustitución cierra con el resultado.
        grad_fric_medio = (
            extra["pc_friction_psi"] / pump_depth if pump_depth > 0 else 0.0
        )
        trace.add(
            "friccion_pc",
            {"(dP/dz)_fricción": grad_fric_medio, "L": pump_depth, "SG": sg},
            tubing_friction,
            context=(
                (
                    "Poettmann-Carpenter elegido a mano en el formulario. "
                    if elegido == "poettmann_carpenter" else
                    f"La fracción de gas libre en la admisión "
                    f"({free_gas_fraction:.3f}) supera el umbral "
                    f"({threshold:.2f}), así que la fricción se calcula con "
                    f"P&C. "
                )
                + f"El gradiente es el promedio del recorrido: se integró en "
                  f"{extra['pc_segments']} tramos, y va de "
                  f"{extra['pc_friction_gradient_bottom_psi_ft']:.5f} psi/ft "
                  f"en la bomba a "
                  f"{extra['pc_friction_gradient_top_psi_ft']:.5f} psi/ft en "
                  f"el cabezal, donde el gas ya se expandió."
            ),
        )
    else:
        # --- Rama monofásica: Hazen-Williams o Darcy-Weisbach --------------
        #
        # Las dos coinciden dentro del 2 % mientras el líquido sea poco
        # viscoso, así que el corte se pone donde empiezan a separarse, que es
        # el mismo techo de 5 cp con que el envelope de Poettmann-Carpenter
        # declara su límite viscoso. Por debajo manda Hazen-Williams, que es la
        # que emplea el procedimiento de Brown y con la que se validaron los
        # ejemplos del libro; por encima, Darcy-Weisbach, que es la única de
        # las dos que puede seguir un flujo laminar.
        from bes.core.multiphase import PC_MAX_OIL_VISCOSITY_CP

        mezcla = _viscosidad_de_la_mezcla(fluid, well, pump_depth,
                                          reservoir.reservoir_temp, pip)
        mu_l = mezcla["viscosity_cp"] if mezcla else None
        avisos_metodo.extend(mezcla["warnings"] if mezcla else [])

        usa_dw = (
            elegido == "darcy_weisbach"
            or (elegido is None and mu_l is not None
                and mu_l > PC_MAX_OIL_VISCOSITY_CP)
        )

        if usa_dw and mu_l is not None:
            friction_method = "darcy_weisbach"
            rho_l = sg * 62.4
            dw = friction_loss_darcy_weisbach(
                q_bpd=objectives.target_flow_rate,
                pipe_id_in=well.tubing_id,
                length_ft=pump_depth,
                density_lb_ft3=rho_l,
                viscosity_cp=mu_l,
            )
            tubing_friction = dw["head_ft"]
            extra["friction_reynolds"] = dw["reynolds"]
            extra["friction_regime"] = dw["regimen"]
            extra["friction_factor"] = dw["friction_factor"]
            extra["liquid_viscosity_cp"] = mu_l
            trace.add(
                "friccion_darcy_weisbach",
                {"f": dw["friction_factor"], "L": pump_depth,
                 "d": well.tubing_id / 12.0, "v": dw["velocity_ft_s"],
                 "g": _G_FT_S2},
                tubing_friction,
                context=(
                    f"El líquido producido tiene {mu_l:.1f} cp en la admisión, "
                    f"por encima de los {PC_MAX_OIL_VISCOSITY_CP:.0f} cp a "
                    f"partir de los cuales Hazen-Williams —establecida con agua "
                    f"en régimen turbulento— deja de seguir el comportamiento "
                    f"del fluido. Re = {dw['reynolds']:.0f}, régimen "
                    f"{dw['regimen']}."
                ),
            )
            if dw["transicion"]:
                avisos_metodo.append(
                    f"El número de Reynolds en la tubería ({dw['reynolds']:.0f}) "
                    f"cae en la zona de transición entre el régimen laminar y "
                    f"el turbulento, donde no rige ninguna de las dos leyes de "
                    f"fricción. El factor se interpoló entre ambas: el valor "
                    f"queda acotado, pero su incerteza es mayor que en "
                    f"cualquiera de los dos regímenes."
                )
            if dw["regimen"] == "laminar":
                avisos_metodo.append(
                    f"El flujo en la tubería es LAMINAR (Re = "
                    f"{dw['reynolds']:.0f}). La pérdida por fricción resulta de "
                    f"{tubing_friction:.0f} ft contra los "
                    f"{friction_loss_hazen_williams(objectives.target_flow_rate, well.tubing_id, pump_depth):.0f} ft "
                    f"que daría Hazen-Williams, que no puede representar este "
                    f"régimen. Se adopta Darcy-Weisbach."
                )
        else:
            friction_method = "hazen_williams"
            tubing_friction = friction_loss_hazen_williams(
                q_bpd=objectives.target_flow_rate,
                pipe_id_in=well.tubing_id,
                length_ft=pump_depth,
            )
            if mu_l is not None:
                extra["liquid_viscosity_cp"] = mu_l
            trace.add(
                "friccion_hazen_williams",
                {"C": 120.0, "q": objectives.target_flow_rate * 0.02917,
                 "d": well.tubing_id, "L": pump_depth},
                tubing_friction,
                context=(
                    "Hazen-Williams elegido a mano en el formulario."
                    if elegido == "hazen_williams" else
                    f"La fracción de gas libre en la admisión "
                    f"({free_gas_fraction:.3f}) no supera el umbral "
                    f"({threshold:.2f}), así que el flujo en el tubing se "
                    f"trata como monofásico"
                    + (
                        f", y el líquido tiene {mu_l:.1f} cp, por debajo de los "
                        f"{PC_MAX_OIL_VISCOSITY_CP:.0f} cp a partir de los "
                        f"cuales corresponde Darcy-Weisbach."
                        if mu_l is not None else "."
                    )
                ),
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
        # Qué correspondía por la física y qué se pidió a mano. Se publican los
        # dos: si coinciden, el aviso viene vacío.
        "friction_method_physics": metodo_fisica,
        "friction_method_requested": elegido,
        "pressure_loss_warnings": avisos_metodo,
        **extra,
    }
