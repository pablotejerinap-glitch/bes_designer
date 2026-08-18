# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Arquitectura de tres capas

El monolito Streamlit se migró a tres capas (frontend React / backend FastAPI /
DB SQLite) y la app Streamlit se retiró. Reglas y convenciones (leerlas antes
de tocar código de arquitectura):

@.claude/rules/architecture.md
@.claude/rules/domain.md
@.claude/rules/api-contract.md
@.claude/rules/frontend.md

Skills del proyecto (invocables): `run`, `add-endpoint`, `add-domain-function`.

**Entorno:** venv en `.venv` (Python 3.14). Usar `.venv\Scripts\python.exe`
(no hay `python`/`pip` en PATH). El backend se instala editable con
`.venv\Scripts\python.exe -m pip install -e backend` — imports absolutos al
paquete `bes`, **sin `sys.path.insert`**. El frontend necesita `npm install`
en `frontend/`.

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

# Validate all book examples end-to-end (regenera docs/VALIDATION.md)
python scripts/validate_all_examples.py

# Typecheck del frontend (desde frontend/)
npx tsc --noEmit

# Regenerar el contrato tipado tras cambiar un schema Pydantic:
#   backend/  python -c "import json;from bes.api.main import app;
#             open('../frontend/openapi.json','w',encoding='utf-8',newline='').write(
#             json.dumps(app.openapi(),separators=(',',':'),ensure_ascii=False))"
#   frontend/ npm run gen:api
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
    ├─ bes/core/ipr.py          → Pwf at perforations (Vogel / Linear / Fetkovich)
    ├─ bes/core/pvt.py          → PVT properties at pressure/temperature (Standing, DAK, Beggs-Robinson)
    ├─ bes/core/multiphase.py   → Poettmann & Carpenter (1952) — ÚNICA correlación multifásica
    │                             calculate_pip()  — pressure traverse annulus → pump depth
    │                             calculate_discharge_pressure() — traverse tubing to surface
    ├─ bes/core/tdh.py          → calculate_tdh()  — TDH = Vertical Lift + Friction + WHP head
    │                             La fricción se calcula con Hazen-Williams o con
    │                             Poettmann-Carpenter según la fracción de gas libre
    │                             en la admisión (ver más abajo)
    ├─ bes/core/pump_design.py  → design_pump_complete() — filter catalog, stage count, HP for every pump
    ├─ bes/core/viscosity.py    → crudos viscosos (< 28 °API). Dos métodos:
    │                             Riling (Brown §4.53112, tablas 4.520/4.521) es el
    │                             camino principal — no necesita saber qué bomba es,
    │                             así que filtra el catálogo invirtiendo el sentido.
    │                             Hydraulic Institute / Turzo (Takács §4.2.2) verifica
    │                             la bomba ya elegida y devuelve la curva corregida.
    │                             Ver .claude/rules/domain.md antes de tocarlo.
    ├─ bes/core/affinity.py     → leyes de afinidad (Q∝N·D, H∝N²·D², HP∝N³·D³·SG)
    │                             sección aparte: no interviene en el diseño
    ├─ bes/core/viscosity.py    → crudos viscosos: procedimiento de Riling §4.53112
    │                             corte en 28 °API; arriba no se corrige nada
    ├─ bes/core/mechanical.py   → verificación de eje y cojinete + tope de etapas
    ├─ bes/core/housing.py      → optimize_housings() — mejor combinación de carcasas
    │                             con la presión como restricción dura (ver más abajo)
    ├─ bes/core/electrical.py   → electrical_design_complete() — motor → cable → transformer
    ├─ bes/core/gas_handling.py → complete_gas_design() — GIP, pressure-increment design, separator rec.
    │                             pressure_increment_design() resuelve la bomba
    │                             tramo por tramo (ver "Método de incrementos")
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

### Correlación multifásica única: Poettmann & Carpenter

