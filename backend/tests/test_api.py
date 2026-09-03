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
    """El veredicto del manejo de gas viaja en la respuesta, con sus números.

    El pozo del payload trae ``max_gip = 0.7``, un valor heredado y muy laxo.
    Antes eso alcanzaba para que la escalera se quedara en el primer escalón
    con 63 % de gas libre en la admisión, lo que no es físico: una bomba sin
    separador no admite semejante fracción de vacío.

    Cada escalón se compara ahora contra el **menor** entre el criterio del
    usuario y lo que la configuración puede manejar (Takács, Fig. 4.25), de
    modo que el escalón sin separador queda acotado al 20 % y la escalera sube
    a instalar uno. Es el comportamiento correcto: el usuario puede pedir algo
    más estricto que el equipo, pero no más laxo.
    """
    body = client.post("/api/gas/design", json=_gas_design_payload()).json()
    f = body["feasibility"]
    assert f["viable"] is True
    assert f["strategy"] == "simple", (
        "con 63 % de gas la bomba necesita separador, por más que el usuario "
        "haya declarado un max_gip laxo"
    )
    assert f["n_separators"] == 1
    assert f["separator_model"] is not None
    # La tolerancia efectiva ya no es el max_gip pelado: la acota la capacidad
    # del equipo.
    assert f["f_pump"] <= f["tolerance"] <= f["max_gip"]
    assert f["switch_lift_method"] is False
    assert f["uses_agh"] is False


def test_gas_design_con_max_gip_realista_instala_separador(
    client: TestClient,
) -> None:
    """Con el límite del dominio (10 %), el mismo pozo sí necesita equipo.

    63 % de gas libre en la admisión: un separador solo deja 30 % en la bomba,
    por encima del criterio, así que la escalera sube al TÁNDEM, que lo baja
    por debajo del 10 % y no necesita manejador avanzado.

    Antes este pozo terminaba en el AGH, pero sólo porque el tándem era
    inalcanzable: el catálogo no publica el rango de caudal de los separadores
    rotativos y no había con qué armarlo. Desbloqueado el escalón, la escalera
    se detiene antes — que es su regla: no instalar equipo de más.
    """
    payload = _gas_design_payload()
    payload["objectives"]["max_gip"] = 0.10
    f = client.post("/api/gas/design", json=payload).json()["feasibility"]
    assert f["viable"] is True
    assert f["strategy"] == "tandem"
    assert f["n_separators"] == 2
    assert f["uses_agh"] is False, "el tándem alcanza: no hace falta el AGH"
    assert f["separator_model"]
    # Ahora sí cumple el criterio de diseño, no sólo la tolerancia del equipo.
    assert f["f_pump"] <= f["max_gip"]


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


class TestCatalogoDeFormulas:
    """GET /api/formulas — las fórmulas del motor, sin correr un diseño.

    Es lo que permite revisarlas con un profesional: la traza de una corrida
    sólo muestra la rama que ese pozo ejecutó.
    """

    def test_lista_todas_las_formulas_sin_correr_nada(self, client):
        r = client.get("/api/formulas")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] > 0
        assert sum(len(t["formulas"]) for t in body["topics"]) == body["total"]

    def test_trae_las_variantes_que_un_caso_concreto_no_ejecutaria(self, client):
        """Las cuatro maneras de llegar a la Pwf conviven en el catálogo."""
        body = client.get("/api/formulas").json()
        ipr = next(t for t in body["topics"] if t["key"] == "ipr")
        pwf = {f["key"] for f in ipr["formulas"] if f["step"] == "pwf_diseno"}
        assert pwf == {
            "pwf_lineal", "pwf_vogel_recta", "pwf_vogel_bifasico", "pwf_fetkovich",
        }

    def test_cada_formula_viaja_con_su_glosario_y_su_cita(self, client):
        body = client.get("/api/formulas").json()
        for tema in body["topics"]:
            for f in tema["formulas"]:
                assert f["symbols"], f["key"]
                assert f["reference"], f["key"]
                assert f["units"], f["key"]
                assert f["module"].startswith("bes."), f["key"]

    def test_publica_la_cobertura_y_hoy_esta_completa(self, client):
        """El campo existe para mostrar lo que falta; hoy no falta nada."""
        body = client.get("/api/formulas").json()
        assert body["pending_topics"] == []
        for tema in body["topics"]:
            assert tema["instrumented"] is True
            assert tema["formulas"], f"{tema['key']} dice estar instrumentado"

    def test_estan_los_diez_temas_del_motor(self, client):
        body = client.get("/api/formulas").json()
        assert {t["key"] for t in body["topics"]} == {
            "ipr", "tdh", "diseno", "viscosidad", "gas",
            "pvt", "multifasico", "afinidad", "electrico", "mecanica",
        }

    def test_la_traza_de_un_diseno_usa_las_claves_del_catalogo(self, client):
        """Las dos vistas hablan el mismo idioma: se pueden cruzar."""
        declaradas = {
            f["key"]
            for t in client.get("/api/formulas").json()["topics"]
            for f in t["formulas"]
        }
        resp = client.post("/api/design", json=_payload())
        assert resp.status_code == 200
        corridas = {
            f["key"]
            for rec in resp.json()["recommendations"]
            for f in rec["design"]["formulas"]
        }
        assert corridas, "el diseño no emitió ninguna fórmula"
        assert corridas <= declaradas, sorted(corridas - declaradas)


