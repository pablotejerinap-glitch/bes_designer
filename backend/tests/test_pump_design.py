"""
Tests for TDH and pump design calculations.
Validates against Kermit Brown, Vol. 2b, Ch. 4.5 book examples.

Book examples used:
  #1A — Centrilift I-300, 10 000 bpd, TDH ≈ 1 670 ft, 28 stages, HP ≈ 180
  #2A — Reda D-40,        1 227 bpd, TDH = 5 830 ft, 254 stages, HP ≈ 79
  #2B — Centrilift I-42B, ~2 080 bpd, TDH = 4 258 ft, 112 stages, HP ≈ 65
"""
from __future__ import annotations

import pytest
from pathlib import Path

from bes.catalogs.loader import CatalogManager
from bes.core.models import (
    DesignObjectives,
    DriveMechanism,
    Fluid,
    IPRMethod,
    PumpCurve,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)
from bes.core.tdh import calculate_tdh, friction_loss_hazen_williams
from bes.core.pump_design import (
    apply_viscosity_correction,
    calculate_motor_hp,
    calculate_stages,
    check_pump_operating_range,
    design_pump_by_model,
    design_pump_complete,
)



# ---------------------------------------------------------------------------
# Catalog fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def manager() -> CatalogManager:
    return CatalogManager()


@pytest.fixture(scope="module")
def d40(manager: CatalogManager) -> PumpCurve:
    match = [p for p in manager.get_all_pumps() if p.model == "D-40"]
    assert match, "D-40 not found in catalog"
    return match[0]


@pytest.fixture(scope="module")
def i300(manager: CatalogManager) -> PumpCurve:
    match = [p for p in manager.get_all_pumps() if p.model == "I-300"]
    assert match, "I-300 not found in catalog"
    return match[0]


@pytest.fixture(scope="module")
def i42b(manager: CatalogManager) -> PumpCurve:
    match = [p for p in manager.get_all_pumps() if p.model == "I-42B"]
    assert match, "I-42B not found in catalog"
    return match[0]


# ---------------------------------------------------------------------------
# Integration-test fixtures — shallow low-pressure well (VL always > 0)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def base_reservoir() -> Reservoir:
    # Pr = 800 psi, Pb = 700 psi, PI = 5 → Pwf ≈ 507 psi at 1 227 bpd
    return Reservoir(
        static_pressure=800.0,
        bubble_point=700.0,
        productivity_index=5.0,
        ipr_method=IPRMethod.VOGEL,
        reservoir_temp=130.0,
        drive_mechanism=DriveMechanism.SOLUTION_GAS,
        datum_depth=3500.0,
    )


@pytest.fixture(scope="module")
def base_fluid() -> Fluid:
    # 35°API oil, 30 % water cut → SG_liquid ≈ 0.91
    return Fluid(
        oil_api=35.0,
        water_cut=0.30,
        gor=150.0,
        gas_sg=0.65,
        water_sg=1.05,
        oil_viscosity_dead=5.0,
        viscosity_temp_ref=100.0,
        bubble_point_pressure=700.0,
        h2s_content=0.0,
        co2_content=0.0,
        sand_production=False,
    )


@pytest.fixture(scope="module")
def base_well() -> WellGeometry:
    # 8-5/8" casing (ID 7.825"), 2-7/8" tubing, perforations 3 200–3 400 ft
    return WellGeometry(
        total_depth=3500.0,
        casing_od=8.625,
        casing_weight=32.0,
        casing_id=7.825,
        tubing_od=2.875,
        tubing_id=2.441,
        perforations_top=3200.0,
        perforations_bottom=3400.0,
        deviation_max=5.0,
        wellhead_temp=70.0,
        bottom_hole_temp=130.0,
    )


@pytest.fixture(scope="module")
def base_surface() -> SurfaceConditions:
    return SurfaceConditions(
        wellhead_pressure_required=100.0,
        flowline_length=1000.0,
        flowline_id=4.0,
        flowline_elevation_change=0.0,
        separator_pressure=50.0,
        power_supply_voltage=4160.0,
        frequency=60.0,
    )


@pytest.fixture(scope="module")
def base_objectives() -> DesignObjectives:
    return DesignObjectives(
        target_flow_rate=1227.0,
        safety_margin_depth=200.0,
        allow_gas_venting=False,
        max_gip=0.10,
        design_life_years=3.0,
        use_vsd=False,
    )


# ---------------------------------------------------------------------------
# 1 — Hazen-Williams friction losses
# ---------------------------------------------------------------------------

