"""POST /api/design — top-N ESP design recommendations."""
from __future__ import annotations

import warnings

from fastapi import APIRouter, Depends

from bes.api.deps import get_catalog
from bes.api.mappers import from_design_result, to_domain_inputs
from bes.api.schemas import DesignRequest, DesignResponse, RecommendationSchema
from bes.recommender.recommendation_engine import generate_recommendations

router = APIRouter(prefix="/api", tags=["design"])


@router.post("/design", response_model=DesignResponse)
def post_design(req: DesignRequest, catalog=Depends(get_catalog)) -> DesignResponse:
    """Run the full recommendation engine and return ranked design packages.

    A domain ``ValueError`` (no feasible design) is turned into HTTP 422 by the
    central handler in ``api.main``. Domain ``UserWarning``s (e.g. a depleted
    reservoir) are captured and surfaced in ``warnings``.
    """
    reservoir, fluid, well, surface, objectives = to_domain_inputs(req)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = generate_recommendations(
            reservoir, fluid, well, surface, objectives, catalog, n=req.n,
        )

    recommendations = [
        RecommendationSchema(
            rank=r["rank"],
            score=r["score"],
            metrics=r["metrics"],
            design=from_design_result(r["design"]),
            rationale=r["rationale"],
            warnings=r["warnings"],
        )
        for r in result["recommendations"]
    ]

    return DesignResponse(
        recommendations=recommendations,
        design_basis=result["design_basis"],
        weights=result["weights"],
        n_candidates_evaluated=result["n_candidates_evaluated"],
        warnings=[str(w.message) for w in caught],
    )
