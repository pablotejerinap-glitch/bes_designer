# Ejemplo de cátedra "ESP 01" — Diseño BES (método métrico)

Primera referencia de validación del método **métrico** (unidades kg/cm², m, °C,
m³/d, g/cm³). Implementado en `bes/core/metric_design.py` como ruta paralela al motor
de campo. Cubierto por `backend/tests/test_esp01.py` (integración) y
`backend/tests/test_metric_design.py` (por paso). Fórmulas y decisiones documentadas en
`docs/METHODOLOGY.md` §7.

## Datos de entrada (`MetricDesignInput`)

| Grupo | Parámetro | Valor |
|---|---|---|
| Pozo | Casing | 5½", 20 lb/ft (ID = 4.778 in) |
| Pozo | Tubing ID | 2.441 in |
| Pozo | Pref / Ps / Total | 2400 / 2250 / 2600 m |
| Pozo | Punzados | 2300–2500 m |
| Prod. | Qwf / Pwf (test) | 260 m³/d / 50 kg/cm² |
| Prod. | Pr (estática) | 170 kg/cm² |
| Prod. | Pbp (descarga) / Pc | 10 / 10 kg/cm² |
| Prod. | Tf / WC / GOR | 95 °C / 91 % / 50 m³/m³ |
| Prod. | Qd / PIP esperada | 300 m³/d / 15 kg/cm² |
| Fluido | API / Peo | 28 / 0.89 g/cm³ |
| Fluido | Peg / Pew / Pb / μ | 0.65 / 1.08 g/cm³ / 170 kg/cm² / 7 cp |
| Sistema | Frecuencia | 50 Hz |

## Tabla de regresión (§6)

Valores esperados de la resolución y su tolerancia. El **TDH se ancla en el valor
aritméticamente correcto (~2301 m)** y sus derivados en los valores
auto-consistentes (§7-B); la columna "lámina" es la referencia de cátedra, que el
motor expone pero no asevera.

| Magnitud | Esperado / tol | Anclado (motor) | Lámina |
|---|---|---|---|
| Pem | 1.0629 ±0.001 | 1.0629 | 1.0629 |
| ΔP_ref | 16 ±0.5 | 15.94 | 16 |
| Padm_a_ref | 31 ±0.5 | 30.94 | 31 |
| Vogel Q/Qmax (test) | 0.872 ±0.005 | 0.872 | 0.872 |
| Qmax | 298 ±2 | 298.2 | 298 |
| Q_producción | 279–280 ±3 | 279.4 | 279–280 |
| TD-2200 H/et (50 Hz) | 5.49 ±0.1 | 5.49 | 5.49 |
| TD-2200 HP/et (50 Hz) | 0.35 ±0.02 | 0.347 | 0.35 |
| TD-2200 Ho (50 Hz) | 7 ±0.3 | 6.94 | 7 |
| Fricción unitaria | 43.5 ±1 | 43.7 | 43.5 |
| Tf | 98 ±3 | 98.3 | 98 |
| PIP (succión) | 15 ±0.5 | 15.0 | 15 |
| **TDH** | **~2301 (§7-B)** | **2301** | 2347 |
| Etapas | (deriva de TDH) | 420 | 428 |
| Housings | (deriva de TDH) | 5×#10 | 4×#10+1×#11 |
| MHP | (deriva de TDH) | 4404 psi · Standard | 4523 psi |
| HP bomba | ~155 (deriva) | 155 | 158 |
| Ejes HR | 2 (§7-C) | 2 HR / 3 STD | 2 |
| Motores | 100/46/1354 + 58.5/47/788 | idem | idem |
| V_motor | 2142 ±5 | 2142 | 2142 |
| Refrigeración | ≥1 ft/s OK | 3.07 ft/s (ref. 4.75) | 4.75 |
| Protector | 2× HL serie 400 (high-load) | HL-400-HL ×2 | idem |
| Caída de cable | 189 ±5 | 191 | 189 |
| **V_superficie** | **2331 ±5** | **2333** | 2331 |

## Ambigüedades del material

- **§7-A Pwf 30 vs 31:** el motor usa Padm real (≈31), parametrizable vía
  `production_pwf_kgcm2`. Ambos redondean a 279–280 m³/d.
- **§7-B TDH:** la aritmética da ~2301 m (no 2347). Se ancló en ~2301 y se expone
  2347 como `tdh_reference_m`. Etapas/housings/MHP/HP derivan de ~2301.
- **§7-C Eje HR:** chequeo de HP acumulado por housing desde el fondo → 2 HR, 3 STD.

Detalle completo de fórmulas y fuentes de catálogo: `docs/METHODOLOGY.md` §7.
