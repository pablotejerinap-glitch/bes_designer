"""Manejo del gas: qué pasa cuando el pozo trae gas libre y cómo se diseña.

**El gas es el enemigo de una bomba centrífuga.** Una bomba está hecha para
mover líquido; el gas es compresible, así que en vez de ser impulsado se
comprime y se expande dentro del impulsor. Con poco gas la bomba entrega menos
altura de la que dice su curva. Con mucho gas deja de bombear directamente:
es el **bloqueo por gas** (*gas lock*).

Por eso todo diseño BES tiene que responder tres preguntas antes de seguir:

    1. ¿Cuánto gas libre hay en la admisión de la bomba?
    2. ¿Hace falta un separador de gas, o alcanza con ventear por el anular?
    3. Con el gas que igual entra, ¿cuántas etapas hacen falta?

Dos magnitudes que la bibliografía mezcla — NO son lo mismo
-----------------------------------------------------------
::

    fracción  f = V_gas / (V_gas + V_líquido)      f = r / (1 + r)
    relación  r = V_gas / V_líquido                r = f / (1 − f)

Una relación de 1.0 es una fracción de **0.50**, no de 1.0. Confundirlas corre
los umbrales a la mitad. :func:`free_gas_fraction_at_intake` devuelve
**fracción**; donde el criterio del libro está en relación, se convierte
explícitamente con :func:`fraction_to_ratio`.

Los umbrales
------------
    Fracción <= 1 %    gas despreciable: vale el diseño monofásico
    Fracción >  1 %    obligatorio calcular la pérdida de carga multifásica
    Fracción >  5 %    obligatorio separador o manejador de gas
    Fracción > 10 % EN LA BOMBA   la BES no converge: evaluar otro método
    Relación > 0.1     la bomba entrega menos altura que su curva de agua
    Relación >= 1.0    bloqueo total por gas: deja de bombear líquido

El separador escala la RELACION, no la fracción
-----------------------------------------------
Un separador que retira el 75 % del gas libre **no** deja ``f × 0.25``. Saca
gas y deja el líquido, así que lo proporcional es la relación::

    r = f/(1−f)  ->  r' = r·(1−η)  ->  f' = r'/(1+r')

El error de la cuenta ingenua crece con el gas: con f = 65 % y η = 75 %, lo
correcto da **31.6 %** y lo ingenuo **16.2 %** — casi el doble, y la diferencia
entre rechazar un pozo y aceptarlo.

El método de incrementos de presión (§4.53103)
----------------------------------------------
Es el corazón del módulo. **Con gas, el caudal volumétrico NO es constante a lo
largo de la bomba**: a medida que la presión sube, el gas se comprime y parte
pasa a solución, así que el fluido ocupa cada vez menos. No se puede resolver
la bomba con un caudal único.

La solución del libro es partir el salto de presión en escalones y resolver
tramo por tramo. En cada tramo se evalúan las propiedades en **los dos
extremos** y se promedian — no en el punto medio, porque Bg va con 1/P y el
promedio de los extremos no es el valor del medio.

Contenido
---------
1. Constantes y umbrales de gas
2. Fracción de gas libre en la admisión, y conversiones fracción <-> relación
3. Ingestión de gas (GIP) y separadores
4. Deterioro de la bomba por gas libre
5. Viabilidad: ¿se puede diseñar este pozo con BES?
6. Propiedades de la mezcla y selección de bomba
7. Método de incrementos de presión — el diseño tramo por tramo
8. Diseño de gas completo, de punta a punta

Nomenclatura
------------
    f, f_g    Fracción volumétrica de gas libre              [0–1]
    r         Relación gas/líquido                           [-]
    GIP       Gas Ingestion Percentage: gas que entra a la bomba [0–1]
    PIP       Presión en la admisión de la bomba             [psia]
    ΔP        Salto de presión que da la bomba               [psi]
    Bg        Factor de volumen del gas                      [bbl/scf]
    Rs        Gas en solución                                [scf/STB]
    GOR       Relación gas-petróleo de producción            [scf/STB]
    WC        Corte de agua                                  [0–1]
    gas lock  Bloqueo por gas: la bomba deja de bombear

Referencias
-----------
Brown, K.E. "The Technology of Artificial Lift Methods", Vol. 2b, §4.53102
    (deterioro por gas) y §4.53103 (método de incrementos de presión).
Takács, G. "Electrical Submersible Pumps Manual".
"""
from __future__ import annotations

import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from bes.core.formulas import FormulaTrace
from bes.core.models import Fluid, Reservoir, WellGeometry
from bes.core.pvt import (
    fluid_properties_at_conditions,
    standing_rs,
    standing_bo,
    gas_z_factor,
    gas_bg,
    water_bw,
)

if TYPE_CHECKING:
    from bes.catalogs.loader import CatalogManager

_BBL_TO_FT3 = 5.615
_RHO_WATER_SC = 62.4   # lb/ft³
_RHO_AIR_SC = 0.0764   # lb/scf

#: Digitalización del Apéndice 4K del libro (ver el ``_source`` del archivo).
_4K_PATH = Path(__file__).parent.parent / "catalogs" / "gas_thru_pump_4K.json"
_4K: dict | None = None


def _oil_sg(api: float) -> float:
    return 141.5 / (131.5 + api)


# ---------------------------------------------------------------------------
# 1. Gas Ingestion Percentage
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Umbrales de gas libre en la admisión
# ---------------------------------------------------------------------------
#
# ATENCIÓN — hay DOS magnitudes distintas y la bibliografía las mezcla:
#
#   fracción  f = V_gas / (V_gas + V_líquido)      [0 – 1]
#   relación  r = V_gas / V_líquido                [0 – ∞)
#
#   f = r / (1 + r)          r = f / (1 − f)
#
# No son intercambiables. Una relación de 1.0 (tanto gas como líquido) es una
# fracción de 0.50, no de 1.0. Confundirlas mueve los umbrales a la mitad, así
# que todo el módulo trabaja en FRACCIÓN —que es lo que devuelve
# free_gas_fraction_at_intake()— y convierte explícitamente donde el criterio
# bibliográfico está expresado en relación.
#
# Criterios (Brown Vol. 2b §4.53102 y Takács, "Electrical Submersible Pumps
# Manual"):
#
#   FRACCIÓN del volumen total en la admisión
#     f ≤ 1 %   gas despreciable: se puede diseñar como monofásico con
#               gradiente constante
#     f > 1 %   obligatorio calcular la pérdida de carga con un modelo
#               multifásico vertical: con gradiente constante el error de
#               diseño se vuelve grande
#     f > 5 %   obligatorio incorporar separador o manejador de gas en el
#               aparejo: el rendimiento hidráulico del equipo convencional
#               se deteriora demasiado
#
#   RELACIÓN gas libre / líquido en la admisión
#     r > 0.1   la bomba empieza a degradarse: entrega menos altura que su
#               curva de agua  (equivale a f > 0.0909)
#     r > 1.0   bloqueo total por gas (gas lock): deja de bombear líquido
#               (equivale a f > 0.50)
# ---------------------------------------------------------------------------

#: Gas despreciable: por debajo, el diseño monofásico es válido.
GAS_FRACTION_NEGLIGIBLE = 0.01
#: Por encima, hace falta separador o manejador de gas.
GAS_FRACTION_SEPARATOR_REQUIRED = 0.05
#: Relación gas/líquido a la que la bomba empieza a perder altura.
GAS_RATIO_DEGRADATION_START = 0.10
#: Relación gas/líquido que produce bloqueo total.
GAS_RATIO_GAS_LOCK = 1.00

#: **FRACCIÓN** de gas libre a la entrada de la bomba, ya descontado el venteo
#: y el separador, por encima de la cual el diseño BES deja de ser viable.
#:
#: OJO — no confundir con ``GAS_RATIO_DEGRADATION_START``, que también vale
#: 0.10 pero es una **relación** gas/líquido (equivale a f = 9.09 %). Son dos
#: criterios distintos que por casualidad comparten el número:
#:
#:   GAS_RATIO_DEGRADATION_START   r > 0.10  la bomba entrega menos altura
#:   GAS_FRACTION_PUMP_LIMIT       f > 0.10  la bomba directamente no sirve
#:
#: Es el valor por defecto de ``DesignObjectives.max_gip``, que lo hace
#: configurable por pozo.
GAS_FRACTION_PUMP_LIMIT = 0.10

#: Fracción de vacío máxima en la ADMISIÓN que admite cada configuración de
#: aparejo, según la comparación de capacidades de manejo de gas que publica
#: Takács (2018), Fig. 4.25, pág. 195.
#:
#: Son **lecturas de las barras de esa figura**, no valores tabulados en el
#: texto: la página consigna en forma expresa únicamente el 50 % de la bomba
#: GasMaster. Se los usa como órdenes de magnitud, y así se declaran.
#:
#: A diferencia de ``GAS_FRACTION_PUMP_LIMIT`` —que es un criterio propio de
#: esta herramienta— estos valores sí tienen fuente, y son la **capacidad de
#: la tecnología**. Por eso la escalera compara cada escalón contra el menor
#: de los dos: el usuario puede pedir algo más estricto que el equipo, pero no
#: más laxo.
#:
#: El valor sin separador depende del tipo de etapa, que el catálogo no
#: publica: se adopta el de flujo radial, que es el conservador.
GAS_VOID_LIMIT_RADIAL = 0.20
GAS_VOID_LIMIT_MIXED_FLOW = 0.40
GAS_VOID_LIMIT_GASMASTER = 0.50
GAS_VOID_LIMIT_WITH_SEPARATOR = 0.80
GAS_VOID_LIMIT_TANDEM = 0.95

#: Techo de la tecnología: por encima de esto no hay configuración de bombeo
#: electrosumergible que lo resuelva (Takács, 2018, Fig. 4.25, pág. 195).
GAS_VOID_LIMIT_ESP = GAS_VOID_LIMIT_TANDEM

#: Capacidad de cada escalón de la escalera, en el mismo orden que
#: :data:`GAS_STRATEGY_LADDER`. El escalón del AGH no figura acá porque su
#: límite lo publica el propio equipo (``max_gvf`` del catálogo).
GAS_VOID_LIMIT_POR_ESCALON = {
    "ninguno": GAS_VOID_LIMIT_RADIAL,
    "simple": GAS_VOID_LIMIT_WITH_SEPARATOR,
    "tandem": GAS_VOID_LIMIT_TANDEM,
}

#: Eficiencia de separación que se supone cuando el modelo elegido no la
#: publica en el catálogo. **Hoy es siempre**: REDA no declara la eficiencia de
#: separación de ninguno de sus doce equipos (se revisaron las págs. 390-399
#: completas), y Centrilift y Wood Group tampoco. Por eso ``max_efficiency``
#: está en ``null`` en todas las entradas.
#:
#: Es un supuesto propio de esta herramienta —no sale de ninguna hoja de datos—
#: y por eso se declara en el veredicto de viabilidad en vez de aplicarse en
#: silencio. Los 0.90 / 0.97 que figuraban acá eran del catálogo ChampionX que
#: se retiró del proyecto: NO volver a ponerlos, eran de otro fabricante y de
#: otro diseño de equipo.
SEPARATOR_DEFAULT_EFFICIENCY = 0.75


def ratio_to_fraction(r: float) -> float:
    """Relación gas/líquido → fracción de gas del volumen total. ``f = r/(1+r)``."""
    return r / (1.0 + r) if r >= 0 else 0.0


def fraction_to_ratio(f: float) -> float:
    """Fracción de gas del volumen total → relación gas/líquido. ``r = f/(1−f)``."""
    if f <= 0.0:
        return 0.0
    return float("inf") if f >= 1.0 else f / (1.0 - f)


def free_gas_fraction_detail(
    fluid: "Fluid",
    pressure: float,
    temp_f: float,
) -> dict:
    """El balance de gas libre **con todos sus intermedios**, para poder mostrarlo.

    Es la misma cuenta que :func:`free_gas_fraction_at_intake` —de hecho aquélla
    llama a ésta y se queda con un solo número—, pero devolviendo cada término
    por separado. Existe porque el reporte tiene que poder mostrar de dónde sale
    la fracción de gas: con el número solo, el lector no puede verificar nada.

    Los intermedios son los que el propio balance necesita:

        Rs      gas que sigue disuelto        [scf/STB]   Standing, acotado al GOR
        GOR−Rs  gas libre                     [scf/STB]
        z       factor de compresibilidad     [-]         Dranchuk & Abou-Kassem
        Bg      factor volumétrico del gas    [bbl/scf]
        Bo, Bw  factores volumétricos         [bbl/STB]

    y de ellos los tres volúmenes sobre la base de un STB de líquido de
    superficie, cuya suma es el denominador de la fracción.

    Args:
        fluid: PVT y composición del fluido.
        pressure: Presión en el punto de evaluación [psia]. Debe ser > 0.
        temp_f: Temperatura en el punto de evaluación [°F].

    Returns:
        dict con ``rs``, ``free_gas_scf``, ``z``, ``bg``, ``bo``, ``bw``,
        ``v_oil``, ``v_water``, ``v_gas``, ``v_total``, ``fraction`` y
        ``ratio``.

    Raises:
        ValueError: Si la presión es <= 0.
    """
    if pressure <= 0:
        raise ValueError(f"pressure must be > 0, got {pressure}")

    pb = fluid.bubble_point_pressure
    gor = fluid.gor
    wc = fluid.water_cut

    rs = min(
        standing_rs(pressure, temp_f, fluid.oil_api, fluid.gas_sg, pb) if pb > 0 else gor,
        gor,
    )
    free_gas = max(gor - rs, 0.0)

    z = gas_z_factor(pressure, temp_f, fluid.gas_sg)
    bg = gas_bg(pressure, temp_f, z)
    bo = standing_bo(rs, temp_f, fluid.oil_api, fluid.gas_sg)
    bw = water_bw(pressure, temp_f)

    v_oil = (1.0 - wc) * bo
    v_water = wc * bw
    v_gas = (1.0 - wc) * free_gas * bg
    v_total = v_oil + v_water + v_gas
    fraction = v_gas / v_total if v_total > 0.0 else 0.0

    return {
        "rs": rs, "free_gas_scf": free_gas, "z": z, "bg": bg, "bo": bo, "bw": bw,
        "v_oil": v_oil, "v_water": v_water, "v_gas": v_gas, "v_total": v_total,
        "fraction": fraction, "ratio": fraction_to_ratio(fraction),
        "pressure": pressure, "temp_f": temp_f,
        "gor": gor, "water_cut": wc,
    }


