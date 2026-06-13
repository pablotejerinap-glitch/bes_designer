"""
Results display for a single BES/ESP design recommendation.
"""
from __future__ import annotations

import streamlit as st

from core.tdh import calculate_tdh


def _get_pump_obj(pump_model: str):
    """Return PumpCurve object from the session-state catalog, or None."""
    catalog = st.session_state.get("catalog")
    if catalog is None:
        return None
    try:
        return next(p for p in catalog.get_all_pumps() if p.model == pump_model)
    except StopIteration:
        return None


def _pwf_from_ipr(reservoir, target_q: float) -> float:
    """Estimate flowing BHP at target_q for the IPR plot operating point."""
    pr = reservoir.static_pressure
    pi = reservoir.productivity_index
    pb = reservoir.bubble_point

    if reservoir.ipr_method.name == "LINEAR":
        return max(0.0, pr - target_q / pi)

    # Vogel / Combined / Fetkovich — use Vogel
    if pb >= pr:
        qmax = pi * pr / 1.8
    else:
        q_pb = pi * (pr - pb)
        qmax = q_pb + pi * pb / 1.8

    ratio = min(target_q / max(qmax, 1e-9), 1.0)
    disc = 0.04 + 3.2 * (1.0 - ratio)
    if disc < 0:
        return 0.0
    return max(0.0, ((-0.2 + disc ** 0.5) / 1.6) * pr)


