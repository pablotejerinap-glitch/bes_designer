"""
Crudos viscosos — procedimiento de Riling (Brown Vol. 2b, §4.53112).

Una curva de bomba se levanta con agua limpia: SG = 1.0 y ~1 cp. Un crudo
viscoso rompe las tres promesas de esa curva —entrega menos caudal, desarrolla
menos altura y consume más potencia—, así que hay que corregirla antes de
seleccionar.

Los ocho pasos del procedimiento y dónde vive cada uno:

    1. TDH bombeando agua de SG 1.0            -> bes.core.tdh (ya existía)
    2. Viscosidad del crudo SIN gas            -> crude_viscosity_ssu()
    3. Corregir por gas en solución            -> crude_viscosity_ssu()
    4. Convertir a SSU                         -> crude_viscosity_ssu()
    5. Corregir por corte de agua              -> parámetro measured_ssu (ver abajo)
    6. Factores de las tablas 4.520 / 4.521    -> viscosity_factors()
    7. Elegir bomba y motor                    -> water_equivalent_duty()
    8. Resto del equipo                        -> el flujo normal de diseño

El sentido de la corrección
---------------------------
Es el punto que más se equivoca. Las tablas dicen **qué fracción de su curva de
agua entrega la bomba con el crudo**. Para SELECCIONAR hay que ir al revés:

    Q_agua = Q_pedido / C_Q          H_agua = H_pedido / C_H

Es decir, si el pozo pide 1700 b/d y 5230 ft con el crudo, hay que buscar una
bomba que **con agua** dé 1932 b/d y 5893 ft. Multiplicar en vez de dividir
subdimensiona el equipo.

Los dos modelos que implementa este módulo
------------------------------------------
Contestan preguntas distintas y por eso conviven:

*Riling / Brown* (secciones 1 a 5) devuelve **un** juego de factores a partir de
la viscosidad y la clase de rendimiento de la bomba. No hace falta saber qué
bomba es, así que sirve **antes** de elegirla: es lo que permite invertir el
sentido y salir a buscar en el catálogo.

*Hydraulic Institute*, curve-fiteado por Turzo et al. (sección 6), corrige la
altura en **cuatro puntos** de la curva y depende del BEP de la bomba concreta.
No sirve para buscar —hay que saber ya cuál es la bomba— pero devuelve la curva
corregida completa, así que sirve **después**, para verificar la elegida.

Documentación completa, con los ejemplos resueltos y las decisiones tomadas:
``docs/CRUDOS_VISCOSOS.md``.
"""

from __future__ import annotations

import json
from bisect import bisect_left
from math import log10
from pathlib import Path

# Los pasos 2 y 3 de Riling salen de las láminas del Apéndice 4L, no de una
# correlación: ver dead_oil_viscosity_chart() y gas_saturated_viscosity_chart().
# Por eso este módulo ya no importa nada de pvt.py.

# --------------------------------------------------------------------------
# Tablas de corrección (dato del catálogo, con procedencia)
# --------------------------------------------------------------------------
_TABLES_PATH = Path(__file__).parent.parent / "catalogs" / "viscosity_correction.json"
_TABLES: dict | None = None

#: Digitalización de la Fig. 4L del libro (ver el ``_source`` del archivo).
_CHARTS_PATH = Path(__file__).parent.parent / "catalogs" / "viscosity_charts.json"
_CHARTS: dict | None = None

#: Rendimientos para los que el libro publica tabla. Fuera de este rango no se
#: extrapola: se acota al extremo más cercano y se avisa.
_TABLE_EFFICIENCIES = (60.0, 70.0)

#: Frontera entre crudo liviano y pesado [°API].
#:
#: De 28 °API para arriba el crudo es liviano y **no se trata como viscoso**:
#: no hace falta corregir la curva de la bomba. Por debajo, la viscosidad
#: empieza a pesar y hay que analizarla.
#:
#: El corte no es arbitrario. Evaluando la cadena completa —viscosidad de la
#: Fig. 4L(2), conversión a SSU y factores de la Tabla 4.521— en el umbral:
#:
#:     28 °API a 120 °F -> 18.8 cp -> 102 SSU -> C_Q = 99.0 %, C_H =  99.5 %
#:     28 °API a 180 °F -> 10.4 cp ->  65 SSU -> C_Q = 99.8 %, C_H = 100.0 %
#:
#: (Con Beggs-Robinson, que es lo que se usaba antes de digitalizar la lámina,
#: daban 12.1 y 4.0 cp y la corrección quedaba en ~0.4 %. La figura del libro
#: es más viscosa; el orden de magnitud de la conclusión no cambia.)
#:
#: O sea que en el umbral la corrección ya es menor al 0.5 %: ruido frente a la
#: incertidumbre de leer la viscosidad de un gráfico. Por debajo empieza a
#: morder, y a 16 °API —el ejemplo de cátedra— se va a 88 %.
VISCOUS_CRUDE_API_THRESHOLD = 28.0


def is_viscous_crude(oil_api: float) -> bool:
    """¿Hay que analizar los efectos de la viscosidad en este crudo?

    Args:
        oil_api: Gravedad del petróleo [°API].

    Returns:
        ``True`` si el crudo es pesado (< 28 °API) y corresponde corregir la
        curva de la bomba; ``False`` si es liviano y se diseña con la curva de
        agua sin corregir.
    """
    return oil_api < VISCOUS_CRUDE_API_THRESHOLD


def _tables() -> dict:
    """Carga las tablas una sola vez."""
    global _TABLES
    if _TABLES is None:
        _TABLES = json.loads(_TABLES_PATH.read_text(encoding="utf-8"))
    return _TABLES


def _charts() -> dict:
    """Carga las láminas digitalizadas de la Fig. 4L una sola vez."""
    global _CHARTS
    if _CHARTS is None:
        _CHARTS = json.loads(_CHARTS_PATH.read_text(encoding="utf-8"))
    return _CHARTS


# --------------------------------------------------------------------------
# Paso 4 — conversión de viscosidad
# --------------------------------------------------------------------------

