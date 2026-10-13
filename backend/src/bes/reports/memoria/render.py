# -*- coding: utf-8 -*-
"""HTML de la memoria de cálculo, con el mismo modelo que la memoria de la tesis.

Cada caso se desarrolla paso a paso: IPR, PIP, pérdidas y TDH (o gas libre y
escalera de incrementos), corrección por viscosidad si corresponde, selección
de la bomba sobre la curva y selección completa del aparejo. Sin notas ni
avisos: sólo fórmula, sustitución, resultado, unidad y cita.
"""
from __future__ import annotations

import math

from bes.reports.memoria import graficos as G
from bes.reports.memoria.aparejo import intermedios
from bes.reports.memoria.formato import B2, B4, CSS, eq, fig, n, paso, tabla
from bes.reports.memoria.pvt import recorrido_anular, recorrido_tubing, tabla_pvt, tabla_pvt_fondo

ND = ("None", None, "")

DIAGRAMA = """   DATOS DEL POZO
        |
   [1] IPR ............... cuanto entrega el reservorio y a que Pwf
        |
   [2] PIP .............. presion que llega a la boca de la bomba
        |                  (recorrido por el anular, PVT punto a punto)
        |
   [3] PERDIDAS DE CARGA . que correlacion corresponde
        |                  hay gas libre? --> SI --> Poettmann & Carpenter
        |                                    NO --> mu <= 5 cp --> Hazen-Williams
        |                                           mu >  5 cp --> Darcy-Weisbach
        |
   [4] TDH ............... elevacion neta + friccion + presion de boca
        |
   [5] BOMBA ............. se lee la curva del catalogo al caudal de diseño
        |                  etapas = TDH / (ft por etapa)
        |
  [5b] SI HAY GAS ....... escalera de incrementos de presion
  [5c] SI ES VISCOSO .... correccion de Riling (laminas 4L + tablas 4.52x)
        |
   [6] MOTOR ............. HP eje x 1.10, OD, temperatura, tension objetivo
   [7] EJE ............... estandar / alta resistencia / ultra alta
   [8] SELLO ............. empuje axial, laberintico o bolsa
   [9] CABLE ............. ampacidad x 1.25, temperatura, que entre
  [10] VERIF. ELECTRICA .. 30 V/1000ft y 5 % de placa
  [11] REFRIGERACION ..... v = Q / A_anular >= 1 ft/s
  [12] SUPERFICIE ........ tension, kVA, transformador, tablero o VSD
  [13] CARCASAS ......... tamaños discretos, etapas ciegas, presion, cojinete"""

REGLAS = [
    ("Gas libre &gt; 5 % en la admisión", "escalera de incrementos en vez de caudal único", "Takács (2018), Sección 1.3.2"),
    ("Gas libre en la admisión", "Poettmann &amp; Carpenter para el recorrido multifásico",
     "Poettmann y Carpenter, descrito en Beggs (2003), pág. 84"),
    ("Sin gas y μ ≤ 5 cp", "Hazen-Williams para la fricción en el tubing", "Brown Vol. 2b, Sección 4.5324, Fig. 4.53 (pág. 63)"),
    ("Sin gas y μ &gt; 5 cp", "Darcy-Weisbach con Reynolds", "Criterio del proyecto"),
    ("Viscosidad ≥ 100 SSU", "corrección de Riling con las láminas del Apéndice 4L",
     "Criterio del proyecto; procedimiento: Brown Vol. 2b, Sección 4.53112 (pág. 90)"),
    ("Gas en la bomba &gt; 10 %", "hace falta separador; se sube por la escalera de manejo de gas",
     "Brown Vol. 2b, Sección 4.523 (pág. 59)"),
    ("HP<sub>eje</sub> &gt; límite estándar", "eje de alta resistencia", "Wood Group ESP Catalogue"),
    ("Velocidad en el anular &lt; 1 ft/s", "el motor no se refrigera", "Takács (2018), Sección 3.3.1.4 (pág. 88)"),
    ("Caída &gt; 30 V/1000 ft", "el cable no sirve: se sube calibre o tensión",
     "Takács (2018), Sección 5.3.6.3 (pág. 257) y ec. 3.8 (pág. 86)"),
]


# --------------------------------------------------------------------- datos
def tabla_datos(r: dict) -> str:
    P = r["pozo"]; R = P["reservoir"]; F = P["fluid"]; W = P["well"]; S = P["surface"]; O = P["objectives"]
    met = {"linear": "lineal", "vogel": "Vogel", "fetkovich": "Fetkovich"}.get(R["ipr_method"], R["ipr_method"])
    izq = [("Presión estática  P<sub>r</sub>", n(R["static_pressure"], 1), "psi"),
           ("Ensayo: caudal", n(R["test_rate"], 1), "STB/d"),
           ("Ensayo: presión de fondo", n(R["test_pwf"], 1), "psi"),
           ("Método de IPR", met, ""),
           ("Presión de burbuja  P<sub>b</sub>", n(R["bubble_point"], 1), "psi"),
           ("Temperatura de reservorio", n(R["reservoir_temp"], 1), "°F"),
           ("Temperatura de boca", n(W["wellhead_temp"], 1), "°F"),
           ("<b>Caudal objetivo</b>", "<b>" + n(O["target_flow_rate"], 1) + "</b>", "STB/d")]
    der = [("Gravedad del petróleo", n(F["oil_api"], 1), "°API"),
           ("Corte de agua", n(F["water_cut"] * 100, 1), "%"),
           ("GOR", n(F["gor"], 1), "scf/STB"),
           ("γ<sub>g</sub> / γ<sub>w</sub>", n(F["gas_sg"], 2) + " / " + n(F["water_sg"], 3), ""),
           ("Profundidad total", n(W["total_depth"], 1), "ft"),
           ("Punzados", n(W["perforations_top"], 0) + " a " + n(W["perforations_bottom"], 0), "ft"),
           ("Casing OD / ID", n(W["casing_od"], 3) + " / " + n(W["casing_id"], 3), "in"),
           ("Tubing OD / ID", n(W["tubing_od"], 3) + " / " + n(W["tubing_id"], 3), "in"),
           ("Presión en boca  P<sub>wh</sub>", n(S["wellhead_pressure_required"], 1), "psi"),
           ("Frecuencia", n(S["frequency"], 0), "Hz")]
    return ('<div class="dos"><div>' + tabla(izq, ["dato", "valor", "unidad"], "mini")
            + '</div><div>' + tabla(der, ["dato", "valor", "unidad"], "mini") + '</div></div>')


# ----------------------------------------------------------------------- IPR
def _vogel_pwf(p_ref: float, frac: float) -> float:
    """Despeje de la ecuación de Vogel (Brown Vol. 4, ec. 2.20)."""
    return 0.125 * p_ref * (-1 + math.sqrt(81 - 80 * frac))


