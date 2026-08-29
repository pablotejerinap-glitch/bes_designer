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


def _ipr_q(reservoir, pwf: float) -> float:
    """Caudal a una Pwf dada — delega en los modelos canónicos de ``core.ipr``.

    Evita reimplementar acá las ecuaciones de IPR. Una copia local anterior
    introducía una **discontinuidad en Pwf = Pb**, porque usaba el AOF total
    como multiplicador de Vogel en vez de (J·Pb/1.8).

    VOGEL usa el **generalizado** (``vogel_composite_ipr``): recta arriba de la
    presión de burbuja, Vogel abajo. Es la misma función que resuelve la Pwf de
    diseño, así que el gráfico y el cálculo **no pueden divergir**. Antes se
    llamaba a ``vogel_ipr`` con ``qmax = J·Pr/1.8``, o sea Vogel puro desde Pr:
    la curva salía doblada desde el primer punto, sin el tramo recto que exige
    el flujo monofásico por encima de Pb.
    """
    from bes.core.ipr import fetkovich_ipr, linear_ipr, vogel_composite_ipr
    from bes.core.models import IPRMethod

    pr = reservoir.static_pressure
    pi = reservoir.productivity_index
    method = reservoir.ipr_method

    pwf_clamped = max(0.0, min(pwf, pr))

    if method is IPRMethod.LINEAR:
        return max(0.0, linear_ipr(pr, pwf_clamped, pi))

    if method is IPRMethod.FETKOVICH:
        # C and n are guaranteed by Reservoir.__post_init__ for this method.
        n = reservoir.fetkovich_n if reservoir.fetkovich_n is not None else 1.0
        return max(0.0, fetkovich_ipr(pr, pwf_clamped, reservoir.fetkovich_c, n))

    # VOGEL generalizado: recta hasta Pb, Vogel de Pb para abajo.
    return max(0.0, vogel_composite_ipr(pr, reservoir.bubble_point, pwf_clamped, pi))


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

#: Cotas de la zona operativa del método de incrementos: el caudal de mezcla
#: en los dos extremos de la bomba no puede apartarse del representativo más
#: de esto. Con gas el caudal NO es constante a lo largo de la bomba —se
#: comprime y parte pasa a solución—, así que la bomba se elige contra un
#: caudal representativo y hay que verificar que los extremos sigan cayendo
#: cerca. Fuera de la banda, la bomba trabaja lejos de donde se la eligió.
GAS_ZONE_UPPER = 1.25
GAS_ZONE_LOWER = 0.75


