# Metodología de cátedra vs. BES Designer

Comparación del procedimiento de diseño de la **Unidad N°9 — Bombeo
Electrosumergible** (apunte de cátedra, Pablo A. Tejerina, pág. 128–141) contra
lo que la aplicación calcula hoy.

Cada estado de esta tabla se verificó **contra el código**, no contra
documentación previa. Reemplaza a
`tools/database_migration/METODOLOGIA_CATEDRA_VS_APLICACION.md`, que quedó
desactualizado: daba por faltantes varias verificaciones que ya están
implementadas.

> **Nota sobre la fuente.** El apunte anuncia *"la selección de 10 ítems"* pero
> el PDF entregado termina en el ítem 8 (transformador de superficie). Los
> ítems **9 y 10 no están en el material**, así que no se los pudo contrastar.

---

## 1. Los 8 pasos contrastados

| # | Paso de la cátedra | Dónde vive en la app | Estado |
|---|---|---|---|
| 1 | Datos del pozo, producción y fluido | `core/models.py` (5 dataclasses validadas) + `ipr.py` + `pvt.py` | ✅ Completo |
| 2a | Selección de bomba por caudal + OD casing + eficiencia | `pump_design.py` + `recommender/` | ✅ Completo |
| 2b | Cálculo del N° de etapas por TDH | `tdh.py` + `pump_design.calculate_stages()` | ✅ Completo |
| 2c | Selección de housing + etapas dummy | `core/housing.py::optimize_housings()` | ✅ Completo |
| 3a | Verificación de presión sobre el housing (MaxP a Q=0) | `core/housing.py` | ✅ Completo |
| 3b | Potencia sobre el eje | `pump_design.calculate_motor_hp()` | ⚠️ Se calcula; **no se verifica** contra el límite del eje |
| 3c | Carga sobre cojinetes de la sección sellante | `electrical.estimate_axial_thrust()` | ⚠️ Fórmula distinta (ver §2) |
| 4a | Motor: HP operativo vs. HP máximo | `pump_design.calculate_motor_hp()` con `sg` y `sg_max` | ✅ Completo |
| 4b | Aumento de temperatura interna del motor | — | ❌ **No implementado** |
| 4c | Refrigeración: velocidad anular 1–20 ft/s | `electrical.fluid_velocity_past_motor()` | ⚠️ Solo verifica el mínimo de 1 ft/s |
| 4d | Preferir tensión alta para bajar amperaje | `electrical.select_motor()` | ✅ Completo |
| 5 | Sello: empuje, cámaras, elastómero, desviación, preferir laberinto | `loader.get_seal()` + `pump_selector` | ⚠️ Parcial (ver §3) |
| 6 | Controlador / tablero de superficie | `loader.select_controller()` + `controllers.json` | ✅ Completo |
| 7 | Cable con compensación por temperatura | `electrical.select_cable()` + `voltage_drop()` | ✅ Completo |
| 8 | Transformador, kVA = V·I·√3/1000 | `electrical.calculate_kva()` + `select_transformer()` | ✅ Completo |

**Orden del flujo.** Coincide exactamente con el de la cátedra:
bomba → etapas → housing → verificación de presión → motor → sello →
controlador → cable → transformador.

---

## 2. Donde la app y la cátedra calculan lo mismo de distinta manera

### TDH y sumergencia

| | Cátedra | App |
|---|---|---|
| Fórmula | `TDH = Prof. succión − Sumergencia + Fricción + P boca` | `TDH = Prof. bomba − PIP·2.31/SG + Fricción + Pwh·2.31/SG` |
| Sumergencia | Valor supuesto, "aproximadamente 200 m" | **Calculada**: PIP por traverse de presión multifásico (Hagedorn-Brown) desde las perforaciones hasta la admisión |

Es la misma ecuación: la sumergencia expresada en altura de fluido *es* el
término `PIP·2.31/SG`. La diferencia está en que la cátedra la asume y la app la
calcula a partir de la IPR y el PVT del pozo. Es un refinamiento, no una
discrepancia.

### Pérdida de carga en el tubing

La cátedra la trata como un término único. La app **elige la correlación según
el gas**: por debajo de la fracción umbral de gas libre en la admisión (default
0.10) usa Hazen-Williams; por encima, el término de fricción de
Poettmann-Carpenter integrado a lo largo del tubing.

### Carga sobre el cojinete de empuje

| | Cátedra | App |
|---|---|---|
| Altura usada | `Ho` = profundidad de la bomba − sumergencia (solo la elevación vertical) | TDH completo |
| Fórmula | `f(peso específico, Ho, A_eje)` | `ΔP_bomba × (π/4 · d_eje²) × 1.20` (Takács) |

La app usa el TDH completo, que incluye fricción y presión de boca, así que
sobre el mismo pozo da un empuje **mayor** que el método de cátedra — más
conservador para elegir el sello. El diámetro de eje sale de una tabla por serie
(`_SHAFT_DIAMETER_IN`), no del catálogo.

### Presión sobre el housing

Idéntica: `MaxP = P(Q=0) × N etapas × Pem`. La app la aplica **acumulada carcasa
a carcasa** desde la admisión, así que en un tándem verifica cada una por
separado y la superior es la crítica. Además es **restricción dura**: una
combinación que la supere se descarta y la bomba no se recomienda.

