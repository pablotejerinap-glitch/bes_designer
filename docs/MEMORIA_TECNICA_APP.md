# BES Designer — Memoria Técnica de la Aplicación

**Proyecto Integrador Profesional — Ingeniería de Petróleo, Universidad Nacional del Comahue**
**Autor:** Pablo Tejerina · **Versión del documento:** 11 de junio de 2026

Este documento describe, en lenguaje simple, qué hace la aplicación BES Designer, cómo lo hace, qué catálogos de equipos utiliza y de dónde provienen sus datos, cómo se validó y cuáles son sus supuestos y limitaciones. Está pensado como base para el informe final de tesis y como material de consulta para el tribunal.

---

## 1. ¿Qué es BES Designer y qué problema resuelve?

El diseño de un sistema de Bombeo Electrosumergible (BES, o ESP por sus siglas en inglés) consiste en seleccionar y dimensionar una cadena completa de equipos de fondo y superficie —bomba centrífuga multietapa, motor eléctrico, cable de potencia, transformador— para llevar un pozo de petróleo a un caudal de producción objetivo.

Hecho a mano, este diseño exige: calcular el comportamiento de afluencia del pozo (IPR), estimar las propiedades de los fluidos a distintas presiones y temperaturas (PVT), integrar gradientes de presión multifásicos a lo largo del pozo, calcular la altura dinámica total que debe vencer la bomba (TDH), recorrer catálogos de fabricantes leyendo curvas de rendimiento, y verificar restricciones geométricas, térmicas y eléctricas. Es un proceso iterativo, propenso a errores y que en la práctica se repite para varias bombas candidatas antes de elegir una.

**BES Designer automatiza ese proceso completo.** A partir de los datos del pozo, evalúa todas las bombas del catálogo que son físicamente compatibles, completa para cada una el diseño hidráulico y eléctrico, las califica con un puntaje multicriterio y devuelve las tres mejores opciones con su justificación, advertencias de diseño y reportes descargables.

La metodología implementada es la de Kermit Brown, *The Technology of Artificial Lift Methods*, Vol. 2b, Cap. 4.5 (PennWell, 1980), complementada con el Vol. 4 (análisis nodal). Cada módulo de cálculo se valida contra los ejemplos numerados del libro.

**Usuario final previsto:** ingenieros de producción que necesitan un prediseño BES rápido y trazable, y en el contexto académico, el desarrollo y defensa de este PIP.

---

## 2. Flujo de trabajo en la aplicación

La interfaz (web, desarrollada con Streamlit) se organiza en seis secciones que siguen el orden natural de un diseño:

| # | Sección | Qué hace el usuario / qué muestra |
|---|---------|-----------------------------------|
| 1 | **Datos del Pozo** | Carga los datos en cinco pestañas: reservorio, fluido, geometría del pozo, condiciones de superficie y objetivos de diseño. Puede cargar un ejemplo del libro con un clic. Todos los datos se validan al guardar (rangos físicos, consistencia geométrica). |
| 2 | **Diseño BES** | Con un botón se ejecuta el diseño completo. Muestra las 3 mejores opciones en pestañas: equipo seleccionado, etapas, TDH, diseño eléctrico, fracción de gas en la admisión, advertencias y justificación en texto. Desde aquí se descargan los reportes PDF, Excel y el caso en JSON. |
| 3 | **Comparación de Opciones** | Gráfico radar y tabla comparativa de las opciones (eficiencia, flexibilidad, costo, puntaje global). |
| 4 | **Análisis de Sensibilidad** | Evalúa cómo cambia el diseño ante variaciones de presión de reservorio, corte de agua y GOR. |
| 5 | **Análisis Nodal** | Construye las curvas de oferta (IPR) y demanda (outflow) del sistema, encuentra el punto de operación natural y con BES, y permite comparar las cuatro correlaciones multifásicas disponibles y simular la declinación de presión del reservorio. |
| 6 | **Acerca de** | Metodología, referencias bibliográficas y créditos. |

---

## 3. El motor de cálculo, paso a paso

Cuando el usuario presiona "Calcular Diseño BES", el sistema ejecuta esta cadena para **cada bomba candidata** del catálogo:

