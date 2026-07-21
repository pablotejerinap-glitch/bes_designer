# Auditoría técnica del modelo de datos — BES Designer

**Rol:** revisión crítica externa del esquema v2, previa al congelamiento del
diseño conceptual. No se asume que el diseño actual es correcto; cada tabla
se examinó contra los datos reales y contra el uso futuro como herramienta
profesional de ingeniería.

**Veredicto general:** el esquema v2 es sólido en su estructura
(maestro→detalle, tabla de fabricantes, N:M resuelta), pero la auditoría
encontró **una violación real de 3FN**, **un error de integridad referencial
latente en los datos actuales**, y **cuatro entidades ausentes** que el
proyecto necesitará. Se recomienda un esquema v3 antes de integrar.

---

## HALLAZGOS CRÍTICOS (violan el diseño declarado)

### H1. `cable_voltage_drop` viola 3FN — dependencia transitiva confirmada con datos

El esquema v2 cuelga la caída de tensión de `cable_id`. Pero físicamente la
caída de tensión depende del **conductor y el calibre**, no del producto
comercial. Verificado contra el catálogo actual:

* 8 combinaciones (conductor, calibre) distintas entre 19 cables;
* 4 combinaciones compartidas por más de un cable;
* **0 casos** donde dos cables con igual (conductor, calibre) tengan curvas
  distintas.

Es decir: `v_drop` depende de `(conductor, size, temp_f)`, y `conductor` y
`size` dependen de `cable_id` → dependencia transitiva → los mismos puntos
están duplicados en la base. Si mañana se corrige un valor de caída para
CU #1, hay que corregirlo en todos los cables CU #1 — la anomalía de
actualización clásica que la 3FN existe para impedir.

**Recomendación (v3):** tabla `conductor_voltage_drop` con
PK `(conductor, size, temp_f)`. `cables` conserva conductor y size como FK
compuesta hacia esa tabla física. Los productos comerciales (tipo, aislación,
temperatura máxima, armadura) siguen en `cables`.

### H2. Integridad referencial rota HOY: serie de motor huérfana

`seal_motor_compatibility.motor_series` no tiene tabla destino — es una
"FK débil" contra el dominio de `motors.series`. La auditoría cruzó ambos
conjuntos y encontró que **los sellos declaran compatibilidad con la serie
`513`, que no existe en el catálogo de motores**.

Puede ser un error de tipeo (¿544? ¿540?) o una serie real aún no cargada —
en cualquier caso, el modelo actual no puede detectarlo. Con una tabla de
series y una FK real, este error habría sido imposible de ingresar.

**Recomendación (v3):** tabla `equipment_series`
(`series_id` PK, `od_nominal_inches`, `description`). `motors.series`,
`pumps.series`, `seals.series` y `seal_motor_compatibility.motor_series`
pasan a ser FK. La serie es además un concepto de ingeniería real (clase de
diámetro del equipo), merece entidad propia.
**Acción de datos:** confirmar con catálogos si `513` es serie válida
(Reda tiene protectores serie 513) y cargarla en `equipment_series`, o
corregir el dato.

---

## HALLAZGOS MAYORES (limitan el crecimiento declarado del proyecto)

### H3. `field_cases` no puede representar un ensamble BES real

El diseño v2 le da a `field_cases` una FK simple por tipo de equipo
(un pump_id, un motor_id...). Pero las instalaciones reales usan
**configuraciones en tándem**: 2–3 secciones de bomba, protectores dobles,
cable principal + extensión de motor (MLE). Con FKs simples, el modelo no
puede registrar la instalación típica de un pozo real — el propósito mismo
de la tabla.

**Recomendación (v3):** tabla `installation_components` con
PK `(case_id, position)`: case_id FK, position (orden en el ensamble,
de abajo hacia arriba), equipment_type (∈ {sensor, motor, seal, gas_handler,
pump, cable, transformer, vsd, switchboard}), equipment_id (ID en el catálogo
correspondiente), quantity, notes. `field_cases` conserva los datos del
evento (fechas, frecuencia, mediciones, estado, causa de falla) y delega el
"qué se instaló" a los componentes. Esto es exactamente cómo se describe un
tandem ESP en la práctica.

### H4. Dos tablas `wells` paralelas sin entidad unificadora

`well_examples.xlsx` y `real_wells.xlsx` definen cada una su tabla `wells`
con el mismo espacio de IDs y columnas casi idénticas. En SQLite serían dos
tablas redundantes, y nada impide que un `well_id` exista en ambas.

**Recomendación (v3, conceptual):** una única entidad `wells` con columna
discriminadora `well_type ∈ {example, real}` (patrón
generalización/especialización). `book_reference` aplica solo a examples
(1:0..1); `field`/`operator` solo a real (NULL en examples). En Excel pueden
seguir siendo dos archivos por comodidad de edición, pero el diseño
conceptual y el DDL de SQLite declaran UNA tabla — documentarlo así en el
ERD y el diseño.

### H5. Entidad ausente: `switchboards` (tableros de control)

Todo pozo BES sin VSD se controla con un switchboard — y en
`TESIS/CATALOGOS` ya existe el catálogo (`Swbd-Mtr Cntrl.pdf`). El equipo de
superficie está incompleto sin esta tabla; agregarla después de congelar el
diseño obligaría a rediseñar `installation_components`.

**Recomendación (v3):** tabla `switchboards` (switchboard_id PK,
manufacturer_id FK, model, max_voltage_v, max_amps, max_hp, nema_rating,
source). Plantilla vacía, misma categoría que `vsds`.

