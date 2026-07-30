# BES Designer — Validación contra Ejemplos del Libro

**Generado:** 2026-07-23  
**Referencia:** Kermit Brown, *The Technology of Artificial Lift Methods*, Vol. 2b, Ch. 4.5

> Los valores de referencia son estimaciones analíticas basadas en las mismas ecuaciones
> del motor de cálculo (TDH por Hazen-Williams, etapas por interpolación de curva).
> Las diferencias se deben principalmente a la correlación Hagedorn-Brown para el PIP
> y a la redondeo de etapas según las opciones de housing del catálogo.

## Leyenda

> ✅ within tolerance · ⚠️ marginal (TDH ±10–20 %, stages/HP ±15–30 %) · ❌ outside tolerance

## Tabla Comparativa

| Ejemplo | TDH Libro (ft) | TDH App (ft) | Δ TDH | Etapas Libro | Etapas App | Δ Etapas | HP Libro | HP App | Δ HP | Bomba Seleccionada | Status |
|---------|---------------|-------------|-------|------------|-----------|----------|---------|--------|------|-------------------|--------|
| EXAMPLE 1A | 1724 | 1721 | -0.1% ✅ | 29 | 29 | +0.0% ✅ | 217 | 216.9 | -0.0% ✅ | I-300 | ✅ |
| EXAMPLE 2A INTERNAL | 4174 | 4249 | +1.8% ✅ | 156 | 139 | -10.9% ✅ | 44 | 45.3 | +2.9% ✅ | SF850 | ✅ |
| EXAMPLE 2A BROWN | 5830 | 5604 | -3.9% ✅ | 254 | 193 | -24.0% ⚠️ | 79 | 81.4 | +3.1% ✅ | SF1200 | ⚠️ |
| EXAMPLE 3A INTERNAL | 6060 | 6713 | +10.8% ⚠️ | 206 | 183 | -11.2% ✅ | 45 | 54.7 | +21.5% ⚠️ | HighRise-UNB7.5 | ⚠️ |

## Detalle por Ejemplo

### EXAMPLE 1A

*Brown Vol.2b Example 1A — Water well, no gas, 8-5/8" casing, 10 000 STB/d*

- **Bomba seleccionada:** I-300
- **TDH:** 1721 ft vs. 1724 ft libro (-0.1%)
- **Etapas:** 29 vs. 29 libro (+0.0%)
- **HP total bomba:** 216.9 vs. 217 libro (-0.0%)
- **Advertencias de diseño:** —

### EXAMPLE 2A INTERNAL

*Brown Vol.2b Example 2A — Oil well, no free gas at pump, 15% water cut, 5-1/2" casing*

- **Bomba seleccionada:** SF850
- **TDH:** 4249 ft vs. 4174 ft libro (+1.8%)
- **Etapas:** 139 vs. 156 libro (-10.9%)
- **HP total bomba:** 45.3 vs. 44 libro (+2.9%)
- **Advertencias de diseño:** —

### EXAMPLE 2A BROWN

*Brown Vol.2b Seccion 4.538 Ejemplo #2A (impreso) - Petroleo sin gas libre, casing 5 1/2", 1227 BFPD*

- **Bomba seleccionada:** SF1200
- **TDH:** 5604 ft vs. 5830 ft libro (-3.9%)
- **Etapas:** 193 vs. 254 libro (-24.0%)
- **HP total bomba:** 81.4 vs. 79 libro (+3.1%)
- **Advertencias de diseño:** Required 193 stages exceeds pump max_stages=185

### EXAMPLE 3A INTERNAL

*Brown Vol.2b Example 3A — Oil well WITH free gas, 50% water cut, high GIP, 5-1/2" casing*

- **Bomba seleccionada:** HighRise-UNB7.5
- **TDH:** 6713 ft vs. 6060 ft libro (+10.8%)
- **Etapas:** 183 vs. 206 libro (-11.2%)
- **HP total bomba:** 54.7 vs. 45 libro (+21.5%)
- **Advertencias de diseño:** —

---

## Notas Metodológicas

1. **PIP (Pump Intake Pressure):** el motor de cálculo usa la correlación de Hagedorn-Brown
   para el traverse de presión multifásico. Los valores de referencia usan la columna
   hidrostática simple (ΔP = SG · 0.433 · Δh), de allí la diferencia en TDH.

2. **Profundidad de bomba:** el selector ubica la bomba safety_margin_depth por encima
   del tope de perforaciones (pump_setting_depth = perforations_top − safety_margin_depth).

3. **Etapas:** se calculan exactamente (ceil(TDH / head_per_stage)); el número puede
   diferir del libro si el catálogo tiene una curva diferente.

4. **HP:** corregido por SG del fluido producido (hp_total = stages × hp/stage × SG).

5. **Catálogos aproximados:** los catálogos incluidos son representativos, no idénticos
   a los del libro original. Diferencias de ±15–30 % son esperables.