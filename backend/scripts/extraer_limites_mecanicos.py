"""Lee de la hoja de 60 Hz del catálogo REDA los límites mecánicos de cada bomba.

Carga en pumps.json, tal como los imprime el catálogo:
    shaft_hp_limit_std, shaft_hp_limit_high_strength   (Shaft brake-power limit)
    housing_burst_psi = {standard, buttress, welded}    (Housing burst-pressure limit;
                                                         null = «Not applicable»)
    fuente_mecanica = "REDA_ESP_Catalog.pdf, pág. N"

Uso: python scripts/extraer_limites_mecanicos.py <carpeta con REDA_ESP_Catalog.pdf>
"""
import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] / "src" / "bes" / "catalogs"


def numero(s: str):
    s = s.strip()
    if s.lower().startswith("not"):
        return None
    return float(s.replace(",", "").replace(".", ""))


def main(carpeta: str) -> None:
    pdf = Path(carpeta) / "REDA_ESP_Catalog.pdf"
    ruta = RAIZ / "pumps.json"
    datos = json.loads(ruta.read_text(encoding="utf8"))
    indice = json.loads((RAIZ / "curvas" / "indice.json").read_text(encoding="utf8"))
    val = r"([\d.,]+ ?psi|Not applicable)"
    for b in datos["pumps"]:
        if b["manufacturer"] != "REDA" or b["model"] not in indice:
            continue
        pag = int(re.search(r"pág\. (\d+)", indice[b["model"]]["fuente"]).group(1))
        t = subprocess.run(["pdftotext", "-f", str(pag), "-l", str(pag), "-layout", str(pdf), "-"],
                           capture_output=True, text=True, check=True).stdout
        t = re.sub(r"[ \t]+", " ", t)
        std = re.search(r"Shaft brake-power limit Standard ([\d,]+) ?hp", t)
        hs = re.search(r"High strength ([\d,]+) ?hp", t)
        ps = re.search(r"Housing burst-pressure limit Standard " + val, t)
        pb = re.search(r"Buttress " + val, t)
        pw = re.search(r"Welded " + val, t)
        if not (std and hs and ps and pb and pw):
            print("sin datos completos:", b["model"], pag)
            continue
        b["shaft_hp_limit_std"] = numero(std.group(1))
        b["shaft_hp_limit_high_strength"] = numero(hs.group(1))
        b["housing_burst_psi"] = {k: numero(m.group(1).replace("psi", ""))
                                  for k, m in (("standard", ps), ("buttress", pb), ("welded", pw))}
        b["fuente_mecanica"] = f"REDA_ESP_Catalog.pdf, pág. {pag}"
        # La tabla de carcasas («Housing / Length / Max. Stages») está unas
        # páginas antes de la curva de 60 Hz.
        for q in range(pag - 1, pag - 6, -1):
            tq = subprocess.run(["pdftotext", "-f", str(q), "-l", str(q), "-layout", str(pdf), "-"],
                                capture_output=True, text=True, check=True).stdout
            if "Max." in tq and "Length" in tq and b["model"] in tq and "Tandem" not in tq:
                b["fuente_carcasas"] = f"REDA_ESP_Catalog.pdf, pág. {q}"
                break
        print(b["model"], pag, b["shaft_hp_limit_std"], b["shaft_hp_limit_high_strength"], b["housing_burst_psi"])
    tandem(pdf, datos)
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf8")


def tandem(pdf: Path, datos: dict) -> None:
    """Tabla «Tandem Combinations» de cada bomba REDA: desde cuántas etapas pide
    cojinete high-load en el protector (nota †) y hasta cuántas llega la tabla."""
    todo = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True,
                          check=True).stdout.split("\f")
    for b in datos["pumps"]:
        if b["manufacturer"] != "REDA":
            continue
        for i, pag in enumerate(todo):
            if re.search(rf"\b{re.escape(b['model'])} Pump, .*Tandem Combinations", pag):
                filas = re.findall(r"^\s+(\d{2,3})\s+(\d{2,4})([†‡§,\s]*)", pag, re.M)
                etapas = [(int(n), m) for _, n, m in filas]
                if not etapas:
                    break
                # Qué símbolo marca «high-load bearing in protector» depende de la
                # tabla; si distingue compresión y flotante, se toma el del tipo de
                # etapa de la nota («Stage counts are for C-CT-ES / FL-CT-ES»).
                tipo = "compression" if re.search(r"for C-", pag) else "floater"
                leyenda = dict(re.findall(r"^\s*([†‡§])\s*Requires use of (.+)$", pag, re.M))
                simb = [k for k, v in leyenda.items()
                        if re.search(r"high[- ]load bearing in protector", v)
                        and (("compression" not in v and "floater" not in v) or tipo in v)]
                hl = [n for n, m in etapas if simb and simb[0] in m]
                b["tandem"] = {"fuente": f"REDA_ESP_Catalog.pdf, pág. {i + 1}",
                               "tipo_etapa": tipo,
                               "etapas_max_tabla": max(n for n, _ in etapas),
                               "etapas_cojinete_hl": min(hl) if hl else None}
                print("tandem", b["model"], b["tandem"])
                break


if __name__ == "__main__":
    main(sys.argv[1])
