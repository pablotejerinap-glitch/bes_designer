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

### En la app SÓLO hay bombas de catálogo real

Las tres del libro se **retiraron del catálogo de la aplicación** (ago-2026):
no salen de un catálogo de fabricante, y la app publica únicamente curvas
digitalizadas de catálogos reales. `bes/catalogs/pumps.json` pasó de 74 a 71
bombas — REDA 54, Centrilift 7, Wood Group ESP 7 (ver la tabla de abajo).

**Los datos impresos NO se perdieron**: viven en
`backend/tests/data/brown_pumps.json` y los inyecta
`tests.brown_pumps.catalogo_con_bombas_del_libro()`, que es lo que usan los
tests de validación contra el libro. La regla de oro sigue en pie; lo que
cambió es que un usuario de la app ya no puede elegir una bomba que no existe
en ningún catálogo.

`tests/test_catalog.py::test_la_app_solo_ofrece_bombas_de_catalogo_real` falla
si alguna vuelve. **No volver a agregarlas.**

### Proveedores del proyecto

Tres, y solo tres: **REDA**, **Centrilift** y **Wood Group ESP**. Cualquier otro
fabricante se borró de los catálogos. El nombre se escribe de una sola forma por
proveedor —convivían `Reda` y `REDA`, que con la comparación exacta contaban
como distintos—.

| Proveedor | Bombas | Motores | Sellos | Cables | ¿Aparejo? |
|---|---:|---:|---:|---:|---|
| REDA | 54 | 850 | 43 | 9 | Sí |
| Centrilift | 10 | 303 | 34 | 6 | Sí |
| Wood Group ESP | 7 | **0** | 39 | 25 | **No: sin motores** |

Los equipos que no son del aparejo —manejadores de gas, accionamientos de
superficie y sensores de fondo— **son todos de REDA** desde agosto de 2026: 12
manejadores, 126 accionamientos (19 FixStar + 107 SpeedStar) y 5 sensores
Phoenix. Antes eran de ChampionX, y eran el último reducto de ese proveedor en
el proyecto. Los 2 tableros de Wood Group se conservan. Ver
`docs/AUDITORIA_CATALOGO_REDA.md`.

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

**La conversión a SSU es una sola**: la ec. 4.14 de Takács (2018, pág. 159),
`SSU = 2.273·(ν + sqrt(ν² + 158.4))`, para los dos caminos. Es la puerta a las
Tablas 4.520/4.521, que se indexan por SSU. Salió ASTM D2161, que se usaba sólo
en el camino de Riling y difería hasta 2 % de la otra.

**Y las correcciones de la bomba salen sólo de esas tablas**: caudal, altura,
rendimiento y potencia. No se mezclan con el Hydraulic Institute.

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
(`select_gas_handler`), pero **hoy ningún equipo la publica**: REDA no la
declara para ninguno de sus separadores, así que en la práctica siempre se
aplica `SEPARATOR_DEFAULT_EFFICIENCY = 0.75` y **se declara en el veredicto**.
Los 90 % / 97 % que aparecían acá eran de ChampionX y se fueron con la purga
(ver más abajo, «Resuelto (ago-2026)»).

`DesignObjectives.max_gip` (default 0.10) es el umbral, y **ahora sí se aplica**:
`evaluate_gas_feasibility()` corre antes de diseñar y el diseño **falla** con el
veredicto, no advierte. Ojo con los casos guardados de antes: traían `max_gip`
0.7 —el campo existía sin usarse— y con ese valor la verificación no filtra nada.

### El separador consume potencia, y el consumo lo publica el catálogo

El separador de fondo va montado **en el mismo eje**, entre el sello y la
bomba, así que su consumo lo mueve el mismo motor y se le suma al HP de la
bomba **antes** de elegir el motor.

**El número sale del modelo elegido, no de una constante.** REDA lo publica a
60 Hz, equipo por equipo (`gas_handlers.json`, campo `hp`):

| Equipo | hp @ 60 Hz | Rango (mezcla, B/D) |
|---|---:|---|
| VGSA D20-60 (vórtex) | 3 | 2 000 – 6 000 |
| VGSA S20-90 (vórtex) | 6 | 2 000 – 9 000 |
| VGSA S70-150 (vórtex) | 14 | 2 000 – 15 000 |
| AGH D5-21 … H100-250 | 13 … 102 | 500 – 25 000 |

