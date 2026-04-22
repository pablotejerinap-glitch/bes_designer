"""
Electrical system design for BES/ESP installations.
Based on: Kermit Brown, "The Technology of Artificial Lift Methods", Vol. 2b,
Sections 4.5325 and 4.5326.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from core.models import Fluid, WellGeometry

if TYPE_CHECKING:
    from catalogs.loader import CatalogManager

# ---------------------------------------------------------------------------
# Voltage-drop lookup (mirrors catalogs/cables.json — Brown Table 4.52 / API RP 11S6)
# Values in V / (A · 1000 ft), 3-phase (√3 already included by manufacturer).
# ---------------------------------------------------------------------------
_VDROP_TEMPS_F = (100.0, 150.0, 180.0, 200.0)
_VDROP_PER_AMP_PER_1000FT: dict[tuple[str, str], tuple[float, ...]] = {
    ("CU", "#1"): (0.235, 0.257, 0.270, 0.281),
    ("CU", "#2"): (0.297, 0.324, 0.341, 0.354),
    ("CU", "#4"): (0.473, 0.516, 0.543, 0.562),
    ("CU", "#6"): (0.752, 0.820, 0.863, 0.894),
    ("AL", "#1"): (0.388, 0.424, 0.446, 0.462),
    ("AL", "#2"): (0.490, 0.535, 0.563, 0.583),
    ("AL", "#4"): (0.779, 0.850, 0.895, 0.927),
}

# Approximate flat-cable armored thickness [in] for annular clearance check
_CABLE_FLAT_THICKNESS_IN: dict[str, float] = {
    "#1": 0.46,
    "#2": 0.40,
    "#4": 0.35,
    "#6": 0.30,
}

# Standard 3-phase transformer ratings [kVA]
_TRANSFORMER_SIZES_KVA = (25.0, 37.5, 50.0, 75.0, 100.0, 150.0, 200.0, 300.0)

# NEC/API RP 11S6 continuous-load derating for cable ampacity selection
_CABLE_DERATING = 1.25


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _interp_vdrop_per_amp(conductor: str, size: str, temp_f: float) -> float:
    """V per amp per 1 000 ft, linearly interpolated at *temp_f*."""
    key = (conductor.upper(), size)
    if key not in _VDROP_PER_AMP_PER_1000FT:
        raise ValueError(f"No voltage-drop data for {size} {conductor}")
    vals = _VDROP_PER_AMP_PER_1000FT[key]
    temps = _VDROP_TEMPS_F
    if temp_f <= temps[0]:
        return vals[0]
    if temp_f >= temps[-1]:
        return vals[-1]
    for i in range(len(temps) - 1):
        if temps[i] <= temp_f <= temps[i + 1]:
            frac = (temp_f - temps[i]) / (temps[i + 1] - temps[i])
            return vals[i] + frac * (vals[i + 1] - vals[i])
    return vals[-1]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def select_cable(
    motor_amps: float,
    pump_depth: float,
    bottom_temp: float,
    casing_id: float,
    motor_od: float,
    catalog_manager: "CatalogManager",
) -> dict:
    """Select the most economical ESP power cable.

    Selection criteria (Brown Vol. 2b, Sections 4.5325–4.5326):

    1. Ampacity  : ``max_amps`` ≥ ``motor_amps`` × 1.25  (NEC continuous-load derating)
    2. Temperature: ``max_temp_f`` ≥ ``bottom_temp`` + 25 °F
    3. Physical fit: flat-cable thickness ≤ one-side annular clearance (casing − motor)
    4. Conductor preference: copper (CU) before aluminium (AL)
    5. Economy: smallest conductor (lowest max_amps) that satisfies 1–4

    Args:
        motor_amps: Rated motor current [A].
        pump_depth: Pump setting depth [ft]. Cable length = pump_depth + 100 ft.
        bottom_temp: Bottom-hole temperature at pump depth [°F].
        casing_id: Casing inner diameter [in].
        motor_od: Motor outer diameter [in].
        catalog_manager: Loaded equipment catalog.

    Returns:
        dict with ``cable_size``, ``cable_type``, ``conductor``, ``manufacturer``,
        ``length_ft``, ``voltage_drop_per_1000ft``, ``max_amps``.

    Raises:
        ValueError: If no qualifying cable exists in the catalog.
    """
    required_ampacity = motor_amps * _CABLE_DERATING
    min_temp_rating = bottom_temp + 25.0
    cable_length = pump_depth + 100.0
    annular_clearance = (casing_id - motor_od) / 2.0

    candidates = [
        c for c in catalog_manager._cables
        if c["max_amps"] >= required_ampacity
        and c["max_temp_f"] >= min_temp_rating
        and _CABLE_FLAT_THICKNESS_IN.get(c["size"], 0.50) <= annular_clearance
    ]

    if not candidates:
        raise ValueError(
            f"No cable found for {motor_amps} A, {bottom_temp} °F, "
            f"casing_id={casing_id:.3f} in, motor_od={motor_od:.3f} in"
        )

    cu = [c for c in candidates if c["conductor"] == "CU"]
    pool = cu if cu else candidates

    # Smallest conductor (minimum max_amps that still meets derating) = most economical
    pool.sort(key=lambda c: c["max_amps"])
    best = pool[0]

    vdrop_per_amp = _interp_vdrop_per_amp(best["conductor"], best["size"], bottom_temp)

    return {
        "cable_size": best["size"],
        "cable_type": best["type"],
        "conductor": best["conductor"],
        "manufacturer": best["manufacturer"],
        "length_ft": cable_length,
        "voltage_drop_per_1000ft": vdrop_per_amp * motor_amps,
        "max_amps": best["max_amps"],
    }


def voltage_drop(
    cable_size: str,
    cable_type: str,
    amps: float,
    temp_f: float,
    length_ft: float,
) -> float:
    """Total cable voltage drop for a one-way run.

    Args:
        cable_size: AWG conductor size string (e.g. ``"#4"``).
        cable_type: Conductor material or insulation type.  If ``"AL"`` appears
            in the string (case-insensitive), aluminium is assumed; otherwise
            copper (CU) is used.
        amps: Operating current [A].
        temp_f: Operating temperature [°F].
        length_ft: Cable run length [ft].

    Returns:
        Total one-way voltage drop [V].
    """
    conductor = "AL" if "AL" in cable_type.upper() else "CU"
    vdrop_per_amp = _interp_vdrop_per_amp(conductor, cable_size, temp_f)
    return vdrop_per_amp * amps * length_ft / 1000.0


def calculate_surface_voltage(
    motor_voltage: float,
    cable_voltage_drop: float,
    transformer_loss_pct: float = 2.5,
) -> float:
    """Required surface (primary) voltage.

    Vs = (Vmotor + cable_drop) × (1 + transformer_loss_pct / 100)

    Args:
        motor_voltage: Motor nameplate voltage [V].
        cable_voltage_drop: Total one-way cable voltage drop [V].
        transformer_loss_pct: Transformer secondary-to-primary loss [%].

    Returns:
        Required surface voltage [V].
    """
    return (motor_voltage + cable_voltage_drop) * (1.0 + transformer_loss_pct / 100.0)


def calculate_kva(surface_voltage: float, motor_amps: float) -> float:
    """Apparent power required from the surface transformer [kVA].

    kVA = Vs × I × √3 / 1 000  (three-phase convention)

    Args:
        surface_voltage: Required surface voltage [V].
        motor_amps: Motor operating current [A].

    Returns:
        Apparent power [kVA].
    """
    return surface_voltage * motor_amps * math.sqrt(3) / 1000.0


def select_transformer(kva_required: float, n_phases: int = 3) -> dict:
    """Select the smallest standard transformer meeting the kVA demand.

    Standard 3-phase ratings [kVA]: 25, 37.5, 50, 75, 100, 150, 200, 300.
    For three single-phase units (n_phases=1), per-unit rating = kva_required / 3.

    Args:
        kva_required: Total apparent power demand [kVA].
        n_phases: 3 for a single 3-phase unit; 1 for three single-phase units.

    Returns:
        dict with ``n_phases``, ``kva_per_unit``, ``n_units``, ``total_kva``.

    Raises:
        ValueError: If demand exceeds the maximum catalog rating (300 kVA/unit).
    """
    if n_phases == 3:
        per_unit_demand = kva_required
        n_units = 1
    else:
        per_unit_demand = kva_required / 3.0
        n_units = 3

    selected = next(
        (s for s in _TRANSFORMER_SIZES_KVA if s >= per_unit_demand), None
    )
    if selected is None:
        raise ValueError(
            f"Demand {kva_required:.1f} kVA ({per_unit_demand:.1f} kVA/unit) "
            f"exceeds maximum catalog rating of {_TRANSFORMER_SIZES_KVA[-1]} kVA"
        )
    return {
        "n_phases": n_phases,
        "kva_per_unit": selected,
        "n_units": n_units,
        "total_kva": selected * n_units,
    }


def select_motor(
    hp_required: float,
    catalog_manager: "CatalogManager",
    pump_od: float,
    bottom_temp: float,
    depth_ft: float,
) -> dict:
    """Select the best ESP motor for the given power and well conditions.

    Selection rules (Brown Vol. 2b, Section 4.5325):

    - HP rating ≥ hp_required × 1.10  (10 % nameplate margin)
    - Motor OD ≤ pump_od × 1.20  (fits same casing as the pump)
    - Temperature: ``max_temp_f`` ≥ bottom_temp + 25 °F
    - Target voltage (HP-based):
        ≤ 70 HP → ~800 V  |  71–200 HP → ~1 200 V  |  > 200 HP → ~2 000 V
    - Among qualified: smallest HP rating, then closest voltage to target.

    Args:
        hp_required: Required shaft power [hp].
        catalog_manager: Loaded equipment catalog.
        pump_od: Pump outer diameter [in] (constrains motor OD).
        bottom_temp: Bottom-hole temperature [°F].
        depth_ft: Pump setting depth [ft] (informational).

    Returns:
        Motor catalog dict (hp_rating, voltage, amperage, od_inches, …).

    Raises:
        ValueError: If no qualifying motor exists.
    """
    hp_min = hp_required * 1.10
    max_od = pump_od * 1.20
    min_temp = bottom_temp + 25.0

    if hp_required <= 70.0:
        target_v = 800.0
    elif hp_required <= 200.0:
        target_v = 1200.0
    else:
        target_v = 2000.0

    candidates = [
        m for m in catalog_manager._motors
        if m["hp_rating"] >= hp_min
        and m["od_inches"] <= max_od
        and m["max_temp_f"] >= min_temp
    ]

    if not candidates:
        raise ValueError(
            f"No motor found for {hp_required} hp, pump_od={pump_od} in, "
            f"bottom_temp={bottom_temp} °F"
        )

    min_hp = min(m["hp_rating"] for m in candidates)
    candidates = [m for m in candidates if m["hp_rating"] == min_hp]
    return min(candidates, key=lambda m: abs(m["voltage"] - target_v))


def electrical_design_complete(
    motor_hp: float,
    pump_od: float,
    well: WellGeometry,
    fluid: Fluid,
    catalog_manager: "CatalogManager",
) -> dict:
    """Complete electrical design: motor → cable → voltage drop → transformer.

    Uses pump_depth = 80 % of total well depth as a proxy when the exact
    pump-setting depth is not provided.

    Args:
        motor_hp: Total pump shaft power required [hp].
        pump_od: Pump outer diameter [in].
        well: Well geometry (casing ID, total depth, bottom-hole temperature).
        fluid: Fluid object (reserved for future material-selection logic).
        catalog_manager: Loaded equipment catalog.

    Returns:
        dict with keys ``motor``, ``cable``, ``cable_voltage_drop_v``,
        ``surface_voltage_v``, ``kva_required``, ``transformer``.
    """
    pump_depth = well.total_depth * 0.80
    bottom_temp = well.bottom_hole_temp

    motor = select_motor(
        hp_required=motor_hp,
        catalog_manager=catalog_manager,
        pump_od=pump_od,
        bottom_temp=bottom_temp,
        depth_ft=pump_depth,
    )

    cable = select_cable(
        motor_amps=motor["amperage"],
        pump_depth=pump_depth,
        bottom_temp=bottom_temp,
        casing_id=well.casing_id,
        motor_od=motor["od_inches"],
        catalog_manager=catalog_manager,
    )

    cable_drop = voltage_drop(
        cable_size=cable["cable_size"],
        cable_type=cable["conductor"],
        amps=motor["amperage"],
        temp_f=bottom_temp,
        length_ft=cable["length_ft"],
    )

    surface_v = calculate_surface_voltage(motor["voltage"], cable_drop)
    kva = calculate_kva(surface_v, motor["amperage"])
    transformer = select_transformer(kva)

    return {
        "motor": motor,
        "cable": cable,
        "cable_voltage_drop_v": cable_drop,
        "surface_voltage_v": surface_v,
        "kva_required": kva,
        "transformer": transformer,
    }
