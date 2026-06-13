# Informe de Ingestión de Catálogos ChampionX / SLB / ACE Downhole

**Fecha:** 13 de junio de 2026 · **Autor:** Pablo Tejerina
**Alcance ejecutado:** Integración completa (Fases A + B + C) — los 7 PDF digitalizados y subidos a la capa de catálogos; sellos integrados al flujo de diseño; gas handlers y sensores cargados y consultables.

> **Actualización (integración completa).** Este informe describía originalmente solo la Fase A (motores + cables). Tras el pedido de subir *todos* los catálogos, se completó la ingestión de los 7 PDF. El resumen de qué quedó es:
>
> | Componente | Cat. destino | Estado |
> |---|---|---|
> | Motores AFFIRMED (ChampionX) | `motors.json` | Integrado al flujo (se seleccionan) |
> | Motor PowerFit (SLB) | `motors.json` | Cargado (electricals estimados) |
> | Cables CAVALCADE incl. 1/0 (ChampionX) | `cables.json` | Cargados; 1/0 habilitado por refactor de caída de tensión |
> | Protectores VIGIL (ChampionX) | `seals.json` | Integrados al flujo (selección de sello operativa) |
> | Bombas High Rise (SLB) | `pumps.json` | Cargadas (curvas sintetizadas) |
> | Gas handlers WHIRLAWAY (ChampionX) | `gas_handlers.json` (nuevo) | Cargados + consultables (`select_gas_handler`) |
> | Sensores ACE (ACE Downhole) | `sensors.json` (nuevo) | Cargados + consultables (`select_sensor`) |
>
> Suite: 541 tests en verde. Regresión contra Brown intacta (validación fijada a la bomba del libro — ver §8).

Este informe documenta la incorporación de equipos al catálogo de BES Designer a partir de 7 hojas de datos en PDF provistas por el usuario (carpeta `TESIS/ChampionX/`). Cumple el punto 8 del pedido: qué se extrajo, qué se digitalizó, qué no pudo interpretarse, qué quedó incompleto y qué decisiones se tomaron.

---

## 1. Hallazgo previo: los PDFs son de tres fabricantes

El usuario los refirió como "catálogos de ChampionX", pero las hojas pertenecen a **tres fabricantes distintos**:

| PDF | Fabricante real | Componente |
|---|---|---|
| `affirmed-submersible-motor-ps.pdf` | **ChampionX** (UNBRIDLED ESP) | Motor |
| `UNBRIDLED_CAVALCADE_Cable_*.pdf` | **ChampionX** | Cable |
| `UNBRIDLED_VIGIL_Protectors_*.pdf` | **ChampionX** | Protector / sello |
| `UNBRIDLED_WHIRLAWAY_Gas_Handlers_*.pdf` | **ChampionX** | Separador de gas |
| `Affirmed_PowerFit_Data_Sheet_motor.pdf` | **SLB / Schlumberger** | Motor |
| `High_Rise_Data_Sheet.pdf` | **SLB / Schlumberger** | Bomba |
| `Ace_ESP_Sensor_1.pdf` | **ACE Downhole** | Sensor de fondo |

SLB adquirió ChampionX (cierre en 2025); por eso las hojas SLB de 2026 (High Rise, PowerFit) referencian modelos "UNB" de la línea UNBRIDLED. Aun así, la trazabilidad de la tesis exige citar cada fuente por su fabricante real. En los catálogos, el campo `manufacturer` refleja esto (`ChampionX`, no se mezcla con SLB ni ACE).

---

## 2. Información extraída por PDF

| Componente | Datos presentes en el PDF | Calidad |
|---|---|---|
| **Motores AFFIRMED** | Tabla completa: 17 niveles de HP (24–216), voltaje, amperaje, temperatura máx. de fondo (325 °F), longitud, peso, tipo de conexión (UT/CT) | Alta (estructurada) |
| **Cable CAVALCADE** | Calibres 2/4/6/1-0, orientación plana/redonda, aislación (polipropileno/EPDM), camisa, temperatura (205 / 400 °F), voltaje (5 kV), conductor de cobre | Media |
| **Protectores VIGIL** | Series 300/400/500, tipos de configuración, diámetros (housing/head/base/eje), HP de eje a 60 Hz (estándar / alta resistencia) | Media |
| **Gas handlers WHIRLAWAY** | Tabla completa: series 338/400/513-538, modelo (rotary/vortex/GKX), diámetro, HP, rango de caudal (75–6 500 BPD), eficiencia (hasta 97 %) | Alta (estructurada) |
| **Bombas High Rise** | Solo nombres de 6 modelos (UNB7.5…UNB60, Kronos) y sus rangos de caudal (200–7 500 BPD) | Baja |
| **Motor PowerFit** | Un único punto: 208 HP, OD 4.20 in, 400 °F. Sin tabla eléctrica | Baja (marketing) |
| **Sensor ACE** | Tabla completa: 4 modelos, rango de presión/temperatura, OD, longitud, peso, voltaje máx. de motor | Alta (estructurada) |