Se consulta por `gas_handling.gas_handler_hp()`, **nunca** leyendo la constante
suelta. `GAS_SEPARATOR_HP = 2.0` quedó como **respaldo** para los modelos que el
fabricante no publica —los rotativos ARS, CRS-ES y DRS-ES—.

- **Antes, no después.** Si el motor se eligiera sobre el HP de la bomba sola,
  quedaría corto justo en los pozos con gas, que son los que menos margen
  tienen. Por eso `_assemble_design()` elige el manejador de gas **antes** de
  llamar a `electrical_design_complete()`.
- **No se esconden.** Viajan en `DesignResult.gas_handler_hp`, aparte de
  `total_pump_hp` y de `motor_hp_max`, que siguen siendo la bomba sola — si se
  mezclaran, la cuenta de etapas × hp/etapa dejaría de reproducirse contra el
  libro. El PDF, el Excel y la tabla de resultados lo publican.
- **Con dos equipos en el eje se suman los dos**, cada uno con su hp. Antes se
  hacía `2 hp × cantidad`, que con consumos distintos por modelo ya no vale;
  por eso `gas_handler_count` viaja como dato propio en vez de despejarse
  dividiendo.

### El rango del separador es de MEZCLA, no de líquido

REDA declara el rango así: *«total liquid and gas operating range, B/D at
60 Hz»* (ESP Catalog, pág. 392). Por el equipo pasa la mezcla entera, así que
hay que consultarlo con el caudal total (`gas_handling.total_intake_rate`):

```
q_total = q_líquido / (1 − f_gas)
```

No es un detalle: 1 227 bpd de líquido con 63 % de gas libre son **3 316 bpd**
de mezcla. El primero cae fuera del rango 2 000–6 000 del VGSA D20-60 y el
segundo entra cómodo — la diferencia entre poder diseñar el pozo y declararlo
inviable. El caudal de líquido que se usa es el de superficie (convención del
resto del selector), así que el total resultante es una cota inferior.

### La escalera de manejo de gas, y cuándo cambiar de método

El aparejo sube por cuatro escalones y **se queda en el primero que alcanza**,
para no instalar equipo de más (`select_gas_handling_strategy`):

```
f_admisión → venteo → ¿alcanza sin separador?     → "ninguno"
                    → ¿alcanza con uno?           → "simple"
                    → ¿alcanza con el tándem?     → "tandem"
                    → ¿lo tolera un manejador?    → "agh"
                    → NO → CAMBIAR DE MÉTODO DE LEVANTAMIENTO
```

**Los tres primeros bajan el gas; el cuarto sube la tolerancia.** Un separador
retira gas y por lo tanto reduce `f_pump`. El **manejador avanzado (AGH)** no
retira nada: acondiciona la mezcla para que la bomba pueda impulsarla con el gas
adentro, hasta la fracción de vacío que publica el fabricante — REDA declara
**45 % de GVF** (ESP Catalog, pág. 393). Por eso su escalón se compara contra
`agh_max_gvf` y no contra `max_gip`, y por eso se apila **sobre** la separación
ya conseguida: *«can also be installed in series above rotary or vortex-type gas
separators»* (misma página).

Consecuencia que hay que leer bien: un pozo puede salir **viable con 30 % de gas
libre en la bomba**. No es que se haya separado hasta ahí — es que el equipo lo
tolera. La advertencia lo dice y el deterioro de altura por gas **no**
desaparece: la curva se sigue leyendo con el caudal de mezcla.

**El AGH no puede pasar por encima de un `max_gip` más estricto.** Si el usuario
lo bajó por debajo de `GAS_FRACTION_PUMP_LIMIT` (0.10) está declarando un
requisito deliberado, y un equipo de catálogo no lo anula. Al revés sí: partiendo
de la tolerancia estándar, el manejador la extiende hasta su GVF publicado.

**El último escalón es el que importa.** Si ni con el manejador encima del
tándem el gas queda por debajo de lo que el equipo tolera, no hay equipo que lo
resuelva (Takács, Fig. 4.25, pág. 195) y corresponde evaluar bombeo de cavidad
progresiva, gas lift o pistón. Se publica en `DesignResult.switch_lift_method`.

**El tándem se arma con tipos DISTINTOS de separador**, no con dos iguales
apilados: *«a tandem RGS, composed of different types of separators»* (Takács
pág. 195). Cada tipo rinde mejor en un rango distinto de fracción de vacío. El
código elige el segundo del tipo opuesto al primero (`_estrategia_de_gas`).

