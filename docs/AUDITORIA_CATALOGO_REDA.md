# Auditoría del catálogo REDA — qué está digitalizado y qué el fabricante no publica

**Fuente única:** `REDA_ESP_Catalog.pdf` (Schlumberger, 2005), 549 páginas, en
`TESIS/CATALOGOS/REDA-SLB/`. Agosto de 2026.

Este documento responde una pregunta concreta: *de todo lo que hace falta para
diseñar una BES, ¿qué está cargado, qué falta por digitalizar y qué **no se
puede** cargar porque REDA no lo publica?* La tercera categoría es la
importante: son los lugares donde el modelo se apoya en un supuesto, y todos
están declarados en el `_source` del catálogo correspondiente.

Regla que gobierna todo lo de abajo: **si el fabricante no publica el dato, el
campo va en `null`.** Nunca un valor estimado. Un `null` deja la verificación
«sin realizar» y avisa; un número inventado la da por aprobada.

---

## 1. Estado por familia de equipo

| Equipo | Cargados | Estado |
|---|---:|---|
| Bombas | 54 | Curvas digitalizadas de la capa vectorial. 4 sin cargar, con causa documentada. |
| Motores | 850 | Completos salvo `max_temp_f` — ver §3. |
| Sellos / protectores | 43 | Sin empuje ni temperatura — ver §3. |
| Cables | 9 | Ampacidad plana de Brown/API. Curvas propias de REDA digitalizadas aparte — ver §2. |
| Manejadores de gas | 12 | 3 vórtice, 3 rotativos, 6 AGH. Sin eficiencia de separación — ver §3. |
| Accionamientos de superficie | 126 | 19 FixStar (tablero fijo) + 107 SpeedStar (VSD). |
| Sensores de fondo | 5 | Phoenix Select ESP y CTS, MultiSensor XT Tipo 0/1 y slimline. |
| Elastómeros | 5 | Tabla completa de la pág. 404. Todavía no se aplica — ver §3. |

---

## 2. Digitalizado en esta pasada

### Manejadores de gas (págs. 391-399) → `gas_handlers.json`

Reemplaza a los 12 equipos de **ChampionX**, fabricante que la purga de
proveedores había eliminado del resto del proyecto y que sobrevivía solamente
acá. Se cargaron los 3 separadores de vórtice y los 6 AGH con su consumo
publicado por modelo (3 a 102 hp a 60 Hz), su OD, longitud, peso y rango de
caudal, más los 3 rotativos con lo poco que el catálogo publica de ellos.

Tres consecuencias que cambiaron el comportamiento del diseño:

1. El consumo del manejo de gas ya **no es una constante de 2 hp**: sale del
   modelo elegido.
2. El rango de caudal del separador es de **mezcla** (líquido + gas), no de
   líquido. Consultarlo con el líquido pelado descartaba equipos que sí
   califican.
3. El **AGH** entró como cuarto escalón de la escalera de manejo de gas. No
   separa: tolera hasta 45 % de GVF. Es la única respuesta del catálogo por
   debajo de 2 000 bpd, donde no entra ningún separador de vórtice.

### Curvas de ampacidad de los cables (págs. 473-488) → `cable_ampacity.json`

8 gráficos «Maximum conductor current, A» vs. «Maximum well temperature, °F»,
de las familias Redalene, Redahot, Redablack, Redalead y de las extensiones de
cable de motor. 6 calibres cada uno (**2/0, 1/0, 1, 2, 4 y 6 AWG**), 21 puntos
por curva.

Leídos de la capa vectorial, sin OCR: las curvas están trazadas en blanco sobre
el fondo del gráfico y los ejes se calibran por regresión sobre las líneas de
grilla. **R² = 1.000000 en los 16 ejes**, 0 problemas en los controles de
plausibilidad (monotonía, no cruce entre calibres, cierre en 0 A).

Un detalle que costó encontrar y que conviene no volver a pisar: los rótulos de
marca están impresos **2.7 pt por encima** de su línea de grilla. Calibrar
contra el centro del rótulo metía un sesgo constante que daba −7 A donde el
gráfico muestra 0. La calibración se ancla en la grilla; los rótulos sólo dicen
cuánto vale cada línea.

**Todavía no se usa.** `get_cable()` sigue eligiendo con el `max_amps` plano,
por dos motivos: engancharlo cambia el cable —y con él la caída de tensión y el
transformador— de todos los pozos, y falta resolver la ambigüedad de §4.

