"""
Mechanical verification of the pump string: shaft and thrust bearing.

Companion to :mod:`bes.core.housing`, which covers the third check of the same
family (housing burst pressure). Together they answer the note manufacturers
print at the bottom of every engineering-data sheet:

    "Maximum staging may be limited by housing pressure limit, shaft capacity
     or thrust loading."

Three independent ceilings on the stage count. The design must respect the
**lowest** of the three — a stack that fits the housing pressure can still
twist the shaft off.

Formulas (cátedra, Unidad N°9 pág. 140):

- **Power on the shaft** — ``HP_eje = P_etapa · #Etapas · Pem``
- **Load on the bearing** — ``Carga TL = Ho · Pem · A_eje``

  where ``Ho`` is the lift the pump must raise to the wellhead and ``A_eje``
  the shaft cross-section.

  .. note::
     The printed formula reads ``Carga TL = Ho · #Etapas · Pem · A_eje``, but
     ``Ho`` is defined there as the **total** lift, which already is the sum of
     what every stage contributes — the ``#Etapas`` factor counts the column
     twice. For a 1500 m lift on a 250-stage pump the printed form gives
     198 000 lbs against protectors rated 5 000–30 000 lbs; without it, 792 lbs,
     which agrees with the Takács estimate the electrical design already uses
     (779 lbs on the same case). The ``#Etapas`` factor is therefore taken as a
     typo and dropped.

Data comes from the per-series catalog (``pump_series.json``). A series with no
entry leaves every check **unverified** — reported as such, never as passed.
"""
from __future__ import annotations

import math

# Presión de una columna de fluido: 1 psi = 2.31 ft de agua.
_FT_PER_PSI = 2.31
_LBS_PER_KG = 2.2046226


def shaft_power(hp_per_stage: float, stages: int, pem: float) -> float:
    """Power the shaft must transmit [hp] — ``HP_eje = P_etapa · #Etapas · Pem``.

    Catalog ``hp/stage`` is rated for water (SG = 1), hence the ``Pem`` factor
    for the real produced mixture. This is the same quantity
    :func:`bes.core.pump_design.calculate_motor_hp` returns; it is restated here
    because it is the input to the shaft check, and having it named makes the
    verification read like the cátedra procedure.

    Args:
        hp_per_stage: Power per stage at the operating rate [hp/stage].
        stages: Number of active stages.
        pem: Average specific gravity of the pumped fluid.

    Returns:
        Shaft power [hp]. Zero if any argument is non-positive.
    """
    if hp_per_stage <= 0 or stages <= 0 or pem <= 0:
        return 0.0
    return hp_per_stage * stages * pem


def shaft_hp_limit_at_frequency(
    limit_hp: float, limit_frequency_hz: float, frequency_hz: float
) -> float:
    """Shaft power limit rescaled to another drive frequency [hp].

    What a shaft can take is a **torque**, not a power, and power is torque
    times speed. At constant torque the admissible power therefore scales
    linearly with the frequency:

        ``HP_limit(f) = HP_limit(f_ref) · f / f_ref``

    This matters because catalogs publish the limit at one frequency — the
    Wood Group sheet at 50 Hz, Alkhorayef's at 60 Hz — and comparing a 60 Hz
    design against a 50 Hz limit under-rates the shaft by 20 %.

    Args:
        limit_hp: Published limit [hp].
        limit_frequency_hz: Frequency the published limit refers to [Hz].
        frequency_hz: Frequency of the design [Hz].

    Returns:
        Limit at the design frequency [hp].

    Raises:
        ValueError: If either frequency is not positive.
    """
    if limit_frequency_hz <= 0:
        raise ValueError(
            f"limit_frequency_hz must be > 0, got {limit_frequency_hz}"
        )
    if frequency_hz <= 0:
        raise ValueError(f"frequency_hz must be > 0, got {frequency_hz}")
    return limit_hp * frequency_hz / limit_frequency_hz


def bearing_load_tl(lift_ft: float, pem: float, shaft_area_in2: float) -> float:
    """Axial load on the seal-section thrust bearing [lbs].

    ``Carga TL = Ho · Pem · A_eje`` — the pressure of the column the pump has
    to raise, acting on the shaft cross-section. In field units the lift in
    feet becomes a pressure with the usual head↔pressure constant:

        ``TL [lbs] = (Ho [ft] · Pem / 2.31) · A_eje [in²]``

    Args:
        lift_ft: Lift the pump must raise to the wellhead [ft].
        pem: Average specific gravity of the pumped fluid.
        shaft_area_in2: Shaft cross-sectional area [in²].

    Returns:
        Axial load [lbs]. Zero if any argument is non-positive.
    """
    if lift_ft <= 0 or pem <= 0 or shaft_area_in2 <= 0:
        return 0.0
    return lift_ft * pem / _FT_PER_PSI * shaft_area_in2


def bearing_load_kg(lift_ft: float, pem: float, shaft_area_in2: float) -> float:
    """Same load as :func:`bearing_load_tl`, in kg — the cátedra's unit."""
    return bearing_load_tl(lift_ft, pem, shaft_area_in2) / _LBS_PER_KG