**En serie se multiplica lo que PASA, no lo que se retira:**

```
η_total = 1 − Π (1 − ηᵢ)
```

Un rotativo de 90 % seguido de un vórtex de 97 % retira **99.7 %**, no el 93.5 %
de promediarlos. Y la reducción se aplica sobre la **relación**, no sobre la
fracción — la regla de arriba vale igual para el tándem.

**Con el catálogo actual el escalón de tándem es inalcanzable, y está bien que
lo sea.** Los únicos separadores REDA seleccionables son de vórtice: los
rotativos ARS / CRS-ES / DRS-ES figuran sólo en las tablas de armado (págs.
395-396), que publican longitud, peso y número de parte pero **no el rango de
caudal**, así que no se pueden verificar contra un pozo y el selector no los
ofrece. Sin dos tipos distintos no hay tándem. La lógica está implementada y
verificada por unidad en `tests/test_gas_separator.py`; se activará sola el día
que aparezca la hoja de datos de un rotativo. **No inventarle un rango.**

**Dos decisiones distintas que no comparten el corte, y no se pueden mezclar:**

| Decisión | Quién la toma | Corte |
|---|---|---|
| ¿Se instala un separador? | `_select_gas_handler` | `gip > 0.10` (heredado) |
| ¿Hace falta un segundo? | la escalera | `objectives.max_gip` |

Un separador instalado consume potencia aunque la escalera diga que no hacía
falta: está en el eje igual. Por eso el conteo tiene piso 1 cuando hay equipo.

### El separador consume según la frecuencia

El manejador va en el mismo eje que la bomba, así que gira a su velocidad y su
consumo escala **con el cubo de la frecuencia** (Takács ec. 4.31):

```
BHP = BHP_base · (f / f_base)³
```

El `hp` de catálogo se entiende publicado a **60 Hz** (campo `hp_frequency_hz`), y `GAS_SEPARATOR_HP = 2.0` también
(`GAS_SEPARATOR_BASE_FREQUENCY_HZ`, supuesto declarado). A 50 Hz son 1.16 hp, no
2. Sin esto quedaba incoherente: la curva de la bomba **sí** se escalaba por
frecuencia (`pump_at_frequency`) y el separador no.

### La eficiencia que usa el modelo es una COTA INFERIOR del gas remanente

El código toma la eficiencia **máxima** de catálogo como si fuera siempre
alcanzable. Takács (Fig. 4.19) muestra que cae al subir el caudal de líquido, y
que pasado un caudal límite **se desploma a cero** porque el inductor deja de
vencer la caída de presión en los puertos de descarga. Además, sólo hay
evidencia publicada de desempeño ideal hasta una **relación** gas/líquido *in
situ* de 0.6 (`RGS_DOCUMENTED_RATIO_LIMIT`, Takács pág. 186). Las dos cosas se
avisan; no se modelan, porque no hay datos para hacerlo sin inventar.

**Dos umbrales de separador que no coinciden.** El aparejo incorpora manejador
de gas recién con **10 %** de gas libre en la admisión
(`pump_selector._GIP_PARA_SEPARADOR`), pero el veredicto de viabilidad lo pide
desde el **5 %** (`GAS_FRACTION_SEPARATOR_REQUIRED`). Entre 5 % y 10 % el
diseño dice que hace falta separador y el aparejo no lo trae. Es una
discrepancia heredada, documentada y **no corregida**: mover el corte cambiaría
el motor de todos los pozos de esa franja.

**Resuelto (ago-2026): el catálogo de manejadores de gas es REDA.** Los 12
equipos de **ChampionX** —fabricante que la purga eliminó del resto del
proyecto— se reemplazaron por los 12 de REDA, digitalizados del *REDA ESP
Catalog* (págs. 391-399): 3 separadores de vórtice, 3 rotativos y 6 AGH.

**Y REDA no publica la eficiencia de separación de ninguno.** Se buscó en las
págs. 390-399 completas: lo único cuantitativo es la capacidad de GVF del AGH
(45 %) y una comparación cualitativa del vórtice contra el rotativo. Por eso
`max_efficiency` es **`null` en todas las entradas** y no un número estimado —
los 0.90 / 0.97 de ChampionX no se trasladaron, eran de otro fabricante y de
otro diseño de equipo. Consecuencia asumida:

- El dominio aplica `SEPARATOR_DEFAULT_EFFICIENCY = 0.75` y **lo declara en el
  veredicto**. Es lo honesto, pero es más conservador que antes: un pozo que
  con el 97 % de ChampionX quedaba en 4.9 % de gas en la bomba, con el 75 %
  queda en 30 % y necesita subir al escalón del AGH.
