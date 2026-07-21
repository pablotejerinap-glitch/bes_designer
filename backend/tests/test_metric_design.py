"""
Per-step unit tests for the metric ESP design path (core/metric_design.py).

Each of the 17 steps of the método de cátedra "ESP 01" is exercised in
isolation.  The end-to-end regression lives in tests/test_esp01.py.
"""
from __future__ import annotations

import pytest

from bes.catalogs.metric_loader import MetricCatalog
from bes.core import units
from bes.core.metric_design import (
    step1_admissible_pressure,
    step2_qmax,
    step3_production,
    read_pump_curve_metric,
    step6_tubing_friction,
    step7_pip_at_suction,
    step8_tdh,
    step9_stages,
    select_housings,
    step11_housing_burst,
    step12_pump_hp_and_shaft,
    select_motors,
    fluid_velocity_past_motor,
    select_protector,
    select_cable,
)

PEM = 1.0629  # ESP 01 mixture gravity


@pytest.fixture(scope="module")
def catalog() -> MetricCatalog:
    return MetricCatalog()


@pytest.fixture(scope="module")
def td2200(catalog: MetricCatalog) -> dict:
    return catalog.get_pump("TD-2200")


# ---------------------------------------------------------------------------
# Step 1 — admissible pressure at reference depth
# ---------------------------------------------------------------------------

class TestStep1:
    def test_delta_and_padm(self):
        delta, padm = step1_admissible_pressure(PEM, 2400, 2250, 15)
        assert delta == pytest.approx(15.94, abs=0.1)   # ≈ 16 kg/cm²
        assert padm == pytest.approx(30.94, abs=0.1)    # ≈ 31 kg/cm²


# ---------------------------------------------------------------------------
# Step 2 — reservoir Qmax (Vogel from test)
# ---------------------------------------------------------------------------

class TestStep2:
    def test_qmax(self):
        ratio, qmax = step2_qmax(170, 50, 260)
        assert ratio == pytest.approx(0.872, abs=0.005)
        assert qmax == pytest.approx(298.0, abs=2.0)


# ---------------------------------------------------------------------------
# Step 3 — production at admissible pressure
# ---------------------------------------------------------------------------

class TestStep3:
    def test_production_pwf31(self):
        _, qmax = step2_qmax(170, 50, 260)
        ratio, q = step3_production(170, 30.94, qmax)
        assert ratio == pytest.approx(0.937, abs=0.005)
        assert q == pytest.approx(279.4, abs=3.0)

    def test_pwf30_slightly_higher(self):
        # §7-A: the lámina computes with 30 instead of 31 -> a touch more rate.
        _, qmax = step2_qmax(170, 50, 260)
        _, q31 = step3_production(170, 31.0, qmax)
        _, q30 = step3_production(170, 30.0, qmax)
        assert q30 > q31
        assert q30 == pytest.approx(280, abs=2)
        assert q31 == pytest.approx(279, abs=2)


# ---------------------------------------------------------------------------
# Steps 4–5 — pump curve read with affinity correction
# ---------------------------------------------------------------------------

class TestReadPumpCurve:
    def test_td2200_60hz_read_at_50hz(self, td2200: dict):
        r = read_pump_curve_metric(td2200, f_op_hz=50.0, q_op_m3d=279.4)
        # enters the 60 Hz curve at 279.4·1.2 ≈ 335 m³/d
        assert r["q_catalog_m3d"] == pytest.approx(335.3, abs=0.5)
        assert r["head_per_stage_m"] == pytest.approx(5.49, abs=0.1)
        assert r["hp_per_stage"] == pytest.approx(0.35, abs=0.02)
        assert r["shutin_head_m"] == pytest.approx(7.0, abs=0.3)

    def test_td3000_50hz_direct(self, catalog: MetricCatalog):
        td3000 = catalog.get_pump("TD-3000")
        r = read_pump_curve_metric(td3000, f_op_hz=50.0, q_op_m3d=279.4)
        # curve already at 50 Hz -> read directly (no affinity shift)
        assert r["q_catalog_m3d"] == pytest.approx(279.4, abs=0.5)
        assert r["head_per_stage_m"] == pytest.approx(4.62, abs=0.1)
        assert r["hp_per_stage"] == pytest.approx(0.38, abs=0.02)
        assert r["efficiency"] == pytest.approx(0.60, abs=0.02)


# ---------------------------------------------------------------------------
# Step 6 — tubing friction (metric Hazen-Williams)
# ---------------------------------------------------------------------------

class TestStep6:
    def test_friction(self):
        f_unit, tf = step6_tubing_friction(279.4, 2.441, 2250, c_factor=95)
        assert f_unit == pytest.approx(43.5, abs=1.0)   # m per 1000 m
        assert tf == pytest.approx(98.0, abs=3.0)        # total m


# ---------------------------------------------------------------------------
# Step 7 — PIP at suction depth
# ---------------------------------------------------------------------------

