"""API tests (FastAPI TestClient) for the BES Designer backend.

Exercises the request→domain→response contract end-to-end, including the
enum mapping and the ValueError→422 error contract.
"""
from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from bes.api.main import app

# Pozos de prueba de la API. NO son casos de libro ni de cátedra: son entradas
# sintéticas, cargadas a mano acá, cuyo único propósito es ejercitar el
# contrato request→dominio→response. Los casos precargados se retiraron del
# proyecto; la app trabaja con datos que carga el usuario.
_WELL_HIGH_RATE = {                     # alto caudal, casing 8-5/8", sin gas
    "reservoir": {
        "static_pressure": 1250.0, "bubble_point": 0.0,
        "test_pwf": 750.0, "test_rate": 5000.0,      # ⇒ J = 10 STB/d/psi
        "ipr_method": "linear", "reservoir_temp": 120.0,
        "drive_mechanism": "water_drive",
    },
    "fluid": {
        "oil_api": 35.0, "water_cut": 1.0, "gor": 0.0, "gas_sg": 0.65,
        "water_sg": 1.1, "oil_viscosity_dead": 1.0, "viscosity_temp_ref": 100.0,
        "bubble_point_pressure": 0.0, "h2s_content": 0.0, "co2_content": 0.0,
        "sand_production": False,
    },
    "well": {
        "total_depth": 2200.0, "casing_od": 8.625, "casing_weight": 24.0,
        "casing_id": 8.097, "tubing_od": 5.5, "tubing_id": 4.778,
        "perforations_top": 1900.0, "perforations_bottom": 2200.0,
        "deviation_max": 0.0, "wellhead_temp": 75.0,
    },
    "surface": {
        "wellhead_pressure_required": 0.0, "flowline_length": 2000.0,
        "flowline_id": 4.0, "flowline_elevation_change": 30.0,
        "separator_pressure": 50.0, "power_supply_voltage": 4160.0,
        "frequency": 60.0,
    },
    "objectives": {
        "target_flow_rate": 10000.0, "safety_margin_depth": 100.0,
        "allow_gas_venting": False, "max_gip": 0.01,
        "design_life_years": 5.0, "use_vsd": False,
    },
}

_WELL_OIL = {                           # petróleo con gas, casing 5-1/2", Vogel
    "reservoir": {
        "static_pressure": 2000.0, "bubble_point": 2000.0,
        "test_pwf": 1000.0, "test_rate": 933.3,      # ⇒ J ≈ 1.2 STB/d/psi
        "ipr_method": "vogel", "reservoir_temp": 170.0,
        "drive_mechanism": "solution_gas",
    },
    "fluid": {
        "oil_api": 30.0, "water_cut": 0.15, "gor": 350.0, "gas_sg": 0.75,
        "water_sg": 1.02, "oil_viscosity_dead": 5.0, "viscosity_temp_ref": 100.0,
        "bubble_point_pressure": 2000.0, "h2s_content": 0.0, "co2_content": 0.0,
        "sand_production": False,
    },
    "well": {
        "total_depth": 6150.0, "casing_od": 5.5, "casing_weight": 17.0,
        "casing_id": 4.892, "tubing_od": 2.375, "tubing_id": 1.995,
        "perforations_top": 5900.0, "perforations_bottom": 6030.0,
        "deviation_max": 0.0, "wellhead_temp": 120.0,
    },
    "surface": {
        "wellhead_pressure_required": 200.0, "flowline_length": 1000.0,
        "flowline_id": 3.0, "flowline_elevation_change": 0.0,
        "separator_pressure": 100.0, "power_supply_voltage": 7200.0,
        "frequency": 60.0,
    },
    "objectives": {
        "target_flow_rate": 1227.0, "safety_margin_depth": 50.0,
        "allow_gas_venting": False, "max_gip": 0.7,
        "design_life_years": 5.0, "use_vsd": False,
        "gas_fraction_pc_threshold": 1.0,
    },
}