- Los catálogos de Centrilift (Baker 2019) y Wood Group **tampoco** publican
  eficiencia, consumo ni rango de caudal de sus separadores: sólo longitud,
  peso y número de parte. REDA es el único de los tres proveedores del proyecto
  con datos suficientes para seleccionar un manejador de gas.
- Si aparece una hoja de datos con la eficiencia medida, se carga ahí y el
  modelo la usa sin tocar código. **Hasta entonces, nada de estimar.**

Fuente: Brown Vol. 2b §4.53102 y Takács, *Electrical Submersible Pumps Manual*.
Las constantes viven en `bes/core/gas_handling.py`
(`GAS_FRACTION_NEGLIGIBLE`, `GAS_FRACTION_SEPARATOR_REQUIRED`,
`GAS_RATIO_DEGRADATION_START`, `GAS_RATIO_GAS_LOCK`).

### El MÉTODO lo elige el usuario; el UMBRAL lo decide la física

Son dos cosas distintas y sólo una es del usuario.

**El método sí se elige** (`DesignObjectives.pressure_loss_method`, selector
«Cálculo de pérdidas de carga en tubería»): `"poettmann_carpenter"`,
`"hazen_williams"` o vacío. **Vacío es el default y significa «que lo decida la
física»**, que es el comportamiento histórico. Si la elección contradice a la
física, se respeta la elección y **se avisa** — corregirla en silencio
escondería que el resultado no es el que la física pide.

**`gas_fraction_pc_threshold` NO se pide por pantalla ni por la API.** Es el
corte con que el programa elige solo cuando el usuario no eligió: por encima del
1 % de gas libre en la admisión, Poettmann-Carpenter.

Vale **0.01** por defecto en `DesignObjectives`. Queda como parámetro
únicamente para **reproducir los ejemplos impresos** de Brown, que se resuelven
a mano como monofásicos y lo fijan en 1.0. Sólo los tests lo tocan.

El default tiene que coincidir con `gas_handling.GAS_FRACTION_NEGLIGIBLE`; no
se importa de ahí porque `gas_handling` importa `models` y sería circular.
`tests/test_gas_handling.py::TestUmbralAutomaticoDePoettmannCarpenter` verifica
que no se desincronicen y que la API no vuelva a exponerlo.

### Envelope de Poettmann & Carpenter

Las hipótesis del método —un único fluido homogéneo, factor de pérdida de carga
constante, flujo turbulento en toda la cañería, aceleración despreciable,
hold-up y resbalamiento absorbidos en el factor de fricción, efectos viscosos
despreciados— acotan dónde vale:

| Límite | Valor | Qué pasa si no se cumple |
|---|---|---|
| Tubería | 2, 2½ y 3 pulg (OD 2 3/8, 2 7/8, 3 1/2) | **Restricción dura** |
| Viscosidad | < 5 cp — petróleos livianos | Aviso |
| RGL | < 1500 scf/bbl | Aviso |
| Caudal | > 400 bbl/d | Aviso |

`RGL = GOR / (1 + WOR)`, **no** el GOR pelado: el GOR se mide por barril de
petróleo y el límite está declarado por barril de líquido. Con corte de agua no
son lo mismo y comparar el GOR daría un veredicto equivocado.

El límite del tubing es duro sólo cuando el método **se eligió a mano**: el
formulario no ofrece otra cañería y la API devuelve 422. Cuando la correlación
la elige la física, los cuatro límites avisan y ninguno frena — si no, un pozo
que hoy se diseña solo dejaría de poder diseñarse.

Vive en `bes/core/multiphase.py` (`poettmann_carpenter_applicability()`,
`gas_liquid_ratio()`), con las constantes declaradas ahí mismo.

**Fuente: apuntes de cátedra aportados por Pablo (agosto 2026).** No agregar
límites de otra procedencia sin que él los verifique.

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

La fricción la elige el usuario con `objectives.pressure_loss_method`. Si no
eligió, la decide la **fracción de gas libre en la admisión**, evaluada antes
del TDH: por debajo de `objectives.gas_fraction_pc_threshold` (default 0.01) se
usa Hazen-Williams; por encima, el término de fricción de Poettmann-Carpenter. Nunca sumar el término de gravedad de P&C al TDH: la
elevación vertical ya representa la columna.