`bes/core/multiphase.py` implementa **solo** Poettmann & Carpenter (1952). Las
otras tres correlaciones que tuvo el módulo (Hagedorn-Brown, Beggs-Brill,
Duns & Ros) se retiraron: la tesis calcula todas las pérdidas de carga por P&C.
Consecuencias:

- `pressure_traverse()` ya **no** recibe `method` ni `direction` (el sentido se
  deduce de `depth_start`/`depth_end`).
- `nodal_analysis.compare_methods()` y `plotting.plot_nodal_comparison()` se
  eliminaron; `NodalRequest` perdió `method` y `compare_all`, y `NodalResponse`
  perdió `mode` y `comparison`.
- El módulo expone `METHOD_KEY` / `METHOD_LABEL` (en `nodal_analysis`) como
  única fuente del nombre de la correlación.

**No volver a agregar correlaciones** sin que Pablo lo pida explícitamente.

Consecuencia asumida y documentada: los ejemplos del libro que Brown resuelve con
Hagedorn-Brown no se reproducen exactamente. En el **#3B** (§4.53104) la presión
de descarga da 1120 psi contra 1300 impresos, y de ahí 175 etapas contra 209. El
método de incrementos en sí es correcto —alimentado con los 1300 psi del libro da
204 etapas y 26 hp—; el desvío entra íntegro por el paso 1. Ver
`docs/EJEMPLO_3B_BROWN.md`, que también deja anotados dos defectos abiertos del
método (el último escalón queda con el resto de la división, y sin
`fixed_pump_model` se arman sartas de 3-4 modelos distintos que no se pueden
construir).

### Método de incrementos de presión (`bes/core/gas_handling.py`)

Procedimiento de Brown Vol. 2b §4.53103 para pozos **con gas libre**: con gas
el caudal volumétrico **no** es constante a lo largo de la bomba —el gas se
comprime y parte pasa a solución—, así que la bomba se resuelve tramo por tramo
en lugar de con un caudal único.

- **Se evalúa en los DOS extremos de cada intervalo y se promedia**, que es lo
  que hace el libro (pasos 4 y 5: *Find average gradient* / *Find average
  volume*). No en el punto medio: Bg va con 1/P, así que
  `f((P₁+P₂)/2) ≠ (f(P₁)+f(P₂))/2`. Además los extremos son lo único que
  permite publicar la tabla con caudal de entrada y de salida.
- **Una sola bomba para toda la sarta**, elegida sobre el caudal de mezcla
  representativo (paso 6 del libro: elige una Reda D-40 y con esa sigue). Antes
  se re-seleccionaba por incremento y salían sartas de 3-4 modelos que no se
  pueden construir y que mezclaban fabricantes. El catálogo se filtra por
  `casing_id`.
- **Viscosidad por intervalo** (Riling, §4.53112): el gas en solución cambia con
  la presión y la viscosidad del crudo vivo con él, así que cada tramo ve un
  fluido distinto. Crudo ≥ 28 °API → factores unitarios, no toca nada.
- **`increment_psi` es configurable** (25/50/100/200 psi…). Las etapas se
  acumulan como fracción y se redondean **una sola vez al final**;
  `total_stages_longhand` conserva la suma de redondear cada tramo, que es la
  convención del cálculo a mano.
- La masa se conserva (`mass_rate_lbm_d`): es el invariante de control del
  método, y el test lo verifica entre extremos.

**Es un camino de diseño completo, no un cálculo aislado.**
`gas_service.run_gas_design_complete()` va del pozo al aparejo: IPR → PIP →
presión de descarga → incrementos → bomba → carcasas → motor → sello → cable →
transformador → VSD. El armado usa `pump_selector.assemble_design()`, **la
misma** función que el camino convencional, así que la regla de no mezclar
fabricantes y los márgenes de motor y cable son los que ya estaban.

- **El switch lo decide la física, con el criterio que ya existía**:
  `gas_method_applies()` compara la fracción de gas libre en la admisión contra
  `objectives.gas_fraction_pc_threshold` — el mismo umbral que elige entre
  Hazen-Williams y Poettmann-Carpenter. No se inventó un umbral nuevo.
