"""
Verificación de la base de datos v2 (normalizada) contra los JSON
=================================================================

Igual que verify_migration.py (etapa 1), pero contra el esquema v2:
carga con CatalogManager (JSON) y con ExcelCatalogManager (Excel
normalizado) y compara campo por campo + selecciones de equipo.
Además verifica que transformers.xlsx coincide con la tupla de
core/electrical.py.

USO:  python verify_database.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# El propio directorio: estos scripts se importan entre si por nombre plano.
sys.path.insert(0, str(Path(__file__).parent))

from bes.catalogs.loader import CatalogManager  # noqa: E402
from bes.core.electrical import _TRANSFORMER_SIZES_KVA  # noqa: E402
from database_loader import ExcelCatalogManager  # noqa: E402

errors: list[str] = []


def eq(a, b) -> bool:
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
            vb = vb or []
            if len(va) != len(vb) or any(not eq(x, y) for x, y in zip(va, vb)):
                errors.append(f"{name}.{k}: {va!r} != {vb!r}")
        elif not eq(va, vb):
            errors.append(f"{name}.{k}: {va!r} != {vb!r}")


def compare_catalog(label, ref_list, new_list, key_fields) -> None:
    if len(ref_list) != len(new_list):
        errors.append(f"{label}: {len(ref_list)} en JSON vs "
                      f"{len(new_list)} en Excel")
        return
    for ref, new in zip(ref_list, new_list):
        name = label + ":" + "_".join(str(ref.get(k, "")) for k in key_fields)
        compare_dicts(name, ref, new)


def main() -> None:
    json_cat = CatalogManager()
    xlsx_cat = ExcelCatalogManager()

    # ---- bombas -------------------------------------------------------
    jp, xp = json_cat.get_all_pumps(), xlsx_cat.get_all_pumps()
    if len(jp) != len(xp):
        errors.append(f"pumps: {len(jp)} vs {len(xp)}")
    for a, b in zip(jp, xp):
        name = f"pump:{a.manufacturer}_{a.series}_{a.model}"
        for attr in ("manufacturer", "series", "model", "od", "min_flow",
                     "max_flow", "bep_flow", "max_stages"):
            if not eq(getattr(a, attr), getattr(b, attr)):
                errors.append(f"{name}.{attr}: {getattr(a, attr)!r} != "
                              f"{getattr(b, attr)!r}")
        if list(a.housing_options) != list(b.housing_options):
            errors.append(f"{name}.housing_options difiere")
        if len(a.points) != len(b.points):
            errors.append(f"{name}: nº de puntos difiere")
        else:
            for i, (pa, pb) in enumerate(zip(a.points, b.points)):
                for attr in ("flow_rate", "head_per_stage", "hp_per_stage",
                             "efficiency"):
                    if not eq(getattr(pa, attr), getattr(pb, attr)):
                        errors.append(f"{name}.curva[{i}].{attr} difiere")

    # ---- resto de catálogos --------------------------------------------
    compare_catalog("motor", json_cat._motors, xlsx_cat._motors,
                    ("manufacturer", "model", "voltage"))
    compare_catalog("cable", json_cat._cables, xlsx_cat._cables,
                    ("manufacturer", "type", "conductor", "size"))
    compare_catalog("seal", json_cat._seals, xlsx_cat._seals,
                    ("manufacturer", "model"))
    compare_catalog("gas_handler", json_cat._gas_handlers,
                    xlsx_cat._gas_handlers, ("manufacturer", "model"))
    compare_catalog("sensor", json_cat._sensors, xlsx_cat._sensors,
                    ("manufacturer", "model"))

    # ---- transformadores: Excel vs tupla hardcodeada --------------------
    excel_sizes = xlsx_cat.get_transformer_sizes_kva()
    if excel_sizes != sorted(_TRANSFORMER_SIZES_KVA):
        errors.append(f"transformers.xlsx {excel_sizes} != "
                      f"electrical.py {sorted(_TRANSFORMER_SIZES_KVA)}")

    # ---- selecciones funcionales ----------------------------------------
    m1 = json_cat.get_motor(hp=100, voltage=1000, series="456")
    m2 = xlsx_cat.get_motor(hp=100, voltage=1000, series="456")
    if m1["model"] != m2["model"]:
        errors.append(f"get_motor: {m1['model']} != {m2['model']}")

    c1 = json_cat.get_cable(amps=40, temp_f=180, voltage=1000)
    c2 = xlsx_cat.get_cable(amps=40, temp_f=180, voltage=1000)
    if (c1["type"], c1["conductor"], c1["size"]) != \
       (c2["type"], c2["conductor"], c2["size"]):
        errors.append("get_cable difiere")

    s1 = json_cat.get_seal("456", temp_f=200, thrust_lbs=5000)
    s2 = xlsx_cat.get_seal("456", temp_f=200, thrust_lbs=5000)
    if s1["model"] != s2["model"]:
        errors.append(f"get_seal: {s1['model']} != {s2['model']}")

    p1 = json_cat.get_pumps_by_flow_range(1300)
    p2 = xlsx_cat.get_pumps_by_flow_range(1300)
    if [p.model for p in p1] != [p.model for p in p2]:
        errors.append("get_pumps_by_flow_range difiere")
    if p1:
        i1 = json_cat.interpolate_pump_curve(p1[0], 1250)
        i2 = xlsx_cat.interpolate_pump_curve(p2[0], 1250)
        for k in i1:
            if not eq(i1[k], i2[k]):
                errors.append(f"interpolate.{k}: {i1[k]} != {i2[k]}")

    gh1 = json_cat.select_gas_handler(2000, casing_id_in=6.2)
    gh2 = xlsx_cat.select_gas_handler(2000, casing_id_in=6.2)
    if (gh1 or {}).get("model") != (gh2 or {}).get("model"):
        errors.append("select_gas_handler difiere")

    sn1 = json_cat.select_sensor(3000, 250, 2300)
    sn2 = xlsx_cat.select_sensor(3000, 250, 2300)
    if (sn1 or {}).get("model") != (sn2 or {}).get("model"):
        errors.append("select_sensor difiere")

    total = (len(jp) + len(json_cat._motors) + len(json_cat._cables)
             + len(json_cat._seals) + len(json_cat._gas_handlers)
             + len(json_cat._sensors))
    if errors:
        print(f"FALLÓ: {len(errors)} diferencias\n")
        for e in errors[:40]:
            print(" -", e)
        sys.exit(1)
    print(f"BASE DE DATOS v2 VERIFICADA: {total} registros idénticos a los "
          f"JSON; transformadores coinciden con electrical.py; selecciones "
          f"de motor, cable, sello, separador, sensor e interpolación de "
          f"curvas idénticas.")


if __name__ == "__main__":
    main()
