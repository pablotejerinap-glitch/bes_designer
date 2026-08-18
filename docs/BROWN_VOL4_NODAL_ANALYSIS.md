# Brown Vol. 4 — Nodal Systems Analysis

> Resumen del capítulo entregado (PDF p.15–196), generado a partir de OCR del scan original.
> Fuente: Brown, K.E. *The Technology of Artificial Lift Methods, Vol. 4: Production Systems Analysis (Nodal Systems Analysis)*. PennWell Books.
> Mapeo a los módulos del BES Designer indicado entre paréntesis. Foco en `bes/core/nodal_analysis.py`.

---

## Estructura del capítulo

```
Chapter 1  (p.15–18)       Introduction (Brown)
Chapter 2  (p.19–69)       Inflow Performance — IPR completa, presente y futura, transient
Chapter 3  (p.70–88)       Multiphase Flow in Pipes — vertical, horizontal, inclinado
Chapter 4  (p.89–196+)     Nodal Systems Analysis — aplicaciones
   §4.1   Introduction
   §4.2   Oil Well Example — solution at every node
   §4.27  Tapered Strings
   §4.28  Surface Chokes & Safety Valves
   §4.3   Injection Wells (water + gas)
   §4.4   Gas Well Example
   §4.5   Gravel-Packed Wells
```

---

## Chapter 1 — Introduction (Brown)

**Concepto central de Nodal Analysis** (también llamado "production systems analysis" / "production optimization"):

> Determinar el caudal al que producirá un pozo de petróleo o gas, evaluando el efecto de cada componente del sistema (tubing, flowline, separator, chokes, safety valves, restricciones de fondo, técnicas de completación incluyendo gravel pack y perforaciones convencionales). Cada componente se evalúa por separado y luego el sistema completo se optimiza.

**Posiciones del nodo (solution position):**

- **Fondo del pozo (P_wf):** aísla el componente de reservorio.
- **Cabeza del pozo (P_wh):** aísla el flowline.
- **Separador (P_sep):** evalúa optimización del separador y compresión.

**Insight clave:** todas las posiciones dan **el mismo caudal** — solo cambia qué componente se aísla visualmente.

**Hallazgos prácticos del libro que vale la pena tener presente:**

- Muchos sistemas de producción operan ineficientemente — flowlines muy chicas, tubings muy grandes o muy chicas.
- En ocean-floor completions el costo de cambiar tubing/flowline es prohibitivo → diámetros iniciales tienen que ser correctos.
- HP del compresor depende **de relación de compresión Y caudal de gas**. Subir P_sep para bajar relación de compresión a menudo aumenta HP total porque sube el caudal requerido.
- "Slim-hole" en gas-lift: regla de aumento de caudal con bajada de WHP ≈ `0.75 × ΔP_wh × PI`.
- Densidades de perforación: 4 spf típico es a menudo **insuficiente**. 16–24 spf o open-hole completions son comunes en Gulf Coast moderno.
- Comparación métodos de levantamiento artificial requiere **tubing intake curves** (capítulo 5 del libro).

---

## Chapter 2 — Inflow Performance → `bes/core/ipr.py`

### 2.1 Single-phase liquid (Darcy) — arriba del Pb

**Ecuación general** (Darcy con todos los términos):

```
        7.08 × 10⁻³ · k·h · (P̄ − P_wf)
q = ──────────────────────────────────────
     μ_o · B_o · [ln(r_e/r_w) − ¾ + S + a'q]
```

donde `a'q` es el término de turbulencia (no-Darcy). Brown §2.2 detalla:

- **Skin (S)** se compone de daño físico, skin tiempo-dependiente `S(q,t)`, y restricción de entrada.
- **Turbulencia `aq`** generalmente despreciable a flujos bajos / baja k. Importante a altos flujos.
- Forma de **Jones-Blount-Glaze**: `(P_R² − P_wf²)/q = aq + b` — útil para distinguir pérdidas por skin vs no-Darcy con un test multi-rate.