def bloque_ipr(r: dict):
    """Devuelve (bloques, pwf de diseño, curva q(pwf), etiqueta de la curva)."""
    R = r["pozo"]["reservoir"]; O = r["pozo"]["objectives"]
    Pr = R["static_pressure"]; pwf_t = R["test_pwf"]; q_t = R["test_rate"]; qt = O["target_flow_rate"]
    met = R["ipr_method"]; b: list[str] = []
    if met == "linear":
        J = q_t / (Pr - pwf_t); pwf = Pr - qt / J
        b += [eq("Índice de productividad", "J = q<sub>ensayo</sub> / (P<sub>r</sub> − P<sub>wf,ensayo</sub>)",
                 f"{n(q_t,1)} / ({n(Pr,1)} − {n(pwf_t,1)}) = {n(q_t,1)} / {n(Pr-pwf_t,1)}",
                 n(J, 6), "STB/d/psi", B4 + "ec. 2.31 (pág. 15)"),
              eq("Presión de fondo al caudal objetivo", "P<sub>wf</sub> = P<sub>r</sub> − q / J",
                 f"{n(Pr,1)} − {n(qt,1)} / {n(J,6)} = {n(Pr,1)} − {n(qt/J,2)}", n(pwf, 2), "psi",
                 B4 + "ec. 2.31 (pág. 15)"),
              eq("AOF (caudal a P<sub>wf</sub> = 0)", "AOF = J · P<sub>r</sub>",
                 f"{n(J,6)} × {n(Pr,1)}", n(J * Pr, 1), "STB/d", "")]
        return b, pwf, (lambda p: J * (Pr - p)), "lineal"

    if met == "fetkovich":
        nn = R.get("fetkovich_n") or 1.0
        C = q_t / (Pr ** 2 - pwf_t ** 2) ** nn
        pwf = math.sqrt(Pr ** 2 - (qt / C) ** (1 / nn))
        ref = "Beggs (2003), ec. 2-54 (pág. 31)"
        b += [eq("Coeficiente de entregabilidad", "C = q<sub>ensayo</sub> / (P<sub>r</sub>² − P<sub>wf,ensayo</sub>²)<sup>n</sup>",
                 f"{n(q_t,1)} / ({n(Pr,1)}² − {n(pwf_t,1)}²)<sup>{n(nn,3)}</sup>", f"{C:.6e}".replace(".", ","),
                 "STB/d/psi<sup>2n</sup>", ref),
              eq("Presión de fondo al caudal objetivo", "P<sub>wf</sub> = [ P<sub>r</sub>² − (q / C)<sup>1/n</sup> ]<sup>1/2</sup>",
                 f"[ {n(Pr,1)}² − ({n(qt,1)} / {C:.6e})<sup>1/{n(nn,3)}</sup> ]<sup>1/2</sup>".replace("e-", "e−"),
                 n(pwf, 4), "psi", ref)]
        return b, pwf, (lambda p: C * (Pr ** 2 - p ** 2) ** nn), "Fetkovich"

    # --- Vogel: puro (saturado) o compuesto (subsaturado) ---------------------
    pb = R.get("bubble_point") or 0.0
    pb = min(pb, Pr) if pb > 0 else Pr
    if pb >= Pr:
        x = pwf_t / Pr; br = 1 - 0.2 * x - 0.8 * x * x; qmax = q_t / br
        pwf = _vogel_pwf(Pr, qt / qmax)
        b += [eq("Cociente P<sub>wf</sub> / P<sub>r</sub> del ensayo", "P<sub>wf</sub> / P<sub>r</sub>",
                 f"{n(pwf_t,1)} / {n(Pr,1)}", n(x, 6), "—", B4 + "Ejemplo #5 (pág. 14)"),
              eq("Denominador de la ec. 2.19", "1 − 0,2·(P<sub>wf</sub>/P<sub>r</sub>) − 0,8·(P<sub>wf</sub>/P<sub>r</sub>)²",
                 f"1 − 0,2({n(x,6)}) − 0,8({n(x,6)})² = 1 − {n(0.2*x,6)} − {n(0.8*x*x,6)}",
                 n(br, 6), "—", B4 + "ec. 2.19 (pág. 14); Fig. 2.14 (Vogel)"),
              eq("Caudal máximo", "q<sub>o max</sub> = q<sub>o</sub> / [ 1 − 0,2·(P<sub>wf</sub>/P<sub>r</sub>) − 0,8·(P<sub>wf</sub>/P<sub>r</sub>)² ]",
                 f"{n(q_t,1)} / {n(br,6)}", n(qmax, 4), "STB/d", B4 + "ec. 2.19 (pág. 14)"),
              eq("Índice de productividad", "J = 1,8 · q<sub>o max</sub> / P<sub>b</sub>, con P<sub>b</sub> = P<sub>r</sub>",
                 f"1,8 × {n(qmax,4)} / {n(Pr,1)}", n(1.8 * qmax / Pr, 6), "STB/d/psi",
                 B4 + "ecs. 2.25 y 2.26 (pág. 15)"),
              eq("Presión de fondo al caudal objetivo",
                 "P<sub>wf</sub> = 0,125 · P<sub>r</sub> · [ −1 + √(81 − 80·(q<sub>o</sub>/q<sub>o max</sub>)) ]",
                 f"0,125 × {n(Pr,1)} × [ −1 + √(81 − 80×{n(qt/qmax,6)}) ]", n(pwf, 4), "psi",
                 B4 + "ec. 2.20 (pág. 14)")]
        return b, pwf, (lambda p: qmax * (1 - 0.2 * (p / Pr) - 0.8 * (p / Pr) ** 2)), "Vogel"

    if pwf_t >= pb:
        J = q_t / (Pr - pwf_t)
        b.append(eq("Índice de productividad", "J = q<sub>ensayo</sub> / (P<sub>r</sub> − P<sub>wf,ensayo</sub>)",
                    f"{n(q_t,1)} / ({n(Pr,1)} − {n(pwf_t,1)})", n(J, 6), "STB/d/psi", B4 + "ec. 2.31 (pág. 15)"))
    else:
        x = pwf_t / pb; br = 1 - 0.2 * x - 0.8 * x * x
        J = q_t / (Pr - pb + pb / 1.8 * br)
        b.append(eq("Índice de productividad",
                    "J = q / { P<sub>r</sub> − P<sub>b</sub> + (P<sub>b</sub>/1,8)·[1 − 0,2·(P<sub>wf</sub>/P<sub>b</sub>) − 0,8·(P<sub>wf</sub>/P<sub>b</sub>)²] }",
                    f"{n(q_t,1)} / {{ {n(Pr,1)} − {n(pb,1)} + ({n(pb,1)}/1,8)×{n(br,6)} }}",
                    n(J, 6), "STB/d/psi", B4 + "ec. 2.30 (pág. 15)"))
    qb = J * (Pr - pb); qmax = qb + J * pb / 1.8
    b += [eq("Caudal en el punto de burbuja", "q<sub>b</sub> = J · (P<sub>r</sub> − P<sub>b</sub>)",
             f"{n(J,6)} × ({n(Pr,1)} − {n(pb,1)})", n(qb, 4), "STB/d", B4 + "ec. 2.27 (pág. 15)"),
          eq("Caudal máximo", "q<sub>o max</sub> = q<sub>b</sub> + J · P<sub>b</sub> / 1,8",
             f"{n(qb,4)} + {n(J,6)} × {n(pb,1)} / 1,8", n(qmax, 4), "STB/d", B4 + "ec. 2.28 (pág. 15)")]
    if qt <= qb:
        pwf = Pr - qt / J
        b.append(eq("Presión de fondo al caudal objetivo", "P<sub>wf</sub> = P<sub>r</sub> − q / J",
                    f"{n(Pr,1)} − {n(qt,1)} / {n(J,6)}", n(pwf, 4), "psi", B4 + "ec. 2.31 (pág. 15)"))
    else:
        frac = (qt - qb) / (qmax - qb); pwf = _vogel_pwf(pb, frac)
        b.append(eq("Presión de fondo al caudal objetivo",
                    "P<sub>wf</sub> = 0,125 · P<sub>b</sub> · [ −1 + √(81 − 80·(q − q<sub>b</sub>)/(q<sub>o max</sub> − q<sub>b</sub>)) ]",
                    f"0,125 × {n(pb,1)} × [ −1 + √(81 − 80×{n(frac,6)}) ]", n(pwf, 4), "psi",
                    B4 + "ec. 2.29 (pág. 15), despejada como la ec. 2.20 (pág. 14)"))

    def curva(p):
        if p >= pb:
            return J * (Pr - p)
        return qb + (qmax - qb) * (1 - 0.2 * (p / pb) - 0.8 * (p / pb) ** 2)
    return b, pwf, curva, "Vogel compuesta"


# ----------------------------------------------------------------------- PIP
def _res(pas: dict, label: str):
    return (pas.get(label) or {}).get("res")


