# Diseño de la Base de Datos — BES Designer

**Etapa:** diseño completo del modelo de datos (Excel hoy, SQLite mañana).
**Regla de oro:** la estructura lógica en Excel es idéntica a la que tendrá
SQLite. Migrar será cambiar el motor de almacenamiento, no el diseño.

---

## 1. Objetivo y estrategia en tres etapas

| Etapa | Almacenamiento | Estado |
|---|---|---|
| 1 | JSON dentro del proyecto (`catalogs/*.json`) | Actual, en producción |
| 2 | **Excel** (`database_migration/data_excel/`) | Esta etapa |
| 3 | SQLite (un archivo `.db`) | Futura |

Excel se usa durante el desarrollo porque un Ingeniero de Petróleo puede
editarlo, validarlo y explicarlo sin programar. Cada **hoja** de Excel es
una **tabla**; cada **archivo** agrupa las tablas de un mismo dominio.
En SQLite, cada hoja pasa a ser una tabla con el mismo nombre y columnas.

## 2. Convenciones de diseño

1. **Nombres de tabla y columna en inglés, snake_case** — idénticos a las
   claves que usa el código. La documentación (hojas README) está en español.
2. **Unidades en el nombre de la columna** (`od_inches`, `max_temp_f`,
   `flow_bpd`): imposible confundir unidades, no hace falta consultar nada.
3. **Claves primarias naturales y legibles** (`pump_id = "Reda_400_D-40"`),
   no enteros autoincrementales. Justificación: las hojas de detalle se leen
   sin cruzar tablas, y los mismos IDs sobreviven a la migración a SQLite.
   Costo aceptado: si un ID cambia, hay que actualizarlo en las tablas hijas
   (documentado en cada README).
4. **Columna `source` obligatoria** en toda fila de datos de ingeniería:
   trazabilidad a Brown Vol. 2B, catálogo de fabricante o norma. Ningún
   número queda sin referencia.
5. **Celda vacía = NULL** (dato no aplicable o no disponible), nunca 0.
6. **Un archivo por dominio**: agregar un fabricante o un equipo es agregar
   filas; agregar un tipo de equipo nuevo es agregar un archivo. El código
   no se modifica en ningún caso.

## 3. Normalización aplicada

* **1FN (primera forma normal — sin listas dentro de celdas):** las listas
  que en JSON eran arrays pasan a tablas de detalle:
  `housing_options` → tabla `pump_housings`;
  `compatible_motor_series` → tabla `seal_motor_compatibility`;
  curvas de bomba → `pump_curves`; caída de tensión → `cable_voltage_drop`.
* **2FN/3FN (sin dependencias parciales ni transitivas):** el fabricante
  deja de repetirse como texto en cada equipo y pasa a la tabla
  `manufacturers`; los equipos lo referencian por FK. Datos del fabricante
  (país, notas) viven en un solo lugar.
* **Desnormalización deliberada: ninguna.** Todas las tablas están en 3FN.

**Por qué importa (para la defensa):** sin 1FN no se puede consultar "qué
bombas tienen housing de 100 etapas" con un filtro simple; sin 3FN, corregir
el nombre de un fabricante exige tocar N filas en M archivos con riesgo de
inconsistencia. La normalización elimina redundancia y anomalías de
actualización — y es exactamente lo que SQLite espera recibir.

## 4. Dominios y archivos

```
data_excel/
├── manufacturers.xlsx      # tabla maestra de fabricantes
├── pumps.xlsx              # pumps, pump_curves, pump_housings
├── motors.xlsx             # motors
├── cables.xlsx             # cables, cable_voltage_drop
├── seals.xlsx              # seals, seal_motor_compatibility
├── gas_handlers.xlsx       # gas_handlers
├── sensors.xlsx            # sensors
├── transformers.xlsx       # transformers  (datos extraídos de electrical.py)
├── vsds.xlsx               # vsds          (plantilla, catálogo futuro)
├── well_examples.xlsx      # wells + 6 tablas 1:1 (casos de validación Brown)
└── real_wells.xlsx         # misma estructura + field_cases + fluid_samples
```

