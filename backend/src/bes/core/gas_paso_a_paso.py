# -*- coding: utf-8 -*-
"""Diseño de un pozo con gas, paso a paso (método nuevo, en construcción).

Sigue el orden de la tesis Inv_83338 (UNCo), pero con las ecuaciones citadas
del proyecto. Cada paso es una función chica que devuelve su resultado y la
lista de cuentas hechas (:class:`Paso`), para que el usuario vea exactamente
qué se calculó, con qué números y de dónde sale la fórmula.

Los pasos se cargan de a uno, a medida que se aprueban:

    1. IPR → Pwf al caudal objetivo ................................. APROBADO
    2a. PVT a una presión y temperatura ............................. APROBADO
    2b-c. Volúmenes, masa y SG de la mezcla ......................... APROBADO
    3. PIP ........................................................... APROBADO
    4. GOR en la succión (separador) ................................. APROBADO
    5. Presión de descarga ........................................... APROBADO
    6. Selección de la bomba ......................................... APROBADO
    7. Incrementos de presión → etapas y potencia .................... APROBADO
    8. Eje, presión de carcasa y arreglo de carcasas ................. APROBADO
    9. Protector (sección sellante) .................................. APROBADO
   10. Motor ......................................................... APROBADO
   11. Cable de potencia y extensión del motor ....................... APROBADO
   12. Tablero y transformador ....................................... APROBADO

Mientras tanto el método anterior (``bes.core.gas_handling``) sigue en uso.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from bes.core.multiphase import pc_friction_factor, pc_friction_gradient
from bes.core.pvt import _pseudo_critical_standing, gas_bg, gas_z_factor, standing_bo

B4 = "Brown Vol. 4, "
B2 = "Brown Vol. 2b, "
TK = "Takács (2018), "
AH = "Ahmed (2010), "
P_ATM = 14.7   # psi — las presiones del usuario son manométricas (psig)
#: Eficiencia del separador de gas. Supuesto del proyecto, dentro de las curvas
#: de 70 a 90 % de Takács (2018), Fig. 4.19 (pág. 187). Los fabricantes no la publican.
ETA_SEPARADOR = 0.75


@dataclass(frozen=True)
class Paso:
    """Una cuenta: nombre, fórmula, sustitución, resultado, unidad y cita."""
    nombre: str
    formula: str
    sustitucion: str
    valor: float | None
    unidad: str
    cita: str


# --------------------------------------------------------------------------
# Paso 1 — IPR de Vogel → Pwf al caudal objetivo
# --------------------------------------------------------------------------
def paso1_ipr_vogel(pr: float, pb: float, pwf_ensayo: float, q_ensayo: float,
                    q_objetivo: float) -> tuple[float, list[Paso]]:
    """Pwf al caudal objetivo con la IPR de Vogel (Brown Vol. 4).

    Reservorio saturado (Pb >= Pr): Vogel, ecs. 2.19 y 2.20. Subsaturado
    (Pb < Pr): IPR compuesta, ecs. 2.27 a 2.31.

    Args:
        pr: Presión estática [psi].
        pb: Presión de burbuja [psi].
        pwf_ensayo: Pwf medida en el ensayo [psi].
        q_ensayo: Caudal medido en el ensayo [BPD].
        q_objetivo: Caudal de diseño [BPD].

    Returns:
        ``(pwf, pasos)``.
    """
    if not 0 <= pwf_ensayo < pr or q_ensayo <= 0:
        raise ValueError("Ensayo inválido: hace falta 0 <= Pwf_ensayo < Pr y q_ensayo > 0.")
    if pb < pr:
        return _ipr_compuesta(pr, pb, pwf_ensayo, q_ensayo, q_objetivo)
    if not 0 <= pwf_ensayo < pr or q_ensayo <= 0:
        raise ValueError("Ensayo inválido: hace falta 0 <= Pwf_ensayo < Pr y q_ensayo > 0.")
    x = pwf_ensayo / pr
    den = 1 - 0.2 * x - 0.8 * x ** 2
    q_max = q_ensayo / den
    if q_objetivo >= q_max:
        raise ValueError(f"El caudal objetivo ({q_objetivo:.1f} BPD) supera q_o max ({q_max:.1f} BPD).")
    frac = q_objetivo / q_max
    pwf = 0.125 * pr * (-1 + math.sqrt(81 - 80 * frac))
    pasos = [
        Paso("Cociente Pwf/Pr del ensayo", "Pwf / Pr",
             f"{pwf_ensayo} / {pr}", x, "—", B4 + "Ejemplo #5 (pág. 14)"),
        Paso("Caudal máximo", "q_o max = q_o / [1 − 0,2·(Pwf/Pr) − 0,8·(Pwf/Pr)²]",
             f"{q_ensayo} / [1 − 0,2×{x:.6f} − 0,8×{x:.6f}²] = {q_ensayo} / {den:.6f}",
             q_max, "BPD", B4 + "ec. 2.19 (pág. 14)"),
        Paso("Pwf al caudal objetivo", "Pwf = 0,125·Pr·[−1 + √(81 − 80·q_o/q_o max)]",
             f"0,125 × {pr} × [−1 + √(81 − 80 × {frac:.6f})]",
             pwf, "psi", B4 + "ec. 2.20 (pág. 14)"),
    ]
    return pwf, pasos


def _ipr_compuesta(pr: float, pb: float, pwf_t: float, q_t: float, q: float) -> tuple[float, list[Paso]]:
    """IPR compuesta de Brown Vol. 4 (pág. 15): recta sobre Pb y Vogel debajo."""
    pasos: list[Paso] = []
    if pwf_t >= pb:
        j = q_t / (pr - pwf_t)
        pasos.append(Paso("Índice de productividad", "J = q_ensayo / (Pr − Pwf_ensayo)",
                          f"{q_t} / ({pr} − {pwf_t})", j, "STB/d/psi", B4 + "ec. 2.31 (pág. 15)"))
    else:
        x = pwf_t / pb
        br = 1 - 0.2 * x - 0.8 * x * x
        j = q_t / (pr - pb + pb / 1.8 * br)
        pasos.append(Paso("Índice de productividad",
                          "J = q / {Pr − Pb + (Pb/1,8)·[1 − 0,2·(Pwf/Pb) − 0,8·(Pwf/Pb)²]}",
                          f"{q_t} / {{{pr} − {pb} + ({pb}/1,8)×{br:.6f}}}", j, "STB/d/psi",
                          B4 + "ec. 2.30 (pág. 15)"))
    qb = j * (pr - pb)
    qmax = qb + j * pb / 1.8
    pasos += [Paso("Caudal en el punto de burbuja", "q_b = J · (Pr − Pb)", f"{j:.6f} × ({pr} − {pb})",
                   qb, "STB/d", B4 + "ec. 2.27 (pág. 15)"),
              Paso("Caudal máximo", "q_o max = q_b + J · Pb / 1,8", f"{qb:.4f} + {j:.6f} × {pb} / 1,8",
                   qmax, "STB/d", B4 + "ec. 2.28 (pág. 15)")]
    if q >= qmax:
        raise ValueError(f"El caudal objetivo ({q:.1f} BPD) supera q_o max ({qmax:.1f} BPD).")
    if q <= qb:
        pwf = pr - q / j
        pasos.append(Paso("Pwf al caudal objetivo", "Pwf = Pr − q / J", f"{pr} − {q} / {j:.6f}",
                          pwf, "psi", B4 + "ec. 2.31 (pág. 15)"))
    else:
        frac = (q - qb) / (qmax - qb)
        pwf = 0.125 * pb * (-1 + math.sqrt(81 - 80 * frac))
        pasos.append(Paso("Pwf al caudal objetivo",
                          "Pwf = 0,125 · Pb · [−1 + √(81 − 80·(q − q_b)/(q_o max − q_b))]",
                          f"0,125 × {pb} × [−1 + √(81 − 80 × {frac:.6f})]", pwf, "psi",
                          B4 + "ec. 2.29 (pág. 15), despejada como la ec. 2.20 (pág. 14)"))
    return pwf, pasos


# --------------------------------------------------------------------------
# Paso 2a — Propiedades PVT a una presión y temperatura
# --------------------------------------------------------------------------
def paso2a_pvt(p_man: float, t_f: float, api: float, gas_sg: float, water_sg: float,
               gor: float) -> tuple[dict, list[Paso]]:
    """Rs, Bo, z, Bg y Bw a P (manométrica) y T.

    Decisiones aprobadas: Rs de Standing (Ahmed ec. 2-69), Bo de Standing
    (Ahmed ec. 2-84), z de Papay (Takács ec. 4.26) con pseudocríticas de
    Standing (Ahmed ecs. 2-18 y 2-19), Bg de Ahmed ec. 2-54 y presión absoluta
    = manométrica + 14,7 psi.
    """
    pa = p_man + P_ATM
    if pa <= 0:
        raise ValueError(f"Presión absoluta no positiva ({pa:.1f} psia): no hay PVT posible.")
    tr = t_f + 460.0
    sgo = 141.5 / (131.5 + api)
    # Rs — Standing (Ahmed ec. 2-69), acotado al GOR de producción
    y = 0.0125 * api - 0.00091 * t_f
    rs_st = gas_sg * ((pa / 18.2 + 1.4) * 10 ** y) ** 1.2048
    rs = min(rs_st, gor)
    # Bo — Standing (Ahmed ec. 2-84), la misma que usa el camino convencional
    F = rs * (gas_sg / sgo) ** 0.5 + 1.25 * t_f
    bo = standing_bo(rs, t_f, api, gas_sg)  # única implementación: pvt.standing_bo
    # z — Papay (Takács ec. 4.26) con pseudocríticas de Standing (Ahmed ecs.
    # 2-18 y 2-19). Única implementación: pvt.gas_z_factor
    ppc, tpc = _pseudo_critical_standing(gas_sg)
    ppr = pa / ppc
    tpr = tr / tpc
    z = gas_z_factor(pa, t_f, gas_sg)
    # Bg — Ahmed ec. 2-54. Única implementación: pvt.gas_bg
    bg = gas_bg(pa, t_f, z)
    # Bw — Ahmed ec. 2-125, agua sin gas
    a1 = 0.9947 + 5.8e-6 * t_f + 1.02e-6 * t_f ** 2
    a2 = -4.228e-6 + 1.8376e-8 * t_f - 6.77e-11 * t_f ** 2
    a3 = 1.3e-10 - 1.3855e-12 * t_f + 4.285e-15 * t_f ** 2
    bw = a1 + a2 * pa + a3 * pa ** 2

    pasos = [
        Paso("Presión absoluta", "P_abs = P + 14,7", f"{p_man:.3f} + 14,7", pa, "psia", ""),
        Paso("Gravedad específica del petróleo", "γo = 141,5 / (131,5 + °API)",
             f"141,5 / (131,5 + {api})", sgo, "—", ""),
        Paso("Exponente de Standing", "y = 0,0125·°API − 0,00091·T",
             f"0,0125×{api} − 0,00091×{t_f:.3f}", y, "—", AH + "ec. 2-69 (pág. 79)"),
        Paso("Gas disuelto (Standing)", "Rs = γg·[(P_abs/18,2 + 1,4)·10^y]^1,2048",
             f"{gas_sg}×[({pa:.3f}/18,2 + 1,4)×10^{y:.5f}]^1,2048", rs_st, "scf/STB",
             AH + "ec. 2-69 (pág. 79)"),
    ]
    if rs < rs_st:
        pasos.append(Paso("Gas disuelto acotado al GOR", "Rs = mín(Rs, GOR)",
                          f"mín({rs_st:.4f}; {gor})", rs, "scf/STB",
                          "Criterio del proyecto: no se puede disolver más gas que el producido"))
    pasos += [
        Paso("Parámetro de Standing", "F = Rs·(γg/γo)^0,5 + 1,25·T",
             f"{rs:.4f}×({gas_sg}/{sgo:.6f})^0,5 + 1,25×{t_f:.3f}", F, "—", AH + "ec. 2-84 (pág. 94)"),
        Paso("Factor volumétrico del petróleo (Standing)", "Bo = 0,9759 + 0,000120·F^1,2",
             f"0,9759 + 0,000120×{F:.4f}^1,2", bo, "bbl/STB", AH + "ec. 2-84 (pág. 94)"),
        Paso("Presión pseudocrítica (Standing)", "Ppc = 677 + 15,0·γg − 37,5·γg²",
             f"677 + 15,0×{gas_sg} − 37,5×{gas_sg}²", ppc, "psia", AH + "ec. 2-18 (pág. 42)"),
        Paso("Temperatura pseudocrítica (Standing)", "Tpc = 168 + 325·γg − 12,5·γg²",
             f"168 + 325×{gas_sg} − 12,5×{gas_sg}²", tpc, "°R", AH + "ec. 2-19 (pág. 42)"),
        Paso("Presión pseudorreducida", "Ppr = P_abs / Ppc", f"{pa:.3f} / {ppc:.3f}", ppr, "—",
             AH + "pág. 42"),
        Paso("Temperatura pseudorreducida", "Tpr = (T + 460) / Tpc", f"{tr:.2f} / {tpc:.3f}", tpr, "—",
             AH + "pág. 42"),
        Paso("Factor de compresibilidad (Papay)",
             "z = 1 − 3,52·Ppr / 10^(0,9813·Tpr) + 0,274·Ppr² / 10^(0,8157·Tpr)",
             f"1 − 3,52×{ppr:.5f}/10^(0,9813×{tpr:.5f}) + 0,274×{ppr:.5f}²/10^(0,8157×{tpr:.5f})",
             z, "—", TK + "ec. 4.26 (pág. 169)"),
        Paso("Factor volumétrico del gas", "Bg = 0,005035·z·(T + 460) / P_abs",
             f"0,005035×{z:.5f}×{tr:.2f} / {pa:.3f}", bg, "bbl/scf", AH + "ec. 2-54 (pág. 66)"),
        Paso("Factor volumétrico del agua (Ahmed ec. 2-125)", "Bw = A1 + A2·P_abs + A3·P_abs²",
             f"{a1:.6f} + ({a2:.4e})×{pa:.3f} + ({a3:.4e})×{pa:.3f}²", bw, "bbl/STB",
             AH + "ec. 2-125 (pág. 124)"),
    ]
    return {"p_abs": pa, "rs": rs, "bo": bo, "z": z, "bg": bg, "bw": bw, "sg_o": sgo}, pasos


# --------------------------------------------------------------------------
# Paso 2b-c — Volúmenes, masa y gravedad específica de la mezcla
# --------------------------------------------------------------------------
def paso2bc_mezcla(q_liq: float, wc: float, gor: float, gas_sg: float, water_sg: float,
                   pvt: dict) -> tuple[dict, list[Paso]]:
    """Volumen de cada fase a P y T, masa de la mezcla y su SG (con todo el gas).

    ``pvt`` es la salida de :func:`paso2a_pvt` a esa misma P y T.
    """
    rs, bo, bg, bw, sgo = pvt["rs"], pvt["bo"], pvt["bg"], pvt["bw"], pvt["sg_o"]
    qo = q_liq * (1 - wc); qw = q_liq * wc
    g_tot = gor * qo; g_sol = rs * qo; g_lib = max(g_tot - g_sol, 0.0)
    vg = g_lib * bg; vo = qo * bo; vw = qw * bw; vt = vg + vo + vw
    masa = (qo * sgo + qw * water_sg) * 62.4 * 5.615 + gor * qo * gas_sg * 0.0764
    sg = masa / (vt * 5.615 * 62.4)
    c1 = B2 + "Sección 4.53103, paso 1, ec. 4.52 (pág. 74)"
    c5 = B2 + "Sección 4.53102, paso 5 (pág. 74)"
    pasos = [
        Paso("Caudal de petróleo", "BOPD = q · (1 − WC)", f"{q_liq} × (1 − {wc})", qo, "STB/d", ""),
        Paso("Caudal de agua", "BWPD = q · WC", f"{q_liq} × {wc}", qw, "STB/d", ""),
        Paso("Gas total", "G_total = GOR · BOPD", f"{gor} × {qo:.3f}", g_tot, "scf/d", c1),
        Paso("Gas en solución", "G_sol = Rs · BOPD", f"{rs:.4f} × {qo:.3f}", g_sol, "scf/d", c1),
        Paso("Gas libre", "G_libre = G_total − G_sol", f"{g_tot:.2f} − {g_sol:.2f}", g_lib, "scf/d", c1),
        Paso("Volumen de gas libre", "Vg = G_libre · Bg", f"{g_lib:.2f} × {bg:.8f}", vg, "bbl/d", c1),
        Paso("Volumen de petróleo", "Vo = BOPD · Bo", f"{qo:.3f} × {bo:.6f}", vo, "bbl/d", c1),
        Paso("Volumen de agua", "Vw = BWPD · Bw", f"{qw:.3f} × {bw:.6f}", vw, "bbl/d", c1),
        Paso("Volumen total", "V = Vg + Vo + Vw", f"{vg:.3f} + {vo:.3f} + {vw:.3f}", vt, "bbl/d", c1),
        Paso("Masa de la mezcla",
             "m = (BOPD·γo + BWPD·γw)·62,4·5,615 + GOR·BOPD·γg·0,0764",
             f"({qo:.3f}×{sgo:.6f} + {qw:.3f}×{water_sg})×62,4×5,615 + {gor}×{qo:.3f}×{gas_sg}×0,0764",
             masa, "lb/d", c5),
        Paso("Gravedad específica de la mezcla", "SG = m / (V · 5,615 · 62,4)",
             f"{masa:.2f} / ({vt:.3f} × 5,615 × 62,4)", sg, "—", c5),
    ]
    return {"qo": qo, "qw": qw, "g_libre": g_lib, "vg": vg, "vo": vo, "vw": vw, "v_total": vt,
            "masa": masa, "sg": sg}, pasos


# --------------------------------------------------------------------------
# Paso 3 — PIP con gradiente constante de la mezcla del fondo
# --------------------------------------------------------------------------
def paso3_pip(pwf: float, sg_mezcla: float, d_pwf: float, d_bomba: float) -> tuple[float, list[Paso]]:
    """PIP = Pwf − 0,433·SG·(D_pwf − D_bomba).

    Args:
        pwf: Presión de fondo fluyente [psi], a la profundidad ``d_pwf``.
        sg_mezcla: SG de la mezcla en el fondo (paso 2b-c).
        d_pwf: Profundidad donde vale la Pwf (base de los punzados) [ft].
        d_bomba: Profundidad de la admisión de la bomba [ft].
    """
    if d_bomba > d_pwf:
        raise ValueError("La bomba no puede estar por debajo del punto donde se mide la Pwf.")
    grad = 0.433 * sg_mezcla
    L = d_pwf - d_bomba
    pip = pwf - grad * L
    pasos = [
        Paso("Gradiente de la mezcla", "grad = 0,433 · SG", f"0,433 × {sg_mezcla:.6f}", grad, "psi/ft",
             B2 + "Ejemplo #1C (pág. 68)"),
        Paso("Columna sobre la admisión", "L = D_Pwf − D_bomba", f"{d_pwf} − {d_bomba}", L, "ft", ""),
        Paso("Presión en la admisión", "PIP = Pwf − grad · L", f"{pwf:.3f} − {grad:.6f} × {L:.3f}",
             pip, "psi", B2 + "Sección 4.5324 (pág. 63)"),
    ]
    return pip, pasos


# --------------------------------------------------------------------------
# Paso 4 — Temperatura en la admisión y GOR en la succión (con separador)
# --------------------------------------------------------------------------
def temperatura_lineal(t_boca: float, t_fondo: float, d_fondo: float, d: float) -> tuple[float, Paso]:
    """Perfil lineal de temperatura entre la boca y el fondo."""
    t = t_boca + (t_fondo - t_boca) * d / d_fondo
    return t, Paso("Temperatura a la profundidad", "T(D) = T_boca + (T_fondo − T_boca)·D / D_fondo",
                   f"{t_boca} + ({t_fondo} − {t_boca}) × {d} / {d_fondo}", t, "°F",
                   "Criterio del proyecto (perfil lineal)")


def paso4_gor_succion(mezcla_adm: dict, pvt_adm: dict, eta_sep: float) -> tuple[dict, list[Paso]]:
    """Gas que entra a la bomba después del separador y GOR en la succión.

    Args:
        mezcla_adm: salida de :func:`paso2bc_mezcla` evaluada a PIP y T de admisión.
        pvt_adm: salida de :func:`paso2a_pvt` a PIP y T de admisión.
        eta_sep: eficiencia de separación [0-1]; 0 si no hay separador.
    """
    qo = mezcla_adm["qo"]; vg = mezcla_adm["vg"]; vl = mezcla_adm["vo"] + mezcla_adm["vw"]
    g_lib = mezcla_adm["g_libre"]; g_sol = pvt_adm["rs"] * qo
    f_adm = vg / (vl + vg) if vl + vg > 0 else 0.0
    vg_b = vg * (1 - eta_sep); g_lib_b = g_lib * (1 - eta_sep)
    f_b = vg_b / (vl + vg_b) if vl + vg_b > 0 else 0.0
    gor_b = (g_lib_b + g_sol) / qo if qo > 0 else 0.0
    c = TK + "ecs. 5.36 y 5.37 (pág. 274)"
    pasos = [
        Paso("Volumen de líquido en la admisión", "V_L = Vo + Vw",
             f"{mezcla_adm['vo']:.3f} + {mezcla_adm['vw']:.3f}", vl, "bbl/d", ""),
        Paso("Gas libre en la admisión (antes del separador)", "f_adm = Vg / (V_L + Vg)",
             f"{vg:.3f} / ({vl:.3f} + {vg:.3f})", f_adm * 100, "%", TK + "ec. 4.23 (pág. 168)"),
        Paso("Gas libre que entra a la bomba", "Vg_bomba = Vg · (1 − η)",
             f"{vg:.3f} × (1 − {eta_sep})", vg_b, "bbl/d", c),
        Paso("Gas libre en la succión (después del separador)", "f_bomba = Vg_bomba / (V_L + Vg_bomba)",
             f"{vg_b:.3f} / ({vl:.3f} + {vg_b:.3f})", f_b * 100, "%", c),
        Paso("Gas libre en la bomba, a condiciones estándar", "G_libre_bomba = G_libre · (1 − η)",
             f"{g_lib:.2f} × (1 − {eta_sep})", g_lib_b, "scf/d", c),
        Paso("GOR en la succión de la bomba", "GOR_bomba = (G_libre_bomba + G_sol) / BOPD",
             f"({g_lib_b:.2f} + {g_sol:.2f}) / {qo:.3f}", gor_b, "scf/STB",
             TK + "ecs. 5.36 y 5.37 (pág. 274); equivale a Rs + (1 − η)·(GOR − Rs)"),
    ]
    return {"f_adm": f_adm, "vg_bomba": vg_b, "v_bomba": vl + vg_b, "f_bomba": f_b, "gor_bomba": gor_b}, pasos


# --------------------------------------------------------------------------
# Paso 5 — Presión de descarga: recorrido por el tubing (Poettmann y Carpenter)
# --------------------------------------------------------------------------
PC = "Brown y Beggs (1977), Sección 2.3322, ec. 2.34 (pág. 106)"
N_TRAMOS_TUBING = 50
TOL_PSI = 0.01   # criterio del proyecto
MAX_ITER = 50


def gradiente_pc(p_man: float, t_f: float, q_liq: float, wc: float, gor: float, api: float,
                 gas_sg: float, water_sg: float, d_in: float) -> tuple[float, list[Paso]]:
    """Gradiente de presión de la mezcla en un punto (Poettmann y Carpenter).

    Sin gas libre la misma cuenta da λl = 1 y ρm = ρl (una sola fase).
    """
    pvt, _ = paso2a_pvt(p_man, t_f, api, gas_sg, water_sg, gor)
    rs, bo, bw, bg, z, sgo, pa = pvt["rs"], pvt["bo"], pvt["bw"], pvt["bg"], pvt["z"], pvt["sg_o"], pvt["p_abs"]
    rho_o = (62.4 * sgo + 0.0136 * rs * gas_sg) / bo
    rho_w = 62.4 * water_sg / bw
    rho_l = rho_o * (1 - wc) + rho_w * wc
    rho_g = 2.70 * gas_sg * pa / (z * (t_f + 460.0))
    area = math.pi / 4 * (d_in / 12) ** 2
    ql = q_liq * ((1 - wc) * bo + wc * bw)
    qg = q_liq * (1 - wc) * max(gor - rs, 0.0) * bg
    vsl = ql * 5.615 / 86400 / area
    vsg = qg * 5.615 / 86400 / area
    vm = vsl + vsg
    lam = vsl / vm
    rho_m = rho_l * lam + rho_g * (1 - lam)
    d_ft = d_in / 12
    nrho = rho_m * vm * d_ft
    f, _fuera = pc_friction_factor(nrho)
    w = rho_m * vm * area * 86400.0
    g_grav = rho_m / 144
    g_fric = pc_friction_gradient(f, w, rho_m, d_ft)
    grad = g_grav + g_fric
    pasos = [
        Paso("PVT en el punto", "Rs, Bo, Bw, z, Bg (paso 2a)", f"a {p_man:.3f} psig y {t_f:.3f} °F",
             rs, "scf/STB (Rs)", "Pasos 2a.1 a 2a.14"),
        Paso("Densidad del petróleo con su gas disuelto", "ρo = (62,4·γo + 0,0136·Rs·γg) / Bo",
             f"(62,4×{sgo:.6f} + 0,0136×{rs:.4f}×{gas_sg}) / {bo:.6f}", rho_o, "lb/ft³", AH + "ec. 2-92 (pág. 97)"),
        Paso("Densidad del agua", "ρw = 62,4·γw / Bw", f"62,4×{water_sg} / {bw:.6f}", rho_w, "lb/ft³", ""),
        Paso("Densidad del líquido", "ρl = ρo·(1 − WC) + ρw·WC",
             f"{rho_o:.4f}×(1 − {wc}) + {rho_w:.4f}×{wc}", rho_l, "lb/ft³", ""),
        Paso("Densidad del gas libre", "ρg = 2,70·γg·P_abs / (z·(T + 460))",
             f"2,70×{gas_sg}×{pa:.3f} / ({z:.5f}×{t_f + 460:.2f})", rho_g, "lb/ft³",
             AH + "ec. 2-17 (pág. 41), con Ma = 28,96·γg y R = 10,73"),
        Paso("Área de flujo", "A = π/4·(d/12)²", f"π/4 × ({d_in}/12)²", area, "ft²", ""),
        Paso("Caudal de líquido en el punto", "q_l = q·[(1 − WC)·Bo + WC·Bw]",
             f"{q_liq}×[(1 − {wc})×{bo:.6f} + {wc}×{bw:.6f}]", ql, "bbl/d", TK + "ec. 4.22 (pág. 168)"),
        Paso("Caudal de gas libre en el punto", "q_g = q·(1 − WC)·(GOR − Rs)·Bg",
             f"{q_liq}×(1 − {wc})×({gor:.4f} − {rs:.4f})×{bg:.8f}", qg, "bbl/d", TK + "ec. 4.15 (pág. 166)"),
        Paso("Velocidad superficial del líquido", "v_sl = q_l·5,615 / 86 400 / A",
             f"{ql:.3f}×5,615 / 86 400 / {area:.6f}", vsl, "ft/s", TK + "ec. 4.17 (pág. 167)"),
        Paso("Velocidad superficial del gas", "v_sg = q_g·5,615 / 86 400 / A",
             f"{qg:.3f}×5,615 / 86 400 / {area:.6f}", vsg, "ft/s", TK + "ec. 4.17 (pág. 167)"),
        Paso("Velocidad de la mezcla", "v_m = v_sl + v_sg", f"{vsl:.5f} + {vsg:.5f}", vm, "ft/s", PC),
        Paso("Fracción de líquido sin deslizamiento", "λl = v_sl / v_m", f"{vsl:.5f} / {vm:.5f}", lam, "—", PC),
        Paso("Densidad de la mezcla", "ρm = ρl·λl + ρg·(1 − λl)",
             f"{rho_l:.4f}×{lam:.5f} + {rho_g:.5f}×(1 − {lam:.5f})", rho_m, "lb/ft³", PC),
        Paso("Numerador del número de Reynolds", "Dρv = ρm·v_m·d",
             f"{rho_m:.4f}×{vm:.5f}×{d_ft:.5f}", nrho, "lb/(ft·s)", "Brown y Beggs (1977), Fig. 2.36 (pág. 106)"),
        Paso("Factor de fricción (Fig. 2.36)", "f = Fig. 2.36 en Dρv, interpolada en log-log",
             f"Dρv = {nrho:.3f}" + (" (fuera de la figura: valor del extremo)" if _fuera else ""), f, "—",
             "Brown y Beggs (1977), Sección 2.3322, Fig. 2.36 (pág. 106)"),
        Paso("Caudal másico", "w = ρm·v_m·A·86 400", f"{rho_m:.4f}×{vm:.5f}×{area:.6f}×86 400",
             w, "lb/d", PC),
        Paso("Gradiente por gravedad", "(dP/dz)_grav = ρm / 144", f"{rho_m:.4f} / 144", g_grav, "psi/ft", PC),
        Paso("Gradiente por fricción", "(dP/dz)_fric = f·w² / (7,413×10¹⁰·ρm·d⁵·144)",
             f"{f:.6f}×{w:.1f}² / (7,413×10¹⁰×{rho_m:.4f}×{d_ft:.5f}⁵×144)", g_fric, "psi/ft", PC),
        Paso("Gradiente total", "dP/dz = (dP/dz)_grav + (dP/dz)_fric", f"{g_grav:.6f} + {g_fric:.7f}",
             grad, "psi/ft", PC),
    ]
    return grad, pasos


def paso5_descarga(p_boca: float, t_boca: float, t_bomba: float, d_bomba: float, q_liq: float,
                   wc: float, gor_bomba: float, api: float, gas_sg: float, water_sg: float,
                   d_tubing_in: float, n: int = N_TRAMOS_TUBING) -> tuple[dict, list[Paso]]:
    """Recorre el tubing de la boca a la descarga en ``n`` tramos.

    La descarga se toma a la MISMA profundidad que la admisión (separación 0 ft),
    como Brown Vol. 2b, Fig. 4.56A (pág. 75).

    En cada tramo: presión y temperatura del punto medio, gradiente de
    Poettmann y Carpenter, y P_(i+1) = P_i + (dP/dz)·Δz. El punto medio se
    itera hasta converger porque el gradiente depende de la presión que se busca.
    """
    dz = d_bomba / n
    p = p_boca
    tramos = []
    detalle_1 = []
    for i in range(n):
        z_m = (i + 0.5) * dz
        t_m = t_boca + (t_bomba - t_boca) * z_m / d_bomba
        # P2 supuesta = P1; se itera hasta que P2 calculada = P2 supuesta
        # (diferencia < TOL_PSI), como en Brown y Beggs (1977), Apéndice C.12.
        p_sig = p
        for _ in range(MAX_ITER):
            p_m = 0.5 * (p + p_sig)
            g, det = gradiente_pc(p_m, t_m, q_liq, wc, gor_bomba, api, gas_sg, water_sg, d_tubing_in)
            p_calc = p + g * dz
            listo = abs(p_calc - p_sig) < TOL_PSI
            p_sig = p_calc
            if listo:
                break
        p_m = 0.5 * (p + p_sig)
        if i == 0:
            detalle_1 = det
        tramos.append({"z0": i * dz, "z1": (i + 1) * dz, "p0": p, "p_m": p_m, "t_m": t_m,
                       "grad": g, "dp": g * dz, "p1": p_sig})
        p = p_sig
    pasos = [
        Paso("GOR que sube por el tubing", "GOR_tubing = GOR_bomba (paso 4c.6)", f"{gor_bomba:.4f}",
             gor_bomba, "scf/STB", "Paso 4c.6"),
        Paso("Profundidad de la descarga", "D_desc = D_bomba (misma que la admisión)", f"{d_bomba}",
             d_bomba, "ft", B2 + "Fig. 4.56A (pág. 75)"),
        Paso("Largo de cada tramo", "Δz = D_bomba / n", f"{d_bomba} / {n}", dz, "ft", "Criterio del proyecto"),
        Paso("Temperatura del punto medio", "T_m = T_boca + (T_bomba − T_boca)·z_m / D_bomba",
             f"{t_boca} + ({t_bomba:.3f} − {t_boca}) × {tramos[0]['z0'] + dz / 2:.2f} / {d_bomba}",
             tramos[0]["t_m"], "°F", "Criterio del proyecto (perfil lineal)"),
        Paso("Presión del punto medio (tramo 1)",
             f"P_m = [P_i + P_(i+1)] / 2, iterando hasta |P_calc − P_sup| < {TOL_PSI} psi",
             f"({tramos[0]['p0']:.3f} + {tramos[0]['p1']:.3f}) / 2", tramos[0]["p_m"], "psig",
             "Criterio del proyecto"),
    ] + detalle_1 + [
        Paso("Presión al final de cada tramo", "P_(i+1) = P_i + (dP/dz)·Δz",
             f"{tramos[0]['p0']:.3f} + {tramos[0]['grad']:.6f} × {dz:.3f} (tramo 1)",
             tramos[0]["p1"], "psig", B2 + "Sección 4.531 (pág. 60)"),
        Paso("Presión de descarga", "P_desc = P_boca + Σ (dP/dz)_i·Δz",
             f"{p_boca} + {sum(t['dp'] for t in tramos):.3f}", p, "psig",
             B2 + "Sección 4.53102, paso 2 (pág. 74)"),
    ]
    return {"p_descarga": p, "tramos": tramos}, pasos


# --------------------------------------------------------------------------
# Paso 6 — Selección de la bomba
# --------------------------------------------------------------------------
def paso6_seleccion(q_succion: float, q_descarga: float, casing_id: float, frecuencia_hz: float,
                    catalog_manager) -> tuple[dict, list[Paso]]:
    """Elige la bomba del catálogo.

    6.3 que entre en el casing; 6.4 que su rango recomendado, llevado a la
    frecuencia de diseño, cubra el caudal de succión y el de descarga; 6.5 la de
    mayor eficiencia al caudal promedio; 6.6 si empatan, la de mayor diámetro.
    """
    from bes.core.affinity import pump_at_frequency
    q_prom = 0.5 * (q_succion + q_descarga)
    q_min, q_max = min(q_succion, q_descarga), max(q_succion, q_descarga)
    evaluadas = []
    for b in catalog_manager.get_all_pumps():
        if b.od >= casing_id:
            continue
        bf = pump_at_frequency(b, frecuencia_hz)
        if not (bf.min_flow <= q_min and q_max <= bf.max_flow):
            continue
        c = catalog_manager.interpolate_pump_curve(bf, q_prom)
        evaluadas.append({"bomba": bf, "fabricante": b.manufacturer, "modelo": b.model, "od": b.od,
                          "q_min": bf.min_flow, "q_max": bf.max_flow, "eficiencia": c["efficiency"]})
    if not evaluadas:
        raise ValueError("Ninguna bomba del catálogo entra en el casing y cubre los dos caudales "
                         f"({q_min:.0f} a {q_max:.0f} bbl/d a {frecuencia_hz:.0f} Hz).")
    evaluadas.sort(key=lambda e: (-round(e["eficiencia"], 4), -e["od"]))
    el = evaluadas[0]
    pasos = [
        Paso("Caudal de mezcla en la succión", "q_succión (paso 4c)", f"{q_succion:.2f}", q_succion, "bbl/d",
             "Paso 4"),
        Paso("Caudal de mezcla en la descarga", "q_descarga = V a P_desc y T_adm (pasos 2a y 2b)",
             f"{q_descarga:.2f}", q_descarga, "bbl/d", B2 + "Sección 4.53101 (pág. 74)"),
        Paso("Caudal promedio", "q_prom = (q_succión + q_descarga) / 2",
             f"({q_succion:.2f} + {q_descarga:.2f}) / 2", q_prom, "bbl/d", ""),
        Paso("Filtro de diámetro", "OD_bomba < ID_casing", f"ID_casing = {casing_id}", casing_id, "in",
             B2 + "Sección 4.5327, paso 4 (pág. 66)"),
        Paso("Filtro de rango", "q_min(f) ≤ q_succión y q_descarga ≤ q_max(f), con q(f) = q_60·(f/60)",
             f"{q_min:.1f} a {q_max:.1f} bbl/d a {frecuencia_hz:.0f} Hz", len(evaluadas), "bombas pasan",
             B2 + "Sección 4.51 (pág. 58) y Sección 4.534 (pág. 67)"),
        Paso("Bomba elegida: mayor eficiencia; si empatan, mayor diámetro",
             "máx η(q_prom); desempate máx OD",
             " · ".join(f"{e['fabricante']} {e['modelo']} (OD {e['od']} in, η {e['eficiencia']*100:.1f} %)"
                        for e in evaluadas),
             el["eficiencia"] * 100, f"% ({el['fabricante']} {el['modelo']})",
             B2 + "Sección 4.5327, paso 4 (pág. 66) y Sección 4.521 (pág. 58)"),
    ]
    return {"bomba": el["bomba"], "modelo": el["modelo"], "fabricante": el["fabricante"], "od": el["od"],
            "q_prom": q_prom, "candidatas": evaluadas}, pasos


# --------------------------------------------------------------------------
# Paso 7 — Incrementos de presión → etapas y potencia
# --------------------------------------------------------------------------
INCREMENTO_PSI = 200.0   # Brown Vol. 2b, Sección 4.53103 (pág. 74): «Assume 200 psi increment»


def paso7_incrementos(pip: float, p_desc: float, t_adm: float, q_liq: float, wc: float,
                      gor_bomba: float, api: float, gas_sg: float, water_sg: float, bomba,
                      catalog_manager, incremento_psi: float = INCREMENTO_PSI
                      ) -> tuple[dict, list[Paso]]:
    """Etapas y potencia por el método de incrementos (Brown Vol. 2b, Sección 4.53102).

    ``bomba`` es la curva ya llevada a la frecuencia de diseño (paso 6). La
    temperatura se toma constante a lo largo de la bomba (Sección 4.53101).
    """
    fronteras = [pip]
    while fronteras[-1] + incremento_psi < p_desc - 1e-9:
        fronteras.append(fronteras[-1] + incremento_psi)
    fronteras.append(p_desc)
    punto = []
    for p in fronteras:
        pvt, _ = paso2a_pvt(p, t_adm, api, gas_sg, water_sg, gor_bomba)
        m, _ = paso2bc_mezcla(q_liq, wc, gor_bomba, gas_sg, water_sg, pvt)
        punto.append({"p": p, "t": t_adm, "gor": gor_bomba, "z": pvt["z"], "rs": pvt["rs"], "bg": pvt["bg"],
                      "bo": pvt["bo"], "vg": m["vg"], "v": m["v_total"], "sg": m["sg"],
                      "grad": 0.433 * m["sg"]})
    tramos = []
    for a, b in zip(punto[:-1], punto[1:]):
        dp = b["p"] - a["p"]
        grad = 0.5 * (a["grad"] + b["grad"])
        sg = 0.5 * (a["sg"] + b["sg"])
        q = 0.5 * (a["v"] + b["v"])
        c = catalog_manager.interpolate_pump_curve(bomba, q)
        psi_et = c["head_per_stage"] * grad
        n = dp / psi_et
        hp = n * c["hp_per_stage"] * sg
        tramos.append({"p0": a["p"], "p1": b["p"], "dp": dp, "q": q, "grad": grad, "sg": sg,
                       "altura": dp / grad,
                       "h": c["head_per_stage"], "hp_et": c["hp_per_stage"], "psi_et": psi_et,
                       "n": n, "hp": hp})
    n_tot = sum(t["n"] for t in tramos)
    n_inst = math.ceil(n_tot - 1e-9)
    hp_tot = sum(t["hp"] for t in tramos)
    t1 = tramos[0]
    c = B2 + "Sección 4.53102"
    pasos = [
        Paso("Salto de presión de la bomba", "ΔP = P_desc − PIP", f"{p_desc:.3f} − {pip:.3f}",
             p_desc - pip, "psi", c + ", paso 3 (pág. 74)"),
        Paso("Escalones de presión", "n = ⌈ΔP / incremento⌉", f"⌈{p_desc - pip:.3f} / {incremento_psi}⌉",
             len(tramos), "escalones", c + ", paso 4 (pág. 74); 200 psi: Sección 4.53103 (pág. 74)"),
        Paso("En cada presión: PVT, volumen y SG de la mezcla", "pasos 2a y 2b-c, con GOR_bomba y T_adm",
             f"T = {t_adm:.3f} °F constante en la bomba", len(punto), "puntos",
             c + ", paso 5; T constante: Sección 4.53101 (pág. 74)"),
        Paso("Gradiente en cada presión", "grad = 0,433 · SG", f"0,433 × {punto[0]['sg']:.6f} (en la admisión)",
             punto[0]["grad"], "psi/ft", c + ", paso 6 (pág. 74)"),
        Paso("Gradiente promedio del escalón", "grad_prom = (grad_i + grad_i+1) / 2",
             f"({punto[0]['grad']:.6f} + {punto[1]['grad']:.6f}) / 2  (escalón 1)", t1["grad"], "psi/ft",
             c + ", paso 7 (pág. 74)"),
        Paso("Caudal promedio del escalón", "q_prom = (V_i + V_i+1) / 2",
             f"({punto[0]['v']:.2f} + {punto[1]['v']:.2f}) / 2  (escalón 1)", t1["q"], "bbl/d",
             c + ", pasos 9 y 10 (pág. 74)"),
        Paso("Altura y potencia por etapa en la curva", "H_etapa, hp_etapa = curva(q_prom) a la frecuencia de diseño",
             f"q = {t1['q']:.2f} bbl/d  (escalón 1)", t1["h"], "ft/etapa", c + ", paso 11 (pág. 74)"),
        Paso("Escalón pasado a altura", "h_i = ΔP_i / grad_prom",
             f"{t1['dp']:.3f} / {t1['grad']:.6f}  (escalón 1)", t1["altura"], "ft", c + ", paso 8 (pág. 74)"),
        Paso("Presión que da cada etapa", "Δp_etapa = H_etapa · grad_prom",
             f"{t1['h']:.4f} × {t1['grad']:.6f}  (escalón 1)", t1["psi_et"], "psi/etapa", c + ", paso 12 (pág. 74)"),
        Paso("Etapas del escalón", "N_i = ΔP_i / Δp_etapa", f"{t1['dp']:.3f} / {t1['psi_et']:.5f}  (escalón 1)",
             t1["n"], "etapas", c + ", paso 13 (pág. 74)"),
        Paso("Potencia del escalón", "HP_i = N_i · hp_etapa · SG_prom",
             f"{t1['n']:.4f} × {t1['hp_et']:.5f} × {t1['sg']:.6f}  (escalón 1)", t1["hp"], "hp",
             c + ", pasos 15 y 16 (pág. 74); HP = hp/etapa·N·SG: Sección 4.5323 (pág. 62)"),
        Paso("Etapas totales", "N = ⌈Σ N_i⌉", f"⌈{n_tot:.3f}⌉", n_inst, "etapas", c + ", paso 14 (pág. 74)"),
        Paso("Potencia total al eje", "HP = Σ HP_i", " + ".join(f"{t['hp']:.2f}" for t in tramos[:4])
             + (" + …" if len(tramos) > 4 else ""), hp_tot, "hp", c + ", paso 16 (pág. 74)"),
    ]
    return {"tramos": tramos, "puntos": punto, "etapas_exactas": n_tot, "etapas": n_inst, "hp": hp_tot}, pasos


# --------------------------------------------------------------------------
# Paso 8 — Eje, presión de carcasa y arreglo de carcasas
# --------------------------------------------------------------------------
TIPOS_CARCASA = (("standard", "estándar"), ("buttress", "buttress"), ("welded", "soldada"))


def paso8_eje_carcasas(modelo: str, etapas: int, hp: float, grad_max: float, frecuencia_hz: float,
                       catalog_manager) -> tuple[dict, list[Paso]]:
    """Verifica el eje y la carcasa (Takács Sección 5.3.3.4, pág. 250) y arma las carcasas.

    Los límites se leen de la hoja de la bomba en el catálogo, a su frecuencia
    base. El arreglo combina las carcasas de la tabla del catálogo: suma justa
    de etapas (o el menor sobrante), la menor cantidad de carcasas y, si
    empatan, menos tamaños distintos con las grandes primero.
    """
    from bes.core.housing import optimize_housings
    raw = next(b for b in catalog_manager.get_all_pumps() if b.model == modelo)
    f_base = raw.catalog_frequency_hz
    rel = frecuencia_hz / f_base
    hoja = raw.fuente_mecanica or "hoja de la bomba en el catálogo"
    if not raw.shaft_hp_limit_std:
        raise ValueError(f"La bomba {modelo} no tiene los límites mecánicos cargados del catálogo.")
    # 8.1 Eje (Takács ec. 5.12)
    std_f = raw.shaft_hp_limit_std * rel
    hs_f = raw.shaft_hp_limit_high_strength * rel
    if hp <= std_f:
        eje = "estándar"
    elif hs_f and hp <= hs_f:
        eje = "alta resistencia"
    else:
        raise ValueError(f"La bomba {modelo} pide {hp:.1f} hp y su eje de alta resistencia "
                         f"admite {hs_f:.1f} hp a {frecuencia_hz:.0f} Hz.")
    # 8.2 Presión de carcasa (Takács ec. 5.13)
    h0 = max(pt.head_per_stage for pt in raw.points)
    p_max = h0 * etapas * grad_max * rel ** 2
    tipo, limite = None, None
    for clave, nombre in TIPOS_CARCASA:
        lim = raw.housing_burst_psi.get(clave)
        if lim and p_max <= lim:
            tipo, limite = nombre, lim
            break
    if tipo is None:
        raise ValueError(f"La presión máxima de la bomba {modelo} ({p_max:.0f} psi) supera "
                         "todas las carcasas del catálogo.")
    # 8.3 Arreglo de carcasas
    arr = optimize_housings(etapas, raw.housings, h0 * rel ** 2, grad_max / 0.433, limite)
    if arr is None:
        raise ValueError(f"Ninguna combinación de carcasas de la {modelo} aloja {etapas} etapas.")
    por_etapas = {h.stages: h for h in raw.housings}
    filas = [{"carcasa": por_etapas[n].code, "etapas": n, "cantidad": k,
              "largo_ft": por_etapas[n].length_ft} for n, k in arr["housings"]]
    largo = sum(f["largo_ft"] * f["cantidad"] for f in filas)
    texto = " + ".join(f"{f['cantidad']} × carcasa {f['carcasa']} ({f['etapas']} etapas)" for f in filas)
    c5 = TK + "Sección 5.3.3.4 (pág. 250)"
    pasos = [
        Paso("Límite del eje estándar a la frecuencia de diseño", "HP_eje = HP_eje base · f / f_base",
             f"{raw.shaft_hp_limit_std:.0f} × {frecuencia_hz:.0f} / {f_base:.0f}", std_f, "hp",
             TK + f"ec. 5.12 (pág. 250); límite: {hoja}"),
        Paso("Límite del eje de alta resistencia", "HP_eje = HP_eje base · f / f_base",
             f"{raw.shaft_hp_limit_high_strength:.0f} × {frecuencia_hz:.0f} / {f_base:.0f}", hs_f, "hp",
             TK + f"ec. 5.12 (pág. 250); límite: {hoja}"),
        Paso(f"Eje: {eje}", "HP_bomba ≤ HP_eje", f"{hp:.2f} hp (paso 7)", hp, "hp", c5),
        Paso("Altura por etapa a caudal cero", "(H/etapa)máx de la curva a f_base",
             f"curva de {f_base:.0f} Hz", h0, "ft/etapa", c5),
        Paso("Gradiente del fluido", "grad = 0,433 · SG en la descarga (el mayor dentro de la bomba, paso 7)",
             f"{grad_max:.6f}", grad_max, "psi/ft", c5),
        Paso("Presión máxima dentro de la bomba", "p_máx = (H/etapa)máx · Etapas · grad · (f / f_base)²",
             f"{h0:.4f} × {etapas} × {grad_max:.6f} × ({frecuencia_hz:.0f} / {f_base:.0f})²", p_max, "psi",
             TK + "ec. 5.13 (pág. 250)"),
        Paso(f"Carcasa: {tipo}", "p_máx ≤ presión de reventamiento de la carcasa",
             " · ".join(f"{n} {raw.housing_burst_psi.get(k):.0f} psi" if raw.housing_burst_psi.get(k)
                        else f"{n} no aplica" for k, n in TIPOS_CARCASA), limite, "psi", c5 + f"; {hoja}"),
        Paso("Arreglo de carcasas", "Σ etapas de las carcasas = Etapas; menor cantidad de carcasas",
             texto, arr["n_housings"], "carcasas",
             (raw.fuente_carcasas or "tabla de carcasas del catálogo") + "; combinación: criterio del proyecto"),
        Paso("Etapas ciegas", "capacidad instalada − Etapas", f"{arr['housing_size_stages']} − {etapas}",
             arr["dummy_stages"], "etapas", ""),
        Paso("Largo de la bomba", "Σ largo de las carcasas",
             " + ".join(f"{f['cantidad']} × {f['largo_ft']}" for f in filas), largo, "ft",
             raw.fuente_carcasas or ""),
    ]
    return {"eje": eje, "hp_eje_std": std_f, "hp_eje_ar": hs_f, "p_max": p_max, "carcasa": tipo,
            "limite_carcasa": limite, "carcasas": filas, "n_carcasas": arr["n_housings"],
            "etapas_ciegas": arr["dummy_stages"], "largo_ft": largo}, pasos


# --------------------------------------------------------------------------
# Paso 9 — Protector (sección sellante)
# --------------------------------------------------------------------------
TIPO_SELLO = {"labyrinth": "laberinto", "bag": "bolsa", "double_bag": "doble bolsa"}


def paso9_protector(modelo: str, etapas: int, eje_bomba: str, t_fondo: float, desviacion: float,
                    catalog_manager) -> tuple[dict, list[Paso]]:
    """Elige el protector (Takács Sección 5.3.4, págs. 251 a 253).

    Serie de la bomba y mismo fabricante; cojinete high-load cuando la tabla de
    tándem de la bomba lo pide; eje de alta resistencia si la bomba lo lleva
    (criterio del proyecto: el catálogo no publica la potencia del eje de cada
    protector); con más de 30° de desviación, sin cámaras solo de laberinto; si
    queda más de uno, el más corto y, si empatan, el primero de la tabla.
    """
    raw = next(b for b in catalog_manager.get_all_pumps() if b.model == modelo)
    c4 = TK + "Sección 5.3.4"
    td = raw.tandem or {}
    umbral, tope = td.get("etapas_cojinete_hl"), td.get("etapas_max_tabla")
    if umbral is not None and etapas >= umbral:
        hl, porque = True, f"{etapas} ≥ {umbral} etapas (nota de la tabla de tándem)"
    elif tope is not None and etapas > tope:
        hl, porque = True, f"{etapas} etapas, más que las {tope} de la tabla de tándem"
    else:
        hl, porque = False, f"{etapas} etapas, sin nota de cojinete high-load en la tabla de tándem"
    cita_hl = td.get("fuente", "tabla de tándem del catálogo")
    if not (umbral is not None and etapas >= umbral):
        cita_hl += "; criterio del proyecto"
    hss = eje_bomba == "alta resistencia"
    sellos = [x for x in catalog_manager.get_all_seals()
              if x["manufacturer"] == raw.manufacturer and x["series"] == raw.series]
    if not sellos:
        raise ValueError(f"No hay protectores {raw.manufacturer} serie {raw.series} en el catálogo.")
    cand = [x for x in sellos if (not hl or x.get("high_load_bearing"))
            and (not hss or x.get("high_strength_shaft"))
            and (desviacion <= 30 or x.get("type") != "labyrinth")]
    if not cand:
        raise ValueError(f"Ningún protector {raw.manufacturer} serie {raw.series} cumple cojinete "
                         f"{'high-load' if hl else 'base'} y eje {'HSS' if hss else 'base'}.")
    el = min(cand, key=lambda x: (x.get("length_ft") or 1e9, sellos.index(x)))
    nombre = el["model"].split(f"-{raw.series}-", 1)[-1]
    fuente = el.get("fuente", "catálogo de protectores")
    elast = [e for e in catalog_manager.get_all_elastomers() if e["temp_limit_f"] >= t_fondo]
    if not elast:
        raise ValueError(f"Ningún elastómero del catálogo admite {t_fondo:.1f} °F.")
    e = min(elast, key=lambda e: e["temp_limit_f"])
    if raw.manufacturer == "Centrilift":
        raise NotImplementedError("El consumo del protector Centrilift no está cargado: "
                                  "Centrilift no lo incluye en la curva de la bomba (Takács pág. 253).")
    motores = ", ".join(el.get("compatible_motor_series") or [])
    pasos = [
        Paso("Serie del protector", "misma serie que la bomba; atornilla a motores de la serie indicada",
             f"bomba {raw.manufacturer} {modelo} serie {raw.series} → protector serie {raw.series}, "
             f"motor serie {motores}", float(raw.series) if raw.series.isdigit() else 0.0, "serie",
             c4 + " (pág. 251); " + fuente),
        Paso("Cojinete de empuje: " + ("high-load (HL)" if hl else "base"),
             "etapas ≥ etapas marcadas en la tabla de tándem", porque, float(etapas), "etapas", cita_hl),
        Paso("Eje del protector: " + ("alta resistencia (HSS)" if hss else "base"),
             "mismo eje que la bomba (paso 8)", f"eje de la bomba: {eje_bomba}", None, "",
             TK + "ec. 5.17 (pág. 252); criterio del proyecto"),
        Paso("Tipo de cámara", "desviación > 30° → bolsa; si no, se admite laberinto",
             f"desviación máxima {desviacion:.0f}°", desviacion, "°", c4 + " (pág. 252)"),
        Paso(f"Protector: {nombre}", "cumple serie, cojinete, eje y tipo; el más corto",
             f"{TIPO_SELLO.get(el.get('type'), el.get('type'))} · {el.get('length_ft')} ft · "
             f"{el.get('weight_lbs')} lb · P/N {el.get('part_number')}", el.get("length_ft") or 0.0, "ft",
             fuente + "; el más corto: criterio del proyecto"),
        Paso(f"Elastómero: {e['name']}", "límite de temperatura ≥ T de fondo; el de menor límite",
             f"{t_fondo:.1f} °F ≤ {e['temp_limit_f']} °F", float(e["temp_limit_f"]), "°F",
             "REDA_ESP_Catalog.pdf, pág. 404"),
        Paso("Consumo de potencia del protector", "incluido en la potencia de la curva de la bomba",
             f"{raw.manufacturer}: 0 hp adicionales", 0.0, "hp", c4 + " (pág. 253)"),
    ]
    return {"protector": nombre, "modelo_sello": el["model"], "tipo": el.get("type"), "hl": hl, "hss": hss,
            "largo_ft": el.get("length_ft"), "peso_lb": el.get("weight_lbs"), "part_number": el.get("part_number"),
            "serie_motor": el.get("compatible_motor_series") or [], "elastomero": e["name"],
            "hp_protector": 0.0}, pasos


# --------------------------------------------------------------------------
# Paso 10 — Motor
# --------------------------------------------------------------------------
HP_SEPARADOR = 1.5   # criterio del proyecto: consumo promedio de un separador de gas
V_ANULAR_MIN, V_ANULAR_MAX = 1.0, 12.0   # Takács Sección 5.3.5 (pág. 253)
ARREGLOS_TANDEM = {1: ("S",), 2: ("UT", "LT"), 3: ("UT", "CT", "LT")}


def _familia(modelo: str, serie: str) -> str:
    import re
    return re.sub(r"-\d+(\.\d+)?HP-\d+V$", "", modelo).replace(f"REDA-{serie}-", "")


def _tiene(tipos: list[str], necesarios: tuple[str, ...]) -> bool:
    base = {t.replace("-GRB", "") for t in tipos}
    return all(t in base for t in necesarios)


def paso10_motor(hp_bomba: float, hp_protector: float, con_separador: bool, series_motor: list[str],
                 fabricante: str, frecuencia_hz: float, casing_id: float, q_liquido: float,
                 catalog_manager) -> tuple[dict, list[Paso]]:
    """Elige el motor (Takács Sección 5.3.5, págs. 253 a 255).

    Potencia del sistema = bomba + protector + separador (ec. 5.40). Se buscan
    motores del fabricante y de la serie que atornilla al protector (paso 9), en
    todas las familias del catálogo salvo las que traen protector integrado
    (Maximus ProMotor) o conexión MaxJoint (Maximus); solo, o en tándem de 2 o 3
    motores iguales con los tipos UT, CT y LT publicados (Takács pág. 79). Gana
    la menor potencia de placa que cubre al sistema; si empatan, el mayor
    voltaje (Takács pág. 255); después, menos motores y menor largo.
    """
    rel = frecuencia_hz / 60.0
    hp_sep = HP_SEPARADOR if con_separador else 0.0
    bhp = hp_bomba + hp_protector + hp_sep
    cand = []
    for m in catalog_manager.get_all_motors():
        if m.get("manufacturer") != fabricante or str(m.get("series")) not in series_motor:
            continue
        fam = _familia(m["model"], str(m["series"]))
        if "MAXIMUS" in fam or not m.get("tipos"):
            continue
        if not m.get("od_inches") or m["od_inches"] >= casing_id:
            continue
        for n, arreglo in ARREGLOS_TANDEM.items():
            if not _tiene(m["tipos"], arreglo):
                continue
            hp_n = n * m["hp_rating"] * rel
            if hp_n >= bhp:
                cand.append((round(hp_n, 6), -n * m["voltage"], n, n * (m.get("length_ft") or 0), m, arreglo))
    if not cand:
        raise ValueError(f"Ningún motor {fabricante} serie {', '.join(series_motor)} (solo o en tándem de "
                         f"hasta 3) cubre {bhp:.2f} hp a {frecuencia_hz:.0f} Hz.")
    cand.sort(key=lambda c: c[:4])
    hp_n, _, n, largo, m, arreglo = cand[0]
    hp_1 = m["hp_rating"] * rel
    v_1 = m["voltage"] * rel
    i = m["amperage"]   # corriente de placa, como el camino convencional (Brown 4.5325)
    od = m["od_inches"]
    v_an = 0.0119 * q_liquido / (casing_id ** 2 - od ** 2)
    pag = m.get("_source", "").split(",")[0].replace("p.", "pág. ")
    c5 = TK + "Sección 5.3.5"
    pasos = [
        Paso("Potencia del separador", "1,5 hp por separador" if con_separador else "sin separador",
             "1 × 1,5" if con_separador else "0", hp_sep, "hp", "criterio del proyecto" if con_separador else ""),
        Paso("Potencia del sistema", "BHP = BHP_bomba + BHP_protector + BHP_separador",
             f"{hp_bomba:.2f} + {hp_protector:.2f} + {hp_sep:.2f}", bhp, "hp", TK + "ec. 5.40 (pág. 276)"),
        Paso("Serie del motor", "la que atornilla al protector (paso 9) y entra en el casing",
             f"serie {m['series']}: OD {od} in < ID casing {casing_id} in", od, "in", c5 + " (pág. 253)"),
        Paso("Potencia de placa de un motor", "HP_motor = HP_60 · f / 60",
             f"{m['hp_rating']:g} × {frecuencia_hz:.0f} / 60", hp_1, "hp", TK + "ec. 5.19 (pág. 254); " + pag),
        Paso(f"Motor: {n} × {_familia(m['model'], str(m['series']))} {m['hp_rating']:g} hp / {m['voltage']:g} V "
             f"({' + '.join(arreglo)})",
             "menor potencia de placa ≥ BHP; si empatan, mayor voltaje",
             f"{n} × {hp_1:.2f} = {hp_n:.2f} hp ≥ {bhp:.2f} hp", hp_n, "hp",
             c5 + " (págs. 253 y 255); tándem: " + TK + "Sección 3.3.1.1 (pág. 79); " + pag),
        Paso("Voltaje de placa", "U = n · U_60 · f / 60", f"{n} × {m['voltage']:g} × {frecuencia_hz:.0f} / 60",
             n * v_1, "V", TK + "ec. 5.20 (pág. 254); tándem: Sección 3.3.1.1 (pág. 79)"),
        Paso("Corriente de placa", "I_placa (igual en tándem)", f"{m['amperage']:g}", m["amperage"], "A",
             pag + "; tándem: " + TK + "Sección 3.3.1.1 (pág. 79)"),
        Paso("Largo del motor", "n · largo", f"{n} × {m.get('length_ft')}", largo, "ft", pag),
        Paso("Velocidad del fluido junto al motor", "v = 0,0119 · q_líquido / (ID_casing² − OD_motor²)",
             f"0,0119 × {q_liquido:.2f} / ({casing_id}² − {od}²)", v_an, "ft/s", TK + "ec. 5.18 (pág. 253)"),
        Paso("Rango de velocidad", "1 ft/s ≤ v ≤ 12 ft/s", f"{v_an:.2f} ft/s", v_an, "ft/s", c5 + " (pág. 253)"),
    ]
    if not (V_ANULAR_MIN <= v_an <= V_ANULAR_MAX):
        raise ValueError(f"Velocidad del fluido junto al motor {v_an:.2f} ft/s, fuera del rango de "
                         f"1 a 12 ft/s (Takács ec. 5.18, pág. 253): diseño descartado.")
    return {"motor": m["model"], "n": n, "arreglo": list(arreglo), "hp_placa": hp_n, "voltaje": n * v_1,
            "corriente_placa": m["amperage"], "corriente": i, "bhp_sistema": bhp, "hp_separador": hp_sep,
            "largo_ft": largo, "od_in": od, "v_anular": v_an}, pasos


# --------------------------------------------------------------------------
# Paso 11 — Cable de potencia y extensión del motor (MLE)
# --------------------------------------------------------------------------
# Cable: el mismo método que el camino convencional (Brown Vol. 2b, Secciones
# 4.5325 y 4.5326), con las mismas funciones de ``bes.core.electrical``.


def paso11_cable(d_bomba: float, corriente: float, u_placa: float, t_fondo: float,
                 largo_bomba: float, largo_protector: float, casing_id: float, motor_od: float,
                 catalog_manager) -> tuple[dict, list[Paso]]:
    """Cable y caída de tensión, igual que el camino convencional (Brown 4.5325 y 4.5326)."""
    from bes.core.electrical import select_cable
    cab = select_cable(motor_amps=corriente, pump_depth=d_bomba, bottom_temp=t_fondo,
                       casing_id=casing_id, motor_od=motor_od, catalog_manager=catalog_manager,
                       motor_voltage=u_placa, fitment_declarado=True)
    largo = cab["length_ft"]
    v_a = cab["voltage_drop_per_1000ft"] / corriente if corriente > 0 else 0.0
    caida = cab["voltage_drop_per_1000ft"] * largo / 1000.0
    mle = largo_bomba + largo_protector + 6.0
    c5 = B2 + "Sección 4.5325"
    pasos = [
        Paso("Largo del cable", "L = D_bomba + 100 ft", f"{d_bomba:.2f} + 100", largo, "ft", c5 + " (pág. 64)"),
        Paso(f"Cable: {cab['manufacturer']} {cab['cable_type']} {cab['cable_size']} AWG {cab['conductor']}",
             "ampacidad ≥ 1,25 · I; temperatura ≥ T_fondo + 25 °F; cobre; el más chico que da ≤ 30 V/1000 ft",
             f"{cab['max_amps']:g} A ≥ 1,25 × {corriente:.2f} A", cab["max_amps"], "A",
             c5 + " y Tabla 4.52 (pág. 64); 1,25 y +25 °F: criterio del proyecto"),
        Paso("Caída por amper cada 1000 ft a la temperatura de fondo", "(ΔV / A·1000 ft) de la Fig. 4.54",
             f"a {t_fondo:.1f} °F", v_a, "V/(A·1000 ft)", c5 + ", Fig. 4.54 (pág. 64)"),
        Paso("Caída de tensión en el cable", "ΔV = (ΔV / A·1000 ft) · I · L / 1000",
             f"{v_a:.4f} × {corriente:.2f} × {largo:.1f} / 1000", caida, "V", c5 + ", Fig. 4.54 (pág. 64)"),
        Paso("Caída cada 1000 ft", "ΔV / L · 1000 ≤ 30 V", f"{caida:.2f} / {largo:.1f} × 1000",
             cab["voltage_drop_per_1000ft"], "V/1000 ft", c5 + " (pág. 64)"),
        Paso("Largo de la extensión del motor (MLE)", "L_MLE = L_bomba + L_protector + 6 ft",
             f"{largo_bomba:.1f} + {largo_protector:.1f} + 6", mle, "ft", TK + "Sección 5.3.8.1 (pág. 260)"),
    ]
    return {"largo_ft": largo, "calibre": cab["cable_size"], "tipo": cab["cable_type"],
            "fabricante": cab["manufacturer"], "conductor": cab["conductor"], "caida": caida,
            "caida_1000": cab["voltage_drop_per_1000ft"], "mle_ft": mle}, pasos


# --------------------------------------------------------------------------
# Paso 12 — Tablero y transformador
# --------------------------------------------------------------------------
def paso12_superficie(u_placa: float, caida: float, corriente: float, fabricante: str, usa_vsd: bool,
                      catalog_manager) -> tuple[dict, list[Paso]]:
    """Tensión y potencia en superficie (Brown 4.5325), tablero y transformador del catálogo."""
    from bes.core.electrical import calculate_kva, calculate_surface_voltage
    u_sup = calculate_surface_voltage(u_placa, caida)
    kva = calculate_kva(u_sup, corriente)
    tipo = "vsd" if usa_vsd else "switchboard"
    tableros = [c for c in catalog_manager.get_all_controllers() if c.get("type") == tipo
                and (c.get("max_kva") or 0) >= kva
                and (usa_vsd or ((c.get("max_voltage") or 0) >= u_sup and (c.get("max_amps") or 0) >= corriente))]
    propios = [c for c in tableros if c.get("manufacturer") == fabricante]
    tableros = propios or tableros
    if not tableros:
        raise ValueError(f"Ningún {'variador' if usa_vsd else 'tablero'} del catálogo cubre {u_sup:.0f} V, "
                         f"{corriente:.1f} A y {kva:.1f} kVA.")
    tab = min(tableros, key=lambda c: (c["max_kva"], c.get("max_voltage") or 0))
    trafos = []
    for t in catalog_manager.get_all_transformers():
        for con, lo, hi in (("delta", "secondary_delta_min", "secondary_delta_max"),
                            ("estrella", "secondary_wye_min", "secondary_wye_max")):
            if t["kva"] >= kva and t.get(lo) is not None and t[lo] <= u_sup <= t[hi]:
                trafos.append((t["kva"], t, con))
                break
    if not trafos:
        raise ValueError(f"Ningún transformador del catálogo da {u_sup:.0f} V con {kva:.1f} kVA.")
    kva_t, tr, con = min(trafos, key=lambda x: x[0])
    import re
    m_f = re.match(r"(.*?pág\. \d+)", tab.get("_source", ""))
    fuente_tab = m_f.group(1) if m_f else tab.get("_source", "")
    c7 = B2 + "Sección 4.5326"
    pasos = [
        Paso("Tensión en superficie", "V_sup = (V_motor + ΔV) · 1,025",
             f"({u_placa:.0f} + {caida:.2f}) × 1,025", u_sup, "V", B2 + "Sección 4.5325 (pág. 65)"),
        Paso("Potencia en superficie", "kVA = V_sup · I · 1,732 / 1000", f"{u_sup:.1f} × {corriente:.2f} × 1,732 / 1000",
             kva, "kVA", B2 + "Sección 4.5326, ec. 4.51 (pág. 65)"),
        Paso(f"{'Variador' if usa_vsd else 'Tablero'}: {tab['model']}",
             "kVA ≥ P" + ("" if usa_vsd else "; tensión ≥ U_sup; corriente ≥ I") + "; el más chico",
             f"{tab.get('max_voltage'):g} V · {tab.get('max_amps'):g} A · {tab['max_kva']:g} kVA",
             tab["max_kva"], "kVA", c7 + " (pág. 65); " + fuente_tab + "; el más chico: criterio del proyecto"),
        Paso(f"Transformador: {kva_t:g} kVA, secundario en {con}",
             "kVA ≥ P; U_sup dentro del rango del secundario; el más chico",
             f"{tr['primary_volts']} V primario · secundario {tr['secondary_delta_min']}-{tr['secondary_delta_max']} V "
             f"delta / {tr['secondary_wye_min']}-{tr['secondary_wye_max']} V estrella · P/N {tr.get('part_number')}",
             float(kva_t), "kVA", c7 + " (pág. 65); Transformers.pdf, «Variable Speed Drive Transformer – 3 Phase»"),
    ]
    return {"u_superficie": u_sup, "kva": kva, "tablero": tab["model"], "transformador_kva": kva_t,
            "transformador_pn": tr.get("part_number"), "conexion": con}, pasos


def _aparejo(cand: dict, pip, pd, t_adm, q_objetivo, wc, gb, api, gas_sg, water_sg, catalog_manager,
             incremento_psi, frecuencia_hz, t_fondo, desviacion_max, eta_sep, casing_id, mez_adm, d_bomba,
             gor, usa_vsd) -> tuple[dict, list[tuple[str, list[Paso]]]]:
    """Pasos 7 a 12 para una bomba candidata. Levanta ValueError si el aparejo no se completa."""
    b: list[tuple[str, list[Paso]]] = []
    inc, p7 = paso7_incrementos(pip, pd, t_adm, q_objetivo, wc, gb, api, gas_sg, water_sg,
                                cand["bomba"], catalog_manager, incremento_psi)
    b.append((f"7. Incrementos de presión de {incremento_psi:.0f} psi → etapas y potencia", p7))
    mec, p8 = paso8_eje_carcasas(cand["modelo"], inc["etapas"], inc["hp"],
                                 max(pt["grad"] for pt in inc["puntos"]), frecuencia_hz, catalog_manager)
    b.append(("8. Eje, presión de carcasa y arreglo de carcasas", p8))
    pro, p9 = paso9_protector(cand["modelo"], inc["etapas"], mec["eje"], t_fondo, desviacion_max,
                              catalog_manager)
    b.append(("9. Protector (sección sellante)", p9))
    mot, p10 = paso10_motor(inc["hp"], pro["hp_protector"], eta_sep > 0, pro["serie_motor"],
                            cand["fabricante"], frecuencia_hz, casing_id, mez_adm["vo"] + mez_adm["vw"],
                            catalog_manager)
    b.append(("10. Motor", p10))
    cab, p11 = paso11_cable(d_bomba, mot["corriente"], mot["voltaje"], t_fondo,
                            mec["largo_ft"], pro["largo_ft"] or 0.0, casing_id, mot["od_in"],
                            catalog_manager)
    b.append(("11. Cable de potencia y extensión del motor", p11))
    sup, p12 = paso12_superficie(mot["voltaje"], cab["caida"], mot["corriente"], cand["fabricante"],
                                 usa_vsd, catalog_manager)
    b.append(("12. Tablero y transformador", p12))
    return {"incrementos": inc, "mecanica": mec, "protector": pro, "motor": mot, "cable": cab,
            "superficie": sup}, b


# --------------------------------------------------------------------------
# Recorrido de los pasos aprobados
# --------------------------------------------------------------------------
def calcular(pr: float, pb: float, pwf_ensayo: float, q_ensayo: float, q_objetivo: float,
             api: float, wc: float, gor: float, gas_sg: float, water_sg: float,
             t_boca: float, t_fondo: float, d_pwf: float, d_bomba: float,
             p_boca: float | None = None, d_tubing_in: float | None = None,
             eta_sep: float = ETA_SEPARADOR, casing_id: float | None = None,
             frecuencia_hz: float | None = None, catalog_manager=None,
             incremento_psi: float = INCREMENTO_PSI, desviacion_max: float = 0.0,
             usa_vsd: bool = False
             ) -> tuple[dict, list[tuple[str, list[Paso]]]]:
    """Corre los pasos aprobados en orden y devuelve (resultados, pasos por bloque)."""
    bloques: list[tuple[str, list[Paso]]] = []
    pwf, p1 = paso1_ipr_vogel(pr, pb, pwf_ensayo, q_ensayo, q_objetivo)
    bloques.append(("1. IPR: presión de fondo fluyente", p1))
    pvt_f, p2a = paso2a_pvt(pwf, t_fondo, api, gas_sg, water_sg, gor)
    bloques.append((f"2a. PVT en el fondo ({pwf:.2f} psig y {t_fondo:.1f} °F)", p2a))
    mez_f, p2bc = paso2bc_mezcla(q_objetivo, wc, gor, gas_sg, water_sg, pvt_f)
    bloques.append(("2b-c. Volúmenes, masa y gravedad específica de la mezcla en el fondo", p2bc))
    pip, p3 = paso3_pip(pwf, mez_f["sg"], d_pwf, d_bomba)
    bloques.append(("3. Presión en la admisión (PIP)", p3))
    if pip <= 0:
        nd = d_pwf - pwf / (0.433 * mez_f["sg"])
        raise ValueError(
            f"La PIP da {pip:.1f} psig: la bomba a {d_bomba:.0f} ft queda por encima del nivel dinámico "
            f"({nd:.0f} ft) y no tendría fluido en la succión. Hay que bajarla o reducir el caudal.")
    t_adm, pt = temperatura_lineal(t_boca, t_fondo, d_pwf, d_bomba)
    pvt_a, p4a = paso2a_pvt(pip, t_adm, api, gas_sg, water_sg, gor)
    mez_a, p4b = paso2bc_mezcla(q_objetivo, wc, gor, gas_sg, water_sg, pvt_a)
    suc, p4c = paso4_gor_succion(mez_a, pvt_a, eta_sep)
    bloques.append(("4a. Temperatura en la admisión", [pt]))
    bloques.append((f"4b. PVT y volúmenes en la admisión ({pip:.2f} psig y {t_adm:.2f} °F)", p4a + p4b))
    bloques.append((f"4c. Separador (η = {eta_sep*100:.0f} %) y GOR en la succión", p4c))
    res = {"pwf": pwf, "pvt_fondo": pvt_f, "mezcla_fondo": mez_f, "pip": pip, "t_adm": t_adm,
           "pvt_adm": pvt_a, "mezcla_adm": mez_a, "succion": suc}
    if p_boca is not None and d_tubing_in is not None:
        des, p5 = paso5_descarga(p_boca, t_boca, t_adm, d_bomba, q_objetivo, wc, suc["gor_bomba"],
                                 api, gas_sg, water_sg, d_tubing_in)
        bloques.append((f"5. Presión de descarga (recorrido por el tubing en {len(des['tramos'])} tramos)", p5))
        res["descarga"] = des
        if casing_id is not None and frecuencia_hz is not None and catalog_manager is not None:
            gb = suc["gor_bomba"]; pd = des["p_descarga"]
            if pd <= pip:
                raise ValueError(
                    f"La presión de descarga ({pd:.1f} psig) no supera la PIP ({pip:.1f} psig): con "
                    f"{suc['f_bomba'] * 100:.1f} % de gas libre en la bomba y GOR {gb:.0f} scf/STB, el gas "
                    f"aliviana la columna del tubing y la bomba no tiene salto de presión que dar.")
            pvt_d, _ = paso2a_pvt(pd, t_adm, api, gas_sg, water_sg, gb)
            mez_d, _ = paso2bc_mezcla(q_objetivo, wc, gb, gas_sg, water_sg, pvt_d)
            sel, p6 = paso6_seleccion(suc["v_bomba"], mez_d["v_total"], casing_id, frecuencia_hz,
                                      catalog_manager)
            descartes: list[tuple[dict, str]] = []
            for cand in sel["candidatas"]:
                try:
                    r7, b7 = _aparejo(cand, pip, pd, t_adm, q_objetivo, wc, gb, api, gas_sg, water_sg,
                                      catalog_manager, incremento_psi, frecuencia_hz, t_fondo, desviacion_max,
                                      eta_sep, casing_id, res["mezcla_adm"], d_bomba, gor, usa_vsd)
                    break
                except ValueError as exc:
                    descartes.append((cand, str(exc)))
            else:
                raise ValueError("Ninguna bomba candidata completa el aparejo: " + " | ".join(
                    f"{c['fabricante']} {c['modelo']}: {m}" for c, m in descartes))
            for c, m in descartes:
                p6.append(Paso(f"Descartada: {c['fabricante']} {c['modelo']}",
                               "el aparejo no se completa en los pasos 7 a 12", m, None, "", ""))
            if descartes:
                p6.append(Paso(f"Bomba usada: {cand['fabricante']} {cand['modelo']}",
                               "la siguiente en el orden de mayor eficiencia y mayor diámetro",
                               f"OD {cand['od']} in, η {cand['eficiencia']*100:.1f} %", cand["eficiencia"] * 100,
                               "%", ""))
            sel = {**sel, "bomba": cand["bomba"], "modelo": cand["modelo"], "fabricante": cand["fabricante"],
                   "od": cand["od"], "descartadas": [(c["modelo"], m) for c, m in descartes]}
            bloques.append((f"6. Selección de la bomba ({frecuencia_hz:.0f} Hz)", p6))
            bloques.extend(b7)
            res["seleccion"] = sel
            res.update(r7)
    return res, bloques


def tabla_evolucion(res: dict, q_liq: float, wc: float, gor: float, api: float, gas_sg: float,
                    water_sg: float, t_fondo: float, t_boca: float, cada: int = 5) -> list[dict]:
    """Evolución del fluido en el pozo, como la Tab. 6 de la tesis: fondo,
    admisión, cada presión dentro de la bomba y el tubing hasta la superficie."""
    def fila(p, t, g, zona, com=""):
        pvt, _ = paso2a_pvt(p, t, api, gas_sg, water_sg, g)
        m, _ = paso2bc_mezcla(q_liq, wc, g, gas_sg, water_sg, pvt)
        return {"zona": zona, "comentario": com, "p": p, "t": t, "gor": g, "z": pvt["z"], "rs": pvt["rs"],
                "bg_mscf": pvt["bg"] * 1000, "bo": pvt["bo"], "bw": pvt["bw"], "vg": m["vg"],
                "v_total": m["v_total"], "sg": m["sg"]}
    filas = [fila(res["pwf"], t_fondo, gor, "fondo", "Fondo de pozo"),
             fila(res["pip"], res["t_adm"], gor, "admision", "Admisión (antes del separador)")]
    inc = res.get("incrementos")
    if inc:
        for i, pt in enumerate(inc["puntos"]):
            com = "Entrada a la bomba" if i == 0 else ("Descarga de la bomba" if i == len(inc["puntos"]) - 1 else "")
            filas.append(fila(pt["p"], pt["t"], pt["gor"], "bomba", com))
    des = res.get("descarga")
    if des:
        trs = des["tramos"]
        for k in range(len(trs) - 1, -1, -cada):
            t = trs[k]
            filas.append(fila(t["p0"], t["t_m"], res["succion"]["gor_bomba"], "tubing",
                              "Boca de pozo" if k == 0 else ""))
        if trs and (len(trs) - 1) % cada != 0:
            filas.append(fila(trs[0]["p0"], t_boca, res["succion"]["gor_bomba"], "tubing", "Boca de pozo"))
    return filas
