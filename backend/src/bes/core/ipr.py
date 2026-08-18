"""
IPR — Curva de comportamiento de afluencia del reservorio.

La IPR (Inflow Performance Relationship) relaciona el caudal que aporta el
reservorio con la presión de fondo fluyente. Es el punto de partida del diseño:
fija la Pwf en las perforaciones para el caudal objetivo.

El simulador implementa **tres métodos**, y solo tres:

    1. Lineal (Darcy)      q = J · (Pr − Pwf)
    2. Vogel GENERALIZADO  recta arriba de la burbuja, Vogel abajo
    3. Fetkovich (1973)    q = C · (Pr² − Pwf²)^n

La presión de burbuja parte la IPR en dos
-----------------------------------------
**Arriba de Pb la IPR es una RECTA.** Con la presión de fondo por encima de la
de burbuja el flujo dentro del reservorio es monofásico y vale Darcy; recién
cuando Pwf baja de Pb se libera gas, cae la permeabilidad relativa al petróleo
y la curva se dobla. Vogel publicó su correlación para reservorios **saturados**
y sólo se aplica a ese tramo::

    Pwf >= Pb :  q = J · (Pr − Pwf)
    Pwf <  Pb :  q = J·(Pr − Pb) + (J·Pb/1.8)·[1 − 0.2·(Pwf/Pb) − 0.8·(Pwf/Pb)²]

Los dos tramos empalman con la misma pendiente, así que la curva es continua y
sin quiebre. Con el reservorio saturado (Pb >= Pr) la fórmula se reduce sola a
Vogel puro. Ver :func:`vogel_composite_ipr`.

Fetkovich **no** lleva este corte: su ajuste de C y n ya absorbe el
comportamiento bifásico (Beggs ec. 2-58). El lineal tampoco, porque es la recta
por definición — pero :func:`ipr_validity_warning` avisa cuando se lo usa
debajo de la burbuja.

Contenido
---------
1. Los tres métodos IPR
2. Ajuste de los parámetros a partir de un ensayo de producción
3. Pwf necesaria para un caudal objetivo (inversión de la IPR)
4. Generación de la curva completa para graficar
5. Auxiliares internos

Nomenclatura
------------
    Pr      Presión estática (media) del reservorio        [psia]
    Pwf     Presión de fondo fluyente                       [psia]
    Pb      Presión de burbuja                              [psia]
    q       Caudal bruto de líquido en superficie           [STB/d]
    J       Índice de productividad (PI)                    [STB/d/psi]
    q_max   Caudal máximo de Vogel, a Pwf = 0               [STB/d]
    AOF     Absolute Open Flow: caudal a Pwf = 0            [STB/d]
    C, n    Coeficiente y exponente de Fetkovich

Referencias
-----------
Brown, K.E. "The Technology of Artificial Lift Methods", Vol. 2b, §4.522
    y Figura 4.55.
Vogel, J.V. (1968). "Inflow Performance Relationships for Solution-Gas Drive
    Wells". Journal of Petroleum Technology.
Beggs, H.D. "Production Optimization Using Nodal Analysis", §2 — el Vogel
    generalizado para reservorios subsaturados (ecs. 2-38 y 2-53) y los
    ejemplos 2-2, 2-5B y 2-7A, que son la regresión de este módulo.
Fetkovich, M.J. (1973). "The Isochronal Testing of Oil Wells". SPE 4529.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from bes.core.models import IPRMethod, Reservoir


# ===========================================================================
# 1. LOS TRES MÉTODOS IPR
# ===========================================================================

def linear_ipr(pr: float, pwf: float, pi: float) -> float:
    """Método LINEAL (Darcy) — índice de productividad constante.

        q = J · (Pr − Pwf)

    Válido para flujo monofásico, es decir con el reservorio sobre la presión
    de burbuja (Pwf >= Pb). En ese caso el caudal crece en línea recta con la
    caída de presión: la pendiente es el índice de productividad J.

    Args:
        pr: Presión estática del reservorio, Pr [psia].
        pwf: Presión de fondo fluyente, Pwf [psia]. Debe cumplir 0 <= Pwf <= Pr.
        pi: Índice de productividad, J [STB/d/psi]. Debe ser > 0.

    Returns:
        Caudal de líquido, q [STB/d].

    Raises:
        ValueError: Si pi <= 0 o pwf > pr.
    """
    if pi <= 0:
        raise ValueError(f"pi must be > 0, got {pi}")
    if pwf > pr:
        raise ValueError(f"pwf ({pwf}) cannot exceed pr ({pr})")

    return pi * (pr - pwf)


def vogel_ipr(pr: float, pwf: float, qmax: float) -> float:
    """Método de VOGEL (1968) — reservorios con empuje por gas en solución.

        q / q_max = 1 − 0.2·(Pwf/Pr) − 0.8·(Pwf/Pr)²

    Válido cuando la presión de fondo cae por debajo de la de burbuja
    (Pwf < Pb): al liberarse gas dentro del reservorio, el flujo pasa a ser
    bifásico y la IPR deja de ser una recta para curvarse hacia abajo.

    Args:
        pr: Presión de referencia, Pr [psia] (la estática, o la de burbuja).
        pwf: Presión de fondo fluyente, Pwf [psia]. Debe cumplir 0 <= Pwf <= Pr.
        qmax: Caudal máximo a Pwf = 0, q_max [STB/d]. Debe ser > 0.

    Returns:
        Caudal de líquido, q [STB/d].

    Raises:
        ValueError: Si qmax <= 0 o pwf > pr.
    """
    if qmax <= 0:
        raise ValueError(f"qmax must be > 0, got {qmax}")
    if pwf > pr:
        raise ValueError(f"pwf ({pwf}) cannot exceed pr ({pr})")
    if pr == 0:
        return 0.0

    x = pwf / pr
    return qmax * (1.0 - 0.2 * x - 0.8 * x ** 2)


def effective_bubble_point(pr: float, pb: float) -> float:
    """Presión de burbuja acotada a la estática [psia].

    Si Pb >= Pr el reservorio está **saturado**: hay gas libre desde el vamos y
    no existe tramo monofásico. Acotando Pb a Pr, la ecuación compuesta se
    reduce sola a Vogel puro, sin necesitar un caso aparte.
    """
    return min(pb, pr) if pb > 0 else pr


def vogel_composite_ipr(pr: float, pb: float, pwf: float, pi: float) -> float:
    """VOGEL GENERALIZADO — recta arriba de la burbuja, Vogel abajo.

    Es el método que corresponde a un reservorio **subsaturado** (Pr > Pb), que
    es el caso normal. Mientras la presión de fondo se mantiene por encima de la
    de burbuja el flujo es monofásico y la IPR es una **recta**; recién cuando
    Pwf baja de Pb se libera gas, el flujo se hace bifásico y la curva se dobla::

        Pwf >= Pb :  q = J · (Pr − Pwf)                        ← recta
        Pwf <  Pb :  q = q_b + (J·Pb/1.8)·[1 − 0.2·(Pwf/Pb) − 0.8·(Pwf/Pb)²]

    con ``q_b = J · (Pr − Pb)``, el caudal justo al llegar a la burbuja.

    Los dos tramos **empalman con la misma pendiente** en Pwf = Pb, así que la
    curva no tiene quiebre: la derivada de Vogel en su origen vale J.

    Con un reservorio **saturado** (Pb >= Pr) la fórmula se reduce sola a Vogel
    puro: ``q_b = 0`` y queda ``q = (J·Pr/1.8)·[1 − 0.2x − 0.8x²]``, o sea
    :func:`vogel_ipr` con ``q_max = J·Pr/1.8``. No hace falta un caso aparte.

    Args:
        pr: Presión estática del reservorio, Pr [psia].
        pb: Presión de burbuja, Pb [psia].
        pwf: Presión de fondo fluyente, Pwf [psia]. Debe cumplir 0 <= Pwf <= Pr.
        pi: Índice de productividad, J [STB/d/psi], la pendiente del tramo
            recto. Debe ser > 0.

    Returns:
        Caudal de líquido, q [STB/d].

    Raises:
        ValueError: Si pi <= 0 o pwf > pr.

    Referencia:
        Beggs, *Production Optimization Using Nodal Analysis*, §2, ecs. 2-38 y
        2-53 («Undersaturated Reservoirs»). Brown Vol. 2b §4.522.
    """
    if pi <= 0:
        raise ValueError(f"pi must be > 0, got {pi}")
    if pwf > pr:
        raise ValueError(f"pwf ({pwf}) cannot exceed pr ({pr})")

    pb_ef = effective_bubble_point(pr, pb)

    if pwf >= pb_ef:
        return pi * (pr - pwf)

    q_b = pi * (pr - pb_ef)
    x = pwf / pb_ef
    return q_b + (pi * pb_ef / 1.8) * (1.0 - 0.2 * x - 0.8 * x ** 2)


def fetkovich_ipr(pr: float, pwf: float, c: float, n: float) -> float:
    """Método de FETKOVICH (1973) — ecuación empírica de contrapresión.

        q = C · (Pr² − Pwf²)^n

    Generaliza la ecuación de contrapresión de los pozos de gas al caso del
    petróleo. Los dos parámetros salen de un ensayo isocronal multi-caudal:

        n = 1.0   flujo laminar (Darcy)
        n = 0.5   flujo totalmente turbulento

    En la práctica n cae entre 0.5 y 1.0.

    Args:
        pr: Presión estática del reservorio, Pr [psia].
        pwf: Presión de fondo fluyente, Pwf [psia]. Debe cumplir 0 <= Pwf <= Pr.
        c: Coeficiente de entregabilidad, C [STB/d/psia^(2n)]. Debe ser > 0.
        n: Exponente de flujo, n [-]. Debe ser > 0; típicamente 0.5 <= n <= 1.0.

    Returns:
        Caudal de líquido, q [STB/d].

    Raises:
        ValueError: Si c <= 0, n <= 0 o pwf > pr.
    """
    if c <= 0:
        raise ValueError(f"c must be > 0, got {c}")
    if n <= 0:
        raise ValueError(f"n must be > 0, got {n}")
    if pwf > pr:
        raise ValueError(f"pwf ({pwf}) cannot exceed pr ({pr})")

    return c * (pr ** 2 - pwf ** 2) ** n


# ===========================================================================
# 2. AJUSTE DE LOS PARÁMETROS A PARTIR DE UN ENSAYO DE PRODUCCIÓN
# ===========================================================================
#
# Ni J, ni q_max, ni C se miden en el pozo: se deducen. Lo que se mide es un
# punto de ensayo estabilizado (Pwf_ensayo, q_ensayo) y la presión estática.
# Las funciones de esta sección invierten cada método para que la curva pase
# exactamente por ese punto medido.
# ---------------------------------------------------------------------------

def vogel_qmax_from_test(pr: float, pwf_test: float, q_test: float) -> float:
    """Despeja el q_max de Vogel a partir de un punto de ensayo.

    Se invierte la ecuación de Vogel:

        q_max = q_ensayo / [ 1 − 0.2·(Pwf_ensayo/Pr) − 0.8·(Pwf_ensayo/Pr)² ]

    Args:
        pr: Presión estática del reservorio, Pr [psia]. Debe ser > 0.
        pwf_test: Pwf medida durante el ensayo [psia]. Debe cumplir 0 <= Pwf < Pr.
        q_test: Caudal medido durante el ensayo [STB/d]. Debe ser > 0.

    Returns:
        Caudal máximo de Vogel, q_max a Pwf = 0 [STB/d].

    Raises:
        ValueError: Si el punto de ensayo no es físicamente válido.
    """
    if q_test <= 0:
        raise ValueError(f"q_test must be > 0, got {q_test}")
    if pr <= 0:
        raise ValueError(f"pr must be > 0, got {pr}")
    if pwf_test >= pr:
        raise ValueError(
            f"pwf_test ({pwf_test}) must be < pr ({pr}) to have meaningful drawdown"
        )

    x = pwf_test / pr
    denominador = 1.0 - 0.2 * x - 0.8 * x ** 2
    if denominador <= 0:
        raise ValueError(
            f"Vogel denominator is non-positive ({denominador:.6f}) for "
            f"pwf_test/pr = {x:.4f}. Test point is outside the valid range."
        )

    return q_test / denominador


def vogel_j_from_test(
    pr: float, pb: float, pwf_test: float, q_test: float
) -> float:
    """Despeja el índice de productividad J del Vogel generalizado.

    Hay **dos casos**, según dónde haya caído la Pwf del ensayo (Beggs §2):

    *Caso 1 — el ensayo está sobre la burbuja* (Pwf_ensayo >= Pb). El punto cae
    en el tramo recto, así que J sale directo::

        J = q_ensayo / (Pr − Pwf_ensayo)

    *Caso 2 — el ensayo está bajo la burbuja* (Pwf_ensayo < Pb). El punto cae en
    el tramo curvo, y hay que invertir la ecuación compuesta::

        J = q_ensayo / { (Pr − Pb) + (Pb/1.8)·[1 − 0.2·(Pwf/Pb) − 0.8·(Pwf/Pb)²] }

    Es el paso que la app se salteaba: tomaba el q_max de Vogel puro desde Pr,
    lo que sobreestima J en ~25 % en un pozo subsaturado típico.

    Args:
        pr: Presión estática, Pr [psia]. Debe ser > 0.
        pb: Presión de burbuja, Pb [psia].
        pwf_test: Pwf medida en el ensayo [psia]. 0 <= Pwf < Pr.
        q_test: Caudal medido en el ensayo [STB/d]. Debe ser > 0.

    Returns:
        Índice de productividad J [STB/d/psi].

    Raises:
        ValueError: Si el punto de ensayo no es físicamente válido.

    Referencia:
        Beggs, *Production Optimization*, §2, Ejemplo 2-5B (Caso 2) y
        procedimiento «Case 1 Procedure».
    """
    if q_test <= 0:
        raise ValueError(f"q_test must be > 0, got {q_test}")
    if pr <= 0:
        raise ValueError(f"pr must be > 0, got {pr}")
    if pwf_test >= pr:
        raise ValueError(
            f"pwf_test ({pwf_test}) must be < pr ({pr}) to have meaningful drawdown"
        )

    pb_ef = effective_bubble_point(pr, pb)

    if pwf_test >= pb_ef:
        # Caso 1: el ensayo cae en el tramo recto.
        return q_test / (pr - pwf_test)

    # Caso 2: el ensayo cae en el tramo de Vogel.
    x = pwf_test / pb_ef
    corchete = 1.0 - 0.2 * x - 0.8 * x ** 2
    denominador = (pr - pb_ef) + (pb_ef / 1.8) * corchete
    if denominador <= 0:
        raise ValueError(
            f"El denominador del Vogel compuesto es no positivo "
            f"({denominador:.6f}): el punto de ensayo está fuera de rango."
        )
    return q_test / denominador


def vogel_aof(pr: float, pb: float, pi: float) -> float:
    """AOF del Vogel generalizado: el caudal a Pwf = 0 [STB/d].

        AOF = J·(Pr − Pb) + J·Pb/1.8

    El primer término es lo que aporta el tramo recto hasta la burbuja; el
    segundo, lo que agrega el tramo de Vogel de Pb hasta cero.
    """
    pb_ef = effective_bubble_point(pr, pb)
    return pi * (pr - pb_ef) + pi * pb_ef / 1.8


def productivity_index_from_test(
    pr: float,
    pwf_test: float,
    q_test: float,
    method: IPRMethod,
    fetkovich_n: float | None = None,
    bubble_point: float | None = None,
) -> dict:
    """Deduce los parámetros de entregabilidad del pozo desde un ensayo.

    Un ensayo estabilizado da un punto (Pwf_ensayo, q_ensayo). Con ese punto y
    la presión estática se ajusta el método IPR elegido:

    LINEAL
        J = q_ensayo / (Pr − Pwf_ensayo)          la recta por el punto medido
        AOF = J · Pr

    VOGEL
        q_max se despeja con vogel_qmax_from_test().
        Se reporta además el J equivalente de la tangente:  J = 1.8 · q_max / Pr
        (es la misma relación que usa el resto del módulo al revés,
        q_max = J · Pr / 1.8, así que la curva pasa por el punto de ensayo).
        AOF = q_max

    FETKOVICH
        Un solo punto no alcanza para ajustar C y n a la vez: son dos incógnitas
        y una sola ecuación. Por eso n viene del ensayo isocronal (o se asume
        1.0 = laminar) y solo se despeja C:

            C = q_ensayo / (Pr² − Pwf_ensayo²)^n

        El J que se devuelve es la secante en el punto de ensayo, meramente
        informativo: la IPR de Fetkovich la manejan C y n.

    Args:
        pr: Presión estática del reservorio, Pr [psia]. Debe ser > 0.
        pwf_test: Pwf estabilizada medida en el ensayo [psia]. 0 <= Pwf < Pr.
        q_test: Caudal bruto estabilizado medido en el ensayo [STB/d]. > 0.
        method: Método IPR a ajustar.
        fetkovich_n: Exponente n de Fetkovich. Solo lo usa FETKOVICH; si se
            omite se toma 1.0 (laminar).
        bubble_point: Presión de burbuja, Pb [psia]. **La usa VOGEL** para
            separar el tramo recto del curvo. Si se omite se toma Pb = Pr, o
            sea reservorio saturado y Vogel puro — que es lo que hacía el
            módulo antes, y sobreestima J en un reservorio subsaturado.

    Returns:
        dict con:
          - ``productivity_index``  J [STB/d/psi] coherente con el método
          - ``drawdown_psi``        Pr − Pwf_ensayo [psi]
          - ``aof``                 caudal a Pwf = 0 según el ajuste [STB/d]
          - ``qmax_vogel``          q_max de Vogel; None salvo VOGEL
          - ``fetkovich_c`` / ``fetkovich_n``   None salvo FETKOVICH

    Raises:
        ValueError: Si el punto de ensayo no es válido o el método no existe.
    """
    if pr <= 0:
        raise ValueError(f"pr must be > 0, got {pr}")
    if q_test <= 0:
        raise ValueError(f"q_test must be > 0, got {q_test}")
    if pwf_test < 0:
        raise ValueError(f"pwf_test must be >= 0, got {pwf_test}")
    if pwf_test >= pr:
        raise ValueError(
            f"pwf_test ({pwf_test}) must be < pr ({pr}): a test with no "
            f"draw-down carries no deliverability information"
        )

    from bes.core.formulas import FormulaTrace
    trace = FormulaTrace()

    drawdown = pr - pwf_test
    trace.add("ajuste_drawdown", {"Pr": pr, "Pwf": pwf_test}, drawdown)
    resultado: dict = {
        "drawdown_psi": drawdown,
        "qmax_vogel": None,
        "fetkovich_c": None,
        "fetkovich_n": None,
    }

    if method is IPRMethod.LINEAR:
        pi = q_test / drawdown
        trace.add(
            "ajuste_j_lineal",
            {"q_ensayo": q_test, "Pr": pr, "Pwf": pwf_test}, pi,
        )
        trace.add("ajuste_aof_lineal", {"J": pi, "Pr": pr}, pi * pr)
        resultado["productivity_index"] = pi
        resultado["aof"] = pi * pr
        resultado["formulas"] = trace.as_list()
        return resultado

    if method is IPRMethod.VOGEL:
        pb_ef = effective_bubble_point(pr, bubble_point or pr)
        saturado = pb_ef >= pr
        bajo_burbuja = pwf_test < pb_ef

        pi = vogel_j_from_test(pr, pb_ef, pwf_test, q_test)

        if saturado:
            trace.add(
                "ajuste_j_vogel_saturado",
                {"q_max": q_test / (1 - 0.2 * (pwf_test / pr)
                                    - 0.8 * (pwf_test / pr) ** 2), "Pr": pr},
                pi,
                context=(
                    f"Pb ({bubble_point:.0f} psi) >= Pr ({pr:.0f} psi): el "
                    f"reservorio ya está saturado, así que no hay tramo recto "
                    f"y vale Vogel puro en todo el rango."
                    if bubble_point is not None else
                    f"Sin presión de burbuja se asume Pb = Pr ({pr:.0f} psi), "
                    f"o sea reservorio saturado y Vogel puro. Pasar la Pb real "
                    f"habilita el tramo recto del Vogel generalizado."
                ),
            )
        elif bajo_burbuja:
            x = pwf_test / pb_ef
            trace.add(
                "ajuste_j_vogel_bajo_pb",
                {"q_ensayo": q_test, "Pr": pr, "Pb": pb_ef, "Pwf": pwf_test},
                pi,
                context=f"El ensayo se hizo a {pwf_test:.0f} psi, por DEBAJO de "
                        f"la burbuja ({pb_ef:.0f} psi), así que cae en el tramo "
                        f"curvo. Pwf/Pb = {x:.4f} y el corchete vale "
                        f"{1 - 0.2*x - 0.8*x**2:.4f}. Despejar J con Vogel puro "
                        f"desde Pr —ignorando la burbuja— lo sobreestima.",
            )
        else:
            trace.add(
                "ajuste_j_vogel_sobre_pb",
                {"q_ensayo": q_test, "Pr": pr, "Pwf": pwf_test}, pi,
                context=f"El ensayo se hizo a {pwf_test:.0f} psi, por ENCIMA de "
                        f"la burbuja ({pb_ef:.0f} psi): cae en el tramo recto, "
                        f"así que J sale directo de la pendiente.",
            )

        q_b = pi * (pr - pb_ef)
        if not saturado:
            trace.add("ajuste_qb", {"J": pi, "Pr": pr, "Pb": pb_ef}, q_b)

        aof = vogel_aof(pr, pb_ef, pi)
        trace.add("ajuste_aof_vogel", {"J": pi, "Pr": pr, "Pb": pb_ef}, aof)

        resultado["productivity_index"] = pi
        resultado["qmax_vogel"] = aof
        resultado["aof"] = aof
        resultado["formulas"] = trace.as_list()
        return resultado

    if method is IPRMethod.FETKOVICH:
        n = 1.0 if fetkovich_n is None else fetkovich_n
        if n <= 0:
            raise ValueError(f"fetkovich_n must be > 0, got {n}")
        c = q_test / (pr ** 2 - pwf_test ** 2) ** n
        trace.add(
            "ajuste_fetkovich_c",
            {"q_ensayo": q_test, "Pr": pr, "Pwf": pwf_test, "n": n}, c,
        )
        aof = fetkovich_ipr(pr, 0.0, c, n)
        trace.add("ajuste_aof_fetkovich", {"C": c, "Pr": pr, "n": n}, aof)
        resultado["productivity_index"] = q_test / drawdown   # secante, informativo
        resultado["fetkovich_c"] = c
        resultado["fetkovich_n"] = n
        resultado["aof"] = aof
        resultado["formulas"] = trace.as_list()
        return resultado

    raise ValueError(f"Unsupported IPR method: {method}")


# ===========================================================================
# 3. Pwf NECESARIA PARA UN CAUDAL OBJETIVO
# ===========================================================================

def calculate_pwf_for_target_rate(
    reservoir: Reservoir,
    target_rate: float,
    fetkovich_c: float | None = None,
    fetkovich_n: float | None = None,
) -> float:
    """Presión de fondo fluyente que hace falta para producir un caudal dado.

    Es la IPR usada al revés: en lugar de "dada la Pwf, ¿cuánto aporta?", se
    pregunta "para este caudal, ¿a qué Pwf hay que bajar?".

    LINEAL      tiene despeje directo:   Pwf = Pr − q / J
    VOGEL       y FETKOVICH no se despejan a mano, así que se resuelve
                numéricamente buscando la raíz de  q(Pwf) − q_objetivo = 0
                entre Pwf = 0 y Pwf = Pr (método de Brent).

    Args:
        reservoir: Reservorio (Pr, Pb, J, método IPR).
        target_rate: Caudal bruto objetivo, q [STB/d]. Debe ser > 0.
        fetkovich_c: Coeficiente C. Si se omite se toma de ``reservoir``.
        fetkovich_n: Exponente n. Si se omite se toma de ``reservoir``, y si
            tampoco está, 1.0.

    Returns:
        Presión de fondo fluyente requerida, Pwf [psia].

    Raises:
        ValueError: Si el caudal pedido supera el AOF del reservorio, si es
            <= 0, o si falta el coeficiente C con el método FETKOVICH.
    """
    if target_rate <= 0:
        raise ValueError(f"target_rate must be > 0, got {target_rate}")

    pr = reservoir.static_pressure
    pi = reservoir.productivity_index
    method = reservoir.ipr_method
    fetkovich_c, fetkovich_n = _resolve_fetkovich_params(
        reservoir, fetkovich_c, fetkovich_n
    )

    # El reservorio no puede dar más que su AOF (caudal a Pwf = 0).
    aof = _compute_aof(reservoir, fetkovich_c, fetkovich_n)
    if target_rate > aof:
        raise ValueError(
            f"target_rate {target_rate:.1f} STB/d exceeds the reservoir AOF "
            f"{aof:.1f} STB/d."
        )

    if method is IPRMethod.LINEAR:
        # Despeje directo de  q = J · (Pr − Pwf)
        return pr - target_rate / pi

    if method is IPRMethod.VOGEL:
        pb = reservoir.bubble_point

        def sobrante(pwf: float) -> float:
            return vogel_composite_ipr(pr, pb, pwf, pi) - target_rate

        return brentq(sobrante, 0.0, pr, xtol=0.01)

    if method is IPRMethod.FETKOVICH:
        if fetkovich_c is None:
            raise ValueError(
                "fetkovich_c must be provided when ipr_method is FETKOVICH"
            )

        def sobrante(pwf: float) -> float:
            return fetkovich_ipr(pr, pwf, fetkovich_c, fetkovich_n) - target_rate

        return brentq(sobrante, 0.0, pr * (1.0 - 1e-9), xtol=0.01)

    raise ValueError(f"Unsupported IPR method: {method}")


# ===========================================================================
# 4. CURVA IPR COMPLETA (para graficar)
# ===========================================================================

def generate_ipr_curve(
    reservoir: Reservoir,
    n_points: int = 50,
    fetkovich_c: float | None = None,
    fetkovich_n: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Evalúa la IPR desde Pwf = Pr hasta Pwf = 0 y devuelve la curva.

    Se recorren *n_points* valores de Pwf repartidos entre los dos extremos:

        Pwf = Pr  →  sin caída de presión, el pozo no aporta:  q = 0
        Pwf = 0   →  caída máxima, el pozo da su AOF

    Args:
        reservoir: Reservorio (Pr, Pb, J, método IPR).
        n_points: Cantidad de puntos de la curva. Por defecto 50.
        fetkovich_c: Coeficiente C. Si se omite se toma de ``reservoir``.
        fetkovich_n: Exponente n. Si se omite se toma de ``reservoir``, y si
            tampoco está, 1.0.

    Returns:
        Tupla ``(q_array, pwf_array)``, ambos de largo *n_points*:
          - ``q_array``   caudales [STB/d], creciendo de 0 al AOF
          - ``pwf_array`` presiones de fondo [psia], bajando de Pr a 0

    Raises:
        ValueError: Si falta el coeficiente C con el método FETKOVICH.
    """
    pr = reservoir.static_pressure
    pi = reservoir.productivity_index
    method = reservoir.ipr_method
    fetkovich_c, fetkovich_n = _resolve_fetkovich_params(
        reservoir, fetkovich_c, fetkovich_n
    )

    pwf_array = np.linspace(pr, 0.0, n_points)

    if method is IPRMethod.LINEAR:
        q_array = np.array([linear_ipr(pr, pwf, pi) for pwf in pwf_array])

    elif method is IPRMethod.VOGEL:
        pb = reservoir.bubble_point
        q_array = np.array(
            [vogel_composite_ipr(pr, pb, pwf, pi) for pwf in pwf_array]
        )

    elif method is IPRMethod.FETKOVICH:
        if fetkovich_c is None:
            raise ValueError(
                "fetkovich_c must be provided when ipr_method is FETKOVICH"
            )
        q_array = np.array(
            [fetkovich_ipr(pr, pwf, fetkovich_c, fetkovich_n) for pwf in pwf_array]
        )

    else:
        raise ValueError(f"Unsupported IPR method: {method}")

    return q_array, pwf_array


