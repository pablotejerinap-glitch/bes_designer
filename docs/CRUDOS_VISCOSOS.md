# Crudos viscosos

Dos métodos, dos fuentes:

- **Riling** — Kermit Brown, *The Technology of Artificial Lift Methods*,
  Vol. 2b, **§4.53112**, con las figuras del Apéndice 4L y las Tablas
  4.520 / 4.521.
- **Hydraulic Institute**, en el ajuste numérico de Turzo et al. — Gábor
  Takács, *Electrical Submersible Pumps Manual*, 2.ª ed., Elsevier 2018,
  **§4.2.2**, ecuaciones 4.1 a 4.14.

Documento de trabajo: describe los métodos, los verifica contra los ejemplos
publicados, resuelve un ejercicio paso a paso y deja anotado qué falta.

**Estado: implementado en `bes/core/viscosity.py`** (etapas 0 a 4 y 5b-5d del
plan de §9). Riling reproduce el ejercicio de cátedra con los valores exactos
—88 % / 88.75 % / 117.3 % de factores, 1932 b/d y 5893 ft de equivalente en
agua—; el modelo Hydraulic Institute reproduce los tres ejemplos publicados
(§11). Enganchado al motor de diseño (etapa 5, ver §12); falta mostrarlo en
pantalla (etapa 7) y el corte de agua (etapa 6, bloqueada). Cubierto por `backend/tests/test_viscosity.py`, 75 tests.

---

## 1. El problema

Las curvas de catálogo de una bomba centrífuga se levantan **con agua limpia**:
SG = 1.0 y viscosidad ≈ 1 cp. Un crudo viscoso rompe las tres cosas que la curva
promete:

- **Entrega menos caudal** — la fricción interna del fluido resiste el paso.
- **Desarrolla menos altura** — parte de la energía del impulsor se disipa en
  corte viscoso en vez de convertirse en presión.
- **Consume más potencia** — la eficiencia cae, y la potencia crece además con
  la densidad del fluido.

Diseñar un pozo de crudo pesado con la curva de agua da una bomba corta de
etapas y un motor corto de potencia. Riling da el procedimiento para corregirlo.

---

## 1-bis. Cuándo aplica: el corte de 28 °API

Antes de entrar al procedimiento hay una decisión previa: **¿este crudo es
viscoso?**

```
°API ≥ 28   →  crudo liviano. NO se corrige nada, se diseña con la curva de agua.
°API < 28   →  crudo pesado. Se corre el procedimiento completo.
```

Los 28.0 exactos cuentan como liviano: el criterio es «de 28 para arriba».

**Por qué ahí.** Evaluando la cadena entera —viscosidad, SSU y factores de la
Tabla 4.521— justo en el umbral:

| | μ | SSU | C_Q | C_H |
|---|---:|---:|---:|---:|
| 28 °API a 120 °F | 12 cp | 72 | 99.6 % | 100.0 % |
| 28 °API a 180 °F | 4 cp | 41 | 100.0 % | 100.0 % |

La corrección ya vale **menos del 0.5 %**, que es menos que el error de leer un
gráfico logarítmico. Corregir ahí sería precisión falsa.

Cómo se comporta al cruzar el umbral, con 50 scf/bbl a 130 °F:

| °API | | C_Q | C_H | Rendimiento |
|---:|---|---:|---:|---:|
| 30 | liviano | 100 % | 100 % | 70.0 % |
| **28** | **liviano** | 100 % | 100 % | 70.0 % |
| **27** | **viscoso** | 100 % | 100 % | 69.4 % |
| 20 | viscoso | 99.2 % | 99.7 % | 66.4 % |
| 16 | viscoso | 92.7 % | 92.9 % | 52.7 % |

Fijate el salto de 28 a 27: el caudal y la altura todavía dan 100 %, **pero el
rendimiento ya cae**. La viscosidad pega primero en la eficiencia, y recién
después en el caudal y la altura — es lo mismo que se ve leyendo la tabla de
arriba abajo (§4).

En el código: `VISCOUS_CRUDE_API_THRESHOLD`, `is_viscous_crude()` y el punto de
entrada `evaluate_viscosity()`, que aplica la regla **antes** de calcular nada.

## 2. Los ocho pasos

Transcripción del §4.53112:

| # | Paso |
|---|---|
| 1 | Determinar el TDH que haría falta bombeando **agua de SG 1.0**, con los procedimientos ya vistos. |
| 2 | Obtener —de ensayos o de la Fig. 4L— la **viscosidad del crudo sin gas** a temperatura de reservorio. |
| 3 | Corregir esa viscosidad **por el gas en solución** (Fig. 4L o ensayos reales). |
| 4 | Convertir la viscosidad a **unidades SSU** (Fig. 4L). |
| 5 | Corregir la viscosidad de la mezcla **por corte de agua**, si hay datos. |
| 6 | Entrar a la **Tabla 4.520 o 4.521** y aplicar los factores de corrección a la capacidad y a la altura. |
| 7 | **Seleccionar** la bomba y el motor. |
| 8 | Dimensionar el resto del equipo de fondo y superficie según los procedimientos anteriores. |

### Discrepancia en la numeración de las figuras

El texto del procedimiento manda al paso 2 a la «Fig. 4L.1» (crudo sin gas) y al
paso 3 a la «Fig. 4L.2» (saturado con gas). Pero en el apéndice las láminas
vienen rotuladas al revés:

- **Fig. 4L (1)** — *Viscosity of gas saturated crude oil at reservoir
  temperature & pressure* → es la del **paso 3**
- **Fig. 4L (2)** — *The viscosity of gas-free oil at oil-field temperatures* →
  es la del **paso 2**

**Hay que guiarse por el contenido de cada lámina, no por su número.** Se usan
en el orden: primero la de crudo sin gas, después la de gas disuelto.

---

## 3. Las figuras del Apéndice 4L

### Fig. 4L (2) — viscosidad del crudo sin gas

