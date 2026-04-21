"""
Tests for the equipment catalog loader.
Validates against Kermit Brown examples and physical consistency rules.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from catalogs.loader import CatalogManager
from core.models import PumpCurve

CATALOG_DIR = str(Path(__file__).parent.parent / "catalogs")


@pytest.fixture(scope="module")
def manager() -> CatalogManager:
    return CatalogManager(CATALOG_DIR)


@pytest.fixture(scope="module")
def d40(manager: CatalogManager) -> PumpCurve:
    pumps = manager.get_all_pumps()
    match = [p for p in pumps if p.model == "D-40"]
    assert match, "D-40 not found in catalog"
    return match[0]


@pytest.fixture(scope="module")
def i300(manager: CatalogManager) -> PumpCurve:
    pumps = manager.get_all_pumps()
    match = [p for p in pumps if p.model == "I-300"]
    assert match, "I-300 not found in catalog"
    return match[0]


# ---------------------------------------------------------------------------
# Catalog loading
# ---------------------------------------------------------------------------

class TestCatalogLoading:
    def test_at_least_10_pumps(self, manager):
        assert len(manager.get_all_pumps()) >= 10

    def test_all_pumps_are_pump_curve_instances(self, manager):
        for p in manager.get_all_pumps():
            assert isinstance(p, PumpCurve)

    def test_at_least_15_motors(self, manager):
        assert len(manager._motors) >= 15

    def test_cables_loaded(self, manager):
        assert len(manager._cables) >= 10

    def test_seals_loaded(self, manager):
        assert len(manager._seals) >= 10

    def test_pumps_have_points(self, manager):
        for pump in manager.get_all_pumps():
            assert len(pump.points) >= 10, f"{pump.model} has fewer than 10 curve points"

    def test_pump_head_monotonically_decreasing(self, manager):
        for pump in manager.get_all_pumps():
            heads = [p.head_per_stage for p in pump.points]
            for i in range(1, len(heads)):
                assert heads[i] <= heads[i - 1], (
                    f"{pump.model}: head not monotone at index {i} "
                    f"({heads[i-1]} -> {heads[i]})"
                )

    def test_pump_efficiency_positive(self, manager):
        for pump in manager.get_all_pumps():
            for pt in pump.points:
                assert 0.0 < pt.efficiency <= 1.0

    def test_pump_bep_in_range(self, manager):
        for pump in manager.get_all_pumps():
            assert pump.min_flow <= pump.bep_flow <= pump.max_flow


# ---------------------------------------------------------------------------
# Pump curve interpolation — Book Example #2A (Kermit Brown, Vol. 2b)
# ---------------------------------------------------------------------------

class TestInterpolationD40:
    """Reda D-40 at 1227 bpd: head ≈ 23 ft/stage, hp ≈ 0.35 hp/stage."""

    def test_head_at_1227_bpd(self, manager, d40):
        result = manager.interpolate_pump_curve(d40, 1227)
        assert result["head_per_stage"] == pytest.approx(23.0, rel=0.02), (
            f"Expected ~23 ft/stage, got {result['head_per_stage']:.2f}"
        )

    def test_hp_at_1227_bpd(self, manager, d40):
        result = manager.interpolate_pump_curve(d40, 1227)
        assert result["hp_per_stage"] == pytest.approx(0.35, rel=0.03), (
            f"Expected ~0.35 hp/stage, got {result['hp_per_stage']:.3f}"
        )

    def test_efficiency_at_1227_positive(self, manager, d40):
        result = manager.interpolate_pump_curve(d40, 1227)
        assert 0.0 < result["efficiency"] <= 1.0

    def test_head_at_bep_higher_than_at_max(self, manager, d40):
        bep = manager.interpolate_pump_curve(d40, d40.bep_flow)
        at_max = manager.interpolate_pump_curve(d40, d40.max_flow)
        assert bep["head_per_stage"] > at_max["head_per_stage"]

    def test_out_of_range_raises(self, manager, d40):
        min_q = min(p.flow_rate for p in d40.points)
        max_q = max(p.flow_rate for p in d40.points)
        with pytest.raises(ValueError):
            manager.interpolate_pump_curve(d40, min_q - 1.0)
        with pytest.raises(ValueError):
            manager.interpolate_pump_curve(d40, max_q + 1.0)


# ---------------------------------------------------------------------------
# Pump curve interpolation — Book Example #1A (Kermit Brown, Vol. 2b)
# ---------------------------------------------------------------------------

class TestInterpolationI300:
    """Centrilift I-300 at 10000 bpd: head ≈ 59.5 ft/stage."""

    def test_head_at_10000_bpd(self, manager, i300):
        result = manager.interpolate_pump_curve(i300, 10000)
        assert result["head_per_stage"] == pytest.approx(59.5, rel=0.02), (
            f"Expected ~59.5 ft/stage, got {result['head_per_stage']:.2f}"
        )

    def test_hp_at_10000_bpd_positive(self, manager, i300):
        result = manager.interpolate_pump_curve(i300, 10000)
        assert result["hp_per_stage"] > 0

    def test_i300_od_fits_in_8625_casing(self, i300):
        # 8-5/8" casing 24 lb/ft has ID ≈ 7.825" — I-300 OD must be below this
        assert i300.od < 7.825


# ---------------------------------------------------------------------------
# Casing filter — 5.5" nominal casing
# ---------------------------------------------------------------------------

class TestCasingFilter:
    """For a 5.5" nominal casing the drift ID is ~4.892" (17 lb/ft).
    Only 400-series (4.00" OD) pumps should pass; 513-series and larger must not.
    """

    CASING_ID_5_5 = 4.892  # ID of 5.5" 17 lb/ft casing [in]

    def test_400_series_passes(self, manager):
        result = manager.get_pumps_by_casing(self.CASING_ID_5_5)
        models_found = {p.model for p in result}
        assert "D-40" in models_found
        assert "D-55" in models_found
        assert "D-82" in models_found

    def test_513_series_excluded(self, manager):
        result = manager.get_pumps_by_casing(self.CASING_ID_5_5)
        excluded_models = {"I-42B", "Y-62B", "N-80", "Z-69"}
        found_excluded = {p.model for p in result} & excluded_models
        assert not found_excluded, (
            f"513-series pumps should not fit in 5.5\" casing, but found: {found_excluded}"
        )

    def test_large_pumps_excluded(self, manager):
        result = manager.get_pumps_by_casing(self.CASING_ID_5_5)
        excluded = {p.model for p in result} & {"I-300", "G-52E"}
        assert not excluded

    def test_filter_returns_list(self, manager):
        result = manager.get_pumps_by_casing(self.CASING_ID_5_5)
        assert isinstance(result, list)

    def test_larger_casing_includes_513(self, manager):
        # 7" casing ID ≈ 6.276" should admit 5.13" pumps
        result = manager.get_pumps_by_casing(6.276)
        series_found = {p.series for p in result}
        assert "513" in series_found


# ---------------------------------------------------------------------------
# Flow range filter
# ---------------------------------------------------------------------------

class TestFlowRangeFilter:
    def test_1227_bpd_matches_d40(self, manager):
        result = manager.get_pumps_by_flow_range(1227)
        models = {p.model for p in result}
        assert "D-40" in models

    def test_10000_bpd_matches_i300(self, manager):
        result = manager.get_pumps_by_flow_range(10000)
        models = {p.model for p in result}
        assert "I-300" in models

    def test_10000_bpd_excludes_small_pumps(self, manager):
        result = manager.get_pumps_by_flow_range(10000)
        models = {p.model for p in result}
        assert "D-40" not in models
        assert "M-34" not in models

    def test_very_high_flow_returns_empty_or_only_large(self, manager):
        result = manager.get_pumps_by_flow_range(50000)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Motor query
# ---------------------------------------------------------------------------

class TestMotorQuery:
    def test_get_motor_returns_dict(self, manager):
        motor = manager.get_motor(hp=50, voltage=860, series="456")
        assert isinstance(motor, dict)
        assert "hp_rating" in motor

    def test_motor_hp_at_least_requested(self, manager):
        motor = manager.get_motor(hp=50, voltage=1000, series="456")
        assert motor["hp_rating"] >= 50

    def test_motor_fallback_ignores_series(self, manager):
        # Series "999" doesn't exist — should fall back to any series
        motor = manager.get_motor(hp=30, voltage=700, series="999")
        assert motor["hp_rating"] >= 30

    def test_motor_no_match_raises(self, manager):
        with pytest.raises(ValueError):
            manager.get_motor(hp=99999, voltage=440, series="375")


# ---------------------------------------------------------------------------
# Cable query
# ---------------------------------------------------------------------------

class TestCableQuery:
    def test_get_cable_returns_dict(self, manager):
        cable = manager.get_cable(amps=40, temp_f=150, voltage=1000)
        assert isinstance(cable, dict)
        assert "max_amps" in cable

    def test_cable_rated_for_amps(self, manager):
        cable = manager.get_cable(amps=40, temp_f=150, voltage=1000)
        assert cable["max_amps"] >= 40

    def test_cable_rated_for_temp(self, manager):
        cable = manager.get_cable(amps=40, temp_f=350, voltage=1000)
        assert cable["max_temp_f"] >= 350

    def test_no_cable_raises(self, manager):
        with pytest.raises(ValueError):
            manager.get_cable(amps=9999, temp_f=150, voltage=1000)

    def test_high_temp_requires_epdm(self, manager):
        # EPDM is the only type rated for 350 °F+ (max_temp_f = 400 °F)
        cable = manager.get_cable(amps=40, temp_f=350, voltage=1000)
        assert cable["max_temp_f"] >= 350
        assert cable["type"] == "EPDM"
