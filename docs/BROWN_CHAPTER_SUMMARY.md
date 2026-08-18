# Brown Vol. 2b — Capítulo 4.5 (Diseño de Sistemas BES)

> Resumen del capítulo entregado (PDF p.71–123 = páginas del libro 58–110), generado a partir de OCR del scan original.
> Fuente: Brown, K.E. (1984). *The Technology of Artificial Lift Methods, Vol. 2b: Electric Submersible Pumping Systems*. PennWell Books.
> Mapeo a los módulos del BES Designer indicado entre paréntesis.

---

## Estructura del capítulo

```
4.4 (cola)  Power supply, transformers, switchboards
4.5 DESIGN OF ELECTRICAL PUMPING INSTALLATIONS
├── 4.51   Introduction
├── 4.52   Factors affecting pump design
├── 4.53   Detailed design of installations
│   ├── 4.532  General considerations & sizing procedure
│   ├── 4.533  Example #1A water well (60 Hz)
│   ├── 4.534  Example #1A 50 Hz (affinity laws)
│   ├── 4.535–536  Example #1B/#1C water wells
│   ├── 4.538  Example #2A oil well (no gas)
│   ├── 4.539  Example #2B oil well (no gas)
│   ├── 4.5310 Example #3 oil wells with gas
│   └── 4.5311 Example #4 viscous crudes
└── 4.54   Operational approaches (Couto)
    ├── 4.543  Solution model
    ├── 4.544  Approaches (systems / flow rate / free gas)
    └── 4.545  Special topics (GLF/OF, gas control)
```

---

## 4.4 (cola) — Suministro eléctrico de superficie

Configuraciones típicas de transformadores y switchboards (Figs. 4.414–4.420):

- 12 500 V → 2 400 V (switchboards 200–600 hp; motores 2 000–2 300 V)
- 12 500 V → 762–830 V (banco central, conexión wye sobre 480 V)
- 440 V con autotransformador local 880 V
- Generadores 2 400 V directo a switchboard

Elección de voltaje según hp y profundidad:

| Caso | Recomendación |
|---|---|
| Bajo hp, pozos someros | 440 V |
| hp ≤ 70, profundidad media | 762–830 V |
| 70–200 hp, pozos profundos | 1 500 V switchboard, motor 900–1 300 V |
| > 200 hp | Elegir 1 500 V o 2 400 V por economía |

---

## 4.51 — Introducción al diseño

Tres consideraciones obligatorias y en este orden:

1. Bomba acorde al **caudal deseado** — cada bomba tiene un rango de eficiencia. Buena IPR evita sobredimensionamiento (que produce *pump-off* intermitente).
2. Bomba acorde al **incremento de presión** necesario (TDH) — se traduce en el número de etapas.
3. Motor acorde al **flujo y head** y a la eficiencia de la etapa.

Factores adicionales del fluido: densidad, viscosidad, contenido de gas, corrosividad, abrasividad.

---

## 4.52 — Factores que afectan el diseño

### 4.521 Flow configuration / tamaño del casing → `bes/core/pump_design.py`, `bes/catalogs/loader.get_pumps_by_casing`

Casing controla el OD máximo de bomba y motor. **Regla**: usar el motor de mayor diámetro que entre en el casing — minimiza costo inicial y operativo.

**Tabla 4.51 — Costo relativo de motor (120 hp)**

| Casing | OD bomba/motor | Costo relativo |
|---|---|---|
| 7" | 5.4" | 1.00 |
| 5½" | 4.56" | 1.44 |
| 4½" | 3.75" | 2.30 |

La mayoría de las instalaciones bombean por tubería sin packer (la bomba cuelga del tubing).

### 4.522 IPR del pozo → `bes/core/ipr.py`

Métodos en orden de complejidad creciente (todos ya implementados en el proyecto):

- **Lineal (PI)** — válido por encima del Pb o en pozos de agua sin gas.
- **Vogel** — flow efficiency = 1, debajo de Pb.
- **Standing extension de Vogel** — para flow efficiency ≠ 1 (pozos dañados o estimulados).
- **Fetkovich** — `q = J(P_R² − P_wf²)` con coeficiente C; requiere flow-after-flow o test isocronal.

