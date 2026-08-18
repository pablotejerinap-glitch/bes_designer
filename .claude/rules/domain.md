# Reglas de dominio — BES Designer

## NO MEZCLAR FABRICANTES

Bomba, motor y sello de un mismo diseño salen **del mismo proveedor**. El cable
y los accesorios están exentos: son intercambiables entre marcas.

Se aplica en `select_motor()` y `CatalogManager.get_seal()`, ambos con el
parámetro `manufacturer`, que `pump_selector` completa con el fabricante de la
bomba (`_aparejo_manufacturer`). Si ese proveedor no tiene con qué, la bomba se
descarta: `select_top_n_pumps` la saltea y prueba la siguiente,
`select_pump_by_model` levanta `ValueError` con el motivo. **Nunca se arma un
aparejo mixto en silencio.**

Excepción única: las bombas `Brown (libro)` (I-300, I-42B, M-34) no son de un
proveedor sino los ejemplos numerados de Kermit Brown que anclan la validación.
No existe un "motor Brown", así que la regla no les aplica.

### Proveedores del proyecto

Tres, y solo tres: **REDA**, **Centrilift** y **Wood Group ESP**. Cualquier otro
fabricante se borró de los catálogos. El nombre se escribe de una sola forma por
proveedor —convivían `Reda` y `REDA`, que con la comparación exacta contaban
como distintos—.

| Proveedor | Bombas | Motores | Sellos | ¿Aparejo? |
|---|---:|---:|---:|---|
| REDA | 34 | 850 | 43 | Sí |
| Centrilift | 10 | 303 | 34 | Sí |
| Wood Group ESP | 7 | **0** | 39 | **No: sin motores** |

Wood Group no tiene catálogo de motores cargado, así que sus 7 bombas quedan sin
poder diseñarse. Se conservan a propósito; el diseño las descarta avisando el
motivo. `tests/test_catalog.py::test_aparejo_propio_por_proveedor` fija ese
estado: si aparece el catálogo de motores Wood Group, el test falla y hay que
sacarlo de la lista de incompletos.

### Límites que impone el catálogo actual

- **Cables**: el de mayor ampacidad publica 100 A. Con el derating de 1.25, la
  corriente de motor máxima diseñable es **80 A**; por encima, `select_cable`
  falla explícito. El 1/0 de mayor ampacidad era ChampionX y se fue con la purga.
- **REDA serie 375** llega a 47 hp; Centrilift en la misma serie y diámetro llega
  a 270 hp. En casing angosto, donde solo entra un motor de 3.75", una bomba REDA
  que pida más de 47 hp se queda sin motor propio.

## Crudo liviano vs. pesado: el corte está en 28 °API

**De 28 °API para arriba el crudo es liviano y NO se trata como viscoso**: se
diseña con la curva de agua sin corregir. Por debajo de 28 °API el crudo es
pesado y hay que analizar los efectos de la viscosidad (procedimiento de Riling,
Brown §4.53112).

El corte no es arbitrario. Corriendo la cadena completa —viscosidad, conversión
a SSU y factores de la Tabla 4.521— justo en el umbral:

```
28 °API a 120 °F  ->  18.8 cp  ->  102 SSU  ->  C_Q = 99.0 %,  C_H =  99.5 %
28 °API a 180 °F  ->  10.4 cp  ->   65 SSU  ->  C_Q = 99.8 %,  C_H = 100.0 %
```

La corrección vale **cerca del 1 %**: menos que el error de leer la viscosidad
de un gráfico. Por debajo empieza a morder, y a 16 °API se va a 88 %.

Estas viscosidades salen de la **Fig. 4L(2) digitalizada**. Antes salían de
Beggs-Robinson y daban 12.1 y 4.0 cp, con una corrección de ~0.4 %; la lámina
del libro es más viscosa que la correlación en todo el rango pesado. La
conclusión no cambia de orden, y el corte de 28 °API es de Riling, no una
consecuencia de esta cuenta.

Vive en `bes/core/viscosity.py` como `VISCOUS_CRUDE_API_THRESHOLD` y
`is_viscous_crude()`. El punto de entrada `evaluate_viscosity()` aplica la regla
**antes** de calcular nada: con crudo liviano devuelve factores unitarios y
`is_viscous = False`, sin tocar el PVT.

Los 28.0 exactos cuentan como **liviano** — el criterio es «de 28 para arriba».

