"""
Sensitivity analysis view — shows how key design metrics respond
to variations in a single input parameter.
"""
from __future__ import annotations

import streamlit as st

from services.sensitivity_service import (
    DEFAULT_N_POINTS,
    PARAM_LABELS,
    base_value,
    run_sensitivity,
    sweep_range,
)
from ui.plots import plot_sensitivity_analysis

_PARAM_LABELS = PARAM_LABELS
_N_POINTS = DEFAULT_N_POINTS


def render_sensitivity() -> None:
    """Render the sensitivity analysis section."""
    reservoir  = st.session_state.get("reservoir")
    fluid      = st.session_state.get("fluid")
    well       = st.session_state.get("well")
    surface    = st.session_state.get("surface")
    objectives = st.session_state.get("objectives")
    catalog    = st.session_state.get("catalog")

    if any(x is None for x in (reservoir, fluid, well, surface, objectives, catalog)):
        st.error("❌ Guardá los datos del pozo primero en '📝 Datos del Pozo'.")
        return

    st.markdown(
        "Varía un parámetro de entrada dentro de un rango y observá cómo "
        "cambian HP, etapas, eficiencia y TDH del diseño óptimo."
    )

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------
    ctrl_col1, ctrl_col2 = st.columns([1, 1])

    with ctrl_col1:
        param = st.selectbox(
            "Parámetro a variar",
            list(_PARAM_LABELS.keys()),
            format_func=lambda k: _PARAM_LABELS[k],
            key="sens_param",
        )

    # Base value for the selected parameter
    base_val = base_value(reservoir, fluid, objectives, param)

    with ctrl_col2:
        pct_range = st.slider(
            "Rango de variación (±%)", min_value=10, max_value=60,
            value=40, step=5, key="sens_pct_range"
        )

    lo, hi = sweep_range(base_val, param, pct_range)

    st.info(
        f"Rango: {lo:.3g} → {hi:.3g}  |  "
        f"Valor base: **{base_val:.3g}**  |  "
        f"{_N_POINTS} puntos de evaluación"
    )

    # ------------------------------------------------------------------
    # Run analysis
    # ------------------------------------------------------------------
    if st.button("▶ Correr análisis", type="primary"):
        progress_bar = st.progress(0.0, text="Calculando...")

        def _progress(idx: int, total: int, val: float) -> None:
            progress_bar.progress(
                (idx + 1) / total,
                text=f"Punto {idx + 1}/{total} — {_PARAM_LABELS[param]} = {val:.3g}",
            )

        sens = run_sensitivity(
            reservoir, fluid, well, surface, objectives, catalog, param,
            pct_range_pct=pct_range, n_points=_N_POINTS, progress=_progress,
        )
        progress_bar.empty()

        if not sens["param_values"]:
            st.error("❌ No se encontraron diseños válidos en el rango seleccionado.")
            return

        st.session_state["sens_results"] = sens

    # ------------------------------------------------------------------
    # Show results (persists after button press)
    # ------------------------------------------------------------------
    sens = st.session_state.get("sens_results")
    if sens is not None:
        st.divider()
        st.markdown(f"### Resultados — Variación de {sens['param_label']}")

        fig = plot_sensitivity_analysis(
            param_values=sens["param_values"],
            metrics_dict=sens["metrics"],
            parameter_label=sens["param_label"],
        )
        st.plotly_chart(fig, use_container_width=True)

        # Summary table
        import pandas as pd
        rows = []
        for x, hp, st_, eff, tdh in zip(
            sens["param_values"],
            sens["metrics"]["HP"],
            sens["metrics"]["Etapas"],
            sens["metrics"]["Eficiencia (%)"],
            sens["metrics"]["TDH (ft)"],
        ):
            rows.append({
                sens["param_label"]: f"{x:.3g}",
                "HP": f"{hp:.0f}",
                "Etapas": f"{st_:.0f}",
                "Eficiencia (%)": f"{eff:.1f}",
                "TDH (ft)": f"{tdh:.0f}",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
