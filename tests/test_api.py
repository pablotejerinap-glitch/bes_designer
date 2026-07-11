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