| | |
|---|---|
| **Entra con** | Gravedad API a 60 °F (eje horizontal, 10 a 65) |
| | Temperatura del crudo (familia de curvas: 100, 130, 160, 190, 220 °F, más una curva rotulada «reservoir temperature») |
| **Sale** | Viscosidad absoluta del crudo sin gas [cp], escala logarítmica de 0.1 a 10 000 |

La pendiente es brutal: a 100 °F, un crudo de 20 °API está cerca de 100 cp y uno
de 40 °API no llega a 3 cp. **La viscosidad es el parámetro más sensible de todo
el diseño.**

### Fig. 4L (1) — corrección por gas en solución

| | |
|---|---|
| **Entra con** | Gas en solución a presión de reservorio [scf/bbl], eje horizontal de 0 a 1300 |
| | Viscosidad del crudo sin gas del paso anterior (familia de curvas: 0.7, 1.0, 1.5, 2, 3, 4, 5, 7, 10, 15, 20, 30, 40, 50, 70, 100, 200, 300, 500 cp) |
| **Sale** | Viscosidad absoluta del crudo saturado a presión y temperatura de reservorio [cp] |

**El gas disuelto adelgaza el crudo**, y bastante: 50 scf/bbl sobre un crudo de
60 cp lo baja a ~33 cp.

### Fig. 4L (3) — conversión a SSU

Nomograma de tres escalas: viscosidad en cP/cSt, gravedad específica
(1.0 / 0.9 / 0.8 / 0.7) y viscosidad en **SSU** (Segundos Saybolt Universal), de
30.2 a 22 000.

La conversión pasa por la viscosidad **cinemática**:

```
ν [cSt] = μ [cp] / SG
```

y de ahí a SSU. Equivalente analítico (ASTM D2161, el que ya usa la app en
`pump_design.py` en sentido inverso):

```
ν < 100 SSU :  cSt = 0.226·SSU − 195/SSU
ν ≥ 100 SSU :  cSt = 0.220·SSU − 135/SSU
```

---

## 4. Las tablas de corrección 4.520 y 4.521

**Son dos tablas, y cuál usar depende del rendimiento máximo de la bomba:**

- **Tabla 4.520** — bombas de **60 %** de rendimiento máximo
- **Tabla 4.521** — bombas de **70 %** de rendimiento máximo

Ese es el eje que le falta a cualquier corrección de una sola entrada: la misma
viscosidad castiga distinto a una bomba mediocre que a una buena.

Encabezado: *«Performances as percentages of performance with water, all at
maximum efficiency»*. O sea que los factores son **porcentajes de lo que la
bomba da con agua**, evaluados en el punto de máximo rendimiento.

### Tabla 4.520 — bombas de 60 %

| SSU | Capacidad % | Altura % | Rendimiento nuevo % | Potencia % (× γ_o) |
|---:|---:|---:|---:|---:|
| 50 | 100.0 | 100.0 | 57.5 | 104.0 |
| 80 | 98.5 | 99.5 | 54.0 | 107.8 |
| 100 | 98.0 | 99.0 | 52.0 | 110.8 |
| 150 | 96.0 | 96.0 | 47.5 | 116.3 |
| 200 | 94.0 | 94.0 | 44.5 | 119.1 |
| 300 | 91.0 | 91.0 | 40.0 | 124.2 |
| 400 | 88.0 | 89.0 | 37.0 | 127.0 |
| 500 | 85.0 | 86.0 | 34.0 | 128.0 |
| 600 | 83.0 | 84.5 | 32.5 | 129.5 |
| 700 | 80.5 | 82.5 | 30.5 | 130.0 |
| 800 | 79.0 | 81.0 | 29.0 | 131.0 |
| 900 | 77.0 | 80.0 | 27.5 | 132.0 |
| 1 000 | 75.0 | 78.0 | 26.5 | 133.0 |
| 1 500 | 69.0 | 72.5 | 22.0 | 136.5 |
| 2 000 | 63.0 | 67.5 | 19.5 | 131.0 |
| 2 500 | 58.0 | 63.0 | 17.0 | 129.0 |
| 3 000 | 54.0 | 60.5 | 15.0 | 127.5 |
| 4 000 | 47.0 | 50.5 | 12.0 | 118.7 |
| 5 000 | 41.0 | 45.0 | 10.0 | 111.0 |

### Tabla 4.521 — bombas de 70 %

| SSU | Capacidad % | Altura % | Rendimiento nuevo % | Potencia % (× γ_o) |
|---:|---:|---:|---:|---:|
| 50 | 100.0 | 100.0 | 67.5 | 100.8 |
| 80 | 99.5 | 100.0 | 65.5 | 103.0 |
| 100 | 99.5 | 99.5 | 63.5 | 105.3 |
| 150 | 98.0 | 99.0 | 62.0 | 109.0 |
| 200 | 96.5 | 97.0 | 59.0 | 111.0 |
| 300 | 94.5 | 95.0 | 55.0 | 114.0 |
| 400 | 92.0 | 92.0 | 51.5 | 115.0 |
| 500 | 90.5 | 90.5 | 49.0 | 117.0 |
| 600 | 89.0 | 89.5 | 47.5 | 117.3 |
| 700 | 87.0 | 88.0 | 45.7 | 117.3 |
| 800 | 85.5 | 86.0 | 44.0 | 117.0 |
| 900 | 84.0 | 85.0 | 43.0 | 116.2 |
| 1 000 | 83.0 | 84.0 | 42.0 | 116.0 |
| 1 500 | 78.0 | 79.0 | 37.0 | 113.5 |
| 2 000 | 74.0 | 75.5 | 34.7 | 112.6 |
| 2 500 | 70.5 | 72.5 | 32.0 | 111.6 |
| 3 000 | 67.0 | 69.5 | 30.0 | 108.8 |
| 4 000 | 61.0 | 64.0 | 27.0 | 101.2 |
| 5 000 | 55.0 | 60.0 | 25.0 | 92.4 |

### El «× 80» de la columna de potencia

En el escaneo la última columna aparece como **«104.0 × 80»**, **«107.8 × 80»**,
etc. Eso **no es un 80**: es **γ_o** —la gravedad específica del petróleo a
temperatura de bombeo— que el propio pie de tabla define. El subíndice `o` de la
letra griega se degradó en el escaneo.

