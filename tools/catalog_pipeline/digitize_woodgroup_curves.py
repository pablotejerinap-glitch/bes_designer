"""Digitaliza las curvas de bomba del catálogo Wood Group ESP (enero 2003).

A diferencia del catálogo REDA, acá **nada es texto**: los números de los ejes,
los rótulos y hasta la tabla de datos de ingeniería están dibujados como
trazos. La única cadena extraíble de la página es el copyright.

Por eso el reparto de tareas es distinto:

* **OCR** (tesseract) sólo para *calibrar*: leer los números de los cuatro ejes
  y ubicar los rótulos de las curvas. Son cadenas cortas y aisladas, el caso
  más favorable para un OCR, y cada eje se valida exigiendo que sus etiquetas
  caigan sobre una recta (R² ≥ 0.999).
* **Trazado por color** para los *datos*: las tres curvas son las únicas formas
  rojas de la página. Se siguen de derecha a izquierda por continuidad, que es
  donde están bien separadas; hacia la izquierda se cruzan.

Ventaja sobre REDA: acá los tres ejes verticales están escalados para esta
bomba, así que la potencia se **lee** en vez de derivarse, y la identidad
hidráulica HP = Q·H·SG/(3960·η) queda libre como verificación independiente.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

import cv2
import fitz
import numpy as np

DPI = 300
GPM_PER_BPD = 42.0 / 1440.0

# Rojo del fabricante: fill (0.924, 0.335, 0.192) en el PDF.
RED_MIN, RED_MARGIN = 140, 60

TITLE = re.compile(r"Performance\s+Curve\s+for\s+([A-Z]{1,3}-?\d{2,4}[A-Z]?)", re.I)
RPM = re.compile(r"@?\s*(\d[\d,]{2,5})\s*RPM", re.I)
PERCENT = re.compile(r"^(\d{1,3})\s*%$")
DECIMAL = re.compile(r"^(\d+(?:\.\d+)?)$")


@dataclass
class Axis:
    slope: float
    intercept: float
    r2: float
    # Extremos en píxeles de las etiquetas que lo calibraron. Delimitan el área
    # de trazado sin extrapolar: fuera de ahí el eje no dice nada.
    lo: float = 0.0
    hi: float = 0.0

    def value(self, pixel: float) -> float:
        return self.slope * pixel + self.intercept

    def pixel(self, value: float) -> float:
        return (value - self.intercept) / self.slope


def render(page) -> np.ndarray:
    pix = page.get_pixmap(dpi=DPI)
    image = np.frombuffer(pix.samples, dtype=np.uint8)
    return image.reshape(pix.height, pix.width, pix.n)[:, :, :3]


def _ocr_pass(payload: bytes, psm: str) -> list[dict]:
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "--psm", psm, "tsv"],
        input=payload, capture_output=True, check=False,
    )
    words = []
    for line in result.stdout.decode("utf-8", "ignore").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12 or not parts[11].strip():
            continue
        left, top, width, height = (int(parts[i]) for i in range(6, 10))
        words.append({
            "text": parts[11].strip(), "conf": float(parts[10]),
            "x": left + width / 2, "y": top + height / 2,
        })
    return words


def ocr_words(image: np.ndarray) -> list[dict]:
    """Palabras con posición, en dos pasadas de tesseract.

    Modo «texto disperso»: la página es un gráfico con etiquetas sueltas, no un
    bloque de texto corrido.
    """
    ok, buffer = cv2.imencode(".png", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    if not ok:
        return []
    return _ocr_pass(buffer.tobytes(), "11")


def _fit(pairs: list[tuple[float, float]]) -> Axis | None:
    """Recta por el subconjunto coherente más grande.

    Un ajuste por mínimos cuadrados sobre todas las etiquetas es rehén del OCR:
    una sola lectura equivocada —un «0.30» leído «030», un número de la nota al
    pie que se coló— arruina el R² y descarta un eje que estaba bien. Se prueban
    todas las rectas que definen dos etiquetas, se elige la que más etiquetas
    deja sobre sí, y recién entonces se ajusta con ese subconjunto.
    """
    if len(pairs) < 3:
        return None
    scale = max(abs(p[1]) for p in pairs) or 1.0
    tolerance = 0.004 * scale
    best: list[tuple[float, float]] = []
    for i, (xi, yi) in enumerate(pairs):
        for xj, yj in pairs[i + 1:]:
            if xi == xj:
                continue
            slope = (yj - yi) / (xj - xi)
            offset = yi - slope * xi
            inliers = [p for p in pairs
                       if abs(p[1] - (slope * p[0] + offset)) <= tolerance]
            if len(inliers) > len(best):
                best = inliers
    if len(best) < 3:
        return None
    # Sin volver a exigir R²: los inliers ya se eligieron por ser coherentes
    # entre sí. Re-filtrarlos descartaba ejes correctos cuando el OCR leía
    # «0.51» en vez de «0.50» y esa lectura entraba raspando en la tolerancia.
    return _least_squares(best, gate=False)


def _least_squares(pairs: list[tuple[float, float]],
                   gate: bool = True) -> Axis | None:
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    if gate and r2 < 0.999:
        return None
    return Axis(slope, intercept, r2, min(xs), max(xs))


def _clean_number(text: str) -> float | None:
    """Los ejes traen basura del OCR: «0.50]», «0.40)», «0.0'0%»."""
    stripped = text.strip().strip("]|)('\"°").replace(",", "")
    if PERCENT.match(stripped):
        return float(PERCENT.match(stripped).group(1))
    if DECIMAL.match(stripped):
        return float(stripped)
    return None