def free_gas_fraction_at_intake(
    fluid: "Fluid",
    pressure: float,
    temp_f: float,
) -> float:
    """Fracción volumétrica de gas libre en la corriente producida, a P y T.

    Es un **balance volumétrico** sobre un STB de líquido de superficie,
    llevado a condiciones de fondo::

        f_g = V_gas / (V_petróleo + V_agua + V_gas)

    con ``V_gas = (1 − WC)·(GOR − Rs)·Bg``, ``V_petróleo = (1 − WC)·Bo`` y
    ``V_agua = WC·Bw``. El gas libre es la diferencia entre el gas que produce
    el pozo (GOR) y el que sigue disuelto (Rs). Rs se acota al GOR total: no
    puede salir de solución más gas del que el pozo produce.

    Evaluada **en la admisión de la bomba**, ésta es la magnitud que gobierna
    todas las decisiones que vienen después: el riesgo de bloqueo por gas, el
    dimensionamiento del separador y —por encima de
    ``DesignObjectives.gas_fraction_pc_threshold``— el cambio de la fricción
    monofásica de Hazen-Williams a Poettmann-Carpenter en
    :func:`bes.core.tdh.calculate_tdh`.

    Args:
        fluid: PVT y composición del fluido.
        pressure: Presión en el punto de evaluación [psia]. Debe ser > 0.
        temp_f: Temperatura en el punto de evaluación [°F].

    Returns:
        Fracción volumétrica de gas libre [0–1]. Cero con crudo muerto
        (GOR = 0), con 100 % de agua, o cuando todo el gas sigue en solución.

    Raises:
        ValueError: Si la presión es <= 0.
    """
    return free_gas_fraction_detail(fluid, pressure, temp_f)["fraction"]


def gas_ingestion_percentage(
    free_gas_at_intake: float,
    gas_vented: float,
    separator_efficiency: float = 0.0,
) -> float:
    """Qué parte del gas libre de la admisión entra realmente a la bomba.

    Parte del gas se puede ventear por el anular antes de llegar a la bomba, y
    un separador de fondo retira otra parte de lo que queda::

        sin separador:  GIP = 1 − gas_venteado / gas_libre_en_admisión
        con separador:  además se le quita la fracción que retira el separador

    Args:
        free_gas_at_intake: Volumen total de gas libre a la profundidad de la
            bomba [cualquier unidad].
        gas_vented: Volumen de gas libre desviado fuera de la bomba [misma
            unidad].
        separator_efficiency: Eficiencia de separación del separador de fondo
            [0–1]. 0 = sin separador.

    Returns:
        Fracción de gas que ingresa a la bomba [0–1].
    """
    if free_gas_at_intake <= 0.0:
        return 0.0

    gip = 1.0 - gas_vented / free_gas_at_intake
    gip = max(0.0, min(1.0, gip))

    if separator_efficiency > 0.0:
        gip = gip * (1.0 - separator_efficiency)

    return max(0.0, min(1.0, gip))


#: Potencia que consume el separador de gas de fondo [hp]. Va montado en el
#: mismo eje, entre el sello y la bomba, así que su consumo **se suma al de la
#: bomba antes de elegir el motor**: el motor mueve las dos cosas.
#:
#: **Es el respaldo, ya no el camino normal.** Desde que el catálogo de REDA
#: está digitalizado, el consumo sale **del modelo elegido** (campo ``hp`` de
#: ``gas_handlers.json``, publicado a 60 Hz): 3 hp el VGSA D20-60, 6 el S20-90,
#: 14 el S70-150. Estos 2 hp quedan para los modelos que el fabricante no
#: publica —los rotativos ARS, CRS-ES y DRS-ES, que sólo figuran en las tablas
#: de armado— y son del orden de lo que consume un separador de tamaño BES.
#:
#: La consulta va por :func:`gas_handler_hp`, nunca leyendo esta constante
#: directamente: si se lee suelta, el consumo publicado se pierde.
GAS_SEPARATOR_HP = 2.0


def total_intake_rate(liquid_rate_bpd: float, free_gas_fraction: float) -> float:
    """Caudal TOTAL —líquido más gas libre— que ve el manejador de gas [bpd].

    El separador se monta debajo de la bomba, así que por él pasa la mezcla
    entera. REDA declara su rango de aplicación exactamente así: *"total liquid
    and gas operating range, B/D at 60 Hz"* (ESP Catalog, pág. 392). Consultar
    el catálogo con el caudal de líquido solo subestima lo que el equipo tiene
    que manejar y descarta separadores que en realidad califican::

        q_total = q_líquido / (1 − f_gas)

    Con 63 % de gas libre, 1 227 bpd de líquido son 3 316 bpd de mezcla: el
    primero cae fuera del rango 2 000–6 000 del VGSA D20-60 y el segundo entra
    cómodo. La diferencia decide si el pozo se puede diseñar o no.

    El caudal de líquido que se pasa es el de **superficie**, que es la
    convención del resto del selector; a presión de admisión el líquido está
    algo expandido (Bo, Bw), así que el total resultante es una cota inferior.

    Args:
        liquid_rate_bpd: Caudal de líquido [bpd].
        free_gas_fraction: Fracción volumétrica de gas libre en la admisión
            [0–1], la que devuelve :func:`free_gas_fraction_at_intake`.

    Returns:
        Caudal total de mezcla en la admisión [bpd]. Con ``f_gas`` fuera de
        [0, 1) devuelve el caudal de líquido sin tocar.
    """
    f = free_gas_fraction
    if not (0.0 <= f < 1.0):
        return liquid_rate_bpd
    return liquid_rate_bpd / (1.0 - f)


def gas_handler_hp(handler: dict | None) -> float:
    """Consumo publicado del manejador de gas, a su frecuencia base [hp].

    El separador va montado en el mismo eje que la bomba, así que su consumo lo
    entrega el mismo motor y **se suma antes de dimensionarlo**.

    Args:
        handler: Entrada del catálogo (``gas_handlers.json``), o ``None``.

    Returns:
        El ``hp`` que publica el fabricante para ese modelo; si no lo publica
        —o si no hay equipo—, :data:`GAS_SEPARATOR_HP` como respaldo.
    """
    if not handler:
        return GAS_SEPARATOR_HP
    hp = handler.get("hp")
    return float(hp) if hp else GAS_SEPARATOR_HP

#: Frecuencia a la que se entiende publicado ``GAS_SEPARATOR_HP`` [Hz].
#:
#: Los fabricantes publican el consumo de estos dispositivos **a una frecuencia
#: fija**, 50 o 60 Hz (Takács §4.4.5). Los catálogos del proyecto son de 60 Hz,
#: así que ese es el valor base. Es un **supuesto declarado**: si mañana el
#: catálogo publica el consumo con su propia frecuencia, este número se
#: reemplaza por el del modelo.
GAS_SEPARATOR_BASE_FREQUENCY_HZ = 60.0


def gas_handler_power_at_frequency(
    base_hp: float,
    frequency_hz: float,
    base_frequency_hz: float = GAS_SEPARATOR_BASE_FREQUENCY_HZ,
) -> float:
    """Potencia del manejador de gas a la frecuencia de operación [hp].

    El separador va en el mismo eje que la bomba, así que gira a la misma
    velocidad y **su consumo escala con la tercera potencia de la frecuencia**,
    igual que el de cualquier máquina rotante::

        BHP = BHP_base · (f / f_base)³

    Sin esta corrección un pozo a 50 Hz cargaría al motor con el consumo de
    60 Hz: 2 hp en vez de 1.16, un 72 % de más sobre ese término. Es la misma
    ley de afinidad con que ``bes.core.affinity.pump_at_frequency`` escala la
    curva de la bomba — dejar una escalada y la otra no era incoherente.

    Args:
        base_hp: Consumo publicado por el fabricante [hp].
        frequency_hz: Frecuencia de operación [Hz]. Debe ser > 0.
        base_frequency_hz: Frecuencia a la que está publicado *base_hp* [Hz].

    Returns:
        Consumo a la frecuencia de operación [hp].

    Raises:
        ValueError: Si alguna frecuencia no es positiva.

    Referencia:
        Takács, G. (2018). *Electrical Submersible Pumps Manual*, 2.ª ed.,
        §4.4.5, ec. 4.31.
    """
    if frequency_hz <= 0:
        raise ValueError(f"frequency_hz must be > 0, got {frequency_hz}")
    if base_frequency_hz <= 0:
        raise ValueError(
            f"base_frequency_hz must be > 0, got {base_frequency_hz}"
        )
    return base_hp * (frequency_hz / base_frequency_hz) ** 3


def tandem_separation_efficiency(efficiencies: "Sequence[float]") -> float:
    """Eficiencia de varios separadores **en serie**.

    Cada separador trabaja sobre lo que le deja el anterior, así que lo que se
    multiplica es el gas que **pasa**, no el que se retira::

        η_total = 1 − Π (1 − ηᵢ)

    Con un rotativo de 90 % seguido de un vórtex de 97 % el tándem retira
    99.7 %, no el 93.5 % que daría promediarlos ni el 187 % de sumarlos.

    Takács (pág. 195) señala que el tándem se arma con separadores de **tipos
    distintos** —no dos iguales apilados— porque cada tipo rinde mejor en un
    rango distinto de fracción de vacío.

    Args:
        efficiencies: Eficiencias individuales, cada una en [0, 1].

    Returns:
        Eficiencia combinada [0–1]. Con la lista vacía devuelve 0.

    Raises:
        ValueError: Si alguna eficiencia cae fuera de [0, 1].

    Referencia:
        Takács, G. (2018), §4.4.5: *"The greatest relative amounts of free gas
        can be handled by a tandem RGS, composed of different types of
        separators."*
    """
    pasa = 1.0
    for eta in efficiencies:
        if not (0.0 <= eta <= 1.0):
            raise ValueError(f"cada eficiencia debe estar en [0, 1], got {eta}")
        pasa *= (1.0 - eta)
    return 1.0 - pasa


def _tablas_4K() -> dict:
    """Carga perezosa de la digitalización del Apéndice 4K."""
    global _4K
    if _4K is None:
        _4K = json.loads(_4K_PATH.read_text(encoding="utf-8"))
    return _4K


def _interp_1d(xs: Sequence[float], ys: Sequence[float], x: float) -> float:
    """Interpolación lineal con acote en los bordes. No extrapola."""
    if x <= xs[0]:
        return float(ys[0])
    if x >= xs[-1]:
        return float(ys[-1])
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return float(ys[i] + t * (ys[i + 1] - ys[i]))
    return float(ys[-1])


def _interp_tabla_4K(filas: Sequence[float], valores: Sequence[Sequence[float]],
                     fila: float, water_cut_pct: float) -> float:
    """Interpola una tabla del 4K en su índice de fila y en el corte de agua."""
    cols = _tablas_4K()["water_cut_pct"]
    por_fila = [_interp_1d(cols, v, water_cut_pct) for v in valores]
    # Las filas de la Tabla 2/3 vienen descendentes (1.0 → 0.0); _interp_1d las
    # necesita ascendentes.
    if filas[0] > filas[-1]:
        return _interp_1d(list(reversed(filas)), list(reversed(por_fila)), fila)
    return _interp_1d(filas, por_fila, fila)


def approach_velocity(intake_flow_bpd: float, casing_id_in: float,
                      seal_od_in: float) -> float:
    """Velocidad de aproximación del fluido a la bomba — Va del Apéndice 4K.

    Es el caudal de admisión dividido por el área anular que queda entre el
    diámetro exterior del sello y el diámetro interior del casing::

        A  = (π/4) · (ID_casing² − OD_sello²) / 144        [ft²]
        Va = q · 5.615 / 86400 / A                          [ft/s]

    La Tabla 1 del apéndice tabula esta misma magnitud por caudal, serie de
    bomba y sello y tamaño de casing; su propia nota declara que está basada en
    «the area between the O.D. of the Seal Section and the I.D. of casings», que
    es lo que se calcula acá. Se prefiere la geometría a la tabla porque cubre
    cualquier combinación y no sólo las tabuladas.

    Args:
        intake_flow_bpd: Caudal total (líquido más gas) en la admisión [bbl/d].
        casing_id_in: Diámetro interior del casing [in].
        seal_od_in: Diámetro exterior del sello [in].

    Returns:
        Velocidad de aproximación [ft/s].

    Raises:
        ValueError: Si el área anular no resulta positiva.

    Referencia:
        Brown Vol. 2b, Apéndice 4K (Rhoads), Tabla 1, pág. 345.
    """
    area_ft2 = math.pi / 4.0 * (casing_id_in ** 2 - seal_od_in ** 2) / 144.0
    if area_ft2 <= 0.0:
        raise ValueError(
            f"El sello (OD {seal_od_in} in) no deja área anular dentro del "
            f"casing (ID {casing_id_in} in)."
        )
    return intake_flow_bpd * _BBL_TO_FT3 / 86400.0 / area_ft2


def free_gas_thru_pump(
    approach_velocity_ft_s: float,
    has_separator: bool,
    pi_over_pbb: float | None = None,
    liquid_viscosity_cp: float | None = None,
    water_cut: float = 0.0,
) -> dict:
    """Porcentaje del gas libre que atraviesa la bomba — método de Rhoads.

    Es el procedimiento del Apéndice 4K, y responde la pregunta que el resto
    del módulo venía resolviendo con criterios propios: de todo el gas libre
    que llega a la admisión, **cuánto entra a la bomba y cuánto sube por el
    anular**. Parte de la velocidad de aproximación y corrige por dos efectos
    de segundo orden::

        sin separador:  pct = 90.5 − ((16 − Va)/16)² · 90
        con separador:  pct = 45.5 − ((16 − Va)/16)² · 45

        pct_neto = pct − efecto_burbuja + efecto_viscosidad

    El separador no entra como una eficiencia que se compone: **entra cambiando
    la curva**. A velocidad máxima el gas pasante cae del 90 % al 45 %, que es
    la única cuantificación del efecto de un separador que publica el libro.

    Los dos efectos de segundo orden se leen de las Tablas 3 y 4 del apéndice.
    El de tamaño de burbuja se **resta** —son los porcentajes del gas que *no*
    pasa— y el de viscosidad se **suma**. Ambos se acotan a los bordes de sus
    tablas y ninguno extrapola.

    Args:
        approach_velocity_ft_s: Velocidad de aproximación Va [ft/s], de
            :func:`approach_velocity`.
        has_separator: Si el aparejo lleva separador de gas.
        pi_over_pbb: Relación entre la presión de admisión y la de burbuja
            [-]. ``None`` omite la corrección por tamaño de burbuja.
        liquid_viscosity_cp: Viscosidad del petróleo muerto a temperatura de
            admisión [cp]. ``None`` omite la corrección por viscosidad. La
            tabla cubre de 0.7 a 16 cp.
        water_cut: Corte de agua [0–1].

    Returns:
        dict con ``pct_base``, ``pct_bubble``, ``pct_viscosity``, ``pct_net``
        y ``fraction`` (el neto como fracción [0–1]).

    Raises:
        ValueError: Si *water_cut* cae fuera de [0, 1].

    Referencia:
        Brown Vol. 2b, Apéndice 4K — «Method for estimating the percent of free
        gas that will go thru a pump», by Don Rhoads, págs. 345-347.
    """
    if not (0.0 <= water_cut <= 1.0):
        raise ValueError(f"water_cut must be in [0, 1], got {water_cut}")

    t = _tablas_4K()
    vel = t["velocidad"]
    va_max = float(vel["_va_max_ft_s"])
    base = float(vel["_base_con_separador" if has_separator
                     else "_base_sin_separador"])
    ajuste = float(vel["_ajuste"])

    va = min(max(0.0, approach_velocity_ft_s), va_max)
    pct_base = base + ajuste - ((va_max - va) / va_max) ** 2 * base

    wc_pct = water_cut * 100.0

    pct_bubble = 0.0
    if pi_over_pbb is not None:
        t3 = t["tabla_3_efecto_burbuja"]
        pct_bubble = _interp_tabla_4K(
            t3["pi_over_pbb"], t3["valores"], float(pi_over_pbb), wc_pct
        )

    pct_visc = 0.0
    if liquid_viscosity_cp is not None:
        t4 = t["tabla_4_efecto_viscosidad"]
        pct_visc = _interp_tabla_4K(
            t4["viscosidad_cp"], t4["valores"], float(liquid_viscosity_cp), wc_pct
        )

    pct_net = min(max(0.0, pct_base - pct_bubble + pct_visc), 100.0)
    return {
        "pct_base": pct_base,
        "pct_bubble": pct_bubble,
        "pct_viscosity": pct_visc,
        "pct_net": pct_net,
        "fraction": pct_net / 100.0,
        "approach_velocity_ft_s": approach_velocity_ft_s,
        "has_separator": has_separator,
    }