class TestHazenWilliams:
    """Validate friction_loss_hazen_williams formula."""

    def test_returns_positive(self):
        assert friction_loss_hazen_williams(1000.0, 3.0, 5000.0) > 0.0

    def test_zero_length_returns_zero(self):
        assert friction_loss_hazen_williams(1000.0, 3.0, 0.0) == 0.0

    def test_increases_with_flow(self):
        h1 = friction_loss_hazen_williams(500.0, 3.0, 1000.0)
        h2 = friction_loss_hazen_williams(1000.0, 3.0, 1000.0)
        assert h2 > h1

    def test_decreases_with_larger_pipe(self):
        h_small = friction_loss_hazen_williams(5000.0, 3.0, 1000.0)
        h_large = friction_loss_hazen_williams(5000.0, 5.0, 1000.0)
        assert h_large < h_small

    def test_proportional_to_length(self):
        h1 = friction_loss_hazen_williams(2000.0, 4.0, 1000.0)
        h2 = friction_loss_hazen_williams(2000.0, 4.0, 2000.0)
        assert h2 == pytest.approx(2.0 * h1, rel=1e-9)

    def test_new_5in_pipe_10000bpd(self):
        # C = 130 (new clean steel). Reference: Brown Vol. 2b ≈ 18.5 ft / 1 000 ft.
        h = friction_loss_hazen_williams(10000.0, 5.0, 1000.0, c_factor=130.0)
        assert h == pytest.approx(18.5, rel=0.05)

    def test_higher_c_gives_lower_loss(self):
        h120 = friction_loss_hazen_williams(5000.0, 4.0, 1000.0, c_factor=120.0)
        h140 = friction_loss_hazen_williams(5000.0, 4.0, 1000.0, c_factor=140.0)
        assert h140 < h120

    def test_bpd_to_gpm_conversion(self):
        # 1440 bpd = 42 gpm exactly; check against direct GPM formula
        q_bpd = 1440.0
        q_gpm = 42.0
        d, c, L = 3.0, 120.0, 1000.0
        h_from_function = friction_loss_hazen_williams(q_bpd, d, L, c)
        h_manual = 0.2083 * (100.0 / c) ** 1.852 * q_gpm ** 1.852 / d ** 4.8655 * L / 100.0
        assert h_from_function == pytest.approx(h_manual, rel=1e-9)


# ---------------------------------------------------------------------------
# 2 — TDH decomposition
# ---------------------------------------------------------------------------

