"""
End-to-end regression test for the metric ESP design — ejercicio "ESP 01".

Reproduces the resolution table (§6 of docs/EJEMPLO_ESP01.md) within the stated
tolerances.  Per the §7-B decision, the TDH is ANCHORED on the arithmetically
correct value (~2301 m) that the exercise's own formula yields with the given
data; the cátedra lámina value (2347 m) is exposed only as an informative
reference (``tdh_reference_m``) and is not asserted as truth.  All downstream
quantities (stages, housings, MHP, HP) therefore follow from ~2301 m and are
asserted at their computed, self-consistent values.
"""
from __future__ import annotations

import pytest

from bes.catalogs.metric_loader import MetricCatalog
from bes.core.metric_design import design_esp_metric, MetricDesignInput


@pytest.fixture(scope="module")
def catalog() -> MetricCatalog:
    return MetricCatalog()


@pytest.fixture(scope="module")
def esp01_input() -> MetricDesignInput:
    return MetricDesignInput(
        casing_od_in=5.5, casing_weight_lbft=20, casing_id_in=4.778, tubing_id_in=2.441,
        perf_top_m=2300, perf_bottom_m=2500, ref_depth_m=2400, total_depth_m=2600,
        suction_depth_m=2250,
        casing_head_pressure_kgcm2=10, discharge_pressure_kgcm2=10,
        q_test_m3d=260, pwf_test_kgcm2=50, reservoir_pressure_kgcm2=170, temp_bottom_c=95,
        water_cut=0.91, gor_m3m3=50, q_target_m3d=300, pip_expected_kgcm2=15,
        oil_api=28, oil_sg=0.89, gas_sg=0.65, water_sg=1.08, bubble_point_kgcm2=170,
        viscosity_cp=7.0, frequency_hz=50,
    )


@pytest.fixture(scope="module")
def result(esp01_input, catalog):
    return design_esp_metric(esp01_input, catalog, pump_model="TD-2200")


# ---------------------------------------------------------------------------
# §6 regression table
# ---------------------------------------------------------------------------

class TestFluidAndPressures:
    def test_pem_mixture(self, result):
        assert result.pem_gcc == pytest.approx(1.0629, abs=0.001)

    def test_delta_p_ref(self, result):
        assert result.delta_p_ref_kgcm2 == pytest.approx(16.0, abs=0.5)

    def test_padm_ref(self, result):
        assert result.padm_ref_kgcm2 == pytest.approx(31.0, abs=0.5)


class TestInflow:
    def test_vogel_ratio_test(self, result):
        assert result.vogel_ratio_test == pytest.approx(0.872, abs=0.005)

    def test_qmax(self, result):
        assert result.qmax_m3d == pytest.approx(298.0, abs=2.0)

    def test_q_production(self, result):
        assert result.q_prod_m3d == pytest.approx(279.5, abs=3.0)


class TestPumpCurveRead:
    def test_head_per_stage(self, result):
        assert result.head_per_stage_m == pytest.approx(5.49, abs=0.1)

    def test_hp_per_stage(self, result):
        assert result.hp_per_stage == pytest.approx(0.35, abs=0.02)

    def test_shutin_head(self, result):
        assert result.shutin_head_m == pytest.approx(7.0, abs=0.3)


class TestFrictionAndPip:
    def test_friction_unit(self, result):
        assert result.friction_unit_m_per_1000m == pytest.approx(43.5, abs=1.0)

    def test_friction_total(self, result):
        assert result.friction_total_m == pytest.approx(98.0, abs=3.0)

    def test_pip_suction(self, result):
        assert result.pip_suction_kgcm2 == pytest.approx(15.0, abs=0.5)


class TestTDH:
    def test_tdh_anchored_on_computed(self, result):
        # §7-B: anchor on the arithmetically correct value, not the lámina.
        assert result.tdh_m == pytest.approx(2301, abs=5)

    def test_catedra_reference_exposed(self, result):
        assert result.tdh_reference_m == 2347.0

    def test_components(self, result):
        c = result.tdh_components
        assert c["suction_depth_m"] == 2250
        assert c["discharge_head_m"] == pytest.approx(94.1, abs=0.3)
        assert c["pip_head_m"] == pytest.approx(141.1, abs=0.3)


class TestStagesAndHousings:
    def test_num_stages(self, result):
        # 2301 / 5.49 -> 420 (self-consistent with the anchored TDH)
        assert result.num_stages == 420

    def test_housings(self, result):
        assert dict((str(h), c) for h, c in result.housings) == {"10": 5}
        assert result.housing_stages_total == 420


class TestHousingBurst:
    def test_mhp(self, result):
        assert result.mhp_psi == pytest.approx(4404, abs=50)

    def test_rating_standard(self, result):
        assert result.housing_rating == "Standard"
        assert result.mhp_psi < result.housing_pressure_limit_psi


class TestMotorPower:
    def test_pump_hp(self, result):
        assert result.pump_hp == pytest.approx(155, abs=3)

    def test_two_high_resistance_housings(self, result):
        # §7-C: dos housings con eje de alta resistencia, el resto estándar.
        assert result.n_high_resistance_housings == 2
        std = [s for s in result.shaft_sections if s["shaft"] == "STD"]
        assert len(std) == 3


class TestMotorsAndVoltage:
    def test_motor_pair(self, result):
        combos = {(m["hp_rating"], m["voltage"]) for m in result.motors}
        assert combos == {(100.0, 1354), (58.5, 788)}

    def test_motor_voltage_total(self, result):
        assert result.motor_voltage_total_v == pytest.approx(2142, abs=5)

    def test_string_amps_compatible(self, result):
        assert result.motor_string_amps == pytest.approx(47, abs=1)


class TestCooling:
    def test_velocity_meets_requirement(self, result):
        assert result.fluid_velocity_ft_s >= 1.0
        assert result.cooling_ok is True

    def test_reference_exposed(self, result):
        assert result.fluid_velocity_reference_ft_s == 4.75


class TestProtector:
    def test_two_high_load_protectors(self, result):
        assert result.protector_type == "labyrinth"
        assert "HL-400" in result.protector_model
        assert result.protector_qty == 2


class TestCable:
    def test_number4_copper(self, result):
        assert result.cable_size == "#4"
        assert result.cable_conductor == "CU"

    def test_cable_drop(self, result):
        assert result.cable_drop_v == pytest.approx(189, abs=5)


class TestSurfaceVoltage:
    def test_surface_voltage(self, result):
        assert result.surface_voltage_v == pytest.approx(2331, abs=5)


# ---------------------------------------------------------------------------
# Candidate handling / §7-A
# ---------------------------------------------------------------------------

class TestCandidates:
    def test_auto_selects_td2200(self, esp01_input, catalog):
        # TD-3000 has lower head/stage -> more stages -> not the primary pick.
        r = design_esp_metric(esp01_input, catalog)
        assert r.pump_model == "TD-2200"
        assert any("TD-3000" in a for a in r.alternatives)

    def test_pwf30_variant(self, esp01_input, catalog):
        # §7-A: computing step 3 with 30 instead of 31 yields a touch more rate,
        # but both round to ~279–280 m³/d.
        r31 = design_esp_metric(esp01_input, catalog, pump_model="TD-2200")
        r30 = design_esp_metric(
            esp01_input, catalog, pump_model="TD-2200", production_pwf_kgcm2=30
        )
        assert r30.q_prod_m3d > r31.q_prod_m3d
        assert r30.q_prod_m3d == pytest.approx(280, abs=2)