def bloque_pip(r: dict, pwf: float):
    P = r["pozo"]; W = P["well"]; F = P["fluid"]; pu = r["pump"]; pas = r["pasos"]
    sgo = 141.5 / (131.5 + F["oil_api"]); wc = F["water_cut"]
    Dp = pu["pump_setting_depth"]; perf = W["perforations_bottom"]
    b = [eq("Gravedad específica del petróleo", "γ<sub>o</sub> = 141,5 / (131,5 + °API)",
            f"141,5 / (131,5 + {n(F['oil_api'],1)})", n(sgo, 6), "—", "")]
    if r["gas"]:
        s = r["summary"]; pip = s["p_intake"]; sg = sgo * (1 - wc) + F["water_sg"] * wc
        L = perf - Dp; R = P["reservoir"]; gor = F["gor"]; gg = F["gas_sg"]; gw = F["water_sg"]
        b.append(eq("Gravedad específica del líquido", "SG = γ<sub>o</sub>·(1 − WC) + γ<sub>w</sub>·WC",
                    f"{n(sgo,6)}×(1 − {n(wc,3)}) + {n(gw,3)}×{n(wc,3)}", n(sg, 6), "—"))
        # --- densidad de la mezcla en el fondo: volumen, masa, masa/volumen -----
        f0 = tabla_pvt_fondo(r, pwf)
        Vt = f0["v_total"]; m_o = (1 - wc) * 62.4 * sgo * 5.615; m_w = wc * 62.4 * gw * 5.615
        m_g = (1 - wc) * gor * 0.0764 * gg; m = m_o + m_w + m_g
        rho = m / (Vt * 5.615); sgm = rho / 62.4; gh = 0.433 * sgm
        from bes.core.pvt import gas_z_factor
        Tr = R["reservoir_temp"]; z0 = gas_z_factor(max(pwf, 14.7), Tr, gg)
        Fst = f0["rs"] * (gg / sgo) ** 0.5 + 1.25 * Tr
        b += ['<div class="sub">Propiedades PVT en el fondo (P<sub>wf</sub>, T de reservorio)</div>',
              eq("Gas disuelto (Standing)",
                 "R<sub>s</sub> = γ<sub>g</sub>·[(P/18,2 + 1,4)·10<sup>0,0125·°API − 0,00091·T</sup>]<sup>1,2048</sup>",
                 f"{n(gg,3)}×[({n(pwf,2)}/18,2 + 1,4)×10<sup>0,0125×{n(F['oil_api'],1)} − 0,00091×{n(Tr,1)}</sup>]<sup>1,2048</sup>",
                 n(f0["rs"], 4), "scf/STB", "Ahmed (2010), ec. 2-69 (pág. 79)"),
              eq("Parámetro de Standing", "F = R<sub>s</sub>·(γ<sub>g</sub>/γ<sub>o</sub>)<sup>0,5</sup> + 1,25·T",
                 f"{n(f0['rs'],4)}×({n(gg,3)}/{n(sgo,6)})<sup>0,5</sup> + 1,25×{n(Tr,1)}", n(Fst, 4), "—",
                 "Ahmed (2010), correlación de Standing para Bo (pág. 94)"),
              eq("Factor volumétrico del petróleo (Standing)", "B<sub>o</sub> = 0,9759 + 0,00012·F<sup>1,2</sup>",
                 f"0,9759 + 0,00012×{n(Fst,4)}<sup>1,2</sup>", n(f0["bo"], 6), "bbl/STB",
                 "Ahmed (2010), correlación de Standing para Bo (pág. 94)"),
              eq("Factor de compresibilidad del gas", "z = Papay (P<sub>pr</sub>, T<sub>pr</sub>)",
                 f"a {n(pwf,2)} psi y {n(Tr,1)} °F, γ<sub>g</sub> = {n(gg,3)}", n(z0, 5), "—",
                 "Papay, en Takács (2018), ec. 4.26 (pág. 169)"),
              eq("Factor volumétrico del gas", "B<sub>g</sub> = 0,005035 · z · (T + 460) / P",
                 f"0,005035 × {n(z0,5)} × ({n(Tr,1)} + 460) / {n(pwf,2)}", n(f0["bg"], 8), "bbl/scf",
                 "Ahmed (2010), ec. 2-54 (pág. 66)"),
              eq("Factor volumétrico del agua (Ahmed ec. 2-125)", "B<sub>w</sub> = A<sub>1</sub> + A<sub>2</sub>·P + A<sub>3</sub>·P²",
                 f"a {n(pwf,2)} psi y {n(Tr,1)} °F", n(f0["bw"], 6), "bbl/STB", "Ahmed (2010), ec. 2-125 (pág. 124)"),
              '<div class="sub">Gravedad específica de la mezcla en el fondo</div>',
              eq("Volumen de la mezcla en el fondo, por STB de líquido",
                 "V = (1 − WC)·B<sub>o</sub> + WC·B<sub>w</sub> + (1 − WC)·(GOR − R<sub>s</sub>)·B<sub>g</sub>",
                 f"a {n(pwf,2)} psi y {n(R['reservoir_temp'],1)} °F: ({n(1-wc,3)})×{n(f0['bo'],6)} + {n(wc,3)}×{n(f0['bw'],6)}"
                 f" + ({n(1-wc,3)})×({n(gor,1)} − {n(f0['rs'],4)})×{n(f0['bg'],8)}",
                 n(Vt, 6), "bbl/STB", B2 + "Sección 4.53102, paso 5A (pág. 74)"),
              eq("Masa del petróleo", "m<sub>o</sub> = (1 − WC) · 62,4 · γ<sub>o</sub> · 5,615",
                 f"({n(1-wc,3)}) × 62,4 × {n(sgo,6)} × 5,615", n(m_o, 4), "lb/STB", B2 + "Sección 4.53102, paso 5B (pág. 74)"),
              eq("Masa del agua", "m<sub>w</sub> = WC · 62,4 · γ<sub>w</sub> · 5,615",
                 f"{n(wc,3)} × 62,4 × {n(gw,3)} × 5,615", n(m_w, 4), "lb/STB", B2 + "Sección 4.53102, paso 5B (pág. 74)"),
              eq("Masa del gas (disuelto + libre)", "m<sub>g</sub> = (1 − WC) · GOR · 0,0764 · γ<sub>g</sub>",
                 f"({n(1-wc,3)}) × {n(gor,1)} × 0,0764 × {n(gg,3)}", n(m_g, 4), "lb/STB",
                 B2 + "Sección 4.53102, paso 5B (pág. 74)"),
              eq("Masa de la mezcla", "m = m<sub>o</sub> + m<sub>w</sub> + m<sub>g</sub>",
                 f"{n(m_o,4)} + {n(m_w,4)} + {n(m_g,4)}", n(m, 4), "lb/STB", ""),
              eq("Densidad de la mezcla", "ρ<sub>mezcla</sub> = m / (V · 5,615)",
                 f"{n(m,4)} / ({n(Vt,6)} × 5,615)", n(rho, 4), "lb/ft³", B2 + "Sección 4.53102, paso 5C (pág. 74)"),
              eq("Gravedad específica de la mezcla", "SG<sub>mezcla</sub> = ρ<sub>mezcla</sub> / 62,4",
                 f"{n(rho,4)} / 62,4", n(sgm, 6), "—", ""),
              eq("Gradiente de la mezcla en el fondo", "grad = 0,433 · SG<sub>mezcla</sub>",
                 f"0,433 × {n(sgm,6)}", n(gh, 6), "psi/ft", B2 + "Ejemplo #1C (pág. 68)"),
              eq("Largo de la columna anular", "L = D<sub>punzados</sub> − D<sub>bomba</sub>",
                 f"{n(perf,1)} − {n(Dp,1)}", n(L, 1), "ft", ""),
              eq("PIP — presión en la admisión", "PIP = P<sub>wf</sub> − grad · L",
                 f"{n(pwf,3)} − {n(gh,6)} × {n(L,1)}", n(pip, 3), "psi", B2 + "Ejemplo #1C (pág. 68)")]
        b += [
              eq("Temperatura en la admisión",
                 "T(L) = T<sub>boca</sub> + (L/D<sub>total</sub>)·(T<sub>res</sub> − T<sub>boca</sub>)",
                 f"{n(W['wellhead_temp'],1)} + ({n(Dp,1)}/{n(W['total_depth'],1)})×"
                 f"({n(R['reservoir_temp'],1)} − {n(W['wellhead_temp'],1)})",
                 n(s["pump_intake_temp_f"], 3), "°F")]
        # --- descarga: recorrido por el tubing -----------------------------------
        gor_t, _, tt = recorrido_tubing(r)
        from bes.core.pvt import standing_rs
        rs_pip = min(standing_rs(pip, s["pump_intake_temp_f"], F["oil_api"], gg, F["bubble_point_pressure"])
                     if F["bubble_point_pressure"] > 0 else gor, gor)
        gip = s["gip"]
        b += ['<div class="sub">Presión de descarga: recorrido por el tubing</div>',
              eq("GOR que sube por el tubing", "GOR<sub>tubing</sub> = R<sub>s</sub>(PIP) + GIP · (GOR − R<sub>s</sub>(PIP))",
                 f"{n(rs_pip,4)} + {n(gip,4)} × ({n(gor,1)} − {n(rs_pip,4)})", n(gor_t, 4), "scf/STB"),
              eq("Presión de descarga", "P<sub>desc</sub> = P<sub>wh</sub> + Σ (dP/dz)<sub>i</sub>·Δz",
                 f"{n(P['surface']['wellhead_pressure_required'],1)} + {n(sum(x['dp'] for x in tt),3)} "
                 f"&nbsp;({len(tt)} tramos de {n(Dp/len(tt),2)} ft, mismas ecuaciones que en el anular)",
                 n(s["p_discharge"], 3), "psi"),
              tabla([(str(i), n(x["z0"], 0) + " → " + n(x["z1"], 0), n(x["p0"], 2), n(x["rho"], 4),
                      n(x["grad"], 6), n(x["p1"], 2), "P&amp;C" if x["metodo"] == "poettmann_carpenter" else "monofásico")
                     for i, x in enumerate(tt, 1) if i % 5 == 0 or i == 1],
                    ["#", "profundidad [ft]", "P<sub>i</sub> [psi]", "ρ<sub>m</sub> [lb/ft³]", "dP/dz [psi/ft]",
                     "P<sub>i+1</sub> [psi]", "método"], "lad")]
        return b, pip, sg
    sg = _res(pas, "Gravedad específica del líquido producido")
    grad = _res(pas, "Gradiente promedio del recorrido anular")
    dpa = _res(pas, "Caída de presión en el anular, de las perforaciones a la bomba")
    pip = _res(pas, "PIP — presión en la admisión de la bomba")
    if pip is None:
        pip = pu.get("intake_pressure")
    if sg is None:
        sg = sgo * (1 - wc) + F["water_sg"] * wc
    b.append(eq("Gravedad específica del líquido", "SG = γ<sub>o</sub>·(1 − WC) + γ<sub>w</sub>·WC",
                f"{n(sgo,6)}×(1 − {n(wc,3)}) + {n(F['water_sg'],3)}×{n(wc,3)}", n(sg, 6), "—"))
    sgf = _res(pas, "Gravedad específica de la mezcla en el fondo")
    if sgf is not None:
        b.append(eq("Gravedad específica de la mezcla en el fondo", "SG<sub>fondo</sub> = m / (V · 5,615 · 62,4)",
                    None, n(sgf, 6), "—", B2 + "Sección 4.53102, paso 5 (pág. 74)"))
    if grad is not None and dpa is not None:
        b.append(eq("Gradiente de la mezcla", "grad = 0,433 · SG<sub>fondo</sub>",
                    f"0,433 × {n(sgf,6)}" if sgf is not None else None, n(grad, 6), "psi/ft",
                    B2 + "Ejemplo #1C (pág. 68)"))
        b.append(eq("Caída en el anular", "Δp<sub>anular</sub> = grad · (D<sub>punzados</sub> − D<sub>bomba</sub>)",
                    f"{n(grad,6)} × ({n(perf,1)} − {n(Dp,1)}) = {n(grad,6)} × {n(perf-Dp,1)}",
                    n(dpa, 3), "psi", B2 + "Ejemplo #1C (pág. 68)"))
        b.append(eq("PIP — presión en la admisión", "PIP = P<sub>wf</sub> − Δp<sub>anular</sub>",
                    f"{n(pwf,3)} − {n(dpa,3)}", n(pip, 3), "psi", B2 + "Sección 4.5324 (pág. 63)"))
    else:
        b.append(eq("PIP — presión en la admisión", "PIP = P<sub>wf</sub> − Δp<sub>anular</sub>",
                    None, n(pip, 3), "psi"))
    return b, pip, sg


