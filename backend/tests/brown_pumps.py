"""Las bombas de los ejemplos de Kermit Brown, sólo para los tests.

**No están en el catálogo de la aplicación, y es a propósito.** La app publica
únicamente bombas digitalizadas de catálogos reales de fabricante (REDA,
Centrilift, Wood Group); las tres del libro —I-300, I-42B y M-34— no salen de un
catálogo sino de los enunciados impresos del Vol. 2b, Cap. 4.5, así que se
retiraron de ``bes/catalogs/pumps.json`` en agosto de 2026.

Pero la **regla de oro** del proyecto sigue en pie: toda cuenta del dominio se
valida contra un ejemplo numerado del libro. Para eso los datos impresos se
conservan acá, en ``tests/data/brown_pumps.json``, y este módulo los inyecta en
un :class:`~bes.catalogs.loader.CatalogManager` cuando un test los necesita.

Uso::

    from tests.brown_pumps import catalogo_con_bombas_del_libro

    @pytest.fixture(scope="module")
    def manager():
        return catalogo_con_bombas_del_libro()

Un diseño que corre con este catálogo **no representa lo que hace la app**:
representa lo que hace el libro. Los tests que verifican qué ofrece la
aplicación tienen que usar ``CatalogManager()`` pelado.
"""
from __future__ import annotations

import json
from pathlib import Path

from bes.catalogs.loader import CatalogManager, _parse_pumps

#: Los datos impresos, fuera del paquete distribuible.
BROWN_PUMPS_JSON = Path(__file__).parent / "data" / "brown_pumps.json"


def bombas_del_libro() -> list:
    """Las tres bombas del libro, ya parseadas a ``PumpCurve``.

    Returns:
        Lista de :class:`bes.core.models.PumpCurve` — I-42B, I-300 y M-34.
    """
    raw = json.loads(BROWN_PUMPS_JSON.read_text(encoding="utf-8"))["pumps"]
    return _parse_pumps(raw)


def catalogo_con_bombas_del_libro() -> CatalogManager:
    """Un catálogo normal **más** las bombas de los ejemplos del libro.

    Los motores, cables, sellos y demás son los del catálogo real: lo único que
    se agrega son las tres curvas impresas, que es lo que hace falta para
    reproducir los ejemplos numerados.

    Returns:
        El ``CatalogManager`` con las tres bombas agregadas.
    """
    cm = CatalogManager()
    cm._pumps = [*cm._pumps, *bombas_del_libro()]
    return cm