def separator_outlet_fraction(free_gas_fraction: float, efficiency: float) -> float:
    """Fracción de gas que QUEDA tras separar *efficiency* del gas libre.

    **No es ``f × (1 − η)``.** El separador saca gas y deja el líquido, así que
    lo que escala linealmente es la **relación** gas/líquido, no la fracción::

        r  = f / (1 − f)
        r' = r · (1 − η)          ← acá sí es proporcional
        f' = r' / (1 + r')

    Tratar la fracción como si fuera relación subestima el gas remanente, y el
    error crece con el gas: con f = 65 % y η = 75 %, la cuenta correcta da
    31.6 % y la incorrecta 16.2 % — casi el doble. Un pozo inviable pasaría
    el filtro. Es la misma confusión fracción/relación que documenta
    ``.claude/rules/domain.md``.

    Args:
        free_gas_fraction: Fracción volumétrica de gas libre antes del
            separador [0–1].
        efficiency: Fracción del gas libre que el separador desvía [0–1].

    Returns:
        Fracción volumétrica de gas libre después del separador [0–1].

    Raises:
        ValueError: Si *efficiency* cae fuera de [0, 1].
    """
    if not (0.0 <= efficiency <= 1.0):
        raise ValueError(f"efficiency must be in [0, 1], got {efficiency}")

    f = min(max(0.0, free_gas_fraction), 1.0)
    if f <= 0.0 or efficiency >= 1.0:
        return 0.0

    r_out = fraction_to_ratio(f) * (1.0 - efficiency)
    return ratio_to_fraction(r_out)


def required_separator_efficiency(
    free_gas_fraction: float, max_gip: float
) -> float | None:
    """Eficiencia mínima que haría falta para bajar de *max_gip*.

    Se despeja de :func:`separator_outlet_fraction`::

        η = 1 − r_objetivo / r_entrada

    Returns:
        La eficiencia necesaria [0–1], o ``None`` si el pozo ya cumple sin
        separador. Puede dar > 1, que es la forma de decir «con ningún
        separador alcanza».
    """
    f = min(max(0.0, free_gas_fraction), 1.0)
    if f <= max_gip:
        return None
    r_in = fraction_to_ratio(f)
    if r_in <= 0:
        return None
    return 1.0 - fraction_to_ratio(max_gip) / r_in


#: Los cuatro escalones de manejo de gas, de menor a mayor capacidad.
#: Espeja el orden de la Fig. 4.25 de Takács (pág. 195), que compara el rango
#: de aplicación de cada solución contra la fracción de vacío en la admisión.
#:
#: El cuarto —``"agh"``— **no separa gas**, y por eso va aparte de los otros
#: tres: el manejador avanzado (REDA AGH, Takács §4.4.6 «gas handlers»)
#: homogeneiza la mezcla para que la bomba la pueda bombear con gas adentro.
#: No baja ``f_pump``: **sube la tolerancia** de ``max_gip`` a ``max_gvf``.
GAS_STRATEGY_LADDER = ("ninguno", "simple", "tandem", "agh")

#: Relación gas/líquido *in situ* hasta la que hay evidencia publicada de que un
#: separador rotativo asegura desempeño ideal de la bomba (Takács pág. 186,
#: ref. [41]: *"the use of such rotary separators ensures ideal pump performance
#: for in situ gas-liquid ratios as high as 0.6"*).
#:
#: Es **relación**, no fracción: 0.6 de relación equivale a 37.5 % de fracción.
#: Por encima de eso el cálculo sigue corriendo pero se avisa, porque se está
#: extrapolando fuera del rango documentado.
RGS_DOCUMENTED_RATIO_LIMIT = 0.6


#: Cómo se llama cada escalón en el reporte. La clave interna es corta porque
#: viaja por la API; el rótulo es el que lee una persona.
_ESCALON_ROTULO = {
    "ninguno": "sin separador",
    "simple": "un separador",
    "tandem": "separador en tándem",
    "agh": "manejador avanzado de gas",
}


def _traza_escalera(ladder: list[dict], f_vent: float,
                    elegido: dict | None) -> list[dict]:
    """La escalera escrita como fórmulas, para el reporte.

    Por cada escalón evaluado emite sus **dos condiciones**, que es lo que hay
    que poder auditar: cuál se cumplió, cuál no, y contra qué valor se comparó
    cada una. Un escalón sirve sólo si pasa las dos, y el remedio de cada falla
    es distinto —si falla la capacidad, ninguna mejora de eficiencia de
    separación lo resuelve—, así que mostrarlas juntas como un único «no
    alcanza» perdería la información útil.

    Se corta en el escalón elegido: los que están por encima no se evaluaron
    para decidir, y publicarlos sugeriría que el aparejo los consideró.

    Args:
        ladder: Los escalones evaluados, tal como los arma
            :func:`select_gas_handling_strategy`.
        f_vent: Gas libre que llega a la admisión, ya descontado el venteo.
        elegido: El escalón que resolvió el pozo, o ``None`` si ninguno.

    Returns:
        Lista de dicts de :class:`bes.core.formulas.Formula`.
    """
    from bes.core.formulas import FormulaTrace

    trace = FormulaTrace()
    for e in ladder:
        rotulo = _ESCALON_ROTULO.get(e["strategy"], e["strategy"])
        cap_ok = e["cumple_capacidad"]
        trace.add(
            "gas_capacidad_configuracion",
            {"f_admisión": f_vent, "capacidad": e["capacidad"]},
            e["capacidad"],
            substitute=False,
            label=f"Escalón «{rotulo}» — condición 1: capacidad",
            context=f"{f_vent:.2%} de gas en la admisión contra "
                    f"{e['capacidad']:.0%} que admite esta configuración: "
                    + ("CUMPLE." if cap_ok else
                       "NO CUMPLE. El gas que llega supera lo que la "
                       "configuración soporta, y ningún separador más eficiente "
                       "lo arregla — hay que subir de configuración."),
        )
        if e["f_pump"] is None:
            trace.add(
                "gas_criterio_bomba",
                {"f_bomba": 0.0, "max_gip": e["tolerancia"]}, e["tolerancia"],
                substitute=False,
                label=f"Escalón «{rotulo}» — condición 2: no evaluable",
                context="El catálogo no ofrece equipo que entre en este pozo "
                        "para esta configuración, así que la condición no se "
                        "puede evaluar.",
            )
        else:
            # Cuánto gas saca el separador, si hay separador. Va entre las dos
            # condiciones porque es lo que las conecta: la 1 mira el gas que
            # llega y la 2 el que queda, y esta cuenta es el paso del uno al
            # otro. El escalón del manejador avanzado NO separa, así que ahí no
            # hay reducción que mostrar.
            eta = e.get("efficiency")
            if eta and e["strategy"] != "agh":
                r_in = fraction_to_ratio(f_vent)
                trace.add(
                    "gas_separador_salida",
                    {"r": r_in, "η": eta, "r'": r_in * (1.0 - eta)},
                    e["f_pump"],
                    label=f"Escalón «{rotulo}» — gas remanente tras separar",
                    context=f"El separador retira el {eta:.1%} del gas libre. "
                            f"La relación cae de {r_in:.4f} a "
                            f"{r_in * (1 - eta):.4f}, y la fracción de "
                            f"{f_vent:.2%} a {e['f_pump']:.2%}. Aplicar el "
                            f"factor sobre la FRACCIÓN daría "
                            f"{f_vent * (1 - eta):.2%}, que es el error más "
                            f"común del procedimiento.",
                )
            crit_ok = e["cumple_criterio"]
            trace.add(
                "gas_criterio_bomba",
                {"f_bomba": e["f_pump"], "max_gip": e["tolerancia"]},
                e["f_pump"],
                label=f"Escalón «{rotulo}» — condición 2: máximo admisible",
                context=f"{e['f_pump']:.2%} de gas entra a la bomba contra "
                        f"{e['tolerancia']:.1%} admisible: "
                        + ("CUMPLE." if crit_ok else "NO CUMPLE.")
                        + (f" El escalón resuelve el pozo."
                           if e.get("alcanza") else ""),
                applies=bool(e.get("alcanza")),
            )
        if e.get("alcanza"):
            break
    return trace.as_list()


