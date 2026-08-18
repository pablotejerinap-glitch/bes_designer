"""
Fetkovich IPR — end-to-end wiring tests.

Anchored to a published example: Beggs, "Production Optimization Using Nodal
Analysis", Example 2-10 (Ch. 2):

    Data: Pr = 2000 psia, n = 0.854, C = 0.00044 STB/d/psia^(2·0.854)
    Equation: qo = 0.00044 · (2000² − Pwf²)^0.854

    Printed table:
        Pwf (psia) | qo (STB/d)
        2000       | 0
        1500       | 94
        1000       | 150
        500        | 181
        0 (AOF)    | 191

Tolerance ±2 % (book values are rounded to integers).
"""
from __future__ import annotations

import warnings

import pytest

from bes.catalogs.loader import CatalogManager
from bes.core.ipr import (
    calculate_pwf_for_target_rate,
    fetkovich_ipr,
    generate_ipr_curve,
    vogel_ipr,
)
from bes.core.models import (
    DesignObjectives,
    DriveMechanism,
    Fluid,
    IPRMethod,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)

# Beggs Example 2-10 parameters
PR = 2000.0
C_BEGGS = 0.00044
N_BEGGS = 0.854

# Printed (Pwf, qo) pairs from the book table
BEGGS_TABLE = [
    (2000.0, 0.0),
    (1500.0, 94.0),
    (1000.0, 150.0),
    (500.0, 181.0),
    (0.0, 191.0),
]


def _beggs_reservoir(**overrides) -> Reservoir:
    """Reservoir carrying the Beggs 2-10 Fetkovich parameters."""
    kwargs = dict(
        static_pressure=PR,
        bubble_point=1500.0,
        productivity_index=1.0,   # unused by FETKOVICH; required field
        ipr_method=IPRMethod.FETKOVICH,
        reservoir_temp=180.0,
        drive_mechanism=DriveMechanism.SOLUTION_GAS,
        fetkovich_c=C_BEGGS,
        fetkovich_n=N_BEGGS,
    )
    kwargs.update(overrides)
    return Reservoir(**kwargs)


# ---------------------------------------------------------------------------
# 1. q(Pwf) reproduces the printed table
# ---------------------------------------------------------------------------

class TestBeggsTable:
    @pytest.mark.parametrize("pwf,q_book", BEGGS_TABLE)
    def test_direct_equation(self, pwf: float, q_book: float):
        q = fetkovich_ipr(PR, pwf, C_BEGGS, N_BEGGS)
        if q_book == 0.0:
            assert q == pytest.approx(0.0, abs=1e-9)
        else:
            assert q == pytest.approx(q_book, rel=0.02)

    def test_curve_from_reservoir_params(self):
        """generate_ipr_curve must read C and n from the Reservoir object."""
        res = _beggs_reservoir()
        q_arr, pwf_arr = generate_ipr_curve(res, n_points=201)
        # Interpolate the generated curve at the book's Pwf points
        import numpy as np
        for pwf, q_book in BEGGS_TABLE:
            if q_book == 0.0:
                continue
            q_interp = float(np.interp(pwf, pwf_arr[::-1], q_arr[::-1]))
            assert q_interp == pytest.approx(q_book, rel=0.02), f"Pwf={pwf}"


# ---------------------------------------------------------------------------
# 2. AOF
# ---------------------------------------------------------------------------

class TestAOF:
    def test_aof_191(self):
        res = _beggs_reservoir()
        q_arr, pwf_arr = generate_ipr_curve(res, n_points=51)
        aof = float(q_arr[-1])           # q at Pwf = 0
        assert float(pwf_arr[-1]) == pytest.approx(0.0, abs=1e-9)
        assert aof == pytest.approx(191.0, rel=0.02)


# ---------------------------------------------------------------------------
# 3. Inverse solver consistency
# ---------------------------------------------------------------------------

class TestInverse:
    def test_pwf_for_150_is_1000(self):
        res = _beggs_reservoir()
        pwf = calculate_pwf_for_target_rate(res, target_rate=150.0)
        assert pwf == pytest.approx(1000.0, rel=0.02)

    def test_explicit_args_still_override(self):
        """Explicit C/n args must keep working (backward compatibility)."""
        res = _beggs_reservoir()
        pwf = calculate_pwf_for_target_rate(
            res, target_rate=150.0, fetkovich_c=C_BEGGS, fetkovich_n=N_BEGGS
        )
        assert pwf == pytest.approx(1000.0, rel=0.02)

    def test_rate_above_aof_rejected(self):
        res = _beggs_reservoir()
        with pytest.raises(ValueError, match="AOF"):
            calculate_pwf_for_target_rate(res, target_rate=500.0)


