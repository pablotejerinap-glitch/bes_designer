"""Memoria de cálculo paso a paso (bes.reports.memoria y sus endpoints)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bes.api.main import app

CASOS = json.loads((Path(__file__).parent / "data" / "memoria_casos.json").read_text(encoding="utf-8"))

_VOGEL_EJ8 = {"static_pressure": 4000.0, "bubble_point": 3000.0, "test_pwf": 2000.0, "test_rate": 600.0,
              "ipr_method": "vogel", "reservoir_temp": 180.0, "drive_mechanism": "solution_gas"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# Pozo «Facultad 01» de la tesis Inv_83338: el caso con gas de la memoria nueva.
POZO_GAS = {
    "reservoir": {"static_pressure": 888.617, "bubble_point": 1863.26, "test_pwf": 842.053,
                  "test_rate": 691.82, "ipr_method": "vogel", "reservoir_temp": 197.6,
                  "drive_mechanism": "solution_gas"},
    "fluid": {"oil_api": 21, "water_cut": 0.89, "gor": 67.4, "gas_sg": 0.65, "water_sg": 1.012,
              "bubble_point_pressure": 1863.26},
    "well": {"total_depth": 7391.71, "casing_od": 5.5, "casing_weight": 15.5, "casing_id": 5.012,
             "tubing_od": 2.875, "tubing_id": 2.441, "perforations_top": 7341.71,
             "perforations_bottom": 7391.71, "deviation_max": 0, "wellhead_temp": 60,
             "pump_setting_depth": 6686.332},
    "surface": {"wellhead_pressure_required": 100, "flowline_length": 1000, "flowline_id": 4,
                "flowline_elevation_change": 0, "separator_pressure": 100,
                "power_supply_voltage": 4160, "frequency": 50},
    "objectives": {"target_flow_rate": 4070.70, "safety_margin_depth": 0, "allow_gas_venting": False,
                   "max_gip": 1.0, "design_life_years": 5, "use_vsd": False},
}


@pytest.fixture(scope="module")
def htmls(client) -> dict[str, str]:
    out = {}
    for k, c in CASOS.items():
        if c["gas"]:
            url, body = "/api/gas/memoria", {**POZO_GAS, "titulo": f"Caso {k}"}
        else:
            url, body = "/api/reports/memoria", {**c["pozo"], "titulo": f"Caso {k}"}
        r = client.post(url, json=body)
        assert r.status_code == 200, r.text[:500]
        assert r.headers["content-type"].startswith("text/html")
        out[k] = r.text
    return out


def _pasos(html: str) -> list[str]:
    return re.findall(r'<span class="num">\d+</span>([^<]+)</div>', html)


_APAREJO = ("SELECCIÓN DEL MOTOR", "VERIFICACIÓN DEL EJE", "SELLO / PROTECTOR Y EMPUJE AXIAL",
            "SELECCIÓN DEL CABLE DE POTENCIA", "VERIFICACIÓN ELÉCTRICA DEL CABLE",
            "REFRIGERACIÓN DEL MOTOR", "TENSIÓN DE SUPERFICIE, TRANSFORMADOR Y TABLERO",
            "CARCASAS Y COJINETES")


class TestModeloDeLaMemoria:
    def test_agua_sigue_el_camino_convencional(self, htmls):
        p = _pasos(htmls["A"])
        assert p[:4] == ["CÁLCULO DE IPR", "PRESIÓN EN LA ADMISIÓN (PIP)", "PÉRDIDAS DE CARGA Y TDH",
                         "SELECCIÓN DE LA BOMBA SOBRE LA CURVA"]
        assert all(t in p for t in _APAREJO)
        assert "GAS LIBRE Y ESCALERA DE INCREMENTOS" not in p
        assert "CORRECCIÓN POR VISCOSIDAD (RILING)" not in p
        assert "CASO A" in htmls["A"]

    def test_gas_sigue_el_metodo_paso_a_paso(self, htmls):
        h = htmls["C"]
        for t in ("1. IPR", "4c. Separador", "5. Presión de descarga", "7. Incrementos de presión",
                  "8. Eje, presión de carcasa", "9. Protector", "10. Motor", "11. Cable",
                  "12. Tablero y transformador", "Evolución del fluido en el pozo",
                  "Escalones de presión dentro de la bomba", "Resumen del diseño", "Datos de entrada"):
            assert t in h, t
        assert "REDA D5800N" in h and "FixStar 3900-70" in h

    def test_gas_sin_datos_de_catalogo_da_422_con_el_motivo(self, client):
        body = {**CASOS["C"]["pozo"], "increment_psi": 200}
        body["well"] = {**body["well"], "pump_setting_depth": 7900}
        r = client.post("/api/gas/memoria", json=body)
        # Cada candidata se rechaza con su motivo. Las Wood Group ya no caen por
        # «límites mecánicos»: los toman de la ficha de su serie (misma marca).
        assert r.status_code == 422 and "Ninguna bomba candidata completa el aparejo" in r.text
        assert "TD-1750: La bomba TD-1750 no tiene los límites mecánicos" not in r.text

    def test_viscoso_trae_riling(self, htmls):
        p = _pasos(htmls["D"])
        assert "CORRECCIÓN POR VISCOSIDAD (RILING)" in p
        assert all(t in p for t in _APAREJO)

    def test_viscoso_muestra_las_cartas_4l_marcadas(self, htmls):
        """Las dos láminas de Brown aparecen redibujadas con la lectura del pozo."""
        html = htmls["D"]
        assert "lectura en la Fig. 4L(2)" in html
        assert "lectura en la Fig. 4L(1)" in html

    def test_sin_notas_ni_avisos(self, htmls):
        for h in htmls.values():
            assert 'class="nota"' not in h and 'class="alerta"' not in h and "eq-note" not in h

    def test_las_citas_de_libros_llevan_pagina(self, htmls):
        for h in htmls.values():
            for ref in re.findall(r'<div class="eq-ref">(.*?)</div>', h):
                if ref.startswith(("Brown", "Takács", "Ahmed", "Beggs")):
                    assert "pág" in ref, ref
            assert "§" not in h and "Swamee" not in h


class TestIPR:
    def test_vogel_compuesta_coincide_con_la_app(self):
        from bes.api.mappers import to_reservoir
        from bes.api.schemas.inputs import ReservoirSchema
        from bes.core.ipr import calculate_pwf_for_target_rate
        from bes.reports.memoria.render import bloque_ipr
        for q in (150.0, 700.0):
            _, pwf, curva, _ = bloque_ipr({"pozo": {"reservoir": _VOGEL_EJ8,
                                                    "objectives": {"target_flow_rate": q}}})
            app_pwf = calculate_pwf_for_target_rate(to_reservoir(ReservoirSchema(**_VOGEL_EJ8)), q)
            assert pwf == pytest.approx(app_pwf, abs=0.05)
            assert curva(pwf) == pytest.approx(q, rel=1e-6)

    def test_ejemplo_8_de_brown_vol_4(self):
        """Brown Vol. 4, Ejemplo #8 (pág. 16): q = 162 b/d a 3500 psi y 780 b/d a 1000 psi."""
        from bes.reports.memoria.render import bloque_ipr
        _, _, curva, _ = bloque_ipr({"pozo": {"reservoir": _VOGEL_EJ8,
                                              "objectives": {"target_flow_rate": 500.0}}})
        assert curva(3500.0) == pytest.approx(162, abs=1)
        assert curva(1000.0) == pytest.approx(780, abs=2)

    def test_fetkovich(self):
        from bes.reports.memoria.render import bloque_ipr
        res = {"static_pressure": 2000.0, "bubble_point": 0.0, "test_pwf": 1500.0, "test_rate": 500.0,
               "ipr_method": "fetkovich", "fetkovich_n": 0.8, "reservoir_temp": 150.0,
               "drive_mechanism": "solution_gas"}
        _, pwf, curva, _ = bloque_ipr({"pozo": {"reservoir": res, "objectives": {"target_flow_rate": 400.0}}})
        assert curva(pwf) == pytest.approx(400.0, rel=1e-9)


def test_pdf_o_aviso_claro(client):
    r = client.post("/api/reports/memoria?formato=pdf", json=CASOS["B"]["pozo"])
    assert r.status_code in (200, 501)
    if r.status_code == 200:
        assert r.content[:4] == b"%PDF"


def test_formato_desconocido_404(client):
    r = client.post("/api/reports/memoria?formato=docx", json=CASOS["B"]["pozo"])
    assert r.status_code == 404


def test_los_reportes_de_siempre_siguen_andando(client):
    r = client.post("/api/reports/xlsx", json=CASOS["B"]["pozo"])
    assert r.status_code == 200
