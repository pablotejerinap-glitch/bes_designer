# Documentación — BES Designer

Índice de `docs/`. El punto de entrada del proyecto es el
[README raíz](../README.md).

## Metodología y cálculo

| Documento | Contenido |
|---|---|
| [METHODOLOGY.md](METHODOLOGY.md) | Metodología de cálculo completa, paso a paso, con la referencia a Brown de cada etapa. Incluye §7, el método métrico de cátedra "ESP 01". |
| [FORMULAS.md](FORMULAS.md) | Compendio de todas las fórmulas implementadas, con archivo, línea y fuente bibliográfica. |
| [VALIDATION.md](VALIDATION.md) | Tabla comparativa app vs. libro (TDH, etapas, HP) para los ejemplos de Brown. Se regenera con `backend/scripts/validate_all_examples.py`. |
| [EJEMPLO_ESP01.md](EJEMPLO_ESP01.md) | Desarrollo del ejercicio de cátedra "ESP 01" en unidades métricas, los 17 pasos. |

## Fuentes resumidas

| Documento | Contenido |
|---|---|
| [BROWN_CHAPTER_SUMMARY.md](BROWN_CHAPTER_SUMMARY.md) | Resumen de Brown Vol. 2b, Cap. 4.5 (diseño de sistemas BES). |
| [BROWN_VOL4_NODAL_ANALYSIS.md](BROWN_VOL4_NODAL_ANALYSIS.md) | Resumen de Brown Vol. 4 (análisis nodal). |

## Uso y catálogos

| Documento | Contenido |
|---|---|
| [USER_GUIDE.md](USER_GUIDE.md) | Guía de usuario de la aplicación. |
| [CHAMPIONX_INGESTION_REPORT.md](CHAMPIONX_INGESTION_REPORT.md) | Informe de digitalización e ingestión de los catálogos ChampionX / SLB / ACE Downhole. |

## Documentos de la tesis

- `Tesis_BES_Pablo_Tejerina_AMPLIADA_v2.docx` — redacción de la tesis.
- `GUIA_ESTUDIO_BES.docx` — guía de estudio para la defensa.

## Otros

- [`_trabajo/`](_trabajo/) — notas de trabajo del desarrollo, no entregables.
- El diseño de la base de datos vive con su código, en
  [`tools/database_migration/`](../tools/database_migration/README.md).