def shaft_area_in2(series: dict) -> float:
    """Shaft cross-section of a series [in²], from the area or the diameter.

    Catalogs publish both and they agree (239.51 mm² = π/4·17.463 mm²); the
    published area wins when present so the number is the manufacturer's, not
    ours.
    """
    area = float(series.get("shaft_area_in2") or 0.0)
    if area > 0:
        return area
    d = float(series.get("shaft_diameter_in") or 0.0)
    return math.pi / 4.0 * d ** 2 if d > 0 else 0.0


def verify_shaft(
    hp_shaft: float, series: dict | None, frequency_hz: float
) -> dict:
    """Check the shaft power against the series limits.

    A design over the **standard** limit is not a failure: it calls for a
    high-strength shaft, exactly as an over-pressured housing calls for a
    high-pressure one. Only exceeding the high-strength limit is infeasible.

    Args:
        hp_shaft: Power on the shaft [hp], from :func:`shaft_power`.
        series: Series record from the catalog, or ``None`` if unknown.
        frequency_hz: Design frequency [Hz], to rescale the published limit.

    Returns:
        dict with ``verified`` (False = the catalog has no data for this
        series), ``hp_shaft``, ``limit_std``, ``limit_high_strength``,
        ``shaft_type`` (``"standard"`` / ``"high_strength"`` / ``""``),
        ``ok`` and ``note``.
    """
    if not series or not series.get("shaft_hp_limit_std"):
        return {
            "verified": False, "hp_shaft": hp_shaft, "limit_std": 0.0,
            "limit_high_strength": 0.0, "shaft_type": "", "ok": True,
            "note": "El catálogo no publica el límite de eje de esta serie: "
                    "la verificación no pudo realizarse.",
        }

    ref = float(series.get("reference_frequency_hz") or 60.0)
    std = shaft_hp_limit_at_frequency(
        float(series["shaft_hp_limit_std"]), ref, frequency_hz
    )
    hs_raw = float(series.get("shaft_hp_limit_high_strength") or 0.0)
    hs = shaft_hp_limit_at_frequency(hs_raw, ref, frequency_hz) if hs_raw else 0.0

    if hp_shaft <= std:
        kind, ok = "standard", True
        note = (f"Eje estándar: {hp_shaft:.1f} hp sobre un límite de "
                f"{std:.1f} hp a {frequency_hz:.0f} Hz.")
    elif hs and hp_shaft <= hs:
        kind, ok = "high_strength", True
        note = (f"Requiere eje de alta resistencia: {hp_shaft:.1f} hp supera el "
                f"límite estándar ({std:.1f} hp) pero entra en el de alta "
                f"resistencia ({hs:.1f} hp) a {frequency_hz:.0f} Hz.")
    else:
        kind, ok = "", False
        top = hs or std
        note = (f"El eje no soporta la potencia: {hp_shaft:.1f} hp supera el "
                f"máximo disponible de la serie ({top:.1f} hp a "
                f"{frequency_hz:.0f} Hz).")

    return {
        "verified": True, "hp_shaft": hp_shaft, "limit_std": std,
        "limit_high_strength": hs, "shaft_type": kind, "ok": ok, "note": note,
    }


def verify_bearing_staging(
    stages: int, bottom_hole_temp_f: float, series: dict | None
) -> dict:
    """Check the stage count against the floater thrust-bearing capacity.

    Manufacturers publish this ceiling as a **stage count with a temperature
    cap** — the Wood Group 400 series allows 303 stages on the standard bearing
    up to 230 °F, or 1529 on the high-load one up to 250 °F — because the
    bearing material loses capacity with temperature. Both conditions bind: a
    well hotter than the cap rules that bearing out no matter how few stages it
    carries.

    Args:
        stages: Active stages in the string.
        bottom_hole_temp_f: Bottom-hole temperature [°F].
        series: Series record from the catalog, or ``None`` if unknown.

    Returns:
        dict with ``verified``, ``stages``, ``limit_stages``, ``bearing_type``
        (``"standard"`` / ``"high_load"`` / ``""``), ``bht_max_f``, ``ok`` and
        ``note``.
    """
    if not series or not series.get("max_staging_bearing_std"):
        return {
            "verified": False, "stages": stages, "limit_stages": 0,
            "bearing_type": "", "bht_max_f": 0.0, "ok": True,
            "note": "El catálogo no publica la capacidad de los cojinetes de "
                    "esta serie: la verificación no pudo realizarse.",
        }

    std_n = int(series["max_staging_bearing_std"])
    std_t = float(series.get("max_staging_bearing_std_bht_max_f") or 0.0)
    hi_n = int(series.get("max_staging_bearing_high_load") or 0)
    hi_t = float(series.get("max_staging_bearing_high_load_bht_max_f") or 0.0)

    if stages <= std_n and (not std_t or bottom_hole_temp_f <= std_t):
        return {
            "verified": True, "stages": stages, "limit_stages": std_n,
            "bearing_type": "standard", "bht_max_f": std_t, "ok": True,
            "note": (f"Cojinete estándar: {stages} etapas sobre un máximo de "
                     f"{std_n}, con temperatura de fondo "
                     f"{bottom_hole_temp_f:.0f} °F ≤ {std_t:.0f} °F."),
        }
    if hi_n and stages <= hi_n and (not hi_t or bottom_hole_temp_f <= hi_t):
        reason = ("la temperatura de fondo supera el límite del estándar"
                  if std_t and bottom_hole_temp_f > std_t
                  else f"las etapas superan el máximo del estándar ({std_n})")
        return {
            "verified": True, "stages": stages, "limit_stages": hi_n,
            "bearing_type": "high_load", "bht_max_f": hi_t, "ok": True,
            "note": (f"Requiere cojinete de alta carga porque {reason}: "
                     f"{stages} etapas sobre un máximo de {hi_n} a "
                     f"{bottom_hole_temp_f:.0f} °F ≤ {hi_t:.0f} °F."),
        }

    top_n, top_t = (hi_n, hi_t) if hi_n else (std_n, std_t)
    if top_t and bottom_hole_temp_f > top_t:
        note = (f"Temperatura de fondo {bottom_hole_temp_f:.0f} °F por encima "
                f"del máximo del cojinete de alta carga ({top_t:.0f} °F).")
    else:
        note = (f"{stages} etapas superan el máximo del cojinete de alta carga "
                f"({top_n}).")
    return {
        "verified": True, "stages": stages, "limit_stages": top_n,
        "bearing_type": "", "bht_max_f": top_t, "ok": False, "note": note,
    }


