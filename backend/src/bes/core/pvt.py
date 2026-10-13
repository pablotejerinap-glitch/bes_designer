"""
PVT — Propiedades del petróleo, el gas y el agua según presión y temperatura.

PVT quiere decir Presión-Volumen-Temperatura. Un fluido de reservorio **no
ocupa el mismo volumen abajo que en superficie**: a 3000 psi el petróleo lleva
gas disuelto y está hinchado; al subir a la superficie el gas se libera y el
petróleo se contrae. Este módulo pone números a ese comportamiento, porque todo
el resto del diseño necesita saber cuánto volumen real está bombeando la bomba.

Las cuatro magnitudes que resuelve
----------------------------------
    Rs   Gas disuelto en el petróleo    ¿cuánto gas trae adentro? [scf/STB]
    Bo   Factor de volumen del petróleo ¿cuánto se hincha?        [bbl/STB]
    Bg   Factor de volumen del gas      ¿cuánto se comprime?      [bbl/scf]
    Bw   Factor de volumen del agua     ¿cuánto se hincha?        [bbl/STB]

Más las densidades y las viscosidades que se desprenden de ellas.

La presión de burbuja parte el problema en dos
----------------------------------------------
La **presión de burbuja (Pb)** es aquella a la que el gas empieza a salir de la
solución, igual que al destapar una botella de gaseosa::

    P >= Pb   subsaturado: TODO el gas está disuelto. Rs queda fijo en el GOR
              de producción y no hay gas libre.
    P <  Pb   saturado: parte del gas ya se liberó. Rs baja con la presión y
              aparece gas libre, que es el que complica el bombeo.

Contenido
---------
1. Constantes físicas y auxiliares internos
2. Standing: gas disuelto (Rs), presión de burbuja (Pb) y volumen de aceite (Bo)
3. Gas: factor de compresibilidad z y volumen (Bg)
4. Agua: volumen (Bw)
5. Viscosidades del petróleo (crudo muerto y crudo vivo)
6. Función compuesta: todas las propiedades de una vez
7. PVT medido de laboratorio, que gana sobre las correlaciones
8. Traza de fórmulas para auditar el cálculo

Nomenclatura
------------
    P       Presión                                          [psia]
    T       Temperatura                                      [°F]
    Pb      Presión de burbuja                               [psia]
    Rs      Gas en solución (solution GOR)                   [scf/STB]
    GOR     Relación gas-petróleo de producción              [scf/STB]
    Bo      Factor de volumen de formación del petróleo      [bbl/STB]
    Bg      Factor de volumen de formación del gas           [bbl/scf]
    Bw      Factor de volumen de formación del agua          [bbl/STB]
    z       Factor de compresibilidad del gas                [-]
    API     Gravedad del petróleo                            [°API]
    γo      Gravedad específica del petróleo (agua = 1)      [-]
    γg      Gravedad específica del gas (aire = 1)           [-]
    μ       Viscosidad                                       [cp]
    STB     Stock Tank Barrel: barril medido en superficie
    scf     Standard Cubic Foot: pie cúbico en condiciones estándar

Referencias
-----------
Standing, M.B. (1947). "A Pressure-Volume-Temperature Correlation for Mixtures
    of California Oils and Gases". API Drilling and Production Practice.
    — Rs, Pb y Bo.
Papay, J., en Takács (2018), ec. 4.26 — factor z del gas.
Beggs, H.D. & Robinson, J.R. (1975). "Estimating the Viscosity of Crude Oil
    Systems". JPT — viscosidades.
McCain, W.D. (1990). "The Properties of Petroleum Fluids", 2ª ed., PennWell
    — Bw del agua.
Ahmed, T. (2010). "Reservoir Engineering Handbook", 4ª ed. — de donde se toman
    las formas publicadas de las ecuaciones (2-54, 2-76, 2-125).
"""

from __future__ import annotations

import math

import numpy as np

from bes.core.models import Fluid

# ===========================================================================
# 1. CONSTANTES FISICAS Y AUXILIARES INTERNOS
# ===========================================================================

_BBL_TO_FT3 = 5.615      #: Pies cúbicos que entran en un barril [ft³/bbl]
_RHO_WATER_SC = 62.4     #: Densidad del agua pura en superficie [lb/ft³]
_RHO_AIR_SC = 0.0764     #: Densidad del aire seco a 14.7 psia y 60 °F [lb/scf]


def _oil_sg(api: float) -> float:
    """Convierte grados API a gravedad específica (agua = 1).

    Es la definición del grado API, no una correlación::

        γo = 141.5 / (131.5 + API)

    Un crudo de 10 °API pesa igual que el agua (γo = 1.0); cuanto más alto el
    API, más liviano el petróleo.

    Args:
        api: Gravedad del petróleo [°API].

    Returns:
        Gravedad específica del petróleo [-].
    """
    return 141.5 / (131.5 + api)


