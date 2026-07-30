"""GET /api/plots/* — Plotly figure JSON for charts that need no extra compute.

Los gráficos que acompañan un cálculo (nodal, sensibilidad) viajan dentro de la
respuesta de ese endpoint. Este router cubre los que el front pide por separado,
como la curva de una bomba del catálogo.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query

from bes.api.deps import get_catalog, resolve_pump
from bes.api.mappers import to_reservoir
from bes.api.schemas.analysis import FigureResponse
from bes.api.schemas.inputs import ReservoirSchema
from bes.plotting import plot_ipr_curve, plot_pump_catalog_curve, plot_pump_curve

router = APIRouter(prefix="/api/plots", tags=["plots"])


@router.post("/ipr-curve", response_model=FigureResponse)
def post_ipr_curve(reservoir: ReservoirSchema) -> FigureResponse:
    """Curva IPR del pozo a partir de los datos de reservorio, sin diseño previo.

    Devuelve el caudal de aporte frente a la presión de fondo fluyente (Pwf)
    según el método elegido (Vogel, Lineal, Combinada o Fetkovich), con el AOF y
    el rango de operación. Alimenta la vista de "Cálculo de IPR": el front manda
    los datos de reservorio y muestra la curva, independiente del análisis nodal
    (que exige una bomba). Un reservorio inválido —p. ej. Fetkovich sin C/n—
    sale como HTTP 422 (handler central).
    """
    res = to_reservoir(reservoir)
    fig = plot_ipr_curve(res)
    return FigureResponse(figure=json.loads(fig.to_json()))


@router.get("/pump-curve", response_model=FigureResponse)
def get_pump_curve(
    pump_model: str = Query(..., description="Modelo de bomba del catálogo"),
    operating_flow: float = Query(..., gt=0, description="Caudal de operación [STB/d]"),
    stages: int = Query(..., gt=0, description="Etapas instaladas"),
    catalog=Depends(get_catalog),
) -> FigureResponse:
    """Curva head/eficiencia/HP de una bomba con el punto de operación marcado.

    Pensada para el resultado de un diseño (escala por ``stages`` y marca el
    punto de operación). Para ver una bomba del catálogo sin un diseño previo,
    usar ``/pump-catalog-curve``. Un ``pump_model`` inexistente sale como HTTP
    422 (handler central).
    """
    pump = resolve_pump(catalog, pump_model)
    fig = plot_pump_curve(pump, operating_flow=operating_flow, stages=stages)
    return FigureResponse(figure=json.loads(fig.to_json()))


@router.get("/pump-catalog-curve", response_model=FigureResponse)
def get_pump_catalog_curve(
    pump_model: str = Query(..., description="Modelo de bomba del catálogo"),
    catalog=Depends(get_catalog),
) -> FigureResponse:
    """Curva de catálogo por etapa de una bomba, sin contexto de diseño.

    Devuelve head/etapa, HP/etapa y eficiencia frente al caudal, con el BEP y el
    rango operativo recomendado. Alimenta la pestaña de "ver la bomba
    seleccionada": el front elige un modelo de ``/api/catalogs`` y pide su curva
    con este endpoint. Un ``pump_model`` inexistente sale como HTTP 422.
    """
    pump = resolve_pump(catalog, pump_model)
    fig = plot_pump_catalog_curve(pump)
    return FigureResponse(figure=json.loads(fig.to_json()))
