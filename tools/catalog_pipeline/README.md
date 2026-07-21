# Pipeline de catálogos de bombas ESP → MySQL `catalogos_pump`

Pipeline **reejecutable** que recorre los PDF de catálogos, extrae fichas y
**digitaliza las curvas de performance** de las bombas, y lo carga todo a una
base **MySQL** llamada `catalogos_pump`. Al agregar catálogos nuevos, se vuelve
a correr y solo procesa lo que cambió.

## Qué hace (los 7 puntos pedidos)

1. **Recorre todos los PDF** de `CATALOGS_DIR` (recursivo).
2. **Extrae tablas y datos** de cada PDF con `pdfplumber` → `output/tables/<pdf>/`.
3. **Digitaliza las curvas** de performance:
   - **Vectorial** (REDA): lee los trazos con color (`get_drawings`) y calibra
     los ejes con los números-texto (`get_text('words')`) → head y power a
     60 Hz, casi punto a punto, **sin OCR**. La **eficiencia se deriva** con la
     identidad hidráulica `eff = Q·H / (135773·HP)`.
   - **Raster** (Centrilift/Alkhorayef): guarda la imagen del gráfico marcada
     para revisión (alcance elegido: sin OCR).
4. **Crea la base MySQL** `catalogos_pump` con esquema normalizado (PK/FK/CHECK
   e índices).
5. **Guarda imágenes** (overlays de QA que muestran los puntos digitalizados
   sobre la curva original) y **logs** por corrida y por PDF (+ tabla
   `processing_log`).
6. **Reejecutable**: `manifest.json` guarda el SHA-256 de cada PDF; los que no
   cambiaron se saltan. Los upserts evitan duplicados.

## Requisitos

- **MySQL Server** corriendo (probado con 8.0). Credenciales en `.env`.
- Python 3.11 (venv incluido en `.venv/`). Dependencias en `requirements.txt`
  (PyMuPDF, pdfplumber, numpy, opencv, PyMySQL, pandas, python-dotenv).
- **No** requiere poppler ni Tesseract: todo es pure-Python.

## Puesta en marcha

```bash
# 1) (una sola vez) crear venv e instalar dependencias
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt

# 2) revisar .env  (MYSQL_ROOT_PASSWORD, CATALOGS_DIR, ...)

# 3) (una sola vez) crear base, usuario dedicado y esquema
.venv/Scripts/python db.py

# 4) correr el pipeline
.venv/Scripts/python pipeline.py            # incremental (salta PDF sin cambios)
.venv/Scripts/python pipeline.py --force    # reprocesa todo
.venv/Scripts/python pipeline.py --only reda # solo PDFs que matcheen "reda"
```

Para **agregar un catálogo nuevo**: copiar el PDF a `CATALOGS_DIR` y correr
`python pipeline.py`. Solo se procesa el nuevo (los demás se saltan por hash).

## Esquema MySQL (`catalogos_pump`)

| Tabla | Descripción |
|---|---|
| `manufacturers` | Fabricantes (PK `manufacturer_id`). |
| `data_sources` | Trazabilidad: qué PDF originó cada dato. |
| `pumps` | Ficha por bomba: serie, modelo, OD, min/bep/max flow, etapas, método de extracción, `review_flag`. |
| `pump_curves` | Puntos digitalizados de la curva (PK `pump_id,flow_bpd`): head, hp y efficiency por etapa. |
| `pump_housings` | Housings/etapas disponibles. |
| `processing_log` | Auditoría de cada corrida por PDF (estado, bombas, curvas, mensaje). |

`review_flag = 1` marca las fichas/curvas que el pipeline no pudo estructurar
con confianza y conviene revisar contra el overlay o la tabla cruda.

## Salidas (`output/`)

```
output/
├── logs/     run_<id>.log         (log completo por corrida)
├── tables/   <pdf>/pNNNN_tK.csv   (todas las tablas crudas + _index.json)
├── images/   <pdf>/<modelo>_pN.png(overlay QA: puntos sobre la curva original)
└── curves/   <pdf>/<modelo>.json  (puntos digitalizados + confianza)
```

## Verificar la carga

```bash
.venv/Scripts/python query.py         # conteos + muestra de bombas y curvas
```

## Resultado de la primera corrida (13 PDF)

| Métrica | Valor |
|---|---|
| Fabricantes | 5 (Reda, Centrilift, Alkhorayef, Borets, WoodGroup) |
| Bombas cargadas | 58 (56 sin flag de revisión) |
| Bombas con curva digitalizada | 56 (REDA) |
| Puntos de curva | 595 |
| Overlays QA + JSON de puntos | 77 + 56 |

REDA aportó las 56 bombas con curva mediante dos plantillas de gráfico:
- **panel único** (series AN/D, landscape): head + power + eficiencia, con caja de
  specs → serie, OD y rango operativo reales (ej. AN550: serie 338, OD 3.38",
  400–700 B/D, BEP 607, eff pico 0.58);
- **panel doble apilado** (series HN, multi-frecuencia): se elige la línea de
  60 Hz por su etiqueta.

Los catálogos con curvas **raster** (Centrilift perf sheets, Alkhorayef) cargan
la ficha por specs y dejan la imagen del gráfico + `review_flag=1`. Borets y
Wood Group quedan con sus tablas crudas volcadas (parser tabular pendiente).

## Notas de diseño

- **REDA** publica cada bomba en dos sistemas de unidades (B/D+ft y m³/d+m);
  el pipeline procesa solo la versión en **B/D + ft** para no duplicar y para
  que la identidad hidráulica de la eficiencia sea válida.
- Las bombas cuya curva es una **imagen raster** (no vectorial) quedan con la
  imagen guardada y `review_flag=1`: su digitalización fina requeriría OCR de
  los ejes (Tesseract), que se decidió no instalar.
- El esquema es compatible con el diseño de `../database_migration` (mismos
  nombres de columna en snake_case), por si más adelante se unifican.
- La **eficiencia se deriva** de head y power (`eff = Q·H/(135773·HP)`, SG=1);
  puede diferir ~5–10 puntos de la curva de eficiencia publicada. Es física y
  sirve para selección; para exactitud fina, validar contra el overlay.
- Los overlays de las páginas rotadas (AN/D) se guardan **de costado**: se
  renderizan en el mismo espacio en que se midieron para que los puntos alineen
  exactamente sobre las curvas.