def _pseudo_critical_standing(gas_sg: float) -> tuple[float, float]:
    """Presión y temperatura pseudo-críticas del gas natural seco (Standing).

    Un gas natural es una mezcla, así que no tiene un punto crítico propio: se
    usan valores «pseudo» calculados a partir de su gravedad específica. Hacen
    falta para entrar al factor de compresibilidad z.

    Válida para 0.55 <= γg <= 0.75.

    Args:
        gas_sg: Gravedad específica del gas (aire = 1.0).

    Returns:
        Tupla (Ppc [psia], Tpc [°R]).
    """
    ppc = 677.0 + 15.0 * gas_sg - 37.5 * gas_sg ** 2
    tpc = 168.0 + 325.0 * gas_sg - 12.5 * gas_sg ** 2
    return ppc, tpc


# ===========================================================================
# 2. STANDING — GAS DISUELTO (Rs), PRESION DE BURBUJA (Pb) Y VOLUMEN (Bo)
# ===========================================================================

def standing_rs(p: float, t: float, api: float, gas_sg: float, pb: float) -> float:
    """Gas disuelto en el petróleo a una presión dada — Standing (1947).

    Responde: de todo el gas que produce el pozo, ¿cuánto está **disuelto** en
    el petróleo a esta presión? El resto es gas libre.

    Por encima de la presión de burbuja el petróleo está subsaturado: todo el
    gas sigue adentro, así que Rs queda anclado en su valor de burbuja. Por
    debajo, el gas se empieza a liberar::

        Rs = γg · [(P/18.2 + 1.4) · 10^(0.0125·API − 0.00091·T)]^1.2048

    El exponente 1.2048 es 1/0.83, y es lo que mantiene esta ecuación
    consistente con la de presión de burbuja (:func:`standing_pb`): una es la
    inversa de la otra.

    Args:
        p: Presión [psia]. Debe ser >= 0.
        t: Temperatura [°F]. Debe ser > 0.
        api: Gravedad del petróleo [°API].
        gas_sg: Gravedad específica del gas (aire = 1.0). Debe ser > 0.
        pb: Presión de burbuja [psia]. Debe ser > 0.

    Returns:
        Gas en solución [scf/STB].

    Raises:
        ValueError: Si algún argumento cae fuera de su rango válido.

    Referencia:
        Standing (1947), API Drilling and Production Practice.
    """
    if p < 0:
        raise ValueError(f"p must be >= 0, got {p}")
    if t <= 0:
        raise ValueError(f"t must be > 0 °F, got {t}")
    if gas_sg <= 0:
        raise ValueError(f"gas_sg must be > 0, got {gas_sg}")
    if pb <= 0:
        raise ValueError(f"pb must be > 0, got {pb}")

    p_eff = min(p, pb)
    exponent = 0.0125 * api - 0.00091 * t
    return gas_sg * ((p_eff / 18.2 + 1.4) * 10.0 ** exponent) ** 1.2048


def standing_pb(rs: float, t: float, api: float, gas_sg: float) -> float:
    """Presión de burbuja — correlación de Standing.

    Es la presión a la que el gas **empieza a salir** de la solución. Sirve para
    convertir un GOR de producción medido en una presión de burbuja, que es el
    dato que parte en dos toda la IPR y todo el PVT::

        Pb = 18.2 · [(Rs/γg)^0.83 · 10^a − 1.4]
        a  = 0.00091·T[°F] − 0.0125·API

    Args:
        rs: Gas en solución en el punto de burbuja, que es igual al GOR total
            de producción [scf/STB]. Debe ser > 0.
        t: Temperatura de reservorio [°F]. Debe ser > 0.
        api: Gravedad del petróleo [°API].
        gas_sg: Gravedad específica del gas (aire = 1.0). Debe ser > 0.

    Returns:
        Presión de burbuja [psia].

    Raises:
        ValueError: Si rs <= 0, t <= 0, gas_sg <= 0, o si el resultado da
            negativo — combinación de datos físicamente inconsistente, que pasa
            con crudos muy pesados o GOR muy bajos.

    Referencia:
        Standing (1947); forma publicada en Ahmed (2010), ec. 2-76.
    """
    if rs <= 0:
        raise ValueError(f"rs must be > 0, got {rs}")
    if t <= 0:
        raise ValueError(f"t must be > 0 °F, got {t}")
    if gas_sg <= 0:
        raise ValueError(f"gas_sg must be > 0, got {gas_sg}")

    # Ahmed Eq. 2-76: Pb = 18.2·[(Rs/γg)^0.83·10^a − 1.4], a = 0.00091·T − 0.0125·API
    a = 0.00091 * t - 0.0125 * api
    pb = 18.2 * ((rs / gas_sg) ** 0.83 * 10.0 ** a - 1.4)
    if pb <= 0:
        raise ValueError(
            f"Computed Pb = {pb:.1f} psia ≤ 0. Check API, T, gas_sg inputs "
            f"(very heavy oil or very low GOR can produce inconsistent results)."
        )
    return pb

def pb_para_pvt(pb_dato: float, gor: float, t: float, api: float, gas_sg: float) -> float:
    """Presión de burbuja con que se evalúa el PVT [psia].

    Si el usuario cargó la Pb, manda el dato. Si la dejó en 0 (vacía) y el pozo
    produce gas, se estima con Standing a partir del GOR (Ahmed ec. 2-76): una
    Pb nula con GOR > 0 no tiene sentido físico, y tratarla como «todo el gas
    disuelto» daba 0 % de gas libre a cualquier presión. Devuelve 0 cuando no
    hay gas (GOR = 0) o cuando Standing da Pb <= 0 (GOR tan bajo que el gas
    queda disuelto a cualquier presión).
    """
    if pb_dato and pb_dato > 0:
        return pb_dato
    if gor <= 0:
        return 0.0
    try:
        return standing_pb(gor, t, api, gas_sg)
    except ValueError:
        return 0.0