Un PI también puede expresarse en `b/d/ft de drawdown` (común en pozos de agua) para mantener continuidad con las curvas del fabricante (que dan ft/etapa).

### 4.523 Bombear gas o no → `bes/core/gas_handling.py`

Dos estrategias:

- **PIP > Pb**: no hay gas libre en la entrada → la bomba ve `q_st × Bo` (caso simple).
- **PIP < Pb**: tubing y cable más cortos pero la bomba debe manejar `q_st × Bo + free gas`. Riesgo de **gas lock** si el ratio gas/líquido a la entrada es alto.

Umbrales clave:

- Free gas / liquid ≤ 0.1 → bomba opera ~normal.
- Por encima de 0.1 → empieza a producir menos head.
- Crece más → gas lock.

### 4.524 Separación de gas

GIP (Gas Ingestion Percentage) — fracción del gas libre que pasa por la bomba. **No hay manera precisa de predecirlo** (incertidumbre ±15–25 %). Recomendación del libro: hacer cálculos para varios valores de GIP y elegir bomba con flexibilidad.

### 4.527 Efecto de la viscosidad → `bes/core/pump_design.py` (corrección HI)

La viscosidad:

- Baja la curva head-capacity (rotando alrededor del head a flujo cero).
- Reduce la eficiencia.
- Mueve el BEP a flujos menores.

Las curvas del catálogo se obtienen con agua (~30 SSU). Para fluidos más viscosos hay que aplicar las correcciones del Hydraulic Institute (Tablas 4.520 y 4.521 del libro).

**Emulsiones:** entre 20–80 % de corte de agua puede formarse emulsión cuya viscosidad supera la del crudo en factores de 2–6×. Riling sugiere ×2–3 para WC 20–40 % y ×5–6 para WC 55–75 %.

### 4.528 Temperatura

Por cada **18 °F** sobre el rating del aislamiento del motor, la **vida útil se reduce a la mitad**. Cables disponibles hasta 350 °F (más caros a mayor temperatura). La temperatura también afecta el cálculo de volumen total (PVT del gas).

### 4.529 Operación vs. unloading

Si el pozo se mata con salmuera, los hp para desplazar el fluido pesado pueden ser mayores que los hp operativos. Un motor admite **hasta 20 % de overload** durante el unloading. Hay que verificar ambas condiciones en el diseño final.

---

## 4.5324 Total Dynamic Head → `bes/core/tdh.py`

Definición precisa (sin gas):

```
TDH = Vertical Lift  +  Tubing Friction  +  Wellhead Pressure Head
                                         −  Suction Head (columna sobre la entrada)
```

Con gas, los cálculos deben hacerse **en psi y luego convertirse a ft** (porque la densidad cambia con la profundidad). Para diseño se sustituyen las pérdidas en flowline horizontal por una `P_wh` equivalente.

### Ejemplo del libro (Example #2A)

```
WHP requerido       = 200 psig
Pump setting depth  = 10 570 ft
Tubing              = 2⅞" EUE
Caudal              = 1 600 b/d
Fluido              = 70 % oil 40°API + 30 % water (1.05 SG) → 54.79 lb/ft³
Fluido sobre entrada = 650 ft

WHP en ft de head    = 200 × 144 / 54.79 = 526 ft
Friction loss        = 10.57 × 20.5 ft/1000 = 217 ft   (Hazen-Williams, C=120)
Elevation Δ          = 10 570 ft
Fluido sobre intake  = −650 ft
TDH                  = 10 633 ft
```

**Fórmulas en uso** (Brown §4.5324, ya implementadas):

- Hazen-Williams: `V = C·R^0.63 · S^0.54 · 0.001 ⁻⁰·⁵⁴` con C = 120 (acero nuevo); equivalente operativo: `0.2083·(100/C)^1.852 · q_gpm^1.852 / d^4.8655` ft/100 ft.
- HP del motor: `hp = hp/stage × n_stages × SG` — el `hp/stage` del catálogo es para SG = 1.0 (agua), por eso multiplicamos.

---

## 4.5325 Cable selection → `bes/core/electrical.py`, `bes/catalogs/cables.json`

**Tabla 4.52 — Capacidad de corriente típica**

