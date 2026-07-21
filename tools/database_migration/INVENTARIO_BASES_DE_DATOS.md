# Las bases de datos de BES Designer — explicación para la defensa

Este documento responde una pregunta simple: **¿cuáles son las bases de
datos de la aplicación y qué contiene cada una?** Está pensado para
explicárselo al jurado sin tecnicismos.

## La regla que ordena todo

> **Dato de ingeniería → vive en la base de datos (Excel).
> Conocimiento de ingeniería (fórmulas, métodos) → vive en el código,
> con su referencia bibliográfica.**

Una bomba con su curva es un DATO (cambia con cada fabricante y catálogo).
La correlación de Standing o la fórmula de TDH es CONOCIMIENTO (no cambia
por fabricante; viene de la literatura). Por eso los catálogos están en
Excel y las fórmulas en Python — y ninguna fórmula tiene números mágicos:
cada constante cita su fuente (Brown Vol. 2B, API RP 11S, etc.).

## Base de datos 1 — CATÁLOGOS DE EQUIPOS (el corazón)

Ubicación: `database_migration/data_excel/` (un archivo = un dominio;
una hoja = una tabla). Es lo que el jurado entendería como "el catálogo
del fabricante convertido en tablas".

| Archivo | Qué contiene | Estado |
|---|---|---|
| `manufacturers.xlsx` | Los 8 fabricantes (Reda, Centrilift, SLB, Weatherford, ChampionX, Alkhorayef...) | Completo |
| `equipment_series.xlsx` | Las series = clases de diámetro (338 ≈ 3.38", 400 ≈ 4.00"...) | Completo |
| `pumps.xlsx` | **60 bombas** con: ficha técnica (3 tablas: pumps, pump_curves con **621 puntos de curva**, pump_housings con longitudes y pesos reales) | 23 de Brown + 37 Alkhorayef |
| `motors.xlsx` | 50 motores (HP, voltaje, amperaje, temperatura) | Completo |
| `cables.xlsx` | 19 cables + caída de tensión física por conductor/calibre/temperatura | Completo |
| `seals.xlsx` | 24 sellos/protectores + tabla de compatibilidad con series de motor | Completo |
| `gas_handlers.xlsx` | 12 separadores de gas | Completo |
| `sensors.xlsx` | 4 sensores de fondo | Completo |
| `transformers.xlsx` | 8 tamaños estándar (antes estaban ocultos dentro del código) | Genéricos; catálogo Wood Group pendiente |
| `vsds.xlsx` | Variadores de frecuencia | Plantilla (sin datos aún) |
| `switchboards.xlsx` | Tableros de control | Plantilla (catálogo Wood Group disponible) |

**Las curvas de los gráficos también son base de datos:** las curvas
Head/Power/Efficiency que el fabricante publica como GRÁFICO se
digitalizaron a puntos numéricos (tabla `pump_curves`) y la aplicación
interpola entre ellos. Un gráfico no se puede consultar; una tabla sí.

## Base de datos 2 — POZOS Y CASOS

| Archivo | Qué contiene |
|---|---|
| `well_examples.xlsx` | Los 6 casos de validación del libro de Brown (datos del pozo + resultados esperados). Son la "regresión": la app debe reproducirlos siempre. |
| `real_wells.xlsx` | Plantilla para pozos reales de campo: el pozo, la instalación (`field_cases` + `installation_components`: qué equipo se bajó, en qué orden, tándems incluidos) y muestras PVT de laboratorio. Se cargará con los datos de TESIS/Casos reales. |

## Base de datos 3 — BIBLIOGRAFÍA (trazabilidad)

| Archivo | Qué contiene |
|---|---|
| `data_sources.xlsx` | Las 49 fuentes de TODOS los datos, con ID corto (BROWN-01, ALKH-01, CHX-02...). Cada fila de cada tabla referencia su fuente: **ningún número de la base queda sin cita.** Las marcadas "estimado/por confirmar" señalan qué validar con catálogos reales. |

## Qué NO es base de datos (para no confundir al jurado)

* **Las fórmulas y correlaciones** (Vogel, Standing, Beggs-Robinson,
  Hazen-Williams, kVA=V·I·√3/1000, leyes de afinidad): son el MÉTODO,
  implementado en `core/` con referencia a Brown y las normas.
* **La interfaz** (Streamlit) y **los reportes** (Excel de salida): son
  presentación, no almacenamiento.
* **Los PDF de TESIS/CATALOGOS**: son las FUENTES en bruto; la base de
  datos es su versión estructurada y consultable.

## Cómo se conecta con la aplicación (una frase)

> La aplicación lee toda su información de ingeniería desde la base de
> datos a través de UNA clase (`ExcelCatalogManager`), que tiene la misma
> interfaz que el lector anterior de JSON. Cambiar el almacenamiento
> (JSON → Excel → SQLite) nunca toca la lógica de ingeniería —
> verificado con los 663 tests automáticos.

## Respuestas de una línea para la defensa

* *"¿Cuántas bases de datos tiene?"* — Tres dominios: catálogos de
  equipos (11 archivos, 20 tablas), pozos y casos (2 archivos), y
  bibliografía (1 archivo). Documentadas en el ERD con sus relaciones.
* *"¿Por qué Excel?"* — Editable y auditable por un ingeniero sin
  programar; misma estructura lógica que tendrá SQLite.
* *"¿Cómo agrego un fabricante?"* — Filas nuevas en los Excel. Cero
  código. Demostrado: Alkhorayef entró con 37 bombas y sus curvas
  digitalizadas sin modificar una línea de la lógica.
* *"¿Cómo sé que los datos son correctos?"* — Tres capas: `check_integrity`
  (claves y rangos), `verify_database` (las 23 bombas históricas idénticas
  al origen), y QA físico de curvas (identidad hidráulica ±estándar API).