def densidades_tramo(r: dict, x: dict, pipe_id: float, gor: float, dz: float) -> list[str]:
    """Todas las densidades y velocidades de un tramo, con las mismas funciones que P&C."""
    from bes.core.multiphase import _make_fluid
    from bes.core.pvt import fluid_properties_at_conditions, gas_z_factor
    F = r["pozo"]["fluid"]; q = r["pozo"]["objectives"]["target_flow_rate"]; wc = F["water_cut"]
    p, t = max(x["pm"], 14.7), x["tm"]; gg = F["gas_sg"]; gw = F["water_sg"]
    sgo = 141.5 / (131.5 + F["oil_api"])
    pr = fluid_properties_at_conditions(_make_fluid(F["oil_api"], wc, gor, gg, gw, p), p, t)
    z = gas_z_factor(p, t, gg); rs, bo, bw, bg = pr["rs"], pr["bo"], pr["bw"], pr["bg"]
    ro = (62.4 * sgo + 0.0136 * rs * gg) / bo; rw = 62.4 * gw / bw; rl = ro * (1 - wc) + rw * wc
    rg = 2.70 * gg * p / (z * (t + 460.0))
    A = math.pi / 4 * (pipe_id / 12) ** 2
    ql = q * ((1 - wc) * bo + wc * bw); qg = q * (1 - wc) * max(gor - rs, 0.0) * bg
    vsl = ql * 5.615 / 86400 / A; vsg = qg * 5.615 / 86400 / A; vm = vsl + vsg; lam = vsl / vm
    rm = rl * lam + rg * (1 - lam); d = pipe_id / 12; Nr = rm * vm * d
    from bes.core.multiphase import pc_friction_factor, pc_friction_gradient
    f, _ = pc_friction_factor(Nr); w = rm * vm * A * 86400.0
    gv = rm / 144; fr = pc_friction_gradient(f, w, rm, d)
    PC = "Brown y Beggs (1977), Sección 2.3322, ec. 2.34 (pág. 106)"
    return ['<div class="sub">Desarrollo del tramo 1</div>',
        eq("Condiciones del punto medio", "P<sub>m</sub>, T<sub>m</sub>", None,
           f"{n(p,3)} psi · {n(t,2)} °F", "", ""),
        eq("PVT en el punto medio", "R<sub>s</sub>, B<sub>o</sub>, B<sub>w</sub>, z, B<sub>g</sub>", None,
           f"R<sub>s</sub> {n(rs,4)} · B<sub>o</sub> {n(bo,6)} · B<sub>w</sub> {n(bw,6)} · z {n(z,5)} · "
           f"B<sub>g</sub> {n(bg,8)}", "", "Ahmed (2010): ecs. 2-69, 2-54, 2-125; Standing para Bo (pág. 94)"),
        eq("Densidad del petróleo con su gas disuelto",
           "ρ<sub>o</sub> = (62,4·γ<sub>o</sub> + 0,0136·R<sub>s</sub>·γ<sub>g</sub>) / B<sub>o</sub>",
           f"(62,4×{n(sgo,6)} + 0,0136×{n(rs,4)}×{n(gg,3)}) / {n(bo,6)}", n(ro, 4), "lb/ft³",
           "Ahmed (2010), ec. 2-92 (pág. 97)"),
        eq("Densidad del agua", "ρ<sub>w</sub> = 62,4·γ<sub>w</sub> / B<sub>w</sub>",
           f"62,4×{n(gw,3)} / {n(bw,6)}", n(rw, 4), "lb/ft³", ""),
        eq("Densidad del líquido", "ρ<sub>l</sub> = ρ<sub>o</sub>·(1 − WC) + ρ<sub>w</sub>·WC",
           f"{n(ro,4)}×(1 − {n(wc,3)}) + {n(rw,4)}×{n(wc,3)}", n(rl, 4), "lb/ft³", ""),
        eq("Densidad del gas libre", "ρ<sub>g</sub> = 2,70·γ<sub>g</sub>·P / (z·(T + 460))",
           f"2,70×{n(gg,3)}×{n(p,3)} / ({n(z,5)}×({n(t,2)} + 460))", n(rg, 5), "lb/ft³",
           "Ahmed (2010), ec. 2-17 (pág. 41), con M<sub>a</sub> = 28,96·γ<sub>g</sub> y R = 10,73"),
        eq("Área de flujo", "A = π/4 · (d/12)²", f"π/4 × ({n(pipe_id,3)}/12)²", n(A, 6), "ft²", ""),
        eq("Caudal de líquido en el fondo", "q<sub>l</sub> = q·[(1 − WC)·B<sub>o</sub> + WC·B<sub>w</sub>]",
           f"{n(q,1)}×[({n(1-wc,3)})×{n(bo,6)} + {n(wc,3)}×{n(bw,6)}]", n(ql, 3), "bbl/d",
           "Takács (2018), ec. 4.22 (pág. 168)"),
        eq("Caudal de gas libre en el fondo", "q<sub>g</sub> = q·(1 − WC)·(GOR − R<sub>s</sub>)·B<sub>g</sub>",
           f"{n(q,1)}×({n(1-wc,3)})×({n(gor,2)} − {n(rs,4)})×{n(bg,8)}", n(qg, 3), "bbl/d",
           "Takács (2018), ec. 4.15 (pág. 166)"),
        eq("Velocidad superficial del líquido", "v<sub>sl</sub> = q<sub>l</sub>·5,615 / 86 400 / A",
           f"{n(ql,3)}×5,615 / 86 400 / {n(A,6)}", n(vsl, 5), "ft/s", "Takács (2018), ec. 4.17 (pág. 167)"),
        eq("Velocidad superficial del gas", "v<sub>sg</sub> = q<sub>g</sub>·5,615 / 86 400 / A",
           f"{n(qg,3)}×5,615 / 86 400 / {n(A,6)}", n(vsg, 5), "ft/s", "Takács (2018), ec. 4.17 (pág. 167)"),
        eq("Velocidad de la mezcla", "v<sub>m</sub> = v<sub>sl</sub> + v<sub>sg</sub>",
           f"{n(vsl,5)} + {n(vsg,5)}", n(vm, 5), "ft/s", PC),
        eq("Fracción de líquido sin deslizamiento", "λ<sub>l</sub> = v<sub>sl</sub> / v<sub>m</sub>",
           f"{n(vsl,5)} / {n(vm,5)}", n(lam, 5), "—", PC),
        eq("Densidad de la mezcla", "ρ<sub>m</sub> = ρ<sub>l</sub>·λ<sub>l</sub> + ρ<sub>g</sub>·(1 − λ<sub>l</sub>)",
           f"{n(rl,4)}×{n(lam,5)} + {n(rg,5)}×(1 − {n(lam,5)})", n(rm, 4), "lb/ft³", PC),
        eq("Numerador del número de Reynolds", "Dρv = ρ<sub>m</sub>·v<sub>m</sub>·d",
           f"{n(rm,4)}×{n(vm,5)}×{n(d,5)}", n(Nr, 3), "lb/(ft·s)", "Brown y Beggs (1977), Fig. 2.36 (pág. 106)"),
        eq("Factor de fricción", "f = Fig. 2.36 en Dρv (interpolación log-log)",
           f"Dρv = {n(Nr,3)}", n(f, 6), "—", "Brown y Beggs (1977), Sección 2.3322, Fig. 2.36 (pág. 106)"),
        eq("Caudal másico", "w = ρ<sub>m</sub>·v<sub>m</sub>·A·86 400",
           f"{n(rm,4)}×{n(vm,5)}×{n(A,6)}×86 400", n(w, 1), "lb/d", PC),
        eq("Gradiente por gravedad del tramo", "(dP/dz)<sub>grav</sub> = ρ<sub>m</sub> / 144",
           f"{n(rm,4)} / 144", n(gv, 6), "psi/ft", PC),
        eq("Gradiente por fricción del tramo", "(dP/dz)<sub>fric</sub> = f·w² / (7,413×10<sup>10</sup>·ρ<sub>m</sub>·d<sup>5</sup>·144)",
           f"{n(f,6)}×{n(w,1)}² / (7,413×10<sup>10</sup>×{n(rm,4)}×{n(d,5)}<sup>5</sup>×144)", n(fr, 7), "psi/ft", PC),
        eq("Caída del tramo", "ΔP = [(dP/dz)<sub>grav</sub> + (dP/dz)<sub>fric</sub>]·Δz",
           f"({n(gv,6)} + {n(fr,7)})×{n(dz,2)}", n((gv + fr) * dz, 4), "psi", "")]


# ----------------------------------------------------------------------- TDH
def bloque_tdh(r: dict, pip: float, sg: float):
    pas = r["pasos"]; pu = r["pump"]; P = r["pozo"]
    kf = next((x for x in pas if x.startswith("Pérdida por fricción")), None)
    Hpip = _res(pas, "Sumergencia — altura equivalente a la presión de admisión")
    Hv = _res(pas, "Elevación vertical neta")
    Hwh = _res(pas, "Altura equivalente a la presión de boca de pozo")
    Hf = pas[kf]["res"] if kf else None
    TDH = _res(pas, "TDH — Altura dinámica total") or pu.get("total_head_required")
    Dp = pu["pump_setting_depth"]; Pwh = P["surface"]["wellhead_pressure_required"]
    b = [eq("Sumergencia", "H<sub>pip</sub> = PIP · 2,31 / SG",
            f"{n(pip,3)} × 2,31 / {n(sg,6)}", n(Hpip, 3), "ft"),
         eq("① Elevación vertical neta", "H<sub>vert</sub> = D<sub>bomba</sub> − H<sub>pip</sub>",
            f"{n(Dp,1)} − {n(Hpip,3)}", n(Hv, 3), "ft", "")]
    if kf:
        b.append(eq("② Pérdida por fricción en el tubing", pas[kf]["expr"], None, n(Hf, 3), "ft", pas[kf]["ref"]))
    b += [eq("③ Altura por la presión de boca", "H<sub>wh</sub> = P<sub>wh</sub> · 2,31 / SG",
             f"{n(Pwh,1)} × 2,31 / {n(sg,6)}", n(Hwh, 3), "ft", ""),
          eq("TDH — altura dinámica total", "TDH = H<sub>vert</sub> + H<sub>fric</sub> + H<sub>wh</sub>",
             f"{n(Hv,3)} + {n(Hf,3)} + {n(Hwh,3)}", n(TDH, 3), "ft")]
    return b, TDH


# ----------------------------------------------------------------------- gas
def html_tabla_pvt(filas: list[dict]) -> str:
    h = ('<table class="t pvt"><thead><tr>' + "".join(f"<th>{c}</th>" for c in
         ["P [psi]", "T [°F]", "GOR [scf/STB]", "Z", "R<sub>s</sub> [scf/STB]", "B<sub>g</sub> [bbl/Mscf]",
          "B<sub>o</sub> [bbl/STB]", "V<sub>g</sub> [b/d]", "V<sub>total</sub> [b/d]", "SG mezcla", "ubicación"])
         + "</tr></thead><tbody>")
    for x in filas:
        st = ' style="background:#E8EEF7"' if x["zona"] == "bomba" else ""
        h += (f"<tr{st}><td>{n(x['P'],2)}</td><td>{n(x['T'],2)}</td><td>{n(x['GOR'],2)}</td><td>{n(x['Z'],5)}</td>"
              f"<td>{n(x['Rs'],3)}</td><td>{n(x['Bg'],4)}</td><td>{n(x['Bo'],4)}</td><td>{n(x['Vg'],2)}</td>"
              f"<td>{n(x['Vt'],2)}</td><td>{n(x['SG'],4)}</td><td>{x['com']}</td></tr>")
    return h + "</tbody></table>"


def bloque_gor_bomba(r: dict, f: float, Rs: float, Bo: float, Bw: float, Bg: float) -> list[str]:
    """GOR con que trabaja la bomba después del separador (el que usa la escalera)."""
    from bes.core.pvt import standing_rs
    s = r["summary"]; fe = r["feas"]; F = r["pozo"]["fluid"]; q = r["pozo"]["objectives"]["target_flow_rate"]
    wc = F["water_cut"]; gor = F["gor"]; gip = s["gip"]; fp = fe["f_pump"]
    fa = fe["f_intake"]; eta = fe.get("separator_efficiency")
    ra = fa / (1 - fa); rb = fp / (1 - fp) if fp < 1 else float("inf")
    Tb = s["pump_intake_temp_f"]; pip = s["p_intake"]
    from bes.core.pvt import pb_para_pvt
    pb = pb_para_pvt(F["bubble_point_pressure"], gor, Tb, F["oil_api"], F["gas_sg"])
    rs_p = min(standing_rs(pip, Tb, F["oil_api"], F["gas_sg"], pb) if pb > 0 else gor, gor)
    libre_b = gip * (gor - rs_p); gor_b = rs_p + libre_b
    Vb = (1 - wc) * Bo + wc * Bw + (1 - wc) * max(gor_b - Rs, 0.0) * Bg
    return ['<div class="sub">GOR en la succión de la bomba</div>',
        eq("Relación gas/líquido en la admisión (a T de admisión)", "r<sub>adm</sub> = f<sub>adm</sub> / (1 − f<sub>adm</sub>)",
           f"{n(fa,6)} / {n(1-fa,6)}", n(ra, 5), "—", "Brown Vol. 2b, Sección 4.523 (pág. 59)"),
    ] + ([eq("Relación que queda después del separador", "r<sub>bomba</sub> = r<sub>adm</sub> · (1 − η)",
             f"{n(ra,5)} × (1 − {n(eta,3)})", n(ra * (1 - eta), 5), "—", "Takács (2018), ec. 5.36 (pág. 274)")]
         if eta else []) + [
        eq("Relación gas/líquido que entra a la bomba", "r<sub>bomba</sub> = f<sub>bomba</sub> / (1 − f<sub>bomba</sub>)",
           f"{n(fp,6)} / {n(1-fp,6)}", n(rb, 5), "—", ""),
        eq("Fracción del gas libre que entra a la bomba", "GIP = r<sub>bomba</sub> / r<sub>adm</sub>",
           f"{n(rb,5)} / {n(ra,5)}", n(gip, 4), "—", "Takács (2018), ec. 5.36 (pág. 274): (1 − η<sub>sep</sub>)"),
        eq("Gas disuelto a la presión de admisión", "R<sub>s</sub>(PIP)",
           f"a {n(pip,2)} psi y {n(Tb,3)} °F", n(rs_p, 4), "scf/STB", "Ahmed (2010), ec. 2-69 (pág. 79)"),
        eq("Gas libre que entra a la bomba", "GIP · (GOR − R<sub>s</sub>)",
           f"{n(gip,4)} × ({n(gor,1)} − {n(rs_p,4)})", n(libre_b, 4), "scf/STB", ""),
        eq("GOR en la bomba", "GOR<sub>bomba</sub> = R<sub>s</sub> + GIP · (GOR − R<sub>s</sub>)",
           f"{n(rs_p,4)} + {n(libre_b,4)}", n(gor_b, 4), "scf/STB"),
        eq("Gas libre en la succión, después del separador", "f<sub>bomba</sub> = r<sub>bomba</sub> / (1 + r<sub>bomba</sub>)",
           f"{n(rb,5)} / (1 + {n(rb,5)})", n(fp * 100, 2) + " %", "", ""),
        eq("Caudal de mezcla que entra a la bomba",
           "q<sub>bomba</sub> = q · [(1 − WC)·B<sub>o</sub> + WC·B<sub>w</sub> + (1 − WC)·(GOR<sub>bomba</sub> − R<sub>s</sub>)·B<sub>g</sub>]",
           f"{n(q,1)} × [({n(1-wc,3)})×{n(Bo,6)} + {n(wc,3)}×{n(Bw,6)} + ({n(1-wc,3)})×({n(gor_b,4)} − {n(Rs,4)})×{n(Bg,8)}]",
           n(s["q_mix_intake_bpd"], 2), "b/d", "Takács (2018), ec. 4.23 (pág. 168)")]