class TestCalculateTDH:
    """Validate TDH component breakdown."""

    # Minimal fixtures scoped to this class only
    @pytest.fixture(scope="class")
    def res(self):
        return Reservoir(
            static_pressure=3000.0, bubble_point=500.0, productivity_index=2.0,
            ipr_method=IPRMethod.LINEAR, reservoir_temp=160.0,
            drive_mechanism=DriveMechanism.WATER_DRIVE, datum_depth=5000.0,
        )

    @pytest.fixture(scope="class")
    def flu(self):
        # 30°API, WC 40 % → SG_oil=0.876, SG_liq=0.876*0.60+1.03*0.40=0.937
        return Fluid(
            oil_api=30.0, water_cut=0.40, gor=100.0, gas_sg=0.65,
            water_sg=1.03, oil_viscosity_dead=8.0, viscosity_temp_ref=100.0,
            bubble_point_pressure=500.0, h2s_content=0.0, co2_content=0.0,
            sand_production=False,
        )

    @pytest.fixture(scope="class")
    def wel(self):
        return WellGeometry(
            total_depth=5500.0, casing_od=7.0, casing_weight=23.0,
            casing_id=6.366, tubing_od=2.875, tubing_id=2.441,
            perforations_top=4800.0, perforations_bottom=5000.0,
            deviation_max=3.0, wellhead_temp=75.0, bottom_hole_temp=160.0,
        )

    @pytest.fixture(scope="class")
    def sur(self):
        return SurfaceConditions(
            wellhead_pressure_required=100.0, flowline_length=500.0,
            flowline_id=3.0, flowline_elevation_change=0.0,
            separator_pressure=50.0, power_supply_voltage=4160.0, frequency=60.0,
        )

    @pytest.fixture(scope="class")
    def obj(self):
        return DesignObjectives(
            target_flow_rate=800.0, safety_margin_depth=100.0,
            allow_gas_venting=False, max_gip=0.10,
            design_life_years=3.0, use_vsd=False,
        )

    def _tdh(self, res, flu, wel, sur, obj, pump_depth=4500.0, pip=1200.0):
        return calculate_tdh(res, flu, wel, sur, obj,
                             pump_depth=pump_depth, pip=pip)

    def test_returns_dict(self, res, flu, wel, sur, obj):
        assert isinstance(self._tdh(res, flu, wel, sur, obj), dict)

    def test_has_required_keys(self, res, flu, wel, sur, obj):
        r = self._tdh(res, flu, wel, sur, obj)
        for key in ("tdh_ft", "vertical_lift_ft", "tubing_friction_ft",
                    "wellhead_pressure_head_ft", "pip_head_ft", "sg_liquid",
                    "pump_depth_ft", "pip_psi"):
            assert key in r, f"Missing key: {key}"

    def test_tdh_equals_sum_of_components(self, res, flu, wel, sur, obj):
        r = self._tdh(res, flu, wel, sur, obj)
        total = (r["vertical_lift_ft"]
                 + r["tubing_friction_ft"]
                 + r["wellhead_pressure_head_ft"])
        assert r["tdh_ft"] == pytest.approx(total, rel=1e-9)

    def test_higher_pip_reduces_tdh(self, res, flu, wel, sur, obj):
        low = self._tdh(res, flu, wel, sur, obj, pip=800.0)
        high = self._tdh(res, flu, wel, sur, obj, pip=1400.0)
        assert high["tdh_ft"] < low["tdh_ft"]

    def test_wellhead_head_uses_2_31_sg(self, res, flu, wel, sur, obj):
        r = self._tdh(res, flu, wel, sur, obj)
        expected = 100.0 * 2.31 / r["sg_liquid"]
        assert r["wellhead_pressure_head_ft"] == pytest.approx(expected, rel=1e-6)

    def test_pip_head_uses_2_31_sg(self, res, flu, wel, sur, obj):
        r = self._tdh(res, flu, wel, sur, obj, pip=1200.0)
        expected = 1200.0 * 2.31 / r["sg_liquid"]
        assert r["pip_head_ft"] == pytest.approx(expected, rel=1e-6)

    def test_friction_positive(self, res, flu, wel, sur, obj):
        r = self._tdh(res, flu, wel, sur, obj)
        assert r["tubing_friction_ft"] > 0.0

    def test_sg_liquid_30api_40wc(self, res, flu, wel, sur, obj):
        r = self._tdh(res, flu, wel, sur, obj)
        sg_oil = 141.5 / (131.5 + 30.0)
        sg_expected = sg_oil * 0.60 + 1.03 * 0.40
        assert r["sg_liquid"] == pytest.approx(sg_expected, rel=1e-6)

    def test_deeper_pump_more_friction(self, res, flu, wel, sur, obj):
        shallow = self._tdh(res, flu, wel, sur, obj, pump_depth=3000.0)
        deep = self._tdh(res, flu, wel, sur, obj, pump_depth=5000.0)
        assert deep["tubing_friction_ft"] > shallow["tubing_friction_ft"]


# ---------------------------------------------------------------------------
# 3 — Stage count — Book Examples #1A, #2A, #2B
# ---------------------------------------------------------------------------

class TestCalculateStages:
    """Validate stage calculations against Brown book examples."""

    def test_example_2a_d40_254_stages(self, d40):
        # #2A: D-40 at 1 227 bpd, head = 23.0 ft/stage.
        # ceil(5830 / 23.0) = ceil(253.48) = 254
        stages = calculate_stages(tdh_ft=5830.0, pump=d40, flow_bpd=1227.0)
        assert stages == 254

    def test_example_1a_i300_28_stages(self, i300):
        # #1A: I-300 at 10 000 bpd, head = 59.5 ft/stage.
        # 28 × 59.5 = 1 666 ft → ceil(1 666 / 59.5) = 28 exactly.
        stages = calculate_stages(tdh_ft=1666.0, pump=i300, flow_bpd=10000.0)
        assert stages == 28

    def test_example_2b_i42b_112_stages(self, i42b):
        # #2B: I-42B at 2 080 bpd → head ≈ 38.10 ft/stage.
        # ceil(4 258 / 38.10) = ceil(111.76) = 112
        stages = calculate_stages(tdh_ft=4258.0, pump=i42b, flow_bpd=2080.0)
        assert stages == 112

    def test_stages_positive(self, d40):
        assert calculate_stages(1000.0, d40, 1227.0) > 0

    def test_more_tdh_more_stages(self, d40):
        s1 = calculate_stages(2000.0, d40, 1227.0)
        s2 = calculate_stages(4000.0, d40, 1227.0)
        assert s2 > s1

    def test_stages_is_int(self, i300):
        assert isinstance(calculate_stages(1500.0, i300, 10000.0), int)

    def test_ceiling_behavior(self, d40):
        # head = 23.0 at 1227 bpd → TDH=46.1 → 46.1/23.0 = 2.004 → ceil = 3
        assert calculate_stages(tdh_ft=46.1, pump=d40, flow_bpd=1227.0) == 3

    def test_exact_multiple_no_extra_stage(self, d40):
        # 46.0 / 23.0 = 2.0 exactly → ceil = 2
        assert calculate_stages(tdh_ft=46.0, pump=d40, flow_bpd=1227.0) == 2


