# BES Designer — Compendio de Fórmulas

Todas las fórmulas implementadas en el motor de cálculo, con referencia al archivo
y línea donde viven y a la fuente bibliográfica. Notación: las unidades van entre
corchetes. Referencia base: Kermit Brown, *The Technology of Artificial Lift
Methods*, Vol. 2b, Cap. 4.5.

---

## 1. IPR — Inflow Performance Relationship
Archivo: [core/ipr.py](../core/ipr.py)

### 1.1 IPR Lineal (Darcy) — [ipr.py:21](../core/ipr.py#L21)
Válida para flujo monofásico (P_wf ≥ P_b).

$$q = J \cdot (P_r - P_{wf})$$

### 1.2 Vogel — [ipr.py:45](../core/ipr.py#L45)
Drive por gas en solución (P_wf < P_b). *Vogel, JPT (1968).*

$$\frac{q}{q_{max}} = 1 - 0.2\left(\frac{P_{wf}}{P_r}\right) - 0.8\left(\frac{P_{wf}}{P_r}\right)^2$$

q_max a partir de un punto de ensayo — [ipr.py:75](../core/ipr.py#L75):

$$q_{max} = \frac{q_{test}}{1 - 0.2\,(P_{wf}/P_r) - 0.8\,(P_{wf}/P_r)^2}$$

### 1.3 IPR Combinada (Standing) — [ipr.py:112](../core/ipr.py#L112)
Lineal arriba de P_b, Vogel abajo, con continuidad en P_b. *Standing, JPT (1970).*

$$P_{wf} \ge P_b:\quad q = J\,(P_r - P_{wf})$$

$$P_{wf} < P_b:\quad q = q_b + \frac{J\,P_b}{1.8}\left[1 - 0.2\frac{P_{wf}}{P_b} - 0.8\left(\frac{P_{wf}}{P_b}\right)^2\right],\quad q_b = J\,(P_r - P_b)$$

### 1.4 Fetkovich — [ipr.py:155](../core/ipr.py#L155)
*Fetkovich (1973).*

$$q = C\,(P_r^2 - P_{wf}^2)^n$$

### 1.5 AOF (caudal a P_wf = 0) — [ipr.py:331](../core/ipr.py#L331)

| Método | AOF |
|---|---|
| Lineal | $J\,P_r$ |
| Vogel | $J\,P_r / 1.8$ |
| Combinada | $J\,(P_r - P_b) + J\,P_b/1.8$ |
| Fetkovich | $C\,P_r^{2n}$ |

> El P_wf para un caudal objetivo se invierte analíticamente (lineal) o por
> `scipy.optimize.brentq` (resto) — [ipr.py:188](../core/ipr.py#L188).

---

## 2. PVT — Propiedades de los fluidos
Archivo: [core/pvt.py](../core/pvt.py)

### 2.1 Gravedad específica del petróleo — [pvt.py:37](../core/pvt.py#L37)

$$\gamma_o = \frac{141.5}{131.5 + API}$$

### 2.2 GOR en solución (Standing) — [pvt.py:62](../core/pvt.py#L62)
Con P_eff = min(P, P_b). *Standing (1947).*

$$R_s = \gamma_g\left[\left(\frac{P_{eff}}{18.2} + 1.4\right)\,10^{\,0.0125\,API - 0.00091\,T}\right]^{1.2048}$$

(El exponente 1.2048 = 1/0.83.)

### 2.3 Presión de burbuja (inversa de Standing) — [pvt.py:103](../core/pvt.py#L103)

$$P_b = 18.2\left[\left(\frac{R_s}{\gamma_g}\right)^{0.83} 10^{\,0.00091\,T - 0.0125\,API} - 1.4\right]$$

### 2.4 Factor volumétrico del petróleo B_o (Standing) — [pvt.py:146](../core/pvt.py#L146)

$$F = R_s\left(\frac{\gamma_g}{\gamma_o}\right)^{0.5} + 1.25\,T$$
$$B_o = 0.9759 + 0.00012\,F^{1.2}$$

### 2.5 Factor z del gas (Dranchuk–Abou-Kassem) — [pvt.py:185](../core/pvt.py#L185)
Pseudo-críticas de Standing — [pvt.py:42](../core/pvt.py#L42):

$$P_{pc} = 677 + 15\,\gamma_g - 37.5\,\gamma_g^2,\qquad T_{pc} = 168 + 325\,\gamma_g - 12.5\,\gamma_g^2$$

Reducidas: $P_{pr} = P/P_{pc}$, $T_{pr} = (T+460)/T_{pc}$, densidad reducida $\rho_r = 0.27\,P_{pr}/(z\,T_{pr})$.

Ecuación de estado DAK (11 constantes, resuelta por iteración):

$$z = 1 + C_1\rho_r + C_2\rho_r^2 - C_3\rho_r^5 + C_4$$

$$C_1 = A_1 + \tfrac{A_2}{T_{pr}} + \tfrac{A_3}{T_{pr}^3} + \tfrac{A_4}{T_{pr}^4} + \tfrac{A_5}{T_{pr}^5}$$
$$C_2 = A_6 + \tfrac{A_7}{T_{pr}} + \tfrac{A_8}{T_{pr}^2},\qquad C_3 = A_9\left(\tfrac{A_7}{T_{pr}} + \tfrac{A_8}{T_{pr}^2}\right)$$
$$C_4 = A_{10}\,(1 + A_{11}\rho_r^2)\,\frac{\rho_r^2}{T_{pr}^3}\,e^{-A_{11}\rho_r^2}$$

Semilla inicial por Papay. *Dranchuk & Abou-Kassem, JCPT (1975).*

### 2.6 Factor volumétrico del gas B_g — [pvt.py:234](../core/pvt.py#L234)

$$B_g = 0.00504\,\frac{z\,(T+460)}{P}\quad [\text{bbl/scf}]$$

### 2.7 Factor volumétrico del agua B_w (McCain) — [pvt.py:265](../core/pvt.py#L265)

$$B_w = 1 + 1.21\times10^{-4}\,\Delta T + 1.0\times10^{-6}\,\Delta T^2 - 3.33\times10^{-6}\,P,\quad \Delta T = T - 60$$

### 2.8 Viscosidad del petróleo (Beggs–Robinson) — [pvt.py:298](../core/pvt.py#L298)
Muerta:

$$X = T^{-1.163}\,e^{\,6.9824 - 0.04658\,API},\qquad \mu_{od} = 10^X - 1\ [\text{cp}]$$

Viva (saturada) — [pvt.py:327](../core/pvt.py#L327):

$$a = 10.715\,(R_s + 100)^{-0.515},\quad b = 5.44\,(R_s + 150)^{-0.338}$$
$$\mu_{ob} = a\,\mu_{od}^{\,b}$$

### 2.9 Densidades in-situ — [pvt.py:420](../core/pvt.py#L420)

$$\rho_o = \frac{62.4\,\gamma_o + 0.0136\,R_s\,\gamma_g}{B_o},\qquad \rho_w = \frac{62.4\,\gamma_w}{B_w}$$
$$\rho_g = 2.70\,\frac{\gamma_g\,P}{z\,(T+460)}$$

### 2.10 Densidad de mezcla — [pvt.py:436](../core/pvt.py#L436)
Balance de masa sobre 1 STB de líquido total de superficie; SG de mezcla = ρ_mix / 62.4.

---

## 3. Flujo multifásico (traverse de presión)
Archivo: [core/multiphase.py](../core/multiphase.py)

### 3.1 Velocidades superficiales — [multiphase.py:123](../core/multiphase.py#L123)
Área: $A = \frac{\pi}{4}(d/12)^2$. Con caudales llevados a condiciones de reservorio:

$$v_{sl} = \frac{q_{l,res}\cdot 5.615}{86400\,A},\qquad v_{sg} = \frac{q_{g,res}\cdot 5.615}{86400\,A}\ [\text{ft/s}]$$
$$v_m = v_{sl} + v_{sg},\qquad \lambda_l = v_{sl}/v_m$$

### 3.2 Factor de fricción Moody (Churchill 1977) — [multiphase.py:91](../core/multiphase.py#L91)

$$f_D = 8\left[\left(\frac{8}{Re}\right)^{12} + (A+B)^{-1.5}\right]^{1/12}$$
$$A = \left[2.457\ln\frac{1}{(7/Re)^{0.9} + 0.27\,\varepsilon/D}\right]^{16},\qquad B = \left(\frac{37530}{Re}\right)^{16}$$

Laminar (Re < 2100): $f_D = 64/Re$.

### 3.3 Gradiente general — [multiphase.py:282](../core/multiphase.py#L282)

$$\frac{dP}{dz} = \underbrace{\frac{\rho_{slip}\sin\theta}{144}}_{\text{gravedad}} + \underbrace{\frac{f_D\,\rho_{ns}\,v_m^2}{2\,g_c\,D\cdot144}}_{\text{fricción}}\ [\text{psi/ft}]$$

con $\rho_{slip} = \rho_l H_L + \rho_g(1-H_L)$ y $\rho_{ns} = \rho_l\lambda_l + \rho_g\lambda_g$.

### 3.4 Hagedorn–Brown (1965) — [multiphase.py:161](../core/multiphase.py#L161)
Números adimensionales:

$$N_{vl} = 1.938\,v_{sl}\,(\rho_l/\sigma)^{0.25},\quad N_{vg} = 1.938\,v_{sg}\,(\rho_l/\sigma)^{0.25}$$
$$N_d = 120.872\,D\,(\rho_l/\sigma)^{0.25},\quad N_L = 0.15726\,\mu_l\,(1/(\rho_l\sigma^3))^{0.25}$$

Holdup por drift-flux de Zuber–Findlay (régimen slug/churn/anular):

$$H_L = 1 - \frac{v_{sg}}{C_0\,v_m + V_d},\quad C_0 = 1.2,\quad V_d = 0.35\sqrt{g\,D\,(\rho_l-\rho_g)/\rho_l}$$

Burbuja (Griffith–Wallis): holdup analítico con velocidad de ascenso V_s = 0.8 ft/s.
Límite de burbuja $L_B = \max(0.25,\ 1.071 - 0.2218\,v_m^2/D)$.

### 3.5 Beggs–Brill (1973) — [multiphase.py:291](../core/multiphase.py#L291)
Número de Froude: $N_{Fr} = v_m^2/(g\,D)$. Holdup horizontal H_L(0) por régimen:

$$H_{L,seg} = \frac{0.980\,\lambda_l^{0.4846}}{N_{Fr}^{0.0868}},\quad H_{L,int} = \frac{0.845\,\lambda_l^{0.5351}}{N_{Fr}^{0.0173}},\quad H_{L,dis} = \frac{1.065\,\lambda_l^{0.5824}}{N_{Fr}^{0.0609}}$$

Corrección por inclinación: $\psi = 1 + C\,[\sin(1.8\theta) - \tfrac13\sin^3(1.8\theta)]$, $H_L = H_L(0)\,\psi$.
Fricción bifásica: $f_{tp} = f_{ns}\,e^{S}$ con S función de $y = \lambda_l/H_L^2$.
*Coeficientes según Brill & Mukherjee, SPE Monograph 17 (1999).*

### 3.6 Poettmann–Carpenter (1952) — [multiphase.py:574](../core/multiphase.py#L574)
Mezcla homogénea (sin slip). Fricción Fanning ajustada a la carta:

$$f_{PC} = 0.030\,N_\rho^{-0.19},\quad N_\rho = \rho_{ns}\,v_m\,D,\quad f_{PC}\in[0.005,\,0.065]$$

### 3.7 Duns–Ros (1963) — [multiphase.py:657](../core/multiphase.py#L657)
Grupos adimensionales (N_d con exponente 0.5):

$$N_{Lv} = 1.938\,v_{sl}(\rho_l/\sigma)^{0.25},\ N_{gv} = 1.938\,v_{sg}(\rho_l/\sigma)^{0.25},\ N_d = 120.7\,D\,(\rho_l/\sigma)^{0.50}$$

Fronteras de régimen: $L_1 = 1 + 0.4\,N_{Lv}$, $L_2 = \max(L_1 + 0.5,\ 1.5 + 0.5\,N_{Lv} + 0.018\,N_d)$.

### 3.8 Integración del traverse — [multiphase.py:467](../core/multiphase.py#L467)
Marcha por n segmentos, gradiente evaluado en el punto medio con 3 pasos correctores
para el PVT dependiente de la presión. Subiendo: $P_{i+1} = P_i - \frac{dP}{dz}\,dz$;
bajando: $P_{i+1} = P_i + \frac{dP}{dz}\,dz$. Temperatura lineal con la profundidad.

### 3.9 Tensión interfacial — [multiphase.py:69](../core/multiphase.py#L69)
*Baker & Swerdloff (1956) + corrección de Ramey por gas disuelto:*

$$\sigma_{68} = 39 - 0.2571\,API,\quad \sigma_{100} = 37.5 - 0.2571\,API$$
$$\sigma_{live} = \sigma_{dead}\,e^{-0.000328\,R_s}$$

---

## 4. TDH — Total Dynamic Head
Archivo: [core/tdh.py](../core/tdh.py) — Brown §4.5324

### 4.1 SG del líquido en superficie — [tdh.py:37](../core/tdh.py#L37)

$$SG_l = \gamma_o\,(1 - f_w) + \gamma_w\,f_w$$

### 4.2 Fricción en tubing (Hazen–Williams) — [tdh.py:10](../core/tdh.py#L10)
Con $q_{gpm} = q_{bpd}\cdot 42/1440$ y C = 120 (acero de diseño):

$$h_f = 0.2083\left(\frac{100}{C}\right)^{1.852}\frac{q_{gpm}^{1.852}}{d^{4.8655}}\cdot\frac{L}{100}\ [\text{ft}]$$

### 4.3 TDH — [tdh.py:43](../core/tdh.py#L43)

$$\text{TDH} = \underbrace{\left(D_{pump} - \frac{PIP\cdot2.31}{SG_l}\right)}_{\text{elevación vertical}} + \underbrace{h_f}_{\text{fricción}} + \underbrace{\frac{P_{wh}\cdot2.31}{SG_l}}_{\text{cabezal}}\ [\text{ft}]$$

---

## 5. Diseño de la bomba
Archivo: [core/pump_design.py](../core/pump_design.py)

### 5.1 Número de etapas — [pump_design.py:45](../core/pump_design.py#L45)

$$N_{stages} = \left\lceil \frac{\text{TDH}}{h_{stage}(q)} \right\rceil$$

### 5.2 Potencia al eje — [pump_design.py:62](../core/pump_design.py#L62)
hp/etapa del catálogo está referido al agua (SG = 1); se corrige por SG del fluido:

$$HP = N_{stages}\cdot hp_{stage}(q)\cdot SG_{fluido}$$

### 5.3 Proximidad al BEP — [pump_design.py:86](../core/pump_design.py#L86)
Cerca del BEP si $|q - q_{BEP}|/q_{BEP} \le 0.15$.

### 5.4 Corrección por viscosidad (Hydraulic Institute) — [pump_design.py:118](../core/pump_design.py#L118)
Conversión SSU → cSt (ASTM D2161):

$$\text{SSU} < 100:\ cSt = 0.226\,\text{SSU} - 195/\text{SSU}$$
$$\text{SSU} \ge 100:\ cSt = 0.220\,\text{SSU} - 135/\text{SSU}$$

Factores C_Q, C_H, C_E interpolados de tabla HI; potencia:

$$hp_{factor} = \frac{C_Q\,C_H}{C_E}$$

(Para μ ≤ 20 SSU todos los factores valen 1.)

---

## 6. Diseño eléctrico
Archivo: [core/electrical.py](../core/electrical.py) — Brown §4.5325–4.5326

### 6.1 Selección de cable — [electrical.py:112](../core/electrical.py#L112)
- Ampacidad: $\text{max\_amps} \ge I_{motor}\cdot 1.25$ (derateo NEC por carga continua)
- Temperatura: $\text{max\_temp} \ge T_{fondo} + 25\,°F$
- Ajuste físico: espesor del cable plano ≤ claro anular $(ID_{casing} - OD_{motor})/2$
- Longitud de cable: $L = D_{pump} + 100\ \text{ft}$

### 6.2 Caída de tensión en el cable — [electrical.py:183](../core/electrical.py#L183)

$$\Delta V = v_{drop/A/1000ft}(T)\cdot I \cdot \frac{L}{1000}\ [\text{V}]$$

### 6.3 Tensión en superficie — [electrical.py:209](../core/electrical.py#L209)

$$V_s = (V_{motor} + \Delta V_{cable})\left(1 + \frac{\text{pérdida\_trafo\,\%}}{100}\right),\quad \text{pérdida} = 2.5\,\%$$

### 6.4 Potencia aparente (trafo) — [electrical.py:229](../core/electrical.py#L229)

$$kVA = \frac{V_s\,I\,\sqrt{3}}{1000}\quad (\text{trifásico})$$

### 6.5 Selección de motor — [electrical.py:283](../core/electrical.py#L283)
- $HP_{rating} \ge HP_{req}\cdot 1.10$ (10 % de margen de placa)
- $OD_{motor} \le OD_{pump}\cdot 1.20$
- Claro de cable: $OD_{motor} + 2\cdot e_{cable,min} \le ID_{casing}$
- Tensión objetivo: ≤70 HP → 800 V; 71–200 HP → 1200 V; >200 HP → 2000 V

### 6.6 Empuje axial sobre el protector — [electrical.py:355](../core/electrical.py#L355)
*Takács, ESP Manual:*

$$\Delta P_{pump} = \text{TDH}\cdot 0.433\cdot SG,\qquad F_{axial} = \Delta P_{pump}\cdot\frac{\pi}{4}d_{shaft}^2\cdot 1.20\ [\text{lbs}]$$

(El factor 1.20 es el margen de diseño; d_shaft según la serie de la bomba.)

---

## 7. Manejo de gas
Archivo: [core/gas_handling.py](../core/gas_handling.py) — Brown §4.53102–4.53103

### 7.1 Porcentaje de ingestión de gas (GIP) — [gas_handling.py:37](../core/gas_handling.py#L37)

$$GIP = \left(1 - \frac{V_{gas,vented}}{V_{gas,intake}}\right)(1 - \eta_{sep})$$

### 7.2 Riesgo de gas lock — [gas_handling.py:73](../core/gas_handling.py#L73)
fg < 0.10 → bajo; 0.10–0.30 → medio; > 0.30 → alto.

### 7.3 Factor de deterioro de la bomba — [gas_handling.py:119](../core/gas_handling.py#L119)

$$f_{det} = \begin{cases} 1.0 & fg < 0.10 \\ 1.0 - \dfrac{fg - 0.10}{0.20}\cdot0.30 & 0.10 \le fg \le 0.30 \\ 0.5 & fg > 0.30 \end{cases}$$

### 7.4 Fracción volumétrica de gas libre en admisión — [gas_handling.py:526](../core/gas_handling.py#L526)

$$f_g = \frac{V_{gas}}{V_{oil} + V_{water} + V_{gas}},\quad V_{gas} = (1 - f_w)\,(GOR - R_s)\,B_g$$

### 7.5 Diseño por incrementos de presión — [gas_handling.py:244](../core/gas_handling.py#L244)
Se divide [P_intake → P_discharge] en pasos de 200 psi. Por incremento, con la mezcla
evaluada en el punto medio:

$$q_{res} = q_{target}\cdot V_{total},\qquad \text{gradiente} = \frac{\rho_{mix}}{144}\ [\text{psi/ft}]$$
$$\text{psi/etapa} = h_{stage}\cdot\text{gradiente},\qquad N_{stages} = \left\lceil\frac{\Delta P}{\text{psi/etapa}}\right\rceil$$
$$HP_{incr} = N_{stages}\cdot hp_{stage,w}\cdot SG_{mix}$$

---

## 8. Scoring (ranking de diseños)
Archivo: [recommender/scoring.py](../recommender/scoring.py)

Pesos: eficiencia 40 %, flexibilidad 30 %, preferencia de proveedor 30 %.

### 8.1 Eficiencia — [scoring.py:25](../recommender/scoring.py#L25)

$$S_{ef} = \text{clip}(\eta\cdot 10,\ 0,\ 10)$$

### 8.2 Flexibilidad (proximidad al BEP) — [scoring.py:39](../recommender/scoring.py#L39)

$$S_{flex} = 10\left(1 - \frac{|q - q_{BEP}|}{(q_{max} - q_{min})/2}\right),\quad \text{acotado a } [0,10]$$

### 8.3 Preferencia de proveedor — [scoring.py:63](../recommender/scoring.py#L63)

$$S_{prov} = \begin{cases} 10 & \text{sin preferencia} \\ 10 & \text{fabricante} = \text{preferido} \\ 5 & \text{en otro caso} \end{cases}$$

### 8.4 Score global — [scoring.py:84](../recommender/scoring.py#L84)

$$S = \frac{\sum_k w_k\,S_k}{\sum_k w_k} = 0.40\,S_{ef} + 0.30\,S_{flex} + 0.30\,S_{prov}$$

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