## 5. Catálogo de tablas

### 5.1 `manufacturers` — fabricantes
| Columna | Tipo | Restricción | Descripción |
|---|---|---|---|
| manufacturer_id | texto | **PK** | Nombre corto único (ej. `Reda`) |
| full_name | texto | NOT NULL | Razón social (ej. Schlumberger REDA) |
| country | texto | NULL | País de origen |
| notes | texto | NULL | Observaciones |

**Por qué existe:** es la tabla padre de todos los catálogos (1:N con cada
equipo). Agregar un fabricante = una fila acá + sus equipos en las otras
tablas. Cero código.

### 5.2 `pumps` / `pump_curves` / `pump_housings`
* `pumps` — PK `pump_id`; FK `manufacturer_id → manufacturers`.
  Columnas: series, model, od_inches, min_flow_bpd, max_flow_bpd,
  bep_flow_bpd, max_stages, source.
  Restricciones: min_flow < bep_flow < max_flow; od_inches > 0.
* `pump_curves` — **PK compuesta (pump_id, flow_bpd)**; FK pump_id.
  Columnas: head_ft_per_stage, hp_per_stage, efficiency (0–1).
  Cardinalidad: pumps 1:N pump_curves (10–11 puntos por bomba).
* `pump_housings` — **PK compuesta (pump_id, stages)**; FK pump_id.
  Una fila por housing disponible. Cardinalidad 1:N.

**Decisión clave:** la curva de rendimiento NO se guarda como polinomio
ajustado sino como puntos discretos del catálogo del fabricante, y el
código interpola. Transparencia: cualquier punto puede verificarse contra
el catálogo en papel.

### 5.3 `motors`
PK `motor_id` (fabricante_serie_modelo — unicidad verificada sobre los 50
motores actuales); FK manufacturer_id. Columnas: series, model, hp_rating,
voltage, amperage, length_ft, max_temp_f, od_inches, source.
Nota: cada combinación tensión/corriente de un mismo frame es un registro
(así viene en los catálogos de fabricante).

### 5.4 `cables` / `cable_voltage_drop`
* `cables` — PK `cable_id` = fabricante_tipo_**conductor**_calibre.
  El conductor (CU/AL) es parte de la clave: existe el mismo calibre en
  cobre y aluminio con caídas de tensión ~65 % distintas (este error de
  clave fue detectado por la verificación automática en la etapa 1).
* `cable_voltage_drop` — **PK compuesta (cable_id, temp_f)**;
  columna v_per_amp_per_1000ft. El loader interpola linealmente en
  temperatura. Cardinalidad: cables 1:N (4 temperaturas por cable).

### 5.5 `seals` / `seal_motor_compatibility`
* `seals` — PK `seal_id`; FK manufacturer_id. Columnas: series, model,
  type (∈ {labyrinth, bag, combined} — Brown §4.5325), od_inches,
  length_ft, thrust_capacity_lbs, max_temp_f, shaft_hp_standard,
  shaft_hp_high_strength, source.
* `seal_motor_compatibility` — **PK compuesta (seal_id, motor_series)**.
  Resuelve la relación **N:M** sellos ↔ series de motor: un sello sirve
  para varias series y una serie admite varios sellos. `motor_series`
  referencia el dominio de valores de `motors.series` (en SQLite se
  reforzará con un CHECK o tabla de series).

### 5.6 `gas_handlers`
PK `gas_handler_id`; FK manufacturer_id. Columnas: series, model,
type (vortex/rotary/...), position, od_inches, length_ft, weight_lbs, hp,
min_flow_bpd, max_flow_bpd, max_efficiency (0–1), source, range_source.