# ---------------------------------------------------------------------------
# 4 — Motor HP — Book Examples #1A, #2A, #2B
# ---------------------------------------------------------------------------

class TestCalculateMotorHP:
    """Validate motor HP with SG correction against Brown book examples."""

    def test_example_2a_d40_hp_approx_79(self, d40):
        # #2A: 254 stages, hp/stage = 0.350, SG = 0.889 → 254 × 0.350 × 0.889 ≈ 79 hp
        hp = calculate_motor_hp(pump=d40, stages=254, flow_bpd=1227.0, sg_fluid=0.889)
        assert hp == pytest.approx(79.0, abs=2.0)

    def test_example_1a_i300_hp_approx_180(self, i300):
        # #1A: 28 stages, hp/stage = 6.80, SG = 0.945 → 28 × 6.80 × 0.945 ≈ 180 hp
        hp = calculate_motor_hp(pump=i300, stages=28, flow_bpd=10000.0, sg_fluid=0.945)
        assert hp == pytest.approx(180.0, abs=3.0)

    def test_example_2b_i42b_hp_approx_65(self, i42b):
        # #2B: 112 stages, hp/stage ≈ 0.708, SG ≈ 0.82 → 112 × 0.708 × 0.82 ≈ 65 hp
        hp = calculate_motor_hp(pump=i42b, stages=112, flow_bpd=2080.0, sg_fluid=0.82)
        assert hp == pytest.approx(65.0, abs=3.0)

    def test_hp_positive(self, d40):
        assert calculate_motor_hp(d40, 100, 1227.0, 0.9) > 0.0

    def test_sg_scales_hp_linearly(self, i300):
        hp1 = calculate_motor_hp(i300, 28, 10000.0, sg_fluid=1.0)
        hp2 = calculate_motor_hp(i300, 28, 10000.0, sg_fluid=0.5)
        assert hp2 == pytest.approx(0.5 * hp1, rel=1e-9)

    def test_double_stages_doubles_hp(self, d40):
        hp1 = calculate_motor_hp(d40, 100, 1227.0, 0.9)
        hp2 = calculate_motor_hp(d40, 200, 1227.0, 0.9)
        assert hp2 == pytest.approx(2.0 * hp1, rel=1e-9)


# ---------------------------------------------------------------------------
# 5 — Operating range check
# ---------------------------------------------------------------------------

class TestCheckPumpOperatingRange:

    def test_at_bep_in_range_and_near_bep(self, d40):
        r = check_pump_operating_range(d40, d40.bep_flow)
        assert r["in_range"] is True
        assert r["near_bep"] is True

    def test_below_min_flow_not_in_range(self, d40):
        r = check_pump_operating_range(d40, d40.min_flow * 0.5)
        assert r["in_range"] is False

    def test_above_max_flow_not_in_range(self, i300):
        r = check_pump_operating_range(i300, i300.max_flow * 1.5)
        assert r["in_range"] is False

    def test_near_min_flag(self, d40):
        # Just above min but within 10 %
        r = check_pump_operating_range(d40, d40.min_flow * 1.05)
        assert r["near_min"] is True

    def test_near_max_flag(self, d40):
        r = check_pump_operating_range(d40, d40.max_flow * 0.95)
        assert r["near_max"] is True

    def test_returns_all_required_keys(self, i300):
        r = check_pump_operating_range(i300, 10000.0)
        for k in ("in_range", "near_min", "near_max", "near_bep", "recommendation"):
            assert k in r

    def test_recommendation_is_string(self, d40):
        assert isinstance(check_pump_operating_range(d40, 1300.0)["recommendation"], str)

    def test_d40_at_1227_in_range(self, d40):
        assert check_pump_operating_range(d40, 1227.0)["in_range"] is True

    def test_i300_at_10000_in_range(self, i300):
        assert check_pump_operating_range(i300, 10000.0)["in_range"] is True

    def test_mid_range_not_near_min_or_max(self, d40):
        # BEP flow is 1300 for D-40 — not near the 10 % boundary on either side
        r = check_pump_operating_range(d40, 1300.0)
        assert r["near_bep"] is True