def standing_bo(rs: float, t: float, api: float, gas_sg: float) -> float:
    """Factor de volumen del petróleo (Bo) — Standing (1947).

    Cuántos barriles ocupa **en el fondo** el petróleo que en superficie mide un
    barril. Siempre es mayor que 1: abajo el crudo está caliente y con gas
    disuelto, así que está hinchado::

        F  = Rs · (γg/γo)^0.5 + 1.25·T
        Bo = 0.9759 + 0.000120 · F^1.2

    donde γo = 141.5 / (131.5 + API) es la gravedad específica del petróleo en
    el tanque.

    Es el factor que convierte el caudal de superficie (STB/d, lo que se vende)
    en el caudal real que tiene que mover la bomba abajo.

    Args:
        rs: Gas en solución en la condición de interés [scf/STB]. Debe ser >= 0.
        t: Temperatura [°F]. Debe ser > 0.
        api: Gravedad del petróleo [°API].
        gas_sg: Gravedad específica del gas (aire = 1.0). Debe ser > 0.

    Returns:
        Factor de volumen del petróleo [bbl/STB]. Típicamente 1.0 a 2.0.

    Raises:
        ValueError: Si rs < 0, t <= 0 o gas_sg <= 0.

    Referencia:
        Standing (1947), API Drilling and Production Practice.
    """
    if rs < 0:
        raise ValueError(f"rs must be >= 0, got {rs}")
    if t <= 0:
        raise ValueError(f"t must be > 0 °F, got {t}")
    if gas_sg <= 0:
        raise ValueError(f"gas_sg must be > 0, got {gas_sg}")

    oil_sg = _oil_sg(api)
    f = rs * (gas_sg / oil_sg) ** 0.5 + 1.25 * t
    return 0.9759 + 0.00012 * f ** 1.2


# ===========================================================================
# 3. GAS — FACTOR DE COMPRESIBILIDAD (z) Y VOLUMEN (Bg)
# ===========================================================================

def gas_z_factor(p: float, t: float, gas_sg: float) -> float:
    """Factor de compresibilidad del gas (z) — Papay, explícito.

    z mide cuánto se aparta el gas real del ideal (z = 1). Se entra con la
    presión y la temperatura pseudorreducidas, calculadas con las
    pseudocríticas de Standing (:func:`_pseudo_critical_standing`)::

        z = 1 − 3,52·Ppr / 10^(0,9813·Tpr) + 0,274·Ppr² / 10^(0,8157·Tpr)

    Es una sola cuenta, sin iteración.

    Referencia:
        Papay, en Takács (2018), ec. 4.26 (pág. 169).
    """
    if p <= 0:
        raise ValueError(f"p must be > 0 for z-factor calculation, got {p}")
    if gas_sg <= 0:
        raise ValueError(f"gas_sg must be > 0, got {gas_sg}")
    ppc, tpc = _pseudo_critical_standing(gas_sg)
    ppr = p / ppc
    tpr = (t + 460.0) / tpc
    z = 1.0 - 3.52 * ppr / 10.0 ** (0.9813 * tpr) + 0.274 * ppr ** 2 / 10.0 ** (0.8157 * tpr)
    return max(0.05, z)


def gas_bg(p: float, t: float, z: float) -> float:
    """Factor de volumen del gas (Bg).

    Cuántos barriles ocupa **en el fondo** un pie cúbico estándar de gas. Como
    el gas se comprime muchísimo, Bg es un número chiquito y **va con 1/P**::

        Bg = 0.005035 · z · T[°R] / P   [bbl/scf]

    Sale de la ley de los gases reales con la conversión de unidades incluida
    (1 bbl = 5.615 ft³; la constante contempla las condiciones estándar de
    14.65 psia y 60 °F).

    Que Bg vaya con 1/P es la razón por la que el método de incrementos de
    presión evalúa cada tramo en sus **dos extremos** y promedia: el valor en el
    punto medio no es el promedio de los extremos.

    Args:
        p: Presión [psia]. Debe ser > 0.
        t: Temperatura [°F].
        z: Factor de compresibilidad del gas [-]. Debe ser > 0.

    Returns:
        Factor de volumen del gas [bbl/scf].

    Raises:
        ValueError: Si p <= 0 o z <= 0.

    Referencia:
        Ahmed (2010), "Reservoir Engineering Handbook", 4ª ed., ec. 2-54.
    """
    if p <= 0:
        raise ValueError(f"p must be > 0, got {p}")
    if z <= 0:
        raise ValueError(f"z must be > 0, got {z}")
    return 0.005035 * z * (t + 460.0) / p


# ===========================================================================
# 4. AGUA — FACTOR DE VOLUMEN (Bw)
# ===========================================================================

