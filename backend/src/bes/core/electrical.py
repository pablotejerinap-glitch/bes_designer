"""Diseño eléctrico del aparejo BES: motor, sello, cable y transformador.

La bomba necesita que le lleven energía eléctrica desde la superficie hasta
2000 o 3000 metros de profundidad, y eso trae dos problemas que este módulo
resuelve.

El primero es que **el cable pierde tensión en el camino**. Si el motor pide
1000 V en el fondo, arriba hay que entregar más, porque una parte se cae a lo
largo del cable. Cuanto más largo el cable y más corriente pasa, más se pierde.

El segundo es que **abajo hay muy poco lugar**. El motor tiene que entrar en el
casing, y además el cable tiene que pasar por el costado del motor. Un motor que
entra justo puede dejar sin espacio al cable.

La cadena de cálculo
--------------------
Va en este orden, y cada paso depende del anterior::

    potencia al eje  ->  MOTOR      (hp, tensión, corriente, diámetro)
                     ->  SELLO      (protege el motor del fluido)
                     ->  CABLE      (calibre que aguante la corriente y entre)
                     ->  CAIDA DE TENSION en el cable
                     ->  TENSION EN SUPERFICIE = la del motor + la caída
                     ->  TRANSFORMADOR (kVA para esa tensión y corriente)

Reglas que atan la selección
----------------------------
**No se mezclan fabricantes.** Bomba, motor y sello salen del mismo proveedor
(ver ``.claude/rules/domain.md``). El cable y los accesorios quedan exentos:
son intercambiables entre marcas. Si el proveedor de la bomba no tiene motor
que sirva, la bomba se descarta — nunca se arma un aparejo mixto en silencio.

**Márgenes que se aplican siempre:**

    - Motor: potencia de placa >= 1.10 × la potencia pedida (10 % de margen)
    - Cable: ampacidad >= 1.25 × la corriente del motor (derating NEC)
    - Temperatura: el equipo tiene que aguantar la de fondo + 25 °F

Límite del catálogo actual
--------------------------
El cable de mayor ampacidad publica 100 A. Con el derating de 1.25, la corriente
de motor máxima diseñable es **80 A**; por encima, :func:`select_cable` falla
con un mensaje explícito.

Nomenclatura
------------
    V           Tensión                                       [V]
    I           Corriente                                     [A]
    kVA         Potencia aparente                             [kVA]
    ampacidad   Corriente máxima que aguanta un cable         [A]
    OD          Outer Diameter: diámetro exterior             [in]
    ID          Inner Diameter: diámetro interior             [in]
    AWG         Calibre de conductor (a menor número, más grueso)
    CU / AL     Cobre / aluminio
    NEC         National Electrical Code
    derating    Reducción de la capacidad nominal por seguridad

Referencia
----------
Brown, K.E. "The Technology of Artificial Lift Methods", Vol. 2b, §4.5325 y
    §4.5326.
Takács, G. "Electrical Submersible Pumps Manual" — empuje axial sobre el sello.
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
    """Volts por amper cada 1000 ft, interpolados a la temperatura pedida.

    Tabla de respaldo antigua, que sólo cubre los calibres #1 a #6. Se prefiere
    :func:`_vdrop_per_amp_from_cable`, que lee la tabla propia de cada cable del
    catálogo.
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
    """Volts por amper cada 1000 ft de un cable del catálogo, a esa temperatura.

    Lee la tabla ``voltage_drop_v_per_amp_per_1000ft`` que trae el propio cable
    (indexada por temperatura), así que sirve para cualquier calibre del
    catálogo — incluidos los que no están en la tabla vieja hardcodeada, como el
    1/0. Sólo cae a la tabla vieja cuando la ficha del cable no publica datos de
    caída de tensión.
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
    """Elige el cable de potencia más económico que cumpla todo.

    Los criterios se aplican en este orden (Brown Vol. 2b, §4.5325–4.5326):

        1. **Ampacidad**: ``max_amps`` >= ``motor_amps`` × 1.25. El 1.25 es el
           derating del NEC por carga continua — un cable no se hace trabajar
           al 100 % de su capacidad todo el día.
        2. **Temperatura**: ``max_temp_f`` >= temperatura de fondo + 25 °F.
        3. **Que entre físicamente**: el espesor del cable plano tiene que
           caber en la luz del anular de un lado (casing − motor).
        4. **Conductor**: se prefiere cobre (CU) antes que aluminio (AL).
        5. **Economía**: entre los que cumplen 1 a 4, el conductor más
           chico — o sea el de menor ampacidad, que es el más barato.

    Args:
        motor_amps: Corriente nominal del motor [A].
        pump_depth: Profundidad de asentamiento de la bomba [ft]. La longitud
            de cable es ``pump_depth + 100 ft``.
        bottom_temp: Temperatura de fondo a la profundidad de la bomba [°F].
        casing_id: Diámetro interior del casing [in].
        motor_od: Diámetro exterior del motor [in].
        catalog_manager: Catálogo de equipos cargado.

    Returns:
        dict con ``cable_size``, ``cable_type``, ``conductor``,
        ``manufacturer``, ``length_ft``, ``voltage_drop_per_1000ft`` y
        ``max_amps``.

    Raises:
        ValueError: Si no hay en el catálogo ningún cable que cumpla.
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
    """Caída de tensión total en el cable, en un solo sentido.

    Es lo que se «pierde» en el camino de la superficie al motor. La tensión que
    hay que entregar arriba es la que pide el motor MÁS esta caída.

    Args:
        cable_size: Calibre AWG del conductor, como texto (por ej. ``"#4"``).
        cable_type: Material del conductor o tipo de aislación. Si aparece
            ``"AL"`` en el texto (sin importar mayúsculas) se supone aluminio;
            si no, cobre.
        amps: Corriente de operación [A].
        temp_f: Temperatura de operación [°F].
        length_ft: Largo del tendido de cable [ft].

    Returns:
        Caída de tensión total, en un sentido [V].
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
    """Potencia aparente que tiene que entregar el transformador de superficie.

        kVA = Vs · I · √3 / 1000

    El √3 es la convención de sistema trifásico.

    Args:
        surface_voltage: Tensión necesaria en superficie [V].
        motor_amps: Corriente de operación del motor [A].

    Returns:
        Potencia aparente [kVA].
    """
    return surface_voltage * motor_amps * math.sqrt(3) / 1000.0


def select_transformer(kva_required: float, n_phases: int = 3) -> dict:
    """Elige el transformador estándar más chico que cubra la demanda de kVA.

    Los transformadores no se fabrican en cualquier tamaño: vienen en una serie
    de valores estándar. Trifásicos [kVA]: 25, 37.5, 50, 75, 100, 150, 200, 300.

    Si en vez de una unidad trifásica se usan tres monofásicas
    (``n_phases=1``), cada una tiene que cubrir un tercio de la demanda.

    Args:
        kva_required: Demanda total de potencia aparente [kVA].
        n_phases: 3 para una unidad trifásica; 1 para tres monofásicas.

    Returns:
        dict con ``n_phases``, ``kva_per_unit``, ``n_units`` y ``total_kva``.

    Raises:
        ValueError: Si la demanda supera el máximo del catálogo
            (300 kVA por unidad).
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


