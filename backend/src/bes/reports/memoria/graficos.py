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