- **Dos rutas al TDH, y se publican las dos.** El aparejo se dimensiona con
  `tdh_equivalent_ft = Σ ΔPᵢ/gradienteᵢ`, que es la identidad del propio
  conteo de etapas despejada al revés y por lo tanto coherente con él. El TDH
  convencional de tres términos viaja como `tdh_conventional_ft`: son rutas
  independientes a la misma magnitud y **discrepan** (11-12 % en los casos
  probados). No se elige una en silencio.
- **La curva se escala a la frecuencia antes de elegir la bomba**
  (`frequency` → `pump_at_frequency`). Sin eso un pozo a 50 Hz se diseñaba
  contra la curva de 60 Hz: en el caso de prueba, 175 etapas en vez de 226.
- **Si la bomba no completa el aparejo se baja a la siguiente**, ordenadas por
  distancia al BEP contra el caudal de mezcla. Cada descarte queda con su
  motivo en `rejected` — nunca en silencio.
- `_pump_perf_clamped()` marca `clamped` cuando la curva se leyó fuera de su
  rango de datos, y eso levanta una advertencia explícita. Un punto acotado al
  extremo **no** se presenta como punto de operación válido.

`housing_and_mechanical_checks()` (en `pump_design.py`) es el bloque de
carcasas + eje + cojinete que comparten los dos caminos: una vez conocidas la
bomba y las etapas, esa parte no depende de cómo se contaron.

Expuesto en `POST /api/gas/increment-design` (sólo hidráulica) y
`POST /api/gas/design` (aparejo completo, mismo `DesignResultSchema` que el
convencional), pestaña **"Pozo con gas"** del front.

**Escalera de incrementos** (`plotting.plot_gas_increment_ladder`): reproduce la
Fig. 4.56B del libro —admisión abajo, descarga arriba, caudal de mezcla a la
izquierda de cada peldaño, presión a la derecha, ΔP total acotado al costado— y
agrega las etapas de cada tramo, que la figura impresa no muestra. Viaja como
`ladder_figure` **dentro** de la respuesta de los dos endpoints, que es la
convención para figuras que dependen de un cálculo. La escala vertical es lineal
en presión, así que un último escalón corto delata el resto de la división (se
marca con `*`). Con muchos tramos se rotula uno de cada *k* —las líneas se
dibujan todas—; si la figura no se puede armar sale `{}` y el diseño no falla.
Toda la figura son anotaciones sobre un solo trace, por eso el rango de X va
fijo a mano: sin eso Plotly ajusta al trace (x=0) y las etiquetas quedan afuera.

**Traza de fórmulas del método**: `pressure_increment_design()` arma un
`FormulaTrace` (`bes.core.formulas`) con **un tramo entero** —caudal promedio,
gradiente promedio, viscosidad si aplica, deterioro si aplica, psi/etapa, etapas
e hp— **más los totales**. Un solo tramo, no todos: con paso de 25 psi son
decenas y todos resuelven la misma cadena. Viaja por dos caminos según el
endpoint: en `/api/gas/design` va dentro de `DesignResult.formulas`, así que
`ResultsView` la muestra con la misma sección que el diseño convencional y sin
código nuevo en el front; en `/api/gas/increment-design`, que no arma un
`DesignResult`, viaja en el campo `formulas` de la respuesta.

**La expresión mostrada tiene que ser la que se ejecutó.** Dos trampas ya
resueltas, fijadas en `tests/test_gas_handling.py::TestTrazaDeFormulasDelMetodo`:
el conteo de escalones lleva **techo** (`n = ⌈ΔP/escalón⌉` — 847/200 da 4.24 y
los tramos son 5, el último se queda con el resto), y los totales van **sin
sustitución** porque reemplazar un sumatorio por su propio valor imprimía
«51.8 = 51.8». Ojo con el mecanismo de sustitución: reemplaza símbolos por
`str.replace`, así que un símbolo de una sola letra puede pisar letras de la
prosa de la fórmula.