_WELLS = {"high_rate": _WELL_HIGH_RATE, "oil": _WELL_OIL}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _payload(well: str = "high_rate", n: int = 3) -> dict:
    """Arma un DesignRequest a partir de uno de los pozos sintéticos."""
    return {**copy.deepcopy(_WELLS[well]), "n": n}


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_catalogs(client: TestClient) -> None:
    r = client.get("/api/catalogs")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["pumps"] > 0
    assert len(body["manufacturers"]) > 0
    assert len(body["pumps"]) == body["counts"]["pumps"]
    # Pump summaries are well-formed
    p = body["pumps"][0]
    assert {"manufacturer", "series", "model", "od", "min_flow", "max_flow", "bep_flow"} <= set(p)


def test_design_high_rate_well(client: TestClient) -> None:
    r = client.post("/api/design", json=_payload("high_rate", n=3))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["recommendations"]) >= 1
    top = body["recommendations"][0]
    assert top["rank"] == 1
    assert top["design"]["pump_model"]           # non-empty
    assert top["design"]["num_stages"] > 0
    assert 0.0 <= top["design"]["pump_efficiency"] <= 1.0
    assert set(top["criteria"]) == {
        "bep_flow_bpd", "bep_distance_frac", "flow_vs_bep_pct",
        "efficiency", "total_pump_hp", "classification",
    }
    assert "ordering_criteria" in body and "design_basis" in body
    # El ordenamiento es lexicográfico: rank 1 no puede estar más lejos del BEP
    # que rank 2 (la eficiencia y la potencia solo desempatan).
    dists = [r["criteria"]["bep_distance_frac"] for r in body["recommendations"]]
    assert dists == sorted(dists)


def test_design_validation_error_pydantic(client: TestClient) -> None:
    """Out-of-range field is rejected by Pydantic as 422."""
    bad = _payload()
    bad["fluid"]["water_cut"] = 2.0  # > 1.0
    r = client.post("/api/design", json=bad)
    assert r.status_code == 422


def test_design_domain_cross_field_422(client: TestClient) -> None:
    """Cross-field domain rule (casing_id < casing_od) not checked by Pydantic
    must surface as HTTP 422 via the central ValueError handler."""
    bad = _payload()
    bad["well"]["casing_id"] = bad["well"]["casing_od"]  # violates casing_id < casing_od
    r = client.post("/api/design", json=bad)
    assert r.status_code == 422
    assert "casing_id" in r.json()["detail"]


def test_design_fetkovich_derives_c_from_the_test(client: TestClient) -> None:
    """n travels schema -> mapper -> Reservoir and C is derived from the test.

    C is no longer an API field: a single test point plus n determines it. The
    test rate is picked so the derived C reproduces 0.0641782, which puts the
    Fetkovich AOF at the example's linear reference (PI x Pr = 12 500 STB/d).
    The operating point therefore stays in the same regime and the design
    assembles — a failure here means the wiring broke, not that the well
    stopped being feasible.
    """
    p = _payload()
    p["reservoir"]["ipr_method"] = "fetkovich"
    p["reservoir"]["fetkovich_n"] = 0.854
    p["reservoir"]["test_pwf"] = 1000.0
    p["reservoir"]["test_rate"] = 5223.8677   # a Pwf = 1000 psia, Pr = 1250
    r = client.post("/api/design", json=p)
    assert r.status_code == 200, r.text
    assert len(r.json()["recommendations"]) >= 1


