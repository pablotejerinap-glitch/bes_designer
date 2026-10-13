# -*- coding: utf-8 -*-
"""Memoria de cálculo del método de gas paso a paso (bes.core.gas_paso_a_paso).

Recibe lo que ya calculó el método (bloques de pasos, evolución del fluido,
escalones y resumen) y lo arma con el mismo formato que el resto de la
memoria: por cada cuenta, fórmula, sustitución, resultado y fuente.
"""
from __future__ import annotations

import re

from bes.reports.memoria.formato import CSS, n, paso, tabla

_DEC = re.compile(r"(?<=\d)\.(?=\d)")


def _coma(texto: str) -> str:
    """Coma decimal en los números de la sustitución."""
    return _DEC.sub(",", texto or "")


def _cuenta(p: dict) -> str:
    h = f'<div class="eq"><div class="eq-n">{p["nombre"]}</div><div class="eq-f">{p["formula"]}</div>'
    if p.get("sustitucion"):
        h += f'<div class="eq-s">= {_coma(p["sustitucion"])}</div>'
    v = p.get("valor")
    if v is not None:
        d = 0 if float(v).is_integer() else 6 if abs(v) < 1 else 4 if abs(v) < 100 else 2
        h += f'<div class="eq-r">= <b>{n(v, d)}</b> <span class="u">{p.get("unidad", "")}</span></div>'
    if p.get("cita"):
        h += f'<div class="eq-ref">{p["cita"]}</div>'
    return h + "</div>"


def _evolucion(filas: list[dict]) -> str:
    return tabla(
        [(f["comentario"] or f["zona"], n(f["p"], 2), n(f["t"], 2), n(f["gor"], 2), n(f["z"], 5),
          n(f["rs"], 3), n(f["bg_mscf"], 4), n(f["bo"], 4), n(f["bw"], 4), n(f["vg"], 2),
          n(f["v_total"], 2), n(f["sg"], 4)) for f in filas],
        ["ubicación", "P<br>[psig]", "T<br>[°F]", "GOR<br>[scf/STB]", "Z", "Rs<br>[scf/STB]",
         "Bg<br>[bbl/Mscf]", "Bo<br>[bbl/STB]", "Bw<br>[bbl/STB]", "Vg<br>[b/d]", "V total<br>[b/d]",
         "SG<br>mezcla"], "apar")


def _escalones(filas: list[dict]) -> str:
    return tabla(
        [(str(i), n(e["p0"], 2), n(e["p1"], 2), n(e["dp"], 2), n(e["q"], 2), n(e["grad"], 5),
          n(e["altura"], 2), n(e["h"], 4), n(e["psi_et"], 4), n(e["n"], 3), n(e["hp_et"], 5),
          n(e["sg"], 4), n(e["hp"], 3)) for i, e in enumerate(filas, 1)],
        ["#", "P inicial<br>[psig]", "P final<br>[psig]", "ΔP<br>[psi]", "q prom<br>[b/d]",
         "grad<br>[psi/ft]", "altura<br>[ft]", "H/etapa<br>[ft]", "psi/etapa", "etapas",
         "hp/etapa", "SG", "hp"], "apar")


def _resumen(r: dict) -> str:
    carc = " + ".join(f'{c["cantidad"]} × carcasa {c["carcasa"]} ({c["etapas"]} etapas)'
                      for c in (r.get("carcasas") or [])) or "—"
    filas = [
        ("Pwf", f'{n(r.get("pwf"))} psig'),
        ("PIP", f'{n(r.get("pip"))} psig'),
        ("GOR en la bomba", f'{n(r.get("gor_bomba"), 3)} scf/STB'),
        ("Presión de descarga", f'{n(r.get("p_descarga"))} psig'),
        ("Bomba", f'{r.get("bomba")} a {n(r.get("frecuencia_hz"), 0)} Hz; {r.get("etapas")} etapas; '
                  f'{n(r.get("hp"))} hp'),
        ("Eje y carcasa", f'eje {r.get("eje")}; carcasa {r.get("carcasa")}'),
        ("Carcasas", f'{carc}; {n(r.get("largo_bomba_ft"), 1)} ft'),
        ("Protector", f'{r.get("protector")} (P/N {r.get("protector_pn")}); elastómero {r.get("elastomero")}'),
        ("Motor", f'{r.get("motor_n")} × {r.get("motor")}; {n(r.get("motor_hp"), 1)} hp; '
                  f'{n(r.get("motor_voltaje"), 0)} V; {n(r.get("motor_corriente"))} A'),
        ("Cable", f'{r.get("cable")}; {n(r.get("cable_largo_ft"), 0)} ft; MLE {n(r.get("mle_largo_ft"), 1)} ft'),
        ("Superficie", f'{n(r.get("u_superficie"), 1)} V; {n(r.get("kva"), 1)} kVA'),
        ("Tablero", str(r.get("tablero"))),
        ("Transformador", f'{n(r.get("transformador_kva"), 0)} kVA (P/N {r.get("transformador_pn")})'),
    ]
    return tabla(filas, ["componente", "resultado"], "apar")


