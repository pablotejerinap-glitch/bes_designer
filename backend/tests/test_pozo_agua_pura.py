"""Pozo de agua pura: el °API no se pide, y sobre todo no influye."""
import pytest
from fastapi.testclient import TestClient

from bes.api.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _pozo(**fluido):
    """Pozo de agua pura. El bloque `fluid` se arma con lo que se pase."""
    base = {
        "water_cut": 1.0, "gas_sg": 0.65, "water_sg": 1.05,
        "sand_production": False,
    }
    base.update(fluido)
    return {
        "reservoir": {
            "static_pressure": 2045.0, "bubble_point": 0.0, "test_pwf": 600.0,
            "test_rate": 800.0, "ipr_method": "vogel", "reservoir_temp": 185.0,
            "drive_mechanism": "solution_gas",
        },
        "fluid": base,
        "well": {
            "total_depth": 7500.0, "casing_od": 5.5, "casing_weight": 17.0,
            "casing_id": 4.892, "tubing_od": 2.875, "tubing_id": 2.441,
            "perforations_top": 7100.0, "perforations_bottom": 7500.0,
            "pump_setting_depth": 7000.0, "deviation_max": 0.0,
            "wellhead_temp": 100.0,
        },
        "surface": {
            "wellhead_pressure_required": 100.0, "flowline_length": 500.0,
            "flowline_id": 3.0, "flowline_elevation_change": 0.0,
            "separator_pressure": 50.0, "power_supply_voltage": 480.0,
            "frequency": 60.0,
        },
        "objectives": {
            "target_flow_rate": 800.0, "safety_margin_depth": 100.0,
            "allow_gas_venting": False, "design_life_years": 5.0,
            "use_vsd": False, "max_gip": 0.1,
        },
    }


class TestPozoDeAguaPura:
    """El tutor cargó un pozo de agua sola y la app le exigió un °API.

    Un pozo con corte de agua 1.0 no tiene petróleo, así que no tiene grado
    API, ni GOR, ni punto de burbuja. Pedirlos obliga a inventar números — y
    hasta septiembre de 2026 esos números inventados ENTRABAN a la cuenta.
    """

    def test_disena_sin_cargar_ninguna_propiedad_del_petroleo(self, client):
        r = client.post("/api/design", json=_pozo())
        assert r.status_code == 200, r.text
        assert r.json()["recommendations"]

    def test_con_petroleo_el_api_sigue_siendo_obligatorio(self, client):
        """La puerta se abre sólo para agua pura, no para todos."""
        p = _pozo(water_cut=0.45, gor=820.0, bubble_point_pressure=2500.0)
        p["reservoir"]["bubble_point"] = 2500.0
        r = client.post("/api/design", json=p)
        assert r.status_code == 422
        assert "oil_api es obligatoria" in r.text

    @pytest.mark.parametrize("api,gor", [
        (5.0, 820.0),     # crudo pesadísimo
        (10.0, 400.0),
        (30.0, 820.0),
        (70.0, 0.0),      # condensado
    ])
    def test_el_api_cargado_NO_puede_cambiar_el_diseno(self, client, api, gor):
        """El corazón del asunto, y la razón de que el relleno sea inocuo.

        Sin esto, un pozo de agua pura cargado con 5 °API salía con 480 etapas
        y 157.5 hp contra 443 y 66.5: un 137 % más de potencia por la
        corrección de viscosidad de un petróleo que no existe.
        """
        # El punto de burbuja NO se varía: es una propiedad del RESERVORIO que
        # entra a la IPR (Vogel parte la curva en Pb) y mueve la Pwf, así que
        # cambiarlo movería el diseño con petróleo o sin él. Lo que se está
        # probando es que las propiedades del PETRÓLEO no influyen.
        libre = client.post("/api/design", json=_pozo()).json()
        cargado = client.post(
            "/api/design", json=_pozo(oil_api=api, gor=gor)
        ).json()

        a = libre["recommendations"][0]["design"]
        b = cargado["recommendations"][0]["design"]
        assert b["pump_model"] == a["pump_model"]
        assert b["num_stages"] == a["num_stages"]
        assert b["total_pump_hp"] == pytest.approx(a["total_pump_hp"], rel=1e-9)
        assert b["total_head_required"] == pytest.approx(
            a["total_head_required"], rel=1e-9
        )

    def test_no_se_corrige_por_viscosidad(self, client):
        """Con agua no hay viscosidad de crudo que corregir."""
        from bes.core.viscosity import evaluate_viscosity
        v = evaluate_viscosity(
            oil_api=5.0, temp_f=185.0, rs_scf_bbl=0.0,
            pump_efficiency_pct=70.0, water_cut=1.0,
        )
        assert v["is_viscous"] is False
        # Los factores van en PORCENTAJE: 100 % es «no se corrige nada».
        assert v["capacity_factor"] == pytest.approx(100.0)
        assert v["head_factor"] == pytest.approx(100.0)
        assert v["oil_api"] is None
        assert "no produce petróleo" in v["reason"]