def select_gas_handling_strategy(
    free_gas_fraction_intake: float,
    single_efficiency: float | None = None,
    tandem_efficiencies: "Sequence[float] | None" = None,
    vent_fraction: float = 0.0,
    max_gip: float = GAS_FRACTION_PUMP_LIMIT,
    single_model: str | None = None,
    tandem_models: "Sequence[str] | None" = None,
    agh_max_gvf: float | None = None,
    agh_model: str | None = None,
) -> dict:
    """Elige el manejo de gas mínimo que hace viable la BES, o la descarta.

    Sube por la escalera y **se queda en el primer escalón que alcanza**, para
    no instalar equipo de más::

        f_admisión → venteo por el anular
                        ↓
            ¿alcanza sin separador?      → "ninguno"
                        ↓ no
            ¿alcanza con uno solo?       → "simple"
                        ↓ no
            ¿alcanza con el tándem?      → "tandem"
                        ↓ no
            ¿un manejador AGH lo tolera? → "agh"
                        ↓ no
            NO VIABLE → cambiar de método de levantamiento

    **Los tres primeros escalones bajan el gas; el cuarto sube la tolerancia.**
    Un separador retira gas y por lo tanto reduce ``f_pump``. El manejador
    avanzado (AGH) no retira nada: acondiciona la mezcla para que la bomba pueda
    bombearla con el gas adentro, hasta la fracción de vacío que publique el
    fabricante (REDA declara 45 % de GVF, pág. 393). Por eso su escalón se
    evalúa contra ``agh_max_gvf`` y no contra ``max_gip``, y por eso se apila
    **sobre** la separación que ya se haya conseguido: el propio catálogo dice
    que el AGH *«can also be installed in series above rotary or vortex-type gas
    separators»*.

    **El último escalón es el que importa.** Si ni con el AGH sobre el tándem el
    gas queda por debajo de lo que el equipo tolera, la bomba centrífuga no
    converge y no hay equipo que lo arregle: corresponde evaluar otro método de
    levantamiento artificial. Es el techo de la tecnología BES para gas
    (Takács, Fig. 4.25), así que fallar ahí es fallar del todo.

    Todas las reducciones se aplican **sobre la relación** gas/líquido, no
    sobre la fracción — ver :func:`separator_outlet_fraction`.

    Args:
        free_gas_fraction_intake: Fracción de gas libre en la admisión, antes
            de cualquier separación [0–1].
        single_efficiency: Eficiencia del separador simple [0–1]. ``None`` = no
            hay separador disponible en el catálogo.
        tandem_efficiencies: Eficiencias de los separadores del tándem. ``None``
            o menos de dos elementos = no se evalúa el escalón de tándem.
        vent_fraction: Fracción del gas libre venteada por el anular antes de
            llegar al separador [0–1].
        max_gip: Fracción máxima de gas admisible en la bomba.
        single_model: Modelo del separador simple, para el texto del veredicto.
        tandem_models: Modelos del tándem, para el texto del veredicto.
        agh_max_gvf: Fracción de vacío máxima que tolera el manejador avanzado
            disponible [0–1]. ``None`` = el catálogo no tiene uno que entre en
            este pozo, y el escalón no se ofrece.
        agh_model: Modelo del manejador avanzado, para el texto del veredicto.

    Returns:
        dict con:
          - ``strategy``    ``"ninguno"`` / ``"simple"`` / ``"tandem"`` /
                            ``"no_viable"``
          - ``viable``      bool
          - ``n_separators``  cuántos separadores lleva el aparejo
          - ``efficiency``  eficiencia combinada aplicada [0–1]
          - ``f_intake`` / ``f_after_vent`` / ``f_pump``  las fracciones
          - ``ladder``      la evaluación de cada escalón, para mostrar
          - ``verdict``     el texto
          - ``switch_lift_method``  bool — ``True`` sólo si hay que cambiar de
            método de levantamiento

    Raises:
        ValueError: Si *max_gip* cae fuera de [0, 1].
    """
    if not (0.0 <= max_gip <= 1.0):
        raise ValueError(f"max_gip must be in [0, 1], got {max_gip}")

    f_intake = min(max(0.0, free_gas_fraction_intake), 1.0)
    f_vent = separator_outlet_fraction(f_intake, vent_fraction)

    tandem = list(tandem_efficiencies or [])
    eta_tandem = (
        tandem_separation_efficiency(tandem) if len(tandem) >= 2 else None
    )

    # Los tres escalones, evaluados siempre: el veredicto muestra la escalera
    # entera aunque se detenga en el primero, porque saber cuánto margen sobra
    # (o falta) es parte de la decisión.
    escalones = [
        ("ninguno", 0, None, f_vent),
        ("simple", 1, single_efficiency,
         separator_outlet_fraction(f_vent, single_efficiency)
         if single_efficiency is not None else None),
        ("tandem", len(tandem), eta_tandem,
         separator_outlet_fraction(f_vent, eta_tandem)
         if eta_tandem is not None else None),
    ]
    # Cada escalón responde DOS preguntas distintas, y tienen que dar bien las
    # dos. Se miden en puntos distintos del aparejo y no se pueden mezclar:
    #
    #   1. ¿La configuración soporta este pozo?
    #      Compara el gas que LLEGA a la admisión contra la capacidad de la
    #      configuración — 20 % sin separador, 80 % con uno, 95 % en tándem
    #      (Takács, Fig. 4.25, pág. 195). Es la tecnología.
    #
    #   2. ¿El gas que entra a la bomba cumple el criterio de diseño?
    #      Compara el gas que queda DESPUÉS de separar contra ``max_gip``. Es
    #      la decisión del usuario.
    #
    # Confundirlas fue un error real: los porcentajes de la Fig. 4.25 están
    # medidos en la admisión, no aguas abajo del separador.
    ladder = []
    for nombre, n, eta, f in escalones:
        capacidad = GAS_VOID_LIMIT_POR_ESCALON[nombre]
        cumple_capacidad = f_vent <= capacidad
        cumple_criterio = f is not None and f <= max_gip
        ladder.append({
            "strategy": nombre, "n_separators": n, "efficiency": eta,
            "f_pump": f,
            "capacidad": capacidad,
            "tolerancia": max_gip,
            "cumple_capacidad": cumple_capacidad,
            "cumple_criterio": cumple_criterio,
            "alcanza": cumple_capacidad and cumple_criterio,
        })

    # Cuarto escalón: el manejador avanzado. NO baja f_pump — lo deja donde lo
    # dejó la mejor separación conseguida— y en cambio sube la tolerancia de
    # max_gip a la fracción de vacío que el fabricante declara para el equipo.
    f_mejor = next(
        (e["f_pump"] for e in reversed(ladder) if e["f_pump"] is not None), f_vent,
    )
    n_sep_mejor = next(
        (e["n_separators"] for e in reversed(ladder) if e["f_pump"] is not None), 0,
    )
    eta_mejor = next(
        (e["efficiency"] for e in reversed(ladder) if e["f_pump"] is not None), None,
    )
    # El manejador sólo puede SUBIR la tolerancia por encima del límite estándar
    # de la tecnología. Si el usuario apretó ``max_gip`` por debajo de
    # GAS_FRACTION_PUMP_LIMIT está declarando un requisito más estricto que el
    # de la bomba convencional —una instalación particular, un criterio de
    # operación—, y un equipo de catálogo no puede pasarle por encima. Al revés
    # sí: con la tolerancia estándar, el AGH la extiende hasta su GVF publicado.
    # El manejador avanzado **sustituye** la capacidad de la configuración por
    # la suya: no separa nada, acondiciona la mezcla para que la bomba pueda
    # impulsarla con el gas adentro hasta la fracción de vacío que publica el
    # fabricante (REDA declara 45 % de GVF). No hereda el 20 % de la bomba
    # desnuda ni el 80 % del separador — ése es justamente el límite que viene
    # a levantar. Las dos preguntas se responden por lo tanto con el mismo
    # valor, y se miden sobre el gas que efectivamente llega a la bomba.
    agh_aplicable = (
        agh_max_gvf is not None
        and max_gip >= GAS_FRACTION_PUMP_LIMIT
        and float(agh_max_gvf) > max_gip
    )
    if agh_aplicable:
        cumple_agh = f_mejor <= float(agh_max_gvf)
        ladder.append({
            "strategy": "agh", "n_separators": n_sep_mejor,
            "efficiency": eta_mejor, "f_pump": f_mejor,
            "capacidad": float(agh_max_gvf),
            "tolerancia": float(agh_max_gvf),
            "cumple_capacidad": cumple_agh,
            "cumple_criterio": cumple_agh,
            "alcanza": cumple_agh,
            "agh_model": agh_model,
        })

    elegido = next((e for e in ladder if e["alcanza"]), None)

    if elegido is not None:
        estrategia = elegido["strategy"]
        f_pump = elegido["f_pump"]
        eta_aplicada = elegido["efficiency"]
        n_sep = elegido["n_separators"]
        tol = elegido["tolerancia"]
        cap = elegido["capacidad"]
        if estrategia == "ninguno":
            veredicto = (
                f"Viable sin separador. El gas libre en la admisión "
                f"({f_intake:.1%}) está dentro de lo que admite una bomba sin "
                f"separador ({cap:.0%}, Takács Fig. 4.25) y por debajo del "
                f"máximo de diseño ({tol:.1%})."
            )
        elif estrategia == "simple":
            equipo = f" ({single_model})" if single_model else ""
            veredicto = (
                f"Viable con UN separador{equipo}. El gas en la admisión "
                f"({f_intake:.1%}) está dentro de lo que admite esa "
                f"configuración ({cap:.0%}, Takács Fig. 4.25), y el separador "
                f"lo baja a {f_pump:.1%} en la bomba, por debajo del máximo de "
                f"diseño ({tol:.1%})."
            )
        elif estrategia == "agh":
            equipo = f" ({agh_model})" if agh_model else ""
            con_sep = (
                f"Sobre la separación conseguida ({n_sep} separador"
                f"{'es' if n_sep != 1 else ''}, {f_pump:.1%} de gas en la bomba)"
                if n_sep else
                f"Sin separador que entre en este pozo, el gas llega entero a "
                f"la bomba ({f_pump:.1%})"
            )
            veredicto = (
                f"Viable con MANEJADOR AVANZADO DE GAS{equipo}. {con_sep}, por "
                f"encima del {max_gip:.1%} que tolera una bomba convencional. "
                f"El manejador NO retira gas: acondiciona la mezcla para que la "
                f"bomba la pueda bombear con el gas adentro, hasta "
                f"{float(agh_max_gvf):.0%} de fracción de vacío. Va en el mismo "
                f"eje, así que suma su consumo al motor y su longitud a la "
                f"sarta."
            )
        else:
            equipo = f" ({' + '.join(tandem_models)})" if tandem_models else ""
            veredicto = (
                f"Viable sólo con separador en TÁNDEM{equipo}: un separador "
                f"solo deja {ladder[1]['f_pump']:.1%} de gas en la bomba, por "
                f"encima del límite ({ladder[1]['tolerancia']:.1%}). Los dos en "
                f"serie retiran "
                f"{eta_aplicada:.1%} del gas libre y lo bajan a {f_pump:.1%}. "
                f"El tándem se arma con separadores de tipos distintos y suma "
                f"su consumo al motor y su longitud a la sarta."
            )
    else:
        # Ningún escalón alcanza: el techo de la tecnología no da.
        estrategia = "no_viable"
        n_sep = 0
        eta_aplicada = eta_tandem if eta_tandem is not None else single_efficiency
        f_pump = next(
            (e["f_pump"] for e in reversed(ladder) if e["f_pump"] is not None),
            f_vent,
        )
        tol_tandem = min(max_gip, GAS_VOID_LIMIT_TANDEM)
        eta_necesaria = required_separator_efficiency(f_vent, tol_tandem)
        if eta_necesaria is None or eta_necesaria >= 1.0:
            detalle = (
                "Aun retirando el 100 % del gas libre el remanente seguiría por "
                "encima del límite."
            )
        else:
            disponible = (
                f"{eta_aplicada:.1%}" if eta_aplicada is not None
                else "no hay separador en el catálogo que entre en este pozo"
            )
            detalle = (
                f"Haría falta una eficiencia de separación de "
                f"{eta_necesaria:.1%}; el tándem alcanza {disponible}."
            )
        techo = (
            f"ni con un manejador avanzado encima "
            f"(tolera {float(agh_max_gvf):.0%} de fracción de vacío)"
            if agh_aplicable
            else "y el catálogo no tiene manejador avanzado que entre en este pozo"
        )
        # Qué falló, escalón por escalón: es lo que el usuario necesita para
        # decidir. Un escalón puede caer por capacidad de la configuración
        # (pregunta 1) o por el criterio de diseño (pregunta 2), y el remedio
        # de cada caso es distinto.
        motivos = []
        for e in ladder:
            if e["f_pump"] is None:
                motivos.append(f"{e['strategy']}: no disponible en el catálogo")
            elif not e["cumple_capacidad"]:
                motivos.append(
                    f"{e['strategy']}: la admisión ({f_vent:.1%}) supera la "
                    f"capacidad de la configuración ({e['capacidad']:.0%})"
                )
            elif not e["cumple_criterio"]:
                motivos.append(
                    f"{e['strategy']}: deja {e['f_pump']:.1%} en la bomba, por "
                    f"encima del máximo de diseño ({e['tolerancia']:.1%})"
                )
        veredicto = (
            f"DISEÑO BES NO VIABLE — CAMBIAR DE MÉTODO DE LEVANTAMIENTO. "
            f"El gas libre en la admisión ({f_intake:.1%}) queda en "
            f"{f_pump:.1%} en la bomba incluso con separador en tándem, {techo}. "
            f"Ningún escalón cumple las dos condiciones — "
            f"{'; '.join(motivos)}. {detalle} "
            f"El tándem es la mayor capacidad de manejo de gas de la "
            f"tecnología BES (Takács, Fig. 4.25): si no alcanza, no hay equipo "
            f"que lo resuelva y corresponde evaluar otro método de "
            f"levantamiento artificial —bombeo de cavidad progresiva, gas lift "
            f"o pistón— según las condiciones del pozo."
        )

    # --- Avisos: dónde el resultado se apoya en un supuesto optimista -------
    warnings: list[str] = []
    if n_sep > 0:
        warnings.append(
            "La eficiencia usada es la MÁXIMA que publica el catálogo. Takács "
            "(Fig. 4.19) muestra que la eficiencia real cae al subir el caudal "
            "de líquido, y que por encima de un caudal límite se desploma a "
            "cero porque el inductor deja de vencer la caída de presión en los "
            "puertos de descarga. El gas remanente calculado acá es por lo "
            "tanto una cota INFERIOR: en operación puede ser mayor."
        )
    if estrategia == "agh":
        warnings.append(
            "El manejador avanzado NO retira gas: el gas libre sigue entrando a "
            f"la bomba ({f_pump:.1%}). Lo que cambia es que la mezcla llega "
            "homogeneizada y la bomba la puede impulsar. La curva de la bomba "
            "se sigue leyendo con el caudal de mezcla, así que el deterioro de "
            "altura por gas NO desaparece — sólo desaparece el bloqueo."
        )
    if max_gip > GAS_FRACTION_PUMP_LIMIT:
        warnings.append(
            f"MODO EJEMPLO — el máximo de gas admisible está cargado en "
            f"{max_gip:.0%}, muy por encima del {GAS_FRACTION_PUMP_LIMIT:.0%} "
            f"que la herramienta adopta como criterio de diseño. Es el valor "
            f"con que se reproducen los enunciados del libro que bombean todo "
            f"el gas, y desactiva la verificación de viabilidad por gas. Los "
            f"escalones siguen acotados por la capacidad de cada configuración "
            f"(Takács, Fig. 4.25), pero el resultado NO representa el criterio "
            f"con que la herramienta diseñaría este pozo."
        )
    if fraction_to_ratio(f_vent) > RGS_DOCUMENTED_RATIO_LIMIT and n_sep > 0:
        warnings.append(
            f"La relación gas/líquido que llega al separador "
            f"({fraction_to_ratio(f_vent):.2f}) supera el 0.6 hasta el que hay "
            f"evidencia publicada de desempeño ideal del separador rotativo "
            f"(Takács pág. 186). El resultado es extrapolación."
        )

    return {
        "strategy": estrategia,
        "viable": elegido is not None,
        "switch_lift_method": elegido is None,
        "n_separators": n_sep,
        "efficiency": eta_aplicada,
        "warnings": warnings,
        # La escalera como traza de fórmulas, para el reporte. El dict
        # ``ladder`` de arriba es el dato crudo que consume la pantalla; esto
        # es la MISMA decisión escrita como cuenta, con su cita, para que se
        # pueda auditar por qué se eligió el escalón que se eligió.
        "formulas": _traza_escalera(ladder, f_vent, elegido),
        "f_intake": f_intake,
        "f_after_vent": f_vent,
        "f_pump": f_pump,
        "max_gip": max_gip,
        "vent_fraction": vent_fraction,
        "single_efficiency": single_efficiency,
        "tandem_efficiency": eta_tandem,
        "ladder": ladder,
        "verdict": veredicto,
        # Cuarto escalón. ``uses_agh`` es lo que mira el armado del aparejo para
        # saber si hay que colgar un manejador avanzado además del separador.
        "uses_agh": estrategia == "agh",
        # Alias de continuidad con la compuerta anterior (evaluate_gas_feasibility):
        # qué separador se supuso y con qué eficiencia. Los consumen la respuesta
        # de /api/gas/design y los reportes.
        "separator_model": (
            " + ".join(tandem_models) if estrategia == "tandem" and tandem_models
            else single_model if n_sep else None
        ),
        "separator_efficiency": eta_aplicada,
        "agh_model": agh_model if estrategia == "agh" else None,
        "agh_max_gvf": agh_max_gvf,
        # Contra qué se comparó el gas en la bomba: max_gip en los tres primeros
        # escalones, la capacidad de GVF del manejador en el cuarto.
        "tolerance": (
            float(agh_max_gvf) if estrategia == "agh" and agh_max_gvf is not None
            else max_gip
        ),
        # La capacidad de la configuración elegida — la pregunta 1. Va aparte
        # de ``tolerance``, que es la pregunta 2: son dos condiciones distintas
        # medidas en dos puntos distintos del aparejo.
        "capacity": (
            float(elegido["capacidad"]) if elegido is not None
            else GAS_VOID_LIMIT_POR_ESCALON["tandem"]
        ),
    }


def evaluate_gas_feasibility(
    free_gas_fraction_intake: float,
    separator_efficiency: float | None = None,
    vent_fraction: float = 0.0,
    max_gip: float = GAS_FRACTION_PUMP_LIMIT,
    separator_model: str | None = None,
) -> dict:
    """¿La BES aguanta este gas, o hay que cambiar de método de levantamiento?

    Encadena las tres etapas que reducen el gas antes de la admisión y compara
    el remanente contra el límite::

        f_admisión → venteo por el anular → separador → f_bomba
                                                          ↓
                                              ¿f_bomba > max_gip?

    Las dos reducciones se aplican **sobre la relación** gas/líquido, no sobre
    la fracción: ver :func:`separator_outlet_fraction`.

    Args:
        free_gas_fraction_intake: Fracción de gas libre en la admisión, antes
            de cualquier separación [0–1].
        separator_efficiency: Fracción del gas libre que retira el separador
            elegido. ``None`` = sin separador.
        vent_fraction: Fracción del gas libre que se ventea por el anular
            antes de llegar al separador [0–1].
        max_gip: Fracción máxima de gas admisible en la bomba.
        separator_model: Modelo del separador, sólo para el texto del veredicto.

    Returns:
        dict con ``viable`` (bool), las fracciones de cada etapa
        (``f_intake``, ``f_after_vent``, ``f_pump``), ``max_gip``,
        ``separator_efficiency``, ``required_efficiency`` y ``verdict``.

    Raises:
        ValueError: Si *max_gip* cae fuera de [0, 1].
    """
    if not (0.0 <= max_gip <= 1.0):
        raise ValueError(f"max_gip must be in [0, 1], got {max_gip}")

    f_intake = min(max(0.0, free_gas_fraction_intake), 1.0)
    f_vent = separator_outlet_fraction(f_intake, vent_fraction)
    f_pump = (
        separator_outlet_fraction(f_vent, separator_efficiency)
        if separator_efficiency is not None else f_vent
    )

    viable = f_pump <= max_gip
    eta_necesaria = required_separator_efficiency(f_vent, max_gip)

    equipo = f" ({separator_model})" if separator_model else ""
    if viable:
        if separator_efficiency is not None:
            veredicto = (
                f"Viable con separador{equipo}: el gas libre baja de "
                f"{f_intake:.1%} en la admisión a {f_pump:.1%} en la bomba, "
                f"por debajo del máximo admisible ({max_gip:.1%})."
            )
        else:
            veredicto = (
                f"Viable sin separador: el gas libre en la admisión "
                f"({f_intake:.1%}) ya está por debajo del máximo admisible "
                f"({max_gip:.1%})."
            )
    else:
        if eta_necesaria is not None and eta_necesaria < 1.0:
            salida = (
                f"Haría falta un separador de {eta_necesaria:.1%} de eficiencia; "
                f"el instalado{equipo} retira "
                f"{(separator_efficiency or 0.0):.1%}."
            )
        else:
            salida = (
                "Ningún separador alcanza: aun retirando el 100 % del gas "
                "libre el remanente seguiría por encima del límite."
            )
        veredicto = (
            f"DISEÑO BES NO VIABLE. El gas libre en la admisión ({f_intake:.1%}) "
            f"queda en {f_pump:.1%} después de "
            f"{'ventear e instalar separador' if separator_efficiency is not None else 'ventear'}, "
            f"por encima del máximo que tolera la bomba ({max_gip:.1%}). {salida} "
            f"Con este nivel de gas el método no converge: corresponde evaluar "
            f"otro método de levantamiento artificial."
        )

    return {
        "viable": viable,
        "f_intake": f_intake,
        "f_after_vent": f_vent,
        "f_pump": f_pump,
        "max_gip": max_gip,
        "vent_fraction": vent_fraction,
        "separator_efficiency": separator_efficiency,
        "separator_model": separator_model,
        "required_efficiency": eta_necesaria,
        "verdict": veredicto,
    }