def plot_pump_curve(
    pump: "PumpCurve",
    operating_flow: float,
    stages: int,
    gas_zone: dict | None = None,
) -> go.Figure:
    """Grafica altura, rendimiento y potencia de la bomba contra el caudal.

    Es la curva característica de la bomba, ya multiplicada por la cantidad de
    etapas instaladas.

    Marca **dos zonas distintas**, que no hay que confundir:

    - **Rango operativo de catálogo** — la banda de color que el fabricante
      publica en su curva. Es propiedad de la bomba y se dibuja siempre.
    - **Zona operativa del método de gas** — 0.75 a 1.25 veces el caudal de
      mezcla representativo. Es propiedad de *este* diseño, y sólo aparece
      cuando se pasa ``gas_zone``.

    Args:
        pump: Bomba del catálogo.
        operating_flow: Caudal de operación [STB/d].
        stages: Cantidad de etapas instaladas.
        gas_zone: Sólo para el camino de pozos con gas. dict con
            ``q_representative`` (el caudal de mezcla con que se eligió la
            bomba), ``q_intake`` (el que ENTRA a la bomba, en la admisión) y
            ``q_discharge`` (el que SALE, ya comprimido). ``None`` —el
            default— no dibuja nada de esto, que es lo que corresponde en el
            camino convencional, donde el caudal es uno solo.

    Returns:
        Figura de Plotly con doble eje Y.
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

    # Rango operativo recomendado del fabricante — la banda sombreada que traen
    # las curvas de catálogo. Sus límites NO son simétricos respecto del BEP:
    # el inferior lo fija el empuje descendente sobre los cojinetes y el
    # superior el ascendente, que son mecanismos distintos.
    #
    # OJO: va DESPUÉS de las trazas. add_vrect descarta los subplots vacíos
    # (exclude_empty_subplots=True por defecto), así que llamarlo antes del
    # primer add_trace no dibuja nada y no avisa.
    fig.add_vrect(
        x0=pump.min_flow, x1=pump.max_flow,
        fillcolor="#90CAF9", opacity=0.15, line_width=0, layer="below",
        annotation_text="Rango operativo recomendado",
        annotation_position="top left",
    )

    if gas_zone:
        _draw_gas_zone(fig, gas_zone)

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


def _draw_gas_zone(fig: go.Figure, gas_zone: dict) -> None:
    """Dibuja la zona operativa del método de incrementos sobre la curva.

    Tres cotas y una banda:

    .. code-block:: text

        0.75·q_rep -------- q_rep -------- 1.25·q_rep
             |                                  |
             +-------- zona operativa ----------+

        q_admisión   el caudal de mezcla que ENTRA a la bomba
        q_descarga   el que SALE, ya comprimido

    Con gas el caudal cae a lo largo de la bomba —el gas se comprime y parte
    pasa a solución—, así que la admisión es el extremo alto y la descarga el
    bajo. Los dos tienen que caer dentro de la banda: si no, la bomba está
    trabajando lejos del caudal con que se la eligió, y en algún tramo puede
    quedar fuera de su propio rango de catálogo.

    Args:
        fig: Figura sobre la que dibujar. Se modifica in situ.
        gas_zone: dict con ``q_representative``, ``q_intake`` y
            ``q_discharge`` [bpd].
    """
    q_rep = float(gas_zone.get("q_representative") or 0.0)
    if q_rep <= 0:
        return

    lo, hi = GAS_ZONE_LOWER * q_rep, GAS_ZONE_UPPER * q_rep

    fig.add_vrect(
        x0=lo, x1=hi,
        fillcolor="#66BB6A", opacity=0.12, line_width=0, layer="below",
        annotation_text=(f"Zona operativa del método de gas "
                         f"({GAS_ZONE_LOWER:g}–{GAS_ZONE_UPPER:g} × q_rep)"),
        annotation_position="bottom right",
    )
    # Los bordes se dibujan aparte: la banda sola no deja leer dónde cae cada
    # cota, y es exactamente lo que hay que verificar.
    for x, texto in ((lo, f"{GAS_ZONE_LOWER:g}·q_rep"), (hi, f"{GAS_ZONE_UPPER:g}·q_rep")):
        fig.add_vline(
            x=x, line_dash="dashdot", line_color="#2E7D32", line_width=1.5,
            annotation_text=texto, annotation_position="bottom",
        )

    fig.add_vline(
        x=q_rep, line_dash="solid", line_color="#2E7D32", line_width=2,
        annotation_text=f"q_rep = {q_rep:,.0f} bpd", annotation_position="top right",
    )

    for clave, etiqueta, color in (
        ("q_intake", "q admisión (entra)", "#00838F"),
        ("q_discharge", "q descarga (sale)", "#6A1B9A"),
    ):
        q = float(gas_zone.get(clave) or 0.0)
        if q <= 0:
            continue
        razon = q / q_rep
        # El fuera-de-banda se marca en el dibujo, no sólo en un aviso de
        # texto: quien mira la figura tiene que ver el problema.
        adentro = GAS_ZONE_LOWER <= razon <= GAS_ZONE_UPPER
        fig.add_vline(
            x=q,
            line_dash="dot" if adentro else "dash",
            line_color=color if adentro else "#C62828",
            line_width=2,
            annotation_text=(f"{etiqueta}: {q:,.0f} bpd "
                             f"({razon:.2f}× q_rep)"
                             + ("" if adentro else "  FUERA")),
            annotation_position="top left",
        )


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

    # Rango operativo del fabricante — la banda sombreada que traen
    # las curvas de catálogo. Sus límites NO son simétricos respecto del BEP:
    # el inferior lo fija el empuje descendente sobre los cojinetes y el
    # superior el ascendente, que son mecanismos distintos.
    #
    # OJO: va DESPUÉS de las trazas. add_vrect descarta los subplots vacíos
    # (exclude_empty_subplots=True por defecto), así que llamarlo antes del
    # primer add_trace no dibuja nada y no avisa.
    fig.add_vrect(
        x0=pump.min_flow, x1=pump.max_flow,
        fillcolor="#90CAF9", opacity=0.15, line_width=0, layer="below",
        annotation_text="Rango operativo",
        annotation_position="top left",
    )

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
    """Perfil de presión contra profundidad de la instalación BES.

    Muestra los puntos clave de presión unidos por líneas: Pwf en las
    perforaciones, PIP en la admisión, presión de descarga y presión de boca de
    pozo. Es la manera más directa de ver de dónde a dónde tiene que levantar la
    bomba.

    Args:
        well: Geometría del pozo.
        dr: ``DesignResult`` con ``intake_pressure``, ``total_head_required`` y
            ``pump_setting_depth``.
        surface: Condiciones de superficie con
            ``wellhead_pressure_required``.
        fluid: Fluido, opcional, para calcular el SG.

    Returns:
        Figura de Plotly, con la profundidad en el eje Y invertido (para que el
        fondo del pozo quede abajo, como en la realidad).
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
# 4. Nodal analysis
# ---------------------------------------------------------------------------