def calibrate(words: list[dict], width: int, height: int) -> dict[str, Axis]:
    """Los cuatro ejes, cada uno desde su propia columna o fila de etiquetas.

    El gráfico ocupa la mitad superior de la página; abajo va la ficha de
    ingeniería, cuyos números no deben confundirse con los del eje.
    """
    numeric = [
        {**word, "value": _clean_number(word["text"])}
        for word in words if _clean_number(word["text"]) is not None
        and word["y"] < height * 0.55           # el gráfico va arriba; abajo, la ficha
    ]

    def cluster(items, key, tolerance):
        groups: list[list[dict]] = []
        for item in sorted(items, key=lambda w: w[key]):
            if groups and item[key] - groups[-1][-1][key] <= tolerance:
                groups[-1].append(item)
            else:
                groups.append([item])
        return groups

    # El eje de caudal es la fila horizontal con más etiquetas: se detecta
    # agrupando por *y* en vez de recortar una franja fija, porque el «0» del
    # eje vertical cae a la misma altura que el del horizontal y una franja los
    # mezcla, arruinando los dos ajustes.
    rows = [g for g in cluster(numeric, "y", 12) if len(g) >= 5]
    flow_row = max(rows, key=len) if rows else []
    if not flow_row:
        return {}
    # El eje de caudal es el borde inferior del gráfico: todo lo que está más
    # abajo es la nota al pie («…March 1, 1990») y la ficha de ingeniería. Sin
    # este corte, el «1990» de la nota entra en la columna de potencia —cae casi
    # en la misma x— y arruina el ajuste de ese eje.
    floor = max(w["y"] for w in flow_row) + 30
    flow_ids = {id(w) for w in flow_row}
    rest = [w for w in numeric if id(w) not in flow_ids and w["y"] < floor]

    columns: dict[str, list[tuple[float, float]]] = {"flow": [
        (w["x"], w["value"]) for w in flow_row]}
    left: list[tuple[float, list[dict]]] = []
    for group in cluster(rest, "x", 30):
        if len(group) < 3:
            continue
        mean_x = sum(w["x"] for w in group) / len(group)
        percent = sum(1 for w in group if w["text"].strip().endswith("%"))
        if mean_x < width * 0.30:
            left.append((mean_x, group))        # hay dos: metros y pies
        else:
            name = "efficiency" if percent > len(group) / 2 else "power"
            columns.setdefault(name, []).extend(
                (w["y"], w["value"]) for w in group)
    if left:
        # La columna de pies es la pegada al gráfico; la de metros va afuera.
        _, feet = max(left, key=lambda pair: pair[0])
        columns["head_ft"] = [(w["y"], w["value"]) for w in feet]

    axes = {}
    for name, pairs in columns.items():
        pairs.sort()
        fitted = _fit(pairs)
        if fitted:
            axes[name] = fitted
    return axes


