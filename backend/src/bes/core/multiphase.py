"""
Pérdida de carga en flujo multifásico — método de Poettmann & Carpenter (1952).

Este módulo calcula cómo varía la presión del fluido a lo largo del pozo cuando
por la cañería circula una mezcla de líquido y gas. Es la única correlación
multifásica del simulador: todas las pérdidas de carga se calculan por
Poettmann & Carpenter.

Contenido
---------
1. Gradiente de presión en un punto   ->  poettmann_carpenter_components()
2. Integración del gradiente          ->  pressure_traverse()
3. Presión en la admisión de la bomba ->  calculate_pip()
4. Presión en la descarga de la bomba ->  calculate_discharge_pressure()
5. Envelope de aplicabilidad          ->  poettmann_carpenter_applicability()

Referencias
-----------
Poettmann, F.H. & Carpenter, P.G. (1952). "The Multiphase Flow of Gas, Oil and
    Water Through Vertical Flow Strings". API Drilling and Production Practice.
Brown, K.E. y Beggs, H.D. (1977). "The Technology of Artificial Lift Methods",
    Vol. 1, Sección 2.3322: ec. 2.34 y Fig. 2.36 (factor de Poettmann & Carpenter).
Brown, K.E. (1980). "The Technology of Artificial Lift Methods", Vol. 2b,
    Sección 4.532 (cálculo de PIP y presión de descarga).

Unidades (todas las cuentas internas)
-------------------------------------
Presión        psi           Longitud / profundidad   ft
Temperatura    °F            Caudal de superficie     STB/d
Densidad       lb/ft³        Velocidad                ft/s
Viscosidad     cp            Diámetro de cañería      pulgadas (se pasa a ft)
Ángulo         grados (0 = horizontal, 90 = vertical hacia arriba)
"""

from __future__ import annotations

import math

import numpy as np

from bes.core.models import Fluid, Reservoir, WellGeometry
from bes.core.pvt import (
    fluid_properties_at_conditions,
    standing_pb,
    pb_para_pvt,
    standing_rs,
    water_viscosity,
)
from bes.core.ipr import calculate_pwf_for_target_rate

# ---------------------------------------------------------------------------
# Constantes físicas
# ---------------------------------------------------------------------------
_GC = 32.174         # lbm·ft / (lbf·s²) — constante gravitacional
_BBL_FT3 = 5.615     # ft³ por barril
_SEC_DAY = 86400.0   # segundos por día
_PSI_CONV = 144.0    # lbf/ft² por psi — dividir por 144 convierte a psi/ft

# ---------------------------------------------------------------------------
# Factor de pérdida de energía de Poettmann & Carpenter — Brown Vol. 1, Fig. 2.36
# ---------------------------------------------------------------------------
#: Curva de la Fig. 2.36 de Brown y Beggs (1977), Sección 2.3322 (pág. 106),
#: digitalizada sobre el escaneo del libro: pares (Dρv [lb/(ft·s)], f [-]).
#: El f es el de la ec. 2.34 del mismo libro (factor tipo Fanning, el que va
#: con la constante 7,413×10¹⁰). Entre puntos se interpola en escala log-log.
#: Fuera del rango impreso (0,853 a 100) se toma el valor del extremo:
#: criterio del proyecto, el libro no da la curva más allá.
BROWN_FIG_2_36: tuple[tuple[float, float], ...] = (
    (0.853, 80.0), (0.974, 50.0), (1.146, 30.0), (1.298, 20.0), (1.618, 10.0),
    (1.870, 7.0), (2.009, 5.0), (2.387, 3.0), (2.746, 2.0), (2.995, 1.5),
    (3.422, 1.0), (3.882, 0.7), (4.360, 0.5), (5.225, 0.3), (6.009, 0.2),
    (6.714, 0.15), (8.032, 0.1), (9.592, 0.07), (10.883, 0.05),
    (12.518, 0.04), (14.898, 0.03), (19.311, 0.02), (22.211, 0.015),
    (29.285, 0.01), (36.685, 0.007), (45.797, 0.005), (52.497, 0.004),
    (67.581, 0.003), (88.196, 0.002), (100.0, 0.00165),
)
#: Constante de la ec. 2.34 de Brown y Beggs (1977): w en lb/d y d en ft.
BROWN_K_2_34 = 7.413e10


def pc_friction_factor(d_rho_v: float) -> tuple[float, bool]:
    """Factor f de Poettmann & Carpenter leído de la Fig. 2.36 de Brown Vol. 1.

    Args:
        d_rho_v: Numerador del número de Reynolds, Dρv = ρ_m·v_m·d [lb/(ft·s)].
            Es igual a 1,4737×10⁻⁵·M·Q/D de Brown.

    Returns:
        ``(f, fuera_de_rango)``. ``fuera_de_rango`` es True si Dρv cae fuera de
        lo impreso (0,853 a 100) y se tomó el valor del extremo.
    """
    xs = [x for x, _ in BROWN_FIG_2_36]
    if d_rho_v <= xs[0]:
        return BROWN_FIG_2_36[0][1], d_rho_v < xs[0]
    if d_rho_v >= xs[-1]:
        return BROWN_FIG_2_36[-1][1], d_rho_v > xs[-1]
    lx = math.log10(d_rho_v)
    for (x1, f1), (x2, f2) in zip(BROWN_FIG_2_36, BROWN_FIG_2_36[1:]):
        if x1 <= d_rho_v <= x2:
            t = (lx - math.log10(x1)) / (math.log10(x2) - math.log10(x1))
            return 10 ** (math.log10(f1) + t * (math.log10(f2) - math.log10(f1))), False
    raise AssertionError("inalcanzable")


def pc_friction_gradient(f: float, w_lb_d: float, rho_m: float, d_ft: float) -> float:
    """Término de fricción de la ec. 2.34 de Brown y Beggs (1977) [psi/ft].

        (dP/dh)_fric = f·w² / (7,413×10¹⁰·ρ_m·d⁵) / 144
    """
    return f * w_lb_d ** 2 / (BROWN_K_2_34 * rho_m * d_ft ** 5) / _PSI_CONV


