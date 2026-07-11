"""POST /api/sensitivity — parameter sweep metrics + Plotly figure JSON."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from api.deps import get_catalog
from api.mappers import (
    to_fluid, to_objectives, to_reservoir, to_surface, to_well,
)
from api.schemas.analysis import SensitivityRequest, SensitivityResponse
from services.sensitivity_service import run_sensitivity
from ui.plots import plot_sensitivity_analysis

router = APIRouter(prefix="/api", tags=["sensitivity"])


@router.post("/sensitivity", response_model=SensitivityResponse)
def post_sensitivity(req: SensitivityRequest, catalog=Depends(get_catalog)) -> SensitivityResponse:
    reservoir = to_reservoir(req.reservoir)
    fluid = to_fluid(req.fluid)
    well = to_well(req.well)
    surface = to_surface(req.surface)
    objectives = to_objectives(req.objectives)

    sens = run_sensitivity(
        reservoir, fluid, well, surface, objectives, catalog, req.param.value,
        pct_range_pct=req.pct_range_pct, n_points=req.n_points,
    )
    if not sens["param_values"]:
        raise ValueError("No se encontraron diseños válidos en el rango seleccionado.")

    fig = plot_sensitivity_analysis(
        param_values=sens["param_values"],
        metrics_dict=sens["metrics"],
        parameter_label=sens["param_label"],
    )

    return SensitivityResponse(
        param=sens["param"],
        param_label=sens["param_label"],
        param_values=sens["param_values"],
        metrics=sens["metrics"],
        figure=json.loads(fig.to_json()),
    )