class TestLaViscosidadMedidaNoEsObligatoriaEnLaAPI:
    """Un pozo sin ensayo de viscosidad tiene que poder diseñarse por la API.

    El campo era ``Field(..., gt=0)`` en los dos lados del contrato, así que
    mandar 0 —o no mandar nada— rebotaba con 422 antes de llegar a calcular.
    Como el motor lee la Fig. 4L(2) cuando no hay dato, el requisito era del
    contrato, no de la física.
    """

    def test_omitir_el_campo_no_rompe_el_diseno(self, client: TestClient) -> None:
        p = _payload("oil")
        del p["fluid"]["oil_viscosity_dead"]
        del p["fluid"]["viscosity_temp_ref"]
        r = client.post("/api/design", json=p)
        assert r.status_code == 200, r.text
        assert r.json()["recommendations"]

    def test_mandarlo_en_null_es_lo_mismo(self, client: TestClient) -> None:
        p = _payload("oil")
        p["fluid"]["oil_viscosity_dead"] = None
        p["fluid"]["viscosity_temp_ref"] = None
        r = client.post("/api/design", json=p)
        assert r.status_code == 200, r.text

    def test_cero_sigue_siendo_un_error(self, client: TestClient) -> None:
        """Ausencia de dato es null, no cero: un crudo de 0 cp no existe."""
        p = _payload("oil")
        p["fluid"]["oil_viscosity_dead"] = 0.0
        assert client.post("/api/design", json=p).status_code == 422

    def test_una_medicion_sin_su_temperatura_se_rechaza(
        self, client: TestClient
    ) -> None:
        p = _payload("oil")
        p["fluid"]["oil_viscosity_dead"] = 150.0
        p["fluid"]["viscosity_temp_ref"] = None
        r = client.post("/api/design", json=p)
        assert r.status_code == 422
        assert "viscosity_temp_ref" in r.text