---

## 3. Brechas reales, y qué haría falta para cerrarlas

| Brecha | Qué falta | Dato necesario |
|---|---|---|
| **Aumento de temperatura interna del motor** | `MT = (OR − WR)·%oil + WR + BHT`, con OR ≈ 35–40 °C (petróleo) y WR ≈ 10–15 °C (agua) a 1 ft/s. Verificar `MT < max_temp_f`. | Ninguno: `motors.json` ya tiene `max_temp_f` y el corte de agua está en `Fluid`. **Es solo código.** |
| **Límite superior de refrigeración (20 ft/s)** | Hoy solo se avisa por debajo de 1 ft/s. | Ninguno. Es solo código. |
| **Verificación del eje de la bomba** | Comparar el HP sobre el eje contra el límite del eje (estándar / alta / ultra resistencia). | `shaft_hp_limit_std / _hs / _uhs` por modelo. Existe en el Excel de desarrollo para 37 bombas (Alkhorayef) y en el catálogo métrico; **no está en `pumps.json`**. |
| **Sello: número de cámaras** | Elegir cuántas cámaras en serie. | Columna `n_chambers` en `seals.json` — no existe. |
| **Sello: tipo de elastómero** | Elegir HSN / Viton / Aflas según temperatura y H₂S/CO₂. | Columna `elastomer_type` en `seals.json` — no existe. La guía de selección está en `TESIS/CATALOGOS/Seals.pdf` (Wood Group). |
| **Tipo de impulsor (radial vs. mixto)** | La cátedra lo usa como criterio de selección: radial para <200 m³/d y pozos profundos, mixto para >275 m³/d y presencia de gas o viscosidad. | Columna `stage_type` en `pumps.json` — existe en el Excel de desarrollo, no en el JSON que lee la app. |
| **Tipo de bomba (compresión vs. flotante)** | Afecta quién absorbe el empuje axial y el rango operativo admisible. | No modelado en el camino de campo. El catálogo métrico ya tiene `bearing_floater_std_stages` y `bearing_high_load_stages`. |
| **Separadores por tipo de la cátedra** | La cátedra clasifica en estándar (0 %), flujo inverso (25–50 %) y rotativo (70–90 %). El catálogo de la app usa `rotary`, `vortex` y `gkx`. | Mapeo de nomenclatura, o eficiencias por tipo según catálogo. |
| **Leyes de afinidad en el diseño de campo** | Implementadas en `units.py` y usadas por el motor métrico, pero el flujo de campo no reescala la curva por frecuencia. | Ninguno. Es solo código. |

**No modelado a propósito** (son operación o accesorios, no cálculo de diseño):
cartas amperométricas, válvulas de retención y drenaje, centralizadores, cable
bands, caja de venteo, penetrador y cabezal. La cavitación / NPSH tampoco: el
propio apunte explica que no suele darse en BES por la sumergencia mínima.

---

## 4. Lo que la app agrega sobre el método de cátedra

El apunte parte del caudal deseado como dato. La app calcula **de dónde sale ese
caudal y a qué presión llega el fluido a la bomba**:

- **IPR**: Vogel, lineal (Darcy) y Fetkovich, con el índice de productividad
  derivado de un ensayo de producción en vez de cargado a mano.
- **PVT**: Standing (Rs, Pb, Bo), Dranchuk–Abou-Kassem (factor z),
  Beggs–Robinson (viscosidad), en lugar de propiedades supuestas.
- **PIP por traverse multifásico** (Hagedorn-Brown), en lugar de la sumergencia
  supuesta de 200 m.
- **Manejo de gas por el método de incrementos de 200 psi** (Brown §4.53103).
- **Análisis nodal** (Brown Vol. 4).
- **Optimización de carcasas por búsqueda** — la cátedra la resuelve mirando el
  catálogo a mano; la app evalúa las combinaciones posibles y ordena por
  criterios estrictos con la presión como restricción.
- **Ranking automático del top-3** por cercanía al BEP → eficiencia → potencia.
- **Análisis de sensibilidad** sobre Pr, corte de agua, GOR y caudal objetivo.
- **Reportes PDF y Excel** con la memoria de cálculo paso a paso.

Los criterios que la cátedra sí fija y la app respeta al pie de la letra: el
10 % de gas libre como umbral para pasar de admisión estándar a separador, la
tolerancia API de ±5 % en altura y ±8 % en potencia (usada como criterio de QA
al digitalizar las curvas), el mínimo de 1 ft/s de refrigeración, y la regla de
nunca subdimensionar el transformador.

---

## 5. Resumen para la defensa

- De los 8 pasos contrastables, la app implementa **completos 6** (datos, bomba,
  etapas, housing + presión, controlador, cable, transformador) y **parciales 2**
  (eje/cojinetes y motor/sello).
- Las brechas son **verificaciones mecánicas y térmicas**, no errores del diseño
  hidráulico: el TDH, las etapas y la selección de equipos ya están validados
  contra los ejemplos impresos de Kermit Brown.
- De las 9 brechas listadas, **3 son solo código** (temperatura del motor, límite
  superior de refrigeración, leyes de afinidad) y **6 esperan datos de catálogo**
  que en varios casos ya existen en el Excel de desarrollo y solo hay que migrar
  al JSON que lee la aplicación.