**Se verificó numéricamente.** Si la hipótesis es correcta, el factor de potencia
tiene que salir de la definición misma de potencia hidráulica:

```
HP% = (C_Q · C_H / η_viscoso) · η_agua · 100        [y después × γ_o]
```

Contrastando esa fórmula contra las 38 filas impresas: **30 coinciden dentro de
1.5 puntos porcentuales y la mayoría dentro de 0.1**. Ejemplo, tabla 4.520 a
1 000 SSU:

```
(0.750 × 0.780 / 0.265) × 0.60 × 100 = 132.5 %     impreso: 133.0 %
```

Las filas con más de 2 puntos de diferencia (4.520 a 900 y 3 000 SSU; 4.521 a 50,
80, 100 y 1 500 SSU) probablemente sean dígitos mal leídos del escaneo, no
errores del libro. **Conviene releerlas de una copia más limpia antes de
cargarlas.** Al programar, el valor que manda es el impreso —es el dato
publicado—, y la fórmula queda como verificación.

### Interpretación física de la tabla

Leyendo la 4.520 de arriba abajo:

- A **50 SSU** la capacidad y la altura no se tocan, pero **el rendimiento ya
  cayó de 60 % a 57.5 %**. La viscosidad pega primero en la eficiencia.
- A **1 000 SSU** la bomba entrega el 75 % del caudal, el 78 % de la altura, y
  su rendimiento se derrumbó a 26.5 % — menos de la mitad.
- A **5 000 SSU** queda en 41 % de caudal y 10 % de rendimiento. **La bomba
  centrífuga dejó de tener sentido**; ahí se piensa en bombeo de cavidad
  progresiva.

El factor de potencia sube hasta ~136 % y después **baja**. No es que la bomba
mejore: es que a esa viscosidad mueve tan poco caudal que la potencia absoluta
cae, aunque el rendimiento sea pésimo.

---

## 5. Ejemplo resuelto

**Crudo pesado de 16 °API, reservorio a 130 °F, 50 scf/bbl de gas en solución,
sin agua. El pozo pide 500 STB/d con un TDH de 4 000 ft.**

### Paso 1 — TDH con agua

Por el procedimiento normal (Brown §4.5324, ya implementado en la app):

```
TDH = 4 000 ft
```

### Gravedad específica del petróleo

```
SG = 141.5 / (131.5 + 16) = 0.9593
```

### Paso 2 — viscosidad del crudo sin gas

De la Fig. 4L (2), entrando con 16 °API y 130 °F: **150 cp**.

Y eso es literalmente lo que hace el código. La lámina está digitalizada en
`catalogs/viscosity_charts.json` y se lee con
`viscosity.dead_oil_viscosity_chart(16, 130)` → **151.9 cp**, interpolando
bilinealmente sobre `log10(μ)` porque el eje de la lámina es logarítmico.

Antes este paso lo resolvía Beggs-Robinson (`pvt.oil_viscosity_dead`), que en el
mismo punto da **59.15 cp**: un factor 2.5 por debajo de la figura, error que se
arrastraba por los pasos 3, 4 y 6 hasta los factores de corrección. Ésa fue la
razón para digitalizar la lámina. La correlación sigue existiendo en `pvt.py`
—la usa el PVT general— pero **no interviene más en el procedimiento de Riling**.

### Paso 3 — corrección por gas disuelto

De la Fig. 4L (1), entrando con 50 scf/bbl sobre la curva de 150 cp: **68 cp**.

También es lo que hace el código. La lámina está digitalizada en el mismo
archivo y se lee con `viscosity.gas_saturated_viscosity_chart(150, 50)` →
**68.0 cp**. Cada curva de esa lámina está rotulada con la viscosidad del crudo
sin gas, así que se entra con el resultado del paso 2; la interpolación es
lineal en el gas en solución (el eje está impreso lineal) y logarítmica en las
dos viscosidades.

Antes este paso lo resolvía Beggs-Robinson (`pvt.oil_viscosity_live`), que sobre
los 150 cp da **76.6 cp**. La figura impresa es en realidad la carta de Chew &
Connally (1959) —otra correlación, con la misma forma funcional
μ_vivo = A · μ_muerto^B pero coeficientes distintos—, así que el módulo citaba
una fuente que no era la que ejecutaba. Leyendo la lámina el problema
desaparece: la fuente citada y la evaluada son la misma.

El gas disuelto **partió la viscosidad al medio**.

### Paso 4 — a unidades SSU

```
ν = 32.91 cp / 0.9593 = 34.31 cSt
                      → 160 SSU        (Fig. 4L-3 / ASTM D2161)
```

### Paso 5 — corrección por corte de agua

Este pozo no produce agua, así que el paso no aplica. **Ojo: si produjera, acá
falta método** — ver §8.

### Paso 6 — factores de la tabla

Bomba de 60 % de rendimiento máximo → **Tabla 4.520**, interpolando entre 150 y
200 SSU:

| | 150 SSU | **160 SSU** | 200 SSU |
|---|---:|---:|---:|
| Capacidad | 96.0 % | **95.6 %** | 94.0 % |
| Altura | 96.0 % | **95.6 %** | 94.0 % |
| Rendimiento nuevo | 47.5 % | **46.9 %** | 44.5 % |
| Potencia | 116.3 % | **116.8 %** | 119.1 % |

### Paso 7 — selección

**Acá está el punto que más se equivoca.** El pozo pide 500 STB/d y 4 000 ft
**bombeando el crudo**. Los factores dicen qué fracción de su curva de agua
entrega la bomba con ese crudo. Entonces la bomba hay que buscarla en su curva de
agua **dividiendo**, no multiplicando:

```
Q_agua = 500  / 0.956 =   523 STB/d
H_agua = 4000 / 0.956 = 4 184 ft
```

Es decir: **hay que elegir una bomba que con agua dé 523 STB/d y 4 184 ft** para
que con este crudo entregue los 500 y 4 000 que el pozo necesita.