### Paso 1 — Afluencia (IPR): ¿qué presión de fondo exige el caudal objetivo?

Según el método elegido se calcula la presión de fondo fluyente (Pwf) necesaria para producir el caudal objetivo:

- **Lineal** (índice de productividad constante): pozos sobre el punto de burbuja.
- **Vogel (1968)**: pozos con empuje por gas en solución, por debajo del punto de burbuja.
- **Combinada**: lineal por encima de Pb, Vogel por debajo (transición continua).
- **Fetkovich (1973)**: IPR empírica de ensayos isócronos.

### Paso 2 — Propiedades de los fluidos (PVT)

A cada presión y temperatura del recorrido se estiman: gas en solución y factor volumétrico del petróleo (Standing, 1947), factor de compresibilidad del gas (Dranchuk y Abou-Kassem, 1975), viscosidad del petróleo (Beggs y Robinson, 1975) y factor volumétrico del agua.

### Paso 3 — Presión de admisión de la bomba (PIP)

Se integra el gradiente de presión multifásico desde las perforaciones hasta la profundidad de instalación de la bomba. Correlaciones disponibles: **Hagedorn-Brown** (por defecto), **Beggs-Brill**, **Duns & Ros** y **Poettmann & Carpenter**.

La profundidad de instalación se fija físicamente:

```
profundidad de bomba = tope de perforaciones − margen de seguridad del usuario
```

### Paso 4 — Altura dinámica total (TDH)

Es la altura que la bomba debe desarrollar (Brown §4.5324):

```
TDH = Elevación vertical + Fricción en tubing + Presión de boca expresada en altura

Elevación vertical = prof. de bomba − (PIP × 2.31 / SG del líquido)
Fricción           = Hazen-Williams: 0.2083 · (100/C)^1.852 · q^1.852 / d^4.8655 · L/100
Altura por presión de boca = Pwh × 2.31 / SG
```

### Paso 5 — Selección hidráulica de la bomba

Para cada bomba del catálogo que (a) cabe en el casing y (b) cubre el caudal objetivo en su rango recomendado:

```
etapas = TDH / (altura por etapa a ese caudal)        [redondeado al housing disponible]
HP de bomba = etapas × hp por etapa × SG del fluido   [las curvas están medidas con agua]
```

Si el fluido es viscoso se aplican los factores de corrección del estándar Hydraulic Institute (caudal, altura y eficiencia se degradan respecto de la curva de agua).

### Paso 6 — Diseño eléctrico

- **Motor**: el de menor potencia nominal que cubra el HP de bomba con 10 % de margen, que quepa en el casing **dejando espacio anular para que pase al menos el cable plano más delgado del catálogo**, y con voltaje cercano al objetivo según la potencia.
- **Cable**: ampacidad con margen del 25 % (práctica NEC/API RP 11S6), temperatura nominal 25 °F por encima de la de fondo, verificación geométrica en el espacio anular, y entre los aptos, el de menor caída de tensión. Longitud = profundidad de bomba + 100 ft.
- **Voltaje de superficie** = voltaje del motor + caída en el cable. **Transformador**: el tamaño estándar inmediato superior al kVA demandado (25 a 300 kVA).

### Paso 7 — Gas libre en la admisión (GIP)

Con el PVT a la presión de admisión se calcula la fracción volumétrica de gas libre que entra a la bomba. Según su magnitud se emiten advertencias y la recomendación de separador de fondo (riesgo de bloqueo por gas, Brown §4.53103). Para pozos con mucho gas existe además el **método de incrementos de presión de 200 psi** del libro: divide el recorrido de presión de la bomba en tramos, calcula el caudal in situ de cada tramo (el gas se comprime y se redisuelve al subir la presión) y selecciona la bomba y el número de etapas tramo por tramo, pudiendo combinar dos modelos de bomba (diseño "tapered", como en el Ejemplo 3B del libro).

### Paso 8 — Puntaje y ranking

Cada diseño completo recibe tres puntajes de 0 a 10, combinados con pesos fijos:

| Criterio | Peso | Qué mide |
|----------|------|----------|
| Eficiencia | 40 % | Eficiencia hidráulica de la bomba en el punto de operación |
| Flexibilidad | 30 % | Cercanía del punto de operación al punto de mejor eficiencia (BEP): operar cerca del BEP maximiza la vida útil |
| Costo | 30 % | Aproximación por potencia total y número de etapas |

El sistema devuelve las 3 mejores opciones, garantizando cuando es posible al menos una por fabricante (diversificación), cada una con una justificación generada en texto.

---

## 4. Catálogos de equipos

Los equipos disponibles están digitalizados en cuatro archivos JSON dentro de `catalogs/`, cargados al inicio por un módulo gestor (`CatalogManager`) que ofrece las consultas que usa el motor de diseño.

### 4.1 Origen y trazabilidad de los datos — importante

Los datos de catálogo provienen de **dos clases de fuente**, identificadas explícitamente en los archivos:

1. **Digitalizados del libro de Brown (Vol. 2b, Cap. 4.5)**: las bombas que aparecen en los ejemplos numerados del libro, y los datos de cables de la Tabla 4.52. Son los datos contra los que se valida el sistema.
2. **Representativos**: equipos agregados para ampliar la cobertura de caudal y la diversidad de fabricantes. Sus curvas se **sintetizan** con el script `scripts/generate_pump_curves.py` usando la forma característica estándar de una bomba centrífuga:
   - altura por etapa: cuadrática decreciente con el caudal;
   - eficiencia: parábola con máximo en el BEP;
   - potencia por etapa: **derivada** de la potencia hidráulica (`HP = q·H·SG / 135 770 / η`), de modo que altura, potencia y eficiencia sean termodinámicamente consistentes en todos los puntos.

   Cada bomba generada lleva un campo `_source` que la identifica, y el archivo lleva una nota global. **Las designaciones de modelo siguen el estilo de cada línea comercial pero no son números de parte reales, y los datos representativos no deben usarse para diseño de campo.**

### 4.2 Catálogo de bombas (`pumps.json`) — 17 modelos

