# BES Designer — Metodología de Cálculo

**Versión:** 1.0.0  
**Referencia principal:** Kermit Brown, *The Technology of Artificial Lift Methods*, Vol. 2b (1984)

---

## 1. Referencias Bibliográficas

| # | Referencia | Uso en BES Designer |
|---|---|---|
| [1] | **Brown, K.E.** (1984). *The Technology of Artificial Lift Methods, Vol. 2b: Electric Submersible Pumping Systems*. PennWell Books, Tulsa. | Metodología completa de diseño ESP: TDH, selección de bomba, etapas, diseño eléctrico, manejo de gas. Referencia principal del proyecto. |
| [2] | **Takacs, G.** (2009). *Electrical Submersible Pumps Manual: Design, Operations, and Maintenance* (2nd ed.). Gulf Professional Publishing. | Procedimientos de diseño motor-cable-transformador; correcciones por viscosidad; criterios de operación. |
| [3] | **Standing, M.B.** (1947). A Pressure-Volume-Temperature Correlation for Mixtures of California Oils and Gases. *API Drilling and Production Practice*, 275–287. | Correlaciones Bo (factor volumétrico del petróleo) y Rs (gas en solución); estimación de la presión de burbuja Pb. |
| [4] | **Vogel, J.V.** (1968). Inflow Performance Relationships for Solution-Gas Drive Wells. *Journal of Petroleum Technology*, 20(1), 83–92. SPE-1476. | Correlación IPR para pozos con drive por gas en solución (flujo bifásico en la formación). |
| [5] | **Dranchuk, P.M. & Abou-Kassem, H.** (1975). Calculation of z-Factors for Natural Gases Using Equations of State. *Journal of Canadian Petroleum Technology*, 14(3), 34–36. JCPT-75-03-03. | Factor de compresibilidad del gas (z-factor) para cálculo del volumen en condiciones de reservorio. |
| [6] | **Hagedorn, A.R. & Brown, K.E.** (1965). Experimental Study of Pressure Gradients Occurring During Continuous Two-Phase Flow in Small-Diameter Vertical Conduits. *Journal of Petroleum Technology*, 17(4), 475–484. SPE-940. | Correlación de gradiente de presión multifásico para calcular la presión de admisión de la bomba (PIP). |
| [7] | **Beggs, H.D. & Brill, J.P.** (1973). A Study of Two-Phase Flow in Inclined Pipes. *Journal of Petroleum Technology*, 25(5), 607–617. SPE-4007. | Correlación de flujo multifásico en tuberías inclinadas; complementa Hagedorn-Brown para pozos desviados. |
| [8] | **Beggs, H.D. & Robinson, J.R.** (1975). Estimating the Viscosity of Crude Oil Systems. *Journal of Petroleum Technology*, 27(9), 1140–1141. SPE-5434. | Correlaciones de viscosidad del crudo muerto, saturado y bajo-saturado en función de temperatura y presión. |
| [9] | **Hydraulic Institute** (1994). *Pump Standards: Effects of Liquid Viscosity on Centrifugal Pump Performance*. HI Standard 9.6.7. | Factores de corrección CQ, CH, CE para desempeño de bomba centrífuga con fluidos viscosos. |
| [10] | **Fetkovich, M.J.** (1973). The Isochronal Testing of Oil Wells. SPE Paper 4529, Fall Meeting of SPE, Las Vegas. | Correlación IPR empírica para pozos sin drive por gas en solución (Fetkovich). |

---

## 2. Correlaciones Implementadas

### 2.1 Relaciones de Desempeño de Afluencia (IPR)

#### LINEAR (Darcy)
Aplicable cuando Pwf > Pb (sin gas libre en la formación).

```
q = PI · (Pr − Pwf)
```

donde `PI` [STB/d/psi] es el índice de productividad medido en prueba.

#### VOGEL
Aplicable cuando Pwf < Pb (drive por gas en solución). Ref. [4].

```
q / q_max = 1 − 0.2·(Pwf/Pr) − 0.8·(Pwf/Pr)²
```

donde `q_max = PI·Pr / 1.8` es el caudal máximo (Pwf = 0).