### Dos métodos de corrección, y cuál manda

| | Riling (Brown §4.53112) | Hydraulic Institute (Takács §4.2.2) |
|---|---|---|
| Necesita saber qué bomba es | no | **sí** (el BEP) |
| Factores de altura | uno | cuatro (0.6/0.8/1.0/1.2 del BEP) |
| Rol en el proyecto | **camino principal**: filtra el catálogo | verificación de la bomba elegida |

**El diseño se ancla en Riling.** El HI queda como segunda opinión, por tres
motivos documentados en `docs/CRUDOS_VISCOSOS.md` §11.5: el propio Takács lo
desaconseja para BES (desvíos de hasta 25 % en caudal y 35 % en rendimiento
contra mediciones reales, porque los diagramas se levantaron con bombas de una
sola etapa y menos vueltas); el rango de caudal validado arranca en 3400 bpd,
por encima de la mayoría de los diseños de este proyecto; y con agua el ajuste
no vuelve a 1.0 sino a 0.95 en rendimiento.

**No promediar las fuentes.** Las tres tablas disponibles (Brown 60 %, Brown
70 %, Centrilift) difieren hasta ~13 puntos porcentuales en el extremo viscoso.
Promediarlas fabricaría una precisión que no tienen. Se elige una y se declara.

**`HI_Q_STAR_MAX = 57.27`** es un tope duro, no un aviso: pasado ese `Q*` el
ajuste de Turzo dice que más viscosidad da mejor rendimiento. Muerde adentro
del rango declarado — una bomba de tamaño BES lo alcanza cerca de 1000 cSt, no
de los 3000 cSt publicados.

**Erratas del impreso ya resueltas** (no «arreglar» de vuelta): el ejemplo de la
pág. 157 de Takács calcula `C_H,1.0` con el signo cambiado, y la ec. 4.12 anota
el rendimiento en % cuando va en fracción. Las dos verificadas contra el paper
original de Turzo en OGJ.

## Umbrales de gas libre en la admisión

**Hay DOS magnitudes y la bibliografía las mezcla. No son intercambiables:**

```
fracción  f = V_gas / (V_gas + V_líquido)      f = r / (1 + r)
relación  r = V_gas / V_líquido                r = f / (1 − f)
```

Una relación de 1.0 es una fracción de **0.50**, no de 1.0. Confundirlas corre
los umbrales a la mitad. `free_gas_fraction_at_intake()` devuelve **fracción**;
`gas_handling.py` convierte con `fraction_to_ratio()` donde el criterio del
libro está en relación.

| Magnitud | Umbral | Qué implica |
|---|---|---|
| Fracción | ≤ 1 % | Gas despreciable: vale el diseño monofásico con gradiente constante |
| Fracción | > 1 % | **Obligatorio** calcular la pérdida de carga con modelo multifásico |
| Fracción | > 5 % | **Obligatorio** separador o manejador de gas en el aparejo |
| Fracción | > 10 % **en la bomba** | La BES **no converge**: evaluar otro método de levantamiento |
| Relación | > 0.1 | La bomba entrega menos altura que su curva de agua (f > 0.0909) |
| Relación | ≥ 1.0 | Bloqueo total por gas: deja de bombear líquido (f ≥ 0.50) |

**Los dos 0.10 NO son el mismo criterio.** `GAS_FRACTION_PUMP_LIMIT` (fracción,
lo que entra a la bomba tras venteo y separador) y `GAS_RATIO_DEGRADATION_START`
(relación, donde la bomba empieza a perder altura) valen los dos 0.10 y
significan cosas distintas: la relación 0.10 equivale a una fracción de 9.09 %.
`tests/test_gas_separator.py::TestLosDosDiezPorCiento` lo fija.

### Separador de gas: se escala la RELACIÓN, no la fracción

Un separador que retira el 75 % del gas libre **no** deja `f × 0.25`. Saca gas y
deja el líquido, así que lo proporcional es la relación::

    r = f/(1−f)  →  r' = r·(1−η)  →  f' = r'/(1+r')

El error de la cuenta ingenua crece con el gas: con f = 65 % y η = 75 %, lo
correcto da **31.6 %** y lo ingenuo **16.2 %** — casi el doble, y la diferencia
entre rechazar un pozo y aceptarlo. Vive en `gas_handling.separator_outlet_fraction()`.