### H6. Fuentes como texto libre repetido

La columna `source` repite cadenas largas ("Brown, K.E. (1980) The
Technology of Artificial Lift Methods, Vol. 2b...") decenas de veces, con
riesgo de variantes de tipeo y sin posibilidad de consultar "todos los datos
que salieron de Brown". Para una tesis, la bibliografía merece estructura.

**Recomendación (v3):** tabla `data_sources` (source_id PK corto y legible,
ej. `BROWN-2B-4.5`; citation completa; type ∈ {libro, catálogo, norma,
medición}; year; file — nombre del PDF en TESIS si aplica). Las columnas
`source` pasan a contener el source_id. Trade-off aceptado: una indirección
al leer, a cambio de consistencia bibliográfica y consultas por fuente.

---

## HALLAZGOS MENORES (documentar, no cambiar)

### H7. `bep_flow_bpd`, `min/max_flow_bpd` parecen derivables de la curva
No lo son: son valores **declarados por el fabricante** (rango recomendado y
BEP de catálogo), que no necesariamente coinciden con el máximo discreto de
la curva cargada. Mantener, documentando en el README que son datos de
catálogo, no derivados — ya que un auditor de 3FN podría objetarlos.

### H8. `book_reference_details` es EAV (entidad-atributo-valor)
El patrón EAV mezcla tipos en la columna `value` y es criticable en general.
Aquí es la elección correcta: son conjuntos de validación heterogéneos entre
ejemplos del libro, de solo lectura, sin lógica sobre ellos. Documentado
como decisión consciente.

### H9. Motores: no dividir en frame + devanados (por ahora)
Conceptualmente un frame admite varios devanados (V/A). Verificado: el
catálogo actual tiene 0 modelos con múltiples variantes V/A — dividir hoy
sería sobre-normalización sin datos que lo justifiquen. Revisar cuando se
cargue un catálogo que publique variantes de devanado por frame.

### H10. Falta declarar índices para la etapa SQLite
Excel no tiene índices, pero el diseño conceptual debe declararlos:
índice en cada FK (`manufacturer_id` en todos los catálogos, `well_id` en
tablas de pozo, `case_id`/`equipment_id` en installation_components) y en
los campos de filtrado frecuente (`pumps.od_inches`, rangos de caudal).
Agregar sección al documento de diseño.

### H11. La "verificación" compara contra JSON pero no valida restricciones
`verify_database.py` prueba equivalencia con el origen, no integridad
interna (PK duplicadas, FK huérfanas — como la serie 513 —, rangos
min<bep<max, eficiencias fuera de 0–1). En Excel, donde no hay motor que
refuerce nada, ese script ES el equivalente de las CHECK constraints.

**Recomendación (v3):** script `check_integrity.py` que valide todas las
restricciones documentadas en los README. Debe correr antes de cada
integración y detectaría hoy el hallazgo H2.

---

## ENTIDADES FUTURAS (diseñar nombre y propósito ahora, crear cuando haya datos)

| Entidad | Propósito | Cuándo |
|---|---|---|
| `equipment_costs` | Costos por equipo con fecha y moneda; reintroduce la dimensión económica al scoring | Cuando haya datos comerciales |
| `cable_ampacity_derating` | Ampacidad vs temperatura (hoy max_amps es un único valor conservador) | Al cargar catálogos completos de cable |
| `pump_viscosity_corrections` | Factores de corrección de curva por viscosidad (estándar HI/fabricante) | Al implementar diseño para crudos viscosos |
| `tubulars` | Catálogo API de casing/tubing (od, peso, id, drift) para autocompletar well_geometry y evitar errores de carga | Fase de importación de pozos reales |
| `design_runs` | Resultados de corridas de diseño (inputs, equipo seleccionado, scores) para comparar alternativas e historial | Al implementar comparación de alternativas |

Estas entidades **no** se crean ahora (no hay datos que ponerles), pero el
diseño las nombra para que nada del esquema v3 las obstruya: todas se
conectan por FKs a tablas ya existentes.

---

## RESUMEN EJECUTIVO — cambios propuestos para el esquema v3

| # | Cambio | Tipo | Esfuerzo |
|---|---|---|---|
| H1 | `conductor_voltage_drop` reemplaza `cable_voltage_drop` | Corrección 3FN | Bajo |
| H2 | Nueva tabla `equipment_series` + FKs; resolver serie 513 | Integridad | Bajo |
| H3 | `installation_components` reemplaza FKs simples de field_cases | Remodelado | Bajo (tabla vacía) |
| H4 | Entidad `wells` unificada con `well_type` (conceptual + ERD) | Documentación | Bajo |
| H5 | Nueva tabla `switchboards` (plantilla) | Entidad ausente | Bajo |
| H6 | Nueva tabla `data_sources`; `source` → source_id | Normalización | Medio (tocar todos los archivos) |
| H10 | Sección de índices en el documento de diseño | Documentación | Bajo |
| H11 | Nuevo `check_integrity.py` (CHECK constraints de Excel) | Verificación | Medio |

Con estos cambios el modelo queda en 3FN real (no solo declarada), con
integridad referencial verificable, ensambles reales representables y
espacio de crecimiento nombrado. Recomiendo congelar el diseño conceptual
recién después de aplicar H1–H5 y H10–H11; H6 puede decidirse por separado
porque afecta la comodidad de edición.
