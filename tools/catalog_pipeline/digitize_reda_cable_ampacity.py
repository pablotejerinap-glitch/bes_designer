"""Digitaliza las curvas de ampacidad de los cables REDA.

El *REDA ESP Catalog* publica, por familia de cable, un gráfico
**«Maximum conductor current, A» vs. «Maximum well temperature, °F»** con una
curva por calibre (2/0, 1/0, 1, 2, 4 y 6 AWG). Es el dato que el diseño
eléctrico necesita y que el catálogo del proyecto no tenía: hasta ahora
``cables.json`` llevaba un ``max_amps`` **plano**, tomado de Brown Tabla 4.52 /
API RP 11S6 por calibre estándar, sin 1/0 ni 2/0.

Por qué importa
---------------
1. **La ampacidad depende de la temperatura**, y mucho: la misma curva cae a la
   mitad entre un pozo frío y uno caliente. Un valor plano es conservador en
   pozos fríos y **optimista en pozos calientes**, que es el lado peligroso.
2. **Agrega los calibres 1/0 y 2/0**, que el catálogo del proyecto no tenía.
   Ése era el techo de 80 A de corriente de motor diseñable documentado en
   ``.claude/rules/domain.md``.
3. Es dato **del fabricante**, no de una tabla genérica por calibre: se puede
   citar en la tesis contra la página del catálogo.

Cómo se leen los gráficos
-------------------------
No hay OCR y no se estima nada. Las curvas están en la **capa vectorial** del
PDF, dibujadas en blanco (``stroking_color == 1.0``) sobre el fondo oscuro del
gráfico, y los ejes se calibran por **regresión lineal sobre las etiquetas de
marca del propio gráfico** — el mismo método que ``digitize_reda_curves.py``
usa con las curvas de bomba. Si la regresión no da R² ≥ 0.9999, el gráfico se
descarta en vez de publicarse dudoso.

La correspondencia curva ↔ calibre sale del orden: la leyenda lista los
calibres de mayor a menor sección (2/0 arriba), y en el gráfico la curva del
conductor más grueso es la de mayor corriente, o sea la más alta. Se verifica
que las dos listas tengan la misma longitud y que las curvas no se crucen;
si se cruzan, el gráfico se descarta.

Salida
------
``backend/src/bes/catalogs/cable_ampacity.json``, con una entrada por familia y
calibre y la curva como pares ``(temp_f, amps)``. No toca ``cables.json``.

Uso::

    python tools/catalog_pipeline/digitize_reda_cable_ampacity.py [--pdf RUTA]
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

# --------------------------------------------------------------------------
# 1. Constantes de lectura
# --------------------------------------------------------------------------

#: Páginas del catálogo con gráfico de ampacidad (índice 0). Se listan a mano
#: porque el título no siempre está en la página —a veces es un encabezado de
#: sección— y buscarlas por texto daría falsos positivos.
PAGINAS_AMPACIDAD = (473, 475, 477, 479, 488)

#: Color con que están trazadas las curvas: blanco sobre el fondo oscuro del
#: gráfico. Es lo que las separa de la grilla, que es gris.
COLOR_CURVA = 1.0

#: Alto máximo (coordenada ``top``) de la zona de gráficos en estas páginas.
#: Por debajo empiezan las tablas de dimensiones, que también tienen líneas.
TOPE_ZONA_GRAFICO = 320.0

#: Ancho mínimo de una curva, en puntos PDF. Los trazos blancos cortos son las
#: muestras de color de la leyenda, no curvas.
ANCHO_MINIMO_CURVA = 60.0

#: R² mínimo de la calibración de un eje. Las marcas de un gráfico vectorial
#: son exactas, así que un ajuste peor significa que se mezclaron etiquetas de
#: otra cosa y el gráfico no se puede leer.
R2_MINIMO = 0.9999

#: Puntos por curva en la salida. Las curvas son suaves y monótonas; 21 puntos
#: dejan un paso de 5 °F en el rango típico de 100 °F.
N_MUESTRAS = 21

_CALIBRE = re.compile(r"No\.\s*([\d/]+)\s*Conductor")


# --------------------------------------------------------------------------
# 2. Geometría: evaluar los trazos del PDF
# --------------------------------------------------------------------------

def _bezier(pts: list[tuple[float, float]], t: float) -> tuple[float, float]:
    """Evalúa una Bézier de grado ``len(pts) - 1`` en el parámetro *t*.

    Se usa el algoritmo de De Casteljau, que es estable y no necesita conocer
    el grado de antemano. Los trazos del catálogo vienen con 3 o 4 puntos de
    control según el operador con que se dibujaron (``v`` o ``c``), y los dos
    casos son la misma curva evaluada con distinto grado.

    Args:
        pts: Puntos de control, en orden.
        t: Parámetro en [0, 1].

    Returns:
        El punto ``(x, y)`` de la curva.
    """
    p = list(pts)
    while len(p) > 1:
        p = [
            (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            for a, b in zip(p, p[1:])
        ]
    return p[0]


def _muestrear(obj: dict, n: int = N_MUESTRAS) -> list[tuple[float, float]]:
    """Muestrea un trazo del PDF en *n* puntos equiespaciados en el parámetro.

    Devuelve coordenadas **de página** (``x``, ``top``), con ``top`` creciendo
    hacia abajo, que es la convención de pdfplumber.
    """
    pts = list(obj.get("pts") or [])
    if len(pts) < 2:
        return []
    return [_bezier(pts, i / (n - 1)) for i in range(n)]


# --------------------------------------------------------------------------
# 3. Calibración de ejes
# --------------------------------------------------------------------------

@dataclass
class Eje:
    """Conversión lineal de píxeles del PDF a unidades de ingeniería."""
    pendiente: float
    ordenada: float
    r2: float

    def valor(self, px: float) -> float:
        return self.pendiente * px + self.ordenada


def _ajustar(px: list[float], val: list[float]) -> Eje | None:
    """Regresión lineal píxel → valor, con su R². ``None`` si no hay 3 marcas.

    Se exigen **tres** marcas y no dos: con dos el ajuste pasa exacto por
    ambas y el R² no informa nada, así que un rótulo mal asociado pasaría sin
    que nadie se entere.
    """
    n = len(px)
    if n < 3:
        return None
    mx, mv = sum(px) / n, sum(val) / n
    sxx = sum((x - mx) ** 2 for x in px)
    if sxx == 0:
        return None
    sxy = sum((x - mx) * (v - mv) for x, v in zip(px, val))
    m = sxy / sxx
    b = mv - m * mx
    sst = sum((v - mv) ** 2 for v in val)
    sse = sum((v - (m * x + b)) ** 2 for x, v in zip(px, val))
    r2 = 1.0 if sst == 0 else 1.0 - sse / sst
    return Eje(m, b, r2)


#: Color de la grilla del gráfico: gris claro. Es lo que la separa de las
#: curvas (blancas) y de las reglas de tabla (casi negras).
COLOR_GRILLA = (0.576, 0.584, 0.596)

#: Distancia máxima, en puntos PDF, entre una línea de grilla y el rótulo que
#: le corresponde. Tiene que ser bastante menor que el paso entre marcas (≈22
#: pt en estos gráficos) para que una línea no se lleve el rótulo de la de al
#: lado. El desfasaje real medido es de 2.7 pt.
TOLERANCIA_APAREO = 8.0


def _grilla(
    page, x_min: float, x_max: float, y_min: float, y_max: float,
) -> tuple[list[float], list[float]]:
    """Posiciones de las líneas de grilla de un gráfico.

    Returns:
        ``(horizontales, verticales)`` — las horizontales como coordenada
        ``top``, las verticales como ``x``. Ordenadas y sin repetidos.
    """
    holgura = 12.0
    horiz, vert = set(), set()
    for l in page.lines:
        if l.get("stroking_color") != COLOR_GRILLA:
            continue
        dentro_x = x_min - holgura <= l["x0"] and l["x1"] <= x_max + holgura * 6
        dentro_y = y_min - holgura * 4 <= l["top"] and l["bottom"] <= y_max + holgura
        if abs(l["top"] - l["bottom"]) < 0.5 and dentro_x and dentro_y:
            horiz.add(round(l["top"], 2))
        elif abs(l["x0"] - l["x1"]) < 0.5 and dentro_x and dentro_y:
            vert.add(round(l["x0"], 2))
    return sorted(horiz), sorted(vert)


def _ajustar_con_grilla(
    grilla: list[float], marcas: list[dict], eje: str,
) -> Eje | None:
    """Calibra un eje apareando las líneas de grilla con los valores rotulados.

    Los rótulos aportan **qué** vale cada marca; la grilla, **dónde** está. Se
    aparean por orden: en el eje X los dos crecen juntos; en el Y el valor
    crece hacia arriba, o sea con ``top`` decreciente, así que la lista de
    valores se da vuelta.

    El apareo es **por cercanía**, no por posición en la lista: el gráfico
    rotula todas las marcas pero sólo dibuja grilla en las intermedias —las de
    los extremos son los ejes, trazados en otro color—, así que las dos listas
    casi nunca tienen la misma longitud. Cada línea se queda con el rótulo más
    cercano, y si ninguno cae dentro de ``TOLERANCIA_APAREO`` la línea se
    descarta en vez de asociarse a la que sobró.

    El desfasaje que esto corrige es real y sistemático: en la pág. 473 los
    rótulos del eje Y están impresos 2.7 pt por encima de su línea de grilla, y
    leerlos como si estuvieran encima daba −7 A donde el gráfico muestra 0.

    Devuelve ``None`` —y el llamador cae a la calibración por rótulos— si no
    quedan al menos tres pares.
    """
    if not grilla or not marcas:
        return None
    clave = "cy" if eje == "y" else "cx"
    px: list[float] = []
    val: list[float] = []
    for g in grilla:
        cerca = min(marcas, key=lambda m: abs(m[clave] - g))
        if abs(cerca[clave] - g) > TOLERANCIA_APAREO:
            continue
        px.append(g)
        val.append(cerca["v"])
    if len(set(val)) != len(val):     # dos líneas con el mismo rótulo: mal apareo
        return None
    return _ajustar(px, val)


# --------------------------------------------------------------------------
# 4. Un gráfico
# --------------------------------------------------------------------------

@dataclass
class Grafico:
    """Un gráfico de ampacidad, ya leído."""
    pagina: int
    lado: str
    familia: str
    calibres: list[str]
    titulo: str = ""
    series: dict[str, list[dict[str, float]]] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)


def _numeros(page, x0: float, x1: float, y0: float, y1: float) -> list[dict]:
    """Palabras que son un número entero, dentro de una ventana de la página."""
    salida = []
    for w in page.extract_words():
        if not re.fullmatch(r"\d{1,4}", w["text"]):
            continue
        cx = (w["x0"] + w["x1"]) / 2.0
        cy = (w["top"] + w["bottom"]) / 2.0
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            salida.append({"v": float(w["text"]), "cx": cx, "cy": cy})
    return salida


def leer_grafico(page, curvas: list[dict], pagina: int, lado: str) -> Grafico | None:
    """Lee un gráfico: calibra los ejes y muestrea cada curva.

    Args:
        page: Página de pdfplumber.
        curvas: Los trazos blancos de ESTE gráfico, ya separados del otro.
        pagina: Índice de página, para trazabilidad.
        lado: ``"izq"`` / ``"der"`` / ``"unico"``.

    Returns:
        El gráfico leído, o ``None`` si no se pudo calibrar.
    """
    x_min = min(c["x0"] for c in curvas)
    x_max = max(c["x1"] for c in curvas)
    y_min = min(c["top"] for c in curvas)
    y_max = max(c["bottom"] for c in curvas)

    # Marcas del eje X: números debajo del gráfico, dentro de su ancho.
    marcas_x = _numeros(page, x_min - 25, x_max + 40, y_max + 2, y_max + 30)
    # Marcas del eje Y: números a la izquierda, dentro de su alto.
    marcas_y = _numeros(page, x_min - 60, x_min - 2, y_min - 35, y_max + 8)

    # **La calibración se ancla en la GRILLA, no en el centro del rótulo.**
    # El centro vertical de un número impreso no cae exactamente sobre su línea
    # de grilla —depende de la fuente y de si el texto tiene descendentes—, y
    # ese desfasaje entra como un sesgo constante en todo el eje: leyendo los
    # rótulos, el fin de curva daba −7 A donde el gráfico muestra 0. Las líneas
    # de grilla sí son geometría exacta. Los rótulos siguen haciendo falta para
    # saber QUÉ vale cada línea; lo que se toma de la grilla es DÓNDE está.
    horiz, vert = _grilla(page, x_min, x_max, y_min, y_max)
    eje_x = _ajustar_con_grilla(vert, marcas_x, "x") or _ajustar(
        [m["cx"] for m in marcas_x], [m["v"] for m in marcas_x]
    )
    eje_y = _ajustar_con_grilla(horiz, marcas_y, "y") or _ajustar(
        [m["cy"] for m in marcas_y], [m["v"] for m in marcas_y]
    )
    if eje_x is None or eje_y is None:
        return None
    if eje_x.r2 < R2_MINIMO or eje_y.r2 < R2_MINIMO:
        return None

    g = Grafico(pagina=pagina, lado=lado, familia="", calibres=[])

    # Curvas de arriba hacia abajo = de mayor a menor corriente = el orden en
    # que la leyenda lista los calibres (2/0 primero).
    for c in sorted(curvas, key=lambda c: c["top"]):
        pts = [
            {
                "temp_f": round(eje_x.valor(x), 1),
                "amps": round(eje_y.valor(y), 1),
            }
            for x, y in _muestrear(c)
        ]
        # La curva se dibuja de izquierda a derecha; si vino al revés se da
        # vuelta, para que la tabla salga siempre en temperatura creciente.
        if len(pts) >= 2 and pts[0]["temp_f"] > pts[-1]["temp_f"]:
            pts.reverse()
        g.series[f"__{len(g.series)}"] = pts

    g.avisos.append(f"R² eje X = {eje_x.r2:.6f}, eje Y = {eje_y.r2:.6f}")
    return g


# --------------------------------------------------------------------------
# 5. Recorrido del PDF
# --------------------------------------------------------------------------

def curvas_de_la_pagina(page) -> list[dict]:
    """Los trazos blancos que son curvas de ampacidad, no muestras de leyenda."""
    return [
        o for o in (page.curves + page.lines)
        if o.get("stroking_color") == COLOR_CURVA
        and not o.get("fill")
        and o["top"] < TOPE_ZONA_GRAFICO
        and (o["x1"] - o["x0"]) >= ANCHO_MINIMO_CURVA
        and len(o.get("pts") or []) >= 2
    ]


def separar_graficos(curvas: list[dict]) -> list[tuple[str, list[dict]]]:
    """Parte los trazos en los gráficos de la página (uno o dos, lado a lado).

    El corte se hace por un hueco horizontal grande entre los comienzos de las
    curvas: en las páginas con dos gráficos los dos bloques arrancan en x muy
    distintos (≈116 y ≈365) y adentro de cada bloque coinciden.
    """
    if not curvas:
        return []
    ordenadas = sorted(curvas, key=lambda c: c["x0"])
    bloques: list[list[dict]] = [[ordenadas[0]]]
    for c in ordenadas[1:]:
        if c["x0"] - bloques[-1][-1]["x0"] > 100.0:
            bloques.append([])
        bloques[-1].append(c)
    if len(bloques) == 1:
        return [("unico", bloques[0])]
    return [(lado, b) for lado, b in zip(("izq", "der", "tercero"), bloques)]


def calibres_de_la_leyenda(page, bloque: list[dict]) -> list[str]:
    """Los calibres que rotula la leyenda de UN gráfico, de arriba hacia abajo.

    **No se leen del texto de la página con una expresión regular.** En la
    pág. 479 los rótulos están compuestos carácter por carácter y con los dos
    gráficos intercalados, así que el texto extraído sale como
    ``"N N o o . . 2 1 / / 0 0 C C ..."`` y cualquier regex lee cualquier cosa.

    Se leen de la **geometría**: cada muestra de color de la leyenda es un
    trazo blanco corto, y su rótulo son los caracteres que están a su derecha,
    a la misma altura. Eso ata cada rótulo a su gráfico sin ambigüedad.

    Args:
        page: Página de pdfplumber.
        bloque: Las curvas de este gráfico, que acotan su zona horizontal.

    Returns:
        Los calibres en orden vertical descendente (el de arriba primero), tal
        como los lista la leyenda. Lista vacía si no se encontró leyenda.
    """
    x0 = min(c["x0"] for c in bloque)
    x1 = max(c["x1"] for c in bloque)
    muestras = [
        l for l in page.lines
        if l.get("stroking_color") == COLOR_CURVA
        and l["top"] < TOPE_ZONA_GRAFICO
        and (l["x1"] - l["x0"]) < ANCHO_MINIMO_CURVA
        and x0 - 20 <= l["x0"] <= x1 + 80
    ]
    salida: list[str] = []
    for m in sorted(muestras, key=lambda l: l["top"]):
        cerca = [
            c for c in page.chars
            if abs((c["top"] + c["bottom"]) / 2 - m["top"]) <= 4.0
            and m["x1"] <= c["x0"] <= m["x1"] + 90
        ]
        texto = "".join(c["text"] for c in sorted(cerca, key=lambda c: c["x0"]))
        hallado = _CALIBRE.search(texto)
        if hallado:
            salida.append(hallado.group(1))
    return salida


def familia_de(pdf, pagina: int, page, lado: str) -> tuple[str, str]:
    """Nombre de familia del cable y título del gráfico, **textuales**.

    La familia sale del encabezado de la página anterior (``"Redalene Cable"``,
    ``"Redahot Cable"``, …), que es donde el catálogo la presenta; el título es
    el que está impreso arriba del gráfico. Los dos se copian tal cual, sin
    normalizar: son la cita.
    """
    anterior = (pdf.pages[pagina - 1].extract_text() or "").split("\n")
    familia = anterior[0].strip() if anterior else ""

    ws = [w for w in page.extract_words() if 88 <= w["top"] <= 104]
    ws.sort(key=lambda w: w["x0"])
    corte = 330.0
    if lado == "der":
        ws = [w for w in ws if w["x0"] >= corte]
    elif lado == "izq":
        ws = [w for w in ws if w["x0"] < corte]
    titulo = " ".join(w["text"] for w in ws).strip()
    # Dos de los gráficos no llevan título propio —el catálogo los deja bajo el
    # encabezado de la página anterior— y a esa altura lo único que hay son los
    # rótulos de la leyenda. Devolver eso como título sería inventarle nombre.
    if "Conductor" in titulo or not titulo:
        titulo = ""
    return familia, titulo


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    pdf = pdfplumber.open(args.pdf)
    graficos: list[Grafico] = []
    problemas: list[str] = []

    for pagina in PAGINAS_AMPACIDAD:
        page = pdf.pages[pagina]
        bloques = separar_graficos(curvas_de_la_pagina(page))

        for lado, bloque in bloques:
            g = leer_grafico(page, bloque, pagina, lado)
            if g is None:
                problemas.append(
                    f"p{pagina} {lado}: no se pudo calibrar los ejes — se descarta"
                )
                continue
            g.familia, titulo = familia_de(pdf, pagina, page, lado)
            g.titulo = titulo
            g.calibres = calibres_de_la_leyenda(page, bloque)
            esperados = len(g.series)
            if len(g.calibres) != esperados:
                problemas.append(
                    f"p{pagina} {lado}: {esperados} curvas pero "
                    f"{len(g.calibres)} calibres en la leyenda — se descarta"
                )
                continue
            g.series = {
                cal: pts for cal, pts in zip(g.calibres, list(g.series.values()))
            }
            graficos.append(g)

    _verificar(graficos, problemas)

    print(f"gráficos leídos: {len(graficos)}")
    for g in graficos:
        print(f"  p{g.pagina} {g.lado:6} [{g.familia}] «{g.titulo}» {g.calibres}")
        for cal, pts in g.series.items():
            print(f"      {cal:4} {pts[0]['temp_f']:6.0f}°F {pts[0]['amps']:6.0f} A"
                  f"  →  {pts[-1]['temp_f']:6.0f}°F {pts[-1]['amps']:6.0f} A")
        for a in g.avisos:
            print(f"      · {a}")
    for p in problemas:
        print("  PROBLEMA:", p)

    if args.out:
        args.out.write_text(
            json.dumps(
                {
                    "_note": (
                        "Ampacidad máxima del conductor en función de la "
                        "temperatura máxima de pozo, por familia de cable y "
                        "calibre. Leída de la capa VECTORIAL del REDA ESP "
                        "Catalog (sin OCR): las curvas están trazadas en blanco "
                        "sobre el fondo del gráfico y los ejes se calibran por "
                        "regresión sobre las líneas de grilla, apareadas con "
                        "los rótulos de marca del propio gráfico. Generado por "
                        "tools/catalog_pipeline/digitize_reda_cable_ampacity.py."
                    ),
                    "_no_extrapolar": (
                        "Cada curva vale sólo entre su primer y su último punto. "
                        "Fuera de ese rango no hay dato: acotar al borde y "
                        "avisar, nunca extender la recta."
                    ),
                    "graficos": [g.__dict__ for g in graficos],
                    "problemas": problemas,
                },
                indent=2, ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print("escrito:", args.out)
    return 0


def _verificar(graficos: list[Grafico], problemas: list[str]) -> None:
    """Controles de plausibilidad sobre lo leído. No corrige: avisa.

    Tres cosas que tienen que cumplirse en cualquier gráfico de ampacidad, y
    que detectan un mal apareo curva↔calibre o un eje mal calibrado:

    1. **Cada curva baja**: más temperatura, menos corriente admisible.
    2. **No se cruzan**: a igual temperatura, el conductor más grueso admite
       más corriente. Si dos curvas se cruzan, se asignaron mal los calibres.
    3. **Empieza en cero grados y termina en cero amperes**, con holgura: es
       cómo están dibujados estos gráficos, y un corrimiento del eje se ve acá.
    """
    orden = ["2/0", "1/0", "1", "2", "4", "6"]
    for g in graficos:
        for cal, pts in g.series.items():
            if pts[0]["amps"] < pts[-1]["amps"]:
                problemas.append(
                    f"p{g.pagina} {g.lado} {cal}: la ampacidad SUBE con la "
                    f"temperatura — curva mal leída"
                )
            if abs(pts[-1]["amps"]) > 8.0:
                g.avisos.append(
                    f"{cal}: la curva termina en {pts[-1]['amps']:.0f} A y no "
                    f"en 0 — posible corrimiento del eje Y"
                )
        presentes = [c for c in orden if c in g.series]
        for grueso, fino in zip(presentes, presentes[1:]):
            if g.series[grueso][0]["amps"] <= g.series[fino][0]["amps"]:
                problemas.append(
                    f"p{g.pagina} {g.lado}: {fino} AWG admite más corriente que "
                    f"{grueso} AWG — calibres mal asignados"
                )


if __name__ == "__main__":
    raise SystemExit(main())
