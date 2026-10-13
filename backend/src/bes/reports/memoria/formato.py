# -*- coding: utf-8 -*-
"""Formato de la memoria de cálculo: números, bloques de ecuación, tablas y citas.

Las citas de :data:`REFS` están verificadas contra la página impresa de los
libros del proyecto. Brown Vol. 2b = página impresa del escaneo; Takács,
Ahmed y Beggs = página impresa. Lo que no está en ningún libro se declara
«Criterio del proyecto».
"""
from __future__ import annotations

PROY = "Criterio del proyecto"
B2 = "Brown Vol. 2b, "
B4 = "Brown Vol. 4, "

REFS: dict[str, str] = {
 "Gravedad específica del líquido": B2 + "Sección 4.5324 (pág. 63)",
 "Caída en el anular": B2 + "Ejemplo #1C (pág. 68)",
 "PIP — presión en la admisión": B2 + "Ejemplo #1C (pág. 68)",
 "Sumergencia": B2 + "Sección 4.5324 (pág. 63)",
 "TDH — altura dinámica total": B2 + "Sección 4.5324 (págs. 62 a 64)",
 "Gradiente por fricción": B2 + "Sección 4.5324, Fig. 4.53 (pág. 63). Darcy-Weisbach: " + PROY,
 "Cantidad de etapas": B2 + "Sección 4.5323 (pág. 61)",
 "Potencia al eje": B2 + "Sección 4.5323 (pág. 62)",
 "Potencia sobre el eje": B2 + "Sección 4.5323 (pág. 62)",
 "Potencia que transmite el eje": B2 + "Sección 4.5323 (pág. 62)",
 "Potencia mínima de placa": PROY,
 "Diámetro máximo admisible": PROY,
 "Temperatura mínima de placa": PROY,
 "Tensión objetivo": PROY + ", con base en " + B2 + "Sección 4.5325 (pág. 65)",
 "Carga axial estimada": "Takács (2018), Sección 2.3.2.5 (págs. 32 y 33). Margen 1,20: " + PROY,
 "Tipo según la desviación del pozo": B2 + "Sección 4.525 (págs. 59 y 60). Límite de 30°: " + PROY,
 "Carga sobre el cojinete de empuje": "Takács (2018), Sección 2.3.2.5 (págs. 32 y 33)",
 "Caída total de tensión": B2 + "Sección 4.5325, Fig. 4.54 (pág. 64)",
 "① Caída por cada 1000 ft": "Takács (2018), Sección 5.3.6.3 (pág. 257)",
 "② Caída relativa a la placa": "Takács (2018), Sección 5.3.6.3 (pág. 257)",
 "Potencia disipada": "Takács (2018), ec. 5.25 (pág. 258)",
 "Velocidad del fluido": "Takács (2018), Sección 3.3.1.4 (pág. 88)",
 "Tensión requerida en superficie": B2 + "Sección 4.5325 (pág. 65)",
 "Potencia aparente": B2 + "Sección 4.5326, ec. 4.51 (pág. 65)",
 "Relación gas/líquido en la admisión": B2 + "Sección 4.523 (pág. 59)",
 "Gas que queda tras separar": "Takács (2018), ecs. 5.36 y 5.37 (pág. 274)",
 "Eficiencia del separador": "Takács (2018), Fig. 4.19 (pág. 187), curvas de 70 a 90 %. El valor de 75 %: supuesto del proyecto",
 "Temperatura en la admisión": PROY,
 "Presión de descarga": B2 + "Sección 4.53102, paso 2 (pág. 74)",
 "GOR que sube por el tubing": PROY,
 "GOR en la bomba": PROY,
 "Gas disuelto en la admisión": "Ahmed (2010), ec. 2-69 (pág. 79)",
 "Factor de volumen del gas": "Ahmed (2010), ec. 2-54 (pág. 66)",
 "Fracción de gas libre": "Takács (2018), Sección 4.4.2, ecs. 4.15, 4.22 y 4.23 (págs. 165 a 168)",
 "La bisagra del método — presión que aporta cada etapa": B2 + "Sección 4.53102, paso 12 (pág. 74)",
 "Etapas del tramo": B2 + "Sección 4.53102, paso 13 (pág. 74)",
 "Etapas totales": B2 + "Sección 4.53102, paso 14 (pág. 74)",
 "Potencia total al eje": B2 + "Sección 4.53102, pasos 15 y 16 (pág. 74)",
 "Salto de presión": B2 + "Sección 4.53102, paso 3 (pág. 74)",
 "Cantidad de escalones": B2 + "Sección 4.53102, paso 4 (pág. 74)",
 "TDH equivalente del método": PROY,
 "Paso 4a — viscosidad cinemática": B2 + "Sección 4.53112, paso 4 (pág. 90)",
 "Paso 5 — corrección por corte de agua": B2 + "Sección 4.53112, paso 5 (pág. 90)",
 "Paso 7a — caudal equivalente en agua": B2 + "Sección 4.53112, paso 6 (pág. 90)",
 "Paso 7b — altura equivalente en agua": B2 + "Sección 4.53112, paso 6 (pág. 90)",
 "Potencia corregida": B2 + "Sección 4.53112, paso 6 (pág. 90)",
 "Caudal con que se entra a la curva": B2 + "Sección 4.53112, paso 6 (pág. 90)",
}