#### COMBINED (recomendado)
Linear para Pwf > Pb; Vogel para Pwf ≤ Pb, garantizando continuidad en Pb.

#### FETKOVICH
```
q = C · (Pr² − Pwf²)ⁿ
```

donde C y n se obtienen de una prueba isocronal. Ref. [10].

---

### 2.2 PVT — Standing (1947)

#### Gas en solución Rs [scf/STB]  Ref. [3]
```
Rs = γg · [P / (18.2·(10^(0.0125·API) / 10^(0.00091·T))) + 1.4]^1.204
```

#### Factor volumétrico del petróleo Bo [RB/STB]  Ref. [3]
```
Bo = 0.972 + 0.000147 · [Rs·(γg/γo)^0.5 + 1.25·T]^1.175
```

#### Presión de burbuja Pb [psi]  Ref. [3]
```
Pb = 18.2 · [(Rs/γg)^0.83 · 10^(0.00091·T) / 10^(0.0125·API) − 1.4]
```

---

### 2.3 z-factor — Dranchuk-Abou-Kassem (1975)

Solución implícita de la ecuación de estado modificada de Benedict-Webb-Rubin. Ref. [5].

```
z = 1 + c₁(ρr)·ρr + c₂(ρr)·ρr² − c₃(ρr)·ρr⁵ + c₄(ρr)
```

donde `ρr = 0.27·Ppr / (z·Tpr)` (densidad reducida), Ppr y Tpr son presiones y temperaturas pseudo-reducidas (regla de Kay).

**Rango de validez:** 1.05 ≤ Tpr ≤ 3.0; 0.2 ≤ Ppr ≤ 30.

---

### 2.4 Viscosidad del Crudo — Beggs-Robinson (1975)

#### Viscosidad crudo muerto μod [cp]  Ref. [8]
```
x = 10^(3.0324 − 0.02023·API) / T^1.163
μod = 10^x − 1
```

#### Viscosidad crudo saturado μob [cp]  Ref. [8]
```
μob = A · μod^B
A = 10.715 · (Rs + 100)^(−0.515)
B = 5.44  · (Rs + 150)^(−0.338)
```

#### Viscosidad crudo sub-saturado (P > Pb)
```
μo = μob · (P/Pb)^m
m  = 2.6 · P^1.187 · exp(−11.513 − 8.98×10⁻⁵ · P)
```

---

### 2.5 Gradiente de Presión Multifásico — Hagedorn-Brown (1965)

Calcula el gradiente de presión en tubería vertical para flujo bifásico gas-líquido. Ref. [6].

```
dP/dz = ρm·g/gc + f·ρn·vm²/(2·gc·d) + ρm·vm·dvm/dz
```

La densidad de mezcla `ρm` se determina con el holdup de líquido Hl mediante correlaciones tabuladas de Hagedorn-Brown (número de líquido, número de velocidad de gas, coeficiente de holdup).

Implementación: integración numérica por pasos de 100 ft desde la profundidad de la bomba hasta la superficie.

#### Beggs-Brill (1973) — pozos desviados  Ref. [7]
Para pozos con inclinación > 10°, se aplica la corrección de Beggs-Brill sobre el holdup:

```
Hl(θ) = Hl(0) · ψ(θ)
ψ(θ)  = 1 + C·[sin(1.8θ) − sin³(1.8θ)/3]
```

---

### 2.6 Cabeza Dinámica Total (TDH) — Brown §4.5324

```
TDH = H_lift + H_friction + H_wh
```

| Componente | Ecuación |
|---|---|
| **Elevación vertical** H_lift | pump_depth − PIP·2.31/SG_liq [ft] |
| **Fricción en tubing** H_friction | Hazen-Williams (ver §2.7) |
| **Presión de cabezal** H_wh | Pwh·2.31/SG_liq [ft] |

---

### 2.7 Fricción en Tubing — Hazen-Williams

```
h_f = 0.2083 · (100/C)^1.852 · q_gpm^1.852 / d^4.8655 · L/100
```

donde `C = 120` (acero de diseño), `d` en pulgadas, `L` en pies, `q` en gpm.

---