Y la potencia:

```
HP = 116.8 % × 0.9593 = 1.121 × la potencia con agua
```

| | Con agua | Con el crudo |
|---|---:|---:|
| Caudal | 523 STB/d | 500 STB/d |
| Altura | 4 184 ft | 4 000 ft |
| Rendimiento | 60 % | 46.9 % |
| Potencia | 1.00 | **1.12** |

Un crudo de 160 SSU —que no es extremo— ya pide **12 % más de potencia** y baja
el rendimiento **13 puntos**.

---

## 6. La lógica del método, en una línea

```
API + temperatura        → Fig 4L(2) → μ sin gas [cp]
μ sin gas + Rs           → Fig 4L(1) → μ saturado [cp]
μ saturado / SG          →            ν [cSt]
ν [cSt]                  → Fig 4L(3) → SSU
SSU + rendimiento bomba  → Tabla 4.520/4.521 → C_Q, C_H, η_nuevo, C_HP
Q_agua = Q_pedido / C_Q  ·  H_agua = H_pedido / C_H  ·  HP = C_HP × γ_o
```

---

## 7. Qué hay en la app

Todo en **`bes/core/viscosity.py`**, con las tablas en
`bes/catalogs/viscosity_correction.json`.

| Función | Paso | Qué hace |
|---|---|---|
| `is_viscous_crude(api)` | previo | El corte de 28 °API |
| `crude_viscosity_ssu()` | 2, 3, 4 | De °API y temperatura a SSU |
| `viscosity_factors()` | 6 | Los cuatro factores, interpolando en SSU y entre tablas |
| `water_equivalent_duty()` | 7 | Invierte el sentido: `Q/C_Q`, `H/C_H` |
| `evaluate_viscosity()` | 2-6 | Punto de entrada: aplica el corte y encadena todo |
| `cst_to_ssu()` / `ssu_to_cst()` | 4 | ASTM D2161 en los dos sentidos |

### Lo que se eliminó

`pump_design.apply_viscosity_correction()` **se borró** (etapa 0 del plan). Tenía
tres problemas de fondo y no la llamaba nadie:

1. **Su tabla no tenía fuente ni coincidía con Riling** — 8 puntos entre 1 y
   500 cSt, sin `_source`, con valores que no son los de las tablas 4.520/4.521.
2. **Le faltaba el eje del rendimiento de la bomba**, que es lo que distingue la
   4.520 de la 4.521.
3. **Corregía en el sentido contrario** al que hace falta para seleccionar.

### Decisiones tomadas al programar

- **La temperatura de evaluación es la de fondo** (§8.2 resuelto).
- **El valor medido de viscosidad manda sobre la correlación.** Beggs-Robinson
  queda de respaldo y **avisa**: para 16 °API a 130 °F da 59 cp contra los
  150 cp de la Fig. 4L-2, porque 16 °API es el borde exacto de su rango de
  validez (16–58 °API) y la curva ahí es exponencial. Riling dice «de ensayos o
  de la Fig. 4L» — la correlación es un tercer camino que él no menciona.
- **Interpolación lineal entre las tablas de 60 % y 70 %**, acotada fuera de ese
  rango (§8.3 resuelto). Las tablas se titulan «approximate changes»: pedirle
  más precisión a la interpolación que a la fuente no tendría sentido.
- **Nunca extrapola.** Fuera de 50–5000 SSU acota y avisa; por arriba el mensaje
  dice explícitamente que la bomba centrífuga dejó de ser la opción (§8.5
  resuelto).
- **El corte de agua entra como dato medido**, no como cuenta. Sin él, el paso 5
  se reporta como **no realizado** — el mismo criterio que se usa con la
  capacidad de empuje de los sellos.

### Pendiente

- **Digitalizar la Fig. 4L-2.** Se intentó desde la captura de la filmina
  (993×746) y no alcanza: el rótulo «RESERVOIR TEMPERATURE» cae justo sobre las
  curvas de 10 a 25 °API y la extracción automática encuentra 62 tramos oscuros
  en la columna de API 16 — las líneas de grilla logarítmica ahogan las curvas.
  Hace falta la página del libro en PDF o una foto a mayor resolución.
- Etapa 5 (enganchar al motor de diseño) y etapa 7 (interfaz).

---

## 8. Lo que falta resolver antes de programar

### 8.1 El paso 5 no tiene método

Riling dice *«corregir la viscosidad de la mezcla por corte de agua, **si hay
datos**»* y no da ninguna correlación. No es un olvido: la viscosidad de una
emulsión agua-petróleo **no se interpola** entre las dos fases.

- Con agua dispersa en petróleo, la emulsión puede ser **varias veces más
  viscosa que el petróleo solo**.
- Pasado el **punto de inversión** (típicamente 50-70 % de corte), la emulsión se
  da vuelta a agua-continua y la viscosidad **se desploma**.

Hace falta decidir: buscar una correlación (Woelflin, Brinkman, Vand) o pedir el
dato de laboratorio y dejar la verificación como no realizada cuando no esté.
**Es el hueco más grande del procedimiento.**

### 8.2 A qué temperatura se evalúa

El paso 2 dice «a temperatura de reservorio», pero la tabla dice «at pumping
temperatures». No son la misma: el fluido se enfría subiendo por el tubing, y la
viscosidad es exponencial con la temperatura. **Hay que definir en qué punto se
evalúa** —admisión de la bomba parece lo correcto— y dejarlo escrito.

### 8.3 Interpolación entre las dos tablas

Las tablas son para 60 % y 70 % exactos. Una bomba de 64 % de rendimiento
máximo cae en el medio. ¿Se interpola entre tablas, se usa la más cercana, o se
extrapola para bombas fuera de ese rango?

### 8.4 El lazo de realimentación

Corregir la altura cambia las etapas, que cambian la potencia, que cambia la
selección de motor. Y si el motor cambia, cambia el diámetro y puede cambiar la
bomba elegida. **Hay que decidir si se itera o se resuelve de una pasada.**

### 8.5 Límite de aplicabilidad

