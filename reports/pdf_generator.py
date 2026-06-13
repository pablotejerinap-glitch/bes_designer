"""PDF report generator for BES/ESP design results using ReportLab."""
from __future__ import annotations

import io
from datetime import date
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

from core.models import DesignResult

_DARK_BLUE  = colors.HexColor("#1a237e")
_LIGHT_BLUE = colors.HexColor("#e3f2fd")
_GRAY       = colors.HexColor("#bdbdbd")
_ORANGE     = colors.HexColor("#e65100")


def _header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_GRAY)
    canvas.drawString(inch, 0.5 * inch, "BES Designer — Reporte de Diseño")
    canvas.drawRightString(letter[0] - inch, 0.5 * inch, f"Página {doc.page}")
    canvas.restoreState()


def _make_table(data: list, col_widths=None, header=True, extra_styles=None) -> Table:
    style_cmds = [
        ("FONTNAME",       (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",       (0, 0), (-1, -1), 9),
        ("GRID",           (0, 0), (-1, -1), 0.5, _GRAY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT_BLUE]),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
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


def generate_design_report(
    design_result: DesignResult,
    well_data: dict,
    output_path: Optional[str] = None,
) -> bytes | str:
    """Generate a PDF design report.

    Args:
        design_result: DesignResult from generate_recommendations().
        well_data: Dict with keys: reservoir, fluid, well, surface, objectives,
                   and optionally well_name (str).
        output_path: Write to this path and return it. If None, return PDF bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=inch, leftMargin=inch,
        topMargin=inch, bottomMargin=0.75 * inch,
    )

    dr         = design_result
    reservoir  = well_data.get("reservoir")
    fluid      = well_data.get("fluid")
    well       = well_data.get("well")
    surface    = well_data.get("surface")
    objectives = well_data.get("objectives")
    well_name  = well_data.get("well_name", "—")

    title_s = ParagraphStyle(
        "t", fontName="Helvetica-Bold", fontSize=20,
        textColor=_DARK_BLUE, alignment=TA_CENTER, spaceAfter=10,
    )
    section_s = ParagraphStyle(
        "sec", fontName="Helvetica-Bold", fontSize=13,
        textColor=_DARK_BLUE, spaceBefore=14, spaceAfter=6,
    )
    sub_s = ParagraphStyle(
        "sub", fontName="Helvetica-Bold", fontSize=10,
        textColor=_DARK_BLUE, spaceAfter=4,
    )
    caption_s = ParagraphStyle(
        "cap", fontName="Helvetica", fontSize=8,
        textColor=colors.HexColor("#757575"), alignment=TA_CENTER, spaceAfter=4,
    )
    warn_s = ParagraphStyle(
        "w", fontName="Helvetica", fontSize=9,
        textColor=_ORANGE, spaceAfter=4, leftIndent=12,
    )

    col_w = [3.0 * inch, 2.2 * inch, 1.0 * inch]
    story = []

    # ------------------------------------------------------------------
    # Cover
    # ------------------------------------------------------------------
    story.append(Spacer(1, 1.2 * inch))

    logo_tbl = Table([["LOGO"]], colWidths=[1.5 * inch], rowHeights=[0.75 * inch])
    logo_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _DARK_BLUE),
        ("TEXTCOLOR",  (0, 0), (-1, -1), colors.white),
        ("FONTNAME",   (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 16),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(logo_tbl)
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("Diseño de Sistema BES", title_s))
    story.append(Paragraph(
        "Bombeo Electrosumergible",
        ParagraphStyle("sub2", fontName="Helvetica", fontSize=14,
                       textColor=_DARK_BLUE, alignment=TA_CENTER, spaceAfter=10),
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=_DARK_BLUE))
    story.append(Spacer(1, 0.25 * inch))

    tgt = f"{objectives.target_flow_rate:,.0f} STB/d" if objectives else "—"
    cov = Table([
        ["Pozo:",               well_name],
        ["Fecha:",              str(date.today())],
        ["Bomba seleccionada:", f"{dr.pump_manufacturer} {dr.pump_model}"],
        ["Tasa objetivo:",      tgt],
        ["Generado por:",       "BES Designer v1.0"],
    ], colWidths=[2.0 * inch, 4.0 * inch])
    cov.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 11),
        ("FONTNAME",      (0, 0), (0, -1),  "Helvetica-Bold"),
        ("TEXTCOLOR",     (0, 0), (0, -1),  _DARK_BLUE),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.5, _GRAY),
    ]))
    story.append(cov)
    story.append(Spacer(1, 0.4 * inch))
    story.append(Paragraph(
        "Basado en: K. Brown — The Technology of Artificial Lift Methods, Vol. 2b",
        caption_s,
    ))
    story.append(PageBreak())

    # ------------------------------------------------------------------
    # 1. Input data
    # ------------------------------------------------------------------
    story.append(Paragraph("1. Datos de Entrada", section_s))

    if reservoir:
        story.append(Paragraph("Reservorio", sub_s))
        story.append(_make_table([
            ["Parámetro",          "Valor",                              "Unidad"],
            ["Presión estática",    f"{reservoir.static_pressure:,.0f}", "psi"],
            ["Presión de burbuja",  f"{reservoir.bubble_point:,.0f}",   "psi"],
            ["PI",                  f"{reservoir.productivity_index:.2f}", "STB/d/psi"],
            ["Método IPR",          reservoir.ipr_method.name,           "—"],
            ["Temperatura",         f"{reservoir.reservoir_temp:.0f}",  "°F"],
            ["Mecanismo empuje",    reservoir.drive_mechanism.name,      "—"],
            ["Profundidad datum",   f"{reservoir.datum_depth:,.0f}",     "ft"],
        ], col_widths=col_w))
        story.append(Spacer(1, 8))

    if fluid:
        story.append(Paragraph("Fluido", sub_s))
        story.append(_make_table([
            ["Parámetro",          "Valor",                                   "Unidad"],
            ["API del crudo",       f"{fluid.oil_api:.1f}",                   "°API"],
            ["Corte de agua (WC)", f"{fluid.water_cut:.1%}",                  "fracción"],
            ["GOR",                 f"{fluid.gor:.0f}",                       "scf/STB"],
            ["Gr. esp. gas",        f"{fluid.gas_sg:.3f}",                    "—"],
            ["Gr. esp. agua",       f"{fluid.water_sg:.3f}",                  "—"],
            ["Viscosidad dead oil", f"{fluid.oil_viscosity_dead:.2f}",        "cp"],
            ["H2S",                 f"{fluid.h2s_content:.0f}",               "ppm"],
            ["CO2",                 f"{fluid.co2_content:.0f}",               "ppm"],
            ["Producción de arena", "Sí" if fluid.sand_production else "No",  "—"],
        ], col_widths=col_w))
        story.append(Spacer(1, 8))

    if well:
        story.append(Paragraph("Geometría del Pozo", sub_s))
        story.append(_make_table([
            ["Parámetro",            "Valor",                           "Unidad"],
            ["Profundidad total",     f"{well.total_depth:,.0f}",       "ft"],
            ["OD casing",            f"{well.casing_od:.3f}",           "in"],
            ["Peso casing",          f"{well.casing_weight:.1f}",       "lb/ft"],
            ["ID casing",            f"{well.casing_id:.3f}",           "in"],
            ["OD tubing",            f"{well.tubing_od:.3f}",           "in"],
            ["ID tubing",            f"{well.tubing_id:.3f}",           "in"],
            ["Perforaciones techo",  f"{well.perforations_top:,.0f}",   "ft"],
            ["Perforaciones base",   f"{well.perforations_bottom:,.0f}","ft"],
            ["Desviación máx.",      f"{well.deviation_max:.1f}",       "°"],
            ["Temp. cabezal",        f"{well.wellhead_temp:.0f}",       "°F"],
            ["BHT",                  f"{well.bottom_hole_temp:.0f}",    "°F"],
        ], col_widths=col_w))
        story.append(Spacer(1, 8))

    if surface:
        story.append(Paragraph("Condiciones Superficiales", sub_s))
        story.append(_make_table([
            ["Parámetro",                   "Valor",                                     "Unidad"],
            ["Presión cabezal req.",          f"{surface.wellhead_pressure_required:.0f}", "psi"],
            ["Longitud flowline",             f"{surface.flowline_length:.0f}",            "ft"],
            ["ID flowline",                   f"{surface.flowline_id:.2f}",                "in"],
            ["Elevación flowline",            f"{surface.flowline_elevation_change:.0f}",  "ft"],
            ["Presión separador",             f"{surface.separator_pressure:.0f}",         "psi"],
            ["Voltaje disponible",            f"{surface.power_supply_voltage:,.0f}",      "V"],
            ["Frecuencia",                    f"{surface.frequency:.0f}",                  "Hz"],
        ], col_widths=col_w))
        story.append(Spacer(1, 8))

    if objectives:
        story.append(Paragraph("Objetivos de Diseño", sub_s))
        story.append(_make_table([
            ["Parámetro",               "Valor",                                        "Unidad"],
            ["Tasa objetivo",            f"{objectives.target_flow_rate:,.0f}",          "STB/d"],
            ["Margen seguridad (prof.)", f"{objectives.safety_margin_depth:.0f}",        "ft"],
            ["Venteo de gas",            "Sí" if objectives.allow_gas_venting else "No", "—"],
            ["Máx. GIP en intake",       f"{objectives.max_gip:.1%}",                   "fracción"],
            ["Vida útil",                f"{objectives.design_life_years:.1f}",          "años"],
            ["VSD",                      "Sí" if objectives.use_vsd else "No",           "—"],
        ], col_widths=col_w))

    story.append(PageBreak())

    # ------------------------------------------------------------------
    # 2. TDH
    # ------------------------------------------------------------------
    story.append(Paragraph("2. Desglose del TDH", section_s))

    if all(x is not None for x in (reservoir, fluid, well, surface, objectives)):
        try:
            from core.tdh import calculate_tdh
            tdh = calculate_tdh(
                reservoir=reservoir, fluid=fluid, well=well,
                surface=surface, objectives=objectives,
                pump_depth=dr.pump_setting_depth, pip=dr.intake_pressure,
            )
            story.append(_make_table([
                ["Componente",             "Valor",                                     "Unidad"],
                ["Elevación vertical",      f"{tdh['vertical_lift_ft']:.1f}",           "ft"],
                ["Fricción en tubería",     f"{tdh['tubing_friction_ft']:.1f}",         "ft"],
                ["Presión cabezal (head)",  f"{tdh['wellhead_pressure_head_ft']:.1f}",  "ft"],
                ["PIP (head)",              f"{tdh['pip_head_ft']:.1f}",                "ft"],
                ["TOTAL TDH",              f"{tdh['tdh_ft']:.1f}",                     "ft"],
            ], col_widths=col_w, extra_styles=[
                ("FONTNAME",   (0, -1), (-1, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, -1), (-1, -1), _LIGHT_BLUE),
            ]))
            story.append(Paragraph(
                f"SG líquido: {tdh['sg_liquid']:.3f}  |  "
                f"Profundidad bomba: {tdh['pump_depth_ft']:.0f} ft  |  "
                f"PIP: {tdh['pip_psi']:.0f} psi",
                caption_s,
            ))
        except Exception:
            story.append(_make_table([
                ["Componente", "Valor", "Unidad"],
                ["TDH (diseño)", f"{dr.total_head_required:.1f}", "ft"],
                ["PIP",          f"{dr.intake_pressure:.1f}",     "psi"],
            ], col_widths=col_w))
    else:
        story.append(_make_table([
            ["Componente", "Valor", "Unidad"],
            ["TDH (diseño)", f"{dr.total_head_required:.1f}", "ft"],
            ["PIP",          f"{dr.intake_pressure:.1f}",     "psi"],
        ], col_widths=col_w))

    story.append(Spacer(1, 14))

    # ------------------------------------------------------------------
    # 3. Pump
    # ------------------------------------------------------------------
    story.append(Paragraph("3. Selección de Bomba", section_s))
    story.append(_make_table([
        ["Parámetro",              "Valor",                          "Unidad"],
        ["Fabricante",              dr.pump_manufacturer,             "—"],
        ["Serie",                   dr.pump_series,                   "—"],
        ["Modelo",                  dr.pump_model,                    "—"],
        ["OD",                      f"{dr.pump_od:.3f}",              "in"],
        ["Número de etapas",        f"{dr.num_stages}",               "—"],
        ["Eficiencia bomba",        f"{dr.pump_efficiency:.1%}",      "—"],
        ["Head / etapa",            f"{dr.head_per_stage:.1f}",       "ft/etapa"],
        ["HP / etapa",              f"{dr.hp_per_stage:.3f}",         "hp/etapa"],
        ["HP total bomba",          f"{dr.total_pump_hp:.1f}",        "hp"],
        ["Profundidad instalación", f"{dr.pump_setting_depth:.0f}",   "ft"],
        ["PIP (intake)",            f"{dr.intake_pressure:.0f}",      "psi"],
        ["GIP en intake",           f"{dr.gip_fraction:.1%}",         "fracción"],
        ["Tasa alcanzada",          f"{dr.flow_rate_achieved:.0f}",   "STB/d"],
    ], col_widths=col_w))
    story.append(Spacer(1, 14))

    # ------------------------------------------------------------------
    # 4. Motor
    # ------------------------------------------------------------------
    story.append(Paragraph("4. Selección de Motor", section_s))
    story.append(_make_table([
        ["Parámetro",  "Valor",                    "Unidad"],
        ["Fabricante",  dr.motor_manufacturer,      "—"],
        ["Modelo",      dr.motor_model,             "—"],
        ["HP nominal",  f"{dr.motor_hp:.0f}",       "hp"],
        ["Voltaje",     f"{dr.motor_voltage:.0f}",  "V"],
        ["Amperaje",    f"{dr.motor_amperage:.0f}", "A"],
        ["OD motor",    f"{dr.motor_od:.3f}",       "in"],
        ["Longitud",    f"{dr.motor_length:.1f}",   "ft"],
    ], col_widths=col_w))
    story.append(Spacer(1, 14))

    # ------------------------------------------------------------------
    # 4b. Seal / protector
    # ------------------------------------------------------------------
    story.append(Paragraph("4b. Sello / Protector", section_s))
    if dr.seal_model:
        story.append(_make_table([
            ["Parámetro",              "Valor",                                "Unidad"],
            ["Fabricante",              dr.seal_manufacturer,                   "—"],
            ["Modelo",                  dr.seal_model,                          "—"],
            ["Tipo",                    dr.seal_type,                           "—"],
            ["Capacidad de empuje",    f"{dr.seal_thrust_capacity_lbs:.0f}",   "lbs"],
            ["Empuje axial estimado",  f"{dr.axial_thrust_lbs:.0f}",           "lbs"],
        ], col_widths=col_w))
    else:
        story.append(Paragraph(
            "Sin protector compatible en catálogo para esta serie de motor.",
            caption_s,
        ))
    story.append(Spacer(1, 14))

    # ------------------------------------------------------------------
    # 5. Electrical
    # ------------------------------------------------------------------
    story.append(Paragraph("5. Diseño Eléctrico", section_s))
    story.append(_make_table([
        ["Parámetro",                  "Valor",                              "Unidad"],
        ["Tipo de cable",               dr.cable_type,                        "—"],
        ["Calibre (AWG)",              f"#{dr.cable_awg}",                   "—"],
        ["Caída de tensión cable",     f"{dr.cable_voltage_drop:.0f}",       "V"],
        ["Voltaje superficial req.",   f"{dr.surface_voltage_required:.0f}", "V"],
        ["Transformador",              f"{dr.transformer_kva:.0f}",          "kVA"],
        ["Eficiencia del sistema",     f"{dr.system_efficiency:.1%}",        "—"],
        ["Frecuencia operación",       f"{dr.operating_frequency:.0f}",      "Hz"],
    ], col_widths=col_w))
    story.append(Spacer(1, 14))

    # ------------------------------------------------------------------
    # 5b. Accessories (gas handling + monitoring)
    # ------------------------------------------------------------------
    story.append(Paragraph("5b. Manejo de Gas y Monitoreo", section_s))
    _gh = (
        f"{dr.gas_handler_manufacturer} {dr.gas_handler_model} "
        f"({dr.gas_handler_type}, η {dr.gas_handler_efficiency:.0%})"
        if dr.gas_handler_model else "No requerido (GIP bajo)"
    )
    _sn = (
        f"{dr.sensor_manufacturer} {dr.sensor_model}"
        if dr.sensor_model else "No disponible en catálogo"
    )
    story.append(_make_table([
        ["Parámetro",          "Valor",  "Unidad"],
        ["Separador de gas",    _gh,      "—"],
        ["Sensor de fondo",     _sn,      "—"],
    ], col_widths=col_w))
    story.append(Spacer(1, 14))

    # ------------------------------------------------------------------
    # 6. Warnings
    # ------------------------------------------------------------------
    all_w = list(dr.warnings)
    if dr.gip_fraction > 0.30:
        all_w.append(
            f"CRÍTICO — Gas libre en intake: {dr.gip_fraction:.1%}. "
            "Se requiere separador de gas de fondo."
        )
    elif dr.gip_fraction > 0.10:
        all_w.append(
            f"AVISO — Gas libre en intake: {dr.gip_fraction:.1%}. "
            "Considerar separador de gas."
        )

    if all_w:
        story.append(Paragraph("6. Advertencias y Recomendaciones", section_s))
        for w in all_w:
            story.append(Paragraph(f"• {w}", warn_s))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    pdf_bytes = buffer.getvalue()

    if output_path is not None:
        with open(output_path, "wb") as fh:
            fh.write(pdf_bytes)
        return output_path
    return pdf_bytes