def test_ipr_from_test_endpoint(client: TestClient) -> None:
    """POST /api/ipr/from-test returns the PI the form shows read-only."""
    r = client.post("/api/ipr/from-test", json={
        "static_pressure": 1250.0,
        "bubble_point": 0.0,
        "test_pwf": 1000.0,
        "test_rate": 2500.0,
        "ipr_method": "linear",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["productivity_index"] == pytest.approx(10.0)
    assert body["drawdown_psi"] == pytest.approx(250.0)
    assert body["aof"] == pytest.approx(12500.0)
    assert body["fetkovich_c"] is None


def test_ipr_from_test_zero_drawdown_422(client: TestClient) -> None:
    """A test at Pwf = Pr carries no deliverability information -> 422."""
    r = client.post("/api/ipr/from-test", json={
        "static_pressure": 1250.0,
        "test_pwf": 1250.0,
        "test_rate": 2500.0,
        "ipr_method": "linear",
    })
    assert r.status_code == 422


def test_design_fetkovich_without_n_422(client: TestClient) -> None:
    """FETKOVICH without n cannot derive C from a one-point test -> HTTP 422."""
    p = _payload()
    p["reservoir"]["ipr_method"] = "fetkovich"
    r = client.post("/api/design", json=p)
    assert r.status_code == 422
    assert "fetkovich_n" in r.json()["detail"]


def test_design_with_pump_model_returns_single_recommendation(client: TestClient) -> None:
    """A manual pump_model bypasses the ranking engine: n is ignored and the
    response carries exactly one recommendation for that named pump."""
    # El #1A pide 217 hp y el catálogo llega a 216: los motores mayores eran
    # Reda/Centrilift sin fuente confirmada y se borraron. Se usa el #2A, cuya
    # bomba (D-40) y motor sí tienen fuente.
    p = _payload("oil", n=3)
    # D-40 es la bomba que elige el propio libro para el #2A. Va sobre el pozo
    # de alto caudal —casing 8-5/8"— y no sobre el de petróleo: ahí el casing de
    # 5-1/2" solo admite un motor de 3.75", y REDA en esa serie llega a 47 hp.
    # Con la regla de fabricante único el diseño fallaría por falta de motor
    # REDA, no por un problema del contrato de la API que este test verifica.
    p["pump_model"] = "D-40"
    # La D-40 es una bomba REDA serie 400: pide un motor de 4.56" de diámetro,
    # que no entra en el casing de 5-1/2" del pozo de prueba (solo admite 3.75",
    # y REDA en esa serie llega a 47 hp). Con la regla de fabricante único el
    # diseño fallaría por falta de motor REDA, que no es lo que este test mide.
    # Se ensancha el casing a 7" para dejar pasar el motor que le corresponde.
    p["well"]["casing_od"] = 7.0
    p["well"]["casing_weight"] = 26.0
    p["well"]["casing_id"] = 6.276
    r = client.post("/api/design", json=p)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["recommendations"]) == 1
    assert body["recommendations"][0]["design"]["pump_model"] == "D-40"
    assert body["n_candidates_evaluated"] == 1
    assert "manual" in body["ordering_criteria"][0].lower()


def test_design_with_unknown_pump_model_422(client: TestClient) -> None:
    p = _payload()
    p["pump_model"] = "NO-EXISTE-XYZ"
    r = client.post("/api/design", json=p)
    assert r.status_code == 422
    assert "NO-EXISTE-XYZ" in r.json()["detail"]


def test_design_with_pump_model_too_large_for_casing_422(client: TestClient) -> None:
    p = _payload()
    p["pump_model"] = "L16000N"
    # ninguna bomba supera el casing de 8-5/8": se angosta a 5-1/2"
    p["well"]["casing_od"] = 5.5
    p["well"]["casing_weight"] = 17.0
    p["well"]["casing_id"] = 4.892  # OD 8.75in, no entra en el casing del pozo de prueba
    r = client.post("/api/design", json=p)
    assert r.status_code == 422
    assert "casing" in r.json()["detail"]


def test_design_fetkovich_n_out_of_range_422(client: TestClient) -> None:
    """n outside [0.5, 1.0] is caught by Pydantic before reaching the domain."""
    p = _payload()
    p["reservoir"]["ipr_method"] = "fetkovich"
    p["reservoir"]["fetkovich_n"] = 1.3
    r = client.post("/api/design", json=p)
    assert r.status_code == 422


def _nodal_payload(**over) -> dict:
    p = _payload()
    body = {"reservoir": p["reservoir"], "fluid": p["fluid"],
            "well": p["well"], "surface": p["surface"]}
    body.update(over)
    return body


def _assert_figure(fig: dict) -> None:
    assert "data" in fig and "layout" in fig  # valid Plotly figure JSON


def test_nodal(client: TestClient) -> None:
    r = client.post("/api/nodal", json=_nodal_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["method"] == "poettmann_carpenter"
    assert set(body["metrics"]) == {
        "q_natural", "q_pump", "incremental_rate", "pwf_operating", "pump_efficiency"
    }
    _assert_figure(body["figure"])


def test_nodal_unknown_pump_422(client: TestClient) -> None:
    r = client.post("/api/nodal", json=_nodal_payload(pump_model="NO-EXISTE", stages=50, pump_depth=4000))
    assert r.status_code == 422
    assert "NO-EXISTE" in r.json()["detail"]


def test_sensitivity(client: TestClient) -> None:
    p = _payload()
    body = {"reservoir": p["reservoir"], "fluid": p["fluid"], "well": p["well"],
            "surface": p["surface"], "objectives": p["objectives"],
            "param": "water_cut", "pct_range_pct": 30, "n_points": 5}
    r = client.post("/api/sensitivity", json=body)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["param"] == "water_cut"
    assert len(b["param_values"]) >= 1
    assert set(b["metrics"]) == {"HP", "Etapas", "Eficiencia (%)", "TDH (ft)"}
    _assert_figure(b["figure"])


def test_report_pdf(client: TestClient) -> None:
    r = client.post("/api/reports/pdf", json=_payload())
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_report_xlsx(client: TestClient) -> None:
    r = client.post("/api/reports/xlsx", json=_payload())
    assert r.status_code == 200, r.text
    assert r.content[:2] == b"PK"  # xlsx is a zip container


def test_report_bad_format_404(client: TestClient) -> None:
    r = client.post("/api/reports/txt", json=_payload())
    assert r.status_code == 404


def test_report_pdf_with_pump_model(client: TestClient) -> None:
    """A manually-selected pump_model reports that exact pump, ignoring rank."""
    p = _payload("oil")
    p["pump_model"] = "D-40"
    # La D-40 es una bomba REDA serie 400: pide un motor de 4.56" de diámetro,
    # que no entra en el casing de 5-1/2" del pozo de prueba (solo admite 3.75",
    # y REDA en esa serie llega a 47 hp). Con la regla de fabricante único el
    # diseño fallaría por falta de motor REDA, que no es lo que este test mide.
    # Se ensancha el casing a 7" para dejar pasar el motor que le corresponde.
    p["well"]["casing_od"] = 7.0
    p["well"]["casing_weight"] = 26.0
    p["well"]["casing_id"] = 6.276
    r = client.post("/api/reports/pdf", json=p)
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"



# --------------------------------------------------------------------------- #
# Gráficos sueltos
# --------------------------------------------------------------------------- #
def test_pump_curve_figure(client: TestClient) -> None:
    """La curva de bomba se pide con un modelo real del catálogo."""
    model = client.get("/api/catalogs").json()["pumps"][0]["model"]
    r = client.get(
        "/api/plots/pump-curve",
        params={"pump_model": model, "operating_flow": 1500, "stages": 100},
    )
    assert r.status_code == 200, r.text
    _assert_figure(r.json()["figure"])


def test_pump_curve_unknown_model_422(client: TestClient) -> None:
    r = client.get(
        "/api/plots/pump-curve",
        params={"pump_model": "NO-EXISTE-XYZ", "operating_flow": 1500, "stages": 100},
    )
    assert r.status_code == 422
    assert "NO-EXISTE-XYZ" in r.json()["detail"]


def test_pump_curve_rejects_nonpositive_stages(client: TestClient) -> None:
    model = client.get("/api/catalogs").json()["pumps"][0]["model"]
    r = client.get(
        "/api/plots/pump-curve",
        params={"pump_model": model, "operating_flow": 1500, "stages": 0},
    )
    assert r.status_code == 422


def test_pump_curve_matches_design_recommendation(client: TestClient) -> None:
    """El front pide la curva con los valores que devuelve /api/design:
    ese par (modelo, etapas) siempre tiene que graficar."""
    design = client.post("/api/design", json=_payload(n=1)).json()
    top = design["recommendations"][0]["design"]
    r = client.get(
        "/api/plots/pump-curve",
        params={
            "pump_model": top["pump_model"],
            "operating_flow": top["flow_rate_achieved"],
            "stages": top["num_stages"],
        },
    )
    assert r.status_code == 200, r.text
    _assert_figure(r.json()["figure"])


def test_affinity_endpoint(client: TestClient) -> None:
    """Las curvas reescaladas viajan por la API con su relación de velocidad."""
    r = client.get("/api/affinity", params={
        "pump_model": "D-40", "frequencies": "50,60", "target_flow": 1560,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pump_model"] == "D-40"
    assert [c["frequency_hz"] for c in body["curves"]] == [50.0, 60.0]
    at50, at60 = body["curves"]
    # Q ∝ N: el BEP se corre en la misma proporción que la frecuencia.
    assert at50["bep_flow"] == pytest.approx(at60["bep_flow"] * 50.0 / 60.0)
    # H ∝ N²
    assert at50["bep_head_per_stage"] == pytest.approx(
        at60["bep_head_per_stage"] * (50.0 / 60.0) ** 2
    )
    # La eficiencia no cambia con la velocidad.
    assert at50["bep_efficiency"] == pytest.approx(at60["bep_efficiency"])
    assert body["frequency_for_target_flow"] == pytest.approx(72.0, abs=0.1)


def test_affinity_figure_endpoint(client: TestClient) -> None:
    r = client.get("/api/affinity/figure",
                   params={"pump_model": "D-40", "frequencies": "50,60"})
    assert r.status_code == 200, r.text
    assert "data" in r.json()["figure"]


def test_affinity_frequency_out_of_vsd_range_422(client: TestClient) -> None:
    r = client.get("/api/affinity",
                   params={"pump_model": "D-40", "frequencies": "120"})
    assert r.status_code == 422
    assert "VSD" in r.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/gas/increment-design — método de incrementos (Brown §4.53103)
# ---------------------------------------------------------------------------

def _gas_payload(**extra) -> dict:
    """Pozo con gas para el método de incrementos, con presiones dadas."""
    base = copy.deepcopy(_WELL_OIL)
    base.update({
        "p_intake": 500.0,
        "p_discharge": 1300.0,
        "increment_psi": 200.0,
        "fixed_pump_model": "D-40",
    })
    base.update(extra)
    return base


def test_gas_increment_design_ok(client: TestClient) -> None:
    r = client.post("/api/gas/increment-design", json=_gas_payload())
    assert r.status_code == 200, r.text
    body = r.json()

    resumen = body["summary"]
    assert resumen["n_increments"] == 4          # (1300−500)/200
    assert resumen["total_stages"] > 0
    assert resumen["total_hp"] > 0
    assert resumen["pump_model"] == "D-40"
    assert len(body["increments"]) == 4


def test_gas_increment_tabla_trae_los_dos_extremos(client: TestClient) -> None:
    """La tabla del §23 necesita caudal de entrada Y de salida, no sólo el medio."""
    r = client.post("/api/gas/increment-design", json=_gas_payload())
    fila = r.json()["increments"][0]

    assert fila["q_lo_bpd"] > fila["q_hi_bpd"], (
        "el gas se comprime: el caudal de mezcla tiene que bajar con la presión"
    )
    assert fila["q_avg_bpd"] == pytest.approx(
        0.5 * (fila["q_lo_bpd"] + fila["q_hi_bpd"])
    )
    for k in ("q_oil_lo", "q_water_lo", "q_gas_lo", "rs_lo", "bo_lo", "bg_lo"):
        assert k in fila


def test_gas_increment_masa_constante(client: TestClient) -> None:
    """El caudal másico es el invariante de control del método (§12)."""
    r = client.post("/api/gas/increment-design", json=_gas_payload())
    assert r.json()["summary"]["mass_rate_lbm_d"] > 0


def test_gas_increment_paso_configurable(client: TestClient) -> None:
    """El tamaño del escalón lo elige el usuario (§4)."""
    r200 = client.post("/api/gas/increment-design", json=_gas_payload())
    r50 = client.post("/api/gas/increment-design",
                      json=_gas_payload(increment_psi=50.0))
    assert r50.status_code == 200, r50.text
    assert r50.json()["summary"]["n_increments"] == 16
    # Afinando el paso el conteo converge, no se dispara.
    assert r50.json()["summary"]["total_stages"] == pytest.approx(
        r200.json()["summary"]["total_stages"], rel=0.10
    )


def test_gas_increment_reporta_origen_del_pvt(client: TestClient) -> None:
    """Sin tabla, correlación; con tabla, laboratorio (§25)."""
    sin = client.post("/api/gas/increment-design", json=_gas_payload())
    assert "Correlaciones" in sin.json()["summary"]["pvt_source"]
    assert sin.json()["increments"][0]["pvt_sources"]["rs"] == "correlacion"

    con = client.post("/api/gas/increment-design", json=_gas_payload(
        pvt_table={
            "points": [
                {"pressure": 500.0, "rs": 80.0, "bo": 1.080, "bg": 0.00577},
                {"pressure": 1300.0, "rs": 240.0, "bo": 1.150, "bg": 0.00220},
            ],
            "source": "PVT experimental pozo de prueba",
            "temperature_f": 170.0,
        },
    ))
    assert con.status_code == 200, con.text
    assert "experimental" in con.json()["summary"]["pvt_source"]
    assert con.json()["increments"][0]["pvt_sources"]["rs"] == "pvt"


def test_gas_increment_descarga_menor_que_admision_422(client: TestClient) -> None:
    r = client.post("/api/gas/increment-design",
                    json=_gas_payload(p_intake=1300.0, p_discharge=500.0))
    assert r.status_code == 422
    assert "p_discharge" in r.json()["detail"]


def test_gas_increment_paso_invalido_422(client: TestClient) -> None:
    r = client.post("/api/gas/increment-design",
                    json=_gas_payload(increment_psi=0.0))
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/gas/design — diseño COMPLETO por incrementos (aparejo entero)
# ---------------------------------------------------------------------------

def _gas_design_payload(**extra) -> dict:
    base = copy.deepcopy(_WELL_OIL)
    base["objectives"].pop("gas_fraction_pc_threshold", None)
    base.update({"increment_psi": 200.0})
    base.update(extra)
    return base


def test_gas_design_completo_ok(client: TestClient) -> None:
    r = client.post("/api/gas/design", json=_gas_design_payload())
    assert r.status_code == 200, r.text
    body = r.json()

    # El método se aplicó por el umbral de gas, no por elección arbitraria.
    assert body["method"]["applies"] is True
    assert body["method"]["free_gas_fraction"] > body["method"]["threshold"]

    # Y terminó en un aparejo completo, no en dos números.
    d = body["design"]
    assert d["pump_model"] and d["num_stages"] > 0
    assert d["motor_model"] and d["motor_hp"] > 0
    assert d["cable_awg"] > 0
    assert d["transformer_kva"] > 0
    assert d["n_housings"] >= 1


def test_gas_design_usa_el_mismo_schema_que_el_convencional(
    client: TestClient,
) -> None:
    """§23: la vista de resultados tiene que servir para los dos caminos."""
    gas = client.post("/api/gas/design", json=_gas_design_payload()).json()
    conv = client.post("/api/design", json=_payload("oil", n=1)).json()

    claves_conv = set(conv["recommendations"][0]["design"])
    assert claves_conv == set(gas["design"]), (
        "el diseño por gas no devuelve el mismo esquema que el convencional"
    )


def test_gas_design_publica_las_dos_rutas_al_tdh(client: TestClient) -> None:
    body = client.post("/api/gas/design", json=_gas_design_payload()).json()
    assert body["tdh_increment_ft"] > 0
    assert body["tdh_conventional_ft"] > 0
    # El aparejo se dimensionó con el TDH del método.
    assert body["design"]["total_head_required"] == pytest.approx(
        body["tdh_increment_ft"]
    )


def test_gas_design_una_sola_bomba(client: TestClient) -> None:
    body = client.post("/api/gas/design", json=_gas_design_payload()).json()
    modelos = {row["pump_model"] for row in body["increments"]}
    assert modelos == {body["design"]["pump_model"]}


def test_gas_design_reporta_la_viabilidad_por_gas(client: TestClient) -> None:
    """El veredicto del separador viaja en la respuesta, con sus números."""
    body = client.post("/api/gas/design", json=_gas_design_payload()).json()
    f = body["feasibility"]
    assert f["viable"] is True
    assert f["f_intake"] > f["f_pump"], "el separador tiene que bajar el gas"
    assert f["f_pump"] <= f["max_gip"]
    assert f["separator_model"]


def test_gas_design_gas_excesivo_422(client: TestClient) -> None:
    """Si el gas remanente supera max_gip, no hay diseño: 422 con el motivo."""
    payload = _gas_design_payload()
    payload["objectives"]["max_gip"] = 0.001
    r = client.post("/api/gas/design", json=payload)
    assert r.status_code == 422
    detalle = r.json()["detail"]
    assert "NO VIABLE" in detalle
    assert "otro método de levantamiento" in detalle


def test_max_gip_es_opcional_y_toma_el_default(client: TestClient) -> None:
    """El campo dejó de ser obligatorio: sin él, el dominio pone 0.10."""
    payload = _gas_design_payload()
    payload["objectives"].pop("max_gip", None)
    r = client.post("/api/gas/design", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["feasibility"]["max_gip"] == pytest.approx(0.10)


def test_gas_design_bomba_sin_motor_422(client: TestClient) -> None:
    """Wood Group no tiene motores: sin fallback, falla explicando."""
    r = client.post("/api/gas/design",
                    json=_gas_design_payload(fixed_pump_model="TD-650"))
    assert r.status_code == 422
    assert "Ninguna bomba" in r.json()["detail"]


def test_gas_design_explica_sus_formulas(client: TestClient) -> None:
    """El aparejo completo lleva la traza del método adentro del DesignResult,
    que es de donde la lee la vista de resultados (misma sección que el camino
    convencional, sin código nuevo en el front)."""
    body = client.post("/api/gas/design", json=_gas_design_payload()).json()
    formulas = body["design"]["formulas"]
    assert formulas, "el diseño por gas tiene que explicar qué cuentas hizo"
    claves = {f["key"] for f in formulas}
    assert {"gas_delta_p", "gas_psi_etapa", "gas_etapas_tramo",
            "gas_etapas_total"} <= claves


def test_gas_increment_explica_sus_formulas(client: TestClient) -> None:
    """El camino de sólo hidráulica no arma un DesignResult, así que la traza
    viaja al costado, en su propio campo."""
    body = client.post("/api/gas/increment-design", json=_gas_payload()).json()
    assert body["formulas"], "la hidráulica también tiene que explicarse"
    et = next(f for f in body["formulas"] if f["key"] == "gas_etapas_tramo")
    # Rehacer la cuenta con los números que muestra da lo que declara.
    assert et["inputs"]["ΔP_tramo"] / et["inputs"]["Δp_etapa"] == pytest.approx(
        et["result"], rel=1e-9
    )


def test_gas_ladder_figure_viaja_en_las_dos_respuestas(client: TestClient) -> None:
    """La escalera (Brown Fig. 4.56B) acompaña al cálculo, como el nodal."""
    completo = client.post("/api/gas/design", json=_gas_design_payload()).json()
    hidraulica = client.post("/api/gas/increment-design",
                             json=_gas_payload()).json()
    for body in (completo, hidraulica):
        fig = body["ladder_figure"]
        assert fig.get("data"), "falta la figura de la escalera"
        # El eje X va oculto y con rango fijo: la figura son anotaciones.
        assert fig["layout"]["xaxis"]["visible"] is False