Para dimensionar lo que está en juego: el #1 AWG Redalene del catálogo actual
publica **100 A planos**; la curva de REDA da **172 A a 0 °F y 74 A a 150 °F**.
El valor plano equivale a leer la curva cerca de 125 °F, así que en cualquier
pozo más caliente que eso el valor que se está usando es **optimista**, que es
el lado peligroso.

### Accionamientos de superficie (págs. 509-531) → `controllers.json`

126 equipos: **19 FixStar** (velocidad fija, 600 a 5 000 V, 45 a 200 A) y
**107 SpeedStar** (variadores: SWD, 2000 Plus, Titan y MVD, de 66 a 2 000 hp).
Antes el catálogo tenía **2** tableros, los dos de Wood Group, que se conservan.

Dos cosas que hubo que resolver:

- **Los kVA sólo vienen impresos en el SpeedStar MVD.** En el resto se calculan
  con `kVA = √3·V·A/1000`, que es la definición de potencia aparente trifásica
  y no una estimación, con la tensión que declara el propio encabezado de la
  tabla («Rating at 480 V, 60 Hz»). Las 10 filas del MVD son el control
  cruzado: sus kVA impresos cierran con esa identidad dentro del 0.1 %, lo que
  valida el método donde no hay con qué contrastar.
- **Un mismo SpeedStar aparece con varios gabinetes** (NEMA 1 / 3R), números de
  pulsos (6 / 12) y temperaturas ambiente (104 / 122 °F), y la corriente
  admisible cambia entre ellos. Son equipos distintos, no repeticiones: el
  nombre de modelo lleva esa etiqueta y los campos `enclosure`, `pulses` y
  `ambient_temp_f` la publican por separado. Leer la página como una sola tabla
  los colapsaba y perdía la mitad.

### Sensores de fondo (págs. 54-61) → `sensors.json`

5 familias Phoenix, con presión, temperatura, temperatura de devanado,
vibración y fuga de corriente donde el catálogo las publica. Reemplazan a los
4 sensores **ACE Downhole**, que habían entrado con la ingesta de ChampionX y
eran —junto con los manejadores de gas— el último reducto de ese proveedor.

Se carga **una entrada por familia, no una por número de parte**: los part
numbers de las págs. 55-58 distinguen elastómero (Viton / Aflas) y serie de
acople, no capacidad de medición. Cuarenta filas con los mismos rangos darían
una falsa sensación de detalle.

Consecuencia asumida: **el gauge REDA más caliente llega a 302 °F**, contra los
350 °F del «ACE Xtreme Temperature» que se fue. Un pozo por encima de eso se
queda sin sensor recomendado — y el diseño sale igual, porque el monitoreo no
participa del dimensionamiento. Fijado en
`tests/test_catalog.py::TestSensorSelection`.

### Guía de elastómeros (pág. 404) → `elastomers.json`

Los cinco compuestos con su límite de temperatura (250 a 399 °F) y su
resistencia a agua/aceite, H₂S, aminas, químicos polares y CO₂.

---

## 3. Lo que REDA NO publica

Esta sección es el resultado de buscar, no de no haber buscado.

### Eficiencia de separación de los manejadores de gas

Se revisaron las págs. 390-399 completas. Lo único cuantitativo es la capacidad
de GVF del AGH (**45 %**) y una comparación cualitativa del vórtice contra el
rotativo (*«extended range and greater efficiency»*, pág. 391).

`max_efficiency` queda en `null` en las 12 entradas y el dominio aplica
`SEPARATOR_DEFAULT_EFFICIENCY = 0.75` **declarándolo en el veredicto**. Los
0.90 / 0.97 que traía el catálogo de ChampionX no se trasladaron: eran de otro
fabricante y de otro diseño de equipo.

Se verificó que **tampoco lo publican Centrilift (Baker 2019) ni Wood Group**:
sus tablas de separadores dan longitud, peso y número de parte, nada más. REDA
es el único de los tres proveedores del proyecto con datos suficientes para
seleccionar un manejador de gas, y ni siquiera él publica la eficiencia.

### Rango de caudal de los separadores rotativos

Los ARS, CRS-ES y DRS-ES figuran sólo en las tablas de armado por serie (págs.
395-396), que publican longitud, peso y número de parte. Sin rango de caudal no
se pueden verificar contra un pozo, así que se cargan pero el selector no los
ofrece.

