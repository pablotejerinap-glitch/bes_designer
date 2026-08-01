"""
Verificación de la migración JSON → Excel
=========================================

Carga los catálogos DOS veces — con el CatalogManager original (JSON)
y con el ExcelCatalogManager nuevo (Excel) — y compara registro por
registro y campo por campo.

Si este script termina en "MIGRACIÓN VERIFICADA", los datos de Excel
son idénticos a los de JSON y la aplicación puede usar cualquiera de
los dos orígenes con resultados de ingeniería idénticos.

USO
---
    python verify_migration.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# El propio directorio: estos scripts se importan entre si por nombre plano.
sys.path.insert(0, str(Path(__file__).parent))

from bes.catalogs.loader import CatalogManager  # noqa: E402
from excel_loader import ExcelCatalogManager  # noqa: E402

errors: list[str] = []


def eq(a, b) -> bool:
    """Igualdad tolerante: 4 == 4.0, floats con tolerancia 1e-9."""
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a is None and b is None
        return abs(float(a) - float(b)) < 1e-9
    return a == b


def compare_dicts(name: str, ref: dict, new: dict) -> None:
    for k in set(ref) | set(new):
        va, vb = ref.get(k), new.get(k)
        if isinstance(va, dict):
            if not isinstance(vb, dict) or set(va) != set(vb) or any(
                not eq(va[t], vb[t]) for t in va
            ):
                errors.append(f"{name}.{k}: {va!r} != {vb!r}")
        elif isinstance(va, list):
            if vb is None:
                vb = []
            if len(va) != len(vb) or any(not eq(x, y) for x, y in zip(va, vb)):
                errors.append(f"{name}.{k}: {va!r} != {vb!r}")
        elif not eq(va, vb):
            errors.append(f"{name}.{k}: {va!r} != {vb!r}")


def compare_catalog(label: str, ref_list: list[dict], new_list: list[dict],
                    key_fields: tuple[str, ...]) -> None:
    if len(ref_list) != len(new_list):
        errors.append(f"{label}: {len(ref_list)} registros en JSON, "
                      f"{len(new_list)} en Excel")
        return
    for ref, new in zip(ref_list, new_list):
        name = label + ":" + "_".join(str(ref.get(k, "")) for k in key_fields)
        compare_dicts(name, ref, new)


def main() -> None:
    json_cat = CatalogManager()
    xlsx_cat = ExcelCatalogManager()

    # ---- bombas (objetos PumpCurve) ----------------------------------
    jp, xp = json_cat.get_all_pumps(), xlsx_cat.get_all_pumps()
    if len(jp) != len(xp):
        errors.append(f"pumps: {len(jp)} en JSON, {len(xp)} en Excel")
    for a, b in zip(jp, xp):
        name = f"pump:{a.manufacturer}_{a.series}_{a.model}"
        for attr in ("manufacturer", "series", "model", "od", "min_flow",
                     "max_flow", "bep_flow", "max_stages"):
            if not eq(getattr(a, attr), getattr(b, attr)):
                errors.append(f"{name}.{attr}: "
                              f"{getattr(a, attr)!r} != {getattr(b, attr)!r}")
        if list(a.housing_options) != list(b.housing_options):
            errors.append(f"{name}.housing_options difiere")
        if len(a.points) != len(b.points):
            errors.append(f"{name}: {len(a.points)} vs {len(b.points)} puntos")
        else:
            for i, (pa, pb) in enumerate(zip(a.points, b.points)):
                for attr in ("flow_rate", "head_per_stage", "hp_per_stage",
                             "efficiency"):
                    if not eq(getattr(pa, attr), getattr(pb, attr)):
                        errors.append(f"{name}.curva[{i}].{attr}: "
                                      f"{getattr(pa, attr)} != {getattr(pb, attr)}")

    # ---- catálogos de dicts ------------------------------------------
    compare_catalog("motor", json_cat._motors, xlsx_cat._motors,
                    ("manufacturer", "model", "hp_rating", "voltage"))
    compare_catalog("cable", json_cat._cables, xlsx_cat._cables,
                    ("manufacturer", "type", "size"))
    compare_catalog("seal", json_cat._seals, xlsx_cat._seals,
                    ("manufacturer", "model"))
    compare_catalog("gas_handler", json_cat._gas_handlers,
                    xlsx_cat._gas_handlers, ("manufacturer", "model"))
    compare_catalog("sensor", json_cat._sensors, xlsx_cat._sensors,
                    ("manufacturer", "model"))

    # ---- prueba funcional: mismas selecciones de equipo ---------------
    # No basta con que los datos sean iguales: verificamos que los
    # métodos de selección devuelven el mismo equipo en ambos orígenes.
    m1 = json_cat.get_motor(hp=100, voltage=1000, series="456")
    m2 = xlsx_cat.get_motor(hp=100, voltage=1000, series="456")
    if m1["model"] != m2["model"]:
        errors.append(f"get_motor difiere: {m1['model']} != {m2['model']}")

    c1 = json_cat.get_cable(amps=40, temp_f=180, voltage=1000)
    c2 = xlsx_cat.get_cable(amps=40, temp_f=180, voltage=1000)
    if (c1["type"], c1["size"]) != (c2["type"], c2["size"]):
        errors.append(f"get_cable difiere: {c1} != {c2}")

    p1 = json_cat.get_pumps_by_flow_range(1300)
    p2 = xlsx_cat.get_pumps_by_flow_range(1300)
    if [p.model for p in p1] != [p.model for p in p2]:
        errors.append("get_pumps_by_flow_range difiere")
    if p1:
        i1 = json_cat.interpolate_pump_curve(p1[0], 1250)
        i2 = xlsx_cat.interpolate_pump_curve(p2[0], 1250)
        for k in i1:
            if not eq(i1[k], i2[k]):
                errors.append(f"interpolate_pump_curve.{k}: {i1[k]} != {i2[k]}")

    # ---- resultado -----------------------------------------------------
    total = (len(jp) + len(json_cat._motors) + len(json_cat._cables)
             + len(json_cat._seals) + len(json_cat._gas_handlers)
             + len(json_cat._sensors))
    if errors:
        print(f"FALLÓ: {len(errors)} diferencias encontradas\n")
        for e in errors[:40]:
            print(" -", e)
        sys.exit(1)
    print(f"MIGRACIÓN VERIFICADA: {total} registros idénticos entre "
          f"JSON y Excel; selección de equipos e interpolación de curvas "
          f"coinciden.")


if __name__ == "__main__":
    main()
