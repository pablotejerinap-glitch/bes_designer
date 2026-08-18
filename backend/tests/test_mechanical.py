"""
Tests for core/mechanical.py — verificación del eje y del cojinete.

Fórmulas del apunte de cátedra, Unidad N°9 pág. 140:
    HP_eje   = P_etapa × #Etapas × Pem
    Carga TL = Ho × Pem × A_eje      (el × #Etapas impreso es un error; ver módulo)

Datos: hoja 'ENGINEERING DATA TD1750 50Hz' de Wood Group, serie 400.
"""
from __future__ import annotations

import math

import pytest

from bes.catalogs.loader import CatalogManager
from bes.core import mechanical as mx


@pytest.fixture(scope="module")
def series400() -> dict:
    s = CatalogManager().get_pump_series("400")
    assert s is not None, "la serie 400 tiene que estar en pump_series.json"
    return s


class TestSeriesCatalog:
    def test_sheet_values_are_transcribed_exactly(self, series400):
        """Las conversiones de la hoja dan valores redondos: 4.000 in, 5.500 in,
        11/16 in. Si alguno se desvía, se cargó mal."""
        assert series400["housing_diameter_in"] == pytest.approx(101.6 / 25.4)
        assert series400["min_casing_size_in"] == pytest.approx(139.7 / 25.4)
        assert series400["shaft_diameter_in"] == pytest.approx(17.463 / 25.4, abs=1e-4)
        assert series400["shaft_area_in2"] == pytest.approx(239.51 / 645.16, abs=1e-5)

    def test_published_area_matches_the_diameter(self, series400):
        """El fabricante publica ambos y tienen que cerrar entre sí."""
        d = series400["shaft_diameter_in"]
        assert mx.shaft_area_in2(series400) == pytest.approx(
            math.pi / 4 * d ** 2, rel=1e-3
        )

    def test_unknown_series_returns_none(self):
        """Sin ficha no se inventa nada: la verificación queda sin hacer."""
        assert CatalogManager().get_pump_series("513") is None


class TestShaftPower:
    def test_formula(self):
        assert mx.shaft_power(0.35, 250, 0.9) == pytest.approx(0.35 * 250 * 0.9)

    def test_scales_with_specific_gravity(self):
        """El hp/etapa del catálogo es para agua; el fluido real lo corrige."""
        assert mx.shaft_power(0.4, 100, 1.2) == pytest.approx(
            1.2 * mx.shaft_power(0.4, 100, 1.0)
        )

    def test_non_positive_returns_zero(self):
        assert mx.shaft_power(0.0, 250, 0.9) == 0.0
        assert mx.shaft_power(0.35, 0, 0.9) == 0.0


class TestShaftLimitFrequency:
    def test_limit_scales_linearly_with_frequency(self):
        """El eje aguanta un TORQUE; la potencia admisible va con la velocidad.
        Los 104 hp de la hoja son a 50 Hz."""
        assert mx.shaft_hp_limit_at_frequency(104.0, 50.0, 60.0) == pytest.approx(124.8)
        assert mx.shaft_hp_limit_at_frequency(104.0, 50.0, 50.0) == pytest.approx(104.0)

    def test_lower_frequency_lowers_the_limit(self):
        assert mx.shaft_hp_limit_at_frequency(104.0, 50.0, 40.0) == pytest.approx(83.2)

    def test_rejects_non_positive_frequency(self):
        with pytest.raises(ValueError, match="frequency_hz"):
            mx.shaft_hp_limit_at_frequency(104.0, 50.0, 0.0)


class TestVerifyShaft:
    def test_within_standard(self, series400):
        r = mx.verify_shaft(80.0, series400, 60.0)
        assert r["verified"] and r["ok"] and r["shaft_type"] == "standard"
        assert r["limit_std"] == pytest.approx(124.8)

    def test_between_standard_and_high_strength(self, series400):
        """Pasarse del estándar no es falla: pide eje de alta resistencia."""
        r = mx.verify_shaft(150.0, series400, 60.0)
        assert r["ok"] and r["shaft_type"] == "high_strength"
        assert "alta resistencia" in r["note"]

    def test_above_high_strength_fails(self, series400):
        r = mx.verify_shaft(250.0, series400, 60.0)
        assert not r["ok"] and r["shaft_type"] == ""

    def test_frequency_moves_the_verdict(self, series400):
        """105 hp entra a 60 Hz (límite 124.8) pero no a 50 (límite 104)."""
        assert mx.verify_shaft(105.0, series400, 60.0)["shaft_type"] == "standard"
        assert mx.verify_shaft(105.0, series400, 50.0)["shaft_type"] == "high_strength"

    def test_unknown_series_is_not_verified_but_does_not_fail(self):
        r = mx.verify_shaft(500.0, None, 60.0)
        assert r["verified"] is False and r["ok"] is True
        assert "no pudo realizarse" in r["note"]