def water_bw(p: float, t: float) -> float:
    """Factor de volumen del agua (Bw) — McCain, para agua sin gas.

    Lo mismo que Bo pero para el agua de formación: cuántos barriles ocupa abajo
    el agua que en superficie mide uno. Se hincha mucho menos que el petróleo
    —anda entre 1.00 y 1.07— porque casi no disuelve gas::

        Bw = A1 + A2·P + A3·P²
        Ai = a1 + a2·T + a3·T²      (T en °F)

    con los coeficientes tabulados para agua libre de gas.

    Args:
        p: Presión [psia]. Debe ser >= 0.
        t: Temperatura [°F]. Debe ser > 0.

    Returns:
        Factor de volumen del agua [bbl/STB]. Típicamente 1.00 a 1.07.

    Raises:
        ValueError: Si p < 0 o t <= 0.

    Referencia:
        McCain (1990), "The Properties of Petroleum Fluids", 2ª ed.;
        reproducida en Ahmed (2010), ec. 2-125.
    """
    if p < 0:
        raise ValueError(f"p must be >= 0, got {p}")
    if t <= 0:
        raise ValueError(f"t must be > 0 °F, got {t}")
    # Ahmed Eq. 2-125 — gas-free water coefficients (Ai = a1 + a2·T + a3·T², T in °F)
    a1 = 0.9947 + 5.8e-6 * t + 1.02e-6 * t ** 2
    a2 = -4.228e-6 + 1.8376e-8 * t - 6.77e-11 * t ** 2
    a3 = 1.3e-10 - 1.3855e-12 * t + 4.285e-15 * t ** 2
    return a1 + a2 * p + a3 * p ** 2


def water_viscosity(t: float) -> float:
    """Viscosidad del agua de formación — Brill y Beggs (1978).

    Depende casi por completo de la temperatura; la presión y la salinidad la
    mueven poco frente a esa dependencia::

        mu_w = exp( 1.003 − 1.479e-2·T + 1.982e-5·T² )      (T en °F)

    Hace falta para la viscosidad de la MEZCLA de líquido producido, que es la
    que gobierna la fricción en la tubería cuando el flujo es monofásico. En un
    pozo de corte de agua alto —que en esta aplicación son la mayoría— la
    mezcla es prácticamente agua, y tratarla con la viscosidad del petróleo
    sobrestimaría groseramente la pérdida de carga.

    **No corrige por salinidad**: el modelo de fluido lleva la gravedad
    específica del agua pero no su composición, de modo que aplicar una
    corrección por sales exigiría un dato que no se tiene. El agua de formación
    salada es algo más viscosa que la dulce, así que el valor resulta una cota
    inferior; la diferencia es menor frente a la incerteza del modelo de mezcla
    descripto en :func:`bes.core.tdh.liquid_mixture_viscosity`.

    Args:
        t: Temperatura [°F]. Debe ser > 0.

    Returns:
        Viscosidad dinámica del agua [cp]. Del orden de 1.1 cp a 60 °F y de
        0.3 cp a 200 °F.

    Raises:
        ValueError: Si t <= 0.

    Referencia:
        Brill y Beggs (1978); forma publicada en Ahmed (2010), ec. 2-127
        (pág. 125).
    """
    if t <= 0:
        raise ValueError(f"t must be > 0 °F, got {t}")
    return math.exp(1.003 - 1.479e-2 * t + 1.982e-5 * t ** 2)


# ===========================================================================
# 5. VISCOSIDADES DEL PETROLEO
# ===========================================================================
#
# OJO — estas dos correlaciones son del PVT general. El procedimiento de crudos
# viscosos de Riling NO las usa: lee las láminas 4L(1) y 4L(2) del libro, que
# están digitalizadas en `viscosity.py`. Ver .claude/rules/domain.md.

def oil_viscosity_brown(fluid, t: float, rs: float) -> tuple[float, float, str]:
    """Viscosidad del crudo muerto y saturado con las láminas de Brown.

    Es la **única** fuente de viscosidad del crudo de la herramienta: la misma
    que usa el procedimiento de Riling (Brown, 1980, Apéndice 4L). Antes el PVT
    general usaba Beggs-Robinson, que no vale por debajo de 16 °API, y la
    herramienta tenía dos valores distintos para la misma propiedad.

    Crudo muerto: el dato de ensayo si se midió a menos de
    ``VISCOSITY_TEMP_TOLERANCE_F`` de ``t``; si no, la Fig. 4L(2). Crudo
    saturado: la Fig. 4L(1) con el gas en solución.

    Args:
        fluid: Fluido producido (°API y viscosidad medida opcional).
        t: Temperatura de evaluación [°F].
        rs: Gas en solución a esa condición [scf/STB].

    Returns:
        (μ_od [cp], μ_ob [cp], origen del crudo muerto: "medido" o "lamina").
    """
    from bes.core.viscosity import (
        VISCOSITY_TEMP_TOLERANCE_F,
        dead_oil_viscosity_chart,
        gas_saturated_viscosity_chart,
    )
    if t <= 0:
        raise ValueError(f"t must be > 0 °F, got {t}")
    medida = getattr(fluid, "oil_viscosity_dead", None)
    t_ref = getattr(fluid, "viscosity_temp_ref", None)
    if medida is not None and t_ref is not None and abs(t_ref - t) <= VISCOSITY_TEMP_TOLERANCE_F:
        mu_od, origen = float(medida), "medido"
    else:
        mu_od, origen = dead_oil_viscosity_chart(fluid.oil_api, t)["mu_cp"], "lamina"
    mu_ob = gas_saturated_viscosity_chart(mu_od, max(rs, 0.0))["mu_cp"]
    return mu_od, mu_ob, origen