### 5.7 `sensors`
PK `sensor_id`; FK manufacturer_id. Columnas: model, intake_pressure_max_psi,
intake_temp_max_f, discharge_pressure_max_psi (NULL = no mide descarga),
motor_winding_temp_max_f, vibration_monitoring (booleano), vibration_max_g,
od_inches, length_in, weight_lbs, max_motor_voltage, source.

### 5.8 `transformers` — **nuevo** (datos extraídos del código)
Hasta ahora los tamaños estándar vivían hardcodeados en
`core/electrical.py` (`_TRANSFORMER_SIZES_KVA`), violando la regla de "sin
datos de ingeniería en el código". Pasan a tabla:

| Columna | Tipo | Restricción | Descripción |
|---|---|---|---|
| transformer_id | texto | **PK** | ej. `Generic_3ph_100kVA` |
| manufacturer_id | texto | FK, NULL | `Generic` para tamaños estándar |
| kva_rating | real | NOT NULL, > 0 | Potencia aparente [kVA] |
| phases | entero | ∈ {1, 3} | Monofásico (banco de 3) o trifásico |
| primary_voltage_v | real | NULL | Tensión primaria [V] |
| secondary_voltage_min_v / max_v | real | NULL | Rango del secundario con taps [V] |
| loss_pct | real | NULL | Pérdida típica [%] (hoy 2.5 % en el código) |
| source | texto | NOT NULL | Norma/catálogo |

Semilla inicial: los 8 tamaños estándar trifásicos (25–300 kVA) que hoy usa
`select_transformer()`. Cuando se incorporen catálogos reales de
fabricantes, se agregan filas — el diseño no cambia.

### 5.9 `vsds` — **nuevo** (plantilla para catálogo futuro)
| Columna | Tipo | Restricción | Descripción |
|---|---|---|---|
| vsd_id | texto | **PK** | fabricante_modelo |
| manufacturer_id | texto | FK | |
| model | texto | NOT NULL | |
| kva_rating | real | > 0 | Capacidad [kVA] |
| input_voltage_v | real | | Tensión de entrada [V] |
| output_voltage_max_v | real | | Tensión máxima de salida [V] |
| output_freq_min_hz / max_hz | real | típ. 30–90 | Rango de frecuencia [Hz] |
| current_max_a | real | > 0 | Corriente máxima [A] |
| drive_type | texto | ∈ {6-pulse, 12-pulse, PWM} | Topología |
| nema_rating | texto | NULL | Gabinete (NEMA 1, 3R...) |
| source | texto | NOT NULL | |

Se entrega **vacía** (solo estructura + README): los datos saldrán de los
catálogos en `TESIS/CATALOGOS` cuando se incorporen. La aplicación hoy solo
usa el flag `use_vsd`; cuando se implemente el diseño con VSD (leyes de
afinidad, Brown §4.5327), la tabla ya estará lista.

### 5.10 `well_examples.xlsx` — casos de validación (Brown)
Estructura espejo de los dataclasses de `core/models.py`. Hojas, todas
**1:1** con PK/FK `well_id`:

| Hoja | Contenido | Modelo Python |
|---|---|---|
| wells | well_id (PK), description, source | — |
| reservoir | static_pressure, bubble_point, productivity_index, ipr_method, reservoir_temp, drive_mechanism, datum_depth | `Reservoir` |
| fluid | oil_api, water_cut, gor, gas_sg, water_sg, viscosidades, h2s/co2, sand_production | `Fluid` |
| well_geometry | total_depth, casing (od/weight/id), tubing (od/id), perforations (top/bottom), deviation_max, temperaturas | `WellGeometry` |
| surface_conditions | wellhead_pressure_required, flowline (length/id/Δelev), separator_pressure, power_supply_voltage, frequency | `SurfaceConditions` |
| design_objectives | target_flow_rate, safety_margin_depth, allow_gas_venting, max_gip, design_life_years, use_vsd | `DesignObjectives` |
| book_reference | tdh_ft, stages, total_hp, expected_pump, notes | resultados esperados del libro |