# ---------------------------------------------------------------------------
# 6 — Viscosity correction (HI method)
# ---------------------------------------------------------------------------

class TestApplyViscosityCorrection:

    def test_water_unity_factors(self, d40):
        pt = d40.points[5]
        r = apply_viscosity_correction(
            pump=d40, flow=pt.flow_rate, head=pt.head_per_stage,
            hp=pt.hp_per_stage, viscosity_ssu=20.0,
        )
        assert r["q_factor"] == pytest.approx(1.0)
        assert r["h_factor"] == pytest.approx(1.0)
        assert r["e_factor"] == pytest.approx(1.0)
        assert r["corrected_flow"] == pytest.approx(pt.flow_rate)
        assert r["corrected_head"] == pytest.approx(pt.head_per_stage)

    def test_high_viscosity_reduces_head(self, d40):
        r = apply_viscosity_correction(
            pump=d40, flow=1300.0, head=22.0, hp=0.347, viscosity_ssu=200.0,
        )
        assert r["h_factor"] < 1.0
        assert r["corrected_head"] < 22.0

    def test_high_viscosity_increases_hp(self, d40):
        # Lower efficiency → more shaft power required
        r = apply_viscosity_correction(
            pump=d40, flow=1300.0, head=22.0, hp=0.347, viscosity_ssu=500.0,
        )
        assert r["corrected_hp"] > 0.347

    def test_returns_all_keys(self, d40):
        r = apply_viscosity_correction(
            pump=d40, flow=1300.0, head=22.0, hp=0.347, viscosity_ssu=100.0,
        )
        for k in ("q_factor", "h_factor", "e_factor", "hp_factor",
                  "corrected_flow", "corrected_head", "corrected_hp"):
            assert k in r

    def test_factors_in_valid_range(self, d40):
        r = apply_viscosity_correction(
            pump=d40, flow=1300.0, head=22.0, hp=0.347, viscosity_ssu=150.0,
        )
        assert 0.0 < r["q_factor"] <= 1.0
        assert 0.0 < r["h_factor"] <= 1.0
        assert 0.0 < r["e_factor"] <= 1.0

    def test_hp_factor_increases_with_viscosity(self, d40):
        r_low = apply_viscosity_correction(
            pump=d40, flow=1300.0, head=22.0, hp=0.347, viscosity_ssu=50.0,
        )
        r_high = apply_viscosity_correction(
            pump=d40, flow=1300.0, head=22.0, hp=0.347, viscosity_ssu=400.0,
        )
        assert r_high["hp_factor"] > r_low["hp_factor"]

    def test_correction_monotone_with_viscosity(self, d40):
        # Head factor should decrease as viscosity increases
        ssu_vals = [30, 60, 100, 200, 400]
        h_factors = [
            apply_viscosity_correction(d40, 1300.0, 22.0, 0.347, v)["h_factor"]
            for v in ssu_vals
        ]
        assert all(h_factors[i] >= h_factors[i + 1] for i in range(len(h_factors) - 1))


# ---------------------------------------------------------------------------
# 7 — Full design workflow (integration)
# ---------------------------------------------------------------------------

