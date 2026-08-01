# Base de datos de ingeniería — BES Designer

Arquitectura de datos: **JSON (actual) → Excel (esta carpeta) → SQLite (futuro)**.

* Diseño completo: **`DISENO_BASE_DE_DATOS.md`** (incluye anexo v3)
* Auditoría técnica: **`AUDITORIA_BASE_DE_DATOS.md`**
* Diagrama: `erd.png` / `erd.svg` / `erd.mermaid`

El proyecto original **no fue modificado**. Esta carpeta es autónoma.
**Estado: diseño conceptual v3 CERRADO**, pendiente de integración.

## Archivos vigentes (esquema v3)

| Archivo | Qué hace |
|---|---|
| `build_database_v3.py` | Genera los 14 Excel de `data_excel/` desde los JSON + datos extraídos del código |
| `database_loader_v3.py` | `ExcelCatalogManager`: misma interfaz que `CatalogManager` (se renombrará a `database_loader.py` al integrar) |
| `check_integrity.py` | Las "CHECK constraints" de Excel: PK únicas, FKs con destino, rangos, relaciones 1:1 |
| `verify_database_v3.py` | Equivalencia total contra los JSON originales |
| `data_excel/` | La base de datos: 14 archivos, cada uno con hoja README (claves, unidades, restricciones) |

Contenido de `data_excel/` (una hoja = una tabla SQLite):
`manufacturers`, `equipment_series`, `data_sources`, `pumps` (pumps,
pump_curves, pump_housings), `motors`, `cables` (cables,
conductor_voltage_drop), `seals` (seals, seal_motor_compatibility),
`gas_handlers`, `sensors`, `transformers`, `vsds` (plantilla),
`switchboards` (plantilla), `well_examples` (9 tablas, 6 casos Brown),
`real_wells` (plantilla con field_cases, installation_components,
fluid_samples).

## Uso

```bash
python build_database_v3.py    # 1. bootstrap desde los JSON legados
python import_alkhorayef.py    # 2. + fabricante Alkhorayef (37 bombas del PDF)
python check_integrity.py     # 3. valida claves, FKs y restricciones
python verify_database_v3.py  # 4. equivalencia con los JSON
```

**Importante:** `build_database_v3.py` regenera desde cero; después de
correrlo hay que volver a correr los importadores (paso 2).

## Esquema v3.1 — importación Alkhorayef (primer fabricante real)

`import_alkhorayef.py` lee el PDF del catálogo 2019 y agrega: el
fabricante, la fuente ALKH-01, las series nuevas (338→1100) y 37 bombas
SPECTRUM con los campos que pide la metodología de la cátedra:
`housing_pressure_limit_psi` (y high), `shaft_diameter_in`, límites de
eje @60Hz (std/HS/UHS), `stage_type`, `min_casing_size_in` y rango
floater. `pump_housings` ganó columnas reales: `housing_code`,
`stages_compression`, `stages_ar_floater/compression` (AR = abrasion
resistant), `length_ft`, `weight_lbs`.

**Curvas: DIGITALIZADAS (v3.2).** `extract_curves_alkhorayef.py` extrajo
las 37 curvas de los gráficos del catálogo: OCR de ticks (tesseract con
fallback por segmentos) + ajuste robusto RANSAC + máscara de color, con
QA por bomba (pico de eficiencia en el BEP, identidad hidráulica
eff = Q·H/(135 773·HP) dentro de ±12 %, head decreciente). 35 bombas
automáticas + 2 por lectura visual (WE-8500, WN-1050) + 1 con override
documentado (WD-3000: el pico real de la curva del catálogo no coincide
con el BEP de su propia ficha). También se cargó el shut-off head
(columna `shutoff_head_ft_per_stage`, dato de la verificación MaxP).
Fuente: ALKH-02. Nota QA: la leyenda de los gráficos del catálogo tiene
los colores intercambiados respecto a los ejes; se asignó por física.

**Estado del catálogo de bombas: 60 con curva** (23 legadas Brown +
37 Alkhorayef). Verificación: `verify_database_v31.py` (semántica de
subconjunto: las legadas idénticas, las nuevas amplían las consultas).
Las capturas de trabajo de la digitalización (`_chart_*.png`,
`_banda_*.png`) ya se borraron; sobrevive `_curva_wa550.png` porque la
usa `generar_memoria_tecnica.py`.

Resultados vigentes:

```
INTEGRIDAD OK: ... (1 aviso: serie 513 sin motores cargados — documentado)
ESQUEMA v3 VERIFICADO: 132 registros idénticos a los JSON; selecciones
de equipo e interpolación idénticas.
```

## `_historico/` — etapas superadas

Nada de esta carpeta se usa: está solo como historial de la evolución
incremental del diseño (v1 plano → v2 normalizado → v3 auditado).

| Etapa | Archivos |
|---|---|
| v1 (plano) | `migrate_json_to_excel.py`, `excel_loader.py`, `verify_migration.py`, `_migrate_exec.py`, `_run_migration_tmp.py` |
| v2 (normalizado) | `build_database.py`, `database_loader.py`, `verify_database.py`, `_build_runner.py` |
| respaldos | `pumps_RESPALDO_*.xlsx` — copias de `data_excel/pumps.xlsx` previas a cada importación |

## Integración (próximo paso, pendiente de aprobación)

```python
# antes
from catalogs.loader import CatalogManager
catalog = CatalogManager()

# después
from database_migration.database_loader_v3 import ExcelCatalogManager
catalog = ExcelCatalogManager()
```

Un cambio de línea + corrida completa de los 400+ tests.

## El diseño en siete líneas (para la defensa)

1. Una hoja Excel = una tabla SQLite; migrar es cambiar el motor, no el diseño.
2. 3FN verificada con datos, no solo declarada (la auditoría corrigió una violación real en cables).
3. Claves naturales legibles; toda FK tiene destino comprobable (`check_integrity.py`).
4. Bibliografía normalizada: cada dato referencia su fuente vía `data_sources`.
5. Los datos de ingeniería salieron del código (transformadores de `electrical.py`).
6. `installation_components` modela ensambles BES reales (tándems), no simplificaciones.
7. Entidades futuras nombradas (costos, derating, viscosidad, tubulares, corridas) sin obstruir nada.
