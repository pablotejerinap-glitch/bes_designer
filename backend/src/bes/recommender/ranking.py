"""Ordenamiento de alternativas por criterios de ingeniería — SIN puntajes.

Cuando varias bombas del catálogo sirven para el mismo pozo, hay que decidir
cuál se recomienda primero. Este módulo hace eso, y la manera en que **no** lo
hace es tan importante como la que sí.

**No hay puntajes, ni pesos, ni escalas de 0 a 10, ni preferencia de marca.**
Antes había un sistema de puntaje ponderado (rendimiento 40 % / flexibilidad
30 % / proveedor 30 %) que se eliminó: esos pesos eran arbitrarios y no salían
de ningún lado. El fabricante es información, no criterio.

En su lugar hay un **orden lexicográfico estricto** de tres criterios físicos::

    1. Distancia al BEP   — |q_op − q_BEP| / q_BEP        (menor es mejor)
    2. Rendimiento        — de la bomba en el punto de operación (mayor mejor)
    3. Potencia requerida — hp totales al eje              (menor es mejor)

Lexicográfico quiere decir que el criterio 2 **sólo** desempata al 1, y el 3
**sólo** desempata a los dos primeros. No se suman ni se promedian.

Por qué la distancia al BEP va primero
--------------------------------------
El BEP (*Best Efficiency Point*) es el caudal de máximo rendimiento de la
bomba. Brown Vol. 2b §4.5325: la bomba se debe elegir de modo que el caudal de
diseño caiga lo más cerca posible de su BEP. Operar lejos del BEP **aumenta el
empuje axial y el desgaste, y acorta la vida útil** — que es lo que más cuesta
en una instalación BES, porque cambiar el equipo implica intervenir el pozo.

Clasificación de la distancia al BEP (SOLO para mostrar)
--------------------------------------------------------
::

    <= 10 %  ->  "optimo"      muy cerca del BEP
    <= 25 %  ->  "aceptable"   moderadamente alejado
    >  25 %  ->  "alejado"     lejos; verificar con el fabricante

**Nunca interviene en el orden**: es una etiqueta para la pantalla. Los
umbrales clasifican la misma magnitud física del criterio 1, y reflejan la
práctica de mantener el punto de operación bien adentro del rango recomendado
por el fabricante, cuya semi-amplitud en las bombas del catálogo anda entre el
20 % y el 40 % del caudal de BEP.

Referencia
----------
Brown, K.E. "The Technology of Artificial Lift Methods", Vol. 2b, §4.5325.
Ver también ``REFORMA_COMPARACION_BES.docx``, donde se documenta la
eliminación del sistema de puntaje ponderado.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bes.core.models import PumpCurve

# Classification thresholds on |q − q_BEP| / q_BEP (fractions)
BEP_OPTIMAL_MAX = 0.10
BEP_ACCEPTABLE_MAX = 0.25

# Classification → UI label (Spanish) and indicator
CLASSIFICATION_LABELS: dict[str, str] = {
    "optimo": "Muy cerca del BEP",
    "aceptable": "Moderadamente alejado del BEP",
    "alejado": "Alejado del BEP",
}
CLASSIFICATION_INDICATORS: dict[str, str] = {
    "optimo": "✅",
    "aceptable": "⚠",
    "alejado": "❌",
}


def bep_distance(pump: "PumpCurve", flow: float) -> float:
    """Distancia relativa entre el caudal de operación y el BEP de la bomba.

        distancia = |caudal − caudal_BEP| / caudal_BEP

    Un valor de 0.0 significa que la bomba opera exactamente en su punto de
    máximo rendimiento; 0.10 significa que el caudal de operación se desvía un
    10 % del caudal de BEP.

    Args:
        pump: Bomba del catálogo (aporta ``bep_flow``).
        flow: Caudal de operación [STB/d]. Debe ser > 0.

    Returns:
        Distancia relativa adimensional [>= 0].

    Raises:
        ValueError: Si el caudal es <= 0 o la bomba no tiene un caudal de BEP
            positivo.
    """
    if flow <= 0:
        raise ValueError(f"flow must be > 0, got {flow}")
    if pump.bep_flow <= 0:
        raise ValueError(f"pump.bep_flow must be > 0, got {pump.bep_flow}")
    return abs(flow - pump.bep_flow) / pump.bep_flow


def ranking_key(
    bep_dist: float,
    efficiency: float,
    total_pump_hp: float,
) -> tuple[float, float, float]:
    """Clave de ordenamiento que implementa el orden estricto de ingeniería.

    Ordenar una lista de candidatas de menor a mayor por esta clave las deja
    ordenadas por: (1) cercanía al BEP, (2) mayor rendimiento, (3) menor
    potencia requerida.

    El truco es que el rendimiento entra **negado**: como la lista se ordena de
    menor a mayor, negarlo hace que el mayor rendimiento quede primero.

    Args:
        bep_dist: Distancia relativa al BEP, de :func:`bep_distance`.
        efficiency: Rendimiento hidráulico en el punto de operación [0–1].
        total_pump_hp: Potencia total al eje de la bomba [hp].

    Returns:
        Tupla usable directamente como clave de ``sort``. Sin pesos.
    """
    return (bep_dist, -efficiency, total_pump_hp)


def classify_bep_distance(bep_dist: float) -> str:
    """Classify a BEP distance for display purposes (never for ordering).

    Args:
        bep_dist: Relative BEP distance [>= 0].

    Returns:
        One of ``"optimo"`` (<= 10 %), ``"aceptable"`` (<= 25 %),
        ``"alejado"`` (> 25 %).
    """
    if bep_dist <= BEP_OPTIMAL_MAX:
        return "optimo"
    if bep_dist <= BEP_ACCEPTABLE_MAX:
        return "aceptable"
    return "alejado"