**Por qué 1:1 en tablas separadas y no una tabla ancha:** cada hoja mapea
un dataclass de la aplicación (misma responsabilidad, mismos campos); es
autodocumentante y en SQLite permite validar cada bloque por separado.
Migrado desde `data/example_wells.json` (7 pozos).

### 5.11 `real_wells.xlsx` — pozos reales y casos de campo (futuro)
Misma estructura 1:1 que well_examples (sin book_reference), más:

* `field_cases` — PK `case_id`; FK `well_id → wells`, y FKs opcionales al
  equipamiento instalado: `pump_id`, `motor_id`, `cable_id`, `seal_id`,
  `gas_handler_id`, `transformer_id`, `vsd_id`. Columnas de operación:
  install_date, operating_frequency_hz, measured_flow_bpd, measured_pip_psi,
  status, failure_date, failure_cause, notes, source.
  **Esta tabla conecta el mundo de los catálogos con el mundo de los pozos**:
  permite comparar diseño teórico vs comportamiento real (objetivo de largo
  plazo de la tesis).
* `fluid_samples` — PK (well_id, sample_id); datos PVT de laboratorio
  (pressure_psia, temp_f, rs_scf_stb, bo_rb_stb, oil_viscosity_cp...).
  Permitirá validar las correlaciones (Standing, Beggs-Robinson) contra
  datos medidos.

Se entregan como plantillas con estructura y README; los datos saldrán de
`TESIS/Casos reales`.

## 6. Resumen de relaciones y cardinalidades

| Relación | Cardinalidad | Implementación |
|---|---|---|
| manufacturers → pumps / motors / cables / seals / gas_handlers / sensors / transformers / vsds | 1:N | FK manufacturer_id |
| pumps → pump_curves | 1:N | PK compuesta (pump_id, flow_bpd) |
| pumps → pump_housings | 1:N | PK compuesta (pump_id, stages) |
| cables → cable_voltage_drop | 1:N | PK compuesta (cable_id, temp_f) |
| seals ↔ series de motores | **N:M** | tabla puente seal_motor_compatibility |
| wells → reservoir / fluid / well_geometry / surface_conditions / design_objectives / book_reference | 1:1 | misma PK well_id en ambas |
| wells → field_cases | 1:N | FK well_id |
| field_cases → pumps, motors, cables, seals, ... | N:1 (opcionales) | FKs al equipamiento instalado |
| wells → fluid_samples | 1:N | PK compuesta (well_id, sample_id) |

## 7. Equivalencia Excel ↔ SQLite

| Concepto Excel | Concepto SQLite |
|---|---|
| Archivo .xlsx | Grupo de tablas de un dominio |
| Hoja | Tabla (`CREATE TABLE` con el mismo nombre) |
| Fila 1 (encabezados) | Nombres de columna |
| Hoja README | Comentarios de esquema + este documento |
| Celda vacía | NULL |
| Convención de PK/FK documentada | `PRIMARY KEY` / `FOREIGN KEY` reforzadas por el motor |
| Validación en verify script | `CHECK constraints` + claves reforzadas |

La única diferencia real: Excel **documenta** las restricciones y un script
las verifica; SQLite las **refuerza** automáticamente. La estructura lógica
no cambia — ese es el argumento central del diseño.

## 8. Guía rápida para la defensa

* *"¿Por qué Excel primero?"* — Editable y auditable por ingenieros sin
  programar; misma estructura lógica que SQLite, así la migración es un
  cambio de motor, no un rediseño.
* *"¿Por qué claves naturales?"* — Legibilidad de las hojas de detalle y
  estabilidad de IDs entre etapas. Trade-off documentado.
* *"¿Está normalizada?"* — 3FN completa: sin listas en celdas (1FN), sin
  fabricante repetido como texto (3FN), relación N:M resuelta con tabla
  puente.