def render_results(rec: dict) -> None:
    """Display a complete design recommendation.

    Args:
        rec: One element from generate_recommendations()["recommendations"].
             Keys: rank, score, metrics, design (DesignResult), rationale, warnings.
    """
    from ui.plots import plot_ipr_curve, plot_pump_curve, plot_pressure_profile

    dr = rec["design"]

    st.subheader(
        f"{'🥇' if rec['rank'] == 1 else '🥈' if rec['rank'] == 2 else '🥉'} "
        f"Opción {rec['rank']}: {dr.pump_manufacturer} {dr.pump_model} — "
        f"Score {rec['score']:.1f}/10"
    )

    # ------------------------------------------------------------------
    # 1. Key metrics
    # ------------------------------------------------------------------
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Etapas de bomba",    str(dr.num_stages))
    m2.metric("HP del motor",       f"{dr.motor_hp:.0f} hp")
    m3.metric("Eficiencia bomba",   f"{dr.pump_efficiency:.1%}")
    m4.metric("Transformador",      f"{dr.transformer_kva:.0f} kVA")

    # ------------------------------------------------------------------
    # 2. TDH breakdown
    # ------------------------------------------------------------------
    reservoir  = st.session_state.get("reservoir")
    fluid      = st.session_state.get("fluid")
    well       = st.session_state.get("well")
    surface    = st.session_state.get("surface")
    objectives = st.session_state.get("objectives")

    if all(x is not None for x in (reservoir, fluid, well, surface, objectives)):
        with st.expander("🔍 Desglose del TDH", expanded=False):
            try:
                tdh_data = calculate_tdh(
                    reservoir=reservoir,
                    fluid=fluid,
                    well=well,
                    surface=surface,
                    objectives=objectives,
                    pump_depth=dr.pump_setting_depth,
                    pip=dr.intake_pressure,
                )
                import pandas as pd
                tdh_rows = [
                    ("Elevación vertical",     f"{tdh_data['vertical_lift_ft']:.1f} ft"),
                    ("Fricción en tubería",    f"{tdh_data['tubing_friction_ft']:.1f} ft"),
                    ("Presión cabezal (head)", f"{tdh_data['wellhead_pressure_head_ft']:.1f} ft"),
                    ("PIP (head)",             f"{tdh_data['pip_head_ft']:.1f} ft"),
                    ("**TOTAL TDH**",          f"**{tdh_data['tdh_ft']:.1f} ft**"),
                ]
                st.table(pd.DataFrame(tdh_rows, columns=["Componente", "Valor"]))
                st.caption(f"SG líquido: {tdh_data['sg_liquid']:.3f}  |  "
                           f"Profundidad bomba: {tdh_data['pump_depth_ft']:.0f} ft  |  "
                           f"PIP: {tdh_data['pip_psi']:.0f} psi")
            except Exception as exc:
                st.warning(f"No se pudo calcular el desglose TDH: {exc}")

    # ------------------------------------------------------------------
    # 3. Equipment specifications
    # ------------------------------------------------------------------
    with st.expander("⚙️ Especificaciones completas", expanded=False):
        s1, s2 = st.columns(2)

        with s1:
            st.markdown("**Bomba seleccionada**")
            st.markdown(f"""
| Campo | Valor |
|---|---|
| Fabricante | {dr.pump_manufacturer} |
| Serie | {dr.pump_series} |
| Modelo | {dr.pump_model} |
| OD | {dr.pump_od:.3f} in |
| Etapas | {dr.num_stages} |
| Profundidad de instalación | {dr.pump_setting_depth:.0f} ft |
| Eficiencia | {dr.pump_efficiency:.1%} |
| Head / etapa | {dr.head_per_stage:.1f} ft |
| HP / etapa | {dr.hp_per_stage:.3f} hp |
| HP total bomba | {dr.total_pump_hp:.1f} hp |
| PIP | {dr.intake_pressure:.0f} psi |
""")

            st.markdown("**Motor**")
            st.markdown(f"""
| Campo | Valor |
|---|---|
| Fabricante | {dr.motor_manufacturer} |
| Modelo | {dr.motor_model} |
| HP nominal | {dr.motor_hp:.0f} hp |
| Voltaje | {dr.motor_voltage:.0f} V |
| Amperaje | {dr.motor_amperage:.0f} A |
| OD | {dr.motor_od:.3f} in |
| Longitud | {dr.motor_length:.1f} ft |
""")

            st.markdown("**Sello / Protector**")
            if dr.seal_model:
                st.markdown(f"""
| Campo | Valor |
|---|---|
| Fabricante | {dr.seal_manufacturer} |
| Modelo | {dr.seal_model} |
| Tipo | {dr.seal_type} |
| Capacidad de empuje | {dr.seal_thrust_capacity_lbs:.0f} lbs |
| Empuje axial estimado | {dr.axial_thrust_lbs:.0f} lbs |
""")
            else:
                st.caption("Sin protector compatible en catálogo para esta serie de motor.")

        with s2:
            st.markdown("**Cable eléctrico**")
            st.markdown(f"""
| Campo | Valor |
|---|---|
| Tipo | {dr.cable_type} |
| Calibre (AWG) | #{dr.cable_awg} |
| Caída de tensión | {dr.cable_voltage_drop:.0f} V |
| Voltaje superficial requerido | {dr.surface_voltage_required:.0f} V |
""")

            st.markdown("**Transformador**")
            st.markdown(f"""
| Campo | Valor |
|---|---|
| Capacidad | {dr.transformer_kva:.0f} kVA |
| GIP en intake | {dr.gip_fraction:.1%} |
| Eficiencia del sistema | {dr.system_efficiency:.1%} |
| Frecuencia operación | {dr.operating_frequency:.0f} Hz |
| Tasa alcanzada | {dr.flow_rate_achieved:.0f} STB/d |
""")

            st.markdown("**Manejo de gas y monitoreo**")
            _gh = (
                f"{dr.gas_handler_manufacturer} {dr.gas_handler_model} "
                f"({dr.gas_handler_type}, η {dr.gas_handler_efficiency:.0%})"
                if dr.gas_handler_model else "No requerido (GIP bajo)"
            )
            _sn = (
                f"{dr.sensor_manufacturer} {dr.sensor_model}"
                if dr.sensor_model else "—"
            )
            st.markdown(f"""
| Campo | Valor |
|---|---|
| Separador de gas | {_gh} |
| Sensor de fondo | {_sn} |
""")

    # ------------------------------------------------------------------
    # 4. Rationale
    # ------------------------------------------------------------------
    with st.expander("💬 Justificación técnica", expanded=False):
        st.info(rec["rationale"])

    # ------------------------------------------------------------------
    # 5. Design warnings
    # ------------------------------------------------------------------
    for w in dr.warnings:
        st.warning(f"⚠️ {w}")

    if dr.gip_fraction > 0.30:
        st.error(
            f"🔴 Gas libre en intake: {dr.gip_fraction:.1%} — "
            "Se recomienda separador de gas de fondo."
        )
    elif dr.gip_fraction > 0.10:
        st.warning(
            f"🟡 Gas libre en intake: {dr.gip_fraction:.1%} — "
            "Considerar separador de gas."
        )

    # ------------------------------------------------------------------
    # 6. Plots
    # ------------------------------------------------------------------
    st.divider()
    st.markdown("### Gráficos")

    if reservoir is not None:
        plot_col1, plot_col2 = st.columns(2)

        with plot_col1:
            try:
                pwf = _pwf_from_ipr(reservoir, dr.flow_rate_achieved)
                fig_ipr = plot_ipr_curve(
                    reservoir,
                    operating_point=(dr.flow_rate_achieved, pwf),
                )
                st.plotly_chart(fig_ipr, use_container_width=True)
            except Exception as exc:
                st.warning(f"No se pudo graficar la curva IPR: {exc}")

        with plot_col2:
            pump_obj = _get_pump_obj(dr.pump_model)
            if pump_obj is not None:
                try:
                    fig_pump = plot_pump_curve(pump_obj, dr.flow_rate_achieved, dr.num_stages)
                    st.plotly_chart(fig_pump, use_container_width=True)
                except Exception as exc:
                    st.warning(f"No se pudo graficar la curva de bomba: {exc}")
            else:
                st.info("Curva de bomba no disponible para este modelo.")

        if well is not None and surface is not None:
            try:
                fig_prof = plot_pressure_profile(well, dr, surface, fluid)
                st.plotly_chart(fig_prof, use_container_width=True)
            except Exception as exc:
                st.warning(f"No se pudo graficar el perfil de presiones: {exc}")
