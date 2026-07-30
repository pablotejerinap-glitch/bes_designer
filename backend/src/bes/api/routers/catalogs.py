"""GET /api/catalogs — light catalog overview for the frontend."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from bes.api.deps import get_catalog
from bes.api.schemas import CatalogSummary, PumpSummary, TubularCatalog, TubularDim

router = APIRouter(prefix="/api", tags=["catalogs"])


@router.get("/catalogs", response_model=CatalogSummary)
def get_catalogs(catalog=Depends(get_catalog)) -> CatalogSummary:
    pumps = catalog.get_all_pumps()
    pump_summaries = [
        PumpSummary(
            manufacturer=p.manufacturer, series=p.series, model=p.model,
            od=p.od, min_flow=p.min_flow, max_flow=p.max_flow, bep_flow=p.bep_flow,
        )
        for p in pumps
    ]
    manufacturers = sorted({p.manufacturer for p in pumps})
    counts = {
        "pumps":        len(pumps),
        "seals":        len(catalog.get_all_seals()),
        "gas_handlers": len(catalog.get_all_gas_handlers()),
        "sensors":      len(catalog.get_all_sensors()),
    }
    return CatalogSummary(pumps=pump_summaries, manufacturers=manufacturers, counts=counts)


@router.get("/catalogs/tubulars", response_model=TubularCatalog)
def get_tubulars(catalog=Depends(get_catalog)) -> TubularCatalog:
    """Tablas dimensionales Tenaris (API 5CT) de casing y tubing.

    Cada fila lleva OD + peso nominal con su ID y drift ya resueltos, de modo
    que el frontend pueda ofrecer OD -> peso y autocompletar el ID sin que el
    usuario tenga que conocerlo.
    """
    return TubularCatalog(
        casing=[TubularDim(**r) for r in catalog.all_casing_dims()],
        tubing=[TubularDim(**r) for r in catalog.all_tubing_dims()],
    )
