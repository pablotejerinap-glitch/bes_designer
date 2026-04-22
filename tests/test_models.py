"""Unit tests for core/models.py — valid construction and validation errors."""

import pytest
from core.models import (
    IPRMethod,
    DriveMechanism,
    Reservoir,
    Fluid,
    WellGeometry,
    SurfaceConditions,
    DesignObjectives,
    PumpPerformancePoint,
    PumpCurve,
    DesignResult,
)


# ---------------------------------------------------------------------------
# Helpers — canonical valid instances
# ---------------------------------------------------------------------------

def valid_reservoir() -> Reservoir:
    return Reservoir(
        static_pressure=3500.0,
        bubble_point=2200.0,
        productivity_index=1.5,
        ipr_method=IPRMethod.VOGEL,
        reservoir_temp=180.0,
        drive_mechanism=DriveMechanism.SOLUTION_GAS,
        datum_depth=8500.0,
    )


def valid_fluid() -> Fluid:
    return Fluid(
        oil_api=32.0,
        water_cut=0.40,
        gor=350.0,
        gas_sg=0.65,
        water_sg=1.08,
        oil_viscosity_dead=12.0,
        viscosity_temp_ref=100.0,
        bubble_point_pressure=2200.0,
        h2s_content=50.0,
        co2_content=200.0,
        sand_production=False,
    )


def valid_well_geometry() -> WellGeometry:
    return WellGeometry(
        total_depth=9000.0,
        casing_od=7.0,
        casing_weight=23.0,
        casing_id=6.366,
        tubing_od=2.875,
        tubing_id=2.441,
        perforations_top=8600.0,
        perforations_bottom=8800.0,
        deviation_max=15.0,
        wellhead_temp=75.0,
        bottom_hole_temp=180.0,
    )


def valid_surface_conditions() -> SurfaceConditions:
    return SurfaceConditions(
        wellhead_pressure_required=100.0,
        flowline_length=500.0,
        flowline_id=3.0,
        flowline_elevation_change=20.0,
        separator_pressure=80.0,
        power_supply_voltage=480.0,
        frequency=60.0,
    )


def valid_design_objectives() -> DesignObjectives:
    return DesignObjectives(
        target_flow_rate=1500.0,
        safety_margin_depth=200.0,
        allow_gas_venting=True,
        max_gip=0.10,
        design_life_years=3.0,
        use_vsd=False,
    )


def valid_pump_point() -> PumpPerformancePoint:
    return PumpPerformancePoint(
        flow_rate=1500.0,
        head_per_stage=28.0,
        hp_per_stage=1.2,
        efficiency=0.65,
    )


def valid_pump_curve() -> PumpCurve:
    points = [
        PumpPerformancePoint(800.0, 35.0, 0.9, 0.55),
        PumpPerformancePoint(1200.0, 32.0, 1.1, 0.65),
        PumpPerformancePoint(1750.0, 26.0, 1.3, 0.60),
    ]
    return PumpCurve(
        manufacturer="Reda",
        series="DN1750",
        model="D1750N",
        od=4.0,
        min_flow=600.0,
        max_flow=2200.0,
        bep_flow=1750.0,
        points=points,
        max_stages=350,
        housing_options=[100, 150, 200, 250, 300, 350],
    )


def valid_design_result() -> DesignResult:
    return DesignResult(
        pump_manufacturer="Reda",
        pump_series="DN1750",
        pump_model="D1750N",
        pump_od=4.0,
        num_stages=120,
        pump_setting_depth=8400.0,
        intake_pressure=1800.0,
        total_head_required=3360.0,
        head_per_stage=28.0,
        hp_per_stage=1.2,
        pump_efficiency=0.65,
        total_pump_hp=144.0,
        motor_manufacturer="Reda",
        motor_model="562 Series 150HP",
        motor_hp=150.0,
        motor_voltage=2280.0,
        motor_amperage=42.0,
        motor_od=5.62,
        motor_length=25.0,
        cable_type="EPDM",
        cable_awg=4,
        cable_voltage_drop=180.0,
        surface_voltage_required=2460.0,
        transformer_kva=400.0,
        system_efficiency=0.52,
        flow_rate_achieved=1510.0,
        operating_frequency=60.0,
        gip_fraction=0.05,
        warnings=["GOR approaching cavitation threshold"],
        alternatives=["Centrilift GC6100 / 130 stages"],
    )


# ---------------------------------------------------------------------------
# Reservoir
# ---------------------------------------------------------------------------

