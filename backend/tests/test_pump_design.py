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

# Pozo sintético para las verificaciones de carcasa y de HP máximo. Cargado a
# mano acá: los casos precargados se retiraron del proyecto. Petróleo con gas,
# casing 5-1/2", donde la D-40 diseña.
def _manual_well():
    from bes.core.models import (
        Reservoir, Fluid, WellGeometry, SurfaceConditions, DesignObjectives,
        IPRMethod, DriveMechanism,
    )
    res = Reservoir(
        static_pressure=2000.0, bubble_point=2000.0,
        test_pwf=1000.0, test_rate=933.3,          # ⇒ J ≈ 1.2 STB/d/psi
        ipr_method=IPRMethod.VOGEL, reservoir_temp=170.0,
        drive_mechanism=DriveMechanism.SOLUTION_GAS,
    )
    fluid = dict(
        oil_api=30.0, water_cut=0.15, gor=350.0, gas_sg=0.75, water_sg=1.02,
        oil_viscosity_dead=5.0, viscosity_temp_ref=100.0,
        bubble_point_pressure=2000.0, h2s_content=0.0, co2_content=0.0,
        sand_production=False,
    )
    well = WellGeometry(
        total_depth=6150.0, casing_od=5.5, casing_weight=17.0, casing_id=4.892,
        tubing_od=2.375, tubing_id=1.995, perforations_top=5900.0,
        perforations_bottom=6030.0, deviation_max=0.0,
        wellhead_temp=120.0,
    )
    surf = SurfaceConditions(
        wellhead_pressure_required=200.0, flowline_length=1000.0,
        flowline_id=3.0, flowline_elevation_change=0.0,
        separator_pressure=100.0, power_supply_voltage=7200.0, frequency=60.0,
    )
    obj = DesignObjectives(
        target_flow_rate=1227.0, safety_margin_depth=50.0,
        allow_gas_venting=False, max_gip=0.7, design_life_years=5.0,
        use_vsd=False, gas_fraction_pc_threshold=1.0,
    )
    return res, fluid, well, surf, obj

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
            drive_mechanism=DriveMechanism.WATER_DRIVE,
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
            deviation_max=3.0, wellhead_temp=75.0,
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
            ipr_method=IPRMethod.VOGEL, reservoir_temp=185.0,
            drive_mechanism=DriveMechanism.SOLUTION_GAS,
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
        # Ninguna bomba del catálogo supera el casing de 8-5/8" del pozo base,
        # así que la prueba usa un casing angosto: la L16000N (OD 7.25")
        # no entra en 5-1/2".
        import dataclasses
        base_well = dataclasses.replace(
            base_well, casing_od=5.5, casing_weight=17.0, casing_id=4.892)
        big_pump = next(p for p in manager.get_all_pumps() if p.model == "L16000N")
        assert big_pump.od >= base_well.casing_id
        with pytest.raises(ValueError, match="casing"):
            design_pump_by_model(
                base_reservoir, base_fluid, base_well, base_surface,
                base_objectives, pump_setting_depth=3000.0, catalog_manager=manager,
                pump_model="L16000N",
            )

    def test_flow_outside_curve_range_raises(self, base_fluid, base_well,
                                              base_surface, manager):
        # Higher reservoir pressure so the target rate is reservoir-feasible;
        # 1 800 bpd is still above D-40's curve range (800-1700 bpd).
        reservoir = Reservoir(
            static_pressure=1500.0, bubble_point=700.0, productivity_index=5.0,
            ipr_method=IPRMethod.VOGEL, reservoir_temp=130.0,
            drive_mechanism=DriveMechanism.SOLUTION_GAS,
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
        cm = CatalogManager()
        res, fdict, w, su, ob = _manual_well()
        from bes.core.models import Fluid
        fl = Fluid(**fdict)
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

    def test_rejects_when_limit_exceeded(self):
        """Una combinación sobre-presionada nunca se devuelve: el optimizador
        agota las alternativas del catálogo y, si ninguna entra, la bomba se
        descarta. Con un modelo elegido a mano el rechazo explica el motivo."""
        from bes.core.pump_design import design_pump_by_model
        cm, res, fl, w, su, ob, psd = self._build()
        pump = next(p for p in cm.get_all_pumps() if p.model == "D-40")
        pump.housing_pressure_limit_psi = 500.0  # límite artificialmente bajo
        try:
            with pytest.raises(ValueError, match="presión admisible"):
                design_pump_by_model(res, fl, w, su, ob, psd, cm, "D-40")
        finally:
            pump.housing_pressure_limit_psi = 5000.0  # restaurar

    def test_over_pressured_pump_drops_out_of_the_candidates(self):
        """En el camino automático el descarte es silencioso: la bomba no se
        ofrece, en vez de recomendarse con una advertencia."""
        from bes.core.pump_design import design_pump_complete
        cm, res, fl, w, su, ob, psd = self._build()
        pump = next(p for p in cm.get_all_pumps() if p.model == "D-40")
        before = [c["pump_model"] for c in
                  design_pump_complete(res, fl, w, su, ob, psd, cm)]
        assert "D-40" in before
        pump.housing_pressure_limit_psi = 500.0
        try:
            after = [c["pump_model"] for c in
                     design_pump_complete(res, fl, w, su, ob, psd, cm)]
            assert "D-40" not in after
        finally:
            pump.housing_pressure_limit_psi = 5000.0

    def test_per_housing_detail_is_cumulative(self):
        """La presión reportada crece carcasa a carcasa desde la admisión y la
        superior es la que ve el diferencial completo."""
        from bes.core.pump_design import design_pump_by_model
        cm, res, fl, w, su, ob, psd = self._build()
        c = design_pump_by_model(res, fl, w, su, ob, psd, cm, "D-40")
        detail = c["housing_detail"]
        assert detail, "el diseño debe reportar el detalle por carcasa"
        pressures = [d["pressure_psi"] for d in detail]
        assert pressures == sorted(pressures)
        assert detail[-1]["pressure_psi"] == pytest.approx(
            c["max_housing_pressure_psi"]
        )
        assert all(d["pressure_ok"] for d in detail)
        assert c["housing_rationale"].startswith("Se seleccion")


class TestMotorHpMaxVsOperative:
    """HP máximo (SG del fluido más pesado) vs operativo (SG de la mezcla)."""

    def _build(self, overrides=None):
        import json
        from bes.catalogs.loader import CatalogManager
        from bes.core.models import Fluid
        cm = CatalogManager()
        res, fdict, w, su, ob = _manual_well()
        if overrides:
            fdict = {**fdict, **overrides}
        fl = Fluid(**fdict)
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


# ===========================================================================
# Friction-correlation switch driven by the free-gas fraction at the intake
# ===========================================================================

class TestFrictionCorrelationSwitch:
    """The free-gas fraction at the pump intake decides which correlation
    computes the tubing pressure loss: Hazen-Williams while the stream is
    essentially liquid, Poettmann-Carpenter once the gas is significant.

    The threshold lives in ``DesignObjectives.gas_fraction_pc_threshold`` so a
    case can state its own criterion (the printed Brown examples pin it at 1.0
    because the book solves them single-phase)."""

    @pytest.fixture(scope="class")
    def res(self):
        return Reservoir(
            static_pressure=2500.0, bubble_point=2400.0,
            ipr_method=IPRMethod.VOGEL, reservoir_temp=180.0,
            drive_mechanism=DriveMechanism.SOLUTION_GAS,
            productivity_index=2.0,
        )

    @pytest.fixture(scope="class")
    def gassy(self):
        """Saturated oil with a high GOR — plenty of free gas at the intake."""
        return Fluid(
            oil_api=32.0, water_cut=0.20, gor=600.0, gas_sg=0.70,
            water_sg=1.03, oil_viscosity_dead=4.0, viscosity_temp_ref=100.0,
            bubble_point_pressure=2400.0, h2s_content=0.0, co2_content=0.0,
            sand_production=False,
        )

    @pytest.fixture(scope="class")
    def dead(self):
        """Dead oil (GOR = 0) — there is no gas to come out of solution."""
        return Fluid(
            oil_api=32.0, water_cut=0.20, gor=0.0, gas_sg=0.70,
            water_sg=1.03, oil_viscosity_dead=4.0, viscosity_temp_ref=100.0,
            bubble_point_pressure=0.0, h2s_content=0.0, co2_content=0.0,
            sand_production=False,
        )

    @pytest.fixture(scope="class")
    def wel(self):
        return WellGeometry(
            total_depth=6200.0, casing_od=7.0, casing_weight=23.0,
            casing_id=6.366, tubing_od=2.875, tubing_id=2.441,
            perforations_top=6000.0, perforations_bottom=6100.0,
            deviation_max=0.0, wellhead_temp=100.0,
        )

    @pytest.fixture(scope="class")
    def sur(self):
        return SurfaceConditions(
            wellhead_pressure_required=150.0, flowline_length=500.0,
            flowline_id=3.0, flowline_elevation_change=0.0,
            separator_pressure=80.0, power_supply_voltage=4160.0, frequency=60.0,
        )

    def _obj(self, threshold: float = 0.10) -> DesignObjectives:
        return DesignObjectives(
            target_flow_rate=900.0, safety_margin_depth=100.0,
            allow_gas_venting=False, max_gip=0.50,
            design_life_years=3.0, use_vsd=False,
            gas_fraction_pc_threshold=threshold,
        )

    def _tdh(self, res, flu, wel, sur, threshold=0.10, fg=None):
        return calculate_tdh(
            res, flu, wel, sur, self._obj(threshold),
            pump_depth=5900.0, pip=400.0, free_gas_fraction=fg,
        )

    def test_dead_oil_uses_hazen_williams(self, res, dead, wel, sur):
        out = self._tdh(res, dead, wel, sur)
        assert out["free_gas_fraction"] == pytest.approx(0.0)
        assert out["friction_method"] == "hazen_williams"
        assert out["tubing_friction_ft"] == pytest.approx(
            friction_loss_hazen_williams(900.0, wel.tubing_id, 5900.0)
        )

    def test_gassy_oil_uses_poettmann_carpenter(self, res, gassy, wel, sur):
        out = self._tdh(res, gassy, wel, sur)
        assert out["free_gas_fraction"] > 0.10
        assert out["friction_method"] == "poettmann_carpenter"

    def test_threshold_is_respected(self, res, gassy, wel, sur):
        """Same gassy well, threshold above its gas fraction → back to H-W."""
        out = self._tdh(res, gassy, wel, sur, threshold=1.0)
        assert out["friction_method"] == "hazen_williams"
        assert out["tubing_friction_ft"] == pytest.approx(
            friction_loss_hazen_williams(900.0, wel.tubing_id, 5900.0)
        )

    def test_switch_happens_exactly_at_the_threshold(self, res, gassy, wel, sur):
        """Strictly above switches; exactly at the threshold does not."""
        assert self._tdh(res, gassy, wel, sur, 0.30, fg=0.30)["friction_method"] \
            == "hazen_williams"
        assert self._tdh(res, gassy, wel, sur, 0.30, fg=0.3001)["friction_method"] \
            == "poettmann_carpenter"

    def test_only_the_friction_term_changes(self, res, gassy, wel, sur):
        """The hybrid substitutes friction alone: lift and wellhead head keep
        the produced-liquid SG, so they must be identical under both methods."""
        hw = self._tdh(res, gassy, wel, sur, threshold=1.0)
        pc = self._tdh(res, gassy, wel, sur, threshold=0.10)
        assert pc["vertical_lift_ft"] == pytest.approx(hw["vertical_lift_ft"])
        assert pc["wellhead_pressure_head_ft"] == pytest.approx(
            hw["wellhead_pressure_head_ft"]
        )
        assert pc["tubing_friction_ft"] != pytest.approx(hw["tubing_friction_ft"])
        # TDH differs by exactly the friction difference — nothing else moved.
        assert pc["tdh_ft"] - hw["tdh_ft"] == pytest.approx(
            pc["tubing_friction_ft"] - hw["tubing_friction_ft"]
        )

    def test_gas_expansion_weights_the_top_of_the_string(self, res, gassy, wel, sur):
        """Why a single mid-point evaluation is not enough: the gas expands as
        the pressure drops, so the mixture is much faster near the wellhead and
        the friction gradient there is far larger than at the pump."""
        pc = self._tdh(res, gassy, wel, sur)
        assert pc["pc_mixture_velocity_top_ft_s"] > pc["pc_mixture_velocity_bottom_ft_s"]
        assert pc["pc_friction_gradient_top_psi_ft"] > pc["pc_friction_gradient_bottom_psi_ft"]

    def test_gravity_term_is_not_double_counted(self, res, gassy, wel, sur):
        """The P&C gravity gradient must never reach the TDH: the vertical-lift
        term already represents the column."""
        pc = self._tdh(res, gassy, wel, sur)
        friction_only_ft = pc["pc_friction_psi"] * 2.31 / pc["sg_liquid"]
        assert pc["tubing_friction_ft"] == pytest.approx(friction_only_ft)

    def test_threshold_out_of_range_rejected(self):
        with pytest.raises(ValueError, match="gas_fraction_pc_threshold"):
            self._obj(1.5)


# ===========================================================================
# Optimización automática de carcasas (bes/core/housing.py)
# ===========================================================================

class TestHousingOptimizer:
    """El módulo busca la mejor combinación en vez de aplicar una regla fija.
    Los tests fijan el ORDEN de los criterios, que es lo que define 'mejor'."""

    @staticmethod
    def _h(*specs):
        """Atajo: _h(200, 150) -> carcasas sin metadatos; acepta dicts."""
        from bes.core.models import PumpHousing
        out = []
        for s in specs:
            out.append(PumpHousing(**s) if isinstance(s, dict) else PumpHousing(stages=s))
        return out

    def _opt(self, required, housings, shutin=20.0, sg=1.0, limit=5000.0):
        from bes.core.housing import optimize_housings
        return optimize_housings(required, housings, shutin, sg, limit)

    def test_exact_match_wins(self):
        """Criterio 1: si existe combinación exacta, se elige."""
        r = self._opt(400, self._h(100, 150, 200))
        assert r["housing_size_stages"] == 400
        assert r["dummy_stages"] == 0
        assert r["housings"] == [(200, 2)]

    def test_minimises_surplus_before_housing_count(self):
        """Criterio 2 manda sobre el 3: se aceptan más carcasas si eso reduce
        el excedente. 100 = 60+40 (2 carcasas, exacto) es mejor que 1x110."""
        r = self._opt(100, self._h(110, 60, 40))
        assert r["housing_size_stages"] == 100
        assert r["dummy_stages"] == 0
        assert r["n_housings"] == 2

    def test_minimises_housing_count_at_equal_surplus(self):
        """Criterio 3: a igual excedente, menos carcasas."""
        r = self._opt(200, self._h(200, 100))
        assert r["n_housings"] == 1
        assert r["housings"] == [(200, 1)]

    def test_prefers_fewer_distinct_lengths(self):
        """Criterio 5: entre soluciones equivalentes, la más estandarizada."""
        r = self._opt(200, self._h(100, 50))
        assert r["housings"] == [(100, 2)]      # no 100+50+50

    def test_surplus_is_minimal_when_no_exact_match(self):
        r = self._opt(245, self._h(50, 75, 100, 125, 150, 175, 200, 225, 250))
        assert r["housing_size_stages"] == 250
        assert r["dummy_stages"] == 5
        assert r["n_housings"] == 1

    def test_tandem_when_stages_exceed_largest_housing(self):
        r = self._opt(500, self._h(200, 150, 100))
        assert r["housing_size_stages"] == 500
        assert sum(n for _, n in r["housings"]) == r["n_housings"] >= 3

    def test_pressure_is_a_hard_constraint(self):
        """Ninguna combinación sobre el límite puede devolverse."""
        assert self._opt(300, self._h(300), shutin=40.0, limit=1000.0) is None

    def test_search_continues_past_infeasible_combinations(self):
        """La combinación de menor excedente puede ser inviable por presión; el
        algoritmo sigue buscando en vez de rendirse. Con 6 etapas de reserva la
        carcasa chica entra y la grande no."""
        from bes.core.models import PumpHousing
        r = self._opt(
            100,
            [PumpHousing(stages=100, pressure_limit_psi=1000),
             PumpHousing(stages=50, pressure_limit_psi=9000)],
            shutin=40.0, sg=1.0, limit=0.0,
        )
        assert r is not None
        assert r["housings"] == [(50, 2)]       # la de 100 se descarta por presión
        assert r["pressure_ok"] is True

    def test_pressure_accumulates_from_the_intake(self):
        """MaxP = P(Q=0) x etapas activas acumuladas x Pem, carcasa a carcasa."""
        r = self._opt(400, self._h(200), shutin=20.0, sg=1.0)
        d = r["detail"]
        assert [x["active_stages_below"] for x in d] == [200, 400]
        assert d[0]["pressure_psi"] == pytest.approx(20.0 * 200 * 1.0 / 2.31)
        assert d[1]["pressure_psi"] == pytest.approx(20.0 * 400 * 1.0 / 2.31)
        assert r["max_housing_pressure_psi"] == pytest.approx(d[-1]["pressure_psi"])

    def test_dummy_stages_develop_no_head(self):
        """Las etapas ciegas no generan presión: la acumulada se topa en las
        activas requeridas, no en la capacidad instalada."""
        r = self._opt(245, self._h(250), shutin=20.0, sg=1.0)
        assert r["detail"][-1]["active_stages_below"] == 245
        assert r["detail"][-1]["pressure_psi"] == pytest.approx(20.0 * 245 / 2.31)

    def test_highest_rated_housing_goes_on_top(self):
        """Donde la presión es mayor va la carcasa mejor calificada."""
        from bes.core.models import PumpHousing
        r = self._opt(
            300,
            [PumpHousing(stages=150, code="STD", pressure_limit_psi=3000),
             PumpHousing(stages=150, code="HP", pressure_limit_psi=6000)],
            shutin=30.0, sg=1.0, limit=0.0,
        )
        assert [d["code"] for d in r["detail"]] == ["STD", "HP"]

    def test_does_not_over_specify_when_standard_suffices(self):
        """Criterio 5: no elegir carcasa de alta presión si la estándar entra."""
        from bes.core.models import PumpHousing
        r = self._opt(
            150,
            [PumpHousing(stages=150, code="STD", pressure_limit_psi=5000),
             PumpHousing(stages=150, code="HP", pressure_limit_psi=9000)],
            shutin=20.0, sg=1.0, limit=0.0,
        )
        assert [d["code"] for d in r["detail"]] == ["STD"]

    def test_missing_limit_is_reported_not_assumed(self):
        """Sin dato de presión no se afirma que la verificación pasó."""
        r = self._opt(100, self._h(100), limit=0.0)
        assert r["pressure_verified"] is False
        assert "no pudo realizarse" in r["rationale"]

    def test_rationale_matches_the_selection(self):
        r = self._opt(400, self._h(100, 150, 200))
        assert "2 carcasas de 200 etapas" in r["rationale"]
        assert "exactamente las 400 etapas" in r["rationale"]
        assert "sin etapas excedentes" in r["rationale"]

    def test_scales_to_a_catalog_of_many_short_housings(self):
        """Alkhorayef publica 15 longitudes cortas: la búsqueda debe seguir
        siendo instantánea y encontrar el ajuste exacto."""
        import time
        sizes = [4, 8, 13, 18, 22, 27, 31, 36, 40, 45, 50, 54, 59, 63, 68]
        t0 = time.perf_counter()
        r = self._opt(245, self._h(*sizes), shutin=27.8, sg=0.9)
        elapsed = time.perf_counter() - t0
        assert r["dummy_stages"] == 0
        assert elapsed < 2.0, f"la búsqueda tardó {elapsed:.2f} s"

    def test_rejects_invalid_input(self):
        from bes.core.housing import optimize_housings
        with pytest.raises(ValueError, match="required_stages"):
            optimize_housings(0, self._h(100), 20.0, 1.0, 5000.0)
        with pytest.raises(ValueError, match="no housings"):
            optimize_housings(100, [], 20.0, 1.0, 5000.0)

    def test_select_housing_wrapper_still_matches_the_optimizer(self):
        """El envoltorio histórico no duplica lógica: delega."""
        from bes.core.pump_design import select_housing
        w = select_housing(245, [50, 75, 100, 125, 150, 175, 200, 225, 250], 250)
        r = self._opt(245, self._h(50, 75, 100, 125, 150, 175, 200, 225, 250))
        assert w["housing_size_stages"] == r["housing_size_stages"]
        assert w["n_housings"] == r["n_housings"]
        assert w["housings"] == r["housings"]
