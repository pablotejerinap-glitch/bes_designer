"""POST /api/nodal — nodal analysis metrics/comparison + Plotly figure JSON."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from api.deps import get_catalog
from api.mappers import to_fluid, to_reservoir, to_surface, to_well
from api.schemas.analysis import NodalComparisonRow, NodalRequest, NodalResponse
from services.nodal_service import run_nodal_analysis
from ui.plots import plot_nodal_analysis, plot_nodal_comparison

router = APIRouter(prefix="/api", tags=["nodal"])


def _resolve_pump(catalog, model: str | None):
    if not model:
        return None
    pump = next((p for p in catalog.get_all_pumps() if p.model == model), None)
    if pump is None:
        raise ValueError(f"pump_model '{model}' no existe en el catálogo")
    return pump


@router.post("/nodal", response_model=NodalResponse)
def post_nodal(req: NodalRequest, catalog=Depends(get_catalog)) -> NodalResponse:
    reservoir = to_reservoir(req.reservoir)
    fluid = to_fluid(req.fluid)
    well = to_well(req.well)
    surface = to_surface(req.surface)
    pump = _resolve_pump(catalog, req.pump_model)

    result = run_nodal_analysis(
        reservoir, fluid, well, surface,
        method=req.method.value, pr_decline_pct=req.pr_decline_pct,
        compare_all=req.compare_all, pump=pump, stages=req.stages, pump_depth=req.pump_depth,
    )
    reservoir_eff = result["reservoir_eff"]

    if req.compare_all:
        fig = plot_nodal_comparison(
            reservoir=reservoir_eff, fluid=fluid, well=well, surface=surface,
            pump=pump, stages=req.stages, pump_depth=req.pump_depth,
        )
        metrics = None
        comparison = [NodalComparisonRow(**row) for row in result["comparison"]]
    else:
        fig = plot_nodal_analysis(
            reservoir=reservoir_eff, fluid=fluid, well=well, surface=surface,
            pump=pump, stages=req.stages, pump_depth=req.pump_depth, method=req.method.value,
        )
        metrics = result["metrics"]
        comparison = None

    return NodalResponse(
        mode=result["mode"],
        method=result["method"],
        pr_decline_pct=result["pr_decline_pct"],
        static_pressure_eff=reservoir_eff.static_pressure,
        has_pump=result["has_pump"],
        metrics=metrics,
        comparison=comparison,
        figure=json.loads(fig.to_json()),
    )
