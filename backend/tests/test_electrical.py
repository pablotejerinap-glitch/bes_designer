"""
Tests for ESP electrical system design.
Validates against Kermit Brown, Vol. 2b, Sections 4.5325–4.5326.

Book examples used:
  Pág 14 (Example 2A) : motor 1 260 V / 45 A, cable #4 CU,
                         drop 24 V/1 000 ft @ 170 °F, Vs ≈ 1 438 V, KVA ≈ 113
  Pág 8               : motor 890 V / 58 A, cable #2 CU, 3 600 ft,
                         drop 20 V/1 000 ft @ 185 °F, Vs ≈ 990 V
"""
from __future__ import annotations

import math
import pytest
from pathlib import Path

from bes.catalogs.loader import CatalogManager
from bes.core.models import Fluid, IPRMethod, DriveMechanism, WellGeometry
from bes.core.electrical import (
    calculate_kva,
    calculate_surface_voltage,
    electrical_design_complete,
    estimate_axial_thrust,
    select_cable,
    select_motor,
    select_transformer,
    voltage_drop,
)



# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def manager() -> CatalogManager:
    return CatalogManager()


@pytest.fixture(scope="module")
def well_7in() -> WellGeometry:
    """7″ 23 lb/ft casing (ID 6.366″) — fits 456-series motor."""
    return WellGeometry(
        total_depth=5000.0,
        casing_od=7.0,
        casing_weight=23.0,
        casing_id=6.366,
        tubing_od=2.875,
        tubing_id=2.441,
        perforations_top=4500.0,
        perforations_bottom=4800.0,
        deviation_max=5.0,
        wellhead_temp=80.0,
        bottom_hole_temp=200.0,
    )


@pytest.fixture(scope="module")
def well_9in() -> WellGeometry:
    """9-5/8″ 47 lb/ft casing (ID 8.681″) — fits 540/544-series motor."""
    return WellGeometry(
        total_depth=7500.0,
        casing_od=9.625,
        casing_weight=47.0,
        casing_id=8.681,
        tubing_od=3.5,
        tubing_id=2.992,
        perforations_top=6800.0,
        perforations_bottom=7000.0,
        deviation_max=5.0,
        wellhead_temp=80.0,
        bottom_hole_temp=200.0,
    )


@pytest.fixture(scope="module")
def base_fluid() -> Fluid:
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


# ---------------------------------------------------------------------------
# 1 — voltage_drop
# ---------------------------------------------------------------------------

class TestVoltageDrop:
    """Validate voltage_drop interpolation against Brown book examples."""

    def test_example_2a_per_1000ft(self):
        # Brown pág 14: #4 CU @ 170 °F, 45 A → 24 V/1 000 ft
        # interp(150=0.516, 180=0.543) @ 170 = 0.534 V/A/1000ft → 0.534 × 45 = 24.03
        h = voltage_drop("#4", "CU", 45.0, 170.0, 1000.0)
        assert h == pytest.approx(24.0, abs=0.5)

    def test_example_p8_per_1000ft(self):
        # Brown pág 8: #2 CU @ 185 °F, 58 A → 20 V/1 000 ft
        # interp(180=0.341, 200=0.354) @ 185 = 0.3442 → 0.3442 × 58 = 19.96
        h = voltage_drop("#2", "CU", 58.0, 185.0, 1000.0)
        assert h == pytest.approx(20.0, abs=0.5)

    def test_example_2a_total_6000ft(self):
        # 24 V/1 000 ft × 6 000 ft = 144 V
        h = voltage_drop("#4", "CU", 45.0, 170.0, 6000.0)
        assert h == pytest.approx(144.0, abs=3.0)

    def test_example_p8_total_3600ft(self):
        # 20 V/1 000 ft × 3 600 ft = 72 V
        h = voltage_drop("#2", "CU", 58.0, 185.0, 3600.0)
        assert h == pytest.approx(72.0, abs=2.0)

    def test_al_higher_drop_than_cu(self):
        h_cu = voltage_drop("#2", "CU", 50.0, 150.0, 1000.0)
        h_al = voltage_drop("#2", "AL", 50.0, 150.0, 1000.0)
        assert h_al > h_cu

    def test_smaller_conductor_higher_drop(self):
        h2 = voltage_drop("#2", "CU", 50.0, 150.0, 1000.0)
        h4 = voltage_drop("#4", "CU", 50.0, 150.0, 1000.0)
        assert h4 > h2

    def test_proportional_to_length(self):
        h1 = voltage_drop("#4", "CU", 50.0, 150.0, 1000.0)
        h2 = voltage_drop("#4", "CU", 50.0, 150.0, 2000.0)
        assert h2 == pytest.approx(2.0 * h1, rel=1e-6)

    def test_proportional_to_amps(self):
        h1 = voltage_drop("#4", "CU", 30.0, 150.0, 1000.0)
        h2 = voltage_drop("#4", "CU", 60.0, 150.0, 1000.0)
        assert h2 == pytest.approx(2.0 * h1, rel=1e-6)

    def test_increases_with_temperature(self):
        h_cold = voltage_drop("#2", "CU", 50.0, 100.0, 1000.0)
        h_hot = voltage_drop("#2", "CU", 50.0, 200.0, 1000.0)
        assert h_hot > h_cold

    def test_clamped_above_max_temp(self):
        h200 = voltage_drop("#2", "CU", 50.0, 200.0, 1000.0)
        h300 = voltage_drop("#2", "CU", 50.0, 300.0, 1000.0)
        assert h300 == pytest.approx(h200, rel=1e-6)

    def test_clamped_below_min_temp(self):
        h100 = voltage_drop("#1", "CU", 40.0, 100.0, 1000.0)
        h50 = voltage_drop("#1", "CU", 40.0, 50.0, 1000.0)
        assert h50 == pytest.approx(h100, rel=1e-6)

    def test_al_string_in_cable_type(self):
        # "Redalene AL" → aluminium conductor detected from string
        h_al = voltage_drop("#2", "Redalene AL", 50.0, 150.0, 1000.0)
        h_explicit = voltage_drop("#2", "AL", 50.0, 150.0, 1000.0)
        assert h_al == pytest.approx(h_explicit, rel=1e-9)


