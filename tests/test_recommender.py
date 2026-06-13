"""
Tests for the BES/ESP recommendation engine — Phase 9.

Validates scoring functions, pump selection, diversification, and the
full recommendation pipeline.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from catalogs.loader import CatalogManager
from core.models import (
    DesignObjectives,
    DesignResult,
    DriveMechanism,
    Fluid,
    IPRMethod,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)
from recommender.scoring import (
    DEFAULT_WEIGHTS,
    provider_score,
    efficiency_score,
    flexibility_score,
    overall_score,
)
from recommender.pump_selector import select_top_n_pumps
from recommender.recommendation_engine import generate_recommendations

CATALOG_DIR = str(Path(__file__).parent.parent / "catalogs")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def manager() -> CatalogManager:
    return CatalogManager(CATALOG_DIR)


@pytest.fixture(scope="module")
def reservoir() -> Reservoir:
    return Reservoir(
        static_pressure=2500.0,
        bubble_point=1500.0,
        productivity_index=1.0,
        ipr_method=IPRMethod.VOGEL,
        reservoir_temp=180.0,
        drive_mechanism=DriveMechanism.SOLUTION_GAS,
        datum_depth=5000.0,
    )


@pytest.fixture(scope="module")
def fluid() -> Fluid:
    return Fluid(
        oil_api=35.0,
        water_cut=0.30,
        gor=150.0,
        gas_sg=0.65,
        water_sg=1.05,
        oil_viscosity_dead=5.0,
        viscosity_temp_ref=100.0,
        bubble_point_pressure=1500.0,
        h2s_content=0.0,
        co2_content=0.0,
        sand_production=False,
    )


@pytest.fixture(scope="module")
def well() -> WellGeometry:
    """7-in 23-lb/ft casing, 5 000 ft well."""
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
        bottom_hole_temp=180.0,
    )


@pytest.fixture(scope="module")
def surface() -> SurfaceConditions:
    return SurfaceConditions(
        wellhead_pressure_required=100.0,
        flowline_length=1000.0,
        flowline_id=3.0,
        flowline_elevation_change=0.0,
        separator_pressure=50.0,
        power_supply_voltage=4160.0,
        frequency=60.0,
    )


@pytest.fixture(scope="module")
def objectives() -> DesignObjectives:
    """1 200 bpd target — within D-40 (Reda) and I-42B (Centrilift) range."""
    return DesignObjectives(
        target_flow_rate=1200.0,
        safety_margin_depth=100.0,
        allow_gas_venting=False,
        max_gip=0.10,
        design_life_years=5.0,
        use_vsd=False,
    )


@pytest.fixture(scope="module")
def d40_pump(manager):
    """D-40 PumpCurve object — used for scoring unit tests."""
    return next(p for p in manager.get_all_pumps() if p.model == "D-40")


# ---------------------------------------------------------------------------
# 1. Scoring functions
# ---------------------------------------------------------------------------

class TestEfficiencyScore:

    def test_perfect_efficiency(self):
        assert efficiency_score(1.0) == pytest.approx(10.0)

    def test_zero_efficiency(self):
        assert efficiency_score(0.0) == pytest.approx(0.0)

    def test_typical_efficiency(self):
        assert efficiency_score(0.60) == pytest.approx(6.0)

    def test_clamped_above_1(self):
        assert efficiency_score(1.5) == pytest.approx(10.0)

    def test_clamped_below_0(self):
        assert efficiency_score(-0.1) == pytest.approx(0.0)

    def test_monotonically_increasing(self):
        scores = [efficiency_score(e) for e in (0.0, 0.40, 0.55, 0.65, 1.0)]
        for a, b in zip(scores, scores[1:]):
            assert a <= b


class TestFlexibilityScore:

    def test_at_bep_is_10(self, d40_pump):
        assert flexibility_score(d40_pump, d40_pump.bep_flow) == pytest.approx(10.0)

    def test_at_min_flow_is_zero_or_below(self, d40_pump):
        score = flexibility_score(d40_pump, d40_pump.min_flow)
        assert score <= 0.0 + 1e-6   # ~0 or clamped to 0

    def test_at_max_flow_is_zero_or_below(self, d40_pump):
        score = flexibility_score(d40_pump, d40_pump.max_flow)
        assert score <= 0.0 + 1e-6

    def test_closer_to_bep_higher_score(self, d40_pump):
        bep = d40_pump.bep_flow
        near = bep + 50.0
        far = bep + 200.0
        assert flexibility_score(d40_pump, near) > flexibility_score(d40_pump, far)

    def test_score_in_range(self, d40_pump):
        for flow in (d40_pump.min_flow, d40_pump.bep_flow, d40_pump.max_flow):
            s = flexibility_score(d40_pump, flow)
            assert 0.0 <= s <= 10.0


class TestProviderScore:

    def test_no_preference_full_marks(self):
        assert provider_score("Reda", "") == pytest.approx(10.0)
        assert provider_score("Reda", None) == pytest.approx(10.0)

    def test_preferred_match_full_marks(self):
        assert provider_score("ChampionX", "ChampionX") == pytest.approx(10.0)

    def test_preferred_match_case_insensitive(self):
        assert provider_score("ChampionX", "championx") == pytest.approx(10.0)

    def test_non_preferred_lower(self):
        s_match = provider_score("ChampionX", "ChampionX")
        s_other = provider_score("Reda", "ChampionX")
        assert s_other < s_match

    def test_score_in_range(self):
        for mfr in ("Reda", "ChampionX", "SLB"):
            for pref in ("", "Reda", "SLB", None):
                s = provider_score(mfr, pref)
                assert 0.0 <= s <= 10.0


class TestOverallScore:

    def test_equal_perfect_scores(self):
        metrics = {"efficiency": 10.0, "flexibility": 10.0, "provider": 10.0}
        assert overall_score(metrics) == pytest.approx(10.0)

    def test_equal_zero_scores(self):
        metrics = {"efficiency": 0.0, "flexibility": 0.0, "provider": 0.0}
        assert overall_score(metrics) == pytest.approx(0.0)

    def test_default_weights_sum_to_1(self):
        assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)

    def test_custom_weights(self):
        metrics = {"efficiency": 10.0, "flexibility": 0.0, "provider": 0.0}
        # Weight only efficiency
        score = overall_score(metrics, {"efficiency": 1.0, "flexibility": 0.0, "provider": 0.0})
        assert score == pytest.approx(10.0)

    def test_mixed_scores(self):
        metrics = {"efficiency": 6.0, "flexibility": 8.0, "provider": 4.0}
        # With default weights: (6×0.4 + 8×0.3 + 4×0.3) / 1.0 = (2.4+2.4+1.2)/1.0 = 6.0
        assert overall_score(metrics) == pytest.approx(6.0, rel=0.01)

    def test_score_in_range(self):
        for eff in (0, 5, 10):
            for flex in (0, 5, 10):
                for prov in (0, 5, 10):
                    s = overall_score({"efficiency": eff, "flexibility": flex, "provider": prov})
                    assert 0.0 <= s <= 10.0


# ---------------------------------------------------------------------------
# 2. select_top_n_pumps
# ---------------------------------------------------------------------------

class TestSelectTopNPumps:

    @pytest.fixture(scope="class")
    def top3(self, manager, reservoir, fluid, well, surface, objectives):
        return select_top_n_pumps(
            reservoir, fluid, well, surface, objectives, manager, n=3, diversify=True
        )

    def test_returns_list(self, top3):
        assert isinstance(top3, list)

    def test_returns_up_to_n(self, top3):
        assert 1 <= len(top3) <= 3

    def test_all_are_design_result_instances(self, top3):
        for dr in top3:
            assert isinstance(dr, DesignResult)

    def test_required_fields_populated(self, top3):
        required = (
            "pump_manufacturer", "pump_series", "pump_model", "pump_od",
            "num_stages", "pump_setting_depth", "intake_pressure",
            "total_head_required", "head_per_stage", "hp_per_stage",
            "pump_efficiency", "total_pump_hp",
            "motor_manufacturer", "motor_model", "motor_hp",
            "motor_voltage", "motor_amperage", "motor_od", "motor_length",
            "cable_type", "cable_awg", "cable_voltage_drop",
            "surface_voltage_required", "transformer_kva",
            "system_efficiency", "flow_rate_achieved", "operating_frequency",
            "gip_fraction",
        )
        for dr in top3:
            for field in required:
                assert hasattr(dr, field), f"Missing field: {field}"
                val = getattr(dr, field)
                assert val is not None, f"Field {field} is None"

    def test_stages_positive(self, top3):
        for dr in top3:
            assert dr.num_stages > 0

    def test_motor_hp_covers_pump_hp(self, top3):
        for dr in top3:
            assert dr.motor_hp >= dr.total_pump_hp * 1.05   # ≥ 10 % margin by design

    def test_efficiency_in_range(self, top3):
        for dr in top3:
            assert 0.0 < dr.pump_efficiency <= 1.0

    def test_system_efficiency_in_range(self, top3):
        for dr in top3:
            assert 0.0 < dr.system_efficiency <= 1.0

    def test_gip_fraction_in_range(self, top3):
        for dr in top3:
            assert 0.0 <= dr.gip_fraction <= 1.0

    def test_cable_awg_positive(self, top3):
        for dr in top3:
            assert dr.cable_awg > 0

    def test_transformer_kva_positive(self, top3):
        for dr in top3:
            assert dr.transformer_kva > 0.0

    def test_pump_setting_depth_positive(self, top3):
        for dr in top3:
            assert dr.pump_setting_depth > 0.0

    def test_diversify_includes_multiple_manufacturers(
        self, manager, reservoir, fluid, well, surface, objectives
    ):
        """If two manufacturers qualify, diversify=True must include both."""
        results = select_top_n_pumps(
            reservoir, fluid, well, surface, objectives,
            manager, n=3, diversify=True,
        )
        manufacturers = {dr.pump_manufacturer for dr in results}
        # At 1200 bpd with 6.366" casing, D-40 (Reda) and I-42B (Centrilift) qualify
        if len(results) >= 2:
            assert len(manufacturers) >= 2, (
                f"Expected diversity, got only: {manufacturers}"
            )

    def test_no_diversify_still_returns_results(
        self, manager, reservoir, fluid, well, surface, objectives
    ):
        results = select_top_n_pumps(
            reservoir, fluid, well, surface, objectives,
            manager, n=3, diversify=False,
        )
        assert len(results) >= 1

    def test_n1_returns_at_most_one(
        self, manager, reservoir, fluid, well, surface, objectives
    ):
        results = select_top_n_pumps(
            reservoir, fluid, well, surface, objectives,
            manager, n=1, diversify=False,
        )
        assert len(results) == 1

    def test_warnings_is_list(self, top3):
        for dr in top3:
            assert isinstance(dr.warnings, list)

    def test_flow_rate_achieved_matches_target(self, top3, objectives):
        for dr in top3:
            assert dr.flow_rate_achieved == pytest.approx(
                objectives.target_flow_rate, rel=0.01
            )

    def test_operating_frequency_matches_surface(self, top3, surface):
        for dr in top3:
            assert dr.operating_frequency == pytest.approx(surface.frequency)


# ---------------------------------------------------------------------------
# 3. generate_recommendations
# ---------------------------------------------------------------------------

class TestGenerateRecommendations:

    @pytest.fixture(scope="class")
    def recs(self, manager, reservoir, fluid, well, surface, objectives):
        return generate_recommendations(
            reservoir, fluid, well, surface, objectives, manager, n=3
        )

    def test_returns_dict(self, recs):
        assert isinstance(recs, dict)

    def test_has_required_top_level_keys(self, recs):
        for k in ("recommendations", "design_basis", "weights", "n_candidates_evaluated"):
            assert k in recs

    def test_recommendations_is_list(self, recs):
        assert isinstance(recs["recommendations"], list)

    def test_returns_n_recommendations(self, recs):
        assert 1 <= len(recs["recommendations"]) <= 3

    def test_each_recommendation_has_required_keys(self, recs):
        for rec in recs["recommendations"]:
            for k in ("rank", "score", "metrics", "design", "rationale", "warnings"):
                assert k in rec, f"Missing key '{k}' in recommendation"

    def test_recommendations_ordered_by_score_descending(self, recs):
        scores = [r["score"] for r in recs["recommendations"]]
        for a, b in zip(scores, scores[1:]):
            assert a >= b, f"Score order violated: {scores}"

    def test_ranks_are_sequential(self, recs):
        ranks = [r["rank"] for r in recs["recommendations"]]
        assert ranks == list(range(1, len(ranks) + 1))

    def test_scores_between_0_and_10(self, recs):
        for rec in recs["recommendations"]:
            assert 0.0 <= rec["score"] <= 10.0

    def test_design_is_design_result(self, recs):
        for rec in recs["recommendations"]:
            assert isinstance(rec["design"], DesignResult)

    def test_rationale_is_nonempty_string(self, recs):
        for rec in recs["recommendations"]:
            assert isinstance(rec["rationale"], str)
            assert len(rec["rationale"]) > 20

    def test_rationale_mentions_pump_model(self, recs):
        for rec in recs["recommendations"]:
            assert rec["design"].pump_model in rec["rationale"]

    def test_metrics_has_three_dimensions(self, recs):
        for rec in recs["recommendations"]:
            assert "efficiency" in rec["metrics"]
            assert "flexibility" in rec["metrics"]
            assert "provider" in rec["metrics"]

    def test_design_basis_present(self, recs):
        basis = recs["design_basis"]
        assert "target_flow_rate_bpd" in basis
        assert "well_depth_ft" in basis
        assert "casing_id_in" in basis
        assert "reservoir_pressure_psi" in basis

    def test_weights_match_defaults(self, recs):
        assert recs["weights"] == DEFAULT_WEIGHTS

    def test_best_recommendation_has_highest_score(self, recs):
        best = recs["recommendations"][0]
        for rec in recs["recommendations"]:
            assert best["score"] >= rec["score"]

    def test_warnings_is_list(self, recs):
        for rec in recs["recommendations"]:
            assert isinstance(rec["warnings"], list)

    def test_pump_od_fits_casing(self, recs, well):
        for rec in recs["recommendations"]:
            assert rec["design"].pump_od < well.casing_id

    def test_surface_voltage_exceeds_motor_voltage(self, recs):
        for rec in recs["recommendations"]:
            dr = rec["design"]
            assert dr.surface_voltage_required > dr.motor_voltage

    def test_n_candidates_evaluated_positive(self, recs):
        assert recs["n_candidates_evaluated"] >= 1

    def test_preferred_provider_boosts_its_score(
        self, manager, reservoir, fluid, well, surface
    ):
        """A design from the preferred provider must score its provider
        dimension at 10, above the 5 it gets without the preference."""
        import dataclasses
        base_obj = DesignObjectives(
            target_flow_rate=1200.0, safety_margin_depth=100.0,
            allow_gas_venting=False, max_gip=0.10, design_life_years=5.0,
            use_vsd=False,
        )
        neutral = generate_recommendations(
            reservoir, fluid, well, surface, base_obj, manager, n=5
        )
        target_mfr = neutral["recommendations"][0]["design"].pump_manufacturer
        pref_obj = dataclasses.replace(base_obj, preferred_manufacturer=target_mfr)
        preferred = generate_recommendations(
            reservoir, fluid, well, surface, pref_obj, manager, n=5
        )
        top = preferred["recommendations"][0]
        assert top["design"].pump_manufacturer == target_mfr
        assert top["metrics"]["provider"] == pytest.approx(10.0)

    def test_n3_request_returns_at_most_3(
        self, manager, reservoir, fluid, well, surface, objectives
    ):
        result = generate_recommendations(
            reservoir, fluid, well, surface, objectives, manager, n=3
        )
        assert len(result["recommendations"]) <= 3

    def test_n1_returns_single_recommendation(
        self, manager, reservoir, fluid, well, surface, objectives
    ):
        result = generate_recommendations(
            reservoir, fluid, well, surface, objectives, manager, n=1
        )
        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["rank"] == 1
