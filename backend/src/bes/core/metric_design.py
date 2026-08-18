"""Camino métrico de diseño — método de cátedra «ESP 01».

Es una ruta **paralela y explícita** al motor de diseño en unidades de campo
(``tdh.py`` + ``pump_design.py`` + ``electrical.py``). Sigue el ejercicio
ESP 01 paso por paso, en unidades métricas (kg/cm², m, °C, m³/d, g/cm³), con
las fórmulas simplificadas del propio ejercicio.

**No reutiliza —y no debe perturbar— la fórmula de TDH de campo** (Brown
§4.5324). Son dos caminos independientes a propósito: uno reproduce el libro,
el otro reproduce la cátedra.

Los 17 pasos están implementados como funciones puras chiquitas, una por paso,
y los orquesta :func:`design_esp_metric`, que devuelve un
:class:`MetricDesignResult` con **todos** los valores intermedios que el
ejercicio informa — así la pantalla, los reportes y los tests pueden leerlos.

Los 17 pasos
------------
    1. Presión admisible referida a la profundidad de referencia
    2. Caudal máximo del reservorio, desde un punto de ensayo (Vogel)
    3. Caudal de producción a la Pwf de trabajo
    4-6. Niveles, sumergencia y altura dinámica
    7. PIP a la profundidad de succión
    8-9. Selección de bomba y cantidad de etapas
    10. Selección de carcasas
    11. Verificación de presión de carcasa
    12. Potencia de la bomba y verificación de eje por carcasa
    13. Selección de motores (uno o dos en tándem)
    14. Verificación de velocidad del fluido por el anular
    15. Selección del protector / sello
    16. Selección de cable y caída de tensión
    17. Verificaciones finales

Ambigüedades conocidas del enunciado
------------------------------------
Están documentadas y resueltas en ``docs/METHODOLOGY.md`` §7:

    §7-A  La lámina titula Pwf = 31 pero calcula con 30. Se puede forzar
          cualquiera de las dos con ``production_pwf_kgcm2``.
    §7-B  El TDH se ancla en los ~2301 m aritméticamente correctos; los
          2347 m de la cátedra se publican aparte como ``tdh_reference_m``.
    §7-C  La verificación de eje se hace por carcasa, no global.

Referencia
----------
``docs/METHODOLOGY.md`` §7 y ``docs/EJEMPLO_ESP01.md``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import numpy as np

from bes.core import units
from bes.core.ipr import vogel_qmax_from_test

if TYPE_CHECKING:
    from bes.catalogs.metric_loader import MetricCatalog

# Cátedra reference for the TDH of ESP 01.  The exercise's lámina reports
# 2347 m, but the formula as written yields ~2301 m with the given data
# (§7-B).  Per the design decision, the engine ANCHORS on the computed value
# and exposes this only as an informative reference (never asserted as truth).
TDH_ESP01_CATEDRA_REFERENCE_M = 2347.0

# Fluid-velocity reference that the ESP 01 chart reads for the motor/casing
# combination (informative; the engine computes velocity from the annulus).
FLUID_VELOCITY_ESP01_REFERENCE_FT_S = 4.75

# Volume of one barrel [ft³] and seconds per day, for fluid-velocity.
_FT3_PER_BBL = 5.615
_SECONDS_PER_DAY = 86_400.0


# ===========================================================================
# Inputs / outputs
# ===========================================================================

@dataclass
class MetricDesignInput:
    """Todos los datos del pozo, la producción y el fluido del ESP-01, en métrico.

    Se mantiene **separado a propósito** de las dataclasses en unidades de campo
    de ``bes/core/models.py``: aquéllas validan rangos de unidades de campo
    (psi, °F) y forzarían conversiones con pérdida acá.
    """
    # --- Well geometry ---
    casing_od_in: float
    casing_weight_lbft: float
    casing_id_in: float
    tubing_id_in: float
    perf_top_m: float
    perf_bottom_m: float
    ref_depth_m: float          # profundidad de referencia (Pref)
    total_depth_m: float
    suction_depth_m: float      # profundidad de succión / asentamiento bomba (Ps)

    # --- Production ---
    casing_head_pressure_kgcm2: float      # Pc (presión en casing, boca)
    discharge_pressure_kgcm2: float        # Pbp (presión de descarga / boca)
    q_test_m3d: float                      # Qwf (caudal de test)
    pwf_test_kgcm2: float                  # Pwf de test
    reservoir_pressure_kgcm2: float        # Pr (estática)
    temp_bottom_c: float                   # Tf
    water_cut: float                       # WC [0–1]
    gor_m3m3: float
    q_target_m3d: float                    # Qd (objetivo)
    pip_expected_kgcm2: float              # PIP (admisión esperada)

    # --- Fluid ---
    oil_api: float
    oil_sg: float                          # Peo [g/cm³]
    gas_sg: float                          # Peg
    water_sg: float                        # Pew [g/cm³]
    bubble_point_kgcm2: float              # Pb
    viscosity_cp: float

    # --- System ---
    frequency_hz: float = 50.0

    def __post_init__(self) -> None:
        if not (0.0 <= self.water_cut <= 1.0):
            raise ValueError(f"water_cut must be in [0, 1], got {self.water_cut}")
        if self.ref_depth_m <= self.suction_depth_m:
            # ΔP_ref would be non-positive; allowed but flagged by caller.
            pass
        if self.reservoir_pressure_kgcm2 <= 0:
            raise ValueError("reservoir_pressure_kgcm2 must be > 0")
        if self.pwf_test_kgcm2 >= self.reservoir_pressure_kgcm2:
            raise ValueError("pwf_test must be < reservoir_pressure (drawdown)")


@dataclass
class MetricDesignResult:
    """Complete ESP-01 metric design output with every reported intermediate."""
    pump_model: str
    frequency_hz: float

    # Step 3 — mixture gravity
    pem_gcc: float

    # Step 1 — admissible pressure at reference depth
    delta_p_ref_kgcm2: float
    padm_ref_kgcm2: float

    # Step 2 — reservoir maximum rate (Vogel from test)
    vogel_ratio_test: float
    qmax_m3d: float

    # Step 3 — production rate at admissible pressure
    production_pwf_kgcm2: float
    vogel_ratio_prod: float
    q_prod_m3d: float

    # Step 5 — pump curve read at operating frequency (affinity-corrected)
    head_per_stage_m: float
    hp_per_stage: float
    shutin_head_m: float          # Ho at operating frequency
    efficiency: float

    # Step 6 — tubing friction
    friction_unit_m_per_1000m: float
    friction_total_m: float

    # Step 7 — PIP at suction depth
    pip_suction_kgcm2: float

    # Step 8 — total dynamic head
    tdh_m: float                  # computed (anchor)
    tdh_reference_m: float        # cátedra lámina (informative only)
    tdh_components: dict

    # Step 9 — stages
    num_stages: int

    # Step 10 — housings
    housings: list                # list of (housing_id, count)
    housing_stages_total: int

    # Step 11 — housing burst check
    mhp_psi: float
    housing_rating: str           # "Standard" | "High-Pressure" | "Exceeds limit"
    housing_pressure_limit_psi: float

    # Step 12 — motor power + shaft check
    pump_hp: float
    shaft_sections: list          # per-housing cumulative shaft HP + rating
    n_high_resistance_housings: int

    # Step 13 — motors + voltage
    motors: list                  # list of motor dicts chosen
    motor_voltage_total_v: float
    motor_string_amps: float
    motor_hp_total: float

    # Step 14 — cooling
    fluid_velocity_ft_s: float
    fluid_velocity_reference_ft_s: float
    cooling_ok: bool

    # Step 15 — protector
    protector_model: str
    protector_type: str
    protector_qty: int

    # Step 16 — cable
    cable_size: str
    cable_conductor: str
    cable_drop_v: float
    cable_temp_correction: float

    # Step 17 — surface voltage
    surface_voltage_v: float

    warnings: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    alternatives: list = field(default_factory=list)


# ===========================================================================
# Step functions (pure)
# ===========================================================================

def step1_admissible_pressure(
    pem_gcc: float, ref_depth_m: float, suction_depth_m: float, pip_expected_kgcm2: float
) -> tuple[float, float]:
    """Paso 1 — presión admisible referida a la profundidad de referencia.

        ΔP_ref     = Pem·(Pref − Ps)/10
        Padm_a_ref = PIP + ΔP_ref

    El /10 es la convención de atmósfera técnica: 1 kgf/cm² ≈ 10 m de columna
    de agua.
    """
    delta = pem_gcc * (ref_depth_m - suction_depth_m) / 10.0
    return delta, pip_expected_kgcm2 + delta


def step2_qmax(pr_kgcm2: float, pwf_test_kgcm2: float, q_test_m3d: float) -> tuple[float, float]:
    """Paso 2 — caudal máximo del reservorio, desde un punto de ensayo (Vogel).

    Returns:
        ``(vogel_ratio, qmax)``, donde ``vogel_ratio = q_ensayo/qmax``.

    Reutiliza :func:`bes.core.ipr.vogel_qmax_from_test`, que es agnóstica de
    unidades — Vogel trabaja con relaciones adimensionales.
    """
    qmax = vogel_qmax_from_test(pr_kgcm2, pwf_test_kgcm2, q_test_m3d)
    return q_test_m3d / qmax, qmax


def step3_production(pr_kgcm2: float, pwf_kgcm2: float, qmax_m3d: float) -> tuple[float, float]:
    """Paso 3 — caudal de producción a la Pwf de trabajo, por Vogel.

    Returns:
        ``(vogel_ratio, q_prod)``.

    ``pwf_kgcm2`` es la Padm_a_ref. Ver §7-A: el ejercicio titula 31 pero
    calcula con 30, así que quien llama decide cuál pasar.
    """
    ratio = pwf_kgcm2 / pr_kgcm2
    vogel = 1.0 - 0.2 * ratio - 0.8 * ratio ** 2
    return vogel, qmax_m3d * vogel


def read_pump_curve_metric(
    pump: dict, f_op_hz: float, q_op_m3d: float
) -> dict:
    """Steps 4–5 — read a metric pump curve at the operating frequency.

    The curve is stored at ``pump['catalog_frequency_hz']``.  To read it at the
    operating frequency, apply the affinity laws (speed change only):

        Q_cat  = Q_op · (f_cat / f_op)            # enter the stored curve here
        H_op   = H_cat · (f_op / f_cat)²
        HP_op  = HP_cat · (f_op / f_cat)³
        Ho_op  = Ho_cat · (f_op / f_cat)²         # shut-in head

    Returns dict: ``head_per_stage_m``, ``hp_per_stage``, ``efficiency``,
    ``shutin_head_m``, ``q_catalog_m3d``.
    """
    f_cat = pump["catalog_frequency_hz"]
    q_cat = units.affinity_flow(q_op_m3d, f_op_hz, f_cat)

    curve = pump["performance_curve"]
    flows = np.array([p["flow_m3d"] for p in curve])
    heads = np.array([p["head_m_per_stage"] for p in curve])
    hps = np.array([p["hp_per_stage"] for p in curve])
    effs = np.array([p["efficiency"] for p in curve])

    head_cat = float(np.interp(q_cat, flows, heads))
    hp_cat = float(np.interp(q_cat, flows, hps))
    eff = float(np.interp(q_cat, flows, effs))
    ho_cat = pump["shutin_head_m_per_stage"]

    return {
        "head_per_stage_m": units.affinity_head(head_cat, f_cat, f_op_hz),
        "hp_per_stage": units.affinity_power(hp_cat, f_cat, f_op_hz),
        "efficiency": eff,
        "shutin_head_m": units.affinity_head(ho_cat, f_cat, f_op_hz),
        "q_catalog_m3d": q_cat,
    }


def step6_tubing_friction(
    q_m3d: float, tubing_id_in: float, length_m: float, c_factor: float = 95.0
) -> tuple[float, float]:
    """Step 6 — Hazen-Williams friction in tubing (metric formulation).

    F [m / 1000 m] = 2.083·(100/C)^1.852·(Q/5.454)^1.852 / ID^4.8655
    Tf [m]         = F · length_m / 1000

    Q in m³/d, ID in inches.  Returns ``(F_per_1000m, Tf)``.
    """
    f_unit = (
        2.083
        * (100.0 / c_factor) ** 1.852
        * (q_m3d / 5.454) ** 1.852
        / tubing_id_in ** 4.8655
    )
    return f_unit, f_unit * length_m / 1000.0


def step7_pip_at_suction(
    pwf_ref_kgcm2: float, ref_depth_m: float, suction_depth_m: float, pem_gcc: float
) -> float:
    """Paso 7 — PIP a la profundidad de succión (coherencia con el paso 1).

        PIP = Pwf_ref − (Pref − Ps)/10 · Pem
    """
    return pwf_ref_kgcm2 - (ref_depth_m - suction_depth_m) / 10.0 * pem_gcc


def step8_tdh(
    suction_depth_m: float,
    friction_total_m: float,
    discharge_pressure_kgcm2: float,
    pip_kgcm2: float,
    pem_gcc: float,
) -> tuple[float, dict]:
    """Step 8 — total dynamic head [m].

    TDH = Ps + Tf + head(Pbp) − head(PIP)      with head(P) = P·10/Pem
    """
    disch_head = units.pressure_to_head_m(discharge_pressure_kgcm2, pem_gcc)
    pip_head = units.pressure_to_head_m(pip_kgcm2, pem_gcc)
    tdh = suction_depth_m + friction_total_m + disch_head - pip_head
    components = {
        "suction_depth_m": suction_depth_m,
        "friction_total_m": friction_total_m,
        "discharge_head_m": disch_head,
        "pip_head_m": pip_head,
    }
    return tdh, components


def step9_stages(tdh_m: float, head_per_stage_m: float) -> int:
    """Step 9 — number of stages = ceil(TDH / head_per_stage)."""
    if head_per_stage_m <= 0:
        raise ValueError("head_per_stage_m must be > 0")
    return math.ceil(tdh_m / head_per_stage_m)


def select_housings(target_stages: int, housing_stages: dict) -> tuple[list, int]:
    """Paso 10 — elige las carcasas que cubran la cantidad de etapas necesaria.

    Regla: primero minimizar las etapas de más (el total tiene que ser >= al
    objetivo), y después minimizar la cantidad de carcasas.

    Args:
        housing_stages: Diccionario que mapea id de carcasa -> etapas por
            carcasa.

    Returns:
        ``(lista_de_(id_carcasa, cantidad), etapas_totales)``.
    """
    # invert stages -> housing id (prefer smallest id if a stage count repeats)
    size_to_id: dict[int, str] = {}
    for hid, stages in housing_stages.items():
        if stages not in size_to_id:
            size_to_id[stages] = hid
    sizes = sorted(size_to_id.keys())
    max_size = sizes[-1]

    cap = target_stages + max_size
    INF = float("inf")
    dp = [INF] * (cap + 1)
    prev = [-1] * (cap + 1)
    dp[0] = 0
    for t in range(1, cap + 1):
        for s in sizes:
            if t - s >= 0 and dp[t - s] + 1 < dp[t]:
                dp[t] = dp[t - s] + 1
                prev[t] = s

    total = next((t for t in range(target_stages, cap + 1) if dp[t] < INF), None)
    if total is None:
        raise ValueError("No housing combination could cover the required stages")

    counts: dict[str, int] = {}
    t = total
    while t > 0:
        s = prev[t]
        hid = size_to_id[s]
        counts[hid] = counts.get(hid, 0) + 1
        t -= s
    housings = sorted(counts.items(), key=lambda kv: -housing_stages[kv[0]])
    return housings, total


def step11_housing_burst(
    shutin_head_m: float, num_stages: int, pem_gcc: float, pump: dict
) -> tuple[float, str, float]:
    """Step 11 — housing burst-pressure check.

    MHP[psi] = Ho[m]·Etapas·Pem·1.4206

    Returns ``(mhp_psi, rating, applied_limit_psi)`` where rating is
    "Standard", "High-Pressure" or "Exceeds limit".
    """
    mhp = units.head_m_to_psi(shutin_head_m * num_stages, pem_gcc)
    limit_std = pump["housing_pressure_limit_psi_std"]
    limit_hp = pump["housing_pressure_limit_psi_hp"]
    if mhp <= limit_std:
        return mhp, "Standard", limit_std
    if mhp <= limit_hp:
        return mhp, "High-Pressure", limit_hp
    return mhp, "Exceeds limit", limit_hp


def step12_pump_hp_and_shaft(
    hp_per_stage: float, pem_gcc: float, housings: list, housing_stages: dict, shaft_limit_std: float
) -> tuple[float, list, int]:
    """Paso 12 (+§7-C) — potencia de la bomba y verificación de eje por carcasa.

        HP total = (HP/etapa) · Etapas · Pem

    **El motor va abajo**, así que el eje transmite la potencia completa de la
    bomba en la carcasa inferior y cada vez menos hacia arriba. La sección de
    eje que alimenta cada carcasa carga la potencia acumulada de esa carcasa
    más la de todas las que tiene encima.

    Las secciones que transmitan más que ``shaft_limit_std`` necesitan eje de
    alta resistencia.

    Returns:
        ``(hp_total, secciones_de_eje, n_alta_resistencia)``, donde
        ``secciones_de_eje`` va de abajo hacia arriba, cada una con
        ``{"housing_id", "housing_hp", "cumulative_shaft_hp", "shaft"}``.
    """
    # Expand housings into a bottom→top ordered list of stage counts.
    ordered_stage_counts: list[tuple[str, int]] = []
    for hid, count in housings:
        for _ in range(count):
            ordered_stage_counts.append((hid, housing_stages[hid]))

    total_stages = sum(s for _, s in ordered_stage_counts)
    total_hp = hp_per_stage * total_stages * pem_gcc

    sections: list[dict] = []
    n_hr = 0
    stages_below = 0
    for hid, stages in ordered_stage_counts:
        housing_hp = hp_per_stage * stages * pem_gcc
        # cumulative HP transmitted by the shaft at the base of this housing:
        # everything from this housing upward = total minus what is below it.
        cumulative = hp_per_stage * (total_stages - stages_below) * pem_gcc
        shaft = "HR" if cumulative > shaft_limit_std else "STD"
        if shaft == "HR":
            n_hr += 1
        sections.append({
            "housing_id": hid,
            "housing_hp": housing_hp,
            "cumulative_shaft_hp": cumulative,
            "shaft": shaft,
        })
        stages_below += stages

    return total_hp, sections, n_hr


def select_motors(
    catalog: MetricCatalog, required_hp: float, max_units: int = 2, amp_tol: float = 3.0
) -> dict:
    """Paso 13 — elige uno o dos motores de la serie que cubran la potencia.

    Las reglas:

        - la potencia total tiene que ser >= la requerida, minimizando el
          excedente;
        - las corrientes tienen que ser compatibles (diferencia máxima entre
          amperajes <= ``amp_tol``), porque los motores apilados van **en
          serie** y por los dos pasa la misma corriente;
        - como desempate, la mayor tensión total.

    Returns:
        dict con ``motors`` (lista), ``total_hp``, ``total_voltage`` y
        ``string_amps``.
    """
    from itertools import combinations_with_replacement

    motors = catalog.get_all_motors()
    best: Optional[dict] = None
    best_key: Optional[tuple] = None

    for n_units in range(1, max_units + 1):
        for combo in combinations_with_replacement(motors, n_units):
            amps = [m["amperage"] for m in combo]
            if max(amps) - min(amps) > amp_tol:
                continue
            total_hp = sum(m["hp_rating"] for m in combo)
            if total_hp < required_hp:
                continue
            total_v = sum(m["voltage"] for m in combo)
            # minimize excess HP, then maximize total voltage
            key = (total_hp - required_hp, -total_v)
            if best_key is None or key < best_key:
                best_key = key
                best = {
                    "motors": list(combo),
                    "total_hp": total_hp,
                    "total_voltage": total_v,
                    "string_amps": max(amps),
                }

    if best is None:
        raise ValueError(
            f"No motor combination (≤{max_units} units) covers {required_hp:.1f} HP "
            f"with compatible currents"
        )
    return best


def fluid_velocity_past_motor(
    q_prod_m3d: float, casing_id_in: float, motor_od_in: float
) -> float:
    """Step 14 — fluid velocity in the casing/motor annulus [ft/s].

    v = Q / A_annulus, with A_annulus = π/4·(casing_id² − motor_od²).
    """
    q_bbl = units.m3d_to_bpd(q_prod_m3d)
    q_ft3_s = q_bbl * _FT3_PER_BBL / _SECONDS_PER_DAY
    area_in2 = math.pi / 4.0 * (casing_id_in ** 2 - motor_od_in ** 2)
    if area_in2 <= 0:
        raise ValueError("motor OD does not fit inside casing ID")
    area_ft2 = area_in2 / 144.0
    return q_ft3_s / area_ft2


def select_protector(catalog: MetricCatalog, num_stages: int) -> dict:
    """Paso 15 — elige el protector / sello para la cantidad de etapas.

    Si las etapas necesarias superan la capacidad del cojinete flotante
    estándar, se elige un protector de cojinete de alta carga (en tándem,
    cantidad 2, como en el ejercicio); si no, un solo protector estándar.
    """
    seals = catalog.get_all_seals()
    std = next((s for s in seals if s["bearing"] == "floater_std"), None)
    high = next((s for s in seals if s["bearing"] == "high_load"), None)
    if std is not None and num_stages <= std["max_stages"]:
        return {"seal": std, "qty": 1}
    if high is None or num_stages > high["max_stages"]:
        raise ValueError(f"No protector bearing carries {num_stages} stages")
    return {"seal": high, "qty": 2}


def select_cable(
    catalog: MetricCatalog,
    current_a: float,
    length_m: float,
    ambient_temp_c: float,
    max_drop_v_per_100m: float = 10.0,
) -> dict:
    """Paso 16 — elige el cable y calcula la caída de tensión total.

    Toma el conductor más chico (o sea el más barato) cuya ampacidad sea >= a
    la corriente y cuya caída corregida por temperatura no supere el máximo
    admitido::

        caída_100m = vdrop_por_amper · I · factor_temperatura
        total      = caída_100m · (largo_m / 100)

    Returns:
        dict con ``cable``, ``temp_factor``, ``drop_per_100m`` y
        ``total_drop_v``.
    """
    temp_factor = catalog.cable_temp_correction_factor(ambient_temp_c)
    # smallest conductor = largest AWG number = highest vdrop_per_amp; iterate
    # from smallest to largest conductor and take the first that passes.
    cables = sorted(
        catalog.get_all_cables(), key=lambda c: -c["vdrop_v_per_100m_per_amp"]
    )
    for cable in cables:
        if cable["max_amps"] < current_a:
            continue
        drop_100m = cable["vdrop_v_per_100m_per_amp"] * current_a * temp_factor
        if drop_100m <= max_drop_v_per_100m:
            return {
                "cable": cable,
                "temp_factor": temp_factor,
                "drop_per_100m": drop_100m,
                "total_drop_v": drop_100m * length_m / 100.0,
            }
    raise ValueError(
        f"No cable keeps the drop ≤ {max_drop_v_per_100m} V/100m at {current_a} A "
        f"/ {ambient_temp_c} °C"
    )


# ===========================================================================
# Orchestrator
# ===========================================================================

def design_esp_metric(
    inp: MetricDesignInput,
    catalog: "MetricCatalog",
    pump_model: Optional[str] = None,
    production_pwf_kgcm2: Optional[float] = None,
    motor_od_in: float = 4.0,
) -> MetricDesignResult:
    """Corre el diseño métrico ESP-01 completo y devuelve el resultado.

    Es el punto de entrada del módulo: orquesta los 17 pasos en orden.

    Args:
        inp: Datos del pozo, producción y fluido, en unidades métricas.
        catalog: Catálogo de equipos métrico, **inyectado por quien llama**.
            ``bes.core`` es la capa de más abajo y nunca importa
            ``bes.catalogs`` por su cuenta; se construye con
            ``MetricCatalog()``, que ubica el JSON que viaja con el paquete.
        pump_model: Fuerza una bomba concreta. Si es ``None``, se elige la que
            necesita menos etapas entre las que entran en el casing, y el
            resto se devuelven como ``alternatives``.
        production_pwf_kgcm2: Override de §7-A para la Pwf del paso 3. Por
            defecto usa la presión admisible Padm_a_ref (o sea 31 en el
            ESP 01); pasar 30 reproduce la aritmética de la lámina.
        motor_od_in: Diámetro exterior del motor [in], para la verificación de
            velocidad del fluido por el anular.

    Returns:
        :class:`MetricDesignResult` con todos los intermedios que informa el
        ejercicio.
    """
    warnings: list[str] = []
    notes: list[str] = []

    # --- shared quantities ---
    pem = units.mixture_specific_gravity(inp.oil_sg, inp.water_sg, inp.water_cut)

    delta_p_ref, padm_ref = step1_admissible_pressure(
        pem, inp.ref_depth_m, inp.suction_depth_m, inp.pip_expected_kgcm2
    )
    vogel_test, qmax = step2_qmax(
        inp.reservoir_pressure_kgcm2, inp.pwf_test_kgcm2, inp.q_test_m3d
    )
    prod_pwf = production_pwf_kgcm2 if production_pwf_kgcm2 is not None else padm_ref
    vogel_prod, q_prod = step3_production(
        inp.reservoir_pressure_kgcm2, prod_pwf, qmax
    )
    if q_prod > inp.q_target_m3d:
        q_prod = inp.q_target_m3d  # never produce more than the target
        notes.append("Q_prod limitado al objetivo Qd.")
    elif qmax < inp.q_target_m3d:
        notes.append(
            f"Qmax ({qmax:.0f} m³/d) < Qd ({inp.q_target_m3d:.0f}); "
            "el reservorio no alcanza el objetivo."
        )

    friction_unit, friction_total = step6_tubing_friction(
        q_prod, inp.tubing_id_in, inp.suction_depth_m
    )
    pip_suction = step7_pip_at_suction(
        padm_ref, inp.ref_depth_m, inp.suction_depth_m, pem
    )
    tdh, tdh_components = step8_tdh(
        inp.suction_depth_m, friction_total,
        inp.discharge_pressure_kgcm2, pip_suction, pem,
    )

    # --- candidate pumps (fit casing + operating flow covered) ---
    candidates = catalog.get_pumps_by_casing(inp.casing_id_in)
    if pump_model is not None:
        candidates = [catalog.get_pump(pump_model)]
    if not candidates:
        raise ValueError("No metric pump fits the casing ID")

    designs: list[tuple[dict, dict, int]] = []
    for pump in candidates:
        read = read_pump_curve_metric(pump, inp.frequency_hz, q_prod)
        q_cat = read["q_catalog_m3d"]
        if not (pump["min_flow_m3d"] <= q_cat <= pump["max_flow_m3d"]):
            continue
        stages = step9_stages(tdh, read["head_per_stage_m"])
        designs.append((pump, read, stages))

    if not designs:
        raise ValueError("No metric pump covers the operating flow at this frequency")

    # primary = fewest stages
    designs.sort(key=lambda d: d[2])
    pump, read, num_stages = designs[0]
    alternatives = [
        f"{p['model']}: {s} etapas ({r['head_per_stage_m']:.2f} m/etapa)"
        for p, r, s in designs[1:]
    ]

    housing_stages = pump["housing_stages"]
    housings, housing_total = select_housings(num_stages, housing_stages)

    mhp, housing_rating, housing_limit = step11_housing_burst(
        read["shutin_head_m"], num_stages, pem, pump
    )
    if housing_rating == "Exceeds limit":
        warnings.append(f"MHP {mhp:.0f} psi supera el límite de housing {housing_limit:.0f} psi.")

    pump_hp, shaft_sections, n_hr = step12_pump_hp_and_shaft(
        read["hp_per_stage"], pem, housings, housing_stages, pump["shaft_hp_limit_std"]
    )
    if n_hr > 0:
        notes.append(
            f"{n_hr} housing(s) requieren eje de alta resistencia (HP acumulado > "
            f"{pump['shaft_hp_limit_std']} HP); el resto, eje estándar."
        )

    motor_sel = select_motors(catalog, pump_hp)
    velocity = fluid_velocity_past_motor(q_prod, inp.casing_id_in, motor_od_in)
    cooling_ok = velocity >= 1.0
    if not cooling_ok:
        warnings.append(f"Velocidad de refrigeración {velocity:.2f} ft/s < 1 ft/s.")

    protector = select_protector(catalog, num_stages)
    cable_sel = select_cable(
        catalog, motor_sel["string_amps"], inp.suction_depth_m, inp.temp_bottom_c
    )
    surface_v = motor_sel["total_voltage"] + cable_sel["total_drop_v"]

    return MetricDesignResult(
        pump_model=pump["model"],
        frequency_hz=inp.frequency_hz,
        pem_gcc=pem,
        delta_p_ref_kgcm2=delta_p_ref,
        padm_ref_kgcm2=padm_ref,
        vogel_ratio_test=vogel_test,
        qmax_m3d=qmax,
        production_pwf_kgcm2=prod_pwf,
        vogel_ratio_prod=vogel_prod,
        q_prod_m3d=q_prod,
        head_per_stage_m=read["head_per_stage_m"],
        hp_per_stage=read["hp_per_stage"],
        shutin_head_m=read["shutin_head_m"],
        efficiency=read["efficiency"],
        friction_unit_m_per_1000m=friction_unit,
        friction_total_m=friction_total,
        pip_suction_kgcm2=pip_suction,
        tdh_m=tdh,
        tdh_reference_m=TDH_ESP01_CATEDRA_REFERENCE_M,
        tdh_components=tdh_components,
        num_stages=num_stages,
        housings=housings,
        housing_stages_total=housing_total,
        mhp_psi=mhp,
        housing_rating=housing_rating,
        housing_pressure_limit_psi=housing_limit,
        pump_hp=pump_hp,
        shaft_sections=shaft_sections,
        n_high_resistance_housings=n_hr,
        motors=motor_sel["motors"],
        motor_voltage_total_v=motor_sel["total_voltage"],
        motor_string_amps=motor_sel["string_amps"],
        motor_hp_total=motor_sel["total_hp"],
        fluid_velocity_ft_s=velocity,
        fluid_velocity_reference_ft_s=FLUID_VELOCITY_ESP01_REFERENCE_FT_S,
        cooling_ok=cooling_ok,
        protector_model=protector["seal"]["model"],
        protector_type=protector["seal"]["type"],
        protector_qty=protector["qty"],
        cable_size=cable_sel["cable"]["size"],
        cable_conductor=cable_sel["cable"]["conductor"],
        cable_drop_v=cable_sel["total_drop_v"],
        cable_temp_correction=cable_sel["temp_factor"],
        surface_voltage_v=surface_v,
        warnings=warnings,
        notes=notes,
        alternatives=alternatives,
    )
