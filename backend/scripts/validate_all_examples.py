"""
Validation script — BES Designer Phase 12.

Runs every example in data/example_wells.json through the full design engine,
compares TDH / stages / HP to the analytical book-reference values stored in
the JSON, and writes a Markdown comparison table to docs/VALIDATION.md.

Usage (from the project root):
    python scripts/validate_all_examples.py
"""
from __future__ import annotations

import json
import sys
import warnings
from datetime import date
from pathlib import Path

# `bes` se importa por el editable install (pip install -e backend/), no por
# manipular sys.path — ver .claude/rules/architecture.md.
_BACKEND = Path(__file__).parent.parent

# Windows consoles default to cp1252, which cannot print ✅/❌
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bes.catalogs.loader import CatalogManager                          # noqa: E402
from bes.core.models import (                                            # noqa: E402
    DesignObjectives,
    DriveMechanism,
    Fluid,
    IPRMethod,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)
from bes.recommender.recommendation_engine import generate_recommendations  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_EXAMPLES_JSON = _BACKEND / "data" / "example_wells.json"
# docs/ es del proyecto, no del backend: vive en la raíz del repo.
_DOCS_DIR      = _BACKEND.parent / "docs"
_OUTPUT_MD     = _DOCS_DIR / "VALIDATION.md"

# ---------------------------------------------------------------------------
# Status thresholds
# ---------------------------------------------------------------------------
_TDH_WARN   = 0.10   # ±10 %  → ✅
_TDH_FAIL   = 0.20   # ±20 %  → ⚠️  (beyond → ❌)
_STAGE_WARN = 0.15   # ±15 %  → ✅
_STAGE_FAIL = 0.30   # ±30 %  → ⚠️
_HP_WARN    = 0.15   # ±15 %  → ✅
_HP_FAIL    = 0.30   # ±30 %  → ⚠️


def _status(delta_pct: float, warn_thr: float, fail_thr: float) -> str:
    adelta = abs(delta_pct)
    if adelta <= warn_thr:
        return "✅"
    if adelta <= fail_thr:
        return "⚠️"
    return "❌"