A 5 000 SSU el rendimiento cae a 10 %. La app debería **avisar que la bomba
centrífuga dejó de ser la opción razonable** en vez de entregar un diseño
formalmente correcto pero absurdo. Falta definir el umbral.

### 8.6 Releer cuatro filas del escaneo

Las filas señaladas en §4 (4.520 a 900 y 3 000 SSU; 4.521 a 50, 80, 100 y
1 500 SSU) no cierran con la fórmula interna por más de 2 puntos. Antes de
cargarlas conviene verlas en una copia mejor.

---

## 9. Plan de implementación

Se construye **de abajo hacia arriba**: primero el dato, después las funciones
puras que lo usan, después el enganche al motor de diseño, y al final la
interfaz. Cada etapa deja tests propios, así que si algo se rompe más adelante
se sabe exactamente en qué capa.

Todo vive en un módulo nuevo, **`bes/core/viscosity.py`**, para no ensuciar
`pump_design.py` y para que el procedimiento se pueda leer de corrido.

### Etapa 0 — Limpiar lo que hay

`pump_design.apply_viscosity_correction()` se elimina. Su tabla no tiene fuente,
no coincide con Riling, le falta el eje del rendimiento y corrige al revés. No
la llama nadie, así que borrarla no rompe nada salvo sus propios tests.

**Entregable:** función y tests eliminados, con nota en `CLAUDE.md`.

---

### Etapa 1 — El dato: tablas 4.520 y 4.521

Archivo `bes/catalogs/viscosity_correction.json`, con las dos tablas completas y
su `_source` apuntando a Brown Vol. 2b, Tablas 4.520 y 4.521.

```json
{
  "_source": "Brown Vol. 2b, Tablas 4.520 y 4.521 ...",
  "_note": "La columna de potencia se publica como «valor × γ_o» ...",
  "tables": {
    "60": [{"ssu": 50, "cq": 100.0, "ch": 100.0, "eff": 57.5, "chp": 104.0}, ...],
    "70": [...]
  }
}
```

**Test de la etapa:** verificar que cada fila cumple la relación interna
`C_HP = (C_Q·C_H/η_nuevo)·η_agua·100` dentro de la tolerancia que salga de §8.6.
Es el mismo control que ya se corrió en §4 y que detectó las cuatro filas
sospechosas.

**Bloqueo:** releer esas cuatro filas antes de cargarlas (§8.6).

---

### Etapa 2 — Pasos 2 a 4: de °API a SSU

```python
def crude_viscosity_ssu(
    oil_api: float, temp_f: float, rs_scf_bbl: float,
) -> dict:
    """Pasos 2, 3 y 4 de Riling: de °API y temperatura a SSU."""
```

Encadena lo que **ya existe** en `pvt.py`:

| Paso de Riling | Función | Fuente |
|---|---|---|
| 2 — crudo sin gas | `dead_oil_viscosity_chart(api, t)` | **Fig. 4L(2) digitalizada** |
| 3 — corregir por gas | `gas_saturated_viscosity_chart(mu_dead, rs)` | **Fig. 4L(1) digitalizada** |
| 4 — a SSU | `cst_to_ssu(cst)` | ASTM D2161 invertida por bisección |

Devuelve el encadenado completo —`mu_dead`, `mu_live`, `cst`, `ssu`— para poder
mostrarlo en la traza de fórmulas.

**Test de la etapa:** que `cst_to_ssu` sea la inversa exacta de la conversión que
ya existe, y el ejemplo de §5 (16 °API, 130 °F, 50 scf/bbl → 160 SSU).

---

### Etapa 3 — Paso 6: los factores

```python
def viscosity_factors(ssu: float, pump_bep_efficiency: float) -> dict:
    """Paso 6: C_Q, C_H, rendimiento nuevo y C_HP, de las tablas 4.520/4.521."""
```

Dos interpolaciones:

- **En SSU**, lineal dentro de la tabla.
- **Entre tablas**, según el rendimiento máximo de la bomba (§8.3 — hay que
  decidir el criterio).

Fuera de rango (< 50 o > 5000 SSU) **no extrapola**: acota y avisa (§8.5).

**Test de la etapa:** los valores de las filas exactas, la interpolación del
ejemplo (160 SSU → C_Q = 95.6 %), y que fuera de rango avise en vez de
inventar.

---

### Etapa 4 — Paso 7: invertir el sentido

```python
def water_equivalent_duty(
    q_required: float, h_required: float, factors: dict,
) -> dict:
    """Paso 7: qué tiene que dar la bomba CON AGUA para cumplir con el crudo."""
```

```
Q_agua = Q_pedido / C_Q
H_agua = H_pedido / C_H
```

Es el punto que más se equivoca (§5, paso 7). Va en su propia función, con el
docstring explicando por qué se divide y no se multiplica.

**Test de la etapa:** ida y vuelta — corregir de agua a viscoso y volver tiene
que devolver el valor original.

---

### Etapa 5 — Enganchar al motor de diseño

En `design_pump_complete()`:

1. Calcular la viscosidad en la **admisión de la bomba** (§8.2 — hay que
   decidirlo y dejarlo escrito).
2. Obtener los factores con el rendimiento de la bomba candidata.
3. Buscar la bomba contra el **caudal y altura equivalentes en agua**.
4. Reportar el rendimiento degradado y la potencia corregida.
5. Emitir la **traza de fórmulas** de los cinco pasos, con la cita a Riling.

**Decisión pendiente (§8.4):** el rendimiento de la bomba entra a la tabla, pero
la tabla cambia la bomba elegida, que tiene otro rendimiento. Hay que definir si
se itera hasta converger o se resuelve de una pasada con el rendimiento de la
primera candidata.

**Test de la etapa:** un pozo con crudo viscoso pide más etapas y más potencia
que el mismo pozo con agua, y la traza sale completa.

---

### Etapa 6 — Corte de agua (paso 5)

**Bloqueada** hasta decidir el método (§8.1). Riling no da ninguno.

Hasta que se decida, el paso se reporta como **no realizado** —el mismo criterio
que se usa con la capacidad de empuje de los sellos— en vez de aplicar una
interpolación que sería falsa.

