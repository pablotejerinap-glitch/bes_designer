"""Shared FastAPI dependencies."""
from __future__ import annotations

from functools import lru_cache

from bes.catalogs.loader import CatalogManager


@lru_cache(maxsize=1)
def get_catalog() -> CatalogManager:
    """Catálogo único para todo el proceso (singleton).

    ``CatalogManager()`` sin argumentos resuelve la carpeta de los JSON a partir
    de la ubicación del paquete, así que **no depende del directorio de
    trabajo**: funciona igual se lo llame desde donde se lo llame.
    """
    return CatalogManager()


def resolve_pump(catalog: CatalogManager, model: str | None):
    """Busca una bomba por su nombre de modelo en el catálogo.

    Devuelve ``None`` si el modelo viene vacío o ausente — quien llama lo
    interpreta como «sin contexto de bomba». Un modelo desconocido levanta
    ``ValueError``, que el manejador central de ``api.main`` convierte en un
    HTTP 422.
    """
    if not model:
        return None
    pump = next((p for p in catalog.get_all_pumps() if p.model == model), None)
    if pump is None:
        raise ValueError(f"pump_model '{model}' no existe en el catálogo")
    return pump