**Estimación rápida de PI** cuando solo se conoce kh:

| kh (md·ft) | Calidad |
|---|---|
| 0–100 | Pozo pobre |
| 100–1 000 | Pozo bueno |
| 1 000–5 000 | Pozo excelente |
| > 5 000 | Excede capacidad del piping |

Si `°API > 30`, aproximación: `J ≈ k·h` (con k en darcies, h en ft).

### 2.2 Two-phase flow — debajo del Pb

#### 2.221–2.222 Vogel (ya en `bes/core/ipr.py`)

```
q/q_max = 1 − 0.2(P_wf/P̄_R) − 0.8(P_wf/P̄_R)²
```

Funciona razonablemente bien hasta WC ≤ 50%. Sirve también para resolver `P_wf` directamente:

```
P_wf = 0.125·P̄_R · [−1 + √(81 − 80·q/q_max)]
```

#### 2.223 Combined linear + Vogel (NO implementada — retirada de la app)

Si `P̄_R > P_b`:

```
q_b = J · (P̄_R − P_b)        # Linear arriba de Pb
q_max = q_b + J·P_b/1.8       # Pendiente Vogel en Pb
q = q_b + (q_max − q_b)·[1 − 0.2(P_wf/P_b) − 0.8(P_wf/P_b)²]    # debajo de Pb
```

#### 2.224 Standing FE ≠ 1.0 (no implementado)

Para pozos dañados o estimulados (Flow Efficiency entre 0.5 y 1.5):

```
P_wf' = P̄_R − (P̄_R − P_wf) · FE
```

luego usar Vogel con `P_wf'`. **Para FE > 1 o flujos muy altos** la fórmula puede dar `P_wf'` negativo — Brown sugiere ecuación de Harrison o de Fetkovich tipo log-log.

#### 2.225 Couto FE ≠ 1 (Equation 2.41/2.42)

Generaliza Standing usando Darcy directamente:

```
q = α · k_o·h/(μ_o·B_o) · 1/[ln(0.472·r_e/r_w) + S]
       · (FE)·(1−R)·[1.8 − 0.8·FE·(1−R)]
```

donde `R = P_wf/P̄_R`. Ventaja: predice presente Y futuro IPR si conocés k_ro, μ_o, B_o futuras.

#### 2.226 Fetkovich 4-point test (ya en `bes/core/ipr.py`)

```
q = J' · (P̄_R² − P_wf²)ⁿ          → Eq. 2.52
```

El exponente `n` y `J'` se obtienen del log-log de `(P̄_R² − P_wf²)` vs `q`.

#### 2.227 Composite IPR con corte de agua (Petrobras) — **NO implementado**

Procedimiento del libro para `Fw > 0` (oil + water producidos):

- Para `0 ≤ q_t ≤ q_b`: relación lineal `P_wf = P̄_R − q_t/J`.
- Para `q_b < q_t < q_omax`: combinar Vogel para oil con linear para water:
  ```
  P_wf = F_o · P_wf_oil(q_t) + F_w · P_wf_water(q_t)
  ```
- Para `q_omax < q_t < q_tmax`: pendiente lineal `tan β` calculada geométricamente cerca de `q_omax`.

**Esto sería un upgrade interesante** para tu IPR module que actualmente no maneja water cut explícitamente en la curva.

### 2.23 Future IPR — métodos múltiples

Cinco aproximaciones para predecir IPR a presiones futuras:

| Método | Sección | Necesita |
|---|---|---|
| **Fetkovich** | §2.231 | Test multi-rate actual + asunción `k_ro ≈ lineal con P` |
| **Combinación Fetkovich + Vogel (Eckmier)** | §2.232 | Un solo test actual + Vogel |
| **Standing** | §2.233 | k_ro presente y futura (de balance de materia) + μ_o, B_o |
| **Couto** | §2.234 | k_ro, μ_o, B_o futuros |
| **Pivot Point (Uhri-Blount)** | §2.235 | **Dos tests** a distintas presiones de yacimiento |