**Errata de Brown ya resuelta** (no "arreglar" de vuelta): el #3A imprime
`Grad_700 = 0.2474`, y es un tipeo por `0.2374`. Lo confirman ρ₇₀₀/144 =
34.185/144, el promedio impreso 0.2143, y los 5.36 psi/etapa impresos. Está
documentado en `tests/test_gas_handling.py::TestExample3ABrownPrinted`, que
valida contra los valores impresos **escritos en el propio test** — sin
depender de ningún archivo de datos.

### PVT medido vs. correlación (`bes/core/pvt.py`)

`PVTTable` / `PVTPoint` permiten inyectar un análisis PVT de laboratorio, que
**gana sobre las correlaciones propiedad por propiedad** (un informe puede
publicar Rs y Bo pero no Bg). `resolve_pvt()` devuelve además `sources`, el
origen de cada valor (`"pvt"` / `"correlacion"` / `"supuesto"`), que viaja hasta
la tabla del front — es lo que hace citable el número en la tesis.

**No extrapola**: fuera del rango medido devuelve `None` y cae a la correlación
avisando. Rs se acota al GOR total incluso si la tabla dice otra cosa.

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

### Correlación de pérdida de carga según el gas

La fracción volumétrica de gas libre en la admisión
(`bes.core.gas_handling.free_gas_fraction_at_intake`) se evalúa **una sola vez,
antes del TDH**, en `design_pump_complete()`, y decide cómo se calcula la
pérdida de carga en el tubing:

| Condición | Correlación |
|---|---|
| `f_g <= objectives.gas_fraction_pc_threshold` | Hazen-Williams (monofásica) |
| `f_g >` umbral | Poettmann-Carpenter, **solo el término de fricción** |

El umbral por defecto es **0.01** (1 %), no 0.10: por encima del 1 % de gas
libre, usar un gradiente de líquido constante introduce un error de diseño
grande. **No se pide por pantalla ni por la API** — el programa evalúa la
fracción de gas y elige solo la correlación. Sobrevive como parámetro sólo para
reproducir los ejemplos impresos de Brown, que lo fijan en 1.0; nada más que
los tests lo tocan. Ver `.claude/rules/domain.md`.

**Cuidado con las dos magnitudes del gas** — fracción `V_g/(V_g+V_l)` y relación
`V_g/V_l` no son lo mismo, y la bibliografía las mezcla. Los umbrales completos
(1 %, 5 %, r>0.1, r≥1.0) están en `.claude/rules/domain.md`.

Es un **híbrido deliberado**: se sustituye solo la fricción, la elevación
vertical y el head de cabeza siguen con el SG del líquido, para conservar el
desglose de tres términos de la UI y los reportes. Consecuencia conocida: en un
pozo con gas la columna real es más liviana, así que la elevación calculada es
conservadora. La fricción P&C se integra en 30 tramos desde el cabezal hacia
abajo (`_friction_loss_poettmann_carpenter`) porque el gas se expande y carga la
fricción hacia el tope; una evaluación en un punto medio la subestima.
`poettmann_carpenter_components()` devuelve gravedad y fricción por separado —
**nunca** sumar `total` al TDH, duplicaría la columna.

`DesignResult.friction_method` reporta cuál se usó.

### Fig. 4L digitalizada (`catalogs/viscosity_charts.json`)

Las láminas del Apéndice 4L de Brown, leídas punto por punto de los originales
que aportó Pablo y **verificadas por él contra el impreso**. No son valores de
correlación: son lecturas del gráfico, y el `_source` lo dice así.

- **`fig_4L_2`** — «Viscosity of gas-free crude oil at oil-field temperatures»,
  grilla de 11 °API (10 a 60) × 5 isotermas (100/130/160/190/220 °F). La lee
  `viscosity.dead_oil_viscosity_chart()`. Es el **paso 2** de Riling.
  La curva «reservoir temperature» de la misma lámina **no se digitalizó**: no
  es una isoterma y su uso no se desprende de la lámina sola.
