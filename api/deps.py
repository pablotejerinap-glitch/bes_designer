"""Shared FastAPI dependencies."""
from __future__ import annotations

from functools import lru_cache

from catalogs.loader import CatalogManager


@lru_cache(maxsize=1)
def get_catalog() -> CatalogManager:
    """Process-wide singleton catalog. ``CatalogManager()`` with no argument
    resolves the JSON dir from the package location, so it is CWD-independent.
    """
    return CatalogManager()