def n(x, d: int = 2) -> str:
    """Número con coma decimal y espacio de miles; «—» si falta."""
    if x is None:
        return "—"
    if isinstance(x, str):
        return x
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def _ref(nom: str, form: str, ref: str | None) -> str | None:
    if nom.startswith("② Pérdida por fricción"):
        return (B2 + "Sección 4.5324, Fig. 4.53 (pág. 63)") if "0.2083" in (form or "") else PROY
    return REFS.get(nom, ref)


def eq(nom, form, sust, res, uni, ref=None) -> str:
    """Bloque de un paso: nombre, fórmula, sustitución, resultado y cita."""
    ref = _ref(nom, form, ref)
    h = f'<div class="eq"><div class="eq-n">{nom}</div><div class="eq-f">{form}</div>'
    if sust:
        h += f'<div class="eq-s">= {sust}</div>'
    h += f'<div class="eq-r">= <b>{res}</b> <span class="u">{uni}</span></div>'
    if ref:
        h += f'<div class="eq-ref">{ref}</div>'
    return h + "</div>"


def tabla(filas, cab=None, cls: str = "") -> str:
    h = f'<table class="t {cls}">'
    if cab:
        h += "<thead><tr>" + "".join(f"<th>{c}</th>" for c in cab) + "</tr></thead>"
    h += "<tbody>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas)
    return h + "</tbody></table>"


def fig(src: str, cap: str) -> str:
    return f'<figure><img src="{src}"><figcaption>{cap}</figcaption></figure>'


def paso(num: int, tit: str, bloques: list[str]) -> str:
    return (f'<div class="paso"><div class="paso-h"><span class="num">{num}</span>{tit}</div>'
            + "".join(bloques) + "</div>")