# ---------------------------------------------------------------------------
# Cable selection reads voltage drop from the catalog (supports 1/0)
# ---------------------------------------------------------------------------

class TestCableVdropFromCatalog:
    def test_one_zero_cable_selectable(self, manager):
        # The CAVALCADE 1/0 cable (absent from the legacy hardcoded table) must
        # be selectable and yield a finite voltage drop from its own JSON data.
        cable = select_cable(
            motor_amps=90.0, pump_depth=6000.0, bottom_temp=180.0,
            casing_id=7.0, motor_od=4.0, catalog_manager=manager,
        )
        assert cable["voltage_drop_per_1000ft"] > 0


# ---------------------------------------------------------------------------
# Axial-thrust estimate (for protector selection)
# ---------------------------------------------------------------------------

class TestAxialThrust:
    def test_hand_calc_series_400(self):
        # TDH 4000 ft, SG 1.0, series 400 (d_shaft 0.62"):
        #   dP = 4000·0.433·1.0 = 1732 psi
        #   A  = pi/4·0.62² = 0.3019 in²
        #   F  = 1732·0.3019·1.20 ≈ 627 lbs
        f = estimate_axial_thrust(4000.0, 1.0, "400")
        assert f == pytest.approx(627.0, rel=0.02)

    def test_scales_with_tdh(self):
        assert estimate_axial_thrust(8000.0, 1.0, "400") > estimate_axial_thrust(4000.0, 1.0, "400")

    def test_design_complete_includes_seal(self, manager, well_7in, base_fluid):
        elec = electrical_design_complete(
            motor_hp=60.0, pump_od=4.0, well=well_7in, fluid=base_fluid,
            catalog_manager=manager, pump_depth=4000.0, tdh_ft=4000.0,
            sg_fluid=1.0, pump_series="456",
        )
        assert "seal" in elec
        assert elec["axial_thrust_lbs"] > 0


# ---------------------------------------------------------------------------
# 2 — calculate_surface_voltage
# ---------------------------------------------------------------------------

class TestSurfaceVoltage:
    """Validate Vs = (Vmotor + cable_drop) × (1 + loss%)."""

    def test_example_2a_vs(self):
        # Brown pág 14: Vmotor=1 260, cable_drop=144 V → Vs ≈ 1 438 V (2.5 % loss)
        vs = calculate_surface_voltage(1260.0, 144.0)
        assert vs == pytest.approx(1438.0, abs=5.0)

    def test_example_p8_vs(self):
        # Brown pág 8: Vmotor=890, cable_drop=72 V → Vs ≈ 990 V
        vs = calculate_surface_voltage(890.0, 72.0)
        assert vs == pytest.approx(990.0, abs=5.0)

    def test_formula_zero_loss(self):
        vs = calculate_surface_voltage(1000.0, 100.0, transformer_loss_pct=0.0)
        assert vs == pytest.approx(1100.0, rel=1e-9)

    def test_larger_drop_larger_vs(self):
        vs1 = calculate_surface_voltage(1000.0, 50.0)
        vs2 = calculate_surface_voltage(1000.0, 150.0)
        assert vs2 > vs1

    def test_default_2p5_pct_loss(self):
        vs = calculate_surface_voltage(1000.0, 0.0)
        assert vs == pytest.approx(1025.0, rel=1e-6)

    def test_custom_loss_pct(self):
        vs = calculate_surface_voltage(1000.0, 0.0, transformer_loss_pct=5.0)
        assert vs == pytest.approx(1050.0, rel=1e-6)


