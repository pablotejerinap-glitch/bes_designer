"""El orden por cercanía al BEP usa el caudal con que la bomba trabaja.

Con crudo viscoso la bomba opera sobre su curva de agua al caudal equivalente
Q/C_Q (Riling, Brown 1980 Sección 4.53112): ése, y no el caudal de superficie,
es el que se compara con el BEP. Con otra frecuencia, el BEP se corre con la
afinidad (Q ∝ f).
"""
from fastapi.testclient import TestClient

from bes.api.main import app

POZO_VISCOSO = {
    "reservoir": {"static_pressure": 1750, "bubble_point": 0, "test_pwf": 1550, "test_rate": 1000,
                  "ipr_method": "linear", "reservoir_temp": 160, "drive_mechanism": "water_drive",
                  "fetkovich_n": None},
    "fluid": {"oil_api": 14, "water_cut": 0.5, "gor": 0, "gas_sg": 0.65, "water_sg": 1.07,
              "oil_viscosity_dead": None, "viscosity_temp_ref": None, "bubble_point_pressure": 0,
              "h2s_content": 0, "co2_content": 0, "sand_production": False},
    "well": {"total_depth": 6450, "casing_od": 5.5, "casing_weight": 17, "casing_id": 4.892,
             "tubing_od": 2.375, "tubing_id": 1.995, "perforations_top": 6400,
             "perforations_bottom": 6450, "deviation_max": 0, "wellhead_temp": 100},
    "surface": {"wellhead_pressure_required": 120, "flowline_length": 1000, "flowline_id": 3,
                "flowline_elevation_change": 0, "separator_pressure": 100,
                "power_supply_voltage": 4160, "frequency": 60},
    "objectives": {"target_flow_rate": 1500, "safety_margin_depth": 100, "allow_gas_venting": True,
                   "max_gip": 0.1, "design_life_years": 5, "use_vsd": False,
                   "design_frequency_hz": None},
}


def test_viscoso_compara_el_bep_con_el_caudal_equivalente_en_agua():
    d = TestClient(app).post("/api/design", json=POZO_VISCOSO).json()
    recs = d["recommendations"]
    assert recs, d
    for r in recs:
        q_agua = r["design"]["viscosity_correction"]["q_water"]
        bep = r["criteria"]["bep_flow_bpd"]
        assert abs(r["criteria"]["bep_distance_frac"] - abs(q_agua - bep) / bep) < 1e-9
    dist = [r["criteria"]["bep_distance_frac"] for r in recs]
    assert dist == sorted(dist)
