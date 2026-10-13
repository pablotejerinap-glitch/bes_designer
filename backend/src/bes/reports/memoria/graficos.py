# -*- coding: utf-8 -*-
"""Gráficos de la memoria de cálculo (PNG embebidos como data URI)."""
from __future__ import annotations

import base64
import io

AZ = "#1F3864"; RO = "#C00000"; VE = "#2E7D32"; NA = "#E36C09"


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.grid": True,
                         "grid.alpha": .3, "figure.dpi": 150})
    return plt


def _uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    import matplotlib.pyplot as plt
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def ipr(fila: dict, curva, pwf_obj: float, etiqueta: str, rotulo: str) -> str:
    """``curva(pwf) -> q``. ``rotulo`` identifica el caso en el título."""
    plt = _plt()
    R = fila["pozo"]["reservoir"]; qt = fila["pozo"]["objectives"]["target_flow_rate"]
    Pr = R["static_pressure"]
    ps = [Pr * i / 200 for i in range(201)]; qs = [curva(p) for p in ps]
    fig, ax = plt.subplots(figsize=(5.1, 3.4))
    ax.plot(qs, ps, color=AZ, lw=2, label=f"IPR ({etiqueta})")
    ax.plot([qt], [pwf_obj], "o", color=RO, ms=8, zorder=5)
    ax.annotate("diseño\n%.0f b/d @ %.0f psi" % (qt, pwf_obj), (qt, pwf_obj), textcoords="offset points",
                xytext=(-80, 16), color=RO, fontsize=8, fontweight="bold")
    if R.get("test_rate") and R.get("test_pwf") is not None:
        ax.plot([R["test_rate"]], [R["test_pwf"]], "s", color=VE, ms=7, zorder=5)
        ax.annotate("ensayo\n%.0f b/d @ %.0f psi" % (R["test_rate"], R["test_pwf"]),
                    (R["test_rate"], R["test_pwf"]), textcoords="offset points", xytext=(8, -30),
                    color=VE, fontsize=8)
    ax.set_xlabel("caudal  q  [STB/d]"); ax.set_ylabel("presión de fondo  Pwf  [psi]")
    ax.set_title(f"{rotulo} — curva IPR", color=AZ, fontweight="bold")
    ax.set_xlim(0, max(qs) * 1.12); ax.set_ylim(0, Pr * 1.08); ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    return _uri(fig)


def bomba(fila: dict, cm, rotulo: str) -> str:
    from bes.core.affinity import pump_at_frequency
    plt = _plt()
    pu = fila["pump"]; P = fila["pozo"]
    hz = P["surface"]["frequency"]
    base = next(p for p in cm.get_all_pumps() if p.model == pu["pump_model"])
    pump = pump_at_frequency(base, hz)
    fl = [pt.flow_rate for pt in pump.points]; hd = [pt.head_per_stage for pt in pump.points]
    ef = [pt.efficiency * 100 for pt in pump.points]
    qop = fila["summary"]["q_mix_intake_bpd"] if fila["gas"] else P["objectives"]["target_flow_rate"]
    fig, ax = plt.subplots(figsize=(5.1, 3.4)); ax2 = ax.twinx()
    ax.plot(fl, hd, color=AZ, lw=2); ax2.plot(fl, ef, color=VE, lw=1.4, ls="--")
    ax.axvspan(pump.min_flow, pump.max_flow, color=AZ, alpha=.07)
    ax.axvline(pump.bep_flow, color="#888", ls=":", lw=1)
    ax.annotate("BEP", (pump.bep_flow, max(hd) * .96), color="#666", fontsize=7, ha="center")
    ax.axvline(qop, color=RO, lw=1.2)
    ax.annotate("operación\n%.0f b/d" % qop, (qop, max(hd) * .5), color=RO, fontsize=8, fontweight="bold",
                ha="center", bbox=dict(fc="white", ec=RO, lw=.7, alpha=.92))
    ax.set_xlabel("caudal  [b/d]"); ax.set_ylabel("ft por etapa", color=AZ)
    ax2.set_ylabel("rendimiento [%]", color=VE); ax2.grid(False)
    ax.set_title("%s — %s %s a %.0f Hz" % (rotulo, pu["pump_manufacturer"], pu["pump_model"], hz),
                 color=AZ, fontweight="bold", fontsize=9)
    fig.tight_layout()
    return _uri(fig)