# ---------------------------------------------------------------------------
# 3 — calculate_kva
# ---------------------------------------------------------------------------

class TestCalculateKva:
    """Validate kVA = Vs × I × √3 / 1 000."""

    def test_example_2a_kva(self):
        # Brown pág 14: Vs=1 438, I=45 A → 1438×45×√3/1000 ≈ 112 kVA (book rounds 113)
        kva = calculate_kva(1438.0, 45.0)
        assert kva == pytest.approx(113.0, abs=2.0)

    def test_uses_sqrt3(self):
        kva = calculate_kva(1000.0, 100.0)
        assert kva == pytest.approx(1000.0 * 100.0 * math.sqrt(3) / 1000.0, rel=1e-9)

    def test_scales_linearly_with_voltage(self):
        kva1 = calculate_kva(1000.0, 50.0)
        kva2 = calculate_kva(2000.0, 50.0)
        assert kva2 == pytest.approx(2.0 * kva1, rel=1e-9)

    def test_scales_linearly_with_amps(self):
        kva1 = calculate_kva(1000.0, 50.0)
        kva2 = calculate_kva(1000.0, 100.0)
        assert kva2 == pytest.approx(2.0 * kva1, rel=1e-9)

    def test_positive(self):
        assert calculate_kva(1000.0, 40.0) > 0.0


# ---------------------------------------------------------------------------
# 4 — select_transformer
# ---------------------------------------------------------------------------

class TestSelectTransformer:

    def test_selects_next_standard_size(self):
        # 113 kVA → next standard ≥ 113 is 150 kVA
        t = select_transformer(113.0)
        assert t["kva_per_unit"] == 150.0

    def test_exact_match(self):
        t = select_transformer(100.0)
        assert t["kva_per_unit"] == 100.0

    def test_just_above_boundary(self):
        t = select_transformer(100.1)
        assert t["kva_per_unit"] == 150.0

    def test_3phase_single_unit(self):
        t = select_transformer(75.0, n_phases=3)
        assert t["n_units"] == 1
        assert t["total_kva"] == t["kva_per_unit"]

    def test_1phase_three_units(self):
        # 90 kVA / 3 = 30 kVA per unit → next size ≥ 30 is 37.5 kVA
        t = select_transformer(90.0, n_phases=1)
        assert t["n_units"] == 3
        assert t["kva_per_unit"] == 37.5
        assert t["total_kva"] == pytest.approx(112.5, rel=1e-6)

    def test_exceeds_max_raises(self):
        with pytest.raises(ValueError):
            select_transformer(10000.0)

    def test_minimum_size(self):
        t = select_transformer(10.0)
        assert t["kva_per_unit"] == 25.0

    def test_returns_required_keys(self):
        t = select_transformer(50.0)
        for k in ("n_phases", "kva_per_unit", "n_units", "total_kva"):
            assert k in t


# ---------------------------------------------------------------------------
# 5 — select_cable
# ---------------------------------------------------------------------------

