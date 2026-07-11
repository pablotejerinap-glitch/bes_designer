"""API tests (FastAPI TestClient) for the BES Designer backend.

Exercises the request→domain→response contract end-to-end, including the
enum mapping and the ValueError→422 error contract.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app

_EXAMPLES = json.loads(
    (Path(__file__).resolve().parent.parent / "data" / "example_wells.json").read_text(encoding="utf-8")
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _payload(example_key: str = "example_1a", n: int = 3) -> dict:
    """Build a DesignRequest payload from a book example.

    The example JSON stores enum members as UPPERCASE names; the API speaks
    lowercase strings, so we normalize the two enum fields.
    """
    ex = copy.deepcopy(_EXAMPLES[example_key])
    res = ex["reservoir"]
    res["ipr_method"] = res["ipr_method"].lower()
    res["drive_mechanism"] = res["drive_mechanism"].lower()
    return {
        "reservoir":  res,
        "fluid":      ex["fluid"],
        "well":       ex["well"],
        "surface":    ex["surface"],
        "objectives": ex["objectives"],
        "n":          n,
    }


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


def test_design_example_1a(client: TestClient) -> None:
    r = client.post("/api/design", json=_payload("example_1a", n=3))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["recommendations"]) >= 1
    top = body["recommendations"][0]
    assert top["rank"] == 1
    assert top["design"]["pump_model"]           # non-empty
    assert top["design"]["num_stages"] > 0
    assert 0.0 <= top["design"]["pump_efficiency"] <= 1.0
    assert set(top["metrics"]) == {"efficiency", "flexibility", "provider"}
    assert "weights" in body and "design_basis" in body


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


def _nodal_payload(**over) -> dict:
    p = _payload()
    body = {"reservoir": p["reservoir"], "fluid": p["fluid"],
            "well": p["well"], "surface": p["surface"]}
    body.update(over)
    return body


def _assert_figure(fig: dict) -> None:
    assert "data" in fig and "layout" in fig  # valid Plotly figure JSON


def test_nodal_single(client: TestClient) -> None:
    r = client.post("/api/nodal", json=_nodal_payload(method="hagedorn_brown"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "single"
    assert set(body["metrics"]) == {
        "q_natural", "q_pump", "incremental_rate", "pwf_operating", "pump_efficiency"
    }
    _assert_figure(body["figure"])


def test_nodal_compare(client: TestClient) -> None:
    r = client.post("/api/nodal", json=_nodal_payload(compare_all=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "compare"
    assert len(body["comparison"]) == 4
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
