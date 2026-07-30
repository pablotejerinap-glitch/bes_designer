"""Builders de figuras Plotly.

Agnósticos de framework a propósito: **no importan streamlit**. Los consume
tanto la API (``fig.to_json()`` → el front lo renderiza con react-plotly.js)
como la app Streamlit. Ver ``.claude/rules/architecture.md``.
"""
from bes.plotting.plots import (
    plot_ipr_curve,
    plot_nodal_analysis,
    plot_nodal_comparison,
    plot_pressure_profile,
    plot_pump_catalog_curve,
    plot_pump_curve,
    plot_sensitivity_analysis,
)

__all__ = [
    "plot_ipr_curve",
    "plot_nodal_analysis",
    "plot_nodal_comparison",
    "plot_pressure_profile",
    "plot_pump_catalog_curve",
    "plot_pump_curve",
    "plot_sensitivity_analysis",
]