def _motivo_sin_motor(
    catalog_manager: "CatalogManager",
    manufacturer: str | None,
    hp_required: float,
    hp_min: float,
    pump_od: float,
    max_od: float,
    casing_id: float | None,
    min_cable_thk: float,
    min_temp: float,
) -> str:
    """Por qué no hay motor, en castellano y con el número que lo explica.

    El mensaje anterior —«No motor found for 47.7 hp, pump_od=4.0 in»— decía
    que no había, pero no por qué, así que el usuario no podía saber si el
    remedio era bajar el caudal, cambiar el casing o que el catálogo de ese
    proveedor no tiene motores. Los cuatro filtros de :func:`select_motor` se
    vuelven a aplicar de a uno para ver **cuál** vació la lista, y el que la
    vació se informa con su magnitud.

    No cambia ninguna decisión: se llama sólo cuando ya se decidió que no hay
    motor, y su única salida es el texto de la excepción.

    Args:
        catalog_manager: Catálogo de equipos cargado.
        manufacturer: Proveedor exigido, o ``None`` si no se exige ninguno.
        hp_required: Potencia al eje pedida [hp].
        hp_min: La misma con el 10 % de margen [hp].
        pump_od: OD de la bomba [in].
        max_od: OD máximo admisible del motor [in].
        casing_id: ID del casing [in], o ``None`` si no se verifica el claro.
        min_cable_thk: Espesor del cable plano más fino del catálogo [in].
        min_temp: Temperatura mínima de bobinado exigida [°F].

    Returns:
        El texto de la excepción.
    """
    de_quien = f" de {manufacturer}" if manufacturer else ""
    del_prov = f" de {manufacturer}" if manufacturer else " del catálogo"

    motores = [
        m for m in catalog_manager._motors
        if manufacturer is None or (m.get("manufacturer") or "") == manufacturer
    ]
    if not motores:
        return (
            f"No hay motores{del_prov} en el catálogo. La regla de aparejo único "
            f"exige que bomba, motor y sello sean del mismo proveedor, así que "
            f"esta bomba no se puede completar."
        )

    # Los que entran físicamente: OD contra la bomba y claro para el cable.
    entran = [m for m in motores if m["od_inches"] <= max_od]
    if casing_id is not None:
        entran = [
            m for m in entran
            if m["od_inches"] + 2.0 * min_cable_thk <= casing_id
        ]

    if not entran:
        od_min = min(m["od_inches"] for m in motores)
        detalle = (
            f"OD del motor + 2 × {min_cable_thk:.2f} in de cable plano "
            f"≤ {casing_id:.3f} in de ID de casing, o sea OD ≤ "
            f"{casing_id - 2.0 * min_cable_thk:.3f} in"
            if casing_id is not None
            else f"OD ≤ {max_od:.2f} in (1.20 × el OD de la bomba)"
        )
        return (
            f"Ningún motor{de_quien} entra en este pozo: hace falta {detalle}, y "
            f"el más fino{del_prov} tiene {od_min:.2f} in. Con la bomba de "
            f"{pump_od:.2f} in no queda luz para pasar el cable."
        )

    # Entran, pero no dan la potencia.
    hp_techo = max(m["hp_rating"] for m in entran)
    if hp_techo < hp_min:
        od_techo = min(
            m["od_inches"] for m in entran if m["hp_rating"] == hp_techo
        )
        motivo = (
            f"El motor más potente{de_quien} que entra en este pozo da "
            f"{hp_techo:.0f} hp (OD {od_techo:.2f} in) y hacen falta "
            f"{hp_min:.1f} hp — {hp_required:.1f} hp al eje más el 10 % de "
            f"margen."
        )
        if casing_id is not None:
            motivo += (
                f" Los motores más grandes{del_prov} no pasan el claro de cable "
                f"de un casing de {casing_id:.3f} in de ID."
            )
        return motivo

    # Entran y dan la potencia: el que sobra es el filtro de temperatura.
    return (
        f"Ningún motor{de_quien} de {hp_min:.1f} hp o más que entre en este "
        f"pozo está calificado para {min_temp:.0f} °F (temperatura de fondo "
        f"más 25 °F de margen)."
    )