class TestElContratoSigueAlDominio:
    """El esquema de la API no puede quedarse atrás de la dataclass del dominio.

    Pydantic descarta **en silencio** los campos que no declara, así que agregar
    uno a ``core.formulas.Formula`` y olvidarse de ``FormulaSchema`` hace que el
    dato nunca llegue a la pantalla sin que falle nada. Ya pasó: ``step``,
    ``topic``, ``symbols`` y ``context`` se agregaron al dominio y viajaron
    perdidos hasta que este test existió.
    """

    def test_formula_schema_declara_todos_los_campos_del_dominio(self):
        import dataclasses
        from bes.core.formulas import Formula
        from bes.api.schemas.outputs import FormulaSchema

        dominio = {f.name for f in dataclasses.fields(Formula)}
        esquema = set(FormulaSchema.model_fields)
        faltan = dominio - esquema
        assert not faltan, (
            f"FormulaSchema no declara {sorted(faltan)}: esos campos se pierden "
            f"al serializar y nunca llegan al front."
        )

    def test_los_campos_nuevos_llegan_de_verdad_por_la_API(self, client):
        """No alcanza con declararlos: hay que verlos en la respuesta."""
        resp = client.post("/api/design", json=_payload())
        assert resp.status_code == 200
        formulas = [
            f
            for rec in resp.json()["recommendations"]
            for f in rec["design"]["formulas"]
        ]
        assert formulas, "el diseño no emitió ninguna fórmula"
        assert any(f["topic"] for f in formulas), "topic llega vacío en todas"
        assert any(f["step"] for f in formulas), "step llega vacío en todas"
        assert any(f["symbols"] for f in formulas), "symbols llega vacío en todas"

    def test_vogel_publica_los_dos_tramos_y_cual_gobierna(self, client):
        """El profesor tiene que poder revisar el método completo, no una mitad.

        Y la distinción de cuál gobierna tiene que ser un DATO (``applies``),
        no una frase escondida en la prosa.
        """
        # Hace falta un reservorio SUBSATURADO (Pb < Pr) para que existan los
        # dos tramos: con bubble_point 0 la Pb efectiva es Pr y no hay recta.
        p = _payload(well="oil")
        p["reservoir"] |= {
            "static_pressure": 2600.0, "bubble_point": 1255.0,
            "test_pwf": 2100.0, "test_rate": 1000.0, "ipr_method": "vogel",
        }
        p["fluid"]["bubble_point_pressure"] = 1255.0
        p["objectives"]["target_flow_rate"] = 1800.0
        resp = client.post("/api/design", json=p)
        assert resp.status_code == 200, resp.json()

        formulas = resp.json()["recommendations"][0]["design"]["formulas"]
        tramos = [f for f in formulas if f["step"] == "pwf_diseno"]
        claves = {f["key"] for f in tramos}
        assert claves == {"pwf_vogel_recta", "pwf_vogel_bifasico"}, (
            "Vogel generalizado es una función partida en dos: se publican los "
            "dos tramos aunque el pozo caiga en uno solo."
        )
        gobiernan = [f for f in tramos if f["applies"] is True]
        assert len(gobiernan) == 1, "tiene que gobernar exactamente un tramo"
        assert [f for f in tramos if f["applies"] is False], (
            "el tramo que no gobierna se marca como tal, no se omite"
        )


class TestElSelectorDePerdidaDeCargaEnLaAPI:
    """El método de pérdida de carga viaja por el contrato; el umbral no.

    Son dos cosas distintas y sólo una es del usuario: elegir la correlación,
    sí; mover el corte de gas con que se la elige sola, no.
    """

    def _pedido(self, metodo, **pozo):
        req = copy.deepcopy(_WELL_OIL)
        req["objectives"].pop("gas_fraction_pc_threshold", None)
        req["objectives"]["pressure_loss_method"] = metodo
        req["well"].update(pozo)
        req["n"] = 1
        return req

    def test_el_campo_es_opcional(self, client):
        """Sin el campo el diseño corre igual: lo decide la física."""
        req = self._pedido(None)
        del req["objectives"]["pressure_loss_method"]
        assert client.post("/api/design", json=req).status_code == 200

    def test_se_puede_elegir_poettmann_carpenter(self, client):
        r = client.post("/api/design", json=self._pedido("poettmann_carpenter"))
        assert r.status_code == 200
        diseno = r.json()["recommendations"][0]["design"]
        assert diseno["friction_method"] == "poettmann_carpenter"

    def test_pc_con_tuberia_fuera_de_rango_falla_con_422(self, client):
        """La restricción del tubing es dura y el mensaje dice qué hacer."""
        r = client.post(
            "/api/design",
            json=self._pedido("poettmann_carpenter", tubing_od=4.5, tubing_id=3.958),
        )
        assert r.status_code == 422
        assert "2 3/8, 2 7/8, 3 1/2" in r.json()["detail"]

    def test_forzar_monofasico_en_un_pozo_con_gas_avisa(self, client):
        r = client.post("/api/design", json=self._pedido("hazen_williams"))
        assert r.status_code == 200
        diseno = r.json()["recommendations"][0]["design"]
        assert diseno["friction_method"] == "hazen_williams"
        assert any("SUBESTIMADA" in w for w in diseno["warnings"])

    def test_un_metodo_que_no_existe_se_rechaza_en_el_schema(self, client):
        r = client.post("/api/design", json=self._pedido("beggs_brill"))
        assert r.status_code == 422

    def test_el_umbral_de_gas_sigue_sin_exponerse(self, client):
        """El selector agrega el método al contrato, NO el umbral."""
        schema = client.get("/openapi.json").json()
        objetivos = schema["components"]["schemas"]["ObjectivesSchema"]["properties"]
        assert "pressure_loss_method" in objetivos
        assert "gas_fraction_pc_threshold" not in objetivos


