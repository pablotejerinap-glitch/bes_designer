"""Response schemas — mirror ``DesignResult`` and the ``generate_recommendations``
return shape. ``DesignResult`` has no enums, so mapping is
``DesignResultSchema(**dataclasses.asdict(dr))``.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class DesignResultSchema(BaseModel):
    # Pump
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
    # Motor
    motor_manufacturer: str
    motor_model: str
    motor_hp: float
    motor_voltage: float
    motor_amperage: float
    motor_od: float
    motor_length: float
    # Cable / power
    cable_type: str
    cable_awg: int
    cable_voltage_drop: float
    surface_voltage_required: float
    transformer_kva: float
    # System
    system_efficiency: float
    flow_rate_achieved: float
    operating_frequency: float
    gip_fraction: float
    warnings: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    # Seal / protector (optional)
    seal_manufacturer: str = ""
    seal_model: str = ""
    seal_type: str = ""
    seal_thrust_capacity_lbs: float = 0.0
    axial_thrust_lbs: float = 0.0
    # Gas handler / separator (optional)
    gas_handler_manufacturer: str = ""
    gas_handler_model: str = ""
    gas_handler_type: str = ""
    gas_handler_efficiency: float = 0.0
    # Downhole sensor (optional)
    sensor_manufacturer: str = ""
    sensor_model: str = ""


class RecommendationSchema(BaseModel):
    rank: int
    score: float
    metrics: dict[str, float]
    design: DesignResultSchema
    rationale: str
    warnings: list[str] = Field(default_factory=list)


class DesignResponse(BaseModel):
    recommendations: list[RecommendationSchema]
    design_basis: dict[str, float]
    weights: dict[str, float]
    n_candidates_evaluated: int
    warnings: list[str] = Field(default_factory=list, description="Warnings del run (p.ej. reservorio depletado)")