**Pivot Point** es elegante: el `dq/dP_wf` en `P_wf = P̄_R*` es invariante para un pozo a lo largo de su vida (definiendo `P̄_R*` como negativo cuando los gradientes convergen).

```
(q_max)_f = 0.2·P̄_R · (dq/dP_wf|_{P_wf=0})_f
```

Para tu proyecto: si querés sensibilidad/proyección a futuro de pozos depletantes, **Pivot Point es probablemente el más práctico** porque solo requiere dos tests de campo (no propiedades de roca).

### 2.24 Transient IPR

Para pozos de baja permeabilidad que tardan en alcanzar pseudo-steady-state. Tres regímenes:

```
transient → late-transient → pseudo-steady-state
```

Brown da ecuaciones para cuándo termina cada régimen. **Tight gas / shale** wells pueden permanecer en transient flow por años, lo que cambia drásticamente la IPR a lo largo del tiempo.

### 2.4 IPR para gas wells — Tight gas con MHF (massive hydraulic frac)

Procedimiento de **type-curve match** (Fig. 2.79 + Agarwal):

1. Plot `1/q` vs `t` en log-log.
2. Match contra type-curve para fractura finita.
3. Obtener `F_CD` (dimensionless fracture flow capacity), `X_f` (longitud media de fractura), y `k_f·w`.
4. Generar IPR futuras usando `1/q_D` a distintos tiempos.

Importante para tu proyecto si vas a aplicarlo a Vaca Muerta — **ahí casi todo es tight gas/oil con frac multi-etapa**.

---

## Chapter 3 — Multiphase Flow in Pipes → `bes/core/multiphase.py`

### 3.1 Ecuación general (vertical, inclinado, horizontal)

```
dP/dZ = (loss_elevation) + (loss_friction) + (loss_acceleration)

      = ρ_m·sin(θ)/g_c  +  f·ρ_m·V_m²/(2·g_c·d)  +  ρ_m·V_m·dV_m/(g_c·dZ)
```

- **Vertical:** elevación = 70–98% del total. Es la componente más difícil de calcular.
- **Horizontal:** elevación = 0; fricción domina.
- **Inclinado:** todos los componentes cuentan; solo la elevación se proyecta a vertical.

### 3.2 Vertical — correlaciones

Brown menciona como la más usada (y la base de tus gradient curves):

- **Hagedorn & Brown** (Fig. 3.3 — holdup correlation; Fig. 3.4 — friction factor).
- Densidad de mezcla: `ρ_m = ρ_L · H_L + ρ_g · (1 − H_L)`.
- Reynolds bifásico: `(N_Re)_TP = (1488 ρ_m V_m d)/μ_n` para fricción.

**Otras correlaciones citadas** (todas las ya tenés en mente para tu proyecto):

- Orkiszewski
- Duns & Ros
- Beggs & Brill (la más versátil — funciona para cualquier ángulo)
- Poettmann & Carpenter

### 3.3 Horizontal

- **Beggs & Brill** sigue siendo top.
- **Eaton et al.** (Fig. 3.12) — la mejor correlación de holdup horizontal.
- **Combinación Eaton-holdup + Dukler-friction** = excelente.
- **Lockhart-Martinelli** y **Baker** todavía usadas con modificaciones.

### 3.4 Inclined / directional wells

- Pozos desviados 60–70° pueden producir **30–35% menos** que un vertical equivalente para el mismo tubing.
- **Beggs-Brill** maneja correctamente la inclinación; sus pérdidas calculadas tienden a ser conservadoras (predicen menor caudal del real).
- Para vertical-flow holdup hasta ~35–40° de desviación se puede usar Hagedorn directamente; arriba de 40° hay que usar Beggs-Brill.

