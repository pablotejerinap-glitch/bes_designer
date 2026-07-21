"""
Extraccion de tablas crudas y de fichas (specs) de bombas ESP.
==============================================================
Dos niveles:
* ``dump_tables`` : vuelca TODAS las tablas detectadas por PDF (pdfplumber)
  a output/tables/<pdf>/  -> cumple "extraer tablas de todos los PDF".
* parsers de specs : intentan estructurar fichas de bomba. Multi-metodo,
  con fallback; lo que no se puede estructurar queda en las tablas crudas.

Cada spec devuelto es un dict con las claves de la tabla ``pumps``.
Los campos que no se pueden determinar quedan None (NULL) y se marca
``review_flag`` = 1 con un motivo.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Optional

import fitz

import pdf_utils as U
from config import TABLES_DIR


# ============================================================ tablas crudas
def dump_tables(pdf_path: Path, out_root: Path = TABLES_DIR,
                max_pages: Optional[int] = None) -> int:
    """Vuelca todas las tablas del PDF a CSV + un indice JSON. Idempotente.
    max_pages limita el barrido en PDFs enormes (pdfplumber es lento en
    paginas con muchos vectores)."""
    dest = out_root / pdf_path.stem
    dest.mkdir(parents=True, exist_ok=True)
    tables = U.extract_tables(pdf_path, max_pages=max_pages)
    index = []
    for i, t in enumerate(tables):
        fn = dest / f"p{t['page']:04d}_t{t['index']}.csv"
        with open(fn, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(t["rows"])
        index.append({"file": fn.name, "page": t["page"], "rows": len(t["rows"]),
                      "cols": max(len(r) for r in t["rows"])})
    with open(dest / "_index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    return len(tables)


# ======================================================== helpers de parsing
_RANGE = re.compile(r"([\d,]+)\s*(?:to|-|–)\s*([\d,]+)")


def _num(s: str) -> Optional[float]:
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _flow_range(text: str) -> Optional[tuple[float, float]]:
    """Busca 'Flow range ... 1,800 to 8,200' saltando '60 Hz'/'50 Hz'."""
    m = re.search(r"[Ff]low\s+range", text)
    if not m:
        return None
    window = text[m.end():m.end() + 90]
    for a, b in _RANGE.findall(window):
        lo, hi = _num(a), _num(b)
        if lo and hi and lo < hi and hi >= 100:   # descarta '60 to ...'
            return lo, hi
    return None


def _od_inches(text: str) -> Optional[float]:
    m = re.search(r"[Oo]uter\s+diameter[^\d]{0,20}(\d\.\d{1,2})", text)
    if m:
        return float(m.group(1))
    return None


def _series(text: str) -> Optional[str]:
    m = re.search(r"[Ss]eries\s+(\d{3})", text)
    return m.group(1) if m else None


# ==================================================== parser: ficha 1-bomba
def parse_spec_block(doc: fitz.Document, page_index: int, manufacturer: str,
                     source_id: str, pdf_file: str) -> Optional[dict]:
    """Paginas tipo 'Specifications' de una sola bomba (Centrilift perf sheet,
    etc.). Devuelve un dict de pumps o None."""
    text = U.page_text(doc, page_index)
    if "specification" not in text.lower() and "flow range" not in text.lower():
        return None
    fr = _flow_range(text)
    od = _od_inches(text)
    series = _series(text)
    # modelo: token alfanumerico tipo 400P60ER / P23 / GC6100, en titulo o nombre
    model = None
    m = re.search(r"\b(\d{3}[A-Z]{1,3}\d{2,5}[A-Z]{0,3})\b", text)
    if m:
        model = m.group(1)
    if not model:
        m = re.search(r"([A-Z]{1,3}\d{2,5})", Path(pdf_file).stem)
        if m:
            model = m.group(1)
    if not (fr or od or series):
        return None
    pid = f"{manufacturer}_{series or 'NA'}_{model or Path(pdf_file).stem}".replace(" ", "")
    reasons = []
    if not fr:
        reasons.append("sin rango de caudal")
    if not model:
        reasons.append("modelo no identificado")
    return {
        "pump_id": pid,
        "manufacturer_id": manufacturer,
        "series": series,
        "model": model,
        "od_inches": od,
        "min_flow_bpd": fr[0] if fr else None,
        "max_flow_bpd": fr[1] if fr else None,
        "bep_flow_bpd": round((fr[0] + fr[1]) / 2) if fr else None,
        "max_stages": None,
        "frequency_hz": 60,
        "source_id": source_id,
        "extraction_method": "pdf-text",
        "review_flag": 1 if reasons else 0,
        "review_reason": "; ".join(reasons) or None,
    }


# ============================================ parser: titulo de curva REDA
# Dos formatos en el catalogo:
#   "REDA* Pump HN13500 Performance Curve"  (modelo despues de 'Pump')
#   "AN550 Pump Performance Curve"          (modelo antes de 'Pump')
_MODEL = r"[A-Z]{1,4}\d[\dA-Z/-]{0,7}"
_REDA_TITLE_AFTER = re.compile(r"Pump\s+(" + _MODEL + r")\s+Performance")
_REDA_TITLE_BEFORE = re.compile(r"(" + _MODEL + r")\s+Pump\s+Performance")


def parse_reda_curve_title(text: str) -> Optional[str]:
    m = _REDA_TITLE_AFTER.search(text) or _REDA_TITLE_BEFORE.search(text)
    if not m:
        return None
    model = m.group(1)
    return None if model.upper() == "REDA" else model


def parse_reda_specs(text: str) -> dict:
    """Caja de specs de las curvas de panel unico (AN/D): rango operativo
    recomendado y diametro de housing (-> OD y serie)."""
    out: dict = {}
    m = re.search(r"[Oo]ptimum operating range\s+([\d,]+)\s*[-–]\s*([\d,]+)", text)
    if m:
        lo, hi = _num(m.group(1)), _num(m.group(2))
        if lo and hi and lo < hi:
            out["op_range"] = (lo, hi)
    m = re.search(r"[Nn]ominal housing diameter\s+(\d\.\d{1,2})", text)
    if m:
        od = float(m.group(1))
        out["od_inches"] = od
        out["series"] = str(int(round(od * 100)))   # 3.38 in -> serie 338
    return out
