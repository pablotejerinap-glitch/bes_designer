"""Shared FastAPI dependencies."""
from __future__ import annotations

from functools import lru_cache

from bes.catalogs.loader import CatalogManager


@lru_cache(maxsize=1)
def get_catalog() -> CatalogManager:
    """Process-wide singleton catalog. ``CatalogManager()`` with no argument
    resolves the JSON dir from the package location, so it is CWD-independent.
    """
    return CatalogManager()


def resolve_pump(catalog: CatalogManager, model: str | None):
    """Look up a pump by catalog model name.

    Returns ``None`` for an empty/absent model (callers treat that as "no pump
    context"). An unknown model raises ``ValueError`` -> HTTP 422 via the
    central handler in ``api.main``.
    """
    if not model:
        return None
    pump = next((p for p in catalog.get_all_pumps() if p.model == model), None)
    if pump is None:
        raise ValueError(f"pump_model '{model}' no existe en el catálogo")
    return pump
