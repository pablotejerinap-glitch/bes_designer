"""Mappers between API Pydantic schemas and domain dataclasses.

Request:  schema -> dataclass  (with explicit string -> enum lookup).
Response: DesignResult -> DesignResultSchema  (trivial; no enums in DesignResult).

Keeping the domain dataclasses untouched (and their ``__post_init__`` validation)
is the whole point — see ``.claude/rules/api-contract.md``.
"""
from __future__ import annotations

from dataclasses import asdict

from bes.api.schemas.inputs import (
    DesignRequest, FluidSchema, ObjectivesSchema, ReservoirSchema,
    SurfaceSchema, WellSchema,
)
from bes.api.schemas.outputs import DesignResultSchema
from bes.core.models import (
    DesignObjectives, DesignResult, DriveMechanism, Fluid, IPRMethod,
    Reservoir, SurfaceConditions, WellGeometry,
)

# String (API) -> domain enum. Keyed by the enum's lowercased name, which is
# exactly the value of the API string enums (e.g. "vogel" -> IPRMethod.VOGEL).
_IPR_BY_NAME = {m.name.lower(): m for m in IPRMethod}
_DRIVE_BY_NAME = {m.name.lower(): m for m in DriveMechanism}


def to_reservoir(s: ReservoirSchema) -> Reservoir:
    """ReservoirSchema -> Reservoir.

    ``productivity_index`` (y el C de Fetkovich) no viajan por la API: los
    deriva ``Reservoir.__post_init__`` del ensayo, con el método IPR elegido.
    """
    return Reservoir(
        static_pressure=s.static_pressure,
        bubble_point=s.bubble_point,
        ipr_method=_IPR_BY_NAME[s.ipr_method.value],
        reservoir_temp=s.reservoir_temp,
        drive_mechanism=_DRIVE_BY_NAME[s.drive_mechanism.value],
        test_pwf=s.test_pwf,
        test_rate=s.test_rate,
        fetkovich_n=s.fetkovich_n,
    )


def to_fluid(s: FluidSchema) -> Fluid:
    return Fluid(**s.model_dump())


def to_well(s: WellSchema) -> WellGeometry:
    return WellGeometry(**s.model_dump())


def to_surface(s: SurfaceSchema) -> SurfaceConditions:
    return SurfaceConditions(**s.model_dump())


def to_objectives(s: ObjectivesSchema) -> DesignObjectives:
    return DesignObjectives(**s.model_dump())


def to_domain_inputs(req: DesignRequest):
    """Map a full DesignRequest to the five domain dataclasses (tuple)."""
    return (
        to_reservoir(req.reservoir),
        to_fluid(req.fluid),
        to_well(req.well),
        to_surface(req.surface),
        to_objectives(req.objectives),
    )


def from_design_result(dr: DesignResult) -> DesignResultSchema:
    """DesignResult -> DesignResultSchema. Field names match; no enums involved."""
    return DesignResultSchema(**asdict(dr))
