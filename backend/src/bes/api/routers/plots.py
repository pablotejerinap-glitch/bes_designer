"""GET /api/plots/* — Plotly figure JSON for charts that need no extra compute.

Los gráficos que acompañan un cálculo (nodal, sensibilidad) viajan dentro de la
respuesta de ese endpoint. Este router cubre los que el front pide por separado,
como la curva de una bomba del catálogo.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query

from bes.api.deps import get_catalog, resolve_pump
from bes.api.schemas.analysis import FigureResponse
from bes.plotting import plot_pump_curve

router = APIRouter(prefix="/api/plots", tags=["plots"])


@router.get("/pump-curve", response_model=FigureResponse)
def get_pump_curve(
    pump_model: str = Query(..., description="Modelo de bomba del catálogo"),
    operating_flow: float = Query(..., gt=0, description="Caudal de operación [STB/d]"),
    stages: int = Query(..., gt=0, description="Etapas instaladas"),
    catalog=Depends(get_catalog),
) -> FigureResponse:
    """Curva head/eficiencia/HP de una bomba con el punto de operación marcado.

    Un ``pump_model`` inexistente sale como HTTP 422 (handler central).
    """
    pump = resolve_pump(catalog, pump_model)
    fig = plot_pump_curve(pump, operating_flow=operating_flow, stages=stages)
    return FigureResponse(figure=json.loads(fig.to_json()))