# ===========================================================================
# 6. FUNCION COMPUESTA — TODAS LAS PROPIEDADES DE UNA VEZ
# ===========================================================================

def fluid_properties_at_conditions(fluid: Fluid, p: float, t: float) -> dict:
    """Todas las propiedades PVT del fluido a una presión y temperatura dadas.

    Es la puerta de entrada que usa el resto del motor: se le pasa el fluido y
    un punto (P, T) del pozo, y devuelve todo lo que hace falta para saber qué
    está bombeando la bomba en ese punto.

    El gas en solución se resuelve según de qué lado de la burbuja estemos:
    por encima de Pb se ancla al GOR de producción medido (está todo disuelto),
    y por debajo se calcula con Standing. Las densidades salen de un **balance
    de masa sobre un barril de líquido de superficie**, que es lo que garantiza
    que la masa se conserve al cambiar de presión.

    Args:
        fluid: Fluido, con °API, GOR, corte de agua y gravedades específicas.
        p: Presión a la que se evalúan las propiedades [psia]. Debe ser > 0.
        t: Temperatura [°F]. Debe ser > 0.

    Returns:
        dict con estas claves:

        =====================  =============================================
        Clave                  Qué es [unidad]
        =====================  =============================================
        rs                     Gas en solución [scf/STB]
        bo                     Factor de volumen del petróleo [bbl/STB]
        bg                     Factor de volumen del gas [bbl/scf]
        bw                     Factor de volumen del agua [bbl/STB]
        mu_oil                 Viscosidad del crudo vivo [cp]
        oil_density            Densidad del petróleo + gas disuelto [lb/ft³]
        water_density          Densidad del agua de formación [lb/ft³]
        gas_density            Densidad del gas libre [lb/ft³]
        mixture_density        Densidad de la mezcla completa [lb/ft³]
        free_gas               Fracción volumétrica de gas libre a P,T [-]
        =====================  =============================================

    Raises:
        ValueError: Si p <= 0 o t <= 0.
    """
    if p <= 0:
        raise ValueError(f"p must be > 0, got {p}")
    if t <= 0:
        raise ValueError(f"t must be > 0 °F, got {t}")

    pb = pb_para_pvt(fluid.bubble_point_pressure, fluid.gor, t, fluid.oil_api, fluid.gas_sg)
    oil_sg = _oil_sg(fluid.oil_api)
    wc = fluid.water_cut

    # --- Gas en solución ---------------------------------------------------
    # Arriba de la burbuja está TODO disuelto, así que Rs es el GOR medido. Por
    # debajo se calcula con Standing, acotado al GOR: el reservorio no puede
    # tener más gas disuelto que el que produce.
    if pb > 0 and p >= pb:
        rs = fluid.gor           # Subsaturado: todo el gas está disuelto
    elif pb > 0:
        rs = min(standing_rs(p, t, fluid.oil_api, fluid.gas_sg, pb), fluid.gor)
    else:
        rs = fluid.gor           # Sin Pb: crudo muerto o subsaturado

    bo = standing_bo(rs, t, fluid.oil_api, fluid.gas_sg)
    bw = water_bw(p, t)

    z = gas_z_factor(p, t, fluid.gas_sg)
    bg = gas_bg(p, t, z)

    mu_dead, mu_live, _ = oil_viscosity_brown(fluid, t, rs)

    # --- Densidades en el fondo [lb/ft³] ------------------------------------
    # Petróleo + su gas disuelto, por barril de reservorio. Se divide por Bo
    # porque el crudo está hinchado: la misma masa ocupa más volumen.
    rho_oil = (_RHO_WATER_SC * oil_sg + 0.0136 * rs * fluid.gas_sg) / bo
    # Agua por barril de reservorio (0.0136 = _RHO_AIR_SC / _BBL_TO_FT3)
    rho_water = _RHO_WATER_SC * fluid.water_sg / bw
    # Gas libre en condiciones de fondo, por ley de los gases reales.
    # El 2.70 sale de la conversión de unidades.
    rho_gas = 2.70 * fluid.gas_sg * p / (z * (t + 460.0))

    # --- Volúmenes por cada STB de líquido de superficie --------------------
    # Todo se refiere a UN barril de líquido medido arriba, que es la unidad en
    # la que se vende y la que el usuario carga como caudal objetivo.
    free_gas_scf = max(fluid.gor - rs, 0.0)   # gas libre por STB de petróleo
    v_oil   = (1.0 - wc) * bo                 # bbl de petróleo, en el fondo
    v_water = wc * bw                         # bbl de agua, en el fondo
    v_gas   = (1.0 - wc) * free_gas_scf * bg  # bbl de gas libre, en el fondo
    total_v = v_oil + v_water + v_gas
    free_gas_frac = v_gas / total_v if total_v > 0.0 else 0.0

    # --- Densidad de la mezcla [lb/ft³] — por balance de masa ---------------
    # Se suma la masa de cada fase y se divide por el volumen total. Hacerlo por
    # masa (y no promediando densidades) es lo que conserva el invariante.
    mass_oil   = (1.0 - wc) * (
        _RHO_WATER_SC * oil_sg * _BBL_TO_FT3     # stock-tank oil
        + _RHO_AIR_SC * rs * fluid.gas_sg         # dissolved gas
    )
    mass_water = wc * _RHO_WATER_SC * fluid.water_sg * _BBL_TO_FT3
    mass_gas   = (1.0 - wc) * free_gas_scf * _RHO_AIR_SC * fluid.gas_sg

    total_mass    = mass_oil + mass_water + mass_gas   # [lb]
    total_vol_ft3 = total_v * _BBL_TO_FT3              # [ft³]
    rho_mix = total_mass / total_vol_ft3 if total_vol_ft3 > 0.0 else 0.0

    return {
        "rs":               rs,
        "bo":               bo,
        "bg":               bg,
        "bw":               bw,
        "mu_oil":           mu_live,
        "oil_density":      rho_oil,
        "water_density":    rho_water,
        "gas_density":      rho_gas,
        "mixture_density":  rho_mix,
        "free_gas":         free_gas_frac,
    }