class TestBearingLoad:
    def test_formula_without_the_stage_factor(self, series400):
        """Carga TL = Ho × Pem × A_eje. En unidades de campo la columna en pies
        se vuelve presión con la constante 2.31."""
        a = mx.shaft_area_in2(series400)
        got = mx.bearing_load_tl(4900.0, 0.9, a)
        assert got == pytest.approx(4900.0 * 0.9 / 2.31 * a)

    def test_magnitude_is_compatible_with_real_seals(self, series400):
        """El chequeo que descarta la lectura literal del apunte: multiplicar
        por las etapas daría ~200 000 lbs contra sellos de 5 000–30 000 lbs."""
        load = mx.bearing_load_tl(4900.0, 0.9, mx.shaft_area_in2(series400))
        assert 100.0 < load < 5000.0

    def test_kg_conversion(self, series400):
        a = mx.shaft_area_in2(series400)
        assert mx.bearing_load_tl(4900.0, 0.9, a) / mx.bearing_load_kg(
            4900.0, 0.9, a
        ) == pytest.approx(2.2046, rel=1e-3)

    def test_non_positive_returns_zero(self, series400):
        assert mx.bearing_load_tl(0.0, 0.9, 0.37) == 0.0


class TestVerifyBearing:
    def test_within_standard(self, series400):
        r = mx.verify_bearing_staging(250, 200.0, series400)
        assert r["ok"] and r["bearing_type"] == "standard"
        assert r["limit_stages"] == 303 and r["bht_max_f"] == pytest.approx(230.0)

    def test_too_many_stages_moves_to_high_load(self, series400):
        r = mx.verify_bearing_staging(400, 200.0, series400)
        assert r["ok"] and r["bearing_type"] == "high_load"
        assert r["limit_stages"] == 1529

    def test_temperature_alone_moves_to_high_load(self, series400):
        """La temperatura manda aunque las etapas entren en el estándar: el
        material del cojinete pierde capacidad con el calor."""
        r = mx.verify_bearing_staging(100, 240.0, series400)
        assert r["ok"] and r["bearing_type"] == "high_load"
        assert "temperatura" in r["note"]

    def test_above_every_bearing_temperature_fails(self, series400):
        r = mx.verify_bearing_staging(100, 300.0, series400)
        assert not r["ok"] and "Temperatura" in r["note"]

    def test_above_high_load_staging_fails(self, series400):
        r = mx.verify_bearing_staging(2000, 200.0, series400)
        assert not r["ok"]

    def test_unknown_series_is_not_verified(self):
        r = mx.verify_bearing_staging(9999, 400.0, None)
        assert r["verified"] is False and r["ok"] is True


class TestStagingCeiling:
    """La nota al pie del fabricante: el tope de etapas lo fija la presión de
    carcasa, la capacidad del eje o la carga sobre el cojinete — el menor."""

    def test_the_lowest_ceiling_governs(self, series400):
        c = mx.staging_ceiling(
            hp_per_stage=0.35, shutin_head_per_stage=39.9, pem=0.9,
            bottom_hole_temp_f=200.0, housing_limit_psi=5000.0,
            series=series400, frequency_hz=60.0,
        )
        assert c["governing"] == min(
            c["by_housing_pressure"], c["by_shaft"], c["by_bearing"]
        )
        assert c["governing_by"] in {"by_housing_pressure", "by_shaft", "by_bearing"}

    def test_housing_ceiling_inverts_the_maxp_formula(self, series400):
        n = mx.max_stages_by_housing_pressure(40.0, 1.0, 5000.0)
        assert n == int(5000.0 // (40.0 / 2.31))

    def test_shaft_ceiling_uses_the_high_strength_limit(self, series400):
        n = mx.max_stages_by_shaft(0.35, 0.9, series400, 60.0)
        assert n == int(200.4 // (0.35 * 0.9))

    def test_missing_data_reports_zero_and_is_excluded(self):
        c = mx.staging_ceiling(0.35, 39.9, 0.9, 200.0, 0.0, None, 60.0)
        assert c["by_housing_pressure"] == 0
        assert c["by_shaft"] == 0 and c["by_bearing"] == 0
        assert c["governing"] == 0 and c["governing_by"] == ""

    def test_hot_well_leaves_no_admissible_bearing(self, series400):
        assert mx.max_stages_by_bearing(300.0, series400) == 0