def _datos(d: dict) -> str:
    filas = [
        ("Presión estática del reservorio, Pr", f'{n(d["pr"])} psig'),
        ("Presión de burbuja, Pb", f'{n(d["pb"])} psig'),
        ("Ensayo: Pwf y caudal", f'{n(d["pwf_ensayo"])} psig; {n(d["q_ensayo"])} STB/d'),
        ("Caudal objetivo", f'{n(d["q_objetivo"])} STB/d'),
        ("Petróleo, corte de agua, GOR", f'{n(d["api"], 1)} °API; {n(d["wc"] * 100, 1)} %; {n(d["gor"], 1)} scf/STB'),
        ("Gravedad del gas y del agua", f'{n(d["gas_sg"], 3)}; {n(d["water_sg"], 3)}'),
        ("Temperatura en boca y en fondo", f'{n(d["t_boca"], 1)} °F; {n(d["t_fondo"], 1)} °F'),
        ("Profundidad de punzados y de la bomba", f'{n(d["d_pwf"])} ft; {n(d["d_bomba"])} ft'),
        ("Presión en boca de pozo", f'{n(d["p_boca"])} psig'),
        ("Tubing ID y casing ID", f'{n(d["d_tubing_in"], 3)} in; {n(d["casing_id"], 3)} in'),
        ("Frecuencia de diseño", f'{n(d["frecuencia_hz"], 0)} Hz'),
        ("Eficiencia del separador", f'{n(d["eta_sep"] * 100, 0)} %'),
        ("Incremento de presión en la bomba", f'{n(d["incremento_psi"], 0)} psi'),
    ]
    return tabla(filas, ["dato", "valor"], "apar")


def memoria_gas_html(calculo: dict, datos: dict, titulo: str = "") -> str:
    """HTML imprimible de la memoria del método de gas paso a paso.

    ``calculo`` es la respuesta del método (bloques, tabla_evolucion,
    escalones, resumen); ``datos`` son los datos de entrada con los nombres de
    ``bes.core.gas_paso_a_paso.calcular``.
    """
    H = [f"<html><head><meta charset='utf-8'><title>BES Designer · memoria de cálculo</title>"
         f"<style>{CSS}</style></head><body>",
         '<div class="noprint"><button onclick="window.print()">Imprimir / guardar como PDF</button></div>',
         '<div class="port"><h1>BES Designer</h1>'
         '<div class="sub" style="border:none">Memoria de cálculo paso a paso</div>'
         f'<div class="sub" style="border:none;font-size:10pt">{titulo or "Pozo con gas"}</div>'
         '<div class="meta">'
         'Metodología: Brown, K. E. (1980), <i>The Technology of Artificial Lift Methods</i>, Vol. 2b, y Vol. 4<br>'
         'Complementada con Takács (2018) y Ahmed (2010)<br><br>'
         'Proyecto Integrador Profesional · Pablo Tejerina<br>'
         'Facultad de Ingeniería · Universidad Nacional del Comahue</div></div>',
         "<h2>Datos de entrada</h2>", _datos(datos), "<h2>Cálculo paso a paso</h2>"]
    for i, b in enumerate(calculo["bloques"], 1):
        num, tit = b["titulo"].split(". ", 1) if ". " in b["titulo"] else (str(i), b["titulo"])
        H.append(paso(i, f"{num}. {_coma(tit)}", [_cuenta(p) for p in b["pasos"]]))
        if b["titulo"].startswith("5.") and calculo.get("tabla_evolucion"):
            H.append("<h3>Evolución del fluido en el pozo</h3>")
            H.append(_evolucion(calculo["tabla_evolucion"]))
        if b["titulo"].startswith("7.") and calculo.get("escalones"):
            H.append("<h3>Escalones de presión dentro de la bomba</h3>")
            H.append(_escalones(calculo["escalones"]))
    H.append("<h2>Resumen del diseño</h2>")
    H.append(_resumen(calculo["resumen"]))
    return "".join(H) + "</body></html>"