def bloque_gas(r: dict) -> list[str]:
    s = r["summary"]; fe = r["feas"]; inc = r["inc"]; F = r["pozo"]["fluid"]; O = r["pozo"]["objectives"]
    i0 = inc[0]; Rs = i0["rs_lo"]; Bo = i0["bo_lo"]; Bg = i0["bg_lo"]; Bw = i0["bw"]
    wc = F["water_cut"]
    Vo = (1 - wc) * Bo; Vw = wc * Bw; Vg = (1 - wc) * (F["gor"] - Rs) * Bg; Vt = Vo + Vw + Vg; f = Vg / Vt
    b = [eq("Gas disuelto en la admisión",
            "R<sub>s</sub> = γ<sub>g</sub>·[(P/18,2 + 1,4)·10<sup>0,0125·°API − 0,00091·T</sup>]<sup>1,2048</sup>",
            f"a {n(s['p_intake'],2)} psi y {n(s['pump_intake_temp_f'],3)} °F", n(Rs, 4), "scf/STB"),
         eq("Gas libre", "GOR − R<sub>s</sub>", f"{n(F['gor'],1)} − {n(Rs,4)}", n(F["gor"] - Rs, 4), "scf/STB", ""),
         eq("Factor de volumen del gas", "B<sub>g</sub> = 0,005035 · z · (T + 460) / P", None, n(Bg, 8), "bbl/scf"),
         eq("Volumen de petróleo", "V<sub>o</sub> = (1 − WC) · B<sub>o</sub>",
            f"({n(1-wc,3)}) × {n(Bo,6)}", n(Vo, 6), "bbl/STB", ""),
         eq("Volumen de agua", "V<sub>w</sub> = WC · B<sub>w</sub>", f"{n(wc,3)} × {n(Bw,6)}", n(Vw, 6), "bbl/STB", ""),
         eq("Volumen de gas libre", "V<sub>g</sub> = (1 − WC)·(GOR − R<sub>s</sub>)·B<sub>g</sub>",
            f"({n(1-wc,3)}) × {n(F['gor']-Rs,4)} × {n(Bg,8)}", n(Vg, 6), "bbl/STB", ""),
         eq("Fracción de gas libre", "f = V<sub>g</sub> / (V<sub>o</sub> + V<sub>w</sub> + V<sub>g</sub>)",
            f"{n(Vg,6)} / {n(Vt,6)}", n(100 * f, 2) + " %", "—"),
         eq("Relación gas/líquido", "r = f / (1 − f)", f"{n(f,6)} / {n(1-f,6)}", n(f / (1 - f), 5), "—", ""),
         eq("Caudal de mezcla en la admisión, antes del separador", "q<sub>adm</sub> = q<sub>líquido</sub> · V<sub>total</sub>",
            f"{n(O['target_flow_rate'],1)} × {n(Vt,6)}", n(O["target_flow_rate"] * Vt, 2), "b/d", ""),
         ] + bloque_gor_bomba(r, f, Rs, Bo, Bw, Bg) + [
         '<div class="sub">Escalera de incrementos</div>',
         eq("Salto de presión", "ΔP = P<sub>desc</sub> − P<sub>adm</sub>",
            f"{n(s['p_discharge'],2)} − {n(s['p_intake'],2)}", n(s["delta_p"], 2), "psi"),
         eq("Cantidad de escalones", "n = ⌈ΔP / escalón⌉",
            f"⌈{n(s['delta_p'],2)} / {n(s['increment_psi'],0)}⌉", str(s["n_increments"]), "tramos")]
    b.append(tabla([(str(i), n(x["p_lo"], 1) + " → " + n(x["p_hi"], 1), n(x["delta_p"], 1),
                     n(x["q_lo_bpd"], 1) + " → " + n(x["q_hi_bpd"], 1), n(x["q_avg_bpd"], 1), n(x["rs"], 1),
                     n(x["gradient"], 5), n(x["head_per_stage"], 3), n(x["psi_per_stage"], 4),
                     n(x["stages_exact"], 2), n(x["hp"], 3)) for i, x in enumerate(inc, 1)],
                   ["#", "p<sub>lo</sub> → p<sub>hi</sub> [psi]", "Δp", "q<sub>lo</sub> → q<sub>hi</sub> [b/d]", "q̄ [b/d]",
                    "R<sub>s</sub>", "grad<br>[psi/ft]", "ft/etapa", "psi/etapa", "etapas", "hp"], "lad"))
    b += [eq("La bisagra del método — presión que aporta cada etapa",
             "Δp<sub>etapa</sub> = H<sub>etapa</sub> · gradiente",
             f"{n(i0['head_per_stage'],3)} ft/etapa × {n(i0['gradient'],6)} psi/ft &nbsp;(tramo 1)",
             n(i0["psi_per_stage"], 5), "psi/etapa"),
          eq("Etapas del tramo", "N<sub>tramo</sub> = Δp<sub>tramo</sub> / Δp<sub>etapa</sub>",
             f"{n(i0['delta_p'],1)} / {n(i0['psi_per_stage'],5)} &nbsp;(tramo 1)", n(i0["stages_exact"], 3), "etapas"),
          eq("Etapas totales", "N = ⌈Σ N<sub>tramo</sub>⌉", f"⌈{n(s['total_stages_exact'],2)}⌉",
             str(s["total_stages"]), "etapas"),
          eq("Potencia total al eje", "HP = Σ (N<sub>tramo</sub> · hp<sub>etapa</sub> · SG<sub>mezcla</sub>)", None,
             n(s["total_hp"], 2), "hp"),
          eq("TDH equivalente del método", "TDH<sub>eq</sub> = Σ (Δp<sub>tramo</sub> / grad<sub>tramo</sub>)", None,
             n(r["tdh"][0], 2), "ft"),
          '<div class="sub">Veredicto de manejo de gas</div>',
          tabla([("Gas libre en la admisión", n(fe["f_intake"] * 100, 2) + " %"),
                 ("Gas que entra a la bomba", n(fe["f_pump"] * 100, 2) + " %"),
                 ("Máximo admisible de diseño", n(fe["max_gip"] * 100, 1) + " %"),
                 ("Configuración elegida", fe["strategy"])], ["concepto", "valor"], "apar")]
    return b


# ---------------------------------------------------------------- viscosidad
def bloque_visc(r: dict) -> list[str]:
    v = r["visc"]; ch = v["viscosity_chain"]; pas = r["pasos"]
    b = [eq("Paso 2 — viscosidad del crudo sin gas", "μ<sub>od</sub> = f(°API, T) — lámina Fig. 4L(2)",
            f"{n(r['pozo']['fluid']['oil_api'],1)} °API a {n(ch['temp_f'],1)} °F", n(ch["mu_dead_cp"], 2), "cp",
            "Brown Vol. 2b, Apéndice 4L, Fig. 4L(2); Sección 4.53113, paso 2 (pág. 91)"),
         eq("Paso 3 — corrección por gas disuelto", "μ<sub>ob</sub> = f(μ<sub>od</sub>, R<sub>s</sub>) — Fig. 4L(1)",
            f"R<sub>s</sub> = {n(ch['rs_scf_bbl'],1)} scf/STB", n(ch["mu_live_cp"], 2), "cp",
            "Brown Vol. 2b, Apéndice 4L, Fig. 4L(1); Sección 4.53113, paso 3 (pág. 91)"),
         eq("Paso 4a — viscosidad cinemática", "ν = μ<sub>ob</sub> / γ<sub>o</sub>",
            f"{n(ch['mu_live_cp'],4)} / {n(ch['sg_oil'],6)}", n(ch["cst"], 4), "cSt"),
         eq("Paso 4b — conversión a Saybolt", "SSU = 2,273 · ( ν + √(ν² + 158,4) )",
            f"2,273 × ( {n(ch['cst'],4)} + √({n(ch['cst']**2,2)} + 158,4) )", n(ch["ssu"], 2), "SSU",
            "Takács (2018), ec. 4.14 (pág. 159)"),
         eq("Paso 5 — corrección por corte de agua", "—", None,
            (v.get("water_cut_correction") or "no_realizada").replace("_", " ").upper(), ""),
         eq("Paso 6 — factores de Riling",
            "(C<sub>Q</sub>, C<sub>H</sub>, C<sub>HP</sub>, η) = Tablas 4.520 / 4.521 interpoladas",
            f"{n(ch['ssu'],0)} SSU sobre una bomba de {n(v.get('pump_max_efficiency_pct'),2)} % de rendimiento máximo",
            f"C<sub>Q</sub> {n(v['capacity_factor'],2)} % · C<sub>H</sub> {n(v['head_factor'],2)} % · "
            f"C<sub>HP</sub> {n(v['hp_factor'],2)} % · η {n(v['degraded_efficiency']*100,2)} %", "",
            "Brown Vol. 2b, Tablas 4.520 (bombas de 60 %) y 4.521 (de 70 %) (pág. 91)"),
         eq("Paso 7a — caudal equivalente en agua", "Q<sub>agua</sub> = Q<sub>pedido</sub> / C<sub>Q</sub>",
            f"{n(v['q_required'],1)} / {n(v['capacity_factor']/100,6)}", n(v["q_water"], 2), "STB/d"),
         eq("Paso 7b — altura equivalente en agua", "H<sub>agua</sub> = TDH<sub>pedido</sub> / C<sub>H</sub>",
            f"{n(v['h_required'],2)} / {n(v['head_factor']/100,6)}", n(v["h_water"], 2), "ft")]
    hp_a = _res(pas, "Potencia al eje de la bomba"); hp_c = _res(pas, "Potencia corregida por viscosidad")
    if hp_a is not None and hp_c is not None:
        b.append(eq("Potencia corregida", "HP<sub>crudo</sub> = HP<sub>agua</sub> · C<sub>HP</sub>",
                    f"{n(hp_a,4)} × {n(v['hp_factor']/100,6)}", n(hp_c, 3), "hp"))
    return b


