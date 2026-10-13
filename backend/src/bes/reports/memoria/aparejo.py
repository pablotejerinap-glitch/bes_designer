# -*- coding: utf-8 -*-
"""Intermedios de la selección del aparejo, recalculados con las mismas
funciones que usa el diseño (``bes.core.electrical`` y el catálogo)."""
from __future__ import annotations

import math

from bes.core import electrical as E


def _limites_eje(cm, pu) -> dict | None:
    """Límites del eje con la consulta única de la herramienta
    (:func:`bes.core.mechanical.mechanical_data`): hoja del modelo, si no la
    serie del mismo fabricante, si no ninguno."""
    from bes.core.mechanical import mechanical_data
    raw = next((p for p in cm.get_all_pumps()
                if p.model == pu["pump_model"] and p.manufacturer == pu["pump_manufacturer"]), None)
    return mechanical_data(raw, cm) if raw is not None else None


def sg_liquido(fila: dict) -> float:
    sg = (fila["pasos"].get("Gravedad específica del líquido producido") or {}).get("res")
    if sg is None:
        fl = fila["pozo"]["fluid"]
        sgo = 141.5 / (131.5 + fl["oil_api"])
        sg = sgo * (1 - fl["water_cut"]) + fl["water_sg"] * fl["water_cut"]
    return sg


def intermedios(fila: dict, cm) -> dict:
    pu = fila["pump"]; P = fila["pozo"]
    W = P["well"]; O_ = P["objectives"]; T = P["reservoir"]["reservoir_temp"]
    sg = sg_liquido(fila)
    tdh = fila["tdh"][0] if fila["gas"] else pu["total_head_required"]
    amps = pu["motor_amperage"]; L = pu["pump_setting_depth"] + 100.0
    vpa = E._interp_vdrop_per_amp("CU", "#%s" % pu["cable_awg"], T)
    chk = E.check_cable_electrical(motor_voltage=pu["motor_voltage"], motor_amps=amps,
                                   vdrop_per_amp_per_1000ft=vpa, length_ft=L)
    d_eje = E._SHAFT_DIAMETER_IN.get(str(pu["pump_series"]), E._DEFAULT_SHAFT_DIAMETER_IN)
    dp = tdh * 0.433 * sg; ar = math.pi / 4 * d_eje ** 2
    a_in2 = math.pi / 4 * (W["casing_id"] ** 2 - pu["motor_od"] ** 2)
    modelo_motor = pu["motor_model"]
    mot = next((m for m in cm._motors if m.get("model") == modelo_motor), None)
    if mot is None and " × " in str(modelo_motor):
        # Motores en tándem: el modelo es «n × unidad».
        cant, unidad = str(modelo_motor).split(" × ", 1)
        base = next((m for m in cm._motors if m.get("model") == unidad), {})
        mot = E._motor_en_tandem(base, int(cant)) if base else {}
    mot = mot or {}
    cab = next((c for c in cm._cables if c.get("size") == "#%s" % pu["cable_awg"]
                and c.get("conductor") == "CU" and c.get("type") == pu["cable_type"]), None) or \
        next((c for c in cm._cables if c.get("size") == "#%s" % pu["cable_awg"]
              and c.get("conductor") == "CU"), {})
    sel = next((s for s in cm._seals if s.get("model") == pu["seal_model"]), {})
    ctl = next((c for c in cm._controllers if c.get("model") == pu["controller_model"]), {})
    hp = pu["total_pump_hp"]
    tv = 800.0 if hp <= 70 else (1200.0 if hp <= 200 else 2000.0)
    q_ref = fila["summary"]["q_mix_intake_bpd"] if fila["gas"] else O_["target_flow_rate"]
    vs = pu["surface_voltage_required"]
    kva = vs * amps * math.sqrt(3) / 1000
    return {
        "hp_etapa": pu["hp_per_stage"], "N": pu["num_stages"], "sg": sg, "hp_eje": hp, "tdh": tdh, "T": T,
        "shaft": pu["shaft_check"] or {}, "serie_datos": _limites_eje(cm, pu),
        "series": _series(cm),
        "bearing": pu.get("bearing_load_lbs"), "ceiling": pu.get("staging_ceiling"),
        "thrust": {"d": d_eje, "dp": dp, "area": ar, "F": pu.get("axial_thrust_lbs"), "margen": 1.20,
                   "desv": W["deviation_max"], "prefer": "bag" if W["deviation_max"] > 30 else "labyrinth"},
        "sello": sel,
        "motor": {"hp_min": round(hp * 1.10, 6), "max_od": round(pu["pump_od"] * 1.20, 6),
                  "t_min": T + 25, "target_v": tv, "m": mot},
        "cable": {"req": amps * 1.25, "clr": (W["casing_id"] - pu["motor_od"]) / 2.0, "L": L, "vpa": vpa,
                  "dV": pu["cable_voltage_drop"], "awg": pu["cable_awg"], "tipo": pu["cable_type"], "c": cab},
        "elec": chk,
        "sup": {"vs": vs, "kva": kva, "trafo": pu["transformer_kva"],
                "cat": cm.select_transformer(kva, vs)},
        "cool": {"a_in2": a_in2, "a_ft2": a_in2 / 144, "v": pu["fluid_velocity_ft_s"], "q": q_ref},
        "ctl": ctl, "use_vsd": O_["use_vsd"],
        "hous": {"size": pu.get("housing_size_stages"), "n": pu.get("n_housings"),
                 "dummy": pu.get("dummy_stages"), "pmax": pu.get("max_housing_pressure_psi")},
    }


def _series(cm) -> list[dict]:
    import json
    from pathlib import Path
    import bes.catalogs as cat
    p = Path(cat.__file__).parent / "pump_series.json"
    return json.loads(p.read_text(encoding="utf-8"))["series"]
