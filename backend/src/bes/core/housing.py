"""
Pump-housing (carcasa) selection and optimisation for BES/ESP design.
Based on: Kermit Brown, "The Technology of Artificial Lift Methods",
Vol. 2b, Section 4.5451 (housing burst pressure).

Once the pump is chosen and the stage count is known, the stages have to be
housed. Manufacturers publish housings as a discrete set of lengths, each
holding a fixed number of stages, and a design that needs more stages than the
largest housing holds is assembled as a **tandem** of several housings in
series. Choosing the combination is a small combinatorial problem, and it is
solved here by search rather than by a fixed rule, so that any catalog — the
ones loaded today and any added later — is handled without touching code.

Objective, applied as a strict lexicographic order (no weights, no scores —
the same discipline as ``bes.recommender.ranking``):

1. exact match on the required stages;
2. otherwise, minimum surplus capacity;
3. minimum number of housings;
4. minimum unused (dummy) stages;
5. simplest, most standard arrangement — fewest distinct housing lengths, and
   larger housings preferred among equals.

Criteria 2 and 4 are the same quantity in this model: every stage of installed
capacity that is not an active stage is a dummy stage, so surplus == dummy.
Criterion 4 is therefore satisfied by construction rather than by a separate
tie-break.

The burst-pressure check is a **hard constraint inside the search**, not a
check applied afterwards: a combination that puts any housing over its rating
is discarded and the search continues, so an over-pressured arrangement can
never be returned.
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
    """Pressure a stack of *stages* develops at shut-in [psi].

    ``MaxP = P(Q=0) · nº etapas · Pem`` — the worst case for the housing is
    zero flow, where the head per stage is maximum and the whole differential
    presses on the vessel. Expressed in field units the shut-in head per stage
    is in ft, so the conversion to psi carries the produced-fluid gravity:

        MaxP [psi] = head_shut-in [ft/stage] · stages · SG / 2.31

    This is the same relation the metric (cátedra) engine applies in
    :func:`bes.core.metric_design.step11_housing_burst`, expressed in field
    units.

    Args:
        shutin_head_per_stage: Head per stage at zero flow [ft/stage].
        stages: Number of *active* stages generating head. Dummy stages
            develop no head and must not be counted here.
        sg_fluid: Specific gravity of the pumped mixture (Pem).

    Returns:
        Pressure developed at the top of that stack [psi]. Never negative.
    """
    if stages <= 0 or shutin_head_per_stage <= 0 or sg_fluid <= 0:
        return 0.0
    return shutin_head_per_stage * stages * sg_fluid / _FT_PER_PSI


def _limit_of(housing: PumpHousing, pump_limit_psi: float) -> float:
    """Rating that governs *housing*: its own when published, else the pump's.

    Returns 0.0 when neither is known, which the caller reads as "no data" and
    treats as unverifiable rather than as a failed check.
    """
    return housing.pressure_limit_psi or pump_limit_psi or 0.0


def _multisets(
    sizes_desc: Sequence[int], target: int, slots: int
) -> Iterator[tuple[int, ...]]:
    """Yield count-vectors over *sizes_desc* using exactly *slots* housings
    whose stage capacities sum to exactly *target*.

    ``sizes_desc`` must be sorted descending. The recursion prunes on the
    largest and smallest sums still reachable with the slots left, which keeps
    the enumeration tractable even for catalogs with many short housings.
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
    """Build the per-housing pressure report for one candidate arrangement.

    The housings are ordered bottom (intake) to top (discharge) by ascending
    rating, so the best-rated vessel sits where the pressure is highest — the
    arrangement an engineer would assemble, and the one that makes a mixed
    standard / high-pressure tandem feasible.

    Active stages fill the stack from the intake upward and the dummy stages
    complete the **topmost** housing, which is how a short fill is made up in
    practice. Pressure accumulates with the active stages below and including
    each housing, so the top housing sees the full shut-in differential.

    Returns ``None`` if any housing exceeds its rating; the caller then keeps
    searching. When no rating is known the housing is reported as unverified
    (``ok`` stays True and ``limit_psi`` is 0.0) rather than silently passing a
    check that was never made.
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
    """Best housing arrangement for *required_stages*, or None if none fits.

    Searches the arrangements the catalog actually allows — every combination
    of the pump's own housing lengths — and returns the optimum under the
    lexicographic objective documented at the top of this module, subject to
    the burst-pressure constraint on every housing of the stack.

    Housings belong to a pump model: a Reda D-40 stack is built from D-40
    housings. The search is therefore over the lengths of the selected pump,
    which is the physically meaningful "all combinations in the catalog" and
    the reason no manufacturer or series is hard-coded anywhere.

    The sweep goes by increasing installed capacity and, within it, by
    increasing housing count, and stops at the first capacity that yields a
    feasible arrangement. Because surplus outranks housing count in the
    objective, that first hit is the optimum — no need to enumerate the rest.

    Args:
        required_stages: Active stages the pump must carry. Must be > 0.
        housings: Housing catalog of the selected pump. Must not be empty.
        shutin_head_per_stage: Head per stage at zero flow [ft/stage], the
            worst case for the vessel.
        sg_fluid: Specific gravity of the pumped mixture (Pem).
        pump_pressure_limit_psi: Pump-level rating [psi], used for any housing
            that does not publish its own. 0 = unknown.
        extra_housing_slack: How many housings above the minimum count the
            search may add to satisfy a pressure constraint.

    Returns:
        dict with ``detail`` (per-housing report, intake → discharge),
        ``housing_size_stages``, ``dummy_stages``, ``n_housings``,
        ``housings`` (``[(stages, count)]``, largest first),
        ``max_housing_pressure_psi``, ``housing_pressure_limit_psi``,
        ``pressure_ok`` and ``pressure_verified``.
        ``None`` when no arrangement keeps every housing within its rating.

    Raises:
        ValueError: If ``required_stages`` <= 0 or the housing list is empty.
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
    """Complete the winning arrangement with its summary and rationale."""
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
    """One-sentence justification of the arrangement, in the app's language.

    Built strictly from the computed values — no canned text and no claim the
    numbers do not support. In particular it says the pressure check *could not
    be made* when the catalog publishes no rating, instead of reporting a pass.

    Args:
        selection: A finalised arrangement from :func:`optimize_housings`.

    Returns:
        Spanish sentence for the UI, the PDF and the Excel report.
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
