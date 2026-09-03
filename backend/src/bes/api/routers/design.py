"""POST /api/design — top-N ESP design recommendations."""
from __future__ import annotations

import warnings

from fastapi import APIRouter, Depends

from bes.api.deps import get_catalog
from bes.api.mappers import from_design_result, to_domain_inputs
from bes.api.schemas import (
    CriteriaSchema, DesignRequest, DesignResponse, RecommendationSchema,
)
from bes.api.schemas.outputs import GasMethodDecision
from bes.recommender.recommendation_engine import (
    generate_recommendation_for_pump, generate_recommendations,
)
from bes.services.gas_service import gas_method_applies

router = APIRouter(prefix="/api", tags=["design"])


@router.post("/design", response_model=DesignResponse)
def post_design(req: DesignRequest, catalog=Depends(get_catalog)) -> DesignResponse:
    """Corre el motor de recomendación y devuelve los diseños ordenados.

    Si se manda ``pump_model``, el ordenamiento se saltea por completo y la
    respuesta trae un solo paquete de diseño para esa bomba (es un override
    manual de la elección del algoritmo, no una alternativa rankeada). En ese
    caso ``n`` se ignora.

    Un ``ValueError`` del dominio —sin diseño viable, bomba desconocida o
    incompatible— lo convierte en HTTP 422 el manejador central de ``api.main``.
    Las ``UserWarning`` del dominio (por ejemplo, un reservorio depletado) se
    capturan y viajan en ``warnings``.
    """
    reservoir, fluid, well, surface, objectives = to_domain_inputs(req)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        if req.pump_model:
            result = generate_recommendation_for_pump(
                reservoir, fluid, well, surface, objectives, catalog,
                pump_model=req.pump_model,
            )
        else:
            result = generate_recommendations(
                reservoir, fluid, well, surface, objectives, catalog, n=req.n,
            )

    recommendations = [
        RecommendationSchema(
            rank=r["rank"],
            criteria=CriteriaSchema(**r["criteria"]),
            design=from_design_result(r["design"]),
            rationale=r["rationale"],
            warnings=r["warnings"],
        )
        for r in result["recommendations"]
    ]

    # ¿Este pozo pedía el método por incrementos?
    #
    # Es un dato INFORMATIVO que se agrega a la respuesta: el diseño que se
    # devuelve es el convencional, calculado exactamente igual que siempre. La
    # pantalla lo usa para avisar —y, si el usuario lo dejó activado, para
    # pasar sola al camino de gas—, pero acá no se cambia ningún número.
    #
    # La fracción de gas libre NO se recalcula: se toma la que la propia
    # corrida ya publicó en ``gip_fraction``. Recalcularla abriría la puerta a
    # que la decisión del método se tome sobre un número distinto del que se
    # usó para diseñar.
    gas_method = None
    if result["recommendations"]:
        elegido = result["recommendations"][0]["design"]
        gas_method = GasMethodDecision(**gas_method_applies(
            fluid=fluid,
            pip=elegido.intake_pressure,
            temp_f=reservoir.reservoir_temp,
            threshold=objectives.gas_fraction_pc_threshold,
            free_gas_fraction=elegido.gip_fraction,
        ))

    return DesignResponse(
        recommendations=recommendations,
        design_basis=result["design_basis"],
        ordering_criteria=result["ordering_criteria"],
        n_candidates_evaluated=result["n_candidates_evaluated"],
        warnings=[str(w.message) for w in caught],
        gas_method=gas_method,
    )