| Fabricante | Modelo | Serie | OD (in) | Rango (bpd) | BEP (bpd) | Origen |
|------------|--------|-------|---------|-------------|-----------|--------|
| Reda | D-20 | 400 | 4.00 | 350 – 800 | 600 | Libro (Ej. #3B) + curva sintetizada |
| Centrilift | M-34 | 400 | 4.00 | 600 – 1 100 | 850 | Libro |
| Reda | D-40 | 400 | 4.00 | 1 000 – 1 600 | 1 300 | Libro (Ej. #2A) |
| Weatherford | WE-1350 | 400 | 4.00 | 1 050 – 1 750 | 1 350 | Representativa |
| Centrilift | I-42B | 513 | 5.13 | 1 200 – 2 200 | 1 700 | Libro (Ej. #2B) |
| Centrilift | N-80 | 513 | 5.13 | 1 590 – 3 520 | 2 500 | Libro |
| Reda | D-55 | 400 | 4.00 | 1 700 – 2 600 | 2 100 | Libro (Ej. #3B) |
| Centrilift | Y-62B | 513 | 5.13 | 1 700 – 2 200 | 1 900 | Libro (Ej. #4) |
| Centrilift | Z-69 | 513 | 5.13 | 1 700 – 2 600 | 2 100 | Libro |
| Weatherford | WE-2400 | 513 | 5.13 | 1 800 – 3 100 | 2 400 | Representativa |
| Reda | G-52E | 540 | 5.40 | 2 000 – 3 200 | 2 600 | Libro |
| Reda | D-82 | 400 | 4.00 | 2 500 – 3 500 | 3 000 | Libro |
| Reda | GN-4000 | 540 | 5.40 | 3 000 – 5 200 | 4 000 | Representativa |
| Weatherford | WE-5000 | 538 | 5.38 | 3 800 – 6 400 | 5 000 | Representativa |
| Reda | GN-5600 | 540 | 5.40 | 4 200 – 7 200 | 5 600 | Representativa |
| Centrilift | GC-6100 | 513 | 5.13 | 4 600 – 7 900 | 6 100 | Representativa |
| Centrilift | I-300 | 738 | 7.38 | 8 000 – 11 500 | 10 000 | Libro (Ej. #1A) |

Cobertura continua de caudal: **350 a 7 900 bpd**, más el tramo de alto caudal 8 000 – 11 500 bpd. Tres fabricantes representados.

Cada bomba almacena: fabricante, serie (diámetro), modelo, OD, rango recomendado de caudal, BEP, número máximo de etapas, opciones de housing (cuerpos comerciales con cantidades fijas de etapas) y su **curva de rendimiento** de 10–11 puntos (caudal, altura/etapa, HP/etapa, eficiencia). El sistema lee la curva por **interpolación lineal** entre puntos.

### 4.3 Catálogo de motores (`motors.json`) — 48 modelos

Motores Reda (series 375, 456 y 540 — el número indica el diámetro en centésimas de pulgada), Centrilift (series 544 y 562) y **ChampionX AFFIRMED** (serie 400, OD 4.00 in), de **24 a 600 HP** y voltajes nominales de 415 a 4 185 V. Cada entrada almacena potencia, voltaje, corriente, diámetro, largo y temperatura máxima admisible.

| Fabricante | Serie | Potencias (HP) |
|------------|-------|----------------|
| Reda | 375 | 25 · 40 · 60 |
| Reda | 456 | 60 · 80 · 100 · 130 |
| Reda | 540 | 150 · 200 · 250 |
| Centrilift | 544 | 175 · 230 |
| Centrilift | 562 | 350 · 450 · 600 |
| ChampionX (AFFIRMED) | 400 | 24 · 36 · 48 · 60 · 72 · 84 · 96 · 108 · 120 · 132 · 144 · 156 · 168 · 180 · 192 · 204 · 216 (33 variantes HP/voltaje) |

Los motores AFFIRMED (digitalizados de la hoja de datos de ChampionX / UNBRIDLED ESP) aportan una granularidad de HP mucho más fina (pasos de 12 HP), lo que permite ajustar la carga del motor más ajustadamente al requerimiento de la bomba. Ver [CHAMPIONX_INGESTION_REPORT.md](CHAMPIONX_INGESTION_REPORT.md).

### 4.4 Catálogo de cables (`cables.json`) — 18 modelos

Cables de potencia trifásicos Reda (Redalene, Redared), Centrilift (EPDM, polietileno) y **ChampionX CAVALCADE** (EPDM/lead), conductor de cobre, calibres **#1, #2, #4 y #6 AWG**, temperaturas nominales de 300 a 500 °F. Para cada cable se tabula la **caída de tensión por amperio por cada 1 000 ft** a cuatro temperaturas (100/150/180/200 °F), valores tomados de la Tabla 4.52 de Brown y de API RP 11S6; el sistema interpola a la temperatura de fondo del pozo. Los cables CAVALCADE (400 °F) se incluyen por diversificación de fabricante; quedan dominados por los cables existentes de mayor temperatura, por lo que rara vez resultan seleccionados.

### 4.5 Catálogo de sellos/protectores (`seals.json`) — 24 modelos

Sellos Reda (series 375/456/540), Centrilift (series 544/562) y **ChampionX VIGIL** (series 300/400/500), en las tres configuraciones típicas (laberinto, bolsa y combinada), con su capacidad de carga axial (de 5 000 a 30 000 lbs) y temperatura máxima. **La selección automática del sello está integrada al flujo de diseño:** para cada diseño se estima el empuje axial (ΔP de bomba × área del eje × margen, según Takacs) y se elige el protector de la serie del motor que soporta esa carga y la temperatura de fondo, prefiriendo laberinto en pozos verticales y bolsa en desviados (>30°). El sello aparece en la interfaz y en los reportes PDF/Excel. Los protectores VIGIL serie 400 son los compatibles con los motores AFFIRMED serie 400.

### 4.6 Catálogo de gas handlers (`gas_handlers.json`) — 12 modelos

Separadores y acondicionadores de gas **ChampionX WHIRLAWAY** (digitalizados de la hoja de datos): separadores rotativos y de vórtice (eficiencia hasta 97 %) y dispositivos GKX para >40 % de gas libre, en series 338/400/513-538, con su rango de caudal (75–6 500 bpd), HP, diámetro y eficiencia. Se consultan con `CatalogManager.select_gas_handler(caudal, casing_id)`.

### 4.7 Catálogo de sensores (`sensors.json`) — 4 modelos

Sensores de fondo **ACE Downhole** (Standard, Mid Range, Xtreme Temperature, Xtreme Temperature Dual) con sus rangos de presión de admisión (5 000–8 000 psi), temperatura (257–350 °F), monitoreo de vibración y voltaje máximo de motor. Son equipos de monitoreo (no intervienen en el dimensionamiento), pero el catálogo permite recomendar el sensor cuyo rango cubre las condiciones del pozo (`select_sensor`).

### 4.8 Cómo consulta el sistema los catálogos

| Consulta | Uso en el diseño |
|----------|------------------|
| Bombas cuyo OD cabe en el diámetro interno del casing | Filtro geométrico inicial |
| Bombas cuyo rango recomendado contiene el caudal objetivo | Filtro hidráulico inicial |
| Interpolación de la curva al caudal de operación | Altura/etapa, HP/etapa y eficiencia usados en los Pasos 5–8 |
| Motor de menor HP que cubre la demanda, que cabe con cable en el anular | Paso 6 |
| Protector de la serie del motor que soporta empuje y temperatura | Paso 6 |
| Cable apto por ampacidad, temperatura y geometría, de menor caída (caída leída del propio catálogo) | Paso 6 |
| Transformador estándar inmediato superior al kVA requerido | Paso 6 |
| Gas handler / sensor cuyo rango cubre las condiciones del pozo | Consultable (no adjuntado aún al resultado) |

---

## 5. Validación

### 5.1 Contra los ejemplos del libro

El criterio rector del proyecto es que **cada resultado sea trazable a Brown**. El script `scripts/validate_all_examples.py` corre los ejemplos de punta a punta y genera `docs/VALIDATION.md`. Resultado vigente:

| Ejemplo | Caso | TDH app vs ref | Etapas app vs ref | HP app vs ref | Bomba |
|---------|------|----------------|--------------------|---------------|-------|
| 1A | Pozo de agua, 10 000 STB/d, casing 8⅝" | 1 721 / 1 724 ft (−0.2 %) | 29 / 29 (0 %) | 216.9 / 217 (0 %) | I-300 |
| 2A | Petróleo sin gas libre, 1 000 STB/d, casing 5½" | 4 249 / 4 174 ft (+1.8 %) | 172 / 156 (+10.3 %) | 36.7 / 44 (−16.5 %) | M-34 |
| 3A | Petróleo con gas libre (GIP alto), 700 STB/d | 6 713 / 6 060 ft (+10.8 %) | 228 / 206 (+10.7 %) | 49.5 / 45 (+9.9 %) | M-34 |

Las diferencias provienen principalmente de que la app integra el gradiente multifásico con Hagedorn-Brown mientras las referencias usan columna hidrostática simple, y del redondeo de etapas a los housings comerciales del catálogo. Como el catálogo incorpora bombas modernas (post-1980) que pueden superar en el ranking a las del libro, la validación se fija explícitamente a la **bomba esperada de Brown** (campo `expected_pump`): se verifica que el motor de cálculo reproduce los números del libro para la bomba del libro, independientemente de cuál bomba encabece la recomendación con el catálogo ampliado.

Además, los cálculos unitarios (fricción de Hazen-Williams, etapas del Ejemplo 2A con la D-40 a la profundidad exacta del libro, Ejemplo 2B con la I-42B, etc.) se validan en tests dedicados con los valores puntuales del libro.

### 5.2 Suite de tests automatizados

El proyecto tiene **522 tests** (pytest), todos en verde, organizados por módulo: modelos y validación de datos, IPR, PVT, flujo multifásico, TDH, diseño de bomba, diseño eléctrico, manejo de gas, catálogos, recomendador, análisis nodal y tests de integración de punta a punta con los tres ejemplos del libro. Los tests de integración verifican tanto los valores numéricos (con tolerancias) como invariantes estructurales (todo diseño debe tener motor, cable y transformador; los puntajes deben estar en 0–10; la bomba debe caber en el casing; etc.).

---

## 6. Arquitectura y tecnologías

```
Entradas del usuario (validadas)
        │
core/   │  ipr.py → pvt.py → multiphase.py → tdh.py → pump_design.py
        │  → electrical.py → gas_handling.py → nodal_analysis.py
        ▼
recommender/  pump_selector.py → scoring.py → recommendation_engine.py
        ▼
ui/ (Streamlit + Plotly)        reports/ (PDF ReportLab · Excel openpyxl · JSON)
```

- **Lenguaje:** Python 3.14. **Dependencias** (versiones fijadas en `requirements.txt`): numpy, scipy, pandas, plotly, streamlit, reportlab, openpyxl, pytest.
- **Separación estricta de capas:** la interfaz no calcula nada; llama a una única función pública (`generate_recommendations`) y muestra el resultado. Esto permite usar el motor de cálculo también desde scripts o notebooks, sin interfaz.
- **Modelos de datos validados:** todas las entradas son `dataclasses` con validación física al construirse (presiones positivas, water cut en [0,1], diámetros consistentes, etc.), de modo que los errores de carga se detectan antes de calcular.
- **Unidades** (consistentes en todo el sistema): psia/psi, °F, STB/d, ft, pulgadas, HP, V/A.
- **Ejecución:** `python -m streamlit run app.py` · **Tests:** `pytest` · **Validación:** `python scripts/validate_all_examples.py`.

---

## 7. Supuestos y limitaciones

Para una lectura honesta de los resultados, el sistema asume y se limita a lo siguiente:

1. **Curvas de catálogo a 60 Hz y con agua.** La corrección por viscosidad (Hydraulic Institute) está implementada; las leyes de afinidad para operación a otra frecuencia (VSD) no están integradas al flujo automático.
2. **Datos representativos.** Las bombas marcadas como representativas (§4.1) sirven para demostrar la metodología y ampliar la cobertura; no reemplazan datos certificados del fabricante.
3. **Profundidad de instalación** fijada en el tope de perforaciones menos el margen de seguridad. No se modela la instalación bajo perforaciones con shroud.
4. **Eficiencia del sistema** aproximada como eficiencia de bomba × 0.92 (proxy de eficiencia de motor); no usa la eficiencia real del motor seleccionado.
5. **Transformadores** acotados a tamaños estándar de hasta 300 kVA; diseños de alta potencia pueden quedar fuera de ese tope.
6. **Empuje axial estimado.** La selección de protector usa un empuje axial *estimado* (ΔP de bomba × área del eje × margen 1.2, con diámetros de eje típicos por serie), no el empuje real catalogado por modelo. Para los protectores VIGIL, la capacidad de empuje y la temperatura son valores estimados (la hoja de datos solo publica HP de eje y diámetros).
7. **Gas handler y sensor consultables pero no adjuntados.** Sus catálogos están cargados y hay lógica de selección (`select_gas_handler`, `select_sensor`), pero el diseño no los incorpora todavía al `DesignResult` ni al puntaje.
8. **Campos cargados pero aún sin efecto en el cálculo:** H₂S, CO₂ y producción de arena (selección de metalurgia), límite de GIP del usuario y uso de VSD. La desviación máxima del pozo sí se usa ahora para elegir el tipo de protector (laberinto vs. bolsa).
9. **Validez de las correlaciones:** las correlaciones PVT y multifásicas tienen los rangos de validez de sus publicaciones originales; fuera de ellos (crudos extrapesados, pozos muy desviados, alta presencia de H₂S/CO₂) los resultados deben tomarse con cautela.
10. **Datos sintéticos/estimados marcados.** Las curvas de las bombas no provenientes del libro (representativas y High Rise), la capacidad/temperatura de los protectores VIGIL y los valores eléctricos del motor PowerFit son estimados; cada entrada lo declara en `_source` y no debe usarse para diseño de campo real.
11. El sistema produce **prediseños**: la decisión final de campo requiere verificación con catálogos certificados, análisis de empuje axial detallado, y criterios operativos de la empresa.

---

## 8. Glosario mínimo

| Término | Significado |
|---------|-------------|
| **BES / ESP** | Bombeo Electrosumergible (Electric Submersible Pump): sistema de levantamiento artificial con bomba centrífuga multietapa de fondo accionada por motor eléctrico. |
| **IPR** | Inflow Performance Relationship: relación entre el caudal aportado por el reservorio y la presión de fondo fluyente. |
| **PVT** | Comportamiento Presión-Volumen-Temperatura de los fluidos del reservorio. |
| **Pwf / Pb / Pr** | Presión de fondo fluyente / de burbuja / estática media del reservorio. |
| **PIP** | Pump Intake Pressure: presión en la admisión de la bomba. |
| **TDH** | Total Dynamic Head: altura total (en ft de líquido) que la bomba debe desarrollar. |
| **BEP** | Best Efficiency Point: caudal de máxima eficiencia de la bomba; operar cerca del BEP maximiza la vida útil. |
| **GIP** | Gas In Pump: fracción de gas libre que ingresa a la bomba; valores altos degradan la curva y pueden bloquear la bomba (gas lock). |
| **GOR / WC** | Relación gas-petróleo de producción / corte de agua. |
| **Housing** | Cuerpo comercial de la bomba con un número fijo de etapas. |
| **Serie** (375, 400, 513…) | Diámetro nominal del equipo en centésimas de pulgada (serie 513 = 5.13"). |
| **Análisis nodal** | Intersección de la curva de oferta del reservorio (IPR) con la curva de demanda del sistema de producción (outflow) para hallar el punto de operación. |

---

## 9. Referencias

- Brown, K. E. (1980). *The Technology of Artificial Lift Methods, Vol. 2b: Electric Submersible Pumping Systems.* PennWell Books, Tulsa. — Metodología principal (Cap. 4.5).
- Brown, K. E. (1984). *The Technology of Artificial Lift Methods, Vol. 4: Production Systems Analysis.* PennWell Books. — Análisis nodal.
- Takacs, G. (2009). *Electrical Submersible Pumps Manual.* Gulf Professional Publishing.
- Vogel, J. V. (1968). "Inflow Performance Relationships for Solution-Gas Drive Wells." *JPT* 20(1), 83–92.
- Standing, M. B. (1947). "A Pressure-Volume-Temperature Correlation for Mixtures of California Oils and Gases." *API Drilling and Production Practice*, 275–287.
- Hagedorn, A. R. & Brown, K. E. (1965). "Experimental Study of Pressure Gradients Occurring During Continuous Two-Phase Flow in Small-Diameter Vertical Conduits." *JPT* 17(4), 475–484.
- Beggs, H. D. & Brill, J. P. (1973). "A Study of Two-Phase Flow in Inclined Pipes." *JPT* 25(5), 607–617.
- Beggs, H. D. & Robinson, J. R. (1975). "Estimating the Viscosity of Crude Oil Systems." *JPT* 27(9), 1140–1141.
- Dranchuk, P. M. & Abou-Kassem, J. H. (1975). "Calculation of Z Factors for Natural Gases Using Equations of State." *JCPT* 14(3), 34–36.
- Fetkovich, M. J. (1973). "The Isochronal Testing of Oil Wells." SPE-4529.
- Hydraulic Institute. *ANSI/HI 9.6.7 — Effects of Liquid Viscosity on Rotodynamic Pump Performance.*
- American Petroleum Institute. *API RP 11S6 — Recommended Practice for Testing of Electric Submersible Pump Cable Systems.*

**Documentos complementarios del repositorio:** `docs/METHODOLOGY.md` (correlaciones en detalle), `docs/USER_GUIDE.md` (guía de uso), `docs/VALIDATION.md` (tabla de validación generada), `docs/BROWN_CHAPTER_SUMMARY.md` y `docs/BROWN_VOL4_NODAL_ANALYSIS.md` (resúmenes del libro).