def max_stages_by_shaft(
    hp_per_stage: float, pem: float, series: dict | None, frequency_hz: float
) -> int:
    """Highest stage count the shaft can drive, 0 when unknown."""
    if not series or not series.get("shaft_hp_limit_std"):
        return 0
    ref = float(series.get("reference_frequency_hz") or 60.0)
    top = float(series.get("shaft_hp_limit_high_strength")
                or series["shaft_hp_limit_std"])
    limit = shaft_hp_limit_at_frequency(top, ref, frequency_hz)
    per_stage = hp_per_stage * pem
    return int(limit // per_stage) if per_stage > 0 else 0


def max_stages_by_housing_pressure(
    shutin_head_per_stage: float, pem: float, limit_psi: float
) -> int:
    """Highest stage count the housing pressure rating allows, 0 when unknown.

    Inverts ``MaxP = P(Q0) · #Etapas · Pem`` — see :mod:`bes.core.housing`.
    """
    if limit_psi <= 0 or shutin_head_per_stage <= 0 or pem <= 0:
        return 0
    per_stage_psi = shutin_head_per_stage * pem / _FT_PER_PSI
    return int(limit_psi // per_stage_psi) if per_stage_psi > 0 else 0


def max_stages_by_bearing(
    bottom_hole_temp_f: float, series: dict | None
) -> int:
    """Highest stage count the thrust bearing allows at this temperature.

    Returns 0 when the series has no data, and 0 as well when the well is
    hotter than every bearing option — there is no admissible stage count then.
    """
    if not series or not series.get("max_staging_bearing_std"):
        return 0
    best = 0
    for n_key, t_key in (
        ("max_staging_bearing_std", "max_staging_bearing_std_bht_max_f"),
        ("max_staging_bearing_high_load", "max_staging_bearing_high_load_bht_max_f"),
    ):
        n = int(series.get(n_key) or 0)
        t = float(series.get(t_key) or 0.0)
        if n and (not t or bottom_hole_temp_f <= t):
            best = max(best, n)
    return best


def staging_ceiling(
    hp_per_stage: float,
    shutin_head_per_stage: float,
    pem: float,
    bottom_hole_temp_f: float,
    housing_limit_psi: float,
    series: dict | None,
    frequency_hz: float,
) -> dict:
    """The three ceilings on the stage count, and which one governs.

    This is the manufacturer's own footnote turned into a number: the design is
    capped by the housing pressure, the shaft capacity or the thrust loading,
    whichever bites first. Ceilings with no data are reported as 0 and excluded
    from the comparison rather than treated as zero-stage limits.

    Returns:
        dict with ``by_housing_pressure``, ``by_shaft``, ``by_bearing``,
        ``governing`` (the binding ceiling, 0 if none is known) and
        ``governing_by`` (which one, ``""`` if none).
    """
    ceilings = {
        "by_housing_pressure": max_stages_by_housing_pressure(
            shutin_head_per_stage, pem, housing_limit_psi
        ),
        "by_shaft": max_stages_by_shaft(hp_per_stage, pem, series, frequency_hz),
        "by_bearing": max_stages_by_bearing(bottom_hole_temp_f, series),
    }
    known = {k: v for k, v in ceilings.items() if v > 0}
    if known:
        name = min(known, key=lambda k: known[k])
        ceilings["governing"] = known[name]
        ceilings["governing_by"] = name
    else:
        ceilings["governing"] = 0
        ceilings["governing_by"] = ""
    return ceilings
