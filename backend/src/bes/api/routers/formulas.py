"""GET /api/formulas — el catálogo de fórmulas del motor de cálculo.

Se puede enumerar **sin correr ningún diseño**, que es justamente el punto: con
la traza de una corrida sólo se ve la rama que ese pozo ejecutó, y para revisar
Fetkovich habría que armar un caso de Fetkovich. Acá están las cuatro maneras de
llegar a la Pwf, las dos correlaciones de fricción y todo el resto, cada una con
su glosario de símbolos y su cita.

La declaración vive en :mod:`bes.core.formula_catalog`; este router sólo la
sirve. Los temas que todavía no emiten traza viajan igual, marcados
``instrumented: false``, para que la pantalla muestre la cobertura real en vez
de esconder lo que falta.
"""
from __future__ import annotations

from fastapi import APIRouter

from bes.api.schemas.analysis import FormulaCatalogResponse
from bes.core.formula_catalog import catalog_by_topic

router = APIRouter(prefix="/api/formulas", tags=["formulas"])


@router.get("", response_model=FormulaCatalogResponse)
def get_formulas() -> dict:
    """Todas las fórmulas del motor, agrupadas por tema y en orden de diseño.

    Returns:
        ``topics``: la lista de temas, cada uno con sus fórmulas.
        ``total``: cuántas fórmulas están instrumentadas hoy.
        ``pending_topics``: los temas que todavía no emiten traza.
    """
    temas = catalog_by_topic()
    return {
        "topics": temas,
        "total": sum(len(t["formulas"]) for t in temas),
        "pending_topics": [t["key"] for t in temas if not t["instrumented"]],
    }