class TestSelectCable:
    """Validate cable selection with NEC 1.25× derating and physical fit."""

    def test_example_2a_selects_4cu(self, manager):
        # motor_amps=45 → required=56.25 A → #6 (55A) eliminated → #4 (65A) selected
        cable = select_cable(
            motor_amps=45.0,
            pump_depth=5900.0,
            bottom_temp=170.0,
            casing_id=6.366,
            motor_od=4.56,
            catalog_manager=manager,
        )
        assert cable["cable_size"] == "#4"
        assert cable["conductor"] == "CU"

    def test_example_p8_selects_2cu(self, manager):
        # motor_amps=58 → required=72.5 A → #4 (≤69A) eliminated → #2 (83A) selected
        cable = select_cable(
            motor_amps=58.0,
            pump_depth=3500.0,
            bottom_temp=185.0,
            casing_id=7.0,
            motor_od=5.44,
            catalog_manager=manager,
        )
        assert cable["cable_size"] == "#2"
        assert cable["conductor"] == "CU"

    def test_example_2a_drop_per_1000ft(self, manager):
        # #4 CU @ 170°F, 45 A → 24 V/1 000 ft
        cable = select_cable(
            motor_amps=45.0,
            pump_depth=5900.0,
            bottom_temp=170.0,
            casing_id=6.366,
            motor_od=4.56,
            catalog_manager=manager,
        )
        assert cable["voltage_drop_per_1000ft"] == pytest.approx(24.0, abs=0.5)

    def test_cable_length_pump_plus_100(self, manager):
        cable = select_cable(
            motor_amps=45.0,
            pump_depth=5900.0,
            bottom_temp=170.0,
            casing_id=6.366,
            motor_od=4.56,
            catalog_manager=manager,
        )
        assert cable["length_ft"] == pytest.approx(6000.0)

    def test_prefers_cu_over_al(self, manager):
        cable = select_cable(
            motor_amps=45.0,
            pump_depth=5900.0,
            bottom_temp=170.0,
            casing_id=6.366,
            motor_od=4.56,
            catalog_manager=manager,
        )
        assert cable["conductor"] == "CU"

    def test_returns_required_keys(self, manager):
        cable = select_cable(
            motor_amps=40.0,
            pump_depth=4000.0,
            bottom_temp=180.0,
            casing_id=6.366,
            motor_od=4.56,
            catalog_manager=manager,
        )
        for k in ("cable_size", "cable_type", "conductor", "manufacturer",
                  "length_ft", "voltage_drop_per_1000ft", "max_amps"):
            assert k in cable

    def test_max_amps_meets_derating(self, manager):
        motor_amps = 40.0
        cable = select_cable(
            motor_amps=motor_amps,
            pump_depth=4000.0,
            bottom_temp=180.0,
            casing_id=6.366,
            motor_od=4.56,
            catalog_manager=manager,
        )
        assert cable["max_amps"] >= motor_amps * 1.25

    def test_no_cable_raises(self, manager):
        # Motor too large + very tight casing → no cable fits
        with pytest.raises(ValueError):
            select_cable(
                motor_amps=9999.0,
                pump_depth=5000.0,
                bottom_temp=170.0,
                casing_id=5.0,
                motor_od=4.9,  # almost no annular clearance
                catalog_manager=manager,
            )

    def test_high_temp_requires_higher_rating(self, manager):
        # At 430°F bottom temp → min rating 455°F → Redalene (450°F) excluded
        # EPDM (500°F) should be selected if available
        cable = select_cable(
            motor_amps=30.0,
            pump_depth=4000.0,
            bottom_temp=430.0,
            casing_id=8.681,
            motor_od=5.40,
            catalog_manager=manager,
        )
        assert cable["max_amps"] >= 30.0 * 1.25


# ---------------------------------------------------------------------------
# 6 — select_motor
# ---------------------------------------------------------------------------

class TestSelectMotor:

    def test_hp_meets_margin(self, manager):
        motor = select_motor(79.0, manager, pump_od=4.0, bottom_temp=170.0, depth_ft=5000.0)
        assert motor["hp_rating"] >= 79.0 * 1.10

    def test_od_within_casing_proxy(self, manager):
        pump_od = 4.0
        motor = select_motor(79.0, manager, pump_od=pump_od, bottom_temp=170.0, depth_ft=5000.0)
        assert motor["od_inches"] <= pump_od * 1.20

    def test_temp_rating_adequate(self, manager):
        motor = select_motor(79.0, manager, pump_od=4.0, bottom_temp=170.0, depth_ft=5000.0)
        assert motor["max_temp_f"] >= 170.0 + 25.0

    def test_low_hp_lower_voltage(self, manager):
        # ≤70 HP → target 800 V → catalog motor closest to 800 V
        motor = select_motor(50.0, manager, pump_od=4.0, bottom_temp=150.0, depth_ft=3000.0)
        assert motor["hp_rating"] >= 50.0 * 1.10
        # 456-60HP-860V should be closest to 800V for pump_od=4.0
        assert motor["voltage"] <= 1200

    def test_medium_hp_medium_voltage(self, manager):
        # 71–200 HP → target 1 200 V
        motor = select_motor(150.0, manager, pump_od=5.13, bottom_temp=200.0, depth_ft=5000.0)
        assert motor["hp_rating"] >= 150.0 * 1.10

    def test_high_hp_high_voltage(self, manager):
        # >200 HP → target 2 000 V
        motor = select_motor(300.0, manager, pump_od=5.62, bottom_temp=200.0, depth_ft=6000.0)
        assert motor["hp_rating"] >= 300.0 * 1.10
        assert motor["voltage"] >= 1500

    def test_returns_dict_with_standard_keys(self, manager):
        motor = select_motor(79.0, manager, pump_od=4.0, bottom_temp=170.0, depth_ft=5000.0)
        for k in ("hp_rating", "voltage", "amperage", "od_inches", "max_temp_f"):
            assert k in motor

    def test_no_motor_raises(self, manager):
        with pytest.raises(ValueError):
            select_motor(99999.0, manager, pump_od=0.1, bottom_temp=170.0, depth_ft=5000.0)

    def test_selects_smallest_qualifying_hp(self, manager):
        # Requesting 50 HP: should return the smallest HP ≥ 55 available in catalog
        motor = select_motor(50.0, manager, pump_od=5.13, bottom_temp=150.0, depth_ft=3000.0)
        # Verify it picked the minimum, not an oversized motor
        all_motors = manager._motors
        qualifying_hps = sorted(
            set(m["hp_rating"] for m in all_motors if m["hp_rating"] >= 55.0)
        )
        assert motor["hp_rating"] == qualifying_hps[0]