def ssu_to_cst(ssu: float) -> float:
    """SSU → centistokes, por ASTM D2161.

    Args:
        ssu: Viscosidad en Segundos Saybolt Universal. Debe ser >= 31.

    Returns:
        Viscosidad cinemática [cSt].
    """
    if ssu < 31.0:
        raise ValueError(f"ssu must be >= 31, got {ssu}")
    if ssu < 100.0:
        return 0.226 * ssu - 195.0 / ssu
    return 0.220 * ssu - 135.0 / ssu


def cst_to_ssu(cst: float) -> float:
    """Centistokes → SSU (paso 4 de Riling, equivale a la Fig. 4L-3).

    Es la inversa de :func:`ssu_to_cst`. ASTM D2161 publica la relación en el
    sentido SSU → cSt y no tiene forma cerrada al revés, así que se invierte
    numéricamente por bisección; la función es monótona creciente, de modo que
    la raíz es única.

    Args:
        cst: Viscosidad cinemática [cSt]. Debe ser > 0.

    Returns:
        Viscosidad en SSU.
    """
    if cst <= 0:
        raise ValueError(f"cst must be > 0, got {cst}")
    lo, hi = 31.0, 1.0e6
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if ssu_to_cst(mid) < cst:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# --------------------------------------------------------------------------
# Pasos 2, 3 y 4 — de °API y temperatura a SSU
# --------------------------------------------------------------------------

