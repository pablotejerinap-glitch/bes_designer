"""Generador del informe PDF del diseño, con ReportLab.

Produce un informe de ingeniería que **se sostiene solo**: portada, resumen
ejecutivo, datos de entrada, metodología de cálculo (método + ecuación +
cita + resultado para este pozo), gráficos, advertencias y referencias.

Los gráficos se renderizan a partir de las mismas figuras de Plotly que
muestra la pantalla, usando kaleido; si kaleido no está disponible (o falla)
se usa matplotlib como respaldo.
"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, Image, KeepTogether, PageBreak, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)

from bes.core.models import DesignResult

_VERSION = "v2.0"

_DARK_BLUE  = colors.HexColor("#1a237e")
_LIGHT_BLUE = colors.HexColor("#eef2fb")
_GRAY       = colors.HexColor("#9e9e9e")
_LT_GRAY    = colors.HexColor("#f2f2f2")
_ORANGE     = colors.HexColor("#c1440e")
_GREEN      = colors.HexColor("#2E7D32")


# ===========================================================================
# Page furniture
# ===========================================================================

def _header_footer(canvas, doc):
    canvas.saveState()
    # Top header band
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(_DARK_BLUE)
    canvas.drawString(inch, letter[1] - 0.55 * inch, "BES Designer — Informe de Diseño")
    canvas.setStrokeColor(_GRAY)
    canvas.setLineWidth(0.4)
    canvas.line(inch, letter[1] - 0.62 * inch, letter[0] - inch, letter[1] - 0.62 * inch)
    # Footer
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_GRAY)
    canvas.drawString(inch, 0.5 * inch, f"Página {doc.page}")
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(
        letter[0] / 2.0, 0.5 * inch,
        f"BES Designer {_VERSION} — Desarrollado por Pablo Agustín Tejerina, UNCo",
    )
    canvas.drawRightString(letter[0] - inch, 0.5 * inch, str(date.today().strftime("%d/%m/%Y")))
    canvas.restoreState()


# ===========================================================================
# Small helpers
# ===========================================================================

# Un dato opcional que el usuario no cargó se declara vacío: no es cero.
_SIN = "No ingresado"

# Etiquetas del selector de pérdidas de carga (DesignObjectives.pressure_loss_method).
_METODO_PERDIDAS = {
    "poettmann_carpenter": "Poettmann-Carpenter (elegido)",
    "hazen_williams": "Hazen-Williams (elegido)",
}


def _num(value, fmt: str, fallback: str = "No calculado") -> str:
    """Format a numeric value, returning *fallback* on any failure/None."""
    try:
        if value is None:
            return fallback
        return format(value, fmt)
    except (ValueError, TypeError):
        return fallback


def _make_table(data, col_widths=None, header=True, extra_styles=None,
                font_size: float = 9, padding: float = 4) -> Table:
    style_cmds = [
        ("FONTNAME",       (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",       (0, 0), (-1, -1), font_size),
        ("GRID",           (0, 0), (-1, -1), 0.4, _GRAY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LT_GRAY]),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",     (0, 0), (-1, -1), padding),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), padding),
        ("LEFTPADDING",    (0, 0), (-1, -1), 6),
    ]
    if header:
        style_cmds += [
            ("BACKGROUND", (0, 0), (-1, 0), _DARK_BLUE),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    if extra_styles:
        style_cmds += extra_styles
    tbl = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def _ficha_de_entrada(bloques, sub_style) -> list:
    """Maqueta los bloques de entrada en dos columnas, para que entren en una hoja.

    Reparte los bloques entre dos columnas equilibrando la cantidad de filas y
    los devuelve dentro de una tabla sin bordes, que es el recurso de ReportLab
    para poner dos flujos verticales lado a lado.

    Args:
        bloques: lista de ``(titulo, filas)``; la primera fila es el encabezado.
        sub_style: estilo de párrafo de los subtítulos.

    Returns:
        Lista de flowables lista para agregar al ``story``.
    """
    if not bloques:
        return []

    # Reparto: se prueban todos los cortes y gana el que deja más baja a la
    # columna más alta. Es esa altura la que decide si la ficha entra en la
    # hoja, así que equilibrar por "mitad de las filas" no alcanza: con cinco
    # bloques de tamaño desparejo el corte por la mitad deja una columna de 36
    # filas contra otra de 17, y la ficha se pasa de página.
    altos = [len(filas) for _, filas in bloques]
    corte = min(range(1, len(bloques) + 1),
                key=lambda k: max(sum(altos[:k]), sum(altos[k:])))
    izq, der = bloques[:corte], bloques[corte:]

    col_w = [1.78 * inch, 0.95 * inch, 0.60 * inch]

    def _columna(items) -> list:
        flow: list = []
        for titulo, filas in items:
            flow.append(Paragraph(titulo, sub_style))
            flow.append(_make_table(filas, col_widths=col_w,
                                    font_size=7.0, padding=1.5))
        return flow

    marco = Table([[_columna(izq), _columna(der)]],
                  colWidths=[3.4 * inch, 3.4 * inch])
    marco.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (0, 0), 0),
        ("RIGHTPADDING",  (-1, 0), (-1, 0), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [marco]


# ---------------------------------------------------------------------------
# IPR helpers (self-contained; used for the operating point and fallback plot)
# ---------------------------------------------------------------------------

def _ipr_q(reservoir, pwf: float) -> float:
    """Caudal de producción a una Pwf dada, según el método IPR del reservorio."""
    pr = reservoir.static_pressure
    pi = reservoir.productivity_index
    pb = reservoir.bubble_point
    if reservoir.ipr_method.name == "LINEAR":
        return max(0.0, pi * (pr - pwf))
    # Vogel family
    if pb >= pr:
        qmax = pi * pr / 1.8
        r = pwf / pr
        return max(0.0, qmax * (1.0 - 0.2 * r - 0.8 * r * r))
    if pwf >= pb:
        return max(0.0, pi * (pr - pwf))
    q_pb = pi * (pr - pb)
    qmax_below = pi * pb / 1.8
    r = pwf / pb
    return q_pb + qmax_below * (1.0 - 0.2 * r - 0.8 * r * r)


def _pwf_op(reservoir, target_q: float) -> float:
    """Flowing BHP at target_q (inverse IPR) for the operating-point marker."""
    pr = reservoir.static_pressure
    lo, hi = 0.0, pr
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _ipr_q(reservoir, mid) > target_q:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ===========================================================================
# Chart rendering: Plotly + kaleido, with matplotlib fallback
# ===========================================================================

_CHART_W, _CHART_H = 900, 500


def _load_pump(model: str, frequency_hz: float = 0.0):
    """Look the pump up in the bundled catalog; None if it cannot be resolved.

    The charts are a nice-to-have: if the catalog is unavailable the report is
    still generated, just without the pump-curve figure.

    Args:
        model: Catalog model name.
        frequency_hz: Frequency the design runs at. 0 = leave the catalog curve
            as published.
    """
    try:
        from bes.catalogs.loader import CatalogManager
        from bes.core.affinity import pump_at_frequency
        cat = CatalogManager()
        pump = next((p for p in cat.get_all_pumps() if p.model == model), None)
        if pump is None:
            return None
        # El catálogo publica a 60 Hz; el diseño puede correr a otra frecuencia.
        # Dibujar la curva sin escalar mostraría una bomba que no es la del
        # diseño (head, HP y rango operativo distintos).
        return pump_at_frequency(pump, frequency_hz) if frequency_hz else pump
    except Exception:
        return None


def _charts_plotly(dr, reservoir, fluid, well, surface, pump) -> list[tuple[str, bytes]]:
    """Render the three charts via Plotly + kaleido. Raises on any failure."""
    import plotly.io as pio
    from bes.plotting.plots import plot_ipr_curve, plot_pump_curve, plot_pressure_profile

    figs: list[tuple[str, object]] = []
    if reservoir is not None:
        op = (dr.flow_rate_achieved, _pwf_op(reservoir, dr.flow_rate_achieved))
        figs.append(("4.1  Curva IPR con punto de operación",
                     plot_ipr_curve(reservoir, operating_point=op)))
    if pump is not None:
        figs.append(("4.2  Curva de performance de la bomba",
                     plot_pump_curve(pump, dr.flow_rate_achieved, dr.num_stages)))
    if well is not None and surface is not None:
        figs.append(("4.3  Perfil de presión en el pozo",
                     plot_pressure_profile(well, dr, surface, fluid)))

    out: list[tuple[str, bytes]] = []
    for title, fig in figs:
        fig.update_layout(paper_bgcolor="white", plot_bgcolor="white")
        png = pio.to_image(fig, format="png", width=_CHART_W, height=_CHART_H, scale=2)
        out.append((title, png))
    if not out:
        raise RuntimeError("no figures produced")
    return out


def _charts_matplotlib(dr, reservoir, fluid, well, surface, pump) -> list[tuple[str, bytes]]:
    """Fallback charts using matplotlib (Agg). Never raises for missing data."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    out: list[tuple[str, bytes]] = []

    def _save(fig) -> bytes:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()

    # 4.1 IPR
    if reservoir is not None:
        try:
            pr = reservoir.static_pressure
            pwf = np.linspace(0.0, pr, 200)
            q = [_ipr_q(reservoir, p) for p in pwf]
            fig, ax = plt.subplots(figsize=(7.2, 4.2))
            ax.plot(q, pwf, color="#1565C0", lw=2.2, label="Curva IPR")
            q_op = dr.flow_rate_achieved
            p_op = _pwf_op(reservoir, q_op)
            ax.plot([q_op], [p_op], "o", color="#D32F2F", ms=8, label="Punto de operación")
            ax.axvline(q_op, ls=":", color="#D32F2F", lw=1)
            ax.axhline(p_op, ls=":", color="#D32F2F", lw=1)
            ax.set_xlabel("Tasa de producción (STB/d)")
            ax.set_ylabel("Pwf — Presión de fondo fluyente (psi)")
            ax.set_title("Curva de Afluencia (IPR)")
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=8)
            out.append(("4.1  Curva IPR con punto de operación", _save(fig)))
        except Exception:
            pass

    # 4.2 Pump curve
    if pump is not None:
        try:
            flows = np.array([p.flow_rate for p in pump.points])
            heads = np.array([p.head_per_stage for p in pump.points]) * dr.num_stages
            effs = np.array([p.efficiency for p in pump.points]) * 100.0
            hps = np.array([p.hp_per_stage for p in pump.points]) * dr.num_stages
            fig, ax = plt.subplots(figsize=(7.2, 4.2))
            ax.plot(flows, heads, color="#1565C0", lw=2.2, label="Head total (ft)")
            ax.plot(flows, hps, color="#E65100", lw=1.8, ls="--", label="HP total")
            ax.set_xlabel("Caudal (STB/d)")
            ax.set_ylabel("Head (ft) / HP")
            ax2 = ax.twinx()
            ax2.plot(flows, effs, color="#2E7D32", lw=1.8, ls=":", label="Eficiencia (%)")
            ax2.set_ylabel("Eficiencia (%)")
            ax.axvline(dr.flow_rate_achieved, ls=":", color="#D32F2F", lw=1.5)
            ax.axvline(pump.bep_flow, ls="--", color="#9C27B0", lw=1)
            ax.set_title(f"Curva de Bomba — {pump.model} ({dr.num_stages} etapas)")
            ax.grid(True, alpha=0.3)
            l1, la1 = ax.get_legend_handles_labels()
            l2, la2 = ax2.get_legend_handles_labels()
            ax.legend(l1 + l2, la1 + la2, fontsize=8, loc="upper right")
            out.append(("4.2  Curva de performance de la bomba", _save(fig)))
        except Exception:
            pass

    # 4.3 Pressure profile
    if well is not None and surface is not None:
        try:
            sg = 1.0
            if fluid is not None:
                so = 141.5 / (131.5 + fluid.oil_api)
                sg = (1.0 - fluid.water_cut) * so + fluid.water_cut * fluid.water_sg
            pip = dr.intake_pressure
            pump_depth = dr.pump_setting_depth
            tdh = dr.total_head_required
            pwh = surface.wellhead_pressure_required
            datum = well.total_depth
            pdisch = pip + tdh * sg / 2.31
            pwf = pip + (datum - pump_depth) * sg / 2.31
            tube_d = np.linspace(0, pump_depth, 50)
            tube_p = pwh + tube_d * sg / 2.31
            ann_d = np.linspace(pump_depth, datum, 50)
            ann_p = pip + (ann_d - pump_depth) * sg / 2.31
            fig, ax = plt.subplots(figsize=(7.2, 4.6))
            ax.plot(tube_p, tube_d, color="#1565C0", lw=2, label="Presión en tubería")
            ax.plot(ann_p, ann_d, color="#2E7D32", lw=2, ls="--", label="Presión en annulus")
            for p, d, lbl in [(pwh, 0, "Pwh"), (pdisch, pump_depth, "P descarga"),
                              (pip, pump_depth, "PIP"), (pwf, datum, "Pwf")]:
                ax.plot([p], [d], "o", ms=7)
                ax.annotate(f" {lbl} {p:.0f} psi", (p, d), fontsize=7, va="center")
            ax.invert_yaxis()
            ax.set_xlabel("Presión (psi)")
            ax.set_ylabel("Profundidad (ft)")
            ax.set_title("Perfil de Presión en el Pozo")
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=8)
            out.append(("4.3  Perfil de presión en el pozo", _save(fig)))
        except Exception:
            pass

    return out


