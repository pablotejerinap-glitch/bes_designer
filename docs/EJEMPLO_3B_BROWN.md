# Ejemplo #3B de Brown — bomba manejando gas

Kermit Brown, *The Technology of Artificial Lift Methods*, Vol. 2b, §4.53104,
pp. 75-77. Es el ejercicio que resuelve el diseño de una bomba **cuando el gas
entra a la bomba**, y por eso no puede resolverse con un TDH único.

Implementado en `bes/core/gas_handling.py`:
`complete_gas_design()` encadena los cinco pasos y `pressure_increment_design()`
hace el bucle de incrementos.

## Por qué este ejercicio es distinto

En los ejemplos #2A y #2B el gas no entra a la bomba —en el #2A se ventea por el
anular, en el #2B no hay gas—, así que la bomba mueve líquido incompresible: el
caudal es el mismo en la admisión y en la descarga, hay un solo TDH y una sola
división.

Acá entra el 100 % del gas. **El gas se comprime a medida que sube por la bomba**,
así que el caudal cae etapa por etapa y la mezcla se va poniendo más pesada. No
existe un TDH único. El método divide el salto de presión en escalones de 200 psi
y resuelve cada uno con las propiedades locales de la mezcla.

La idea que sostiene todo el método: **una etapa siempre entrega los mismos pies
de altura, pero cuántos psi valen esos pies depende de la densidad de la mezcla
en ese punto.** Abajo, con mucho gas libre, la mezcla es liviana y una etapa
rinde poco; arriba, ya comprimida, la misma etapa rinde el doble.

## Datos de entrada

