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
    """Compute the natural (no-pump) outflow deliverability curve.

    For each surface liquid rate *q*, calculates the minimum Pwf required
    to deliver that rate through the tubing and surface flowline:

        P_wh(q)   = P_sep + ΔP_flowline(q) + ΔP_elevation
        Pwf_req(q) = pressure_traverse(from wellhead DOWN to perforations,
                                        starting at P_wh(q))

    Args:
        fluid: Fluid PVT properties.
        well: Well geometry (tubing ID, depths, temperatures).
        surface: Surface conditions (separator pressure, flowline geometry).
        bottom_temp_f: Temperatura de fondo [°F] — ``reservoir.reservoir_temp``.
            Es el extremo inferior del perfil geotérmico del traverse.
        n_points: Number of rate evaluation points (excluding q = 0).
        q_max: Upper rate limit [STB/d].  Defaults to 5 000 STB/d.

    Returns:
        Tuple ``(q_array, pwf_array)`` of length *n_points* + 1.
        ``q_array`` is increasing; ``pwf_array`` is J-shaped — decreasing
        in the holdup-dominated region at low rates, increasing once
        friction dominates (the left branch is the unstable heading region).
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
    """Compute the ESP-assisted outflow curve.

    Subtracts the pump ΔP from the natural outflow curve at each rate::

        ΔP_pump(q) = head_per_stage(q) × stages × SG / 2.31   [psi]
        Pwf_pump(q) = Pwf_natural(q) − ΔP_pump(q)

    Args:
        fluid: Fluid PVT properties.
        well: Well geometry.
        surface: Surface conditions.
        pump: PumpCurve catalog entry for the selected pump.
        stages: Number of installed pump stages.
        pump_depth: Pump setting depth [ft TVD] (informational, not used
            in current head model but reserved for future depth corrections).
        n_points: Number of rate evaluation points.
        q_max: Upper rate limit [STB/d].  Defaults to 5 000 STB/d.

    Returns:
        Tuple ``(q_array, pwf_array)`` same shape as
        ``outflow_curve_natural``.
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
    """Find the natural and pump-assisted operating points (nodal analysis).

    Intersects the IPR with the outflow curve(s) using
    ``scipy.optimize.brentq``.

    Args:
        reservoir: Reservoir IPR parameters.
        fluid: Fluid PVT properties.
        well: Well geometry.
        surface: Surface conditions.
        pump: PumpCurve catalog entry (optional).
        stages: Number of pump stages (required when *pump* is given).
        pump_depth: Pump setting depth [ft TVD] (required when *pump* given).

    Returns:
        Dictionary with keys:

        =====================  ====================================================
        natural_flow           ``{'q': float, 'pwf': float}`` or ``None`` if dead
        pump_flow              ``{'q': float, 'pwf': float}`` or ``None``
        pump_dp_psi            Pump differential pressure [psi]
        pump_efficiency        Pump hydraulic efficiency at operating point [0-1]
        incremental_rate       q_pump − q_natural [STB/d]
        method_used            Correlation name used
        q_ipr                  IPR q array [STB/d]
        pwf_ipr                IPR Pwf array [psia]
        q_outflow              Outflow curve q array [STB/d]
        pwf_outflow_natural    Natural outflow Pwf array [psia]
        pwf_outflow_pump       Pump outflow Pwf array [psia] or ``None``
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
    """Find the (q, Pwf) intersection of IPR and outflow using brentq.

    Returns ``None`` when no intersection exists (dead well).
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
