# Runner temporal (workaround de caché de sincronización): aplica en
# memoria la corrección de build_well_examples y ejecuta build_database.
# El archivo canónico build_database.py ya contiene esta misma corrección.
from __future__ import annotations

import json
from pathlib import Path

import build_database as bd
from build_database import (BLOCK_SHEET, DATA_DIR, WELL_BLOCKS, Workbook,
                            write_readme, write_sheet, KEY_NOTE)


def build_well_examples_fixed():
    with open(DATA_DIR / "example_wells.json", encoding="utf-8") as f:
        data = json.load(f)
    wells = {k: v for k, v in data.items() if not k.startswith("_")}

    wb = Workbook()
    ws = wb.active
    ws.title = "wells"
    write_sheet(ws, ["well_id", "description", "source"],
                [[wid, w.get("description", ""), "data/example_wells.json"]
                 for wid, w in wells.items()])

    for block in WELL_BLOCKS:
        cols = []
        for w in wells.values():
            for k, v in w.get(block, {}).items():
                if isinstance(v, (dict, list)):
                    continue
                if k not in cols:
                    cols.append(k)
        if not cols:
            continue
        ws_b = wb.create_sheet(BLOCK_SHEET[block])
        rows = [[wid] + [w.get(block, {}).get(c) for c in cols]
                for wid, w in wells.items()]
        write_sheet(ws_b, ["well_id"] + cols, rows)

    detail_rows = []
    for wid, w in wells.items():
        for group, v in w.get("book_reference", {}).items():
            if isinstance(v, dict):
                for item, val in v.items():
                    if isinstance(val, (dict, list)):
                        val = json.dumps(val)
                    detail_rows.append([wid, group, item, val])
    if detail_rows:
        ws_d = wb.create_sheet("book_reference_details")
        write_sheet(ws_d, ["well_id", "detail_group", "item", "value"],
                    detail_rows)

    write_readme(wb, "Pozos de ejemplo — casos de validación (Brown Vol. 2B)", [
        ("Estructura y claves",
         [("wells", "Tabla maestra. PK: well_id (ej. example_1a)."),
          ("Hojas 1:1", "reservoir, fluid, well_geometry, surface_conditions, design_objectives y book_reference tienen relación 1:1 con wells: misma PK well_id, que es a la vez FK → wells."),
          ("Por qué 1:1 y no una tabla ancha", "Cada hoja es el espejo de un dataclass de core/models.py (Reservoir, Fluid, WellGeometry, SurfaceConditions, DesignObjectives): misma responsabilidad, mismos campos. Autodocumentante y validable por bloque.")]),
        ("Unidades (convención del proyecto)",
         [("Presiones", "psia (diferenciales en psi)."),
          ("Temperaturas", "°F."),
          ("Caudales", "STB/d o bpd."),
          ("Profundidades", "pies (TVD o MD)."),
          ("Diámetros", "pulgadas.")]),
        ("book_reference",
         [("Contenido", "Resultados esperados del libro (TDH, etapas, HP, bomba) usados como regresión: los tests comparan el cálculo de la aplicación contra estos valores."),
          ("book_reference_details", "Tabla clave-valor para conjuntos de validación heterogéneos (incrementos de presión del Ej. 3A, casos del Ej. 3B). PK compuesta: (well_id, detail_group, item). Mantiene la 1FN sin crear decenas de columnas dispersas.")]),
        KEY_NOTE,
    ])
    wb.save(bd.OUTPUT_DIR / "well_examples.xlsx")
    return wells


bd.build_well_examples = build_well_examples_fixed

if __name__ == "__main__":
    bd.main()