Efecto colateral, documentado en `.claude/rules/domain.md`: como los únicos
separadores seleccionables son de vórtice y el tándem se arma con **tipos
distintos**, el escalón de tándem queda inalcanzable con este catálogo. La
lógica está implementada y verificada por unidad; se activa sola el día que
aparezca la hoja de datos de un rotativo.

### Empuje admisible de los sellos

No hay ningún gráfico ni tabla de capacidad de empuje de los protectores en el
catálogo. Se recorrieron las págs. 401-407 (sección Protectors) y no está.
`thrust_capacity_lbs` queda en `null` en las 43 entradas, y la verificación de
carga axial informa **«verificación no realizada»** en vez de aprobar.

Es lo que bloquea la tarea de digitalizar los gráficos de empuje: no se pueden
digitalizar gráficos que el catálogo no trae.

### Temperatura máxima de motores y sellos

- **Motores**: `max_temp_f` en `null` en las 850 entradas. Las tablas de motor
  publican potencia, tensión, corriente, tipo, longitud, peso y número de parte
  a 60 y 50 Hz — no la temperatura.
- **Sellos**: ídem. Lo más cerca es la guía de elastómeros de la pág. 404, pero
  **el catálogo de protectores no dice qué elastómero lleva cada modelo**, así
  que la tabla no se puede aplicar modelo por modelo sin suponer. Por eso
  `elastomers.json` está cargado y sin usar.

  Y aunque se supiera, el propio impreso advierte que el límite no se compara
  contra la temperatura de fondo sin más: *«an elastomeric component will
  operate at a higher temperature than the ambient wellbore temperature,
  depending on its location in the equipment»*.

### Ampacidad de los cables 1/0 y 2/0 en tabla

REDA ofrece esos dos calibres —figuran en las tablas de dimensiones de
Redalene PPEO, Redablack EER y Redalead ELTB/EHLBE— pero su ampacidad sólo
aparece en los gráficos de §2, no en ninguna tabla. Es el motivo por el que el
techo de 80 A de corriente de motor diseñable sigue vigente hasta que se
enganche la curva.

---

### Lo que se leyó y se decidió NO cargar

No todo lo que está impreso merece entrar al catálogo. Estos bloques se
revisaron y quedaron afuera a propósito, porque el modelo no los usa y cargarlos
sólo agregaría números de parte sin ningún dato que el diseño pueda verificar:

| Bloque | Págs. | Por qué no entra |
|---|---|---|
| Bolt-on intakes (sin separación) | 395-400 | Publican longitud, peso y número de parte. El modelo no tiene concepto de «admisión» separado de la bomba. |
| Accesorios FixStar (luces piloto, registrador Bristol) | 510 | Sin rating eléctrico. |
| Transformadores de instrumento | 510 | Son de medición, no de potencia: no entran al dimensionamiento. |
| Hardware espWatcher / SCADA | 510, 531 | Telemetría. |
| UniConn, StarView | 533-539 | Controlador de sitio y software. Cada FixStar ya viene con un UniConn, según la nota del propio catálogo. |
| Módulos TVSS StarShield | 542-547 | Protección contra sobretensiones transitorias. |
| Protectores de cable Lasalle | 489-490 | Accesorio mecánico de instalación. |
| Crossovers de base de motor, subs de descarga | 59-61 | Adaptación mecánica entre series. |

---

## 4. Pendiente de verificación contra el impreso

**Los dos gráficos de la pág. 473 llevan impreso el mismo título, «Redalene
Flat Cable», y no son el mismo gráfico**: el izquierdo llega a 250 A y el
derecho a 350 A. Se verificó carácter por carácter en la capa de texto del PDF;
no es un error de extracción.

Sin saber qué los distingue —clase de temperatura, tensión, tipo de armadura—
no se puede decidir cuál corresponde a las entradas `Redalene` de
`cables.json`, y elegir a ojo sería peor que no usar el dato.

---

## 5. Bombas que quedaron afuera, con su causa

| Bomba | Causa |
|---|---|
| P2500A | No pasa su propio control de forma de curva |
| D4300N | Errata del impreso: el eje de altura imprime `5 10 15 20 25 35 35`, la regresión no da lineal |
| GN5200 | Asignación de rótulos cruzada (`power` → `efficiency`) |
| HN13500 | Ídem |

`M520`, `M675`, `N1050` y `N1400` no están como tales porque son modelos base:
sus curvas viven en las variantes de corte A/B/C, que **sí** están cargadas.