# ------------------------------------------------------------------- aparejo
def bloques_aparejo(r: dict, A: dict) -> dict[str, list[str]]:
    pu = r["pump"]; P = r["pozo"]; W = P["well"]; T = A["T"]
    m = A["motor"]; mot = m["m"]; c = A["cable"]; cab = c["c"]
    el = A["elec"]; th = A["thrust"]; sel = A["sello"]; cl = A["cool"]
    sp = A["sup"]; ctl = A["ctl"]; ho = A["hous"]; sh = A["shaft"]; ser = A["serie_datos"]
    OK = lambda v: "<b>CUMPLE</b>" if v else "<b>NO CUMPLE</b>"  # noqa: E731
    S: dict[str, list[str]] = {}

    S["motor"] = [
        eq("Potencia sobre el eje", "HP<sub>eje</sub> = N · hp<sub>etapa</sub> · SG",
           f"{A['N']} × {n(A['hp_etapa'],6)} × {n(A['sg'],6)}", n(A["hp_eje"], 4), "hp"),
        eq("Potencia mínima de placa", "HP<sub>placa</sub> ≥ HP<sub>eje</sub> × 1,10",
           f"{n(A['hp_eje'],4)} × 1,10", n(m["hp_min"], 4), "hp"),
        eq("Diámetro máximo admisible", "OD<sub>motor</sub> ≤ OD<sub>bomba</sub> × 1,20",
           f"{n(pu['pump_od'],3)} × 1,20", n(m["max_od"], 4), "in"),
        eq("Temperatura mínima de placa", "T<sub>max,motor</sub> ≥ T<sub>fondo</sub> + 25 °F",
           f"{n(T,1)} + 25", n(m["t_min"], 1), "°F"),
        eq("Tensión objetivo",
           "≤ 70 hp → 800 V &nbsp;·&nbsp; 71 a 200 hp → 1200 V &nbsp;·&nbsp; &gt; 200 hp → 2000 V",
           f"HP<sub>eje</sub> = {n(A['hp_eje'],1)} hp", n(m["target_v"], 0), "V"),
        '<div class="sub">Filtros aplicados al catálogo, en orden</div>',
        tabla([
            ("1. Fabricante", "igual al de la bomba (aparejo único)", pu["pump_manufacturer"]),
            ("2. Potencia de placa", f"≥ {n(m['hp_min'],2)} hp", f"{n(mot.get('hp_rating'),0)} hp&nbsp; ✓"),
            ("3. Diámetro", f"≤ {n(m['max_od'],3)} in", f"{n(mot.get('od_inches'),2)} in&nbsp; ✓"),
            ("4. Temperatura", f"≥ {n(m['t_min'],0)} °F",
             "<b>no publicada → verificación NO REALIZADA</b>" if mot.get("max_temp_f") in ND
             else f"{n(mot.get('max_temp_f'),0)} °F ✓"),
            ("5. Luz para el cable", "OD<sub>motor</sub> + 2 × espesor del cable más fino ≤ ID del casing",
             (f"el fabricante declara casing mínimo {n(mot.get('min_casing_od_in'),1)}\" para la serie ✓"
              if mot.get("min_casing_od_in") not in ND else f"luz de {n(c['clr'],3)} in por lado ✓")),
            ("6. Desempate", "menor potencia de placa; a igualdad, tensión más cerca de la objetivo",
             f"{n(mot.get('voltage'),0)} V"),
        ], ["filtro", "criterio", "este pozo"], "apar"),
        eq("Motor elegido", mot.get("model", pu.get("motor_model", "")), None,
           f"{n(mot.get('hp_rating'),0)} hp · {n(mot.get('voltage'),0)} V · {n(mot.get('amperage'),1)} A",
           f"serie {mot.get('series')} · OD {n(mot.get('od_inches'),2)} in · largo {n(mot.get('length_ft'),1)} ft",
           f"{pu['pump_manufacturer']} ESP Catalog"),
    ]

    b = [eq("Potencia que transmite el eje", "HP<sub>eje</sub> = hp<sub>etapa</sub> · N · SG",
            f"{n(A['hp_etapa'],6)} × {A['N']} × {n(A['sg'],6)}", n(sh.get("hp_shaft"), 4), "hp"),
         eq("Límite del eje llevado a la frecuencia de diseño",
            "HP<sub>lím</sub>(f) = HP<sub>lím</sub>(f<sub>ref</sub>) · f / f<sub>ref</sub>",
            (f"{n(ser.get('shaft_hp_limit_std'),0)} × {n(P['surface']['frequency'],0)} / "
             f"{n(ser.get('reference_frequency_hz'),0)}" if ser else None),
            (n(sh.get("limit_std"), 1) if sh.get("verified") else "—"), "hp",
            ("Takács (2018), ec. 5.12 (pág. 250); límite: " + ser["fuente"]) if ser and ser.get("fuente")
            else "Wood Group ESP, hojas de engineering data"),
         '<div class="sub">Límites de eje del catálogo</div>',
         tabla([(s.get("series"), s.get("manufacturer"), n(s.get("shaft_diameter_in"), 4),
                 n(s.get("shaft_hp_limit_std"), 0), n(s.get("shaft_hp_limit_high_strength"), 0),
                 n(s.get("shaft_hp_limit_ultra_high_strength"), 0), n(s.get("reference_frequency_hz"), 0))
                for s in A["series"]],
               ["serie", "fabricante", "d<sub>eje</sub> [in]", "eje estándar [hp]",
                "alta resistencia [hp]", "ultra alta [hp]", "f de referencia [Hz]"], "apar")]
    if sh.get("verified"):
        b.append(eq("Veredicto", "HP<sub>eje</sub> contra los límites de la serie",
                    f"{n(sh['hp_shaft'],1)} hp &nbsp;vs&nbsp; estándar {n(sh['limit_std'],0)} hp &nbsp;vs&nbsp; "
                    f"alta resistencia {n(sh['limit_high_strength'],0)} hp",
                    ("EJE ESTÁNDAR" if sh["shaft_type"] == "standard" else
                     "EJE DE ALTA RESISTENCIA" if sh["shaft_type"] == "high_strength" else "NO SOPORTA"), "", ""))
    else:
        b.append(eq("Veredicto", "HP<sub>eje</sub> contra los límites de la serie",
                    f"serie {pu['pump_series']}: sin límites publicados", "VERIFICACIÓN NO REALIZADA", "", ""))
    S["eje"] = b

    S["sello"] = [
        eq("Diferencial de presión de la bomba", "ΔP = TDH · 0,433 · SG",
           f"{n(A['tdh'],2)} × 0,433 × {n(A['sg'],6)}", n(th["dp"], 2), "psi", ""),
        eq("Sección del eje", "A = π/4 · d<sub>eje</sub>²", f"π/4 × ({n(th['d'],4)})²", n(th["area"], 5), "in²", ""),
        eq("Carga axial estimada", "F<sub>axial</sub> = ΔP · A · margen",
           f"{n(th['dp'],2)} × {n(th['area'],5)} × 1,20", n(float(th["F"] or 0), 2), "lbs"),
        eq("Tipo según la desviación del pozo",
           "desviación ≤ 30° → laberíntico &nbsp;|&nbsp; &gt; 30° → bolsa elastomérica",
           f"desviación máxima: {n(th['desv'],1)}°",
           "LABERÍNTICO" if th["prefer"] == "labyrinth" else "BOLSA", ""),
        '<div class="sub">Filtros aplicados</div>',
        tabla([
            ("1. Compatibilidad", f"la serie del motor ({mot.get('series')}) debe figurar en el protector",
             f"{sel.get('compatible_motor_series')} ✓"),
            ("2. Temperatura", f"≥ {n(T,0)} °F",
             "<b>no publicada → NO REALIZADA</b>" if sel.get("max_temp_f") in ND else f"{sel.get('max_temp_f')} °F ✓"),
            ("3. Capacidad de empuje", f"≥ {n(float(th['F'] or 0),0)} lbs",
             "<b>no publicada → NO REALIZADA</b>" if sel.get("thrust_capacity_lbs") in ND
             else f"{sel.get('thrust_capacity_lbs')} lbs ✓"),
            ("4. Tipo", "se prefiere el de la regla de desviación; si ninguno aguanta, se acepta otro", sel.get("type")),
            ("5. Economía", "la menor capacidad de empuje que alcance", "—"),
        ], ["filtro", "criterio", "este pozo"], "apar"),
        eq("Sello elegido", sel.get("model", pu.get("seal_model") or ""), None,
           f"{sel.get('type')} · serie {sel.get('series')}",
           f"largo {n(float(sel.get('length_ft') or 0),1)} ft", f"{pu['pump_manufacturer']} ESP Catalog"),
    ]

    S["cable"] = [
        eq("Ampacidad requerida", "I<sub>cable</sub> ≥ I<sub>motor</sub> × 1,25",
           f"{n(mot.get('amperage'),1)} × 1,25", n(c["req"], 3), "A", ""),
        eq("Temperatura mínima de aislación", "T<sub>max,cable</sub> ≥ T<sub>fondo</sub> + 25 °F",
           f"{n(T,1)} + 25", n(T + 25, 1), "°F", ""),
        eq("Luz disponible en el anular", "luz = (ID<sub>casing</sub> − OD<sub>motor</sub>) / 2",
           f"({n(W['casing_id'],3)} − {n(mot.get('od_inches'),3)}) / 2", n(c["clr"], 4), "in", ""),
        eq("Largo del tendido", "L<sub>cable</sub> = profundidad de bomba + 100 ft",
           f"{n(pu['pump_setting_depth'],1)} + 100", n(c["L"], 1), "ft", ""),
        '<div class="sub">Filtros aplicados, en orden</div>',
        tabla([
            ("1. Ampacidad", f"≥ {n(c['req'],2)} A", f"{cab.get('max_amps')} A ✓"),
            ("2. Temperatura", f"≥ {n(T+25,0)} °F", f"{cab.get('max_temp_f')} °F ✓"),
            ("3. Que entre físicamente", f"espesor del cable plano ≤ {n(c['clr'],3)} in",
             "casing mínimo ya declarado por el fabricante del motor ✓"),
            ("4. Conductor", "se prefiere cobre (CU) antes que aluminio (AL)", f"{cab.get('conductor')} ✓"),
            ("5. Economía", "el conductor más chico que cumpla 1 a 4 (el más barato)", f"AWG {c['awg']}"),
        ], ["filtro", "criterio", "este pozo"], "apar"),
        eq("Cable elegido", f"{cab.get('manufacturer')} {cab.get('type')} AWG {c['awg']} {cab.get('conductor')}",
           None, f"{cab.get('max_amps')} A · {cab.get('max_temp_f')} °F", f"{n(c['L'],0)} ft de tendido",
           "Catálogo de cables del proyecto"),
    ]

    S["elec"] = [
        eq("Caída específica a la temperatura del pozo", "V/(A·1000 ft) = tabla del cable, interpolada en T",
           f"tabla del {cab.get('type')} AWG {c['awg']} a {n(T,1)} °F", n(c["vpa"], 6), "V/(A·1000 ft)", ""),
        eq("Caída total de tensión", "ΔV = (V/A·1000 ft) · I · L / 1000",
           f"{n(c['vpa'],6)} × {n(mot.get('amperage'),1)} × {n(c['L'],1)} / 1000", n(c["dV"], 4), "V"),
        '<div class="sub">Las verificaciones de la caída (manda la de 30 V/1000 ft)</div>',
        eq("① Caída por cada 1000 ft", "ΔV / L · 1000 ≤ 30 V/1000 ft",
           f"{n(c['dV'],4)} / {n(c['L'],1)} × 1000",
           n(el["voltage_drop_per_1000ft"], 4) + " V/1000 ft · " + OK(el["drop_per_1000ft_ok"]), ""),
        eq("② Caída relativa a la placa", "ΔV / V<sub>motor</sub> ≤ 5 %",
           f"{n(c['dV'],4)} / {n(mot.get('voltage'),0)}",
           n(el["voltage_drop_fraction"] * 100, 3) + " % · " + OK(el["drop_fraction_ok"]), ""),
        '<div class="sub">Pérdida de potencia en el cable</div>',
        eq("Resistencia por fase", "R = (V/A·1000 ft) · L / (1000 · √3)",
           f"{n(c['vpa'],6)} × {n(c['L'],1)} / (1000 × 1,7320508)", n(el["resistance_ohms"], 6), "Ω", ""),
        eq("Potencia disipada", "P = 3 · I² · R / 1000",
           f"3 × ({n(mot.get('amperage'),1)})² × {n(el['resistance_ohms'],6)} / 1000", n(el["power_loss_kw"], 5), "kW"),
    ]

    mod = float(mot.get("od_inches") or pu.get("motor_od") or 0)
    S["refri"] = [
        eq("Área del anular", "A = π/4 · (ID<sub>casing</sub>² − OD<sub>motor</sub>²)",
           f"π/4 × ({n(W['casing_id'],3)}² − {n(mod,2)}²) = π/4 × ({n(W['casing_id']**2,4)} − {n(mod**2,4)})",
           n(cl["a_in2"], 4), "in²", ""),
        eq("Área en pies cuadrados", "A = A[in²] / 144", f"{n(cl['a_in2'],4)} / 144", n(cl["a_ft2"], 6), "ft²", ""),
        eq("Velocidad del fluido", "v = q · 5,615 / 86 400 / A",
           f"{n(cl['q'],1)} × 5,615 / 86 400 / {n(cl['a_ft2'],6)}", n(cl["v"], 4), "ft/s"),
        eq("Criterio", "v ≥ 1 ft/s", f"{n(cl['v'],4)} ≥ 1,0", "VERIFICA" if cl["v"] >= 1.0 else "NO VERIFICA", "", ""),
    ]

    t = sp.get("cat") or {}
    c_ = str(t.get("connection", "")).lower()
    rng = f"{n(t.get('secondary_%s_min' % c_),0)} a {n(t.get('secondary_%s_max' % c_),0)} V" if c_ else "s/d"
    S["sup"] = [
        eq("Tensión requerida en superficie",
           "V<sub>sup</sub> = (V<sub>motor</sub> + ΔV<sub>cable</sub>) × (1 + 2,5 %)",
           f"({n(mot.get('voltage'),0)} + {n(c['dV'],4)}) × 1,025", n(sp["vs"], 4), "V"),
        eq("Potencia aparente", "kVA = V<sub>sup</sub> · I · √3 / 1000",
           f"{n(sp['vs'],4)} × {n(mot.get('amperage'),1)} × 1,7320508 / 1000", n(sp["kva"], 4), "kVA"),
        eq("Transformador elegido",
           "menor kVA del catálogo con kVA ≥ demanda y V<sub>sup</sub> dentro del rango de secundario (DELTA o WYE)",
           f"kVA ≥ {n(sp['kva'],1)} ; V<sub>sup</sub> = {n(sp['vs'],1)} V",
           f"{n(sp['trafo'],0)} kVA · parte {t.get('part_number','s/d')} · {str(t.get('connection','')).upper()}"
           + (f" · secundario {rng}" if c_ else ""),
           "", "Catálogo de transformadores (Inv_83338, Tab. 15)"),
        '<div class="sub">Tablero fijo o variador de frecuencia</div>',
        tabla([
            ("Tipo pedido", "", "VARIADOR (VSD)" if A["use_vsd"] else "TABLERO FIJO (switchboard)"),
            ("Tensión", f"≥ {n(sp['vs'],0)} V", f"{n(ctl.get('max_voltage'),0)} V ✓"),
            ("Potencia aparente", f"≥ {n(sp['kva'],0)} kVA", f"{n(ctl.get('max_kva'),0)} kVA ✓"),
            ("Corriente", f"≥ {n(mot.get('amperage'),0)} A", f"{n(ctl.get('max_amps'),0)} A ✓"),
            ("Desempate", "el más económico (menor kVA) que cubra los tres", f"<b>{ctl.get('model')}</b>"),
        ], ["límite del equipo", "hace falta", "el elegido"], "apar"),
    ]

    S["carcasa"] = [
        eq("Etapas a instalar", "N = ⌈TDH / H<sub>etapa</sub>⌉", None, str(pu["num_stages"]), "etapas", ""),
        eq("Carcasas", "combinación de tamaños de catálogo que cubra N con el menor número de cuerpos",
           f"{ho.get('n') or 1} carcasa(s) para {pu['num_stages']} etapas activas · etapas ciegas: {ho.get('dummy') or 0}",
           str(ho.get("size") or pu["num_stages"]), "etapas de capacidad", ""),
        eq("Presión sobre la carcasa", "P<sub>carcasa</sub> = ρ<sub>mezcla</sub> · g · h &nbsp;(a caudal cero)",
           None, n(float(ho.get("pmax") or 0), 1), "psi", ""),
        eq("Carga sobre el cojinete de empuje", "Carga = H<sub>o</sub> · SG · A<sub>eje</sub>",
           None, n(float(A.get("bearing") or 0), 2), "lbs"),
    ]
    return S


