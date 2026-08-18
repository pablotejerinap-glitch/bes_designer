"""Verificación mecánica de la bomba: eje y cojinete de empuje.

Va de la mano con :mod:`bes.core.housing`, que cubre la tercera verificación de
la misma familia (la presión que aguanta la carcasa). Entre los tres módulos
responden la nota al pie que los fabricantes imprimen en toda hoja de datos:

    «Maximum staging may be limited by housing pressure limit, shaft capacity
     or thrust loading.»

O sea: **hay tres topes distintos a la cantidad de etapas** y el diseño tiene
que respetar el MENOR de los tres. Una sarta que entra holgada en la presión de
carcasa igual puede torcer el eje.

Los tres topes
--------------
    1. Presión de carcasa   -> housing.py
    2. Capacidad del eje    -> este módulo
    3. Carga sobre el cojinete de empuje -> este módulo

Las fórmulas (apuntes de cátedra, Unidad N°9 pág. 140)
------------------------------------------------------
**Potencia sobre el eje**::

    HP_eje = P_etapa · #Etapas · Pem

**Carga sobre el cojinete**::

    Carga TL = Ho · Pem · A_eje

donde ``Ho`` es la elevación que la bomba tiene que levantar hasta boca de pozo
y ``A_eje`` la sección transversal del eje.

Una errata del apunte, ya resuelta
----------------------------------
El impreso dice ``Carga TL = Ho · #Etapas · Pem · A_eje``, pero ahí mismo
define ``Ho`` como la elevación **total**, que ya es la suma de lo que aporta
cada etapa: el factor ``#Etapas`` cuenta la columna dos veces.

Con 1500 m de elevación y una bomba de 250 etapas, la forma impresa da
**198 000 lbs** contra sellos calificados para 5 000–30 000 lbs. Sin ese
factor da **792 lbs**, que coincide con la estimación de Takács que ya usa el
diseño eléctrico (779 lbs en el mismo caso). Por eso se toma como tipeo y se
descarta. **No volver a agregarlo.**

De dónde salen los datos
------------------------
Del catálogo por serie (``pump_series.json``). Una serie sin ficha deja todas
las verificaciones **SIN REALIZAR** — y se reporta así, nunca como aprobadas.
Hoy sólo está cargada la serie 400, de la hoja *ENGINEERING DATA TD1750 50Hz*
de Wood Group. **No agregar series con valores estimados.**

Nomenclatura
------------
    HP_eje    Potencia que el eje tiene que transmitir      [hp]
    P_etapa   Potencia por etapa, de la curva de catálogo   [hp/etapa]
    #Etapas   Cantidad de etapas activas                    [-]
    Pem       Gravedad específica media del fluido bombeado [-]
    Ho        Elevación hasta boca de pozo                  [ft]
    A_eje     Sección transversal del eje                   [in²]
    TL        Thrust Load: carga axial sobre el cojinete    [lbs]
    BHT       Bottom Hole Temperature: temperatura de fondo [°F]
"""
from __future__ import annotations

import math

# Presión de una columna de fluido: 1 psi = 2.31 ft de agua.
_FT_PER_PSI = 2.31
_LBS_PER_KG = 2.2046226


def shaft_power(hp_per_stage: float, stages: int, pem: float) -> float:
    """Potencia que el eje tiene que transmitir [hp].

        HP_eje = P_etapa · #Etapas · Pem

    El ``hp/etapa`` del catálogo está calibrado para agua (SG = 1), de ahí el
    factor ``Pem`` con la gravedad específica de la mezcla real.

    Es la misma magnitud que devuelve
    :func:`bes.core.pump_design.calculate_motor_hp`; se vuelve a escribir acá
    porque es el dato de entrada de la verificación del eje, y tenerla con
    nombre propio hace que el módulo se lea como el procedimiento de cátedra.

    Args:
        hp_per_stage: Potencia por etapa al caudal de operación [hp/etapa].
        stages: Cantidad de etapas activas.
        pem: Gravedad específica media del fluido bombeado.

    Returns:
        Potencia sobre el eje [hp]. Cero si algún argumento no es positivo.
    """
    if hp_per_stage <= 0 or stages <= 0 or pem <= 0:
        return 0.0
    return hp_per_stage * stages * pem


