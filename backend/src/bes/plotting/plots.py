"""
Plotly visualization functions for BES Designer.
All functions return a plotly Figure ready for st.plotly_chart().
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

if TYPE_CHECKING:
    from bes.core.models import DesignResult, PumpCurve, Reservoir, WellGeometry

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sg_liquid_simple(oil_api: float, water_cut: float, water_sg: float) -> float:
    sg_oil = 141.5 / (131.5 + oil_api)
    return sg_oil * (1.0 - water_cut) + water_sg * water_cut


def _vogel_pwf(reservoir, q: float) -> float:
    """Compute Pwf for a given flow rate using Vogel or linear IPR."""
    pr = reservoir.static_pressure
    pi = reservoir.productivity_index
    pb = reservoir.bubble_point

    if reservoir.ipr_method.name == "LINEAR":
        return max(0.0, pr - q / pi)

    # Vogel / Combined / Fetkovich → use Vogel
    if pb >= pr:  # depleted: fully two-phase
        qmax = pi * pr / 1.8
    else:
        q_at_pb = pi * (pr - pb)
        qmax = q_at_pb + pi * pb / 1.8

    ratio = min(q / max(qmax, 1e-6), 1.0)
    # Solve 0.8x^2 + 0.2x + (ratio-1) = 0 for x = Pwf/ref
    ref_p = pr
    disc = 0.04 + 3.2 * (1.0 - ratio)
    if disc < 0:
        return 0.0
    x = (-0.2 + disc ** 0.5) / 1.6
    return max(0.0, x * ref_p)


def _ipr_q(reservoir, pwf: float) -> float:
    """Flow rate at a given Pwf — delegates to the canonical core.ipr models.

    Avoids re-implementing the IPR equations here (a previous local copy
    introduced a discontinuity at Pwf = Pb because it used the total AOF
    as the Vogel multiplier instead of (PI·Pb/1.8)).
    """
    from bes.core.ipr import linear_ipr, vogel_ipr, combined_ipr
    from bes.core.models import IPRMethod

    pr = reservoir.static_pressure
    pi = reservoir.productivity_index
    pb = reservoir.bubble_point
    method = reservoir.ipr_method

    pwf_clamped = max(0.0, min(pwf, pr))

    if method is IPRMethod.LINEAR:
        return max(0.0, linear_ipr(pr, pwf_clamped, pi))

    if method is IPRMethod.VOGEL or pb >= pr:
        # Pure Vogel — used when reservoir is fully below bubble point too
        qmax = pi * pr / 1.8
        return max(0.0, vogel_ipr(pr, pwf_clamped, qmax))

    # COMBINED (default for Pr > Pb): linear above Pb, Vogel below — C0 continuous
    return max(0.0, combined_ipr(pr, pb, pwf_clamped, pi))


# ---------------------------------------------------------------------------
# 1. IPR curve
# ---------------------------------------------------------------------------

def plot_ipr_curve(reservoir, operating_point: tuple | None = None) -> go.Figure:
    """Plot Inflow Performance Relationship curve.

    Args:
        reservoir: Reservoir dataclass instance.
        operating_point: Optional (q_stbd, pwf_psi) tuple to mark on the plot.

    Returns:
        Plotly Figure.
    """
    pr = reservoir.static_pressure
    pwf_vals = np.linspace(0.0, pr, 300)
    q_vals = [_ipr_q(reservoir, p) for p in pwf_vals]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=q_vals,
        y=pwf_vals,
        name="Curva IPR",
        line=dict(color="#1565C0", width=2.5),
        hovertemplate="q = %{x:.0f} STB/d<br>Pwf = %{y:.0f} psi<extra></extra>",
    ))

    if reservoir.bubble_point < pr:
        pb = reservoir.bubble_point
        q_pb = _ipr_q(reservoir, pb)
        fig.add_trace(go.Scatter(
            x=[q_pb], y=[pb],
            name=f"Punto de burbuja ({pb:.0f} psi)",
            mode="markers",
            marker=dict(color="#FFA000", size=10, symbol="diamond"),
        ))

    if operating_point is not None:
        q_op, pwf_op = operating_point
        fig.add_trace(go.Scatter(
            x=[q_op], y=[pwf_op],
            name="Punto de operación",
            mode="markers",
            marker=dict(color="#D32F2F", size=13, symbol="circle"),
            hovertemplate=f"q = {q_op:.0f} STB/d<br>Pwf = {pwf_op:.0f} psi<extra></extra>",
        ))
        # Vertical + horizontal lines at operating point
        fig.add_vline(x=q_op, line_dash="dot", line_color="#D32F2F", line_width=1)
        fig.add_hline(y=pwf_op, line_dash="dot", line_color="#D32F2F", line_width=1)

    fig.update_layout(
        title="Curva de Afluencia (IPR)",
        xaxis_title="Tasa de producción (STB/d)",
        yaxis_title="Pwf — Presión de fondo fluyente (psi)",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=60, b=50, l=60, r=20),
        hovermode="x unified",
    )
    return fig


# ---------------------------------------------------------------------------
# 2. Pump curve
# ---------------------------------------------------------------------------

def plot_pump_curve(pump: "PumpCurve", operating_flow: float, stages: int) -> go.Figure:
    """Plot pump head, efficiency, and HP vs flow for a given stage count.

    Args:
        pump: PumpCurve catalog object.
        operating_flow: Operating flow rate [STB/d].
        stages: Number of installed stages.

    Returns:
        Plotly Figure with dual y-axes.
    """
    flows = np.array([p.flow_rate for p in pump.points])
    heads = np.array([p.head_per_stage for p in pump.points]) * stages
    effs = np.array([p.efficiency for p in pump.points]) * 100.0
    hps = np.array([p.hp_per_stage for p in pump.points]) * stages

    # Interpolate operating point values
    def _interp(x_arr, y_arr, x):
        if x <= x_arr[0]:
            return float(y_arr[0])
        if x >= x_arr[-1]:
            return float(y_arr[-1])
        return float(np.interp(x, x_arr, y_arr))

    op_head = _interp(flows, heads, operating_flow)
    op_eff = _interp(flows, effs, operating_flow)
    op_hp = _interp(flows, hps, operating_flow)

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Head curve
    fig.add_trace(go.Scatter(
        x=flows, y=heads, name="TDH (ft)",
        line=dict(color="#1565C0", width=2.5),
        hovertemplate="q=%{x:.0f} STB/d<br>Head=%{y:.0f} ft<extra></extra>",
    ), secondary_y=False)

    # HP curve
    fig.add_trace(go.Scatter(
        x=flows, y=hps, name="HP total",
        line=dict(color="#E65100", width=2, dash="dash"),
        hovertemplate="q=%{x:.0f} STB/d<br>HP=%{y:.1f}<extra></extra>",
    ), secondary_y=False)

    # Efficiency curve (secondary y)
    fig.add_trace(go.Scatter(
        x=flows, y=effs, name="Eficiencia (%)",
        line=dict(color="#2E7D32", width=2, dash="dot"),
        hovertemplate="q=%{x:.0f} STB/d<br>Eff=%{y:.1f}%<extra></extra>",
    ), secondary_y=True)

    # Operating point markers
    fig.add_trace(go.Scatter(
        x=[operating_flow, operating_flow],
        y=[op_head, op_hp],
        name="Punto de operación",
        mode="markers",
        marker=dict(color="#D32F2F", size=12, symbol="circle"),
        hovertemplate="Punto de operación<br>Head=%{y:.0f}<extra></extra>",
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=[operating_flow], y=[op_eff],
        name="Efic. en operación",
        mode="markers",
        marker=dict(color="#D32F2F", size=12, symbol="diamond"),
        showlegend=False,
    ), secondary_y=True)

    fig.add_vline(x=operating_flow, line_dash="dot", line_color="#D32F2F", line_width=1.5)

    # BEP marker
    fig.add_vline(x=pump.bep_flow, line_dash="dash", line_color="#9C27B0", line_width=1,
                  annotation_text="BEP", annotation_position="top")

    fig.update_layout(
        title=f"Curva de Bomba — {pump.model} ({stages} etapas)",
        xaxis_title="Caudal (STB/d)",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=60, b=50, l=60, r=60),
    )
    fig.update_yaxes(title_text="Head (ft) / HP", secondary_y=False)
    fig.update_yaxes(title_text="Eficiencia (%)", secondary_y=True,
                     range=[0, max(effs) * 1.3])

    return fig


def plot_pump_catalog_curve(pump: "PumpCurve") -> go.Figure:
    """Curva de catálogo *por etapa* de una bomba, sin contexto de diseño.

    A diferencia de :func:`plot_pump_curve` — que escala por el número de etapas
    instaladas y marca el punto de operación de un diseño concreto — esta figura
    muestra la curva cruda del fabricante tal como se digitalizó: head por etapa,
    HP por etapa y eficiencia frente al caudal, con el BEP marcado y el rango
    operativo recomendado sombreado. Es la que alimenta la pestaña de
    "ver la bomba seleccionada" del front, que sólo elige un modelo del catálogo.

    Args:
        pump: PumpCurve del catálogo.

    Returns:
        Plotly Figure con doble eje Y (head/HP a la izquierda, eficiencia a la
        derecha). Agnóstico de framework: la API lo serializa con ``to_json()``.
    """
    flows = np.array([p.flow_rate for p in pump.points])
    heads = np.array([p.head_per_stage for p in pump.points])
    hps = np.array([p.hp_per_stage for p in pump.points])
    effs = np.array([p.efficiency for p in pump.points]) * 100.0

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Rango operativo recomendado (sombreado)
    fig.add_vrect(
        x0=pump.min_flow, x1=pump.max_flow,
        fillcolor="#90CAF9", opacity=0.12, line_width=0,
        annotation_text="Rango operativo", annotation_position="top left",
    )

    fig.add_trace(go.Scatter(
        x=flows, y=heads, name="Head (ft/etapa)",
        line=dict(color="#1565C0", width=2.5),
        hovertemplate="q=%{x:.0f} STB/d<br>Head=%{y:.2f} ft/etapa<extra></extra>",
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=flows, y=hps, name="HP/etapa",
        line=dict(color="#E65100", width=2, dash="dash"),
        hovertemplate="q=%{x:.0f} STB/d<br>HP=%{y:.3f}/etapa<extra></extra>",
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=flows, y=effs, name="Eficiencia (%)",
        line=dict(color="#2E7D32", width=2, dash="dot"),
        hovertemplate="q=%{x:.0f} STB/d<br>Eff=%{y:.1f}%<extra></extra>",
    ), secondary_y=True)

    # BEP: caudal de máxima eficiencia
    bep_eff = float(np.interp(pump.bep_flow, flows, effs))
    fig.add_trace(go.Scatter(
        x=[pump.bep_flow], y=[bep_eff],
        name="BEP", mode="markers",
        marker=dict(color="#9C27B0", size=12, symbol="star"),
        hovertemplate=f"BEP<br>q={pump.bep_flow:.0f} STB/d<br>Eff=%{{y:.1f}}%<extra></extra>",
    ), secondary_y=True)
    fig.add_vline(x=pump.bep_flow, line_dash="dash", line_color="#9C27B0", line_width=1)

    fig.update_layout(
        title=(f"Curva de catálogo — {pump.manufacturer} {pump.model} "
               f"(serie {pump.series}, {pump.od}\" OD)"),
        xaxis_title="Caudal (STB/d)",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=70, b=50, l=60, r=60),
    )
    fig.update_yaxes(title_text="Head (ft/etapa) / HP", secondary_y=False, rangemode="tozero")
    fig.update_yaxes(title_text="Eficiencia (%)", secondary_y=True,
                     range=[0, max(effs) * 1.3])

    return fig


# ---------------------------------------------------------------------------
# 3. Pressure profile
# ---------------------------------------------------------------------------

def plot_pressure_profile(
    well,
    dr: "DesignResult",
    surface,
    fluid=None,
) -> go.Figure:
    """Pressure vs depth profile for the ESP completion.

    Shows key pressure points: Pwf, PIP, Pdisch, Pwh with connecting lines.

    Args:
        well: WellGeometry object.
        dr: DesignResult with intake_pressure, total_head_required, pump_setting_depth.
        surface: SurfaceConditions with wellhead_pressure_required.
        fluid: Optional Fluid object for SG computation.

    Returns:
        Plotly Figure (depth on y-axis, inverted).
    """
    sg = 1.0
    if fluid is not None:
        sg = _sg_liquid_simple(fluid.oil_api, fluid.water_cut, fluid.water_sg)

    pip = dr.intake_pressure
    pump_depth = dr.pump_setting_depth
    tdh = dr.total_head_required
    pwh = surface.wellhead_pressure_required
    datum = well.total_depth

    # Discharge pressure (psi)
    pdisch = pip + tdh * sg / 2.31

    # Approximate flowing BHP from balance
    # Pdisch = Pwh + pump_depth * sg / 2.31 (simplified, no friction)
    # Pwf ≈ pip + (datum - pump_depth) * sg / 2.31
    pwf = pip + (datum - pump_depth) * sg / 2.31

    # Tubing line: wellhead → pump discharge (depth 0 to pump_depth)
    tube_depths = np.linspace(0, pump_depth, 50)
    tube_pressures = pwh + tube_depths * sg / 2.31  # hydrostatic approximation

    # Annulus/inflow line: pump intake to datum
    ann_depths = np.linspace(pump_depth, datum, 50)
    ann_pressures = pip + (ann_depths - pump_depth) * sg / 2.31

    fig = go.Figure()

    # Tubing pressure profile (Pdisch → Pwh)
    fig.add_trace(go.Scatter(
        x=tube_pressures[::-1],
        y=tube_depths[::-1],
        name="Presión en tubería",
        line=dict(color="#1565C0", width=2),
        hovertemplate="P=%{x:.0f} psi @ %{y:.0f} ft<extra></extra>",
    ))

    # Annulus/wellbore pressure (PIP → Pwf)
    fig.add_trace(go.Scatter(
        x=ann_pressures,
        y=ann_depths,
        name="Presión en annulus",
        line=dict(color="#2E7D32", width=2, dash="dash"),
        hovertemplate="P=%{x:.0f} psi @ %{y:.0f} ft<extra></extra>",
    ))

    # Key point markers
    key_points = [
        (pwh, 0, "Pwh", "#1565C0"),
        (pdisch, pump_depth, "P descarga", "#E65100"),
        (pip, pump_depth, "PIP", "#D32F2F"),
        (pwf, datum, "Pwf", "#2E7D32"),
    ]
    for p, d, label, color in key_points:
        fig.add_trace(go.Scatter(
            x=[p], y=[d],
            name=f"{label} = {p:.0f} psi",
            mode="markers+text",
            marker=dict(color=color, size=11, symbol="circle"),
            text=[f"  {label}<br>  {p:.0f} psi"],
            textposition="middle right",
            showlegend=True,
        ))

    # Pump depth marker
    fig.add_hline(
        y=pump_depth,
        line_dash="dot",
        line_color="#9C27B0",
        line_width=1.5,
        annotation_text=f"Bomba @ {pump_depth:.0f} ft",
        annotation_position="right",
    )

    # Pressure jump at pump (vertical segment)
    fig.add_trace(go.Scatter(
        x=[pip, pdisch],
        y=[pump_depth, pump_depth],
        name="Incremento bomba",
        mode="lines",
        line=dict(color="#E65100", width=3),
        hovertemplate="ΔP = %{x:.0f} psi<extra></extra>",
        showlegend=False,
    ))

    fig.update_layout(
        title="Perfil de Presiones vs Profundidad",
        xaxis_title="Presión (psi)",
        yaxis_title="Profundidad (ft TVD)",
        yaxis_autorange="reversed",
        template="plotly_white",
        legend=dict(orientation="v", xanchor="right", x=0.99, yanchor="top", y=0.99,
                    font=dict(size=10)),
        margin=dict(t=60, b=50, l=70, r=20),
        hovermode="closest",
    )

    return fig


# ---------------------------------------------------------------------------
# 4. Sensitivity analysis
# ---------------------------------------------------------------------------

def plot_sensitivity_analysis(
    param_values: list[float],
    metrics_dict: dict[str, list[float]],
    parameter_label: str,
) -> go.Figure:
    """4-panel sensitivity analysis grid.

    Args:
        param_values: List of parameter values (x-axis for each subplot).
        metrics_dict: {metric_name: [values]} — expected keys:
            "HP", "Etapas", "Eficiencia (%)", "TDH (ft)".
        parameter_label: Display name for the x-axis parameter.

    Returns:
        Plotly Figure with 2×2 subplot grid.
    """
    metrics_order = ["HP", "Etapas", "Eficiencia (%)", "TDH (ft)"]
    colors = ["#1565C0", "#2E7D32", "#E65100", "#6A1B9A"]

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=metrics_order,
        horizontal_spacing=0.12,
        vertical_spacing=0.18,
    )

    positions = [(1, 1), (1, 2), (2, 1), (2, 2)]

    for (row, col), metric, color in zip(positions, metrics_order, colors):
        vals = metrics_dict.get(metric, [])
        if not vals:
            continue
        fig.add_trace(
            go.Scatter(
                x=param_values[: len(vals)],
                y=vals,
                mode="lines+markers",
                name=metric,
                line=dict(color=color, width=2),
                marker=dict(size=8),
                showlegend=False,
                hovertemplate=f"{parameter_label}=%{{x:.2f}}<br>{metric}=%{{y:.1f}}<extra></extra>",
            ),
            row=row,
            col=col,
        )

    fig.update_layout(
        title=f"Análisis de Sensibilidad — Variación de {parameter_label}",
        template="plotly_white",
        height=540,
        margin=dict(t=80, b=40, l=50, r=20),
    )

    return fig


# ---------------------------------------------------------------------------
# 5. Nodal analysis — single method
# ---------------------------------------------------------------------------

_METHOD_LABELS = {
    "hagedorn_brown":       "Hagedorn-Brown",
    "beggs_brill":          "Beggs-Brill",
    "duns_ros":             "Duns & Ros",
    "poettmann_carpenter":  "Poettmann & Carpenter",
}

_METHOD_COLORS_COMPARISON = {
    "hagedorn_brown":       "#E65100",   # orange
    "beggs_brill":          "#6A1B9A",   # purple
    "duns_ros":             "#00838F",   # teal/cyan
    "poettmann_carpenter":  "#4E342E",   # brown
}


def plot_nodal_analysis(
    reservoir,
    fluid,
    well,
    surface,
    pump=None,
    stages=None,
    pump_depth=None,
    method: str = "hagedorn_brown",
) -> go.Figure:
    """Professional nodal-analysis chart (IPR + outflow curves + operating points).

    Args:
        reservoir: Reservoir dataclass.
        fluid: Fluid dataclass.
        well: WellGeometry dataclass.
        surface: SurfaceConditions dataclass.
        pump: Optional PumpCurve catalog entry.
        stages: Number of pump stages (required when *pump* is given).
        pump_depth: Pump setting depth [ft TVD].
        method: Multiphase correlation to use.

    Returns:
        Plotly Figure with IPR, natural and (optionally) pump outflow curves,
        operating-point markers, a shaded benefit zone, and a summary
        annotation box.
    """
    from bes.core.nodal_analysis import find_operating_point

    result = find_operating_point(
        reservoir, fluid, well, surface,
        method=method, pump=pump, stages=stages, pump_depth=pump_depth,
    )

    q_ipr   = result["q_ipr"]
    pwf_ipr = result["pwf_ipr"]
    q_out   = result["q_outflow"]
    pwf_nat = result["pwf_outflow_natural"]
    pwf_pmp = result["pwf_outflow_pump"]
    nat_op  = result["natural_flow"]
    pmp_op  = result["pump_flow"]
    method_label = _METHOD_LABELS.get(method, method)

    fig = go.Figure()

    # ── IPR (inflow) curve ───────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=q_ipr, y=pwf_ipr,
        name="IPR (Inflow)",
        line=dict(color="#1565C0", width=3),
        hovertemplate="q = %{x:.0f} STB/D<br>Pwf = %{y:.0f} psi<extra>IPR</extra>",
    ))

    # ── Natural outflow curve ────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=q_out, y=pwf_nat,
        name="Outflow Natural",
        line=dict(color="#D32F2F", width=2, dash="dash"),
        hovertemplate="q = %{x:.0f} STB/D<br>Pwf = %{y:.0f} psi<extra>Natural</extra>",
    ))

    # ── Pump outflow curve ───────────────────────────────────────────────────
    if pwf_pmp is not None:
        pump_label = "Outflow con BES"
        if pump is not None:
            pump_label += f" ({pump.model})"
        fig.add_trace(go.Scatter(
            x=q_out, y=pwf_pmp,
            name=pump_label,
            line=dict(color="#2E7D32", width=3),
            hovertemplate="q = %{x:.0f} STB/D<br>Pwf = %{y:.0f} psi<extra>Con BES</extra>",
        ))

    # ── Natural operating point marker ───────────────────────────────────────
    if nat_op:
        q_n, p_n = nat_op["q"], nat_op["pwf"]
        fig.add_trace(go.Scatter(
            x=[q_n], y=[p_n],
            mode="markers+text",
            name=f"Flujo Natural: {q_n:.0f} STB/D",
            marker=dict(color="#D32F2F", size=14, symbol="circle",
                        line=dict(color="white", width=2)),
            text=[f"  Flujo Natural<br>  {q_n:.0f} STB/D<br>  {p_n:.0f} psi"],
            textposition="top right",
            hovertemplate=f"Flujo Natural<br>q = {q_n:.0f} STB/D<br>Pwf = {p_n:.0f} psi<extra></extra>",
        ))

    # ── Pump operating point marker ──────────────────────────────────────────
    if pmp_op:
        q_p, p_p = pmp_op["q"], pmp_op["pwf"]
        fig.add_trace(go.Scatter(
            x=[q_p], y=[p_p],
            mode="markers+text",
            name=f"Con BES: {q_p:.0f} STB/D",
            marker=dict(color="#2E7D32", size=14, symbol="circle",
                        line=dict(color="white", width=2)),
            text=[f"  Con BES<br>  {q_p:.0f} STB/D<br>  {p_p:.0f} psi"],
            textposition="top right",
            hovertemplate=f"Con BES<br>q = {q_p:.0f} STB/D<br>Pwf = {p_p:.0f} psi<extra></extra>",
        ))

    # ── Shaded benefit zone between the two operating points ─────────────────
    if nat_op and pmp_op:
        q_n = nat_op["q"]
        q_p = pmp_op["q"]
        incr = result["incremental_rate"]
        fig.add_vrect(
            x0=q_n, x1=q_p,
            fillcolor="rgba(46, 125, 50, 0.12)",
            layer="below",
            line_width=0,
        )
        fig.add_annotation(
            x=(q_n + q_p) / 2.0,
            y=reservoir.static_pressure * 0.15,
            text=f"<b>Δq = +{incr:.0f} STB/D</b>",
            showarrow=False,
            font=dict(color="#2E7D32", size=13),
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="#2E7D32",
            borderwidth=1,
        )

    # ── Summary annotation box ────────────────────────────────────────────────
    q_nat_val = nat_op["q"]  if nat_op  else 0.0
    q_pmp_val = pmp_op["q"]  if pmp_op  else 0.0
    pct = (result["incremental_rate"] / max(q_nat_val, 1.0)) * 100.0
    pump_info = (f"{pump.manufacturer} {pump.model} — {stages} etapas"
                 if pump is not None else "Sin bomba")
    ann_text = (
        f"<b>Método:</b> {method_label}<br>"
        f"<b>Caudal Natural:</b> {q_nat_val:.0f} STB/D<br>"
        f"<b>Caudal con BES:</b> {q_pmp_val:.0f} STB/D<br>"
        f"<b>Incremento:</b> +{result['incremental_rate']:.0f} STB/D "
        f"(+{pct:.0f} %)<br>"
        f"<b>Bomba:</b> {pump_info}"
    )
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0.98, y=0.97,
        text=ann_text,
        showarrow=False,
        align="left",
        font=dict(size=11),
        bgcolor="rgba(255,255,255,0.88)",
        bordercolor="#888",
        borderwidth=1,
        xanchor="right",
        yanchor="top",
    )

    fig.update_layout(
        title=f"Análisis Nodal del Sistema — Método {method_label}",
        xaxis_title="Caudal de Producción (STB/D)",
        yaxis_title="Presión de Fondo Pwf (psi)",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        hovermode="x unified",
        xaxis=dict(showgrid=True, gridcolor="#eee"),
        yaxis=dict(showgrid=True, gridcolor="#eee"),
        margin=dict(t=70, b=55, l=65, r=20),
    )
    return fig


# ---------------------------------------------------------------------------
# 6. Nodal analysis — four-method comparison
# ---------------------------------------------------------------------------

def plot_nodal_comparison(
    reservoir,
    fluid,
    well,
    surface,
    pump=None,
    stages=None,
    pump_depth=None,
) -> go.Figure:
    """Overlay the four outflow curves on one IPR to compare correlations.

    Runs ``compare_methods`` internally and plots:
    - The shared IPR in blue.
    - Each method's outflow curve (with pump if provided, else natural)
      in its own colour.
    - Operating-point markers for each method.

    Args:
        reservoir, fluid, well, surface, pump, stages, pump_depth:
            Same arguments as ``find_operating_point``.

    Returns:
        Plotly Figure.
    """
    from bes.core.nodal_analysis import compare_methods

    results = compare_methods(
        reservoir, fluid, well, surface,
        pump=pump, stages=stages, pump_depth=pump_depth,
    )

    fig = go.Figure()

    # ── Shared IPR ───────────────────────────────────────────────────────────
    ipr_q   = results["_ipr"]["q"]
    ipr_pwf = results["_ipr"]["pwf"]
    fig.add_trace(go.Scatter(
        x=ipr_q, y=ipr_pwf,
        name="IPR (Inflow)",
        line=dict(color="#1565C0", width=3),
        hovertemplate="q = %{x:.0f} STB/D<br>Pwf = %{y:.0f} psi<extra>IPR</extra>",
    ))

    _methods_order = ("hagedorn_brown", "beggs_brill", "duns_ros", "poettmann_carpenter")

    for m in _methods_order:
        res   = results[m]
        color = _METHOD_COLORS_COMPARISON[m]
        label = _METHOD_LABELS[m]
        q_out = res["q_outflow"]
        # Show pump curve if available, otherwise natural
        pwf_show = (res["pwf_outflow_pump"]
                    if res["pwf_outflow_pump"] is not None
                    else res["pwf_outflow_natural"])

        fig.add_trace(go.Scatter(
            x=q_out, y=pwf_show,
            name=label,
            line=dict(color=color, width=2),
            hovertemplate=f"q = %{{x:.0f}} STB/D<br>Pwf = %{{y:.0f}} psi<extra>{label}</extra>",
        ))

        op = res["pump_flow"] or res["natural_flow"]
        if op:
            fig.add_trace(go.Scatter(
                x=[op["q"]], y=[op["pwf"]],
                mode="markers",
                marker=dict(color=color, size=12, symbol="circle",
                            line=dict(color="white", width=2)),
                showlegend=False,
                hovertemplate=(
                    f"{label}<br>q = {op['q']:.0f} STB/D"
                    f"<br>Pwf = {op['pwf']:.0f} psi<extra></extra>"
                ),
            ))

    pump_suffix = f" con BES ({pump.model})" if pump is not None else " (flujo natural)"
    fig.update_layout(
        title=f"Comparación de Correlaciones — Análisis Nodal{pump_suffix}",
        xaxis_title="Caudal de Producción (STB/D)",
        yaxis_title="Presión de Fondo Pwf (psi)",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        hovermode="x unified",
        xaxis=dict(showgrid=True, gridcolor="#eee"),
        yaxis=dict(showgrid=True, gridcolor="#eee"),
        margin=dict(t=70, b=55, l=65, r=20),
    )
    return fig
