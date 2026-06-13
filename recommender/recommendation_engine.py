"""
Recommendation engine — top-level API for BES/ESP equipment selection.

Produces ranked, annotated ESP design packages (pump + motor + cable +
transformer) with a human-readable rationale for each recommendation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from core.models import (
    DesignObjectives,
    DesignResult,
    Fluid,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)
from recommender.pump_selector import select_top_n_pumps
from recommender.scoring import (
    DEFAULT_WEIGHTS,
    provider_score,
    efficiency_score,
    flexibility_score,
    overall_score,
)

if TYPE_CHECKING:
    from catalogs.loader import CatalogManager


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _score_design(
    dr: DesignResult,
    pump_obj,
    target_flow: float,
    casing_id: float,
    preferred_manufacturer: str = "",
) -> tuple[float, dict[str, float]]:
    """Re-compute all scoring dimensions for a DesignResult."""
    eff_s  = efficiency_score(dr.pump_efficiency)
    flex_s = flexibility_score(pump_obj, target_flow)
    prov_s = provider_score(dr.pump_manufacturer, preferred_manufacturer)
    metrics = {"efficiency": eff_s, "flexibility": flex_s, "provider": prov_s}
    return overall_score(metrics), metrics


def _build_rationale(
    dr: DesignResult,
    metrics: dict[str, float],
    score: float,
    rank: int,
) -> str:
    """Generate a one-paragraph plain-English rationale for a design choice."""
    parts: list[str] = []

    # Opening
    if rank == 1:
        parts.append(
            f"Top recommendation: {dr.pump_model} ({dr.pump_manufacturer}), "
            f"overall score {score:.1f}/10."
        )
    else:
        parts.append(
            f"Alternative {rank}: {dr.pump_model} ({dr.pump_manufacturer}), "
            f"overall score {score:.1f}/10."
        )

    # Efficiency
    parts.append(
        f"Pump efficiency {dr.pump_efficiency:.1%} "
        f"(efficiency score {metrics['efficiency']:.1f}/10)."
    )

    # BEP proximity
    flex = metrics["flexibility"]
    if flex >= 8.0:
        parts.append("Operating very close to BEP — optimal hydraulic reliability.")
    elif flex >= 5.0:
        parts.append("Operating within acceptable distance of BEP.")
    else:
        parts.append(
            "Flow point is distant from BEP — verify this operating point "
            "is acceptable or consider an alternative pump."
        )

    # Equipment summary
    parts.append(
        f"{dr.num_stages} stages developing {dr.total_head_required:.0f} ft TDH. "
        f"Motor: {dr.motor_model} {dr.motor_hp:.0f} hp / "
        f"{dr.motor_voltage:.0f} V / {dr.motor_amperage:.0f} A. "
        f"Cable: #{dr.cable_awg} {dr.cable_type}, "
        f"surface voltage {dr.surface_voltage_required:.0f} V, "
        f"transformer {dr.transformer_kva:.0f} kVA."
    )

    # Gas warning
    if dr.gip_fraction > 0.30:
        parts.append(
            f"High free-gas fraction at intake ({dr.gip_fraction:.0%}) — "
            "downhole gas separator strongly recommended."
        )
    elif dr.gip_fraction > 0.10:
        parts.append(
            f"Moderate free-gas fraction ({dr.gip_fraction:.0%}) — "
            "gas separator should be considered."
        )

    # Stage-count warning
    if dr.warnings:
        parts.append(f"Design flags: {'; '.join(dr.warnings)}.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_recommendations(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    catalog: "CatalogManager",
    n: int = 3,
) -> dict:
    """Generate the top N complete ESP design recommendations.

    Each recommendation includes a full DesignResult (pump, motor, cable,
    transformer), individual dimension scores, an overall score, and a
    plain-English rationale explaining the selection.

    Args:
        reservoir: Reservoir properties.
        fluid: Fluid PVT and composition.
        well: Well geometry (casing, tubing, depths, temperatures).
        surface: Surface conditions (WHP, flowline, voltage, frequency).
        objectives: Production targets and design constraints.
        catalog: Loaded equipment catalog (pumps, motors, cables, seals).
        n: Number of recommendations to return (default 3).

    Returns:
        dict with keys:

        ``recommendations``
            List of dicts, one per recommendation, each containing:

            - ``rank``       : 1-based position (1 = best).
            - ``score``      : Overall score [0–10].
            - ``metrics``    : Per-dimension scores (efficiency, flexibility, provider).
            - ``design``     : :class:`~core.models.DesignResult` object.
            - ``rationale``  : Plain-English selection rationale [str].
            - ``warnings``   : Design flags inherited from hydraulic design.

        ``design_basis``
            Summary of the input conditions used for selection.

        ``weights``
            Scoring weights applied (copy of :data:`~recommender.scoring.DEFAULT_WEIGHTS`).

        ``n_candidates_evaluated``
            Number of pump candidates scored before selecting the top N.

    Raises:
        ValueError: If no qualifying designs can be built.
    """
    designs = select_top_n_pumps(
        reservoir=reservoir,
        fluid=fluid,
        well=well,
        surface=surface,
        objectives=objectives,
        catalog=catalog,
        n=n,
        diversify=objectives.use_vsd is not None,  # always diversify when possible
    )

    if not designs:
        raise ValueError(
            "No complete ESP design could be assembled for the given conditions."
        )

    pump_lookup = {p.model: p for p in catalog.get_all_pumps()}

    recommendations: list[dict] = []
    for rank, dr in enumerate(designs, start=1):
        pump_obj = pump_lookup.get(dr.pump_model)
        if pump_obj is None:
            continue

        score, metrics = _score_design(
            dr=dr,
            pump_obj=pump_obj,
            target_flow=objectives.target_flow_rate,
            casing_id=well.casing_id,
            preferred_manufacturer=objectives.preferred_manufacturer,
        )
        rationale = _build_rationale(dr, metrics, score, rank)

        recommendations.append({
            "rank":     rank,
            "score":    round(score, 2),
            "metrics":  {k: round(v, 2) for k, v in metrics.items()},
            "design":   dr,
            "rationale": rationale,
            "warnings": dr.warnings,
        })

    # Ensure recommendations are sorted by score descending
    recommendations.sort(key=lambda r: r["score"], reverse=True)
    for i, rec in enumerate(recommendations, start=1):
        rec["rank"] = i

    return {
        "recommendations": recommendations,
        "design_basis": {
            "target_flow_rate_bpd": objectives.target_flow_rate,
            "well_depth_ft":        well.total_depth,
            "casing_id_in":         well.casing_id,
            "reservoir_pressure_psi": reservoir.static_pressure,
            "bottom_hole_temp_f":   well.bottom_hole_temp,
        },
        "weights": dict(DEFAULT_WEIGHTS),
        "n_candidates_evaluated": len(designs),
    }