def escalera(fila: dict, rotulo: str) -> tuple[str, str]:
    plt = _plt()
    inc = fila["inc"]; s = fila["summary"]
    fig, ax = plt.subplots(figsize=(5.4, 4.2))
    for row in inc:
        ax.barh((row["p_lo"] + row["p_hi"]) / 2, row["q_avg_bpd"], height=row["delta_p"] * 0.86,
                color="#4472C4", alpha=.75, edgecolor="white", lw=.6)
        ax.text(row["q_avg_bpd"] + 20, (row["p_lo"] + row["p_hi"]) / 2, "%.0f et." % row["stages_exact"],
                va="center", fontsize=7, color=AZ)
    ax.set_xlabel("caudal de mezcla  [b/d]"); ax.set_ylabel("presión  [psi]")
    ax.set_title(f"{rotulo} — escalera de incrementos", color=AZ, fontweight="bold", fontsize=9)
    ax.axhline(s["p_intake"], color=RO, lw=1.2, ls="--"); ax.axhline(s["p_discharge"], color=VE, lw=1.2, ls="--")
    ax.text(60, s["p_intake"], "ADMISIÓN %.0f psi" % s["p_intake"], color=RO, fontsize=7, va="bottom")
    ax.text(60, s["p_discharge"], "DESCARGA %.0f psi" % s["p_discharge"], color=VE, fontsize=7, va="top")
    ax.grid(axis="x", alpha=.3); ax.set_xlim(0, max(x["q_avg_bpd"] for x in inc) * 1.28)
    fig.tight_layout(); a = _uri(fig)
    fig, ax = plt.subplots(figsize=(5.4, 3.2)); ax2 = ax.twinx()
    p = [x["p_lo"] for x in inc] + [inc[-1]["p_hi"]]; q = [x["q_lo_bpd"] for x in inc] + [inc[-1]["q_hi_bpd"]]
    ax.plot(p, q, "o-", color=AZ, lw=2, ms=4)
    ax2.plot([(x["p_lo"] + x["p_hi"]) / 2 for x in inc], [x["rs"] for x in inc], "s--", color=NA, lw=1.4, ms=4)
    ax.set_xlabel("presión  [psi]"); ax.set_ylabel("caudal de mezcla  [b/d]", color=AZ)
    ax2.set_ylabel("Rs  [scf/STB]", color=NA); ax.grid(alpha=.3); ax2.grid(False)
    ax.set_title(f"{rotulo} — el gas se comprime y se redisuelve", color=AZ, fontweight="bold", fontsize=9)
    fig.tight_layout()
    return a, _uri(fig)


def viscosidad(fila: dict, rotulo: str) -> str:
    import matplotlib.patches as mp
    plt = _plt()
    vc = fila["visc"]; ch = vc["viscosity_chain"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 2.9), gridspec_kw={"width_ratios": [1.35, 1]})
    pasos = [("Fig. 4L(2)\n%.0f °API, %.0f °F" % (fila["pozo"]["fluid"]["oil_api"], ch["temp_f"]), "%.1f cp" % ch["mu_dead_cp"]),
             ("Fig. 4L(1)\nRs = %.0f scf/STB" % ch["rs_scf_bbl"], "%.1f cp" % ch["mu_live_cp"]),
             ("÷ SG = %.4f" % ch["sg_oil"], "%.2f cSt" % ch["cst"]),
             ("ec. 4.14 Takács\ncSt → SSU", "%.1f SSU" % ch["ssu"])]
    a1.axis("off")
    for i, (t, v) in enumerate(pasos):
        y = 3 - i
        a1.add_patch(mp.FancyBboxPatch((0.02, y - 0.34), 0.96, 0.66, boxstyle="round,pad=0.02",
                     fc="#EAF0FA" if i % 2 == 0 else "#F3F6FC", ec=AZ, lw=.8))
        a1.text(0.06, y + 0.06, t, fontsize=7.4, color="#333", va="center")
        a1.text(0.94, y + 0.06, v, fontsize=9.5, color=AZ, fontweight="bold", va="center", ha="right")
        if i < 3:
            a1.annotate("", xy=(0.5, y - 0.36), xytext=(0.5, y - 0.52),
                        arrowprops=dict(arrowstyle="-|>", color=AZ, lw=1.1))
    a1.set_xlim(0, 1); a1.set_ylim(-0.7, 3.6)
    a1.set_title(f"{rotulo} — cadena de Riling", color=AZ, fontweight="bold", fontsize=9)
    fac = [("C_Q\ncapacidad", vc["capacity_factor"], VE), ("C_H\naltura", vc["head_factor"], AZ),
           ("C_HP\npotencia", vc["hp_factor"], RO)]
    a2.bar([x[0] for x in fac], [x[1] for x in fac], color=[x[2] for x in fac], alpha=.85, width=.6)
    a2.axhline(100, color="#666", ls="--", lw=1)
    for i, x in enumerate(fac):
        a2.text(i, x[1] + 3, "%.2f %%" % x[1], ha="center", fontsize=8.5, fontweight="bold", color=x[2])
    a2.set_ylim(0, 150); a2.set_ylabel("% respecto del agua"); a2.grid(axis="y", alpha=.3)
    a2.set_title("Tablas 4.520 / 4.521 a %.0f SSU" % ch["ssu"], color=AZ, fontweight="bold", fontsize=9)
    fig.tight_layout()
    return _uri(fig)


# ---------------------------------------------------------------------------
# Láminas 4L de Brown redibujadas con la lectura del pozo
# ---------------------------------------------------------------------------
# Se dibujan con las mismas tablas digitalizadas que usa el cálculo
# (catalogs/viscosity_charts.json) y con la misma regla de interpolación
# (segmentos rectos en log μ), de modo que la lectura marcada es exactamente
# el valor que entró a la cuenta.

