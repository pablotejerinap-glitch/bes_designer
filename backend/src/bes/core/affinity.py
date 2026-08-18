"""
Affinity laws — centrifugal pump performance at a different speed, impeller
diameter or fluid.

Catalog performance curves are published at a fixed speed, for clean water
(SG = 1, µ = 1 cp) and for **one stage**. The affinity laws predict the curve at
other conditions:

    Q₂ = Q₁ · (N₂/N₁) · (D₂/D₁)
    H₂ = H₁ · (N₂/N₁)² · (D₂/D₁)²
    HP₂ = HP₁ · (N₂/N₁)³ · (D₂/D₁)³ · (SG₂/SG₁)

Efficiency is **not** scaled: it is invariant under a speed or diameter change,
which is what makes the laws a similarity transform and not a fit.

Working in hertz instead of rpm
-------------------------------
An ESP is driven by a two-pole induction motor, so the synchronous speed is
``120·f / poles`` and the shaft turns slower by the slip (about 2.8 %: 3000 rpm
synchronous at 50 Hz against roughly 2917 rpm real). Since the slip is
essentially the same at both frequencies it cancels in the ratio,

    N₂/N₁ = f₂/f₁
    
    
    
so the laws can be applied directly to the drive frequency. That is how a VSD
design is done in practice and it avoids carrying a slip assumption into the
result. :func:`synchronous_rpm` and :func:`motor_rpm` are provided for display.

Reference: Brown, *The Technology of Artificial Lift Methods*, Vol. 2b,
Table 4.21; and the cátedra notes, Unidad N°9 (pág. 135).
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
    """Flow at the new speed/diameter: ``Q₂ = Q₁·(N₂/N₁)·(D₂/D₁)``.

    Args:
        q: Flow at the reference condition [b/d or m³/d — the unit passes through].
        freq_from: Reference (catalog) frequency [Hz]. Must be > 0.
        freq_to: Target frequency [Hz]. Must be > 0.
        diameter_ratio: ``D₂/D₁``. 1.0 = unchanged impeller.

    Returns:
        Flow at the target condition, in the same unit as ``q``.

    Raises:
        ValueError: If any frequency or the diameter ratio is not positive.
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
    """Brake power: ``HP₂ = HP₁·(N₂/N₁)³·(D₂/D₁)³·(SG₂/SG₁)``.

    Unlike head, power **does** depend on density: moving a heavier fluid over
    the same head costs proportionally more. Catalog curves are for water, so
    ``sg_ratio`` is the produced-fluid specific gravity when scaling from a
    catalog value.

    Args:
        hp: Brake power at the reference condition [hp].
        freq_from: Reference (catalog) frequency [Hz].
        freq_to: Target frequency [Hz].
        diameter_ratio: ``D₂/D₁``.
        sg_ratio: ``SG₂/SG₁``. Must be > 0.

    Returns:
        Brake power at the target condition [hp].

    Raises:
        ValueError: If a frequency, the diameter ratio or ``sg_ratio`` is not
            positive.
    """
    n, d = _ratios(freq_from, freq_to, diameter_ratio)
    if sg_ratio <= 0:
        raise ValueError(f"sg_ratio must be > 0, got {sg_ratio}")
    return hp * n ** 3 * d ** 3 * sg_ratio