class TestReservoir:
    def test_valid(self):
        r = valid_reservoir()
        assert r.static_pressure == 3500.0
        assert r.ipr_method is IPRMethod.VOGEL

    def test_negative_static_pressure(self):
        with pytest.raises(ValueError, match="static_pressure"):
            Reservoir(
                static_pressure=-100.0, bubble_point=2200.0, productivity_index=1.5,
                ipr_method=IPRMethod.LINEAR, reservoir_temp=180.0,
                drive_mechanism=DriveMechanism.WATER_DRIVE, datum_depth=8500.0,
            )

    def test_bubble_point_exceeds_static_pressure_warns(self):
        with pytest.warns(UserWarning, match="bubble_point"):
            Reservoir(
                static_pressure=2000.0, bubble_point=2500.0, productivity_index=1.5,
                ipr_method=IPRMethod.VOGEL, reservoir_temp=180.0,
                drive_mechanism=DriveMechanism.SOLUTION_GAS, datum_depth=8500.0,
            )

    def test_zero_productivity_index(self):
        with pytest.raises(ValueError, match="productivity_index"):
            Reservoir(
                static_pressure=3500.0, bubble_point=2200.0, productivity_index=0.0,
                ipr_method=IPRMethod.LINEAR, reservoir_temp=180.0,
                drive_mechanism=DriveMechanism.GAS_CAP, datum_depth=8500.0,
            )


# ---------------------------------------------------------------------------
# Fluid
# ---------------------------------------------------------------------------

class TestFluid:
    def test_valid(self):
        f = valid_fluid()
        assert f.oil_api == 32.0
        assert f.sand_production is False

    def test_api_too_low(self):
        with pytest.raises(ValueError, match="oil_api"):
            Fluid(
                oil_api=2.0, water_cut=0.4, gor=350.0, gas_sg=0.65, water_sg=1.08,
                oil_viscosity_dead=12.0, viscosity_temp_ref=100.0,
                bubble_point_pressure=2200.0, h2s_content=50.0,
                co2_content=200.0, sand_production=False,
            )

    def test_api_too_high(self):
        with pytest.raises(ValueError, match="oil_api"):
            Fluid(
                oil_api=75.0, water_cut=0.4, gor=350.0, gas_sg=0.65, water_sg=1.08,
                oil_viscosity_dead=12.0, viscosity_temp_ref=100.0,
                bubble_point_pressure=2200.0, h2s_content=50.0,
                co2_content=200.0, sand_production=False,
            )

    def test_water_cut_out_of_range(self):
        with pytest.raises(ValueError, match="water_cut"):
            Fluid(
                oil_api=32.0, water_cut=1.5, gor=350.0, gas_sg=0.65, water_sg=1.08,
                oil_viscosity_dead=12.0, viscosity_temp_ref=100.0,
                bubble_point_pressure=2200.0, h2s_content=50.0,
                co2_content=200.0, sand_production=False,
            )

    def test_negative_gor(self):
        with pytest.raises(ValueError, match="gor"):
            Fluid(
                oil_api=32.0, water_cut=0.4, gor=-10.0, gas_sg=0.65, water_sg=1.08,
                oil_viscosity_dead=12.0, viscosity_temp_ref=100.0,
                bubble_point_pressure=2200.0, h2s_content=50.0,
                co2_content=200.0, sand_production=False,
            )


# ---------------------------------------------------------------------------
# WellGeometry
# ---------------------------------------------------------------------------

