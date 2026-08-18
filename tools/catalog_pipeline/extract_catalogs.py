"""Extractores de los catálogos de fabricante que viven en TESIS/CATALOGOS.

Un extractor por bloque de datos, todos con la misma disciplina: se lee lo
que el PDF imprime y nada más. Lo que el fabricante no publica queda en
`null` y el motivo se anota en `_source`.

## Motores REDA


El PDF publica las dos frecuencias lado a lado y usa celdas combinadas: la
potencia está centrada verticalmente sobre un grupo de filas de tensión. No
hay líneas de rayado que separen los grupos en toda la página, así que la
asociación se resuelve por **cercanía vertical**: para una celda centrada, la
potencia de su propio grupo siempre está más cerca en *y* que la del grupo
vecino, que queda a media altura de ambos.

Cada fila retenida pasa dos verificaciones físicas independientes derivadas de
la ley V/f constante (par constante) que rige a un motor de inducción:

    V(60 Hz) / V(50 Hz) ≈ 6/5      HP(60 Hz) / HP(50 Hz) ≈ 6/5

Una fila mal emparejada casi nunca satisface las dos a la vez, así que el
filtro es un detector de errores de extracción, no un ajuste de datos. Las
filas que no pasan se descartan y se reportan: no se corrigen a mano.

## Sellos y cable Wood Group, protectores REDA

Tablas de texto plano, se leen con `pdftotext -layout`.

Uso:
    python tools/catalog_pipeline/extract_catalogs.py motores-reda <pdf> [salida]
    python tools/catalog_pipeline/extract_catalogs.py sellos-wg    <pdf> [salida]
    python tools/catalog_pipeline/extract_catalogs.py cable-wg     <pdf> [salida]
    python tools/catalog_pipeline/extract_catalogs.py protectores-reda <pdf> [salida]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pdfplumber

# --------------------------------------------------------------------------
# Diámetro externo por serie. En REDA el número de serie ES el OD en
# centésimas de pulgada; se verifica contra la tabla "Motor Capacity Ranges"
# del propio catálogo (mínimo casing OD), pág. 410.
# --------------------------------------------------------------------------
SERIES_OD_IN = {375: 3.75, 456: 4.56, 540: 5.40, 562: 5.62, 738: 7.38}
SERIES_MIN_CASING_IN = {375: 4.500, 456: 5.500, 540: 7.000, 562: 7.000, 738: 8.625}

NUM = re.compile(r"^\d{1,3}(?:,\d{3})*(?:\.\d+)?$")
PART = re.compile(r"^\d{6,9}$")
LENGTH = re.compile(r"^\d+(?:\.\d+)?$")

TITLES = [
    re.compile(r"^(\d{3})\s+(?:Series\s+|Dominator\*?\s+)?Motors[—-](.+)$"),
    re.compile(r"^(\d{3})\s+Series\s+(Maximus\*?)\s+Motors\s*(?:\(continued\))?$"),
    re.compile(r"^(\d{3})\s+(Maximus\*?\s+ProMotor)[—-](.+)$"),
]

# Etiquetas del encabezado, en el orden en que aparecen de izquierda a derecha.
HEAD = ["Power", "Voltage,", "Power", "Voltage,", "Current,", "Type", "Length,"]
COL = {"hp60": 0, "v60": 1, "hp50": 2, "v50": 3, "amps": 4, "type": 5, "length": 6}

RATIO = 6.0 / 5.0
TOL = 0.035


def _num(text: str) -> float | None:
    return float(text.replace(",", "")) if text and NUM.match(text) else None


def title_of(text: str) -> tuple[int | None, str | None]:
    """Serie y familia del motor, leídas del título de la página."""
    for line in text.splitlines():
        line = line.strip()
        for rx in TITLES:
            m = rx.match(line)
            if not m:
                continue
            groups = list(m.groups())
            family = " ".join(g.strip() for g in groups[1:] if g)
            family = re.sub(r"\s*\(continued\)\s*$", "", family)
            return int(groups[0]), family.replace("*", "").strip()
    return None, None


def column_edges(page) -> tuple[list[float] | None, float | None]:
    """Bordes verticales derivados del encabezado real de cada página.

    No se pueden fijar por constante: las páginas de ProMotor intercalan
    columnas de protector y sensor que corren todo lo que está a la derecha.
    """
    words = page.extract_words()
    header_top = next((w["top"] for w in words if w["text"] == "Current,"), None)
    if header_top is None:
        return None, None
    header = sorted(
        (w for w in words if abs(w["top"] - header_top) < 2), key=lambda w: w["x0"]
    )
    starts, wanted = [], list(HEAD)
    for word in header:
        if wanted and word["text"] == wanted[0]:
            starts.append(word["x0"])
            wanted.pop(0)
    if wanted:
        return None, None
    right = next((w["x0"] for w in header if w["x0"] > starts[-1]), page.width)
    edges = [starts[0] - 8]
    edges += [(a + b) / 2 for a, b in zip(starts, starts[1:])]
    edges.append((starts[-1] + right) / 2)
    return edges, header_top


def _cell(words, edges, name):
    lo, hi = edges[COL[name]], edges[COL[name] + 1]
    return [w for w in words if lo <= w["x0"] < hi]


def parse_page(page) -> list[dict]:
    edges, header_top = column_edges(page)
    if not edges:
        return []
    words = [w for w in page.extract_words() if w["top"] > header_top + 8]
    hp60s = [(w["top"], _num(w["text"])) for w in _cell(words, edges, "hp60")
             if _num(w["text"])]
    hp50s = [(w["top"], _num(w["text"])) for w in _cell(words, edges, "hp50")
             if _num(w["text"])]
    if not hp60s:
        return []

    def nearest(pairs, y):
        return min(pairs, key=lambda p: abs(p[0] - y))[1] if pairs else None

    volt_words = sorted(
        (w for w in _cell(words, edges, "v60") if _num(w["text"])),
        key=lambda w: w["top"],
    )
    lengths = sorted(
        ((w["top"], float(w["text"])) for w in _cell(words, edges, "length")
         if LENGTH.match(w["text"])),
        key=lambda pair: pair[0],
    )

    rows = []
    for position, word in enumerate(volt_words):
        line = [w for w in words if abs(w["top"] - word["top"]) < 3]
        first = lambda name: next(                        # noqa: E731
            (_num(w["text"]) for w in _cell(line, edges, name) if _num(w["text"])),
            None,
        )
        # La longitud vive en las filas de variante mecánica (UT/CT), que están
        # debajo de la fila eléctrica y no comparten su *y*. Se toma la primera
        # variante antes de que empiece la fila eléctrica siguiente.
        ceiling = (volt_words[position + 1]["top"]
                   if position + 1 < len(volt_words) else float("inf"))
        length = next((value for top, value in lengths
                       if word["top"] - 3 <= top < ceiling - 3), None)
        rows.append({
            "hp_60hz": nearest(hp60s, word["top"]),
            "volts_60hz": _num(word["text"]),
            "hp_50hz": nearest(hp50s, word["top"]),
            "volts_50hz": first("v50"),
            "amps": first("amps"),
            "length_ft": length,
        })
    return rows


def valid(row: dict) -> bool:
    """Las dos verificaciones V/f. Una fila mal emparejada falla al menos una."""
    needed = ("hp_60hz", "hp_50hz", "volts_60hz", "volts_50hz", "amps")
    if any(not row.get(k) for k in needed):
        return False
    return all(
        abs(row[a] / row[b] - RATIO) <= TOL
        for a, b in (("volts_60hz", "volts_50hz"), ("hp_60hz", "hp_50hz"))
    )


def extract(pdf_path: Path) -> tuple[list[dict], dict]:
    raw = []
    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if "Frequency, 60 Hz" not in text or "Capacity Ranges" in text:
                continue
            series, family = title_of(text)
            if not series:
                continue
            for row in parse_page(page):
                raw.append({"series": series, "family": family,
                            "page": index + 1, **row})

    kept, seen = [], set()
    for row in raw:
        if not valid(row):
            continue
        key = (row["series"], row["family"], row["hp_60hz"], row["volts_60hz"])
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)

    kept.sort(key=lambda r: (r["series"], r["family"], r["hp_60hz"], r["volts_60hz"]))
    stats = {"filas_crudas": len(raw), "descartadas_por_verificacion":
             sum(1 for r in raw if not valid(r)), "duplicadas":
             len(raw) - sum(1 for r in raw if not valid(r)) - len(kept),
             "retenidas": len(kept)}
    return kept, stats


def to_catalog(rows: list[dict], source_pdf: str) -> list[dict]:
    """Convierte al esquema de `bes/catalogs/motors.json`."""
    motors = []
    for row in rows:
        series, family = row["series"], row["family"]
        hp, volts = row["hp_60hz"], row["volts_60hz"]
        tag = re.sub(r"[^A-Z0-9]+", "-", family.upper()).strip("-")
        motors.append({
            "manufacturer": "REDA",
            "series": str(series),
            "model": f"REDA-{series}-{tag}-{hp:g}HP-{volts:g}V",
            "hp_rating": hp,
            "voltage": volts,
            "amperage": row["amps"],
            "length_ft": row["length_ft"],
            "max_temp_f": None,
            "od_inches": SERIES_OD_IN[series],
            "frequency_hz": 60,
            "hp_rating_50hz": row["hp_50hz"],
            "voltage_50hz": row["volts_50hz"],
            "min_casing_od_in": SERIES_MIN_CASING_IN[series],
            "_source": (
                f"{source_pdf} p.{row['page']}, tabla «{series} {family}». "
                "Placa a 60 Hz y a 50 Hz publicadas por el fabricante; amperaje "
                "único para ambas frecuencias (V/f constante). OD = número de "
                "serie en centésimas de pulgada, verificado contra la tabla "
                "Motor Capacity Ranges. El catálogo 2005 NO publica temperatura "
                "máxima de bobinado por modelo: max_temp_f queda en null."
            ),
        })
    return motors


# ==========================================================================
# Sellos Wood Group  ·  Seals.pdf
# ==========================================================================
# El PDF no publica capacidad de empuje como número: la da en cuatro gráficos
# (empuje vs. temperatura de fondo, para estándar y alta carga, a 50 y 60 Hz).
# Por eso `thrust_capacity_lbs` sale en null. Tampoco publica temperatura
# máxima por modelo: la tabla de elastómeros es por material de bolsa (HSN
# 250 °F, Viton 300 °F, Aflas 350 °F) y el modelo no dice cuál trae.

_WG_SERIES = re.compile(r"^(\d{3}) Series\b")
_WG_ROW = re.compile(
    r"^(?P<desc>[A-Z][A-Z0-9 ./'\"\-]*?)\s+"
    r"(?P<ft>\d+\.\d+)\s+(?P<m>\d+\.\d+)\s+"
    r"(?P<lbs>\d+(?:\.\d+)?)\s+(?P<kgs>\d+(?:\.\d+)?)\s+"
    r"(?P<pn>\d{6,})(?:\s+(?P<pn_ar>\d{6,}))?\s*$"
)
_WG_SHAFT = re.compile(r"SHAFT LIMIT\s+STANDARD\s+(\d+)\s*HP")
_WG_SHAFT_HS = re.compile(r"HIGH STRENGTH\s+(\d+)\s*HP")
_WG_HOUSING_OD = re.compile(r"HOUSING DIAMETER\s+(\d+\.\d+)\s*[”\"]")
_WG_SHAFT_OD = re.compile(r"SHAFT DIAMETER\s+(\d+\.\d+)\s*[”\"]")


def _seal_type(description: str) -> str:
    upper = description.upper()
    if "DOUBLE BAG" in upper or "DBG" in upper:
        return "double_bag"
    if "BAG" in upper or "SBG" in upper:
        return "bag"
    return "labyrinth"


def extract_wg_seals(text: str, source: str) -> list[dict]:
    """Protectores Wood Group, agrupados por serie con su ficha mecánica."""
    blocks: dict[str, dict] = {}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        series = _WG_SERIES.match(stripped)
        if series:
            current = series.group(1)
            blocks.setdefault(current, {"rows": [], "spec": {}})
            continue
        if current is None:
            continue
        row = _WG_ROW.match(stripped)
        if row:
            blocks[current]["rows"].append(row.groupdict())
            continue
        for rx, key in ((_WG_SHAFT, "hp_std"), (_WG_SHAFT_HS, "hp_hs"),
                        (_WG_HOUSING_OD, "od"), (_WG_SHAFT_OD, "shaft_od")):
            found = rx.search(stripped)
            # La ficha de ingeniería de una serie aparece DESPUÉS de sus filas,
            # así que se asigna a la serie abierta y nunca se pisa.
            if found and key not in blocks[current]["spec"]:
                blocks[current]["spec"][key] = float(found.group(1))

    seals = []
    for series, block in sorted(blocks.items()):
        spec = block["spec"]
        for row in block["rows"]:
            description = " ".join(row["desc"].split())
            seals.append({
                "manufacturer": "Wood Group ESP",
                "series": series,
                "model": description,
                "type": _seal_type(description),
                "compatible_motor_series": [series],
                "od_inches": spec.get("od"),
                "length_ft": float(row["ft"]),
                "weight_lbs": float(row["lbs"]),
                "shaft_diameter_in": spec.get("shaft_od"),
                "thrust_capacity_lbs": None,
                "max_temp_f": None,
                "shaft_hp_standard": spec.get("hp_std"),
                "shaft_hp_high_strength": spec.get("hp_hs"),
                "part_number": row["pn"],
                "part_number_abrasion_resistant": row["pn_ar"],
                "_source": (
                    f"{source}, sección SEAL SECTION, serie {series}. Longitud, "
                    "peso, part number y límites de eje son los impresos. El PDF "
                    "NO publica capacidad de empuje como número (está en los "
                    "gráficos de empuje vs. BHT) ni temperatura máxima por "
                    "modelo: ambos quedan en null."
                ),
            })
    return seals


# ==========================================================================
# Cable Wood Group  ·  Cable-Woodgroup.pdf
# ==========================================================================
# Sólo se leen las tablas de cable de potencia, que son las que traen calibre
# y dimensiones. El catálogo NO publica ampacidad ni caída de tensión, así que
# esos campos quedan en null: sin ellos `select_cable` no puede usarlos, y es
# preferible a inventarlos.

_WG_POWER_HEADER = re.compile(r"POWERLINE\s+(\d+)\s+(\d+)KV\s+(ROUND|FLAT)\s+CABLE")
_WG_POWER_ROW = re.compile(
    r"^\s*(?P<size>1/0|2/0|[1-9])\s+(?P<constr>[A-Za-z/ ]+?)\s+"
    r"(?P<ins>[A-Z]{2,})\s+(?P<jacket>[A-Z]{2,})\s+(?P<armor>[A-Za-z]+)\s+"
    r"(?P<pn>\d{6,})\s+(?P<lbft>\d+\.\d+)\s+(?P<inches>\d+\.\d+)"
)


def extract_wg_cables(text: str, source: str) -> list[dict]:
    cables, family, kv = [], None, None
    for line in text.splitlines():
        header = _WG_POWER_HEADER.search(line)
        if header:
            family, kv = f"Powerline {header.group(1)}", int(header.group(2))
            continue
        row = _WG_POWER_ROW.match(line)
        if not row or family is None:
            continue
        cables.append({
            "manufacturer": "Wood Group ESP",
            "type": family,
            "conductor": "CU",
            "size": f"#{row['size']}",
            "shape": "round",
            "rated_kv": kv,
            "insulation": row["ins"],
            "jacket": row["jacket"],
            "armor": row["armor"].strip(),
            "outside_diameter_in": float(row["inches"]),
            "weight_lb_per_ft": float(row["lbft"]),
            "max_amps": None,
            "max_temp_f": None,
            "voltage_drop_v_per_amp_per_1000ft": None,
            "part_number": row["pn"],
            "_source": (
                f"{source}, sección POWER CABLE, {family} {kv} kV. Calibre, "
                "diámetro, peso y part number son los impresos. El catálogo NO "
                "publica ampacidad, temperatura máxima ni caída de tensión: "
                "quedan en null y el cable no participa de la selección "
                "automática hasta conseguir esos datos."
            ),
        })
    return cables


# ==========================================================================
# Protectores REDA  ·  sección «Modular Protector Configurations»
# ==========================================================================
_REDA_PROT_SERIES = re.compile(
    r"^(\d{3}) Series(?: Modular)? \(Bolts to "
    r"(\d{3})(?:\s+(?:and|or|/)\s+(\d{3}))? Series Motors\)"
)
_REDA_PROT_ROW = re.compile(
    r"^(?P<desc>[A-Z0-9][A-Z0-9\-]*)\s+"
    r"(?P<ft>\d+\.\d+)\s+\[(?P<m>[\d.]+)\]\s+"
    r"(?P<lbs>[\d,]+)\s+\[(?P<kg>[\d.,]+)\]\s+"
    r"(?P<pn>[A-Z0-9]{6,}|tba\S*)(?:\s+(?P<pn2>[A-Z0-9]{6,}|tba\S*))?\s*$"
)

# Temperatura límite del elastómero, tabla «Elastomer Application Guidelines».
_REDA_ELASTOMER_F = {"HSN": 300.0, "VITON": 351.0, "AFLAS": 399.0}

_PROT_SUFFIXES = {"HL", "HSS", "HTM", "AFL", "PF", "CR"}


def _reda_protector_type(description: str) -> str:
    """Tipo de cámara, leído del código según la nomenclatura del catálogo.

    Un código modular alterna cámara y conexión: L = laberinto, B = bolsa de
    elastómero, M = fuelle metálico; S = serie, P = paralelo. Así «LSB» es
    laberinto + bolsa en serie y «LSBPB» agrega una segunda bolsa en paralelo.
    Los sufijos (-HL alta carga, -HSS eje reforzado, -HTM alta temperatura)
    no describen la cámara.
    """
    parts = [p for p in description.split("-") if p not in _PROT_SUFFIXES]
    base = parts[0] if parts else description
    if base == "66L":
        return "labyrinth"
    if base.startswith("SB") or (len(parts) > 1 and parts[-1].startswith("SB")):
        return "bag"
    chambers = base[0::2]                       # posiciones pares = cámaras
    if "M" in chambers:
        return "metal_bellows"
    bags = chambers.count("B")
    return "double_bag" if bags >= 2 else "bag" if bags == 1 else "labyrinth"


def extract_reda_protectors(text: str, source: str) -> list[dict]:
    """Sólo la sección «Modular Protector Configurations».

    El acotado importa: el patrón de fila —descripción, longitud [m], peso [kg],
    dos part numbers— es el mismo que usan las tablas de motores y de bases, así
    que sin cortar por sección el extractor se lleva puesto medio catálogo.
    """
    # Se filtra por página (pdftotext separa con form-feed) en vez de por
    # marcador de sección: el pie de página no aparece en todas y la sección
    # terminaba desbordándose sobre las tablas de motores.
    pages = [p for p in text.split("\f")
             if "Modular Protector Configurations" in p or "Series Motors)" in p]

    protectors: list[dict] = []
    series: str | None = None
    motor_series: list[str] = []
    for line in "\n".join(pages).splitlines():
        stripped = line.strip()
        header = _REDA_PROT_SERIES.match(stripped)
        if header:
            series = header.group(1)
            motor_series = [g for g in header.groups()[1:] if g]
            continue
        row = _REDA_PROT_ROW.match(stripped)
        if not row or series is None:
            continue
        description = row["desc"]
        protectors.append({
            "manufacturer": "REDA",
            "series": series,
            "model": f"REDA-{series}-{description}",
            "type": _reda_protector_type(description),
            # El catálogo dice explícitamente a qué motores atornilla: no hay
            # que inferir compatibilidad por diámetro.
            "compatible_motor_series": motor_series,
            "od_inches": SERIES_OD_IN.get(int(series)),
            "length_ft": float(row["ft"]),
            "weight_lbs": float(row["lbs"].replace(",", "")),
            "thrust_capacity_lbs": None,
            "max_temp_f": None,
            "high_load_bearing": "HL" in description,
            "high_strength_shaft": "HSS" in description,
            "part_number": None if str(row["pn"]).startswith("tba") else row["pn"],
            "_source": (
                f"{source}, «Modular Protector Configurations», serie {series} "
                f"(atornilla a motores serie {', '.join(motor_series)}). "
                "Longitud, peso y part number impresos. El catálogo NO publica "
                "capacidad de empuje ni temperatura por modelo: la temperatura "
                "depende del elastómero de la bolsa (HSN 300 °F, Viton 351 °F, "
                "Aflas 399 °F) y el modelo no lo declara."
            ),
        })
    return protectors


# ==========================================================================
EXTRACTORS = {
    "sellos-wg": ("seals", extract_wg_seals),
    "cable-wg": ("cables", extract_wg_cables),
    "protectores-reda": ("seals", extract_reda_protectors),
}

# Extractores que reciben la ruta al PDF en vez del texto plano.
PDF_BASED: set[str] = set()


def _pdftotext(pdf_path: Path) -> str:
    import subprocess
    return subprocess.run(["pdftotext", "-layout", str(pdf_path), "-"],
                          capture_output=True, text=True, check=True).stdout


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    what, pdf_path = sys.argv[1], Path(sys.argv[2])
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(f"{what}.json")

    if what == "motores-reda":
        rows, stats = extract(pdf_path)
        records, key = to_catalog(rows, pdf_path.name), "motors"
        for name, value in stats.items():
            print(f"  {name:<32} {value:>6}")
    elif what in EXTRACTORS:
        key, function = EXTRACTORS[what]
        # La mayoría de los extractores trabajan sobre el texto plano del PDF;
        # los listados en PDF_BASED necesitan el PDF entero porque usan la
        # geometría de la página (coordenadas, no solo el texto).
        if what in PDF_BASED:
            records = function(pdf_path, pdf_path.name)
        else:
            records = function(_pdftotext(pdf_path), pdf_path.name)
    else:
        sys.exit(f"no sé extraer «{what}». Opciones: motores-reda, "
                 + ", ".join(EXTRACTORS))

    out_path.write_text(json.dumps({key: records}, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(f"  {len(records)} registros -> {out_path}\n")
    groups: dict[str, int] = {}
    for record in records:
        groups[str(record.get("series", record.get("type", "?")))] = (
            groups.get(str(record.get("series", record.get("type", "?"))), 0) + 1)
    for name, count in sorted(groups.items()):
        print(f"    {name:<28} {count:>4}")




# ==========================================================================
# Transformadores y tableros Wood Group
# ==========================================================================
_WG_TRAFO_KIND = re.compile(r"^([A-Z][A-Z /–\-0-9]{6,})\s*$")
_WG_TRAFO_ROW = re.compile(
    r"^\s*(?P<kva>\d+(?:\.\d+)?)\s+(?P<primary>\d{3,4})\s+"
    r"(?P<sec_lo>[\d,]+)\s*[–-]\s*(?P<sec_hi>[\d,]+)\s+(?P<conn>DELTA|WYE)\b"
)


def extract_wg_transformers(text: str, source: str) -> list[dict]:
    """Transformadores: kVA, tensión primaria y rango secundario por conexión."""
    records, kind = [], "TRANSFORMER"
    for line in text.splitlines():
        title = _WG_TRAFO_KIND.match(line.strip())
        if title and "TRANSFORMER" in title.group(1):
            kind = " ".join(title.group(1).split())
            continue
        row = _WG_TRAFO_ROW.match(line)
        if not row:
            continue
        records.append({
            "manufacturer": "Wood Group ESP",
            "type": kind,
            "kva": float(row["kva"]),
            "primary_volts": float(row["primary"]),
            "secondary_volts_min": float(row["sec_lo"].replace(",", "")),
            "secondary_volts_max": float(row["sec_hi"].replace(",", "")),
            "connection": row["conn"].lower(),
            "_source": f"{source}, sección «{kind}». Valores impresos.",
        })
    return records


_WG_SWBD = re.compile(r"^SWITCHBOARD,\s*(?P<desc>.+?)\s+(?P<pn>\d{6,})\s*$")
# La clase de tensión está impresa una sola vez, centrada sobre su grupo de
# fusibles, y las filas arrastran texto de la columna vecina: no se puede
# anclar al fin de línea ni exigir la tensión en cada fila.
_WG_FUSE = re.compile(r"^\s*(?P<volts>\d{4})?\s*(?P<amps>\d{2,3})\s+(?P<pn>13\d{4})\b")
_SQRT3 = 3 ** 0.5


def extract_wg_switchboards(text: str, source: str) -> list[dict]:
    """Tableros de superficie, con el amperaje que habilitan sus fusibles.

    El catálogo publica tres tableros por clase de tensión y una tabla de
    fusibles por tensión y amperaje. La potencia aparente NO está impresa: se
    calcula con kVA = √3·V·A/1000, que es la definición, y queda anotado.
    """
    boards, fuses = [], {}
    volts = None
    for line in text.splitlines():
        board = _WG_SWBD.match(line.strip())
        if board:
            boards.append((board["desc"], board["pn"]))
            continue
        fuse = _WG_FUSE.match(line)
        if fuse:
            if fuse["volts"]:
                volts = float(fuse["volts"])
            if volts:
                fuses.setdefault(volts, []).append(float(fuse["amps"]))

    records = []
    for description, part in boards:
        rango = re.search(r"(\d{3,4})\s*[–-]\s*(\d{3,4})", description)
        hi = float(rango.group(2)) if rango else float(
            re.search(r"(\d{3,4})", description).group(1))
        lo = float(rango.group(1)) if rango else 0.0
        amps_pool = [a for v, lista in fuses.items() if lo <= v <= hi for a in lista]
        max_amps = max(amps_pool) if amps_pool else None
        records.append({
            "manufacturer": "Wood Group ESP",
            "model": f"SWITCHBOARD {description}",
            "type": "switchboard",
            "min_voltage": lo, "max_voltage": hi,
            "max_amps": max_amps,
            "max_kva": (round(_SQRT3 * hi * max_amps / 1000.0, 1)
                        if max_amps else None),
            "part_number": part,
            "_source": (
                f"{source}, sección SWITCHBOARDS. Tensión y part number "
                "impresos; el amperaje es el mayor fusible que el catálogo "
                "ofrece para esa clase de tensión. max_kva NO está impreso: se "
                "calcula con kVA = raiz(3)*V*A/1000, que es la definición."
            ),
        })
    return records


EXTRACTORS["trafos-wg"] = ("transformers", extract_wg_transformers)
EXTRACTORS["tableros-wg"] = ("controllers", extract_wg_switchboards)




# ==========================================================================
# Carcasas de bomba Wood Group  ·  «Curvas BOMBAS Woodgroup.pdf»
# ==========================================================================
# Estas tablas SÍ son texto, a diferencia de las páginas de curva del mismo
# PDF, donde hasta los números de los ejes están dibujados.
_WG_PUMP_TITLE = re.compile(r"^([A-Z]{1,3}-\d{2,4}[A-Z]?)\s+PUMP\s*$")
_WG_PUMP_SERIES = re.compile(r"^(\d{3})\s+Series\s*$")
_WG_HOUSING_ROW = re.compile(
    r"^\s*(?P<hsg>\d{1,2})\s+(?P<ft>\d+\.\d+)\s+(?P<m>\d+\.\d+)\s+"
    r"(?P<lbs>\d+)\s+(?P<kg>\d+\.\d+)\s+(?P<stgs>\d{1,4})\s+(?P<pn>\d{5,})"
)


def extract_wg_pump_housings(text: str, source: str) -> list[dict]:
    records: list[dict] = []
    model = series = None
    for line in text.splitlines():
        stripped = line.strip()
        title = _WG_PUMP_TITLE.match(stripped)
        if title:
            model, series = title.group(1), None
            continue
        serie = _WG_PUMP_SERIES.match(stripped)
        if serie and model:
            series = serie.group(1)
            continue
        row = _WG_HOUSING_ROW.match(line)
        if row and model:
            records.append({
                "model": model, "series": series,
                "code": row["hsg"], "length_ft": float(row["ft"]),
                "weight_lbs": float(row["lbs"]), "stages": int(row["stgs"]),
                "part_number": row["pn"],
                "_source": f"{source}, tabla «{model} PUMP».",
            })
    return records


EXTRACTORS["carcasas-wg"] = ("housings", extract_wg_pump_housings)


# ==========================================================================
# Motores Centrilift / Baker Hughes
# ==========================================================================
#
# «Baker Hughes Technical Catalog — Artificial Lift ESP» (nov-2019), sección 2,
# páginas 199-211. A diferencia del catálogo REDA, acá no hay celdas combinadas:
# cada fila de la tabla es una fila de texto completa y autocontenida:
#
#     SIZE   HP        VOLT/AMPS        LENGTH      WEIGHT
#            60HZ 50HZ 60HZ     50HZ    FT.   M.    LBS. KG.
#             44   37  480/59   400/59  7.0   2.13  345  157
#
# Cada fila retenida pasa la misma verificación física que el extractor REDA,
# la ley V/f constante del motor de inducción:
#
#     V(60 Hz) / V(50 Hz) ≈ 6/5      HP(60 Hz) / HP(50 Hz) ≈ 6/5
#
# No es un ajuste de datos: es un detector de errores de lectura. Una fila mal
# leída rara vez satisface las dos relaciones a la vez. Las que no pasan se
# descartan y se informan; no se corrigen a mano.
#
# El amperaje es el mismo en ambas frecuencias (el catálogo lo publica así:
# a par constante la corriente no cambia), y eso también se verifica.
# --------------------------------------------------------------------------

# En Centrilift el número de serie ES el OD en centésimas de pulgada.
_BAKER_SERIES_OD_IN = {375: 3.75, 450: 4.50, 562: 5.62, 725: 7.25, 880: 8.80}

# Una fila de motor: HP60 HP50 V60/A60 V50/A50 largo_ft largo_m peso_lb peso_kg
_BAKER_MOTOR_ROW = re.compile(
    r"^\s*(?P<hp60>\d+)\s+(?P<hp50>\d+)\s+"
    r"(?P<v60>\d+)/(?P<a60>\d+)\s+(?P<v50>\d+)/(?P<a50>\d+)\s+"
    r"(?P<ft>[\d.]+)\s+(?P<m>[\d.]+)\s+(?P<lbs>\d+)\s+(?P<kg>\d+)\s*$"
)

# Título de página: «450 Series SP Motors», «725 Series HMI Motors (cont.)»…
_BAKER_MOTOR_TITLE = re.compile(r"^(?P<series>\d{3})\b")

# El OD impreso en el encabezado de la tabla, para contrastar con la serie.
_BAKER_OD_HEADER = re.compile(r"(?P<inch>[\d.]+)\s*(?:INCH|in\.)\s*\(\s*(?P<mm>[\d.]+)\s*(?:MM|mm)\s*\)\s*O\.?D\.?", re.I)

# Fila de frecuencias, justo debajo de «SIZE HP VOLT/AMPS …»:
#   «60 HZ 50 HZ 60 HZ 50 HZ FT. M. LBS. KG.»   (o 120/100 en los de imán
#   permanente, que giran al doble de velocidad accionados por variador)
_BAKER_FREQ_ROW = re.compile(r"^\s*(?P<f1>\d+)\s*HZ\s+(?P<f2>\d+)\s*HZ\b", re.I)

# Construcción de una, dos o tres piezas. OJO: no es un atributo de la página
# sino un rótulo que parte la página en sub-tablas. La 199, por ejemplo, trae
# las tres construcciones una debajo de la otra separadas por estos rótulos, así
# que hay que ir arrastrando el estado línea por línea y no buscarlo de una vez
# en toda la hoja: eso etiquetaría mal a las filas de las sub-tablas siguientes.
_BAKER_PIECES = re.compile(r"\b(One|Two|Three)[-\s]Piece\b", re.I)
_BAKER_PIECE_CODE = {"ONE": "1P", "TWO": "2P", "THREE": "3P"}

# Marcas que cierran la designación del modelo dentro de su línea.
_BAKER_DESIG_CUT = re.compile(r"\s*\(|\s+Motors?\b|\s+\d+\.\d+\s*(?:in\.|INCH)", re.I)
_BAKER_DESIG_LEAD = re.compile(r"^\d{3}\s+Series\s+|^\d{3}(?=[A-Z])|^\d{3}\s+", re.I)


def _baker_designation(line: str) -> str:
    """Designación del modelo a partir de la línea que precede al encabezado.

    Ejemplos reales del catálogo::

        «450SP Motors (Motors Below are One-Piece Construction) 4.50 INCH…» -> SP
        «562 Series MXPY»                                                  -> MXPY
        «HMI-VC Motors (Motors Below are Two-Piece Construction)…»         -> HMI-VC
        «375 Magnefficient PMM 3.75 in. (95.3 mm) O.D.»                    -> MAGNEFFICIENT-PMM
    """
    cut = _BAKER_DESIG_CUT.search(line)
    texto = line[: cut.start()] if cut else line
    texto = _BAKER_DESIG_LEAD.sub("", texto.strip()).strip()
    return re.sub(r"\s+", "-", texto).upper() or "STD"


def _vf_ratio_ok(a: float, b: float, tolerance: float = 0.035) -> bool:
    """¿La relación a/b se parece a 6/5, dentro de la tolerancia?"""
    if b <= 0:
        return False
    return abs((a / b) / 1.2 - 1.0) <= tolerance


def extract_baker_motors(pdf_path: Path, source: str) -> list[dict]:
    """Motores Centrilift del catálogo técnico Baker Hughes 2019.

    Recorre las páginas de la sección «MOTORS», lee cada fila de la tabla y la
    valida contra la ley V/f. Devuelve los registros en el formato del catálogo
    de la app, con `_source` apuntando a la página exacta.
    """
    records: list[dict] = []
    descartadas: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            lines = text.split("\n")
            if not lines:
                continue

            # --- localizar el encabezado de la tabla -----------------------
            # El bloque de título va desde la primera línea hasta «SIZE …».
            # Hay que mirarlo entero: en varias páginas la palabra «Motor» no
            # está en la primera línea sino en la segunda o la tercera.
            try:
                k = next(j for j, l in enumerate(lines)
                         if l.strip().upper().startswith("SIZE"))
            except StopIteration:
                continue

            encabezado = lines[:k]
            if not encabezado or "Motor" not in " ".join(encabezado):
                continue

            title_match = _BAKER_MOTOR_TITLE.match(encabezado[0].strip())
            if not title_match:
                continue
            series = int(title_match.group("series"))
            if series not in _BAKER_SERIES_OD_IN:
                continue

            # --- frecuencias de la tabla -----------------------------------
            # Casi todas son 60/50 Hz; las de imán permanente son 120/100 Hz.
            freq_match = _BAKER_FREQ_ROW.match(lines[k + 1]) if k + 1 < len(lines) else None
            if not freq_match:
                continue
            f_nom, f_alt = float(freq_match["f1"]), float(freq_match["f2"])

            # --- designación y construcción --------------------------------
            # La línea inmediatamente anterior a «SIZE» es la que nombra el
            # modelo; si es sólo un rótulo suelto se retrocede una más.
            desig_line = encabezado[-1].strip()
            if desig_line.upper() in ("MXP DIMENSIONS", "") and len(encabezado) > 1:
                desig_line = encabezado[-2].strip()
            designation = _baker_designation(desig_line)

            # OD: se prefiere el impreso en la tabla; la serie es el respaldo.
            od_in = _BAKER_SERIES_OD_IN[series]
            od_header = _BAKER_OD_HEADER.search(text)
            if od_header:
                od_in = float(od_header.group("inch"))

            page_no = index + 1
            pieces = None   # se actualiza al cruzar cada rótulo de construcción
            for line in lines:
                marca = _BAKER_PIECES.search(line)
                if marca:
                    pieces = _BAKER_PIECE_CODE[marca.group(1).upper()]

                row = _BAKER_MOTOR_ROW.match(line)
                if not row:
                    continue

                hp60, hp50 = float(row["hp60"]), float(row["hp50"])
                v60, v50 = float(row["v60"]), float(row["v50"])
                a60, a50 = float(row["a60"]), float(row["a50"])

                # --- verificaciones físicas (ley V/f constante) -------------
                if not _vf_ratio_ok(v60, v50):
                    descartadas.append(f"p{page_no} V60/V50={v60}/{v50}: {line.strip()}")
                    continue
                if not _vf_ratio_ok(hp60, hp50, tolerance=0.06):
                    descartadas.append(f"p{page_no} HP60/HP50={hp60}/{hp50}: {line.strip()}")
                    continue
                if a60 != a50:
                    descartadas.append(f"p{page_no} amperajes distintos {a60}≠{a50}: {line.strip()}")
                    continue

                partes = f"-{pieces}" if pieces else ""
                model = (f"CENTRILIFT-{series}-{designation}{partes}"
                         f"-{int(hp60)}HP-{int(v60)}V").upper()

                # Los campos «_50hz» sólo se llenan si la segunda columna es
                # realmente 50 Hz. En los motores de imán permanente es 100 Hz
                # y meterla ahí sería mentir sobre lo que publica el catálogo.
                es_50 = f_alt == 50.0
                records.append({
                    "manufacturer": "Centrilift",
                    "series": series,
                    "model": model,
                    "hp_rating": hp60,
                    "voltage": v60,
                    "amperage": a60,
                    "length_ft": float(row["ft"]),
                    "weight_lbs": float(row["lbs"]),
                    "max_temp_f": None,
                    "od_inches": od_in,
                    "frequency_hz": f_nom,
                    "hp_rating_50hz": hp50 if es_50 else None,
                    "voltage_50hz": v50 if es_50 else None,
                    "alt_frequency_hz": f_alt,
                    "hp_rating_alt": hp50,
                    "voltage_alt": v50,
                    "min_casing_od_in": None,
                    "_source": (
                        f"{source} p.{page_no}, tabla «{encabezado[0].strip()}"
                        f" / {desig_line}». Placa a {int(f_nom)} Hz y a "
                        f"{int(f_alt)} Hz publicadas por el fabricante; amperaje "
                        f"idéntico en ambas frecuencias según el catálogo. "
                        f"Temperatura máxima y casing mínimo: el catálogo no los "
                        f"publica en esta tabla, quedan en null."
                    ),
                })

    if descartadas:
        print(f"  filas descartadas por no pasar la ley V/f: {len(descartadas)}")
        for d in descartadas[:10]:
            print(f"    {d}")

    return records


EXTRACTORS["motores-baker"] = ("motors", extract_baker_motors)
PDF_BASED.add("motores-baker")


# ==========================================================================
# Sellos (protectores) Centrilift / Baker Hughes
# ==========================================================================
#
# «Baker Hughes Technical Catalog — Artificial Lift ESP» (nov-2019), pp.193-197.
# Cada página cubre una serie de sello y dice para qué serie de motor sirve:
#
#     «400 Series Seals for 450 Series Motors»
#     MODEL   DESCRIPTION                                 LENGTH     WEIGHT
#                                                         FT.  M.    LBS. KG.
#     FSFB3   Single seal, two chambers, B/L, ...         4.4  1.35  123  56
#
# Dos complicaciones del PDF:
#   1. La descripción se corta en varias líneas y las medidas pueden quedar en
#      una línea suelta en el medio; hay que arrastrarlas al modelo abierto.
#   2. Algunos modelos (la familia DURA+) se listan sin medidas. Se cargan
#      igual, con longitud y peso en null: existen en el catálogo aunque no
#      publiquen dimensiones.
#
# Cada fila con medidas se verifica convirtiendo entre los dos sistemas de
# unidades que el propio catálogo imprime lado a lado.
# --------------------------------------------------------------------------

# El titulo no es uniforme: «400 Series Seals for 450 Series Motors», pero
# tambien «513 Seals for 562 Motors» y «675 & 875 Series Seals for 562, 725 & 880».
_BAKER_SEAL_TITLE = re.compile(
    r"^(?P<serie>\d{3})(?:\s*&\s*\d{3})?\s+(?:Series\s+)?Seals?\s+for\s+"
    r"(?P<motores>[\d,\s&]+?)\s*(?:Series\s+)?(?:Motors|$)",
    re.I,
)
# Modelo: FSFB3, FSB3 UT, DURA+L/2B, DSFC4…
_BAKER_SEAL_MODEL = re.compile(r"^(?P<model>[A-Z][A-Z0-9+/.\-]{1,14}(?:\s(?:UT|LT))?)\s+(?P<resto>\S.*)$")
_BAKER_SEAL_DIMS = re.compile(r"(?P<ft>\d+\.?\d*)\s+(?P<m>\d+\.\d+)\s+(?P<lbs>\d+)\s+(?P<kg>\d+)\s*$")
_BAKER_SEAL_ONLY_DIMS = re.compile(r"^\s*(?P<ft>\d+\.?\d*)\s+(?P<m>\d+\.\d+)\s+(?P<lbs>\d+)\s+(?P<kg>\d+)\s*$")
_BAKER_SEAL_STOP = re.compile(r"^(Standard construction|For special|For shipping|All lengths|\d+ of \d+)", re.I)


def _baker_seal_type(descripcion: str) -> str:
    """Clasifica el protector por cómo aísla el aceite del motor."""
    d = descripcion.upper()
    tiene_bolsa = "BAG" in d or "BLADDER" in d or "/B" in d or "ELASTOMER" in d
    tiene_lab = "LAB" in d or "LABYRINTH" in d or "/L" in d
    if tiene_bolsa and tiene_lab:
        return "combination"
    if tiene_bolsa:
        return "bag"
    if tiene_lab:
        return "labyrinth"
    return "unknown"


def extract_baker_seals(pdf_path: Path, source: str) -> list[dict]:
    """Protectores Centrilift del catálogo técnico Baker Hughes 2019."""
    records: list[dict] = []
    descartadas: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages):
            lines = (page.extract_text() or "").split("\n")
            if not lines:
                continue
            titulo = _BAKER_SEAL_TITLE.match(lines[0].strip())
            if not titulo:
                continue

            serie = int(titulo.group("serie"))
            motores = re.findall(r"\d{3}", titulo.group("motores"))
            page_no = index + 1
            abierto: dict | None = None

            for line in lines[1:]:
                texto = line.strip()
                if not texto:
                    continue
                if _BAKER_SEAL_STOP.match(texto):
                    abierto = None
                    continue

                # medidas sueltas: pertenecen al modelo que quedó abierto
                solas = _BAKER_SEAL_ONLY_DIMS.match(texto)
                if solas and abierto is not None:
                    _baker_seal_set_dims(abierto, solas, descartadas, page_no)
                    abierto = None
                    continue

                m = _BAKER_SEAL_MODEL.match(texto)
                if not m:
                    continue
                # las descripciones sueltas de la seccion "Optional Features" no
                # son modelos: no arrancan con un codigo corto en mayusculas
                modelo = m.group("model")
                if modelo in ("MODEL", "DESCRIPTION", "LENGTH", "WEIGHT", "FT.", "LBS."):
                    continue

                resto = m.group("resto")
                dims = _BAKER_SEAL_DIMS.search(resto)
                registro = {
                    "manufacturer": "Centrilift",
                    "series": serie,
                    "model": modelo,
                    "type": _baker_seal_type(resto),
                    "compatible_motor_series": motores,
                    "od_inches": serie / 100.0,
                    "length_ft": None,
                    "weight_lbs": None,
                    "shaft_diameter_in": None,
                    "thrust_capacity_lbs": None,
                    "max_temp_f": None,
                    "part_number": None,
                    "description": _BAKER_SEAL_DIMS.sub("", resto).strip(),
                    "_source": (
                        f"{source} p.{page_no}, tabla «{lines[0].strip()}». "
                        f"Capacidad de empuje, temperatura máxima y diámetro de eje: "
                        f"el catálogo no los publica en esta tabla, quedan en null."
                    ),
                }
                if dims:
                    _baker_seal_set_dims(registro, dims, descartadas, page_no)
                    abierto = None
                else:
                    abierto = registro   # las medidas pueden venir más abajo
                records.append(registro)

    if descartadas:
        print(f"  filas con medidas inconsistentes: {len(descartadas)}")
        for d in descartadas[:6]:
            print(f"    {d}")
    return records


def _baker_seal_set_dims(registro: dict, m, descartadas: list, page_no: int) -> None:
    """Carga largo y peso verificando la conversión entre unidades del catálogo."""
    ft, metros = float(m.group("ft")), float(m.group("m"))
    lbs, kg = float(m.group("lbs")), float(m.group("kg"))
    if abs(ft * 0.3048 - metros) > 0.06 or abs(lbs * 0.45359 - kg) > 3.0:
        descartadas.append(
            f"p{page_no} {registro['model']}: {ft}ft/{metros}m {lbs}lb/{kg}kg"
        )
        return
    registro["length_ft"] = ft
    registro["weight_lbs"] = lbs


EXTRACTORS["sellos-baker"] = ("seals", extract_baker_seals)
PDF_BASED.add("sellos-baker")


if __name__ == "__main__":
    main()