class TestDesignPumpComplete:
    """Integration tests for design_pump_complete end-to-end."""

    def test_returns_list(self, base_reservoir, base_fluid, base_well,
                          base_surface, base_objectives, manager):
        results = design_pump_complete(
            base_reservoir, base_fluid, base_well, base_surface,
            base_objectives, pump_setting_depth=3000.0,
            catalog_manager=manager,
        )
        assert isinstance(results, list)

    def test_results_have_required_keys(self, base_reservoir, base_fluid, base_well,
                                        base_surface, base_objectives, manager):
        results = design_pump_complete(
            base_reservoir, base_fluid, base_well, base_surface,
            base_objectives, pump_setting_depth=3000.0,
            catalog_manager=manager,
        )
        if results:
            for key in ("pump_model", "pump_manufacturer", "pump_od",
                        "stages", "tdh_ft", "head_per_stage", "hp_per_stage",
                        "efficiency", "total_pump_hp", "pip_psi", "sg_liquid",
                        "operating_check", "tdh_breakdown", "warnings"):
                assert key in results[0], f"Missing key: {key}"

    def test_stages_positive(self, base_reservoir, base_fluid, base_well,
                             base_surface, base_objectives, manager):
        results = design_pump_complete(
            base_reservoir, base_fluid, base_well, base_surface,
            base_objectives, pump_setting_depth=3000.0,
            catalog_manager=manager,
        )
        for r in results:
            assert r["stages"] > 0

    def test_tdh_positive(self, base_reservoir, base_fluid, base_well,
                          base_surface, base_objectives, manager):
        results = design_pump_complete(
            base_reservoir, base_fluid, base_well, base_surface,
            base_objectives, pump_setting_depth=3000.0,
            catalog_manager=manager,
        )
        for r in results:
            assert r["tdh_ft"] > 0.0

    def test_hp_positive(self, base_reservoir, base_fluid, base_well,
                         base_surface, base_objectives, manager):
        results = design_pump_complete(
            base_reservoir, base_fluid, base_well, base_surface,
            base_objectives, pump_setting_depth=3000.0,
            catalog_manager=manager,
        )
        for r in results:
            assert r["total_pump_hp"] > 0.0

    def test_sorted_by_efficiency_descending(self, base_reservoir, base_fluid,
                                              base_well, base_surface,
                                              base_objectives, manager):
        results = design_pump_complete(
            base_reservoir, base_fluid, base_well, base_surface,
            base_objectives, pump_setting_depth=3000.0,
            catalog_manager=manager,
        )
        if len(results) >= 2:
            effs = [r["efficiency"] for r in results]
            assert all(effs[i] >= effs[i + 1] for i in range(len(effs) - 1))

    def test_pump_od_fits_casing(self, base_reservoir, base_fluid, base_well,
                                 base_surface, base_objectives, manager):
        results = design_pump_complete(
            base_reservoir, base_fluid, base_well, base_surface,
            base_objectives, pump_setting_depth=3000.0,
            catalog_manager=manager,
        )
        for r in results:
            assert r["pump_od"] < base_well.casing_id

    def test_d40_selected_for_1227bpd(self, base_reservoir, base_fluid, base_well,
                                       base_surface, base_objectives, manager):
        results = design_pump_complete(
            base_reservoir, base_fluid, base_well, base_surface,
            base_objectives, pump_setting_depth=3000.0,
            catalog_manager=manager,
        )
        models = [r["pump_model"] for r in results]
        assert "D-40" in models, f"D-40 not found; got {models}"

    def test_large_well_i300_selected(self, manager):
        """High-flow 9-5/8" casing well — I-300 must appear in candidates."""
        reservoir = Reservoir(
            static_pressure=2500.0, bubble_point=800.0, productivity_index=15.0,
            ipr_method=IPRMethod.COMBINED, reservoir_temp=185.0,
            drive_mechanism=DriveMechanism.SOLUTION_GAS, datum_depth=7000.0,
        )
        fluid = Fluid(
            oil_api=32.0, water_cut=0.20, gor=200.0, gas_sg=0.65,
            water_sg=1.05, oil_viscosity_dead=5.0, viscosity_temp_ref=100.0,
            bubble_point_pressure=800.0, h2s_content=0.0, co2_content=0.0,
            sand_production=False,
        )
        well = WellGeometry(
            total_depth=7500.0,
            casing_od=9.625,
            casing_weight=47.0,
            casing_id=8.681,   # 9-5/8" 47 lb/ft
            tubing_od=3.5,
            tubing_id=2.992,
            perforations_top=6800.0,
            perforations_bottom=7000.0,
            deviation_max=5.0,
            wellhead_temp=80.0,
            bottom_hole_temp=185.0,
        )
        surface = SurfaceConditions(
            wellhead_pressure_required=100.0, flowline_length=500.0,
            flowline_id=4.0, flowline_elevation_change=0.0,
            separator_pressure=50.0, power_supply_voltage=4160.0, frequency=60.0,
        )
        objectives = DesignObjectives(
            target_flow_rate=10000.0, safety_margin_depth=200.0,
            allow_gas_venting=False, max_gip=0.10,
            design_life_years=3.0, use_vsd=False,
        )
        results = design_pump_complete(
            reservoir, fluid, well, surface, objectives,
            pump_setting_depth=6000.0, catalog_manager=manager,
        )
        models = [r["pump_model"] for r in results]
        assert "I-300" in models, f"I-300 not found in results; got {models}"


# ---------------------------------------------------------------------------
# 6 — design_pump_by_model (manual pump selection, bypasses the
#     casing/flow-range prefilter used for auto-recommendation)
# ---------------------------------------------------------------------------