# ---------------------------------------------------------------------------
# 2. Gas Lock Risk
# ---------------------------------------------------------------------------

def check_gas_lock_risk(
    free_gas_fraction: float,
    threshold: float = GAS_FRACTION_NEGLIGIBLE,
) -> dict:
    """Clasifica el riesgo por gas libre en la admisión, según los cuatro umbrales.

    Trabaja con la **fracción** del volumen total —lo que devuelve
    :func:`free_gas_fraction_at_intake`— y convierte a **relación** gas/líquido
    donde el criterio bibliográfico está expresado así (degradación y bloqueo).

    Niveles:
        ``none``      f ≤ 1 %: gas despreciable, vale el diseño monofásico.
        ``low``       1 % < f ≤ 5 %: hay que calcular la pérdida de carga con
                      un modelo multifásico, pero el equipo convencional sirve.
        ``medium``    f > 5 % (o r > 0.1): separador obligatorio; por encima de
                      r = 0.1 la bomba además entrega menos altura que su curva.
        ``high``      r ≥ 1.0 (f ≥ 0.50): bloqueo total por gas, la bomba deja
                      de mover líquido.

    Args:
        free_gas_fraction: Fracción volumétrica de gas libre del total [0–1].
        threshold: Límite de gas despreciable. Por defecto 1 %.

    Returns:
        dict con ``risk``, ``free_gas_fraction``, ``free_gas_ratio``,
        ``needs_separator``, ``pump_degrades``, ``gas_locked`` y
        ``recommendation``.
    """
    f = min(max(0.0, free_gas_fraction), 1.0)
    r = fraction_to_ratio(f)

    degrada = r > GAS_RATIO_DEGRADATION_START
    bloqueo = r >= GAS_RATIO_GAS_LOCK
    separador = f > GAS_FRACTION_SEPARATOR_REQUIRED

    if bloqueo:
        riesgo = "high"
        rec = (
            f"Bloqueo por gas: la relación gas/líquido en la admisión "
            f"({r:.2f}) alcanza o supera 1.0. La bomba deja de mover líquido. "
            f"Hay que separar gas antes de la admisión, bajar la bomba por "
            f"debajo de los punzados o cambiar de método de levantamiento."
        )
    elif separador or degrada:
        riesgo = "medium"
        motivos = []
        if separador:
            motivos.append(f"la fracción de gas libre ({f:.1%}) supera el 5 %")
        if degrada:
            motivos.append(
                f"la relación gas/líquido ({r:.2f}) supera 0.1, con lo que la "
                f"bomba entrega menos altura que su curva de agua"
            )
        rec = (
            "Separador o manejador de gas obligatorio: " + " y ".join(motivos) + "."
        )
    elif f > threshold:
        riesgo = "low"
        rec = (
            f"Gas presente ({f:.1%}): la pérdida de carga en el tubing debe "
            f"calcularse con un modelo multifásico, no con gradiente constante. "
            f"El equipo convencional sirve sin separador."
        )
    else:
        riesgo = "none"
        rec = (
            f"Gas despreciable ({f:.1%} ≤ {threshold:.0%}): el diseño "
            f"monofásico con gradiente constante es válido."
        )

    return {
        "risk": riesgo,
        "free_gas_fraction": f,
        "free_gas_ratio": r,
        "needs_separator": separador,
        "pump_degrades": degrada,
        "gas_locked": bloqueo,
        "recommendation": rec,
    }


# ---------------------------------------------------------------------------
# 3. Pump Deterioration Factor
# ---------------------------------------------------------------------------

def pump_deterioration_factor(free_gas_fraction: float) -> float:
    """Pérdida de altura de la bomba por el gas libre que ingresa.

    El criterio bibliográfico está expresado en **relación** gas/líquido, no en
    fracción: la degradación arranca en r = 0.1 y el bloqueo total llega en
    r = 1.0. Acá se recibe la fracción —que es lo que calcula
    :func:`free_gas_fraction_at_intake`— y se convierte, para que los umbrales
    queden donde los pone la bibliografía y no a la mitad.

        r ≤ 0.1   sin degradación                    (f ≤ 0.0909)
        0.1 < r < 1.0   la altura cae linealmente de 1.0 a 0
        r ≥ 1.0   bloqueo total: no entrega altura   (f ≥ 0.50)

    Referencia: Brown Vol. 2b §4.53102; Takács, *ESP Manual*.

    Args:
        free_gas_fraction: Fracción volumétrica de gas libre del total en la
            admisión [0–1].

    Returns:
        Factor multiplicador de la altura por etapa [0–1].
    """
    f = min(max(0.0, free_gas_fraction), 1.0)
    r = fraction_to_ratio(f)

    if r <= GAS_RATIO_DEGRADATION_START:
        return 1.0
    if r >= GAS_RATIO_GAS_LOCK:
        return 0.0
    # Caída lineal entre el inicio de la degradación y el bloqueo total.
    tramo = (r - GAS_RATIO_DEGRADATION_START) / (
        GAS_RATIO_GAS_LOCK - GAS_RATIO_DEGRADATION_START
    )
    return 1.0 - tramo


# ---------------------------------------------------------------------------
# Internal helpers for pressure_increment_design
# ---------------------------------------------------------------------------

def _mixture_volumes_and_density(
    p: float,
    t: float,
    fluid: Fluid,
    water_cut: float,
    gip: float,
    pvt_table=None,
) -> dict:
    """Fracciones volumétricas y densidad de la mezcla dentro de la bomba, a P y T.

    Todos los volúmenes están referidos a **1 STB de líquido total**
    (petróleo + agua).

    Ojo con la base de cálculo: Brown trabaja por STB de **petróleo**
    (Vol = Bo + Bw + gas_libre·Bg); acá la base es 1 STB de **líquido total**,
    así que cada término lleva su fracción ((1−WC) o WC). Las dos bases dan el
    mismo caudal total al multiplicar por su caudal de superficie — verificado
    contra el #3A: 4.5034 b/STB petróleo × 250 = 2.2517 b/STB líquido × 500
    = 1125.85 b/d.

    Args:
        p: Presión [psia].
        t: Temperatura [°F].
        fluid: Fluido producido.
        water_cut: Corte de agua [0–1].
        gip: Fracción del gas libre que efectivamente entra a la bomba [0–1].
        pvt_table: :class:`bes.core.pvt.PVTTable` medida. Cuando se pasa, sus
            valores ganan sobre las correlaciones (§5 del procedimiento).

    Returns:
        dict con: rs, bo, bg, bw, free_gas_scf, v_oil, v_water, v_gas,
        v_total, rho_mix [lb/ft³], gradient [psi/ft], sg_mix [-],
        pvt_sources (origen de cada propiedad) y pvt_warnings.
    """
    from bes.core.pvt import resolve_pvt

    gor = fluid.gor
    oil_api = fluid.oil_api
    gas_sg_val = fluid.gas_sg
    water_sg_val = fluid.water_sg
    wc = water_cut

    # PVT — tabla medida si la hay, correlación si no (con el origen anotado).
    pvt = resolve_pvt(p, t, fluid, pvt_table)
    rs = pvt["rs"]
    bo = pvt["bo"]
    bg = pvt["bg"]
    bw = pvt["bw"]

    free_gas_scf = max(gor - rs, 0.0)   # scf per STB oil

    # Volumes [bbl res / STB total surface liquid]
    v_oil   = (1.0 - wc) * bo
    v_water = wc * bw
    v_gas   = (1.0 - wc) * free_gas_scf * bg * gip
    v_total = v_oil + v_water + v_gas

    # Mass [lb / STB total surface liquid] — constant with pressure
    oil_sg_val2 = _oil_sg(oil_api)
    m_oil        = (1.0 - wc) * _RHO_WATER_SC * oil_sg_val2 * _BBL_TO_FT3
    m_water      = wc * _RHO_WATER_SC * water_sg_val * _BBL_TO_FT3
    m_gas_dis    = (1.0 - wc) * rs * _RHO_AIR_SC * gas_sg_val
    m_gas_free   = (1.0 - wc) * free_gas_scf * gip * _RHO_AIR_SC * gas_sg_val
    m_total      = m_oil + m_water + m_gas_dis + m_gas_free

    v_total_ft3 = v_total * _BBL_TO_FT3
    rho_mix = m_total / v_total_ft3 if v_total_ft3 > 0.0 else _RHO_WATER_SC

    return {
        "rs":           rs,
        "bo":           bo,
        "bg":           bg,
        "bw":           bw,
        "free_gas_scf": free_gas_scf,
        "v_oil":        v_oil,
        "v_water":      v_water,
        "v_gas":        v_gas,
        "v_total":      v_total,
        "rho_mix":      rho_mix,
        "gradient":     rho_mix / 144.0,
        "sg_mix":       rho_mix / _RHO_WATER_SC,
        "pvt_sources":  pvt["sources"],
        "pvt_warnings": pvt["warnings"],
    }


def _select_pump_for_flow(
    q_bpd: float,
    catalog_manager: "CatalogManager",
    casing_id: float | None = None,
    transform=None,
):
    """Elige del catálogo la bomba cuyo rango de caudal cubra mejor ``q_bpd``.

    Prefiere las bombas donde ``min_flow <= q_bpd <= max_flow``; si ninguna
    califica, toma la de borde más cercano.

    Cuando se pasa ``casing_id``, el catálogo se filtra **primero** por
    diámetro (§17 del procedimiento): una bomba que no entra en el casing no es
    candidata, por bien que le calce el caudal. Sin ese filtro el método podía
    devolver una bomba imposible de bajar al pozo.

    Args:
        q_bpd: Caudal de mezcla en condiciones de bomba [bpd].
        catalog_manager: Catálogo cargado.
        casing_id: Diámetro interno del casing [in]. ``None`` = sin filtro.
        transform: Función que se aplica a cada bomba antes de comparar
            rangos — se usa para llevar la curva a la frecuencia de operación.
            Sin ella se compara contra los rangos de catálogo (60 Hz).

    Returns:
        El ``PumpCurve`` elegido, ya transformado si corresponde.

    Raises:
        ValueError: Si ninguna bomba del catálogo entra en el casing.
    """
    if casing_id is not None:
        all_pumps = catalog_manager.get_pumps_by_casing(casing_id)
        if not all_pumps:
            raise ValueError(
                f"Ninguna bomba del catálogo entra en un casing de "
                f"{casing_id:.3f} in de diámetro interno."
            )
    else:
        all_pumps = catalog_manager.get_all_pumps()

    if transform is not None:
        all_pumps = [transform(p) for p in all_pumps]

    candidates = [p for p in all_pumps if p.min_flow <= q_bpd <= p.max_flow]
    if candidates:
        return min(candidates, key=lambda p: abs(p.bep_flow - q_bpd))
    # Fallback: nearest by range boundary distance
    def _dist(p):
        if q_bpd < p.min_flow:
            return p.min_flow - q_bpd
        return q_bpd - p.max_flow
    return min(all_pumps, key=_dist)


def _pump_perf_clamped(pump, q_bpd: float, catalog_manager: "CatalogManager") -> dict:
    """Interpola la curva acotando el caudal al rango de datos publicado.

    La interpolación no extrapola, así que un caudal fuera de la curva se lee en
    el extremo más cercano. Eso **no** es un punto válido de operación: la
    altura que devuelve es la del extremo, no la que la bomba daría ahí. Por eso
    el resultado viene marcado con ``clamped`` y con el caudal realmente usado,
    para que quien llama pueda advertirlo en vez de presentarlo como bueno.

    Returns:
        Lo que devuelve ``interpolate_pump_curve``, más ``clamped`` (bool),
        ``q_requested`` y ``q_used`` [bpd].
    """
    flows = [pt.flow_rate for pt in pump.points]
    q_min, q_max = min(flows), max(flows)
    q_clamped = max(min(q_bpd, q_max), q_min)
    perf = dict(catalog_manager.interpolate_pump_curve(pump, q_clamped))
    perf["clamped"] = q_clamped != q_bpd
    perf["q_requested"] = q_bpd
    perf["q_used"] = q_clamped
    return perf


def _manufacturer_has_motors(
    manufacturer: str, catalog_manager: "CatalogManager"
) -> bool:
    """¿Ese proveedor tiene motores cargados para armar el aparejo?

    Las bombas del libro (``Brown (libro)``) no son de un proveedor: son los
    ejemplos numerados que anclan la validación, y la regla de no mezclar
    fabricantes no les aplica. No están en el catálogo de la aplicación desde
    ago-2026 — sólo las inyectan los tests.
    """
    if manufacturer in _NO_ES_PROVEEDOR_GAS:
        return True
    return any(
        m.get("manufacturer") == manufacturer
        for m in getattr(catalog_manager, "_motors", [])
    )


#: Fabricantes que no son proveedores comerciales: no se les exige aparejo
#: propio. Espeja ``recommender.pump_selector._NO_ES_PROVEEDOR``.
_NO_ES_PROVEEDOR_GAS = frozenset({"Brown (libro)"})


#: Factores neutros: la bomba entrega su curva de agua sin corregir.
_VISCOSIDAD_NEUTRA = {
    "is_viscous": False,
    "capacity_factor": 100.0,
    "head_factor": 100.0,
    "hp_factor": 100.0,
    "warnings": [],
}