CSS = """
@page { size: A4; margin: 15mm 14mm 16mm 14mm;
  @bottom-center { content: "BES Designer · memoria de cálculo · pág. " counter(page) " de " counter(pages);
    font: 7.5pt 'DejaVu Sans'; color:#888; } }
@page :first { @bottom-center { content: ""; } }
@media screen { body{max-width:190mm;margin:10mm auto} .noprint{margin:0 0 12px 0} }
@media print { .noprint{display:none} }
*{box-sizing:border-box}
body{font-family:'DejaVu Sans',Arial,sans-serif;font-size:8.6pt;color:#222;line-height:1.4}
h1{font-size:22pt;color:#1F3864;margin:0 0 4px 0}
h2{font-size:13.5pt;color:#fff;background:#1F3864;padding:6px 10px;margin:0 0 10px 0;
   page-break-before:always;page-break-after:avoid;border-radius:3px}
h3{font-size:10pt;color:#1F3864;margin:14px 0 6px 0;page-break-after:avoid;
   border-bottom:1.5px solid #1F3864;padding-bottom:2px}
.port{text-align:center;padding-top:52mm}
.port .sub{font-size:12pt;color:#555;margin-top:6px}
.port .meta{margin-top:34mm;font-size:9pt;color:#666}
.paso{margin:0 0 12px 0}
.paso-h{background:#EAF0FA;border-left:4px solid #1F3864;padding:5px 9px;font-weight:bold;
        color:#1F3864;font-size:9.6pt;margin-bottom:7px;page-break-after:avoid}
.paso-h .num{display:inline-block;background:#1F3864;color:#fff;width:17px;height:17px;line-height:17px;
             text-align:center;border-radius:50%;margin-right:7px;font-size:8pt}
.eq{border-left:2px solid #C5D3EA;padding:3px 0 3px 9px;margin:0 0 7px 0;page-break-inside:avoid}
.eq-n{font-weight:bold;color:#333;font-size:8.4pt}
.eq-f{font-family:'DejaVu Serif',Georgia,serif;color:#7030A0;margin:2px 0;font-size:9pt}
.eq-s{font-family:'DejaVu Sans Mono',monospace;color:#555;font-size:7.8pt;margin:1px 0}
.eq-r{font-size:9.4pt;color:#1F3864;margin-top:2px}
.eq-r b{font-size:10.4pt}
.eq .u{color:#888;font-size:8pt;font-style:italic}
.eq-ref{font-size:7pt;color:#999;font-style:italic;margin-top:2px}
.pvt td,.pvt th{font-size:6.6pt;padding:2px 3px;text-align:right}.pvt td{white-space:nowrap}.pvt td:last-child{text-align:left}.cap{font-size:8pt;text-align:center;margin:3px 0 10px 0}
table.t{border-collapse:collapse;width:100%;margin:6px 0 10px 0;font-size:7.6pt}
table.t th{background:#1F3864;color:#fff;padding:4px 5px;text-align:left;font-weight:bold}
table.t td{border-bottom:1px solid #DDE4F0;padding:3px 5px;vertical-align:top}
table.t tr:nth-child(even) td{background:#F6F8FC}
table.mini td:nth-child(2){text-align:right;font-weight:bold;color:#1F3864;white-space:nowrap}
table.mini td:nth-child(3){color:#888;font-style:italic;width:52px}
table.lad{font-size:6.6pt} table.lad td{padding:2px 3px;text-align:right}
table.lad td:nth-child(2),table.lad td:nth-child(4){text-align:center}
table.apar td:first-child{width:170px;color:#555}
.dos{display:flex;gap:10px}.dos>div{flex:1}
.sub{font-weight:bold;color:#1F3864;font-size:9.2pt;margin:12px 0 5px 0;
     border-bottom:1px dotted #9AB;padding-bottom:2px;page-break-after:avoid}
figure{margin:8px 0;text-align:center;page-break-inside:avoid}
figure img{width:100%;max-width:430px}
figcaption{font-size:7.2pt;color:#777;font-style:italic;margin-top:3px}
.figs{display:flex;gap:8px}.figs figure{flex:1}.figs img{max-width:100%}
.res{background:#E8F3E8;border:1.5px solid #2E7D32;border-radius:4px;padding:8px 11px;margin:10px 0}
.res .tt{font-weight:bold;color:#2E7D32;font-size:9.6pt;margin-bottom:4px}
.flow{background:#F7F9FC;border:1px solid #C5D3EA;border-radius:4px;padding:9px 12px;
      font-family:'DejaVu Sans Mono',monospace;font-size:7.4pt;line-height:1.55;white-space:pre}
"""