class TestLaEscaleraDeGasLlegaPorLaApi:
    """El contrato sigue al dominio: Pydantic descarta en silencio lo que no declara.

    Los campos de la escalera de gas se agregaron a ``DesignResult`` y sin
    declararlos en ``DesignResultSchema`` viajaban perdidos hasta la pantalla
    sin que fallara nada. Es el mismo mecanismo que documenta
    ``.claude/rules/api-contract.md``.
    """

    CAMPOS = (
        "gas_handler_count", "gas_strategy", "gas_fraction_at_pump",
        "switch_lift_method", "gas_verdict",
    )

    def test_el_schema_declara_los_campos_del_dominio(self):
        import dataclasses
        from bes.api.schemas.outputs import DesignResultSchema
        from bes.core.models import DesignResult

        del_dominio = {f.name for f in dataclasses.fields(DesignResult)}
        del_schema = set(DesignResultSchema.model_fields)
        for campo in self.CAMPOS:
            assert campo in del_dominio, f"{campo} no está en DesignResult"
            assert campo in del_schema, (
                f"{campo} está en el dominio pero no en el schema: viajaría perdido"
            )


class TestLaZonaOperativaLlegaAlGrafico:
    """Del diseño con gas a la figura, sin que el front calcule nada."""

    def _design(self, client):
        r = client.post("/api/gas/design", json=_gas_design_payload())
        assert r.status_code == 200, r.text
        return r.json()["design"]

    def test_el_diseno_con_gas_publica_los_tres_caudales(self, client):
        d = self._design(client)
        assert d["gas_q_representative_bpd"] > 0
        # Con gas el caudal CAE a lo largo de la bomba: el gas se comprime y
        # parte pasa a solución. La admisión es el extremo alto.
        assert d["gas_q_intake_bpd"] > d["gas_q_discharge_bpd"]

    def test_el_diseno_convencional_no_los_trae(self, client):
        r = client.post("/api/design", json={**copy.deepcopy(_WELL_HIGH_RATE),
                                             "n": 1})
        assert r.status_code == 200, r.text
        d = r.json()["recommendations"][0]["design"]
        assert d["gas_q_representative_bpd"] == 0.0

    def test_la_figura_dibuja_la_zona_con_esos_caudales(self, client):
        d = self._design(client)
        fig = client.get("/api/plots/pump-curve", params={
            "pump_model": d["pump_model"],
            "operating_flow": d["flow_rate_achieved"],
            "stages": d["num_stages"],
            "q_representative": d["gas_q_representative_bpd"],
            "q_intake": d["gas_q_intake_bpd"],
            "q_discharge": d["gas_q_discharge_bpd"],
        }).json()["figure"]
        textos = " | ".join(a.get("text", "") for a in
                            fig["layout"]["annotations"])
        assert "Zona operativa del método de gas" in textos
        assert "q admisión (entra)" in textos and "q descarga (sale)" in textos
        # La banda del fabricante no se pierde.
        assert "Rango operativo recomendado" in textos

    def test_sin_las_cotas_la_curva_sale_como_siempre(self, client):
        d = self._design(client)
        fig = client.get("/api/plots/pump-curve", params={
            "pump_model": d["pump_model"],
            "operating_flow": d["flow_rate_achieved"],
            "stages": d["num_stages"],
        }).json()["figure"]
        textos = " | ".join(a.get("text", "") for a in
                            fig["layout"]["annotations"])
        assert "Zona operativa" not in textos
        assert "Rango operativo recomendado" in textos