| Grupo | Parámetro | Valor |
|---|---|---|
| Pozo | Profundidad | 7000 ft |
| Pozo | Tubing | 2⅜ in. OD |
| Pozo | Casing | 5½ in. (17 #/ft) |
| Reservorio | P̄r / Pwf | 1000 / 500 psi |
| Superficie | Pwh | 200 psi |
| Producción | q | 500 b/d (100 % petróleo) |
| Producción | G/O | 500 scf/bbl |
| Fluido | °API / γg | 35 / 0.65 |
| Temperatura | Superficie / fondo | 120 / 160 °F |
| Gas | GIP | 100 % (todo el gas entra) |

## Los cinco pasos

### 1. Presión de descarga

Cuánta presión tiene que entregar la bomba para que el pozo llegue a superficie
con 200 psi en la boca. Sale de un **recorrido de presión multifásico por el
tubing**, desde el cabezal hacia abajo.

El libro lista cinco correlaciones válidas para este paso (p. 75):
Hagedorn-Brown, Orkiszewski, Duns-Ros, Beggs-Brill y **Poettmann-Carpenter**.
Usa Hagedorn-Brown y obtiene **1300 psi**.

### 2. Volumen a cada presión

Sobre la base de 1 barril de tanque:

```
V = q_o·(1−Wc)·Bo  +  q_o·Wc·Bw  +  q_o·(1−Wc)·(GOR − Rs)·GIP·Bg
    └── petróleo ──┘  └── agua ──┘  └────── gas libre ──────────┘
```

En la admisión, a 500 psi:

```
V_in = 500 × 1.08 + 500 × (500 − 80) × 1.0 × 0.00577 = 1751.7 b/d
```

### 3. Densidad de la mezcla — el paso que sostiene el método

**La masa que atraviesa la bomba es constante**; lo que cambia es el volumen que
ocupa. De ahí sale la densidad a cada presión:

```
Peso de 500 b/d de petróleo + su gas asociado = 160 900 lb/d
Si esos 1751.7 b/d fueran agua:  1751.7 × 350 = 613 095 lb/d
SG en la admisión = 160 900 / 613 095 = 0.262
```

Una mezcla de **SG 0.262**, más liviana que la nafta. Eso es lo que la bomba
mueve abajo, y explica por qué rinde tan poco ahí.

| Presión | Volumen [b/d] | SG | Gradiente [psi/ft] |
|---:|---:|---:|---:|
| 500 | 1751.7 | 0.262 | 0.113 |
| 700 | 1314.6 | 0.350 | 0.151 |
| 900 | 1068 | 0.430 | 0.186 |
| 1100 | 922 | 0.499 | 0.218 |
| 1300 | 873 | 0.527 | 0.228 |

El volumen cae a la mitad y el SG se duplica: **la bomba se vuelve más eficiente
a medida que sube**.

### 4. Etapas por incremento

Con los promedios de cada escalón:

```
psi por etapa = altura por etapa [ft] × gradiente medio [psi/ft]
etapas        = Δp / (psi por etapa)
hp            = etapas × hp/etapa (agua) × SG de la mezcla
```

| Incremento | V medio | SG medio | ft/etapa | psi/etapa | Etapas | HP |
|---|---:|---:|---:|---:|---:|---:|
| 500→700 | 1533 | 0.305 | 18.4 | 2.42 | 83 | 8.88 |
| 700→900 | 1191 | 0.389 | 23.3 | 3.93 | 51 | 6.75 |
| 900→1100 | — | — | — | — | 40 | 5.94 |
| 1100→1300 | — | — | — | — | 35 | 5.57 |
| **Total** | | | | | **209** | **27** |

**83 etapas para los primeros 200 psi contra 35 para los últimos.** Mismo salto
de presión, misma bomba, menos de la mitad de etapas. Todo por el gas.

### 5. Resultado del libro

Bomba D-40 (Reda) de **209 etapas**, **27 hp**, admisión 1751.7 b/d a 500 psi,
descarga 873 b/d a 1300 psi.

## Qué reproduce la app y qué no

Corrida completa de `complete_gas_design()`, sin pasarle ningún valor intermedio:

| | Libro | App | Dif |
|---|---:|---:|---:|
| PIP | 500 psi | 500 | exacto |
| **Presión de descarga** | **1300 psi** | **1120** | **−14 %** |
| Salto de presión | 800 psi | 620 | −22 % |
| GIP | 100 % | 100 % | exacto |
| **Etapas** | **209** | **175** | **−16 %** |
| HP | 27 | 21.7 | −20 % |

**El mecanismo está completo**: la app calcula la PIP, la presión de descarga, la
fracción de gas libre, corre los cuatro incrementos y evalúa el riesgo de bloqueo
por gas. No falta ningún paso.

### El desvío entra por un solo lugar

Todo el error viene del **paso 1**. El libro usa Hagedorn-Brown; la app
implementa **solo Poettmann-Carpenter** (ver `docs/FORMULAS.md` §3 y la sección
correspondiente de `CLAUDE.md`). P&C no considera deslizamiento entre fases, así
que la columna le sale más liviana y la presión de descarga menor: 1120 en vez de
1300 psi.

Con 620 psi de salto en vez de 800, hacen falta menos etapas. **No es un error de
implementación del método de incrementos**: alimentando la app con los 1300 psi
del libro, el resultado es 204 etapas y 26 hp —a 2.4 % y 3.7 % de los valores
impresos—, y el primer incremento da exactamente 83 etapas con SG 0.305 y
gradiente 0.132.

Poettmann-Carpenter es una de las cinco correlaciones que el propio libro habilita
para este paso, así que el procedimiento es válido; simplemente no es el que
produjo el 209 impreso. **Es el costo aceptado de haber dejado una sola
correlación**, y se documenta acá en vez de disimularlo.

## Defectos abiertos del método de incrementos

Dos, detectados al correr el ejercicio de punta a punta. Ninguno afecta el caso
del libro (donde el salto de 800 psi se divide justo en cuatro), pero sí a un
pozo real:

1. **El último escalón queda con el resto.** Los incrementos son de 200 psi
   fijos: con un salto de 620 psi quedan 500-700-900-1100 y un último escalón de
   **20 psi**. Debería repartirse parejo en vez de dejar sobra.

2. **Sin bomba fija, arma una sarta imposible.** `_select_pump_for_flow()` elige
   la bomba de cada incremento por su caudal, y devuelve combinaciones como
   `FC1600 (61 et.) + FC1200 (48) + DC1000 (67) + FC925 (5)`: cuatro modelos
   distintos apilados en una sola sarta, que no se puede construir. El libro
   elige **una sola bomba** —la D-40— y la usa en los cuatro escalones. El
   parámetro `fixed_pump_model` permite forzar ese comportamiento, pero no es el
   predeterminado.

## Ambigüedad del enunciado del #3A

El ejemplo #3A (§4.53103, p. 74), que es este mismo método aplicado a un solo
incremento, declara `q_L = 1000 b/d` con 50 % de agua, pero después multiplica el
volumen unitario **por 250**, o sea 250 STB/d de petróleo — que corresponden a
500 b/d brutos, no 1000.

Con 500 b/d brutos la app da 1010 b/d de volumen medio contra los 1017 impresos y
36 etapas contra 38. Con 1000 da exactamente el doble de volumen. **El número
auto-consistente con la aritmética del libro es 500.**
