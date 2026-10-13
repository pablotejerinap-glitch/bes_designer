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


# --- Foto de la curva de catálogo de cada bomba ------------------------------
_CURVAS = __import__("pathlib").Path(__file__).resolve().parents[2] / "catalogs" / "curvas"


def _indice_curvas() -> dict:
    import json
    p = _CURVAS / "indice.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@router.get("/catalogs/pumps/{model}/curva-info")
def get_curva_info(model: str, hz: float = 60.0) -> dict:
    """Qué foto de catálogo hay para la bomba y a qué frecuencia.

    Se muestra la de la frecuencia de diseño si existe (50 o 60 Hz); si no, la
    más cercana. Centrilift no publica curvas dibujadas: ``tiene_foto`` = False.
    """
    ent = _indice_curvas().get(model)
    if not ent:
        return {"tiene_foto": False, "hz": None, "fuente": None}
    disponibles = [f for f in ("60", "50") if f in ent]
    elegida = min(disponibles, key=lambda f: abs(float(f) - hz))
    return {"tiene_foto": True, "hz": int(elegida), "fuente": ent["fuente"],
            "url": f"/api/catalogs/pumps/{model}/curva.jpg?hz={elegida}"}


@router.get("/catalogs/pumps/{model}/curva.jpg")
def get_curva_foto(model: str, hz: int = 60):
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    ent = _indice_curvas().get(model, {})
    nombre = ent.get(str(hz))
    if not nombre:
        raise HTTPException(status_code=404, detail=f"No hay foto de catálogo de {model} a {hz} Hz.")
    return FileResponse(_CURVAS / nombre, media_type="image/jpeg")
