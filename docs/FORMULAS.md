# BES Designer — Compendio de Fórmulas

Todas las fórmulas implementadas en el motor de cálculo, con referencia al archivo
y línea donde viven y a la fuente bibliográfica. Notación: las unidades van entre
corchetes. Referencia base: Kermit Brown, *The Technology of Artificial Lift
Methods*, Vol. 2b, Cap. 4.5.

> **Para revisar el motor, la fuente es la pestaña «Fórmulas» de la app**
> (`GET /api/formulas`), no este archivo. Ahí las fórmulas se listan **desde el
> propio código** —`bes/core/formula_catalog.py`, la única declaración de cada
> una— así que no pueden decir una cosa y el programa hacer otra. Este documento
> se escribe a mano y por lo tanto puede quedar atrasado; sirve como texto
> corrido para leer, no como referencia autoritativa.
>
> Estado: **las 82 fórmulas del motor están en el catálogo**, en los diez temas
> —IPR, PVT, multifásico, TDH, diseño, viscosidad, gas, afinidad, eléctrico y
> mecánica—. No queda nada sin instrumentar.

---

## 1. IPR — Inflow Performance Relationship
Archivo: [backend/src/bes/core/ipr.py](../backend/src/bes/core/ipr.py)

El simulador implementa **tres métodos, y solo tres**.

### 1.1 IPR Lineal (Darcy) — `linear_ipr()`
Válida para flujo monofásico (P_wf ≥ P_b): el caudal crece en línea recta con la
caída de presión, y la pendiente es el índice de productividad.

$$q = J \cdot (P_r - P_{wf})$$

### 1.2 Vogel — `vogel_ipr()`
Empuje por gas en solución (P_wf < P_b): al liberarse gas dentro del reservorio
el flujo pasa a bifásico y la IPR se curva hacia abajo. *Vogel, JPT (1968).*

$$\frac{q}{q_{max}} = 1 - 0.2\left(\frac{P_{wf}}{P_r}\right) - 0.8\left(\frac{P_{wf}}{P_r}\right)^2$$

q_max a partir de un punto de ensayo — `vogel_qmax_from_test()`:

$$q_{max} = \frac{q_{test}}{1 - 0.2\,(P_{wf}/P_r) - 0.8\,(P_{wf}/P_r)^2}$$

> **Vogel puro sólo vale con el reservorio saturado** ($P_b \ge P_r$). En un
> reservorio subsaturado hay que usar la forma generalizada de §1.2-bis: aplicar
> Vogel desde $P_r$ en todo el rango sobreestima el índice de productividad
> —25 % en un pozo típico— y curva un tramo de la IPR que es recto.

### 1.2-bis Vogel generalizado — `vogel_composite_ipr()`

**Es el método que usa el simulador.** La presión de burbuja parte la IPR en
dos: arriba de $P_b$ el flujo en el reservorio es monofásico y vale Darcy, así
que la IPR es una **recta**; recién debajo de $P_b$ se libera gas y la curva se
dobla. *Beggs, §2, ecs. 2-38 y 2-53.*

$$q = J\,(P_r - P_{wf}) \qquad \text{para } P_{wf} \ge P_b$$

$$q = q_b + \frac{J\,P_b}{1.8}\left[1 - 0.2\left(\frac{P_{wf}}{P_b}\right) - 0.8\left(\frac{P_{wf}}{P_b}\right)^2\right] \qquad \text{para } P_{wf} < P_b$$

con $q_b = J\,(P_r - P_b)$, el caudal justo al llegar a la burbuja. Los dos
tramos **empalman con la misma pendiente** en $P_b$, así que la curva es
continua y sin quiebre.

Con el reservorio saturado ($P_b \ge P_r$) se reduce sola a Vogel puro con
$q_{max} = J\,P_r/1.8$ — no hace falta un caso aparte, y de eso se ocupa
`effective_bubble_point()`.

**J a partir del ensayo — `vogel_j_from_test()`.** Hay dos casos según dónde
cayó la $P_{wf}$ medida:

| Caso | Despeje |
|---|---|
| Ensayo **sobre** $P_b$ (tramo recto) | $J = \dfrac{q_{test}}{P_r - P_{wf,test}}$ |
| Ensayo **bajo** $P_b$ (tramo curvo) | $J = \dfrac{q_{test}}{(P_r - P_b) + \dfrac{P_b}{1.8}\left[1 - 0.2\,(P_{wf}/P_b) - 0.8\,(P_{wf}/P_b)^2\right]}$ |

Regresión: Beggs Ejemplos 2-2 (saturado) y 2-5B (subsaturado, ensayo bajo $P_b$),
en `tests/test_ipr.py::TestVogelGeneralizadoBeggs`.

### 1.3 Fetkovich — `fetkovich_ipr()`
Ecuación empírica de contrapresión. *Fetkovich, SPE 4529 (1973).*

$$q = C\,(P_r^2 - P_{wf}^2)^n$$

con $n = 1.0$ flujo laminar (Darcy) y $n = 0.5$ flujo totalmente turbulento; en
la práctica $0.5 \le n \le 1.0$.

