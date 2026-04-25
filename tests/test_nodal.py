"""
Tests for nodal analysis and the two new multiphase correlations.

Tolerances are set at ±20-30 % because the four correlations legitimately
disagree with each other by that margin on typical field cases.
"""
from __future__ import annotations

import pytest
import numpy as np

from core.models import (
    DriveMechanism,
    Fluid,
    IPRMethod,
    PumpCurve,
    PumpPerformancePoint,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)
from core.multiphase import poettmann_carpenter_gradient, duns_ros_gradient
from core.nodal_analysis import (
    compare_methods,
    find_operating_point,
    outflow_curve_natural,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fluid():
    return Fluid(
        oil_api=35.0,
        water_cut=0.4,
        gor=300.0,
        gas_sg=0.70,
        water_sg=1.05,
        oil_viscosity_dead=5.0,
        viscosity_temp_ref=100.0,
        bubble_point_pressure=1500.0,
        h2s_content=0.0,
        co2_content=0.0,
        sand_production=False,
    )


@pytest.fixture
def reservoir():
    return Reservoir(
        static_pressure=3000.0,
        bubble_point=1500.0,
        productivity_index=2.0,
        ipr_method=IPRMethod.VOGEL,
        reservoir_temp=180.0,
        drive_mechanism=DriveMechanism.SOLUTION_GAS,
        datum_depth=7000.0,
    )


@pytest.fixture
def well():
    return WellGeometry(
        total_depth=7000.0,
        casing_od=7.0,
        casing_weight=26.0,
        casing_id=6.276,
        tubing_od=2.875,
        tubing_id=2.441,
        perforations_top=6900.0,
        perforations_bottom=7000.0,
        deviation_max=0.0,
        wellhead_temp=75.0,
        bottom_hole_temp=180.0,
    )


@pytest.fixture
def surface():
    return SurfaceConditions(
        wellhead_pressure_required=150.0,
        flowline_length=500.0,
        flowline_id=3.0,
        flowline_elevation_change=0.0,
        separator_pressure=100.0,
        power_supply_voltage=3000.0,
        frequency=60.0,
    )


@pytest.fixture
def pump():
    pts = [
        PumpPerformancePoint(flow_rate=300,  head_per_stage=34.0, hp_per_stage=0.70, efficiency=0.55),
        PumpPerformancePoint(flow_rate=600,  head_per_stage=31.0, hp_per_stage=0.85, efficiency=0.67),
        PumpPerformancePoint(flow_rate=900,  head_per_stage=27.0, hp_per_stage=0.95, efficiency=0.71),
        PumpPerformancePoint(flow_rate=1200, head_per_stage=21.0, hp_per_stage=1.05, efficiency=0.65),
        PumpPerformancePoint(flow_rate=1500, head_per_stage=14.0, hp_per_stage=1.15, efficiency=0.55),
    ]
    return PumpCurve(
        manufacturer="TestMfg",
        series="TN1",
        model="TN1-900",
        od=4.0,
        min_flow=250.0,
        max_flow=1600.0,
        bep_flow=900.0,
        points=pts,
        max_stages=350,
        housing_options=[100, 150, 200, 250, 300, 350],
    )


# ---------------------------------------------------------------------------
# Parte A — gradient correlation smoke tests
# ---------------------------------------------------------------------------

def test_poettmann_gradient_liquid_only():
    """Pure water (GOR=0, WC=1) → gradient ≈ water_sg × 0.433 psi/ft."""
    water_sg = 1.05
    grad = poettmann_carpenter_gradient(
        q_liq=300.0, wc=1.0, gor=0.0,
        gas_sg=0.65, oil_api=30.0, water_sg=water_sg,
        p=2000.0, t=150.0, pipe_id=2.441, angle=90.0,
    )
    expected = water_sg * 0.433
    # Allow up to +30 % for friction, but must be above the hydrostatic
    assert expected * 0.92 <= grad <= expected * 1.30, (
        f"P&C gradient {grad:.4f} psi/ft outside expected range "
        f"[{expected*0.92:.4f}, {expected*1.30:.4f}]"
    )


def test_duns_ros_gradient_liquid_only():
    """Pure water (GOR=0, WC=1) → gradient ≈ water_sg × 0.433 psi/ft."""
    water_sg = 1.05
    grad = duns_ros_gradient(
        q_liq=300.0, wc=1.0, gor=0.0,
        gas_sg=0.65, oil_api=30.0, water_sg=water_sg,
        p=2000.0, t=150.0, pipe_id=2.441, angle=90.0,
    )
    expected = water_sg * 0.433
    assert expected * 0.92 <= grad <= expected * 1.30, (
        f"D&R gradient {grad:.4f} psi/ft outside expected range "
        f"[{expected*0.92:.4f}, {expected*1.30:.4f}]"
    )


# ---------------------------------------------------------------------------
# Parte B — outflow curve shape
# ---------------------------------------------------------------------------

def test_outflow_curve_increasing(fluid, well, surface):
    """Natural outflow curve Pwf must be non-decreasing with rate."""
    q_arr, pwf_arr = outflow_curve_natural(
        fluid, well, surface, method="hagedorn_brown", n_points=20
    )
    # Allow tiny floating-point dips, but the endpoint must exceed the start
    assert pwf_arr[-1] > pwf_arr[0], (
        f"Outflow curve not increasing: pwf[0]={pwf_arr[0]:.1f} "
        f"pwf[-1]={pwf_arr[-1]:.1f} psi"
    )
    # Majority of consecutive pairs must be non-decreasing
    diffs = np.diff(pwf_arr)
    n_decreasing = np.sum(diffs < -1.0)   # allow <1 psi noise
    assert n_decreasing <= 2, f"{n_decreasing} decreasing steps found in outflow curve"


# ---------------------------------------------------------------------------
# Parte B — operating points
# ---------------------------------------------------------------------------

def test_operating_point_with_pump_higher_q(reservoir, fluid, well, surface, pump):
    """With pump installed, operating rate must exceed natural flow rate."""
    stages = 150
    pump_depth = 6000.0

    result = find_operating_point(
        reservoir, fluid, well, surface,
        method="hagedorn_brown",
        pump=pump, stages=stages, pump_depth=pump_depth,
    )

    nat = result["natural_flow"]
    pmp = result["pump_flow"]

    # Both operating points must exist for this well (Pr=3000 psi, PI=2)
    assert nat is not None, "Well should have natural flow (Pr=3000, PI=2)"
    assert pmp is not None, "Pump-assisted flow should exist"
    assert pmp["q"] > nat["q"], (
        f"Pump rate {pmp['q']:.0f} not higher than natural {nat['q']:.0f} STB/d"
    )
    assert result["incremental_rate"] > 0


def test_compare_methods_returns_4(reservoir, fluid, well, surface, pump):
    """compare_methods must return entries for all four correlations."""
    results = compare_methods(
        reservoir, fluid, well, surface,
        pump=pump, stages=150, pump_depth=6000.0,
    )
    for m in ("hagedorn_brown", "beggs_brill", "duns_ros", "poettmann_carpenter"):
        assert m in results, f"Method '{m}' missing from compare_methods output"
        res = results[m]
        assert res["pump_flow"] is not None, (
            f"Method '{m}' returned no pump operating point"
        )
        q_pump = res["pump_flow"]["q"]
        assert q_pump > 0, f"Method '{m}': q_pump={q_pump:.1f} must be > 0"

    assert "_ipr" in results
    assert len(results["_ipr"]["q"]) > 0