### 3.5 Restrictions / chokes — **muy relevante para nodal**

#### 3.5.1.1 Surface chokes (Gilbert formula)

```
P_wh = (435 · R^0.546 · q) / S^1.89
```

donde `S` = choke size en `64`-avos de pulgada, `R` = GLR (Mcf/bbl), `q` = b/d.

**Condición de aplicabilidad:** crítico/sónico cuando `P_downstream / P_wh ≤ 0.7`. Si no se cumple, usar ecuación subcritical (sub-sónica).

Variantes que el libro cita: **API-14B**, **Ashford & Pierce**, **Fortunati**, modelo de la **Universidad de Tulsa**, y la modificación de **Mach-Proaño-Brown**.

#### 3.5.2 Safety valves

Dos categorías:
- **Velocity-actuated** (diferencial-controlado): cierra cuando ΔP_choke supera valor preset.
- **Pressure-actuated** (similar a gas-lift valve): cierra cuando P en la válvula cae bajo umbral.

El libro entrega un **procedimiento completo** para diseñar válvulas de seguridad con nodal (§4.283):

1. Curva `P_safety_valve_arriba` vs `q` desde el separador.
2. Curva `P_safety_valve_abajo` vs `q` desde el reservorio.
3. ΔP normal vs ΔP emergencia.
4. ΔP creado por cada tamaño de orificio.
5. Cierre confiable: `ΔP_emergency − ΔP_normal ≥ 150 psi`.

---

## Chapter 4 — Nodal Systems Analysis applications → `bes/core/nodal_analysis.py`

### 4.2 Oil well example — todas las posiciones de nodo dan el mismo caudal

El libro toma **un solo problema** y lo resuelve desde 4 posiciones distintas para demostrar consistencia:

| Posición del nodo | Procedimiento |
|---|---|
| **P_wh (cabeza de pozo)** | Asumir `q`, calcular `P_wh` desde separador (horizontal traverse) **y** desde el yacimiento (IPR + tubing). Plot `P_wh` vs `q` para cada lado. Intersección = caudal real. |
| **P_wf (fondo de pozo)** | Asumir `q`, calcular `P_wf` desde IPR **y** desde separador (horizontal + tubing). Intersección = caudal. |
| **P_sep (separador)** | Asumir `q`, calcular `P_sep` requerida desde reservorio **y** desde sales line. |
| **P̄_R (reservorio)** | Inverso — asume `q`, suma todas las pérdidas hasta llegar a `P̄_R`. Útil para **proyectar a futuro depletion**. |

**El ejemplo de Brown** (datos clave que sirven como test de regresión):

```
Separador 100 psi
Flowline 3 000 ft × 2 in
Profundidad 5 000 ft (centro perforaciones)
GOR 400 scf/bbl
P̄_R 2 200 psi
PI = 1.0 b/d/psi (constante)
Tubing 2⅜ in
WOR = 0
Resultado: caudal de operación ≈ 900 b/d, P_wh ≈ 245 psi, P_wf ≈ 1 300 psi
```

→ **Sería un excelent test de integración** para `bes/core/nodal_analysis.find_operating_point()`. Si pasás los inputs anteriores, el caudal calculado debería ser ~900 b/d ±5 %.

### 4.27 Tapered strings (sección que puede agregar valor a tu app)

Pozos con liner abajo + tubing más grande arriba. Procedimiento:

1. Nodo en la posición del taper (ej. 3 500 ft, top del liner).
2. Convergir desde ambos extremos:
   - **Above-taper:** desde separador → top of taper.
   - **Below-taper:** desde reservorio → bottom of taper.
3. Plot ambas curvas; intersección = caudal.

**Resultado típico del ejemplo:** 2⅞" arriba + 2⅜" abajo da 1 020 b/d vs solo 2⅜" daba 900 b/d. Pero 3½" + 2⅜" da solo 1 045 b/d (incremento marginal y mayor riesgo de heading).

