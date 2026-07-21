# Prompts para Claude Code — Rediseño de la app en 7 pasos

Orden de ejecución: 1 → 2 → 3 → 4. Verificar cada uno (pytest + abrir la app)
antes de pasar al siguiente. Cada prompt es autónomo.

---

## PROMPT 1 — Nueva sección "Cálculos: IPR e Índice de Productividad"

```text
Contexto: BES Designer (Streamlit). Leé CLAUDE.md primero. La app tiene
secciones en app.py definidas por _SEC_* (línea ~43) y un sidebar radio.
El motor de cálculo IPR ya existe COMPLETO en core/ipr.py — NO crear
fórmulas nuevas, solo exponer las existentes en la interfaz:
  linear_ipr(), vogel_ipr(), vogel_qmax_from_test(), combined_ipr(),
  fetkovich_ipr(), fetkovich_future_c(), vogel_future_qmax(),
  calculate_pwf_for_target_rate(), generate_ipr_curve(), _compute_aof().

Tarea: crear una nueva sección "Cálculos" (constante _SEC_CALC), ubicada
en el menú ENTRE "Datos del Pozo" y "Diseño BES", con una pestaña "IPR"
educativa y funcional. Crear el archivo nuevo ui/calculos_view.py con la
vista (no meter todo en app.py).

La pestaña IPR debe tener:

1. Guard: si no hay datos cargados en st.session_state.reservoir,
   mostrar st.info("Primero cargá los datos en 'Datos del Pozo'").

2. Bloque "Índice de productividad (J)":
   - Mostrar la fórmula con st.latex: J = q / (P_r - P_wf)
   - Dos modos con st.radio:
     a) "J conocido": muestra el J cargado en Datos del Pozo.
     b) "Calcular J desde ensayo": inputs q_test [STB/d] y Pwf_test [psi];
        calcula J = q_test/(Pr - Pwf_test) para flujo monofásico, y si
        Pwf_test < Pb usa vogel_qmax_from_test() y muestra q_max.
        Botón para GUARDAR el J calculado en st.session_state.reservoir
        (crear un Reservoir nuevo con dataclasses.replace, NO mutar).

3. Bloque "Curva IPR":
   - Selector de método (LINEAR/VOGEL/FETKOVICH/COMBINED, el mismo enum
     IPRMethod de core/models.py).
   - Mostrar la fórmula del método elegido con st.latex y UNA línea de
     referencia bibliográfica:
       Lineal:    q = J(Pr - Pwf)            [Darcy]
       Vogel:     q/qmax = 1 - 0.2(Pwf/Pr) - 0.8(Pwf/Pr)^2   [Vogel 1968]
       Fetkovich: q = C(Pr^2 - Pwf^2)^n       [Fetkovich 1973]
       Combinada: lineal sobre Pb + Vogel debajo  [Brown Vol.2B]
   - Graficar la curva con generate_ipr_curve() usando plotly (consistente
     con ui/plots.py). Marcar en el gráfico: AOF (Pwf=0), Pb si aplica, y
     el punto de operación al caudal objetivo
     (calculate_pwf_for_target_rate).
   - Mostrar métricas: AOF [STB/d], Pwf al caudal objetivo [psi].

4. Bloque "Predicción futura (efecto de la caída de presión estática)":
   - Input: presión estática futura Pr_futura [psi].
   - Usar fetkovich_future_c() o vogel_future_qmax() según el método,
     y graficar la IPR actual y la futura superpuestas.
   - Mostrar la fórmula correspondiente con st.latex, p.ej.
     C_f = C_p (Pr_f / Pr_p)  y  qmax_f = qmax_p (Pr_f/Pr_p)^3 — VERIFICAR
     los exponentes leyendo las docstrings de core/ipr.py y usar
     exactamente lo que el código implementa; si la docstring no lo
     aclara, PREGUNTAME antes de escribir la fórmula en pantalla.

Restricciones:
- NO modificar core/ (solo lectura). Todo el trabajo es UI.
- Estilo consistente con ui/forms.py y ui/results_view.py existentes.
- pytest completo debe seguir en verde (663 tests).
- Al terminar: explicame qué archivos tocaste y cómo probar la pestaña.
```

---

## PROMPT 2 — Completar "Cálculos" con pestañas PVT y TDH

