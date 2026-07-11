"""POST /api/reports/{pdf,xlsx} — generate a design report as a file download."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import Field

from api.deps import get_catalog
from api.mappers import to_domain_inputs
from api.schemas import DesignRequest
from recommender.recommendation_engine import generate_recommendations
from reports.excel_exporter import generate_design_excel
from reports.pdf_generator import generate_design_report

router = APIRouter(prefix="/api", tags=["reports"])

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_FORMATS = {
    "pdf":  ("application/pdf", "reporte_bes.pdf", generate_design_report),
    "xlsx": (_XLSX_MIME, "reporte_bes.xlsx", generate_design_excel),
}


class ReportRequest(DesignRequest):
    rank: int = Field(0, ge=0, description="Índice de la recomendación a reportar (0 = mejor)")


@router.post("/reports/{fmt}")
def post_report(fmt: str, req: ReportRequest, catalog=Depends(get_catalog)) -> Response:
    if fmt not in _FORMATS:
        raise HTTPException(status_code=404, detail=f"Formato '{fmt}' no soportado (pdf|xlsx)")

    reservoir, fluid, well, surface, objectives = to_domain_inputs(req)
    result = generate_recommendations(
        reservoir, fluid, well, surface, objectives, catalog, n=max(req.rank + 1, 3),
    )
    recs = result["recommendations"]
    if req.rank >= len(recs):
        raise ValueError(f"rank {req.rank} fuera de rango ({len(recs)} recomendaciones)")

    dr = recs[req.rank]["design"]
    well_data = {
        "reservoir": reservoir, "fluid": fluid, "well": well,
        "surface": surface, "objectives": objectives,
    }
    media, filename, generate = _FORMATS[fmt]
    data = generate(dr, well_data)
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