# ---------------------------------------------------------------------------
# 4. Early, clear validation errors
# ---------------------------------------------------------------------------

class TestValidation:
    def test_missing_c_and_n_fails_at_construction(self):
        with pytest.raises(ValueError, match="fetkovich_c and fetkovich_n"):
            _beggs_reservoir(fetkovich_c=None, fetkovich_n=None)

    def test_missing_c_fails_at_construction(self):
        with pytest.raises(ValueError, match="fetkovich_c and fetkovich_n"):
            _beggs_reservoir(fetkovich_c=None)

    def test_missing_n_fails_at_construction(self):
        with pytest.raises(ValueError, match="fetkovich_c and fetkovich_n"):
            _beggs_reservoir(fetkovich_n=None)

    def test_negative_c_rejected(self):
        with pytest.raises(ValueError, match="fetkovich_c must be > 0"):
            _beggs_reservoir(fetkovich_c=-0.001)

    def test_n_out_of_physical_range_rejected(self):
        with pytest.raises(ValueError, match=r"fetkovich_n must be in \[0.5, 1.0\]"):
            _beggs_reservoir(fetkovich_n=1.3)
        with pytest.raises(ValueError, match=r"fetkovich_n must be in \[0.5, 1.0\]"):
            _beggs_reservoir(fetkovich_n=0.3)

    def test_other_methods_do_not_require_params(self):
        res = _beggs_reservoir(ipr_method=IPRMethod.VOGEL,
                               fetkovich_c=None, fetkovich_n=None)
        assert res.fetkovich_c is None


# ---------------------------------------------------------------------------
# 5. End-to-end design with FETKOVICH
# ---------------------------------------------------------------------------

class TestEndToEndDesign:
    """Full recommendation run with a FETKOVICH reservoir.

    Built on the Beggs 2-10 equation with C scaled ×10 (C = 0.0044, same n)
    so the AOF (~1915 STB/d) supports a realistic ESP target of 1200 STB/d
    on the Example-2A well geometry.
    """

    @pytest.fixture(scope="class")
    def design_output(self) -> dict:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            reservoir = _beggs_reservoir(fetkovich_c=0.0044)

        fluid = Fluid(
            oil_api=35.0, water_cut=0.30, gor=150.0, gas_sg=0.65, water_sg=1.05,
            oil_viscosity_dead=5.0, viscosity_temp_ref=100.0,
            bubble_point_pressure=1500.0, h2s_content=0.0, co2_content=0.0,
            sand_production=False,
        )
        well = WellGeometry(
            total_depth=5000.0, casing_od=7.0, casing_weight=23.0, casing_id=6.366,
            tubing_od=2.875, tubing_id=2.441,
            perforations_top=4500.0, perforations_bottom=4800.0,
            deviation_max=5.0, wellhead_temp=80.0,
        )
        surface = SurfaceConditions(
            wellhead_pressure_required=100.0, flowline_length=1000.0,
            flowline_id=3.0, flowline_elevation_change=0.0,
            separator_pressure=50.0, power_supply_voltage=4160.0, frequency=60.0,
        )
        objectives = DesignObjectives(
            target_flow_rate=1200.0, safety_margin_depth=100.0,
            allow_gas_venting=False, max_gip=0.10,
            design_life_years=5.0, use_vsd=False,
        )

        from bes.recommender.recommendation_engine import generate_recommendations
        catalog = CatalogManager()
        return generate_recommendations(
            reservoir, fluid, well, surface, objectives, catalog, n=3
        )

    def test_produces_recommendations(self, design_output: dict):
        recs = design_output["recommendations"]
        assert len(recs) >= 1

    def test_top_design_is_complete(self, design_output: dict):
        dr = design_output["recommendations"][0]["design"]
        assert dr.num_stages > 0
        assert dr.total_pump_hp > 0
        assert dr.motor_hp > 0
        assert dr.surface_voltage_required > 0
        assert dr.flow_rate_achieved == pytest.approx(1200.0, rel=0.01)