### 2.8 Corrección por Viscosidad — Hydraulic Institute  Ref. [9]

Los catálogos de bomba están en agua (1 cP). Para fluidos viscosos se aplican:

```
Qc = CQ · Q_agua
Hc = CH · H_agua
Ec = CE · E_agua
```

Los factores CQ, CH, CE se interpolan de la tabla HI en función de la viscosidad cinemática en cSt (conversión desde SSU mediante ASTM D2161).

---

### 2.9 Gas en la Bomba (GIP) — Brown §4.53103

Fracción volumétrica de gas libre a las condiciones de la admisión:

```
GIP = V_gas / (V_gas + V_oil + V_water)
```

donde los volúmenes se calculan a condiciones downhole (P = PIP, T = T_bomba) usando Bo, Bw y Bg. El gas libre es el exceso sobre Rs:

```
V_gas = (GOR − Rs) · Bg · (1 − WC)
```

---

### 2.10 Scoring Multi-Criterio

Score global = Σ wᵢ · sᵢ / Σ wᵢ

| Dimensión | Peso | Criterio |
|---|---|---|
| Eficiencia | 0.40 | s_eff = η_bomba × 10 (0–1 → 0–10) |
| Flexibilidad | 0.30 | Distancia normalizada al BEP (10 en BEP, 0 en extremos) |
| Costo | 0.30 | Función inversa de HP total y número de etapas |

---

## 3. Suposiciones del Modelo

1. **Flujo estacionario.** El diseño asume condiciones de régimen permanente; no modela la respuesta transitoria al arranque ni al cambio de velocidad.

2. **Caudal de diseño fijo.** La bomba se diseña exactamente para `target_flow_rate`; la curva de sistema no se calcula explícitamente.

3. **Fluido incompresible en tubing.** La fricción en tubing (Hazen-Williams) asume fluido monofásico. El efecto del gas libre en la tubería se ignora en el TDH (la fase gas solo afecta el cálculo del PIP y el GIP).

4. **Temperatura lineal.** El perfil de temperatura en el pozo se asume lineal entre `wellhead_temp` y `bottom_hole_temp`.

5. **Sin slippage de gas en la bomba.** Para el cálculo de HP se asume que el gas libre pasa por la bomba sin cambio de fase. Los efectos de segregación fase-gas dentro del rodete no se modelan.

6. **Propiedades de fluido en superficie.** El GOR, WC y API son valores de condiciones estándar; la correlación Standing/DAK los convierte a condiciones de reservorio.

7. **Un solo intervalo de perforaciones.** El modelo no distingue múltiples intervalos de afluencia ni IPR compuesto.

8. **Bomba en posición vertical.** Las curvas de rendimiento del catálogo son para instalación vertical. Para desviaciones > 30°, se recomienda verificar con el fabricante.

9. **Potencia de motor = bomba × 1.15 mínimo.** El motor seleccionado tiene al menos 15 % de margen sobre la potencia requerida por la bomba.

10. **Cable de calibre uniforme.** Se asume un solo calibre AWG para toda la longitud del cable; no se modela cable tapering.

---

## 4. Limitaciones Conocidas

| Limitación | Impacto | Mitigación |
|---|---|---|
| Catálogos de bomba aproximados | TDH y etapas pueden diferir ±15–30 % del libro de Brown | Usar catálogos reales del fabricante para diseño definitivo |
| Sin correlación de emulsión | Viscosidad de la mezcla agua-crudo puede subestimarse | Medir viscosidad de la emulsión y usar el campo de corrección HI |
| Sin cálculo de fuerza axial | No se verifica la carga sobre el sello/protector | Revisar el límite de empuje axial de la bomba con el fabricante |
| Temperatura de motor estimada | Se usa T_bottom_hole como temperatura del motor | La temperatura real del motor depende del flujo refrigerante; verificar con el fabricante |
| Sin modelo de degradación | No proyecta cambios de PI o GOR en el tiempo | Correr el análisis de sensibilidad para distintos escenarios de declinación |
| Hagedorn-Brown para baja tensión superficial | Puede sobreestimar el holdup de líquido con gas amargo | Usar Beggs-Brill manualmente si H₂S > 5 000 ppm |
| Un solo fase de motor por diseño | No se evalúa el apilamiento de dos motores | Agregar al catálogo motores compuestos si aplica |