### 4.28 Surface chokes & safety valves

Ya cubierto arriba. La regla para safety valves (`ΔP_emergency − ΔP_normal ≥ 150 psi`) es relevante si querés agregar un módulo de safety valve sizing al proyecto.

### 4.3 Injection wells (water + gas) — **NO implementado en BES Designer**

Brown muestra que nodal analysis se aplica igual a inyectores:

- **IPR de inyección:** `q_inj = J · (P_wf − P̄_R)` (signo invertido).
- Tubing intake curve a la inversa: presión vs profundidad **decrece** hacia abajo.
- Solución exactamente análoga a la del productor.

**Aplicación más útil en tu app:** evaluar wells convertidos de productor a inyector (típico en yacimientos maduros de Neuquén).

### 4.4 Gas well example

Misma estructura, usa **Cullender-Smith** para gas dry vertical. Análisis del ejemplo numérico:

```
P̄_R = 5 200 psi
Tubing 2.441" ID, profundidad 10 000 ft
P_wh = 1 000 psi → q = 28.6 MMscfd
P_wh = 200 psi  → q = 29.3 MMscfd  (diferencia despreciable, no vale la pena comprimir)
P_wh = 3 000 psi → q = 21 MMscfd

Tubing 2.992" ID, P_wh = 1 000 psi → q = 45.6 MMscfd  (vs 28.6 con 2.441")
```

**Insight:** para gas wells con buena permeabilidad, **el tamaño de tubing domina sobre la WHP**. Para un pozo gasífero malo (low k), bajar WHP es lo que importa.

### 4.5 Gravel-packed wells (gas + oil)

**Esto sí no lo tenés** en el proyecto y para Vaca Muerta puede ser irrelevante (formaciones consolidadas), pero para campos convencionales del Comahue es muy aplicable.

#### Ecuaciones Jones-Blount-Glaze (linear flow a través del gravel pack)

**Oil:**
```
P_wfs − P_wf = ΔP = a·q² + b·q

a = (9.08 × 10⁻¹³ · β · B_o² · ρ_o · L) / A²
b = (μ_o · B_o · L) / (1.127 × 10⁻³ · k_g · A)
β = 1.47 × 10⁷ / k_g^0.55
```

**Gas:**
```
P_wfs² − P_wf² = a·q² + b·q

a = (1.247 × 10⁻¹⁰ · β · γ_g · T·Z·L) / A²
b = (8.93 × 10³ · μ_g · T·Z·L) / (k_g · A)
β = 2.33 × 10¹⁰ / k_g^1.201
```

Donde:
- `L` = tunnel length = espesor del gravel pack (cement-to-screen-OD), típicamente ~0.25 ft.
- `A` = área total abierta al flujo = `(área 1 perforación) × (shot density) × (intervalo perforado)`.
- `k_g` (en md): **20-40 mesh = 100 000 md, 40-60 mesh = 45 000 md** (valores in-situ, ya derateados).

#### Diseño práctico

1. Construir IPR sin gravel pack.
2. Construir tubing intake curve.
3. Calcular sistema ΔP vs q (sin gravel pack).
4. Calcular ΔP del gravel pack para distintas combinaciones de **shot density** + **perforated interval**.
5. **Regla del libro:** ΔP_gravel_pack ≤ 200 psi para pack longevo. Algunos operadores aceptan hasta 300–500 psi.

**Ejemplo del libro (gas well):**
- 4 spf, 10 ft → ΔP = 1 240 psi (inaceptable)
- 4 spf, 20 ft → ΔP = 440 psi (aceptable)
- 8 spf, 10 ft → caudal 22 MMscfd con ΔP bajo (mejor opción)

---

## Mapeo a la arquitectura del BES Designer