def mixture_specific_gravity(fluid: Fluid, p: float, t: float) -> float:
    """Gravedad específica de la mezcla petróleo/agua/gas a P y T.

    Calcula la densidad de la mezcla con
    :func:`fluid_properties_at_conditions` y la divide por la del agua pura en
    condiciones estándar (62.4 lb/ft³).

    Args:
        fluid: Fluido producido.
        p: Presión [psia]. Debe ser > 0.
        t: Temperatura [°F]. Debe ser > 0.

    Returns:
        Gravedad específica de la mezcla [-], respecto del agua dulce.
    """
    props = fluid_properties_at_conditions(fluid, p, t)
    return props["mixture_density"] / _RHO_WATER_SC


# ===========================================================================
# TABLA PVT MEDIDA — tiene prioridad sobre las correlaciones
# ===========================================================================
#
# Una correlación es un ajuste estadístico sobre cientos de crudos que no son
# el nuestro. Un análisis PVT de laboratorio es el fluido del pozo. Cuando el
# dato medido existe, manda; la correlación queda de respaldo para las
# propiedades que la tabla no publica.
#
# Cada valor que sale de acá viaja con su ORIGEN (`sources`), porque en la
# tesis hay que poder decir de dónde salió cada número. Los tres orígenes son:
#
#     "pvt"          interpolado de la tabla de laboratorio
#     "correlacion"  calculado con Standing / Papay / láminas 4L de Brown
#     "supuesto"     valor fijado a mano, sin respaldo experimental
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field   # noqa: E402  (sección auto-contenida)

#: Propiedades que una tabla PVT puede publicar y este módulo sabe consumir.
PVT_TABLE_FIELDS = ("rs", "bo", "bg", "bw", "z", "mu_oil")

#: Orígenes posibles de un valor PVT, de mayor a menor jerarquía.
PVT_SOURCE_TABLE = "pvt"
PVT_SOURCE_CORRELATION = "correlacion"
PVT_SOURCE_ASSUMED = "supuesto"


@dataclass(frozen=True)
class PVTPoint:
    """Una fila del análisis PVT: las propiedades medidas a una presión.

    Los campos son **opcionales** porque un informe de laboratorio rara vez
    publica las seis columnas. Lo que falte se completa con la correlación y
    queda marcado como tal en ``sources``.

    Args:
        pressure: Presión de la fila [psia]. Debe ser > 0.
        rs: Gas en solución [scf/STB].
        bo: Factor volumétrico del petróleo [rb/STB].
        bg: Factor volumétrico del gas [bbl/scf].
        bw: Factor volumétrico del agua [bbl/STB].
        z: Factor de compresibilidad del gas [-].
        mu_oil: Viscosidad del petróleo vivo [cp].
    """

    pressure: float
    rs: float | None = None
    bo: float | None = None
    bg: float | None = None
    bw: float | None = None
    z: float | None = None
    mu_oil: float | None = None

    def __post_init__(self) -> None:
        if self.pressure <= 0:
            raise ValueError(f"pressure must be > 0, got {self.pressure}")