def bloque_separador(r: dict) -> list[str]:
    fe = r["feas"]; W = r["pozo"]["well"]; O = r["pozo"]["objectives"]
    f = fe["f_intake"]; rr = f / (1 - f); q_cons = O["target_flow_rate"] / (1 - f)
    eta = fe["separator_efficiency"]
    return [
        eq("Relación gas/líquido en la admisión", "r = f / (1 − f)", f"{n(f,6)} / {n(1-f,6)}", n(rr, 5), "—"),
        eq("Caudal con que se consulta el catálogo", "q<sub>consulta</sub> = q<sub>líquido</sub> / (1 − f)",
           f"{n(O['target_flow_rate'],1)} / (1 − {n(f,6)})", n(q_cons, 2), "b/d", ""),
        '<div class="sub">Filtros del catálogo de separadores</div>',
        tabla([
            ("1. Rango de caudal publicado", "min_flow ≤ q<sub>consulta</sub> ≤ max_flow",
             "un equipo sin rango publicado NO se puede verificar y queda fuera"),
            ("2. Que entre en el casing", f"OD del separador &lt; {n(W['casing_id'],3)} in", "—"),
            ("3. Que separe gas", "los manejadores avanzados (AGH) NO separan: acondicionan la mezcla", "—"),
            ("4. Tipo preferido", "vórtex antes que rotativo", "—"),
            ("5. Desempate", "mayor eficiencia; a igualdad, el de menor consumo", "—"),
        ], ["filtro", "criterio", "nota"], "apar"),
        '<div class="sub">La escalera de configuraciones</div>',
        tabla([
            ("sin separador", "20 %", f"{n(f*100,2)} %", "<b>FALLA ①</b>" if f > 0.20 else "cumple ①", "—",
             "<b>ELEGIDO</b>" if fe["strategy"] == "none" else "—"),
            ("un separador", "80 %", f"{n(f*100,2)} %", "cumple ①" if f <= 0.80 else "<b>FALLA ①</b>",
             f"{n(fe['f_pump']*100,2)} %" if fe["strategy"] == "simple" else "—",
             "<b>ELEGIDO</b>" if fe["strategy"] == "simple" else "—"),
            ("tándem", "95 %", f"{n(f*100,2)} %", "cumple ①" if f <= 0.95 else "<b>FALLA ①</b>",
             f"{n(fe['f_pump']*100,2)} %" if fe["strategy"] == "tandem" else "—",
             "<b>ELEGIDO</b>" if fe["strategy"] == "tandem" else "—"),
            ("manejador avanzado (AGH)", f"{n((fe.get('agh_max_gvf') or 0)*100,0)} % de GVF",
             f"{n(f*100,2)} %", "no separa: sube la tolerancia", "—",
             "<b>ELEGIDO</b>" if fe["strategy"] == "agh" else "—"),
        ], ["configuración", "① capacidad (Takács Fig. 4.25, pág. 195)", "gas en la admisión", "¿pasa ①?",
            "② gas en la bomba", "resultado"], "apar"),
    ] + ([
        eq("Gas que queda tras separar", "r' = r · (1 − η) &nbsp;→&nbsp; f' = r' / (1 + r')",
           f"r' = {n(rr,5)} × (1 − {n(eta,3)}) = {n(rr*(1-eta),5)}",
           n(fe["f_pump"] * 100, 2) + " %", "de gas en la bomba"),
        eq("Eficiencia del separador", "η", None, n(eta * 100, 1) + " %", ""),
    ] if eta else []) + [
        eq("Configuración elegida", "número de separadores × modelo", None,
           f"{fe.get('n_separators') or 0} × {fe.get('separator_model') or '—'}", "", ""),
    ]


