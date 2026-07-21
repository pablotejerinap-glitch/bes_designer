# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Rediseño de arquitectura en curso (rama refactor/architecture-redesign)

Migramos el monolito Streamlit a una arquitectura de tres capas
(frontend React / backend FastAPI / DB SQLite). Reglas y convenciones del
rediseño (leerlas antes de tocar código de arquitectura):

@.claude/rules/architecture.md
@.claude/rules/domain.md
@.claude/rules/api-contract.md
@.claude/rules/frontend.md

Skills del proyecto (invocables): `run`, `add-endpoint`, `add-domain-function`.
Plan completo: `C:\Users\maria\.claude\plans\quiet-stargazing-scott.md`.

**Entorno:** venv en `.venv` (Python 3.14). Usar `.venv\Scripts\python.exe`
(no hay `python`/`pip` en PATH). El proyecto está instalado editable
(`pip install -e .`) — imports absolutos, **sin `sys.path.insert`**.

## Commands

```bash
# Todos los comandos usan el intérprete del venv: .venv\Scripts\python.exe
# Los de Python se corren desde backend/ (ahí viven pyproject.toml y tests/).

# Run all tests
pytest

# Run a single test file
pytest tests/test_pump_design.py

# Run a single test class or function
pytest tests/test_pump_design.py::TestCalculateStages
pytest tests/test_pump_design.py::TestCalculateStages::test_example_2a_d40_254_stages

# Launch the FastAPI backend (required by the SPA)
python -m uvicorn bes.api.main:app --reload --port 8000

# Launch the React SPA (dev)
cd frontend && npm run dev

# Everything at once
docker compose up --build

# Validate all book examples end-to-end
python scripts/validate_all_examples.py
```

No linter or formatter is configured. `requirements.txt` lists all dependencies (numpy, scipy, pandas, matplotlib, plotly, reportlab, openpyxl, pytest).

## Architecture

**BES Designer** automatiza el diseño de sistemas de Bombeo Electrosumergible (ESP/BES) siguiendo la metodología de Kermit Brown, *The Technology of Artificial Lift Methods*, Vol. 2b, Cap. 4.5. Todos los cálculos se validan contra los ejemplos numerados del libro.

### Repository layout

Dos carpetas de primer nivel, cada una desplegable por separado. Adentro de
`backend/` el layout es `src/` y el único paquete distribuible es `bes`:

```
backend/            todo el Python — unidad de despliegue autocontenida
  src/bes/          paquete único distribuible (pip install -e backend/)
    core/           dominio puro — sin frameworks
    catalogs/       catálogos JSON + queries (los .json viajan con el paquete)
    recommender/    selección y ordenamiento por criterios
    reports/        PDF / Excel
    services/       orquestación agnóstica de framework
    plotting/       builders Plotly — agnósticos, los consume la API
    api/            capa de entrega HTTP (FastAPI)
  tests/ data/ scripts/
  pyproject.toml  requirements*.txt  Dockerfile
frontend/           SPA React (Vite + TS + Mantine)
docker-compose.yml · docs/ · README.md · CLAUDE.md   ← nivel proyecto
```

`bes.api` y `frontend/` son **adaptadores de entrega**; el dominio vive debajo
y no depende de ninguno. La app Streamlit se retiró al alcanzar React paridad.

### Data flow

```
User inputs (Reservoir, Fluid, WellGeometry, SurfaceConditions, DesignObjectives)
    │
    ├─ bes/core/ipr.py          → Pwf at perforations (Vogel / Linear / Fetkovich / Combined)
    ├─ bes/core/pvt.py          → PVT properties at pressure/temperature (Standing, DAK, Beggs-Robinson)
    ├─ bes/core/multiphase.py   → calculate_pip()  — pressure traverse annulus → pump depth
    │                             calculate_discharge_pressure() — traverse tubing to surface
    ├─ bes/core/tdh.py          → calculate_tdh()  — TDH = Vertical Lift + Friction + WHP head
    ├─ bes/core/pump_design.py  → design_pump_complete() — filter catalog, stage count, HP for every pump
    ├─ bes/core/electrical.py   → electrical_design_complete() — motor → cable → transformer
    ├─ bes/core/gas_handling.py → complete_gas_design() — GIP, pressure-increment design, separator rec.
    │
    ├─ bes/recommender/
    │      pump_selector.py        → select_top_n_pumps() — runs hydraulic + electrical, orders by engineering criteria
    │      ranking.py              → bep_distance() / ranking_key() / classify_bep_distance() — no scores, no weights
    │      recommendation_engine.py → generate_recommendations() — top-level API
    │
    └─ bes/services/               → orquestación agnóstica de framework (números crudos, no UI)
           nodal_service.py        → run_nodal_analysis()
           sensitivity_service.py  → run_sensitivity()
           case_bundle.py          → case_bundle_json() — formato guardar/abrir (futuro DB)
```