# ===========================================================================
# 5. AUXILIARES INTERNOS
# ===========================================================================

def ipr_trace(reservoir: Reservoir, target_rate: float, pwf: float) -> list[dict]:
    """Traza de fórmulas del paso IPR, para mostrar en pantalla.

    Es el **primer** cálculo de todo el diseño: de acá sale la Pwf en las
    perforaciones, y de ella el PIP, el TDH y todo lo demás. Antes la traza
    arrancaba recién en el TDH, así que el paso que fija el punto de partida
    quedaba invisible.

    Devuelve dos entradas: la ecuación IPR del método elegido —escrita con los
    valores del pozo— y el draw-down que resulta.

    Args:
        reservoir: Reservorio (Pr, Pb, J, método IPR).
        target_rate: Caudal objetivo, q [STB/d].
        pwf: Pwf ya resuelta para ese caudal [psia].

    Returns:
        Lista de dicts de :class:`bes.core.formulas.Formula`.
    """
    from bes.core.formulas import FormulaTrace

    trace = FormulaTrace()
    pr = reservoir.static_pressure
    pi = reservoir.productivity_index
    metodo = reservoir.ipr_method
    pb_ef = effective_bubble_point(pr, reservoir.bubble_point)

    if metodo is IPRMethod.LINEAR:
        trace.add("pwf_lineal", {"Pr": pr, "q": target_rate, "J": pi}, pwf)

    elif metodo is IPRMethod.VOGEL:
        # Vogel generalizado es una función PARTIDA EN DOS, así que se muestran
        # los dos tramos siempre, aunque el punto de diseño caiga en uno solo.
        # Con una mitad sola no se puede revisar el método: no se ve dónde se
        # dobla la curva ni por qué este pozo cayó del lado que cayó.
        saturado = pb_ef >= pr
        q_b = pi * (pr - pb_ef)
        en_el_tramo_recto = pwf >= pb_ef

        # El caudal de burbuja es la bisagra: marca dónde se dobla la curva.
        if not saturado:
            trace.add(
                "pwf_qb", {"J": pi, "Pr": pr, "Pb": pb_ef}, q_b,
                context=f"Es la bisagra del método: hasta {q_b:,.0f} STB/d la "
                        f"IPR es una recta, y de ahí en adelante se dobla. El "
                        f"caudal de diseño ({target_rate:,.0f} STB/d) cae "
                        f"{'por debajo' if target_rate <= q_b else 'por encima'}"
                        f", así que gobierna el tramo "
                        f"{'recto' if en_el_tramo_recto else 'curvo'}.",
            )

        # --- Tramo recto: vale de Pr hasta Pb ---------------------------------
        if saturado:
            pass       # Reservorio saturado: no existe tramo recto.
        elif en_el_tramo_recto:
            trace.add(
                "pwf_vogel_recta",
                {"q": target_rate, "J": pi, "Pr": pr}, pwf,
                applies=True,
                context=f"La Pwf de diseño ({pwf:,.0f} psi) queda POR ENCIMA "
                        f"de la presión de burbuja ({pb_ef:,.0f} psi): el "
                        f"flujo en el reservorio todavía es monofásico y vale "
                        f"la recta de Darcy.",
            )
        else:
            # No gobierna: se muestra evaluado en su propio borde, la burbuja.
            trace.add(
                "pwf_vogel_recta",
                {"q": q_b, "J": pi, "Pr": pr}, pb_ef,
                applies=False,
                context=f"Este tramo cubre de 0 a {q_b:,.0f} STB/d, o sea de "
                        f"Pr hasta la burbuja. Acá se lo evalúa en su borde "
                        f"para ver dónde termina. El caudal de diseño "
                        f"({target_rate:,.0f} STB/d) lo supera.",
            )

        # --- Tramo curvo: vale de Pb hacia abajo ------------------------------
        if not en_el_tramo_recto:
            x = pwf / pb_ef
            trace.add(
                "pwf_vogel_bifasico",
                {"q": target_rate, "q_b": q_b, "J": pi, "Pb": pb_ef}, pwf,
                applies=True,
                context=f"La Pwf de diseño ({pwf:,.0f} psi) cae POR DEBAJO de "
                        f"la burbuja ({pb_ef:,.0f} psi): Pwf/Pb = {x:.4f} y el "
                        f"corchete vale {1 - 0.2*x - 0.8*x**2:.4f}. No se "
                        f"despeja a mano; se resuelve numéricamente por Brent."
                        + ("" if not saturado else
                           f" El reservorio está SATURADO (Pb ≥ Pr), así que no "
                           f"hay tramo recto y vale Vogel puro en todo el rango."),
            )
        else:
            # No gobierna: arranca justo donde termina el recto, en la burbuja.
            trace.add(
                "pwf_vogel_bifasico",
                {"q": q_b, "q_b": q_b, "J": pi, "Pb": pb_ef}, pb_ef,
                applies=False,
                context=f"Este tramo arranca en {q_b:,.0f} STB/d —el corchete "
                        f"se anula y devuelve la burbuja, que es como los dos "
                        f"tramos empalman sin quiebre— y sigue hasta el AOF. "
                        f"El caudal de diseño ({target_rate:,.0f} STB/d) no "
                        f"llega.",
            )

    elif metodo is IPRMethod.FETKOVICH:
        c = reservoir.fetkovich_c
        n = reservoir.fetkovich_n or 1.0
        # El AOF ubica el punto de diseño dentro del rango del reservorio, que
        # es lo que en Vogel muestra el caudal de burbuja.
        trace.add(
            "ajuste_aof_fetkovich", {"C": c, "Pr": pr, "n": n},
            _compute_aof(reservoir, c, n),
            context=f"Es el techo del reservorio. El caudal de diseño "
                    f"({target_rate:,.0f} STB/d) tiene que caer por debajo.",
        )
        trace.add(
            "pwf_fetkovich",
            {"q": target_rate, "C": c, "Pr": pr, "n": n}, pwf,
            context=f"Una sola ecuación para TODO el rango: Fetkovich **no se "
                    f"parte** en la presión de burbuja ({pb_ef:,.0f} psi), a "
                    f"diferencia de Vogel. El ajuste de C y n ya absorbe el "
                    f"comportamiento bifásico del reservorio (Beggs ec. 2-58), "
                    f"así que agregarle un tramo recto sería un error. Se "
                    f"resuelve por Brent: no tiene despeje directo para Pwf.",
        )

    trace.add("diseno_drawdown", {"Pr": pr, "Pwf": pwf}, pr - pwf)
    return trace.as_list()


