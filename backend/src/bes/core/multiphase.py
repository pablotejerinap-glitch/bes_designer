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
Brown, K.E. (1977). "The Technology of Artificial Lift Methods", Vol. 1,
    Tabla 4-7 (carta del factor de fricción de Poettmann & Carpenter).
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

import numpy as np

from bes.core.models import Fluid, Reservoir, WellGeometry
from bes.core.pvt import fluid_properties_at_conditions, standing_pb
from bes.core.ipr import calculate_pwf_for_target_rate

# ---------------------------------------------------------------------------
# Constantes físicas
# ---------------------------------------------------------------------------
_GC = 32.174         # lbm·ft / (lbf·s²) — constante gravitacional
_BBL_FT3 = 5.615     # ft³ por barril
_SEC_DAY = 86400.0   # segundos por día
_PSI_CONV = 144.0    # lbf/ft² por psi — dividir por 144 convierte a psi/ft


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

    Ecuación del gradiente
    ----------------------
        dP/dz  =  ρm · sen(θ) / 144            <- término de gravedad
                + f · ρm · vm² / (2·gc·d·144)  <- término de fricción

    donde
        ρm = ρl · λl + ρg · (1 − λl)     densidad de la mezcla   [lb/ft³]
        λl = vsl / vm                    fracción de líquido sin deslizamiento
        vm = vsl + vsg                   velocidad de la mezcla  [ft/s]
        d  = diámetro interno            [ft]
        gc = 32.174 lbm·ft/(lbf·s²)
        f  = factor de fricción de Fanning (ver abajo)

    Factor de fricción
    ------------------
        N_ρ = ρm · vm · d                grupo tipo Reynolds de P&C
        f   = 0.030 · N_ρ^(−0.19)        ajuste log-log a la carta original
        f   se acota entre 0.005 y 0.065 (rango del gráfico publicado)

    Por qué se devuelven los términos por separado
    ----------------------------------------------
    El TDH ya contabiliza la columna de fluido como "elevación vertical", con el
    SG del líquido. Quien solo quiera reemplazar la pérdida por fricción debe
    tomar ``friction`` y **nunca** ``total``: sumar el total contaría la columna
    hidrostática dos veces.

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

    # --- Factor de fricción de Poettmann & Carpenter ------------------------
    n_rho = max(rho_m * vm * d_ft, 1e-6)
    f_pc = 0.030 * n_rho ** (-0.19)
    f_pc = max(0.005, min(0.065, f_pc))

    # --- Los dos términos del gradiente [psi/ft] ----------------------------
    sin_theta = np.sin(np.radians(angle))
    grad_gravity = rho_m * sin_theta / _PSI_CONV
    grad_friction = f_pc * rho_m * vm ** 2 / (2.0 * _GC * d_ft * _PSI_CONV)

    return {
        "gravity": grad_gravity,
        "friction": grad_friction,
        "total": grad_gravity + grad_friction,
        "mixture_density": rho_m,
        "mixture_velocity": vm,
        "liquid_holdup_noslip": lambda_l,
        "friction_factor": f_pc,
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

        # Tres pasadas correctoras: el PVT depende de la presión buscada
        p_mid = pressures[i]
        for _ in range(3):
            grad = poettmann_carpenter_gradient(
                q_liq=q_liq,
                wc=fluid.water_cut,
                gor=fluid.gor,
                gas_sg=fluid.gas_sg,
                oil_api=fluid.oil_api,
                water_sg=fluid.water_sg,
                p=max(p_mid, 14.7),
                t=t_mid,
                pipe_id=pipe_id,
                angle=90.0,
            )
            dp = grad * dz
            p_next = pressures[i] - dp if going_up else pressures[i] + dp
            p_mid = 0.5 * (pressures[i] + max(p_next, 14.7))

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

    Procedimiento (Brown Vol. 2b, §4.532):
        1. Pwf en las perforaciones, a partir del IPR del reservorio.
        2. Temperatura en la profundidad de la bomba (perfil lineal).
        3. Recorrido de presión hacia arriba, desde las perforaciones hasta la
           admisión, por el espacio anular (se usa el ID del casing).
        4. La presión al final de ese recorrido es el PIP.

    Args:
        reservoir: Reservorio (presión estática, Pb, IPR).
        fluid: Fluido (PVT, GOR, corte de agua).
        well: Geometría del pozo (profundidades, ID de casing, temperaturas).
        pump_setting_depth: Profundidad de la admisión de la bomba [ft TVD].
        target_rate: Caudal bruto de líquido objetivo [STB/d].

    Returns:
        Presión en la admisión de la bomba, PIP [psia].
    """
    pwf = calculate_pwf_for_target_rate(reservoir, target_rate)

    def temp_at(depth: float) -> float:
        """Temperatura interpolada linealmente entre boca de pozo y fondo.

        El extremo de fondo es la temperatura de reservorio: la geometría del
        pozo ya no la duplica.
        """
        frac = depth / max(well.total_depth, 1.0)
        return well.wellhead_temp + frac * (
            reservoir.reservoir_temp - well.wellhead_temp
        )

    _, pressures = pressure_traverse(
        q_liq=target_rate,
        fluid=fluid,
        pipe_id=well.casing_id,
        depth_start=well.perforations_bottom,
        depth_end=pump_setting_depth,
        p_start=pwf,
        t_start=temp_at(well.perforations_bottom),
        t_end=temp_at(pump_setting_depth),
        n_segments=PIP_TRAVERSE_SEGMENTS,
    )
    return float(pressures[-1])


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
        # Sin ensayo: el PVT de P&C resuelve la viscosidad con Beggs-Robinson,
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
    acotado = c["friction_factor"] in (0.005, 0.065)
    trace.add(
        "pc_factor_friccion",
        {"ρ_m": c["mixture_density"], "v_m": c["mixture_velocity"],
         "d": c["pipe_id_ft"]},
        c["friction_factor"],
        context=("El valor quedó acotado al extremo del rango de la carta."
                 if acotado else ""),
    )
    trace.add(
        "pc_gradiente_gravedad",
        {"ρ_m": c["mixture_density"], "θ": angle}, c["gravity"],
    )
    trace.add(
        "pc_gradiente_friccion",
        {"f": c["friction_factor"], "ρ_m": c["mixture_density"],
         "v_m": c["mixture_velocity"], "g_c": _GC, "d": c["pipe_id_ft"]},
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
    from bes.core.viscosity import dead_oil_viscosity_chart

    if fluid.oil_viscosity_dead is not None:
        mu_o = fluid.oil_viscosity_dead
        visc_source = f"ensayo de laboratorio a {fluid.viscosity_temp_ref:.0f} °F"
    else:
        mu_o = dead_oil_viscosity_chart(fluid.oil_api, temp_f)["mu_cp"]
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