La capa `bes.services` es la fuente única de verdad detrás de la API FastAPI.
No importa ningún framework. Ver `.claude/rules/architecture.md`.

`bes.api` llama a `generate_recommendations()`; el front solo renderiza. `bes.reports` genera PDF y Excel, `bes.plotting` las figuras.

### Key models (`bes/core/models.py`)

All inputs are dataclasses with `__post_init__` validation:
- `Reservoir`, `Fluid`, `WellGeometry`, `SurfaceConditions`, `DesignObjectives` — inputs
- `PumpCurve`, `PumpPerformancePoint` — catalog types
- `DesignResult` — the single output object that flows into the UI and reports

### Catalog system (`bes/catalogs/`)

JSON files (`pumps.json`, `motors.json`, `cables.json`, `seals.json`) loaded once by `CatalogManager`. Key query methods:
- `get_pumps_by_casing(casing_id_in)` — filters `pump.od < casing_id`
- `get_pumps_by_flow_range(flow_bpd)` — filters `min_flow ≤ q ≤ max_flow`
- `interpolate_pump_curve(pump, flow_bpd)` — linear interpolation → `{head_per_stage, hp_per_stage, efficiency}`
- `get_motor(hp, voltage, series)` — smallest HP ≥ required, closest voltage
- `get_cable(amps, temp_f, voltage)` — lowest voltage-drop cable meeting ampacity and temperature

### Units convention

| Quantity | Unit |
|---|---|
| Pressure | psia (differentials in psi) |
| Temperature | °F |
| Flow rates | STB/d (surface) or bpd |
| Depths / lengths | ft TVD or ft MD |
| Diameters | inches |
| Power | hp |
| Voltage / current | V / A |

### TDH formula (Brown §4.5324)

```
TDH = Vertical Lift + Tubing Friction + Wellhead Pressure Head

Vertical Lift          = pump_depth − (PIP × 2.31 / SG_liquid)
Tubing Friction        = Hazen-Williams: 0.2083 × (100/C)^1.852 × q_gpm^1.852 / d^4.8655 × L/100
Wellhead Pressure Head = Pwh × 2.31 / SG_liquid
```

`hp/stage` catalog values are rated for water (SG = 1.0); multiply by `sg_fluid` for actual fluid HP.

### Engineering-criteria ordering (no scoring)

`bes/recommender/ranking.py`: alternatives are ordered by a strict lexicographic key — (1) BEP distance `|q − q_BEP| / q_BEP` ascending, (2) pump efficiency descending, (3) required shaft HP ascending. There are **no weighted scores, no 0–10 scales, and no provider preference**; the manufacturer is informational only (`DesignObjectives` has no provider field). `classify_bep_distance()` labels the BEP distance for display only (≤10 % óptimo / ≤25 % aceptable / >25 % alejado) and never affects the ordering. Each recommendation carries a `criteria` dict with the raw values and a natural-language `rationale` built exclusively from calculated data. The former weighted scoring system (efficiency 40 % / flexibility 30 % / provider 30 %) was removed — see `REFORMA_COMPARACION_BES.docx`.

The API exposes this as `RecommendationSchema.criteria` (`CriteriaSchema`) and `DesignResponse.ordering_criteria`; there is no `score`, `metrics` or `weights` field.

### Book examples used as regression tests

| Example | Pump | Flow (bpd) | TDH (ft) | Stages | HP |
|---|---|---|---|---|---|
| #1A | Centrilift I-300 | 10 000 | 1 670 | 28 | 180 |
| #2A | Reda D-40 | 1 227 | 5 830 | 254 | ≈79 |
| #2B | Centrilift I-42B | ~2 080 | 4 258 | 112 | ≈65 |
| Friction | 5" new pipe | 10 000 | ≈18.5 ft/1 000 ft | — | — |

Tests live in `tests/test_pump_design.py`. When adding new calculations, validate against a Brown example and add a corresponding test.

### pump_setting_depth convention

`select_top_n_pumps()` in `bes/recommender/pump_selector.py` sets `pump_setting_depth = max(well.perforations_top − objectives.safety_margin_depth, 100 ft)` and passes it through to the electrical design (cable length). `electrical_design_complete()` accepts an optional `pump_depth`; when omitted it falls back to the legacy proxy `total_depth × 0.80`. For a custom depth, pass it explicitly to `design_pump_complete()` or `calculate_tdh()`.
