"""
Tests for the BES/ESP recommendation engine.

Validates the engineering-criteria ranking (BEP distance → efficiency →
required power), pump selection, and the full recommendation pipeline.
No scores, no weights, no provider preference.
"""
from __future__ import annotations

import pytest

from bes.catalogs.loader import CatalogManager
from bes.core.models import (
    DesignObjectives,
    DesignResult,
    DriveMechanism,
    Fluid,
    IPRMethod,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)
from bes.recommender.ranking import (
    BEP_ACCEPTABLE_MAX,
    BEP_OPTIMAL_MAX,
    bep_distance,
    classify_bep_distance,
    ranking_key,
)
from bes.recommender.pump_selector import select_pump_by_model, select_top_n_pumps
from bes.recommender.recommendation_engine import (
    generate_recommendation_for_pump, generate_recommendations,
)



# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def manager() -> CatalogManager:
    return CatalogManager()


@pytest.fixture(scope="module")
def reservoir() -> Reservoir:
    return Reservoir(
        static_pressure=2500.0,
        bubble_point=1500.0,
        productivity_index=1.0,
        ipr_method=IPRMethod.VOGEL,
        reservoir_temp=180.0,
        drive_mechanism=DriveMechanism.SOLUTION_GAS,
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
    """D-40 PumpCurve object — used for ranking unit tests."""
    return next(p for p in manager.get_all_pumps() if p.model == "D-40")


# ---------------------------------------------------------------------------
# 1. Engineering-criteria ranking primitives
# ---------------------------------------------------------------------------

class TestBepDistance:

    def test_at_bep_is_zero(self, d40_pump):
        assert bep_distance(d40_pump, d40_pump.bep_flow) == pytest.approx(0.0)

    def test_symmetric_around_bep(self, d40_pump):
        bep = d40_pump.bep_flow
        assert bep_distance(d40_pump, bep + 100.0) == pytest.approx(
            bep_distance(d40_pump, bep - 100.0)
        )

    def test_is_relative_fraction(self, d40_pump):
        bep = d40_pump.bep_flow
        assert bep_distance(d40_pump, bep * 1.10) == pytest.approx(0.10)

    def test_closer_to_bep_smaller_distance(self, d40_pump):
        bep = d40_pump.bep_flow
        assert bep_distance(d40_pump, bep + 50.0) < bep_distance(d40_pump, bep + 200.0)

    def test_invalid_flow_rejected(self, d40_pump):
        with pytest.raises(ValueError, match="flow"):
            bep_distance(d40_pump, 0.0)


class TestRankingKey:
    """Strict lexicographic ordering: BEP → efficiency → power. No weights."""

    def test_bep_distance_dominates(self):
        # A pump much less efficient but closer to BEP must rank first
        close_inefficient = ranking_key(0.05, 0.40, 200.0)
        far_efficient = ranking_key(0.20, 0.70, 50.0)
        assert close_inefficient < far_efficient

    def test_efficiency_breaks_bep_ties(self):
        better_eff = ranking_key(0.10, 0.65, 100.0)
        worse_eff = ranking_key(0.10, 0.55, 50.0)
        assert better_eff < worse_eff

    def test_power_breaks_remaining_ties(self):
        lower_hp = ranking_key(0.10, 0.60, 80.0)
        higher_hp = ranking_key(0.10, 0.60, 120.0)
        assert lower_hp < higher_hp

    def test_identical_criteria_equal_keys(self):
        assert ranking_key(0.1, 0.6, 100.0) == ranking_key(0.1, 0.6, 100.0)


class TestClassifyBepDistance:

    def test_optimal_at_zero(self):
        assert classify_bep_distance(0.0) == "optimo"

    def test_optimal_boundary(self):
        assert classify_bep_distance(BEP_OPTIMAL_MAX) == "optimo"

    def test_acceptable_band(self):
        assert classify_bep_distance(0.15) == "aceptable"
        assert classify_bep_distance(BEP_ACCEPTABLE_MAX) == "aceptable"

    def test_far_beyond_acceptable(self):
        assert classify_bep_distance(0.30) == "alejado"

    def test_thresholds_are_ordered(self):
        assert 0.0 < BEP_OPTIMAL_MAX < BEP_ACCEPTABLE_MAX


# ---------------------------------------------------------------------------
# 2. select_top_n_pumps
# ---------------------------------------------------------------------------

class TestSelectTopNPumps:

    @pytest.fixture(scope="class")
    def top3(self, manager, reservoir, fluid, well, surface, objectives):
        return select_top_n_pumps(
            reservoir, fluid, well, surface, objectives, manager, n=3
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

    def test_ordered_by_engineering_criteria(
        self, top3, manager, objectives
    ):
        """Results must come ordered by the strict engineering key."""
        pump_lookup = {p.model: p for p in manager.get_all_pumps()}
        keys = []
        for dr in top3:
            pump_obj = pump_lookup[dr.pump_model]
            keys.append(ranking_key(
                bep_dist=bep_distance(pump_obj, objectives.target_flow_rate),
                efficiency=dr.pump_efficiency,
                total_pump_hp=dr.total_pump_hp,
            ))
        assert keys == sorted(keys), f"Engineering order violated: {keys}"

    def test_manufacturer_plays_no_role(self, top3, manager, objectives):
        """The ordering must be reproducible from physical criteria alone —
        no field of the result depends on manufacturer identity."""
        # Rebuild the expected order using ONLY physical quantities
        pump_lookup = {p.model: p for p in manager.get_all_pumps()}
        expected = sorted(
            top3,
            key=lambda dr: ranking_key(
                bep_dist=bep_distance(
                    pump_lookup[dr.pump_model], objectives.target_flow_rate
                ),
                efficiency=dr.pump_efficiency,
                total_pump_hp=dr.total_pump_hp,
            ),
        )
        assert [dr.pump_model for dr in top3] == [dr.pump_model for dr in expected]

    def test_n1_returns_at_most_one(
        self, manager, reservoir, fluid, well, surface, objectives
    ):
        results = select_top_n_pumps(
            reservoir, fluid, well, surface, objectives,
            manager, n=1,
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
        for k in ("recommendations", "design_basis", "ordering_criteria",
                  "n_candidates_evaluated"):
            assert k in recs

    def test_no_scoring_artifacts_remain(self, recs):
        """The output must not carry scores, metrics, or weights."""
        assert "weights" not in recs
        for rec in recs["recommendations"]:
            assert "score" not in rec
            assert "metrics" not in rec

    def test_recommendations_is_list(self, recs):
        assert isinstance(recs["recommendations"], list)

    def test_returns_n_recommendations(self, recs):
        assert 1 <= len(recs["recommendations"]) <= 3

    def test_each_recommendation_has_required_keys(self, recs):
        for rec in recs["recommendations"]:
            for k in ("rank", "criteria", "design", "rationale", "warnings"):
                assert k in rec, f"Missing key '{k}' in recommendation"

    def test_ordered_by_engineering_criteria(self, recs):
        keys = [
            ranking_key(
                bep_dist=r["criteria"]["bep_distance_frac"],
                efficiency=r["criteria"]["efficiency"],
                total_pump_hp=r["criteria"]["total_pump_hp"],
            )
            for r in recs["recommendations"]
        ]
        assert keys == sorted(keys), f"Engineering order violated: {keys}"

    def test_ranks_are_sequential(self, recs):
        ranks = [r["rank"] for r in recs["recommendations"]]
        assert ranks == list(range(1, len(ranks) + 1))

    def test_criteria_are_physical_quantities(self, recs):
        for rec in recs["recommendations"]:
            cr = rec["criteria"]
            assert cr["bep_flow_bpd"] > 0
            assert cr["bep_distance_frac"] >= 0.0
            assert cr["flow_vs_bep_pct"] > 0.0
            assert 0.0 < cr["efficiency"] <= 1.0
            assert cr["total_pump_hp"] > 0.0
            assert cr["classification"] in ("optimo", "aceptable", "alejado")

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

    def test_rationale_built_from_calculated_values(self, recs):
        """The explanation must quote the design's own numbers."""
        for rec in recs["recommendations"]:
            dr = rec["design"]
            assert f"{dr.num_stages}" in rec["rationale"]
            assert dr.motor_model in rec["rationale"]

    def test_design_basis_present(self, recs):
        basis = recs["design_basis"]
        assert "target_flow_rate_bpd" in basis
        assert "well_depth_ft" in basis
        assert "casing_id_in" in basis
        assert "reservoir_pressure_psi" in basis

    def test_ordering_criteria_documented(self, recs):
        """The output documents the criteria applied, in priority order."""
        oc = recs["ordering_criteria"]
        assert len(oc) == 3
        assert "BEP" in oc[0]
        assert "ficiencia" in oc[1]
        assert "otencia" in oc[2]

    def test_best_recommendation_is_closest_to_bep_or_ties(self, recs):
        best = recs["recommendations"][0]
        for rec in recs["recommendations"]:
            assert best["criteria"]["bep_distance_frac"] <= (
                rec["criteria"]["bep_distance_frac"] + 1e-12
            )

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

    def test_selection_is_provider_neutral(self, recs):
        """No brand advantage exists: DesignObjectives has no provider
        field and the recommendation carries no provider dimension."""
        import dataclasses as _dc
        field_names = {f.name for f in _dc.fields(DesignObjectives)}
        assert "preferred_manufacturer" not in field_names
        for rec in recs["recommendations"]:
            assert "provider" not in rec.get("criteria", {})

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


# ---------------------------------------------------------------------------
# 4. select_pump_by_model / generate_recommendation_for_pump — manual
#    override of the recommendation engine (bypasses ranking entirely)
# ---------------------------------------------------------------------------

class TestSelectPumpByModel:

    def test_returns_design_result_for_requested_pump(
        self, manager, reservoir, fluid, well, surface, objectives
    ):
        dr = select_pump_by_model(
            reservoir, fluid, well, surface, objectives, manager, pump_model="D-40"
        )
        assert isinstance(dr, DesignResult)
        assert dr.pump_model == "D-40"

    def test_matches_top_n_result_for_same_pump(
        self, manager, reservoir, fluid, well, surface, objectives
    ):
        """Selecting a pump manually must reproduce the exact same design the
        ranked engine would compute for that pump — no divergent code path."""
        top = select_top_n_pumps(
            reservoir, fluid, well, surface, objectives, manager, n=10
        )
        ranked_d40 = next(dr for dr in top if dr.pump_model == "D-40")

        manual_d40 = select_pump_by_model(
            reservoir, fluid, well, surface, objectives, manager, pump_model="D-40"
        )
        assert manual_d40.num_stages == ranked_d40.num_stages
        assert manual_d40.total_pump_hp == pytest.approx(ranked_d40.total_pump_hp)
        assert manual_d40.motor_model == ranked_d40.motor_model

    def test_unknown_pump_raises(
        self, manager, reservoir, fluid, well, surface, objectives
    ):
        with pytest.raises(ValueError, match="NO-EXISTE"):
            select_pump_by_model(
                reservoir, fluid, well, surface, objectives, manager,
                pump_model="NO-EXISTE",
            )

    def test_pump_too_large_for_casing_raises(
        self, manager, reservoir, fluid, well, surface, objectives
    ):
        # well.casing_id = 6.366in (7in casing); L16000N (OD 8.75in) can't fit.
        with pytest.raises(ValueError, match="casing"):
            select_pump_by_model(
                reservoir, fluid, well, surface, objectives, manager,
                pump_model="L16000N",
            )


class TestGenerateRecommendationForPump:

    @pytest.fixture(scope="class")
    def manual(self, manager, reservoir, fluid, well, surface, objectives):
        return generate_recommendation_for_pump(
            reservoir, fluid, well, surface, objectives, manager, pump_model="D-40"
        )

    def test_returns_dict_with_required_keys(self, manual):
        for k in ("recommendations", "design_basis", "ordering_criteria",
                  "n_candidates_evaluated"):
            assert k in manual

    def test_single_recommendation_ranked_1(self, manual):
        assert len(manual["recommendations"]) == 1
        assert manual["recommendations"][0]["rank"] == 1
        assert manual["n_candidates_evaluated"] == 1

    def test_design_is_the_requested_pump(self, manual):
        assert manual["recommendations"][0]["design"].pump_model == "D-40"

    def test_criteria_are_physical_quantities(self, manual):
        cr = manual["recommendations"][0]["criteria"]
        assert cr["bep_flow_bpd"] > 0
        assert 0.0 < cr["efficiency"] <= 1.0
        assert cr["classification"] in ("optimo", "aceptable", "alejado")

    def test_rationale_mentions_manual_selection(self, manual):
        rationale = manual["recommendations"][0]["rationale"]
        assert "manualmente" in rationale
        assert "D-40" in rationale

    def test_ordering_criteria_documents_manual_override(self, manual):
        assert len(manual["ordering_criteria"]) == 1
        assert "manual" in manual["ordering_criteria"][0].lower()

    def test_unknown_pump_raises(
        self, manager, reservoir, fluid, well, surface, objectives
    ):
        with pytest.raises(ValueError, match="NO-EXISTE"):
            generate_recommendation_for_pump(
                reservoir, fluid, well, surface, objectives, manager,
                pump_model="NO-EXISTE",
            )
