"""POST /api/nodal — métricas del análisis nodal + figura Plotly en JSON."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from bes.api.deps import get_catalog, resolve_pump
from bes.api.mappers import to_fluid, to_reservoir, to_surface, to_well
from bes.api.schemas.analysis import NodalRequest, NodalResponse
from bes.services.nodal_service import run_nodal_analysis
from bes.plotting import plot_nodal_analysis

router = APIRouter(prefix="/api", tags=["nodal"])


@router.post("/nodal", response_model=NodalResponse)
def post_nodal(req: NodalRequest, catalog=Depends(get_catalog)) -> NodalResponse:
    reservoir = to_reservoir(req.reservoir)
    fluid = to_fluid(req.fluid)
    well = to_well(req.well)
    surface = to_surface(req.surface)
    pump = resolve_pump(catalog, req.pump_model)

    result = run_nodal_analysis(
        reservoir, fluid, well, surface,
        pr_decline_pct=req.pr_decline_pct,
        pump=pump, stages=req.stages, pump_depth=req.pump_depth,
    )
    reservoir_eff = result["reservoir_eff"]

    fig = plot_nodal_analysis(
        reservoir=reservoir_eff, fluid=fluid, well=well, surface=surface,
        pump=pump, stages=req.stages, pump_depth=req.pump_depth,
    )

    return NodalResponse(
        method=result["method"],
        pr_decline_pct=result["pr_decline_pct"],
        static_pressure_eff=reservoir_eff.static_pressure,
        has_pump=result["has_pump"],
        metrics=result["metrics"],
        figure=json.loads(fig.to_json()),
    )