def _viscosity_factors_for_interval(
    fluid: Fluid,
    temp_f: float,
    rs: float,
    pump_efficiency_pct: float,
    apply: bool,
) -> dict:
    """Factores de Riling para UN intervalo de presión (Brown §4.53112).

    La corrección se evalúa intervalo por intervalo y no una sola vez porque el
    gas en solución **cambia con la presión**: a 500 psi el crudo del #3A tiene
    84 scf/b disueltos y a 700 psi tiene 124, y más gas disuelto es crudo más
    liviano. Como la viscosidad entra en Rs, cada tramo de la bomba ve un
    fluido distinto.

    Con crudo de 28 °API o más devuelve factores unitarios sin tocar el PVT: la
    regla de crudo liviano vive en ``evaluate_viscosity`` y se aplica antes de
    calcular nada.

    Args:
        fluid: Fluido producido.
        temp_f: Temperatura del intervalo [°F].
        rs: Gas en solución promedio del intervalo [scf/bbl].
        pump_efficiency_pct: Rendimiento de la bomba en ese punto [%], leído de
            la curva de agua — es lo que pide la Tabla 4.521.
        apply: ``False`` desactiva la corrección y devuelve factores unitarios.

    Returns:
        dict con ``is_viscous``, ``capacity_factor``, ``head_factor``,
        ``hp_factor``, ``new_efficiency`` y ``warnings``.
    """
    if not apply:
        return {**_VISCOSIDAD_NEUTRA, "new_efficiency": pump_efficiency_pct}

    from bes.core.viscosity import evaluate_viscosity

    # El dato medido sólo vale a la temperatura a la que se midió.
    dead_oil_cp = None
    if fluid.oil_viscosity_dead is not None:
        if abs(fluid.viscosity_temp_ref - temp_f) <= 20.0:
            dead_oil_cp = fluid.oil_viscosity_dead

    resultado = evaluate_viscosity(
        oil_api=fluid.oil_api,
        temp_f=temp_f,
        rs_scf_bbl=rs,
        pump_efficiency_pct=pump_efficiency_pct,
        dead_oil_cp=dead_oil_cp,
    )
    return {
        "is_viscous": resultado["is_viscous"],
        "capacity_factor": resultado["capacity_factor"],
        "head_factor": resultado["head_factor"],
        "hp_factor": resultado["hp_factor"],
        "new_efficiency": resultado["new_efficiency"],
        "warnings": resultado.get("warnings", []),
    }


# ---------------------------------------------------------------------------
# 4. Pressure Increment Design
# ---------------------------------------------------------------------------

def _apportion_stages(
    exact_by_model: dict[str, float], total: int
) -> list[tuple[str, int]]:
    """Reparte *total* etapas enteras entre modelos, según sus fracciones exactas.

    Cada modelo se lleva su parte entera y las etapas que sobran van a los que
    tengan mayor resto (reparto por restos mayores). Así el desglose por modelo
    suma exactamente el total del encabezado: sin esto, redondear cada modelo
    por separado da un desglose que no cierra con el número que se reporta.
    """
    if not exact_by_model:
        return []

    piso = {m: int(v) for m, v in exact_by_model.items()}
    sobrante = total - sum(piso.values())

    # Los que tienen mayor resto se llevan las etapas que faltan repartir.
    por_resto = sorted(
        exact_by_model, key=lambda m: exact_by_model[m] - piso[m], reverse=True
    )
    for i in range(max(sobrante, 0)):
        piso[por_resto[i % len(por_resto)]] += 1

    return [(m, n) for m, n in piso.items() if n > 0]