def _lerp_log(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    """Interpola ``log10(y)`` linealmente en x. Devuelve el log, no el valor."""
    if x1 == x0:
        return log10(y0)
    t = (x - x0) / (x1 - x0)
    return log10(y0) + t * (log10(y1) - log10(y0))


def dead_oil_viscosity_chart(oil_api: float, temp_f: float) -> dict:
    """Paso 2 de Riling: viscosidad del crudo **sin gas**, leída de la Fig. 4L(2).

    Es la lámina «Viscosity of gas-free crude oil at oil-field temperatures» del
    Vol. 2b de Brown, digitalizada en ``catalogs/viscosity_charts.json``. Riling
    dice literalmente que este dato sale «de ensayos o de la Fig. 4L», así que
    ésta es la fuente que manda cuando no hay medición de laboratorio.

    **Reemplaza a Beggs-Robinson en crudos pesados, que es donde la correlación
    se queda corta**: para 16 °API a 130 °F la correlación da 59 cp y la figura
    150 cp — un factor 2.5, que arrastra todo el resto del procedimiento.

    La interpolación es bilineal sobre ``log10(μ)``: el eje de viscosidad de la
    lámina es logarítmico, de modo que interpolar el logaritmo equivale a leer
    con la regla sobre el papel. **No extrapola**: fuera de la grilla acota al
    borde más cercano y lo avisa.

    Args:
        oil_api: Gravedad del petróleo [°API a 60 °F]. Grilla: 10 a 60.
        temp_f: Temperatura de evaluación [°F]. Grilla: 100 a 220.

    Returns:
        dict con ``mu_cp`` (viscosidad [cp]), ``clamped`` (``True`` si hubo que
        acotar al borde de la lámina) y ``warnings``.
    """
    if oil_api <= 0:
        raise ValueError(f"oil_api must be > 0, got {oil_api}")
    if temp_f <= 0:
        raise ValueError(f"temp_f must be > 0 °F, got {temp_f}")

    fig = _charts()["fig_4L_2"]
    apis: list[float] = fig["api"]
    isos: list[dict] = fig["isotermas"]
    temps: list[float] = [iso["temp_f"] for iso in isos]

    warnings: list[str] = []

    api = min(max(oil_api, apis[0]), apis[-1])
    if api != oil_api:
        warnings.append(
            f"{oil_api:.1f} °API cae fuera de la Fig. 4L(2), que va de "
            f"{apis[0]:.0f} a {apis[-1]:.0f} °API. Se lee el borde "
            f"({api:.0f} °API); la figura no se extrapola."
        )

    t = min(max(temp_f, temps[0]), temps[-1])
    if t != temp_f:
        warnings.append(
            f"{temp_f:.0f} °F cae fuera de la Fig. 4L(2), que va de "
            f"{temps[0]:.0f} a {temps[-1]:.0f} °F. Se lee la isoterma del borde "
            f"({t:.0f} °F); la figura no se extrapola."
        )

    # Índice del tramo que contiene el punto, en cada eje.
    ia = min(max(bisect_left(apis, api) - 1, 0), len(apis) - 2)
    it = min(max(bisect_left(temps, t) - 1, 0), len(temps) - 2)

    # Primero a lo largo de °API, sobre cada una de las dos isotermas que
    # encierran el punto; después entre ellas, en temperatura.
    log_mu = []
    for iso in (isos[it], isos[it + 1]):
        mu = iso["mu_cp"]
        log_mu.append(_lerp_log(api, apis[ia], apis[ia + 1], mu[ia], mu[ia + 1]))

    if temps[it + 1] == temps[it]:
        resultado = log_mu[0]
    else:
        f = (t - temps[it]) / (temps[it + 1] - temps[it])
        resultado = log_mu[0] + f * (log_mu[1] - log_mu[0])

    return {
        "mu_cp": 10.0**resultado,
        "clamped": bool(warnings),
        "warnings": warnings,
    }


def _read_curve(curva: dict, rs: float) -> float:
    """Lee una curva de la Fig. 4L(1) en ``rs``. Devuelve ``log10(μ)``."""
    xs: list[float] = curva["rs_scf_bbl"]
    ys: list[float] = curva["mu_cp"]
    i = min(max(bisect_left(xs, rs) - 1, 0), len(xs) - 2)
    return _lerp_log(rs, xs[i], xs[i + 1], ys[i], ys[i + 1])


def gas_saturated_viscosity_chart(mu_dead_cp: float, rs_scf_bbl: float) -> dict:
    """Paso 3 de Riling: viscosidad del crudo **saturado**, de la Fig. 4L(1).

    Es la lámina «Viscosity of gas saturated crude oil at reservoir temperature
    & pressure» del Vol. 2b, digitalizada en ``catalogs/viscosity_charts.json``.
    Se entra con la viscosidad del crudo sin gas —que es la etiqueta de cada
    curva— y con el gas en solución, y se sale con la viscosidad del crudo vivo
    en el punto de burbuja.

    **Reemplaza a Beggs-Robinson** (``pvt.oil_viscosity_live``) en el
    procedimiento de Riling. Sobre el ejemplo de cátedra —150 cp con
    50 scf/bbl— la correlación daba 76.6 cp contra los 68 de la figura; la
    lámina da 67.9.

    Interpola linealmente en ``rs`` (el eje de la lámina es lineal) y sobre
    ``log10(μ)`` en las dos viscosidades, que es como están impresas las
    escalas. **No extrapola**: fuera de la familia de curvas, o pasado el final
    de una curva, acota y avisa.

    Args:
        mu_dead_cp: Viscosidad del crudo sin gas a temperatura de reservorio
            [cp] — normalmente lo que devuelve
            :func:`dead_oil_viscosity_chart`. Familia: 0.7 a 500 cp.
        rs_scf_bbl: Gas en solución a la presión de reservorio [scf/bbl].
            Cada curva termina en su propio máximo; la de 500 cp a 350 y las
            tres livianas a 1400.

    Returns:
        dict con ``mu_cp``, ``clamped`` y ``warnings``.
    """
    if mu_dead_cp <= 0:
        raise ValueError(f"mu_dead_cp must be > 0, got {mu_dead_cp}")
    if rs_scf_bbl < 0:
        raise ValueError(f"rs_scf_bbl must be >= 0, got {rs_scf_bbl}")

    curvas: list[dict] = _charts()["fig_4L_1"]["curvas"]
    etiquetas: list[float] = [c["mu_dead_cp"] for c in curvas]

    warnings: list[str] = []

    mu_dead = min(max(mu_dead_cp, etiquetas[0]), etiquetas[-1])
    if mu_dead != mu_dead_cp:
        warnings.append(
            f"Un crudo sin gas de {mu_dead_cp:.1f} cp cae fuera de la familia "
            f"de curvas de la Fig. 4L(1), que va de {etiquetas[0]:.1f} a "
            f"{etiquetas[-1]:.0f} cp. Se lee la curva del borde "
            f"({mu_dead:.1f} cp); la figura no se extrapola."
        )

    im = min(max(bisect_left(etiquetas, mu_dead) - 1, 0), len(curvas) - 2)
    baja, alta = curvas[im], curvas[im + 1]

    # Las dos curvas que encierran el punto no terminan en el mismo gas en
    # solución. Manda la que termina antes: más allá, una de las dos ya no
    # tiene dato y el promedio sería mitad lectura y mitad invento.
    rs_max = min(baja["rs_scf_bbl"][-1], alta["rs_scf_bbl"][-1])
    rs = min(rs_scf_bbl, rs_max)
    if rs != rs_scf_bbl:
        warnings.append(
            f"{rs_scf_bbl:.0f} scf/bbl queda pasando el final de la curva de "
            f"la Fig. 4L(1) para un crudo de {mu_dead:.1f} cp, que llega hasta "
            f"{rs_max:.0f} scf/bbl. Se lee el extremo de la curva; la figura "
            f"no se extrapola."
        )

    log_baja = _read_curve(baja, rs)
    log_alta = _read_curve(alta, rs)

    resultado = _lerp_log(
        log10(mu_dead),
        log10(baja["mu_dead_cp"]),
        log10(alta["mu_dead_cp"]),
        10.0**log_baja,
        10.0**log_alta,
    )

    return {
        "mu_cp": 10.0**resultado,
        "clamped": bool(warnings),
        "warnings": warnings,
    }


def crude_viscosity_ssu(
    oil_api: float,
    temp_f: float,
    rs_scf_bbl: float,
    dead_oil_cp: float | None = None,
) -> dict:
    """Pasos 2, 3 y 4: viscosidad del crudo en la admisión, en SSU.

    **La temperatura de evaluación es la de fondo** (decisión del proyecto; el
    paso 2 del libro dice «a temperatura de reservorio» y la tabla dice «at
    pumping temperature», que no son la misma cosa).

    Paso 2 — crudo sin gas. Riling dice «de ensayos o de la Fig. 4L», y ése es
    exactamente el orden: si se pasa ``dead_oil_cp`` manda ese valor; si no, se
    lee la **Fig. 4L(2)** digitalizada (:func:`dead_oil_viscosity_chart`). Ahí
    está la dependencia con la temperatura, que es la que hace falta cuando el
    dato medido está referido a otra. Beggs-Robinson **ya no interviene** en
    este paso: en crudos pesados quedaba muy corta —59 cp contra los 150 cp de
    la figura para 16 °API a 130 °F— y arrastraba el error por todo el resto
    del procedimiento. El resultado marca ``dead_oil_source``.

    Paso 3 — corrección por gas disuelto, leyendo la **Fig. 4L(1)**
    (:func:`gas_saturated_viscosity_chart`). Sobre los 150 cp del ejemplo y
    50 scf/bbl da 68.0 cp, que es exactamente el valor de la filmina.
    Beggs-Robinson daba 76.6 y **ya no interviene** en este paso.

    Con eso los dos pasos de viscosidad salen de las láminas del libro, que es
    lo que dice el procedimiento. Antes salían de correlaciones ajenas al libro:
    la figura impresa es la carta de Chew & Connally (1959) y el código evaluaba
    Beggs-Robinson —dos correlaciones distintas para la misma magnitud—, así que
    el módulo citaba una fuente que no era la que se ejecutaba. Ese problema
    desaparece leyendo la lámina.

    Paso 4 — a SSU, pasando por la viscosidad cinemática.

    Args:
        oil_api: Gravedad del petróleo [°API].
        temp_f: Temperatura de evaluación [°F] — la de fondo.
        rs_scf_bbl: Gas en solución a esa presión y temperatura [scf/bbl].
        dead_oil_cp: Viscosidad del crudo sin gas [cp], de ensayo. Cuando se
            omite se lee de la Fig. 4L(2).

    Returns:
        dict con ``mu_dead_cp``, ``mu_live_cp``, ``cst``, ``ssu``, ``sg_oil``,
        ``dead_oil_source`` (``"medido"`` o ``"fig_4L_2"``) y ``warnings``.
    """
    if oil_api <= 0:
        raise ValueError(f"oil_api must be > 0, got {oil_api}")
    if temp_f <= 0:
        raise ValueError(f"temp_f must be > 0 °F, got {temp_f}")
    if rs_scf_bbl < 0:
        raise ValueError(f"rs_scf_bbl must be >= 0, got {rs_scf_bbl}")

    warnings: list[str] = []
    sg_oil = 141.5 / (131.5 + oil_api)

    # --- Paso 2 -----------------------------------------------------------
    if dead_oil_cp is not None and dead_oil_cp > 0:
        mu_dead = float(dead_oil_cp)
        origen = "medido"
    else:
        lectura = dead_oil_viscosity_chart(oil_api, temp_f)
        mu_dead = lectura["mu_cp"]
        origen = "fig_4L_2"
        warnings.extend(lectura["warnings"])
        warnings.append(
            f"Viscosidad del crudo sin gas leída de la Fig. 4L(2) del libro "
            f"({mu_dead:.1f} cp) a {oil_api:.1f} °API y {temp_f:.0f} °F: no se "
            f"cargó un valor de ensayo. Es la fuente que indica Riling, pero un "
            f"PVT medido sigue siendo mejor dato."
        )

    # --- Paso 3 -----------------------------------------------------------
    saturado = gas_saturated_viscosity_chart(mu_dead, rs_scf_bbl)
    mu_live = saturado["mu_cp"]
    warnings.extend(saturado["warnings"])

    # --- Paso 4 -----------------------------------------------------------
    cst = mu_live / sg_oil
    ssu = cst_to_ssu(cst)

    return {
        "mu_dead_cp": mu_dead,
        "mu_live_cp": mu_live,
        "cst": cst,
        "ssu": ssu,
        "sg_oil": sg_oil,
        "dead_oil_source": origen,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# Paso 6 — factores de corrección
# --------------------------------------------------------------------------

def _interp_rows(rows: list[dict], ssu: float) -> dict:
    """Interpola una tabla en SSU. Fuera de rango acota, no extrapola."""
    xs = [r["ssu"] for r in rows]
    campos = ("capacity_factor", "head_factor", "new_efficiency", "hp_factor")

    if ssu <= xs[0]:
        return {k: rows[0][k] for k in campos}
    if ssu >= xs[-1]:
        return {k: rows[-1][k] for k in campos}

    i = bisect_left(xs, ssu)
    lo, hi = rows[i - 1], rows[i]
    f = (ssu - lo["ssu"]) / (hi["ssu"] - lo["ssu"])
    return {k: lo[k] + f * (hi[k] - lo[k]) for k in campos}


def viscosity_factors(ssu: float, pump_efficiency_pct: float) -> dict:
    """Paso 6: factores de corrección de las tablas 4.520 y 4.521.

    Dos interpolaciones encadenadas:

    1. **En SSU**, lineal dentro de cada tabla.
    2. **Entre tablas**, lineal según el rendimiento máximo de la bomba. El
       libro publica dos: 60 % (Tabla 4.520) y 70 % (Tabla 4.521). Una bomba de
       64 % cae en el medio y se interpola. Fuera de [60, 70] se **acota**: la
       propia tabla se titula «approximate changes», así que extrapolar sería
       pedirle más precisión que a la fuente.

    Args:
        ssu: Viscosidad de la mezcla a temperatura de bombeo [SSU].
        pump_efficiency_pct: Rendimiento máximo de la bomba [%], típicamente
            entre 50 y 75.

    Returns:
        dict con ``capacity_factor``, ``head_factor``, ``new_efficiency`` y
        ``hp_factor`` (todos en %), más ``ssu``, ``pump_efficiency_pct``,
        ``clamped_ssu``, ``clamped_efficiency`` y ``warnings``.
    """
    if ssu <= 0:
        raise ValueError(f"ssu must be > 0, got {ssu}")

    # El dominio guarda el rendimiento como fracción [0, 1]; estas tablas se
    # indexan por PORCENTAJE. Pasar 0.7 donde va 70 no rompe nada: la tabla se
    # acota al extremo de 60 % y devuelve factores plausibles pero equivocados.
    # Por eso se rechaza en vez de avisar — no existe una bomba de 5 %.
    if pump_efficiency_pct <= 5.0:
        raise ValueError(
            f"pump_efficiency_pct = {pump_efficiency_pct} es demasiado bajo para "
            f"ser un rendimiento de bomba en porcentaje. Las tablas 4.520/4.521 se "
            f"indexan por porcentaje (60, 70), no por fracción: si tenés "
            f"{pump_efficiency_pct} como fracción, multiplicalo por 100."
        )

    t = _tables()["tables"]
    rows60, rows70 = t["60"]["rows"], t["70"]["rows"]
    ssu_min, ssu_max = rows60[0]["ssu"], rows60[-1]["ssu"]
    eff_min, eff_max = _TABLE_EFFICIENCIES

    warnings: list[str] = []

    acotado_ssu = not (ssu_min <= ssu <= ssu_max)
    if ssu < ssu_min:
        warnings.append(
            f"Viscosidad de {ssu:.0f} SSU por debajo del rango de las tablas "
            f"({ssu_min:.0f} SSU): se usan los factores del extremo, que son "
            f"prácticamente los del agua."
        )
    elif ssu > ssu_max:
        warnings.append(
            f"Viscosidad de {ssu:.0f} SSU por encima del rango de las tablas "
            f"({ssu_max:.0f} SSU). A esa viscosidad el rendimiento cae por "
            f"debajo del 10 % y la bomba centrífuga deja de ser la opción "
            f"razonable: evaluar bombeo de cavidad progresiva."
        )

    acotado_eff = not (eff_min <= pump_efficiency_pct <= eff_max)
    if acotado_eff:
        warnings.append(
            f"El libro publica tablas para bombas de {eff_min:.0f} % y "
            f"{eff_max:.0f} % de rendimiento máximo; esta bomba da "
            f"{pump_efficiency_pct:.1f} %. Se usa la tabla del extremo más "
            f"cercano, sin extrapolar."
        )

    f60 = _interp_rows(rows60, ssu)
    f70 = _interp_rows(rows70, ssu)

    # Interpolación entre tablas por rendimiento, acotada a [60, 70].
    w = (min(max(pump_efficiency_pct, eff_min), eff_max) - eff_min) / (eff_max - eff_min)
    factores = {k: f60[k] + w * (f70[k] - f60[k]) for k in f60}

    return {
        **factores,
        "ssu": ssu,
        "pump_efficiency_pct": pump_efficiency_pct,
        "clamped_ssu": acotado_ssu,
        "clamped_efficiency": acotado_eff,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# Paso 7 — invertir el sentido para seleccionar
# --------------------------------------------------------------------------

def water_equivalent_duty(
    q_required: float,
    h_required: float,
    factors: dict,
    sg_mixture: float,
) -> dict:
    """Paso 7: qué tiene que dar la bomba CON AGUA para cumplir con el crudo.

    **Se divide, no se multiplica.** Los factores de la tabla dicen qué
    fracción de su curva de agua entrega la bomba cuando mueve el crudo::

        Q_crudo = C_Q · Q_agua        H_crudo = C_H · H_agua

    Para seleccionar se conoce el lado izquierdo —lo que el pozo pide— y se
    busca el derecho::

        Q_agua = Q_crudo / C_Q        H_agua = H_crudo / C_H

    Multiplicar en vez de dividir da una bomba y un motor cortos. Es el error
    más común de todo el procedimiento.

    La potencia va con el factor de la tabla **por γ_o**, la gravedad
    específica de la mezcla a temperatura de bombeo: el libro publica esa
    columna como «valor × γ_o».

    Args:
        q_required: Caudal que el pozo pide, con el crudo [STB/d].
        h_required: Altura que el pozo pide, con el crudo [ft].
        factors: Lo que devuelve :func:`viscosity_factors`.
        sg_mixture: Gravedad específica de la mezcla producida a temperatura
            de bombeo (γ_o).

    Returns:
        dict con ``q_water``, ``h_water``, ``hp_multiplier``,
        ``degraded_efficiency`` y los factores usados.
    """
    if q_required <= 0:
        raise ValueError(f"q_required must be > 0, got {q_required}")
    if h_required <= 0:
        raise ValueError(f"h_required must be > 0, got {h_required}")

    cq = factors["capacity_factor"] / 100.0
    ch = factors["head_factor"] / 100.0
    chp = factors["hp_factor"] / 100.0

    if cq <= 0 or ch <= 0:
        raise ValueError(
            "Los factores de corrección son nulos: a esta viscosidad la bomba "
            "centrífuga no desarrolla caudal ni altura útiles."
        )

    return {
        "q_water": q_required / cq,
        "h_water": h_required / ch,
        # La potencia crece por dos motivos que se multiplican: el rendimiento
        # cae (factor de la tabla) y el fluido pesa distinto que el agua (γ_o).
        "hp_multiplier": chp * sg_mixture,
        "degraded_efficiency": factors["new_efficiency"] / 100.0,
        "capacity_factor": factors["capacity_factor"],
        "head_factor": factors["head_factor"],
        "hp_factor": factors["hp_factor"],
        "sg_mixture": sg_mixture,
    }


# ==========================================================================
# 6. Modelo Hydraulic Institute — curve-fit de Turzo et al. (2000)
#
#    Fuente: Takács, G., «Electrical Submersible Pumps Manual», 2.ª ed.,
#    Elsevier 2018, §4.2.2, ecs. 4.1 a 4.12 y 4.14. Las ecuaciones son el
#    ajuste numérico que Turzo, Takács y Zsuga publicaron en Oil & Gas
#    Journal (29-may-2000) sobre los dos diagramas originales del Hydraulic
#    Institute, para no tener que leerlos a ojo.
# ==========================================================================

#: bpd -> «100 gpm», la unidad rara en que Turzo expresa Q* y Q_BEP.
#: 1 bbl = 42 gal y 1 día = 1440 min, así que gpm = bpd · 42/1440.
_BPD_TO_100GPM = 42.0 / 1440.0 / 100.0

#: Rango de validez declarado por el Hydraulic Institute (Takács §4.2.2).
#: Fuera de él las ecuaciones siguen dando un número, pero es extrapolación.
HI_RATE_RANGE_BPD = (3_400.0, 340_000.0)
HI_HEAD_RANGE_FT = (6.0, 600.0)
HI_VISCOSITY_RANGE_CST = (4.0, 3_000.0)

#: Tope de Q* por encima del cual el ajuste deja de tener sentido físico.
#:
#: Los polinomios de Turzo son ajustes a una zona acotada del diagrama y
#: extrapolan mal. Dos cosas se rompen, en este orden:
#:
#:     Q* > 57.3  el término cuadrático de C_eta (ec. 4.7, que va en +) domina
#:                y la parábola se da vuelta: el modelo empieza a decir que MÁS
#:                viscosidad da MEJOR rendimiento. Absurdo.
#:     Q* > 65.4  C_Q (ec. 4.6) cruza el cero y se hace negativo.
#:
#: El tope es el vértice de la parábola de C_eta, calculado de los propios
#: coeficientes en vez de escrito a mano: -b/(2a) con a = 2.8875e-4 y
#: b = -3.3075e-2. Da 57.27.
#:
#: **Este límite muerde adentro del rango declarado de viscosidad.** Una bomba
#: de tamaño BES (BEP ~5000 bpd, 25 ft/etapa) llega a Q* = 57 alrededor de los
#: 1000 cSt, muy por debajo de los 3000 cSt que el Hydraulic Institute declara
#: como techo. El techo declarado supone bombas de oleoducto, que son las que
#: se usaron para levantar los diagramas. Es la manifestación concreta de la
#: crítica que el propio Takács recoge en la pág. 168.
HI_Q_STAR_MAX = 3.3075e-2 / (2.0 * 2.8875e-4)


def cst_to_ssu_takacs(cst: float) -> float:
    """Centistokes → SSU por la forma cerrada de Takács (ec. 4.14).

    Una sola expresión para todo el rango, sin las dos ramas de ASTM D2161::

        SSU = 2.273 · (cSt + sqrt(cSt² + 158.4))

    Se usa dentro del camino Hydraulic Institute, para reproducir los ejemplos
    de Takács con su propia conversión. El camino de Riling sigue con
    :func:`cst_to_ssu`, que es ASTM. Las dos difieren ~1-2 % en el rango de
    interés; la diferencia se documenta en ``docs/CRUDOS_VISCOSOS.md``.

    Args:
        cst: Viscosidad cinemática [cSt]. Debe ser > 0.

    Returns:
        Viscosidad en Segundos Saybolt Universal.
    """
    if cst <= 0:
        raise ValueError(f"cst must be > 0, got {cst}")
    return 2.273 * (cst + (cst * cst + 158.4) ** 0.5)


def brake_horsepower(q_bpd: float, head_ft: float, sg: float, efficiency: float) -> float:
    """Potencia al freno de una bomba centrífuga (Takács ec. 4.12).

    .. code-block:: text

        BHP = 7.368e-6 · Q · H · γ / η

    **El rendimiento entra como fracción, no como porcentaje.** El libro anota
    la unidad de η como «%», pero es un error: con η en % el resultado da 100
    veces chico. Verificado contra sus propios ejemplos — en el BEP del Ejemplo
    4.1 (900 bpd, 21.8 ft, γ = 1.0, η = 64 %) la fórmula tiene que dar los
    0.225 HP que el Ejemplo 4.2 lee de la curva de agua, y eso sale con
    η = 0.64. La constante lo confirma: 42/(1440·3960) = 7.366e-6, que es la
    conversión de bpd·ft·SG a HP hidráulicos, y esa cuenta lleva η en fracción.

    Args:
        q_bpd: Caudal [bpd].
        head_ft: Altura desarrollada [ft].
        sg: Gravedad específica del líquido.
        efficiency: Rendimiento de la bomba, **en fracción** (0 < η ≤ 1).

    Returns:
        Potencia al freno [HP].
    """
    if efficiency <= 0 or efficiency > 1:
        raise ValueError(
            f"efficiency must be a fraction in (0, 1], got {efficiency}. "
            "Si tenés el rendimiento en porcentaje, dividilo por 100."
        )
    return 7.368e-6 * q_bpd * head_ft * sg / efficiency


def hydraulic_institute_factors(
    viscosity_cst: float,
    q_bep_bpd: float,
    h_bep_ft: float,
) -> dict:
    """Factores de corrección del Hydraulic Institute (Takács ecs. 4.4 a 4.11).

    A diferencia de las tablas de Riling —que sólo miran la viscosidad— acá los
    factores dependen también del **BEP de la bomba concreta**: la misma
    viscosidad castiga distinto a una bomba grande que a una chica. Todo pasa
    por un único parámetro de correlación, el caudal corregido ``Q*``::

        y  = -7.5946 + 6.6504·ln(H_BEP) + 12.8429·ln(Q_BEP)
        Q* = exp[ (39.5276 + 26.5605·ln(ν) - y) / 51.6565 ]

    con H_BEP en ft, Q_BEP en «100 gpm» y ν en cSt. De ``Q*`` salen un factor
    de caudal, uno de rendimiento y **cuatro** de altura, uno para cada uno de
    los caudales 0.6, 0.8, 1.0 y 1.2 veces el del BEP.

    Dos erratas del impreso, las dos verificadas
    --------------------------------------------
    1. El **ejemplo resuelto** de la pág. 157 calcula ``C_H,1.0`` con el término
       cuadrático en **+**, y le da 0.844. La ecuación 4.10, impresa dos páginas
       antes, lo tiene en **−**, que da 0.829. Manda la ecuación: el ejemplo del
       paper original de OGJ (Q* = 2.698) publica C_H3 = 0.9810, y eso sale con
       el signo −; con + daría 0.9812. Además, con + los coeficientes
       cuadráticos dejarían de ser monótonos (−4.36e-5, −4.18e-5, +1.41e-5,
       +1.31e-5) y las curvas de 0.8 y 1.0 se cruzarían a partir de Q* ≈ 45,
       que es físicamente imposible: la corrección no puede ser más benigna
       lejos del BEP que cerca.
    2. En cambio ``C_η`` (ec. 4.7) **sí** lleva el cuadrático en **+**, y así
       está impreso. Confirmado con los dos ejemplos.

    Args:
        viscosity_cst: Viscosidad cinemática del líquido [cSt].
        q_bep_bpd: Caudal del BEP en la curva de agua [bpd].
        h_bep_ft: Altura del BEP en la curva de agua [ft]. Es la altura **por
            etapa** si la curva del catálogo es por etapa, que es el caso.

    Returns:
        dict con ``q_star``, ``y``, ``capacity_factor`` (C_Q),
        ``efficiency_factor`` (C_η), ``head_factors`` (los cuatro C_H indexados
        por 0.6/0.8/1.0/1.2), ``ssu`` y ``warnings``.
    """
    from math import exp, log

    if viscosity_cst <= 0:
        raise ValueError(f"viscosity_cst must be > 0, got {viscosity_cst}")
    if q_bep_bpd <= 0:
        raise ValueError(f"q_bep_bpd must be > 0, got {q_bep_bpd}")
    if h_bep_ft <= 0:
        raise ValueError(f"h_bep_ft must be > 0, got {h_bep_ft}")

    warnings: list[str] = []
    if not (HI_VISCOSITY_RANGE_CST[0] <= viscosity_cst <= HI_VISCOSITY_RANGE_CST[1]):
        warnings.append(
            f"Viscosidad de {viscosity_cst:.0f} cSt fuera del rango validado "
            f"del Hydraulic Institute ({HI_VISCOSITY_RANGE_CST[0]:.0f}–"
            f"{HI_VISCOSITY_RANGE_CST[1]:.0f} cSt): los factores son extrapolación."
        )
    if not (HI_RATE_RANGE_BPD[0] <= q_bep_bpd <= HI_RATE_RANGE_BPD[1]):
        warnings.append(
            f"Caudal de BEP de {q_bep_bpd:.0f} bpd fuera del rango validado "
            f"({HI_RATE_RANGE_BPD[0]:.0f}–{HI_RATE_RANGE_BPD[1]:.0f} bpd). La "
            "mayoría de los diseños BES cae por debajo del piso: los diagramas "
            "originales se levantaron con bombas de oleoducto, mucho más grandes."
        )
    if not (HI_HEAD_RANGE_FT[0] <= h_bep_ft <= HI_HEAD_RANGE_FT[1]):
        warnings.append(
            f"Altura de BEP de {h_bep_ft:.0f} ft fuera del rango validado "
            f"({HI_HEAD_RANGE_FT[0]:.0f}–{HI_HEAD_RANGE_FT[1]:.0f} ft). Ojo: "
            "el modelo se aplica a la altura POR ETAPA, no al TDH del pozo."
        )

    q_bep_100gpm = q_bep_bpd * _BPD_TO_100GPM

    # Ecuaciones 4.5 y 4.4.
    y = -7.5946 + 6.6504 * log(h_bep_ft) + 12.8429 * log(q_bep_100gpm)
    q_star = exp((39.5276 + 26.5605 * log(viscosity_cst) - y) / 51.6565)

    if q_star > HI_Q_STAR_MAX:
        raise ValueError(
            f"Q* = {q_star:.1f} pasa el tope de {HI_Q_STAR_MAX:.1f} en el que el "
            f"ajuste de Turzo deja de tener sentido físico (a partir de ahí el "
            f"modelo dice que más viscosidad da mejor rendimiento, y poco después "
            f"el factor de caudal se hace negativo). Con {viscosity_cst:.0f} cSt "
            f"sobre un BEP de {q_bep_bpd:.0f} bpd y {h_bep_ft:.1f} ft el modelo "
            f"Hydraulic Institute no aplica: usar las tablas de Riling, y evaluar "
            f"si a esta viscosidad corresponde una bomba centrífuga."
        )

    qs2 = q_star * q_star

    # Ecuaciones 4.6 y 4.7. El cuadrático de C_eta va en +, y está bien impreso.
    c_q = 1.0 - 4.0327e-3 * q_star - 1.724e-4 * qs2
    c_eta = 1.0 - 3.3075e-2 * q_star + 2.8875e-4 * qs2

    # Ecuaciones 4.8 a 4.11. Signos según la ECUACIÓN, no según el ejemplo.
    head_factors = {
        0.6: 1.0 - 3.68e-3 * q_star - 4.36e-5 * qs2,
        0.8: 1.0 - 4.4723e-3 * q_star - 4.18e-5 * qs2,
        1.0: 1.0 - 7.00763e-3 * q_star - 1.41e-5 * qs2,
        1.2: 1.0 - 9.01e-3 * q_star + 1.31e-5 * qs2,
    }

    if c_q <= 0 or c_eta <= 0 or min(head_factors.values()) <= 0:
        raise ValueError(
            f"A {viscosity_cst:.0f} cSt los factores del Hydraulic Institute se "
            f"van a cero o negativos (Q* = {q_star:.1f}): el modelo dejó de tener "
            "sentido físico. La bomba centrífuga no es la opción a esa viscosidad."
        )

    return {
        "q_star": q_star,
        "y": y,
        "capacity_factor": c_q,
        "efficiency_factor": c_eta,
        "head_factors": head_factors,
        "viscosity_cst": viscosity_cst,
        "ssu": cst_to_ssu_takacs(viscosity_cst),
        "q_bep_bpd": q_bep_bpd,
        "h_bep_ft": h_bep_ft,
        "warnings": warnings,
    }


def hi_corrected_curve(
    water_points: dict,
    factors: dict,
    shutoff_head_ft: float | None = None,
) -> list[dict]:
    """Curva corregida por viscosidad, punto por punto (Takács ecs. 4.1 a 4.3).

    Recibe los cuatro puntos de la curva de agua a 0.6, 0.8, 1.0 y 1.2 veces el
    caudal del BEP y devuelve dónde queda cada uno con el fluido viscoso::

        Q_visc = C_Q · Q_agua      H_visc = C_H · H_agua      η_visc = C_η · η_agua

    Si se pasa ``shutoff_head_ft`` se agrega el quinto punto, el de caudal cero.
    **Ese punto no se corrige**: a caudal nulo no hay pérdidas por fricción
    dentro de la bomba, así que la altura de cierre es la misma con crudo que
    con agua. Es lo que ancla el extremo izquierdo de la curva nueva.

    Args:
        water_points: ``{0.6: {"q": ..., "h": ..., "eff": ...}, 0.8: ..., ...}``
            con el caudal en bpd, la altura en ft y el rendimiento en %.
        factors: Lo que devuelve :func:`hydraulic_institute_factors`.
        shutoff_head_ft: Altura a caudal cero [ft], opcional.

    Returns:
        Lista de dicts ordenada por caudal, cada uno con ``fraction``, ``q_bpd``,
        ``head_ft``, ``efficiency_pct`` y ``corrected``.
    """
    c_q = factors["capacity_factor"]
    c_eta = factors["efficiency_factor"]
    c_h = factors["head_factors"]

    puntos: list[dict] = []
    if shutoff_head_ft is not None:
        puntos.append({
            "fraction": 0.0,
            "q_bpd": 0.0,
            "head_ft": shutoff_head_ft,
            "efficiency_pct": 0.0,
            "corrected": False,
        })

    for fr in (0.6, 0.8, 1.0, 1.2):
        if fr not in water_points:
            raise ValueError(f"Falta el punto {fr} en water_points")
        p = water_points[fr]
        puntos.append({
            "fraction": fr,
            "q_bpd": c_q * p["q"],
            "head_ft": c_h[fr] * p["h"],
            "efficiency_pct": c_eta * p["eff"],
            "corrected": True,
        })

    return puntos


def centrilift_factors(ssu: float) -> dict:
    """Factores de la Tabla 4.1 de Takács — la tabla de Centrilift.

    Tercera fuente, para contrastar. No es el camino de diseño: sirve para ver
    cuánta dispersión hay entre fabricantes a la misma viscosidad. Trae una
    columna propia de potencia al freno, que se usa con la ec. 4.13::

        BHP_visc = C_BHP · BHP_agua · γ_l

    Fuera del rango de la tabla se **acota**, no se extrapola.

    Args:
        ssu: Viscosidad [SSU].

    Returns:
        dict con ``capacity_factor``, ``head_factor``, ``efficiency_factor`` y
        ``bhp_factor`` (los cuatro en fracción), más ``clamped`` y ``warnings``.
    """
    if ssu <= 0:
        raise ValueError(f"ssu must be > 0, got {ssu}")

    rows = _tables()["centrilift_table"]["rows"]
    campos = ("capacity_factor", "head_factor", "efficiency_factor", "bhp_factor")
    xs = [r["ssu"] for r in rows]
    warnings: list[str] = []

    acotado = not (xs[0] <= ssu <= xs[-1])
    if acotado:
        warnings.append(
            f"Viscosidad de {ssu:.0f} SSU fuera de la Tabla 4.1 "
            f"({xs[0]:.0f}–{xs[-1]:.0f} SSU): se acota al extremo, no se extrapola."
        )

    if ssu <= xs[0]:
        crudos = {k: rows[0][k] for k in campos}
    elif ssu >= xs[-1]:
        crudos = {k: rows[-1][k] for k in campos}
    else:
        i = bisect_left(xs, ssu)
        lo, hi = rows[i - 1], rows[i]
        f = (ssu - lo["ssu"]) / (hi["ssu"] - lo["ssu"])
        crudos = {k: lo[k] + f * (hi[k] - lo[k]) for k in campos}

    if 3_000.0 < ssu < 5_000.0:
        warnings.append(
            "Entre 3000 y 5000 SSU la Tabla 4.1 pasa por la fila de 4000 SSU, "
            "que publica un factor de eficiencia de 0.278 y rompe la tendencia "
            "(0.218 a 3000 → 0.149 a 5000). Es una errata del impreso; el valor "
            "coherente sería ~0.178. Se transcribió tal cual y no se corrige en "
            "silencio: el rendimiento interpolado acá está inflado."
        )

    return {
        **{k: v / 100.0 for k, v in crudos.items()},
        "ssu": ssu,
        "clamped": acotado,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# Punto de entrada: el procedimiento completo, con la regla de los 28 °API
# --------------------------------------------------------------------------

#: Lo que se devuelve cuando el crudo es liviano: nada se corrige.
_SIN_CORRECCION = {
    "capacity_factor": 100.0,
    "head_factor": 100.0,
    "hp_factor": 100.0,
    "clamped_ssu": False,
    "clamped_efficiency": False,
    "warnings": [],
}


def evaluate_viscosity(
    oil_api: float,
    temp_f: float,
    rs_scf_bbl: float,
    pump_efficiency_pct: float,
    dead_oil_cp: float | None = None,
    measured_mixture_ssu: float | None = None,
) -> dict:
    """Procedimiento de Riling completo, con la regla de crudo liviano adelante.

    **De 28 °API para arriba el crudo es liviano y no se corrige nada**: se
    devuelven factores unitarios y ``is_viscous`` en ``False``. El diseño usa
    la curva de agua tal cual, que es lo correcto — en el umbral la corrección
    ya vale menos del 0.5 %.

    Por debajo de 28 °API se corre la cadena completa: viscosidad del crudo sin
    gas, corrección por gas disuelto, conversión a SSU y factores de las Tablas
    4.520 / 4.521.

    El corte de agua (paso 5) entra por ``measured_mixture_ssu``: es un dato de
    laboratorio, no una cuenta. Riling dice «si hay datos disponibles» porque la
    viscosidad de una emulsión no se interpola entre las fases —puede ser varias
    veces la del petróleo solo y se desploma pasado el punto de inversión—. Sin
    ese dato el paso queda **sin realizar**, y se avisa.

    Args:
        oil_api: Gravedad del petróleo [°API].
        temp_f: Temperatura de evaluación [°F] — la de fondo.
        rs_scf_bbl: Gas en solución [scf/bbl].
        pump_efficiency_pct: Rendimiento máximo de la bomba [%].
        dead_oil_cp: Viscosidad del crudo sin gas [cp], medida o de la
            Fig. 4L-2. Sin ella se estima con Beggs-Robinson y se avisa.
        measured_mixture_ssu: Viscosidad de la mezcla con agua [SSU], medida.
            Cuando se pasa, **reemplaza** a la del crudo solo (paso 5).

    Returns:
        dict con ``is_viscous``, ``oil_api``, ``api_threshold``, los factores de
        corrección, el detalle de la viscosidad en ``viscosity`` (o ``None`` en
        crudo liviano), ``water_cut_correction`` y ``warnings``.
    """
    if is_viscous_crude(oil_api):
        v = crude_viscosity_ssu(oil_api, temp_f, rs_scf_bbl, dead_oil_cp)
        warnings = list(v["warnings"])

        # --- Paso 5 — corte de agua -----------------------------------------
        if measured_mixture_ssu is not None and measured_mixture_ssu > 0:
            ssu_diseno = float(measured_mixture_ssu)
            correccion_agua = "medida"
        else:
            ssu_diseno = v["ssu"]
            correccion_agua = "no_realizada"
            warnings.append(
                "Corte de agua: sin viscosidad medida de la mezcla, el paso 5 "
                "queda SIN REALIZAR. Se usa la del crudo solo, que puede quedar "
                "muy por debajo: una emulsión agua en petróleo llega a ser "
                "varias veces más viscosa que el petróleo (en el ejemplo de "
                "cátedra, 30 % de agua llevó 325 SSU a 650 SSU)."
            )

        f = viscosity_factors(ssu_diseno, pump_efficiency_pct)
        warnings.extend(f["warnings"])

        return {
            "is_viscous": True,
            "oil_api": oil_api,
            "api_threshold": VISCOUS_CRUDE_API_THRESHOLD,
            "design_ssu": ssu_diseno,
            "viscosity": v,
            "water_cut_correction": correccion_agua,
            "capacity_factor": f["capacity_factor"],
            "head_factor": f["head_factor"],
            "new_efficiency": f["new_efficiency"],
            "hp_factor": f["hp_factor"],
            "clamped_ssu": f["clamped_ssu"],
            "clamped_efficiency": f["clamped_efficiency"],
            "warnings": warnings,
        }

    # --- Crudo liviano: no se corrige nada ---------------------------------
    return {
        "is_viscous": False,
        "oil_api": oil_api,
        "api_threshold": VISCOUS_CRUDE_API_THRESHOLD,
        "design_ssu": None,
        "viscosity": None,
        "water_cut_correction": "no_aplica",
        "new_efficiency": pump_efficiency_pct,
        "reason": (
            f"Crudo de {oil_api:.1f} °API: liviano (≥ "
            f"{VISCOUS_CRUDE_API_THRESHOLD:.0f} °API). No se corrige la curva "
            f"por viscosidad — en el umbral la corrección ya es menor al 0.5 %."
        ),
        **_SIN_CORRECCION,
    }
