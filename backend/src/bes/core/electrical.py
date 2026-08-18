"""
Electrical system design for BES/ESP installations.
Based on: Kermit Brown, "The Technology of Artificial Lift Methods", Vol. 2b,
Sections 4.5325 and 4.5326.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from bes.core.models import Fluid, WellGeometry

if TYPE_CHECKING:
    from bes.catalogs.loader import CatalogManager

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

# Flat-cable radial (minor-axis) thickness [in], the dimension that competes for
# the casing-motor annular clearance. Values #6-#1 are the established
# approximations of the flat armored series; each is ~0.14-0.15 in over the AWG
# conductor diameter (aislación + chaqueta + armadura), growing ~0.06 in per size
# step near the large end. 1/0 is extrapolated on that basis (AWG 1/0 conductor
# ~0.325 in) to 0.52 in — consistent with the series and bounded above by
# commercial 1/0 flat 3C cable (~0.68 in for heavy-duty jacketed). Ref.: Takacs
# (2018), ESP Manual §3.4, Table 3.6 (conductor diameters).
_CABLE_FLAT_THICKNESS_IN: dict[str, float] = {
    "1/0": 0.52,
    "#1": 0.46,
    "#2": 0.40,
    "#4": 0.35,
    "#6": 0.30,
}

# Standard 3-phase transformer ratings [kVA]
_TRANSFORMER_SIZES_KVA = (25.0, 37.5, 50.0, 75.0, 100.0, 150.0, 200.0, 300.0)

# Representative pump-shaft diameters [in] by pump series, for axial-thrust
# estimation (industry-typical; not a per-model catalog value).
_SHAFT_DIAMETER_IN = {
    "400": 0.62, "420": 0.62, "456": 0.69, "513": 0.69, "538": 0.69,
    "540": 0.88, "544": 0.88, "562": 0.88, "738": 1.19,
}
_DEFAULT_SHAFT_DIAMETER_IN = 0.69
_THRUST_MARGIN = 1.20   # design margin on estimated axial load
# Wellbore inclination above which a labyrinth seal loses effectiveness and a
# bag (positive-seal) protector is preferred (Brown §4.5325).
_SEAL_DEVIATION_THRESHOLD_DEG = 30.0

# NEC/API RP 11S6 continuous-load derating for cable ampacity selection
_CABLE_DERATING = 1.25


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _interp_vdrop_per_amp(conductor: str, size: str, temp_f: float) -> float:
    """V per amp per 1 000 ft, linearly interpolated at *temp_f*.

    Legacy fallback table (only #1–#6). Prefer ``_vdrop_per_amp_from_cable``,
    which reads each cable's own voltage-drop data from the catalog.
    """
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


def _vdrop_per_amp_from_cable(cable: dict, temp_f: float) -> float:
    """V per amp per 1 000 ft for a catalog cable, interpolated at *temp_f*.

    Reads the cable's own ``voltage_drop_v_per_amp_per_1000ft`` table (keyed by
    temperature) so any conductor size in the catalog is supported — including
    sizes absent from the legacy hardcoded table (e.g. 1/0). Falls back to the
    legacy table only when the cable entry carries no voltage-drop data.
    """
    vd_map = cable.get("voltage_drop_v_per_amp_per_1000ft")
    if not vd_map:
        return _interp_vdrop_per_amp(cable["conductor"], cable["size"], temp_f)
    temps = sorted(float(k) for k in vd_map)
    vals = [vd_map[str(int(t))] for t in temps]
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
    motor_voltage: float = 0.0,
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

    # A diferencia del motor y del protector, acá un dato ausente SÍ descalifica:
    # sin ampacidad ni temperatura no hay forma de saber si el cable aguanta, y
    # elegirlo sería afirmar algo que el catálogo no dice. Los cables de Wood
    # Group entran al catálogo como referencia (calibre, dimensiones, peso) pero
    # no participan de la selección hasta conseguir esos dos números.
    candidates = [
        c for c in catalog_manager._cables
        if c.get("max_amps") is not None
        and c.get("max_temp_f") is not None
        and c["max_amps"] >= required_ampacity
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

    # Del más chico al más grande: el más chico es el más barato, pero también
    # el que más cae. Se recorre en ese orden y se toma el PRIMERO que además
    # pasa las verificaciones eléctricas — el más económico de los que sirven,
    # no el más económico a secas.
    pool.sort(key=lambda c: c["max_amps"])

    best = None
    best_check: dict = {}
    fallback = None
    fallback_check: dict = {}
    for cand in pool:
        v = _vdrop_per_amp_from_cable(cand, bottom_temp)
        check = (
            check_cable_electrical(motor_voltage, motor_amps, v, cable_length)
            if motor_voltage > 0 else {"ok": True}
        )
        if fallback is None:
            fallback, fallback_check = cand, check
        if check["ok"]:
            best, best_check = cand, check
            break

    if best is None:
        # Ningún calibre del catálogo satisface el arranque o la banda de
        # 30 V/1000 ft. Se devuelve el mayor disponible con la advertencia:
        # descartar el diseño acá escondería que el problema es el catálogo, y
        # el remedio real suele ser un motor de mayor tensión (menos corriente).
        best = pool[-1]
        best_check = check_cable_electrical(
            motor_voltage, motor_amps,
            _vdrop_per_amp_from_cable(best, bottom_temp), cable_length,
        ) if motor_voltage > 0 else fallback_check

    vdrop_per_amp = _vdrop_per_amp_from_cable(best, bottom_temp)

    return {
        "cable_size": best["size"],
        "cable_type": best["type"],
        "conductor": best["conductor"],
        "manufacturer": best["manufacturer"],
        "length_ft": cable_length,
        "voltage_drop_per_1000ft": vdrop_per_amp * motor_amps,
        "max_amps": best["max_amps"],
        "electrical_check": best_check,
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


# ---------------------------------------------------------------------------
# Verificación eléctrica del cable (Brown §4.5325; apunte de cátedra Unidad N°9)
#
# Los catálogos publican la caída de tensión como V por amper por 1000 ft, que
# es la caída **de línea** — ya lleva el √3 del sistema trifásico. De ahí sale
# la resistencia por fase, que es lo que piden las dos fórmulas de abajo.
# ---------------------------------------------------------------------------

# Corriente de arranque directo de un motor de inducción ESP, en veces la
# nominal. El rango de la bibliografía es 4-6×; se usa el extremo inferior
# porque es el que fija la fórmula del apunte.
_STARTUP_CURRENT_MULTIPLIER = 4.0

# Mínimo de tensión de placa que debe llegar a bornes durante el arranque.
_MIN_STARTUP_VOLTAGE_RATIO = 0.5

# Reglas prácticas de diseño del calibre.
_MAX_VDROP_PER_1000FT = 30.0   # banda sombreada de la carta de caída de tensión
_MAX_VDROP_FRACTION = 0.05     # 5 % de la tensión de placa del motor


def cable_resistance_ohms(
    vdrop_per_amp_per_1000ft: float, length_ft: float
) -> float:
    """Resistencia por fase del tramo de cable [Ω].

    El dato de catálogo es la caída **de línea** por amper y por 1000 ft, o sea
    ``√3 · R_fase`` por cada 1000 ft. Se despeja la resistencia por fase, que es
    la que entra en la pérdida Joule trifásica.

    Args:
        vdrop_per_amp_per_1000ft: Caída de línea [V/(A·1000 ft)] a la
            temperatura de operación.
        length_ft: Longitud del tramo [ft].

    Returns:
        Resistencia por fase [Ω]. Cero si algún argumento no es positivo.
    """
    if vdrop_per_amp_per_1000ft <= 0 or length_ft <= 0:
        return 0.0
    return vdrop_per_amp_per_1000ft / math.sqrt(3.0) * length_ft / 1000.0


def cable_power_loss_kw(amps: float, resistance_ohms: float) -> float:
    """Potencia disipada en el cable por efecto Joule [kW].

    ``ΔP_c = 3·I²·R_T / 1000`` — los tres conductores, con la resistencia por
    fase a la temperatura del pozo. Es el término operativo (OPEX) del criterio
    económico de Brown: el calibre óptimo minimiza la suma de la amortización
    del cable y esta energía disipada.

    Args:
        amps: Corriente de operación del motor [A].
        resistance_ohms: Resistencia por fase del tramo [Ω].

    Returns:
        Pérdida trifásica [kW].
    """
    if amps <= 0 or resistance_ohms <= 0:
        return 0.0
    return 3.0 * amps ** 2 * resistance_ohms / 1000.0


def startup_voltage_ratio(
    motor_voltage: float,
    voltage_drop_v: float,
    start_multiplier: float = _STARTUP_CURRENT_MULTIPLIER,
) -> float:
    """Fracción de la tensión de placa que llega a bornes en el arranque [0–1].

    Un motor de inducción arranca demandando 4 a 6 veces su corriente nominal,
    y esa corriente cae sobre el mismo cable. La verificación es:

        ``U_start / U_np = (U_np − 4·I·R_T) / U_np``

    Como la caída a corriente nominal ya es ``I·R_T`` en términos de línea, el
    cálculo se apoya en ella y no vuelve a decomponer la resistencia — así el
    chequeo de arranque y la caída de tensión del diseño no pueden divergir.

    Si la relación cae por debajo de 0.5 el motor **no arranca**: no es una
    advertencia de eficiencia, es una falla de puesta en marcha.

    Args:
        motor_voltage: Tensión de placa del motor [V].
        voltage_drop_v: Caída de tensión en el cable a corriente nominal [V].
        start_multiplier: Corriente de arranque en veces la nominal.

    Returns:
        ``U_start/U_np``. Puede ser negativa si el cable es muy chico, lo que
        indica que la tensión de bornes colapsa por completo.

    Raises:
        ValueError: Si ``motor_voltage`` no es positiva.
    """
    if motor_voltage <= 0:
        raise ValueError(f"motor_voltage must be > 0, got {motor_voltage}")
    return (motor_voltage - start_multiplier * voltage_drop_v) / motor_voltage


def check_cable_electrical(
    motor_voltage: float,
    motor_amps: float,
    vdrop_per_amp_per_1000ft: float,
    length_ft: float,
) -> dict:
    """Las tres verificaciones eléctricas del cable, sobre un candidato.

    Devuelve el detalle completo en vez de un booleano porque los tres
    criterios no tienen el mismo peso:

    - **Arranque** (``U_start/U_np > 0.5``) es físico: si no llega tensión el
      motor no parte. Restricción dura.
    - **30 V/1000 ft** es la banda de las cartas de diseño del fabricante.
      Restricción dura.
    - **5 % de la tensión de placa** es una regla práctica de eficiencia. Se
      **reporta** pero no descarta: con pozos profundos y motores de tensión
      moderada suele ser inalcanzable con los calibres del catálogo, y
      descartar por ella dejaría el diseño sin solución.

    Args:
        motor_voltage: Tensión de placa [V].
        motor_amps: Corriente nominal [A].
        vdrop_per_amp_per_1000ft: Caída de línea del cable a la temperatura
            del pozo [V/(A·1000 ft)].
        length_ft: Longitud del cable [ft].

    Returns:
        dict con ``voltage_drop_v``, ``voltage_drop_per_1000ft``,
        ``voltage_drop_fraction``, ``resistance_ohms``, ``power_loss_kw``,
        ``startup_ratio``, ``startup_ok``, ``drop_per_1000ft_ok``,
        ``drop_fraction_ok`` y ``ok`` (= las dos duras).
    """
    drop = vdrop_per_amp_per_1000ft * motor_amps * length_ft / 1000.0
    per_1000 = drop / length_ft * 1000.0 if length_ft > 0 else 0.0
    resistance = cable_resistance_ohms(vdrop_per_amp_per_1000ft, length_ft)
    ratio = startup_voltage_ratio(motor_voltage, drop)
    startup_ok = ratio > _MIN_STARTUP_VOLTAGE_RATIO
    per_1000_ok = per_1000 <= _MAX_VDROP_PER_1000FT
    fraction = drop / motor_voltage if motor_voltage > 0 else 0.0
    return {
        "voltage_drop_v": drop,
        "voltage_drop_per_1000ft": per_1000,
        "voltage_drop_fraction": fraction,
        "resistance_ohms": resistance,
        "power_loss_kw": cable_power_loss_kw(motor_amps, resistance),
        "startup_ratio": ratio,
        "startup_ok": startup_ok,
        "drop_per_1000ft_ok": per_1000_ok,
        "drop_fraction_ok": fraction <= _MAX_VDROP_FRACTION,
        "ok": startup_ok and per_1000_ok,
    }


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
    casing_id: float | None = None,
    manufacturer: str | None = None,
) -> dict:
    """Select the best ESP motor for the given power and well conditions.

    Selection rules (Brown Vol. 2b, Section 4.5325):

    - Fabricante: cuando se indica *manufacturer*, el motor debe ser de ese
      proveedor. Es la regla de aparejo único — bomba, motor y sello del mismo
      fabricante (ver ``.claude/rules/domain.md``).
    - HP rating ≥ hp_required × 1.10  (10 % nameplate margin)
    - Motor OD ≤ pump_od × 1.20  (fits same casing as the pump)
    - Cable clearance: motor OD + 2 × thinnest flat cable ≤ casing_id,
      so that at least one catalog cable can physically run past the motor
      (only checked when *casing_id* is given).
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
        casing_id: Casing inner diameter [in]. Enables the cable-clearance
            check; without it a large-OD motor may pass selection and then
            leave no annular room for any cable.

    Returns:
        Motor catalog dict (hp_rating, voltage, amperage, od_inches, …).

    Raises:
        ValueError: If no qualifying motor exists.
    """
    # El margen del 10 % se redondea a 6 decimales antes de comparar. Sin eso,
    # 50.0 × 1.10 da 55.000000000000006 en punto flotante y un motor de placa
    # 55 hp —que es EXACTAMENTE el margen pedido— queda descartado por un error
    # de redondeo. El margen es una regla de ingeniería, no una desigualdad
    # estricta: un motor que da justo el 10 % cumple.
    hp_min = round(hp_required * 1.10, 6)
    max_od = round(pump_od * 1.20, 6)
    min_temp = bottom_temp + 25.0
    min_cable_thk = min(_CABLE_FLAT_THICKNESS_IN.values())

    if hp_required <= 70.0:
        target_v = 800.0
    elif hp_required <= 200.0:
        target_v = 1200.0
    else:
        target_v = 2000.0

    candidates = [
        m for m in catalog_manager._motors
        if (manufacturer is None or (m.get("manufacturer") or "") == manufacturer)
        and m["hp_rating"] >= hp_min
        and m["od_inches"] <= max_od
        and motor_temperature_ok(m, min_temp)
        and (
            casing_id is None
            or m["od_inches"] + 2.0 * min_cable_thk <= casing_id
        )
    ]

    if not candidates:
        de_quien = f" de {manufacturer}" if manufacturer else ""
        raise ValueError(
            f"No motor found{de_quien} for {hp_required} hp, pump_od={pump_od} in, "
            f"bottom_temp={bottom_temp} °F"
        )

    # Un motor cuya corriente ningún cable del catálogo puede llevar no es un
    # motor seleccionable: el remedio de campo es subir la tensión de placa,
    # que baja la corriente para la misma potencia. Se aplica como preferencia
    # y no como filtro duro para que, si no queda ninguno, sea `select_cable`
    # quien informe el motivo exacto.
    feasible = [
        m for m in candidates
        if m["amperage"] * _CABLE_DERATING
        <= max_cable_ampacity(catalog_manager, bottom_temp, casing_id, m["od_inches"])
    ]
    candidates = feasible or candidates

    min_hp = min(m["hp_rating"] for m in candidates)
    candidates = [m for m in candidates if m["hp_rating"] == min_hp]
    return min(candidates, key=lambda m: abs(m["voltage"] - target_v))


def max_cable_ampacity(
    catalog_manager: "CatalogManager",
    bottom_temp: float,
    casing_id: float | None,
    motor_od: float,
) -> float:
    """Corriente máxima que algún cable del catálogo puede llevar a este motor.

    Aplica los mismos filtros que :func:`select_cable` —temperatura y espesor
    contra el claro anular—, así que responde exactamente la pregunta que
    importa: *¿existe cable para este motor?*
    """
    min_temp_rating = bottom_temp + 25.0
    clearance = (casing_id - motor_od) / 2.0 if casing_id is not None else float("inf")
    usable = [
        c["max_amps"] for c in catalog_manager._cables
        if c.get("max_amps") is not None
        and c.get("max_temp_f") is not None
        and c["max_temp_f"] >= min_temp_rating
        and _CABLE_FLAT_THICKNESS_IN.get(c["size"], 0.50) <= clearance
    ]
    return max(usable) if usable else 0.0


def motor_temperature_ok(motor: dict, min_temp_f: float) -> bool:
    """¿El motor soporta *min_temp_f*? Un dato ausente NO descalifica.

    No todos los catálogos publican la temperatura máxima de bobinado por
    modelo: el de REDA (Schlumberger, 2005), por ejemplo, la menciona solo en
    prosa. Descartar esos motores dejaría fuera un catálogo entero por un dato
    que el fabricante no imprime; darlos por buenos en silencio sería peor.

    El criterio es el mismo que ya usa la ficha mecánica de serie: **dato
    ausente = verificación no realizada**, el motor sigue en carrera y el
    diseño se entrega con la advertencia que emite
    :func:`electrical_design_complete`.
    """
    rating = motor.get("max_temp_f")
    return True if rating is None else rating >= min_temp_f


def estimate_axial_thrust(tdh_ft: float, sg_fluid: float, pump_series: str) -> float:
    """Estimate the axial (downthrust) load the protector must carry [lbs].

    Approximates the hydraulic downthrust as the pump differential pressure
    acting on the shaft cross-section, with a design margin (Takacs, *ESP
    Manual*):

        ΔP_pump [psi] = TDH × 0.433 × SG
        F_axial [lbs] = ΔP_pump × (π/4 · d_shaft²) × margin

    Args:
        tdh_ft: Total dynamic head developed by the pump [ft].
        sg_fluid: Produced-fluid specific gravity.
        pump_series: Pump series (selects a representative shaft diameter).

    Returns:
        Estimated axial thrust load [lbs].
    """
    import math
    d_shaft = _SHAFT_DIAMETER_IN.get(str(pump_series), _DEFAULT_SHAFT_DIAMETER_IN)
    dp_psi = tdh_ft * 0.433 * sg_fluid
    area = math.pi / 4.0 * d_shaft ** 2
    return dp_psi * area * _THRUST_MARGIN


_MIN_COOLING_VELOCITY_FT_S = 1.0   # velocidad mínima de fluido para enfriar el motor
_FT3_PER_BBL = 5.615
_SECONDS_PER_DAY = 86400.0


def fluid_velocity_past_motor(
    flow_bpd: float, casing_id_in: float, motor_od_in: float
) -> float:
    """Velocidad del fluido en el anular casing-motor [ft/s].

    El fluido producido sube por el espacio entre el motor y la pared del casing
    y es lo que refrigera al motor. ``v = Q / A_anular`` con
    ``A_anular = π/4·(ID_casing² − OD_motor²)``. Brown/Takacs recomiendan
    ``v ≥ 1 ft/s``; por debajo, evaluar camisa de enfriamiento.

    Raises:
        ValueError: si el motor no entra en el casing (área anular ≤ 0).
    """
    import math
    area_in2 = math.pi / 4.0 * (casing_id_in ** 2 - motor_od_in ** 2)
    if area_in2 <= 0:
        raise ValueError("el motor no entra en el casing (área anular ≤ 0)")
    q_ft3_s = flow_bpd * _FT3_PER_BBL / _SECONDS_PER_DAY
    area_ft2 = area_in2 / 144.0
    return q_ft3_s / area_ft2


def electrical_design_complete(
    motor_hp: float,
    pump_od: float,
    well: WellGeometry,
    fluid: Fluid,
    catalog_manager: "CatalogManager",
    pump_depth: float | None = None,
    tdh_ft: float | None = None,
    sg_fluid: float = 1.0,
    pump_series: str | None = None,
    flow_bpd: float = 0.0,
    use_vsd: bool = False,
    manufacturer: str | None = None,
    bottom_temp_f: float | None = None,
) -> dict:
    """Complete electrical design: motor → seal → cable → voltage drop → transformer.

    Regla de aparejo único: si se pasa *manufacturer* (el fabricante de la
    bomba), el motor y el sello se buscan solo entre los de ese proveedor. Si no
    hay, el diseño falla en vez de armar un aparejo mixto. El cable y los
    accesorios quedan exentos: son intercambiables entre marcas.

    Args:
        motor_hp: Total pump shaft power required [hp].
        pump_od: Pump outer diameter [in].
        well: Well geometry (casing ID, total depth).
        fluid: Fluid object (reserved for future material-selection logic).
        catalog_manager: Loaded equipment catalog.
        pump_depth: Pump setting depth [ft MD] — governs cable length and
            voltage drop. Falls back to 80 % of total depth when omitted.
        tdh_ft: Total dynamic head [ft], used to estimate axial thrust for the
            protector. When omitted, the seal is selected on series and
            temperature only (no thrust check).
        sg_fluid: Produced-fluid specific gravity (for the thrust estimate).
        pump_series: Pump series, used both for the thrust shaft diameter and
            (with the motor series) to find a compatible protector.
        bottom_temp_f: Temperatura de fondo [°F] — ``reservoir.reservoir_temp``.
            Es la que fija el derating del motor y del cable. Omitirla usa el
            piso conservador de 250 °F, que es el peor caso de los catálogos.

    Returns:
        dict with keys ``motor``, ``seal`` (may be ``None``), ``cable``,
        ``cable_voltage_drop_v``, ``surface_voltage_v``, ``kva_required``,
        ``transformer``, ``axial_thrust_lbs``, ``seal_warning`` (may be ``None``).
    """
    if pump_depth is None:
        pump_depth = well.total_depth * 0.80
    # Sin temperatura de fondo se toma el peor caso, no una cómoda: subestimarla
    # elegiría un motor que en el pozo real no aguanta.
    bottom_temp = 250.0 if bottom_temp_f is None else bottom_temp_f

    motor = select_motor(
        hp_required=motor_hp,
        catalog_manager=catalog_manager,
        pump_od=pump_od,
        bottom_temp=bottom_temp,
        depth_ft=pump_depth,
        casing_id=well.casing_id,
        manufacturer=manufacturer,
    )

    # --- Protector / seal (non-fatal: a missing match warns, does not abort) ---
    thrust_lbs = (
        estimate_axial_thrust(tdh_ft, sg_fluid, pump_series or motor["series"])
        if tdh_ft is not None else 0.0
    )
    prefer_type = (
        "bag" if well.deviation_max > _SEAL_DEVIATION_THRESHOLD_DEG else "labyrinth"
    )
    seal: dict | None = None
    seal_warning: str | None = None
    try:
        seal = catalog_manager.get_seal(
            motor_series=str(motor["series"]),
            temp_f=bottom_temp,
            thrust_lbs=thrust_lbs,
            prefer_type=prefer_type,
            manufacturer=manufacturer,
        )
    except ValueError:
        de_quien = f" de {manufacturer}" if manufacturer else ""
        seal_warning = (
            f"Sin protector{de_quien} compatible en catálogo para motor serie "
            f"{motor['series']} ({bottom_temp:.0f} °F, {thrust_lbs:.0f} lbs de empuje)."
        )

    cable = select_cable(
        motor_amps=motor["amperage"],
        pump_depth=pump_depth,
        bottom_temp=bottom_temp,
        casing_id=well.casing_id,
        motor_od=motor["od_inches"],
        catalog_manager=catalog_manager,
        motor_voltage=motor["voltage"],
    )

    cable_drop = cable["voltage_drop_per_1000ft"] * cable["length_ft"] / 1000.0
    # Avisos eléctricos del cable, en el mismo estilo que el resto del módulo.
    cable_check = cable.get("electrical_check") or {}
    cable_warnings: list[str] = []
    if cable_check and not cable_check.get("startup_ok", True):
        cable_warnings.append(
            f"Arranque comprometido: al arrancar llega el "
            f"{cable_check['startup_ratio'] * 100:.0f} % de la tensión de placa "
            f"(mínimo 50 %). El {cable['cable_size']} es el mayor calibre del "
            f"catálogo que entra en el anular; el remedio habitual es un motor "
            f"de mayor tensión, que baja la corriente."
        )
    if cable_check and not cable_check.get("drop_per_1000ft_ok", True):
        cable_warnings.append(
            f"Caída de tensión {cable_check['voltage_drop_per_1000ft']:.1f} "
            f"V/1000 ft: supera los 30 V/1000 ft de la carta de diseño."
        )
    if cable_check and not cable_check.get("drop_fraction_ok", True):
        cable_warnings.append(
            f"Caída de tensión {cable_check['voltage_drop_fraction'] * 100:.1f} % "
            f"de la tensión de placa (regla práctica: 5 %). Se disipan "
            f"{cable_check['power_loss_kw']:.1f} kW en el cable."
        )

    surface_v = calculate_surface_voltage(motor["voltage"], cable_drop)
    kva = calculate_kva(surface_v, motor["amperage"])
    transformer = select_transformer(kva)

    # --- Controlador de superficie (tablero fijo o VSD); no fatal ---
    controller: dict | None = None
    controller_warning: str | None = None
    try:
        controller = catalog_manager.get_controller(
            voltage=surface_v, kva=kva, amps=motor["amperage"], prefer_vsd=use_vsd
        )
    except ValueError:
        controller_warning = (
            f"Sin controlador en catálogo para {surface_v:.0f} V, {kva:.0f} kVA, "
            f"{motor['amperage']:.0f} A."
        )

    # --- Enfriamiento del motor: velocidad de fluido en el anular ---
    fluid_velocity: float = 0.0
    cooling_ok = True
    cooling_warning: str | None = None
    if flow_bpd > 0:
        try:
            fluid_velocity = fluid_velocity_past_motor(
                flow_bpd, well.casing_id, float(motor["od_inches"])
            )
            cooling_ok = fluid_velocity >= _MIN_COOLING_VELOCITY_FT_S
            if not cooling_ok:
                cooling_warning = (
                    f"Velocidad de fluido {fluid_velocity:.2f} ft/s < "
                    f"{_MIN_COOLING_VELOCITY_FT_S:.0f} ft/s: puede no enfriar el motor. "
                    f"Evaluar camisa de enfriamiento (motor shroud)."
                )
        except ValueError:
            cooling_ok = False
            cooling_warning = "No se pudo evaluar el enfriamiento (motor no entra en el casing)."

    # Verificación térmica del motor: si el catálogo no publica el dato, se
    # informa como no realizada en vez de darla por aprobada.
    motor_warning: str | None = None
    if motor.get("max_temp_f") is None:
        motor_warning = (
            f"Temperatura máxima de bobinado no publicada para el motor "
            f"{motor.get('model', '')} ({motor.get('manufacturer', '')}). "
            f"Verificación térmica NO realizada: confirmar con el fabricante "
            f"que soporta {bottom_temp + 25.0:.0f} °F."
        )

    return {
        "motor": motor,
        "motor_warning": motor_warning,
        "seal": seal,
        "cable": cable,
        "cable_voltage_drop_v": cable_drop,
        "surface_voltage_v": surface_v,
        "kva_required": kva,
        "transformer": transformer,
        "axial_thrust_lbs": thrust_lbs,
        "seal_warning": seal_warning,
        "fluid_velocity_ft_s": fluid_velocity,
        "cooling_ok": cooling_ok,
        "cooling_warning": cooling_warning,
        "controller": controller,
        "controller_warning": controller_warning,
        "cable_check": cable_check,
        "cable_warnings": cable_warnings,
    }