class TestWellGeometry:
    def test_valid(self):
        w = valid_well_geometry()
        assert w.total_depth == 9000.0

    def test_perforations_inverted(self):
        with pytest.raises(ValueError, match="perforations_bottom"):
            WellGeometry(
                total_depth=9000.0, casing_od=7.0, casing_weight=23.0,
                casing_id=6.366, tubing_od=2.875, tubing_id=2.441,
                perforations_top=8800.0, perforations_bottom=8600.0,
                deviation_max=15.0, wellhead_temp=75.0, bottom_hole_temp=180.0,
            )

    def test_perforations_below_total_depth(self):
        with pytest.raises(ValueError, match="perforations_bottom"):
            WellGeometry(
                total_depth=9000.0, casing_od=7.0, casing_weight=23.0,
                casing_id=6.366, tubing_od=2.875, tubing_id=2.441,
                perforations_top=8600.0, perforations_bottom=9500.0,
                deviation_max=15.0, wellhead_temp=75.0, bottom_hole_temp=180.0,
            )

    def test_casing_id_larger_than_od(self):
        with pytest.raises(ValueError, match="casing_id"):
            WellGeometry(
                total_depth=9000.0, casing_od=7.0, casing_weight=23.0,
                casing_id=7.5, tubing_od=2.875, tubing_id=2.441,
                perforations_top=8600.0, perforations_bottom=8800.0,
                deviation_max=15.0, wellhead_temp=75.0, bottom_hole_temp=180.0,
            )

    def test_tubing_od_larger_than_casing_id(self):
        with pytest.raises(ValueError, match="tubing_od"):
            WellGeometry(
                total_depth=9000.0, casing_od=7.0, casing_weight=23.0,
                casing_id=6.366, tubing_od=6.5, tubing_id=5.9,
                perforations_top=8600.0, perforations_bottom=8800.0,
                deviation_max=15.0, wellhead_temp=75.0, bottom_hole_temp=180.0,
            )

    def test_invalid_deviation(self):
        with pytest.raises(ValueError, match="deviation_max"):
            WellGeometry(
                total_depth=9000.0, casing_od=7.0, casing_weight=23.0,
                casing_id=6.366, tubing_od=2.875, tubing_id=2.441,
                perforations_top=8600.0, perforations_bottom=8800.0,
                deviation_max=95.0, wellhead_temp=75.0, bottom_hole_temp=180.0,
            )

    def test_bhtemp_less_than_wellhead(self):
        with pytest.raises(ValueError, match="bottom_hole_temp"):
            WellGeometry(
                total_depth=9000.0, casing_od=7.0, casing_weight=23.0,
                casing_id=6.366, tubing_od=2.875, tubing_id=2.441,
                perforations_top=8600.0, perforations_bottom=8800.0,
                deviation_max=15.0, wellhead_temp=180.0, bottom_hole_temp=75.0,
            )


# ---------------------------------------------------------------------------
# SurfaceConditions
# ---------------------------------------------------------------------------

class TestSurfaceConditions:
    def test_valid(self):
        s = valid_surface_conditions()
        assert s.frequency == 60.0

    def test_invalid_frequency(self):
        with pytest.raises(ValueError, match="frequency"):
            SurfaceConditions(
                wellhead_pressure_required=100.0, flowline_length=500.0,
                flowline_id=3.0, flowline_elevation_change=20.0,
                separator_pressure=80.0, power_supply_voltage=480.0,
                frequency=45.0,
            )

    def test_negative_separator_pressure(self):
        with pytest.raises(ValueError, match="separator_pressure"):
            SurfaceConditions(
                wellhead_pressure_required=100.0, flowline_length=500.0,
                flowline_id=3.0, flowline_elevation_change=20.0,
                separator_pressure=-10.0, power_supply_voltage=480.0,
                frequency=60.0,
            )


# ---------------------------------------------------------------------------
# DesignObjectives
# ---------------------------------------------------------------------------

class TestDesignObjectives:
    def test_valid(self):
        d = valid_design_objectives()
        assert d.use_vsd is False

    def test_negative_flow_rate(self):
        with pytest.raises(ValueError, match="target_flow_rate"):
            DesignObjectives(
                target_flow_rate=-100.0, safety_margin_depth=200.0,
                allow_gas_venting=True, max_gip=0.10,
                design_life_years=3.0, use_vsd=False,
            )

    def test_max_gip_out_of_range(self):
        with pytest.raises(ValueError, match="max_gip"):
            DesignObjectives(
                target_flow_rate=1500.0, safety_margin_depth=200.0,
                allow_gas_venting=True, max_gip=1.5,
                design_life_years=3.0, use_vsd=False,
            )


# ---------------------------------------------------------------------------
# PumpPerformancePoint
# ---------------------------------------------------------------------------

class TestPumpPerformancePoint:
    def test_valid(self):
        p = valid_pump_point()
        assert p.efficiency == 0.65

    def test_efficiency_out_of_range(self):
        with pytest.raises(ValueError, match="efficiency"):
            PumpPerformancePoint(flow_rate=1500.0, head_per_stage=28.0,
                                 hp_per_stage=1.2, efficiency=1.5)

    def test_negative_head(self):
        with pytest.raises(ValueError, match="head_per_stage"):
            PumpPerformancePoint(flow_rate=1500.0, head_per_stage=-5.0,
                                 hp_per_stage=1.2, efficiency=0.65)