def _load_examples() -> dict:
    with open(_EXAMPLES_JSON, encoding="utf-8") as fh:
        raw = json.load(fh)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _build_dataclasses(ex: dict):
    r = ex["reservoir"]
    f = ex["fluid"]
    w = ex["well"]
    s = ex["surface"]
    o = ex["objectives"]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        reservoir = Reservoir(
            static_pressure=r["static_pressure"],
            bubble_point=r["bubble_point"],
            ipr_method=IPRMethod[r["ipr_method"]],
            reservoir_temp=r["reservoir_temp"],
            drive_mechanism=DriveMechanism[r["drive_mechanism"]],
            datum_depth=r["datum_depth"],
            test_pwf=r.get("test_pwf"),
            test_rate=r.get("test_rate"),
            productivity_index=r.get("productivity_index"),
            fetkovich_c=r.get("fetkovich_c"),
            fetkovich_n=r.get("fetkovich_n"),
        )

    fluid = Fluid(
        oil_api=f["oil_api"],
        water_cut=f["water_cut"],
        gor=f["gor"],
        gas_sg=f["gas_sg"],
        water_sg=f["water_sg"],
        oil_viscosity_dead=f["oil_viscosity_dead"],
        viscosity_temp_ref=f["viscosity_temp_ref"],
        bubble_point_pressure=f["bubble_point_pressure"],
        h2s_content=f["h2s_content"],
        co2_content=f["co2_content"],
        sand_production=f["sand_production"],
    )

    well = WellGeometry(
        total_depth=w["total_depth"],
        casing_od=w["casing_od"],
        casing_weight=w["casing_weight"],
        casing_id=w["casing_id"],
        tubing_od=w["tubing_od"],
        tubing_id=w["tubing_id"],
        perforations_top=w["perforations_top"],
        perforations_bottom=w["perforations_bottom"],
        deviation_max=w["deviation_max"],
        wellhead_temp=w["wellhead_temp"],
        bottom_hole_temp=w["bottom_hole_temp"],
    )

    surface = SurfaceConditions(
        wellhead_pressure_required=s["wellhead_pressure_required"],
        flowline_length=s["flowline_length"],
        flowline_id=s["flowline_id"],
        flowline_elevation_change=s["flowline_elevation_change"],
        separator_pressure=s["separator_pressure"],
        power_supply_voltage=s["power_supply_voltage"],
        frequency=s["frequency"],
    )

    objectives = DesignObjectives(
        target_flow_rate=o["target_flow_rate"],
        safety_margin_depth=o["safety_margin_depth"],
        allow_gas_venting=o["allow_gas_venting"],
        max_gip=o["max_gip"],
        design_life_years=o["design_life_years"],
        use_vsd=o["use_vsd"],
        gas_fraction_pc_threshold=o.get("gas_fraction_pc_threshold", 0.10),
    )

    return reservoir, fluid, well, surface, objectives


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("BES Designer — Validation against book examples")
    print("=" * 60)

    catalog = CatalogManager()
    examples = _load_examples()

    rows: list[dict] = []

    for name, ex in examples.items():
        label = name.upper().replace("_", " ")
        desc  = ex.get("description", "")
        ref   = ex["book_reference"]

        # Increment-method examples (e.g. #3A Brown) have no whole-well
        # tdh/stages/hp; they are validated by dedicated unit tests instead.
        if "tdh_ft" not in ref:
            print(f"\nSkipping {label}: {desc}")
            print("  (increment-method example — validated in tests, not whole-well)")
            continue

        print(f"\nRunning {label}: {desc}")

        try:
            res, flu, wel, sur, obj = _build_dataclasses(ex)
            results = generate_recommendations(
                reservoir=res,
                fluid=flu,
                well=wel,
                surface=sur,
                objectives=obj,
                catalog=catalog,
                n=3,
            )
        except Exception as exc:
            print(f"  ERROR: {exc}")
            rows.append({
                "name": label,
                "description": desc,
                "tdh_ref": ref["tdh_ft"],
                "tdh_app": "ERROR",
                "tdh_pct": "—",
                "stages_ref": ref["stages"],
                "stages_app": "ERROR",
                "stages_pct": "—",
                "hp_ref": ref["total_hp"],
                "hp_app": "ERROR",
                "hp_pct": "—",
                "pump": "—",
                "status": "❌",
                "warnings": str(exc),
            })
            continue

        # Validate against the book's pump (not the beauty-contest winner): as
        # the catalog grows with modern pumps a newer model may out-rank the
        # 1980 textbook pump; the engine's correctness is checked on Brown's pump.
        _want = ref.get("expected_pump")
        dr = next(
            (rec["design"] for rec in results["recommendations"]
             if rec["design"].pump_model == _want),
            results["recommendations"][0]["design"],
        )
        tdh_app    = dr.total_head_required
        stages_app = dr.num_stages
        hp_app     = dr.total_pump_hp
        pump_model = dr.pump_model

        tdh_pct    = (tdh_app    - ref["tdh_ft"])   / ref["tdh_ft"]    * 100
        stages_pct = (stages_app - ref["stages"])    / ref["stages"]    * 100
        hp_pct     = (hp_app     - ref["total_hp"])  / ref["total_hp"]  * 100

        tdh_st    = _status(tdh_pct    / 100, _TDH_WARN,   _TDH_FAIL)
        stage_st  = _status(stages_pct / 100, _STAGE_WARN, _STAGE_FAIL)
        hp_st     = _status(hp_pct     / 100, _HP_WARN,    _HP_FAIL)

        # Overall status = worst of the three
        order = {"✅": 0, "⚠️": 1, "❌": 2}
        overall = max([tdh_st, stage_st, hp_st], key=lambda s: order[s])

        warn_msgs = dr.warnings[:2]  # first 2 warnings for brevity

        print(f"  Pump:   {pump_model}")
        print(f"  TDH:    {tdh_app:.0f} ft  (ref {ref['tdh_ft']} ft, {tdh_pct:+.1f}%) {tdh_st}")
        print(f"  Stages: {stages_app}  (ref {ref['stages']}, {stages_pct:+.1f}%) {stage_st}")
        print(f"  HP:     {hp_app:.1f}  (ref {ref['total_hp']}, {hp_pct:+.1f}%) {hp_st}")
        if warn_msgs:
            print(f"  Warnings: {'; '.join(warn_msgs)}")

        rows.append({
            "name": label,
            "description": desc,
            "tdh_ref": ref["tdh_ft"],
            "tdh_app": f"{tdh_app:.0f}",
            "tdh_pct": f"{tdh_pct:+.1f}%",
            "tdh_st": tdh_st,
            "stages_ref": ref["stages"],
            "stages_app": str(stages_app),
            "stages_pct": f"{stages_pct:+.1f}%",
            "stage_st": stage_st,
            "hp_ref": ref["total_hp"],
            "hp_app": f"{hp_app:.1f}",
            "hp_pct": f"{hp_pct:+.1f}%",
            "hp_st": hp_st,
            "pump": pump_model,
            "status": overall,
            "warnings": "; ".join(warn_msgs) if warn_msgs else "—",
        })

    # -----------------------------------------------------------------------
    # Write VALIDATION.md
    # -----------------------------------------------------------------------
    _DOCS_DIR.mkdir(parents=True, exist_ok=True)

    legend = (
        "✅ within tolerance · "
        "⚠️ marginal (TDH ±10–20 %, stages/HP ±15–30 %) · "
        "❌ outside tolerance"
    )

    lines: list[str] = [
        "# BES Designer — Validación contra Ejemplos del Libro",
        "",
        f"**Generado:** {date.today().isoformat()}  ",
        "**Referencia:** Kermit Brown, *The Technology of Artificial Lift Methods*, Vol. 2b, Ch. 4.5",
        "",
        "> Los valores de referencia son estimaciones analíticas basadas en las mismas ecuaciones",
        "> del motor de cálculo (TDH por Hazen-Williams, etapas por interpolación de curva).",
        "> Las diferencias se deben principalmente a la correlación Hagedorn-Brown para el PIP",
        "> y a la redondeo de etapas según las opciones de housing del catálogo.",
        "",
        "## Leyenda",
        "",
        f"> {legend}",
        "",
        "## Tabla Comparativa",
        "",
        "| Ejemplo | TDH Libro (ft) | TDH App (ft) | Δ TDH | "
        "Etapas Libro | Etapas App | Δ Etapas | "
        "HP Libro | HP App | Δ HP | "
        "Bomba Seleccionada | Status |",
        "|---------|---------------|-------------|-------|"
        "------------|-----------|----------|"
        "---------|--------|------|"
        "-------------------|--------|",
    ]

    for r in rows:
        if r["tdh_app"] == "ERROR":
            line = (
                f"| {r['name']} | {r['tdh_ref']} | ERROR | — | "
                f"{r['stages_ref']} | ERROR | — | "
                f"{r['hp_ref']} | ERROR | — | — | ❌ |"
            )
        else:
            line = (
                f"| {r['name']} "
                f"| {r['tdh_ref']} | {r['tdh_app']} | {r['tdh_pct']} {r['tdh_st']} "
                f"| {r['stages_ref']} | {r['stages_app']} | {r['stages_pct']} {r['stage_st']} "
                f"| {r['hp_ref']} | {r['hp_app']} | {r['hp_pct']} {r['hp_st']} "
                f"| {r['pump']} | {r['status']} |"
            )
        lines.append(line)

    lines += [
        "",
        "## Detalle por Ejemplo",
        "",
    ]
    for r in rows:
        lines.append(f"### {r['name']}")
        lines.append("")
        lines.append(f"*{r['description']}*")
        lines.append("")
        if r["tdh_app"] != "ERROR":
            lines.append(f"- **Bomba seleccionada:** {r['pump']}")
            lines.append(f"- **TDH:** {r['tdh_app']} ft vs. {r['tdh_ref']} ft libro ({r['tdh_pct']})")
            lines.append(f"- **Etapas:** {r['stages_app']} vs. {r['stages_ref']} libro ({r['stages_pct']})")
            lines.append(f"- **HP total bomba:** {r['hp_app']} vs. {r['hp_ref']} libro ({r['hp_pct']})")
            lines.append(f"- **Advertencias de diseño:** {r['warnings']}")
        else:
            lines.append(f"- **ERROR:** {r['warnings']}")
        lines.append("")

    lines += [
        "---",
        "",
        "## Notas Metodológicas",
        "",
        "1. **PIP (Pump Intake Pressure):** el motor de cálculo usa la correlación de Hagedorn-Brown",
        "   para el traverse de presión multifásico. Los valores de referencia usan la columna",
        "   hidrostática simple (ΔP = SG · 0.433 · Δh), de allí la diferencia en TDH.",
        "",
        "2. **Profundidad de bomba:** el selector ubica la bomba safety_margin_depth por encima",
        "   del tope de perforaciones (pump_setting_depth = perforations_top − safety_margin_depth).",
        "",
        "3. **Etapas:** se calculan exactamente (ceil(TDH / head_per_stage)); el número puede",
        "   diferir del libro si el catálogo tiene una curva diferente.",
        "",
        "4. **HP:** corregido por SG del fluido producido (hp_total = stages × hp/stage × SG).",
        "",
        "5. **Catálogos aproximados:** los catálogos incluidos son representativos, no idénticos",
        "   a los del libro original. Diferencias de ±15–30 % son esperables.",
    ]

    _OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{'=' * 60}")
    print(f"VALIDATION.md guardado en: {_OUTPUT_MD}")


if __name__ == "__main__":
    main()