| Cable | Max amp |
|---|---|
| #1 Cu | 115 |
| 2/0 Al | 115 |
| #2 Cu | 95 |
| 1/0 Al | 95 |
| #4 Cu | 70 |
| #2 Al | 70 |
| #6 Cu | 55 |
| #4 Al | 55 |

**Voltage drop** se lee de la Fig. 4.54 (gráfico Volts/1000 ft vs amperaje, por tamaño de cable y temperatura).

**Voltaje en superficie requerido**:

```
V_surf = (V_motor + V_cable_drop) × 1.025
                                   ──┬──
                          margen 2.5 % por pérdidas en transformador
```

Ejemplo: motor 890 V, 58 A, 3 600 ft de #2 Cu → drop 20 V/1000 ft × 3.6 = 72 V → 962 V × 1.025 = 990 V superficie.

Tipos disponibles (TRW-Reda):

- **Redalene** (estándar, ≤ 180 °F)
- **Redared** (galvanizado, ≤ 300 °F)
- **Polietileno** (corrosión, ≤ 140 °F)

---

## 4.5326 Sizing del transformador

```
kva = V_surf × A_motor × √3 / 1000      (Eq. 4.51)
```

Si se usa banco de 3 monofásicos, dividir entre 3 y redondear al tamaño comercial siguiente (37.5, 50, 75, 100 kva, etc.).

**Tipo de hookup**: AA, YA, YY — la mayoría de los submergibles son MA (delta-wye) o YA (wye abierto).

---

## 4.5327 Procedimiento resumido (11 pasos) → mapeado a `bes/recommender/recommendation_engine.py`

1. Recolectar y analizar datos del pozo, producción, fluido y eléctricos.
2. Determinar capacidad productiva (PIP/profundidad de bomba) y volumen total a bombear.
3. **Calcular TDH** = friction + system pressure + vertical lift.
4. Para (Q, TDH) elegir el tipo de bomba más eficiente que entre en el casing.
5. **Calcular número de etapas** = TDH / (head/stage).
6. **Determinar HP del motor** usando la mayor SG esperada (incluye correcciones por viscosidad y unloading).
7. Seleccionar **tamaño y tipo de cable** según ampacidad y temperatura.
8. Calcular **drop de voltaje en cable** y voltaje requerido en superficie → fija el switchboard.
9. Calcular **kva del transformador**.
10. Seleccionar accesorios: tubing head, válvulas check/bleeder, etc.
11. Definir medidas adicionales: protección contra corrosión, shroud si la bomba está sobre las perforaciones, etc.

---

## Ejemplos del libro — tests de regresión actuales

### Example #1A — Pozo de agua, 10 000 b/d (60 Hz)