def plot_nodal_analysis(
    reservoir,
    fluid,
    well,
    surface,
    pump=None,
    stages=None,
    pump_depth=None,
) -> go.Figure:
    """Gráfico de análisis nodal: curvas IPR y de descarga, con el punto de cruce.

    Es **el gráfico que resume todo el diseño**. La curva IPR baja (a más
    caudal, menos presión de fondo disponible) y la de descarga sube (a más
    caudal, más presión hace falta). Donde se cruzan, el pozo produce.

    Con la bomba instalada, la curva de descarga baja —la bomba aporta
    presión— y el cruce se corre a un caudal mayor. Esa diferencia es el
    beneficio del equipo.

    Args:
        reservoir: Reservorio.
        fluid: Fluido producido.
        well: Geometría del pozo.
        surface: Condiciones de superficie.
        pump: Bomba del catálogo, opcional.
        stages: Cantidad de etapas (obligatoria si se pasa ``pump``).
        pump_depth: Profundidad de asentamiento [ft TVD].

    Returns:
        Figura de Plotly con la IPR, la curva de descarga natural y (si
        corresponde) la que resulta con bomba, los marcadores de los puntos de
        operación, la zona de beneficio sombreada y un recuadro de resumen.
    """
    from bes.core.nodal_analysis import METHOD_LABEL, find_operating_point

    result = find_operating_point(
        reservoir, fluid, well, surface,
        pump=pump, stages=stages, pump_depth=pump_depth,
    )

    q_ipr   = result["q_ipr"]
    pwf_ipr = result["pwf_ipr"]
    q_out   = result["q_outflow"]
    pwf_nat = result["pwf_outflow_natural"]
    pwf_pmp = result["pwf_outflow_pump"]
    nat_op  = result["natural_flow"]
    pmp_op  = result["pump_flow"]
    method_label = METHOD_LABEL

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


