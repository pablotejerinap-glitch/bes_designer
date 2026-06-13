"""
ChampionX catalog ingestion — Fase A (motores AFFIRMED + cables CAVALCADE).

Transcribe las tablas de especificaciones de las hojas de datos de ChampionX
(UNBRIDLED ESP Systems) a los catálogos JSON existentes, sin tocar ninguna
entrada previa. Es idempotente: en cada corrida elimina las entradas
ChampionX que él mismo agregó y las vuelve a escribir.

Fuentes (carpeta del usuario, no versionadas en el repo):
  - affirmed-submersible-motor-ps.pdf  → tabla "AFFIRMED Motor Specifications"
  - UNBRIDLED_CAVALCADE_Cable_Solution_Sheet_0321.pdf → tabla de cables

Decisiones de digitalización (ver docs/CHAMPIONX_INGESTION_REPORT.md):
  - Serie/OD: las hojas VIGIL y WHIRLAWAY de ChampionX declaran "400 series =
    4.00 in", así que los motores AFFIRMED 400-series se cargan con
    series="400", od_inches=4.00 (convención del proyecto: serie = OD×100).
  - max_temp_f = 325 °F: temperatura de fondo a plena carga de la hoja (la
    temperatura de operación del motor, 400 °F, no es la que limita la
    selección).
  - Filas UT/CT: UT y CT comparten especificaciones eléctricas; se carga una
    entrada por combinación (HP, voltaje) para no duplicar.
  - Cables CAVALCADE: la hoja da calibre/aislación/temperatura pero NO
    ampacidad ni caída de tensión. Esos valores son función física del
    conductor (AWG) y se reusan, idénticos, de los cables del mismo calibre ya
    presentes en el catálogo (estándar API RP 11S6 / Brown Tabla 4.52). El
    calibre 1/0 de la hoja se posterga: requiere refactorizar el cálculo de
    caída de tensión (hoy tabla fija en core/electrical.py).

Uso (desde la raíz del proyecto):
    python scripts/ingest_championx.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_MOTORS_JSON = _ROOT / "catalogs" / "motors.json"
_CABLES_JSON = _ROOT / "catalogs" / "cables.json"

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
    return motors


# ---------------------------------------------------------------------------
# CAVALCADE power cable — EPDM/lead, 400 °F, solid copper, 5 kV.
# Ampacidad y caída de tensión reusadas del calibre equivalente del catálogo
# (constante física por AWG). Calibre 1/0 pospuesto (ver docstring).
# ---------------------------------------------------------------------------
_CABLE_VDROP_BY_SIZE = {
    "#2": {"100": 0.297, "150": 0.324, "180": 0.341, "200": 0.354},
    "#4": {"100": 0.473, "150": 0.516, "180": 0.543, "200": 0.562},
    "#6": {"100": 0.752, "150": 0.820, "180": 0.863, "200": 0.894},
}
_CABLE_MAX_AMPS = {"#2": 88, "#4": 69, "#6": 55}
_CABLE_SOURCE = "ChampionX CAVALCADE data sheet (EPDM/lead, 400°F); ampacity & vdrop per-AWG std (API RP 11S6)"


def build_cables() -> list[dict]:
    cables: list[dict] = []
    for size in ("#2", "#4", "#6"):
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


def _merge(path: Path, key: str, new_items: list[dict]) -> tuple[int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    kept = [x for x in data[key] if x.get("manufacturer") != _MANUFACTURER]
    data[key] = kept + new_items
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return len(kept), len(new_items)


def main() -> None:
    motors = build_motors()
    cables = build_cables()
    mk, mn = _merge(_MOTORS_JSON, "motors", motors)
    ck, cn = _merge(_CABLES_JSON, "cables", cables)
    print(f"motors.json: {mk} previos + {mn} ChampionX AFFIRMED")
    print(f"cables.json: {ck} previos + {cn} ChampionX CAVALCADE")
    hps = sorted({m["hp_rating"] for m in motors})
    print(f"  motores AFFIRMED: {len(motors)} entradas, HP {hps[0]}–{hps[-1]}, "
          f"serie {_MOTOR_SERIES} (od {_MOTOR_OD_IN}\"), {_MOTOR_MAX_TEMP_F}°F")
    print(f"  cables CAVALCADE: {[c['size'] for c in cables]} EPDM/400°F CU")


if __name__ == "__main__":
    main()