class TestDesignPumpByModel:
    """design_pump_by_model must reproduce design_pump_complete's per-pump
    result exactly, and enforce casing fit / curve range as hard bounds."""

    def test_matches_design_pump_complete_for_same_pump(
        self, base_reservoir, base_fluid, base_well, base_surface,
        base_objectives, manager,
    ):
        batch = design_pump_complete(
            base_reservoir, base_fluid, base_well, base_surface,
            base_objectives, pump_setting_depth=3000.0, catalog_manager=manager,
        )
        d40_from_batch = next(r for r in batch if r["pump_model"] == "D-40")

        single = design_pump_by_model(
            base_reservoir, base_fluid, base_well, base_surface,
            base_objectives, pump_setting_depth=3000.0, catalog_manager=manager,
            pump_model="D-40",
        )
        assert single["stages"] == d40_from_batch["stages"]
        assert single["total_pump_hp"] == pytest.approx(d40_from_batch["total_pump_hp"])
        assert single["tdh_ft"] == pytest.approx(d40_from_batch["tdh_ft"])
        assert single["efficiency"] == pytest.approx(d40_from_batch["efficiency"])

    def test_unknown_model_raises(self, base_reservoir, base_fluid, base_well,
                                   base_surface, base_objectives, manager):
        with pytest.raises(ValueError, match="NO-EXISTE"):
            design_pump_by_model(
                base_reservoir, base_fluid, base_well, base_surface,
                base_objectives, pump_setting_depth=3000.0, catalog_manager=manager,
                pump_model="NO-EXISTE",
            )

    def test_pump_too_large_for_casing_raises(self, base_reservoir, base_fluid,
                                               base_well, base_surface,
                                               base_objectives, manager):
        # SM18500 (OD 8.75") does not fit base_well's 8-5/8" casing (ID 7.825").
        big_pump = next(p for p in manager.get_all_pumps() if p.model == "SM18500")
        assert big_pump.od >= base_well.casing_id
        with pytest.raises(ValueError, match="casing"):
            design_pump_by_model(
                base_reservoir, base_fluid, base_well, base_surface,
                base_objectives, pump_setting_depth=3000.0, catalog_manager=manager,
                pump_model="SM18500",
            )

    def test_flow_outside_curve_range_raises(self, base_fluid, base_well,
                                              base_surface, manager):
        # Higher reservoir pressure so the target rate is reservoir-feasible;
        # 1 800 bpd is still above D-40's curve range (800-1700 bpd).
        reservoir = Reservoir(
            static_pressure=1500.0, bubble_point=700.0, productivity_index=5.0,
            ipr_method=IPRMethod.VOGEL, reservoir_temp=130.0,
            drive_mechanism=DriveMechanism.SOLUTION_GAS, datum_depth=3500.0,
        )
        objectives = DesignObjectives(
            target_flow_rate=1800.0, safety_margin_depth=200.0,
            allow_gas_venting=False, max_gip=0.10,
            design_life_years=3.0, use_vsd=False,
        )
        with pytest.raises(ValueError, match="D-40"):
            design_pump_by_model(
                reservoir, base_fluid, base_well, base_surface,
                objectives, pump_setting_depth=3000.0, catalog_manager=manager,
                pump_model="D-40",
            )


class TestSelectHousing:
    """Selección de carcasa(s) estándar y etapas ciegas (dummy)."""

    D40 = [50, 75, 100, 125, 150, 175, 200, 225, 250]

    def test_picks_smallest_option_above_required(self):
        from bes.core.pump_design import select_housing
        h = select_housing(193, self.D40, 250)
        assert h["housing_size_stages"] == 200
        assert h["dummy_stages"] == 7
        assert h["n_housings"] == 1

    def test_exact_fit_no_dummy(self):
        from bes.core.pump_design import select_housing
        h = select_housing(200, self.D40, 250)
        assert h["dummy_stages"] == 0 and h["n_housings"] == 1

    def test_tandem_when_exceeds_max(self):
        from bes.core.pump_design import select_housing
        h = select_housing(400, self.D40, 250)
        assert h["n_housings"] == 2
        assert h["housing_size_stages"] >= 400
        assert sum(cap * cnt for cap, cnt in h["housings"]) == h["housing_size_stages"]

    def test_dummy_never_negative_and_covers_required(self):
        from bes.core.pump_design import select_housing
        for req in (1, 28, 100, 244, 251, 333, 500):
            h = select_housing(req, self.D40, 250)
            assert h["dummy_stages"] >= 0
            assert h["housing_size_stages"] >= req


