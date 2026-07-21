"""
Digitalizacion de curvas de performance de bombas ESP.
======================================================
Dos motores:

* VECTORIAL (``digitize_vector``): para PDFs cuyas curvas son trazos
  vectoriales (REDA, Wood Group). Lee los ticks de eje como TEXTO
  (``get_text('words')``) => calibracion exacta sin OCR, y las polilineas
  con color (``get_drawings``) => la curva casi punto a punto. Para las
  familias multi-frecuencia elige la linea de 60 Hz por proximidad a su
  etiqueta. La eficiencia se deriva de head y power con la identidad
  hidraulica (REDA no la grafica).

* RASTER (``extract_chart_image``): para curvas que son imagen embebida
  (Centrilift/Alkhorayef). Guarda el grafico para revision/овerlay; la
  digitalizacion fina por mascara de color queda marcada para revision
  (alcance elegido: sin OCR).

Salidas: puntos [{flow_bpd, head_ft_per_stage, hp_per_stage, efficiency}],
una imagen overlay de QA y un dict de diagnostico con la confianza.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import fitz
import numpy as np

from config import HYDRAULIC_K


# ----------------------------------------------------------- ajuste lineal
def _robust_linear(pairs: list[tuple[float, float]], tol_frac: float = 0.03
                   ) -> Optional[tuple[float, float]]:
    """(pixel, valor) -> (m, b) con seleccion de inliers. None si no ajusta."""
    pairs = [(p, v) for p, v in pairs if v is not None]
    if len(pairs) < 3:
        if len(pairs) == 2 and pairs[0][0] != pairs[1][0]:
            (p1, v1), (p2, v2) = pairs
            m = (v2 - v1) / (p2 - p1)
            return m, v1 - m * p1
        return None
    vmax = max(v for _, v in pairs)
    vmin = min(v for _, v in pairs)
    tol = max(tol_frac * (vmax - vmin), 1e-6)
    best = None
    n = len(pairs)
    for i in range(n):
        for j in range(i + 1, n):
            (p1, v1), (p2, v2) = pairs[i], pairs[j]
            if abs(p1 - p2) < 1e-6 or v1 == v2:
                continue
            m = (v2 - v1) / (p2 - p1)
            b = v1 - m * p1
            inl = [(p, v) for p, v in pairs if abs(m * p + b - v) <= tol]
            if best is None or len(inl) > len(best):
                best = inl
    if not best or len(best) < 3:
        return None
    ps = np.array([p for p, _ in best])
    vs = np.array([v for _, v in best])
    m, b = np.polyfit(ps, vs, 1)
    return float(m), float(b)


# ------------------------------------------------------------- ejes por texto
@dataclass
class Panel:
    kind: str                         # 'head' | 'power'
    m: float                          # py -> valor
    b: float
    y_lo: float                       # franja vertical del panel (px)
    y_hi: float

    def value(self, py):  return self.m * py + self.b
    def contains(self, py, margin=12): return self.y_lo - margin <= py <= self.y_hi + margin


@dataclass
class Axes:
    x: tuple[float, float]            # px -> capacity (bpd)
    panels: list[Panel]
    plot: tuple[float, float, float, float]  # x0,x1,y0,y1 (px)

    def flow(self, px):  return self.x[0] * px + self.x[1]

    def panel(self, kind: str) -> Optional[Panel]:
        for p in self.panels:
            if p.kind == kind:
                return p
        return None


_NUMWORD = re.compile(r"^\d[\d,]*\.?\d*$")


def _numeric_words(page: fitz.Page) -> list[tuple[float, float, float]]:
    out = []
    for w in page.get_text("words"):
        t = w[4].strip()
        if _NUMWORD.match(t):
            try:
                v = float(t.replace(",", ""))
            except ValueError:
                continue
            cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
            out.append((cx, cy, v))
    return out


def _split_monotonic_runs(col: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """col = [(py, valor)] ordenado por py -> tramos = paneles apilados.
    Corta cuando (a) el valor sube (reset: head 80->10, power 10->0) o
    (b) el paso entre etiquetas se achica bruscamente (head paso 10 -> power
    paso 1), caso REDA en el que ambos ejes concatenan de forma monotona."""
    col = sorted(col, key=lambda t: t[0])
    if len(col) < 3:
        return []
    runs: list[list] = [[col[0]]]
    for py, v in col[1:]:
        prev_v = runs[-1][-1][1]
        dv = v - prev_v
        new_run = dv > 0.05 * max(1.0, abs(prev_v))          # (a) reset
        if not new_run and len(runs[-1]) >= 2:               # (b) paso mas chico
            steps = [abs(runs[-1][i + 1][1] - runs[-1][i][1])
                     for i in range(len(runs[-1]) - 1)]
            steps = [s for s in steps if s > 1e-6]
            med = float(np.median(steps)) if steps else 0.0
            if med > 0 and abs(dv) < 0.45 * med:
                new_run = True
        if new_run and len(runs[-1]) >= 3:
            runs.append([])
        runs[-1].append((py, v))
    return [r for r in runs if len(r) >= 3]


def chart_units(page: fitz.Page) -> str:
    """'english' (B/D + ft), 'metric' (m3/d + m) o 'unknown', segun los
    titulos de eje. REDA publica cada bomba en ambos sistemas."""
    t = page.get_text("text").lower().replace(" ", "")
    if "capacity(b/d)" in t or "capacity(bpd)" in t or "head(ft)" in t:
        return "english"
    if ("capacity(m3/d)" in t or "capacity(m³/d)" in t or "head(m)" in t
            or "capacity(m3" in t):
        return "metric"
    return "unknown"


def calibrate_axes(page: fitz.Page) -> Optional[Axes]:
    nums = _numeric_words(page)
    if len(nums) < 6:
        return None

    # --- eje X: fila horizontal de numeros (misma y, x creciente) ---
    yrows: dict[int, list] = {}
    for n in nums:
        yrows.setdefault(round(n[1] / 6), []).append(n)
    xrow_best = None
    for g in yrows.values():
        if len(g) < 4:
            continue
        fit = _robust_linear([(n[0], n[2]) for n in g])
        if fit and fit[0] > 0:
            span = max(n[0] for n in g) - min(n[0] for n in g)
            if xrow_best is None or span > xrow_best[2]:
                xrow_best = (fit, g, span)
    if not xrow_best:
        return None
    x_fit = xrow_best[0]
    x_axis_y = float(np.median([n[1] for n in xrow_best[1]]))
    x0 = min(n[0] for n in xrow_best[1])
    x1 = max(n[0] for n in xrow_best[1])

    # --- columna(s) Y a la izquierda del plot: numeros con cx < x0 ---
    left = [(n[1], n[2]) for n in nums if n[0] < x0 - 2 and n[1] < x_axis_y + 8]
    panels: list[Panel] = []
    if left:
        runs = _split_monotonic_runs(left)
        # ordena por posicion vertical (arriba primero): head arriba, power abajo
        runs.sort(key=lambda r: np.median([py for py, _ in r]))
        kinds = ["head", "power", "aux"]
        for i, run in enumerate(runs[:3]):
            fit = _robust_linear([(py, v) for py, v in run], tol_frac=0.05)
            if not fit:
                continue
            ys = [py for py, _ in run]
            panels.append(Panel(kind=kinds[i], m=fit[0], b=fit[1],
                                y_lo=min(ys), y_hi=max(ys)))

    y0 = min([p.y_lo for p in panels], default=x_axis_y)
    y1 = max([p.y_hi for p in panels] + [x_axis_y])
    return Axes(x=x_fit, panels=panels, plot=(x0, x1, y0, y1))


# ------------------------------------------------ polilineas vectoriales
def _bezier_pts(p0, p1, p2, p3, n=6):
    pts = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        x = (mt**3 * p0.x + 3 * mt**2 * t * p1.x + 3 * mt * t**2 * p2.x + t**3 * p3.x)
        y = (mt**3 * p0.y + 3 * mt**2 * t * p1.y + 3 * mt * t**2 * p2.y + t**3 * p3.y)
        pts.append((x, y))
    return pts


def colored_polylines(page: fitz.Page) -> dict[tuple, list[list[tuple[float, float]]]]:
    """color RGB redondeado -> lista de polilineas (cada una lista de puntos)."""
    out: dict[tuple, list] = {}
    for d in page.get_drawings():
        col = d.get("color")
        if col is None:
            continue
        rgb = tuple(round(c, 2) for c in col)
        pts: list[tuple[float, float]] = []
        for it in d["items"]:
            if it[0] == "l":
                if not pts:
                    pts.append((it[1].x, it[1].y))
                pts.append((it[2].x, it[2].y))
            elif it[0] == "c":
                if not pts:
                    pts.append((it[1].x, it[1].y))
                pts.extend(_bezier_pts(it[1], it[2], it[3], it[4]))
        if len(pts) >= 3:
            out.setdefault(rgb, []).append(pts)
    return out


def _freq_labels(page: fitz.Page, freq: int = 60) -> list[tuple[float, float]]:
    """Centros de las etiquetas 'NN Hz' que coinciden con freq."""
    words = page.get_text("words")
    labels = []
    for i, w in enumerate(words):
        if w[4].strip() == str(freq):
            # busca 'Hz' contiguo a la derecha en la misma linea
            for w2 in words:
                if w2[4].strip().lower() == "hz" and abs(w2[1] - w[1]) < 3 \
                        and 0 <= w2[0] - w[2] < 25:
                    labels.append(((w[0] + w[2]) / 2, (w[1] + w[3]) / 2))
                    break
    return labels


def _nearest_polyline(polys, target):
    best, bestd = None, 1e18
    tx, ty = target
    for pl in polys:
        d = min((px - tx)**2 + (py - ty)**2 for px, py in pl)
        if d < bestd:
            bestd, best = d, pl
    return best


def _polys_in_panel(polys, panel: Panel):
    """Polilineas cuya mayoria de puntos cae en la franja vertical del panel."""
    out = []
    for pl in polys:
        inside = sum(1 for _, py in pl if panel.contains(py))
        if inside >= max(3, 0.6 * len(pl)):
            out.append(pl)
    return out


def _pick_curve(polys, panel: Panel, freq_labels):
    """Elige la polilinea de la curva objetivo dentro del panel. Con etiquetas
    de 60 Hz usa proximidad; si no, la de valor mediano (60 Hz suele ser la del
    medio del abanico)."""
    polys = _polys_in_panel([p for p in polys if len(p) >= 4], panel)
    if not polys:
        return None
    region_labels = [lb for lb in freq_labels if panel.contains(lb[1], margin=30)]
    if region_labels:
        best, bestd = None, 1e18
        for lb in region_labels:
            pl = _nearest_polyline(polys, lb)
            d = min((px - lb[0])**2 + (py - lb[1])**2 for px, py in pl)
            if d < bestd:
                bestd, best = d, pl
        if best:
            return best
    polys_sorted = sorted(polys, key=lambda pl: np.median([py for _, py in pl]))
    return polys_sorted[len(polys_sorted) // 2]


def _sample_polyline(pl, axes: Axes, panel: Panel, q_points):
    """Interpola la polilinea (en px) a valores en cada caudal objetivo."""
    data = sorted(((axes.flow(px), panel.value(py)) for px, py in pl),
                  key=lambda t: t[0])
    data = [(q, v) for q, v in data if v is not None]
    if len(data) < 3:
        return [None] * len(q_points)
    qs = np.array([d[0] for d in data])
    vs = np.array([d[1] for d in data])
    out = []
    for q in q_points:
        if q < qs.min() - 1 or q > qs.max() + 1:
            out.append(None)
        else:
            out.append(float(np.interp(q, qs, vs)))
    return out


# ------------------------------------------------------- API de alto nivel
@dataclass
class CurveResult:
    points: list[dict] = field(default_factory=list)
    method: str = "vector"
    confidence: float = 0.0
    review: bool = True
    reason: str = ""
    n_points: int = 0
    axes: Optional["Axes"] = None
    units: str = "english"
    marks: list = field(default_factory=list)   # (x_px, y_px, (b,g,r)) visual


# ============================== panel unico (landscape, 3 ejes) ==============
def _derotated(page: fitz.Page):
    """Palabras numericas y polilineas de color en el espacio VISUAL (derotado).
    Las paginas AN/D de REDA estan rotadas 90 grados."""
    dm = page.derotation_matrix
    nums = []
    for w in page.get_text("words"):
        t = w[4].strip()
        if not _NUMWORD.match(t):
            continue
        try:
            v = float(t.replace(",", ""))
        except ValueError:
            continue
        p = fitz.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2) * dm
        nums.append((p.x, p.y, v))
    polys: dict[tuple, list] = {}
    for d in page.get_drawings():
        col = d.get("color")
        if col is None:
            continue
        rgb = tuple(round(c, 2) for c in col)
        pts = []
        for it in d["items"]:
            if it[0] == "l":
                for pp in (it[1], it[2]):
                    q = pp * dm
                    pts.append((q.x, q.y))
            elif it[0] == "c":
                for pp in _bezier_pts(it[1], it[2], it[3], it[4]):
                    q = fitz.Point(pp) * dm
                    pts.append((q.x, q.y))
        if len(pts) >= 4:
            polys.setdefault(rgb, []).append(pts)
    return nums, polys


def _value_columns(nums):
    """Columnas verticales (dx cte) con progresion aritmetica limpia -> ejes.
    Devuelve [(dx, (m,b), puntos)] ordenado por dx."""
    cols: dict[int, list] = {}
    for x, y, v in nums:
        cols.setdefault(round(x / 8), []).append((x, y, v))
    out = []
    for g in cols.values():
        if len(g) < 4:
            continue
        fit = _robust_linear([(y, v) for _, y, v in g], tol_frac=0.05)
        if fit and abs(fit[0]) > 1e-9:
            dx = float(np.median([x for x, _, _ in g]))
            out.append((dx, fit, g))
    out.sort(key=lambda c: c[0])
    return out


def _longest_color_path(polys, want: str):
    """Devuelve la polilinea mas larga del color pedido ('blue'|'red')."""
    best, bestn = None, 0
    for rgb, pls in polys.items():
        r, gc, b = rgb
        is_blue = b - max(r, gc) > 0.15
        is_red = r - max(gc, b) > 0.25
        if (want == "blue" and not is_blue) or (want == "red" and not is_red):
            continue
        for pl in pls:
            if len(pl) > bestn:
                bestn, best = len(pl), pl
    return best


def _digitize_single_panel(page: fitz.Page, units: str, freq: int) -> CurveResult:
    nums, polys = _derotated(page)
    if len(nums) < 6:
        return CurveResult(method="vector-1p", review=True, units=units,
                           reason="pocas etiquetas numericas")
    # --- eje X (capacidad): fila horizontal con progresion en dx ---
    rows: dict[int, list] = {}
    for x, y, v in nums:
        rows.setdefault(round(y / 8), []).append((x, v))
    x_fit = None
    for g in rows.values():
        if len(g) < 4:
            continue
        fit = _robust_linear([(x, v) for x, v in g])
        if fit and abs(fit[0]) > 1e-9:      # capacidad: pendiente de cualquier signo
            span = max(x for x, _ in g) - min(x for x, _ in g)
            vspan = max(v for _, v in g) - min(v for _, v in g)
            if vspan > 50 and (x_fit is None or span > x_fit[0]):
                x_fit = (span, fit)
    if x_fit is None:
        return CurveResult(method="vector-1p", review=True, units=units,
                           reason="no se calibro el eje X")
    x_m, x_b = x_fit[1]
    cols = _value_columns(nums)
    if len(cols) < 2:
        return CurveResult(method="vector-1p", review=True, units=units,
                           reason="ejes de valor insuficientes")
    blue = _longest_color_path(polys, "blue")
    red = _longest_color_path(polys, "red")
    if blue is None:
        return CurveResult(method="vector-1p", review=True, units=units,
                           reason="sin curva de head (azul)")

    def flow(px):
        return x_m * px + x_b
    q_lo = max(0.0, min(flow(p[0]) for p in blue))
    q_hi = max(flow(p[0]) for p in blue)
    if not (q_hi > q_lo):
        return CurveResult(method="vector-1p", review=True, units=units,
                           reason="eje X invalido")
    q_points = [round(q) for q in np.linspace(max(q_lo, 0.03 * q_hi),
                                              0.97 * q_hi, 11)]

    def sample(pl, m, b):
        data = sorted(((flow(px), m * py + b) for px, py in pl),
                      key=lambda t: t[0])
        qs = np.array([d[0] for d in data])
        vs = np.array([d[1] for d in data])
        return [float(np.interp(q, qs, vs)) if qs.min() - 1 <= q <= qs.max() + 1
                else None for q in q_points]

    # --- asignacion de ejes por FISICA: probar cada columna para head y para
    #     power; quedarse con el par (head decreciente + eff pico en 0.25-0.85) ---
    best = None
    for hi in range(len(cols)):
        heads = sample(blue, cols[hi][1][0], cols[hi][1][1])
        hv = [h for h in heads if h is not None]
        if len(hv) < 6 or hv[0] <= 0 or hv[0] < hv[-1]:
            continue                       # head debe decrecer
        red_options = range(len(cols)) if red is not None else [None]
        for pi in red_options:
            if pi == hi:
                continue
            pts = []
            powers = (sample(red, cols[pi][1][0], cols[pi][1][1])
                      if pi is not None else [None] * len(q_points))
            for q, h, p in zip(q_points, heads, powers):
                if h is None or h <= 0:
                    continue
                eff = (max(0.0, min(0.999, q * h / (HYDRAULIC_K * p)))
                       if p and p > 0 else None)
                pts.append({"flow_bpd": q, "head_ft_per_stage": round(h, 3),
                            "hp_per_stage": round(p, 4) if p else None,
                            "efficiency": round(eff, 3) if eff else None})
            effs = [pt["efficiency"] for pt in pts if pt["efficiency"]]
            peak = max(effs) if effs else 0
            # score: premia eff pico fisico y muchos puntos
            physical = 0.25 <= peak <= 0.85
            score = (len(pts) + (10 if physical else 0)
                     - abs(peak - 0.6) * 5)
            if best is None or score > best[0]:
                best = (score, pts, peak, physical, hi, pi)
    if best is None:
        return CurveResult(method="vector-1p", review=True, units=units,
                           reason="no se pudo asignar ejes head/power")
    _, points, peak, physical, hi, pi = best
    # marcas para el overlay (espacio visual/derotado = pixmap de la pagina)
    hm, hb = cols[hi][1]
    pm, pb = (cols[pi][1] if pi is not None else (None, None))
    marks = []
    for pt in points:
        px = (pt["flow_bpd"] - x_b) / x_m
        marks.append((px, (pt["head_ft_per_stage"] - hb) / hm, (255, 0, 0)))
        if pm and pt["hp_per_stage"]:
            marks.append((px, (pt["hp_per_stage"] - pb) / pm, (0, 0, 255)))
    reasons = []
    if not physical:
        reasons.append(f"eff pico {peak:.2f} fuera de rango fisico")
    if len(points) < 6:
        reasons.append(f"solo {len(points)} puntos")
    conf = round(min(1.0, len(points) / 9.0) * (1.0 if physical else 0.5), 2)
    return CurveResult(points=points, method="vector-1p", units=units,
                       confidence=conf, review=bool(reasons),
                       reason="; ".join(reasons), n_points=len(points),
                       marks=marks)


def digitize_vector(page: fitz.Page, *, freq: int = 60) -> CurveResult:
    units = chart_units(page)
    if units == "metric":
        # se procesa solo la version en B/D + ft (misma bomba, sin duplicar)
        return CurveResult(method="vector", review=True, units="metric",
                           reason="grafico metrico (se usa el gemelo en B/D)")
    if page.rotation in (90, 270):
        # layout de panel unico (AN/D): head+power+eff, 3 ejes, landscape
        return _digitize_single_panel(page, units, freq)
    axes = calibrate_axes(page)
    head_panel = axes.panel("head") if axes else None
    if axes is None or head_panel is None:
        return CurveResult(method="vector", review=True, units=units,
                           reason="no se pudieron calibrar los ejes")
    power_panel = axes.panel("power")
    polys_by_color = colored_polylines(page)

    def is_grayish(c):
        return max(c) - min(c) < 0.12
    # todas las polilineas de color (curvas), sin grillas gris/negro
    color_polys = [pl for c, pls in polys_by_color.items()
                   if not is_grayish(c) for pl in pls]
    if not color_polys:
        return CurveResult(method="vector", review=True,
                           reason="no hay polilineas de color (curvas)")
    labels = _freq_labels(page, freq)
    head_pl = _pick_curve(color_polys, head_panel, labels)
    power_pl = _pick_curve(color_polys, power_panel, labels) if power_panel else None

    q_lo, q_hi = axes.flow(axes.plot[0]), axes.flow(axes.plot[1])
    if not (q_hi > q_lo):
        return CurveResult(method="vector", review=True, reason="eje X invalido")
    q_points = [round(q) for q in np.linspace(max(q_lo, 0.03 * q_hi),
                                              0.98 * q_hi, 11)]
    heads = (_sample_polyline(head_pl, axes, head_panel, q_points)
             if head_pl else [None] * len(q_points))
    powers = (_sample_polyline(power_pl, axes, power_panel, q_points)
              if (power_pl and power_panel) else [None] * len(q_points))

    points = []
    for q, h, p in zip(q_points, heads, powers):
        if h is None or h <= 0:
            continue
        eff = None
        if p and p > 0:
            eff = max(0.0, min(0.999, q * h / (HYDRAULIC_K * p)))
        points.append({"flow_bpd": q, "head_ft_per_stage": round(h, 3),
                       "hp_per_stage": round(p, 4) if p else None,
                       "efficiency": round(eff, 3) if eff else None})

    reasons = []
    hs = [pt["head_ft_per_stage"] for pt in points]
    if len(hs) >= 5 and sum(1 for a, b in zip(hs, hs[1:]) if b > a * 1.05) > 1:
        reasons.append("head no decreciente")
    if power_pl is None:
        reasons.append("sin curva de potencia (eff no derivada)")
    conf = min(1.0, len(points) / 9.0) * (1.0 if power_pl else 0.6)
    if len(points) < 6:
        reasons.append(f"solo {len(points)} puntos")
    # sanidad de eficiencia derivada: el pico deberia caer en 0.35-0.85
    effs = [pt["efficiency"] for pt in points if pt["efficiency"]]
    if effs and max(effs) < 0.2:
        reasons.append(f"eff pico {max(effs):.2f} sospechosa (revisar escala)")
    return CurveResult(points=points, method="vector", axes=axes, units=units,
                       confidence=round(conf, 2),
                       review=bool(reasons), reason="; ".join(reasons),
                       n_points=len(points))


def save_overlay(page: fitz.Page, res: CurveResult, out_path: Path,
                 zoom: float = 2.0, title: str = "") -> None:
    """Rasteriza la pagina y superpone los puntos digitalizados (QA visual):
    circulos AZULES = head muestreado, ROJOS = power muestreado.
    Las paginas rotadas con marcas se renderizan en el espacio DEROTADO (mismo
    en el que se midio) para que los puntos alineen exactamente; el grafico
    queda de costado pero la verificacion es precisa."""
    if res.marks and page.rotation in (90, 270):
        mat = fitz.Matrix(zoom, zoom) * page.derotation_matrix
    else:
        mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n)[:, :, :3].copy()
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    axes = res.axes
    if axes:
        head_p = axes.panel("head")
        power_p = axes.panel("power")
        for pt in res.points:
            px = (pt["flow_bpd"] - axes.x[1]) / axes.x[0]
            if head_p and pt["head_ft_per_stage"] is not None:
                py = (pt["head_ft_per_stage"] - head_p.b) / head_p.m
                cv2.circle(img, (int(px * zoom), int(py * zoom)), 4, (255, 0, 0), -1)
            if power_p and pt["hp_per_stage"]:
                py = (pt["hp_per_stage"] - power_p.b) / power_p.m
                cv2.circle(img, (int(px * zoom), int(py * zoom)), 4, (0, 0, 255), -1)
    for mx, my, color in res.marks:      # panel unico (marcas ya en visual)
        cv2.circle(img, (int(mx * zoom), int(my * zoom)), 4, color, -1)
    banner = f"{title}  metodo={res.method} pts={res.n_points} conf={res.confidence}"
    if res.review:
        banner += f"  REVISAR: {res.reason}"
    cv2.putText(img, banner, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (0, 128, 0), 1, cv2.LINE_AA)
    cv2.imwrite(str(out_path), img)


def extract_chart_image(doc: fitz.Document, page_index: int, out_path: Path
                        ) -> bool:
    """Guarda la imagen embebida mas grande de la pagina (curvas raster)."""
    import pdf_utils as U
    best = None
    for arr in U.iter_page_images(doc, page_index):
        if best is None or arr.size > best.size:
            best = arr
    if best is None:
        return False
    cv2.imwrite(str(out_path), cv2.cvtColor(best, cv2.COLOR_RGB2BGR))
    return True
