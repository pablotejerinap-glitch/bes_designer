"""
Análisis nodal para el diseño de pozos con BES/ESP.

Construye las curvas de entrega (outflow) y las cruza con el IPR para hallar el
punto de operación, con y sin bomba. Las pérdidas de carga en el tubing se
calculan siempre por Poettmann & Carpenter (ver ``bes.core.multiphase``).

Flujo de uso
------------
1. ``outflow_curve_natural`` / ``outflow_curve_with_pump`` dan la Pwf requerida
   en función del caudal de superficie.
2. ``find_operating_point`` busca dónde el IPR corta la curva de outflow.
"""

from __future__ import annotations

import numpy as np
from scipy.interpolate import interp1d
from scipy.optimize import brentq

from bes.core.models import Fluid, PumpCurve, Reservoir, SurfaceConditions, WellGeometry
from bes.core.ipr import generate_ipr_curve
from bes.core.tdh import _sg_liquid, friction_loss_hazen_williams
from bes.core.multiphase import pressure_traverse

# Única correlación multifásica del simulador.
METHOD_KEY = "poettmann_carpenter"
METHOD_LABEL = "Poettmann & Carpenter"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def outflow_curve_natural(
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    bottom_temp_f: float,
    n_points: int = 30,
    q_max: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Curva de descarga natural del pozo, o sea SIN bomba.

    Responde: para cada caudal, ¿qué presión de fondo hace falta para que el
    fluido suba solo hasta el separador? ::

        P_wh(q)    = P_sep + ΔP_línea(q) + ΔP_elevación
        Pwf_req(q) = recorrido de presión desde el cabezal HACIA ABAJO hasta
                     las punzados, arrancando en P_wh(q)

    Args:
        fluid: Propiedades PVT del fluido.
        well: Geometría del pozo (ID de tubing, profundidades, temperaturas).
        surface: Condiciones de superficie (presión de separador, geometría de
            la línea de conducción).
        bottom_temp_f: Temperatura de fondo [°F] — ``reservoir.reservoir_temp``.
            Es el extremo inferior del perfil geotérmico del recorrido.
        n_points: Cantidad de caudales a evaluar (sin contar q = 0).
        q_max: Caudal máximo a evaluar [STB/d]. Por defecto 5000.

    Returns:
        Tupla ``(q_array, pwf_array)`` de largo ``n_points + 1``.
        ``q_array`` es creciente; ``pwf_array`` tiene **forma de J**:
        primero baja, en la zona de caudales bajos donde manda el holdup, y
        después sube cuando empieza a mandar la fricción. La rama izquierda es
        la zona inestable de cabeceo (*heading*).
    """
    q_max = q_max or 5000.0
    sg = _sg_liquid(fluid)

    # q = 0: static head only, no friction
    pwf_zero = surface.separator_pressure + sg * 0.433 * well.total_depth

    q_arr = np.linspace(1.0, q_max, n_points)
    pwf_arr = np.empty(n_points)

    # Extremo inferior del perfil geotérmico: la temperatura de reservorio.
    t_bottom = bottom_temp_f

    for i, q in enumerate(q_arr):
        dp_fl = friction_loss_hazen_williams(
            q_bpd=q,
            pipe_id_in=surface.flowline_id,
            length_ft=surface.flowline_length,
        ) * sg / 2.31
        dp_elev = surface.flowline_elevation_change * sg / 2.31
        p_wh = surface.separator_pressure + dp_fl + dp_elev
        p_wh = max(p_wh, surface.wellhead_pressure_required)

        try:
            _, pressures = pressure_traverse(
                q_liq=q,
                fluid=fluid,
                pipe_id=well.tubing_id,
                depth_start=0.0,
                depth_end=well.total_depth,
                p_start=p_wh,
                t_start=well.wellhead_temp,
                t_end=t_bottom,
                n_segments=20,
            )
            pwf_arr[i] = float(pressures[-1])
        except Exception:
            # Fallback to hydrostatic if traverse fails (e.g. near-zero rate)
            pwf_arr[i] = p_wh + sg * 0.433 * well.total_depth

    q_full = np.concatenate([[0.0], q_arr])
    pwf_full = np.concatenate([[pwf_zero], pwf_arr])
    return q_full, pwf_full


def outflow_curve_with_pump(
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    pump: PumpCurve,
    stages: int,
    pump_depth: float,
    bottom_temp_f: float,
    n_points: int = 30,
    q_max: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Curva de descarga del pozo CON la bomba instalada.

    Le resta a la curva natural el diferencial de presión que aporta la
    bomba, caudal por caudal::

        ΔP_bomba(q) = altura_por_etapa(q) · #etapas · SG / 2.31   [psi]
        Pwf_bomba(q) = Pwf_natural(q) − ΔP_bomba(q)

    Args:
        fluid: Propiedades PVT del fluido.
        well: Geometría del pozo.
        surface: Condiciones de superficie.
        pump: Ficha de catálogo de la bomba elegida.
        stages: Cantidad de etapas instaladas.
        pump_depth: Profundidad de asentamiento [ft TVD]. Informativa: hoy no
            entra en el modelo de altura, queda reservada para correcciones
            por profundidad a futuro.
        n_points: Cantidad de caudales a evaluar.
        q_max: Caudal máximo a evaluar [STB/d]. Por defecto 5000.

    Returns:
        Tupla ``(q_array, pwf_array)``, con la misma forma que
        :func:`outflow_curve_natural`.
    """
    q_full, pwf_nat = outflow_curve_natural(
        fluid, well, surface, bottom_temp_f, n_points, q_max
    )

    sg = _sg_liquid(fluid)
    flows = np.array([pt.flow_rate for pt in pump.points])
    heads = np.array([pt.head_per_stage for pt in pump.points])

    pwf_pump = np.empty_like(pwf_nat)
    for i, q in enumerate(q_full):
        q_cl = float(np.clip(q, flows[0], flows[-1]))
        head_ps = float(np.interp(q_cl, flows, heads))
        pwf_pump[i] = pwf_nat[i] - head_ps * stages * sg / 2.31

    return q_full, pwf_pump


def find_operating_point(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    pump: PumpCurve | None = None,
    stages: int | None = None,
    pump_depth: float | None = None,
) -> dict:
    """Encuentra el punto de operación, con y sin bomba (análisis nodal).

    **Es el corazón del análisis nodal.** El reservorio puede entregar cierto
    caudal a cierta presión (curva IPR), y el pozo necesita cierta presión para
    levantar cierto caudal (curva de descarga). El pozo va a producir justo
    donde las dos curvas se cruzan: es el único punto que satisface a las dos.

    El cruce se busca numéricamente con ``scipy.optimize.brentq``.

    Args:
        reservoir: Parámetros IPR del reservorio.
        fluid: Propiedades PVT del fluido.
        well: Geometría del pozo.
        surface: Condiciones de superficie.
        pump: Ficha de catálogo de la bomba (opcional).
        stages: Cantidad de etapas (obligatorio si se pasa ``pump``).
        pump_depth: Profundidad de asentamiento [ft TVD] (obligatoria si se
            pasa ``pump``).

    Returns:
        dict con estas claves:

        =====================  ====================================================
        natural_flow           ``{'q':…, 'pwf':…}`` o ``None`` si el pozo no fluye
        pump_flow              ``{'q':…, 'pwf':…}`` o ``None``
        pump_dp_psi            Diferencial de presión de la bomba [psi]
        pump_efficiency        Rendimiento en el punto de operación [0-1]
        incremental_rate       q_con_bomba − q_natural [STB/d]
        method_used            Nombre de la correlación usada
        q_ipr                  Caudales de la curva IPR [STB/d]
        pwf_ipr                Pwf de la curva IPR [psia]
        q_outflow              Caudales de la curva de descarga [STB/d]
        pwf_outflow_natural    Pwf de descarga sin bomba [psia]
        pwf_outflow_pump       Pwf de descarga con bomba [psia] o ``None``
        =====================  ====================================================
    """
    # 1. IPR curve (q monotone ↑, pwf monotone ↓)
    q_ipr, pwf_ipr = generate_ipr_curve(reservoir, n_points=100)
    q_aof = float(q_ipr[-1])

    # 2. Outflow curves — slightly beyond AOF so the intersection is captured
    q_max_out = max(q_aof * 1.25, 500.0)
    n_pts = 60

    q_out, pwf_nat = outflow_curve_natural(
        fluid, well, surface, reservoir.reservoir_temp, n_pts, q_max_out
    )

    # 3. Natural operating point
    nat_result = _intersect(q_ipr, pwf_ipr, q_out, pwf_nat)

    # 4. Pump-assisted operating point
    pwf_pump_curve: np.ndarray | None = None
    pump_result = None
    pump_dp_psi = 0.0
    pump_eff = 0.0

    if pump is not None and stages is not None and pump_depth is not None:
        _, pwf_pump_curve = outflow_curve_with_pump(
            fluid, well, surface, pump, stages, pump_depth,
            reservoir.reservoir_temp, n_pts, q_max_out,
        )
        pump_result = _intersect(q_ipr, pwf_ipr, q_out, pwf_pump_curve)

        if pump_result is not None:
            q_op = pump_result["q"]
            sg = _sg_liquid(fluid)
            flows = np.array([pt.flow_rate for pt in pump.points])
            heads = np.array([pt.head_per_stage for pt in pump.points])
            effs  = np.array([pt.efficiency    for pt in pump.points])
            q_cl  = float(np.clip(q_op, flows[0], flows[-1]))
            pump_dp_psi = float(np.interp(q_cl, flows, heads)) * stages * sg / 2.31
            pump_eff    = float(np.interp(q_cl, flows, effs))

    q_nat_val  = nat_result["q"]  if nat_result  else 0.0
    q_pump_val = pump_result["q"] if pump_result else 0.0

    # El incremental solo existe si hay DOS puntos de operación que restar.
    # Si falta alguno —porque no se pidió bomba, o porque el pozo no cruza la
    # curva— no se resta contra un cero ficticio: eso daría un incremental
    # negativo del tamaño del caudal natural, que no significa nada.
    # Quien necesite distinguir los dos casos mira `pump_flow`: es None cuando
    # se pidió bomba y aun así no hubo punto de operación.
    if nat_result is not None and pump_result is not None:
        incremental = q_pump_val - q_nat_val
    else:
        incremental = 0.0

    return {
        "natural_flow":         nat_result,
        "pump_flow":            pump_result,
        "pump_dp_psi":          pump_dp_psi,
        "pump_efficiency":      pump_eff,
        "incremental_rate":     incremental,
        "method_used":          METHOD_KEY,
        "q_ipr":                q_ipr,
        "pwf_ipr":              pwf_ipr,
        "q_outflow":            q_out,
        "pwf_outflow_natural":  pwf_nat,
        "pwf_outflow_pump":     pwf_pump_curve,
    }


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _intersect(
    q_ipr: np.ndarray,
    pwf_ipr: np.ndarray,
    q_out: np.ndarray,
    pwf_out: np.ndarray,
) -> dict | None:
    """Busca el cruce (q, Pwf) entre la IPR y la curva de descarga, con brentq.

    Devuelve ``None`` cuando no hay cruce, o sea cuando el pozo está muerto: el
    reservorio no tiene fuerza para levantar el fluido a ningún caudal.
    """
    f_ipr = interp1d(q_ipr, pwf_ipr, kind="linear", fill_value="extrapolate")
    f_out = interp1d(q_out, pwf_out, kind="linear", fill_value="extrapolate")

    q_lo = float(max(q_out[0], q_ipr[0], 1.0))
    q_hi = float(min(q_out[-1], q_ipr[-1]))
    if q_hi <= q_lo:
        return None

    def residual(q: float) -> float:
        return float(f_ipr(q)) - float(f_out(q))

    r_lo = residual(q_lo)
    r_hi = residual(q_hi)

    # Dead well: outflow pressure always exceeds IPR pressure
    if r_lo <= 0.0:
        return None

    # IPR above outflow across the full range — return the boundary point
    if r_hi >= 0.0:
        q_op = q_hi
        pwf_op = (float(f_ipr(q_op)) + float(f_out(q_op))) / 2.0
        return {"q": float(q_op), "pwf": float(pwf_op)}

    try:
        q_op = float(brentq(residual, q_lo, q_hi, xtol=0.5, maxiter=150))
        pwf_op = (float(f_ipr(q_op)) + float(f_out(q_op))) / 2.0
        return {"q": q_op, "pwf": pwf_op}
    except Exception:
        return None