---

### Etapa 7 — Interfaz

- Campo de viscosidad y su temperatura ya existen en el formulario.
- Mostrar en resultados: viscosidad en cp y SSU, los cuatro factores, el
  rendimiento degradado y la potencia corregida.
- La traza de fórmulas sale sola: la emite la etapa 5.
- **Advertencia visible** cuando la viscosidad sale del rango de las tablas.

---

### Resumen de dependencias

```
Etapa 0 (limpiar)  ─┐
Etapa 1 (tablas)   ─┼─▶ Etapa 3 (factores) ─┐
Etapa 2 (a SSU)    ─┘                        ├─▶ Etapa 5 (motor) ─▶ Etapa 7 (UI)
                        Etapa 4 (invertir) ──┘
                        Etapa 6 (corte de agua) ── BLOQUEADA
```

### Lo que hace falta para arrancar

| Necesito | Para qué |
|---|---|
| **Un ejercicio resuelto** | Validar de punta a punta. Sin un caso con respuesta conocida no hay forma de saber si está bien. |
| Las cuatro filas releídas (§8.6) | Cargar las tablas con confianza |
| Decisión sobre §8.2 (temperatura) | Etapa 5 |
| Decisión sobre §8.3 (interpolar entre tablas) | Etapa 3 |
| Decisión sobre §8.4 (iterar o no) | Etapa 5 |
| Decisión sobre §8.1 (corte de agua) | Etapa 6 |

---

## 11. El modelo Hydraulic Institute (Takács §4.2.2)

Takács trata el mismo problema con otro método. No reemplaza a Riling: contesta
otra pregunta, y por eso conviven en el módulo.

### 11.1 Qué hace distinto

| | Riling (Brown) | Hydraulic Institute (Takács) |
|---|---|---|
| Entrada | viscosidad + clase de rendimiento | viscosidad + **BEP de la bomba** |
| Factor de altura | uno solo | **cuatro**, a 0.6 / 0.8 / 1.0 / 1.2 del BEP |
| Forma | tablas, se interpola | ecuaciones cerradas |
| ¿Hay que saber qué bomba es? | no | **sí** |
| Sirve para | **buscar** en el catálogo | **verificar** la elegida |

Que Riling no necesite saber la bomba es precisamente lo que lo hace útil como
filtro: permite invertir el sentido (`Q_agua = Q_pedido / C_Q`) y salir a
buscar. El HI no puede hacer eso —necesita el BEP, que es lo que todavía no se
conoce— pero a cambio devuelve la **curva corregida completa**, así que sirve
después, para confirmar que la bomba elegida sigue cumpliendo.

### 11.2 Las ecuaciones

Todo pasa por un único parámetro de correlación, el caudal corregido `Q*`:

```
y  = −7.5946 + 6.6504·ln(H_BEP) + 12.8429·ln(Q_BEP)          (ec. 4.5)
Q* = exp[ (39.5276 + 26.5605·ln(ν) − y) / 51.6565 ]          (ec. 4.4)
```

con `H_BEP` en ft, `Q_BEP` en **«100 gpm»** (unidad rara: bpd × 42/1440/100) y
`ν` en cSt. De `Q*` salen los seis factores:

```
C_Q     = 1 − 4.0327e−3·Q* − 1.724e−4·Q*²                    (ec. 4.6)
C_η     = 1 − 3.3075e−2·Q* + 2.8875e−4·Q*²                   (ec. 4.7)
C_H,0.6 = 1 − 3.68e−3·Q*    − 4.36e−5·Q*²                    (ec. 4.8)
C_H,0.8 = 1 − 4.4723e−3·Q*  − 4.18e−5·Q*²                    (ec. 4.9)
C_H,1.0 = 1 − 7.00763e−3·Q* − 1.41e−5·Q*²                    (ec. 4.10)
C_H,1.2 = 1 − 9.01e−3·Q*    + 1.31e−5·Q*²                    (ec. 4.11)
```

Se aplican **multiplicando**, que es el sentido natural (`Q_visc = C_Q · Q_agua`).
Para seleccionar hay que invertirlo igual que con Riling.

El punto de caudal cero **no se corrige**: sin caudal no hay fricción dentro de
la bomba, así que la altura de cierre es la misma con crudo que con agua. Es lo
que ancla el extremo izquierdo de la curva nueva.

### 11.3 Dos erratas del impreso, las dos verificadas

**Errata 1 — el signo de `C_H,1.0`.** El ejemplo resuelto de la pág. 157 lo
calcula con el cuadrático en **+** y le da 0.844. La ecuación 4.10, impresa dos
páginas antes, lo tiene en **−**, que da 0.829. Manda la ecuación, por tres
razones independientes:

1. El ejemplo del paper original en *Oil & Gas Journal* (Q* = 2.698) publica
   `C_H3 = 0.9810`. Con − sale 0.98099; con + saldría 0.98120.
2. Con + los coeficientes cuadráticos dejan de ser monótonos
   (−4.36e−5, −4.18e−5, **+1.41e−5**, +1.31e−5).
3. Con + las curvas de 0.8 y 1.0 se cruzan a partir de Q* ≈ 45: el modelo
   diría que la corrección es más benigna en el BEP que al 80 % del BEP, lo
   cual no tiene sentido físico.

**Errata 2 — la unidad del rendimiento en la ec. 4.12.** El libro anota
`η = pump efficiency, %`, pero la fórmula sólo cierra con η en **fracción**:

```
BHP = 7.368e−6 · Q · H · γ / η
```

Con η en % da 100 veces chico. Verificado contra sus propios números: el BEP con
agua del Ejemplo 4.1 (900 bpd, 21.8 ft, γ = 1.0, η = 64 %) tiene que dar los
0.225 HP que el Ejemplo 4.2 lee de la curva, y eso sale con η = 0.64. La
constante lo confirma: 42/(1440·3960) = 7.366e−6 es la conversión de bpd·ft·SG
a HP hidráulicos, y esa cuenta lleva el rendimiento en fracción.

