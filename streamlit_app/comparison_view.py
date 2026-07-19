"""
Side-by-side comparison of the top-N ESP design recommendations.
"""
from __future__ import annotations

import streamlit as st

_MEDALS = ["🥇", "🥈", "🥉"]


def render_comparison(recommendations: list[dict]) -> None:
    """Display top recommendations in parallel columns for easy comparison.

    Args:
        recommendations: List of recommendation dicts from
            generate_recommendations()["recommendations"].
    """
    if not recommendations:
        st.info("No hay recomendaciones disponibles. Calculá el diseño primero.")
        return

    n = min(len(recommendations), 3)
    cols = st.columns(n)

    for i, (col, rec) in enumerate(zip(cols, recommendations[:n])):
        dr     = rec["design"]
        medal  = _MEDALS[i] if i < len(_MEDALS) else f"#{rec['rank']}"
        delta  = None

        # Score delta vs best
        if i > 0:
            best_score = recommendations[0]["score"]
            delta = f"{rec['score'] - best_score:+.2f}"

        with col:
            st.markdown(f"## {medal} Opción {rec['rank']}")
            st.markdown(f"**{dr.pump_manufacturer}** — {dr.pump_model}")
            st.caption(f"Serie: {dr.pump_series}  |  OD: {dr.pump_od:.3f}\"")

            st.metric(
                label="Score total",
                value=f"{rec['score']:.2f} / 10",
                delta=delta,
                delta_color="normal",
            )

            # Score breakdown
            m = rec["metrics"]
            st.progress(m["efficiency"] / 10.0,
                        text=f"Eficiencia: {m['efficiency']:.1f}/10")
            st.progress(m["flexibility"] / 10.0,
                        text=f"Flexibilidad (BEP): {m['flexibility']:.1f}/10")
            st.progress(m["provider"] / 10.0,
                        text=f"Preferencia de proveedor: {m['provider']:.1f}/10")

            st.divider()

            # Compact specs table
            st.markdown("**Resumen técnico**")
            st.markdown(f"""
| | |
|---|---|
| Etapas | {dr.num_stages} |
| HP motor | {dr.motor_hp:.0f} hp |
| Voltaje motor | {dr.motor_voltage:.0f} V |
| Amperaje | {dr.motor_amperage:.0f} A |
| Eficiencia bomba | {dr.pump_efficiency:.1%} |
| Transformador | {dr.transformer_kva:.0f} kVA |
| TDH | {dr.total_head_required:.0f} ft |
| PIP | {dr.intake_pressure:.0f} psi |
| Cable | #{dr.cable_awg} {dr.cable_type} |
| GIP en intake | {dr.gip_fraction:.1%} |
| Efic. sistema | {dr.system_efficiency:.1%} |
""")

            st.divider()

            # Rationale
            st.caption("**Justificación:**")
            st.caption(rec["rationale"])

            # Warnings
            for w in dr.warnings:
                st.warning(f"⚠️ {w}", icon=None)

            st.divider()

            # Selection button
            if st.button(
                f"✅ Seleccionar esta opción",
                key=f"select_rec_{i}",
                use_container_width=True,
                type="primary" if i == st.session_state.get("selected_rec_idx", 0) else "secondary",
            ):
                st.session_state["selected_rec_idx"] = i
                st.success(
                    f"✅ Opción {rec['rank']} seleccionada. "
                    "Volvé a '⚙️ Diseño BES' para ver el resultado completo."
                )

            if st.session_state.get("selected_rec_idx", 0) == i:
                st.success("← Opción actualmente seleccionada")