- **`fig_4L_1`** — «Viscosity of gas saturated crude oil at reservoir
  temperature & pressure», familia de 17 curvas rotuladas por la viscosidad del
  crudo **sin** gas (0.7 a 500 cp) contra el gas en solución (0 a 1400 scf/bbl).
  La lee `viscosity.gas_saturated_viscosity_chart()`. Es el **paso 3**.
  Cada curva lleva **su propia grilla de `rs`** porque terminan en puntos
  distintos —la de 500 cp a 350 scf/bbl, sólo las tres livianas llegan a 1400—;
  entre dos curvas manda el límite de la más corta, que si no medio resultado
  sería lectura y medio invento. En `rs = 0` cada curva vale su etiqueta, y un
  test lo usa como control de carga.
- Las dos interpolan sobre `log10(μ)` (los ejes de viscosidad de las láminas son
  logarítmicos) y linealmente en el otro eje, como está impreso. Ninguna
  extrapola: fuera de rango acotan al borde y avisan.

**Las dos desplazaron a Beggs-Robinson en el procedimiento de Riling**, que era
una correlación ajena al libro puesta donde el libro manda leer una figura —y
encima el módulo citaba Chew-Connally, que tampoco era lo que se ejecutaba.
`pvt.oil_viscosity_dead` / `oil_viscosity_live` siguen existiendo para el PVT
general; `viscosity.py` ya no importa nada de `pvt.py`.

El encadenado completo reproduce el ejercicio de cátedra **entrando sólo con
°API, temperatura y gas en solución** (`test_el_ejercicio_de_catedra_sale_de_las_laminas_solas`):

| Paso | Fuente | App | Libro | Antes (correlación) |
|---|---|---|---|---|
| 2 | Fig. 4L(2) | 151.9 cp | 150 cp | 59.2 cp |
| 3 | Fig. 4L(1) | 68.7 cp | 68 cp | 76.6 cp |
| 4 | ASTM D2161 | 327.2 SSU | 325 SSU | — |

Consecuencia documentada de la 4L(2): en el umbral de 28 °API la lámina da
18.8 cp donde la correlación daba 12.1, así que la corrección pasó de ~0.4 % a
~1 %. El corte de 28 °API se sostiene igual — es de Riling, no de esta cuenta.

Regla vigente sobre estos datos: **nada entra acá que Pablo no haya aportado y
verificado.** Ni correlaciones de fuera del libro, ni valores estimados.

### Leyes de afinidad (`bes/core/affinity.py`)

Módulo **independiente del flujo de diseño**: es la pestaña "Leyes de afinidad",
un banco de pruebas sobre la curva de catálogo. Ningún cálculo de diseño lo
llama.

Implementa la forma completa (velocidad × diámetro × SG). `units.affinity_*`
—los atajos de velocidad pura que usa el camino métrico— delegan acá: **una sola
implementación de las leyes en todo el proyecto**.

La eficiencia **no** se escala. La altura **no** lleva término de SG; la
potencia sí. Se trabaja en Hz porque el deslizamiento se cancela en la relación
`N₂/N₁ = f₂/f₁`.

**`pump_at_frequency()` sí interviene en el diseño**, y es obligatorio:
`design_pump_complete()` lleva la curva a la frecuencia de operación **antes de
filtrar por rango de caudal**, y el objeto escalado viaja a la interpolación,
las etapas, la distancia al BEP y el shut-in de la carcasa. Sin eso un pozo a
50 Hz se diseñaría contra la curva de 60 Hz: 44 % menos etapas de las que
necesita. La frecuencia sale de `operating_frequency(surface, objectives)` —
la de red, salvo que `use_vsd` y `design_frequency_hz` la sobreescriban.

`PumpCurve.catalog_frequency_hz` (default 60 Hz, opcional en el JSON) es la
línea de base. 66 de las 89 bombas declaran 60 Hz en su `_source`; las 23
restantes son las de Brown, que también son 60 Hz.

