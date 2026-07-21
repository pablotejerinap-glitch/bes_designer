"""
Utilidades de lectura de PDF (PyMuPDF + pdfplumber, sin binarios externos).
===========================================================================
* deteccion de fabricante por nombre de archivo + texto,
* texto por pagina,
* extraccion de tablas (pdfplumber),
* extraccion / render de imagenes de graficos (PyMuPDF).

No requiere poppler ni tesseract: todo es pure-Python.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterator, Optional

import fitz  # PyMuPDF
import numpy as np

from config import MANUFACTURER_PATTERNS, NON_PUMP_HINTS


# ------------------------------------------------------------------- hashing
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------- deteccion fabricante
def detect_manufacturer(pdf_path: Path, first_pages_text: str = "") -> str:
    hay = (pdf_path.name + " " + first_pages_text).lower()
    for needle, mfr in MANUFACTURER_PATTERNS:
        if needle in hay:
            return mfr
    return "Desconocido"


def is_pump_catalog(pdf_path: Path, first_pages_text: str = "") -> bool:
    """Heuristica: es catalogo de bombas salvo que el nombre lo marque como
    otro equipo (cable, sello, motor, transformador...) y el texto no hable
    claramente de bombas."""
    name = pdf_path.name.lower()
    if any(h in name for h in NON_PUMP_HINTS):
        # excepcion: algunos catalogos generales de 'systems' incluyen bombas
        txt = first_pages_text.lower()
        return ("pump" in txt and ("stage" in txt or "bpd" in txt
                                   or "impeller" in txt))
    return True


# --------------------------------------------------------------------- texto
def open_doc(pdf_path: Path) -> fitz.Document:
    return fitz.open(pdf_path)


def page_text(doc: fitz.Document, page_index: int) -> str:
    return doc[page_index].get_text("text")


def first_pages_text(doc: fitz.Document, n: int = 3) -> str:
    return "\n".join(page_text(doc, i) for i in range(min(n, doc.page_count)))


# --------------------------------------------------------------------- tablas
def extract_tables(pdf_path: Path, max_pages: Optional[int] = None) -> list[dict]:
    """Devuelve tablas detectadas por pdfplumber: [{page, rows: [[...]]}].
    pdfplumber es mas fiable que PyMuPDF para tablas vectoriales."""
    import pdfplumber

    out: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages if max_pages is None else pdf.pages[:max_pages]
        for pi, page in enumerate(pages):
            try:
                tables = page.extract_tables()
            except Exception:
                tables = []
            for ti, tbl in enumerate(tables):
                rows = [[("" if c is None else str(c).strip()) for c in row]
                        for row in tbl if any(c not in (None, "") for c in row)]
                if len(rows) >= 2:  # al menos encabezado + 1 fila
                    out.append({"page": pi + 1, "index": ti, "rows": rows})
    return out


# ------------------------------------------------------------------- imagenes
def iter_page_images(doc: fitz.Document, page_index: int,
                     min_w: int = 300, min_h: int = 200) -> Iterator[np.ndarray]:
    """Imagenes embebidas (RGB) de una pagina, grandes (probables graficos)."""
    page = doc[page_index]
    for img in page.get_images(full=True):
        xref = img[0]
        try:
            pix = fitz.Pixmap(doc, xref)
            if pix.n >= 5:  # CMYK / con alpha -> a RGB
                pix = fitz.Pixmap(fitz.csRGB, pix)
            if pix.width < min_w or pix.height < min_h:
                continue
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n)
            if pix.n == 1:
                arr = np.repeat(arr, 3, axis=2)
            elif pix.n >= 4:
                arr = arr[:, :, :3]
            yield np.ascontiguousarray(arr[:, :, :3])
        except Exception:
            continue


def render_page(doc: fitz.Document, page_index: int, zoom: float = 3.0) -> np.ndarray:
    """Rasteriza una pagina completa a RGB (para curvas vectoriales, no
    imagenes embebidas)."""
    page = doc[page_index]
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n)
    return np.ascontiguousarray(arr[:, :, :3])


# ------------------------------------------------------- helpers de parsing
_NUM = r"[-+]?\d[\d,]*\.?\d*"


def find_numbers(text: str) -> list[float]:
    out = []
    for m in re.findall(_NUM, text):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out