def _render_charts(dr, reservoir, fluid, well, surface) -> tuple[list[tuple[str, bytes]], str]:
    """Return (charts, engine). engine is 'plotly+kaleido' or 'matplotlib' or 'none'."""
    pump = _load_pump(dr.pump_model, dr.operating_frequency)
    try:
        charts = _charts_plotly(dr, reservoir, fluid, well, surface, pump)
        if charts:
            return charts, "plotly+kaleido"
    except Exception:
        pass
    try:
        charts = _charts_matplotlib(dr, reservoir, fluid, well, surface, pump)
        if charts:
            return charts, "matplotlib"
    except Exception:
        pass
    return [], "none"


# ===========================================================================
# Methodology values (real numbers for this design)
# ===========================================================================

def _methodology(dr, reservoir, fluid, well, surface, objectives) -> dict:
    """Compute the real values quoted in Section 3. Every field is guarded."""
    M: dict = {}

    # Temperature at pump depth (linear profile)
    t_pump = None
    try:
        t_pump = (well.wellhead_temp + (dr.pump_setting_depth / well.total_depth)
                  * (reservoir.reservoir_temp - well.wellhead_temp))
    except Exception:
        t_pump = getattr(reservoir, "reservoir_temp", None)
    M["t_pump"] = t_pump

    # 3.1 IPR
    try:
        M["qmax"] = _ipr_q(reservoir, 0.0)
    except Exception:
        M["qmax"] = None
    M["q_pip"] = getattr(dr, "flow_rate_achieved", None)

    # 3.2 PVT at PIP
    try:
        from bes.core.pvt import standing_rs, standing_bo
        pb = fluid.bubble_point_pressure
        rs = min(standing_rs(dr.intake_pressure, t_pump, fluid.oil_api, fluid.gas_sg, pb)
                 if pb > 0 else fluid.gor, fluid.gor)
        M["rs_pip"] = rs
        M["bo_pip"] = standing_bo(rs, t_pump, fluid.oil_api, fluid.gas_sg)
    except Exception:
        M["rs_pip"] = None
        M["bo_pip"] = None
    M["free_gas_pct"] = getattr(dr, "gip_fraction", None)

    # 3.3 In-pump volumetric rate
    try:
        from bes.core.gas_handling import _mixture_volumes_and_density
        v = _mixture_volumes_and_density(dr.intake_pressure, t_pump, fluid,
                                         fluid.water_cut, 1.0)["v_total"]
        M["q_pump_bfpd"] = dr.flow_rate_achieved * v
    except Exception:
        try:
            M["q_pump_bfpd"] = dr.flow_rate_achieved * M["bo_pip"]
        except Exception:
            M["q_pump_bfpd"] = None

    # 3.4 TDH breakdown
    try:
        from bes.core.tdh import calculate_tdh
        M["tdh"] = calculate_tdh(
            reservoir=reservoir, fluid=fluid, well=well, surface=surface,
            objectives=objectives, pump_depth=dr.pump_setting_depth,
            pip=dr.intake_pressure,
        )
    except Exception:
        M["tdh"] = None

    # 3.8 kVA cross-check
    try:
        M["kva_calc"] = (dr.surface_voltage_required * dr.motor_amperage * 1.732) / 1000.0
    except Exception:
        M["kva_calc"] = None

    # 3.9 gas
    try:
        from bes.core.gas_handling import check_gas_lock_risk, recommend_gas_separator
        M["gas_risk"] = check_gas_lock_risk(dr.gip_fraction)["risk"]
        M["separator"] = recommend_gas_separator(dr.gip_fraction, dr.pump_series)
    except Exception:
        M["gas_risk"] = None
        M["separator"] = None

    return M