| Sección Brown Vol 4 | Módulo del proyecto | Estado |
|---|---|---|
| §1 Concepto Nodal | `bes/core/nodal_analysis.py` (existe) | ✅ |
| §2.221 Vogel | `bes/core/ipr.py` | ✅ |
| §2.223 Combined | — (retirada: la app expone Linear, Vogel y Fetkovich) | ❌ |
| §2.224 Standing FE | — | ❌ NO implementado |
| §2.225 Couto FE | — | ❌ NO implementado |
| §2.226 Fetkovich 4-point | `bes/core/ipr.py` (IPRMethod.FETKOVICH) | ✅ |
| §2.227 Composite IPR (con WC) | — | ❌ NO implementado |
| §2.231 Fetkovich future IPR | — | ❌ NO |
| §2.232 Eckmier (Fetkovich+Vogel) | — | ❌ NO |
| §2.233 Standing future | — | ❌ NO |
| §2.234 Couto future | — | ❌ NO |
| §2.235 Pivot Point (Uhri-Blount) | — | ❌ NO (recomendado, solo necesita 2 tests) |
| §2.24 Transient IPR | — | ❌ NO |
| §3 Multiphase | `bes/core/multiphase.py` | ✅ |
| §3.5 Choke Gilbert | — | ❌ NO (relevante para análisis con choke superficial) |
| §4.2 Solution at all 4 nodes | `bes/core/nodal_analysis.py` | ✅ parcial |
| §4.27 Tapered strings | — | ❌ NO |
| §4.28 Safety valves | — | ❌ NO |
| §4.3 Injection wells | — | ❌ NO (interesante para Neuquén) |
| §4.5 Gravel pack ΔP (Jones-Blount-Glaze) | — | ❌ NO |

### Recomendaciones de implementación priorizadas para la tesis

**Críticas (poco esfuerzo, alto valor):**

1. **Composite IPR con water cut** (§2.227) — fácil, agrega capacidad real para pozos maduros. Te dejo las ecuaciones arriba.
2. **Standing FE ≠ 1.0** (§2.224) — 1 ecuación + extensión de Harrison para FE altos. Permite modelar pozos dañados/estimulados.
3. **Pivot Point** (§2.235) — futuro IPR con solo 2 tests, sin necesidad de propiedades de roca futuras.
4. **Test de regresión Brown §4.2** — el ejemplo numérico (PI=1.0, GOR=400, profundidad=5000 ft) debe dar 900 b/d. Es un test ideal para `nodal_analysis.find_operating_point`.

**Alto valor para defensa de tesis:**

5. **Tapered strings** (§4.27) — pocos software comerciales lo manejan bien y es realista en pozos profundos.
6. **Surface choke con Gilbert** (§3.511) — agrega un módulo de análisis de chokes; muy útil para optimizar producción.
7. **Gravel pack ΔP** (§4.5) — diferenciador para pozos no consolidados (bastante común en zonas de Comahue).

**Para futuras versiones / nice-to-have:**

8. Safety valve sizing (§4.28) — relevante para offshore o pozos con regulaciones estrictas.
9. Future IPR con Fetkovich (§2.231) — proyección de declinación.
10. Injection wells (§4.3) — extensión natural del recomendador.

---

## Caveat sobre el OCR

Este resumen se generó a partir del OCR (Tesseract en inglés) del PDF escaneado original. **162 de 182 páginas** se OCR-earon exitosamente; las 20 páginas restantes (p.19, 84, 87, 96-99, 116, 120, 140-145, 173-174, 192-196) fallaron en la extracción de texto pero las JPEGs tienen contenido — son páginas con figuras pesadas o tablas complejas, no blank pages.

Los errores típicos del OCR:
- Subíndices y caracteres griegos a veces mal interpretados (γ ↔ y, ρ ↔ p, μ ↔ M).
- Tablas con números desplazados.
- Fórmulas con sub/super-índices Unicode pueden estar corruptas — verificar contra el PDF original si vas a citar fórmulas exactas en la tesis.

Si necesitás re-OCR de páginas específicas a mayor resolución, decime cuáles.