def pressure_increment_design(
    reservoir: Reservoir,
    fluid: Fluid,
    p_intake: float,
    p_discharge: float,
    target_rate: float,
    catalog_manager: "CatalogManager",
    gip: float = 1.0,
    water_cut: float = 0.0,
    increment_psi: float = 200.0,
    apply_deterioration: bool = False,
    fixed_pump_model: str | None = None,
    casing_id: float | None = None,
    apply_viscosity: bool = True,
    pvt_table=None,
    frequency: float | None = None,
) -> dict:
    """Diseño de la bomba por incrementos de presión, para pozos con gas (§4.53103).

    **Es el método central del módulo.** Divide el salto de presión de la bomba
    [p_intake → p_discharge] en escalones iguales, evalúa las propiedades de la
    mezcla en **los dos extremos** de cada escalón y las **promedia** (pasos 4 y
    5 del libro), y con eso determina las etapas y la potencia de cada tramo.

    Por qué los extremos y no el punto medio
    ----------------------------------------
    Bg va con 1/P, así que promediar f(P₁) con f(P₂) **no** da f((P₁+P₂)/2). El
    libro imprime los dos extremos (Vol₅₀₀ = 4.5034, Vol₇₀₀ = 3.6292 →
    Q̄ = 1017 b/d) y ése es el procedimiento que se reproduce. Además es lo
    único que permite publicar la tabla por intervalo con caudal de entrada y
    de salida.

    El invariante de control
    ------------------------
    La **masa se conserva** a lo largo de toda la bomba; lo que cambia es el
    volumen. Verificado contra el #3A: 174 375 lbm/d idéntico a 500 y a 700 psi.

    Una sola bomba para toda la sarta
    ---------------------------------
    Se elige sobre el caudal de mezcla representativo (paso 6 del libro). Antes
    se re-seleccionaba por incremento y salían sartas de 3-4 modelos distintos,
    que no se pueden construir y encima mezclaban fabricantes.

    Args:
        reservoir: Reservorio — su ``reservoir_temp`` se usa para todo el PVT.
        fluid: Propiedades PVT del fluido (GOR, API, gas_sg, water_sg, Pb).
        p_intake: Presión en la admisión de la bomba [psia].
        p_discharge: Presión en la descarga de la bomba [psia].
        target_rate: Caudal bruto de líquido en superficie [STB/d].
        catalog_manager: Catálogo de equipos cargado.
        gip: Fracción de gas que entra a la bomba [0–1]. Por defecto 1.0.
        water_cut: Corte de agua [0–1]. Por defecto 0 (petróleo puro).
        increment_psi: Tamaño del escalón de presión [psi]. Por defecto 200.
        apply_deterioration: Si es True, la altura que desarrolla cada etapa se
            castiga con ``pump_deterioration_factor`` evaluado en la fracción
            local de gas libre (Brown §4.53102). Menos altura por etapa
            significa menos psi ganados por etapa, o sea **más etapas** — así
            se reproducen las variantes «con deterioro» del #3B. Por defecto
            False.
        fixed_pump_model: Si se indica, la sarta usa exactamente ese modelo en
            vez de elegirlo por el caudal representativo. Sirve para reproducir
            los casos de una sola bomba del libro (por ej. el #3B caso 1, todo
            D-40). Si el modelo no existe, cae a la selección automática.
        casing_id: Diámetro interno del casing [in]. Filtra el catálogo antes
            de elegir la bomba (§17): sin esto se puede elegir una bomba que no
            entra en el pozo. ``None`` = sin filtro.
        apply_viscosity: Aplica la corrección de Riling **por intervalo**. Con
            crudo >= 28 °API no cambia nada (factores unitarios). Por defecto
            True.
        pvt_table: :class:`bes.core.pvt.PVTTable` de laboratorio. Sus valores
            ganan sobre las correlaciones, propiedad por propiedad (§5).
        frequency: Frecuencia de operación [Hz]. La curva se reescala con las
            leyes de afinidad **antes** de elegir la bomba y de leer la altura:
            a 50 Hz el rango operativo se corre ~17 % hacia abajo, así que sin
            esto un pozo con variador se diseñaría contra la curva de 60 Hz.
            ``None`` = usar la curva de catálogo tal cual.

    Returns:
        dict con: ``total_stages``, ``total_hp``, ``pump_combination`` (lista
        de tuplas (modelo, etapas)), ``increment_table`` (lista de dicts, uno
        por incremento), ``pump_model`` / ``pump_manufacturer`` /
        ``pump_series``, ``q_representative_bpd``, ``q_mix_max_bpd``,
        ``q_mix_min_bpd``, ``mass_rate_lbm_d``, ``pvt_warnings`` y
        ``viscosity_warnings``.

    Raises:
        ValueError: Si ``p_discharge`` <= ``p_intake``, o si ninguna bomba del
            catálogo entra en el casing.
    """
    if p_discharge <= p_intake:
        raise ValueError(
            f"p_discharge ({p_discharge}) must be greater than "
            f"p_intake ({p_intake})"
        )

    temp = reservoir.reservoir_temp

    # ---------------------------------------------------------------------
    # Paso 1 — fronteras de los intervalos y PVT en CADA frontera.
    #
    # Brown evalúa el fluido en los DOS extremos del incremento y promedia
    # (§4.53103 pasos 4 y 5: "Find average gradient" / "Find average volume").
    # Se calcula una vez por frontera y se reusa: el extremo superior de un
    # incremento es el inferior del siguiente.
    # ---------------------------------------------------------------------
    boundaries = []
    p = p_intake
    while p < p_discharge - 1e-6:
        boundaries.append(p)
        p = min(p + increment_psi, p_discharge)
    boundaries.append(p_discharge)

    props_at = [
        _mixture_volumes_and_density(pb_, temp, fluid, water_cut, gip, pvt_table)
        for pb_ in boundaries
    ]
    q_at = [target_rate * pr["v_total"] for pr in props_at]   # bpd en cada frontera

    # ---------------------------------------------------------------------
    # Paso 2 — caudal representativo de cada intervalo: Qavg = (Q1 + Q2)/2,
    # local al intervalo, nunca el promedio de todo el sistema.
    # ---------------------------------------------------------------------
    intervalos = []
    for i in range(len(boundaries) - 1):
        lo, hi = props_at[i], props_at[i + 1]
        prom = lambda k, _lo=lo, _hi=hi: 0.5 * (_lo[k] + _hi[k])  # noqa: E731
        v_total_avg = prom("v_total")
        intervalos.append({
            "p_lo": boundaries[i],
            "p_hi": boundaries[i + 1],
            "delta_p": boundaries[i + 1] - boundaries[i],
            "lo": lo, "hi": hi,
            "q_lo": q_at[i], "q_hi": q_at[i + 1],
            "q_avg": 0.5 * (q_at[i] + q_at[i + 1]),
            "v_total": v_total_avg,
            "gradient": prom("gradient"),
            "rho_mix": prom("rho_mix"),
            "sg_mix": prom("sg_mix"),
            "rs": prom("rs"), "bo": prom("bo"),
            "bg": prom("bg"), "bw": prom("bw"),
            "v_oil": prom("v_oil"), "v_water": prom("v_water"),
            "v_gas": prom("v_gas"),
            "fg_ratio": prom("v_gas") / v_total_avg if v_total_avg > 0 else 0.0,
        })

    # ---------------------------------------------------------------------
    # Paso 3 — UNA bomba para toda la sarta, elegida sobre el caudal de mezcla
    # representativo (Brown §4.53103 pasos 5-6: "Find average volume" →
    # "Select pump for this average flow rate", y elige una sola Reda D-40).
    #
    # Antes se re-seleccionaba por incremento y salían sartas de 3-4 modelos
    # distintos, que no se pueden construir y además mezclaban fabricantes
    # —prohibido por .claude/rules/domain.md—. Con una sola bomba la regla se
    # cumple sola.
    # ---------------------------------------------------------------------
    # La curva se lleva a la frecuencia de operación ANTES de elegir: a 50 Hz el
    # rango operativo se corre ~17 % hacia abajo (Q ∝ N), así que seleccionar
    # contra los rangos de catálogo (60 Hz) elegiría mal la bomba. Es la misma
    # regla que aplica design_pump_complete en el camino convencional.
    def _a_frecuencia(p):
        if frequency is None:
            return p
        from bes.core.affinity import pump_at_frequency
        return pump_at_frequency(p, frequency)

    forced_pump = None
    if fixed_pump_model:
        matches = [
            p for p in catalog_manager.get_all_pumps()
            if p.model == fixed_pump_model
        ]
        forced_pump = _a_frecuencia(matches[0]) if matches else None

    q_representativo = (
        sum(iv["q_avg"] for iv in intervalos) / len(intervalos)
        if intervalos else target_rate
    )
    if forced_pump is not None:
        pump = forced_pump
    else:
        pump = _select_pump_for_flow(
            q_representativo, catalog_manager, casing_id,
            transform=_a_frecuencia if frequency is not None else None,
        )

    selection_warnings: list[str] = []
    if not (pump.min_flow <= q_representativo <= pump.max_flow):
        selection_warnings.append(
            f"La {pump.model} opera fuera de su rango recomendado "
            f"({pump.min_flow:.0f}–{pump.max_flow:.0f} bpd) con el caudal de "
            f"mezcla representativo ({q_representativo:.0f} bpd). La curva se "
            f"lee acotada al extremo, así que la altura por etapa es optimista."
        )
    if not _manufacturer_has_motors(pump.manufacturer, catalog_manager):
        selection_warnings.append(
            f"{pump.manufacturer} no publica motores en el catálogo, así que "
            f"esta bomba no puede completarse en un aparejo del mismo "
            f"proveedor (.claude/rules/domain.md). El diseño hidráulico de "
            f"abajo es válido; el eléctrico no se puede cerrar."
        )

    # -----------------------------------------------------------------------
    # Traza de fórmulas (bes.core.formulas): qué cuenta se hizo y con qué
    # números. Se arma con las MISMAS variables que entran al cálculo — si se
    # escribiera aparte podría decir una cosa y el programa hacer otra.
    #
    # Un tramo se traza ENTERO (el primero) y el resto se resume: con paso de
    # 25 psi hay decenas de tramos y todos resuelven la misma cadena, así que
    # repetirla no agrega información y sí ruido.
    # -----------------------------------------------------------------------
    trace = FormulaTrace()
    trace.add(
        "gas_delta_p",
        {"P_desc": p_discharge, "P_adm": p_intake},
        p_discharge - p_intake,
    )
    # El techo NO es decorativo: 847/200 da 4.24, y los tramos son 5. El
    # último se queda con el resto de la división.
    trace.add(
        "gas_n_incrementos",
        {"ΔP": p_discharge - p_intake, "escalón": increment_psi},
        len(intervalos),
    )
    trace.add(
        "gas_q_representativo",
        {"Σ Q_prom,i": sum(iv["q_avg"] for iv in intervalos),
         "n": len(intervalos)},
        q_representativo,
        context=f"Con este caudal se eligió la {pump.manufacturer} "
                f"{pump.model} para toda la sarta.",
    )

    total_stages_exact = 0.0        # suma de fracciones, sin redondear
    total_stages_longhand = 0       # suma de ceil por incremento (convención del libro)
    total_hp = 0.0
    tdh_equivalent_ft = 0.0         # Σ ΔPᵢ/gradienteᵢ — la altura que desarrolla
    pump_counts: dict[str, float] = {}
    increment_table: list[dict] = []
    pvt_warnings: list[str] = []
    viscosity_warnings: list[str] = []
    fuera_de_rango: list[tuple] = []

    for idx, iv in enumerate(intervalos):
        p_lo, p_hi = iv["p_lo"], iv["p_hi"]
        p_mid = 0.5 * (p_lo + p_hi)
        delta_p = iv["delta_p"]

        v_total  = iv["v_total"]
        rho_mix  = iv["rho_mix"]
        gradient = iv["gradient"]
        sg_mix   = iv["sg_mix"]
        fg_ratio = iv["fg_ratio"]
        q_res    = iv["q_avg"]

        for pr in (iv["lo"], iv["hi"]):
            for w in pr["pvt_warnings"]:
                if w not in pvt_warnings:
                    pvt_warnings.append(w)

        # --- Curva de agua en el caudal del intervalo -------------------
        curve = _pump_perf_clamped(pump, q_res, catalog_manager)
        if curve["clamped"]:
            fuera_de_rango.append((p_lo, p_hi, q_res, curve["q_used"]))
        # interpolate_pump_curve devuelve el rendimiento en FRACCIÓN [0-1];
        # las tablas de Riling lo piden en PORCENTAJE.
        eficiencia_agua = curve.get("efficiency", 0.0) * 100.0

        # --- Corrección por viscosidad (Riling, §4.53112) ---------------
        # Se evalúa POR INTERVALO: el gas en solución cambia con la presión y
        # la viscosidad del crudo vivo con él. Crudo ≥ 28 °API devuelve
        # factores unitarios y esto no toca nada.
        visc = _viscosity_factors_for_interval(
            fluid, temp, iv["rs"], eficiencia_agua, apply_viscosity
        )
        cq = visc["capacity_factor"] / 100.0
        ch = visc["head_factor"] / 100.0
        chp = visc["hp_factor"] / 100.0
        for w in visc.get("warnings", []):
            if w not in viscosity_warnings:
                viscosity_warnings.append(w)

        if visc["is_viscous"]:
            # La bomba mueve q_res de crudo viscoso; sobre su curva de AGUA eso
            # equivale a q_res/C_Q, y la altura que entrega es C_H veces la de
            # agua en ese punto. Se divide para entrar a la curva y se
            # multiplica para salir — invertirlo da una bomba corta.
            curve = _pump_perf_clamped(pump, q_res / cq if cq > 0 else q_res,
                                       catalog_manager)
            head_per_stage = curve["head_per_stage"] * ch
        else:
            head_per_stage = curve["head_per_stage"]

        hp_per_stage_w = curve["hp_per_stage"]   # rated for water
        eficiencia = visc["new_efficiency"]

        # Pump-deterioration derating of the head (Brown §4.53102).
        det_factor = pump_deterioration_factor(fg_ratio) if apply_deterioration else 1.0
        head_effective = head_per_stage * det_factor

        psi_per_stage = head_effective * gradient
        if psi_per_stage <= 0.0:
            continue

        # Etapas EXACTAS del incremento. No se redondea acá: redondear en cada
        # incremento cuesta hasta media etapa cada vez, y ese error se acumula
        # con la cantidad de incrementos. Con 4 escalones de 200 psi es
        # despreciable, pero al afinar el paso —que es justamente lo que hace la
        # solución por computadora del libro, §4.53105, resolviendo etapa por
        # etapa— el conteo se infla en vez de converger: 204 etapas con paso de
        # 200 psi contra 428 con paso de 2 psi, para el mismo pozo.
        # Se acumula la fracción y se redondea UNA sola vez, al final.
        stages_exact = delta_p / psi_per_stage

        # Shaft-power corrected for mixture SG (water-rated catalog × SG) and,
        # con crudo viscoso, por el factor de potencia de la tabla de Riling.
        hp_incr = stages_exact * hp_per_stage_w * sg_mix * chp

        # Altura que la bomba desarrolla en este tramo. No es una correlación
        # nueva: es la misma identidad que ya usa el conteo de etapas
        # (etapas = ΔP / (head_etapa · gradiente)), despejada al revés. Sumada
        # sobre todos los tramos da el TDH equivalente del método, que es con
        # el que se dimensiona el aparejo.
        head_incr_ft = delta_p / gradient if gradient > 0 else 0.0

        # --- Traza del PRIMER tramo, entera -----------------------------
        # Todos los tramos resuelven esta misma cadena; se muestra una vez y
        # los demás se resumen al final. Las variables son las que acaban de
        # entrar a la cuenta, no una copia escrita a mano.
        if idx == 0:
            lo0, hi0 = iv["lo"], iv["hi"]
            trace.add(
                "gas_q_avg",
                {"Q_ent": iv["q_lo"], "Q_sal": iv["q_hi"]}, q_res,
                label=f"Caudal de mezcla del tramo {p_lo:,.0f}–{p_hi:,.0f} psi",
                context="El caudal cae al subir la presión porque el gas se "
                        "comprime y parte pasa a solución.",
            )
            trace.add(
                "gas_gradient",
                {"grad_ent": lo0["gradient"], "grad_sal": hi0["gradient"]},
                gradient,
            )
            if visc["is_viscous"]:
                trace.add(
                    "gas_visc",
                    {"Q_prom": q_res, "C_Q": cq, "C_H": ch}, head_per_stage,
                    context=f"El crudo es de {fluid.oil_api:.1f} °API, así que "
                            f"corresponde corregir. Se divide para entrar a la "
                            f"curva de agua y se multiplica para salir.",
                )
            if apply_deterioration:
                trace.add(
                    "gas_deterioro",
                    {"H_etapa": head_per_stage, "f_det": det_factor},
                    head_effective,
                    context=f"El tramo tiene {fg_ratio * 100:.1f} % de gas libre.",
                )
            trace.add(
                "gas_psi_etapa",
                {"H_efec": head_effective, "grad": gradient}, psi_per_stage,
                context="Ésta es la bisagra de todo el método.",
            )
            trace.add(
                "gas_etapas_tramo",
                {"ΔP_tramo": delta_p, "Δp_etapa": psi_per_stage}, stages_exact,
                context="Al afinar el paso, redondear por tramo infla el conteo "
                        "en vez de converger. La suma de los redondeos por tramo "
                        "se publica aparte, que es la convención del cálculo a "
                        "mano.",
            )
            trace.add(
                "gas_hp_tramo",
                {"N_tramo": stages_exact, "HP_etapa": hp_per_stage_w,
                 "SG_mezcla": sg_mix, "C_HP": chp},
                hp_incr,
            )

        total_stages_exact += stages_exact
        total_hp += hp_incr
        tdh_equivalent_ft += head_incr_ft

        # El conteo con redondeo por incremento se conserva aparte: es la
        # convención del cálculo a mano del libro (83+51+40+35 = 209).
        n_stages = math.ceil(stages_exact)
        total_stages_longhand += n_stages

        model = pump.model
        pump_counts[model] = pump_counts.get(model, 0.0) + stages_exact

        lo, hi = iv["lo"], iv["hi"]
        increment_table.append({
            "p_lo":             p_lo,
            "p_hi":             p_hi,
            "p_mid":            p_mid,
            "delta_p":          delta_p,
            # --- Promedios del intervalo (los que usa el cálculo) ---------
            "rs":               iv["rs"],
            "bo":               iv["bo"],
            "bg":               iv["bg"],
            "bw":               iv["bw"],
            "free_gas_scf":     0.5 * (lo["free_gas_scf"] + hi["free_gas_scf"]),
            "v_oil":            iv["v_oil"],
            "v_water":          iv["v_water"],
            "v_gas":            iv["v_gas"],
            "v_total":          v_total,
            "rho_mix":          rho_mix,
            "gradient":         gradient,
            "sg_mix":           sg_mix,
            "fg_ratio":         fg_ratio,
            "q_res_bpd":        q_res,
            "q_avg_bpd":        q_res,
            # --- Valores en cada extremo (los que imprime Brown) ----------
            "q_lo_bpd":         iv["q_lo"],
            "q_hi_bpd":         iv["q_hi"],
            "q_oil_lo":         target_rate * lo["v_oil"],
            "q_oil_hi":         target_rate * hi["v_oil"],
            "q_water_lo":       target_rate * lo["v_water"],
            "q_water_hi":       target_rate * hi["v_water"],
            "q_gas_lo":         target_rate * lo["v_gas"],
            "q_gas_hi":         target_rate * hi["v_gas"],
            "rs_lo":            lo["rs"],          "rs_hi":       hi["rs"],
            "bo_lo":            lo["bo"],          "bo_hi":       hi["bo"],
            "bg_lo":            lo["bg"],          "bg_hi":       hi["bg"],
            "rho_lo":           lo["rho_mix"],     "rho_hi":      hi["rho_mix"],
            "gradient_lo":      lo["gradient"],    "gradient_hi": hi["gradient"],
            # --- Bomba ----------------------------------------------------
            "pump_model":       model,
            "head_per_stage":   head_per_stage,
            "efficiency":       eficiencia,
            "det_factor":       det_factor,
            "head_effective":   head_effective,
            "hp_per_stage_w":   hp_per_stage_w,
            "psi_per_stage":    psi_per_stage,
            "head_incr_ft":     head_incr_ft,
            "stages_exact":     stages_exact,
            "stages":           n_stages,
            "hp":               hp_incr,
            # La curva se leyó fuera de su rango de datos: la altura es la del
            # extremo, no la que la bomba daría a ese caudal.
            "curve_clamped":    curve["clamped"],
            "q_curve_used":     curve["q_used"],
            # --- Viscosidad (Riling) --------------------------------------
            "is_viscous":       visc["is_viscous"],
            "capacity_factor":  visc["capacity_factor"],
            "head_factor":      visc["head_factor"],
            "hp_factor":        visc["hp_factor"],
            # --- Trazabilidad del dato (§25) ------------------------------
            "pvt_sources":      lo["pvt_sources"],
        })

    # Redondeo final, una sola vez: no se puede instalar una fracción de etapa,
    # y hace falta al menos la cantidad exacta que pide el cálculo.
    total_stages = math.ceil(total_stages_exact)

    # --- Traza de los totales ------------------------------------------------
    trace.add(
        "gas_etapas_total",
        {"Σ N_tramo": total_stages_exact}, total_stages,
        context=f"Se suman las fracciones de los {len(increment_table)} tramos. "
                f"Redondeando cada tramo por separado —la convención del cálculo "
                f"a mano— darían {total_stages_longhand} etapas.",
    )
    # Los dos totales van SIN sustitución: reemplazar el sumatorio por su propio
    # valor daría «51.8 = 51.8», que no informa nada. La expresión queda en
    # símbolos y el resultado lo agrega la vista.
    trace.add(
        "gas_hp_total", {}, total_hp, substitute=False,
        context=f"Suma de los {len(increment_table)} tramos.",
    )
    trace.add(
        "gas_tdh_equivalente", {}, tdh_equivalent_ft, substitute=False,
        context="Con este valor se dimensiona el aparejo.",
    )

    # Reparto por modelo: se redondea cada uno y se ajusta el mayor para que la
    # suma cierre con el total, así el desglose no contradice al encabezado.
    pump_combination = _apportion_stages(pump_counts, total_stages)

    # La curva se leyó acotada en algún tramo: hay que decirlo, no presentar el
    # punto como si fuera de operación válida. La altura de un extremo de la
    # curva no es la que la bomba entrega a un caudal que la curva no cubre.
    if fuera_de_rango:
        q_lo_c = min(f[2] for f in fuera_de_rango)
        q_hi_c = max(f[2] for f in fuera_de_rango)
        selection_warnings.append(
            f"En {len(fuera_de_rango)} de {len(intervalos)} tramos el caudal de "
            f"mezcla ({q_lo_c:.0f}–{q_hi_c:.0f} bpd) queda fuera de los datos "
            f"publicados de la curva de la {pump.model} "
            f"({min(pt.flow_rate for pt in pump.points):.0f}–"
            f"{max(pt.flow_rate for pt in pump.points):.0f} bpd). La altura se "
            f"leyó en el extremo de la curva: NO es un punto de operación "
            f"válido y las etapas de esos tramos son optimistas. Elegir una "
            f"bomba cuyo rango cubra el caudal de mezcla."
        )

    # Caudal másico: invariante de control del método (§12). Se evalúa en la
    # admisión, pero da lo mismo en cualquier frontera — es justamente el punto.
    mass_rate = (
        props_at[0]["rho_mix"] * props_at[0]["v_total"] * _BBL_TO_FT3 * target_rate
    )
    trace.add(
        "gas_masa",
        {"ρ_adm": props_at[0]["rho_mix"], "V_adm": props_at[0]["v_total"],
         "q_STB": target_rate},
        mass_rate,
        context="Evaluada acá en la admisión, pero da lo mismo en cualquier "
                "frontera: ése es justamente el punto.",
    )

    return {
        "total_stages":      total_stages,
        "total_stages_exact": round(total_stages_exact, 2),
        "total_stages_longhand": total_stages_longhand,
        "total_hp":          round(total_hp, 2),
        # TDH equivalente: Σ ΔPᵢ/gradienteᵢ. Es la altura que la bomba
        # desarrolla según ESTE método, y con la que se dimensiona el aparejo.
        # No es el TDH de la fórmula de tres términos: ver la nota de
        # run_gas_design_complete sobre la discrepancia entre ambas rutas.
        "tdh_equivalent_ft": tdh_equivalent_ft,
        "pump_combination":  pump_combination,
        "increment_table":   increment_table,
        "p_intake":          p_intake,
        "p_discharge":       p_discharge,
        "delta_p":           p_discharge - p_intake,
        "n_increments":      len(increment_table),
        "gip":               gip,
        "water_cut":         water_cut,
        "apply_deterioration": apply_deterioration,
        "fixed_pump_model":  fixed_pump_model,
        # --- Bomba única de la sarta (§17) ------------------------------
        # El objeto va entero: ya viene escalado a la frecuencia de operación,
        # y el adaptador lo necesita para carcasas, BEP y verificación mecánica.
        "pump_curve":        pump,
        "pump_model":        pump.model,
        "pump_manufacturer": pump.manufacturer,
        "pump_series":       pump.series,
        "q_representative_bpd": q_representativo,
        # --- Resumen de caudales de mezcla (§23) ------------------------
        "q_mix_max_bpd":     max(q_at),
        "q_mix_min_bpd":     min(q_at),
        "q_mix_intake_bpd":  q_at[0],
        "q_mix_discharge_bpd": q_at[-1],
        "mass_rate_lbm_d":   mass_rate,
        # --- Trazabilidad y avisos (§25) --------------------------------
        "pvt_source":        (
            pvt_table.source if pvt_table is not None
            else "Correlaciones Standing / DAK / McCain"
        ),
        "pvt_warnings":      pvt_warnings,
        "viscosity_warnings": viscosity_warnings,
        "selection_warnings": selection_warnings,
        "increment_psi":     increment_psi,
        # --- Traza de fórmulas (bes.core.formulas) -----------------------
        # Un tramo entero + los totales. La consume tanto la vista de
        # hidráulica como el DesignResult del aparejo completo.
        "formulas":          trace.as_list(),
    }


# ---------------------------------------------------------------------------
# 4bis. Adaptador: resultado por intervalos → candidato de diseño
# ---------------------------------------------------------------------------