# ===========================================================================
# 1. GRADIENTE DE PRESIÓN — Poettmann & Carpenter (1952)
# ===========================================================================

def poettmann_carpenter_components(
    q_liq: float,
    wc: float,
    gor: float,
    gas_sg: float,
    oil_api: float,
    water_sg: float,
    p: float,
    t: float,
    pipe_id: float,
    angle: float = 90.0,
) -> dict:
    """Gradiente de presión de Poettmann & Carpenter, separado en sus dos términos.

    El método trata a la mezcla gas-líquido como **homogénea** (sin deslizamiento
    entre fases): las dos fases viajan a la misma velocidad, de modo que la
    densidad de la mezcla se obtiene ponderando por el caudal in-situ de cada
    una. El factor de fricción es empírico, leído de la carta original de
    Poettmann & Carpenter.

    Ecuación del gradiente (Brown y Beggs, 1977, ec. 2.34)
    -------------------------------------------------------
        dP/dz  =  ρm · sen(θ) / 144                    <- término de gravedad
                + f · w² / (7.413e10 · ρm · d⁵) / 144  <- término de fricción
        w = ρm · vm · A · 86 400   caudal másico [lb/d]

    donde
        ρm = ρl · λl + ρg · (1 − λl)     densidad de la mezcla   [lb/ft³]
        λl = vsl / vm                    fracción de líquido sin deslizamiento
        vm = vsl + vsg                   velocidad de la mezcla  [ft/s]
        d  = diámetro interno            [ft]
        gc = 32.174 lbm·ft/(lbf·s²)
        f  = factor de pérdida de energía de P&C (ver abajo)

    Factor de fricción
    ------------------
        Dρv = ρm · vm · d                numerador del número de Reynolds
        f   = Fig. 2.36 de Brown Vol. 1, digitalizada (:data:`BROWN_FIG_2_36`)

    Por qué se devuelven los términos por separado
    ----------------------------------------------
    El TDH ya contabiliza la columna de fluido como "elevación vertical", con el
    SG del líquido. Quien solo quiera reemplazar la pérdida por fricción debe
    tomar ``friction`` y **nunca** ``total``: sumar el total contaría la columna
    hidrostática dos veces.

    LIMITACIÓN DECLARADA — el término de fricción no es separable
    -------------------------------------------------------------
    Partir el gradiente en dos y usar sólo uno es **una licencia del proyecto,
    no algo que P&C habiliten**, y así se declara en la tesis.

    Beggs (*Production Optimization*, pág. 84) describe cómo se levantó la
    correlación: se midieron **únicamente la presión de superficie y la de
    fondo** y los caudales de 334 pozos fluyentes —la mayoría por debajo de
    500 STB/d—. No se midió hold-up ni se dividieron los pozos en tramos. El
    factor de fricción se despejó **por diferencia**::

        f_TP = 2·g_c·d·(dP/dL)_fricción / (ρ·v²)

    donde ``(dP/dL)_fricción`` es lo que queda después de restar un término de
    elevación calculado con densidad SIN RESBALAMIENTO. Es decir: el "factor de
    fricción" de P&C no es fricción de pared, es un residuo que absorbe todo lo
    que el método desprecia —resbalamiento, patrones de flujo, aceleración— y
    sólo cierra **acompañado del término de elevación con el que se lo despejó**.

    Acá se lo suma, en cambio, a una elevación calculada con el SG del líquido.
    Son dos modelos de densidad distintos, y el residuo de uno queda pegado a la
    elevación del otro. El error que eso introduce no está acotado por ninguna
    fuente del proyecto.

    La salida correcta sería Hagedorn & Brown, que Beggs presenta en la página
    siguiente justamente porque sí mide hold-up. Queda fuera del alcance: cambiar
    la correlación del tubing mueve el PIP, la presión de descarga y el TDH de
    todos los casos con gas, incluido el #3B ya validado contra el impreso.

    Args:
        q_liq: Caudal bruto de líquido en superficie [STB/d].
        wc: Corte de agua [0-1].
        gor: Relación gas-petróleo total de producción [scf/STB].
        gas_sg: Gravedad específica del gas (aire = 1.0).
        oil_api: Gravedad del petróleo [°API].
        water_sg: Gravedad específica del agua de formación.
        p: Presión en el punto de cálculo [psia].
        t: Temperatura en el punto de cálculo [°F].
        pipe_id: Diámetro interno de la cañería [pulgadas].
        angle: Inclinación respecto de la horizontal [°]. 90 = vertical.

    Returns:
        dict con ``gravity``, ``friction`` y ``total`` en [psi/ft], más los
        intermedios: ``mixture_density`` [lb/ft³], ``mixture_velocity`` [ft/s],
        ``liquid_holdup_noslip`` [-] y ``friction_factor`` [-].

    Raises:
        ValueError: Si q_liq <= 0 o pipe_id <= 0.
    """
    if q_liq <= 0:
        raise ValueError(f"q_liq must be > 0, got {q_liq}")
    if pipe_id <= 0:
        raise ValueError(f"pipe_id must be > 0, got {pipe_id}")

    # --- Propiedades PVT a la presión y temperatura del punto ---------------
    fluid = _make_fluid(oil_api, wc, gor, gas_sg, water_sg, p)
    props = fluid_properties_at_conditions(fluid, p, t)

    rho_l = props["oil_density"] * (1.0 - wc) + props["water_density"] * wc
    rho_g = props["gas_density"]

    # --- Velocidades superficiales ------------------------------------------
    area = _pipe_area(pipe_id)
    vsl, vsg = _superficial_velocities(q_liq, wc, gor, props, area)

    vm = vsl + vsg                 # velocidad de la mezcla       [ft/s]
    lambda_l = vsl / vm            # fracción de líquido sin deslizamiento
    d_ft = pipe_id / 12.0          # diámetro interno             [ft]

    # --- Densidad de la mezcla (sin deslizamiento) --------------------------
    rho_m = rho_l * lambda_l + rho_g * (1.0 - lambda_l)

    # --- Factor de Poettmann & Carpenter (Brown Vol. 1, Fig. 2.36) ----------
    n_rho = max(rho_m * vm * d_ft, 1e-6)
    f_pc, fuera = pc_friction_factor(n_rho)
    w = rho_m * vm * area * _SEC_DAY          # caudal másico [lb/d]

    # --- Los dos términos del gradiente [psi/ft] (Brown, ec. 2.34) ----------
    sin_theta = np.sin(np.radians(angle))
    grad_gravity = rho_m * sin_theta / _PSI_CONV
    grad_friction = pc_friction_gradient(f_pc, w, rho_m, d_ft)

    return {
        "gravity": grad_gravity,
        "friction": grad_friction,
        "total": grad_gravity + grad_friction,
        "mixture_density": rho_m,
        "mixture_velocity": vm,
        "liquid_holdup_noslip": lambda_l,
        "friction_factor": f_pc,
        "d_rho_v": n_rho,
        "mass_rate_lb_d": w,
        "friction_factor_out_of_chart": fuera,
        # Intermedios: los consume poettmann_carpenter_trace() para poder
        # mostrar la cadena completa sin recalcularla —recalcular sería abrir
        # la puerta a que la traza y la cuenta se separen—.
        "area_ft2": area,
        "pipe_id_ft": d_ft,
        "liquid_density": rho_l,
        "gas_density": rho_g,
        "v_superficial_liquid": vsl,
        "v_superficial_gas": vsg,
        "angle_deg": angle,
    }


