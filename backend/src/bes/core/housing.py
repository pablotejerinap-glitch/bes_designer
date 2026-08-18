"""Carcasas de la bomba — selección y optimización.

Una vez elegida la bomba y sabida la cantidad de etapas, esas etapas hay que
**meterlas adentro de algo**. Los fabricantes venden carcasas en un conjunto
discreto de longitudes, cada una con capacidad para una cantidad fija de
etapas. Si el diseño pide más etapas de las que entran en la carcasa más
grande, se arma un **tándem**: varias carcasas en serie, una arriba de la otra.

Elegir la combinación es un problema combinatorio chico, y acá se resuelve
**buscando** en vez de con una regla fija, para que cualquier catálogo —los que
están cargados hoy y los que se agreguen mañana— funcione sin tocar código.

El criterio de elección, en orden estricto
------------------------------------------
Sin pesos y sin puntajes, la misma disciplina que ``bes.recommender.ranking``:

    1. que dé EXACTO con las etapas necesarias;
    2. si no, el mínimo excedente de capacidad;
    3. la menor cantidad de carcasas;
    4. la menor cantidad de etapas ciegas (dummy);
    5. el arreglo más simple y estándar: menos longitudes distintas, y entre
       iguales, las carcasas grandes primero.

Los criterios 2 y 4 son la misma magnitud en este modelo: toda etapa de
capacidad instalada que no sea una etapa activa es una etapa ciega, así que
excedente == ciegas. El criterio 4 queda satisfecho por construcción y no hace
falta un desempate aparte.

La presión es una restricción DURA
----------------------------------
La verificación de presión de reventamiento se aplica **dentro** de la
búsqueda, no después: una combinación que ponga cualquier carcasa por encima de
su calificación se descarta y la búsqueda sigue. Así es imposible que se
devuelva un arreglo sobrepresionado. Antes esto era sólo una advertencia — **no
volver a eso**.

Nomenclatura
------------
    MaxP        Presión máxima que ve la carcasa           [psi]
    P(Q=0)      Altura por etapa a caudal cero (shut-in)   [ft/etapa]
    Pem         Gravedad específica de la mezcla bombeada  [-]
    etapa ciega Etapa instalada que no genera altura (dummy)
    tándem      Varias carcasas en serie

Referencia
----------
Brown, K.E. "The Technology of Artificial Lift Methods", Vol. 2b, §4.5451
    (presión de reventamiento de carcasa).
"""
from __future__ import annotations

from typing import Iterator, Sequence

from bes.core.models import PumpHousing

# ft of fluid column per psi (÷ SG) — the project-wide head↔pressure constant.
_FT_PER_PSI = 2.31

# How many housings above the minimum the search is allowed to consider. With a
# uniform pressure rating the minimum-count arrangement is always the answer;
# the slack only matters once a catalog publishes per-housing ratings, where
# splitting the stack differently can bring a housing under its limit.
_EXTRA_HOUSING_SLACK = 2


def housing_pressure_psi(
    shutin_head_per_stage: float, stages: int, sg_fluid: float
) -> float:
    """Presión que desarrolla una pila de etapas a caudal cero [psi].

        MaxP = P(Q=0) · #Etapas · Pem

    El **peor caso para la carcasa es el caudal cero** (shut-in, válvula
    cerrada): ahí la altura por etapa es máxima y todo el diferencial empuja
    contra el recipiente.

    En unidades de campo la altura de shut-in por etapa viene en pies, así que
    la conversión a psi arrastra la gravedad del fluido producido::

        MaxP [psi] = altura_shut-in [ft/etapa] · #Etapas · SG / 2.31

    Es la misma relación que aplica el motor métrico de cátedra en
    :func:`bes.core.metric_design.step11_housing_burst`, escrita en unidades de
    campo.

    Args:
        shutin_head_per_stage: Altura por etapa a caudal cero [ft/etapa].
        stages: Cantidad de etapas **activas**, las que generan altura. Las
            etapas ciegas no desarrollan altura y NO se cuentan acá.
        sg_fluid: Gravedad específica de la mezcla bombeada (Pem).

    Returns:
        Presión desarrollada en el tope de esa pila [psi]. Nunca negativa.
    """
    if stages <= 0 or shutin_head_per_stage <= 0 or sg_fluid <= 0:
        return 0.0
    return shutin_head_per_stage * stages * sg_fluid / _FT_PER_PSI


