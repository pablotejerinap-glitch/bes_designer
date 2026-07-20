"""
Vendor catalog ingestion (ChampionX / SLB) into the existing JSON catalogs.

Transcribe las tablas de especificaciones de las hojas de datos provistas por
el usuario a los catálogos JSON existentes, sin tocar entradas previas de otros
fabricantes. Es idempotente: en cada corrida elimina las entradas que él mismo
agregó (por fabricante+línea) y las reescribe.

Fuentes (carpeta del usuario, no versionadas en el repo):
  - affirmed-submersible-motor-ps.pdf          → motores AFFIRMED (ChampionX)
  - Affirmed_PowerFit_Data_Sheet_motor.pdf     → motor PowerFit (SLB)
  - UNBRIDLED_CAVALCADE_Cable_Solution_Sheet    → cables CAVALCADE (ChampionX)
  - UNBRIDLED_VIGIL_Protectors_Solution_Sheet   → protectores VIGIL (ChampionX)

Catálogos nuevos (gas handlers WHIRLAWAY, sensores ACE) y bombas High Rise se
generan por separado (catalogs/gas_handlers.json, sensors.json escritos a mano
con trazabilidad; bombas en scripts/generate_pump_curves.py).

Decisiones de digitalización (ver docs/CHAMPIONX_INGESTION_REPORT.md):
  - Serie/OD AFFIRMED: las hojas VIGIL y WHIRLAWAY declaran "400 series =
    4.00 in" → series="400", od_inches=4.00 (convención: serie = OD×100).
  - AFFIRMED max_temp_f = 325 °F (temp. de fondo a plena carga).
  - Cables CAVALCADE: la hoja no publica ampacidad ni caída de tensión; son
    función física del AWG y se reusan del calibre equivalente del catálogo
    (API RP 11S6 / Brown 4.52). Incluye el calibre 1/0 (su caída se lee del
    propio JSON tras el refactor de core/electrical.py).
  - Protectores VIGIL: la hoja da HP de eje y diámetros, NO empuje ni
    temperatura. Se carga shaft_hp real; thrust_capacity_lbs y max_temp_f son
    ESTIMADOS (consistentes con protectores del mismo diámetro del catálogo) y
    quedan marcados en _source. La serie VIGIL 400 es la única compatible con
    los motores AFFIRMED serie 400.
  - Motor PowerFit (SLB): hoja de marketing, solo OD 4.20"/208 HP/400 °F. Los
    valores eléctricos (voltaje/amperaje) son ESTIMADOS desde la fila AFFIRMED
    de HP comparable y quedan marcados en _source.

Uso (desde la raíz del proyecto):
    python scripts/ingest_championx.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from bes.catalogs import CATALOG_DIR

_ROOT = Path(__file__).parent.parent
_MOTORS_JSON = CATALOG_DIR / "motors.json"
_CABLES_JSON = CATALOG_DIR / "cables.json"
_SEALS_JSON = CATALOG_DIR / "seals.json"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_MANUFACTURER = "ChampionX"

# ---------------------------------------------------------------------------
# AFFIRMED submersible motors — 400 series (4.00 in OD), UNBRIDLED ESP Systems
# Cada fila: HP, [(voltaje, amperaje), ...], longitud_ft
# Transcrito de "AFFIRMED Motor Specifications" (filas UT).
# ---------------------------------------------------------------------------
_AFFIRMED_MOTORS: list[tuple[int, list[tuple[int, float]], float]] = [
    (24,  [(439, 35.0),  (682, 22.5)],  5.7),
    (36,  [(415, 55.5),  (901, 25.5)],  7.4),
    (48,  [(877, 35.0),  (1363, 22.5)], 9.0),
    (60,  [(995, 38.5),  (1400, 27.5)], 10.6),
    (72,  [(951, 48.5),  (2044, 22.5)], 12.2),
    (84,  [(968, 55.5),  (2102, 25.5)], 13.8),
    (96,  [(945, 65.0),  (2402, 25.5)], 15.4),
    (108, [(881, 78.5),  (2520, 27.5)], 17.0),
    (120, [(1586, 48.5), (2598, 29.5)], 18.6),
    (132, [(1076, 78.5), (2635, 32.0)], 20.2),
    (144, [(1174, 78.5), (2389, 38.5)], 21.8),
    (156, [(1272, 78.5), (2588, 38.5)], 23.4),
    (168, [(1653, 65.0), (2503, 43.0)], 25.0),
    (180, [(2682, 43.0)],               26.6),
    (192, [(1890, 65.0), (2537, 48.5)], 28.2),
    (204, [(1664, 78.5), (2695, 48.5)], 29.9),
    (216, [(1762, 78.5), (2490, 55.5)], 31.5),
]

_MOTOR_SERIES = "400"
_MOTOR_OD_IN = 4.00
_MOTOR_MAX_TEMP_F = 325   # bottomhole at full HP load (hoja AFFIRMED)
_MOTOR_SOURCE = "ChampionX AFFIRMED data sheet (UNBRIDLED ESP); OD cross-ref VIGIL/WHIRLAWAY 400-series = 4.00 in"


# PowerFit (SLB) — single small-diameter motor. Marketing sheet: OD 4.20",
# 208 HP, 400 °F. Electrical values estimated from the AFFIRMED 204 HP row.
_POWERFIT_SOURCE = "SLB Affirmed PowerFit data sheet (OD 4.20\"/208HP/400°F); voltage & amperage ESTIMATED from AFFIRMED 204HP row"


def build_motors() -> list[dict]:
    motors: list[dict] = []
    for hp, vi_pairs, length in _AFFIRMED_MOTORS:
        for voltage, amps in vi_pairs:
            motors.append({
                "manufacturer": _MANUFACTURER,
                "series": _MOTOR_SERIES,
                "model": f"AFFIRMED-{_MOTOR_SERIES}-{hp}HP-{voltage}V",
                "hp_rating": hp,
                "voltage": voltage,
                "amperage": amps,
                "length_ft": length,
                "max_temp_f": _MOTOR_MAX_TEMP_F,
                "od_inches": _MOTOR_OD_IN,
                "_source": _MOTOR_SOURCE,
            })
    # SLB PowerFit, two voltage variants (estimated electricals)
    for voltage, amps in ((1664, 78.5), (2695, 48.5)):
        motors.append({
            "manufacturer": "SLB",
            "series": "420",
            "model": f"PowerFit-420-208HP-{voltage}V",
            "hp_rating": 208,
            "voltage": voltage,
            "amperage": amps,
            "length_ft": 29.9,
            "max_temp_f": 400,
            "od_inches": 4.20,
            "_source": _POWERFIT_SOURCE,
        })
    return motors


# ---------------------------------------------------------------------------
# CAVALCADE power cable — EPDM/lead, 400 °F, solid copper, 5 kV.
# Ampacidad y caída de tensión reusadas del calibre equivalente del catálogo
# (constante física por AWG). Calibre 1/0 pospuesto (ver docstring).
# ---------------------------------------------------------------------------
_CABLE_VDROP_BY_SIZE = {
    "1/0": {"100": 0.187, "150": 0.205, "180": 0.215, "200": 0.224},
    "#2":  {"100": 0.297, "150": 0.324, "180": 0.341, "200": 0.354},
    "#4":  {"100": 0.473, "150": 0.516, "180": 0.543, "200": 0.562},
    "#6":  {"100": 0.752, "150": 0.820, "180": 0.863, "200": 0.894},
}
_CABLE_MAX_AMPS = {"1/0": 115, "#2": 88, "#4": 69, "#6": 55}
_CABLE_SOURCE = "ChampionX CAVALCADE data sheet (EPDM/lead, 400°F); ampacity & vdrop per-AWG std (API RP 11S6)"


def build_cables() -> list[dict]:
    cables: list[dict] = []
    for size in ("1/0", "#2", "#4", "#6"):
        cables.append({
            "manufacturer": _MANUFACTURER,
            "type": "EPDM",
            "conductor": "CU",
            "size": size,
            "max_amps": _CABLE_MAX_AMPS[size],
            "max_temp_f": 400,
            "voltage_drop_v_per_amp_per_1000ft": _CABLE_VDROP_BY_SIZE[size],
            "_source": _CABLE_SOURCE,
        })
    return cables


# ---------------------------------------------------------------------------
# VIGIL protectors — shaft HP and diameters are real (data sheet);
# thrust_capacity_lbs and max_temp_f are ESTIMATED (see docstring/report).
# (series, od, compatible_motor_series, shaft_hp_std, shaft_hp_high)
# ---------------------------------------------------------------------------
_VIGIL_SERIES = [
    ("300", 3.75, ["375"],               256, 410),
    ("400", 4.00, ["400"],               256, 410),
    ("500", 5.13, ["540", "544", "562", "513"], 637, 1019),
]
# Estimated thrust per type, by series (consistent with same-diameter catalog seals)
_VIGIL_THRUST = {
    "300": {"labyrinth": 6500,  "bag": 5000,  "combined": 8000},
    "400": {"labyrinth": 9000,  "bag": 7500,  "combined": 12000},
    "500": {"labyrinth": 18000, "bag": 15000, "combined": 22000},
}
_VIGIL_LENGTH = {"labyrinth": 3.8, "bag": 4.2, "combined": 5.5}
_VIGIL_MAX_TEMP_F = 400  # estimated (sheet gives no temperature rating)
_VIGIL_SOURCE = "ChampionX VIGIL data sheet (series/OD/shaft_hp real); thrust_capacity_lbs & max_temp_f ESTIMATED"


def build_seals() -> list[dict]:
    seals: list[dict] = []
    for series, od, compat, hp_std, hp_high in _VIGIL_SERIES:
        for stype in ("labyrinth", "bag", "combined"):
            seals.append({
                "manufacturer": _MANUFACTURER,
                "series": series,
                "model": f"VIGIL-{series}-{stype[:4].upper()}",
                "type": stype,
                "compatible_motor_series": compat,
                "od_inches": od,
                "length_ft": _VIGIL_LENGTH[stype],
                "thrust_capacity_lbs": _VIGIL_THRUST[series][stype],
                "max_temp_f": _VIGIL_MAX_TEMP_F,
                "shaft_hp_standard": hp_std,
                "shaft_hp_high_strength": hp_high,
                "_source": _VIGIL_SOURCE,
            })
    return seals


def _merge(path: Path, key: str, new_items: list[dict]) -> tuple[int, int]:
    """Replace ingestion-managed entries (those carrying _source) and re-add.

    Idempotent: catalog entries written by this script are tagged with
    ``_source``; previous fabricant entries (no ``_source``) are preserved.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    kept = [x for x in data[key] if "_source" not in x]
    data[key] = kept + new_items
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return len(kept), len(new_items)


def main() -> None:
    motors = build_motors()
    cables = build_cables()
    seals = build_seals()
    mk, mn = _merge(_MOTORS_JSON, "motors", motors)
    ck, cn = _merge(_CABLES_JSON, "cables", cables)
    sk, sn = _merge(_SEALS_JSON, "seals", seals)
    print(f"motors.json: {mk} previos + {mn} ingestados (AFFIRMED + PowerFit)")
    print(f"cables.json: {ck} previos + {cn} CAVALCADE")
    print(f"seals.json:  {sk} previos + {sn} VIGIL")
    hps = sorted({m["hp_rating"] for m in motors if m["manufacturer"] == _MANUFACTURER})
    print(f"  motores AFFIRMED: HP {hps[0]}–{hps[-1]} serie {_MOTOR_SERIES} "
          f"(od {_MOTOR_OD_IN}\") + PowerFit 208HP serie 420 (SLB)")
    print(f"  cables CAVALCADE: {[c['size'] for c in cables]} EPDM/400°F CU")
    print(f"  sellos VIGIL: series {[s for s,*_ in _VIGIL_SERIES]} × 3 tipos")


if __name__ == "__main__":
    main()