def plot_affinity_curves(
    pump: "PumpCurve",
    frequencies: list[float],
    diameter_ratio: float = 1.0,
    sg_ratio: float = 1.0,
    target_flow: float | None = None,
) -> go.Figure:
    """Familia de curvas de la misma bomba a distintas frecuencias.

    Muestra de un vistazo lo que dicen las leyes de afinidad: al bajar la
    frecuencia la curva se corre hacia caudales menores (Q ∝ N) y baja mucho más
    rápido en altura (H ∝ N²), mientras el rango operativo se comprime en la
    misma proporción que el caudal. La eficiencia no cambia, por eso no se
    grafica: sería la misma curva desplazada.

    Args:
        pump: PumpCurve del catálogo.
        frequencies: Frecuencias a dibujar [Hz]. Se ordenan de menor a mayor.
        diameter_ratio: ``D₂/D₁`` si el impulsor está rebajado.
        sg_ratio: ``SG₂/SG₁`` para la ley de potencia.
        target_flow: Caudal objetivo [STB/d]. Si se pasa, se marca con una
            vertical para leer a ojo qué frecuencia lo alcanza dentro del rango.

    Returns:
        Plotly Figure con head/etapa a la izquierda y HP/etapa a la derecha.
    """
    from bes.core.affinity import scale_curve

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    palette = ["#B0BEC5", "#64B5F6", "#1565C0", "#0D47A1", "#4A148C", "#880E4F"]

    for i, freq in enumerate(sorted(frequencies)):
        curve = scale_curve(pump, freq, diameter_ratio=diameter_ratio, sg_ratio=sg_ratio)
        color = palette[i % len(palette)]
        flows = [p["flow_bpd"] for p in curve["points"]]
        heads = [p["head_ft_per_stage"] for p in curve["points"]]
        hps = [p["hp_per_stage"] for p in curve["points"]]
        base = freq == pump.catalog_frequency_hz

        fig.add_trace(go.Scatter(
            x=flows, y=heads, name=f"{freq:.0f} Hz",
            legendgroup=f"{freq:.0f}",
            line=dict(color=color, width=3 if base else 2),
            hovertemplate=(f"{freq:.0f} Hz<br>q=%{{x:.0f}} STB/d"
                           "<br>Head=%{y:.2f} ft/etapa<extra></extra>"),
        ), secondary_y=False)

        fig.add_trace(go.Scatter(
            x=flows, y=hps, name=f"HP {freq:.0f} Hz",
            legendgroup=f"{freq:.0f}", showlegend=False,
            line=dict(color=color, width=1.5, dash="dash"),
            hovertemplate=(f"{freq:.0f} Hz<br>q=%{{x:.0f}} STB/d"
                           "<br>HP=%{y:.3f}/etapa<extra></extra>"),
        ), secondary_y=True)

        # BEP de cada frecuencia: se corre linealmente con el caudal.
        fig.add_trace(go.Scatter(
            x=[curve["bep_flow"]], y=[curve["bep_head_per_stage"]],
            mode="markers", showlegend=False, legendgroup=f"{freq:.0f}",
            marker=dict(color=color, size=10, symbol="star"),
            hovertemplate=(f"BEP {freq:.0f} Hz<br>q={curve['bep_flow']:.0f} STB/d"
                           f"<br>Head={curve['bep_head_per_stage']:.2f} ft/etapa"
                           "<extra></extra>"),
        ), secondary_y=False)

    if target_flow and target_flow > 0:
        fig.add_vline(
            x=target_flow, line_dash="dot", line_color="#D32F2F", line_width=2,
            annotation_text=f"Objetivo {target_flow:.0f} STB/d",
            annotation_position="top right",
        )

    fig.update_layout(
        title=(f"Leyes de afinidad — {pump.manufacturer} {pump.model} "
               f"(curva de catálogo a {pump.catalog_frequency_hz:.0f} Hz)"),
        xaxis_title="Caudal (STB/d)",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=70, b=50, l=60, r=60),
    )
    fig.update_yaxes(title_text="Head (ft/etapa)", secondary_y=False, rangemode="tozero")
    fig.update_yaxes(title_text="HP/etapa", secondary_y=True, rangemode="tozero")
    return fig


# ---------------------------------------------------------------------------
# 8. Escalera de incrementos de presión (Brown Fig. 4.56B)
# ---------------------------------------------------------------------------

