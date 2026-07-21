# Metodología de la cátedra vs BES Designer — análisis de brechas

**Fuente:** procedimiento de diseño BES enseñado en la cátedra de
Producción (10 ítems), contrastado contra la implementación actual de la
aplicación (que sigue a Brown, *The Technology of Artificial Lift
Methods*, Vol. 2B, §4.5 — el libro de Kermit está en TESIS/Libros).
Ambas metodologías son la misma en esencia; la cátedra agrega
verificaciones mecánicas y térmicas que Brown desarrolla en secciones que
la aplicación aún no implementa.

## Mapa paso a paso

| Paso cátedra | Módulo de la app | Estado | Observaciones |
|---|---|---|---|
| 1. Datos del pozo/producción/fluido | `core/models.py` (Reservoir, Fluid, WellGeometry, SurfaceConditions) + `ipr.py` + `pvt.py` | ✅ Completo | Todos los datos listados existen como campos validados. La base v3 los almacena en las tablas de pozos. |
| 2a. Selección de bomba (caudal + OD casing + eficiencia) | `pump_design.py` + `recommender/` | ✅ Completo | Filtra por casing y rango de caudal, compara eficiencias y BEP — igual que la cátedra ("2 o 3 bombas candidatas" = el top-N del recomendador). |
| 2b. TDH y número de etapas | `tdh.py` + `pump_design.py` | ✅ Completo | Misma fórmula (elevación + fricción + presión en boca). Validado contra ejemplos de Brown. |
| 2c. Selección de housing + etapas dummy | catálogo `pump_housings` | ⚠️ Parcial | Los housings disponibles están en la base (tabla pump_housings), pero la app no selecciona la combinación de housings ni calcula etapas dummy. |
| 3a. Presión máxima sobre housing (MaxP a Q=0) | — | ❌ Falta | MaxP = H(Q=0) × #etapas × γ. Requiere: (1) altura a caudal CERO — las curvas cargadas empiezan en el caudal mínimo, no en shut-off; (2) columna `housing_pressure_limit_psi` en pumps (el catálogo Alkhorayef la trae: ej. 5000 psi). |
| 3b. Potencia sobre el eje | `electrical.py` (hp_required) + `seals.shaft_hp_*` | ⚠️ Parcial | La potencia se calcula y los sellos tienen límite de eje; falta la verificación explícita eje-de-bomba (requiere diámetro de eje por serie). |
| 3c. Carga sobre cojinetes | `electrical.py::estimate_axial_thrust()` + `get_seal()` | ⚠️ Parcial | Existe y el sello se selecciona por empuje. PERO los diámetros de eje están **hardcodeados** en `_SHAFT_DIAMETER_IN` — deben migrar a la columna `shaft_diameter_in` de `equipment_series` (misma regla que los transformadores). |
| 4a. Motor: HPoperativo vs HPmáximo | `electrical.py` | ❌ Falta HPmáx | Selecciona por HP operativo. Falta el HP máximo (arranque con agua o crudo desgasificado: misma fórmula con γ_agua) y elegir el mayor. |
| 4b. Aumento de temperatura interna del motor | — | ❌ Falta | MT = (OR − WR) × %oil + WR + BHT, con OR≈35-40°C (petróleo), WR≈10-15°C (agua) a 1 ft/s. Verificar MT < max_temp_f del motor (la columna ya existe). |
| 4c. Refrigeración: velocidad anular 1–20 ft/s | — | ❌ Falta | v = q / (A_casing − A_motor). Todos los datos ya están en la base (casing_id, motors.od_inches, caudal). Si no verifica → recomendar camisa de enfriamiento. |
| 4d. Voltaje alto para bajar amperaje | `catalogs/loader.py::get_motor()` | ✅ | Elige la tensión más cercana a la disponible; la recomendación de la cátedra (preferir tensión alta) puede hacerse explícita en el scoring. |
| 5. Sello (empuje, cámaras, elastómero, desviación, preferir laberinto) | `get_seal()` | ⚠️ Parcial | Empuje ✓, temperatura ✓, preferencia laberinto ✓ (más barato — igual que la cátedra). Faltan: número de cámaras, tipo de elastómero por fluido (H2S/CO2 ya están en Fluid), criterio por desviación del pozo. |
| 6. Controlador de superficie / tablero | tabla `switchboards` (v3) | ⚠️ Estructura lista | La tabla existe (vacía — catálogo Wood Group disponible). Falta la lógica de selección por V/A/HP máximos. VSD ídem. |
| 7. Cable con compensación por temperatura | `get_cable()` + `conductor_voltage_drop` | ✅ Completo | Caída de tensión interpolada en temperatura — exactamente el procedimiento de la cátedra. |
| 8. Transformador (kVA = V×I×√3/1000, nunca subdimensionar) | `electrical.py::calculate_kva()` + `select_transformer()` | ✅ Completo | Fórmula idéntica (√3 = 1.732 ✓). Selecciona el menor kVA ≥ demanda. La reserva para consumo futuro puede agregarse como margen configurable. |