def _marca(ax, x, y, x0, y0, txt, dx=12, dy=14):
    ax.plot([x, x], [y0, y], color=RO, lw=1.3, ls="--", zorder=4)
    ax.plot([x0, x], [y, y], color=RO, lw=1.3, ls="--", zorder=4)
    ax.plot([x], [y], "o", color=RO, ms=7, zorder=5)
    ax.annotate(txt, (x, y), textcoords="offset points", xytext=(dx, dy), color=RO, fontsize=8,
                fontweight="bold", bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=RO, lw=.8))


def carta_4l2(api: float, temp_f: float, mu_od: float, medido: bool, rotulo: str) -> str:
    """Fig. 4L(2): viscosidad del crudo sin gas en función de °API e isoterma."""
    from bes.core.viscosity import _charts, dead_oil_viscosity_chart
    plt = _plt()
    L = _charts()["fig_4L_2"]
    apis = L["api"]
    fig, ax = plt.subplots(figsize=(5.6, 3.9))
    grises = ["#1F3864", "#2F5597", "#5B7DB8", "#8EA6D2", "#B4C4E3"]
    for iso, c in zip(L["isotermas"], grises):
        ax.plot(apis, iso["mu_cp"], color=c, lw=1.4, label=f"{iso['temp_f']:.0f} °F")
    temps = [iso["temp_f"] for iso in L["isotermas"]]
    if not medido and temps[0] <= temp_f <= temps[-1] and temp_f not in temps:
        ys = [dead_oil_viscosity_chart(a, temp_f)["mu_cp"] for a in apis]
        ax.plot(apis, ys, color=RO, lw=1.2, ls=":", label=f"{temp_f:.0f} °F (interpolada)")
    ax.set_yscale("log")
    ax.set_xlim(apis[0], apis[-1]); ax.set_ylim(0.1, 10000)
    if medido:
        ax.text(0.97, 0.95, f"μod de ensayo = {mu_od:.1f} cP\n(medido a la temperatura de evaluación:\nno se lee la lámina)",
                transform=ax.transAxes, ha="right", va="top", fontsize=8, color=RO,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=RO, lw=.8))
    else:
        _marca(ax, api, mu_od, apis[0], 0.1, f"{api:.1f} °API, {temp_f:.0f} °F\nμod = {mu_od:.1f} cP")
    ax.set_xlabel("gravedad del crudo  [°API a 60 °F]")
    ax.set_ylabel("viscosidad del crudo sin gas  μod  [cP]")
    ax.set_title(f"{rotulo} — Fig. 4L(2): crudo sin gas", color=AZ, fontweight="bold")
    ax.legend(title="isoterma", fontsize=7, title_fontsize=7, loc="lower left")
    ax.grid(True, which="both", alpha=.25)
    fig.tight_layout()
    return _uri(fig)


def carta_4l1(mu_od: float, rs: float, mu_ob: float, rotulo: str) -> str:
    """Fig. 4L(1): viscosidad del crudo saturado según μod y el gas en solución."""
    from bes.core.viscosity import _charts, gas_saturated_viscosity_chart
    plt = _plt()
    curvas = _charts()["fig_4L_1"]["curvas"]
    fig, ax = plt.subplots(figsize=(5.6, 3.9))
    for cv in curvas:
        ax.plot(cv["rs_scf_bbl"], cv["mu_cp"], color="#8EA6D2", lw=1.0)
        ax.text(cv["rs_scf_bbl"][0] + 8, cv["mu_cp"][0], f"{cv['mu_dead_cp']:g}", fontsize=6.5,
                color="#1F3864", va="center")
    etiquetas = [cv["mu_dead_cp"] for cv in curvas]
    if mu_od not in etiquetas and etiquetas[0] <= mu_od <= etiquetas[-1]:
        hi = next(cv for cv in curvas if cv["mu_dead_cp"] > mu_od)
        lo = [cv for cv in curvas if cv["mu_dead_cp"] < mu_od][-1]
        rmax = min(hi["rs_scf_bbl"][-1], lo["rs_scf_bbl"][-1])
        xs = [rmax * i / 60 for i in range(61)]
        ys = [gas_saturated_viscosity_chart(mu_od, x)["mu_cp"] for x in xs]
        ax.plot(xs, ys, color=RO, lw=1.2, ls=":", label=f"curva de {mu_od:.0f} cP (interpolada)")
        ax.legend(fontsize=7, loc="upper right")
    ax.set_yscale("log"); ax.set_xlim(0, 1400); ax.set_ylim(0.1, 600)
    _marca(ax, rs, mu_ob, 0, 0.1, f"μod = {mu_od:.1f} cP, Rs = {rs:.0f}\nμob = {mu_ob:.1f} cP", dx=14, dy=10)
    ax.set_xlabel("gas en solución a la presión de admisión  Rs  [scf/bbl]")
    ax.set_ylabel("viscosidad del crudo saturado  μob  [cP]")
    ax.set_title(f"{rotulo} — Fig. 4L(1): corrección por gas disuelto", color=AZ, fontweight="bold")
    ax.grid(True, which="both", alpha=.25)
    fig.tight_layout()
    return _uri(fig)