En el código el rendimiento en porcentaje se **rechaza con `ValueError`**, para
que nadie repita el error que el libro induce.

### 11.4 Dónde se rompe el modelo — el hallazgo

Las ecuaciones son un ajuste a una zona acotada del diagrama y extrapolan mal.
Dos cosas se rompen, en este orden:

| | Qué pasa |
|---|---|
| `Q* > 57.3` | El cuadrático de `C_η` (que va en +) domina y la parábola se da vuelta: el modelo empieza a decir que **más viscosidad da mejor rendimiento**. |
| `Q* > 65.4` | `C_Q` cruza el cero y se hace negativo. |

El tope se calcula de los propios coeficientes —el vértice de la parábola,
`−b/2a` con a = 2.8875e−4 y b = −3.3075e−2— y no está escrito a mano:
`HI_Q_STAR_MAX = 57.27`. Pasado ese punto la función levanta `ValueError` en vez
de devolver un número sin sentido.

**Lo importante: ese límite muerde adentro del rango de viscosidad que el propio
Hydraulic Institute declara.** Sobre una bomba de tamaño BES —BEP de 5000 bpd y
25 ft por etapa— el modelo llega al tope alrededor de los **1000 cSt**, un tercio
de los 3000 cSt publicados como techo. La misma viscosidad sobre una bomba de
oleoducto (BEP 300 000 bpd, 500 ft) entra sin problema. El techo declarado
supone bombas grandes, que son con las que se levantaron los diagramas.

### 11.5 Por qué el HI no es el camino principal

El propio Takács lo desaconseja para BES, en la pág. 168:

> *Several investigations heavily criticized the Hydraulic Institute model based
> on measurements using actual ESPs with viscous liquids. Deviations were
> observed as high as 25 % in liquid rate and about 35 % in pump efficiency
> calculations. The reason (…) the viscous correction factors were developed for
> single-stage volute pumps operating at lower rotational speeds. Therefore, the
> Hydraulic Institute correlations cannot be expected to give accurate results if
> applied to ESPs.*

A eso se suman dos cosas que se ven en los números:

- **El rango de caudal validado empieza en 3400 bpd** (100 gpm). La mayoría de
  los diseños BES de este proyecto cae por debajo del piso. El módulo avisa.
- **Con agua el ajuste no vuelve a 1.0**: a 1 cSt sobre un BEP de 5000 bpd da
  `C_Q = 0.994` y `C_η = 0.951`. Ese ~5 % de sesgo en rendimiento es del ajuste,
  no del fluido. Hay un test que lo fija explícitamente
  (`test_con_agua_el_ajuste_no_vuelve_exactamente_a_uno`).

Por eso el diseño se ancla en Riling y el HI queda como verificación y como
segunda opinión.

### 11.6 La tercera fuente: Tabla 4.1 de Centrilift

Takács §4.2.3 publica además una tabla de fabricante (Centrilift) con la
**misma grilla de viscosidades** que las 4.520/4.521 de Brown — 50, 80, 100,
150, 200, 300 … 5000 SSU. Son dos escaneos independientes de la misma familia
de tablas, así que se pueden contrastar fila por fila. Está cargada en
`catalogs/viscosity_correction.json` bajo `centrilift_table`.

El contraste **no** es tranquilizador, y ese es el punto:

| SSU | C_Q Brown 60 % | C_Q Brown 70 % | C_Q Centrilift | C_H Brown 60 % | C_H Brown 70 % | C_H Centrilift |
|---:|---:|---:|---:|---:|---:|---:|
| 400 | 88.0 | 92.0 | **84.7** | 89.0 | 92.0 | **90.9** |
| 1000 | 75.0 | 83.0 | **70.8** | 78.0 | 84.0 | **83.3** |
| 3000 | 54.0 | 67.0 | **56.2** | 60.5 | 69.5 | **73.3** |

Centrilift es **más severa con el caudal** (queda por debajo de la tabla de
60 % en 15 de las 19 filas) y **más benigna con la altura** (por encima en 17 de
19, y a partir de 1500 SSU supera incluso a la de 70 %). La brecha llega a
**~13 puntos porcentuales** en el extremo viscoso.

Ese es el orden de incertidumbre real del método tabulado. Es el motivo por el
que el diseño se ancla en una sola fuente en vez de promediar: promediar
fabricaría una precisión que las fuentes no tienen.

**Anomalía anotada:** la fila de 4000 SSU publica un factor de eficiencia de
0.278, que rompe la tendencia monótona (0.218 a 3000 → 0.149 a 5000). Es un
error de imprenta; el valor coherente sería ~0.178. **Se transcribió tal como
está impreso** y la función avisa cuando la interpolación pasa por ahí. No se
corrige en silencio.

### 11.7 Verificación

| Ejemplo | Fuente | Qué se reprodujo |
|---|---|---|
| Ejemplo 4.1 | Takács pág. 157 | y = −4.276 · Q* = 23.34 · C_Q = 0.812 · C_η = 0.385 · los cuatro C_H · la curva corregida completa |
| Ejemplo 4.2 | Takács pág. 159 | 88 cSt → 402 SSU (ec. 4.14) · tabla Centrilift · BEP corregido a 762 bpd, 19.8 ft, 31.8 %, 0.34 HP |
| Turzo et al. | *OGJ*, 29-may-2000 | y = 94.7 · Q* = 2.698 · C_Q = 0.9879 · C_η = 0.9129 · C_H = 0.9898 / 0.9870 / 0.9810 / 0.9758 |

El único valor que **no** coincide con el impreso es `C_H,1.0` del Ejemplo 4.1,
por la errata de §11.3 — y ahí el ejemplo de OGJ dirime a favor del código.

### 11.8 Las dos conversiones cSt → SSU

Cada camino usa la conversión de su propia fuente:

| Camino | Fórmula | Fuente |
|---|---|---|
| Riling | dos ramas, corte en 100 SSU | ASTM D2161 |
| Hydraulic Institute | `SSU = 2.273·(cSt + √(cSt² + 158.4))` | Takács ec. 4.14 |

