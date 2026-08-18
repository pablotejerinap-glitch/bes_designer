"""Leyes de afinidad — la misma bomba a otra velocidad, diámetro o fluido.

Las curvas de catálogo se publican a una velocidad fija, con agua limpia
(SG = 1, µ = 1 cp) y **para una sola etapa**. Las leyes de afinidad dicen cómo
se mueve esa curva cuando cambian las condiciones::

    Q₂  = Q₁  · (N₂/N₁)  · (D₂/D₁)
    H₂  = H₁  · (N₂/N₁)² · (D₂/D₁)²
    HP₂ = HP₁ · (N₂/N₁)³ · (D₂/D₁)³ · (SG₂/SG₁)

En castellano: si la bomba gira al doble de vueltas, entrega el doble de
caudal, cuatro veces la altura y ocho veces la potencia.

Dos detalles que se prestan a confusión
---------------------------------------
El **rendimiento NO se escala**: queda igual. Eso es justamente lo que hace que
esto sea una transformación de semejanza y no un ajuste estadístico.

La **altura no lleva término de SG, pero la potencia sí**. Levantar una columna
de fluido hasta cierta altura da la misma altura sea cual sea el fluido; lo que
cambia es lo que cuesta hacerlo, porque un fluido más pesado pide más potencia.

Por qué se trabaja en hertz y no en rpm
---------------------------------------
Una bomba BES la mueve un motor de inducción, cuya velocidad sincrónica es
``120·f / polos``. El eje gira un poco más lento por el deslizamiento (unos
2.8 %: 3000 rpm sincrónicas a 50 Hz contra unas 2917 reales). Como el
deslizamiento es prácticamente el mismo a las dos frecuencias, **se cancela en
la división**::

    N₂/N₁ = f₂/f₁

Así que las leyes se pueden aplicar directamente sobre la frecuencia del
variador, sin arrastrar ninguna suposición de deslizamiento al resultado. Es
como se diseña con VSD en la práctica. :func:`synchronous_rpm` y
:func:`motor_rpm` existen sólo para mostrar en pantalla.

Dónde entra esto en el diseño
-----------------------------
Este módulo es sobre todo la pestaña «Leyes de afinidad», un banco de pruebas
independiente del diseño. Pero hay **una excepción importante**:
:func:`pump_at_frequency` sí interviene, y es obligatoria. El diseño lleva la
curva a la frecuencia real ANTES de filtrar el catálogo por rango de caudal;
sin eso, un pozo a 50 Hz se diseñaría contra la curva de 60 Hz y saldrían 44 %
menos etapas de las que necesita.

Contenido
---------
1. Las tres leyes, una por función (caudal, altura, potencia)
2. Inversión: qué frecuencia hace falta para un caudal dado
3. Velocidades del motor (sincrónica y real), sólo para mostrar
4. Potencia hidráulica y rendimiento
5. Escalado de una curva de catálogo completa
6. Traza de fórmulas para auditar el cálculo

Nomenclatura
------------
    Q       Caudal                                          [b/d]
    H       Altura (head) por etapa                         [ft]
    HP      Potencia al freno (brake horsepower)            [hp]
    N       Velocidad de giro                               [rpm]
    f       Frecuencia de alimentación                      [Hz]
    D       Diámetro del impulsor                           [in]
    SG      Gravedad específica del fluido                  [-]
    η       Rendimiento                                     [-]
    BEP     Best Efficiency Point: caudal de máximo rendimiento
    VSD     Variador de frecuencia

Referencias
-----------
Brown, K.E. "The Technology of Artificial Lift Methods", Vol. 2b, Tabla 4.21.
Apuntes de cátedra, Unidad N°9 (pág. 135).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bes.core.models import PumpCurve

# Hydraulic-horsepower constant for Q [b/d], H [ft], SG (see hydraulic_hp).
HYDRAULIC_HP_CONSTANT = 135_771.0

# Induction-motor slip typical of an ESP motor: 3000 rpm synchronous at 50 Hz
# against ~2917 rpm at the shaft. Display only — it cancels in every ratio.
TYPICAL_SLIP = 1.0 - 2917.0 / 3000.0

_DEFAULT_POLES = 2


def _ratios(
    freq_from: float, freq_to: float, diameter_ratio: float
) -> tuple[float, float]:
    """Validate and return ``(speed_ratio, diameter_ratio)``."""
    if freq_from <= 0:
        raise ValueError(f"freq_from must be > 0, got {freq_from}")
    if freq_to <= 0:
        raise ValueError(f"freq_to must be > 0, got {freq_to}")
    if diameter_ratio <= 0:
        raise ValueError(f"diameter_ratio must be > 0, got {diameter_ratio}")
    return freq_to / freq_from, diameter_ratio


def scale_flow(
    q: float, freq_from: float, freq_to: float, diameter_ratio: float = 1.0
) -> float:
    """Ley de caudal: ``Q₂ = Q₁·(N₂/N₁)·(D₂/D₁)``.

    El caudal va con la **primera** potencia de la relación de velocidades: al
    doble de vueltas, el doble de caudal.

    Args:
        q: Caudal en la condición de referencia [b/d o m³/d — la unidad pasa
            de largo, la función no la interpreta].
        freq_from: Frecuencia de referencia, la del catálogo [Hz]. Debe ser > 0.
        freq_to: Frecuencia buscada [Hz]. Debe ser > 0.
        diameter_ratio: Relación ``D₂/D₁``. 1.0 = impulsor sin recortar.

    Returns:
        Caudal en la condición buscada, en la misma unidad que ``q``.

    Raises:
        ValueError: Si alguna frecuencia o la relación de diámetros no es
            positiva.
    """
    n, d = _ratios(freq_from, freq_to, diameter_ratio)
    return q * n * d


def scale_head(
    h: float, freq_from: float, freq_to: float, diameter_ratio: float = 1.0
) -> float:
    """Head at the new speed/diameter: ``H₂ = H₁·(N₂/N₁)²·(D₂/D₁)²``.

    Head is independent of the fluid density, so no SG term appears here: a
    given impeller at a given speed develops the same head in feet whether it
    pumps water or brine.

    Args:
        h: Head at the reference condition [ft or m].
        freq_from: Reference (catalog) frequency [Hz].
        freq_to: Target frequency [Hz].
        diameter_ratio: ``D₂/D₁``.

    Returns:
        Head at the target condition, in the same unit as ``h``.
    """
    n, d = _ratios(freq_from, freq_to, diameter_ratio)
    return h * n ** 2 * d ** 2


def scale_power(
    hp: float,
    freq_from: float,
    freq_to: float,
    diameter_ratio: float = 1.0,
    sg_ratio: float = 1.0,
) -> float:
    """Ley de potencia: ``HP₂ = HP₁·(N₂/N₁)³·(D₂/D₁)³·(SG₂/SG₁)``.

    La potencia va con el **cubo** de la relación de velocidades: al doble de
    vueltas, ocho veces la potencia. Es la ley que más muerde y la razón por la
    que bajar un poco la frecuencia ahorra mucha energía.

    A diferencia de la altura, la potencia **sí** depende de la densidad: mover
    un fluido más pesado a la misma altura cuesta proporcionalmente más. Como
    las curvas de catálogo están levantadas con agua, al escalar desde catálogo
    se pasa como ``sg_ratio`` la gravedad específica del fluido producido.

    Args:
        hp: Potencia al freno en la condición de referencia [hp].
        freq_from: Frecuencia de referencia, la del catálogo [Hz].
        freq_to: Frecuencia buscada [Hz].
        diameter_ratio: Relación ``D₂/D₁``.
        sg_ratio: Relación ``SG₂/SG₁``. Debe ser > 0.

    Returns:
        Potencia al freno en la condición buscada [hp].

    Raises:
        ValueError: Si una frecuencia, la relación de diámetros o ``sg_ratio``
            no es positiva.
    """
    n, d = _ratios(freq_from, freq_to, diameter_ratio)
    if sg_ratio <= 0:
        raise ValueError(f"sg_ratio must be > 0, got {sg_ratio}")
    return hp * n ** 3 * d ** 3 * sg_ratio


def frequency_for_flow(
    flow_at_reference: float, target_flow: float, reference_frequency: float
) -> float:
    """Frecuencia que lleva la bomba al caudal buscado [Hz].

    Es la ley de caudal dada vuelta. Como el caudal es lineal con la
    velocidad, el despeje es directo::

        f₂ = f₁ · (Q₂/Q₁)

    Ésta es la pregunta que se hace de verdad al diseñar con variador —«¿a qué
    frecuencia consigo el caudal que quiero?»— y no la inversa.

    Args:
        flow_at_reference: Caudal conocido a ``reference_frequency`` [b/d].
            Debe ser > 0.
        target_flow: Caudal deseado [b/d]. Debe ser > 0.
        reference_frequency: Frecuencia a la que vale ``flow_at_reference`` [Hz].

    Returns:
        Frecuencia de alimentación necesaria [Hz].

    Raises:
        ValueError: Si algún argumento no es positivo.
    """
    if flow_at_reference <= 0:
        raise ValueError(f"flow_at_reference must be > 0, got {flow_at_reference}")
    if target_flow <= 0:
        raise ValueError(f"target_flow must be > 0, got {target_flow}")
    if reference_frequency <= 0:
        raise ValueError(
            f"reference_frequency must be > 0, got {reference_frequency}"
        )
    return reference_frequency * target_flow / flow_at_reference


def synchronous_rpm(freq_hz: float, poles: int = _DEFAULT_POLES) -> float:
    """Synchronous speed of the driving motor: ``120·f / polos`` [rpm]."""
    if freq_hz <= 0:
        raise ValueError(f"freq_hz must be > 0, got {freq_hz}")
    if poles <= 0:
        raise ValueError(f"poles must be > 0, got {poles}")
    return 120.0 * freq_hz / poles


def motor_rpm(
    freq_hz: float, poles: int = _DEFAULT_POLES, slip: float = TYPICAL_SLIP
) -> float:
    """Velocidad real del eje, ya descontado el deslizamiento [rpm].

        N = 120·f/polos · (1 − s)

    **Sólo para mostrar en pantalla.** Ningún resultado de este módulo depende
    del deslizamiento, porque se cancela en toda relación de afinidad.
    """
    if not (0.0 <= slip < 1.0):
        raise ValueError(f"slip must be in [0, 1), got {slip}")
    return synchronous_rpm(freq_hz, poles) * (1.0 - slip)


def hydraulic_hp(flow_bpd: float, head_ft: float, sg: float) -> float:
    """Potencia hidráulica entregada al fluido [hp].

        HHP = Q · Hd · SG / 135 771      (Q en b/d, Hd en ft)

    Es el trabajo útil: lo que efectivamente se le entrega al fluido. Junto con
    la potencia al freno que publica la curva de catálogo cierra la identidad
    del rendimiento, ``η = HHP / BHP``, que es como se controló la calidad de
    las curvas digitalizadas (ver ``tools/catalog_pipeline``).

    Args:
        flow_bpd: Caudal [b/d].
        head_ft: Altura total desarrollada [ft].
        sg: Gravedad específica del fluido bombeado.

    Returns:
        Potencia hidráulica [hp]. Devuelve cero si algún argumento no es
        positivo.
    """
    if flow_bpd <= 0 or head_ft <= 0 or sg <= 0:
        return 0.0
    return flow_bpd * head_ft * sg / HYDRAULIC_HP_CONSTANT


def pump_at_frequency(
    pump: "PumpCurve",
    frequency_hz: float,
    diameter_ratio: float = 1.0,
) -> "PumpCurve":
    """La misma bomba, tal como se comporta a otra frecuencia.

    **Esta función SÍ interviene en el diseño, y es obligatoria.** Las curvas de
    catálogo se publican a una sola frecuencia (60 Hz en todos los catálogos de
    este proyecto). Diseñar un pozo que va a girar a otra frecuencia contra la
    curva publicada está mal de tres maneras a la vez:

        - la altura por etapa se equivoca por ``(f₂/f₁)²``
        - la potencia por etapa, por ``(f₂/f₁)³``
        - el rango de caudal recomendado, por ``f₂/f₁``

    Ese tercer punto es el más traicionero: con el rango corrido, la bomba
    correcta puede ni siquiera entrar en la lista de candidatas.

    Devuelve un ``PumpCurve`` de verdad y no un diccionario, a propósito: así
    todo lo que viene después —el filtro por rango de caudal, la interpolación
    de la curva, el conteo de etapas, la distancia al BEP del ranking, la
    presión a caudal cero de la verificación de carcasa— sigue funcionando sin
    cambios, pero sobre números que ya están a la frecuencia real del pozo.

    El resultado declara ``catalog_frequency_hz = frequency_hz``, así que
    escalar una curva ya escalada no hace nada: la operación es idempotente.

    Args:
        pump: Bomba de catálogo, a su frecuencia publicada.
        frequency_hz: Frecuencia a la que va a girar realmente [Hz].
        diameter_ratio: Relación ``D₂/D₁`` si el impulsor está recortado.

    Returns:
        Un ``PumpCurve`` nuevo. La identidad, la geometría y las carcasas pasan
        intactas — lo único que se mueve es la curva hidráulica.

    Raises:
        ValueError: Si ``frequency_hz`` o ``diameter_ratio`` no es positivo.
    """
    from bes.core.models import PumpCurve, PumpPerformancePoint

    base = pump.catalog_frequency_hz or 60.0
    if frequency_hz == base and diameter_ratio == 1.0:
        return pump

    n, d = _ratios(base, frequency_hz, diameter_ratio)
    points = [
        PumpPerformancePoint(
            flow_rate=scale_flow(p.flow_rate, base, frequency_hz, diameter_ratio),
            head_per_stage=scale_head(
                p.head_per_stage, base, frequency_hz, diameter_ratio
            ),
            # Sin SG: el catálogo es para agua y el HP del fluido real se
            # corrige aguas abajo (calculate_motor_hp multiplica por sg).
            hp_per_stage=scale_power(
                p.hp_per_stage, base, frequency_hz, diameter_ratio
            ),
            efficiency=p.efficiency,      # invariante bajo las leyes
        )
        for p in pump.points
    ]
    return PumpCurve(
        manufacturer=pump.manufacturer,
        series=pump.series,
        model=pump.model,
        od=pump.od,
        min_flow=scale_flow(pump.min_flow, base, frequency_hz, diameter_ratio),
        max_flow=scale_flow(pump.max_flow, base, frequency_hz, diameter_ratio),
        bep_flow=scale_flow(pump.bep_flow, base, frequency_hz, diameter_ratio),
        points=points,
        max_stages=pump.max_stages,
        housing_options=list(pump.housing_options),
        housing_pressure_limit_psi=pump.housing_pressure_limit_psi,
        housings=list(pump.housings),
        catalog_frequency_hz=frequency_hz,
    )


def scale_curve(
    pump: "PumpCurve",
    to_frequency_hz: float,
    from_frequency_hz: float | None = None,
    diameter_ratio: float = 1.0,
    sg_ratio: float = 1.0,
) -> dict:
    """Reescala una curva de catálogo completa a otra frecuencia, diámetro y fluido.

    Todos los puntos se mueven juntos —el caudal con la primera potencia de la
    relación de velocidades, la altura con el cuadrado, la potencia con el
    cubo—, así que la curva entera, su rango recomendado de operación y su BEP
    se corren de forma consistente. El rendimiento pasa sin cambios, que es
    justamente el contenido físico de las leyes.

    Args:
        pump: Bomba de catálogo cuya curva se va a reescalar.
        to_frequency_hz: Frecuencia buscada [Hz].
        from_frequency_hz: Frecuencia a la que está publicada la curva [Hz].
            Si se omite, se toma el ``catalog_frequency_hz`` de la bomba.
        diameter_ratio: Relación ``D₂/D₁`` si el impulsor está recortado.
            1.0 = tal como viene publicada.
        sg_ratio: Relación ``SG₂/SG₁`` para la ley de potencia. Las curvas de
            catálogo son de agua, así que pasar el SG del fluido producido da
            la potencia al freno sobre el fluido real.

    Returns:
        dict con ``frequency_hz``, ``from_frequency_hz``, ``speed_ratio``,
        ``synchronous_rpm``, ``motor_rpm``, ``min_flow``, ``max_flow``,
        ``bep_flow``, ``bep_head_per_stage``, ``bep_hp_per_stage``,
        ``bep_efficiency`` y ``points`` (lista de dicts con ``flow_bpd``,
        ``head_ft_per_stage``, ``hp_per_stage`` y ``efficiency``).

    Raises:
        ValueError: Si una frecuencia, la relación de diámetros o ``sg_ratio``
            no es positiva.
    """
    base = from_frequency_hz or getattr(pump, "catalog_frequency_hz", 60.0) or 60.0
    n, _ = _ratios(base, to_frequency_hz, diameter_ratio)

    points = [
        {
            "flow_bpd": scale_flow(p.flow_rate, base, to_frequency_hz, diameter_ratio),
            "head_ft_per_stage": scale_head(
                p.head_per_stage, base, to_frequency_hz, diameter_ratio
            ),
            "hp_per_stage": scale_power(
                p.hp_per_stage, base, to_frequency_hz, diameter_ratio, sg_ratio
            ),
            "efficiency": p.efficiency,     # invariante bajo las leyes
        }
        for p in pump.points
    ]

    # El BEP se mueve con el caudal, así que se relee sobre la curva escalada.
    bep_flow = scale_flow(pump.bep_flow, base, to_frequency_hz, diameter_ratio)
    at_bep = min(points, key=lambda pt: abs(pt["flow_bpd"] - bep_flow)) if points else {}

    return {
        "frequency_hz": to_frequency_hz,
        "from_frequency_hz": base,
        "speed_ratio": n,
        "diameter_ratio": diameter_ratio,
        "sg_ratio": sg_ratio,
        "synchronous_rpm": synchronous_rpm(to_frequency_hz),
        "motor_rpm": motor_rpm(to_frequency_hz),
        "min_flow": scale_flow(pump.min_flow, base, to_frequency_hz, diameter_ratio),
        "max_flow": scale_flow(pump.max_flow, base, to_frequency_hz, diameter_ratio),
        "bep_flow": bep_flow,
        "bep_head_per_stage": at_bep.get("head_ft_per_stage", 0.0),
        "bep_hp_per_stage": at_bep.get("hp_per_stage", 0.0),
        "bep_efficiency": at_bep.get("efficiency", 0.0),
        "points": points,
    }


# --------------------------------------------------------------------------
# Traza de fórmulas
# --------------------------------------------------------------------------

def affinity_trace(
    q: float,
    h: float,
    hp: float,
    freq_from: float,
    freq_to: float,
    diameter_ratio: float = 1.0,
    sg_ratio: float = 1.0,
    poles: int = _DEFAULT_POLES,
) -> list[dict]:
    """Las tres leyes de afinidad aplicadas a un punto, con sus números.

    Función aparte, igual que :func:`bes.core.ipr.ipr_trace`, para no ensuciar
    la firma de ``scale_flow`` / ``scale_head`` / ``scale_power``, que usa todo
    el motor. Llama a esas mismas funciones, así que la traza no puede separarse
    de la cuenta.

    Args:
        q: Caudal en la condición de referencia [b/d].
        h: Altura en la condición de referencia [ft].
        hp: Potencia al eje en la condición de referencia [hp].
        freq_from: Frecuencia de referencia (la del catálogo) [Hz].
        freq_to: Frecuencia de operación [Hz].
        diameter_ratio: ``D₂/D₁``. 1.0 = impulsor sin recortar.
        sg_ratio: ``SG₂/SG₁``. 1.0 = se queda en la curva de agua.
        poles: Polos del motor, para la velocidad sincrónica.

    Returns:
        Lista de dicts de :class:`bes.core.formulas.Formula`.
    """
    from bes.core.formulas import FormulaTrace

    n = freq_to / freq_from
    q2 = scale_flow(q, freq_from, freq_to, diameter_ratio)
    h2 = scale_head(h, freq_from, freq_to, diameter_ratio)
    hp2 = scale_power(hp, freq_from, freq_to, diameter_ratio, sg_ratio)

    trace = FormulaTrace()
    trace.add(
        "afinidad_caudal",
        {"Q₁": q, "N₂/N₁": n, "D₂/D₁": diameter_ratio}, q2,
        context=f"De {freq_from:.0f} Hz a {freq_to:.0f} Hz." + (
            "" if diameter_ratio == 1.0 else
            f" Con el impulsor recortado a {diameter_ratio:.3f} del original."
        ),
    )
    trace.add(
        "afinidad_altura",
        {"H₁": h, "N₂/N₁": n, "D₂/D₁": diameter_ratio}, h2,
        context=f"La relación va al cuadrado: {n:.4f}² = {n ** 2:.4f}.",
    )
    trace.add(
        "afinidad_potencia",
        {"HP₁": hp, "N₂/N₁": n, "D₂/D₁": diameter_ratio, "SG₂/SG₁": sg_ratio},
        hp2,
        context=f"La relación va al cubo: {n:.4f}³ = {n ** 3:.4f}." + (
            " El SG es 1.0, o sea que el resultado sigue siendo de agua."
            if sg_ratio == 1.0 else ""
        ),
    )
    trace.add(
        "afinidad_rpm_sincronica",
        {"f": freq_to, "polos": poles}, synchronous_rpm(freq_to, poles),
        context=f"Con deslizamiento típico el eje giraría a "
                f"{motor_rpm(freq_to, poles):,.0f} rpm, pero el deslizamiento "
                f"se cancela en todas las relaciones de arriba.",
    )
    trace.add(
        "afinidad_hp_hidraulico",
        {"Q": q2, "H": h2, "SG": sg_ratio}, hydraulic_hp(q2, h2, sg_ratio),
        context="Con la potencia al eje cierra el rendimiento η = HHP / BHP.",
    )
    return trace.as_list()


def frequency_for_flow_trace(
    flow_at_reference: float, target_flow: float, reference_frequency: float
) -> list[dict]:
    """La ley del caudal invertida: a qué frecuencia sale el caudal que quiero.

    Args:
        flow_at_reference: Caudal conocido a ``reference_frequency`` [b/d].
        target_flow: Caudal deseado [b/d].
        reference_frequency: Frecuencia a la que vale el caudal conocido [Hz].

    Returns:
        Lista de dicts de :class:`bes.core.formulas.Formula`.
    """
    from bes.core.formulas import FormulaTrace

    f2 = frequency_for_flow(flow_at_reference, target_flow, reference_frequency)
    trace = FormulaTrace()
    trace.add(
        "afinidad_frecuencia_objetivo",
        {"f₁": reference_frequency, "Q₂": target_flow, "Q₁": flow_at_reference},
        f2,
        context="Es la pregunta que hace un diseño con VSD: no «qué caudal da "
                "a esta frecuencia» sino «a qué frecuencia da el que quiero».",
    )
    return trace.as_list()
