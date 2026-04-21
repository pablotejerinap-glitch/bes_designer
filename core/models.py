"""
Data models for BES/ESP system design.
Based on: Kermit Brown, "The Technology of Artificial Lift Methods", Vol. 2b, Ch. 4.5.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class IPRMethod(Enum):
    """Inflow Performance Relationship method for reservoir modeling."""
    LINEAR = auto()       # Darcy / straight-line PI (above bubble point)
    VOGEL = auto()        # Vogel correlation (solution-gas drive)
    FETKOVICH = auto()    # Fetkovich empirical IPR
    COMBINED = auto()     # Linear above Pb, Vogel below Pb


class DriveMechanism(Enum):
    """Primary reservoir energy source."""
    SOLUTION_GAS = auto()
    WATER_DRIVE = auto()
    GAS_CAP = auto()
    COMBINATION = auto()


@dataclass
class Reservoir:
    """Static reservoir properties used for IPR and fluid-behavior calculations.

    Attributes:
        static_pressure: Current average reservoir pressure [psi].
        bubble_point: Bubble-point pressure of the reservoir fluid [psi].
        productivity_index: Well PI at test conditions [STB/d/psi].
        ipr_method: IPR correlation to apply.
        reservoir_temp: Bottom-hole static temperature [°F].
        drive_mechanism: Primary energy mechanism of the reservoir.
        datum_depth: Reference depth for pressure calculations [ft TVD].
    """
    static_pressure: float
    bubble_point: float
    productivity_index: float
    ipr_method: IPRMethod
    reservoir_temp: float
    drive_mechanism: DriveMechanism
    datum_depth: float

    def __post_init__(self) -> None:
        if self.static_pressure <= 0:
            raise ValueError(f"static_pressure must be > 0, got {self.static_pressure}")
        if self.bubble_point < 0:
            raise ValueError(f"bubble_point must be >= 0, got {self.bubble_point}")
        if self.bubble_point > self.static_pressure:
            raise ValueError(
                f"bubble_point ({self.bubble_point}) cannot exceed "
                f"static_pressure ({self.static_pressure})"
            )
        if self.productivity_index <= 0:
            raise ValueError(f"productivity_index must be > 0, got {self.productivity_index}")
        if self.reservoir_temp <= 0:
            raise ValueError(f"reservoir_temp must be > 0 °F, got {self.reservoir_temp}")
        if self.datum_depth <= 0:
            raise ValueError(f"datum_depth must be > 0, got {self.datum_depth}")


@dataclass
class Fluid:
    """Fluid PVT and composition properties.

    Attributes:
        oil_api: Stock-tank oil gravity [°API]. Valid range: 5–70.
        water_cut: Produced water fraction at surface conditions [0–1].
        gor: Producing gas-oil ratio at surface [scf/STB].
        gas_sg: Gas specific gravity (air = 1.0).
        water_sg: Brine specific gravity (pure water = 1.0).
        oil_viscosity_dead: Dead-oil viscosity at viscosity_temp_ref [cp].
        viscosity_temp_ref: Temperature at which dead-oil viscosity was measured [°F].
        bubble_point_pressure: Fluid bubble-point pressure for PVT calculations [psi].
        h2s_content: Hydrogen sulfide concentration [ppm]. Affects material selection.
        co2_content: Carbon dioxide concentration [ppm]. Affects corrosion design.
        sand_production: True if well produces sand (affects pump selection).
    """
    oil_api: float
    water_cut: float
    gor: float
    gas_sg: float
    water_sg: float
    oil_viscosity_dead: float
    viscosity_temp_ref: float
    bubble_point_pressure: float
    h2s_content: float
    co2_content: float
    sand_production: bool

    def __post_init__(self) -> None:
        if not (5.0 <= self.oil_api <= 70.0):
            raise ValueError(f"oil_api must be in [5, 70] °API, got {self.oil_api}")
        if not (0.0 <= self.water_cut <= 1.0):
            raise ValueError(f"water_cut must be in [0, 1], got {self.water_cut}")
        if self.gor < 0:
            raise ValueError(f"gor must be >= 0, got {self.gor}")
        if self.gas_sg <= 0:
            raise ValueError(f"gas_sg must be > 0, got {self.gas_sg}")
        if self.water_sg <= 0:
            raise ValueError(f"water_sg must be > 0, got {self.water_sg}")
        if self.oil_viscosity_dead <= 0:
            raise ValueError(f"oil_viscosity_dead must be > 0, got {self.oil_viscosity_dead}")
        if self.viscosity_temp_ref <= 0:
            raise ValueError(f"viscosity_temp_ref must be > 0 °F, got {self.viscosity_temp_ref}")
        if self.bubble_point_pressure < 0:
            raise ValueError(f"bubble_point_pressure must be >= 0, got {self.bubble_point_pressure}")
        if self.h2s_content < 0:
            raise ValueError(f"h2s_content must be >= 0, got {self.h2s_content}")
        if self.co2_content < 0:
            raise ValueError(f"co2_content must be >= 0, got {self.co2_content}")


@dataclass
class WellGeometry:
    """Wellbore geometry and completion dimensions.

    Attributes:
        total_depth: Measured depth to the bottom of the well [ft MD].
        casing_od: Casing outer diameter [in].
        casing_weight: Casing nominal weight [lb/ft] — determines wall thickness.
        casing_id: Casing inner diameter (drift) [in]. Constrains pump OD.
        tubing_od: Production tubing outer diameter [in].
        tubing_id: Production tubing inner diameter [in]. Governs friction losses.
        perforations_top: Measured depth to top of perforated interval [ft MD].
        perforations_bottom: Measured depth to bottom of perforated interval [ft MD].
        deviation_max: Maximum wellbore inclination along the production string [°].
            Values > 30° may require bent-housing or flex-shaft pump considerations.
        wellhead_temp: Ambient temperature at surface / wellhead [°F].
        bottom_hole_temp: Temperature at pump-setting depth [°F].
    """
    total_depth: float
    casing_od: float
    casing_weight: float
    casing_id: float
    tubing_od: float
    tubing_id: float
    perforations_top: float
    perforations_bottom: float
    deviation_max: float
    wellhead_temp: float
    bottom_hole_temp: float

    def __post_init__(self) -> None:
        if self.total_depth <= 0:
            raise ValueError(f"total_depth must be > 0, got {self.total_depth}")
        if self.casing_od <= 0:
            raise ValueError(f"casing_od must be > 0, got {self.casing_od}")
        if self.casing_weight <= 0:
            raise ValueError(f"casing_weight must be > 0, got {self.casing_weight}")
        if self.casing_id <= 0:
            raise ValueError(f"casing_id must be > 0, got {self.casing_id}")
        if self.casing_id >= self.casing_od:
            raise ValueError(
                f"casing_id ({self.casing_id}) must be < casing_od ({self.casing_od})"
            )
        if self.tubing_od <= 0:
            raise ValueError(f"tubing_od must be > 0, got {self.tubing_od}")
        if self.tubing_id <= 0:
            raise ValueError(f"tubing_id must be > 0, got {self.tubing_id}")
        if self.tubing_id >= self.tubing_od:
            raise ValueError(
                f"tubing_id ({self.tubing_id}) must be < tubing_od ({self.tubing_od})"
            )
        if self.tubing_od >= self.casing_id:
            raise ValueError(
                f"tubing_od ({self.tubing_od}) must be < casing_id ({self.casing_id})"
            )
        if self.perforations_top <= 0:
            raise ValueError(f"perforations_top must be > 0, got {self.perforations_top}")
        if self.perforations_bottom <= self.perforations_top:
            raise ValueError(
                f"perforations_bottom ({self.perforations_bottom}) must be "
                f"> perforations_top ({self.perforations_top})"
            )
        if self.perforations_bottom > self.total_depth:
            raise ValueError(
                f"perforations_bottom ({self.perforations_bottom}) cannot exceed "
                f"total_depth ({self.total_depth})"
            )
        if not (0.0 <= self.deviation_max <= 90.0):
            raise ValueError(f"deviation_max must be in [0, 90]°, got {self.deviation_max}")
        if self.wellhead_temp <= 0:
            raise ValueError(f"wellhead_temp must be > 0 °F, got {self.wellhead_temp}")
        if self.bottom_hole_temp <= self.wellhead_temp:
            raise ValueError(
                f"bottom_hole_temp ({self.bottom_hole_temp}) must be "
                f"> wellhead_temp ({self.wellhead_temp})"
            )


@dataclass
class SurfaceConditions:
    """Surface infrastructure and power-supply parameters.

    Attributes:
        wellhead_pressure_required: Minimum required tubing-head pressure [psi].
        flowline_length: Total flowline length from wellhead to separator [ft].
        flowline_id: Flowline inner diameter [in].
        flowline_elevation_change: Net elevation change along flowline (+ = uphill) [ft].
        separator_pressure: Operating pressure of the production separator [psi].
        power_supply_voltage: Available surface supply voltage [V].
        frequency: Power grid frequency [Hz]. Typically 60 (Americas) or 50 (rest).
    """
    wellhead_pressure_required: float
    flowline_length: float
    flowline_id: float
    flowline_elevation_change: float
    separator_pressure: float
    power_supply_voltage: float
    frequency: float

    def __post_init__(self) -> None:
        if self.wellhead_pressure_required < 0:
            raise ValueError(
                f"wellhead_pressure_required must be >= 0, got {self.wellhead_pressure_required}"
            )
        if self.flowline_length < 0:
            raise ValueError(f"flowline_length must be >= 0, got {self.flowline_length}")
        if self.flowline_id <= 0:
            raise ValueError(f"flowline_id must be > 0, got {self.flowline_id}")
        if self.separator_pressure < 0:
            raise ValueError(f"separator_pressure must be >= 0, got {self.separator_pressure}")
        if self.power_supply_voltage <= 0:
            raise ValueError(f"power_supply_voltage must be > 0, got {self.power_supply_voltage}")
        if self.frequency not in (50.0, 60.0):
            raise ValueError(f"frequency must be 50 or 60 Hz, got {self.frequency}")


@dataclass
class DesignObjectives:
    """User-specified production targets and design constraints.

    Attributes:
        target_flow_rate: Desired gross liquid production rate [STB/d].
        safety_margin_depth: Additional depth added below pump-setting for
            operational contingency (e.g., fluid level drop) [ft].
        allow_gas_venting: If True, a vent/gas-separator is assumed available.
        max_gip: Maximum allowable gas-in-pump fraction (free gas at pump intake)
            as a fraction [0–1]. Values > 0.10 risk pump cavitation.
        design_life_years: Expected run-life for equipment sizing and MTBF targets [years].
        use_vsd: If True, design includes a Variable Speed Drive (VSD/VFD).
    """
    target_flow_rate: float
    safety_margin_depth: float
    allow_gas_venting: bool
    max_gip: float
    design_life_years: float
    use_vsd: bool

    def __post_init__(self) -> None:
        if self.target_flow_rate <= 0:
            raise ValueError(f"target_flow_rate must be > 0, got {self.target_flow_rate}")
        if self.safety_margin_depth < 0:
            raise ValueError(f"safety_margin_depth must be >= 0, got {self.safety_margin_depth}")
        if not (0.0 <= self.max_gip <= 1.0):
            raise ValueError(f"max_gip must be in [0, 1], got {self.max_gip}")
        if self.design_life_years <= 0:
            raise ValueError(f"design_life_years must be > 0, got {self.design_life_years}")


@dataclass
class PumpPerformancePoint:
    """Single operating point on a pump performance curve.

    Attributes:
        flow_rate: Liquid throughput at this point [b/d].
        head_per_stage: Hydraulic head developed per stage at this flow [ft/stage].
        hp_per_stage: Shaft power required per stage [hp/stage].
        efficiency: Pump hydraulic efficiency at this point [0–1].
    """
    flow_rate: float
    head_per_stage: float
    hp_per_stage: float
    efficiency: float

    def __post_init__(self) -> None:
        if self.flow_rate < 0:
            raise ValueError(f"flow_rate must be >= 0, got {self.flow_rate}")
        if self.head_per_stage < 0:
            raise ValueError(f"head_per_stage must be >= 0, got {self.head_per_stage}")
        if self.hp_per_stage < 0:
            raise ValueError(f"hp_per_stage must be >= 0, got {self.hp_per_stage}")
        if not (0.0 <= self.efficiency <= 1.0):
            raise ValueError(f"efficiency must be in [0, 1], got {self.efficiency}")


@dataclass
class PumpCurve:
    """Manufacturer pump catalog entry with full performance curve.

    Attributes:
        manufacturer: Equipment manufacturer name (e.g., "Reda", "Centrilift").
        series: Pump series / product line (e.g., "DN1750", "GC6100").
        model: Specific model designation.
        od: Pump outer diameter [in]. Must fit inside casing_id.
        min_flow: Minimum recommended operating flow rate [b/d].
        max_flow: Maximum recommended operating flow rate [b/d].
        bep_flow: Best efficiency point flow rate [b/d].
        points: List of performance points spanning the operating range.
        max_stages: Maximum number of stages available in this housing.
        housing_options: Available housing sizes (number of stages) from catalog.
    """
    manufacturer: str
    series: str
    model: str
    od: float
    min_flow: float
    max_flow: float
    bep_flow: float
    points: list[PumpPerformancePoint]
    max_stages: int
    housing_options: list[int]

    def __post_init__(self) -> None:
        if self.od <= 0:
            raise ValueError(f"od must be > 0, got {self.od}")
        if self.min_flow < 0:
            raise ValueError(f"min_flow must be >= 0, got {self.min_flow}")
        if self.max_flow <= self.min_flow:
            raise ValueError(
                f"max_flow ({self.max_flow}) must be > min_flow ({self.min_flow})"
            )
        if not (self.min_flow <= self.bep_flow <= self.max_flow):
            raise ValueError(
                f"bep_flow ({self.bep_flow}) must be in "
                f"[min_flow={self.min_flow}, max_flow={self.max_flow}]"
            )
        if not self.points:
            raise ValueError("points list cannot be empty")
        if self.max_stages <= 0:
            raise ValueError(f"max_stages must be > 0, got {self.max_stages}")
        if not self.housing_options:
            raise ValueError("housing_options list cannot be empty")
        if any(s <= 0 for s in self.housing_options):
            raise ValueError("all housing_options values must be > 0")
        if not self.manufacturer.strip():
            raise ValueError("manufacturer cannot be empty")
        if not self.model.strip():
            raise ValueError("model cannot be empty")


@dataclass
class DesignResult:
    """Complete output of a BES/ESP design calculation.

    Attributes:
        pump_manufacturer: Selected pump manufacturer.
        pump_series: Selected pump series.
        pump_model: Selected pump model designation.
        pump_od: Pump outer diameter [in].
        num_stages: Number of pump stages required.
        pump_setting_depth: Recommended pump intake depth [ft MD].
        intake_pressure: Pressure at pump intake [psi].
        total_head_required: Total dynamic head the pump must develop [ft].
        head_per_stage: Head per stage at operating point [ft/stage].
        hp_per_stage: Power per stage at operating point [hp/stage].
        pump_efficiency: Pump hydraulic efficiency at operating point [0–1].
        total_pump_hp: Total pump shaft power requirement [hp].
        motor_manufacturer: Selected motor manufacturer.
        motor_model: Motor model designation.
        motor_hp: Motor nameplate power rating [hp].
        motor_voltage: Motor nameplate voltage [V].
        motor_amperage: Motor nameplate current at rated load [A].
        motor_od: Motor outer diameter [in].
        motor_length: Motor length (one or stacked) [ft].
        cable_type: Cable jacket type / insulation class (e.g., "EPDM", "Polypro").
        cable_awg: Cable conductor size [AWG].
        cable_voltage_drop: Estimated voltage drop along cable [V].
        surface_voltage_required: Required surface voltage to deliver motor voltage [V].
        transformer_kva: Recommended transformer rating [kVA].
        system_efficiency: Overall system efficiency (pump × motor × cable) [0–1].
        flow_rate_achieved: Calculated gross liquid rate at operating point [STB/d].
        operating_frequency: Pump operating frequency (relevant for VSD designs) [Hz].
        gip_fraction: Estimated free-gas fraction at pump intake [0–1].
        warnings: List of design warnings or flags for engineer review.
        alternatives: List of alternative equipment combinations considered.
    """
    pump_manufacturer: str
    pump_series: str
    pump_model: str
    pump_od: float
    num_stages: int
    pump_setting_depth: float
    intake_pressure: float
    total_head_required: float
    head_per_stage: float
    hp_per_stage: float
    pump_efficiency: float
    total_pump_hp: float
    motor_manufacturer: str
    motor_model: str
    motor_hp: float
    motor_voltage: float
    motor_amperage: float
    motor_od: float
    motor_length: float
    cable_type: str
    cable_awg: int
    cable_voltage_drop: float
    surface_voltage_required: float
    transformer_kva: float
    system_efficiency: float
    flow_rate_achieved: float
    operating_frequency: float
    gip_fraction: float
    warnings: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.num_stages <= 0:
            raise ValueError(f"num_stages must be > 0, got {self.num_stages}")
        if self.pump_setting_depth <= 0:
            raise ValueError(f"pump_setting_depth must be > 0, got {self.pump_setting_depth}")
        if self.intake_pressure <= 0:
            raise ValueError(f"intake_pressure must be > 0, got {self.intake_pressure}")
        if self.total_head_required <= 0:
            raise ValueError(f"total_head_required must be > 0, got {self.total_head_required}")
        if not (0.0 <= self.pump_efficiency <= 1.0):
            raise ValueError(f"pump_efficiency must be in [0, 1], got {self.pump_efficiency}")
        if not (0.0 <= self.system_efficiency <= 1.0):
            raise ValueError(f"system_efficiency must be in [0, 1], got {self.system_efficiency}")
        if self.flow_rate_achieved <= 0:
            raise ValueError(f"flow_rate_achieved must be > 0, got {self.flow_rate_achieved}")
        if not (0.0 <= self.gip_fraction <= 1.0):
            raise ValueError(f"gip_fraction must be in [0, 1], got {self.gip_fraction}")
        if self.motor_hp <= 0:
            raise ValueError(f"motor_hp must be > 0, got {self.motor_hp}")
        if self.motor_voltage <= 0:
            raise ValueError(f"motor_voltage must be > 0, got {self.motor_voltage}")
        if self.transformer_kva <= 0:
            raise ValueError(f"transformer_kva must be > 0, got {self.transformer_kva}")
        if self.cable_awg <= 0:
            raise ValueError(f"cable_awg must be > 0, got {self.cable_awg}")
        if not self.pump_manufacturer.strip():
            raise ValueError("pump_manufacturer cannot be empty")
        if not self.motor_manufacturer.strip():
            raise ValueError("motor_manufacturer cannot be empty")