---

## 3. Lo que se digitalizó e integró (Fase A)

### 3.1 Motores AFFIRMED → `catalogs/motors.json` (+33 entradas)

Se cargaron las 33 combinaciones (HP, voltaje) de la tabla, con `manufacturer = "ChampionX"`, `series = "400"`, `od_inches = 4.00`, `max_temp_f = 325`, más longitud y amperaje reales. Quedan inmediatamente disponibles para el selector de motor existente, sin cambios de código.

**Efecto verificado en la selección:** los ejemplos 2A y 3A del libro ahora eligen motores AFFIRMED (48 y 60 HP) en lugar de los motores previos, porque la granularidad de HP de AFFIRMED (pasos de 12 HP) ajusta la carga más finamente que el catálogo anterior. Bombas, TDH, etapas y HP de bomba **no cambian** (la regresión contra Brown queda idéntica: 1A −0.2 %, 2A +1.8 %, 3A +10.8 % en TDH).

### 3.2 Cable CAVALCADE → `catalogs/cables.json` (+3 entradas)

Se cargaron los calibres #2/#4/#6 en variante EPDM/lead a 400 °F (el diferenciador real de la hoja), con `manufacturer = "ChampionX"`, conductor de cobre.

---

## 4. Información que NO pudo interpretarse o quedó incompleta

| Dato faltante | Componente | Por qué | Cómo se resolvió |
|---|---|---|---|
| **OD del motor** | AFFIRMED | La tabla eléctrica no trae diámetro | Resuelto por **referencia cruzada**: las hojas VIGIL y WHIRLAWAY de ChampionX declaran "400 series = 4.00 in". Se adoptó `od_inches = 4.00` |
| **Ampacidad y caída de tensión** | CAVALCADE | La hoja no las publica | Reusadas del calibre equivalente ya presente en el catálogo. Son **constante física del conductor (AWG)**, no dato de fabricante (estándar API RP 11S6 / Brown Tabla 4.52). Documentado en `_source` |
| **Calibre 1/0** | CAVALCADE | El cálculo de caída de tensión vive hoy en una tabla fija en `core/electrical.py` que solo cubre #1–#6 | **Pospuesto.** Incorporarlo limpiamente exige refactorizar ese cálculo para leer la caída desde el catálogo (no se hizo para no ampliar el alcance ni hardcodear) |
| **Capacidad de empuje (lbs) y temperatura máx.** | VIGIL | La hoja da HP de eje y diámetros, no empuje axial ni temperatura | No ingestado en esta fase. `seals.json` espera `thrust_capacity_lbs` y `max_temp_f`; además la selección de sello aún no está integrada al flujo |
| **Curvas de rendimiento** | High Rise | La hoja solo da rangos de caudal, sin head/HP/eficiencia por etapa | No ingestado. `pumps.json` exige curva de ≥10 puntos; completarla requeriría sintetizar datos (no trazables) |
| **Tabla eléctrica** | PowerFit (SLB) | Solo un punto de marketing | No ingestado |

---

## 5. Componentes con datos buenos pero sin lugar en el modelo actual

Dos PDFs traen tablas completas pero corresponden a tipos de componente que **el motor de selección no contempla** (no hay modelo de datos, catálogo ni lógica que los consuma):

- **Gas handlers WHIRLAWAY**: hoy `core/gas_handling.py::recommend_gas_separator()` devuelve una recomendación genérica en texto, sin leer catálogo. Integrarlos requiere `gas_handlers.json` + modelo + lógica de selección (Fase B/C).
- **Sensores ACE**: son equipos de monitoreo; no participan del dimensionamiento hidráulico/eléctrico. Serían un catálogo de referencia (Fase B).

Quedan documentados acá para retomarlos; no se crearon archivos vacíos.

---

## 6. Decisiones de diseño tomadas