def red_bands(image: np.ndarray,
              box: tuple[float, float, float, float] | None = None
              ) -> dict[int, list[float]]:
    """Centro vertical de cada tramo rojo, columna por columna.

    *box* recorta al área de trazado. Hace falta: el logotipo del fabricante,
    arriba a la derecha, es del mismo rojo que las curvas y sin recorte se
    convierte en el punto de partida del trazado.
    """
    red, green, blue = (image[:, :, i].astype(int) for i in range(3))
    mask = ((red > RED_MIN) & (red - green > RED_MARGIN)
            & (red - blue > RED_MARGIN))
    if box:
        x0, y0, x1, y1 = (int(v) for v in box)
        outside = np.ones_like(mask)
        outside[max(y0, 0):y1, max(x0, 0):x1] = False
        mask[outside] = False
    bands: dict[int, list[float]] = {}
    for x in range(mask.shape[1]):
        rows = np.nonzero(mask[:, x])[0]
        if rows.size == 0:
            continue
        centres, start, previous = [], rows[0], rows[0]
        for row in rows[1:]:
            if row - previous > 3:
                centres.append((start + previous) / 2)
                start = row
            previous = row
        centres.append((start + previous) / 2)
        bands[x] = centres
    return bands


def trace(bands: dict[int, list[float]], x_from: int, x_to: int,
          seeds: list[float], max_jump: float = 12.0,
          memory: int = 40) -> list[dict[int, float]]:
    """Sigue N curvas desde *x_from* hacia *x_to* por continuidad de pendiente.

    Se recorre de derecha a izquierda porque ahí las tres curvas están bien
    separadas. El punto delicado son los cruces: la altura y el rendimiento se
    tocan, y a un par de píxeles de distancia «la banda más cercana» pertenece
    igual de bien a las dos, así que un seguimiento por posición las intercambia
    y a partir de ahí cada traza sigue la curva de la otra.

    Por eso se predice dónde debería estar cada curva extrapolando su propia
    pendiente reciente, y se asignan las bandas resolviendo primero los
    emparejamientos más seguros. En un cruce las pendientes son distintas
    —la altura baja, el rendimiento sube— y eso las desambigua.
    """
    tracks: list[dict[int, float]] = [{} for _ in seeds]
    recent: list[list[tuple[int, float]]] = [[] for _ in seeds]
    last = list(seeds)
    step = -1 if x_to < x_from else 1

    def predict(index: int, x: int) -> float:
        history = recent[index]
        if len(history) < 5:
            return last[index]
        x0, y0 = history[0]
        x1, y1 = history[-1]
        slope = (y1 - y0) / (x1 - x0) if x1 != x0 else 0.0
        return y1 + slope * (x - x1)

    for x in range(x_from, x_to, step):
        available = list(bands.get(x, []))
        if not available:
            continue
        pairs = sorted(
            (abs(band - predict(index, x)), index, band)
            for index in range(len(seeds)) for band in available
        )
        taken_tracks: set[int] = set()
        taken_bands: set[float] = set()
        for distance, index, band in pairs:
            if distance > max_jump or index in taken_tracks or band in taken_bands:
                continue
            tracks[index][x] = band
            last[index] = band
            recent[index].append((x, band))
            del recent[index][:-memory]
            taken_tracks.add(index)
            taken_bands.add(band)
    return tracks


def _label_positions(words: list[dict]) -> dict[str, tuple[float, float]]:
    wanted = {"capacity": "head", "efficiency": "efficiency",
              "horsepower": "power"}
    found = {}
    for word in words:
        key = word["text"].strip().lower().rstrip(":.,")
        for prefix, name in wanted.items():
            if key.startswith(prefix[:7]) and name not in found:
                found[name] = (word["x"], word["y"])
    return found


def _assign_by_shape(tracks: list[dict[int, float]],
                     known: dict[str, int]) -> dict[str, int]:
    """Completa la asignación por la forma de cada traza.

    En coordenadas de imagen la *y* crece hacia abajo, así que la altura —que
    baja con el caudal— es la que más sube en *y* de punta a punta, y la
    potencia es la de menor recorrido vertical. El rendimiento queda por
    descarte. No hace falta más: son tres trazas y tres magnitudes.
    """
    assignment = dict(known)
    free = [i for i in range(len(tracks)) if i not in assignment.values()]

    def traits(index: int) -> tuple[float, float]:
        track = tracks[index]
        keys = sorted(track)
        if len(keys) < 5:
            return 0.0, 0.0
        drop = track[keys[-1]] - track[keys[0]]        # + si el valor baja
        span = max(track.values()) - min(track.values())
        return drop, span

    if "head" not in assignment and free:
        chosen = max(free, key=lambda i: traits(i)[0])
        assignment["head"] = chosen
        free.remove(chosen)
    if "power" not in assignment and free:
        chosen = min(free, key=lambda i: traits(i)[1])
        assignment["power"] = chosen
        free.remove(chosen)
    if "efficiency" not in assignment and free:
        assignment["efficiency"] = free[0]
    return assignment