def shaft_hp_limit_at_frequency(
    limit_hp: float, limit_frequency_hz: float, frequency_hz: float
) -> float:
    """Lleva el límite de potencia del eje a otra frecuencia [hp].

    Lo que aguanta un eje es un **torque**, no una potencia. Y potencia es
    torque por velocidad, así que a torque constante la potencia admisible
    escala linealmente con la frecuencia::

        HP_limite(f) = HP_limite(f_ref) · f / f_ref

    Importa porque los catálogos publican el límite a una frecuencia sola —la
    hoja de Wood Group a 50 Hz, la de Alkhorayef a 60 Hz— y comparar un diseño
    de 60 Hz contra un límite de 50 Hz subestima el eje en un 20 %.

    Ejemplo: los 104 hp que la hoja de Wood Group da a 50 Hz son 124.8 hp a
    60 Hz.

    Args:
        limit_hp: Límite publicado [hp].
        limit_frequency_hz: Frecuencia a la que se publicó ese límite [Hz].
        frequency_hz: Frecuencia del diseño [Hz].

    Returns:
        Límite a la frecuencia del diseño [hp].

    Raises:
        ValueError: Si alguna de las dos frecuencias no es positiva.
    """
    if limit_frequency_hz <= 0:
        raise ValueError(
            f"limit_frequency_hz must be > 0, got {limit_frequency_hz}"
        )
    if frequency_hz <= 0:
        raise ValueError(f"frequency_hz must be > 0, got {frequency_hz}")
    return limit_hp * frequency_hz / limit_frequency_hz


def bearing_load_tl(lift_ft: float, pem: float, shaft_area_in2: float) -> float:
    """Carga axial sobre el cojinete de empuje de la sección sellante [lbs].

        Carga TL = Ho · Pem · A_eje

    Es la presión de la columna que la bomba tiene que levantar, actuando sobre
    la sección del eje. En unidades de campo, la elevación en pies se pasa a
    presión con la constante de siempre::

        TL [lbs] = (Ho [ft] · Pem / 2.31) · A_eje [in²]

    Ver la nota del encabezado del módulo sobre el factor ``#Etapas`` que trae
    el apunte impreso y que acá se descarta a propósito.

    Args:
        lift_ft: Elevación que la bomba tiene que levantar hasta boca de
            pozo [ft].
        pem: Gravedad específica media del fluido bombeado.
        shaft_area_in2: Sección transversal del eje [in²].

    Returns:
        Carga axial [lbs]. Cero si algún argumento no es positivo.
    """
    if lift_ft <= 0 or pem <= 0 or shaft_area_in2 <= 0:
        return 0.0
    return lift_ft * pem / _FT_PER_PSI * shaft_area_in2


def bearing_load_kg(lift_ft: float, pem: float, shaft_area_in2: float) -> float:
    """Same load as :func:`bearing_load_tl`, in kg — the cátedra's unit."""
    return bearing_load_tl(lift_ft, pem, shaft_area_in2) / _LBS_PER_KG


def shaft_area_in2(series: dict) -> float:
    """Sección transversal del eje de una serie [in²].

    Los catálogos publican tanto el área como el diámetro, y coinciden
    (239.51 mm² = π/4 · 17.463 mm²). Cuando está el área publicada, gana: así
    el número es del fabricante y no nuestro.

    Args:
        series: Ficha de la serie, del catálogo.

    Returns:
        Sección del eje [in²]. Cero si la serie no publica ninguno de los dos.
    """
    area = float(series.get("shaft_area_in2") or 0.0)
    if area > 0:
        return area
    d = float(series.get("shaft_diameter_in") or 0.0)
    return math.pi / 4.0 * d ** 2 if d > 0 else 0.0


