"""Servicio de análisis nodal.

El **análisis nodal** cruza dos curvas: lo que el reservorio puede entregar
(IPR) contra lo que el pozo necesita para levantar ese caudal (curva de
descarga). Donde se cruzan está el punto de operación real del pozo.

Este servicio produce las métricas numéricas y los datos de la tabla de
comparación; el armado de las figuras vive en ``bes.plotting``. Acá sólo se
resuelve el lado de los **datos**.

Todas las pérdidas de carga se calculan por Poettmann & Carpenter, que es la
única correlación multifásica del proyecto.
"""
from __future__ import annotations

from dataclasses import replace

from bes.core.models import Fluid, PumpCurve, Reservoir, SurfaceConditions, WellGeometry
from bes.core.nodal_analysis import METHOD_KEY, METHOD_LABEL, find_operating_point

# Única correlación multifásica del simulador (ver bes.core.multiphase).
NODAL_METHOD_KEY = METHOD_KEY
NODAL_METHOD_LABEL = METHOD_LABEL


def apply_reservoir_decline(reservoir: Reservoir, pr_decline_pct: float) -> Reservoir:
    """Devuelve un Reservoir con la presión estática bajada un porcentaje.

    Sirve para simular la **depleción**: qué le pasa al pozo cuando el
    reservorio pierde presión con los años. Es una de las preguntas centrales al
    dimensionar un equipo que va a estar años instalado.

    La presión de burbuja se acota a la nueva presión estática (más baja): no
    tiene sentido una burbuja por encima de la presión del reservorio. Si la
    declinación es cero o negativa, devuelve el reservorio original sin tocar.

    Es la **única fuente de verdad** de la simulación de declinación: la usan
    tanto el servicio de métricas como los constructores de gráficos.
    """
    if pr_decline_pct <= 0:
        return reservoir
    pr_new = reservoir.static_pressure * (1.0 - pr_decline_pct / 100.0)
    pb_new = min(reservoir.bubble_point, pr_new)
    return replace(reservoir, static_pressure=pr_new, bubble_point=pb_new)


def _single_metrics(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    pump: PumpCurve | None,
    stages: int | None,
    pump_depth: float | None,
) -> dict[str, float]:
    result = find_operating_point(
        reservoir, fluid, well, surface,
        pump=pump, stages=stages, pump_depth=pump_depth,
    )
    nat = result["natural_flow"]
    pmp = result["pump_flow"]
    q_nat = nat["q"] if nat else 0.0
    q_pmp = pmp["q"] if pmp else 0.0
    pwf_op = pmp["pwf"] if pmp else (nat["pwf"] if nat else 0.0)
    return {
        "q_natural":        q_nat,
        "q_pump":           q_pmp,
        "incremental_rate": result["incremental_rate"],
        "pwf_operating":    pwf_op,
        "pump_efficiency":  result["pump_efficiency"],
    }


def run_nodal_analysis(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    surface: SurfaceConditions,
    *,
    pr_decline_pct: float = 0.0,
    pump: PumpCurve | None = None,
    stages: int | None = None,
    pump_depth: float | None = None,
) -> dict:
    """Corre el análisis nodal y devuelve los resultados numéricos crudos.

    Args:
        reservoir, fluid, well, surface: Entradas del dominio.
        pr_decline_pct: Declinación de presión del reservorio a simular [%].
        pump, stages, pump_depth: Contexto opcional de la bomba, que viene del
            diseño elegido.

    Returns:
        dict con ``reservoir_eff`` (el Reservoir efectivo después de la
        declinación), ``pr_decline_pct``, ``has_pump``, ``method`` y
        ``metrics``. Todos los valores son números crudos — darles formato es
        trabajo de la interfaz.
    """
    reservoir_eff = apply_reservoir_decline(reservoir, pr_decline_pct)

    return {
        "reservoir_eff":  reservoir_eff,
        "pr_decline_pct": pr_decline_pct,
        "has_pump":       pump is not None,
        "method":         NODAL_METHOD_KEY,
        "metrics": _single_metrics(
            reservoir_eff, fluid, well, surface, pump, stages, pump_depth,
        ),
    }