Con un separador del 75 %, el límite del 10 % en la bomba tolera hasta **30.8 %**
de gas libre en la admisión. La eficiencia sale del catálogo
(`select_gas_handler`: rotary 90 %, vórtex 97 %); si el modelo no la publica se
supone `SEPARATOR_DEFAULT_EFFICIENCY = 0.75` y **se declara en el veredicto**.

`DesignObjectives.max_gip` (default 0.10) es el umbral, y **ahora sí se aplica**:
`evaluate_gas_feasibility()` corre antes de diseñar y el diseño **falla** con el
veredicto, no advierte. Ojo con los casos guardados de antes: traían `max_gip`
0.7 —el campo existía sin usarse— y con ese valor la verificación no filtra nada.

**Pendiente:** `catalogs/gas_handlers.json` tiene los 12 manejadores de
**ChampionX**, fabricante que la purga de catálogos eliminó del resto del
proyecto. El veredicto de viabilidad depende de esa eficiencia (97 % del vórtex),
así que conviene resolverlo antes de citar resultados en la tesis.

Fuente: Brown Vol. 2b §4.53102 y Takács, *Electrical Submersible Pumps Manual*.
Las constantes viven en `bes/core/gas_handling.py`
(`GAS_FRACTION_NEGLIGIBLE`, `GAS_FRACTION_SEPARATOR_REQUIRED`,
`GAS_RATIO_DEGRADATION_START`, `GAS_RATIO_GAS_LOCK`).

### El umbral lo decide la física, no el usuario

**`gas_fraction_pc_threshold` NO se pide por pantalla ni por la API.** El
programa evalúa la fracción de gas libre en la admisión y elige solo la
correlación de fricción: por encima del 1 %, Poettmann-Carpenter.

Vale **0.01** por defecto en `DesignObjectives`. Queda como parámetro
únicamente para **reproducir los ejemplos impresos** de Brown, que se resuelven
a mano como monofásicos y lo fijan en 1.0. Sólo los tests lo tocan.

El default tiene que coincidir con `gas_handling.GAS_FRACTION_NEGLIGIBLE`; no
se importa de ahí porque `gas_handling` importa `models` y sería circular.
`tests/test_gas_handling.py::TestUmbralAutomaticoDePoettmannCarpenter` verifica
que no se desincronicen y que la API no vuelva a exponerlo.

**Historia, para que no se repita:** el umbral estuvo cargado en tres lugares
con dos valores distintos —el dominio en 0.01, y tanto el schema de la API como
el formulario React en 0.10—. Como el front manda el suyo en cada request, la
app corría con el 10 % viejo: pozos con hasta 10 % de gas libre se diseñaban
como monofásicos, subestimando la fricción ~17 ft en un pozo de 5600 ft.
**No volver a exponerlo.**

## IPR — Vogel es COMPUESTO, no Vogel puro

**Arriba de la presión de burbuja la IPR es una RECTA.** Con Pwf > Pb el flujo
en el reservorio es monofásico y vale Darcy; recién debajo de Pb se libera gas,
el flujo se hace bifásico y la curva se dobla.

```
Pwf >= Pb :  q = J · (Pr − Pwf)
Pwf <  Pb :  q = J·(Pr − Pb) + (J·Pb/1.8)·[1 − 0.2·(Pwf/Pb) − 0.8·(Pwf/Pb)²]
AOF       =  J·(Pr − Pb) + J·Pb/1.8
```

Los dos tramos **empalman con la misma pendiente** en Pb: la curva no tiene
quiebre. Con el reservorio **saturado** (Pb >= Pr) la fórmula se reduce sola a
Vogel puro con `q_max = J·Pr/1.8` — no hace falta un caso aparte, y para eso
está `effective_bubble_point()`.

El **J se despeja del ensayo en dos casos** (Beggs §2): si la Pwf del ensayo
quedó sobre Pb, sale directo de la recta; si quedó debajo, hay que invertir la
ecuación compuesta. Es `vogel_j_from_test()`.

**Historia, para que no se repita:** `ipr.py` no mencionaba `bubble_point` ni
una vez. Aplicaba Vogel puro desde Pr en todo el rango, así que la IPR salía
curva también arriba de la burbuja. En un pozo subsaturado típico
(Pr 4500 / Pb 2900, ensayo 1200 STB/d a 2200 psi) eso daba **J = 0.6751 en vez
de 0.5393: un 25 % de más**, y ponía el punto de burbuja en 909 STB/d en vez de
863. Fijado en `tests/test_ipr.py::TestProductivityIndexFromTest`.