# ===========================================================================
# Main entry point
# ===========================================================================

def generate_design_report(
    design_result: DesignResult,
    well_data: dict,
    output_path: Optional[str] = None,
) -> bytes | str:
    """Genera el informe PDF del diseño.

    Args:
        design_result: ``DesignResult`` de ``generate_recommendations()``.
        well_data: dict con las claves reservoir, fluid, well, surface,
            objectives y, opcionalmente, well_name (texto).
        output_path: Si se indica, escribe ahí y devuelve la ruta. Si es
            ``None``, devuelve los bytes del PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=inch, leftMargin=inch,
        topMargin=0.9 * inch, bottomMargin=0.75 * inch,
        title="Informe de Diseño BES",
    )

    dr         = design_result
    reservoir  = well_data.get("reservoir")
    fluid      = well_data.get("fluid")
    well       = well_data.get("well")
    surface    = well_data.get("surface")
    objectives = well_data.get("objectives")
    _wn        = well_data.get("well_name")
    well_name  = _wn if (_wn and str(_wn).strip() and str(_wn).strip() != "—") else "Pozo sin identificar"

    # ---- Styles (serif body, sans headings) ----------------------------
    title_s = ParagraphStyle("t", fontName="Times-Bold", fontSize=21,
                             textColor=_DARK_BLUE, alignment=TA_CENTER, spaceAfter=8, leading=25)
    cover_sub_s = ParagraphStyle("cs", fontName="Times-Roman", fontSize=13,
                                 alignment=TA_CENTER, spaceAfter=6, leading=17)
    section_s = ParagraphStyle("sec", fontName="Helvetica-Bold", fontSize=13,
                              textColor=_DARK_BLUE, spaceBefore=12, spaceAfter=4)
    sub_s = ParagraphStyle("sub", fontName="Helvetica-Bold", fontSize=10.5,
                          textColor=_DARK_BLUE, spaceBefore=8, spaceAfter=3)
    body_s = ParagraphStyle("body", fontName="Times-Roman", fontSize=10.5,
                           alignment=TA_JUSTIFY, spaceAfter=5, leading=15)
    method_s = ParagraphStyle("method", fontName="Times-Italic", fontSize=10,
                             alignment=TA_JUSTIFY, spaceAfter=4, leading=14,
                             textColor=colors.HexColor("#333333"))
    result_s = ParagraphStyle("res", fontName="Times-Bold", fontSize=10,
                             spaceBefore=2, spaceAfter=8, leading=14,
                             textColor=colors.black, leftIndent=4)
    caption_s = ParagraphStyle("cap", fontName="Helvetica", fontSize=8,
                              textColor=colors.HexColor("#757575"),
                              alignment=TA_CENTER, spaceAfter=4)
    warn_s = ParagraphStyle("w", fontName="Times-Roman", fontSize=10,
                           spaceAfter=6, leftIndent=10, leading=14)
    eq_style = ParagraphStyle("eq", fontName="Times-Roman", fontSize=11,
                             alignment=TA_CENTER, leading=15)

    col_w = [2.9 * inch, 2.3 * inch, 1.0 * inch]
    story: list = []

    def _equation(text: str):
        p = Paragraph(text, eq_style)
        t = Table([[p]], colWidths=[5.4 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, -1), _LIGHT_BLUE),
            ("BOX",          (0, 0), (-1, -1), 0.4, _GRAY),
            ("TOPPADDING",   (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING",  (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        return t

    def _method_block(title, method_text, equation, result_text):
        flow = [Paragraph(title, sub_s), Paragraph(method_text, method_s)]
        if equation:
            flow += [Spacer(1, 2), _equation(equation), Spacer(1, 3)]
        flow.append(Paragraph(result_text, result_s))
        return KeepTogether(flow)

    # ------------------------------------------------------------------
    # ENCABEZADO — va en la misma hoja que los datos de entrada, para que la
    # primera hoja del informe sea la ficha completa de lo que cargó el usuario.
    # ------------------------------------------------------------------
    # El cuerpo del encabezado es chico a propósito: cada punto que ocupa acá
    # se lo saca a la ficha de entrada, que tiene que entrar entera abajo.
    head_s = ParagraphStyle("head", parent=title_s, fontSize=15, leading=17,
                            spaceAfter=3)
    head_sub_s = ParagraphStyle("headsub", parent=cover_sub_s, fontSize=9.5,
                                leading=12, spaceAfter=1)
    story.append(Paragraph(
        "Informe de Diseño — Sistema de Bombeo Electrosumergible", head_s))
    story.append(HRFlowable(width="100%", thickness=1.4, color=_DARK_BLUE))
    story.append(Spacer(1, 4))
    tgt = _num(getattr(objectives, "target_flow_rate", None), ",.0f")
    story.append(Paragraph(
        f"{well_name} &nbsp;&#183;&nbsp; Bomba seleccionada: {dr.pump_manufacturer} "
        f"{dr.pump_model} &nbsp;&#183;&nbsp; Tasa de diseño: {tgt} STB/d",
        head_sub_s))
    story.append(Paragraph(
        f"Fecha de generación: {date.today().strftime('%d/%m/%Y')} "
        f"&nbsp;&#183;&nbsp; BES Designer {_VERSION}", caption_s))
    story.append(Spacer(1, 4))

    # ------------------------------------------------------------------
    # SECTION 1 — INPUT DATA
    #
    # Los cinco bloques de entrada van completos y en la PRIMERA hoja: es la
    # ficha de lo que cargó el usuario, y partirla en dos páginas obliga a ir
    # y venir para leer un solo dato. Por eso se maquetan en dos columnas con
    # cuerpo reducido, en vez de una sola columna que desborda la hoja.
    # ------------------------------------------------------------------
    story.append(Paragraph("1. Datos de Entrada", section_s))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GRAY, spaceAfter=6))

    _ENC = ["Parámetro", "Valor", "Unidad"]
    bloques: list[tuple[str, list]] = []

    if reservoir:
        bloques.append(("Reservorio", [
            _ENC,
            ["Presión estática", _num(reservoir.static_pressure, ",.0f"), "psi"],
            ["Presión de burbuja", _num(reservoir.bubble_point, ",.0f"), "psi"],
            ["Índice de productividad", _num(reservoir.productivity_index, ".2f"), "STB/d/psi"],
            ["Método IPR", reservoir.ipr_method.name, "—"],
            ["Temperatura", _num(reservoir.reservoir_temp, ".0f"), "°F"],
            ["Mecanismo de empuje", reservoir.drive_mechanism.name, "—"],
            ["Ensayo — Pwf", _num(reservoir.test_pwf, ",.0f", fallback=_SIN), "psi"],
            ["Ensayo — caudal", _num(reservoir.test_rate, ",.0f", fallback=_SIN), "STB/d"],
            ["Fetkovich C", _num(reservoir.fetkovich_c, ".4g", fallback=_SIN), "—"],
            ["Fetkovich n", _num(reservoir.fetkovich_n, ".2f", fallback=_SIN), "—"],
        ]))

    if fluid:
        bloques.append(("Fluido", [
            _ENC,
            ["API del crudo", _num(fluid.oil_api, ".1f"), "°API"],
            ["Corte de agua", _num(fluid.water_cut, ".1%"), "fracción"],
            ["GOR", _num(fluid.gor, ".0f"), "scf/STB"],
            ["Gravedad específica del gas", _num(fluid.gas_sg, ".3f"), "—"],
            ["Gravedad específica del agua", _num(fluid.water_sg, ".3f"), "—"],
            ["Presión de burbuja (fluido)", _num(fluid.bubble_point_pressure, ",.0f"), "psi"],
            ["Viscosidad crudo muerto",
             _num(fluid.oil_viscosity_dead, ".2f",
                  fallback="Sin ensayo — Fig. 4L(2)"), "cp"],
            ["Temp. del ensayo de viscosidad",
             _num(fluid.viscosity_temp_ref, ".0f", fallback=_SIN), "°F"],
            ["H2S", _num(fluid.h2s_content, ".0f"), "ppm"],
            ["CO2", _num(fluid.co2_content, ".0f"), "ppm"],
            ["Producción de arena", "Sí" if fluid.sand_production else "No", "—"],
        ]))

    if well:
        bloques.append(("Geometría del Pozo", [
            _ENC,
            ["Profundidad total", _num(well.total_depth, ",.0f"), "ft"],
            ["OD casing", _num(well.casing_od, ".3f"), "in"],
            ["Peso casing", _num(well.casing_weight, ".1f"), "lb/ft"],
            ["ID casing", _num(well.casing_id, ".3f"), "in"],
            ["OD tubing", _num(well.tubing_od, ".3f"), "in"],
            ["ID tubing", _num(well.tubing_id, ".3f"), "in"],
            ["Perforaciones techo", _num(well.perforations_top, ",.0f"), "ft"],
            ["Perforaciones base", _num(well.perforations_bottom, ",.0f"), "ft"],
            ["Desviación máxima", _num(well.deviation_max, ".1f"), "°"],
            ["Temperatura cabezal", _num(well.wellhead_temp, ".0f"), "°F"],
            ["Temperatura de fondo (BHT)",
             _num(getattr(reservoir, "reservoir_temp", None), ".0f"), "°F"],
            ["Asentamiento impuesto",
             _num(well.pump_setting_depth, ",.0f", fallback="Automático"), "ft"],
        ]))

    if surface:
        bloques.append(("Superficie", [
            _ENC,
            ["Presión de cabezal requerida", _num(surface.wellhead_pressure_required, ".0f"), "psi"],
            ["Longitud de flowline", _num(surface.flowline_length, ".0f"), "ft"],
            ["ID de flowline", _num(surface.flowline_id, ".2f"), "in"],
            ["Cambio de elevación flowline", _num(surface.flowline_elevation_change, ".0f"), "ft"],
            ["Presión de separador", _num(surface.separator_pressure, ".0f"), "psi"],
            ["Voltaje disponible", _num(surface.power_supply_voltage, ",.0f"), "V"],
            ["Frecuencia", _num(surface.frequency, ".0f"), "Hz"],
        ]))

    if objectives:
        bloques.append(("Objetivos de Diseño", [
            _ENC,
            ["Tasa objetivo", _num(objectives.target_flow_rate, ",.0f"), "STB/d"],
            ["Margen de seguridad (profundidad)", _num(objectives.safety_margin_depth, ".0f"), "ft"],
            ["Venteo de gas", "Sí" if objectives.allow_gas_venting else "No", "—"],
            ["GIP máximo en admisión", _num(objectives.max_gip, ".1%"), "fracción"],
            ["Vida útil de diseño", _num(objectives.design_life_years, ".1f"), "años"],
            ["Variador de velocidad (VSD)", "Sí" if objectives.use_vsd else "No", "—"],
            ["Frecuencia de diseño (VSD)",
             _num(objectives.design_frequency_hz, ".1f", fallback="La de red"), "Hz"],
            ["Pérdidas de carga",
             _METODO_PERDIDAS.get(objectives.pressure_loss_method,
                                  "Automático"), "—"],
        ]))

    story.extend(_ficha_de_entrada(bloques, sub_s))
    story.append(PageBreak())

    # ------------------------------------------------------------------
    # SECTION 2 — EXECUTIVE SUMMARY
    # ------------------------------------------------------------------
    story.append(Paragraph("2. Resumen Ejecutivo", section_s))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GRAY, spaceAfter=6))

    # Dynamic intro paragraph
    _depth = _num(getattr(well, "total_depth", None), ",.0f")
    _api = _num(getattr(fluid, "oil_api", None), ".0f")
    _wc = getattr(fluid, "water_cut", None)
    _wc_txt = _num(_wc * 100, ".0f") if isinstance(_wc, (int, float)) else "No calculado"
    _gor = _num(getattr(fluid, "gor", None), ".0f")
    _fluid_kind = "petróleo"
    if isinstance(_wc, (int, float)):
        if _wc >= 0.99:
            _fluid_kind = "agua"
        elif _wc >= 0.5:
            _fluid_kind = "mezcla con predominio de agua"
    intro = (
        f"Se diseñó un sistema de bombeo electrosumergible para producir "
        f"<b>{tgt} STB/d</b> de {_fluid_kind} (API {_api}°, corte de agua {_wc_txt} %, "
        f"GOR {_gor} scf/STB) en un pozo de <b>{_depth} ft</b> de profundidad total. "
        f"El diseño requiere una bomba <b>{dr.pump_manufacturer} {dr.pump_model}</b> de "
        f"<b>{dr.num_stages} etapas</b>, accionada por un motor de "
        f"<b>{_num(dr.motor_hp, '.0f')} HP</b>, para desarrollar un TDH de "
        f"<b>{_num(dr.total_head_required, ',.0f')} ft</b> a una profundidad de "
        f"instalación de {_num(dr.pump_setting_depth, ',.0f')} ft."
    )
    story.append(Paragraph(intro, body_s))
    story.append(Spacer(1, 6))

    # Equipment summary table
    _cable_len = _num(getattr(dr, "pump_setting_depth", None), ",.0f")
    _seal = f"{dr.seal_manufacturer} {dr.seal_model}".strip() if dr.seal_model else "No seleccionado"
    # El consumo del separador se publica al lado del equipo: el motor se
    # dimensionó con esos hp adentro, así que el número tiene que estar a la
    # vista para que la cuenta de potencia cierre.
    # El consumo sale del catálogo por modelo (REDA lo publica a 60 Hz), y con
    # dos equipos en el eje —tándem, o separador + manejador avanzado— es la
    # suma de los dos. Por eso se publica la cantidad además del hp.
    _gh = (f"{dr.gas_handler_manufacturer} {dr.gas_handler_model}".strip()
           + (f" ×{dr.gas_handler_count}" if dr.gas_handler_count > 1 else "")
           + (f"  (+{dr.gas_handler_hp:.1f} hp)" if dr.gas_handler_hp else "")
           if dr.gas_handler_model else "No requerido")
    _sn = (f"{dr.sensor_manufacturer} {dr.sensor_model}".strip()
           if dr.sensor_model else "No incluido")
    story.append(_make_table([
        ["Componente", "Especificación", "Detalle"],
        ["Bomba", f"{dr.pump_manufacturer} {dr.pump_model}",
         f"Serie {dr.pump_series} · {dr.num_stages} etapas"],
        ["Motor", f"{_num(dr.motor_hp, '.0f')} HP",
         f"{_num(dr.motor_voltage, '.0f')} V · {_num(dr.motor_amperage, '.0f')} A"],
        ["Cable", f"#{dr.cable_awg} {dr.cable_type}",
         f"Longitud ≈ {_cable_len} ft"],
        ["Transformador", f"{_num(dr.transformer_kva, '.0f')} kVA", "Banco trifásico"],
        ["Sello / Protector", _seal, dr.seal_type or "—"],
        ["Separador de gas", _gh, dr.gas_handler_type or "—"],
        ["Sensor de fondo", _sn, "—"],
    ], col_widths=[1.5 * inch, 2.6 * inch, 2.1 * inch]))
    story.append(Spacer(1, 8))

    # Critical warnings
    crit = list(dr.warnings)
    if dr.gip_fraction > 0.30:
        crit.append(f"Gas libre en la admisión: {dr.gip_fraction:.1%}. "
                    "Se recomienda separador de gas de fondo.")
    if crit:
        story.append(Paragraph("Advertencias críticas", sub_s))
        for w in crit:
            story.append(Paragraph(f"• {w}", warn_s))
    else:
        story.append(Paragraph(
            "No se registraron advertencias críticas para las condiciones ingresadas.",
            body_s))

    story.append(PageBreak())

    # ------------------------------------------------------------------
    # SECTION 3 — METHODOLOGY
    # ------------------------------------------------------------------
    story.append(Paragraph("3. Metodología de Cálculo", section_s))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GRAY, spaceAfter=6))
    story.append(Paragraph(
        "Cada etapa del diseño se resuelve con el método, la ecuación y la "
        "referencia que se indican, y se reporta el resultado obtenido para este pozo.",
        body_s))
    story.append(Spacer(1, 4))

    M = _methodology(dr, reservoir, fluid, well, surface, objectives)

    # 3.1 IPR
    story.append(_method_block(
        "3.1  Capacidad Productiva (IPR)",
        "La capacidad productiva del pozo se determinó mediante la correlación de "
        "Vogel (1968), aplicable a reservorios con empuje por gas en solución, según "
        "el procedimiento descrito en Brown (1980), Sección 4.5322.",
        "q / q<sub>max</sub> = 1 − 0.2 (P<sub>wf</sub>/P<sub>R</sub>) − 0.8 (P<sub>wf</sub>/P<sub>R</sub>)<sup>2</sup>",
        f"q<sub>max</sub> = {_num(M.get('qmax'), ',.0f')} STB/d&nbsp;&nbsp;|&nbsp;&nbsp;"
        f"Caudal a PIP de diseño = {_num(M.get('q_pip'), ',.0f')} STB/d",
    ))

    # 3.2 PVT
    fg = M.get("free_gas_pct")
    fg_txt = _num(fg * 100, ".1f") if isinstance(fg, (int, float)) else "No calculado"
    story.append(_method_block(
        "3.2  Propiedades PVT del Fluido",
        "Las propiedades del fluido se estimaron mediante las correlaciones de "
        "Standing (1947): relación gas-petróleo en solución (Rs), factor de volumen "
        "de formación del petróleo (Bo) y, para el gas, el factor volumétrico Bg "
        "con z por Dranchuk-Abou-Kassem.",
        None,
        f"Bo @ PIP = {_num(M.get('bo_pip'), '.3f')} bbl/STB&nbsp;&nbsp;|&nbsp;&nbsp;"
        f"Rs @ PIP = {_num(M.get('rs_pip'), '.0f')} scf/STB&nbsp;&nbsp;|&nbsp;&nbsp;"
        f"Gas libre @ PIP = {fg_txt} %",
    ))

    # 3.3 In-pump rate
    story.append(_method_block(
        "3.3  Caudal de Diseño en la Bomba",
        "El caudal en condiciones de bomba se obtiene aplicando los factores "
        "volumétricos de formación al caudal de superficie, según Brown (1980), "
        "Sección 4.538.",
        "Q<sub>bomba</sub> = q<sub>o</sub> · B<sub>o</sub> + q<sub>w</sub> · B<sub>w</sub> + gas libre",
        f"Q<sub>bomba</sub> = {_num(M.get('q_pump_bfpd'), ',.0f')} BFPD",
    ))

    # 3.4 TDH
    tdh = M.get("tdh")
    if tdh:
        story.append(Paragraph("3.4  Altura Dinámica Total (TDH)", sub_s))
        story.append(Paragraph(
            "El TDH se compone de la elevación vertical neta, las pérdidas por "
            "fricción en el tubing (Hazen-Williams) y la presión requerida en "
            "cabezal, conforme a Brown (1980), Sección 4.5324.", method_s))
        story.append(Spacer(1, 2))
        story.append(_equation("TDH = H<sub>d</sub> + F<sub>t</sub> + F<sub>wh</sub>"))
        story.append(Spacer(1, 4))
        story.append(_make_table([
            ["Componente", "Símbolo", "Valor (ft)"],
            ["Elevación vertical neta", "Hd", _num(tdh["vertical_lift_ft"], ",.0f")],
            ["Fricción en tubing", "Ft", _num(tdh["tubing_friction_ft"], ",.0f")],
            ["Presión de cabezal (head)", "Fwh", _num(tdh["wellhead_pressure_head_ft"], ",.0f")],
            ["TOTAL TDH", "", _num(tdh["tdh_ft"], ",.0f")],
        ], col_widths=[3.0 * inch, 1.2 * inch, 2.0 * inch], extra_styles=[
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), _LIGHT_BLUE),
        ]))
        story.append(Spacer(1, 8))
    else:
        story.append(_method_block(
            "3.4  Altura Dinámica Total (TDH)",
            "El TDH se compone de elevación vertical, fricción en tubing y presión "
            "de cabezal (Brown, 1980, Sección 4.5324).",
            "TDH = H<sub>d</sub> + F<sub>t</sub> + F<sub>wh</sub>",
            f"TDH = {_num(dr.total_head_required, ',.0f')} ft",
        ))

    # 3.5 Pump & stages
    story.append(_method_block(
        "3.5  Selección de Bomba y Número de Etapas",
        "La bomba se seleccionó del catálogo filtrado por diámetro de casing y rango "
        "operativo, maximizando la eficiencia al caudal de diseño. El número de "
        "etapas resulta de dividir el TDH por el head por etapa a dicho caudal "
        "(Brown, 1980, Sección 4.5323).",
        "N = TDH / (head por etapa)",
        f"N = {dr.num_stages} etapas&nbsp;&nbsp;|&nbsp;&nbsp;"
        f"head/etapa = {_num(dr.head_per_stage, '.1f')} ft @ "
        f"{_num(dr.flow_rate_achieved, ',.0f')} STB/d&nbsp;&nbsp;|&nbsp;&nbsp;"
        f"Eficiencia = {_num(dr.pump_efficiency, '.1%')}",
    ))

    # 3.5b Housings
    if dr.housing_detail:
        _combo = " + ".join(
            f"{h['stages']} et" + (f" [{h['code']}]" if h["code"] else "")
            for h in dr.housing_detail
        )
        _check = (
            ("OK" if dr.housing_pressure_ok else "FAIL")
            if dr.housing_pressure_verified else "sin verificar (el catálogo no "
            "publica la presión admisible)"
        )
        story.append(_method_block(
            "3.5b  Optimización de Carcasas (Pump Housings)",
            "Las etapas se alojan en carcasas de longitudes discretas del catálogo. "
            "La combinación se busca entre todas las posibles y se elige por criterios "
            "estrictos: ajuste exacto de etapas, mínimo excedente, mínima cantidad de "
            "carcasas y arreglo más estandarizado. La presión de la carcasa a caudal "
            "cero (Brown, 1980, Sección 4.5451) es restricción obligatoria: una "
            "combinación que la supere se descarta.",
            "MaxP = P<sub>(Q=0)</sub> × N<sub>etapas activas</sub> × Pem",
            f"Arreglo = {_combo}&nbsp;&nbsp;|&nbsp;&nbsp;"
            f"Instaladas = {dr.housing_size_stages} et "
            f"({dr.dummy_stages} ciegas)&nbsp;&nbsp;|&nbsp;&nbsp;"
            f"MaxP = {_num(dr.max_housing_pressure_psi, ',.0f')} psi&nbsp;&nbsp;|"
            f"&nbsp;&nbsp;Verificación = {_check}<br/><br/>{dr.housing_rationale}",
        ))

    # 3.6 Power & motor
    story.append(_method_block(
        "3.6  Potencia y Motor",
        "La potencia al eje es el producto del número de etapas por la potencia por "
        "etapa (referida a agua) corregida por la gravedad específica del fluido. El "
        "motor se toma como el menor del catálogo cuya potencia nominal cubre el "
        "requerimiento.",
        "HP = N × (hp por etapa) × SG<sub>fluido</sub>",
        f"HP requerido = {_num(dr.total_pump_hp, '.1f')} hp&nbsp;&nbsp;|&nbsp;&nbsp;"
        f"Motor seleccionado = {dr.motor_manufacturer} {dr.motor_model} "
        f"de {_num(dr.motor_hp, '.0f')} HP",
    ))

    # 3.7 Cable & electrical
    story.append(_method_block(
        "3.7  Cable y Sistema Eléctrico",
        "El cable se seleccionó por capacidad de corriente y temperatura de pozo. La "
        "caída de tensión se calculó a partir de las curvas del fabricante y la "
        "longitud del cable (Brown, 1980, Sección 4.5325).",
        None,
        f"Cable #{dr.cable_awg} {dr.cable_type}&nbsp;&nbsp;|&nbsp;&nbsp;"
        f"V<sub>caída</sub> = {_num(dr.cable_voltage_drop, '.0f')} V&nbsp;&nbsp;|&nbsp;&nbsp;"
        f"V<sub>superficie</sub> = {_num(dr.surface_voltage_required, '.0f')} V",
    ))

    # 3.8 Transformer
    story.append(_method_block(
        "3.8  Transformador",
        "El banco de transformación se dimensionó a partir del voltaje de superficie "
        "requerido y la corriente del motor, para suministro trifásico.",
        "kVA = (V<sub>s</sub> × A × 1.73) / 1000",
        f"kVA calculado = {_num(M.get('kva_calc'), '.0f')}&nbsp;&nbsp;→&nbsp;&nbsp;"
        f"Transformador seleccionado = {_num(dr.transformer_kva, '.0f')} kVA",
    ))

    # 3.9 Gas handling (conditional)
    show_gas = (isinstance(dr.gip_fraction, (int, float)) and dr.gip_fraction > 0.05) \
        or any("gas" in str(w).lower() for w in dr.warnings)
    if show_gas:
        risk_map = {"low": "bajo", "medium": "medio", "high": "alto"}
        risk = risk_map.get(M.get("gas_risk"), "No calculado")
        sep = M.get("separator")
        if sep and dr.gip_fraction > 0.10:
            sep_info = sep["separator"]
            sep_txt = f"Sí — {sep_info.get('type', '')} ({sep_info.get('model', '')})"
        else:
            sep_txt = "No requerido"
        story.append(_method_block(
            "3.9  Manejo de Gas",
            "Dado el contenido de gas libre en la admisión, se aplicó el método de "
            "incrementos de presión (Brown, 1980, Sección 4.53102), que evalúa la "
            "densidad y el gradiente de la mezcla en incrementos discretos de presión "
            "y corrige el desempeño de la bomba.",
            None,
            f"GIP = {_num(dr.gip_fraction * 100, '.1f')} %&nbsp;&nbsp;|&nbsp;&nbsp;"
            f"Riesgo de gas lock = {risk}&nbsp;&nbsp;|&nbsp;&nbsp;"
            f"Separador recomendado: {sep_txt}",
        ))

    story.append(PageBreak())

    # ------------------------------------------------------------------
    # SECTION 4 — CHARTS
    # ------------------------------------------------------------------
    story.append(Paragraph("4. Gráficos", section_s))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GRAY, spaceAfter=6))

    charts, engine = _render_charts(dr, reservoir, fluid, well, surface)
    if charts:
        for title, png in charts:
            img = Image(io.BytesIO(png), width=6.3 * inch, height=3.5 * inch)
            img.hAlign = "CENTER"
            story.append(KeepTogether([Paragraph(title, sub_s), img, Spacer(1, 10)]))
    else:
        story.append(Paragraph(
            "No fue posible generar los gráficos en este entorno "
            "(kaleido/matplotlib no disponibles).", body_s))

    story.append(PageBreak())

    # ------------------------------------------------------------------
    # SECTION 5 — WARNINGS & RECOMMENDATIONS
    # ------------------------------------------------------------------
    story.append(Paragraph("5. Advertencias y Recomendaciones", section_s))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GRAY, spaceAfter=6))

    _EXPL = {
        "bep": "La bomba opera alejada de su punto de mejor eficiencia (BEP); "
               "revisar el caudal de diseño o considerar otro modelo para reducir "
               "empuje axial y vibración.",
        "gas": "El gas libre en la admisión degrada el head y puede provocar gas "
               "lock; se sugiere separador de fondo o asentar la bomba más profunda.",
        "gip": "Fracción de gas en admisión elevada; ver la Sección 3.9.",
    }
    shown = list(dr.warnings)
    if dr.gip_fraction > 0.30:
        shown.append(f"Gas libre en la admisión: {dr.gip_fraction:.1%}.")
    elif dr.gip_fraction > 0.10:
        shown.append(f"Gas libre en la admisión moderado: {dr.gip_fraction:.1%}.")

    if shown:
        story.append(Paragraph("Advertencias del diseño", sub_s))
        for w in shown:
            wl = str(w).lower()
            expl = ""
            if "bep" in wl or "eficien" in wl:
                expl = " " + _EXPL["bep"]
            elif "gas" in wl:
                expl = " " + _EXPL["gas"]
            story.append(Paragraph(f"• {w}{expl}", warn_s))
    else:
        story.append(Paragraph("El diseño no presenta advertencias.", body_s))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Recomendaciones operativas", sub_s))
    recs = [
        "Arranque: verificar sentido de giro y registrar corriente de arranque; "
        "usar arranque suave o VSD si el par de arranque es elevado.",
        "Monitoreo: registrar presión y temperatura de admisión, corriente del "
        "motor y frecuencia; comparar contra los valores de diseño de este informe.",
        "Accesorios: instalar válvula de retención (check) y de purga (bleeder) en "
        "el tubing; considerar sensor de fondo para diagnóstico continuo.",
    ]
    if dr.gip_fraction > 0.10:
        recs.append("Gas: prever separador de gas de fondo o manejo de gas según la "
                    "Sección 3.9 para proteger la bomba del gas lock.")
    for r in recs:
        story.append(Paragraph(f"• {r}", warn_s))

    story.append(PageBreak())

    # ------------------------------------------------------------------
    # SECTION 6 — REFERENCES
    # ------------------------------------------------------------------
    story.append(Paragraph("6. Referencias", section_s))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GRAY, spaceAfter=6))
    refs = [
        "Brown, K.E. (1980). <i>The Technology of Artificial Lift Methods, Vol. 2b</i>. "
        "PennWell Books.",
        "Vogel, J.V. (1968). Inflow Performance Relationships for Solution-Gas Drive "
        "Wells. <i>Journal of Petroleum Technology</i>, 20(1), 83–92. SPE-1476.",
        "Standing, M.B. (1947). A Pressure-Volume-Temperature Correlation for Mixtures "
        "of California Oils and Gases. <i>API Drilling and Production Practice</i>.",
        "Hagedorn, A.R. &amp; Brown, K.E. (1965). Experimental Study of Pressure "
        "Gradients Occurring During Continuous Two-Phase Flow in Small-Diameter "
        "Vertical Conduits. <i>Journal of Petroleum Technology</i>, 17(4), 475–484.",
    ]
    ref_s = ParagraphStyle("ref", fontName="Times-Roman", fontSize=10,
                          leftIndent=14, firstLineIndent=-14, spaceAfter=6, leading=14)
    for r in refs:
        story.append(Paragraph(r, ref_s))

    # ------------------------------------------------------------------
    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    pdf_bytes = buffer.getvalue()

    if output_path is not None:
        with open(output_path, "wb") as fh:
            fh.write(pdf_bytes)
        return output_path
    return pdf_bytes