def ipr_validity_warning(reservoir: Reservoir, pwf: float) -> str | None:
    """Avisa cuando el método IPR elegido se está usando fuera de su rango.

    El único caso que hoy amerita aviso es el **método lineal por debajo de la
    presión de burbuja**. La recta de Darcy supone flujo monofásico; en cuanto
    Pwf baja de Pb se libera gas en el reservorio, cae la permeabilidad
    relativa al petróleo y la IPR real se dobla hacia abajo. Seguir sobre la
    recta **sobreestima el aporte del pozo**, y el error crece con la caída de
    presión: Beggs reporta 70-80 % a Pwf baja.

    No se corrige sola: el usuario eligió «Lineal», que por definición es la
    recta. Lo que corresponde es decírselo, para que evalúe pasar a Vogel.

    Args:
        reservoir: Reservorio (Pr, Pb, método IPR).
        pwf: Presión de fondo fluyente del punto de diseño [psia].

    Returns:
        El texto del aviso, o ``None`` si el método se está usando dentro de su
        rango de validez.

    Referencia:
        Beggs, *Production Optimization Using Nodal Analysis*, §2, ec. 2-34.
    """
    if reservoir.ipr_method is not IPRMethod.LINEAR:
        return None
    pb = reservoir.bubble_point
    if pb <= 0 or pwf >= pb:
        return None

    pr = reservoir.static_pressure
    pi = reservoir.productivity_index
    q_recta = pi * (pr - pwf)
    q_vogel = vogel_composite_ipr(pr, pb, pwf, pi)
    exceso = (q_recta / q_vogel - 1.0) * 100.0 if q_vogel > 0 else 0.0

    return (
        f"Método IPR lineal con la Pwf de diseño ({pwf:.0f} psi) por debajo de "
        f"la presión de burbuja ({pb:.0f} psi): ahí el flujo en el reservorio "
        f"ya es bifásico y la recta de Darcy deja de valer. Con el mismo J, el "
        f"Vogel generalizado daría {q_vogel:.0f} STB/d contra los "
        f"{q_recta:.0f} STB/d de la recta — la recta sobreestima un "
        f"{exceso:.0f} %. Evaluar cambiar el método a Vogel."
    )


