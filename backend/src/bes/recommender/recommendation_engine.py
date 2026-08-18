"""Motor de recomendación — la API de más alto nivel del paquete.

Arma paquetes de diseño BES completos (bomba + motor + cable + transformador)
y los ordena por criterios estrictos de ingeniería: distancia al BEP →
rendimiento → potencia requerida (ver ``recommender/ranking.py``).

Cada recomendación viaja con sus **valores crudos** de los criterios y con una
justificación en castellano armada **exclusivamente a partir de los datos
calculados** — nada de texto enlatado.

**No hay puntajes, ni pesos, ni preferencia de proveedor**: el fabricante se
informa como dato, no como criterio de selección.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from bes.core.models import (
    DesignObjectives,
    DesignResult,
    Fluid,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)
from bes.recommender.pump_selector import select_pump_by_model, select_top_n_pumps
from bes.recommender.ranking import (
    bep_distance,
    classify_bep_distance,
    ranking_key,
)

if TYPE_CHECKING:
    from bes.catalogs.loader import CatalogManager


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_criteria(dr: DesignResult, pump_obj, target_flow: float) -> dict:
    """Raw engineering criteria for one design — the data the ranking uses."""
    dist = bep_distance(pump_obj, target_flow)
    return {
        "bep_flow_bpd": pump_obj.bep_flow,
        "bep_distance_frac": dist,
        "flow_vs_bep_pct": 100.0 * target_flow / pump_obj.bep_flow,
        "efficiency": dr.pump_efficiency,
        "total_pump_hp": dr.total_pump_hp,
        "classification": classify_bep_distance(dist),
    }


def _build_rationale(
    dr: DesignResult,
    criteria: dict,
    rank: int,
    avg_efficiency: float,
    n_alternatives: int,
    manual: bool = False,
) -> str:
    """Natural-language explanation assembled ONLY from calculated values.

    Every number in the sentence comes from the hydraulic/electrical design
    or the pump catalog curve — nothing is estimated or invented here.
    ``manual=True`` frames the intro as a user override rather than a ranked
    alternative (used by ``generate_recommendation_for_pump``).
    """
    if manual:
        intro = (
            f"La bomba {dr.pump_model} ({dr.pump_manufacturer}) fue "
            f"seleccionada manualmente por el usuario. Opera al "
            f"{criteria['flow_vs_bep_pct']:.0f} % de su caudal de máxima "
            f"eficiencia (BEP = {criteria['bep_flow_bpd']:.0f} STB/d frente a "
            f"{dr.flow_rate_achieved:.0f} STB/d de diseño), alcanza el TDH "
            f"requerido de {dr.total_head_required:.0f} ft con "
            f"{dr.num_stages} etapas y presenta una eficiencia hidráulica del "
            f"{dr.pump_efficiency:.1%}"
        )
    else:
        ordinal = (
            "primera alternativa" if rank == 1 else f"alternativa {rank}"
        )
        intro = (
            f"La bomba {dr.pump_model} ({dr.pump_manufacturer}) fue seleccionada "
            f"como {ordinal} porque opera al "
            f"{criteria['flow_vs_bep_pct']:.0f} % de su caudal de máxima "
            f"eficiencia (BEP = {criteria['bep_flow_bpd']:.0f} STB/d frente a "
            f"{dr.flow_rate_achieved:.0f} STB/d de diseño), alcanza el TDH "
            f"requerido de {dr.total_head_required:.0f} ft con "
            f"{dr.num_stages} etapas y presenta una eficiencia hidráulica del "
            f"{dr.pump_efficiency:.1%}"
        )

    parts: list[str] = [intro]

    if n_alternatives > 1:
        comparison = (
            "superior" if dr.pump_efficiency >= avg_efficiency else "inferior"
        )
        parts.append(
            f", {comparison} al promedio de las {n_alternatives} alternativas "
            f"evaluadas ({avg_efficiency:.1%})"
        )

    parts.append(
        f". La potencia requerida es {dr.total_pump_hp:.1f} hp, cubierta por "
        f"un motor {dr.motor_model} de {dr.motor_hp:.0f} hp "
        f"({dr.motor_voltage:.0f} V / {dr.motor_amperage:.0f} A)."
    )

    dist_pct = criteria["bep_distance_frac"] * 100.0
    classification = criteria["classification"]
    if classification == "optimo":
        parts.append(
            f" El punto operativo está a {dist_pct:.0f} % del BEP, dentro de "
            "la zona de máxima confiabilidad hidráulica."
        )
    elif classification == "aceptable":
        parts.append(
            f" El punto operativo está a {dist_pct:.0f} % del BEP: operación "
            "aceptable, dentro del rango recomendado del fabricante."
        )
    else:
        parts.append(
            f" El punto operativo está a {dist_pct:.0f} % del BEP: verificar "
            "con el fabricante la operación sostenida en este punto."
        )

    if dr.gip_fraction > 0.30:
        parts.append(
            f" Gas libre en la admisión: {dr.gip_fraction:.0%} — se requiere "
            "separador de gas de fondo."
        )
    elif dr.gip_fraction > 0.10:
        parts.append(
            f" Gas libre en la admisión: {dr.gip_fraction:.0%} — considerar "
            "separador de gas."
        )

    if dr.warnings:
        parts.append(f" Observaciones de diseño: {'; '.join(dr.warnings)}.")

    return "".join(parts)


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
    """Genera las N mejores recomendaciones de diseño BES completas.

    Las alternativas se ordenan por criterios estrictos de ingeniería, en este
    orden de prioridad: (1) distancia del caudal de operación al BEP de la
    bomba, (2) rendimiento hidráulico en el punto de operación, (3) menor
    potencia al eje requerida. Sin puntajes ponderados ni preferencia de
    proveedor; el fabricante es informativo.

    Args:
        reservoir: Propiedades del reservorio.
        fluid: PVT y composición del fluido.
        well: Geometría del pozo (casing, tubing, profundidades, temperaturas).
        surface: Condiciones de superficie (presión de boca, línea, tensión,
            frecuencia).
        objectives: Objetivos de producción y restricciones de diseño.
        catalog: Catálogo de equipos cargado (bombas, motores, cables, sellos).
        n: Cuántas recomendaciones devolver (por defecto 3).

    Returns:
        dict con estas claves:

        ``recommendations``
            Lista de dicts, uno por recomendación, cada uno con:

            - ``rank``      : posición desde 1 (1 = la mejor según los
              criterios).
            - ``criteria``  : los valores crudos usados para ordenar
              (bep_flow_bpd, bep_distance_frac, flow_vs_bep_pct, efficiency,
              total_pump_hp, classification).
            - ``design``    : el objeto :class:`~core.models.DesignResult`.
            - ``rationale`` : justificación en castellano, armada a partir de
              los valores calculados.
            - ``warnings``  : advertencias heredadas del diseño hidráulico.

        ``design_basis``
            Resumen de las condiciones de entrada usadas para seleccionar.

        ``ordering_criteria``
            Lista ordenada de los criterios aplicados. Es documentación del
            método, **no** pesos ajustables.

        ``n_candidates_evaluated``
            Cuántos diseños completos se armaron y ordenaron.

    Raises:
        ValueError: Si no se puede armar ningún diseño que califique.
    """
    designs = select_top_n_pumps(
        reservoir=reservoir,
        fluid=fluid,
        well=well,
        surface=surface,
        objectives=objectives,
        catalog=catalog,
        n=n,
    )

    if not designs:
        raise ValueError(
            "No complete ESP design could be assembled for the given conditions."
        )

    pump_lookup = {p.model: p for p in catalog.get_all_pumps()}

    # Pair each design with its criteria; drop designs whose pump vanished
    # from the catalog (defensive — should not happen in practice).
    paired: list[tuple[DesignResult, dict]] = []
    for dr in designs:
        pump_obj = pump_lookup.get(dr.pump_model)
        if pump_obj is None:
            continue
        paired.append(
            (dr, _build_criteria(dr, pump_obj, objectives.target_flow_rate))
        )

    if not paired:
        raise ValueError(
            "No complete ESP design could be assembled for the given conditions."
        )

    # Enforce the engineering ordering at this level too (same key as the
    # selector): BEP distance asc → efficiency desc → required power asc.
    paired.sort(
        key=lambda item: ranking_key(
            bep_dist=item[1]["bep_distance_frac"],
            efficiency=item[1]["efficiency"],
            total_pump_hp=item[1]["total_pump_hp"],
        )
    )

    avg_efficiency = (
        sum(dr.pump_efficiency for dr, _ in paired) / len(paired)
    )

    recommendations: list[dict] = []
    for rank, (dr, criteria) in enumerate(paired, start=1):
        rationale = _build_rationale(
            dr=dr,
            criteria=criteria,
            rank=rank,
            avg_efficiency=avg_efficiency,
            n_alternatives=len(paired),
        )
        recommendations.append({
            "rank":      rank,
            "criteria":  criteria,
            "design":    dr,
            "rationale": rationale,
            "warnings":  dr.warnings,
        })

    return {
        "recommendations": recommendations,
        "design_basis": {
            "target_flow_rate_bpd": objectives.target_flow_rate,
            "well_depth_ft":        well.total_depth,
            "casing_id_in":         well.casing_id,
            "reservoir_pressure_psi": reservoir.static_pressure,
            "bottom_hole_temp_f":   reservoir.reservoir_temp,
        },
        "ordering_criteria": [
            "1. Cercanía al BEP (|q − q_BEP| / q_BEP, ascendente)",
            "2. Eficiencia hidráulica en el punto operativo (descendente)",
            "3. Potencia requerida en el eje (ascendente)",
        ],
        "n_candidates_evaluated": len(paired),
    }


def generate_recommendation_for_pump(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    objectives: DesignObjectives,
    catalog: "CatalogManager",
    pump_model: str,
) -> dict:
    """Arma el paquete de diseño completo para UNA bomba elegida por el usuario.

    Saltea por completo el ordenamiento del motor de recomendación: esto es un
    override manual de la elección del algoritmo, no una alternativa rankeada.

    El dict que devuelve tiene la **misma forma** que el de
    :func:`generate_recommendations` (una lista ``recommendations`` de un solo
    elemento, rank 1), así que la API y el frontend lo pueden renderizar por el
    mismo camino sin código nuevo.

    Args:
        reservoir: Propiedades del reservorio.
        fluid: PVT y composición del fluido.
        well: Geometría del pozo.
        surface: Condiciones de superficie y alimentación eléctrica.
        objectives: Objetivos de producción.
        catalog: Catálogo de equipos cargado.
        pump_model: Nombre del modelo de catálogo que eligió el usuario.

    Raises:
        ValueError: Si la bomba no existe, no entra en el casing del pozo, o el
            diseño no se puede completar en las condiciones pedidas.
    """
    dr = select_pump_by_model(
        reservoir=reservoir,
        fluid=fluid,
        well=well,
        surface=surface,
        objectives=objectives,
        catalog=catalog,
        pump_model=pump_model,
    )

    pump_obj = next(p for p in catalog.get_all_pumps() if p.model == pump_model)
    criteria = _build_criteria(dr, pump_obj, objectives.target_flow_rate)
    rationale = _build_rationale(
        dr=dr,
        criteria=criteria,
        rank=1,
        avg_efficiency=dr.pump_efficiency,
        n_alternatives=1,
        manual=True,
    )

    return {
        "recommendations": [{
            "rank":      1,
            "criteria":  criteria,
            "design":    dr,
            "rationale": rationale,
            "warnings":  dr.warnings,
        }],
        "design_basis": {
            "target_flow_rate_bpd": objectives.target_flow_rate,
            "well_depth_ft":        well.total_depth,
            "casing_id_in":         well.casing_id,
            "reservoir_pressure_psi": reservoir.static_pressure,
            "bottom_hole_temp_f":   reservoir.reservoir_temp,
        },
        "ordering_criteria": [
            "Selección manual del usuario — no se aplica ordenamiento por criterios.",
        ],
        "n_candidates_evaluated": 1,
    }
