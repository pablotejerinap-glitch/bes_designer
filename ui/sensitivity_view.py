"""
Sensitivity analysis view — shows how key design metrics respond
to variations in a single input parameter.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import streamlit as st

from recommender.recommendation_engine import generate_recommendations
from ui.plots import plot_sensitivity_analysis

_PARAM_LABELS = {
    "water_cut":       "Corte de agua (WC)",
    "gor":             "GOR (scf/STB)",
    "static_pressure": "Presión de reservorio (psi)",
    "target_flow_rate":"Tasa objetivo (STB/d)",
}

_N_POINTS = 7   # number of evaluation points


def _get_varied_inputs(param: str, value: float):
    """Return (reservoir, fluid, objectives) with *param* set to *value*.

    Reads the base objects from session_state and uses dataclasses.replace()
    to substitute the chosen parameter.
    """
    import warnings as _warnings
    reservoir  = st.session_state.reservoir
    fluid      = st.session_state.fluid
    objectives = st.session_state.objectives

    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore", UserWarning)

        if param == "water_cut":
            v = float(np.clip(value, 0.0, 0.99))
            fluid = replace(fluid, water_cut=v)
        elif param == "gor":
            v = max(0.0, float(value))
            fluid = replace(fluid, gor=v)
        elif param == "static_pressure":
            v = max(50.0, float(value))
            reservoir = replace(reservoir, static_pressure=v)
        elif param == "target_flow_rate":
            v = max(10.0, float(value))
            objectives = replace(objectives, target_flow_rate=v)

    return reservoir, fluid, objectives


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
    base_values = {
        "water_cut":        fluid.water_cut,
        "gor":              fluid.gor,
        "static_pressure":  reservoir.static_pressure,
        "target_flow_rate": objectives.target_flow_rate,
    }
    base_val = base_values[param]

    with ctrl_col2:
        pct_range = st.slider(
            "Rango de variación (±%)", min_value=10, max_value=60,
            value=40, step=5, key="sens_pct_range"
        )

    lo = base_val * (1.0 - pct_range / 100.0)
    hi = base_val * (1.0 + pct_range / 100.0)

    # Clamp to physically valid ranges
    if param == "water_cut":
        lo, hi = max(lo, 0.01), min(hi, 0.99)
    elif param in ("gor", "static_pressure", "target_flow_rate"):
        lo = max(lo, 1.0)

    param_values = np.linspace(lo, hi, _N_POINTS)

    st.info(
        f"Rango: {lo:.3g} → {hi:.3g}  |  "
        f"Valor base: **{base_val:.3g}**  |  "
        f"{_N_POINTS} puntos de evaluación"
    )

    # ------------------------------------------------------------------
    # Run analysis
    # ------------------------------------------------------------------
    if st.button("▶ Correr análisis", type="primary"):
        hp_vals:   list[float] = []
        stage_vals: list[float] = []
        eff_vals:  list[float] = []
        tdh_vals:  list[float] = []
        valid_xs:  list[float] = []

        progress_bar = st.progress(0.0, text="Calculando...")

        for idx, val in enumerate(param_values):
            progress_bar.progress(
                (idx + 1) / _N_POINTS,
                text=f"Punto {idx + 1}/{_N_POINTS} — {_PARAM_LABELS[param]} = {val:.3g}",
            )
            try:
                res_v, flu_v, obj_v = _get_varied_inputs(param, val)
                recs = generate_recommendations(
                    reservoir=res_v,
                    fluid=flu_v,
                    well=well,
                    surface=surface,
                    objectives=obj_v,
                    catalog=catalog,
                    n=1,
                )
                dr = recs["recommendations"][0]["design"]
                hp_vals.append(dr.motor_hp)
                stage_vals.append(float(dr.num_stages))
                eff_vals.append(dr.pump_efficiency * 100.0)
                tdh_vals.append(dr.total_head_required)
                valid_xs.append(float(val))
            except Exception:
                pass  # skip points where no design is feasible

        progress_bar.empty()

        if not valid_xs:
            st.error("❌ No se encontraron diseños válidos en el rango seleccionado.")
            return

        st.session_state["sens_results"] = {
            "param_values": valid_xs,
            "metrics": {
                "HP":            hp_vals,
                "Etapas":        stage_vals,
                "Eficiencia (%)": eff_vals,
                "TDH (ft)":      tdh_vals,
            },
            "param_label": _PARAM_LABELS[param],
        }

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