def _compute_aof(
    reservoir: Reservoir,
    fetkovich_c: float | None,
    fetkovich_n: float,
) -> float:
    """AOF (Absolute Open Flow): el caudal que daría el pozo con Pwf = 0 [STB/d].

    Es el techo físico del reservorio y sirve de tope al caudal de diseño.

        LINEAL      AOF = J · Pr
        VOGEL       AOF = J·(Pr − Pb) + J·Pb/1.8   (Vogel generalizado)
                    Con el reservorio saturado (Pb >= Pr) se reduce a J·Pr/1.8.
        FETKOVICH   AOF = C · (Pr²)^n
    """
    pr = reservoir.static_pressure
    pi = reservoir.productivity_index
    method = reservoir.ipr_method

    if method is IPRMethod.LINEAR:
        return pi * pr
    if method is IPRMethod.VOGEL:
        return vogel_aof(pr, reservoir.bubble_point, pi)
    if method is IPRMethod.FETKOVICH:
        if fetkovich_c is None:
            raise ValueError("fetkovich_c required for FETKOVICH method")
        return fetkovich_ipr(pr, 0.0, fetkovich_c, fetkovich_n)

    raise ValueError(f"Unsupported IPR method: {method}")


def _resolve_fetkovich_params(
    reservoir: Reservoir,
    fetkovich_c: float | None,
    fetkovich_n: float | None,
) -> tuple[float | None, float]:
    """Decide qué C y n usar: mandan los argumentos explícitos, si no el Reservoir.

    ``c`` puede quedar en None — quien llama levanta el error con su propio
    mensaje. ``n`` cae en 1.0 (laminar) si no se especificó en ningún lado.
    El ``getattr`` protege contra objetos Reservoir creados antes de que estos
    campos existieran (por ejemplo, sesiones guardadas).
    """
    c = fetkovich_c if fetkovich_c is not None else getattr(reservoir, "fetkovich_c", None)
    n = fetkovich_n if fetkovich_n is not None else getattr(reservoir, "fetkovich_n", None)
    return c, (n if n is not None else 1.0)