### Los otros dos métodos: verificados, no tocados

- **Lineal** — la recta de Darcy es correcta como fórmula; es lo que el usuario
  pide al elegirla. Lo que faltaba era **avisar** cuando la Pwf de diseño cae
  bajo Pb, donde deja de valer (Beggs reporta errores de 70-80 % a Pwf baja).
  Lo hace `ipr_validity_warning()`. **No convertirla en compuesta**: dejaría de
  ser el método lineal.
- **Fetkovich** — **no lleva corte por presión de burbuja, y está bien así.**
  Beggs ec. 2-58 integra Darcy sobre las dos regiones de un reservorio
  subsaturado y concluye que «Fetkovich then stated that the composite effect
  results in an equation of the form q = C(Pr² − Pwf²)^n»: el ajuste de C y n ya
  absorbe el comportamiento bifásico. Agregarle un tramo recto sería un error.
  Verificado contra el Ejemplo 2-7A del Beggs, punto por punto.

## Regla de oro (validación contra el libro)

Toda correlación o cálculo nuevo del dominio se **valida contra un ejemplo
numerado del libro de Kermit Brown** (*The Technology of Artificial Lift
Methods*, Vol. 2b, Cap. 4.5) y se agrega un test. La disciplina de los **545
tests verdes** es el activo más valioso del proyecto — no romperla.

Ejemplos de referencia usados como tests de regresión:

| Ejemplo | Bomba | Caudal (bpd) | TDH (ft) | Etapas | HP |
|---|---|---|---|---|---|
| #1A | Centrilift I-300 | 10 000 | 1 670 | 28 | 180 |
| #2A | Reda D-40 | 1 227 | 5 830 | 254 | ≈79 |
| #2B | Centrilift I-42B | ~2 080 | 4 258 | 112 | ≈65 |

Datos en `data/example_wells.json`; tests en `tests/`.

## Convención de unidades

| Magnitud | Unidad |
|---|---|
| Presión | psia (diferenciales en psi) |
| Temperatura | °F |
| Caudal | STB/d (superficie) o bpd |
| Profundidad / longitud | ft TVD o ft MD |
| Diámetros | pulgadas |
| Potencia | hp |
| Voltaje / corriente | V / A |

`hp/stage` del catálogo está calibrado para agua (SG = 1.0); multiplicar por
`sg_fluid` para el HP real.

## Glosario ESP/BES (para quien no es de petróleo)

- **BES / ESP**: Bombeo Electrosumergible / Electric Submersible Pump.
- **IPR** (Inflow Performance Relationship): capacidad de aporte del reservorio
  (caudal vs. presión de fondo). Métodos: Vogel, Linear, Fetkovich.
- **PVT**: propiedades del fluido (Bo, Rs, Pb, viscosidad, z-factor) según presión/temp.
- **Pwf**: presión de fondo fluyente en las perforaciones.
- **PIP** (Pump Intake Pressure): presión en la admisión de la bomba.
- **TDH** (Total Dynamic Head): altura total que debe desarrollar la bomba =
  Vertical Lift + Fricción de tubería + Head de presión en superficie.
- **BEP** (Best Efficiency Point): caudal de máxima eficiencia de la bomba.
- **GIP / GIP fraction**: fracción de gas libre en la admisión de la bomba.
- **VSD/VFD**: variador de frecuencia.
- **Stage (etapa)**: cada impulsor+difusor de la bomba; se apilan para dar TDH.

## Fórmula de TDH (Brown §4.5324)

```
TDH = Vertical Lift + Fricción de tubería + Head de presión en superficie
Vertical Lift  = pump_depth − (PIP × 2.31 / SG_liquid)
Fricción       = Hazen-Williams  ó  Poettmann-Carpenter (ver abajo)
Head Pwh       = Pwh × 2.31 / SG_liquid
```

La fricción depende de la **fracción de gas libre en la admisión**, que se
evalúa antes del TDH: por debajo de `objectives.gas_fraction_pc_threshold`
(default 0.10) se usa Hazen-Williams; por encima, el término de fricción de
Poettmann-Carpenter. Nunca sumar el término de gravedad de P&C al TDH: la
elevación vertical ya representa la columna.