### Verificación mecánica (`bes/core/mechanical.py`)

Las otras dos de las tres verificaciones mecánicas (la de carcasa está en
`housing.py`). Son la nota al pie de toda hoja de engineering data: el tope de
etapas lo fija la presión de carcasa, la capacidad del eje o la carga sobre el
cojinete — **manda el menor** (`staging_ceiling()`).

- `HP_eje = P_etapa × #Etapas × Pem`. Pasar el límite estándar pide eje de alta
  resistencia; pasar el de alta resistencia descarta la bomba. **El límite
  escala con la frecuencia** (`shaft_hp_limit_at_frequency`): el eje aguanta un
  torque, y potencia = torque × velocidad. La hoja de Wood Group da 104 hp a
  50 Hz = 124.8 hp a 60 Hz.
- `Carga TL = Ho × Pem × A_eje`, con Ho la elevación hasta boca de pozo. **Sin
  el `× #Etapas` que trae impreso el apunte**: Ho ya es el total, y el factor
  cuenta la columna dos veces (daría 198 000 lbs contra sellos de 5 000–30 000).
- El cojinete se verifica por **etapas máximas con tope de temperatura**: 303 a
  230 °F o 1529 a 250 °F en la serie 400. Las dos condiciones atan.

Los datos son **por serie**, en `catalogs/pump_series.json`. Hoy solo la serie
400, de la hoja *ENGINEERING DATA TD1750 50Hz* de Wood Group. Serie sin ficha =
`get_pump_series()` devuelve `None` y las verificaciones quedan **sin realizar**,
nunca aprobadas. **No agregar series con valores estimados.**

### Optimización de carcasas (`bes/core/housing.py`)

Después de calcular las etapas, `_design_candidate()` llama a
`optimize_housings()`, que busca la mejor combinación de las longitudes de
carcasa **de esa bomba** (las carcasas son específicas del modelo: no se
mezclan fabricantes). Orden lexicográfico, sin pesos: exacto → mínimo excedente
→ menos carcasas → menos longitudes distintas → sin sobre-especificar presión →
carcasas grandes primero.

La verificación de presión es **restricción dura dentro de la búsqueda**: si
ningún arreglo entra, `_design_candidate()` devuelve `None` y la bomba se
descarta (con `strict=True`, para una bomba elegida a mano, levanta `ValueError`
explicando el motivo). Antes era solo una advertencia — no volver a eso.

`MaxP_k = P(Q=0) × etapas activas acumuladas hasta k × Pem`, acumulada desde la
admisión, así que la carcasa superior es la crítica; las etapas ciegas no
generan head. Misma relación que `metric_design.step11_housing_burst()`.

`PumpHousing` (en `models.py`) lleva `code`, `material`, `od_in`,
`pressure_limit_psi`, `length_ft` y `weight_lbs` como **opcionales**: hoy los
catálogos solo publican la cantidad de etapas y `PumpCurve.__post_init__` los
sintetiza desde `housing_options`. El día que un catálogo traiga el bloque
`housings`, el loader lo lee y los campos aparecen solos — sin tocar código.
Con `pressure_limit_psi` por carcasa el optimizador ubica la mejor calificada
arriba y habilita tándems mixtos estándar / alta presión.

`DesignResult.housing_detail` es la ficha por carcasa y `housing_rationale` la
justificación generada a partir de los valores calculados.

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

Tests live in `backend/tests/test_pump_design.py`. When adding new calculations, validate against a Brown example and add a corresponding test.

`backend/data/example_wells.json` distinguishes two kinds of scenario:
`*_internal` are project scenarios, `*_brown` carry the **printed** values from
the book (§4.538 #2A, §4.53103 #3A, §4.53104-07 #3B with its six cases and the
PVT table 4.53). The `_brown` increment-method ones have no whole-well
`tdh_ft`; `scripts/validate_all_examples.py` skips them and
`tests/test_integration.py` validates them by unit instead
(`TestExample2ABrown`, `TestExample3ABrownIncrements`, `TestExample3BBrown`).
`ejercicio_esp_neuquen` is the metric cátedra well converted to field units.