def resumen_aparejo(r: dict) -> str:
    pu = r["pump"]; sc = pu.get("shaft_check") or {}
    return tabla([
        ("Bomba", f"{pu['pump_manufacturer']} {pu['pump_model']}, serie {pu['pump_series']}, OD {n(pu['pump_od'],2)} in"),
        ("Etapas", f"<b>{pu['num_stages']}</b>" + (f" en {pu['n_housings']} carcasas" if pu.get("n_housings") else "")),
        ("Rendimiento en el punto", n((pu.get("pump_efficiency") or 0) * 100, 2) + " %"),
        ("Potencia al eje", "<b>" + n(pu["total_pump_hp"], 2) + " hp</b>"),
        ("Verificación del eje", {"standard": "eje estándar", "high_strength": "eje de alta resistencia",
                                  "ultra_high_strength": "eje de ultra alta resistencia"}.get(
                                      sc.get("shaft_type"), "no realizada") if sc.get("verified") else "no realizada"),
        ("Sello", pu.get("seal_model") or "—"),
        ("Motor", f"{pu.get('motor_model')}<br><b>{n(pu['motor_hp'],0)} hp</b> · {n(pu['motor_voltage'],0)} V · "
                  f"{n(pu['motor_amperage'],1)} A · OD {n(pu.get('motor_od'),2)} in"),
        ("Refrigeración", f"v = {n(pu.get('fluid_velocity_ft_s'),3)} ft/s · mínimo 1 ft/s · "
                          f"<b>{'VERIFICA' if pu.get('cooling_ok') else 'NO VERIFICA'}</b>"),
        ("Cable", f"AWG {pu.get('cable_awg')} {pu.get('cable_type')} · caída {n(pu.get('cable_voltage_drop'),2)} V"),
        ("Tensión en superficie", n(pu.get("surface_voltage_required"), 2) + " V"),
        ("Transformador", n(pu.get("transformer_kva"), 0) + " kVA"
         + (f" · parte {pu['transformer_model']}" if pu.get("transformer_model") else "")),
        ("Tablero / variador", pu.get("controller_model") or "—"),
        ("Sensor de fondo", pu.get("sensor_model") or "—"),
        ("Rendimiento del sistema", n((pu.get("system_efficiency") or 0) * 100, 2) + " %"),
    ], ["componente", "selección"], "apar")


# --------------------------------------------------------------------- casos
def seccion_caso(r: dict, cm, rotulo: str, titulo: str) -> str:
    pu = r["pump"]; H = [f"<h2>{titulo}</h2>"]
    if r.get("fuente"):
        H.append(f'<div style="margin:0 0 6px 0"><b>Fuente del enunciado:</b> {r["fuente"]}</div>')
    H.append("<h3>Datos del pozo</h3>" + tabla_datos(r))
    bi, pwf, curva, etq = bloque_ipr(r); r["pwf"] = pwf
    H.append(paso(1, "CÁLCULO DE IPR", bi))
    H.append(fig(G.ipr(r, curva, pwf, etq, rotulo),
                 f"Curva IPR ({rotulo}). El cuadrado verde es el ensayo; el círculo rojo, el punto de diseño."))
    bp, pip, sg = bloque_pip(r, pwf)
    H.append(paso(2, "PRESIÓN EN LA ADMISIÓN (PIP)", bp))
    nro = 3
    if r["gas"]:
        H.append(paso(nro, "GAS LIBRE Y ESCALERA DE INCREMENTOS", bloque_gas(r)))
        H.append('<div class="sub">Evolución del fluido en el pozo</div>' + html_tabla_pvt(tabla_pvt(r))
                 + f'<div class="cap">Tabla. Evolución del fluido en el pozo ({rotulo}): fondo, admisión, '
                 f'{len(r["inc"])} incrementos de presión dentro de la bomba (sombreados) y tubing hasta superficie.</div>')
        _, pvt = G.escalera(r, rotulo)
        H.append(fig(pvt, "El gas se comprime y se redisuelve al subir la presión."))
    else:
        bt, _ = bloque_tdh(r, pip, sg)
        H.append(paso(nro, "PÉRDIDAS DE CARGA Y TDH", bt))
    nro += 1
    if r["viscoso"]:
        H.append(paso(nro, "CORRECCIÓN POR VISCOSIDAD (RILING)", bloque_visc(r)))
        H.append(fig(G.viscosidad(r, rotulo), "Cadena de Riling y factores leídos de las Tablas 4.520 / 4.521."))
        nro += 1
    sel = []
    if r["viscoso"]:
        v = r["visc"]
        sel.append(eq("Caudal con que se entra a la curva", "Q<sub>agua</sub> = Q / C<sub>Q</sub>",
                      f"{n(v['q_required'],1)} / {n(v['capacity_factor']/100,6)}", n(v["q_water"], 2), "STB/d"))
    # El TDH que entra al conteo es el que usó la app: con crudo viscoso es el
    # equivalente en agua (TDH / C_H), no el TDH del crudo.
    ent = (r["pasos"].get("Cantidad de etapas") or {}).get("in") or {}
    tdh_sel = r["tdh"][0] if r["gas"] else ent.get("TDH", pu.get("total_head_required"))
    h_sel = ent.get("H_etapa", pu.get("head_per_stage")) if not r["gas"] else pu.get("head_per_stage")
    nom_tdh = "TDH" if abs(tdh_sel - (pu.get("total_head_required") or tdh_sel)) < 0.01 or r["gas"] else "H<sub>agua</sub>"
    sel += [eq("Altura por etapa", "H<sub>etapa</sub> = curva(q)", None, n(h_sel, 4), "ft/etapa",
               "Catálogo del fabricante"),
            eq("Cantidad de etapas", f"N = ⌈{nom_tdh} / H<sub>etapa</sub>⌉",
               f"⌈{n(tdh_sel,3)} / {n(h_sel,4)}⌉ = ⌈{n(tdh_sel/h_sel,3)}⌉", str(pu["num_stages"]), "etapas"),
            eq("Potencia al eje", "HP = N · hp<sub>etapa</sub> · SG", None, n(pu["total_pump_hp"], 2), "hp")]
    H.append(paso(nro, "SELECCIÓN DE LA BOMBA SOBRE LA CURVA", sel)); nro += 1
    H.append(fig(G.bomba(r, cm, rotulo), f"Curva de la {pu['pump_manufacturer']} {pu['pump_model']}. La banda azul "
                                         f"es el rango recomendado; la línea roja, el punto de operación."))
    A = intermedios(r, cm); S = bloques_aparejo(r, A)
    if r["gas"]:
        H.append(paso(nro, "SELECCIÓN DEL SEPARADOR DE GAS", bloque_separador(r))); nro += 1
    for tit, key in (("SELECCIÓN DEL MOTOR", "motor"), ("VERIFICACIÓN DEL EJE", "eje"),
                     ("SELLO / PROTECTOR Y EMPUJE AXIAL", "sello"), ("SELECCIÓN DEL CABLE DE POTENCIA", "cable"),
                     ("VERIFICACIÓN ELÉCTRICA DEL CABLE", "elec"), ("REFRIGERACIÓN DEL MOTOR", "refri"),
                     ("TENSIÓN DE SUPERFICIE, TRANSFORMADOR Y TABLERO", "sup"), ("CARCASAS Y COJINETES", "carcasa")):
        H.append(paso(nro, tit, S[key])); nro += 1
    H.append('<div class="sub">Resumen del aparejo</div>' + resumen_aparejo(r))
    tdh_txt = n(r["tdh"][0], 1) + " ft (por incrementos)" if r["gas"] else n(pu.get("total_head_required"), 1) + " ft"
    H.append(f'<div class="res"><div class="tt">RESULTADO — {rotulo.upper()}</div>'
             f'<b>{pu["pump_manufacturer"]} {pu["pump_model"]}</b> · <b>{pu["num_stages"]} etapas</b> · '
             f'TDH {tdh_txt} · <b>{n(pu["total_pump_hp"],1)} hp</b> al eje · '
             f'motor de {n(pu["motor_hp"],0)} hp / {n(pu["motor_voltage"],0)} V · '
             f'cable AWG {pu.get("cable_awg")} · transformador de {n(pu.get("transformer_kva"),0)} kVA</div>')
    return "".join(H)


def documento(casos: list[tuple[str, str, dict]], cm, subtitulo: str = "", pie: str = "") -> str:
    """``casos`` = lista de (rótulo corto, título de sección, fila)."""
    H = [f"<html><head><meta charset='utf-8'><title>BES Designer · memoria de cálculo</title>"
         f"<style>{CSS}</style></head><body>",
         '<div class="noprint"><button onclick="window.print()">Imprimir / guardar como PDF</button></div>',
         '<div class="port"><h1>BES Designer</h1>'
         '<div class="sub" style="border:none">Memoria de cálculo paso a paso</div>'
         f'<div class="sub" style="border:none;font-size:10pt">{subtitulo}</div>'
         '<div class="meta">'
         f'{pie}<br><br>'
         'Metodología: Brown, K. E. (1980), <i>The Technology of Artificial Lift Methods</i>, Vol. 2b, y Vol. 4<br>'
         'Complementada con Takács (2018), Beggs (2003) y Ahmed (2010)<br><br>'
         'Proyecto Integrador Profesional · Pablo Tejerina<br>'
         'Facultad de Ingeniería · Universidad Nacional del Comahue</div></div>',
         "<h2>Cómo se lee este documento</h2>",
         '<div class="eq"><div class="eq-n">así se ve un paso</div>'
         '<div class="eq-f">J = q<sub>ensayo</sub> / (P<sub>r</sub> − P<sub>wf,ensayo</sub>)</div>'
         '<div class="eq-s">= 2 500,0 / (1 250,0 − 1 000,0) = 2 500,0 / 250,0</div>'
         '<div class="eq-r">= <b>10,000000</b> <span class="u">STB/d/psi</span></div>'
         '<div class="eq-ref">Brown Vol. 4, ec. 2.31 (pág. 15)</div></div>',
         "<h3>El procedimiento completo</h3>", f'<div class="flow">{DIAGRAMA}</div>']
    for rotulo, titulo, r in casos:
        H.append(seccion_caso(r, cm, rotulo, titulo))
    if len(casos) > 1:
        H.append("<h2>Los casos, lado a lado</h2>")
        filas = []
        for rotulo, titulo, r in casos:
            pu = r["pump"]; P = r["pozo"]
            tdh = r["tdh"][0] if r["gas"] else pu.get("total_head_required")
            filas.append((titulo.split(") ")[-1], n(P["fluid"]["oil_api"], 0) + " °API", n(P["fluid"]["water_cut"] * 100, 0) + " %",
                          n(P["fluid"]["gor"], 0), n(P["objectives"]["target_flow_rate"], 0),
                          n(P["well"]["total_depth"], 0), f'{pu["pump_manufacturer"]}<br>{pu["pump_model"]}',
                          str(pu["num_stages"]), n(tdh, 0), n(pu["total_pump_hp"], 1), n(pu["motor_hp"], 0)))
        H.append(tabla(filas, ["caso", "°API", "corte de agua", "GOR<br>[scf/STB]", "q objetivo<br>[STB/d]",
                               "profundidad<br>[ft]", "bomba", "etapas", "TDH<br>[ft]", "hp al eje", "motor<br>[hp]"],
                       "apar"))
    H.append("<h3>Las reglas que decidieron cada rama</h3>")
    H.append(tabla(REGLAS, ["si se cumple esto…", "…la herramienta hace esto", "fuente"], "apar"))
    return "".join(H) + "</body></html>"