* *"¿Cómo se agrega un fabricante nuevo?"* — Una fila en manufacturers y
  filas en las tablas de sus equipos. Ningún cambio de código: el loader
  lee lo que haya.
* *"¿Qué pasó con los datos hardcodeados?"* — Los tamaños de transformador
  se extrajeron de `electrical.py` a la tabla transformers, cumpliendo la
  regla de que los datos de ingeniería viven fuera del código.

---

# ANEXO — Esquema v3 (cambios de la auditoría)

El esquema v2 descrito arriba fue sometido a una auditoría técnica externa
(`AUDITORIA_BASE_DE_DATOS.md`). Los hallazgos aprobados producen el
**esquema v3, versión definitiva del diseño conceptual**:

## Cambios estructurales

| Hallazgo | Cambio en v3 |
|---|---|
| H1 | `conductor_voltage_drop` (PK conductor+size+temp_f) reemplaza a `cable_voltage_drop`. La caída de tensión es física del conductor/calibre; en v2 estaba duplicada en cada producto comercial (violación de 3FN verificada con los datos). |
| H2 | Nueva tabla `equipment_series` (PK series_id, od_nominal_inches). `pumps.series`, `motors.series`, `seals.series` y `seal_motor_compatibility.motor_series` son ahora FK reales. Detectó que la serie 513 estaba citada por sellos sin motores cargados. |
| H3 | `installation_components` (PK case_id+position) reemplaza las FKs simples de `field_cases`: representa el ensamble real (tándems de bombas, sellos dobles, cable + MLE). `field_cases` queda como el EVENTO (fechas, mediciones, falla). |
| H4 | Entidad `wells` unificada con discriminador `well_type ∈ {example, real}`. En Excel siguen siendo dos archivos por comodidad; en SQLite será UNA tabla. |
| H5 | Nueva plantilla `switchboards` (tableros de control; catálogo en TESIS/CATALOGOS). |
| H6 | Nueva tabla `data_sources` (PK source_id corto: BROWN-01, CHX-02...). Todas las columnas `source` pasan a `source_id` FK; la cita completa vive una sola vez. El tipo "estimado / por confirmar" marca datos a validar con catálogos reales. |

## Decisiones documentadas (sin cambio)

* **H7:** min/bep/max de bombas son valores declarados por el fabricante, no
  derivados de la curva — no violan 3FN.
* **H8:** `book_reference_details` es EAV consciente (datos de validación
  heterogéneos, solo lectura).
* **H9:** motores sin dividir en frame+devanados hasta que un catálogo
  publique variantes V/A por frame.

## Índices para la etapa SQLite (H10)

Al generar el DDL, crear índices en: toda FK (`manufacturer_id`, `series`,
`source_id`, `pump_id`, `well_id`, `case_id`), y en los campos de filtrado
frecuente de la selección de equipos: `pumps(od_inches)`,
`pumps(min_flow_bpd, max_flow_bpd)`, `motors(hp_rating)`,
`cables(max_amps, max_temp_f)`, `seals(thrust_capacity_lbs)`. Las PK
compuestas generan sus índices automáticamente.

## Verificación de restricciones (H11)

`check_integrity.py` es el equivalente Excel de las CHECK constraints:
valida unicidad de PK, FKs con destino, rangos (0<min<bep<max, 0<eff<1,
valores positivos) y relaciones 1:1 completas. Debe correr tras cada
edición manual y antes de cada integración.

## Entidades futuras nombradas (no creadas)

`equipment_costs`, `cable_ampacity_derating`, `pump_viscosity_corrections`,
`tubulars` (casing/tubing API), `design_runs`. Todas se conectan por FK a
tablas existentes; nada del esquema v3 las obstruye.

**Estado: diseño conceptual CERRADO.** Verificación vigente: 132 registros
idénticos a los JSON; integridad OK (1 aviso documentado: serie 513 sin
motores cargados).
