# -*- coding: utf-8 -*-
"""Tabla de evolución del fluido en el pozo para un diseño con gas.

Usa las mismas funciones y entradas que la escalera de incrementos de la app:
en la bomba el fluido es el del tubing (GOR reducido por el separador) a la
temperatura de reservorio; el control final verifica que el caudal total de
cada escalón coincida con el de la escalera.
"""
from __future__ import annotations

import dataclasses


def tabla_pvt(fila: dict) -> list[dict]:
    from bes.core.gas_handling import _mixture_volumes_and_density, gor_en_el_tubing
    from bes.core.multiphase import _make_fluid, pressure_traverse
    from bes.core.pvt import gas_z_factor

    P = fila["pozo"]; F = P["fluid"]; W = P["well"]; R = P["reservoir"]; S = P["surface"]
    s = fila["summary"]; inc = fila["inc"]; q = P["objectives"]["target_flow_rate"]
    wc = F["water_cut"]; pip = s["p_intake"]; Tb = s["pump_intake_temp_f"]; Tres = R["reservoir_temp"]
    base = _make_fluid(F["oil_api"], wc, F["gor"], F["gas_sg"], F["water_sg"], pip)
    base = dataclasses.replace(base, bubble_point_pressure=F["bubble_point_pressure"], gor=F["gor"])
    tub = dataclasses.replace(base, gor=gor_en_el_tubing(base, pip, Tb, s["gip"]))
    eta = (fila.get("feas") or {}).get("separator_efficiency")

    def fila_(p, t, fl, zona, com=""):
        p = max(p, 14.7)   # mismo piso que el recorrido de presión de la app
        m = _mixture_volumes_and_density(p, t, fl, wc, 1.0)
        return {"P": p, "T": t, "GOR": fl.gor, "Z": gas_z_factor(p, t, fl.gas_sg), "Rs": m["rs"],
                "Bg": m["bg"] * 1000.0, "Bo": m["bo"], "Vg": m["v_gas"] * q, "Vt": m["v_total"] * q,
                "SG": m["sg_mix"], "zona": zona, "com": com}

    pwf = fila.get("pwf")
    filas = []
    if pwf is not None:
        filas.append(fila_(pwf, Tres, base, "anular", "Fondo de pozo"))
    filas.append(fila_(pip, Tres, base, "anular", "Intake de la bomba"))
    com = "Entrada a la bomba" + (f" (separador η = {eta*100:.0f} %)" if eta else "")
    filas.append(fila_(pip, Tres, tub, "bomba", com))
    for x in inc[1:]:
        filas.append(fila_(x["p_lo"], Tres, tub, "bomba"))
    filas.append(fila_(s["p_discharge"], Tres, tub, "bomba", "Descarga de la bomba"))
    depth = s["pump_setting_depth"]; Twh = W["wellhead_temp"]
    d, p = pressure_traverse(q, tub, W["tubing_id"], 0.0, depth, S["wellhead_pressure_required"],
                             Twh, Tb, 50)
    for i in range(len(d) - 6, 0, -5):
        filas.append(fila_(float(p[i]), Twh + d[i] / depth * (Tb - Twh), tub, "tubing"))
    filas.append(fila_(S["wellhead_pressure_required"], Twh, tub, "tubing", "Superficie"))
    return filas


def _fluido(fila: dict, gor: float | None = None):
    from bes.core.multiphase import _make_fluid
    F = fila["pozo"]["fluid"]
    fl = _make_fluid(F["oil_api"], F["water_cut"], F["gor"], F["gas_sg"], F["water_sg"], 1000.0)
    return dataclasses.replace(fl, bubble_point_pressure=F["bubble_point_pressure"],
                               gor=F["gor"] if gor is None else gor)


def recorrido(fila: dict, fl, pipe_id: float, d0: float, d1: float, p0: float, t0: float, t1: float,
              n: int) -> list[dict]:
    """Mismo lazo que ``bes.core.multiphase.pressure_traverse`` (3 pasadas por
    tramo, PVT en el punto medio), guardando el detalle de cada tramo."""
    from bes.core.multiphase import gradiente_del_recorrido
    q = fila["pozo"]["objectives"]["target_flow_rate"]
    dz = abs(d1 - d0) / n; sube = d1 < d0; p = p0; filas = []
    for i in range(n):
        za = d0 + (d1 - d0) * i / n; zb = d0 + (d1 - d0) * (i + 1) / n
        zm = 0.5 * (za + zb); tm = t0 + (zm - d0) / (d1 - d0 + 1e-12) * (t1 - t0)
        pm = p
        for _ in range(3):
            g, dg = gradiente_del_recorrido(q_liq=q, fluid=fl, p=max(pm, 14.7), t=tm, pipe_id=pipe_id, angle=90.0)
            p_sig = p - g * dz if sube else p + g * dz
            pm = 0.5 * (p + max(p_sig, 14.7))
        p_sig = max(p_sig, 14.7)
        filas.append({"z0": za, "z1": zb, "p0": p, "pm": pm, "tm": tm, "rho": dg.get("mixture_density"),
                      "vm": dg.get("mixture_velocity"), "lam": dg.get("liquid_holdup_noslip"),
                      "f": dg.get("friction_factor"), "grav": dg.get("gravity"), "fric": dg.get("friction"),
                      "grad": g, "dp": g * dz, "p1": p_sig, "metodo": dg.get("metodo", "")})
        p = p_sig
    return filas


def recorrido_anular(fila: dict, pwf: float) -> list[dict]:
    """Punzados → admisión por el casing, 20 tramos (``calculate_pip``)."""
    from bes.core.multiphase import PIP_TRAVERSE_SEGMENTS
    P = fila["pozo"]; W = P["well"]; R = P["reservoir"]
    D = fila["summary"]["pump_setting_depth"]
    t = lambda z: W["wellhead_temp"] + z / max(W["total_depth"], 1.0) * (R["reservoir_temp"] - W["wellhead_temp"])  # noqa: E731
    return recorrido(fila, _fluido(fila), W["casing_id"], W["perforations_bottom"], D, pwf,
                     t(W["perforations_bottom"]), t(D), PIP_TRAVERSE_SEGMENTS)


def recorrido_tubing(fila: dict) -> tuple[float, float, list[dict]]:
    """Boca → descarga por el tubing, 50 tramos, con el GOR del tubing."""
    from bes.core.gas_handling import gor_en_el_tubing
    P = fila["pozo"]; W = P["well"]; S = P["surface"]; s = fila["summary"]
    base = _fluido(fila)
    gor_t = gor_en_el_tubing(base, s["p_intake"], s["pump_intake_temp_f"], s["gip"])
    rows = recorrido(fila, _fluido(fila, gor_t), W["tubing_id"], 0.0, s["pump_setting_depth"],
                     S["wellhead_pressure_required"], W["wellhead_temp"], s["pump_intake_temp_f"], 50)
    return gor_t, base.gor, rows


def tabla_pvt_fondo(fila: dict, pwf: float) -> dict:
    """PVT y volumen por STB de líquido en el fondo (Pwf, T de reservorio), con todo el gas."""
    from bes.core.gas_handling import _mixture_volumes_and_density
    R = fila["pozo"]["reservoir"]
    return _mixture_volumes_and_density(max(pwf, 14.7), R["reservoir_temp"], _fluido(fila),
                                        fila["pozo"]["fluid"]["water_cut"], 1.0)
