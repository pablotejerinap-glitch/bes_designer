"""
BES Designer — Streamlit application entry point.
Phase 10: Complete UI for automated ESP/BES design.

Run with:
    python -m streamlit run app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Ensure project root is importable
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# Page configuration (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    layout="wide",
    page_title="BES Designer",
    page_icon="🛢️",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Lazy imports (after sys.path is set)
# ---------------------------------------------------------------------------
from catalogs.loader import CatalogManager                                  # noqa: E402
from recommender.recommendation_engine import generate_recommendations       # noqa: E402
from ui.forms import render_data_forms                                       # noqa: E402
from ui.results_view import render_results                                   # noqa: E402
from ui.comparison_view import render_comparison                             # noqa: E402
from ui.sensitivity_view import render_sensitivity                           # noqa: E402
from reports.pdf_generator import generate_design_report                     # noqa: E402
from reports.excel_exporter import generate_design_excel                     # noqa: E402

# ---------------------------------------------------------------------------
# Session-state initialisation
# ---------------------------------------------------------------------------
_SS_DEFAULTS: dict = {
    "reservoir":       None,
    "fluid":           None,
    "well":            None,
    "surface":         None,
    "objectives":      None,
    "design_results":  None,
    "selected_rec_idx": 0,
    "catalog":         None,
    "sens_results":    None,
}
for _k, _v in _SS_DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ---------------------------------------------------------------------------
# Catalog — cached so it loads once per browser session
# ---------------------------------------------------------------------------

@st.cache_resource
def _load_catalog() -> CatalogManager:
    return CatalogManager(str(_ROOT / "catalogs"))


catalog = _load_catalog()
st.session_state.catalog = catalog

# ---------------------------------------------------------------------------
# Sidebar — navigation
# ---------------------------------------------------------------------------
st.sidebar.image(
    "https://img.icons8.com/ios-filled/100/4A90D9/oil-pump.png",
    width=60,
)
st.sidebar.title("BES Designer")
st.sidebar.caption("Diseño automatizado de ESP")
st.sidebar.divider()

section = st.sidebar.radio(
    "Navegación",
    [
        "📝 Datos del Pozo",
        "⚙️ Diseño BES",
        "📊 Comparación de Opciones",
        "📈 Análisis de Sensibilidad",
        "📐 Análisis Nodal",
        "ℹ️ Acerca de",
    ],
    label_visibility="collapsed",
)

# Sidebar status panel
st.sidebar.divider()
st.sidebar.markdown("**Estado**")
if st.session_state.reservoir is not None:
    st.sidebar.success("✅ Datos del pozo guardados")
else:
    st.sidebar.warning("⚠️ Sin datos del pozo")

if st.session_state.design_results is not None:
    n_recs = len(st.session_state.design_results["recommendations"])
    st.sidebar.success(f"✅ {n_recs} diseño(s) calculado(s)")
else:
    st.sidebar.info("ℹ️ Diseño pendiente de cálculo")

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------
st.title("🛢️ BES Designer — Diseño Automatizado de Bombeo Electrosumergible")
st.caption(
    "Basado en Kermit Brown — *The Technology of Artificial Lift Methods, Vol. 2b*"
)
st.divider()

# ---------------------------------------------------------------------------
# Section: Datos del Pozo
# ---------------------------------------------------------------------------
if section == "📝 Datos del Pozo":
    render_data_forms()

# ---------------------------------------------------------------------------
# Section: Diseño BES
# ---------------------------------------------------------------------------
elif section == "⚙️ Diseño BES":
    st.header("⚙️ Diseño BES")

    if st.session_state.reservoir is None:
        st.error(
            "❌ Primero completá y guardá los datos del pozo "
            "en la sección '📝 Datos del Pozo'."
        )
        st.stop()

    # Summary of loaded inputs
    with st.expander("📋 Resumen de datos cargados", expanded=False):
        r = st.session_state.reservoir
        f = st.session_state.fluid
        w = st.session_state.well
        s = st.session_state.surface
        o = st.session_state.objectives

        ci1, ci2, ci3, ci4 = st.columns(4)
        ci1.metric("Presión reservorio",  f"{r.static_pressure:,.0f} psi")
        ci2.metric("Temperatura BHP",     f"{r.reservoir_temp:.0f} °F")
        ci3.metric("Profundidad total",   f"{w.total_depth:,.0f} ft")
        ci4.metric("ID casing",           f"{w.casing_id:.3f} in")

        ci5, ci6, ci7, ci8 = st.columns(4)
        ci5.metric("Tasa objetivo",       f"{o.target_flow_rate:,.0f} STB/d")
        ci6.metric("Corte de agua",       f"{f.water_cut:.0%}")
        ci7.metric("GOR",                 f"{f.gor:.0f} scf/STB")
        ci8.metric("Voltaje disponible",  f"{s.power_supply_voltage:,.0f} V")

    st.divider()

    # Calculate button
    if st.button(
        "🚀 Calcular Diseño BES",
        type="primary",
        use_container_width=True,
        help="Evalúa todas las bombas del catálogo y selecciona las mejores opciones",
    ):
        with st.spinner("Calculando diseño óptimo — evaluando catálogo completo..."):
            try:
                results = generate_recommendations(
                    reservoir=st.session_state.reservoir,
                    fluid=st.session_state.fluid,
                    well=st.session_state.well,
                    surface=st.session_state.surface,
                    objectives=st.session_state.objectives,
                    catalog=catalog,
                    n=3,
                )
                st.session_state.design_results = results
                st.session_state.selected_rec_idx = 0
                n_cand = results["n_candidates_evaluated"]
                n_recs = len(results["recommendations"])
                st.success(
                    f"✅ Diseño completado: {n_recs} opción(es) seleccionada(s) "
                    f"de {n_cand} candidato(s) evaluado(s)."
                )
            except ValueError as exc:
                st.error(f"❌ No se encontró diseño válido: {exc}")
                st.stop()
            except Exception as exc:
                st.error(f"❌ Error inesperado en el cálculo: {exc}")
                st.stop()

    # Show results for the selected recommendation
    if st.session_state.design_results is not None:
        recs = st.session_state.design_results["recommendations"]
        idx  = st.session_state.get("selected_rec_idx", 0)

        if len(recs) > 1:
            tab_labels = [
                f"{'🥇' if r['rank']==1 else '🥈' if r['rank']==2 else '🥉'} "
                f"Opción {r['rank']}: {r['design'].pump_model}"
                for r in recs
            ]
            tabs = st.tabs(tab_labels)
            for tab, rec in zip(tabs, recs):
                with tab:
                    render_results(rec)
        else:
            render_results(recs[0])

        # ----------------------------------------------------------------
        # Download section
        # ----------------------------------------------------------------
        st.divider()
        st.subheader("📥 Descargar Reportes")

        import json as _json
        import dataclasses as _dc

        selected_dr = recs[min(idx, len(recs) - 1)]["design"]
        _well_dl = {
            "reservoir":  st.session_state.reservoir,
            "fluid":      st.session_state.fluid,
            "well":       st.session_state.well,
            "surface":    st.session_state.surface,
            "objectives": st.session_state.objectives,
        }

        dl1, dl2, dl3 = st.columns(3)

        with dl1:
            try:
                _pdf = generate_design_report(selected_dr, _well_dl)
                st.download_button(
                    "📕 Descargar PDF",
                    data=_pdf,
                    file_name="reporte_bes.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception as _e:
                st.error(f"❌ Error generando PDF: {_e}")

        with dl2:
            try:
                _xlsx = generate_design_excel(selected_dr, _well_dl)
                st.download_button(
                    "📗 Descargar Excel",
                    data=_xlsx,
                    file_name="reporte_bes.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            except Exception as _e:
                st.error(f"❌ Error generando Excel: {_e}")

        with dl3:
            try:
                _case = {
                    "generated":    str(__import__("datetime").date.today()),
                    "design_result": _dc.asdict(selected_dr),
                    "reservoir":    _dc.asdict(st.session_state.reservoir),
                    "fluid":        _dc.asdict(st.session_state.fluid),
                    "well":         _dc.asdict(st.session_state.well),
                    "surface":      _dc.asdict(st.session_state.surface),
                    "objectives":   _dc.asdict(st.session_state.objectives),
                }
                _json_bytes = _json.dumps(_case, default=str, indent=2).encode("utf-8")
                st.download_button(
                    "💾 Guardar Caso JSON",
                    data=_json_bytes,
                    file_name="caso_bes.json",
                    mime="application/json",
                    use_container_width=True,
                )
            except Exception as _e:
                st.error(f"❌ Error generando JSON: {_e}")

# ---------------------------------------------------------------------------
# Section: Comparación de Opciones
# ---------------------------------------------------------------------------
elif section == "📊 Comparación de Opciones":
    st.header("📊 Comparación de Opciones")

    if st.session_state.design_results is None:
        st.error(
            "❌ Primero calculá el diseño en la sección '⚙️ Diseño BES'."
        )
    else:
        recs = st.session_state.design_results["recommendations"]
        st.caption(
            f"{len(recs)} opción(es) evaluadas  |  "
            f"Pesos de scoring: eficiencia 40 % · flexibilidad 30 % · proveedor 30 %"
        )
        render_comparison(recs)

# ---------------------------------------------------------------------------
# Section: Análisis de Sensibilidad
# ---------------------------------------------------------------------------
elif section == "📈 Análisis de Sensibilidad":
    st.header("📈 Análisis de Sensibilidad")
    render_sensitivity()

# ---------------------------------------------------------------------------
# Section: Análisis Nodal
# ---------------------------------------------------------------------------
elif section == "📐 Análisis Nodal":
    st.header("📐 Análisis Nodal del Sistema")

    if st.session_state.reservoir is None:
        st.error(
            "❌ Primero completá y guardá los datos del pozo "
            "en la sección '📝 Datos del Pozo'."
        )
        st.stop()

    reservoir_base = st.session_state.reservoir
    fluid          = st.session_state.fluid
    well           = st.session_state.well
    surface        = st.session_state.surface

    # ── Sidebar controls ─────────────────────────────────────────────────────
    with st.sidebar:
        st.divider()
        st.markdown("**Opciones Nodal**")

        _method_map = {
            "Hagedorn-Brown":        "hagedorn_brown",
            "Beggs-Brill":           "beggs_brill",
            "Duns & Ros":            "duns_ros",
            "Poettmann & Carpenter": "poettmann_carpenter",
        }
        method_choice = st.selectbox(
            "Correlación multifásica",
            list(_method_map.keys()),
            key="nodal_method",
        )
        method = _method_map[method_choice]

        compare_all = st.checkbox("Comparar todos los métodos", key="nodal_compare")

        pr_decline = st.slider(
            "Declinación de Pr (%)",
            min_value=0, max_value=50, value=0, step=5,
            key="nodal_pr_decline",
            help="Simula la caída de presión de reservorio respecto al valor actual.",
        )

        calc_btn = st.button(
            "🔍 Calcular Análisis Nodal",
            type="primary",
            use_container_width=True,
            key="nodal_calc_btn",
        )

    # ── Reservoir with optional decline ──────────────────────────────────────
    from core.models import Reservoir as _Reservoir
    if pr_decline > 0:
        pr_new = reservoir_base.static_pressure * (1.0 - pr_decline / 100.0)
        pb_new = min(reservoir_base.bubble_point, pr_new)
        reservoir_eff = _Reservoir(
            static_pressure=pr_new,
            bubble_point=pb_new,
            productivity_index=reservoir_base.productivity_index,
            ipr_method=reservoir_base.ipr_method,
            reservoir_temp=reservoir_base.reservoir_temp,
            drive_mechanism=reservoir_base.drive_mechanism,
            datum_depth=reservoir_base.datum_depth,
        )
    else:
        reservoir_eff = reservoir_base

    if pr_decline > 0:
        st.info(
            f"ℹ️ Simulando Pr = {reservoir_eff.static_pressure:.0f} psi "
            f"(−{pr_decline} % del original {reservoir_base.static_pressure:.0f} psi)"
        )

    # ── Get pump from the top design recommendation (if available) ────────────
    pump_obj   = None
    stages_val = None
    pump_depth_val = None
    if st.session_state.design_results is not None:
        top_design = st.session_state.design_results["recommendations"][0]["design"]
        pump_model_name = top_design.pump_model
        pump_depth_val  = top_design.pump_setting_depth
        stages_val      = top_design.num_stages
        pump_obj = next(
            (p for p in catalog.get_all_pumps() if p.model == pump_model_name),
            None,
        )
        if pump_obj is None:
            st.warning(
                f"⚠️ Bomba '{pump_model_name}' no encontrada en catálogo. "
                "Se mostrará sólo flujo natural."
            )

    if pump_obj is None:
        st.info("ℹ️ Sin diseño BES calculado — se muestra sólo el flujo natural.")

    # ── Calculate ─────────────────────────────────────────────────────────────
    if calc_btn:
        with st.spinner("Calculando análisis nodal…"):
            try:
                from ui.plots import plot_nodal_analysis, plot_nodal_comparison
                from core.nodal_analysis import find_operating_point, compare_methods

                if not compare_all:
                    # ── Single-method view ────────────────────────────────────
                    fig_nodal = plot_nodal_analysis(
                        reservoir=reservoir_eff,
                        fluid=fluid,
                        well=well,
                        surface=surface,
                        pump=pump_obj,
                        stages=stages_val,
                        pump_depth=pump_depth_val,
                        method=method,
                    )
                    st.plotly_chart(fig_nodal, use_container_width=True)

                    # Metrics
                    result = find_operating_point(
                        reservoir_eff, fluid, well, surface,
                        method=method,
                        pump=pump_obj, stages=stages_val, pump_depth=pump_depth_val,
                    )
                    nat = result["natural_flow"]
                    pmp = result["pump_flow"]
                    q_nat  = nat["q"]  if nat  else 0.0
                    q_pmp  = pmp["q"]  if pmp  else 0.0
                    pwf_op = pmp["pwf"] if pmp else (nat["pwf"] if nat else 0.0)
                    incr_pct = (result["incremental_rate"] / max(q_nat, 1.0)) * 100.0

                    mc1, mc2, mc3, mc4 = st.columns(4)
                    mc1.metric("Caudal Natural",  f"{q_nat:.0f} STB/D")
                    mc2.metric(
                        "Caudal con BES",
                        f"{q_pmp:.0f} STB/D",
                        delta=f"+{result['incremental_rate']:.0f} STB/D" if q_pmp > 0 else None,
                    )
                    mc3.metric("Pwf Operación",   f"{pwf_op:.0f} psi")
                    mc4.metric(
                        "Eficiencia BES",
                        f"{result['pump_efficiency'] * 100:.1f} %",
                    )

                else:
                    # ── Comparison view (4 methods) ───────────────────────────
                    fig_comp = plot_nodal_comparison(
                        reservoir=reservoir_eff,
                        fluid=fluid,
                        well=well,
                        surface=surface,
                        pump=pump_obj,
                        stages=stages_val,
                        pump_depth=pump_depth_val,
                    )
                    st.plotly_chart(fig_comp, use_container_width=True)

                    cmp_results = compare_methods(
                        reservoir_eff, fluid, well, surface,
                        pump=pump_obj, stages=stages_val, pump_depth=pump_depth_val,
                    )

                    import pandas as _pd
                    _labels = {
                        "hagedorn_brown":       "Hagedorn-Brown",
                        "beggs_brill":          "Beggs-Brill",
                        "duns_ros":             "Duns & Ros",
                        "poettmann_carpenter":  "Poettmann & Carpenter",
                    }
                    table_rows = []
                    for m_key, m_label in _labels.items():
                        res = cmp_results[m_key]
                        q_n = res["natural_flow"]["q"]  if res["natural_flow"] else 0
                        q_p = res["pump_flow"]["q"]     if res["pump_flow"]    else 0
                        pwf = res["pump_flow"]["pwf"]   if res["pump_flow"]    else 0
                        eff = res["pump_efficiency"]
                        table_rows.append({
                            "Correlación":            m_label,
                            "Q Natural (STB/D)":      f"{q_n:.0f}",
                            "Q con BES (STB/D)":      f"{q_p:.0f}",
                            "Incremento (STB/D)":     f"{q_p - q_n:.0f}",
                            "Pwf operación (psi)":    f"{pwf:.0f}",
                            "Eficiencia bomba (%)":   f"{eff * 100:.1f}",
                        })
                    st.subheader("Tabla comparativa")
                    st.dataframe(
                        _pd.DataFrame(table_rows),
                        use_container_width=True,
                        hide_index=True,
                    )

            except Exception as _exc:
                st.error(f"❌ Error en análisis nodal: {_exc}")
                import traceback as _tb
                st.expander("Detalle del error").write(_tb.format_exc())

# ---------------------------------------------------------------------------
# Section: Acerca de
# ---------------------------------------------------------------------------
elif section == "ℹ️ Acerca de":
    st.header("ℹ️ Acerca de BES Designer")

    st.markdown("""
