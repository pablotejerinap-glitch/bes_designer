# Cómo está armada BES Designer — desglose parte por parte

**Autor:** Pablo Agustín Tejerina (ING-9659) · **Documento generado:** 3 de agosto de 2026
**Estado verificado al escribir este documento:** 750 tests en verde (`pytest`, 34,6 s).

Este documento explica **cómo está construida la aplicación**, pieza por pieza,
en el orden en que conviene leerla. No es la guía de usuario
([`USER_GUIDE.md`](USER_GUIDE.md)) ni el compendio de fórmulas
([`FORMULAS.md`](FORMULAS.md)): es el recorrido por la **estructura** —
qué capa hace qué, por qué está separada así, y de dónde salió cada número.

Índice:

1. [La idea en una página](#1-la-idea-en-una-página)
2. [La decisión estructural: tres capas y una regla](#2-la-decisión-estructural-tres-capas-y-una-regla)
3. [Mapa del repositorio](#3-mapa-del-repositorio)
4. [El motor de cálculo (`bes/core`)](#4-el-motor-de-cálculo-bescore)
5. [Los catálogos (`bes/catalogs`)](#5-los-catálogos-bescatalogs)
6. [El recomendador (`bes/recommender`)](#6-el-recomendador-besrecommender)
7. [Los servicios (`bes/services`)](#7-los-servicios-besservices)
8. [La API HTTP (`bes/api`)](#8-la-api-http-besapi)
9. [El frontend React (`frontend/`)](#9-el-frontend-react-frontend)
10. [Gráficos y reportes](#10-gráficos-y-reportes)
11. [La digitalización de las curvas de catálogo](#11-la-digitalización-de-las-curvas-de-catálogo)
12. [Validación y tests](#12-validación-y-tests)
13. [Empaquetado y despliegue](#13-empaquetado-y-despliegue)
14. [Recorrido completo de un cálculo, de punta a punta](#14-recorrido-completo-de-un-cálculo-de-punta-a-punta)
15. [Qué es dato real y qué es estimado](#15-qué-es-dato-real-y-qué-es-estimado)

---

## 1. La idea en una página

BES Designer hace, en segundos, el procedimiento de diseño de Bombeo
Electrosumergible que un ingeniero hace a mano con el libro de Kermit Brown
(*The Technology of Artificial Lift Methods*, Vol. 2b, Cap. 4.5), una planilla y
los catálogos de fabricante: recibe los datos del pozo y devuelve el equipo
recomendado —bomba, número de etapas, motor, cable, sello, separador de gas,
sensor, controlador y transformador—, comparando alternativas y justificando
cada elección con los valores calculados.

Todo el desarrollo se ordenó alrededor de una distinción:

- **El método** (fórmulas, correlaciones, criterios de selección) no cambia si
  mañana aparece un fabricante nuevo → vive **escrito en código**, con la cita
  bibliográfica de cada fórmula en el docstring.
- **Los datos** (qué bombas existen, sus curvas, motores, cables) cambian todo
  el tiempo → viven **fuera del código**, en catálogos JSON con un campo
  `_source` que dice de dónde salió cada número.

Consecuencia práctica: **agregar un fabricante no toca el programa**, agrega
filas de datos.

---

## 2. La decisión estructural: tres capas y una regla

El proyecto nació como un monolito Streamlit y se migró a tres capas. La app
Streamlit se retiró al alcanzar React la paridad funcional.

```
frontend/ (React)  ──HTTP/JSON──▶  bes.api (FastAPI)  ──▶  bes.services
                                                            │
                                                            ▼
                                              bes.core (dominio puro)
                                              bes.catalogs · bes.recommender
                                              bes.reports  · bes.plotting
```

**La regla de dirección de dependencias** (no negociable, en
`.claude/rules/architecture.md`):

1. `bes.core` **nunca** importa un framework — ni `streamlit`, ni `fastapi`, ni
   `sqlalchemy`. Solo funciones puras sobre dataclasses.
2. `bes.services` orquesta el dominio y es agnóstico de framework: devuelve
   **números crudos**, nunca strings formateados ni objetos de UI.
3. `bes.api` y React **dependen** de los servicios, nunca al revés.
4. `bes.plotting` construye figuras Plotly sin importar ninguna UI, para que la
   API pueda serializarlas con `fig.to_json()`.

Lo importante: **esa regla no es un comentario, es un test**.
`backend/tests/test_architecture.py` parsea el AST de cada archivo de
`core/`, `catalogs/`, `recommender/`, `reports/`, `services/` y `plotting/` y
falla si aparece un import prohibido. El chequeo es estático y no por import,
justamente para detectar un `import fastapi` escondido dentro de una función o
de un `if`. Es la diferencia entre una convención y una restricción real.

**Por qué `core/` y `services/` no viven adentro de `api/`:** si vivieran ahí,
cualquier otra interfaz —un script batch, un notebook, otra UI— tendría que
importar FastAPI solo para poder calcular. `bes.api` y `frontend/` son
*adaptadores de entrega*; ninguno de los dos es "el backend".

---

## 3. Mapa del repositorio

```
backend/                    todo el Python — unidad de despliegue autocontenida
  src/bes/                  único paquete distribuible (pip install -e backend)
    core/       ~5 400 líneas   dominio puro: física e ingeniería
    catalogs/     ~575 líneas   JSON de equipos + queries
    recommender/  ~860 líneas   selección y ordenamiento
    services/     ~380 líneas   orquestación agnóstica de framework
    plotting/     ~800 líneas   builders Plotly
    reports/    ~1 350 líneas   PDF (ReportLab) y Excel (openpyxl)
    api/          ~980 líneas   capa HTTP (FastAPI)
  tests/          750 tests
  data/           example_wells.json (pozos de los ejemplos del libro)
  scripts/        validate_all_examples.py, generate_pump_curves.py, ingest_championx.py
  pyproject.toml  Dockerfile  requirements*.txt
frontend/         ~2 500 líneas TS/TSX — SPA React (Vite + Mantine + Plotly)
tools/            utilidades de desarrollo, FUERA del paquete y de la imagen Docker
  catalog_pipeline/     digitalización de PDF → MySQL (reejecutable)
  database_migration/   Excel → base de datos, auditoría, ERD
docs/             metodología, fórmulas, validación, este documento
docker-compose.yml · README.md · CLAUDE.md
```

El layout es `src/`: **está prohibido `sys.path.insert`**. Todos los imports son
absolutos (`from bes.core.models import ...`) y funcionan porque el paquete se
instala editable (`pip install -e backend`). Los catálogos JSON viajan **dentro**
del paquete y se resuelven con `Path(__file__).parent`
(`bes/catalogs/loader.py:16`), nunca desde el CWD ni desde la raíz del repo:
`CatalogManager()` sin argumentos ya los encuentra, corra desde donde corra.

---

## 4. El motor de cálculo (`bes/core`)

Es el corazón, y es Python puro: numpy/scipy y nada más. Cada módulo es un
escalón del procedimiento de Brown.

### 4.1 `models.py` — el vocabulario compartido (501 líneas)

Once dataclasses que son el contrato de datos de todo el sistema. Cinco de
entrada — `Reservoir`, `Fluid`, `WellGeometry`, `SurfaceConditions`,
`DesignObjectives` —, dos de catálogo — `PumpCurve`, `PumpPerformancePoint` — y
una de salida: `DesignResult`.

Lo que las hace algo más que contenedores es **`__post_init__`**: cada
dataclass valida sus rangos físicos y la consistencia cruzada en el momento de
construirse. `casing_id < casing_od`, `tubing_od < casing_id`,
`perforations_bottom ≤ total_depth`, `oil_api ∈ [5, 70]`,
`bep_flow ∈ [min_flow, max_flow]`, `frequency ∈ {50, 60}`. Un objeto inválido
**no llega a existir**, así que ninguna función del dominio necesita revalidar
sus argumentos.

Un caso vale la pena mirarlo porque muestra el criterio: si
`bubble_point > static_pressure`, no se lanza un error sino un
`warnings.warn(UserWarning)`. Es una condición **físicamente válida** en un
reservorio depletado con empuje por gas en solución. La API captura esos
warnings y los devuelve al usuario en vez de rechazar el diseño
(`api/routers/design.py:35-41`).

Los parámetros de Fetkovich muestran el mismo diseño: `fetkovich_c` y
`fetkovich_n` son opcionales, pero **obligatorios** si
`ipr_method is FETKOVICH`, con `n ∈ [0.5, 1.0]` (1,0 = laminar, 0,5 =
turbulencia total). Un `Reservoir` incompleto falla al construirse, no adentro
del solver tres capas más abajo.

### 4.2 `ipr.py` — cuánto aporta el pozo (464 líneas)

Cuatro métodos de curva de afluencia:

| Método | Uso |
|---|---|
| `linear_ipr` | PI constante (Darcy), por encima del punto de burbuja |
| `vogel_ipr` | Empuje por gas en solución, por debajo de Pb |
| `combined_ipr` | Standing compuesto: lineal arriba de Pb, Vogel abajo |
| `fetkovich_ipr` | Empírico de contrapresión, `q = C·(Pr² − Pwf²)ⁿ` |

Más los helpers de IPR futura — `fetkovich_future_c()` (Beggs Ec. 2-74) y
`vogel_future_qmax()` (Ec. 2-78, ley cúbica de declinación) — que usan presión
**absoluta** en la relación de presiones. Regresión contra el Ejemplo 2-10 de
Beggs en `tests/test_fetkovich.py`.

La función que consume el resto del sistema es
`calculate_pwf_for_target_rate()`: dado un caudal objetivo, devuelve la presión
de fondo fluyente necesaria. Es la entrada de todo el cálculo hidráulico.

### 4.3 `pvt.py` — propiedades del fluido (485 líneas)

Correlaciones estándar, cada una con su cita:

- **Standing (1947)** — `Rs` (GOR en solución), `Pb`, `Bo`
- **Dranchuk-Abou-Kassem (1975)** — factor `z` del gas (resuelto numéricamente)
- **McCain** — `Bw`
- **Beggs-Robinson (1975)** — viscosidad de petróleo muerto y vivo
- **Standing (1977)** — propiedades pseudo-críticas del gas

`fluid_properties_at_conditions(fluid, p, t)` evalúa todo el paquete a una
presión y temperatura dadas; es lo que llama el integrador multifásico en cada
segmento del pozo.

### 4.4 `multiphase.py` — el gradiente de presión (929 líneas)

El módulo más pesado. Implementa **cuatro correlaciones** de flujo multifásico:

| Correlación | Año | Característica |
|---|---|---|
| Hagedorn-Brown | 1965 | Por defecto; holdup correlacionado |
| Beggs-Brill | 1973 | Sensible al ángulo, sirve para pozos desviados |
| Duns-Ros | 1963 | Por regímenes de flujo |
| Poettmann-Carpenter | 1952 | Histórica, de referencia |

Sobre ellas, `pressure_traverse()` integra numéricamente el gradiente a lo largo
del pozo en segmentos, recalculando PVT en cada paso (la presión cambia → cambia
`Rs`, `Bo`, `z`, las velocidades superficiales y el holdup).

Las dos funciones que exporta al resto del sistema:

- **`calculate_pip()`** — el PIP (presión en la admisión de la bomba). Es la
  secuencia de Brown §4.532: (1) `Pwf` en las perforaciones por IPR, (2) perfil
  lineal de temperatura entre boca y fondo, (3) traverse **hacia arriba** por el
  anular casing, desde las perforaciones hasta la profundidad de la bomba, en 20
  segmentos, (4) la presión en el último punto es el PIP.
- **`calculate_discharge_pressure()`** — el traverse por la tubería desde la
  boca de pozo hasta la bomba, para el análisis nodal.

El factor de fricción usa Churchill (1977), que cubre laminar y turbulento en
una sola expresión sin discontinuidad.

### 4.5 `tdh.py` — la altura dinámica total (109 líneas)

Corto y central. Brown §4.5324:

```
TDH = Vertical Lift + Fricción de tubería + Head de presión en superficie

Vertical Lift  = pump_depth − (PIP × 2,31 / SG_liquid)
Fricción       = 0,2083 · (100/C)^1,852 · q_gpm^1,852 / d^4,8655 · L/100   (Hazen-Williams)
Head Pwh       = Pwh × 2,31 / SG_liquid
```

Acá viven también dos helpers chicos con consecuencias grandes:

- `_sg_liquid()` — SG de la mezcla petróleo/agua a condiciones de superficie →
  define el **HP operativo**.
- `_sg_max()` — SG del fluido **más pesado** (agua o petróleo desgasificado) →
  define el **HP máximo** (Brown §4.5325). El motor se dimensiona sobre este
  último, no sobre el operativo, porque durante el arranque, el desgasificado o
  produciendo agua antes de estabilizar, la bomba puede estar moviendo el fluido
  más pesado. Dimensionar sobre el HP operativo es cómo se quema un motor.

### 4.6 `pump_design.py` — etapas, potencia y carcasas (488 líneas)

`design_pump_complete()` es el flujo hidráulico completo:

1. PIP vía `calculate_pip()`.
2. TDH vía `calculate_tdh()`.
3. Filtrar el catálogo: `pump.od < casing_id` **y** `min_flow ≤ q ≤ max_flow`.
4. Para cada candidata: interpolar la curva al caudal objetivo, calcular etapas
   y HP, verificar el rango de operación.
5. Devolver la lista ordenada por eficiencia.

Las piezas finas:

- **`calculate_stages()`** = `ceil(TDH / head_per_stage)`. Techo, no redondeo:
  la bomba tiene que **alcanzar o superar** el TDH requerido.
- **`calculate_motor_hp()`** — el `hp/stage` del catálogo está calibrado para
  agua (SG = 1,0); se multiplica por el SG del fluido real.
- **`select_housing()`** — las carcasas vienen en longitudes discretas. Un
  problema de programación dinámica (tipo *coin change*) elige la combinación
  que cubre las etapas activas con el **mínimo exceso** y, a igualdad, el menor
  número de carcasas. Las etapas sobrantes son **etapas ciegas (dummy)** y se
  reportan como advertencia.
- **Verificación de presión de carcasa** (Brown §4.5451) — el peor caso es a
  caudal cero (*shut-in*), donde el head por etapa es máximo. Se aproxima el
  shut-in por el head máximo de la curva, se apila por el número de etapas y se
  compara contra el límite de trabajo del housing.
- **Tándem** — si las etapas superan `max_stages`, se recomienda instalar N
  bombas en serie. La advertencia explica algo que no es obvio: el diseño
  hidráulico **no cambia** (mismo caudal → mismo head/etapa, HP/etapa,
  eficiencia y TDH); solo se reparten las etapas entre carcasas.
- **`apply_viscosity_correction()`** — tabla del Hydraulic Institute con los
  factores CQ/CH/CE, y conversión SSU→cSt por ASTM D2161. Por debajo de 20 SSU
  los factores son unitarios y los valores pasan sin tocar.

`design_pump_by_model()` es la variante para cuando el usuario **elige la bomba
a mano**: saltea el prefiltro de rango recomendado (es un override deliberado
del algoritmo), pero mantiene como restricciones duras el OD contra el casing y
los límites de la propia curva —la interpolación no extrapola.

### 4.7 `electrical.py` — motor, sello, cable, transformador (549 líneas)

`electrical_design_complete()` encadena la selección eléctrica:

**motor → sello → cable → caída de tensión → voltaje de superficie → transformador**

- `select_motor()` — el menor HP ≥ requerido, voltaje más cercano, serie
  compatible con la bomba, y verificación de temperatura de fondo.
- `estimate_axial_thrust()` — la carga axial (downthrust) que tiene que
  soportar el protector, a partir del TDH, el SG y la serie.
- `select_cable()` — el cable **más económico** que cumpla ampacidad y
  temperatura. La caída de tensión se interpola linealmente en temperatura
  desde la tabla del catálogo (V por amperio por cada 1 000 ft).
- `fluid_velocity_past_motor()` — velocidad del fluido en el anular
  casing-motor. Es la verificación de **enfriamiento**: el motor ESP se enfría
  por el fluido que pasa por afuera; si la velocidad es baja, se sobrecalienta
  aunque eléctricamente esté bien dimensionado.
- `calculate_kva()` y `select_transformer()` — el menor transformador estándar
  que cubra la demanda.

### 4.8 `gas_handling.py` — el gas libre (629 líneas)

- `gas_ingestion_percentage()` — qué fracción del gas libre en la admisión
  entra efectivamente a la bomba.
- `check_gas_lock_risk()` — riesgo de bloqueo por gas.
- `pump_deterioration_factor()` — derateo de la performance por gas ingerido.
- `pressure_increment_design()` — el método de **incrementos de presión** de
  Brown §4.53103 para pozos gasíferos: en vez de un TDH único, se diseña etapa
  por etapa recalculando las propiedades del fluido a medida que sube la
  presión. Es el método del Ejemplo 3 del libro.
- `recommend_gas_separator()` — recomendación de separador según la serie.

En el flujo automático, el separador solo se recomienda cuando la fracción de
gas en la admisión supera el 10 % (`pump_selector.py:308`).

### 4.9 `nodal_analysis.py` — oferta contra demanda (352 líneas)

Construye la curva de *inflow* (IPR) y la de *outflow*, natural y asistida por
bomba, y encuentra el punto de operación con `brentq` (búsqueda de raíz
acotada). `compare_methods()` corre el análisis con las cuatro correlaciones
multifásicas para mostrar la dispersión entre ellas — que es información
honesta: el punto de operación depende de qué correlación se elija.

### 4.10 `units.py` + `metric_design.py` — el camino métrico paralelo

`metric_design.py` (727 líneas) implementa el ejercicio de cátedra **"ESP 01"**
en unidades métricas (kg/cm², m, °C, m³/d, g/cm³) con **las fórmulas
simplificadas propias del ejercicio** — no reusa la fórmula de TDH de campo.
Son 17 pasos, cada uno una función pura: presión admisible → qmax → producción
→ lectura de curva → fricción → PIP → TDH → etapas → carcasas → burst → HP y
eje → motores → enfriamiento → protector → cable.

Es deliberadamente **un motor aparte**: mezclarlo con el de campo habría
contaminado los dos. `units.py` tiene las conversiones y las leyes de afinidad
(`Q ∝ N`, `H ∝ N²`, `HP ∝ N³`).

Un detalle de criterio documentado en `METHODOLOGY.md` §7-B: el TDH se ancla en
el valor **aritméticamente correcto** (~2 301 m) y el valor de la cátedra
(2 347 m) se expone aparte como `tdh_reference_m`. No se replicó un error de
redondeo para que "diera igual".

**Restricción de capas:** `metric_design.py` recibe el catálogo **inyectado por
el llamador**. `bes.core` es la capa de abajo y nunca importa `bes.catalogs` en
runtime — y `tests/test_architecture.py` lo verifica.

---

## 5. Los catálogos (`bes/catalogs`)

Los datos, separados del método. JSON que viajan dentro del paquete.

| Archivo | Entradas | Fabricantes |
|---|---|---|
| `pumps.json` | **89 bombas** | Summit ESP 56 · Alkhorayef 9 · Centrilift 8 · Reda 7 · SLB 6 · Weatherford 3 |
| `motors.json` | 50 | ChampionX 33 · Reda 10 · Centrilift 5 · SLB 2 |
| `cables.json` | 19 | Reda 9 · Centrilift 6 · ChampionX 4 |
| `seals.json` | 24 | Reda 9 · ChampionX 9 · Centrilift 6 |
| `gas_handlers.json` | 12 | ChampionX (WHIRLAWAY) |
| `sensors.json` | 4 | ACE Downhole |
| `controllers.json` | 10 | Reda 5 · ChampionX 3 · Centrilift 2 |
| `casing_tubing.json` | 161 casing + 38 tubing | Tenaris (API 5CT 8ª ed. / ISO 11960) |
| `metric_catalog.json` | 2 bombas, 7 motores, 2 sellos, 3 cables | Wood Group serie 400 / TR4 (método métrico) |

**`CatalogManager`** (`loader.py`, 475 líneas) los carga una vez y expone las
consultas: `get_pumps_by_casing()`, `get_pumps_by_flow_range()`,
`interpolate_pump_curve()`, `get_motor()`, `get_cable()`, `get_seal()`,
`select_gas_handler()`, `select_sensor()`, `get_controller()`, más las tablas
dimensionales de casing y tubing.

**Trazabilidad.** Cada entrada lleva un campo **`_source`** que dice de dónde
salió el número y qué parte es estimada. No es decorativo: es lo que hace el
dato citable en la tesis. Ejemplo real de una entrada de bomba:

> `"Digitalizado de alkhorayef-esp-catalog-2019.pdf pag. 20 (WD-4300, 400 series, Mixed Flow, 60 Hz, SpGr=1.0). Curvas Head/Power/Efficiency extraidas por mascara de color sobre la imagen JPEG nativa embebida (902x588 px); ejes calibrados por deteccion de la caja del grafico...; QA por identidad hidraulica eta=Q*H/(135773*BHP): error <1 pto% en todo el rango operativo 1200-5200 bpd. NOTA: la leyenda impresa al pie del grafico tiene los colores Head/Power/Efficiency INTERCAMBIADOS respecto de los titulos de eje; se uso la asignacion por titulo de eje, confirmada por la identidad hidraulica."`

Ese `_source` documenta hasta un **error del catálogo del fabricante** detectado
por el control de calidad físico. Al editar un catálogo, el `_source` se
mantiene.

---

## 6. El recomendador (`bes/recommender`)

Acá está la decisión metodológica más discutible del proyecto, y por eso la más
documentada.

### 6.1 `ranking.py` — ordenamiento por criterios, sin puntajes

El sistema **anterior** puntuaba con pesos arbitrarios: eficiencia 40 % /
flexibilidad 30 % / **preferencia de proveedor 30 %**. Se eliminó (ver
`REFORMA_COMPARACION_BES.docx`). Un puntaje ponderado esconde las decisiones
adentro de constantes que nadie puede defender, y una dimensión de "proveedor"
en un trabajo académico es directamente indefendible.

Lo reemplaza un **orden lexicográfico estricto** de tres criterios físicos:

1. **Distancia al BEP** — `|q − q_BEP| / q_BEP`, ascendente
2. **Eficiencia de la bomba** en el punto de operación, descendente
3. **Potencia de eje requerida**, ascendente

El criterio 2 solo desempata el 1; el 3 solo desempata los dos primeros. **Sin
pesos, sin escalas 0–10, sin dimensión de marca** — el fabricante es
informativo. `DesignObjectives` ni siquiera tiene un campo de proveedor.

La base de ingeniería (Brown §4.5325): la bomba debe seleccionarse para que el
caudal de diseño caiga lo más cerca posible de su punto de máxima eficiencia;
operar lejos del BEP aumenta el empuje axial y el desgaste, y reduce la vida
útil.

`classify_bep_distance()` etiqueta la distancia (≤10 % óptimo / ≤25 % aceptable
/ >25 % alejado) **solo para mostrar**, y jamás participa del ordenamiento.

### 6.2 `pump_selector.py` — el ensamblado (388 líneas)

`select_top_n_pumps()` corre el diseño hidráulico de todas las bombas que
entran, las ordena por la clave de ranking, y **recién entonces** ensambla el
diseño eléctrico de las mejores.

Un detalle que parece menor y no lo es: **no se trunca a N antes de ensamblar**.
Un candidato mejor rankeado puede fallar al ensamblar —por ejemplo, su motor
dimensionado sobre el HP máximo exige un cable que no entra en el casing— y en
ese caso hay que **seguir bajando en el ranking** en vez de devolver menos
diseños, o ninguno. El bucle atrapa el fallo por candidato y sigue.

Acá también se fija la convención de profundidad:

```python
pump_setting_depth = max(perforations_top − safety_margin_depth, 100 ft)
```

El piso de 100 ft evita que un margen de seguridad absurdo produzca una bomba en
superficie.

`select_pump_by_model()` es el camino del override manual: mismo ensamblado,
sin ranking, y los fallos **se propagan** en vez de saltar al siguiente —una
bomba elegida a mano no tiene alternativa a la que caer.

### 6.3 `recommendation_engine.py` — la API de alto nivel (354 líneas)

`generate_recommendations()` devuelve, por cada alternativa, un dict `criteria`
con los **valores crudos** que usó el ranking (BEP, distancia, % del BEP,
eficiencia, HP, clasificación) y un `rationale` en lenguaje natural
**construido exclusivamente a partir de datos calculados**. Nada de texto
genérico: si dice "opera al 96 % del BEP con 68 % de eficiencia", esos dos
números salen del cálculo.

---

## 7. Los servicios (`bes/services`)

Orquestación agnóstica de framework. Tres módulos:

- **`nodal_service.py`** — `run_nodal_analysis()`, más
  `apply_reservoir_decline()`, que es la fuente única de verdad para simular
  declinación de presión (aplica el porcentaje y **clampea** el punto de
  burbuja al nuevo valor estático).
- **`sensitivity_service.py`** — `run_sensitivity()`: barre un parámetro
  (corte de agua, GOR, presión de reservorio o caudal objetivo) y reporta cómo
  responden HP, etapas, eficiencia y TDH. El progreso se comunica por un
  **callback**, no por la UI: por eso la capa no sabe qué interfaz la llama.
- **`case_bundle.py`** — serializa un caso completo (entradas + resultado) a
  dict/JSON. Es el formato de guardar/abrir y el candidato natural para la tabla
  `designs` cuando llegue SQLite.

---

## 8. La API HTTP (`bes/api`)

Capa delgada sobre los servicios. Once endpoints:

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/api/health` | Ping para el indicador de conexión del front |
| `POST` | `/api/design` | Recomendaciones top-N (o una bomba forzada) |
| `GET` | `/api/catalogs` | Resumen de catálogo para el front |
| `GET` | `/api/catalogs/tubulars` | Tablas dimensionales Tenaris |
| `POST` | `/api/nodal` | Métricas nodales + figura Plotly |
| `POST` | `/api/sensitivity` | Barrido + figura Plotly |
| `POST` | `/api/reports/{pdf,xlsx}` | Descarga del reporte |
| `GET` | `/api/examples` | Pozos del libro para precargar el formulario |
| `POST` | `/api/plots/ipr-curve` | Curva IPR sin diseño previo |
| `GET` | `/api/plots/pump-curve` | Curva con punto de operación marcado |
| `GET` | `/api/plots/pump-catalog-curve` | Curva de catálogo por etapa |

### Las tres decisiones de contrato

**1. Esquemas Pydantic separados, no conversión del dominio.** Las dataclasses
de `core/models.py` **se mantienen**; en `api/schemas/` viven esquemas Pydantic
que las espejan, y `api/mappers.py` traduce en ambos sentidos. Convertir el
dominio a Pydantic habría roto los tests que esperan `ValueError` con mensajes
específicos, y el `warnings.warn` "blando" de `Reservoir`. Como los nombres de
campo coinciden, el mapeo es trivial: `DesignResultSchema(**asdict(dr))` de
salida, `Fluid(**schema.model_dump())` de entrada.

**2. Enums string hacia afuera, enteros adentro.** `IPRMethod` y
`DriveMechanism` usan `auto()`, o sea valores **enteros**. Esos enteros no se
exponen nunca: la API habla `"vogel"`, `"linear"`, `"solution_gas"`, y el mapper
hace el lookup explícito por nombre en minúscula.

**3. Contrato de errores central.** Un solo handler en `api/main.py:44`
convierte cualquier `ValueError` del dominio —diseño inviable, validación
cruzada, bomba inexistente— en **HTTP 422** con el mensaje del error. Pydantic
ya devuelve 422 para validación por campo, así que el front ve un solo código
para "tus datos no cierran". Los `UserWarning` del dominio se capturan con
`warnings.catch_warnings(record=True)` y se devuelven en el campo `warnings` de
la respuesta en vez de perderse.

**Gráficos:** los endpoints devuelven **Plotly figure JSON** llamando a los
builders de `bes.plotting` (`fig.to_json()`). No se reimplementa ningún gráfico
en JavaScript.

**Catálogo:** `get_catalog()` en `deps.py` es un singleton `lru_cache` de
proceso — los JSON se leen una vez, no en cada request.

---

## 9. El frontend React (`frontend/`)

**Stack:** Vite 5 + React 18 + TypeScript estricto + Mantine 7 +
`react-plotly.js`. Unas 2 500 líneas.

**Layout de dos paneles, estilo pengtools:** toolbar arriba, entradas a la
izquierda (secciones colapsables + botón *Calcular* fijo al pie), gráficos y
resultados a la derecha con sub-pestañas. Por debajo de ~1 000 px colapsa a una
columna. Tema claro/oscuro conmutable.

**Componentes:**

| Componente | Qué hace |
|---|---|
| `App.tsx` (416) | Estado global, toolbar, guardar/abrir casos, pestañas |
| `WellForm.tsx` (436) | Acordeón de 5 secciones: Reservorio · Fluido · Geometría · Superficie · Objetivos |
| `ResultsView.tsx` (204) | Las alternativas en pestañas, con métricas y justificación |
| `ComparisonView.tsx` (150) | Tabla comparativa con los tres criterios crudos |
| `DesignCharts.tsx` (126) | Sub-pestañas Curva de bomba / Análisis nodal |
| `SensitivityView.tsx` (183) | Barrido de parámetros |
| `IprPanel.tsx` (115) | Curva IPR independiente del diseño |
| `PumpLibrary.tsx` (216) | Biblioteca del catálogo, filtrada por casing |
| `PlotFigure.tsx` (29) | Envoltura fina de `<Plot>` — recibe el JSON y lo pasa |

**Las reglas que se respetan:**

- **Cliente tipado generado desde OpenAPI**, no escrito a mano:
  `npm run gen:api` corre `openapi-typescript` sobre `openapi.json`. Tras
  cambiar un schema Pydantic se regenera el contrato y el compilador de
  TypeScript marca cualquier desajuste.
- **Cero lógica de negocio en el front.** El front formatea y renderiza.
- **Cero lógica de gráficos en JS.** `PlotFigure` recibe la figura ya
  construida por el backend.

Dos detalles de UX que resuelven problemas reales:

- **`syncPb()`** (`App.tsx:49`) — el punto de burbuja es una sola magnitud
  física pero el modelo lo guarda en dos campos (`Reservoir.bubble_point` para
  IPR/nodal, `Fluid.bubble_point_pressure` para PVT). El formulario pide **uno
  solo** y fuerza que el de fluido lo iguale, así IPR y PVT nunca quedan
  inconsistentes.
- **Los resultados guardan el snapshot de las entradas que los produjeron.** Si
  el usuario sigue editando el formulario, los gráficos y el reporte siguen
  correspondiendo al diseño que está en pantalla, no a lo que hay tipeado.

El desplegable de bomba manual filtra por `p.od < casing_id`, el **mismo**
criterio que el backend, para no ofrecer opciones condenadas a un 422.

---

## 10. Gráficos y reportes

**`bes/plotting/plots.py`** (772 líneas) — siete builders Plotly: curva IPR,
curva de bomba con punto de operación, curva de catálogo, perfil de presión,
análisis de sensibilidad, análisis nodal y comparación de correlaciones. No
importan ninguna UI: por eso la API puede serializarlos y el PDF renderizarlos.

**`bes/reports/pdf_generator.py`** (894 líneas) — reporte con ReportLab:
portada, entradas, metodología paso a paso con las citas de Brown, resultados,
diseño eléctrico, advertencias y gráficos embebidos. Tiene **dos motores de
gráfico**: Plotly vía Kaleido y, si Kaleido no está disponible, un fallback a
matplotlib. El reporte sale con figuras igual.

**`bes/reports/excel_exporter.py`** (459 líneas) — libro openpyxl con hojas
Resumen, Entradas, TDH (con el desglose de los tres términos), Bomba, Eléctrico
y Advertencias.

---

## 11. La digitalización de las curvas de catálogo

Los fabricantes publican las curvas de rendimiento como **gráficos**, no como
tablas. Para que el programa pueda interpolar `head/etapa`, `hp/etapa` y
eficiencia a un caudal cualquiera, hubo que convertir esos gráficos en números.
Se hizo con dos pipelines, según cómo esté hecho el PDF.

### 11.1 El control de calidad físico (lo que hace confiable a todo lo demás)

Antes que las herramientas, el criterio. Toda curva digitalizada se valida con
la **identidad hidráulica**:

```
η = Q · H / (135 773 · BHP)        [Q en bpd, H en ft, BHP en hp, SG = 1,0]
```

Las tres curvas del gráfico —head, potencia y eficiencia— **no son
independientes**: están ligadas por esa ecuación. Si la lectura de una es mala,
la identidad no cierra. Es un control cruzado que no depende de confiar en el
proceso de lectura.

En la práctica: en las bombas Summit el error medio quedó en **0,08 puntos
porcentuales** (máximo 0,16) dentro del rango operativo; en las Alkhorayef,
**por debajo de 1 punto porcentual**. Las tolerancias usadas son coherentes con
el estándar API (±5 % en altura, ±8 % en potencia).

Se agregan dos verificaciones más: que el pico de eficiencia caiga en el caudal
BEP que declara la ficha, y que el head sea monótonamente decreciente.

**El control detectó errores del propio catálogo.** En el Alkhorayef 2019, la
leyenda impresa al pie del gráfico tiene los colores de Head/Power/Efficiency
**intercambiados** respecto de los títulos de eje. Se usó la asignación por
título de eje, y la identidad hidráulica confirmó cuál de las dos lecturas era
la correcta. Quedó anotado en el `_source` de esas nueve bombas.

### 11.2 Pipeline A — `tools/catalog_pipeline/` (PDF → MySQL, reejecutable)

Recorre todos los PDF de un directorio y carga fichas y curvas a una base MySQL
`catalogos_pump` con esquema normalizado. Tiene dos motores de lectura:

**Vectorial** (`digitize.py:digitize_vector`) — para PDF cuyas curvas son
**trazos vectoriales** (REDA, Wood Group). Es el caso bueno:

- Los ticks de los ejes se leen como **texto** (`get_text('words')` de PyMuPDF),
  o sea calibración exacta **sin OCR**.
- Las polilíneas se leen con `get_drawings()` y se separan por color → la curva
  queda casi punto a punto.
- El ajuste pixel→valor es **robusto**: `_robust_linear()` prueba pares de
  puntos y se queda con el que maximiza inliers dentro de tolerancia, así un
  tick mal leído no arrastra la calibración.
- En las familias multi-frecuencia se elige la línea de 60 Hz **por proximidad
  a su etiqueta**.
- La eficiencia se **deriva** por la identidad hidráulica, porque REDA no la
  grafica.

**Raster** (`extract_chart_image`) — para curvas que son imagen embebida
(Centrilift, Alkhorayef): guarda el gráfico y marca `review_flag = 1`. La
digitalización fina requeriría OCR de los ejes, y este pipeline se diseñó sin
dependencias externas (ni Tesseract ni poppler).

**Es reejecutable:** `manifest.json` guarda el SHA-256 de cada PDF y saltea los
que no cambiaron; los upserts evitan duplicados. Para agregar un catálogo, se
copia el PDF y se vuelve a correr.

**Salidas:** tablas crudas en CSV, JSON de puntos, logs por corrida, y
**overlays de QA** — imágenes con los puntos digitalizados dibujados sobre la
curva original, para verificación visual. (Las páginas rotadas se guardan de
costado a propósito: se renderizan en el mismo espacio en que se midieron para
que los puntos alineen exactamente.)

Primera corrida sobre 13 PDF: 5 fabricantes, 58 bombas, 56 con curva
digitalizada, 595 puntos de curva.

### 11.3 Pipeline B — `extract_curves_alkhorayef.py` (raster con OCR)

El caso difícil: el catálogo Alkhorayef 2019 publica las curvas como **imágenes
JPEG embebidas** (902×588 px). La cadena:

1. **Localizar** las páginas de bomba buscando el texto "Optimum operating
   range" y el código de modelo.
2. **Extraer** la imagen del gráfico con `pdfimages`.
3. **Detectar la caja del gráfico** por proyección de píxeles oscuros (las
   líneas de eje son las columnas/filas con más densidad).
4. **Calibrar los ejes** por OCR de los ticks (Tesseract), con **ajuste robusto
   RANSAC** y un fallback por segmentos cuando el OCR falla.
5. **Extraer cada curva por máscara de color** (Head / Power / Efficiency).
6. **Limpiar**: suavizado Savitzky-Golay, remuestreo PCHIP, head forzado
   no-creciente y eficiencia forzada unimodal — restricciones que vienen de la
   física de una bomba centrífuga, no de la estadística.
7. **QA por identidad hidráulica** (±12 %), pico de eficiencia en el BEP, head
   decreciente. Lo que no pasa el QA **se reporta para lectura visual** en vez
   de entrar silenciosamente.

Resultado: **35 de 37 bombas automáticas**. Dos quedaron para lectura visual
(WE-8500 y WN-1050, con los ticks de caudal ilegibles para OCR) y una (WD-3000)
necesitó forzar el BEP porque el pico real de la curva del catálogo no coincide
con el BEP declarado en su propia ficha. El proceso es idempotente.

### 11.4 Las bombas Summit ESP (56 de las 89)

Mismo enfoque raster: páginas sin capa de texto, renderizadas a 150 DPI, curvas
Head (azul) / HP (rojo) / Efficiency (verde) extraídas por máscara de color,
caudal calibrado por OCR de ticks, caja del gráfico por detección de bordes,
rango operativo tomado del sombreado "Standard Range", BEP del pico de
eficiencia, y las carcasas leídas por OCR de la página de dimensiones.

El `hp/etapa` se **deriva** por la identidad hidráulica, con cross-check contra
el HP impreso donde es legible: coincidencia **0–1 %**.

### 11.5 Ingesta tabular — `ingest_championx.py` y el informe

No todos los PDF necesitan digitalización de curvas. Los de motores, cables,
protectores, gas handlers y sensores traen **tablas**. `ingest_championx.py`
las carga a los JSON correspondientes.
[`CHAMPIONX_INGESTION_REPORT.md`](CHAMPIONX_INGESTION_REPORT.md) documenta
exactamente qué se extrajo de cada uno de los 7 PDF, **qué no pudo
interpretarse y qué quedó incompleto** — incluido el hallazgo de que los
"catálogos de ChampionX" eran en realidad de **tres fabricantes distintos**
(ChampionX, SLB y ACE Downhole), y que se citan por su fabricante real aunque
SLB haya adquirido ChampionX.

### 11.6 `tools/database_migration/` — el camino a base de datos

Migración de los catálogos a Excel normalizado (tablas de fabricantes, bombas,
curvas punto por punto, motores, sellos, cables, transformadores, VSD,
switchboards, pozos reales), con auditoría por formas normales, diagrama
entidad-relación (`erd.mermaid` / `erd.svg`) y verificadores de integridad. La
documentación de diseño está en `DISENO_BASE_DE_DATOS.md` y
`AUDITORIA_BASE_DE_DATOS.md`.

**`tools/` está deliberadamente fuera del paquete `bes` y fuera de la imagen
Docker del backend.** Son utilidades de desarrollo: importan `bes.*` a través
del install editable —sin tocar `sys.path`— y resuelven los datos del catálogo
con `Path(bes.__file__).parent`.

---

## 12. Validación y tests

**750 tests, verdes, en 34,6 segundos.** Es el activo más valioso del proyecto.

| Archivo | Tests | Cubre |
|---|---|---|
| `test_pump_design.py` | 69 | Etapas, HP, carcasas, viscosidad |
| `test_integration.py` | 68 | Ejemplos completos del libro |
| `test_electrical.py` | 67 | Motor, cable, transformador, sello |
| `test_recommender.py` | 66 | Ranking y ensamblado |
| `test_gas_handling.py` | 63 | Gas libre, incrementos de presión |
| `test_pvt.py` | 61 | Correlaciones PVT |
| `test_catalog.py` | 55 | Consultas e interpolación |
| `test_ipr.py` | 49 | Las cuatro IPR |
| `test_models.py` | 34 | Validación de dataclasses |
| `test_esp01.py` | 32 | Método métrico de cátedra |
| `test_multiphase.py` | 30 | Las cuatro correlaciones |
| `test_fetkovich.py` | 25 | Fetkovich contra Beggs Ej. 2-10 |
| `test_api.py` | 24 | Contrato HTTP, enums, errores 422 |
| `test_metric_design.py` | 22 | Pasos métricos |
| `test_units.py` | 16 | Conversiones y afinidad |
| resto | 29 | Casing/tubing, nodal, plots, scripts, **arquitectura** |

**La regla de oro:** toda correlación nueva del dominio se valida contra un
**ejemplo numerado del libro** y se agrega su test.

| Ejemplo | Bomba | Caudal | TDH | Etapas | HP |
|---|---|---|---|---|---|
| #1A | Centrilift I-300 | 10 000 bpd | 1 670 ft | 28 | 180 |
| #2A | Reda D-40 | 1 227 bpd | 5 830 ft | 254 | ≈79 |
| #2B | Centrilift I-42B | ~2 080 bpd | 4 258 ft | 112 | ≈65 |
| Fricción | 5" caño nuevo | 10 000 bpd | ≈18,5 ft/1 000 ft | — | — |

`backend/data/example_wells.json` distingue dos clases de escenario: los
`*_internal` son escenarios del proyecto, y los `*_brown` llevan los valores
**impresos** del libro (§4.538 #2A, §4.53103 #3A, §4.53104-07 #3B con sus seis
casos y la tabla PVT 4.53). Los `_brown` del método de incrementos no tienen un
`tdh_ft` de pozo completo, así que `validate_all_examples.py` los saltea y
`test_integration.py` los valida **por unidad**.

`scripts/validate_all_examples.py` regenera [`VALIDATION.md`](VALIDATION.md),
que compara app contra libro. Los desvíos están reportados con su semáforo, no
escondidos: el Ejemplo 1A da −0,1 % en TDH y 0,0 % en etapas; el 2A impreso da
−3,9 % en TDH pero **−24 % en etapas**, marcado ⚠️, porque el catálogo actual no
tiene la D-40 exacta del libro y elige una SF1200 con otro head por etapa.

---

## 13. Empaquetado y despliegue

**Entorno de desarrollo:** venv en `.venv` (Python 3.14 en la máquina del autor;
el backend corre igual en 3.11). Backend instalado editable:

```bash
.venv\Scripts\python.exe -m pip install -e backend
cd frontend && npm install
```

**Correr las dos capas:**

```bash
# backend (desde backend/)
python -m uvicorn bes.api.main:app --reload --port 8000
# frontend (desde frontend/)
npm run dev
# o todo junto
docker compose up --build
```

`docker-compose.yml` levanta dos servicios: `api` (FastAPI en :8000, con
healthcheck sobre `/api/health`) y `frontend` (nginx en :8080 sirviendo la SPA
y proxyando `/api` al backend). El front espera a que el healthcheck del api
pase (`depends_on: condition: service_healthy`). En Docker el front va tras
nginx —mismo origen—, así que **CORS solo importa para el dev directo con
Vite**; los orígenes permitidos son configurables por `BES_CORS_ORIGINS`.

**Tras cambiar un schema Pydantic**, regenerar el contrato tipado:

```bash
# backend/ → exporta el OpenAPI
python -c "import json;from bes.api.main import app; open('../frontend/openapi.json','w',encoding='utf-8',newline='').write(json.dumps(app.openapi(),separators=(',',':'),ensure_ascii=False))"
# frontend/ → regenera los tipos TS
npm run gen:api && npx tsc --noEmit
```

---

## 14. Recorrido completo de un cálculo, de punta a punta

Para fijar todo lo anterior, el camino de un click:

1. **El usuario** completa las 5 secciones del formulario (o carga un ejemplo
   del libro desde `GET /api/examples`) y presiona **Calcular diseño BES**.
2. **`App.tsx`** arma un `DesignInputs` (tipado desde el OpenAPI) y hace
   `POST /api/design`.
3. **FastAPI** valida el cuerpo con Pydantic. Un campo fuera de rango muere acá
   con 422.
4. **`mappers.to_domain_inputs()`** convierte los cinco esquemas a las cinco
   dataclasses, traduciendo `"vogel"` → `IPRMethod.VOGEL`. Los `__post_init__`
   corren y validan la consistencia cruzada.
5. **`generate_recommendations()`** llama a `select_top_n_pumps()`:
   - `pump_setting_depth = max(perf_top − margen, 100 ft)`
   - **`calculate_pip()`**: `Pwf` por IPR → traverse Hagedorn-Brown hacia arriba
     por el anular, 20 segmentos, recalculando PVT en cada uno → PIP.
   - **`calculate_tdh()`**: elevación + fricción Hazen-Williams + head de Pwh.
   - **Filtro de catálogo**: `od < casing_id` y `min_flow ≤ q ≤ max_flow`.
   - **Por cada candidata**: interpolar la curva, `ceil(TDH/head)` etapas,
     HP operativo (SG mezcla) y **HP máximo** (SG del fluido más pesado),
     carcasas por programación dinámica, chequeo de presión de housing.
   - **Ordenar** por `(distancia BEP, −eficiencia, HP)`.
   - **Ensamblar de arriba hacia abajo** hasta juntar N diseños factibles:
     motor sobre el HP máximo → sello por empuje axial → cable por ampacidad y
     temperatura → caída de tensión → voltaje de superficie → transformador →
     verificación de enfriamiento → GIP en la admisión → separador si GIP >
     10 % → sensor.
6. **`generate_recommendations()`** agrega a cada diseño su dict `criteria` con
   los valores crudos y el `rationale` en texto.
7. **`from_design_result()`** mapea cada `DesignResult` a su esquema de salida.
   Los `UserWarning` capturados viajan en el campo `warnings`.
8. **El front** renderiza las alternativas en pestañas. Al abrir "Curva de
   bomba" pide `GET /api/plots/pump-curve`, que devuelve **Plotly figure JSON**;
   `PlotFigure` solo se lo pasa a `<Plot>`.
9. **Exportar PDF/Excel** hace `POST /api/reports/{fmt}` con el mismo snapshot
   de entradas, y el backend regenera el diseño y arma el archivo.

En ningún punto de esa cadena hay un cálculo en el navegador.

---

## 15. Qué es dato real y qué es estimado

La honestidad sobre las fuentes es parte del trabajo. El desglose de las 89
bombas:

| Clase | Cantidad | Qué tan real es |
|---|---|---|
| **Digitalizadas de PDF de fabricante** | 65 | Summit ESP (56) y Alkhorayef (9): head, potencia y eficiencia leídos del gráfico publicado, con QA por identidad hidráulica. Es dato del fabricante. |
| **De los ejemplos de Brown** | 4 | Bombas de validación (D-40, I-300, I-42B y la de los ejemplos 2A/3A), transcritas del libro. |
| **Ancladas a datos reales, curva sintetizada** | 20 | El **BEP (head y eficiencia) y el rango de caudal son reales** —de catálogos Reda/SLB/Pengtools, de una hoja de especificación Baker Hughes o de una bomba experimental publicada (TUALP)—, pero los puntos fuera del BEP siguen la forma centrífuga estándar y el HP se **deriva** por potencia hidráulica. |

Las de la tercera clase se generan con `scripts/generate_pump_curves.py`, cuya
forma es explícita:

```
head(x) = H_bep · (1,42 − 0,10·x − 0,32·x²)      x = q / q_bep
eff(x)  = eff_bep · (1 − 0,85·(x − 1)²)
hp(x)   = q · head / (135 770 · eff)              [agua, SG = 1,0]
```

El script es **idempotente** y **nunca toca las bombas del libro**. Su propio
docstring lo dice: *"These are REPRESENTATIVE curves... not a substitute for the
manufacturer's measured curve."* Cada una lo declara en su `_source`.

**Otras limitaciones conocidas, en una lista:**

- El PIP depende de la correlación multifásica elegida; Hagedorn-Brown es el
  default. `compare_methods()` existe justamente para mostrar la dispersión
  entre las cuatro.
- La eficiencia de sistema se aproxima como `eficiencia_bomba × 0,92` (0,92
  ≈ eficiencia típica de motor), acotada a 0,99.
- Cuando `electrical_design_complete()` se llama sin profundidad explícita, cae
  al proxy heredado `total_depth × 0,80` para la longitud de cable. El camino
  normal (`select_top_n_pumps`) **siempre** pasa la profundidad real.
- Las curvas están a **60 Hz y SG = 1,0**; el ajuste por frecuencia se hace por
  leyes de afinidad y el de fluido por SG.
- La persistencia de casos hoy es `localStorage` del navegador.
  `case_bundle.py` ya tiene el formato listo para la tabla SQLite cuando llegue.
- La app entrega un **prediseño trazable**, no reemplaza la validación del
  fabricante con su curva medida.

---

## Para seguir leyendo

| Documento | Contenido |
|---|---|
| [`METHODOLOGY.md`](METHODOLOGY.md) | La metodología de cálculo paso a paso, con la referencia a Brown de cada etapa (incluye §7, el método métrico) |
| [`FORMULAS.md`](FORMULAS.md) | Todas las fórmulas, con archivo, línea y fuente bibliográfica |
| [`VALIDATION.md`](VALIDATION.md) | App vs. libro, ejemplo por ejemplo |
| [`EJEMPLO_ESP01.md`](EJEMPLO_ESP01.md) | Los 17 pasos del ejercicio de cátedra |
| [`USER_GUIDE.md`](USER_GUIDE.md) | Cómo se usa la aplicación |
| [`CHAMPIONX_INGESTION_REPORT.md`](CHAMPIONX_INGESTION_REPORT.md) | Qué se digitalizó de cada PDF, y qué no |
| [`../tools/catalog_pipeline/README.md`](../tools/catalog_pipeline/README.md) | El pipeline de digitalización en detalle |
| [`../tools/database_migration/README.md`](../tools/database_migration/README.md) | El diseño de la base de datos |
| `.claude/rules/*.md` | Las reglas de arquitectura, dominio, contrato de API y frontend |