> **Fetkovich NO se parte en la presión de burbuja, y está bien así.** Beggs
> (ec. 2-58) integra Darcy sobre las dos regiones de un reservorio subsaturado y
> concluye que *«Fetkovich then stated that the composite effect results in an
> equation of the form $q = C(P_r^2 - P_{wf}^2)^n$»*: el ajuste de $C$ y $n$ ya
> absorbe el comportamiento bifásico. Agregarle un tramo recto sería un error.
> Regresión contra el Ejemplo 2-7A del Beggs, punto por punto.

### 1.4 Índice de productividad a partir de un ensayo — `productivity_index_from_test()`

El índice de productividad **no es un dato de entrada**: se deriva del ensayo de
producción (P_wf y caudal estabilizados) invirtiendo el modelo IPR elegido, de
modo que la curva pase exactamente por el punto medido.

| Método | Despeje |
|---|---|
| Lineal | $J = \dfrac{q_{test}}{P_r - P_{wf,test}}$ |
| Vogel | Por §1.2-bis, con los dos casos según dónde cayó la $P_{wf}$ del ensayo |
| Fetkovich | $C = \dfrac{q_{test}}{(P_r^2 - P_{wf,test}^2)^n}$ con $n$ dado |

> Un ensayo de **un solo punto** no permite ajustar $C$ y $n$ a la vez (dos
> incógnitas, una ecuación): por eso Fetkovich exige cargar $n$ —del ensayo
> multi-rate flow-after-flow o isocronal— y solo despeja $C$. En ese método el
> $J$ que se muestra es la secante en el punto de ensayo, informativo: la IPR la
> gobiernan $C$ y $n$.

Expuesto por la API en `POST /api/ipr/from-test`; el formulario lo muestra en
solo lectura junto al draw-down y al AOF.

### 1.5 AOF (caudal a P_wf = 0) — `_compute_aof()`

Es el techo físico del reservorio y le pone tope al caudal de diseño.

| Método | AOF |
|---|---|
| Lineal | $J\,P_r$ |
| Vogel | $J\,(P_r - P_b) + J\,P_b/1.8$  — `vogel_aof()`; con $P_b \ge P_r$ queda $J\,P_r/1.8$ |
| Fetkovich | $C\,P_r^{2n}$ |

### 1.6 P_wf para un caudal objetivo — `calculate_pwf_for_target_rate()`

Es la IPR usada al revés. El método lineal tiene despeje directo:

$$P_{wf} = P_r - \frac{q}{J}$$

Vogel y Fetkovich no se despejan a mano, así que se busca numéricamente la raíz
de $q(P_{wf}) - q_{objetivo} = 0$ entre $P_{wf}=0$ y $P_{wf}=P_r$
(`scipy.optimize.brentq`, método de Brent).

Es el **primer** cálculo del diseño: de esta $P_{wf}$ sale el PIP y de ahí todo
el TDH. Por eso la traza de fórmulas en pantalla arranca acá — `ipr_trace()`
emite la ecuación del método elegido con los valores del pozo, el caudal en la
burbuja cuando corresponde, y el draw-down resultante.

### 1.7 Validez del método lineal — `ipr_validity_warning()`

La recta de Darcy supone flujo monofásico. Si la $P_{wf}$ de diseño cae por
debajo de $P_b$, el flujo ya es bifásico y la recta **sobreestima el aporte del
pozo** — Beggs reporta errores de 70-80 % a $P_{wf}$ baja. El simulador no la
corrige (el usuario eligió la recta) pero emite una advertencia que cuantifica
la diferencia contra el Vogel generalizado con el mismo $J$.

---

## 2. PVT — Propiedades de los fluidos
Archivo: [core/pvt.py](../backend/src/bes/core/pvt.py)

### 2.1 Gravedad específica del petróleo — [pvt.py:37](../backend/src/bes/core/pvt.py#L37)

$$\gamma_o = \frac{141.5}{131.5 + API}$$

### 2.2 GOR en solución (Standing) — [pvt.py:62](../backend/src/bes/core/pvt.py#L62)
Con P_eff = min(P, P_b). *Standing (1947).*

$$R_s = \gamma_g\left[\left(\frac{P_{eff}}{18.2} + 1.4\right)\,10^{\,0.0125\,API - 0.00091\,T}\right]^{1.2048}$$

(El exponente 1.2048 = 1/0.83.)

### 2.3 Presión de burbuja (inversa de Standing) — [pvt.py:103](../backend/src/bes/core/pvt.py#L103)

$$P_b = 18.2\left[\left(\frac{R_s}{\gamma_g}\right)^{0.83} 10^{\,0.00091\,T - 0.0125\,API} - 1.4\right]$$

### 2.4 Factor volumétrico del petróleo B_o (Standing) — [pvt.py:146](../backend/src/bes/core/pvt.py#L146)

$$F = R_s\left(\frac{\gamma_g}{\gamma_o}\right)^{0.5} + 1.25\,T$$
$$B_o = 0.9759 + 0.00012\,F^{1.2}$$

