"""POST /api/design — top-N ESP design recommendations."""
from __future__ import annotations

import warnings

from fastapi import APIRouter, Depends

from bes.api.deps import get_catalog
from bes.api.mappers import from_design_result, to_domain_inputs
from bes.api.schemas import (
    CriteriaSchema, DesignRequest, DesignResponse, RecommendationSchema,
)
from bes.recommender.recommendation_engine import (
    generate_recommendation_for_pump, generate_recommendations,
)

router = APIRouter(prefix="/api", tags=["design"])


@router.post("/design", response_model=DesignResponse)
def post_design(req: DesignRequest, catalog=Depends(get_catalog)) -> DesignResponse:
    """Run the recommendation engine and return ranked design packages.

    If ``pump_model`` is set, the recommendation engine's ranking is bypassed
    entirely and the response carries a single design package for that named
    pump (a manual override of the algorithm's choice, not a ranked
    alternative) — ``n`` is ignored in that case.

    A domain ``ValueError`` (no feasible design, unknown/incompatible pump) is
    turned into HTTP 422 by the central handler in ``api.main``. Domain
    ``UserWarning``s (e.g. a depleted reservoir) are captured and surfaced in
    ``warnings``.
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

    return DesignResponse(
        recommendations=recommendations,
        design_basis=result["design_basis"],
        ordering_criteria=result["ordering_criteria"],
        n_candidates_evaluated=result["n_candidates_evaluated"],
        warnings=[str(w.message) for w in caught],
    )