# ---------------------------------------------------------------------------
# PumpCurve
# ---------------------------------------------------------------------------

class TestPumpCurve:
    def test_valid(self):
        pc = valid_pump_curve()
        assert pc.manufacturer == "Reda"
        assert len(pc.points) == 3

    def test_bep_outside_range(self):
        points = [PumpPerformancePoint(1500.0, 28.0, 1.2, 0.65)]
        with pytest.raises(ValueError, match="bep_flow"):
            PumpCurve(
                manufacturer="Reda", series="DN1750", model="D1750N",
                od=4.0, min_flow=600.0, max_flow=2200.0, bep_flow=300.0,
                points=points, max_stages=350,
                housing_options=[100, 200, 300],
            )

    def test_max_flow_less_than_min_flow(self):
        points = [PumpPerformancePoint(1500.0, 28.0, 1.2, 0.65)]
        with pytest.raises(ValueError, match="max_flow"):
            PumpCurve(
                manufacturer="Reda", series="DN1750", model="D1750N",
                od=4.0, min_flow=2200.0, max_flow=600.0, bep_flow=1500.0,
                points=points, max_stages=350,
                housing_options=[100, 200],
            )

    def test_empty_points(self):
        with pytest.raises(ValueError, match="points"):
            PumpCurve(
                manufacturer="Reda", series="DN1750", model="D1750N",
                od=4.0, min_flow=600.0, max_flow=2200.0, bep_flow=1500.0,
                points=[], max_stages=350, housing_options=[100],
            )

    def test_empty_manufacturer(self):
        points = [PumpPerformancePoint(1500.0, 28.0, 1.2, 0.65)]
        with pytest.raises(ValueError, match="manufacturer"):
            PumpCurve(
                manufacturer="   ", series="DN1750", model="D1750N",
                od=4.0, min_flow=600.0, max_flow=2200.0, bep_flow=1500.0,
                points=points, max_stages=350, housing_options=[100],
            )


# ---------------------------------------------------------------------------
# DesignResult
# ---------------------------------------------------------------------------

class TestDesignResult:
    def test_valid(self):
        dr = valid_design_result()
        assert dr.num_stages == 120
        assert dr.warnings == ["GOR approaching cavitation threshold"]

    def test_zero_stages(self):
        with pytest.raises(ValueError, match="num_stages"):
            dr = valid_design_result()
            object.__setattr__(dr, "num_stages", 0)
            dr.__post_init__()

    def test_system_efficiency_out_of_range(self):
        with pytest.raises(ValueError, match="system_efficiency"):
            DesignResult(
                pump_manufacturer="Reda", pump_series="DN1750", pump_model="D1750N",
                pump_od=4.0, num_stages=120, pump_setting_depth=8400.0,
                intake_pressure=1800.0, total_head_required=3360.0,
                head_per_stage=28.0, hp_per_stage=1.2, pump_efficiency=0.65,
                total_pump_hp=144.0, motor_manufacturer="Reda",
                motor_model="562 Series 150HP", motor_hp=150.0,
                motor_voltage=2280.0, motor_amperage=42.0, motor_od=5.62,
                motor_length=25.0, cable_type="EPDM", cable_awg=4,
                cable_voltage_drop=180.0, surface_voltage_required=2460.0,
                transformer_kva=400.0, system_efficiency=1.5,
                flow_rate_achieved=1510.0, operating_frequency=60.0,
                gip_fraction=0.05,
            )

    def test_gip_fraction_out_of_range(self):
        with pytest.raises(ValueError, match="gip_fraction"):
            DesignResult(
                pump_manufacturer="Reda", pump_series="DN1750", pump_model="D1750N",
                pump_od=4.0, num_stages=120, pump_setting_depth=8400.0,
                intake_pressure=1800.0, total_head_required=3360.0,
                head_per_stage=28.0, hp_per_stage=1.2, pump_efficiency=0.65,
                total_pump_hp=144.0, motor_manufacturer="Reda",
                motor_model="562 Series 150HP", motor_hp=150.0,
                motor_voltage=2280.0, motor_amperage=42.0, motor_od=5.62,
                motor_length=25.0, cable_type="EPDM", cable_awg=4,
                cable_voltage_drop=180.0, surface_voltage_required=2460.0,
                transformer_kva=400.0, system_efficiency=0.52,
                flow_rate_achieved=1510.0, operating_frequency=60.0,
                gip_fraction=-0.1,
            )