def select_motor(
    hp_required: float,
    catalog_manager: "CatalogManager",
    pump_od: float,
    bottom_temp: float,
    depth_ft: float,
    casing_id: float | None = None,
    manufacturer: str | None = None,
) -> dict:
    """Elige el mejor motor para la potencia pedida y las condiciones del pozo.

    Las reglas, en orden (Brown Vol. 2b, §4.5325):

        - **Fabricante**: si se indica ``manufacturer``, el motor tiene que ser
          de ese proveedor. Es la regla de aparejo único — bomba, motor y sello
          del mismo fabricante (ver ``.claude/rules/domain.md``).
        - **Potencia**: placa >= ``hp_required`` × 1.10 (10 % de margen).
        - **Diámetro**: OD del motor <= OD de la bomba × 1.20, para que entre en
          el mismo casing que la bomba.
        - **Luz para el cable**: OD del motor + 2 × el cable plano más fino
          <= ID del casing, para que al menos un cable del catálogo pueda pasar
          por al lado del motor. Sólo se verifica si se pasa ``casing_id``.
        - **Temperatura**: ``max_temp_f`` >= temperatura de fondo + 25 °F.
        - **Tensión objetivo**, según la potencia::

              <= 70 HP     ->  ~800 V
              71 a 200 HP  ->  ~1200 V
              > 200 HP     ->  ~2000 V

        - Entre los que califican: el de menor potencia de placa, y a igualdad,
          el de tensión más cercana a la objetivo.

    Args:
        hp_required: Potencia al eje necesaria [hp].
        catalog_manager: Catálogo de equipos cargado.
        pump_od: Diámetro exterior de la bomba [in], que limita el del motor.
        bottom_temp: Temperatura de fondo [°F].
        depth_ft: Profundidad de asentamiento [ft], sólo informativa.
        casing_id: Diámetro interior del casing [in]. Habilita la verificación
            de luz para el cable; sin ella, un motor de diámetro grande puede
            pasar la selección y después no dejar lugar para ningún cable.

    Returns:
        dict del motor del catálogo (hp_rating, voltage, amperage,
        od_inches, …).

    Raises:
        ValueError: Si no hay ningún motor que califique.
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
        raise ValueError(_motivo_sin_motor(
            catalog_manager, manufacturer, hp_required, hp_min,
            pump_od, max_od, casing_id, min_cable_thk, min_temp,
        ))

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
    """Estima la carga axial (empuje hacia abajo) que tiene que aguantar el sello.

    El empuje hidráulico se aproxima como el diferencial de presión de la bomba
    actuando sobre la sección del eje, con un margen de diseño::

        ΔP_bomba [psi] = TDH · 0.433 · SG
        F_axial [lbs]  = ΔP_bomba · (π/4 · d_eje²) · margen

    Args:
        tdh_ft: Altura dinámica total que desarrolla la bomba [ft].
        sg_fluid: Gravedad específica del fluido producido.
        pump_series: Serie de la bomba, que fija un diámetro de eje
            representativo.

    Returns:
        Carga axial estimada [lbs].

    Referencia:
        Takács, "Electrical Submersible Pumps Manual".
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
    """Diseño eléctrico completo: motor → sello → cable → caída → transformador.

    Es el punto de entrada del módulo. Encadena todos los pasos en orden y
    devuelve el aparejo eléctrico entero.

    **Regla de aparejo único**: si se pasa ``manufacturer`` (el fabricante de la
    bomba), el motor y el sello se buscan sólo entre los de ese proveedor. Si no
    hay, el diseño falla en vez de armar un aparejo mixto. El cable y los
    accesorios quedan exentos: son intercambiables entre marcas.

    Args:
        motor_hp: Potencia total al eje de la bomba [hp].
        pump_od: Diámetro exterior de la bomba [in].
        well: Geometría del pozo (ID de casing, profundidad total).
        fluid: Fluido producido (reservado para elegir materiales a futuro).
        catalog_manager: Catálogo de equipos cargado.
        pump_depth: Profundidad de asentamiento [ft MD] — es la que fija el
            largo del cable y por lo tanto la caída de tensión. Si se omite,
            se usa el 80 % de la profundidad total.
        tdh_ft: Altura dinámica total [ft], para estimar el empuje axial sobre
            el sello. Si se omite, el sello se elige sólo por serie y
            temperatura, sin verificación de empuje.
        sg_fluid: Gravedad específica del fluido producido, para el empuje.
        pump_series: Serie de la bomba, que se usa tanto para el diámetro de
            eje del empuje como (junto con la serie del motor) para encontrar
            un sello compatible.
        bottom_temp_f: Temperatura de fondo [°F] — ``reservoir.reservoir_temp``.
            Es la que fija el derating del motor y del cable. Omitirla usa el
            piso conservador de 250 °F, que es el peor caso de los catálogos.

    Returns:
        dict con ``motor``, ``seal`` (puede ser ``None``), ``cable``,
        ``cable_voltage_drop_v``, ``surface_voltage_v``, ``kva_required``,
        ``transformer``, ``axial_thrust_lbs`` y ``seal_warning`` (puede ser
        ``None``).
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


# --------------------------------------------------------------------------
# Traza de fórmulas
# --------------------------------------------------------------------------

def electrical_trace(
    motor_voltage: float,
    motor_amps: float,
    cable_length_ft: float,
    cable_size: str,
    cable_type: str,
    temp_f: float,
    transformer_loss_pct: float = 2.5,
    tdh_ft: float = 0.0,
    sg_fluid: float = 1.0,
    pump_series: str = "",
    flow_bpd: float = 0.0,
    casing_id_in: float = 0.0,
    motor_od_in: float = 0.0,
) -> list[dict]:
    """La cadena eléctrica con sus números: cable, arranque, trafo y protector.

    Función aparte, como :func:`bes.core.ipr.ipr_trace`, para no tocar las
    firmas de las funciones puras. Llama a las mismas que usa el diseño.

    Args:
        motor_voltage: Tensión nominal del motor [V].
        motor_amps: Corriente a plena carga [A].
        cable_length_ft: Longitud de cable [ft].
        cable_size: Calibre AWG del conductor (p. ej. ``"#4"``).
        cable_type: Material o tipo de aislación del conductor.
        temp_f: Temperatura de operación del cable [°F].
        transformer_loss_pct: Pérdida del transformador [%].
        tdh_ft: Altura dinámica total [ft]. 0 omite el empuje axial.
        sg_fluid: Gravedad específica del fluido [-].
        pump_series: Serie de la bomba, para el diámetro de eje.
        flow_bpd: Caudal producido [b/d]. 0 omite la refrigeración.
        casing_id_in: Diámetro interno del casing [in].
        motor_od_in: Diámetro externo del motor [in].

    Returns:
        Lista de dicts de :class:`bes.core.formulas.Formula`.
    """
    from bes.core.formulas import FormulaTrace

    trace = FormulaTrace()

    # La caída por amper sale del catálogo interpolada a la temperatura de
    # operación; es la misma que usa voltage_drop() por dentro.
    conductor = "AL" if "AL" in cable_type.upper() else "CU"
    vdrop_per_amp_per_1000ft = _interp_vdrop_per_amp(conductor, cable_size, temp_f)
    dv = voltage_drop(cable_size, cable_type, motor_amps, temp_f, cable_length_ft)
    trace.add(
        "elec_caida_tension",
        {"v_caida": vdrop_per_amp_per_1000ft, "I": motor_amps,
         "L": cable_length_ft},
        dv,
        context=f"Son {dv / motor_voltage * 100:.1f} % de la tensión del motor."
        if motor_voltage > 0 else "",
    )

    r = cable_resistance_ohms(vdrop_per_amp_per_1000ft, cable_length_ft)
    trace.add(
        "elec_resistencia_cable",
        {"v_caida": vdrop_per_amp_per_1000ft, "L": cable_length_ft}, r,
    )
    trace.add(
        "elec_perdida_cable",
        {"I": motor_amps, "R": r}, cable_power_loss_kw(motor_amps, r),
    )

    if motor_voltage > 0:
        trace.add(
            "elec_tension_arranque",
            {"V_motor": motor_voltage, "k": _STARTUP_CURRENT_MULTIPLIER,
             "ΔV": dv},
            startup_voltage_ratio(motor_voltage, dv),
            context="Si baja demasiado el motor no desarrolla par y no "
                    "arranca, aunque en régimen anduviera.",
        )

    vs = calculate_surface_voltage(motor_voltage, dv, transformer_loss_pct)
    trace.add(
        "elec_tension_superficie",
        {"V_motor": motor_voltage, "ΔV": dv, "pérdida": transformer_loss_pct},
        vs,
    )
    trace.add(
        "elec_kva", {"V_s": vs, "I": motor_amps}, calculate_kva(vs, motor_amps),
    )

    if tdh_ft > 0 and pump_series:
        d_shaft = _SHAFT_DIAMETER_IN.get(str(pump_series), _DEFAULT_SHAFT_DIAMETER_IN)
        trace.add(
            "elec_empuje_axial",
            {"ΔP": tdh_ft * 0.433 * sg_fluid,
             "A_eje": math.pi / 4.0 * d_shaft ** 2,
             "margen": _THRUST_MARGIN},
            estimate_axial_thrust(tdh_ft, sg_fluid, pump_series),
        )

    if flow_bpd > 0 and casing_id_in > motor_od_in > 0:
        area_in2 = math.pi / 4.0 * (casing_id_in ** 2 - motor_od_in ** 2)
        trace.add(
            "elec_area_anular",
            {"ID_casing": casing_id_in, "OD_motor": motor_od_in}, area_in2,
        )
        v = fluid_velocity_past_motor(flow_bpd, casing_id_in, motor_od_in)
        trace.add(
            "elec_velocidad_motor",
            {"Q": flow_bpd, "A_anular": area_in2}, v,
            context=("Por debajo de 1 ft/s: evaluar camisa de enfriamiento."
                     if v < 1.0 else "Supera el mínimo de 1 ft/s recomendado."),
        )
    return trace.as_list()