@dataclass
class PVTTable:
    """Análisis PVT de laboratorio: filas ordenadas por presión.

    Interpola **linealmente** entre filas y no extrapola: fuera del rango
    medido devuelve ``None`` para todas las propiedades, de modo que el
    resolvedor caiga a la correlación en vez de inventar un valor. Extrapolar
    un PVT es exactamente el tipo de dato falso que el capítulo 25 del pliego
    prohíbe.

    Args:
        points: Filas del informe. Se ordenan solas por presión.
        source: De dónde sale la tabla — va textual a los reportes.
            Ej.: ``"PVT experimental pozo LLL-1001, informe 2024-03"``.
        temperature_f: Temperatura del ensayo [°F]. Informativa: si difiere
            mucho de la de evaluación, :func:`resolve_pvt` avisa.

    Raises:
        ValueError: Si no hay al menos dos filas, o si hay presiones repetidas.
    """

    points: list[PVTPoint]
    source: str = "PVT experimental"
    temperature_f: float | None = None
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError(
                f"PVTTable necesita al menos 2 filas para interpolar, "
                f"recibió {len(self.points)}"
            )
        self.points = sorted(self.points, key=lambda pt: pt.pressure)
        presiones = [pt.pressure for pt in self.points]
        if len(set(presiones)) != len(presiones):
            raise ValueError("PVTTable tiene presiones repetidas")

    @property
    def pressure_range(self) -> tuple[float, float]:
        """Presión mínima y máxima medidas [psia]."""
        return self.points[0].pressure, self.points[-1].pressure

    def covers(self, p: float) -> bool:
        """¿La presión *p* cae dentro del rango medido?"""
        lo, hi = self.pressure_range
        return lo <= p <= hi

    def at(self, p: float) -> dict[str, float | None]:
        """Interpola las propiedades a la presión *p*.

        Returns:
            dict con las claves de :data:`PVT_TABLE_FIELDS`. Cada una vale
            ``None`` si la tabla no la publica o si *p* cae fuera del rango.
        """
        if not self.covers(p):
            return {campo: None for campo in PVT_TABLE_FIELDS}

        # Fila exacta, o el par que encierra a p.
        lo = max((pt for pt in self.points if pt.pressure <= p),
                 key=lambda pt: pt.pressure)
        hi = min((pt for pt in self.points if pt.pressure >= p),
                 key=lambda pt: pt.pressure)

        if lo.pressure == hi.pressure:
            return {campo: getattr(lo, campo) for campo in PVT_TABLE_FIELDS}

        peso = (p - lo.pressure) / (hi.pressure - lo.pressure)
        salida: dict[str, float | None] = {}
        for campo in PVT_TABLE_FIELDS:
            v_lo = getattr(lo, campo)
            v_hi = getattr(hi, campo)
            # Sólo se interpola si LAS DOS filas publican la propiedad.
            salida[campo] = (
                v_lo + peso * (v_hi - v_lo)
                if v_lo is not None and v_hi is not None
                else None
            )
        return salida


#: Diferencia de temperatura a partir de la cual se avisa que la tabla PVT
#: está medida lejos de la condición evaluada. Bo y Rs dependen de T, así que
#: una tabla levantada a otra temperatura deja de ser el fluido del problema.
PVT_TEMP_TOLERANCE_F = 20.0


def resolve_pvt(
    p: float,
    t: float,
    fluid: Fluid,
    table: "PVTTable | None" = None,
) -> dict:
    """Rs, Bo, Bg, Bw y Z a P y T, con el origen de cada valor.

    Jerarquía del pliego (§5): **tabla de laboratorio > correlación**. Para
    cada propiedad por separado, porque un informe puede publicar Rs y Bo pero
    no Bg.

    Rs se acota al GOR total del pozo: no puede haber más gas disuelto que el
    que el pozo produce, ni siquiera si la tabla lo dice.

    Args:
        p: Presión [psia]. Debe ser > 0.
        t: Temperatura [°F].
        fluid: Fluido — aporta GOR, °API, SG del gas y presión de burbuja.
        table: Análisis PVT medido. ``None`` = sólo correlaciones.

    Returns:
        dict con ``rs``, ``bo``, ``bg``, ``bw``, ``z``, más:
          - ``sources``   dict propiedad → origen (``"pvt"`` / ``"correlacion"``)
          - ``warnings``  lista de avisos (tabla fuera de rango, T distinta…)

    Raises:
        ValueError: Si p <= 0.
    """
    if p <= 0:
        raise ValueError(f"p must be > 0, got {p}")

    medido = table.at(p) if table is not None else {c: None for c in PVT_TABLE_FIELDS}
    origenes: dict[str, str] = {}
    avisos: list[str] = []

    if table is not None:
        if not table.covers(p):
            lo, hi = table.pressure_range
            avisos.append(
                f"La tabla PVT ({table.source}) cubre {lo:.0f}–{hi:.0f} psia y "
                f"se evaluó a {p:.0f} psia: fuera de rango. No se extrapola — "
                f"se usan correlaciones en ese punto."
            )
        if (
            table.temperature_f is not None
            and abs(table.temperature_f - t) > PVT_TEMP_TOLERANCE_F
        ):
            avisos.append(
                f"La tabla PVT está medida a {table.temperature_f:.0f} °F y se "
                f"evaluó a {t:.0f} °F ({abs(table.temperature_f - t):.0f} °F de "
                f"diferencia). Rs y Bo dependen de la temperatura: verificar que "
                f"la tabla corresponda a la condición del problema."
            )

    def _tomar(campo: str, calcular):
        """Devuelve el valor medido si existe; si no, el de la correlación."""
        v = medido.get(campo)
        if v is not None:
            origenes[campo] = PVT_SOURCE_TABLE
            return float(v)
        origenes[campo] = PVT_SOURCE_CORRELATION
        return calcular()

    pb = pb_para_pvt(fluid.bubble_point_pressure, fluid.gor, t, fluid.oil_api, fluid.gas_sg)
    gor = fluid.gor

    rs = _tomar(
        "rs",
        lambda: (
            standing_rs(p, t, fluid.oil_api, fluid.gas_sg, pb) if pb > 0 else gor
        ),
    )
    # Tope físico: el gas disuelto no puede superar al que produce el pozo.
    rs = min(rs, gor)

    bo = _tomar("bo", lambda: standing_bo(rs, t, fluid.oil_api, fluid.gas_sg))
    z = _tomar("z", lambda: gas_z_factor(p, t, fluid.gas_sg))
    bg = _tomar("bg", lambda: gas_bg(p, t, z))
    bw = _tomar("bw", lambda: water_bw(p, t))

    return {
        "rs": rs,
        "bo": bo,
        "bg": bg,
        "bw": bw,
        "z": z,
        "sources": origenes,
        "warnings": avisos,
    }


