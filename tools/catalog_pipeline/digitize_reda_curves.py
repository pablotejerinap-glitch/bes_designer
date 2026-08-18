"""Digitaliza las curvas de bomba del catálogo REDA ESP (Schlumberger, 2005).

Las curvas del PDF son **vectoriales**: cero imágenes, cientos de segmentos de
línea. Eso permite leer las coordenadas exactas de cada trazo en vez de estimar
píxeles sobre una imagen. No hay OCR ni ajuste manual en ninguna parte.

Cada página trae tres curvas sobre un mismo eje de caudal, cada una con su
propio eje vertical:

    azul   (1.0, 0.68, 0.0, 0.3)   altura por etapa
    negro  (0.0, 0.0, 0.0, 1.0)    eficiencia
    rojo   (0.0, 1.0, 1.0, 0.0)    potencia por etapa

La asignación no se adivina por color: el propio gráfico rotula «Head»,
«Efficiency» y «Power» junto a su curva, y se resuelve por cercanía vertical
a la polilínea correspondiente.

La calibración de los cuatro ejes se deriva de las etiquetas numéricas de cada
uno mediante regresión lineal, y se verifica que sean efectivamente lineales
(R² ≥ 0.9999) antes de usarlas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pdfplumber

HEAD_COLOR = "(1.0, 0.68, 0.0, 0.3)"
EFF_COLOR = "(0.0, 0.0, 0.0, 1.0)"
POWER_COLOR = "(0.0, 1.0, 1.0, 0.0)"

TITLE = re.compile(
    r"REDA\*? ESP ([A-Z0-9]+) Pump Performance Curve\s+(\d+)\s*Hz,\s*([\d,]+)\s*rpm"
)
NUMBER = re.compile(r"^\d{1,3}(?:,\d{3})*(?:\.\d+)?$")


@dataclass
class Axis:
    """Transformación afín entre coordenadas del PDF y unidades de dato."""
    slope: float
    intercept: float
    r2: float

    def value(self, coordinate: float) -> float:
        return self.slope * coordinate + self.intercept


def _fit(coordinates: list[float], values: list[float]) -> Axis | None:
    """Recta por mínimos cuadrados; devuelve None si el eje no es lineal."""
    n = len(coordinates)
    if n < 3:
        return None
    mean_x = sum(coordinates) / n
    mean_y = sum(values) / n
    sxx = sum((c - mean_x) ** 2 for c in coordinates)
    sxy = sum((c - mean_x) * (v - mean_y) for c, v in zip(coordinates, values))
    if sxx == 0:
        return None
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_tot = sum((v - mean_y) ** 2 for v in values)
    ss_res = sum((v - (slope * c + intercept)) ** 2
                 for c, v in zip(coordinates, values))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    return Axis(slope, intercept, r2) if r2 >= 0.9999 else None


def plot_frame(page) -> tuple[float, float, float, float] | None:
    """Área de trazado: izquierda, derecha y base del marco; tope de la banda.

    El rectángulo repetido da los tres primeros bordes, pero en las páginas
    métricas ese mismo rectángulo abarca también el bloque de especificaciones,
    así que su borde superior está muy por encima del gráfico. El tope real lo
    marca la banda sombreada de rango operativo, que llega justo hasta arriba
    del área de trazado y comparte su base.
    """
    # Se elige por ALTURA, no por repetición ni por área: el bloque de
    # especificaciones tiene el mismo ancho que el gráfico y a veces se dibuja
    # más veces que él, así que ni el conteo ni el área lo distinguen. La altura
    # sí: el área de trazado es cuatro veces más alta.
    wide = [(round(r["x0"], 1), round(r["top"], 1),
             round(r["x1"], 1), round(r["bottom"], 1))
            for r in page.rects if r["x1"] - r["x0"] > 200]
    if not wide:
        return None
    # Alto primero y ancho como desempate: la banda de rango operativo llega de
    # arriba abajo igual que el gráfico, así que ordenar sólo por altura puede
    # devolverla a ella y recortar el eje de caudal a un tercio.
    x0, top, x1, bottom = max(wide, key=lambda k: (k[3] - k[1], k[2] - k[0]))

    bands = [r for r in page.rects
             if abs(r["bottom"] - bottom) < 1.5
             and x0 < r["x0"] and r["x1"] < x1
             and r["top"] > top + 5]
    if bands:
        top = min(b["top"] for b in bands)
    return x0, top, x1, bottom


def calibrate(page, frame) -> dict[str, Axis]:
    """Ejes leídos de sus propias etiquetas numéricas.

    El eje de caudal va debajo del marco; los tres verticales se separan por
    su distancia horizontal al marco: altura a la izquierda, potencia y
    eficiencia a la derecha, en ese orden.
    """
    x0, top, x1, bottom = frame
    ticks: dict[str, list[tuple[float, float]]] = {
        "flow": [], "head": [], "power": [], "efficiency": []
    }
    right: list[tuple[float, float, float]] = []

    for word in page.extract_words():
        text = word["text"].replace(",", "")
        if not NUMBER.match(word["text"]):
            continue
        value = float(text)
        cx = (word["x0"] + word["x1"]) / 2
        cy = (word["top"] + word["bottom"]) / 2
        if bottom - 2 < cy < bottom + 22 and x0 - 20 < cx < x1 + 20:
            ticks["flow"].append((cx, value))
        elif top - 6 <= cy <= bottom + 6 and cx < x0 - 2:
            ticks["head"].append((cy, value))
        elif top - 6 <= cy <= bottom + 6 and cx > x1 + 2:
            right.append((cx, cy, value))

    # Las dos columnas de la derecha se agrupan por cercanía real y no
    # redondeando: el «0» de cada eje se imprime centrado bajo su columna y con
    # un redondeo fijo cae en un grupo propio, partiendo el eje en dos.
    right.sort()
    columns: list[list[tuple[float, float, float]]] = []
    for entry in right:
        if columns and entry[0] - columns[-1][-1][0] <= 18:
            columns[-1].append(entry)
        else:
            columns.append([entry])
    for index, column in enumerate(columns[:2]):
        name = "power" if index == 0 else "efficiency"
        ticks[name] += [(cy, value) for _, cy, value in column]

    axes = {}
    for name, pairs in ticks.items():
        if not pairs:
            continue
        pairs.sort()
        fitted = _fit([p[0] for p in pairs], [p[1] for p in pairs])
        if fitted:
            axes[name] = fitted
    return axes


def polylines(page, frame) -> dict[str, list[tuple[float, float]]]:
    """Puntos de cada curva, dentro del marco, ordenados por caudal."""
    x0, top, x1, bottom = frame

    def inside(x: float, y: float) -> bool:
        return x0 - 1 <= x <= x1 + 1 and top - 1 <= y <= bottom + 1

    found: dict[str, set] = {c: set() for c in (HEAD_COLOR, EFF_COLOR, POWER_COLOR)}
    for line in page.lines:
        color = str(line.get("stroking_color"))
        if color not in found:
            continue
        a = (line["x0"], line["top"])
        b = (line["x1"], line["bottom"])
        if not (inside(*a) and inside(*b)):
            continue
        # El marco y las marcas de eje son rectos y largos; las curvas no.
        horizontal = abs(a[1] - b[1]) < 0.3 and abs(a[0] - b[0]) > 50
        vertical = abs(a[0] - b[0]) < 0.3 and abs(a[1] - b[1]) > 50
        if horizontal or vertical:
            continue
        found[color].add(a)
        found[color].add(b)
    for curve in page.curves:
        color = str(curve.get("stroking_color"))
        if color in found:
            found[color].update(p for p in curve.get("pts", []) if inside(*p))
    return {color: sorted(points) for color, points in found.items()}


def assign_by_label(page, curves: dict) -> dict[str, str]:
    """Empareja cada rótulo del gráfico con la curva que tiene más cerca.

    La asignación es **biyectiva**: una curva no puede ser a la vez la altura y
    el rendimiento. Sin esa restricción, cuando el rótulo «Head» cae cerca de la
    curva de rendimiento las dos magnitudes terminan leyendo la misma polilínea
    sobre ejes distintos —salen proporcionales entre sí— y el resultado parece
    plausible pero es la misma curva dos veces.
    """
    candidates = []
    for word in page.extract_words():
        label = word["text"]
        if label not in ("Head", "Efficiency", "Power"):
            continue
        cx = (word["x0"] + word["x1"]) / 2
        cy = (word["top"] + word["bottom"]) / 2
        for color, points in curves.items():
            near = [p for p in points if abs(p[0] - cx) < 25]
            if near:
                candidates.append(
                    (min(abs(p[1] - cy) for p in near), label.lower(), color))

    mapping: dict[str, str] = {}
    used: set[str] = set()
    for distance, name, color in sorted(candidates):
        if distance >= 60 or name in mapping or color in used:
            continue
        mapping[name] = color
        used.add(color)

    # Respaldo por color para lo que quedó sin rótulo cercano. El color es
    # constante en todo el catálogo; el rótulo del gráfico manda cuando existe.
    for name, color in (("head", HEAD_COLOR), ("efficiency", EFF_COLOR),
                        ("power", POWER_COLOR)):
        if name not in mapping and color not in used and curves.get(color):
            mapping[name] = color
            used.add(color)
    return mapping


def shape_is_consistent(points: list[dict]) -> bool:
    """La altura cae con el caudal y la eficiencia tiene un solo máximo interior.

    Es la comprobación que atrapa una asignación de curvas cruzada, que es el
    modo de falla que ni la calibración ni el R² detectan.
    """
    if len(points) < 5:
        return False
    heads = [p["head_per_stage"] for p in points]
    effs = [p["efficiency"] for p in points]
    if heads[0] <= heads[-1]:
        return False
    # No se exige monotonía estricta: varias bombas de alto caudal tienen la
    # curva «enganchada», con un tramo central que vuelve a subir. Sí se exige
    # que la tendencia general baje y que el último tercio caiga.
    ascents = sum(1 for a, b in zip(heads, heads[1:]) if b > a + 1e-9)
    if ascents > len(heads) // 3:
        return False
    tail = heads[2 * len(heads) // 3:]
    if tail[0] <= tail[-1]:
        return False
    peak = effs.index(max(effs))
    return 0 < peak < len(effs) - 1 and max(effs) > 0.15


def _interpolate(points: list[tuple[float, float]], x: float) -> float | None:
    if not points or x < points[0][0] or x > points[-1][0]:
        return None
    for (xa, ya), (xb, yb) in zip(points, points[1:]):
        if xa <= x <= xb:
            return ya if xb == xa else ya + (yb - ya) * (x - xa) / (xb - xa)
    return points[-1][1]


def digitize_page(page, n_points: int = 21) -> dict | None:
    text = page.extract_text() or ""
    title = TITLE.search(text)
    frame = plot_frame(page)
    if not title or not frame:
        return None
    axes = calibrate(page, frame)
    if {"flow", "head", "power", "efficiency"} - set(axes):
        return None
    curves = polylines(page, frame)
    labels = assign_by_label(page, curves)
    if {"head", "power", "efficiency"} - set(labels):
        return None

    head_pts = curves[labels["head"]]
    # El rango lo fija SOLO la curva de altura, que es la que el fabricante
    # dibuja de extremo a extremo del eje. Intersecarlo con el de la curva de
    # potencia —que en varias páginas arranca más a la derecha— recortaba el
    # rango de forma distinta en la página de 60 Hz que en la de 50 Hz, y al
    # comparar por índice terminaban enfrentándose caudales que no se
    # corresponden. Eso hacía fallar la verificación por afinidad de siete
    # bombas con desvíos del 20 %, que no eran errores de lectura sino de rango.
    x_min, x_max = head_pts[0][0], head_pts[-1][0]
    points = []
    for i in range(n_points):
        x = x_min + (x_max - x_min) * i / (n_points - 1)
        y_head = _interpolate(head_pts, x)
        y_eff = _interpolate(curves[labels["efficiency"]], x)
        if y_head is None or y_eff is None:
            continue
        # La potencia sólo se usa como control; si su trazo no cubre este
        # caudal el punto igual sirve, porque la potencia se deriva.
        y_power = _interpolate(curves[labels["power"]], x)
        flow = axes["flow"].value(x)
        head = axes["head"].value(y_head)
        efficiency = max(axes["efficiency"].value(y_eff), 0.0) / 100
        points.append({
            "flow_rate": round(flow, 1),
            "head_per_stage": round(head, 4),
            "efficiency": round(efficiency, 4),
            # Potencia LEÍDA del gráfico. Se conserva sólo como control: en las
            # bombas chicas la curva queda aplastada contra el eje (el eje llega
            # a 2 hp y la curva vale 0.1) y ahí la lectura pierde resolución.
            "_hp_read": (round(axes["power"].value(y_power), 5)
                         if y_power is not None else None),
        })
    return {
        "model": title.group(1),
        "frequency_hz": int(title.group(2)),
        "rpm": int(title.group(3).replace(",", "")),
        "metric": "m3" in text and "(m)" in text,
        "r2": {name: round(axis.r2, 6) for name, axis in axes.items()},
        "points": points,
    }


GPM_PER_BPD = 42.0 / 1440.0
BPD_PER_M3D = 6.289811
FT_PER_M = 3.280840


def add_derived_power(curve: dict) -> dict:
    """Potencia al eje por etapa, derivada de la altura y el rendimiento.

    No es una estimación: por definición de rendimiento de bomba,

        HP_eje = Q[gpm] · H[ft] · SG / (3960 · η)

    y el catálogo aclara que la curva es «for one stage in fluid of 1.00 sg».
    Se prefiere a la lectura del gráfico porque la altura y el rendimiento se
    leen sobre ejes bien escalados —y se validan contra las leyes de afinidad
    dentro del 0.2 %—, mientras que la curva de potencia comparte un eje único
    de 0 a 2 hp para todo el catálogo y en las bombas chicas queda comprimida
    en unos pocos puntos de papel.

    El campo `_hp_read` conserva la lectura para poder auditar la diferencia.
    """
    metric = curve["metric"]
    for point in curve["points"]:
        flow_bpd = point["flow_rate"] * (BPD_PER_M3D if metric else 1.0)
        head_ft = point["head_per_stage"] * (FT_PER_M if metric else 1.0)
        efficiency = point["efficiency"]
        if efficiency <= 0.02:
            point["hp_per_stage"] = 0.0
            continue
        hp = flow_bpd * GPM_PER_BPD * head_ft / (3960.0 * efficiency)
        point["hp_per_stage"] = round(hp, 5)
    ratios = sorted(
        point["_hp_read"] / point["hp_per_stage"]
        for point in curve["points"]
        if point.get("_hp_read") is not None and point.get("hp_per_stage")
    )
    if ratios:
        curve["hp_read_vs_derived"] = round(ratios[len(ratios) // 2], 4)
    return curve


def digitize(pdf_path: str, n_points: int = 21) -> list[dict]:
    results = []
    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages):
            digitized = digitize_page(page, n_points)
            if not digitized:
                continue
            digitized["page"] = index + 1
            digitized["shape_ok"] = shape_is_consistent(digitized["points"])
            results.append(add_derived_power(digitized))
    return results


SPEC = {
    # Algunas páginas usan la barra de fracción tipográfica (U+2044) en «B⁄D».
    "flow_min_max": re.compile(
        r"Optimum operating range\s+([\d,]+)\s*[–-]\s*([\d,]+)\s*B[/⁄]D"),
    "od_in": re.compile(r"Nominal housing diameter\s+([\d.]+)\s*in\."),
    "shaft_in": re.compile(r"Shaft diameter\s+([\d.]+)\s*in\."),
    "shaft_area_in2": re.compile(r"Shaft cross-sectional area\s+([\d.]+)\s*in\."),
    "min_casing_in": re.compile(r"Min\. casing size\s+([\d.]+)\s*in\."),
    "shaft_hp_std": re.compile(r"Shaft brake-power limit\s+Standard\s+([\d,]+)\s*hp"),
    "shaft_hp_hs": re.compile(r"High strength\s+([\d,]+)\s*hp"),
    "burst_buttress_psi": re.compile(r"Buttress\s+([\d,]+)\s*psi"),
    "burst_welded_psi": re.compile(r"Welded\s+([\d,]+)\s*psi"),
}


def page_specs(text: str) -> dict:
    """Ficha mecánica impresa junto a la curva (sólo la página en unidades US)."""
    found: dict[str, float] = {}
    for name, rx in SPEC.items():
        match = rx.search(text)
        if not match:
            continue
        if name == "flow_min_max":
            found["min_flow_bpd"] = float(match.group(1).replace(",", ""))
            found["max_flow_bpd"] = float(match.group(2).replace(",", ""))
        else:
            found[name] = float(match.group(1).replace(",", ""))
    return found


HOUSING_TITLE = re.compile(r"^([A-Z]{1,3}\d{3,5}[A-Z]?) Pump\b")
HOUSING_ROW = re.compile(
    r"^\s*(?P<code>\d{2,3})\s+"
    r"(?P<ft>\d+\.\d+)\s+\[[\d.]+\]\s+"
    r"(?P<lbs>[\d,]+)\s+\[[\d.,]+\]\s+"
    r"(?P<stages>\d{1,4})\b"
)


def housing_tables(pdf_path: str) -> dict[str, list[dict]]:
    """Carcasas por modelo: código, longitud, peso y etapas máximas.

    El catálogo publica una tabla por bomba con las carcasas disponibles y
    cuántas etapas entra cada una. Es el dato que necesita el optimizador de
    carcasas, y es real: hasta ahora se sintetizaba a partir del tope de etapas.
    """
    import subprocess

    text = subprocess.run(["pdftotext", "-layout", pdf_path, "-"],
                          capture_output=True, text=True, check=True).stdout
    tables: dict[str, list[dict]] = {}
    model: str | None = None
    for page in text.split("\f"):
        if "Max." not in page or "Stages" not in page:
            continue
        for line in page.splitlines():
            stripped = line.strip()
            title = HOUSING_TITLE.match(stripped)
            if title:
                model = title.group(1)
                continue
            row = HOUSING_ROW.match(line)
            if row and model:
                entry = {
                    "code": row["code"],
                    "length_ft": float(row["ft"]),
                    "weight_lbs": float(row["lbs"].replace(",", "")),
                    "stages": int(row["stages"]),
                }
                bucket = tables.setdefault(model, [])
                if entry["code"] not in {h["code"] for h in bucket}:
                    bucket.append(entry)
    return tables


def with_specs(pdf_path: str, curves: list[dict]) -> list[dict]:
    with pdfplumber.open(pdf_path) as pdf:
        for curve in curves:
            if not curve["metric"]:
                text = pdf.pages[curve["page"] - 1].extract_text() or ""
                curve["specs"] = page_specs(text)
    return curves


if __name__ == "__main__":
    import json
    import sys

    out = with_specs(sys.argv[1], digitize(sys.argv[1]))
    print(f"{len(out)} curvas digitalizadas")
    if len(sys.argv) > 2:
        open(sys.argv[2], "w", encoding="utf-8").write(
            json.dumps(out, indent=1, ensure_ascii=False))
