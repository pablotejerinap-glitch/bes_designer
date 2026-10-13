# -*- coding: utf-8 -*-
"""Arma los datos de un caso para la memoria de cálculo (capa API).

Corre el diseño por el mismo camino que la API (``/api/design`` o
``/api/gas/design``) y junta en un solo diccionario lo que la memoria
necesita: datos del pozo, aparejo elegido, traza de fórmulas y, según el caso,
la escalera de incrementos o la corrección por viscosidad.
"""
from __future__ import annotations

from typing import Any

_CAMPOS_BOMBA = (
    "pump_manufacturer", "pump_model", "pump_series", "pump_od", "num_stages", "n_housings",
    "pump_setting_depth", "intake_pressure", "total_head_required", "head_per_stage",
    "hp_per_stage", "pump_efficiency", "total_pump_hp", "motor_manufacturer", "motor_model",
    "motor_hp", "motor_voltage", "motor_amperage", "motor_od", "cable_type", "cable_awg",
    "cable_voltage_drop", "surface_voltage_required", "transformer_kva", "transformer_model",
    "transformer_connection", "transformer_secondary_range_v", "system_efficiency",
    "flow_rate_achieved", "operating_frequency", "seal_model", "controller_model", "sensor_model",
    "fluid_velocity_ft_s", "cooling_ok", "shaft_check", "gip_fraction", "gas_fraction_at_pump",
    "gas_handler_model", "housing_size_stages", "dummy_stages", "staging_ceiling",
    "max_housing_pressure_psi", "axial_thrust_lbs", "bearing_load_lbs", "seal_thrust_capacity_lbs",
)

_ENTRADAS = ("reservoir", "fluid", "well", "surface", "objectives")


def _pozo(req) -> dict:
    d = req.model_dump(mode="json")
    return {k: d[k] for k in _ENTRADAS}


def _fila(pozo: dict, des: dict, titulo: str, fuente: str) -> dict:
    pasos = {f.get("label"): {"expr": f.get("expression"), "res": f.get("result"),
                              "u": f.get("units"), "ref": f.get("reference"),
                              "ctx": f.get("context"), "in": f.get("inputs") or {}}
             for f in des.get("formulas", []) or []}
    vc = des.get("viscosity_correction")
    viscoso = bool(isinstance(vc, dict) and vc.get("capacity_factor") is not None
                   and vc.get("viscosity_chain"))
    return {"pozo": pozo, "titulo": titulo, "fuente": fuente,
            "pump": {x: des.get(x) for x in _CAMPOS_BOMBA},
            "pasos": pasos, "gas": False, "viscoso": viscoso,
            "visc": vc if viscoso else None}


def caso_convencional(req, catalog, rank: int = 0, titulo: str = "", fuente: str = "") -> dict:
    """Diseño sin gas libre en la bomba: ``/api/design``."""
    from bes.api.routers.design import post_design
    resp = post_design(req, catalog).model_dump(mode="json")
    recs = resp["recommendations"]
    if rank >= len(recs):
        raise ValueError(f"rank {rank} fuera de rango ({len(recs)} recomendaciones)")
    fila = _fila(_pozo(req), recs[rank]["design"], titulo, fuente)
    fila["crit"] = recs[rank].get("criteria")
    return fila


def caso_gas(req, catalog, titulo: str = "", fuente: str = "") -> dict:
    """Diseño completo por incrementos de presión: ``/api/gas/design``."""
    from bes.api.routers.gas import post_gas_complete_design
    resp: dict[str, Any] = post_gas_complete_design(req, catalog).model_dump(mode="json")
    fila = _fila(_pozo(req), resp["design"], titulo, fuente)
    fila.update(gas=True, viscoso=False, visc=None, summary=resp["summary"],
                feas=resp["feasibility"], inc=resp["increments"],
                tdh=[resp["tdh_increment_ft"], resp["tdh_conventional_ft"]],
                incremento=req.increment_psi)
    return fila