# ---------------------------------------------------------------------------
# Traza de fórmulas
# ---------------------------------------------------------------------------

def pvt_trace(fluid: Fluid, p: float, t: float) -> list[dict]:
    """Las propiedades PVT del fluido en un punto, fórmula por fórmula.

    Función aparte, como :func:`bes.core.ipr.ipr_trace`, para no cambiarle la
    firma a las correlaciones que usa todo el motor. Llama a esas mismas
    funciones, así que la traza no puede separarse de la cuenta.

    Args:
        fluid: Fluido producido.
        p: Presión del punto [psia].
        t: Temperatura del punto [°F].

    Returns:
        Lista de dicts de :class:`bes.core.formulas.Formula`, en el orden en que
        se encadenan las correlaciones.
    """
    from bes.core.formulas import FormulaTrace

    api, gas_sg = fluid.oil_api, fluid.gas_sg
    sg_o = _oil_sg(api)
    pb = pb_para_pvt(fluid.bubble_point_pressure, fluid.gor, t, api, gas_sg)
    rs = min(standing_rs(p, t, api, gas_sg, pb), fluid.gor) if pb > 0 else fluid.gor
    bo = standing_bo(rs, t, api, gas_sg)
    ppc, tpc = _pseudo_critical_standing(gas_sg)
    ppr, tpr = p / ppc, (t + 460.0) / tpc
    z = gas_z_factor(p, t, gas_sg)
    bg = gas_bg(p, t, z)
    bw = water_bw(p, t)
    mu_od, mu_ob, origen_mu = oil_viscosity_brown(fluid, t, rs)
    props = fluid_properties_at_conditions(fluid, p, t)

    trace = FormulaTrace()
    trace.add("pvt_sg_petroleo", {"API": api}, sg_o)
    trace.add(
        "pvt_pb", {"Rs": fluid.gor, "γ_g": gas_sg, "T": t, "API": api}, pb,
        context=("Presión de burbuja cargada como dato, no correlacionada."
                 if fluid.bubble_point_pressure else
                 "Sin dato de laboratorio: se estima con Standing."),
    )
    trace.add(
        "pvt_rs",
        {"γ_g": gas_sg, "P_ef": min(p, pb), "API": api, "T": t}, rs,
        context=(f"A {p:,.0f} psia el fluido está por ENCIMA de la burbuja "
                 f"({pb:,.0f} psia): todo el gas está disuelto y Rs se acota al "
                 f"GOR total." if p >= pb else
                 f"A {p:,.0f} psia el fluido está por debajo de la burbuja "
                 f"({pb:,.0f} psia): hay {fluid.gor - rs:.0f} scf/STB de gas "
                 f"libre."),
    )
    trace.add(
        "pvt_bo",
        {"F": rs * (gas_sg / sg_o) ** 0.5 + 1.25 * t}, bo,
    )
    fuera_de_rango = gas_sg < 0.55 or gas_sg > 0.75
    trace.add(
        "pvt_ppc", {"γ_g": gas_sg}, ppc,
        context=(f"γ_g = {gas_sg:.3f} queda fuera del rango 0.55–0.75 de la "
                 f"correlación: el valor se usa igual, extrapolado."
                 if fuera_de_rango else ""),
    )
    trace.add("pvt_tpc", {"γ_g": gas_sg}, tpc)
    trace.add("pvt_ppr", {"P": p, "P_pc": ppc}, ppr)
    trace.add("pvt_tpr", {"T": t, "T_pc": tpc}, tpr)
    trace.add(
        "pvt_z", {"P_pr": ppr, "T_pr": tpr}, z,
        context=f"Da {z:.4f}, o sea un {abs(1 - z) * 100:.0f} % de apartamiento "
                f"del gas ideal.",
    )
    trace.add("pvt_bg", {"z": z, "T": t, "P": p}, bg)
    trace.add("pvt_bw", {"ΔT": t - 60.0, "P": p}, bw)
    trace.add(
        "visc_mu_muerta", {"°API": api, "T": t}, mu_od, substitute=False,
        context=("Dato de ensayo de laboratorio." if origen_mu == "medido"
                 else "Leída de la Fig. 4L(2) de Brown."),
    )
    trace.add(
        "visc_mu_viva", {"μ_od": mu_od, "Rs": rs}, mu_ob,
        context=f"El gas disuelto baja la viscosidad de {mu_od:.1f} a "
                f"{mu_ob:.1f} cp.",
    )
    trace.add(
        "pvt_densidad_petroleo",
        {"γ_o": sg_o, "Rs": rs, "γ_g": gas_sg, "Bo": bo},
        props["oil_density"],
    )
    trace.add(
        "pvt_densidad_gas", {"γ_g": gas_sg, "P": p, "z": z, "T": t},
        props["gas_density"],
    )
    return trace.as_list()
