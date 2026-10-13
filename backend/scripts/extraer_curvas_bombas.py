# -*- coding: utf-8 -*-
"""Extrae la foto de la curva de catálogo de cada bomba (60 y 50 Hz).

Uso: python scripts/extraer_curvas_bombas.py <carpeta con los PDF de catálogo>

Lee la página de cada bomba del campo ``_source`` de ``pumps.json`` y guarda
un JPG recortado en ``src/bes/catalogs/curvas/`` más un índice
``curvas/indice.json``. REDA: la curva de 60 Hz está en la página citada y la
de 50 Hz dos páginas después. Wood Group: 60 Hz en la citada, 50 Hz en la
siguiente. Centrilift no publica curvas dibujadas (sólo coeficientes).
"""
import json, re, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1] / "src" / "bes" / "catalogs"
SALIDA = RAIZ / "curvas"
PDFS = {"REDA": "REDA_ESP_Catalog.pdf", "Wood Group ESP": "Curvas BOMBAS Woodgroup.pdf"}
DPI = 110


def texto(pdf, pag):
    r = subprocess.run(["pdftotext", "-f", str(pag), "-l", str(pag), "-layout", str(pdf), "-"],
                       capture_output=True, text=True)
    return r.stdout


def render(pdf, pag, recorte, destino):
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdftoppm", "-r", str(DPI), "-f", str(pag), "-l", str(pag), "-png",
                        str(pdf), f"{d}/p"], check=True)
        img = Image.open(next(Path(d).glob("p*.png"))).convert("RGB")
        w, h = img.size
        x0, y0, x1, y1 = recorte
        img.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))).save(destino, quality=82)


def main(carpeta):
    carpeta = Path(carpeta)
    SALIDA.mkdir(exist_ok=True)
    bombas = json.loads((RAIZ / "pumps.json").read_text(encoding="utf-8"))["pumps"]
    indice = {}
    for b in bombas:
        fab = b["manufacturer"]
        if fab not in PDFS:
            continue
        m = re.search(r"p\.(\d+)", b["_source"])
        if not m:
            continue
        pdf = carpeta / PDFS[fab]
        p60 = int(m.group(1))
        if fab == "REDA":
            p50 = p60 + 2
            ok50 = f"{b['model']} Pump Performance Curve" in texto(pdf, p50) and "50 Hz" in texto(pdf, p50)
            recorte = (0.08, 0.05, 0.93, 0.72)
        else:
            p50, ok50 = p60 + 1, True
            recorte = (0.03, 0.03, 0.97, 0.62)
        ent = {"fuente": f"{PDFS[fab]}, pág. {p60} (60 Hz)"}
        render(pdf, p60, recorte, SALIDA / f"{b['model']}_60.jpg"); ent["60"] = f"{b['model']}_60.jpg"
        if ok50:
            render(pdf, p50, recorte, SALIDA / f"{b['model']}_50.jpg"); ent["50"] = f"{b['model']}_50.jpg"
            ent["fuente"] += f" y pág. {p50} (50 Hz)"
        indice[b["model"]] = ent
        print(b["model"], ent)
    (SALIDA / "indice.json").write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