def plot_gas_increment_ladder(
    rows: list[dict],
    *,
    p_intake: float,
    p_discharge: float,
    pump_model: str = "",
    total_stages: int | None = None,
    max_labels: int = 12,
) -> go.Figure:
    """Diagrama de escalera del método de incrementos — Brown Vol. 2b Fig. 4.56B.

    Reproduce la figura del libro: una columna vertical con la admisión abajo y
    la descarga arriba, el **caudal de mezcla a la izquierda** de cada peldaño,
    la **presión a la derecha**, el ΔP de cada tramo sobre el eje y el ΔP total
    acotado al costado.

    Dice de un vistazo lo que la tabla hace leer fila por fila: que el volumen
    **baja** al subir la presión, porque el gas se comprime y parte pasa a
    solución. Es el motivo de todo el método — con gas el caudal no es constante
    a lo largo de la bomba, así que no se puede resolver con un caudal único.

    Agrega sobre el libro las **etapas de cada tramo**, que es lo que el ΔP
    cuesta y lo que la figura impresa no muestra.

    La escala vertical es lineal en presión, así que la separación entre
    peldaños es proporcional al ΔP: si el último escalón quedó con el resto de
    la división, se ve corto y queda marcado.

    Args:
        rows: Filas de ``pressure_increment_design`` (``increment_table``).
            Cada una aporta ``p_lo``/``p_hi``, ``q_lo_bpd``/``q_hi_bpd`` y
            ``stages``.
        p_intake: Presión de admisión [psia] — la base de la escalera.
        p_discharge: Presión de descarga [psia] — el tope.
        pump_model: Modelo de bomba, para el título.
        total_stages: Etapas totales, para el título.
        max_labels: Tope de peldaños rotulados. Con más tramos que esto se
            rotula uno de cada *k* (los extremos siempre), para que las
            etiquetas no se pisen. Las líneas se dibujan todas.

    Returns:
        Plotly Figure. Agnóstico de framework: la API lo serializa con
        ``to_json()``.

    Raises:
        ValueError: Si ``rows`` viene vacío — no hay escalera que dibujar.
    """
    if not rows:
        raise ValueError("plot_gas_increment_ladder necesita al menos un intervalo")

    # Fronteras: el extremo superior de un tramo es el inferior del siguiente,
    # así que alcanza con los 'lo' más el 'hi' del último.
    p_bounds = [float(r["p_lo"]) for r in rows] + [float(rows[-1]["p_hi"])]
    q_bounds = [float(r["q_lo_bpd"]) for r in rows] + [float(rows[-1]["q_hi_bpd"])]

    # Geometría en unidades de eje X (no de margen: el front pisa los márgenes).
    X_RUNG = 1.0        # medio ancho del peldaño
    X_VOL = -1.25       # etiqueta de caudal, a la izquierda
    X_PRES = 1.25       # etiqueta de presión, a la derecha
    X_BRACKET = 2.75    # acotación del ΔP total
    AZUL, NARANJA, GRIS, VIOLETA = "#1565C0", "#E65100", "#616161", "#6A1B9A"

    # Con muchos tramos las etiquetas se pisan: se rotula uno de cada k.
    paso = max(1, -(-len(rows) // max_labels))   # ceil
    def rotula(i: int) -> bool:
        return i % paso == 0 or i == len(rows) - 1

    fig = go.Figure()

    # --- columna y peldaños --------------------------------------------------
    fig.add_shape(
        type="line", x0=0, x1=0, y0=p_intake, y1=p_discharge,
        line=dict(color=AZUL, width=2.5), layer="below",
    )
    for p in p_bounds:
        fig.add_shape(
            type="line", x0=-X_RUNG, x1=X_RUNG, y0=p, y1=p,
            line=dict(color=AZUL, width=2),
        )

    # --- caudal (izquierda) y presión (derecha) en cada frontera -------------
    for i, (p, q) in enumerate(zip(p_bounds, q_bounds)):
        if not (rotula(i) or i == len(p_bounds) - 1):
            continue
        fig.add_annotation(
            x=X_VOL, y=p, text=f"<b>{q:,.0f}</b> b/d".replace(",", " "),
            showarrow=False, xanchor="right", yanchor="middle",
            font=dict(size=12, color=AZUL),
        )
        fig.add_annotation(
            x=X_PRES, y=p, text=f"<b>{p:,.0f}</b> psi".replace(",", " "),
            showarrow=False, xanchor="left", yanchor="middle",
            font=dict(size=12, color=GRIS),
        )

    # --- ΔP y etapas de cada tramo, sobre el eje -----------------------------
    dp_nominal = max((float(r["delta_p"]) for r in rows), default=0.0)
    for i, r in enumerate(rows):
        if not rotula(i):
            continue
        dp = float(r["delta_p"])
        medio = 0.5 * (float(r["p_lo"]) + float(r["p_hi"]))
        # El último tramo suele quedar con el resto de la división: se marca.
        resto = i == len(rows) - 1 and abs(dp - dp_nominal) > 1e-6
        texto = f"ΔP = {dp:,.0f}".replace(",", " ")
        if resto:
            texto += " *"
        fig.add_annotation(
            x=0, y=medio, text=f"<b>{texto}</b><br><span style='font-size:10px'>"
                               f"{r['stages']} etapas</span>",
            showarrow=False, xanchor="center", yanchor="middle",
            font=dict(size=11, color=NARANJA if not resto else VIOLETA),
            bgcolor="rgba(255,255,255,0.88)", borderpad=3,
        )

    # --- acotación del ΔP total ---------------------------------------------
    delta_total = p_discharge - p_intake
    fig.add_shape(type="line", x0=X_BRACKET, x1=X_BRACKET,
                  y0=p_intake, y1=p_discharge,
                  line=dict(color=VIOLETA, width=1.5))
    for p in (p_intake, p_discharge):
        fig.add_shape(type="line", x0=X_BRACKET - 0.18, x1=X_BRACKET + 0.18,
                      y0=p, y1=p, line=dict(color=VIOLETA, width=1.5))
    fig.add_annotation(
        x=X_BRACKET + 0.28, y=0.5 * (p_intake + p_discharge),
        text=f"<b>ΔP TOTAL = {delta_total:,.0f} psi</b>".replace(",", " "),
        showarrow=False, xanchor="left", yanchor="middle", textangle=-90,
        font=dict(size=12, color=VIOLETA),
    )

    # --- extremos ------------------------------------------------------------
    fig.add_annotation(
        x=0, y=p_intake, yshift=-24, text="<b>ADMISIÓN</b>", showarrow=False,
        xanchor="center", font=dict(size=11, color=AZUL),
    )
    fig.add_annotation(
        x=0, y=p_discharge, yshift=24, text="<b>DESCARGA</b>", showarrow=False,
        xanchor="center", font=dict(size=11, color=AZUL),
    )

    # --- hover: los dos extremos de cada frontera ---------------------------
    fig.add_trace(go.Scatter(
        x=[0.0] * len(p_bounds), y=p_bounds, mode="markers",
        marker=dict(size=9, color=AZUL),
        customdata=q_bounds, showlegend=False,
        hovertemplate="P = %{y:.0f} psia<br>Caudal de mezcla = %{customdata:.0f} b/d"
                      "<extra></extra>",
    ))

    titulo = "Incrementos de presión — Brown Vol. 2b Fig. 4.56B"
    if pump_model:
        detalle = pump_model
        if total_stages is not None:
            detalle += f", {total_stages} etapas"
        titulo += f"<br><span style='font-size:12px;color:#616161'>{detalle}</span>"

    # El rango en X se fija a mano porque toda la figura son anotaciones: sin
    # esto Plotly ajusta al único trace (x = 0) y las etiquetas quedan afuera.
    fig.update_layout(
        title=titulo,
        template="plotly_white",
        showlegend=False,
        xaxis=dict(range=[-3.0, 4.3], visible=False, fixedrange=True),
        yaxis=dict(title_text="Presión (psia)", showgrid=False, zeroline=False),
        margin=dict(t=80, b=40, l=60, r=20),
    )
    return fig