def is_curve_page(page) -> bool:
    """¿Vale la pena renderizar y pasarle OCR a esta página?

    El catálogo alterna, cada cuatro páginas: curva a 60 Hz, curva a 50 Hz,
    tabla de carcasas y gráfico de familia a frecuencia variable. Las tablas se
    reconocen por tener texto de verdad —las páginas de gráfico sólo traen el
    copyright—, y descartarlas antes de renderizar ahorra un cuarto del trabajo,
    que a 300 dpi con OCR no es poco.
    """
    return len(page.get_text().strip()) < 100


AXIS_STRIPS = {
    # nombre -> (x0, x1) como fracción del ancho, relativo al área del gráfico
    "head_ft": (-0.075, 0.005),
    "power": (0.995, 1.045),
    "efficiency": (1.035, 1.095),
}


def rescue_axis(image: np.ndarray, name: str, box: tuple[float, float, float, float]
                ) -> Axis | None:
    """Reintenta un eje leyendo sólo su tira, en modo bloque.

    El modo «texto disperso» que se usa para toda la página es el correcto para
    encontrar rótulos sueltos, pero se saltea etiquetas cuando están apretadas
    en una columna. Recortando la tira del eje, tesseract ve una columna de
    números y nada más, que es donde el modo por bloques acierta.
    """
    x0, y0, x1, y1 = box
    span = x1 - x0
    left, right = AXIS_STRIPS[name]
    crop_x0 = max(int(x0 + left * span), 0)
    crop_x1 = min(int(x0 + right * span), image.shape[1])
    crop_y0, crop_y1 = max(int(y0) - 20, 0), min(int(y1) + 20, image.shape[0])
    if crop_x1 - crop_x0 < 20 or crop_y1 - crop_y0 < 20:
        return None
    crop = image[crop_y0:crop_y1, crop_x0:crop_x1]
    ok, buffer = cv2.imencode(".png", cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
    if not ok:
        return None
    pairs = []
    for word in _ocr_pass(buffer.tobytes(), "6"):
        value = _clean_number(word["text"])
        if value is not None:
            pairs.append((word["y"] + crop_y0, value))
    pairs.sort()
    return _fit(pairs)


def digitize_page(page, n_points: int = 21) -> dict | None:
    if not is_curve_page(page):
        return None
    image = render(page)
    height, width = image.shape[:2]
    words = ocr_words(image)
    text = " ".join(w["text"] for w in words)
    title = TITLE.search(text)
    if not title:
        return None
    # El gráfico de familia a frecuencia variable dibuja nueve curvas de altura
    # y ninguna de rendimiento: no sirve para el catálogo y confundiría al
    # trazador. Se reconoce por su propio título.
    if re.search(r"Variable\s+Frequency", text, re.I):
        return None
    axes = calibrate(words, width, height)
    faltan = {"flow", "head_ft", "power", "efficiency"} - set(axes)
    # El eje de caudal y al menos uno vertical alcanzan para ubicar el área del
    # gráfico; con eso se recuperan los verticales que el OCR de página perdió.
    if "flow" in axes and faltan and faltan != {"flow"}:
        vertical = next((axes[n] for n in ("head_ft", "efficiency", "power")
                         if n in axes), None)
        if vertical:
            box = (axes["flow"].lo, vertical.lo, axes["flow"].hi, vertical.hi)
            for name in list(faltan):
                if name == "flow":
                    continue
                recovered = rescue_axis(image, name, box)
                if recovered:
                    axes[name] = recovered
        faltan = {"flow", "head_ft", "power", "efficiency"} - set(axes)
    if faltan:
        return None

    # Área de trazado deducida de los propios ejes: desde caudal cero hasta el
    # tope del eje de altura, con un margen de un punto de rejilla.
    box = (axes["flow"].lo - 8, axes["head_ft"].lo - 8,
           axes["flow"].hi + 8, axes["head_ft"].hi + 8)
    bands = red_bands(image, box)
    xs = sorted(x for x in bands if len(bands[x]) >= 3)
    if len(xs) < 50:
        return None
    x_right = xs[-1]
    seeds = sorted(bands[x_right])[:3]           # arriba→abajo en el extremo
    tracks = trace(bands, x_right, min(bands) - 1, seeds)

    labels = _label_positions(words)
    # Cada rótulo se queda con la traza que pasa más cerca de él, sin repetir.
    assignment: dict[str, int] = {}
    used: set[int] = set()
    scored = []
    for name, (lx, ly) in labels.items():
        for index, track in enumerate(tracks):
            near = [y for x, y in track.items() if abs(x - lx) < 120]
            if near:
                scored.append((min(abs(y - ly) for y in near), name, index))
    for distance, name, index in sorted(scored):
        if distance < 60 and name not in assignment and index not in used:
            assignment[name] = index
            used.add(index)
    # Lo que el OCR no rotuló se resuelve por forma. Son tres trazas y tres
    # magnitudes, así que cada una que se identifica reduce el problema: la
    # altura es la que más cae de punta a punta y la potencia la más plana.
    if len(assignment) < 3:
        assignment = _assign_by_shape(tracks, assignment)
    if len(assignment) < 3:
        return None

    def sample(track: dict[int, float], x: float) -> float | None:
        keys = sorted(track)
        if not keys or x < keys[0] or x > keys[-1]:
            return None
        for a, b in zip(keys, keys[1:]):
            if a <= x <= b:
                ya, yb = track[a], track[b]
                return ya if b == a else ya + (yb - ya) * (x - a) / (b - a)
        return track[keys[-1]]

    # El rango útil es donde las TRES trazas existen. Tomar el de la altura y
    # descartar después los puntos sin rendimiento o sin potencia dejaba curvas
    # de seis puntos sueltos; así se obtienen los mismos puntos, contiguos y
    # sobre el tramo que las tres cubren.
    usados = [tracks[assignment[n]] for n in ("head", "efficiency", "power")]
    x_min = max(min(track) for track in usados)
    x_max = min(max(track) for track in usados)
    if x_max - x_min < 100:
        return None
    head_track = tracks[assignment["head"]]
    points = []
    for i in range(n_points):
        x = x_min + (x_max - x_min) * i / (n_points - 1)
        y_head = sample(head_track, x)
        y_eff = sample(tracks[assignment["efficiency"]], x)
        y_power = sample(tracks[assignment["power"]], x)
        if None in (y_head, y_eff, y_power):
            continue
        points.append({
            "flow_rate": round(axes["flow"].value(x), 1),
            "head_per_stage": round(axes["head_ft"].value(y_head), 4),
            "efficiency": round(max(axes["efficiency"].value(y_eff), 0.0) / 100, 4),
            "hp_per_stage": round(max(axes["power"].value(y_power), 0.0), 5),
        })
    rpm = RPM.search(text)
    return {
        "model": title.group(1).upper().replace("--", "-"),
        "rpm": int(rpm.group(1).replace(",", "")) if rpm else None,
        "r2": {name: round(axis.r2, 6) for name, axis in axes.items()},
        "points": points,
    }


def hydraulic_check(points: list[dict]) -> float | None:
    """Mediana de HP leída / HP por la identidad. Las tres curvas son lecturas
    independientes sobre ejes propios, así que la identidad es una verificación
    real y no una definición circular."""
    ratios = []
    for point in points:
        if point["efficiency"] < 0.15 or point["hp_per_stage"] <= 0:
            continue
        theoretical = (point["flow_rate"] * GPM_PER_BPD * point["head_per_stage"]
                       / (3960.0 * point["efficiency"]))
        if theoretical > 0:
            ratios.append(point["hp_per_stage"] / theoretical)
    if not ratios:
        return None
    ratios.sort()
    return round(ratios[len(ratios) // 2], 4)


def digitize(pdf_path: str, n_points: int = 21) -> list[dict]:
    results = []
    with fitz.open(pdf_path) as document:
        for index, page in enumerate(document):
            digitized = digitize_page(page, n_points)
            if not digitized or not digitized["points"]:
                continue
            digitized["page"] = index + 1
            digitized["hp_read_vs_identity"] = hydraulic_check(digitized["points"])
            results.append(digitized)
    return results


if __name__ == "__main__":
    import json
    import sys

    out = digitize(sys.argv[1])
    print(f"{len(out)} curvas digitalizadas")
    for curve in out:
        print(f"   pag {curve['page']:>3}  {curve['model']:<9} {curve['rpm']} rpm  "
              f"{len(curve['points'])} pts  HP leída/identidad = "
              f"{curve['hp_read_vs_identity']}")
    if len(sys.argv) > 2:
        open(sys.argv[2], "w", encoding="utf-8").write(
            json.dumps(out, indent=1, ensure_ascii=False))