def increment_result_to_candidate(
    inc: dict,
    sg: float,
    tdh_info: dict,
    bottom_temp_f: float,
    catalog_manager: "CatalogManager",
    sg_max: float | None = None,
    extra_warnings: list[str] | None = None,
    strict: bool = False,
) -> dict | None:
    """Traduce la salida del método por incrementos al candidato de diseño.

    El resto de BES Designer —selección de motor, sello, cable, transformador,
    VSD y el armado del ``DesignResult``— consume un **dict de candidato** con
    una forma fija, la que produce ``pump_design._design_candidate()``. Este
    adaptador arma ese mismo dict a partir del resultado por intervalos, para
    que el pozo con gas siga por el camino que ya existe en vez de tener uno
    propio. **No recalcula hidráulica**: sólo traduce y agrega las
    verificaciones de carcasa y mecánica, que son las mismas funciones que usa
    el camino convencional.

    Cómo se resuelven las magnitudes «por etapa», que el método por intervalos
    no tiene como valor único:

    ``tdh_ft``
        ``Σ ΔPᵢ/gradienteᵢ`` — la altura que la bomba desarrolla según este
        método. Es la identidad que ya usa el conteo de etapas, despejada al
        revés, **no** la fórmula de tres términos del camino convencional. Las
        dos rutas pueden discrepar; ``tdh_info`` viaja igual para poder
        auditarlo.

    ``head_per_stage``
        ``TDH_equivalente / etapas_exactas`` — el promedio ponderado exacto.

    ``hp_per_stage`` y ``efficiency``
        Promedios ponderados por etapas de cada tramo. La potencia total NO se
        recalcula desde estos promedios: se toma la suma por intervalos, que ya
        lleva el SG y el factor de viscosidad de cada tramo.

    Args:
        inc: Lo que devuelve :func:`pressure_increment_design`.
        sg: SG de la mezcla producida → HP operativo.
        tdh_info: Desglose del TDH convencional. Aporta ``vertical_lift_ft``
            para la carga axial y queda en el candidato para auditoría.
        bottom_temp_f: Temperatura de fondo [°F].
        catalog_manager: Catálogo cargado.
        sg_max: SG del fluido más pesado → HP máximo, con el que se dimensiona
            el motor. Si se omite se usa ``sg``.
        extra_warnings: Avisos del pozo (no de la bomba) a anteponer.
        strict: Propagado a las verificaciones de carcasa y mecánica.

    Returns:
        El dict de candidato, o ``None`` si la bomba no se puede armar
        (carcasas, eje o cojinete), que es la señal de «probá la siguiente».

    Raises:
        ValueError: Sólo con ``strict=True``.
    """
    from bes.core.pump_design import (
        check_pump_operating_range,
        housing_and_mechanical_checks,
    )

    pump = inc["pump_curve"]
    tabla = inc["increment_table"]
    stages = inc["total_stages"]
    stages_exact = sum(r["stages_exact"] for r in tabla) or 1.0

    def _ponderado(clave: str) -> float:
        return sum(r[clave] * r["stages_exact"] for r in tabla) / stages_exact

    tdh_ft = inc["tdh_equivalent_ft"]
    head_per_stage = tdh_ft / stages_exact
    hp_per_stage = _ponderado("hp_per_stage_w")
    # La eficiencia de la tabla viene en PORCENTAJE; el candidato la lleva en
    # fracción [0-1], que es como la publica interpolate_pump_curve.
    efficiency = _ponderado("efficiency") / 100.0

    total_hp = inc["total_hp"]
    factor_max = (sg_max / sg) if (sg_max and sg > 0) else 1.0

    warnings: list[str] = [
        *(extra_warnings or []),
        *inc.get("selection_warnings", []),
        *inc.get("pvt_warnings", []),
        *inc.get("viscosity_warnings", []),
    ]

    q_rep = inc["q_representative_bpd"]
    op_check = check_pump_operating_range(pump, q_rep)
    if not op_check["in_range"]:
        warnings.append("Flow rate outside pump operating range")

    mech = housing_and_mechanical_checks(
        catalog_manager=catalog_manager,
        pump=pump,
        stages=stages,
        sg=sg,
        hp_per_stage=hp_per_stage,
        head_per_stage=head_per_stage,
        vertical_lift_ft=float(tdh_info.get("vertical_lift_ft", 0.0)),
        bottom_temp_f=bottom_temp_f,
        warnings=warnings,
        strict=strict,
    )
    if mech is None:
        return None

    viscoso = any(r["is_viscous"] for r in tabla)

    return {
        **mech,
        # La traza viene del propio cálculo por incrementos: es la cadena que
        # se ejecutó, no una reescritura. Así el aparejo completo muestra las
        # fórmulas del método por el mismo camino que el diseño convencional
        # (ResultsView las lee de DesignResult.formulas).
        #
        # Delante van las del balance de gas libre, que ``calculate_tdh`` ya
        # calculó: son las que explican de dónde sale la fracción con que este
        # camino decide TODO —la correlación de fricción, la escalera de manejo
        # de gas y la propia aplicación del método—. Sin ellas el reporte del
        # pozo con gas arranca por el salto de presión y el porcentaje de gas
        # aparece sin origen.
        "formulas": [
            *[f for f in tdh_info.get("formulas", [])
              if f.get("step") == "balance_gas_libre"],
            *inc.get("formulas", []),
        ],
        "pump_model": pump.model,
        "pump_manufacturer": pump.manufacturer,
        "pump_od": pump.od,
        "stages": stages,
        "tdh_ft": tdh_ft,
        "head_per_stage": head_per_stage,
        "hp_per_stage": hp_per_stage,
        "efficiency": efficiency,
        "total_pump_hp": total_hp,
        "motor_hp_max": total_hp * factor_max,
        "pip_psi": inc["p_intake"],
        "sg_liquid": sg,
        "pump_curve": pump,
        "operating_frequency_hz": pump.catalog_frequency_hz,
        "operating_check": op_check,
        "tdh_breakdown": tdh_info,
        "free_gas_fraction": tabla[0]["fg_ratio"] if tabla else 0.0,
        "friction_method": "poettmann_carpenter",
        "viscosity_correction": (
            {
                "is_viscous": True,
                "capacity_factor": _ponderado("capacity_factor"),
                "head_factor": _ponderado("head_factor"),
                "hp_factor": _ponderado("hp_factor"),
                "note": "Promedios ponderados por etapas; la corrección de "
                        "Riling se aplicó tramo por tramo, no una sola vez.",
            }
            if viscoso else None
        ),
        "design_flow_rate": q_rep,
        "design_head_ft": tdh_ft,
        "warnings": warnings,
        # --- Específico del método por incrementos ---------------------
        "design_method": "pressure_increment",
        # Los tres caudales que definen la zona operativa del método. Con gas
        # el caudal NO es constante a lo largo de la bomba, así que un solo
        # número no la describe: la bomba se eligió contra el representativo y
        # hay que poder verificar dónde caen los dos extremos.
        "gas_q_representative_bpd": q_rep,
        "gas_q_intake_bpd": inc["q_mix_intake_bpd"],
        "gas_q_discharge_bpd": inc["q_mix_discharge_bpd"],
        "increment_table": tabla,
        "p_discharge_psi": inc["p_discharge"],
        "increment_psi": inc["increment_psi"],
        "mass_rate_lbm_d": inc["mass_rate_lbm_d"],
        "total_stages_longhand": inc["total_stages_longhand"],
        "tdh_conventional_ft": tdh_info.get("tdh_ft"),
    }


# ---------------------------------------------------------------------------
# 5. Recommend Gas Separator
# ---------------------------------------------------------------------------

_SEPARATOR_MODELS: dict[str, dict] = {
    "400": {
        "type": "Rotary Gas Separator",
        "model": "GasMaster-400",
        "manufacturer": "Reda",
        "efficiency": 0.90,
    },
    "513": {
        "type": "Reverse Flow Separator",
        "model": "MVP-513",
        "manufacturer": "Centrilift",
        "efficiency": 0.85,
    },
    "540": {
        "type": "Rotary Gas Separator",
        "model": "GS-540",
        "manufacturer": "Reda",
        "efficiency": 0.90,
    },
    "738": {
        "type": "Advanced Gas Handler",
        "model": "AGH-738",
        "manufacturer": "Centrilift",
        "efficiency": 0.80,
    },
}

_SEPARATOR_GENERIC = {
    "type": "Standard Gas Separator",
    "model": "GS-Generic",
    "manufacturer": "Various",
    "efficiency": 0.75,
}


def recommend_gas_separator(
    free_gas_at_intake: float,
    pump_series: str,
) -> dict:
    """Recomienda un separador de gas de fondo para la serie de bomba dada.

    Args:
        free_gas_at_intake: Fracción volumétrica de gas libre en la
            admisión [0–1].
        pump_series: Serie de la bomba (por ej. ``"400"``, ``"513"``).

    Returns:
        dict con ``separator`` (datos del equipo), ``free_gas_ratio`` y
        ``notes``.
    """
    sep = _SEPARATOR_MODELS.get(pump_series, _SEPARATOR_GENERIC)

    notes = []
    if free_gas_at_intake > 0.30:
        notes.append("High gas fraction — separator is strongly recommended")
    elif free_gas_at_intake > 0.10:
        notes.append("Moderate gas fraction — separator recommended for reliability")
    else:
        notes.append("Low gas fraction — separator optional")

    return {
        "separator":      sep,
        "free_gas_ratio": free_gas_at_intake,
        "pump_series":    pump_series,
        "notes":          notes,
    }


# ---------------------------------------------------------------------------
# 6. Complete Gas Design
# ---------------------------------------------------------------------------

def complete_gas_design(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    pump_depth: float,
    target_rate: float,
    catalog_manager: "CatalogManager",
    vent_gas_pct: float = 0.0,
    wellhead_pressure: float = 100.0,
    apply_deterioration: bool = False,
    fixed_pump_model: str | None = None,
) -> dict:
    """Diseño de gas completo, de punta a punta (Brown §4.53103, Ejemplo 3).

    Los pasos, en orden:

        1. Calcular la presión de admisión (PIP) con el recorrido multifásico.
        2. Calcular la presión de descarga con el recorrido por el tubing.
        3. Evaluar el gas libre en la admisión y la fracción que entra (GIP).
        4. Correr el diseño por incrementos de presión.
        5. Evaluar el riesgo de bloqueo por gas y recomendar separador si hace
           falta.

    Args:
        reservoir: Propiedades del reservorio.
        fluid: PVT y composición del fluido.
        well: Geometría del pozo.
        pump_depth: Profundidad de asentamiento de la bomba [ft TVD].
        target_rate: Caudal bruto de líquido buscado [STB/d].
        catalog_manager: Catálogo de equipos cargado.
        vent_gas_pct: Fracción de gas libre venteada por el anular [0–1].
            0 = entra todo el gas (GIP 100 %), 1 = se ventea todo.
        wellhead_pressure: Presión fluyente en boca de pozo [psia] para el
            recorrido de descarga — pasar
            ``SurfaceConditions.wellhead_pressure_required`` si está
            disponible.

    Returns:
        dict con: ``pip``, ``p_discharge``, ``gip``,
        ``free_gas_ratio_at_intake``, ``gas_lock_risk``,
        ``deterioration_factor``, ``separator_recommendation`` e
        ``increment_design``.
    """
    from bes.core.multiphase import calculate_pip, calculate_discharge_pressure

    # --- Temperature at pump depth (linear profile) ---
    t_pump = (
        well.wellhead_temp
        + (pump_depth / well.total_depth) * (reservoir.reservoir_temp - well.wellhead_temp)
    )

    # --- 1. Pump Intake Pressure ---
    pip = calculate_pip(
        reservoir=reservoir,
        fluid=fluid,
        well=well,
        pump_setting_depth=pump_depth,
        target_rate=target_rate,
    )

    # --- 2. Pump Discharge Pressure ---
    p_discharge = calculate_discharge_pressure(
        fluid=fluid,
        tubing_id=well.tubing_id,
        pump_depth=pump_depth,
        wellhead_pressure=wellhead_pressure,
        target_rate=target_rate,
        t_pump=t_pump,
        t_wellhead=well.wellhead_temp,
    )

    # Sanity: discharge must exceed intake
    if p_discharge <= pip:
        p_discharge = pip + 1000.0  # minimum 1000 psi differential

    # --- 3. Free gas and GIP ---
    pb = fluid.bubble_point_pressure
    t = t_pump
    rs_at_pip = min(
        standing_rs(pip, t, fluid.oil_api, fluid.gas_sg, pb) if pb > 0 else fluid.gor,
        fluid.gor,
    )
    free_gas_at_intake = max(fluid.gor - rs_at_pip, 0.0)  # scf/STB oil

    # Volumetric free gas fraction at pump intake
    z_pip = gas_z_factor(pip, t, fluid.gas_sg)
    bg_pip = gas_bg(pip, t, z_pip)
    bo_pip = standing_bo(rs_at_pip, t, fluid.oil_api, fluid.gas_sg)
    bw_pip = water_bw(pip, t)

    wc = fluid.water_cut
    v_oil_pip = (1.0 - wc) * bo_pip
    v_water_pip = wc * bw_pip
    v_gas_pip = (1.0 - wc) * free_gas_at_intake * bg_pip
    v_total_pip = v_oil_pip + v_water_pip + v_gas_pip
    fg_ratio = v_gas_pip / v_total_pip if v_total_pip > 0.0 else 0.0

    # Gas vented is vent_gas_pct of the free gas
    gas_vented = free_gas_at_intake * vent_gas_pct
    gip = gas_ingestion_percentage(free_gas_at_intake, gas_vented)

    # --- 4. Gas lock risk and deterioration ---
    gas_risk = check_gas_lock_risk(fg_ratio * gip)
    det_factor = pump_deterioration_factor(fg_ratio * gip)

    # --- 5. Separator recommendation ---
    # Infer pump series from first qualifying catalog pump
    qualifying = catalog_manager.get_pumps_by_casing(well.casing_id)
    pump_series = qualifying[0].series if qualifying else "400"
    sep_rec = recommend_gas_separator(fg_ratio, pump_series)

    # --- 6. Pressure increment design ---
    inc_design = pressure_increment_design(
        reservoir=reservoir,
        fluid=fluid,
        p_intake=pip,
        p_discharge=p_discharge,
        target_rate=target_rate,
        catalog_manager=catalog_manager,
        gip=gip,
        water_cut=wc,
        increment_psi=200.0,
        apply_deterioration=apply_deterioration,
        fixed_pump_model=fixed_pump_model,
    )

    # --- 7. In-pump intake / discharge volumetric rates [bpd reservoir] ---
    intake_props = _mixture_volumes_and_density(pip, t, fluid, wc, gip)
    discharge_props = _mixture_volumes_and_density(p_discharge, t, fluid, wc, gip)
    intake_volume_bpd = target_rate * intake_props["v_total"]
    discharge_volume_bpd = target_rate * discharge_props["v_total"]

    return {
        "pip":                       pip,
        "p_discharge":               p_discharge,
        "gip":                       gip,
        "free_gas_ratio_at_intake":  fg_ratio,
        "intake_volume_bpd":         intake_volume_bpd,
        "discharge_volume_bpd":      discharge_volume_bpd,
        "gas_lock_risk":             gas_risk,
        "deterioration_factor":      det_factor,
        "separator_recommendation":  sep_rec,
        "increment_design":          inc_design,
    }
