"""
Orquestador del pipeline de catalogos de bombas ESP  ->  MySQL catalogos_pump
=============================================================================
Recorre todos los PDF de la carpeta de catalogos y, por cada uno:

1. calcula su SHA-256 y consulta el manifest: si no cambio y no se fuerza,
   lo SALTA (reejecucion incremental al agregar catalogos nuevos);
2. detecta el fabricante;
3. vuelca las tablas crudas (pdfplumber) a output/tables/<pdf>/;
4. segun el fabricante:
     - REDA  -> digitaliza las curvas vectoriales (head+power, 60 Hz) de cada
                pagina, deriva la eficiencia, crea la ficha de bomba y guarda
                overlay de QA + JSON de puntos;
     - resto -> parsea fichas (specs) de las paginas tipo 'Specifications' y
                guarda la imagen del grafico (curva raster) marcada para
                revision (alcance elegido: sin OCR);
5. carga todo a MySQL (upserts idempotentes) y registra processing_log.

USO:
    python pipeline.py                 # incremental (salta PDF sin cambios)
    python pipeline.py --force         # reprocesa todo
    python pipeline.py --only reda     # solo PDFs cuyo nombre matchee
    python pipeline.py --catalogs DIR  # otra carpeta de catalogos
    python db.py                       # (una vez) crea base, usuario y esquema
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import sys
import uuid
from pathlib import Path

import fitz

import db
import digitize as D
import extract as E
import pdf_utils as U
from config import (CATALOGS_DIR, CURVES_DIR, IMAGES_DIR, LOG_DIR,
                    MANIFEST_PATH, MANUFACTURER_FULLNAME)


# ----------------------------------------------------------------- logging
def setup_logging(run_id: str) -> logging.Logger:
    log = logging.getLogger("pipeline")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
    fh = logging.FileHandler(LOG_DIR / f"run_{run_id}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    log.addHandler(fh)
    log.addHandler(ch)
    return log


# ----------------------------------------------------------------- manifest
def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}


def save_manifest(man: dict) -> None:
    MANIFEST_PATH.write_text(json.dumps(man, indent=2, ensure_ascii=False),
                             encoding="utf-8")


# -------------------------------------------------------- helpers de specs
def _specs_from_curve(model: str, points: list[dict]) -> dict:
    """Deriva min/bep/max flow de los puntos digitalizados de la curva."""
    qs = [p["flow_bpd"] for p in points]
    eff_pts = [(p["flow_bpd"], p["efficiency"]) for p in points if p["efficiency"]]
    bep = max(eff_pts, key=lambda t: t[1])[0] if eff_pts else (
        qs[len(qs) // 2] if qs else None)
    return {"min_flow_bpd": min(qs) if qs else None,
            "max_flow_bpd": max(qs) if qs else None,
            "bep_flow_bpd": bep}


# ------------------------------------------------------ procesador: REDA
def process_reda(doc, pdf_path, source_id, conn, log) -> tuple[int, int]:
    """Digitaliza las curvas vectoriales de cada pagina de bomba (version en
    B/D + ft). Crea una ficha por bomba con specs derivadas de la curva."""
    img_dir = IMAGES_DIR / pdf_path.stem
    curve_dir = CURVES_DIR / pdf_path.stem
    img_dir.mkdir(parents=True, exist_ok=True)
    curve_dir.mkdir(parents=True, exist_ok=True)
    n_pumps = n_curves = 0
    seen: set[str] = set()
    for pidx in range(doc.page_count):
        txt = doc[pidx].get_text("text")
        if "Performance Curve" not in txt:
            continue
        if D.chart_units(doc[pidx]) != "english":
            continue                      # el gemelo metrico se ignora
        model = E.parse_reda_curve_title(txt)
        if not model or model in seen:
            continue
        res = D.digitize_vector(doc[pidx], freq=60)
        if res.n_points == 0:
            continue                      # pagina indice / sin curva calibrable
        seen.add(model)
        pump_id = f"Reda_{model}"
        specs = _specs_from_curve(model, res.points)
        box = E.parse_reda_specs(txt)     # caja de specs (panel unico AN/D)
        # rango recomendado de la caja si esta; si no, extension de la curva
        op = box.get("op_range")
        min_flow = op[0] if op else specs["min_flow_bpd"]
        max_flow = op[1] if op else specs["max_flow_bpd"]
        bep = specs["bep_flow_bpd"]
        if op and not (op[0] <= (bep or 0) <= op[1]):
            bep = round((op[0] + op[1]) / 2)
        pump = {
            "pump_id": pump_id, "manufacturer_id": "Reda",
            "series": box.get("series"),
            "model": model, "od_inches": box.get("od_inches"),
            "min_flow_bpd": min_flow, "max_flow_bpd": max_flow,
            "bep_flow_bpd": bep, "max_stages": None,
            "frequency_hz": 60, "source_id": source_id,
            "extraction_method": res.method,
            "review_flag": 1 if res.review else 0,
            "review_reason": res.reason or (None if box else
                             "OD/serie no en la pagina de curva"),
        }
        db.upsert_pump(conn, pump)
        n = db.replace_curve_points(conn, pump_id, res.points)
        n_pumps += 1
        n_curves += 1 if n else 0
        # artefactos: overlay QA + JSON de puntos
        D.save_overlay(doc[pidx], res, img_dir / f"{model}_p{pidx+1}.png",
                       title=f"{model} p{pidx+1}")
        (curve_dir / f"{model}.json").write_text(
            json.dumps({"pump_id": pump_id, "model": model, "page": pidx + 1,
                        "confidence": res.confidence, "review": res.review,
                        "points": res.points}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        log.info(f"  REDA {model}: {n} puntos conf={res.confidence} "
                 f"{'REVISAR' if res.review else 'OK'} {res.reason}")
    return n_pumps, n_curves


# ------------------------------------------ procesador generico: specs
def process_spec_sheets(doc, pdf_path, mfr, source_id, conn, log) -> tuple[int, int]:
    """Paginas 'Specifications' (Centrilift perf sheets, etc.): ficha por
    bomba + imagen del grafico raster guardada para revision."""
    img_dir = IMAGES_DIR / pdf_path.stem
    img_dir.mkdir(parents=True, exist_ok=True)
    n_pumps = 0
    for pidx in range(doc.page_count):
        spec = E.parse_spec_block(doc, pidx, mfr, source_id, pdf_path.name)
        if not spec:
            continue
        db.upsert_pump(conn, spec)
        n_pumps += 1
        # guarda la imagen de curva (raster) de esta pagina o la contigua
        for pg in {pidx, max(0, pidx - 1)}:
            if D.extract_chart_image(doc, pg,
                                     img_dir / f"{spec['model'] or 'p'}_{pg+1}.png"):
                break
        log.info(f"  {mfr} {spec['pump_id']}: specs "
                 f"{'REVISAR' if spec['review_flag'] else 'OK'} "
                 f"{spec['review_reason'] or ''}")
    return n_pumps, 0


# ------------------------------------------------------ proceso por PDF
def process_pdf(pdf_path, conn, run_id, manifest, force, log) -> None:
    name = pdf_path.name
    digest = U.sha256(pdf_path)
    prev = manifest.get(name)
    if prev and prev.get("sha256") == digest and not force:
        log.info(f"SALTA (sin cambios): {name}")
        return

    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        log.error(f"no se pudo abrir {name}: {exc}")
        return

    fpt = U.first_pages_text(doc, 2)
    mfr = U.detect_manufacturer(pdf_path, fpt)
    is_pump = U.is_pump_catalog(pdf_path, fpt)
    full, country = MANUFACTURER_FULLNAME.get(mfr, (mfr, ""))
    db.upsert_manufacturer(conn, mfr, full, country)
    source_id = f"{mfr.upper()}-{pdf_path.stem[:24]}"
    db.upsert_source(conn, source_id, name, "catalogo-pdf",
                     f"Catalogo {mfr}: {name}")

    log.info(f"PROCESA: {name}  fabricante={mfr}  paginas={doc.page_count}  "
             f"bombas={'si' if is_pump else 'no (otro equipo)'}")

    # 1) tablas crudas (todas) — salvo PDFs enormes: se cap ea para no colgar
    try:
        cap = 60 if doc.page_count > 100 else None
        n_tables = E.dump_tables(pdf_path, max_pages=cap)
    except Exception as exc:
        n_tables = -1
        log.warning(f"  extraccion de tablas fallo: {exc}")
    log.info(f"  tablas volcadas: {n_tables}")

    # 2) fichas + curvas segun fabricante
    pumps = curves = 0
    status = "ok"
    msg = ""
    try:
        if not is_pump:
            status = "skip-no-bombas"
            msg = "catalogo de otro equipo (no bombas)"
        elif mfr == "Reda":
            pumps, curves = process_reda(doc, pdf_path, source_id, conn, log)
        else:
            pumps, curves = process_spec_sheets(doc, pdf_path, mfr, source_id,
                                                conn, log)
        if is_pump and pumps == 0:
            status = "sin-fichas"
            msg = "no se pudieron estructurar fichas (ver tablas crudas)"
    except Exception as exc:
        status = "error"
        msg = str(exc)
        log.exception(f"  error procesando {name}: {exc}")

    db.log_processing(conn, run_id=run_id, pdf_file=name, pdf_sha256=digest,
                      manufacturer_id=mfr, status=status, pumps_found=pumps,
                      curves_digitized=curves, message=msg)
    manifest[name] = {"sha256": digest, "run_id": run_id, "status": status,
                      "pumps": pumps, "curves": curves, "manufacturer": mfr,
                      "ts": _dt.datetime.now().isoformat(timespec="seconds")}
    save_manifest(manifest)
    doc.close()
    log.info(f"  => {status}: {pumps} bombas, {curves} curvas")


# --------------------------------------------------------------------- main
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Pipeline catalogos ESP -> MySQL")
    ap.add_argument("--force", action="store_true", help="reprocesa todo")
    ap.add_argument("--only", default="", help="subcadena del nombre de PDF")
    ap.add_argument("--catalogs", default=str(CATALOGS_DIR))
    args = ap.parse_args(argv)

    run_id = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    log = setup_logging(run_id)

    # esquema idempotente (por si es la primera corrida)
    db.create_schema()
    conn = db.connect()

    cat_dir = Path(args.catalogs)
    pdfs = sorted(p for p in cat_dir.rglob("*.pdf")
                  if args.only.lower() in p.name.lower())
    log.info(f"=== corrida {run_id}: {len(pdfs)} PDF en {cat_dir} ===")

    manifest = load_manifest()
    for pdf in pdfs:
        process_pdf(pdf, conn, run_id, manifest, args.force, log)

    conn.close()
    c = db.counts()
    log.info(f"=== FIN corrida {run_id} ===")
    log.info(f"MySQL catalogos_pump: {c}")
    print("\nResumen MySQL:", c)


if __name__ == "__main__":
    main()