---

## 5. Rangos de Aplicabilidad

### Parámetros de reservorio

| Parámetro | Mínimo | Máximo | Notas |
|---|---|---|---|
| Presión estática Pr | 50 psi | 20 000 psi | — |
| Temperatura de reservorio | 50 °F | 450 °F | Límite de Standing; extrapolación fuera de rango |
| PI lineal | 0.01 STB/d/psi | 50 STB/d/psi | — |
| API | 5 °API | 70 °API | Standing válido aprox. 15–52 °API; extrapolación fuera |
| GOR | 0 scf/STB | 10 000 scf/STB | — |

### Parámetros de pozo

| Parámetro | Mínimo | Máximo | Notas |
|---|---|---|---|
| Profundidad total | 500 ft | 25 000 ft | — |
| Temperatura BHT | 50 °F | 450 °F | Límite catálogo de motor: 300–350 °F |
| Casing OD | 4.5 in | 9.625 in | Según catálogo de bombas disponibles |
| Desviación máxima | 0° | 90° | Beggs-Brill aplica; curvas de bomba para pozos inclinados difieren |

### Parámetros de fluido

| Parámetro | Mínimo | Máximo | Notas |
|---|---|---|---|
| Corte de agua | 0 | 1 (100 %) | — |
| Viscosidad crudo muerto | 0.1 cp | 5 000 cp | Corrección HI válida hasta ~500 cSt con limitaciones |
| SG agua | 1.00 | 1.30 | — |

### Tasas de producción y equipamiento

| Bomba | Rango de caudal | Casing mínimo |
|---|---|---|
| Centrilift M-34 | 600–1 100 STB/d | 4.5 in (OD 4.00 in) |
| Reda D-40 | 1 000–1 600 STB/d | 4.5 in (OD 4.00 in) |
| Reda D-55 | 1 700–2 600 STB/d | 4.5 in (OD 4.00 in) |
| Reda D-82 | 2 500–3 500 STB/d | 4.5 in (OD 4.00 in) |
| Centrilift I-42B | 1 200–2 200 STB/d | 5.5 in (OD 5.13 in) |
| Centrilift Y-62B | 1 700–2 200 STB/d | 5.5 in (OD 5.13 in) |
| Centrilift N-80 | 1 590–3 520 STB/d | 5.5 in (OD 5.13 in) |
| Centrilift Z-69 | 1 700–2 600 STB/d | 5.5 in (OD 5.13 in) |
| Reda G-52E | 2 000–3 200 STB/d | 5.5 in (OD 5.40 in) |
| Centrilift I-300 | 8 000–11 500 STB/d | 8.625 in (OD 7.38 in) |

---

## 6. Diagrama de Flujo del Diseño

```
Entrada: Reservoir · Fluid · WellGeometry · SurfaceConditions · DesignObjectives
        │
        ▼
    IPR (Vogel / Linear / Fetkovich / Combined)
    → Pwf en la tasa objetivo
        │
        ▼
    PVT Standing + DAK z-factor
    → Rs, Bo, Bw, Bg a condiciones de admisión
        │
        ▼
    Traverse de presión (Hagedorn-Brown / Beggs-Brill)
    → PIP (Pump Intake Pressure)
        │
        ▼
    TDH = H_lift + H_friction + H_wh
        │
        ▼
    GIP fraction (gas libre a condiciones PIP)
        │
        ▼
    Para cada bomba del catálogo que cabe en el casing y cubre el caudal:
        Etapas = ceil(TDH / h_per_stage)
        HP_bomba = etapas × hp/stage × SG_líquido
        (Corrección por viscosidad si aplica)
        │
        ▼
    Diseño eléctrico: Motor → Cable → Transformador
        │
        ▼
    Scoring (eficiencia · flexibilidad · costo)
        │
        ▼
    Top-3 recomendaciones (con diversificación de fabricante)
        │
        ▼
Salida: DesignResult (bomba + motor + cable + transformador + advertencias)
```
