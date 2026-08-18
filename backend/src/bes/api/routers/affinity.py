"""GET /api/affinity/* — leyes de afinidad sobre una bomba del catálogo.

Sección independiente del diseño: acá se explora cómo cambia la curva de una
bomba al variar la frecuencia del motor, el diámetro del impulsor o el fluido,
sin resolver un pozo. El cálculo vive en ``bes.core.affinity``.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query

from bes.api.deps import get_catalog, resolve_pump
from bes.api.schemas.analysis import AffinityResponse, FigureResponse
from bes.core.affinity import frequency_for_flow, scale_curve
from bes.plotting import plot_affinity_curves

router = APIRouter(prefix="/api/affinity", tags=["affinity"])


def _parse_frequencies(raw: str) -> list[float]:
    """"50,60,70" -> [50.0, 60.0, 70.0], validando el rango físico del VSD."""
    try:
        values = [float(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise ValueError(f"Lista de frecuencias inválida: '{raw}'") from None
    if not values:
        raise ValueError("Hay que pedir al menos una frecuencia")
    for f in values:
        if not (20.0 <= f <= 90.0):
            raise ValueError(
                f"Frecuencia {f:.0f} Hz fuera del rango operable de un VSD "
                f"(20–90 Hz)"
            )
    return values


@router.get("", response_model=AffinityResponse)
def get_affinity(
    pump_model: str = Query(..., description="Modelo de bomba del catálogo"),
    frequencies: str = Query(
        "50,60", description="Frecuencias a evaluar [Hz], separadas por coma",
    ),
    diameter_ratio: float = Query(
        1.0, gt=0, le=2, description="D₂/D₁ si el impulsor está rebajado",
    ),
    sg_ratio: float = Query(
        1.0, gt=0, le=3, description="SG₂/SG₁ para la ley de potencia",
    ),
    target_flow: float | None = Query(
        None, gt=0, description="Caudal objetivo [STB/d] para despejar la frecuencia",
    ),
    catalog=Depends(get_catalog),
) -> AffinityResponse:
    """Curvas de la bomba a varias frecuencias, más la frecuencia objetivo.

    Devuelve una curva reescalada por cada frecuencia pedida. Si se pasa
    ``target_flow``, además despeja la frecuencia que lleva el BEP a ese caudal
    (``f₂ = f₁·Q₂/Q₁``), que es la pregunta que se hace un diseño con variador.

    Un modelo inexistente o una frecuencia fuera del rango del variador salen
    como HTTP 422 (handler central).
    """
    pump = resolve_pump(catalog, pump_model)
    freqs = _parse_frequencies(frequencies)

    curves = [
        scale_curve(pump, f, diameter_ratio=diameter_ratio, sg_ratio=sg_ratio)
        for f in sorted(freqs)
    ]

    required = None
    if target_flow:
        required = frequency_for_flow(
            flow_at_reference=pump.bep_flow,
            target_flow=target_flow,
            reference_frequency=pump.catalog_frequency_hz,
        )

    return AffinityResponse(
        pump_model=pump.model,
        pump_manufacturer=pump.manufacturer,
        pump_series=pump.series,
        catalog_frequency_hz=pump.catalog_frequency_hz,
        curves=curves,
        target_flow=target_flow,
        frequency_for_target_flow=required,
    )


@router.get("/figure", response_model=FigureResponse)
def get_affinity_figure(
    pump_model: str = Query(..., description="Modelo de bomba del catálogo"),
    frequencies: str = Query("50,60", description="Frecuencias [Hz] separadas por coma"),
    diameter_ratio: float = Query(1.0, gt=0, le=2),
    sg_ratio: float = Query(1.0, gt=0, le=3),
    target_flow: float | None = Query(None, gt=0),
    catalog=Depends(get_catalog),
) -> FigureResponse:
    """Familia de curvas a distintas frecuencias, como figura Plotly."""
    pump = resolve_pump(catalog, pump_model)
    fig = plot_affinity_curves(
        pump,
        frequencies=_parse_frequencies(frequencies),
        diameter_ratio=diameter_ratio,
        sg_ratio=sg_ratio,
        target_flow=target_flow,
    )
    return FigureResponse(figure=json.loads(fig.to_json()))