def poettmann_carpenter_gradient(
    q_liq: float,
    wc: float,
    gor: float,
    gas_sg: float,
    oil_api: float,
    water_sg: float,
    p: float,
    t: float,
    pipe_id: float,
    angle: float = 90.0,
) -> float:
    """Gradiente de presión total (gravedad + fricción) de Poettmann & Carpenter.

    Atajo de :func:`poettmann_carpenter_components` cuando solo interesa la suma.
    Los argumentos son idénticos.

    Returns:
        Gradiente dP/dz [psi/ft]. Positivo = la presión aumenta hacia abajo.
    """
    return poettmann_carpenter_components(
        q_liq, wc, gor, gas_sg, oil_api, water_sg, p, t, pipe_id, angle
    )["total"]


# ===========================================================================
# 2. INTEGRACIÓN DEL GRADIENTE A LO LARGO DEL POZO
# ===========================================================================

#: Factor C de Hazen-Williams para acero de diseño. 130 sería caño nuevo; se
#: adopta 120 por ser el criterio con que se dimensiona, no el de estreno.
HW_C_FACTOR = 120.0


def friccion_monofasica(
    q_res_bpd: float,
    pipe_id: float,
    rho_l: float,
    mu_l_cp: float,
    sg_l: float,
) -> tuple[float, dict]:
    """Gradiente de fricción de UNA sola fase líquida [psi/ft].

    Poettmann & Carpenter es una correlación **multifásica**: correlaciona el
    gradiente de una mezcla gas-líquido sin deslizamiento, y su factor de
    fricción es un residuo empírico que absorbe el resbalamiento y los patrones
    de flujo. Sin gas libre no hay nada de eso que absorber, y aplicarla a una
    sola fase es usar una correlación fuera de su objeto.

    Se elige con el MISMO criterio que el tubing (``tdh.calculate_tdh``):

        μ > 5 cp    ->  Darcy-Weisbach con Reynolds
        μ <= 5 cp   ->  Hazen-Williams

    El caudal que entra es el de FONDO, no el de superficie: es el volumen que
    realmente circula por el anular a esa presión y temperatura.

    Args:
        q_res_bpd: Caudal de líquido a condiciones de fondo [bbl/d].
        pipe_id: Diámetro interno del conducto [in].
        rho_l: Densidad del líquido a condiciones de fondo [lb/ft³].
        mu_l_cp: Viscosidad del líquido [cp].
        sg_l: Gravedad específica del líquido, para pasar pies a psi.

    Returns:
        ``(gradiente_psi_ft, diagnostico)``. El diagnóstico trae el método
        elegido, el número de Reynolds, el régimen y la velocidad.
    """
    d_ft = pipe_id / 12.0
    area = np.pi / 4.0 * d_ft ** 2
    v = q_res_bpd * _BBL_FT3 / _SEC_DAY / area if area > 0 else 0.0
    mu_lb_ft_s = max(mu_l_cp, 1e-9) * 6.7197e-4
    reynolds = rho_l * v * d_ft / mu_lb_ft_s if mu_lb_ft_s > 0 else 0.0

    if mu_l_cp > PC_MAX_OIL_VISCOSITY_CP:
        if reynolds < 2000.0:
            f = 64.0 / reynolds if reynolds > 0 else 0.0
            regimen = "laminar"
        else:
            # Swamee-Jain para cañería lisa.
            f = 0.25 / (math.log10(5.74 / reynolds ** 0.9)) ** 2
            regimen = "turbulento"
        grad = f * rho_l * v * v / (2.0 * _GC * d_ft * _PSI_CONV)
        metodo = "darcy_weisbach"
    else:
        # Hazen-Williams devuelve pies de líquido cada 100 ft de cañería; se
        # pasa a psi/ft con la gravedad específica.
        q_gpm = q_res_bpd * 42.0 / 1440.0
        ft_por_100 = (
            0.2083 * (100.0 / HW_C_FACTOR) ** 1.852
            * q_gpm ** 1.852 / pipe_id ** 4.8655
        )
        grad = ft_por_100 / 100.0 * sg_l / 2.31
        # Factor de Darcy EQUIVALENTE: el que daría este mismo gradiente. No es
        # un dato de Hazen-Williams —que no usa factor de fricción— sino la
        # forma de publicar el resultado en las mismas unidades que el resto de
        # la traza, y de poder compararlo con el de Poettmann & Carpenter.
        denom = rho_l * v * v / (2.0 * _GC * d_ft * _PSI_CONV)
        f = grad / denom if denom > 0 else 0.0
        regimen = "turbulento" if reynolds >= 2000.0 else "laminar"
        metodo = "hazen_williams"

    return grad, {
        "metodo": metodo,
        "reynolds": reynolds,
        "regimen": regimen,
        "velocidad_ft_s": v,
        "friction_factor": f,
    }