## Consecuencias para la base de datos (esquema v3 → v3.1)

Las brechas NO requieren rediseño — solo columnas y datos nuevos,
confirmando la arquitectura:

1. `pumps` + `housing_pressure_limit_psi` [psi] y `shaft_diameter_in`
   [pulg] (o esta última en `equipment_series` si es constante por serie
   — los valores hardcodeados de `electrical.py` sugieren que lo es).
   El catálogo Alkhorayef trae ambos por modelo.
2. `pump_curves`: incluir el punto de **caudal cero (shut-off head)**
   cuando el catálogo lo publique — necesario para MaxP. No cambia la PK.
3. `seals` + `n_chambers` (número de cámaras) y `elastomer_type`
   (HSN/Viton/Aflas — el PDF Seals.pdf de Wood Group trae la guía de
   selección por temperatura y fluido).
4. `motors`: ya tiene todo lo necesario para MT y refrigeración.
5. `switchboards`/`vsds`: estructura lista; poblar con Wood Group.

## Nuevos cálculos a implementar (módulos, cuando se apruebe)

Todos con referencia a Brown §4.5 y al apunte de la cátedra:
`verify_housing_pressure()`, `calculate_max_hp()` (γ_agua),
`calculate_motor_temp_rise()`, `verify_cooling_velocity()`,
`select_housings()` (con etapas dummy), `select_switchboard()`.
Son verificaciones puras (entradas → advertencia/OK), ideales para
agregarse a `DesignResult` sin tocar el flujo existente.

## Sobre Autograph (Baker Hughes)

Plan sugerido cuando tengas la transcripción y capturas del video:

1. **Benchmark de validación:** correr en Autograph 2-3 diseños con
   bombas Centrilift (que ambos sistemas tienen) y comparar TDH, etapas,
   HP y equipo seleccionado contra BES Designer. Diferencias ≤ ±5% en
   altura / ±8% en potencia son el estándar API que cita la cátedra —
   criterio de aceptación perfecto para la tesis.
2. Los casos comparados se guardan como pozos en la base (well_type =
   example) con sus resultados en `book_reference`/`details`, igual que
   los ejemplos de Brown — la estructura ya lo soporta.
3. Las capturas sirven además como referencia de UI profesional para el
   rediseño de la interfaz.

## Para la defensa

* La aplicación implementa fielmente los pasos 1, 2, 7 y 8, y
  parcialmente 3, 5 y 6 — validados contra Brown.
* Las brechas identificadas (MaxP, HPmáx, MT, refrigeración, dummy
  stages) son **verificaciones de seguridad mecánica/térmica**, no
  errores del diseño hidráulico: el TDH y la selección de equipos ya son
  correctos.
* El hecho de que cerrar estas brechas solo requiera columnas nuevas y
  funciones de verificación — sin rediseñar nada — es evidencia de que
  la arquitectura (datos fuera del código, esquema normalizado, capas
  separadas) funciona.
