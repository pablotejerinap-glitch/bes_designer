"""Traductores entre los esquemas Pydantic de la API y las dataclasses del dominio.

::

    Pedido:    esquema -> dataclass   (con lookup explícito string -> enum)
    Respuesta: DesignResult -> DesignResultSchema

**El objetivo es no tocar las dataclasses del dominio** ni su validación en
``__post_init__``. Convertirlas a Pydantic rompería los tests que esperan
``ValueError`` con mensajes específicos, y el ``warnings.warn`` «suave» de
``Reservoir``.

Ver ``.claude/rules/api-contract.md``.
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
