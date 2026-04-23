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
    from core.models import DesignResult, PumpCurve, Reservoir, WellGeometry

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
    """Flow rate at a given Pwf."""
    pr = reservoir.static_pressure
    pi = reservoir.productivity_index
    pb = reservoir.bubble_point

    if reservoir.ipr_method.name == "LINEAR":
        return max(0.0, pi * (pr - pwf))

    if pb >= pr:
        qmax = pi * pr / 1.8
        x = pwf / pr
    else:
        q_at_pb = pi * (pr - pb)
        qmax = q_at_pb + pi * pb / 1.8
        if pwf >= pb:
            return pi * (pr - pwf)
        x = pwf / pb

    return max(0.0, qmax * (1.0 - 0.2 * x - 0.8 * x ** 2))


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