class TestStep7:
    def test_pip(self):
        pip = step7_pip_at_suction(30.94, 2400, 2250, PEM)
        assert pip == pytest.approx(15.0, abs=0.5)


# ---------------------------------------------------------------------------
# Step 8 — TDH
# ---------------------------------------------------------------------------

class TestStep8:
    def test_tdh_arithmetic(self):
        tdh, comp = step8_tdh(2250, 98.3, 10.0, 15.0, PEM)
        assert tdh == pytest.approx(2301, abs=5)
        assert comp["discharge_head_m"] == pytest.approx(94.1, abs=0.3)
        assert comp["pip_head_m"] == pytest.approx(141.1, abs=0.3)


# ---------------------------------------------------------------------------
# Step 9 — stages
# ---------------------------------------------------------------------------

class TestStep9:
    def test_stages_ceil(self):
        assert step9_stages(2301.2, 5.487) == 420

    def test_rejects_zero_head(self):
        with pytest.raises(ValueError):
            step9_stages(2301, 0.0)


# ---------------------------------------------------------------------------
# Step 10 — housing selection
# ---------------------------------------------------------------------------

class TestStep10:
    HS = {"7": 58, "10": 84, "11": 92, "15": 125}

    def test_420_is_five_of_10(self):
        housings, total = select_housings(420, self.HS)
        assert total == 420
        assert dict((str(h), c) for h, c in housings) == {"10": 5}

    def test_428_matches_catedra(self):
        # target 428 (the lámina TDH) -> 4×#10 + 1×#11
        housings, total = select_housings(428, self.HS)
        assert total == 428
        assert dict((str(h), c) for h, c in housings) == {"10": 4, "11": 1}

    def test_small_target(self):
        housings, total = select_housings(100, self.HS)
        assert total >= 100


# ---------------------------------------------------------------------------
# Step 11 — housing burst check
# ---------------------------------------------------------------------------

class TestStep11:
    def test_mhp_standard(self, td2200: dict):
        mhp, rating, limit = step11_housing_burst(6.944, 420, PEM, td2200)
        assert mhp == pytest.approx(4404, abs=50)
        assert rating == "Standard"
        assert limit == 5000


# ---------------------------------------------------------------------------
# Step 12 — pump HP and per-housing shaft check
# ---------------------------------------------------------------------------

class TestStep12:
    HS = {"10": 84, "11": 92}

    def test_hp_and_two_hr_sections(self):
        housings = [("10", 5)]
        total_hp, sections, n_hr = step12_pump_hp_and_shaft(
            0.3473, PEM, housings, self.HS, shaft_limit_std=104
        )
        assert total_hp == pytest.approx(155, abs=3)
        # bottom section carries full HP, top carries least
        assert sections[0]["cumulative_shaft_hp"] > sections[-1]["cumulative_shaft_hp"]
        assert n_hr == 2   # "dos bombas con eje de alta resistencia" (§7-C)


# ---------------------------------------------------------------------------
# Step 13 — motor selection
# ---------------------------------------------------------------------------

class TestStep13:
    def test_tandem_pair(self, catalog: MetricCatalog):
        sel = select_motors(catalog, required_hp=155.0)
        hps = sorted(m["hp_rating"] for m in sel["motors"])
        assert hps == [58.5, 100.0]
        assert sel["total_voltage"] == 2142
        assert sel["total_hp"] == pytest.approx(158.5)
        assert sel["string_amps"] == 47


# ---------------------------------------------------------------------------
# Step 14 — fluid velocity past the motor
# ---------------------------------------------------------------------------

class TestStep14:
    def test_velocity_positive_and_cools(self):
        v = fluid_velocity_past_motor(279.4, casing_id_in=4.778, motor_od_in=4.0)
        assert v > 1.0   # cooling requirement met

    def test_rejects_oversize_motor(self):
        with pytest.raises(ValueError):
            fluid_velocity_past_motor(279.4, casing_id_in=4.0, motor_od_in=4.5)


# ---------------------------------------------------------------------------
# Step 15 — protector selection
# ---------------------------------------------------------------------------

class TestStep15:
    def test_high_load_for_many_stages(self, catalog: MetricCatalog):
        sel = select_protector(catalog, 420)
        assert sel["seal"]["bearing"] == "high_load"
        assert sel["qty"] == 2

    def test_standard_for_few_stages(self, catalog: MetricCatalog):
        sel = select_protector(catalog, 200)
        assert sel["seal"]["bearing"] == "floater_std"
        assert sel["qty"] == 1


# ---------------------------------------------------------------------------
# Step 16 — cable selection
# ---------------------------------------------------------------------------

class TestStep16:
    def test_selects_number4_and_drop(self, catalog: MetricCatalog):
        sel = select_cable(catalog, current_a=47, length_m=2250, ambient_temp_c=95)
        assert sel["cable"]["size"] == "#4"
        assert sel["temp_factor"] == pytest.approx(1.20, abs=0.01)
        assert sel["total_drop_v"] == pytest.approx(189, abs=5)
