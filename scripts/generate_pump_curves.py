"""
Synthetic pump-curve generator — catalog expansion.

Generates physically consistent performance curves for pumps whose exact
catalog data is not available in Brown Vol. 2b, and merges them into
catalogs/pumps.json (book pumps are never touched; generated models are
replaced in place on re-run, so the script is idempotent).

Methodology (standard centrifugal characteristic shape):

    head(x) = H_bep · (1.42 − 0.10·x − 0.32·x²)        x = q / q_bep
    eff(x)  = eff_bep · (1 − 0.85·(x − 1)²)
    hp(x)   = q · head / (135 770 · eff)                [water, SG = 1.0]

The HP curve is *derived* from hydraulic horsepower so that head, power and
efficiency are mutually consistent at every point. Curves span
0.50–1.45 × BEP (11 points); the recommended operating range sits inside.

These are REPRESENTATIVE curves: model designations follow each
manufacturer's product-line style but are not actual part numbers, and the
numbers must not be used for real field design.

Usage (from the project root):
    python scripts/generate_pump_curves.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_PUMPS_JSON = _ROOT / "catalogs" / "pumps.json"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Specs for generated pumps.
# head_bep [ft/stage] and eff_bep anchored to public product-line ranges;
# D-20 anchored to Brown Ex. #3B (231 stages / 41.25 hp → ~0.17 hp/stage).
# ---------------------------------------------------------------------------
GENERATED_SPECS: list[dict] = [
    {
        "manufacturer": "Reda", "series": "400", "model": "D-20",
        "od_inches": 4.0, "bep_flow_bpd": 600,
        "min_flow_bpd": 350, "max_flow_bpd": 800,
        "head_bep": 17.5, "eff_bep": 0.46,
        "max_stages": 300, "housing_options": [50, 100, 150, 200, 250, 300],
        "source": "Brown Vol. 2b Ex. #3B (hp/stage anchor); curve synthesized",
    },
    {
        "manufacturer": "Reda", "series": "540", "model": "GN-4000",
        "od_inches": 5.40, "bep_flow_bpd": 4000,
        "min_flow_bpd": 3000, "max_flow_bpd": 5200,
        "head_bep": 42.0, "eff_bep": 0.69,
        "max_stages": 140, "housing_options": [30, 50, 70, 90, 110, 140],
        "source": "Representative — REDA GN-series style",
    },
    {
        "manufacturer": "Reda", "series": "540", "model": "GN-5600",
        "od_inches": 5.40, "bep_flow_bpd": 5600,
        "min_flow_bpd": 4200, "max_flow_bpd": 7200,
        "head_bep": 47.0, "eff_bep": 0.71,
        "max_stages": 120, "housing_options": [30, 50, 70, 90, 110, 120],
        "source": "Representative — REDA GN-series style",
    },
    {
        "manufacturer": "Centrilift", "series": "513", "model": "GC-6100",
        "od_inches": 5.13, "bep_flow_bpd": 6100,
        "min_flow_bpd": 4600, "max_flow_bpd": 7900,
        "head_bep": 34.0, "eff_bep": 0.70,
        "max_stages": 160, "housing_options": [40, 60, 80, 100, 120, 140, 160],
        "source": "Representative — Centrilift GC-series style",
    },
    {
        "manufacturer": "Weatherford", "series": "400", "model": "WE-1350",
        "od_inches": 4.0, "bep_flow_bpd": 1350,
        "min_flow_bpd": 1050, "max_flow_bpd": 1750,
        "head_bep": 23.5, "eff_bep": 0.60,
        "max_stages": 240, "housing_options": [50, 75, 100, 125, 150, 200, 240],
        "source": "Representative — Weatherford ESP style",
    },
    {
        "manufacturer": "Weatherford", "series": "513", "model": "WE-2400",
        "od_inches": 5.13, "bep_flow_bpd": 2400,
        "min_flow_bpd": 1800, "max_flow_bpd": 3100,
        "head_bep": 30.0, "eff_bep": 0.66,
        "max_stages": 130, "housing_options": [30, 50, 70, 90, 110, 130],
        "source": "Representative — Weatherford ESP style",
    },
    {
        "manufacturer": "Weatherford", "series": "538", "model": "WE-5000",
        "od_inches": 5.38, "bep_flow_bpd": 5000,
        "min_flow_bpd": 3800, "max_flow_bpd": 6400,
        "head_bep": 44.0, "eff_bep": 0.70,
        "max_stages": 130, "housing_options": [30, 50, 70, 90, 110, 130],
        "source": "Representative — Weatherford ESP style",
    },
    # SLB High Rise (Oculus tech) — model names and flow ranges from the data
    # sheet; head/HP/efficiency curves SYNTHESIZED (the sheet has no curves).
    # min/max are the near-BEP recommended band (subset of the data-sheet range).
    {
        "manufacturer": "SLB", "series": "400", "model": "HighRise-UNB7.5",
        "od_inches": 4.00, "bep_flow_bpd": 700,
        "min_flow_bpd": 525, "max_flow_bpd": 910,
        "head_bep": 24.0, "eff_bep": 0.62,
        "max_stages": 300, "housing_options": [50, 100, 150, 200, 250, 300],
        "source": "SLB High Rise data sheet (flow range real; curve synthesized)",
    },
    {
        "manufacturer": "SLB", "series": "400", "model": "HighRise-UNB17.5",
        "od_inches": 4.00, "bep_flow_bpd": 1600,
        "min_flow_bpd": 1200, "max_flow_bpd": 2080,
        "head_bep": 30.0, "eff_bep": 0.68,
        "max_stages": 250, "housing_options": [50, 100, 150, 200, 250],
        "source": "SLB High Rise data sheet (flow range real; curve synthesized)",
    },
    {
        "manufacturer": "SLB", "series": "400", "model": "HighRise-Kronos",
        "od_inches": 4.00, "bep_flow_bpd": 1700,
        "min_flow_bpd": 1275, "max_flow_bpd": 2210,
        "head_bep": 31.0, "eff_bep": 0.68,
        "max_stages": 250, "housing_options": [50, 100, 150, 200, 250],
        "source": "SLB High Rise data sheet (flow range real; curve synthesized)",
    },
    {
        "manufacturer": "SLB", "series": "513", "model": "HighRise-UNB35",
        "od_inches": 5.13, "bep_flow_bpd": 2600,
        "min_flow_bpd": 1950, "max_flow_bpd": 3380,
        "head_bep": 38.0, "eff_bep": 0.71,
        "max_stages": 160, "housing_options": [40, 60, 80, 100, 120, 140, 160],
        "source": "SLB High Rise data sheet (flow range real; curve synthesized)",
    },
    {
        "manufacturer": "SLB", "series": "538", "model": "HighRise-UNB43",
        "od_inches": 5.38, "bep_flow_bpd": 3900,
        "min_flow_bpd": 2925, "max_flow_bpd": 5070,
        "head_bep": 44.0, "eff_bep": 0.72,
        "max_stages": 140, "housing_options": [30, 50, 70, 90, 110, 140],
        "source": "SLB High Rise data sheet (flow range real; curve synthesized)",
    },
    {
        "manufacturer": "SLB", "series": "538", "model": "HighRise-UNB60",
        "od_inches": 5.38, "bep_flow_bpd": 5200,
        "min_flow_bpd": 3900, "max_flow_bpd": 6760,
        "head_bep": 49.0, "eff_bep": 0.73,
        "max_stages": 120, "housing_options": [30, 50, 70, 90, 110, 120],
        "source": "SLB High Rise data sheet (flow range real; curve synthesized)",
    },
]

_X_MIN, _X_MAX, _N_POINTS = 0.50, 1.45, 11
_HHP_CONST = 135_770.0  # hp = q[bpd] · H[ft] · SG / 135 770


def _round_flow(q: float) -> int:
    """Round curve flows to a tidy step matched to magnitude."""
    step = 10 if q < 2000 else 50
    return int(round(q / step) * step)


def _head_shape(x: float) -> float:
    return 1.42 - 0.10 * x - 0.32 * x * x


def _eff_shape(x: float) -> float:
    return 1.0 - 0.85 * (x - 1.0) ** 2


def build_curve(spec: dict) -> list[dict]:
    q_bep = spec["bep_flow_bpd"]
    points: list[dict] = []
    seen: set[int] = set()
    for i in range(_N_POINTS):
        x = _X_MIN + (_X_MAX - _X_MIN) * i / (_N_POINTS - 1)
        q = _round_flow(x * q_bep)
        if q in seen:  # rounding collision on small pumps
            continue
        seen.add(q)
        x_eff = q / q_bep
        head = spec["head_bep"] * _head_shape(x_eff)
        eff = spec["eff_bep"] * _eff_shape(x_eff)
        hp = q * head / (_HHP_CONST * eff)
        points.append({
            "flow_bpd": q,
            "head_ft_per_stage": round(head, 1),
            "hp_per_stage": round(hp, 3),
            "efficiency": round(eff, 3),
        })
    return points


def build_pump(spec: dict) -> dict:
    return {
        "manufacturer": spec["manufacturer"],
        "series": spec["series"],
        "model": spec["model"],
        "od_inches": spec["od_inches"],
        "min_flow_bpd": spec["min_flow_bpd"],
        "max_flow_bpd": spec["max_flow_bpd"],
        "bep_flow_bpd": spec["bep_flow_bpd"],
        "max_stages": spec["max_stages"],
        "housing_options": spec["housing_options"],
        "_source": spec["source"],
        "performance_curve": build_curve(spec),
    }


def main() -> None:
    data = json.loads(_PUMPS_JSON.read_text(encoding="utf-8"))
    generated_models = {s["model"] for s in GENERATED_SPECS}

    kept = [p for p in data["pumps"] if p["model"] not in generated_models]
    new = [build_pump(s) for s in GENERATED_SPECS]
    data["pumps"] = kept + new

    data["_note"] = (
        "Two data classes: (1) pumps digitized from Kermit Brown Vol. 2b "
        "Ch. 4.5 examples; (2) pumps generated by scripts/generate_pump_curves.py "
        "(marked with _source) — representative curves with standard centrifugal "
        "shape, HP derived from hydraulic horsepower for thermodynamic "
        "consistency. Representative data: NOT for real field design."
    )

    _PUMPS_JSON.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"pumps.json actualizado: {len(kept)} existentes + {len(new)} generadas")
    for p in new:
        pc = p["performance_curve"]
        hps = [pt["hp_per_stage"] for pt in pc]
        heads = [pt["head_ft_per_stage"] for pt in pc]
        assert all(heads[i] > heads[i + 1] for i in range(len(heads) - 1)), p["model"]
        print(
            f"  {p['manufacturer']:11s} {p['model']:8s} serie {p['series']} "
            f"od={p['od_inches']}\"  rango {p['min_flow_bpd']}–{p['max_flow_bpd']} "
            f"bep={p['bep_flow_bpd']}  head@bep={pc[0]['head_ft_per_stage']:.0f}→"
            f"{pc[-1]['head_ft_per_stage']:.0f} ft  hp {min(hps):.3f}–{max(hps):.3f}  "
            f"({len(pc)} pts)"
        )


if __name__ == "__main__":
    main()