```text
Contexto: BES Designer. Leé CLAUDE.md. Continúa el trabajo de la sección
"Cálculos" (ui/calculos_view.py) agregando dos pestañas junto a "IPR".

Pestaña "PVT":
- Guard de datos como en IPR.
- Slider/inputs de presión de evaluación [psi] (default: de Pwf a Pr) y
  usar la temperatura de reservorio cargada.
- Mostrar en tabla las propiedades calculadas con core/pvt.py a esa (P,T):
  Pb, Rs, Bo, viscosidad muerta y viva, factor Z, densidades.
- Junto a cada propiedad, su correlación de origen (Standing 1947,
  Beggs-Robinson 1975, Dranchuk-Abou-Kassem 1975) — leer los nombres
  exactos de las funciones/docstrings de core/pvt.py.
- Graficar Rs y Bo vs presión (de 14.7 a Pr) con plotly.

Pestaña "TDH":
- Requiere que exista un diseño calculado (st.session_state.design_results);
  si no, st.info que indique correr primero el Diseño BES... PERO también
  ofrecer un "cálculo rápido" independiente: con los datos del pozo +
  caudal objetivo, calcular PIP (core/multiphase.calculate_pip) y TDH
  (core/tdh.calculate_tdh) y mostrar el DESGLOSE en 3 términos con
  st.latex y sus valores:
    TDH = Elevación + Fricción + Altura por presión en boca
    Elevación = D_bomba - PIP·2.31/SG
    Fricción (Hazen-Williams): mostrar la fórmula completa
    h_whp = P_wh·2.31/SG
- Un gráfico de barras apiladas con los 3 componentes del TDH.

Restricciones: NO modificar core/. pytest en verde. Si alguna firma de
función no coincide con lo descripto, leé el código y adaptate; si hay
ambigüedad de ingeniería, PREGUNTAME.
```

---

## PROMPT 3 — Reordenar la navegación al flujo de 7 pasos

```text
Contexto: BES Designer. Leé CLAUDE.md. Hoy el menú (app.py, _SECTIONS) es:
Datos del Pozo / Diseño BES / Comparación / Sensibilidad / Análisis Nodal
/ Información — más la sección "Cálculos" agregada recientemente.

Tarea: reordenar y renombrar el menú lateral para que refleje el flujo de
trabajo de diseño, numerado:

  1. Datos del pozo        (existente: _SEC_DATA)
  2. Cálculos (IPR·PVT·TDH) (existente: _SEC_CALC)
  3. Diseño BES            (existente: _SEC_DESIGN — el ranking completo)
  4. Selección de equipos  (renombrar la actual "Comparación": es donde
                            se comparan las alternativas lado a lado)
  5. Resultado recomendado (NUEVA vista liviana: muestra SOLO la mejor
                            recomendación con su justificación (rationale),
                            el resumen del equipo completo bomba→motor→
                            cable→sello→transformador y el botón de
                            descarga del Excel. Reutilizar render_results
                            y el bloque de descarga existente — mover el
                            download aquí desde Diseño BES)
  6. Sensibilidad          (existente)
  7. Análisis nodal        (existente)
  — Información            (dejarla al final, sin número)

Además, GATING suave: si el usuario entra a un paso sin haber completado
los anteriores, mostrar st.info con qué le falta (ej. en el paso 3 sin
datos cargados: "Completá el paso 1"). No bloquear con errores, solo
guiar. Usar st.session_state existente (reservoir, design_results, etc.).

Restricciones:
- Reorganización PURA: no cambiar ningún cálculo ni la lógica del
  recomendador.
- Cuidado con los nombres de sección: hay strings comparados con
  `section ==` en app.py — actualizar todos consistentemente.
- pytest en verde. Al terminar, mostrame captura mental del nuevo menú y
  qué quedó en cada paso.
```

---

## PROMPT 4 — Análisis nodal y flujo bifásico (temario de cátedra)

```text
Contexto: BES Designer. Leé CLAUDE.md y docs/METHODOLOGY.md. El módulo
core/nodal_analysis.py ya tiene: outflow_curve_natural(),
outflow_curve_with_pump(), find_operating_point(), compare_methods().
El flujo multifásico usa Hagedorn-Brown y Orkiszewski (core/multiphase.py).

Tarea en dos partes:

Parte A (solo UI): enriquecer la sección "7. Análisis nodal":
- Gráfico IPR (inflow) vs curva de demanda (outflow) con y sin bomba,
  marcando el punto de operación (find_operating_point).
- Explicación breve en pantalla de qué es el análisis nodal y qué
  significa el punto de operación.
- Selector de correlación de flujo vertical si compare_methods() lo
  permite, mostrando ambas curvas superpuestas.

Parte B (requiere MI input — preguntame antes de implementar):
La cátedra ve las correlaciones de Poettmann-Carpenter, Duns-Ros y
Gilbert para flujo bifásico vertical, y el concepto de RGL óptima.
La app hoy tiene Hagedorn-Brown y Orkiszewski. NO implementes las
correlaciones nuevas de memoria: pedime el apunte de cátedra o las
ecuaciones exactas que quiero usar (dame la lista de qué necesitás:
rangos de validez, constantes, gráficas digitalizadas si las hay).
Cuando te pase el material, implementalas como funciones nuevas en
core/multiphase.py SIN tocar las existentes, cada una con su test
contra un ejemplo resuelto que yo te dé.

Restricciones: pytest siempre en verde; las correlaciones nuevas entran
solo con su ejemplo de validación. Si un ejemplo no cierra, avisame en
vez de forzarlo.
```

---

## Nota general para todas las sesiones

Si Claude Code encuentra que algo descripto acá no coincide con el código
real (nombres, firmas), debe leer el código y adaptarse — el código manda.
Si la duda es de INGENIERÍA (una fórmula, un criterio, una constante),
debe preguntarme a mí antes de decidir.