def gradiente_del_recorrido(
    q_liq: float,
    fluid: "Fluid",
    p: float,
    t: float,
    pipe_id: float,
    angle: float = 90.0,
) -> tuple[float, dict]:
    """Gradiente de presión del recorrido, con el método que corresponda.

    **El fusible es el GAS LIBRE.** Poettmann & Carpenter correlaciona una
    mezcla gas-líquido; lo que la hace multifásica es la presencia de una fase
    gaseosa, no que haya dos líquidos. Petróleo y agua sin gas —o con todo el
    gas todavía en solución, por encima del punto de burbuja— son una sola fase
    líquida y se resuelven con el gradiente monofásico::

        hay gas libre   ->  Poettmann & Carpenter
        no hay          ->  ρ_l/144  +  fricción monofásica

    El término de gravedad es el mismo por los dos caminos: sin gas P&C da
    λ_l = 1 y ρ_m = ρ_l. Lo que cambia es la fricción, que pasa a calcularse
    con Hazen-Williams o Darcy-Weisbach según la viscosidad, igual que en el
    tubing.

    Args:
        q_liq: Caudal bruto de líquido en superficie [STB/d].
        fluid: PVT y composición del fluido.
        p: Presión del punto [psia].
        t: Temperatura del punto [°F].
        pipe_id: Diámetro interno del conducto [in].
        angle: Inclinación respecto de la horizontal [°].

    Returns:
        ``(gradiente_total_psi_ft, diagnostico)``.
    """
    comps = poettmann_carpenter_components(
        q_liq=q_liq, wc=fluid.water_cut, gor=fluid.gor, gas_sg=fluid.gas_sg,
        oil_api=fluid.oil_api, water_sg=fluid.water_sg, p=max(p, 14.7), t=t,
        pipe_id=pipe_id, angle=angle,
    )

    # ¿Hay gas libre? Se decide con el punto de burbuja QUE CARGÓ EL USUARIO,
    # no con el que P&C se calcula puertas adentro. ``_make_fluid`` estima el
    # suyo con Standing a 160 °F fijos, y con él un pozo por encima de su
    # burbuja real puede aparecer con gas libre —o al revés—. Para elegir el
    # método manda el dato del pozo.
    pb = pb_para_pvt(fluid.bubble_point_pressure, fluid.gor, t, fluid.oil_api, fluid.gas_sg)
    rs = min(
        standing_rs(max(p, 14.7), t, fluid.oil_api, fluid.gas_sg, pb)
        if pb > 0 else fluid.gor,
        fluid.gor,
    )
    hay_gas_libre = (
        fluid.water_cut < 1.0 and max(fluid.gor - rs, 0.0) > 0.0
    )
    if hay_gas_libre:
        return comps["total"], {**comps, "metodo": "poettmann_carpenter"}

    # --- Una sola fase líquida ------------------------------------------
    props = fluid_properties_at_conditions(
        _make_fluid(fluid.oil_api, fluid.water_cut, fluid.gor,
                    fluid.gas_sg, fluid.water_sg, p), max(p, 14.7), t,
    )
    wc = fluid.water_cut
    mu_l = props["mu_oil"] * (1.0 - wc) + water_viscosity(t) * wc
    sg_l = _oil_sg_local(fluid.oil_api) * (1.0 - wc) + fluid.water_sg * wc
    q_res = q_liq * ((1.0 - wc) * props["bo"] + wc * props["bw"])

    fric, diag = friccion_monofasica(
        q_res, pipe_id, comps["mixture_density"], mu_l, sg_l,
    )
    total = comps["gravity"] + fric
    return total, {
        **comps, "friction": fric, "total": total,
        "viscosidad_liquido_cp": mu_l, **diag,
    }


def _oil_sg_local(api: float) -> float:
    """Gravedad específica del petróleo de tanque."""
    return 141.5 / (131.5 + api)