def verify_shaft(
    hp_shaft: float, series: dict | None, frequency_hz: float
) -> dict:
    """Verifica la potencia sobre el eje contra los límites de la serie.

    Pasarse del límite **estándar** no es una falla: significa que hace falta un
    eje de alta resistencia, igual que una carcasa sobrepresionada pide una
    carcasa de alta presión. Recién pasarse del límite de alta resistencia hace
    inviable el diseño.

    Args:
        hp_shaft: Potencia sobre el eje [hp], la que da :func:`shaft_power`.
        series: Ficha de la serie del catálogo, o ``None`` si no se conoce.
        frequency_hz: Frecuencia del diseño [Hz], para llevar el límite
            publicado a la frecuencia real.

    Returns:
        dict con ``verified`` (False = el catálogo no tiene datos de esta
        serie), ``hp_shaft``, ``limit_std``, ``limit_high_strength``,
        ``shaft_type`` (``"standard"`` / ``"high_strength"`` / ``""``),
        ``ok`` y ``note``.
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
    """Verifica la cantidad de etapas contra la capacidad del cojinete de empuje.

    Los fabricantes publican este tope como una **cantidad de etapas con un
    límite de temperatura**, no como una carga: la serie 400 de Wood Group
    admite 303 etapas con el cojinete estándar hasta 230 °F, o 1529 con el de
    alta carga hasta 250 °F. Es así porque el material del cojinete pierde
    capacidad al calentarse.

    **Las dos condiciones atan**: un pozo más caliente que el tope descarta ese
    cojinete por más pocas etapas que lleve.

    Args:
        stages: Etapas activas de la sarta.
        bottom_hole_temp_f: Temperatura de fondo [°F].
        series: Ficha de la serie del catálogo, o ``None`` si no se conoce.

    Returns:
        dict con ``verified``, ``stages``, ``limit_stages``, ``bearing_type``
        (``"standard"`` / ``"high_load"`` / ``""``), ``bht_max_f``, ``ok`` y
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
    """Máximo de etapas que permite la presión de carcasa. 0 si no se conoce.

    Es la inversa de ``MaxP = P(Q0) · #Etapas · Pem`` — ver
    :mod:`bes.core.housing`.

    Args:
        shut_in_head_psi: Presión que da la bomba a caudal cero, por
            etapa [psi/etapa].
        pressure_limit_psi: Presión que aguanta la carcasa [psi].
        pem: Gravedad específica media del fluido bombeado.

    Returns:
        Cantidad máxima de etapas.
    """
    if limit_psi <= 0 or shutin_head_per_stage <= 0 or pem <= 0:
        return 0
    per_stage_psi = shutin_head_per_stage * pem / _FT_PER_PSI
    return int(limit_psi // per_stage_psi) if per_stage_psi > 0 else 0


def max_stages_by_bearing(
    bottom_hole_temp_f: float, series: dict | None
) -> int:
    """Máximo de etapas que permite el cojinete a esta temperatura.

    Devuelve 0 cuando la serie no tiene datos, y también 0 cuando el pozo está
    más caliente que todas las opciones de cojinete — ahí no hay ninguna
    cantidad de etapas admisible.

    Args:
        bottom_hole_temp_f: Temperatura de fondo [°F].
        series: Ficha de la serie del catálogo, o ``None``.

    Returns:
        Cantidad máxima de etapas, 0 si no hay dato o si el pozo es demasiado
        caliente.
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
    """Los tres topes a la cantidad de etapas, y cuál manda.

    Es la nota al pie del fabricante convertida en número: el diseño queda
    limitado por la presión de carcasa, por la capacidad del eje o por la carga
    sobre el cojinete, **lo que muerda primero**.

    Los topes sin datos se reportan como 0 y quedan EXCLUIDOS de la
    comparación, no tratados como un límite de cero etapas — que sería decir
    que no se puede instalar ninguna.

    Returns:
        dict con ``by_housing_pressure``, ``by_shaft``, ``by_bearing``,
        ``governing`` (el tope que manda, 0 si no se conoce ninguno) y
        ``governing_by`` (cuál de los tres es, ``""`` si ninguno).
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


# --------------------------------------------------------------------------
# Traza de fórmulas
# --------------------------------------------------------------------------

def mechanical_trace(
    hp_per_stage: float,
    stages: int,
    pem: float,
    lift_ft: float,
    shutin_head_per_stage: float,
    active_stages: int,
    housing_limit_psi: float,
    bottom_hole_temp_f: float,
    series: dict | None,
    frequency_hz: float,
) -> list[dict]:
    """Las tres verificaciones mecánicas con sus números, y cuál manda.

    Función aparte, como :func:`bes.core.ipr.ipr_trace`, para no cambiarle la
    firma a las funciones puras. Llama a las mismas que usa el diseño.

    Args:
        hp_per_stage: Potencia por etapa de la curva de catálogo [hp/etapa].
        stages: Etapas de la sarta [-].
        pem: Gravedad específica media del fluido bombeado [-].
        lift_ft: Elevación hasta boca de pozo [ft].
        shutin_head_per_stage: Altura por etapa a caudal cero [ft/etapa].
        active_stages: Etapas activas acumuladas en la carcasa crítica [-].
        housing_limit_psi: Presión admisible de la carcasa [psi].
        bottom_hole_temp_f: Temperatura de fondo [°F].
        series: Ficha de la serie (``pump_series.json``) o ``None``.
        frequency_hz: Frecuencia de operación [Hz].

    Returns:
        Lista de dicts de :class:`bes.core.formulas.Formula`. Las verificaciones
        sin datos de serie **no** emiten fórmula: quedan sin realizar, que no es
        lo mismo que aprobadas.
    """
    from bes.core.formulas import FormulaTrace
    from bes.core.housing import housing_pressure_psi

    trace = FormulaTrace()

    trace.add(
        "mec_potencia_eje",
        {"P_etapa": hp_per_stage, "N": stages, "Pem": pem},
        shaft_power(hp_per_stage, stages, pem),
    )

    if series:
        limite = series.get("shaft_hp_limit_std") or 0.0
        f_ref = series.get("reference_frequency_hz") or 0.0
        if limite > 0 and f_ref > 0:
            trace.add(
                "mec_limite_eje_frecuencia",
                {"HP_lim(f_ref)": limite, "f_ref": f_ref, "f": frequency_hz},
                shaft_hp_limit_at_frequency(limite, f_ref, frequency_hz),
                context=f"El fabricante publica el límite a {f_ref:.0f} Hz y "
                        f"este diseño corre a {frequency_hz:.0f} Hz.",
            )

    area = shaft_area_in2(series or {})
    if area > 0:
        trace.add(
            "mec_carga_cojinete",
            {"Ho": lift_ft, "Pem": pem, "A_eje": area},
            bearing_load_tl(lift_ft, pem, area),
            context="Ho es la elevación TOTAL, así que no lleva el factor "
                    "«× N etapas» que trae impreso el apunte.",
        )

    if shutin_head_per_stage > 0 and active_stages > 0:
        trace.add(
            "mec_presion_carcasa",
            {"P(Q=0)": shutin_head_per_stage, "N_activas": active_stages,
             "Pem": pem},
            housing_pressure_psi(shutin_head_per_stage, active_stages, pem),
            context=(
                f"Contra un límite de {housing_limit_psi:,.0f} psi."
                if housing_limit_psi > 0 else
                "Sin límite publicado para esta carcasa: queda SIN VERIFICAR."
            ),
        )

    topes = staging_ceiling(
        hp_per_stage=hp_per_stage,
        shutin_head_per_stage=shutin_head_per_stage,
        pem=pem,
        bottom_hole_temp_f=bottom_hole_temp_f,
        housing_limit_psi=housing_limit_psi,
        series=series,
        frequency_hz=frequency_hz,
    )
    if topes["governing"] > 0:
        trace.add(
            "mec_tope_etapas",
            {"N_carcasa": topes["by_housing_pressure"],
             "N_eje": topes["by_shaft"],
             "N_cojinete": topes["by_bearing"]},
            topes["governing"],
            context=f"Manda «{topes['governing_by']}». Un tope en 0 es una "
                    f"verificación SIN DATOS, no un límite de cero etapas: se "
                    f"excluye de la comparación.",
        )
    return trace.as_list()