Difieren menos del 3 % en todo el rango de interés (a 88 cSt: 407.6 contra
402.1, un 1.4 %). Se mantienen separadas a propósito, para que cada método
reproduzca sus propios ejemplos publicados sin ajustes.

---

## 12. El lazo de realimentación: por qué cierra en una pasada

§8.4 dejaba abierto si la corrección había que iterarla. La respuesta, una vez
programada, es **no** — y el motivo vale la pena escribirlo porque no es obvio.

El temor era circular: corregir la altura cambia las etapas → cambia la potencia
→ cambia el motor → cambia el diámetro → puede cambiar la bomba. Eso sería un
lazo real **si el factor de corrección dependiera del punto de operación**.

No depende. Las tablas se titulan *«performance correction chart for pumps of
60 % (70 %) **maximum** efficiency»*: se indexan por el rendimiento **máximo de
catálogo** de la bomba, que es un dato fijo del equipo, no del punto donde
termine trabajando. Entonces:

```
C_Q, C_H, C_HP  =  f(SSU, rendimiento máximo de catálogo)     ← ambos conocidos de entrada
Q_agua = Q_pedido / C_Q                                        ← queda fijo
H_agua = TDH / C_H                                             ← queda fijo
etapas = H_agua / H_etapa(Q_agua)                              ← una sola evaluación
```

Nada de lo que se calcula después realimenta a los factores. La corrección se
resuelve en una pasada, exacta, sin criterio de convergencia ni tolerancia.

**Dónde sí quedaría un lazo:** aguas abajo, en la selección de motor. Más
potencia puede pedir un motor de mayor diámetro, y si no entra en el casing hay
que volver a elegir bomba. Ese lazo ya existía antes de la viscosidad —es el
flujo normal de `pump_selector`— y la corrección sólo cambia los números que
entran, no la estructura.

**Cuidado si alguien quiere «mejorarlo»:** usar el rendimiento del punto de
operación en vez del máximo de catálogo *sí* crearía un punto fijo, y además
sería incorrecto respecto de la definición de la tabla.

### El prefiltro también se corrige

Un detalle que se pasa por alto: `design_pump_complete()` filtra el catálogo por
rango de caudal **antes** de diseñar. Con crudo viscoso ese filtro tiene que ir
contra el equivalente en agua, no contra el caudal pedido, porque es contra el
equivalente que después se busca en la curva. Filtrar con el pedido dejaría
afuera bombas que sí sirven. Y como el equivalente depende del rendimiento de
cada bomba, se calcula **por candidata** (`_design_flow_for`).

En el caso de prueba —1500 STB/d de crudo de 16 °API a 136 °F— la lista de
candidatas pasa de 14 a 12: dos bombas dejan de cubrir el caudal equivalente de
1618 STB/d. Eso es el filtro haciendo su trabajo, no un error.

### Estado de la etapa 5

Enganchado en `design_pump_complete()` y `design_pump_by_model()`. Sobre el mismo
pozo, cambiando sólo el crudo:

| | 32 °API (liviano) | 16 °API, 150 cp medidos |
|---|---:|---:|
| Caudal pedido | 1500 STB/d | 1500 STB/d |
| Caudal contra el que se busca | 1500 | **1618** |
| TDH pedido | 3305 ft | 3514 ft |
| Altura contra la que se busca | 3305 | **3783** |
| Etapas | 156 | **187** |
| Potencia al eje | 47.5 hp | **70.0 hp** |
| Rendimiento | 73.6 % | **52.7 %** |

Viscosidad evaluada en la **admisión** (136 °F por perfil geotérmico a 5600 ft),
no en fondo de pozo: 365 SSU → C_Q = 92.7 %, C_H = 92.9 %, C_HP = 114.3 %.

### Un cruce de unidades que casi pasa desapercibido

El dominio guarda el rendimiento como **fracción** en [0, 1]
(`PumpPerformancePoint.efficiency`); las tablas 4.520/4.521 se indexan por
**porcentaje**. Pasar 0.7 donde va 70 no rompía nada: la tabla se acotaba al
extremo de 60 % y devolvía factores plausibles pero equivocados, con un aviso
fácil de ignorar («esta bomba da 0.7 %»).

Ahora `viscosity_factors()` **rechaza** cualquier rendimiento ≤ 5 % —no existe
una bomba así— y la conversión vive en un único lugar,
`_pump_max_efficiency_pct()`.

---

## 13. Fuentes

- Brown, K.E. *The Technology of Artificial Lift Methods*, Vol. 2b, §4.53112
  (procedimiento de Riling), Apéndice 4L (Figs. 4L-1 a 4L-3), Tablas 4.520 y
  4.521.
- Takács, G. (2018). *Electrical Submersible Pumps Manual*, 2.ª ed., Elsevier.
  §4.2 «Pumping Viscous Liquids», ecs. 4.1 a 4.14 y Tabla 4.1.
- Turzo, Z., Takács, G. & Zsuga, J. (2000). «Equations correct centrifugal pump
  curves for viscosity». *Oil & Gas Journal*, 29 de mayo de 2000. Presentado en
  el 47th Southwestern Petroleum Short Course, Lubbock, Texas.
- Hydraulic Institute — diagramas originales de corrección por viscosidad.
- ASTM D2161 — conversión SSU ↔ cSt.
- Beggs, H.D. & Robinson, J.R. (1975). «Estimating the Viscosity of Crude Oil
  Systems», *JPT* — **las dos** correlaciones que el proyecto ejecuta:
  crudo muerto (`pvt.oil_viscosity_dead`) y crudo vivo
  (`pvt.oil_viscosity_live`).
- Chew, J.N. & Connally, C.A. (1959). «A Viscosity Correlation for
  Gas-Saturated Crude Oils», *Trans. AIME* — es la carta que Brown reproduce en
  la Fig. 4L, y de ella sale la forma funcional μ_vivo = A · μ_muerto^B que
  Beggs-Robinson después refitea. **No está implementada**: el paso 3 lo
  resuelve Beggs-Robinson. Esta bibliografía decía lo contrario.