### IPR — exactamente tres métodos

`bes/core/ipr.py` implementa **solo** Lineal (Darcy), Vogel (1968) y Fetkovich
(1973). El archivo está escrito para que se lea sin saber programar: docstrings
en español, notación de libro (Pr, Pwf, J, q_max, C, n) y la fórmula arriba de
cada cuenta. Está organizado en cinco secciones numeradas: (1) los tres métodos,
(2) ajuste desde el ensayo, (3) Pwf para un caudal objetivo, (4) curva completa,
(5) auxiliares internos.

Los helpers de IPR futuro `fetkovich_future_c()` y `vogel_future_qmax()` se
**eliminaron**: nunca los llamaba el motor de diseño, solo sus propios tests.
**No agregar un cuarto método** sin que Pablo lo pida.

`Reservoir.fetkovich_c` / `fetkovich_n` carry the deliverability parameters
(C > 0, n ∈ [0.5, 1.0]); both are **required** when `ipr_method is FETKOVICH`
and validated in `__post_init__`, so an incomplete Reservoir fails at
construction rather than deep inside the solver. Functions still accept
explicit `fetkovich_c`/`fetkovich_n` arguments, which win over the model
fields (`_resolve_fetkovich_params`). Regression in `tests/test_fetkovich.py`
against Beggs Example 2-10.

### Metric design path (método de cátedra "ESP 01")

A **parallel, explicit** engine in `bes/core/metric_design.py` implements the
cátedra exercise "ESP 01" in metric units (kg/cm², m, °C, m³/d, g/cm³) with the
exercise's own simplified formulas — it does **not** reuse the field TDH
formula. Entry point: `design_esp_metric(MetricDesignInput, catalog, ...)` →
`MetricDesignResult` (17 steps, each a pure function). Unit conversions live in
`bes/core/units.py`; the dedicated catalog is `bes/catalogs/metric_catalog.json`
(loaded by `bes/catalogs/metric_loader.py` → `MetricCatalog`). The catalog is
**injected by the caller** — `bes.core` is the bottom layer and never imports
`bes.catalogs` at runtime (`tests/test_architecture.py` enforces this). The
field engine and its catalogs are untouched. Formulas, catalog sources and the
resolved ambiguities are documented in `docs/METHODOLOGY.md` §7 and
`docs/EJEMPLO_ESP01.md`; regression in `tests/test_esp01.py`. Note (§7-B): TDH
anchors on the arithmetically-correct ~2301 m, exposing the cátedra 2347 m only
as `tdh_reference_m`.

### Catalog provenance

Every catalog entry carries a `_source` field stating where the number comes
from and which values are estimated. Keep it when editing: it is what makes the
data citable in the thesis. Pump curves anchor their BEP and flow range to real
catalog data where available (see `CORRECCION_CATALOGOS.md`); off-BEP points
follow the standard centrifugal shape.

### Development tooling (`tools/`)

`tools/catalog_pipeline/` (PDF catalog digitization) and
`tools/database_migration/` (Excel → DB build) are project-level utilities,
deliberately outside the `bes` package and the backend Docker image. They
import `bes.*` through the editable install — no `sys.path` manipulation — and
resolve catalog data with `Path(bes.__file__).parent`.

### pump_setting_depth convention

`select_top_n_pumps()` in `bes/recommender/pump_selector.py` sets `pump_setting_depth = max(well.perforations_top − objectives.safety_margin_depth, 100 ft)` and passes it through to the electrical design (cable length). `electrical_design_complete()` accepts an optional `pump_depth`; when omitted it falls back to the legacy proxy `total_depth × 0.80`. For a custom depth, pass it explicitly to `design_pump_complete()` or `calculate_tdh()`.