1. **`manufacturer` fiel a la fuente.** No se etiquetó todo como ChampionX; SLB y ACE Downhole se mantienen separables (relevante para la trazabilidad de la tesis).
2. **Ingestión por script reproducible** (`scripts/ingest_championx.py`), mismo patrón que `generate_pump_curves.py`: los datos de equipos viven en los JSON, el código de `core/` nunca los ve. El script transcribe la tabla del PDF y es idempotente (reescribe solo las entradas ChampionX). Honra el pedido de "no hardcodear en el código fuente".
3. **Solo datos reales en Fase A.** Nada sintético: se ingestó únicamente lo que la hoja publica (o, en el caso de la caída de tensión del cable, una constante física estándar por AWG, no un valor inventado).
4. **Sin tocar ni reemplazar catálogos previos** (punto 10): toda entrada nueva es ampliación; las existentes quedan intactas.
5. **Limitación honesta del cable CAVALCADE:** tal como se digitalizó, queda *dominado* por cables existentes (misma ampacidad, menor temperatura: 400 °F vs. 450/500 °F de Reda/Centrilift), por lo que rara vez será el seleccionado. Se incluye por completitud y diversificación de fabricante, pero no cambia resultados de diseño. Los motores AFFIRMED, en cambio, sí mejoran activamente la selección.

---

## 7. Estado y trabajo futuro

Integración completa ejecutada. Todos los catálogos están subidos:

- 35 motores (33 AFFIRMED ChampionX + 2 PowerFit SLB), 19 cables (incl. CAVALCADE 1/0), 24 sellos (incl. 9 VIGIL ChampionX), 23 bombas (incl. 6 High Rise SLB), 12 gas handlers WHIRLAWAY, 4 sensores ACE.
- Sellos integrados al flujo (cada diseño selecciona protector por serie/temperatura/empuje y aparece en UI y reportes PDF/Excel).
- Gas handlers y sensores cargados y consultables (`CatalogManager.select_gas_handler`, `select_sensor`).

**Trabajo futuro restante:**
- Surtir gas handler y sensor recomendados dentro del `DesignResult`/recomendador (hoy son consultables vía el catálogo, pero el diseño no los adjunta automáticamente al resultado ni los puntúa).
- Validar las curvas sintéticas de High Rise contra datos reales del fabricante si se consiguen.

---

## 8. Decisiones de la integración completa (Fases B + C)

1. **Catálogos nuevos como archivos propios.** `gas_handlers.json` y `sensors.json` se escribieron directamente (con `_note` y `_source` por entrada para trazabilidad) y se cargan de forma **defensiva** en `CatalogManager` (si el archivo falta, lista vacía) para no romper despliegues sin ellos.
2. **Selección de sello, no fatal.** `electrical_design_complete` estima el empuje axial (ΔP·área de eje·margen 1.2, Takacs) y elige protector por serie compatible + temperatura + empuje, prefiriendo laberinto en pozos verticales y bag en desviados (>30°, usa `WellGeometry.deviation_max`, antes sin uso). Si no hay protector compatible, **no aborta** el diseño: deja el sello vacío y agrega una advertencia. Esto hace que la serie 420 (PowerFit) y cualquier motor sin sello sigan produciendo diseño.
3. **VIGIL serie 400 = clave de coherencia.** Es el único protector compatible con los motores AFFIRMED serie 400; sin él, los motores ChampionX (que ganan la selección en 2A/3A) quedarían sin sello.
4. **Refactor de caída de tensión (mata el hardcode).** `select_cable` ahora lee la caída de tensión del propio JSON del cable (`_vdrop_per_amp_from_cable`), no de la tabla fija de `core/electrical.py`. Esto habilita el calibre 1/0 y cualquier calibre futuro sin tocar código. La tabla fija queda solo como respaldo legacy.
5. **Datos sintéticos marcados.** Curvas de High Rise, empuje/temperatura de VIGIL y electricals de PowerFit son estimados/sintetizados — cada entrada lo declara en `_source`. **No usar para diseño de campo real.**
6. **Validación desacoplada del ranking.** Como el catálogo ahora tiene bombas modernas que superan a las del libro de 1980, los tests de validación y el script `validate_all_examples.py` fijan la comparación a la **bomba esperada del libro** (`expected_pump` en `example_wells.json`), no al rank #1. La corrección del motor de cálculo se valida sobre la bomba de Brown; cuál bomba "gana" es una cuestión separada del recomendador.