**BES Designer** es una herramienta para el diseño automatizado y selección de
equipos para sistemas de Bombeo Electrosumergible (BES/ESP) en pozos de petróleo.

El motor de cálculo implementa los procedimientos estándar de la industria en
10 módulos Python con más de 400 tests automatizados.

---

### Metodología de diseño

| Módulo | Descripción |
|---|---|
| IPR | Vogel, Linear, Fetkovich, Combined |
| PVT | Correlaciones de Standing, DAK (gas z-factor) |
| TDH | Hazen-Williams, perfil hidrostático |
| Diseño de bomba | Interpolación de curvas, corrección por viscosidad (HI) |
| Diseño eléctrico | Motor, cable, transformador |
| Gas handling | Método de incrementos de presión (Brown §4.53103) |
| Recomendador | Scoring multi-criterio + diversificación por fabricante |

---

### Referencias bibliográficas

- **Brown, K.E.** (1984). *The Technology of Artificial Lift Methods, Vol. 2b:
  Electric Submersible Pumping Systems*. PennWell Books.
- **Takacs, G.** (2009). *Electrical Submersible Pumps Manual*. Gulf Professional Publishing.
- **Vogel, J.V.** (1968). Inflow Performance Relationships for Solution-Gas Drive Wells.
  *Journal of Petroleum Technology*, 20(1), 83–92. SPE-1476.
- **Standing, M.B.** (1947). A Pressure-Volume-Temperature Correlation for Mixtures of
  California Oils and Gases. *API Drilling and Production Practice*.
- **Dranchuk, P.M. & Abou-Kassem, H.** (1975). Calculation of z-Factors for Natural Gases
  Using Equations of State. *Journal of Canadian Petroleum Technology*. JCPT-75-03-03.

---

### Créditos

Desarrollado como proyecto de tesis de grado en Ingeniería de Petróleo.

| | |
|---|---|
| **Versión BES Designer** | 1.0.0 (Fase 10) |
| **Tests automatizados** | 400+ |
| **Módulos de cálculo** | 10 |
| **Fuente** | [GitHub — placeholder](https://github.com/placeholder/bes_designer) |
""")