| Dato | Valor |
|---|---|
| Casing | 8⅝" OD (ID drift 7.892") |
| Profundidad | 2 200 ft |
| Static fluid level | 500 ft |
| PI | 10 b/d/ft drawdown |
| SG fluido | 1.1 |
| WHP requerido | (incluye 30 ft elevación + flowline) |
| **Lift** | 1 500 ft (1 000 drawdown + 500 static) |
| **Friction tubing** (5") | 18.5 ft/1000 → 29.6 ft |
| **WHP head** | 30 + 65 ft/1000 × 2000 = 140 ft |
| **TDH** | 1 670 ft |
| Bomba | I-300 (Centrilift, 8 000–11 500 b/d) |
| head/stage @ 10 000 b/d | 59.5 ft |
| **Etapas** | 28 |
| hp/stage | 5.85 (water) |
| **HP motor** | 28 × 5.85 × 1.1 = 180 hp → motor 200 hp 1160 V 105 A |

### Example #1A 50 Hz (afinidad)

```
Q ∝ N        Q₅₀ = (2915/3500) × Q₆₀ = 83.3 %
H ∝ N²       H₅₀ = 69.4 %
HP ∝ N³      HP₅₀ = 57.8 %
```

48 etapas (vs 28 en 60 Hz), 190 hp (vs 188).

### Example #2A — Pozo de petróleo sin gas, 1 600 b/d

```
TDH = 5 060 (lift) + 250 (fricción 2⅜" tubing) + 520 (WHP) = 5 830 ft
Bomba: D-40 (Reda, 4" OD para casing 5½")
head/stage @ 1227 bpd = 23 ft → 254 etapas
hp/stage máx = 0.99 → 254 × 0.99 × 0.89 = 224 hp (operación)
Motor seleccionado: 90 hp 456 series 1260 V 45 A (con margen unloading)
Cable: #4 Cu Redalene, drop 24 V/1000 ft → V_surf = 1438 V
kva: 1450 × 45 × 1.73 / 1000 = 113 → 3 × 50 kva
```

### Example #2B — Pozo de petróleo sin gas, 1 600 STB/D

Similar a #2A pero con casing 7", tubing 2⅞", profundidad 11 000 ft, 30 % WC.

```
Bomba: I-42B (Centrilift 513 series para casing 7")
head/stage @ 1600 bpd = 38.3 ft → 112 etapas
hp/stage = 0.69 → 112 × 0.69 × 0.84 = 65 hp
Motor: 75 hp 544 series 1350 V 35 A
TDH: 4258 ft
```

### Example #3 — Pozo con gas (procedimiento clave)

Procedimiento resumido (16 pasos, §4.53102):

1. Determinar PIP.
2. Determinar **discharge pressure** con correlación multifásica (Hagedorn-Brown / Beggs-Brill / Orkiszewski / Duns-Ros / Poettmann-Carpenter).
3. ΔP = P_disch − P_intake.
4. Dividir ΔP en **incrementos** (200 psi típico para mano; cada etapa para computadora).
5. En cada presión calcular volumen de oil/gas/water, masa, ρ_mix, gradiente.
6. Promediar gradientes entre puntos.
7. Convertir a ft de head.
8. Q promedio entre puntos.
9. Para cada Q seleccionar bomba y leer ft/stage.
10. ΔP/etapa = gradiente × (ft/stage).
11. n_etapas por incremento = ΔP_incr / (ΔP/etapa).
12. **Total** = Σ etapas. Probable **bomba combinada** (tapered): ej. 120 etapas X-50 + 60 etapas Z-60.

#### Resultados clave del Example #3B (500 b/d oil, GOR=500, depth 7000 ft, 5½" csg)

| Caso | Stages | HP | Discharge psi | Notas |
|---|---|---|---|---|
| Hagedorn long-hand, 100 % gas, no slip | 209 D-40 | 27 | 1300 | 200 psi increments |
| Orkiszewski computer, 100 % gas, no slip | 21 D-55 + 173 D-40 | 27.84 | 1214 | tapered |
| Orkiszewski, 100 % gas, **deterioration** | 263 mixed | ~30 | 1214 | +69 etapas vs no-slip |
| Orkiszewski, 50 % gas vented | 211 (58 D-40 + 153 D-20) | 31.86 | 1832 | menor lift en tubing |
| Orkiszewski, 50 % gas + 50 % water | 231 D-20 | 41.25 | 2628 | sin deterioration |

**Insight clave (Brown):** ventear 50 % del gas *aumenta* los HP (de 27.84 a 31.86) porque se pierde el efecto de aligeramiento de la columna de tubing. Hay que evaluar el trade-off.

**Pump deterioration**: el head efectivo de la bomba se degrada cuando el ratio in-situ free gas / liquid supera 0.1, llega a 0 cuando supera 3. Las correcciones específicas son confidenciales por fabricante.

### Example #3C — Pozo con gas (computer Centrilift)

Usa Vogel para IPR (debajo de Pb). Soporta múltiples profundidades de bomba para evaluar sensibilidad. Encuentra:

- **PIP > Pb** (10 570 ft): 32 etapas Y-62B, 25 hp. Caso "todo en solución".
- **PIP = Pb** (7 656 ft): 34 etapas, 27 hp.
- **Punto donde GLR libre alcanza el límite** (5 226 ft): 63 etapas, 49 hp.
- 4 000 ft → infeasible (gas excesivo).

### Example #4 — Crudos viscosos (Riling)

Procedimiento (§4.53112):

1. Calcular TDH como si fuera agua (SG=1.0).
2. Viscosidad libre de gas a T_res (Fig. 4L.1 del libro).
3. Corregir por gas en solución (Fig. 4L.2).
4. Convertir a SSU.
5. Si hay corte de agua: aplicar factor 2–3 (WC 20–40 %), 5–6 (WC 55–75 %).
6. Aplicar factores de las **Tablas 4.520 / 4.521** (60 % o 70 % bombas de eficiencia máxima):
   - Capacity factor (Q_w / Q_v)
   - Head factor (H_v / H_w)
   - HP factor

Ejemplo: 16°API, 130°F, GOR 50 → 65 cp gas-saturado → 400 SSU → ×2 emulsión = 800 SSU → factores 85.5 / 86.0 / 117.0 → 1990 b/d corregido, 137 stages Y-62B, 162 hp.

---

## 4.54 — Aproximación operacional (Couto) — base para `bes/core/nodal_analysis.py`

El planteo de Couto generaliza el problema en términos de variables operacionales y restricciones en un espacio (q, p, h):

### Variables del problema

```
Operacionales:    q_st  (caudal stock-tank)
                  D_PM  (profundidad de seteo)
                  f_gPM (fracción de gas libre bombeada)

Ambientales:      P_PMI (pump inlet),  P_PMO (pump outlet)
                  T_PM, P_PML, P_PMH

Configuración:    q_PMUL (rate range upper),  q_PMLL (lower)
                  T_PMLIM, ΔP_INTL, ΔP_EXTL
```

### Constraints clave

- `ΔP_INT = P_PMH − P_PML ≤ ΔP_INTL` (no estallar).
- `ΔP_EXT = P_PMO − P_PMI ≤ ΔP_EXTL` (no colapsar).
- `T_PM ≤ T_PMLIM`.
- `q_PMLL ≤ q_PML, q_PMH ≤ q_PMUL`.
- `q_PML ≤ GLF × q_liquid_in_situ` (criterio de gas-lock).

### Master regions (Figs. 4.514–4.539)

Tres modos gráficos para resolver el mismo problema:

- **Systems approach**: D_PM fijo, varían (q_st, f_gPM). Plot p × q. Se identifican zonas inaccesibles por venteo, gas-lock, ΔP interno/externo, T y q_PMUL/q_PMLL.
- **Flow rate approach**: q_st fijo, varían (D_PM, f_gPM). Útil para análisis de incompatibilidad y selección de bomba con caudal predefinido.
- **Free gas approach**: f_gPM fijo, varían (q_st, D_PM). Útil para evaluar venteo controlado.

### 4.5451 Criterio de diseño de la serie de bombas

**Gas Lock Factor**:

```
GLF = q_PMLIM / q_liquid_in_situ
    = 1 / λ_L_min     (inversa del holdup mínimo permisible)
```

GLF típicamente > 1 (O'Neil sugiere **GLF = 2** como regla general).

**Overlap Factor** entre bombas consecutivas de una serie:

```
OF = (q_PMLL)_{i+1} / (q_PMUL)_i        debe ser < 1
```

Para tener una serie de bombas conectables que cubra todos los q_st posibles con cualquier f_gPM ∈ [0,1]:

```
(q_PMLIM)_i  = (q_PMLL)_i × GLF
(q_PMLL)_{i+1} = (q_PMUL)_i × OF
```

Ejemplo con GLF=1.67 y OF=0.90: serie 1000–1670, 1500–2500, 2250–3750, 3375–5625, 5063–8438, 7594–12 656.

### 4.5452 Control de gas (cuatro técnicas)

1. **Surface choke** (4.54522). Cerrar el choke del casing aumenta P_ch y baja la interfaz gas/líquido en el anular, pero *no cambia* f_gv mientras la interfaz no toque la entrada de la bomba. Solo después de ese punto crítico el choke controla efectivamente el venteo.
2. **Shifting pump within the well** (4.54523). f_gv natural varía con la profundidad — máxima cuando la bomba se acerca a la interfaz gas/líquido del anular abierto, mínima cuando está frente a las perforaciones.
3. **Bottomhole separation** (4.54524). Aumenta el venteo natural sin aumentar el gas libre — geometría diseñada para favorecer la velocidad ascendente axial sobre la centrípeta radial. Idealmente lleva f_gv → 1.
4. **Gas recycling** (4.54525). Si P_wh tubing > P_ch, se puede recircular gas hacia abajo por el anular. f_gPM > 1. Reduce la presión interna que la bomba debe desarrollar y por tanto el HP.

### 4.5453 Determinación de PIP desde superficie

Tres casos:

- **Caso 1**: PIP < P_sat, sin venteo → `PIP = P_ch + ΔP_static_gas_column`.
- **Caso 2**: PIP < P_sat, con venteo → cerrar choke gradualmente; cuando P_ch deja de subir, esa P_ch es la máxima → `PIP ≈ P_ch_max + ΔP_static_gas_column`.
- **Caso 3**: PIP ≥ P_sat → no hay gas libre en la entrada; método similar a caso 1 pero usando densidad de líquido.

---

## Mapeo a la arquitectura del BES Designer

| Sección Brown | Módulo del proyecto | Notas |
|---|---|---|
| 4.522 IPR | `bes/core/ipr.py` | Vogel, Linear y Fetkovich implementados |
| PVT (Standing) | `bes/core/pvt.py` | Standing, DAK, Beggs-Robinson |
| 4.5324 TDH | `bes/core/tdh.py` | Hazen-Williams + lift + WHP head |
| 4.5325 Cable | `bes/core/electrical.py`, `bes/catalogs/cables.json` | Tabla 4.52 → `get_cable(amps, temp_f, voltage)` |
| 4.5326 Transformer | `bes/core/electrical.py` | `kva = V × A × √3 / 1000` |
| 4.5327 Procedure | `bes/recommender/recommendation_engine.py` | 11 pasos del libro |
| 4.5310 Gas wells | `bes/core/gas_handling.py`, `bes/core/multiphase.py` | Hagedorn-Brown / Beggs-Brill |
| 4.5311 Viscous | `bes/core/pump_design.py` | Tablas HI 4.520/521 |
| 4.54 Couto operational | `bes/core/nodal_analysis.py` | Master regions, GLF, dominancia |
| 4.5451 GLF/OF | `bes/recommender/ranking.py` (distancia al BEP) | criterio 1 del ordenamiento |

### Sugerencias de validación adicional

Las siguientes constantes/tablas del libro vale la pena chequear contra los catálogos JSON actuales:

1. **Tabla 4.51** (costo relativo de motor por casing) — quedó sin uso al eliminarse la dimensión de costo del ordenamiento.
2. **Tabla 4.52** (ampacidad de cables) — verificar que `cables.json` la respeta.
3. **Tablas 4.520/4.521** (correcciones HI por viscosidad) — si están en `pump_design.py`, agregar test contra el ejemplo de viscosos del libro.
4. **GLF = 2** (O'Neil) — confirmar que se aplica como límite superior en `gas_handling.complete_gas_design`.
5. **Pump deterioration** (degradación cuando GLR libre/líquido > 0.1, total > 3) — chequear si está implementado.

### Tests de regresión que ya están alineados

| Test | Sección Brown | Estado |
|---|---|---|
| Example #1A — 28 stages, 180 hp | 4.533 | ✅ en `backend/tests/test_pump_design.py` (CLAUDE.md) |
| Example #2A — 254 stages, ≈79 hp | 4.538 | ✅ |
| Example #2B — 112 stages, ≈65 hp | 4.539 | ✅ |
| Friction 5" new pipe, 10 000 b/d ≈ 18.5 ft/1000 | 4.533 | ✅ |

### Tests faltantes (sugeridos)

- **Affinity laws 60↔50 Hz** (§4.534): 28 → 48 stages, 180 → 190 hp.
- **Example #3B Hagedorn long-hand**: 209 stages D-40, 27 hp, P_disch 1300 psi.
- **Example #3B Orkiszewski no-slip**: 21 D-55 + 173 D-40, 27.84 hp.
- **Example #4 viscous**: 137 stages Y-62B, 162 hp.

---

## Caveat sobre el OCR

Este resumen se generó a partir del OCR (Tesseract en inglés) del PDF escaneado original. Hay errores típicos:

- Subíndices y caracteres griegos a veces mal interpretados (γ ↔ y, ρ ↔ p).
- Algunas tablas perdieron alineación (números desplazados).
- Fórmulas con subíndices Unicode pueden estar corruptas.

Si querés validar puntualmente alguna fórmula o número, te puedo re-OCR la página específica a más alta resolución.