### 2.5 Factor z del gas (Dranchuk–Abou-Kassem) — [pvt.py:185](../backend/src/bes/core/pvt.py#L185)
Pseudo-críticas de Standing — [pvt.py:42](../backend/src/bes/core/pvt.py#L42):

$$P_{pc} = 677 + 15\,\gamma_g - 37.5\,\gamma_g^2,\qquad T_{pc} = 168 + 325\,\gamma_g - 12.5\,\gamma_g^2$$

Reducidas: $P_{pr} = P/P_{pc}$, $T_{pr} = (T+460)/T_{pc}$, densidad reducida $\rho_r = 0.27\,P_{pr}/(z\,T_{pr})$.

Ecuación de estado DAK (11 constantes, resuelta por iteración):

$$z = 1 + C_1\rho_r + C_2\rho_r^2 - C_3\rho_r^5 + C_4$$

$$C_1 = A_1 + \tfrac{A_2}{T_{pr}} + \tfrac{A_3}{T_{pr}^3} + \tfrac{A_4}{T_{pr}^4} + \tfrac{A_5}{T_{pr}^5}$$
$$C_2 = A_6 + \tfrac{A_7}{T_{pr}} + \tfrac{A_8}{T_{pr}^2},\qquad C_3 = A_9\left(\tfrac{A_7}{T_{pr}} + \tfrac{A_8}{T_{pr}^2}\right)$$
$$C_4 = A_{10}\,(1 + A_{11}\rho_r^2)\,\frac{\rho_r^2}{T_{pr}^3}\,e^{-A_{11}\rho_r^2}$$

Semilla inicial por Papay. *Dranchuk & Abou-Kassem, JCPT (1975).*

### 2.6 Factor volumétrico del gas B_g — [pvt.py:234](../backend/src/bes/core/pvt.py#L234)

$$B_g = 0.00504\,\frac{z\,(T+460)}{P}\quad [\text{bbl/scf}]$$

### 2.7 Factor volumétrico del agua B_w (McCain) — [pvt.py:265](../backend/src/bes/core/pvt.py#L265)

$$B_w = 1 + 1.21\times10^{-4}\,\Delta T + 1.0\times10^{-6}\,\Delta T^2 - 3.33\times10^{-6}\,P,\quad \Delta T = T - 60$$

### 2.8 Viscosidad del petróleo (Beggs–Robinson) — [pvt.py:298](../backend/src/bes/core/pvt.py#L298)
Muerta:

$$X = T^{-1.163}\,e^{\,6.9824 - 0.04658\,API},\qquad \mu_{od} = 10^X - 1\ [\text{cp}]$$

Viva (saturada) — [pvt.py:327](../backend/src/bes/core/pvt.py#L327):

$$a = 10.715\,(R_s + 100)^{-0.515},\quad b = 5.44\,(R_s + 150)^{-0.338}$$
$$\mu_{ob} = a\,\mu_{od}^{\,b}$$

### 2.9 Densidades in-situ — [pvt.py:420](../backend/src/bes/core/pvt.py#L420)

$$\rho_o = \frac{62.4\,\gamma_o + 0.0136\,R_s\,\gamma_g}{B_o},\qquad \rho_w = \frac{62.4\,\gamma_w}{B_w}$$
$$\rho_g = 2.70\,\frac{\gamma_g\,P}{z\,(T+460)}$$

### 2.10 Densidad de mezcla — [pvt.py:436](../backend/src/bes/core/pvt.py#L436)
Balance de masa sobre 1 STB de líquido total de superficie; SG de mezcla = ρ_mix / 62.4.

---

## 3. Flujo multifásico — Poettmann & Carpenter (1952)
Archivo: [backend/src/bes/core/multiphase.py](../backend/src/bes/core/multiphase.py)

Es la **única** correlación multifásica del simulador: todas las pérdidas de
carga se calculan por Poettmann & Carpenter.

### 3.1 Velocidades superficiales — `_superficial_velocities()`
Área de flujo: $A = \frac{\pi}{4}(d/12)^2$ [ft²]. Los caudales de superficie se
llevan a condiciones de fondo con los factores volumétricos del PVT:

$$q_{l,res} = q_o B_o + q_w B_w,\qquad q_{g,res} = q_o\,(GOR - R_s)\,B_g\ [\text{bbl/d}]$$
$$v_{sl} = \frac{q_{l,res}\cdot 5.615}{86400\,A},\qquad v_{sg} = \frac{q_{g,res}\cdot 5.615}{86400\,A}\ [\text{ft/s}]$$
$$v_m = v_{sl} + v_{sg},\qquad \lambda_l = v_{sl}/v_m$$

### 3.2 Densidad de la mezcla — `poettmann_carpenter_components()`
P&C supone mezcla **homogénea**: sin deslizamiento entre fases, las dos viajan a
la misma velocidad, así que la densidad se pondera por la fracción de caudal.

$$\rho_m = \rho_l\,\lambda_l + \rho_g\,(1-\lambda_l)\ [\text{lb/ft}^3]$$

### 3.3 Factor de fricción — `poettmann_carpenter_components()`
Empírico, ajuste log-log a la carta original (Brown 1977, Vol. 1, Tabla 4-7):

$$N_\rho = \rho_m\,v_m\,d,\qquad f_{PC} = 0.030\,N_\rho^{-0.19},\qquad f_{PC}\in[0.005,\,0.065]$$

### 3.4 Gradiente de presión — `poettmann_carpenter_components()`

$$\frac{dP}{dz} = \underbrace{\frac{\rho_m\sin\theta}{144}}_{\text{gravedad}} + \underbrace{\frac{f_{PC}\,\rho_m\,v_m^2}{2\,g_c\,d\cdot144}}_{\text{fricción}}\ [\text{psi/ft}]$$

con $g_c = 32.174$ lbm·ft/(lbf·s²) y $d$ el diámetro interno en ft.

> La función devuelve los dos términos por separado. El TDH ya contabiliza la
> columna de fluido como *elevación vertical*, así que quien solo reemplace la
> pérdida por fricción debe tomar `friction`, **nunca** `total`.

### 3.5 Integración del traverse — `pressure_traverse()`
Marcha por *n* segmentos; el gradiente se evalúa en el punto medio con 3 pasos
correctores, porque el PVT depende de la presión que se está buscando.
Subiendo: $P_{i+1} = P_i - \frac{dP}{dz}\,dz$;
bajando: $P_{i+1} = P_i + \frac{dP}{dz}\,dz$. Temperatura lineal con la profundidad.

### 3.6 Presiones de admisión y descarga
`calculate_pip()` — Pwf por IPR, luego traverse hacia arriba por el anular
(ID del casing) hasta la admisión de la bomba.
`calculate_discharge_pressure()` — desde la presión de cabeza, traverse hacia
abajo por el tubing hasta la profundidad de la bomba. Ambas siguen Brown
Vol. 2b, §4.532.

---

## 4. TDH — Total Dynamic Head
Archivo: [core/tdh.py](../backend/src/bes/core/tdh.py) — Brown §4.5324

### 4.1 SG del líquido en superficie — [tdh.py:37](../backend/src/bes/core/tdh.py#L37)

$$SG_l = \gamma_o\,(1 - f_w) + \gamma_w\,f_w$$

### 4.2 Elección de la correlación de pérdida de carga

La fricción en el tubing **no siempre se calcula igual**. La elige el usuario
con `objectives.pressure_loss_method`; si no eligió —el default— la decide la
fracción volumétrica de gas libre en la admisión, $f_g$, evaluada antes que el
TDH (`bes.core.gas_handling.free_gas_fraction_at_intake`).

| Condición | Correlación |
|---|---|
| $f_g \le$ umbral | Hazen–Williams (§4.3) — la corriente es prácticamente líquida |
| $f_g >$ umbral | Poettmann–Carpenter, **solo el término de fricción** (§4.4) |

El umbral es `DesignObjectives.gas_fraction_pc_threshold`, por defecto **0.01**
— el mismo corte por debajo del cual el gas se considera despreciable. **No se
expone** ni por pantalla ni por la API; sobrevive como parámetro sólo porque los
ejemplos impresos de Brown lo fijan en 1.0, ya que el libro los resuelve como
monofásicos.

Con un método elegido a mano se usa ése y el umbral no interviene. Si la
elección contradice a la física, el diseño sale con un aviso.

### 4.2b Envelope de Poettmann-Carpenter

El método se levantó con pozos de un tipo determinado, y fuera de ahí no vale:

| Límite | Valor | Si no se cumple |
|---|---|---|
| Tubería | 2, 2½ y 3 pulg (OD 2 3/8, 2 7/8, 3 1/2) | Restricción dura |
| Viscosidad del petróleo | < 5 cp | Aviso |
| Relación gas-líquido | < 1500 scf/bbl | Aviso |
| Caudal de líquido | > 400 bbl/d | Aviso |

$$RGL = \frac{GOR}{1 + WOR},\qquad WOR = \frac{W_c}{1 - W_c}$$

El GOR se mide por barril de **petróleo** y el límite está declarado por barril
de **líquido**: con corte de agua no son lo mismo.

> **Qué deja afuera este híbrido.** Solo se sustituye la fricción; la elevación
> vertical y el head de cabeza siguen usando el SG del líquido. En un pozo con
> gas real la columna del tubing también es más liviana que la de líquido, así
> que el término de elevación calculado acá es **conservador**: sobreestima la
> altura que la bomba debe desarrollar.

### 4.3 Fricción en tubing (Hazen–Williams) — [tdh.py:10](../backend/src/bes/core/tdh.py#L10)
Con $q_{gpm} = q_{bpd}\cdot 42/1440$ y C = 120 (acero de diseño):

$$h_f = 0.2083\left(\frac{100}{C}\right)^{1.852}\frac{q_{gpm}^{1.852}}{d^{4.8655}}\cdot\frac{L}{100}\ [\text{ft}]$$

### 4.4 Fricción en tubing (Poettmann–Carpenter, término de fricción)

De las dos contribuciones del gradiente P&C (§3.6) se acumula **únicamente la de
fricción**: la de gravedad es la contraparte física de la elevación vertical que
el TDH ya contabiliza, y sumarla contaría la columna dos veces.

El gradiente no puede evaluarse en un punto representativo único. El gas se
expande al caer la presión hacia la superficie, así que la velocidad de la
mezcla cerca del cabezal es varias veces la que tiene en la bomba y la fricción
—que va con $v^2$— queda fuertemente cargada hacia el tope de la columna. Por
eso se integra marchando el tubing en 30 tramos desde el cabezal (donde la
presión es dato) hacia abajo:

$$h_f = \frac{2.31}{SG_l}\sum_{i=1}^{30} \left(\frac{dP}{dz}\right)_{fric,i}\,\Delta z\ [\text{ft}]$$

avanzando la presión con el gradiente **total** (el perfil real del tubing lo
gobiernan ambos términos) pero acumulando solo el de fricción. Partir del
cabezal elimina además la circularidad: no hace falta estimar el TDH para
calcular la fricción.

### 4.5 TDH — [tdh.py:43](../backend/src/bes/core/tdh.py#L43)

$$\text{TDH} = \underbrace{\left(D_{pump} - \frac{PIP\cdot2.31}{SG_l}\right)}_{\text{elevación vertical}} + \underbrace{h_f}_{\text{fricción}} + \underbrace{\frac{P_{wh}\cdot2.31}{SG_l}}_{\text{cabezal}}\ [\text{ft}]$$

---

## 5. Diseño de la bomba
Archivo: [core/pump_design.py](../backend/src/bes/core/pump_design.py)

### 5.1 Número de etapas — [pump_design.py:45](../backend/src/bes/core/pump_design.py#L45)

$$N_{stages} = \left\lceil \frac{\text{TDH}}{h_{stage}(q)} \right\rceil$$

### 5.2 Potencia al eje — [pump_design.py:62](../backend/src/bes/core/pump_design.py#L62)
hp/etapa del catálogo está referido al agua (SG = 1); se corrige por SG del fluido:

$$HP = N_{stages}\cdot hp_{stage}(q)\cdot SG_{fluido}$$

### 5.3 Optimización de carcasas (pump housings) — `core/housing.py`

Las etapas se alojan en carcasas de longitudes discretas del catálogo. La
combinación **no se decide por regla**: se buscan las arreglos posibles y se
ordenan por una clave lexicográfica estricta —misma disciplina que el
ordenamiento de bombas (§8), sin pesos ni puntajes:

1. ajuste exacto de las etapas requeridas;
2. si no hay exacto, mínimo excedente de capacidad;
3. mínima cantidad de carcasas;
4. mínimas etapas desaprovechadas — en este modelo coincide con (2): toda
   etapa instalada que no es activa es una etapa ciega;
5. arreglo más simple y estandarizado — menos longitudes distintas, sin
   sobre-especificar la calificación de presión, y carcasas grandes primero.

### 5.4 Verificación de presión de carcasa (Brown §4.5451)

Restricción **dura dentro de la búsqueda**, no chequeo posterior: un arreglo
que ponga cualquier carcasa sobre su calificación se descarta y la búsqueda
continúa. El peor caso es a caudal cero, donde el head por etapa es máximo:

$$\text{MaxP}_k = P_{(Q=0)}\cdot N_{\text{activas},\,\le k}\cdot\text{Pem}
= \frac{h_{shut\text{-}in}\,[\text{ft/etapa}]\cdot N_{\text{activas},\,\le k}\cdot SG}{2.31}\ [\text{psi}]$$

La presión **se acumula desde la admisión**: la carcasa $k$ ve el diferencial
de todas las etapas activas por debajo y dentro de ella, así que la superior es
la crítica. Las etapas ciegas no generan head y no suman. Es la misma relación
que aplica el motor métrico en `metric_design.step11_housing_burst()`,
expresada en unidades de campo.

Cuando el catálogo publica la presión de cada carcasa, el arreglo se ordena con
la mejor calificada arriba, que es donde la presión es máxima; eso permite
tándems mixtos estándar / alta presión. Si el catálogo no publica el límite, el
resultado dice que **la verificación no pudo realizarse** en vez de darla por
aprobada.

### 5.5 Verificación mecánica: eje y cojinete — `core/mechanical.py`

Junto con la presión de carcasa (§5.4) son las **tres verificaciones mecánicas**
que el fabricante resume en la nota al pie de toda hoja de engineering data:

> *"Maximum staging may be limited by housing pressure limit, shaft capacity or
> thrust loading."*

Tres topes independientes sobre el número de etapas. **Manda el menor**: una
pila que entra en la presión de carcasa puede igual torcer el eje.

#### Potencia sobre el eje

$$HP_{eje} = P_{etapa}\cdot N_{etapas}\cdot Pem$$

con $P_{etapa}$ leída de la curva al caudal de producción. Pasarse del límite
**estándar** no es una falla: pide eje de **alta resistencia**, igual que una
carcasa sobre-presionada pide una de alta presión. Solo superar el de alta
resistencia hace inviable el diseño.

> **El límite depende de la frecuencia.** Lo que aguanta un eje es un *torque*,
> y la potencia es torque por velocidad: a torque constante el límite escala
> lineal con la frecuencia, $HP_{lim}(f) = HP_{lim}(f_{ref})\cdot f/f_{ref}$.
> La hoja de Wood Group publica 104 hp **a 50 Hz**, que son 124.8 hp a 60 Hz.
> Comparar un diseño de 60 Hz contra el límite de 50 sub-califica el eje un 20 %.

#### Carga sobre el cojinete de la sección sellante

$$\text{Carga TL} = H_o\cdot Pem\cdot A_{eje}
\;=\;\frac{H_o\,[\text{ft}]\cdot Pem}{2.31}\cdot A_{eje}\,[\text{in}^2]\ [\text{lbs}]$$

donde $H_o$ es la elevación que la bomba levanta hasta boca de pozo y $A_{eje}$
la sección transversal del eje.

> **Corrección respecto del apunte.** La fórmula impresa es
> $\text{Carga TL} = H_o\cdot N_{etapas}\cdot Pem\cdot A_{eje}$, pero ahí
> mismo se define $H_o$ como la elevación **total**, que ya es la suma de lo que
> aporta cada etapa: el factor $N_{etapas}$ cuenta la columna dos veces. Con
> 1500 m de elevación y 250 etapas la forma impresa da **198 000 lbs** contra
> protectores calificados para 5 000–30 000 lbs; sin ese factor da **792 lbs**,
> que coincide con los 779 lbs que estima Takács sobre el mismo caso. El factor
> se toma como error de tipeo y se descarta.

#### Capacidad del cojinete de empuje

El fabricante la publica como un **número de etapas con un tope de temperatura**
—la serie 400 admite 303 etapas en el cojinete estándar hasta 230 °F, o 1529 en
el de alta carga hasta 250 °F— porque el material pierde capacidad con el calor.
**Las dos condiciones atan**: un pozo más caliente que el tope descarta ese
cojinete por pocas etapas que lleve.

#### Los datos

Vienen de `catalogs/pump_series.json`, **por serie** (el eje, la carcasa y los
cojinetes son hardware de la serie, no del modelo hidráulico). Hoy solo la
**serie 400** tiene ficha, transcrita de la hoja *ENGINEERING DATA TD1750 50Hz*
de Wood Group. Una serie sin ficha deja las verificaciones **sin realizar** —
reportadas como tales, nunca como aprobadas.

### 5.6 Proximidad al BEP — [pump_design.py:86](../backend/src/bes/core/pump_design.py#L86)
Cerca del BEP si $|q - q_{BEP}|/q_{BEP} \le 0.15$.

### 5.7 Leyes de afinidad — `core/affinity.py`

Las curvas de catálogo se publican a una **frecuencia fija**, con agua limpia
(SG = 1, µ = 1 cp) y **para una etapa**. Las leyes de afinidad predicen la curva
a otra velocidad, otro diámetro de impulsor u otro fluido:

$$Q_2 = Q_1\left(\frac{N_2}{N_1}\right)\left(\frac{D_2}{D_1}\right)$$

$$H_2 = H_1\left(\frac{N_2}{N_1}\right)^2\left(\frac{D_2}{D_1}\right)^2$$

$$HP_2 = HP_1\left(\frac{N_2}{N_1}\right)^3\left(\frac{D_2}{D_1}\right)^3\left(\frac{SG_2}{SG_1}\right)$$

La **eficiencia no se escala**: es invariante ante un cambio de velocidad o de
diámetro, y eso es lo que convierte a las leyes en una transformación de
similitud y no en un ajuste empírico.

Nótese que la **altura no lleva término de gravedad específica** y la potencia
sí: un impulsor a una velocidad dada desarrolla los mismos pies de columna
bombee agua o salmuera, pero mover el fluido más pesado cuesta proporcionalmente
más potencia.

#### Por qué se trabaja en hertz y no en rpm

El motor es de inducción de dos polos, así que la velocidad sincrónica es
$120f/\text{polos}$ y el eje gira más lento por el deslizamiento (≈2.8 %:
3000 rpm sincrónicas a 50 Hz contra ≈2917 rpm reales). Como el deslizamiento es
prácticamente el mismo a ambas frecuencias, **se cancela en la relación**:

$$\frac{N_2}{N_1} = \frac{f_2}{f_1}$$

por lo que las leyes se aplican directamente sobre la frecuencia del variador.
Así se diseña en la práctica y evita arrastrar un supuesto de deslizamiento al
resultado. `synchronous_rpm()` y `motor_rpm()` quedan para mostrar en pantalla.

#### Frecuencia para un caudal objetivo

La ley de caudal es lineal en la velocidad, así que se invierte en forma
cerrada — es la pregunta que hace un diseño con variador:

$$f_2 = f_1\,\frac{Q_2}{Q_1}$$

#### Potencia hidráulica y eficiencia

$$HHP = \frac{Q\cdot H_d\cdot SG}{135\,771}\quad [\text{hp}],\qquad
\eta = \frac{\text{Potencia hidráulica}}{\text{Potencia al freno}}$$

con Q en b/d y H_d en ft. Es la identidad con la que se controló la calidad de
las curvas digitalizadas (ver `tools/catalog_pipeline`). El apunte de cátedra
redondea la constante a 136 000.

Expuesto por la API en `GET /api/affinity` y `GET /api/affinity/figure`; el
front lo muestra en la pestaña **Leyes de afinidad**.

#### Dónde entra en el diseño

Las curvas de catálogo del proyecto están **todas publicadas a 60 Hz**, pero un
pozo argentino corre a **50 Hz**. Diseñar contra la curva sin escalar está mal
en tres cosas a la vez:

| Magnitud a 50 Hz | Factor | Consecuencia |
|---|---|---|
| Head por etapa | $(50/60)^2 = 0.694$ | faltan **44 % más de etapas** |
| HP por etapa | $(50/60)^3 = 0.579$ | motor sobredimensionado |
| Rango operativo | $50/60 = 0.833$ | la bomba puede ni pertenecer a la lista de candidatas |

Por eso `design_pump_complete()` lleva **toda la curva** a la frecuencia de
operación con `pump_at_frequency()` **antes de filtrar por rango de caudal**, y
el objeto escalado es el que viaja a la interpolación, al conteo de etapas, a la
distancia al BEP del ordenamiento y al head de shut-in de la verificación de
presión de carcasa.

La frecuencia de operación es la de red (`SurfaceConditions.frequency`), salvo
que haya variador: con `use_vsd` se puede fijar `design_frequency_hz` y diseñar
a esa velocidad. Sin variador la bomba gira a la frecuencia de línea y el campo
se rechaza.

> **Cuidado al verificar a mano.** El invariante de las leyes es
> **punto-a-punto correspondiente**: $(Q, H)$ va a $(Q\,r,\;H\,r^2)$. A
> **caudal fijo** el cociente de alturas *no* es $r^2$, porque al escalar la
> curva ese caudal queda en otra posición relativa. Ambas cosas son la misma
> ley bien aplicada.

### 5.8 Corrección por viscosidad (Hydraulic Institute) — [pump_design.py:118](../backend/src/bes/core/pump_design.py#L118)
Conversión cSt → SSU (Takács 2018, ec. 4.14 — la única del proyecto):

$$\text{SSU} < 100:\ cSt = 0.226\,\text{SSU} - 195/\text{SSU}$$
$$\text{SSU} \ge 100:\ cSt = 0.220\,\text{SSU} - 135/\text{SSU}$$

Factores C_Q, C_H, C_E interpolados de tabla HI; potencia:

$$hp_{factor} = \frac{C_Q\,C_H}{C_E}$$

(Para μ ≤ 20 SSU todos los factores valen 1.)

---

## 6. Diseño eléctrico
Archivo: [core/electrical.py](../backend/src/bes/core/electrical.py) — Brown §4.5325–4.5326

### 6.1 Selección de cable — [electrical.py:112](../backend/src/bes/core/electrical.py#L112)
- Ampacidad: $\text{max\_amps} \ge I_{motor}\cdot 1.25$ (derateo NEC por carga continua)
- Temperatura: $\text{max\_temp} \ge T_{fondo} + 25\,°F$
- Ajuste físico: espesor del cable plano ≤ claro anular $(ID_{casing} - OD_{motor})/2$
- Longitud de cable: $L = D_{pump} + 100\ \text{ft}$

### 6.2 Verificación eléctrica del cable — `check_cable_electrical()`

El dato de catálogo es la caída **de línea** por amper y por 1000 ft, o sea que
ya lleva el $\sqrt{3}$ adentro. De ahí se despeja la resistencia por fase:

$$R_T = \frac{\Delta V_{[V/(A\cdot1000ft)]}}{\sqrt{3}}\cdot\frac{L}{1000}\ [\Omega]$$

**Pérdida por efecto Joule** — el término operativo del criterio económico de
Brown (§4.5325):

$$\Delta P_c = \frac{3\cdot I^2\cdot R_T}{1000}\ [\text{kW}]$$

**Verificación de arranque.** Un motor de inducción arranca demandando 4 a 6
veces su corriente nominal, y esa corriente cae sobre el mismo cable:

$$\frac{U_{start}}{U_{np}} = \frac{U_{np} - 4\,I\,R_T}{U_{np}} > 0.5$$

Si baja de 0.5 el motor **no arranca**: no es una advertencia de eficiencia,
es una falla de puesta en marcha.

#### Los tres criterios no pesan igual

| Criterio | Trato |
|---|---|
| Arranque > 0.5 | **Restricción dura** — es física |
| ≤ 30 V/1000 ft (banda de la carta) | **Restricción dura** |
| ≤ 5 % de la tensión de placa | **Se reporta**, no descarta |

El 5 % es una regla práctica que en pozos profundos con motores de tensión
moderada resulta inalcanzable con los calibres del catálogo: aplicarla como
filtro dejaría 10 de los 11 casos sin ningún cable. Se informa junto con los kW
disipados para que la decisión sea del ingeniero.

> **Cambio de criterio en la selección.** Antes se elegía el conductor **más
> chico** que aguantara la corriente — justo el que más cae. Ahora se recorre de
> menor a mayor y se toma el primero que además pasa las verificaciones: el más
> económico *de los que sirven*. Sobre los 11 casos de ejemplo, los diseños que
> no arrancaban pasaron de **7 a 2**, y esos dos avisan que el remedio es un
> motor de mayor tensión.

### 6.3 Caída de tensión en el cable — [electrical.py:183](../backend/src/bes/core/electrical.py#L183)

$$\Delta V = v_{drop/A/1000ft}(T)\cdot I \cdot \frac{L}{1000}\ [\text{V}]$$

### 6.4 Tensión en superficie — [electrical.py:209](../backend/src/bes/core/electrical.py#L209)

$$V_s = (V_{motor} + \Delta V_{cable})\left(1 + \frac{\text{pérdida\_trafo\,\%}}{100}\right),\quad \text{pérdida} = 2.5\,\%$$

### 6.5 Potencia aparente (trafo) — [electrical.py:229](../backend/src/bes/core/electrical.py#L229)

$$kVA = \frac{V_s\,I\,\sqrt{3}}{1000}\quad (\text{trifásico})$$

### 6.6 Selección de motor — [electrical.py:283](../backend/src/bes/core/electrical.py#L283)
- $HP_{rating} \ge HP_{req}\cdot 1.10$ (10 % de margen de placa)
- $OD_{motor} \le OD_{pump}\cdot 1.20$
- Claro de cable: $OD_{motor} + 2\cdot e_{cable,min} \le ID_{casing}$
- Tensión objetivo: ≤70 HP → 800 V; 71–200 HP → 1200 V; >200 HP → 2000 V

### 6.7 Empuje axial sobre el protector — [electrical.py:355](../backend/src/bes/core/electrical.py#L355)
*Takács, ESP Manual:*

$$\Delta P_{pump} = \text{TDH}\cdot 0.433\cdot SG,\qquad F_{axial} = \Delta P_{pump}\cdot\frac{\pi}{4}d_{shaft}^2\cdot 1.20\ [\text{lbs}]$$

(El factor 1.20 es el margen de diseño; d_shaft según la serie de la bomba.)

---

## 7. Manejo de gas
Archivo: [core/gas_handling.py](../backend/src/bes/core/gas_handling.py) — Brown §4.53102–4.53103

### 7.1 Porcentaje de ingestión de gas (GIP) — [gas_handling.py:37](../backend/src/bes/core/gas_handling.py#L37)

$$GIP = \left(1 - \frac{V_{gas,vented}}{V_{gas,intake}}\right)(1 - \eta_{sep})$$

### 7.2 Riesgo de gas lock — [gas_handling.py:73](../backend/src/bes/core/gas_handling.py#L73)
fg < 0.10 → bajo; 0.10–0.30 → medio; > 0.30 → alto.

### 7.3 Factor de deterioro de la bomba — [gas_handling.py:119](../backend/src/bes/core/gas_handling.py#L119)

$$f_{det} = \begin{cases} 1.0 & fg < 0.10 \\ 1.0 - \dfrac{fg - 0.10}{0.20}\cdot0.30 & 0.10 \le fg \le 0.30 \\ 0.5 & fg > 0.30 \end{cases}$$

### 7.4 Fracción volumétrica de gas libre en admisión — [gas_handling.py:526](../backend/src/bes/core/gas_handling.py#L526)

$$f_g = \frac{V_{gas}}{V_{oil} + V_{water} + V_{gas}},\quad V_{gas} = (1 - f_w)\,(GOR - R_s)\,B_g$$

### 7.5 Diseño por incrementos de presión — [gas_handling.py:244](../backend/src/bes/core/gas_handling.py#L244)
Se divide [P_intake → P_discharge] en pasos de 200 psi. Por incremento, con la mezcla
evaluada en el punto medio:

$$q_{res} = q_{target}\cdot V_{total},\qquad \text{gradiente} = \frac{\rho_{mix}}{144}\ [\text{psi/ft}]$$
$$\text{psi/etapa} = h_{stage}\cdot\text{gradiente},\qquad N_{stages} = \left\lceil\frac{\Delta P}{\text{psi/etapa}}\right\rceil$$
$$HP_{incr} = N_{stages}\cdot hp_{stage,w}\cdot SG_{mix}$$

---

## 8. Ordenamiento de diseños (sin scoring)
Archivo: [bes/recommender/ranking.py](../backend/src/bes/recommender/ranking.py)

Las alternativas se ordenan por una clave **lexicográfica** de tres criterios
físicos. No hay pesos, ni escalas 0–10, ni dimensión de proveedor: el
fabricante es informativo. El criterio 2 solo desempata igualdades del 1, y el
3 solo igualdades de los dos primeros.

Base ingenieril (Brown §4.5325): el caudal de diseño debe caer lo más cerca
posible del punto de máxima eficiencia; operar lejos del BEP aumenta el empuje
axial y el desgaste, y reduce la vida útil.

### 8.1 Criterio 1 — distancia al BEP (ascendente)

$$d_{BEP} = \frac{|q - q_{BEP}|}{q_{BEP}}$$

### 8.2 Criterio 2 — eficiencia hidráulica (descendente)

$$\eta = \eta(q)\ \text{ leída de la curva de catálogo en el punto operativo}$$

### 8.3 Criterio 3 — potencia en el eje (ascendente)

$$HP_{eje} = N_{stages}\cdot hp_{stage,w}\cdot SG_{fluido}$$

### 8.4 Clave de ordenamiento

$$k = \left(d_{BEP},\ -\eta,\ HP_{eje}\right)$$

Ordenar ascendente por $k$ da la prioridad buscada. La clasificación
$d_{BEP} \le 10\,\%$ "óptimo", $\le 25\,\%$ "aceptable", $> 25\,\%$ "alejado"
es **solo para mostrar** y nunca interviene en el orden.

---

## Constantes de conversión usadas

| Constante | Valor | Uso |
|---|---|---|
| Cabeza ↔ presión | 2.31 ft/psi (÷SG) | Conversión PIP/P_wh a ft de columna |
| Presión ↔ gradiente | 0.433 psi/ft (×SG) | Empuje axial |
| bbl → ft³ | 5.615 | Velocidades, volúmenes |
| Agua a SC | 62.4 lb/ft³ | Densidades, SG de mezcla |
| Aire a SC | 0.0764 lb/scf | Masa de gas |
| g, g_c | 32.174 | Gravedad / fricción |
| 144 | (lbf/ft²)/psi | Gradiente → psi/ft |
| cp → lb/(ft·s) | 6.72×10⁻⁴ | Número de Reynolds |