def pressure_traverse(
    q_liq: float,
    fluid: Fluid,
    pipe_id: float,
    depth_start: float,
    depth_end: float,
    p_start: float,
    t_start: float,
    t_end: float,
    n_segments: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """Integra el gradiente de presión entre dos profundidades.

    El gradiente no es constante: depende de la presión, que es justamente lo
    que se busca. Por eso el tramo se divide en *n_segments* segmentos y en cada
    uno se evalúa el gradiente en el punto medio, repitiendo el cálculo tres
    veces para que la presión usada en el PVT sea consistente con la resultante.

    En cada segmento:
        P(i+1) = P(i) − dP/dz · Δz     si el recorrido va hacia arriba
        P(i+1) = P(i) + dP/dz · Δz     si el recorrido va hacia abajo

    La temperatura se interpola linealmente entre *t_start* y *t_end*.

    Nota sobre el ángulo: las cuentas siempre usan θ = 90° (flujo vertical
    ascendente, que es como el fluido circula realmente). Lo único que cambia
    según el sentido del recorrido es el signo con que se acumula el gradiente.
    Usar θ = −90° para bajar sería incorrecto: invertiría la gravedad.

    Args:
        q_liq: Caudal bruto de líquido [STB/d].
        fluid: Objeto Fluid (API, GOR, corte de agua, gravedades, Pb).
        pipe_id: Diámetro interno del conducto [pulgadas].
        depth_start: Profundidad del nodo inicial [ft TVD].
        depth_end: Profundidad del nodo final [ft TVD].
        p_start: Presión conocida en depth_start [psia].
        t_start: Temperatura en depth_start [°F].
        t_end: Temperatura en depth_end [°F].
        n_segments: Cantidad de segmentos de integración. Por defecto 50.

    Returns:
        Tupla ``(profundidades, presiones)``, ambos arrays de longitud
        ``n_segments + 1``. La presión nunca baja de 14.7 psia.
    """
    depths = np.linspace(depth_start, depth_end, n_segments + 1)
    pressures = np.empty(n_segments + 1)
    pressures[0] = p_start

    dz = abs(depth_end - depth_start) / n_segments   # largo del segmento [ft]
    going_up = depth_end < depth_start

    for i in range(n_segments):
        # Punto medio del segmento: profundidad y temperatura
        d_mid = 0.5 * (depths[i] + depths[i + 1])
        t_frac = (d_mid - depth_start) / (depth_end - depth_start + 1e-12)
        t_mid = t_start + t_frac * (t_end - t_start)

        # P2 supuesta = P1; se itera hasta que P2 calculada = P2 supuesta
        # (diferencia < 0,01 psi), como en Brown y Beggs (1977), Apéndice C.12.
        p_next = pressures[i]
        for _ in range(50):
            p_mid = 0.5 * (pressures[i] + max(p_next, 14.7))
            grad, _diag = gradiente_del_recorrido(
                q_liq=q_liq,
                fluid=fluid,
                p=max(p_mid, 14.7),
                t=t_mid,
                pipe_id=pipe_id,
                angle=90.0,
            )
            dp = grad * dz
            p_calc = pressures[i] - dp if going_up else pressures[i] + dp
            listo = abs(p_calc - p_next) < 0.01
            p_next = p_calc
            if listo:
                break

        pressures[i + 1] = max(p_next, 14.7)

    return depths, pressures


# ===========================================================================
# 3. PRESIONES DE ADMISIÓN Y DESCARGA DE LA BOMBA
# ===========================================================================

#: Tramos en que se parte el recorrido anular perforaciones -> admisión. Vive
#: acá y no como número suelto porque la traza de fórmulas lo publica: quien
#: audita el PIP tiene que poder saber en cuántos pasos se integró.
PIP_TRAVERSE_SEGMENTS = 20


def calculate_pip(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    pump_setting_depth: float,
    target_rate: float,
) -> float:
    """Presión en la admisión de la bomba (PIP) para un caudal dado.

    Un solo método para toda la herramienta, el de Brown (Vol. 2b, Ejemplo #1C,
    pág. 68), el mismo que usa el método para pozos con gas::

        PIP = Pwf − 0,433 · SG · (D_punzados − D_bomba)

    1. Pwf en la base de los punzados, a partir de la IPR.
    2. SG de la mezcla en el fondo (Pwf y temperatura de reservorio) por balance
       de masa (Brown Vol. 2b, Sección 4.53102, paso 5).
    3. Gradiente constante 0,433 · SG sobre la columna punzados-bomba. La
       fricción en el casing se desprecia: es menor al 0,3 % del gradiente.

    Returns:
        PIP [psi].
    """
    from bes.core.gas_paso_a_paso import paso2a_pvt, paso2bc_mezcla, paso3_pip

    pwf = calculate_pwf_for_target_rate(reservoir, target_rate)
    pvt, _ = paso2a_pvt(pwf, reservoir.reservoir_temp, fluid.oil_api, fluid.gas_sg,
                        fluid.water_sg, fluid.gor)
    mezcla, _ = paso2bc_mezcla(target_rate, fluid.water_cut, fluid.gor, fluid.gas_sg,
                               fluid.water_sg, pvt)
    pip, _ = paso3_pip(pwf, mezcla["sg"], well.perforations_bottom, pump_setting_depth)
    if pip <= 0.0:
        # La columna sobre la bomba no alcanza a equilibrar la Pwf: la admisión
        # queda por encima del nivel dinámico y no tendría fluido.
        raise ValueError(
            f"La presión en la admisión llega a 0 psig: la bomba a {pump_setting_depth:.0f} ft queda "
            f"por encima del nivel dinámico para {target_rate:.0f} STB/d (Pwf {pwf:.1f} psi). "
            f"Hay que bajarla o reducir el caudal.")
    return float(pip)


def calculate_discharge_pressure(
    fluid: Fluid,
    tubing_id: float,
    pump_depth: float,
    wellhead_pressure: float,
    target_rate: float,
    t_pump: float,
    t_wellhead: float,
) -> float:
    """Presión que la bomba debe entregar a la descarga.

    Se arranca en la boca de pozo, con la presión de cabeza conocida, y se baja
    por el tubing hasta la profundidad de la bomba (Brown Vol. 2b, §4.532).

    Args:
        fluid: Fluido.
        tubing_id: Diámetro interno del tubing [pulgadas].
        pump_depth: Profundidad de la descarga de la bomba [ft TVD].
        wellhead_pressure: Presión de cabeza de tubing, THP [psia].
        target_rate: Caudal bruto de líquido [STB/d].
        t_pump: Temperatura a la profundidad de la bomba [°F].
        t_wellhead: Temperatura en boca de pozo [°F].

    Returns:
        Presión de descarga de la bomba [psia].
    """
    _, pressures = pressure_traverse(
        q_liq=target_rate,
        fluid=fluid,
        pipe_id=tubing_id,
        depth_start=0.0,
        depth_end=pump_depth,
        p_start=wellhead_pressure,
        t_start=t_wellhead,
        t_end=t_pump,
        n_segments=50,
    )
    return float(pressures[-1])


# ===========================================================================
# 4. FUNCIONES AUXILIARES
# ===========================================================================

def _pipe_area(id_in: float) -> float:
    """Área de flujo de la cañería, a partir del diámetro interno [in] -> [ft²]."""
    return np.pi / 4.0 * (id_in / 12.0) ** 2


def _superficial_velocities(
    q_liq: float,
    wc: float,
    gor: float,
    props: dict,
    area_ft2: float,
) -> tuple[float, float]:
    """Velocidades superficiales de líquido y gas en el punto de cálculo.

    "Superficial" significa: la velocidad que tendría esa fase si ocupara ella
    sola toda la sección de la cañería. Se obtiene pasando los caudales de
    superficie a condiciones de fondo con los factores volumétricos del PVT.

        q_o,fondo = q_o,sup · Bo                    [bbl/d]
        q_w,fondo = q_w,sup · Bw                    [bbl/d]
        q_g,fondo = q_o,sup · (GOR − Rs) · Bg       [bbl/d]  (solo gas libre)

        vs = q_fondo · 5.615 / 86400 / área         [ft/s]

    Args:
        q_liq: Caudal bruto de líquido en superficie [STB/d].
        wc: Corte de agua [0-1].
        gor: GOR total de producción [scf/STB].
        props: Diccionario PVT de fluid_properties_at_conditions().
        area_ft2: Área de flujo de la cañería [ft²].

    Returns:
        Tupla ``(vsl, vsg)`` — velocidades superficiales de líquido y gas [ft/s].
    """
    q_oil_sc = q_liq * (1.0 - wc)
    q_wat_sc = q_liq * wc

    q_liq_res = q_oil_sc * props["bo"] + q_wat_sc * props["bw"]      # bbl/d
    free_gas_scf = q_oil_sc * max(gor - props["rs"], 0.0)            # scf/d
    q_gas_res = free_gas_scf * props["bg"]                           # bbl/d

    vsl = q_liq_res * _BBL_FT3 / _SEC_DAY / area_ft2
    vsg = q_gas_res * _BBL_FT3 / _SEC_DAY / area_ft2
    return max(vsl, 1e-8), max(vsg, 0.0)


def _make_fluid(
    oil_api: float,
    wc: float,
    gor: float,
    gas_sg: float,
    water_sg: float,
    p: float,
) -> Fluid:
    """Arma un objeto Fluid a partir de los escalares que reciben las correlaciones.

    La presión de burbuja se estima con la correlación de Standing para que el
    módulo PVT distinga correctamente el régimen sobre y bajo saturación.
    """
    try:
        pb = standing_pb(rs=gor, t=160.0, api=oil_api, gas_sg=gas_sg)
    except ValueError:
        pb = p   # si la correlación no aplica, se toma la presión del punto

    return Fluid(
        oil_api=oil_api,
        water_cut=wc,
        gor=max(gor, 0.0),
        gas_sg=gas_sg,
        water_sg=water_sg,
        # Sin ensayo: el PVT de P&C lee la viscosidad de las láminas 4L de Brown,
        # así que un valor acá no se usaría. None lo dice; un placeholder
        # numérico haría creer que hay un dato medido.
        oil_viscosity_dead=None,
        viscosity_temp_ref=None,
        bubble_point_pressure=pb,
        h2s_content=0.0,
        co2_content=0.0,
        sand_production=False,
    )


# --------------------------------------------------------------------------
# Traza de fórmulas
# --------------------------------------------------------------------------

def poettmann_carpenter_trace(
    q_liq: float,
    wc: float,
    gor: float,
    oil_api: float,
    gas_sg: float,
    water_sg: float,
    pipe_id: float,
    p: float,
    t: float,
    angle: float = 90.0,
) -> list[dict]:
    """La cadena completa de Poettmann & Carpenter en un punto, paso por paso.

    Sigue el patrón de :func:`bes.core.ipr.ipr_trace`: función aparte, para no
    ensuciar la firma de las funciones puras que usa todo el motor. **No
    recalcula nada**: llama a :func:`poettmann_carpenter_components` y lee sus
    intermedios, de modo que la traza no puede separarse de la cuenta.

    Args:
        q_liq: Caudal bruto de líquido en superficie [STB/d].
        wc: Corte de agua [0-1].
        gor: GOR total de producción [scf/STB].
        oil_api: Gravedad del petróleo [°API].
        gas_sg: Gravedad específica del gas [-].
        water_sg: Gravedad específica del agua [-].
        pipe_id: Diámetro interno de la cañería [in].
        p: Presión del punto [psia].
        t: Temperatura del punto [°F].
        angle: Ángulo respecto de la horizontal [°]. 90 = vertical.

    Returns:
        Lista de dicts de :class:`bes.core.formulas.Formula`, en el orden en que
        se ejecutan.
    """
    from bes.core.formulas import FormulaTrace

    c = poettmann_carpenter_components(
        q_liq=q_liq, wc=wc, gor=gor, oil_api=oil_api, gas_sg=gas_sg,
        water_sg=water_sg, pipe_id=pipe_id, p=p, t=t, angle=angle,
    )
    props = fluid_properties_at_conditions(
        _make_fluid(oil_api, wc, gor, gas_sg, water_sg, p), p, t
    )

    q_oil_sc = q_liq * (1.0 - wc)
    q_liq_res = q_oil_sc * props["bo"] + q_liq * wc * props["bw"]
    q_gas_res = q_oil_sc * max(gor - props["rs"], 0.0) * props["bg"]

    trace = FormulaTrace()
    trace.add("pc_area", {"d": pipe_id}, c["area_ft2"])
    trace.add(
        "pc_q_liquido_fondo",
        {"q_o": q_oil_sc, "Bo": props["bo"], "q_w": q_liq * wc,
         "Bw": props["bw"]},
        q_liq_res,
    )
    trace.add(
        "pc_q_gas_fondo",
        {"q_o": q_oil_sc, "GOR": gor, "Rs": props["rs"], "Bg": props["bg"]},
        q_gas_res,
        context=(
            f"A {p:,.0f} psia el gas en solución ({props['rs']:.0f} scf/STB) ya "
            f"cubre todo el GOR: no queda gas libre."
            if gor <= props["rs"] else
            f"A {p:,.0f} psia hay {gor - props['rs']:.0f} scf/STB de gas libre."
        ),
    )
    trace.add(
        "pc_velocidad_superficial",
        {"q_fondo": q_liq_res, "A": c["area_ft2"]},
        c["v_superficial_liquid"],
        label="Velocidad superficial del líquido",
    )
    trace.add(
        "pc_velocidad_superficial",
        {"q_fondo": q_gas_res, "A": c["area_ft2"]},
        c["v_superficial_gas"],
        label="Velocidad superficial del gas",
    )
    trace.add(
        "pc_holdup_sin_deslizamiento",
        {"v_sl": c["v_superficial_liquid"], "v_m": c["mixture_velocity"]},
        c["liquid_holdup_noslip"],
    )
    trace.add(
        "pc_densidad_mezcla",
        {"ρ_l": c["liquid_density"], "λ_l": c["liquid_holdup_noslip"],
         "ρ_g": c["gas_density"]},
        c["mixture_density"],
    )
    trace.add(
        "pc_factor_friccion",
        {"ρ_m": c["mixture_density"], "v_m": c["mixture_velocity"],
         "d": c["pipe_id_ft"]},
        c["friction_factor"],
        context=(f"Dρv = {c['d_rho_v']:.2f} cae fuera de la Fig. 2.36 (0,853 a "
                 f"100): se tomó el valor del extremo."
                 if c["friction_factor_out_of_chart"] else ""),
    )
    trace.add(
        "pc_caudal_masico",
        {"ρ_m": c["mixture_density"], "v_m": c["mixture_velocity"],
         "A": c["area_ft2"]},
        c["mass_rate_lb_d"],
    )
    trace.add(
        "pc_gradiente_gravedad",
        {"ρ_m": c["mixture_density"], "θ": angle}, c["gravity"],
    )
    trace.add(
        "pc_gradiente_friccion",
        {"f": c["friction_factor"], "w": c["mass_rate_lb_d"],
         "ρ_m": c["mixture_density"], "d": c["pipe_id_ft"]},
        c["friction"],
    )
    trace.add(
        "pc_gradiente_total",
        {"(dP/dz)_grav": c["gravity"], "(dP/dz)_fric": c["friction"]},
        c["total"],
        context=(
            f"La fricción es el {100.0 * c['friction'] / c['total']:.2f} % del "
            f"gradiente en este punto: en un pozo vertical manda el peso de la "
            f"columna."
            if c["total"] > 0 else ""
        ),
    )
    return trace.as_list()


# ===========================================================================
# 5. ENVELOPE DE APLICABILIDAD DE POETTMANN & CARPENTER
# ===========================================================================
#
# Las hipótesis del método y el rango de pozos para el que fue levantado. Están
# acá, en el mismo módulo que la correlación, para que nadie pueda usar una sin
# leer las otras.
#
# Hipótesis:
#
#   1. Gas, petróleo y agua son un ÚNICO fluido que se mueve en conjunto.
#   2. Factor de pérdida de carga CONSTANTE en toda la tubería. Es el gran
#      problema del método.
#   3. Flujo turbulento en toda la cañería: ignora los patrones de flujo.
#   4. La aceleración es despreciable.
#   5. El hold-up y el resbalamiento no se tienen en cuenta — quedan absorbidos
#      dentro del factor de fricción empírico.
#   6. Los efectos de viscosidad se desprecian.
#
# Las hipótesis 2, 3, 5 y 6 son las que explican los cuatro límites de abajo.
#
# Fuente: apuntes de cátedra aportados por Pablo (agosto 2026). NO agregar acá
# límites de otra procedencia sin que él los verifique.

#: Diámetros de tubing para los que se levantó la correlación: los nominales
#: 2 pulg, 2½ pulg y 3 pulg, que en la tabla API/Tenaris son estos OD [in].
PC_TUBING_OD_IN: tuple[float, ...] = (2.375, 2.875, 3.5)

#: Los mismos, como se rotulan en el catálogo.
PC_TUBING_OD_LABELS: tuple[str, ...] = ("2 3/8", "2 7/8", "3 1/2")

#: Tolerancia al comparar un OD contra la lista [in].
PC_TUBING_OD_TOL = 1e-3

#: Viscosidad máxima del petróleo [cp]. Por encima el método no vale: los
#: efectos viscosos son justamente lo que la hipótesis 6 desprecia.
PC_MAX_OIL_VISCOSITY_CP = 5.0

#: Relación gas-líquido máxima [scf/bbl].
PC_MAX_GLR_SCF_BBL = 1500.0

#: Caudal mínimo de líquido [bbl/d]. Por debajo el resbalamiento gobierna, y
#: la hipótesis 5 lo ignora.
PC_MIN_LIQUID_RATE_BPD = 400.0


def gas_liquid_ratio(gor: float, water_cut: float) -> float:
    """Relación gas-líquido (RGL) a partir del GOR y el corte de agua.

    El GOR se mide **por barril de petróleo**; la RGL, **por barril de líquido**
    (petróleo + agua). En un pozo con agua no son lo mismo, y el envelope de
    Poettmann & Carpenter está declarado en RGL::

        RGL = GOR / (1 + WOR)        con WOR = Wc / (1 − Wc)

    Como ``1 + WOR = 1/(1 − Wc)``, la cuenta se reduce a ``RGL = GOR · (1 − Wc)``,
    pero se deja escrita en la forma de la cátedra porque es la que se audita.

    Args:
        gor: Relación gas-petróleo de producción [scf/STB]. Debe ser >= 0.
        water_cut: Corte de agua [0-1). Debe ser < 1: un pozo que produce sólo
            agua no tiene barriles de petróleo con los que definir el GOR.

    Returns:
        Relación gas-líquido [scf/bbl].

    Raises:
        ValueError: Si gor < 0 o water_cut queda fuera de [0, 1).
    """
    if gor < 0:
        raise ValueError(f"gor must be >= 0, got {gor}")
    if not (0.0 <= water_cut < 1.0):
        raise ValueError(f"water_cut must be in [0, 1), got {water_cut}")

    wor = water_cut / (1.0 - water_cut)
    return gor / (1.0 + wor)


def tubing_od_is_pc_range(tubing_od: float) -> bool:
    """¿El OD del tubing es uno de los tres para los que vale P&C?

    Args:
        tubing_od: Diámetro exterior del tubing [in].

    Returns:
        ``True`` si coincide con 2 3/8, 2 7/8 o 3 1/2 dentro de la tolerancia.
    """
    return any(abs(tubing_od - od) <= PC_TUBING_OD_TOL for od in PC_TUBING_OD_IN)


def poettmann_carpenter_applicability(
    fluid: Fluid,
    well: WellGeometry,
    q_liq: float,
    temp_f: float,
) -> dict:
    """Verifica el pozo contra el envelope declarado de Poettmann & Carpenter.

    Los cuatro límites del método, verificados uno por uno::

        tubing   2 pulg, 2½ pulg o 3 pulg (OD 2.375 / 2.875 / 3.5 in)
        mu_o     < 5 cp — petróleos livianos
        RGL      < 1500 scf/bbl
        q_liq    > 400 bbl/d

    **No falla ni corrige nada**: devuelve el veredicto y los avisos, y quien
    llama decide. La única restricción dura del proyecto es la del tubing, y se
    aplica más arriba —en el formulario y en el contrato— para que no se pueda
    elegir una cañería fuera de rango con P&C seleccionado a mano.

    La viscosidad sale del ensayo de laboratorio si hay uno cargado; si no, se
    lee de la Fig. 4L(2) con la °API y la temperatura del punto, que es el mismo
    camino que usa el procedimiento de Riling. Es el dato que decide el segundo
    límite, así que se declara de dónde salió.

    Args:
        fluid: Fluido producido — °API, corte de agua, GOR y viscosidad medida.
        well: Geometría del pozo — OD del tubing.
        q_liq: Caudal bruto de líquido en superficie [bbl/d].
        temp_f: Temperatura a la que evaluar la viscosidad [°F]. Normalmente la
            de admisión de la bomba.

    Returns:
        dict con:

        - ``applicable``: ``True`` si los cuatro límites se cumplen.
        - ``checks``: una entrada por límite, con ``item``, ``value``,
          ``limit``, ``ok`` y ``message``.
        - ``warnings``: los ``message`` de los límites que NO se cumplen.
        - ``viscosity_cp`` / ``viscosity_source``: el valor usado y su origen.
        - ``glr_scf_bbl``: la RGL calculada.
    """
    from bes.core.pvt import oil_viscosity_brown

    # Misma regla que en todo el programa: el ensayo vale sólo dentro de la
    # tolerancia de temperatura; si no, se lee la Fig. 4L(2).
    mu_o, _, origen = oil_viscosity_brown(fluid, temp_f, 0.0)
    if origen == "medido":
        visc_source = f"ensayo de laboratorio a {fluid.viscosity_temp_ref:.0f} °F"
    else:
        visc_source = f"Fig. 4L(2) con {fluid.oil_api:.1f} °API a {temp_f:.0f} °F"

    glr = gas_liquid_ratio(fluid.gor, fluid.water_cut)
    tubing_ok = tubing_od_is_pc_range(well.tubing_od)
    etiquetas = ", ".join(PC_TUBING_OD_LABELS)

    checks = [
        {
            "item": "tubing",
            "value": well.tubing_od,
            "limit": f"OD {etiquetas} in",
            "ok": tubing_ok,
            "message": (
                f"Poettmann-Carpenter se levantó con tubing de 2, 2½ y 3 pulg "
                f"(OD {etiquetas} in). El pozo tiene {well.tubing_od:.3f} in: "
                f"fuera del rango del método."
            ),
        },
        {
            "item": "viscosidad",
            "value": mu_o,
            "limit": f"< {PC_MAX_OIL_VISCOSITY_CP:.0f} cp",
            "ok": mu_o < PC_MAX_OIL_VISCOSITY_CP,
            "message": (
                f"Poettmann-Carpenter vale para petróleos livianos, de menos de "
                f"{PC_MAX_OIL_VISCOSITY_CP:.0f} cp. Acá la viscosidad es "
                f"{mu_o:.1f} cp ({visc_source}): el método desprecia justamente "
                f"los efectos viscosos, así que la pérdida de carga sale corta."
            ),
        },
        {
            "item": "rgl",
            "value": glr,
            "limit": f"< {PC_MAX_GLR_SCF_BBL:.0f} scf/bbl",
            "ok": glr < PC_MAX_GLR_SCF_BBL,
            "message": (
                f"La relación gas-líquido es {glr:,.0f} scf/bbl y el método vale "
                f"hasta {PC_MAX_GLR_SCF_BBL:,.0f}. Con tanto gas el "
                f"resbalamiento entre fases gobierna, y P&C no lo representa."
            ),
        },
        {
            "item": "caudal",
            "value": q_liq,
            "limit": f"> {PC_MIN_LIQUID_RATE_BPD:.0f} bbl/d",
            "ok": q_liq > PC_MIN_LIQUID_RATE_BPD,
            "message": (
                f"El caudal de líquido es {q_liq:,.0f} bbl/d y el método vale "
                f"por encima de {PC_MIN_LIQUID_RATE_BPD:.0f}. A caudal bajo la "
                f"mezcla no va turbulenta en toda la cañería y el resbalamiento "
                f"deja de ser despreciable."
            ),
        },
    ]

    return {
        "applicable": all(c["ok"] for c in checks),
        "checks": checks,
        "warnings": [c["message"] for c in checks if not c["ok"]],
        "viscosity_cp": mu_o,
        "viscosity_source": visc_source,
        "glr_scf_bbl": glr,
    }