def _limit_of(housing: PumpHousing, pump_limit_psi: float) -> float:
    """Presión que califica a esta carcasa: la propia si la publica, si no la de
    la bomba.

    Devuelve 0.0 cuando no se conoce ninguna de las dos, y quien llama lo lee
    como «sin datos» — o sea, no verificable, que NO es lo mismo que aprobado.
    """
    return housing.pressure_limit_psi or pump_limit_psi or 0.0


def _multisets(
    sizes_desc: Sequence[int], target: int, slots: int
) -> Iterator[tuple[int, ...]]:
    """Genera las combinaciones de carcasas que suman exactamente las etapas
    pedidas usando exactamente ``slots`` carcasas.

    ``sizes_desc`` tiene que venir ordenado de mayor a menor. La recursión poda
    usando la suma máxima y la mínima todavía alcanzables con los lugares que
    quedan, lo que mantiene la enumeración manejable aun con catálogos que
    tienen muchas carcasas cortas.
    """
    n = len(sizes_desc)
    if n == 0:
        return
    smallest = sizes_desc[-1]

    def rec(i: int, rem_sum: int, rem_slots: int, acc: list[int]) -> Iterator[tuple[int, ...]]:
        if rem_slots == 0:
            if rem_sum == 0:
                yield tuple(acc) + (0,) * (n - len(acc))
            return
        if i == n:
            return
        # Unreachable: too much left for the slots, or too little.
        if rem_sum > rem_slots * sizes_desc[i] or rem_sum < rem_slots * smallest:
            return
        size = sizes_desc[i]
        for k in range(min(rem_slots, rem_sum // size), -1, -1):
            acc.append(k)
            yield from rec(i + 1, rem_sum - k * size, rem_slots - k, acc)
            acc.pop()

    yield from rec(0, target, slots, [])


def _min_housings(sizes: Sequence[int], target: int) -> int | None:
    """Fewest housings whose capacities sum to exactly *target* (None if none).

    Unbounded coin-change over the available housing lengths.
    """
    INF = float("inf")
    dp = [INF] * (target + 1)
    dp[0] = 0
    for t in range(1, target + 1):
        for s in sizes:
            if s <= t and dp[t - s] + 1 < dp[t]:
                dp[t] = dp[t - s] + 1
    return None if dp[target] == INF else int(dp[target])


def _evaluate(
    stack: list[PumpHousing],
    required_stages: int,
    shutin_head_per_stage: float,
    sg_fluid: float,
    pump_limit_psi: float,
) -> dict | None:
    """Arma el informe de presión carcasa por carcasa para un arreglo candidato.

    Las carcasas se ordenan de abajo (admisión) hacia arriba (descarga) por
    calificación creciente, así la mejor calificada queda donde la presión es
    más alta. Es el arreglo que armaría un ingeniero, y es lo que hace viable
    un tándem mixto de carcasas estándar y de alta presión.

    Las etapas activas llenan la pila desde la admisión hacia arriba y las
    etapas ciegas completan la carcasa **de más arriba**, que es como se
    completa un llenado corto en la práctica. La presión se acumula con las
    etapas activas que quedan por debajo de cada carcasa (incluida ella), así
    que la carcasa superior es la que ve el diferencial completo: **es la
    crítica**.

    Devuelve ``None`` si alguna carcasa se pasa de su calificación, y entonces
    quien llama sigue buscando. Cuando no se conoce ninguna calificación, la
    carcasa se reporta como no verificada (``ok`` queda en True y ``limit_psi``
    en 0.0) en vez de aprobar en silencio una verificación que nunca se hizo.
    """
    ordered = sorted(
        stack,
        key=lambda h: (_limit_of(h, pump_limit_psi) or float("inf"), h.stages),
    )

    detail: list[dict] = []
    cumulative_capacity = 0
    for position, h in enumerate(ordered, start=1):
        cumulative_capacity += h.stages
        # Active stages present at or below this housing.
        active_below = min(cumulative_capacity, required_stages)
        pressure = housing_pressure_psi(
            shutin_head_per_stage, active_below, sg_fluid
        )
        limit = _limit_of(h, pump_limit_psi)
        ok = limit <= 0.0 or pressure <= limit
        if not ok:
            return None
        detail.append({
            "position": position,
            "stages": h.stages,
            "code": h.code,
            "material": h.material,
            "od_in": h.od_in,
            "length_ft": h.length_ft,
            "weight_lbs": h.weight_lbs,
            "active_stages_below": active_below,
            "pressure_psi": pressure,
            "limit_psi": limit,
            "limit_known": limit > 0.0,
            "pressure_ok": ok,
        })

    installed = sum(h.stages for h in ordered)
    return {
        "detail": detail,
        "housing_size_stages": installed,
        "dummy_stages": installed - required_stages,
        "n_housings": len(ordered),
    }


def _sort_key(candidate: dict, required_stages: int) -> tuple:
    """Strict lexicographic objective — see the module docstring."""
    detail = candidate["detail"]
    sizes = [d["stages"] for d in detail]
    return (
        candidate["housing_size_stages"] - required_stages,   # 1 & 2: surplus
        candidate["n_housings"],                              # 3
        len(set(sizes)),                                      # 5a: fewest lengths
        sum(d["limit_psi"] for d in detail),                  # 5b: don't over-specify
        tuple(-s for s in sorted(sizes, reverse=True)),       # 5c: larger first
    )


def optimize_housings(
    required_stages: int,
    housings: Sequence[PumpHousing],
    shutin_head_per_stage: float,
    sg_fluid: float,
    pump_pressure_limit_psi: float = 0.0,
    extra_housing_slack: int = _EXTRA_HOUSING_SLACK,
) -> dict | None:
    """El mejor arreglo de carcasas para las etapas pedidas, o None si no entra.

    Busca entre los arreglos que el catálogo **realmente permite** —todas las
    combinaciones de las longitudes de carcasa de esa bomba— y devuelve el
    óptimo según el orden lexicográfico documentado arriba, sujeto a la
    restricción de presión en cada carcasa de la pila.

    Las carcasas son **específicas del modelo**: una sarta de Reda D-40 se arma
    con carcasas D-40, no se mezclan fabricantes. Por eso la búsqueda es sobre
    las longitudes de la bomba seleccionada.

    Como el excedente pesa más que la cantidad de carcasas en el orden de
    criterios, el primer arreglo viable que aparece **ya es el óptimo**: no hace
    falta enumerar el resto.

    Args:
        required_stages: Etapas activas que tiene que llevar la bomba.
            Debe ser > 0.
        housings: Catálogo de carcasas de la bomba elegida. No puede estar
            vacío.
        shutin_head_per_stage: Altura por etapa a caudal cero [ft/etapa], el
            peor caso para el recipiente.
        sg_fluid: Gravedad específica de la mezcla bombeada (Pem).
        pump_pressure_limit_psi: Calificación a nivel bomba [psi], que se usa
            para las carcasas que no publican la propia. 0 = se desconoce.
        extra_housing_slack: Cuántas carcasas por encima del mínimo puede
            agregar la búsqueda con tal de cumplir la restricción de presión.

    Returns:
        dict con ``detail`` (informe por carcasa, de admisión a descarga),
        ``housing_size_stages``, ``dummy_stages``, ``n_housings``,
        ``housings`` (``[(etapas, cantidad)]``, las grandes primero),
        ``max_housing_pressure_psi``, ``housing_pressure_limit_psi``,
        ``pressure_ok`` y ``pressure_verified``.
        ``None`` cuando ningún arreglo mantiene todas las carcasas dentro de su
        calificación.

    Raises:
        ValueError: Si ``required_stages`` <= 0 o la lista de carcasas está
            vacía.
    """
    if required_stages <= 0:
        raise ValueError(f"required_stages must be > 0, got {required_stages}")
    if not housings:
        raise ValueError("the pump has no housings in the catalog")

    # Dedupe on the attributes the search can distinguish; a catalog listing
    # the same length twice with the same rating offers only one real choice.
    by_key: dict[tuple[int, float], PumpHousing] = {}
    for h in housings:
        by_key.setdefault((h.stages, _limit_of(h, pump_pressure_limit_psi)), h)
    types = sorted(by_key.values(), key=lambda h: (-h.stages, -_limit_of(h, pump_pressure_limit_psi)))
    sizes_desc = [h.stages for h in types]
    distinct_sizes = sorted(set(sizes_desc))
    largest = max(distinct_sizes)

    for installed in range(required_stages, required_stages + largest + 1):
        floor = _min_housings(distinct_sizes, installed)
        if floor is None:
            continue                     # this capacity is not reachable
        best: dict | None = None
        best_key: tuple | None = None
        for slots in range(floor, floor + extra_housing_slack + 1):
            for counts in _multisets(sizes_desc, installed, slots):
                stack = [
                    types[i] for i, k in enumerate(counts) for _ in range(k)
                ]
                evaluated = _evaluate(
                    stack, required_stages, shutin_head_per_stage,
                    sg_fluid, pump_pressure_limit_psi,
                )
                if evaluated is None:
                    continue             # over-pressured — keep searching
                key = _sort_key(evaluated, required_stages)
                if best_key is None or key < best_key:
                    best, best_key = evaluated, key
            if best is not None:
                break                    # fewer housings always wins at this capacity
        if best is not None:
            return _finalize(best, required_stages, pump_pressure_limit_psi)

    return None


def _finalize(
    best: dict, required_stages: int, pump_pressure_limit_psi: float
) -> dict:
    """Completa el arreglo ganador con su resumen y su justificación."""
    detail = best["detail"]
    sizes = [d["stages"] for d in detail]
    counts: dict[int, int] = {}
    for s in sizes:
        counts[s] = counts.get(s, 0) + 1

    top = detail[-1]
    verified = any(d["limit_known"] for d in detail)
    result = {
        **best,
        "required_stages": required_stages,
        "housings": sorted(counts.items(), key=lambda kv: -kv[0]),
        "max_housing_pressure_psi": top["pressure_psi"],
        "housing_pressure_limit_psi": top["limit_psi"] or pump_pressure_limit_psi,
        "pressure_ok": all(d["pressure_ok"] for d in detail),
        "pressure_verified": verified,
    }
    result["rationale"] = build_rationale(result)
    return result


def build_rationale(selection: dict) -> str:
    """Justificación del arreglo en una frase, en el idioma de la app.

    Se arma **estrictamente a partir de los valores calculados**: nada de texto
    enlatado ni de afirmaciones que los números no respalden. En particular,
    dice que la verificación de presión *no se pudo hacer* cuando el catálogo no
    publica calificación, en vez de informar que pasó.

    Args:
        selection: Un arreglo ya finalizado por :func:`optimize_housings`.

    Returns:
        Frase en castellano para la pantalla, el PDF y el Excel.
    """
    counts = selection["housings"]
    parts = [
        f"{n} carcasa{'s' if n > 1 else ''} de {stages} etapas"
        for stages, n in counts
    ]
    if len(parts) == 1:
        combo = parts[0]
    else:
        combo = ", ".join(parts[:-1]) + " y " + parts[-1]

    required = selection["required_stages"]
    dummy = selection["dummy_stages"]
    n_housings = selection["n_housings"]
    single = n_housings == 1

    verb = "Se seleccionó" if single else "Se seleccionaron"
    cubrir = "cubre" if single else "cubren"

    if dummy == 0:
        fit = f"{cubrir} exactamente las {required} etapas requeridas sin etapas excedentes"
    else:
        fit = (
            f"{cubrir} las {required} etapas requeridas con el menor excedente "
            f"posible del catálogo ({dummy} etapa{'s' if dummy > 1 else ''} "
            f"ciega{'s' if dummy > 1 else ''})"
        )

    minimality = (
        "es la menor cantidad de carcasas que lo consigue"
        if single
        else f"son la menor cantidad de carcasas que lo consigue ({n_housings} en tándem)"
    )

    if not selection["pressure_verified"]:
        pressure = (
            "la verificación de presión no pudo realizarse porque el catálogo no "
            "publica la presión admisible de la carcasa"
        )
    else:
        pressure = (
            f"y la presión de operación máxima "
            f"({selection['max_housing_pressure_psi']:.0f} psi, sobre la carcasa "
            f"superior) se mantiene dentro de la admisible "
            f"({selection['housing_pressure_limit_psi']:.0f} psi)"
        )

    return f"{verb} {combo} porque {fit}, {minimality}, {pressure}."