class TestElDisenoConvencionalAvisaQueElPozoTieneGas:
    """La app detecta sola el gas libre; el usuario no tiene que ir a buscarlo.

    ``/api/design`` publica el veredicto del método (``gas_method``) y el de la
    escalera de manejo de gas (``design.gas_feasibility``). Los dos son
    **informativos**: la respuesta sigue siendo el diseño convencional,
    calculado exactamente igual que antes. Lo que cambia es que la pantalla
    puede avisar —y, si el usuario lo dejó activado, pasar sola al método de
    incrementos— en vez de exigir que alguien sospeche que hacía falta.
    """

    def test_con_gas_libre_el_metodo_por_incrementos_aplica(self, client):
        body = client.post("/api/design", json=_payload("oil")).json()
        gm = body["gas_method"]
        assert gm is not None
        assert gm["applies"] is True
        assert gm["free_gas_fraction"] > gm["threshold"]
        assert "incrementos de presión" in gm["reason"]

    def test_sin_gas_libre_no_aplica_y_nada_cambia(self, client):
        """Pozo de agua pura, GOR 0: el convencional es el que corresponde."""
        body = client.post("/api/design", json=_payload("high_rate")).json()
        gm = body["gas_method"]
        assert gm is not None
        assert gm["applies"] is False
        assert gm["free_gas_fraction"] <= gm["threshold"]

    def test_la_fraccion_publicada_es_LA_MISMA_con_que_se_diseno(self, client):
        """No se recalcula: sería otra cuenta y podría dar otro número.

        Si la decisión del método se tomara sobre una fracción distinta de la
        que eligió la correlación de fricción, la app podría avisar que hay gas
        y haber diseñado como si no lo hubiera (o al revés).
        """
        body = client.post("/api/design", json=_payload("oil")).json()
        diseño = body["recommendations"][0]["design"]
        assert body["gas_method"]["free_gas_fraction"] == diseño["gip_fraction"]

    def test_el_umbral_sigue_sin_poder_elegirse_por_la_API(self, client):
        """Se publica cuál fue, pero no se acepta uno distinto.

        Está prohibido exponerlo (``.claude/rules/domain.md``): lo que el
        usuario elige es el MÉTODO de pérdidas de carga, no el corte con que el
        programa decide solo.
        """
        payload = _payload("oil")
        payload["objectives"]["gas_fraction_pc_threshold"] = 0.99
        body = client.post("/api/design", json=payload).json()
        # El valor mandado se ignora: manda el default del dominio.
        assert body["gas_method"]["threshold"] == 0.01
        assert body["gas_method"]["applies"] is True

    def test_el_veredicto_de_la_escalera_viaja_por_el_camino_convencional(self, client):
        """Antes vivía sólo en /api/gas/design y la pestaña Diseño no lo tenía.

        La escalera se corre igual en los dos caminos —``_estrategia_de_gas``
        la llama el mismo ``_assemble_design``—, así que esconderla en uno de
        los dos era una asimetría de la pantalla, no del cálculo.
        """
        diseño = client.post(
            "/api/design", json=_payload("oil")
        ).json()["recommendations"][0]["design"]
        gf = diseño["gas_feasibility"]
        assert gf is not None
        # Las dos preguntas de cada escalón, cada una con su referencia.
        assert 0.0 < gf["capacity"] <= 1.0
        assert gf["tolerance"] > 0.0
        assert gf["strategy"] in ("ninguno", "simple", "tandem", "agh", "no_viable")
        assert gf["verdict"]
        # Y el resumen que ya se publicaba sigue coincidiendo con la escalera.
        assert diseño["gas_strategy"] == gf["strategy"]
        assert diseño["switch_lift_method"] == gf["switch_lift_method"]

    def test_el_mismo_esquema_que_usa_el_camino_de_gas(self):
        """Un esquema, no dos que se parecen.

        Si se hubiera creado un ``GasFeasibility`` paralelo para este camino,
        los dos podrían divergir campo a campo sin que nada falle.
        """
        from bes.api.schemas.analysis import GasCompleteDesignResponse
        from bes.api.schemas.outputs import DesignResultSchema

        del_gas = GasCompleteDesignResponse.model_fields["feasibility"].annotation
        del_convencional = DesignResultSchema.model_fields["gas_feasibility"].annotation
        assert del_gas.__name__ == "GasFeasibility"
        assert del_gas in getattr(del_convencional, "__args__", (del_convencional,))

    def test_un_diseno_sin_escalera_declara_ausencia_y_no_ceros(self, client):
        """``{}`` viaja como ``null``: la ausencia del dato no es "todo en cero".

        Un ``capacity`` en 0 se leería como "esta configuración no admite nada",
        que es una afirmación, no la falta de una.
        """
        import dataclasses

        from bes.api.deps import get_catalog
        from bes.api.mappers import from_design_result, to_domain_inputs
        from bes.api.schemas import DesignRequest
        from bes.core.models import DesignResult
        from bes.recommender.pump_selector import select_top_n_pumps

        # El dominio arranca en {}: la ausencia se representa vacía, no en cero.
        campo = next(
            f for f in dataclasses.fields(DesignResult) if f.name == "gas_feasibility"
        )
        assert campo.default_factory is dict

        req = DesignRequest(**_payload("oil"))
        dr = select_top_n_pumps(*to_domain_inputs(req), get_catalog(), n=1)[0]
        assert dr.gas_feasibility, "la escalera corrió: el dict no puede venir vacío"

        # Y un diseño sin escalera cruza el mapper como None, no como ceros.
        sin_escalera = dataclasses.replace(dr, gas_feasibility={})
        assert from_design_result(sin_escalera).gas_feasibility is None