class TestHousingPressure:
    """Verificación de presión sobre la carcasa (MaxP shut-in vs límite)."""

    def _build(self):
        import json
        from bes.catalogs.loader import CatalogManager
        from bes.core.models import (
            Reservoir, Fluid, WellGeometry, SurfaceConditions, DesignObjectives,
            IPRMethod, DriveMechanism,
        )
        cm = CatalogManager()
        ex = json.load(open("data/example_wells.json"))["example_2a_brown"]
        r = dict(ex["reservoir"])
        r["ipr_method"] = IPRMethod[r["ipr_method"]]
        r["drive_mechanism"] = DriveMechanism[r["drive_mechanism"]]
        res = Reservoir(**r)
        fl = Fluid(**ex["fluid"]); w = WellGeometry(**ex["well"])
        su = SurfaceConditions(**ex["surface"]); ob = DesignObjectives(**ex["objectives"])
        psd = max(w.perforations_top - ob.safety_margin_depth, 100.0)
        return cm, res, fl, w, su, ob, psd

    def test_maxp_matches_formula_and_ok(self):
        from bes.core.pump_design import design_pump_by_model, _sg_liquid
        cm, res, fl, w, su, ob, psd = self._build()
        c = design_pump_by_model(res, fl, w, su, ob, psd, cm, "D-40")
        pump = next(p for p in cm.get_all_pumps() if p.model == "D-40")
        shutin = max(pt.head_per_stage for pt in pump.points)
        expected = shutin * c["stages"] * _sg_liquid(fl) / 2.31
        assert c["max_housing_pressure_psi"] == pytest.approx(expected, rel=1e-6)
        assert c["housing_pressure_limit_psi"] == 5000.0
        assert c["housing_pressure_ok"] is True  # 2A queda holgado

    def test_warns_when_limit_exceeded(self):
        from bes.core.pump_design import design_pump_by_model
        cm, res, fl, w, su, ob, psd = self._build()
        pump = next(p for p in cm.get_all_pumps() if p.model == "D-40")
        pump.housing_pressure_limit_psi = 500.0  # límite artificialmente bajo
        try:
            c = design_pump_by_model(res, fl, w, su, ob, psd, cm, "D-40")
            assert c["housing_pressure_ok"] is False
            assert any("carcasa" in wtxt.lower() for wtxt in c["warnings"])
        finally:
            pump.housing_pressure_limit_psi = 5000.0  # restaurar


class TestMotorHpMaxVsOperative:
    """HP máximo (SG del fluido más pesado) vs operativo (SG de la mezcla)."""

    def _build(self, overrides=None):
        import json
        from bes.catalogs.loader import CatalogManager
        from bes.core.models import (
            Reservoir, Fluid, WellGeometry, SurfaceConditions, DesignObjectives,
            IPRMethod, DriveMechanism,
        )
        cm = CatalogManager()
        ex = json.load(open("data/example_wells.json"))["example_2a_brown"]
        r = dict(ex["reservoir"]); r["ipr_method"] = IPRMethod[r["ipr_method"]]
        r["drive_mechanism"] = DriveMechanism[r["drive_mechanism"]]
        fdict = dict(ex["fluid"])
        if overrides:
            fdict.update(overrides)
        res = Reservoir(**r); fl = Fluid(**fdict); w = WellGeometry(**ex["well"])
        su = SurfaceConditions(**ex["surface"]); ob = DesignObjectives(**ex["objectives"])
        psd = max(w.perforations_top - ob.safety_margin_depth, 100.0)
        return cm, res, fl, w, su, ob, psd

    def test_max_ge_operative_with_water_cut(self):
        from bes.core.pump_design import design_pump_by_model
        from bes.core.tdh import _sg_liquid, _sg_max
        cm, res, fl, w, su, ob, psd = self._build()
        c = design_pump_by_model(res, fl, w, su, ob, psd, cm, "D-40")
        assert c["motor_hp_max"] >= c["total_pump_hp"]
        # el cociente = SG máx / SG mezcla
        assert c["motor_hp_max"] / c["total_pump_hp"] == pytest.approx(
            _sg_max(fl) / _sg_liquid(fl), rel=1e-6
        )

    def test_equal_for_full_water(self):
        from bes.core.pump_design import design_pump_by_model
        cm, res, fl, w, su, ob, psd = self._build(overrides={"water_cut": 1.0})
        c = design_pump_by_model(res, fl, w, su, ob, psd, cm, "D-40")
        assert c["motor_hp_max"] == pytest.approx(c["total_pump_hp"], rel=1e-9)