# ---------------------------------------------------------------------------
# 7 — electrical_design_complete (integration)
# ---------------------------------------------------------------------------

class TestElectricalDesignComplete:

    def test_returns_dict_with_required_keys(self, manager, well_7in, base_fluid):
        result = electrical_design_complete(100.0, 4.56, well_7in, base_fluid, manager)
        for k in ("motor", "cable", "cable_voltage_drop_v",
                  "surface_voltage_v", "kva_required", "transformer"):
            assert k in result

    def test_motor_hp_adequate(self, manager, well_7in, base_fluid):
        result = electrical_design_complete(100.0, 4.56, well_7in, base_fluid, manager)
        assert result["motor"]["hp_rating"] >= 100.0 * 1.10

    def test_cable_is_copper(self, manager, well_7in, base_fluid):
        result = electrical_design_complete(100.0, 4.56, well_7in, base_fluid, manager)
        assert result["cable"]["conductor"] == "CU"

    def test_voltage_drop_positive(self, manager, well_7in, base_fluid):
        result = electrical_design_complete(100.0, 4.56, well_7in, base_fluid, manager)
        assert result["cable_voltage_drop_v"] > 0.0

    def test_surface_voltage_exceeds_motor_voltage(self, manager, well_7in, base_fluid):
        result = electrical_design_complete(100.0, 4.56, well_7in, base_fluid, manager)
        assert result["surface_voltage_v"] > result["motor"]["voltage"]

    def test_kva_positive(self, manager, well_7in, base_fluid):
        result = electrical_design_complete(100.0, 4.56, well_7in, base_fluid, manager)
        assert result["kva_required"] > 0.0

    def test_transformer_covers_kva_demand(self, manager, well_7in, base_fluid):
        result = electrical_design_complete(100.0, 4.56, well_7in, base_fluid, manager)
        assert result["transformer"]["total_kva"] >= result["kva_required"]

    def test_large_well_i300_scenario(self, manager, well_9in, base_fluid):
        """High-power scenario with 9-5/8″ casing and large motor."""
        result = electrical_design_complete(180.0, 7.38, well_9in, base_fluid, manager)
        assert result["motor"]["hp_rating"] >= 180.0 * 1.10
        assert result["motor"]["od_inches"] <= 7.38 * 1.20
        assert result["transformer"]["total_kva"] >= result["kva_required"]

    def test_surface_voltage_formula_consistent(self, manager, well_7in, base_fluid):
        result = electrical_design_complete(100.0, 4.56, well_7in, base_fluid, manager)
        expected_vs = calculate_surface_voltage(
            result["motor"]["voltage"],
            result["cable_voltage_drop_v"],
        )
        assert result["surface_voltage_v"] == pytest.approx(expected_vs, rel=1e-9)

    def test_kva_formula_consistent(self, manager, well_7in, base_fluid):
        result = electrical_design_complete(100.0, 4.56, well_7in, base_fluid, manager)
        expected_kva = calculate_kva(
            result["surface_voltage_v"],
            result["motor"]["amperage"],
        )
        assert result["kva_required"] == pytest.approx(expected_kva, rel=1e-9)