def frequency_for_flow(
    flow_at_reference: float, target_flow: float, reference_frequency: float
) -> float:
    """Frequency that moves the pump to *target_flow* [Hz].

    Inverts the flow law, which is linear in speed:
    ``f₂ = f₁ · (Q₂/Q₁)``. This is the question a VSD design actually asks —
    "at what frequency do I get the rate I want?" — rather than "what rate do I
    get at this frequency".

    Args:
        flow_at_reference: Known flow at ``reference_frequency`` [b/d]. Must be > 0.
        target_flow: Desired flow [b/d]. Must be > 0.
        reference_frequency: Frequency at which ``flow_at_reference`` holds [Hz].

    Returns:
        Required drive frequency [Hz].

    Raises:
        ValueError: If any argument is not positive.
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
    """Shaft speed after slip [rpm] — ``120·f/polos · (1 − s)``.

    Display value only: the slip cancels in every affinity ratio, so no result
    of this module depends on it.
    """
    if not (0.0 <= slip < 1.0):
        raise ValueError(f"slip must be in [0, 1), got {slip}")
    return synchronous_rpm(freq_hz, poles) * (1.0 - slip)


def hydraulic_hp(flow_bpd: float, head_ft: float, sg: float) -> float:
    """Hydraulic power delivered to the fluid [hp].

    ``HHP = Q · Hd · SG / 135 771`` with Q in b/d and Hd in ft. Together with
    the brake power read from the catalog curve this closes the efficiency
    identity ``η = HHP / BHP``, which is how the digitised curves were quality
    checked (see ``tools/catalog_pipeline``).

    Args:
        flow_bpd: Flow rate [b/d].
        head_ft: Total head developed [ft].
        sg: Specific gravity of the pumped fluid.

    Returns:
        Hydraulic horsepower [hp]. Zero when any argument is non-positive.
    """
    if flow_bpd <= 0 or head_ft <= 0 or sg <= 0:
        return 0.0
    return flow_bpd * head_ft * sg / HYDRAULIC_HP_CONSTANT


def pump_at_frequency(
    pump: "PumpCurve",
    frequency_hz: float,
    diameter_ratio: float = 1.0,
) -> "PumpCurve":
    """The same pump as it behaves at *frequency_hz*, as a ``PumpCurve``.

    Catalog curves are published at one frequency (60 Hz for every catalog in
    this project). Designing a well that runs at another frequency — 50 Hz in
    Argentina, or any frequency set on a VSD — against the published curve is
    wrong in three ways at once: the head per stage is off by ``(f₂/f₁)²``, the
    power per stage by ``(f₂/f₁)³``, and the recommended flow range by
    ``f₂/f₁``, so the pump may not even belong in the shortlist.

    Returning a real ``PumpCurve`` rather than a dict is deliberate: every
    consumer downstream — the flow-range filter, the curve interpolation, the
    stage count, the BEP distance in the ranking, the shut-in head of the
    housing pressure check — keeps working unchanged, on numbers that are now
    at the frequency the well actually runs at.

    The result declares ``catalog_frequency_hz = frequency_hz``, so scaling an
    already-scaled curve is a no-op and the operation is idempotent.

    Args:
        pump: Catalog pump, at its published frequency.
        frequency_hz: Frequency the pump will actually run at [Hz].
        diameter_ratio: ``D₂/D₁`` if the impeller is trimmed.

    Returns:
        A new ``PumpCurve``. Identity, geometry and housings are carried over
        untouched — only the hydraulic curve moves.

    Raises:
        ValueError: If ``frequency_hz`` or ``diameter_ratio`` is not positive.
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
    """Rescale a whole catalog curve to another frequency, diameter and fluid.

    Every point moves together — flow with the first power of the speed ratio,
    head with the square, power with the cube — so the whole curve, its
    recommended operating range and its BEP shift consistently. Efficiency is
    carried over unchanged, which is the physical content of the laws.

    Args:
        pump: Catalog pump whose curve is to be rescaled.
        to_frequency_hz: Target drive frequency [Hz].
        from_frequency_hz: Frequency the catalog curve was published at [Hz].
            Defaults to the pump's own ``catalog_frequency_hz``.
        diameter_ratio: ``D₂/D₁`` if the impeller is trimmed. 1.0 = as published.
        sg_ratio: ``SG₂/SG₁`` for the power law. Catalog curves are for water,
            so pass the produced-fluid SG to get brake power on the real fluid.

    Returns:
        dict with ``frequency_hz``, ``from_frequency_hz``, ``speed_ratio``,
        ``synchronous_rpm``, ``motor_rpm``, ``min_flow``, ``max_flow``,
        ``bep_flow``, ``bep_head_per_stage``, ``bep_hp_per_stage``,
        ``bep_efficiency`` and ``points`` (list of dicts with ``flow_bpd``,
        ``head_ft_per_stage``, ``hp_per_stage`` and ``efficiency``).

    Raises:
        ValueError: If a frequency, the diameter ratio or ``sg_ratio`` is not
            positive.
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