class TestElModoEjemploSeAvisaEnLaPantalla:
    """Con ``max_gip`` en 100 % el resultado NO es un diseño real.

    Es el valor con que se reproducen los enunciados del libro que bombean todo
    el gas, y desactiva la verificación de viabilidad. La advertencia vivía en
    la escalera y la respuesta de ``/api/gas/design`` publicaba sólo las del
    cálculo hidráulico, así que nunca llegaba a la pantalla — justo la que no
    puede faltar, porque sin ella un modo ejemplo se lee como un diseño.
    """

    @staticmethod
    def _pozo_modo_ejemplo() -> dict:
        payload = copy.deepcopy(_WELLS["oil"])
        payload["objectives"]["max_gip"] = 1.0
        payload["increment_psi"] = 200.0
        return payload

    def test_la_advertencia_llega_en_la_respuesta_del_endpoint(self, client):
        r = client.post("/api/gas/design", json=self._pozo_modo_ejemplo())
        assert r.status_code == 200, r.text
        avisos = r.json()["warnings"]
        assert any("MODO EJEMPLO" in w for w in avisos), avisos

    def test_no_se_repite_el_mismo_aviso_dos_veces(self, client):
        """Las dos listas que se unen comparten avisos; duplicarlos les resta peso."""
        avisos = client.post(
            "/api/gas/design", json=self._pozo_modo_ejemplo()
        ).json()["warnings"]
        assert len(avisos) == len(set(avisos))

    def test_con_max_gip_normal_no_se_avisa_modo_ejemplo(self, client):
        payload = copy.deepcopy(_WELLS["oil"])
        payload["objectives"]["max_gip"] = 0.10
        payload["increment_psi"] = 200.0
        r = client.post("/api/gas/design", json=payload)
        if r.status_code == 200:
            assert not any("MODO EJEMPLO" in w for w in r.json()["warnings"])
        else:
            # Con el criterio real el pozo puede quedar inviable; lo que no
            # puede es pasar como diseño válido sin decir que es modo ejemplo.
            assert r.status_code == 422


class TestLaCapacidadDeLaConfiguracionEsUnNumero:
    """"Capacidad de esa configuración: NaN %" — el dato tiene que llegar.

    ``capacity`` responde la 1.ª pregunta de cada escalón (¿la configuración
    admite el gas que hay en la admisión?) y sale de Takács Fig. 4.25. Si no
    llega, la pantalla no puede decir por qué un pozo pasó o no pasó.
    """

    def test_llega_por_el_camino_de_gas(self, client):
        payload = copy.deepcopy(_WELLS["oil"])
        payload["objectives"]["max_gip"] = 1.0
        payload["increment_psi"] = 200.0
        cap = client.post("/api/gas/design", json=payload).json()["feasibility"]["capacity"]
        assert isinstance(cap, (int, float)) and 0.0 < cap <= 1.0

    def test_llega_tambien_por_el_camino_convencional(self, client):
        gf = client.post(
            "/api/design", json=_payload("oil")
        ).json()["recommendations"][0]["design"]["gas_feasibility"]
        assert gf is not None
        assert isinstance(gf["capacity"], (int, float)) and 0.0 < gf["capacity"] <= 1.0

    def test_el_contrato_publicado_lo_declara(self):
        """El front lo lee del contrato generado; si no está, llega undefined."""
        import json
        from pathlib import Path

        contrato = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"
        esquemas = json.loads(contrato.read_text(encoding="utf-8"))["components"]["schemas"]
        assert "capacity" in esquemas["GasFeasibility"]["properties"]


class TestCuandoNoHayAparejoElErrorDicePorQue:
    """Un 422 sin motivo no le sirve a nadie.

    El caso real es el Brown #3A: nueve bombas entran en el casing de 5½", el
    diseño hidráulico sale bien en las nueve, y ninguna completa el aparejo
    —REDA se queda sin motor porque el 456 no deja luz para el cable, y Wood
    Group no tiene motores cargados—. El usuario recibía «No complete ESP
    design could be assembled for the given conditions», en inglés y sin una
    sola pista de si el remedio era bajar el caudal, cambiar el casing o
    cambiar de proveedor.

    Los motivos ya se conocían: ``select_top_n_pumps`` los descartaba con un
    ``except ... continue``. Ahora se juntan y se publican, que es lo que el
    camino de gas ya hacía.
    """

    @staticmethod
    def _brown_3a() -> dict:
        """§4.53103 — casing 5½", 500 b/d de líquido con 50 % de agua, 7000 ft."""
        return {
            "reservoir": {
                "static_pressure": 1000.0, "bubble_point": 2000.0,
                "test_pwf": 800.0, "test_rate": 273.3333, "ipr_method": "vogel",
                "reservoir_temp": 160.0, "drive_mechanism": "solution_gas",
            },
            "fluid": {
                "oil_api": 35.0, "water_cut": 0.5, "gor": 500.0, "gas_sg": 0.65,
                "water_sg": 1.07, "oil_viscosity_dead": 5.0,
                "viscosity_temp_ref": 100.0, "bubble_point_pressure": 2000.0,
                "h2s_content": 0.0, "co2_content": 0.0, "sand_production": False,
            },
            "well": {
                "total_depth": 7000.0, "casing_od": 5.5, "casing_weight": 17.0,
                "casing_id": 4.892, "tubing_od": 2.375, "tubing_id": 1.995,
                "perforations_top": 6950.0, "perforations_bottom": 7000.0,
                "deviation_max": 0.0, "wellhead_temp": 120.0,
            },
            "surface": {
                "wellhead_pressure_required": 200.0, "flowline_length": 1000.0,
                "flowline_id": 3.0, "flowline_elevation_change": 0.0,
                "separator_pressure": 100.0, "power_supply_voltage": 4160.0,
                "frequency": 60.0,
            },
            "objectives": {
                "target_flow_rate": 500.0, "safety_margin_depth": 50.0,
                "allow_gas_venting": False, "max_gip": 1.0,
                "design_life_years": 5.0, "use_vsd": False,
            },
            "n": 3,
        }

    def test_el_422_explica_la_causa_y_no_solo_el_sintoma(self, client):
        r = client.post("/api/design", json=self._brown_3a())
        assert r.status_code == 422
        detalle = r.json()["detail"]
        # Cuántas bombas se intentaron, y por qué falló cada grupo.
        assert "completa el aparejo" in detalle
        assert "Motivos:" in detalle
        # La causa concreta: el motor que entra no da la potencia.
        assert "hp" in detalle and "casing" in detalle

    def test_el_mensaje_esta_en_castellano(self, client):
        """El tutor de la tesis lee la pantalla, no el código."""
        detalle = client.post("/api/design", json=self._brown_3a()).json()["detail"]
        assert "No complete ESP design" not in detalle
        assert "No motor found" not in detalle

    def test_la_misma_causa_no_se_repite_una_vez_por_bomba(self, client):
        """Cinco líneas iguales esconden que el motivo es uno solo."""
        detalle = client.post("/api/design", json=self._brown_3a()).json()["detail"]
        assert detalle.count("El motor más potente") == 1

    def test_un_proveedor_sin_motores_lo_dice_con_todas_las_letras(self, client):
        """Wood Group tiene bombas y ningún motor: es un estado conocido."""
        detalle = client.post("/api/design", json=self._brown_3a()).json()["detail"]
        assert "No hay motores de Wood Group ESP" in detalle

    def test_un_pozo_que_si_disena_sigue_diseñando(self, client):
        """El mensaje nuevo no puede haber convertido un éxito en un error."""
        r = client.post("/api/design", json=_payload("high_rate"))
        assert r.status_code == 200
        assert r.json()["recommendations"]
