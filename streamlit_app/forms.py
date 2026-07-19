"""
Input forms for BES Designer — Phase 10 UI.
Renders the 5-tab well data form and handles example loading / saving.
"""
from __future__ import annotations

import warnings

import streamlit as st

from bes.core.models import (
    DesignObjectives,
    DriveMechanism,
    Fluid,
    IPRMethod,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)

# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

_CASING_ID_MAP: dict[tuple[float, float], float] = {
    (4.5,  9.5): 4.090, (4.5, 11.6): 4.000, (4.5, 13.5): 3.920,
    (5.5, 14.0): 4.950, (5.5, 17.0): 4.892, (5.5, 20.0): 4.778,
    (7.0, 17.0): 6.538, (7.0, 20.0): 6.456, (7.0, 23.0): 6.366,
    (7.0, 26.0): 6.276, (7.0, 29.0): 6.184,
    (8.625, 24.0): 8.097, (8.625, 32.0): 7.921,
    (8.625, 36.0): 7.825, (8.625, 40.0): 7.725,
}
_CASING_OD_DEFAULT_ID = {4.5: 4.090, 5.5: 4.892, 7.0: 6.366, 8.625: 7.825}
_TUBING_ID_MAP = {2.375: 1.995, 2.875: 2.441, 3.5: 2.992}

_IPR_OPTIONS   = ["VOGEL", "LINEAR", "FETKOVICH", "COMBINED"]
_DRIVE_OPTIONS = ["SOLUTION_GAS", "WATER_DRIVE", "GAS_CAP", "COMBINATION"]
_DRIVE_LABELS  = {
    "SOLUTION_GAS": "Solution Gas Drive",
    "WATER_DRIVE":  "Water Drive",
    "GAS_CAP":      "Gas Cap Drive",
    "COMBINATION":  "Combination Drive",
}

# ---------------------------------------------------------------------------
# Example datasets
# ---------------------------------------------------------------------------

_EXAMPLE_2A: dict = {
    # Reservoir
    "frm_static_pressure": 2500.0, "frm_bubble_point": 1500.0,
    "frm_pi": 1.0, "frm_ipr_method": "VOGEL",
    "frm_reservoir_temp": 180.0, "frm_datum_depth": 5000.0,
    "frm_drive": "SOLUTION_GAS",
    # Fluid
    "frm_oil_api": 35.0, "frm_water_cut": 0.30, "frm_gor": 150.0,
    "frm_gas_sg": 0.65, "frm_water_sg": 1.05, "frm_visc_dead": 5.0,
    "frm_visc_temp_ref": 100.0, "frm_h2s": 0.0, "frm_co2": 0.0,
    "frm_sand": False,
    # Geometry
    "frm_total_depth": 5000.0, "frm_casing_od": 7.0, "frm_casing_weight": 23.0,
    "frm_casing_id": 6.366, "frm_tubing_od": 2.875, "frm_tubing_id": 2.441,
    "frm_perf_top": 4500.0, "frm_perf_bottom": 4800.0,
    "frm_deviation": 5.0, "frm_wh_temp": 80.0, "frm_bht": 180.0,
    # Surface
    "frm_whp": 100.0, "frm_fl_length": 1000.0, "frm_fl_id": 3.0,
    "frm_fl_elev": 0.0, "frm_sep_p": 50.0,
    "frm_voltage": 4160.0, "frm_freq": 60.0,
    # Objectives
    "frm_target_q": 1200.0, "frm_safety_depth": 100.0,
    "frm_allow_vent": False, "frm_max_gip": 0.10,
    "frm_design_life": 5.0, "frm_vsd": False,
    "frm_preferred_mfr": "Sin preferencia",
}

# Option shown for "no provider preference"
_NO_PREFERENCE = "Sin preferencia"

_EXAMPLE_3A: dict = {
    # Reservoir (depleted gassy — Pb > Pr, warns but valid)
    "frm_static_pressure": 2000.0, "frm_bubble_point": 2300.0,
    "frm_pi": 0.5, "frm_ipr_method": "VOGEL",
    "frm_reservoir_temp": 160.0, "frm_datum_depth": 7000.0,
    "frm_drive": "SOLUTION_GAS",
    # Fluid
    "frm_oil_api": 35.0, "frm_water_cut": 0.50, "frm_gor": 500.0,
    "frm_gas_sg": 0.65, "frm_water_sg": 1.07, "frm_visc_dead": 5.0,
    "frm_visc_temp_ref": 100.0, "frm_h2s": 0.0, "frm_co2": 0.0,
    "frm_sand": False,
    # Geometry
    "frm_total_depth": 7500.0, "frm_casing_od": 7.0, "frm_casing_weight": 23.0,
    "frm_casing_id": 6.366, "frm_tubing_od": 2.875, "frm_tubing_id": 2.441,
    "frm_perf_top": 6800.0, "frm_perf_bottom": 7000.0,
    "frm_deviation": 0.0, "frm_wh_temp": 100.0, "frm_bht": 160.0,
    # Surface
    "frm_whp": 150.0, "frm_fl_length": 2000.0, "frm_fl_id": 3.0,
    "frm_fl_elev": 0.0, "frm_sep_p": 100.0,
    "frm_voltage": 4160.0, "frm_freq": 60.0,
    # Objectives
    "frm_target_q": 400.0, "frm_safety_depth": 100.0,
    "frm_allow_vent": True, "frm_max_gip": 0.15,
    "frm_design_life": 5.0, "frm_vsd": False,
}

_FIELD_DEFAULTS: dict = {
    "frm_static_pressure": 2000.0, "frm_bubble_point": 2300.0,
    "frm_pi": 0.95, "frm_ipr_method": "VOGEL",
    "frm_reservoir_temp": 170.0, "frm_datum_depth": 5950.0,
    "frm_drive": "SOLUTION_GAS",
    "frm_oil_api": 40.0, "frm_water_cut": 0.30, "frm_gor": 500.0,
    "frm_gas_sg": 0.75, "frm_water_sg": 1.05, "frm_visc_dead": 3.6,
    "frm_visc_temp_ref": 100.0, "frm_h2s": 0.0, "frm_co2": 0.0,
    "frm_sand": False,
    "frm_total_depth": 6150.0, "frm_casing_od": 7.0, "frm_casing_weight": 17.0,
    "frm_casing_id": 6.538, "frm_tubing_od": 2.875, "frm_tubing_id": 2.441,
    "frm_perf_top": 5900.0, "frm_perf_bottom": 5970.0,
    "frm_deviation": 0.0, "frm_wh_temp": 120.0, "frm_bht": 170.0,
    "frm_whp": 200.0, "frm_fl_length": 2000.0, "frm_fl_id": 4.0,
    "frm_fl_elev": 30.0, "frm_sep_p": 100.0,
    "frm_voltage": 12500.0, "frm_freq": 60.0,
    "frm_target_q": 1250.0, "frm_safety_depth": 100.0,
    "frm_allow_vent": False, "frm_max_gip": 0.10,
    "frm_design_life": 5.0, "frm_vsd": False,
}


def _init_defaults() -> None:
    for k, v in _FIELD_DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _load_example(example_key: str) -> None:
    st.session_state["_load_example"] = example_key
    st.rerun()


def _lookup_casing_id(od: float, weight: float) -> float:
    """Return closest known casing ID for the given OD and weight."""
    key = (od, weight)
    if key in _CASING_ID_MAP:
        return _CASING_ID_MAP[key]
    # Find closest weight for this OD
    candidates = {w: cid for (o, w), cid in _CASING_ID_MAP.items() if o == od}
    if candidates:
        closest_w = min(candidates.keys(), key=lambda w: abs(w - weight))
        return candidates[closest_w]
    return _CASING_OD_DEFAULT_ID.get(od, 6.366)


# ---------------------------------------------------------------------------
# Model builder
# ---------------------------------------------------------------------------

def _build_models() -> tuple:
    """Read all frm_* keys from session_state and construct model objects.

    Returns:
        (Reservoir, Fluid, WellGeometry, SurfaceConditions, DesignObjectives)
    Raises:
        ValueError: if any model validation fails.
    """
    ss = st.session_state

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        reservoir = Reservoir(
            static_pressure=float(ss["frm_static_pressure"]),
            bubble_point=float(ss["frm_bubble_point"]),
            productivity_index=float(ss["frm_pi"]),
            ipr_method=IPRMethod[ss["frm_ipr_method"]],
            reservoir_temp=float(ss["frm_reservoir_temp"]),
            drive_mechanism=DriveMechanism[ss["frm_drive"]],
            datum_depth=float(ss["frm_datum_depth"]),
        )

    fluid = Fluid(
        oil_api=float(ss["frm_oil_api"]),
        water_cut=float(ss["frm_water_cut"]),
        gor=float(ss["frm_gor"]),
        gas_sg=float(ss["frm_gas_sg"]),
        water_sg=float(ss["frm_water_sg"]),
        oil_viscosity_dead=float(ss["frm_visc_dead"]),
        viscosity_temp_ref=float(ss["frm_visc_temp_ref"]),
        bubble_point_pressure=float(ss["frm_bubble_point"]),
        h2s_content=float(ss["frm_h2s"]),
        co2_content=float(ss["frm_co2"]),
        sand_production=bool(ss["frm_sand"]),
    )

    well = WellGeometry(
        total_depth=float(ss["frm_total_depth"]),
        casing_od=float(ss["frm_casing_od"]),
        casing_weight=float(ss["frm_casing_weight"]),
        casing_id=float(ss["frm_casing_id"]),
        tubing_od=float(ss["frm_tubing_od"]),
        tubing_id=float(ss["frm_tubing_id"]),
        perforations_top=float(ss["frm_perf_top"]),
        perforations_bottom=float(ss["frm_perf_bottom"]),
        deviation_max=float(ss["frm_deviation"]),
        wellhead_temp=float(ss["frm_wh_temp"]),
        bottom_hole_temp=float(ss["frm_bht"]),
    )

    surface = SurfaceConditions(
        wellhead_pressure_required=float(ss["frm_whp"]),
        flowline_length=float(ss["frm_fl_length"]),
        flowline_id=float(ss["frm_fl_id"]),
        flowline_elevation_change=float(ss["frm_fl_elev"]),
        separator_pressure=float(ss["frm_sep_p"]),
        power_supply_voltage=float(ss["frm_voltage"]),
        frequency=float(ss["frm_freq"]),
    )

    _mfr = ss.get("frm_preferred_mfr", _NO_PREFERENCE)
    objectives = DesignObjectives(
        target_flow_rate=float(ss["frm_target_q"]),
        safety_margin_depth=float(ss["frm_safety_depth"]),
        allow_gas_venting=bool(ss["frm_allow_vent"]),
        max_gip=float(ss["frm_max_gip"]),
        design_life_years=float(ss["frm_design_life"]),
        use_vsd=bool(ss["frm_vsd"]),
        preferred_manufacturer=("" if _mfr == _NO_PREFERENCE else str(_mfr)),
    )

    return reservoir, fluid, well, surface, objectives


# ---------------------------------------------------------------------------
# Inline validation warnings (non-blocking)
# ---------------------------------------------------------------------------

def _show_validation_warnings() -> None:
    ss = st.session_state

    pb  = ss.get("frm_bubble_point", 0)
    pr  = ss.get("frm_static_pressure", 1)
    if pb > pr:
        st.warning(
            f"⚠️ Punto de burbuja ({pb:.0f} psi) > Presión estática ({pr:.0f} psi). "
            "Válido para reservorios depletados con empuje por gas en solución (Vogel aplica)."
        )

    pt = ss.get("frm_perf_top", 0)
    pb2 = ss.get("frm_perf_bottom", 0)
    if pb2 <= pt:
        st.warning("⚠️ Perforación inferior debe ser mayor que la superior.")

    td = ss.get("frm_total_depth", 0)
    if pb2 > td:
        st.warning("⚠️ Perforaciones sobrepasan la profundidad total del pozo.")

    wh_t = ss.get("frm_wh_temp", 0)
    bht  = ss.get("frm_bht", 0)
    if bht <= wh_t:
        st.warning("⚠️ Temperatura BHP debe ser mayor que la temperatura en cabezal.")

    cid = ss.get("frm_casing_id", 0)
    cod = ss.get("frm_casing_od", 0)
    if cid >= cod:
        st.warning("⚠️ ID del casing debe ser menor que el OD.")

    tod = ss.get("frm_tubing_od", 0)
    tid = ss.get("frm_tubing_id", 0)
    if tid >= tod:
        st.warning("⚠️ ID del tubing debe ser menor que el OD.")
    if tod >= cid:
        st.warning("⚠️ OD del tubing debe ser menor que el ID del casing.")

    target_q = ss.get("frm_target_q", 0)
    if target_q <= 0:
        st.warning("⚠️ La tasa objetivo debe ser mayor que cero.")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_data_forms() -> None:
    """Render the 5-tab well data input form."""
    st.header("📝 Datos del Pozo")
    _init_defaults()

    # Apply pending example BEFORE any widgets are instantiated
    _ex = st.session_state.pop("_load_example", None)
    if _ex == "2A":
        for k, v in _EXAMPLE_2A.items():
            st.session_state[k] = v
        st.rerun()
    elif _ex == "3A":
        for k, v in _EXAMPLE_3A.items():
            st.session_state[k] = v
        st.rerun()

    tab_res, tab_flu, tab_geo, tab_sup, tab_obj = st.tabs([
        "🪨 Reservorio", "💧 Fluido", "🔧 Geometría", "🏭 Superficie", "🎯 Objetivos"
    ])

    # ------------------------------------------------------------------
    # Tab 1: Reservorio
    # ------------------------------------------------------------------
    with tab_res:
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Presión estática (psi)", min_value=10.0, max_value=20000.0,
                            step=50.0, key="frm_static_pressure")
            st.number_input("Punto de burbuja (psi)", min_value=0.0, max_value=20000.0,
                            step=50.0, key="frm_bubble_point")
            st.number_input("Índice de productividad (STB/d/psi)", min_value=0.01,
                            max_value=50.0, step=0.05, key="frm_pi")
            st.selectbox("Método IPR", _IPR_OPTIONS, key="frm_ipr_method")
        with col2:
            st.number_input("Temperatura de reservorio (°F)", min_value=50.0,
                            max_value=450.0, step=5.0, key="frm_reservoir_temp")
            st.number_input("Profundidad datum (ft)", min_value=100.0,
                            max_value=25000.0, step=50.0, key="frm_datum_depth")
            st.selectbox("Mecanismo de empuje",
                         list(_DRIVE_LABELS.keys()),
                         format_func=lambda k: _DRIVE_LABELS[k],
                         key="frm_drive")

    # ------------------------------------------------------------------
    # Tab 2: Fluido
    # ------------------------------------------------------------------
    with tab_flu:
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Gravedad API del crudo (°API)", min_value=5.0,
                            max_value=70.0, step=0.5, key="frm_oil_api")
            st.slider("Corte de agua (fracción)", 0.0, 1.0, step=0.01,
                      key="frm_water_cut")
            st.number_input("RGA — Gas-Oil Ratio (scf/STB)", min_value=0.0,
                            max_value=10000.0, step=10.0, key="frm_gor")
            st.number_input("Gravedad específica del gas (aire=1)", min_value=0.5,
                            max_value=1.5, step=0.01, key="frm_gas_sg")
            st.number_input("Gravedad específica del agua (agua=1)", min_value=1.0,
                            max_value=1.3, step=0.01, key="frm_water_sg")
        with col2:
            st.number_input("Viscosidad crudo muerto (cp)", min_value=0.1,
                            max_value=5000.0, step=0.1, key="frm_visc_dead")
            st.number_input("Temperatura ref. viscosidad (°F)", min_value=50.0,
                            max_value=300.0, step=5.0, key="frm_visc_temp_ref")
            st.number_input("Contenido H₂S (ppm)", min_value=0.0,
                            max_value=1000000.0, step=10.0, key="frm_h2s")
            st.number_input("Contenido CO₂ (ppm)", min_value=0.0,
                            max_value=1000000.0, step=10.0, key="frm_co2")
            st.checkbox("Producción de arena", key="frm_sand")

    # ------------------------------------------------------------------
    # Tab 3: Geometría
    # ------------------------------------------------------------------
    with tab_geo:
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Profundidad total (ft MD)", min_value=500.0,
                            max_value=25000.0, step=50.0, key="frm_total_depth")

            casing_od_val = st.selectbox("Casing OD (in)", [4.5, 5.5, 7.0, 8.625],
                                         key="frm_casing_od")
            st.number_input("Peso de casing (lb/ft)", min_value=5.0,
                            max_value=80.0, step=0.5, key="frm_casing_weight")
            typical_cid = _lookup_casing_id(
                float(st.session_state["frm_casing_od"]),
                float(st.session_state["frm_casing_weight"]),
            )
            st.caption(f"ID típico para OD={casing_od_val}\" "
                       f"@ {st.session_state['frm_casing_weight']:.1f} lb/ft: "
                       f"**{typical_cid:.3f} in**")
            st.number_input("Casing ID (in) — drift", min_value=1.0,
                            max_value=15.0, step=0.001, format="%.3f",
                            key="frm_casing_id")

            tubing_od_val = st.selectbox("Tubing OD (in)", [2.375, 2.875, 3.5],
                                         key="frm_tubing_od")
            st.caption(f"ID típico para tubing {tubing_od_val}\": "
                       f"**{_TUBING_ID_MAP.get(float(tubing_od_val), 2.441):.3f} in**")
            st.number_input("Tubing ID (in)", min_value=0.5, max_value=5.0,
                            step=0.001, format="%.3f", key="frm_tubing_id")

        with col2:
            st.number_input("Tope de perforaciones (ft MD)", min_value=100.0,
                            max_value=25000.0, step=10.0, key="frm_perf_top")
            st.number_input("Base de perforaciones (ft MD)", min_value=100.0,
                            max_value=25000.0, step=10.0, key="frm_perf_bottom")
            st.number_input("Desviación máxima (°)", min_value=0.0,
                            max_value=90.0, step=1.0, key="frm_deviation")
            st.number_input("Temperatura cabezal (°F)", min_value=32.0,
                            max_value=200.0, step=5.0, key="frm_wh_temp")
            st.number_input("Temperatura BHP (°F)", min_value=50.0,
                            max_value=450.0, step=5.0, key="frm_bht")

    # ------------------------------------------------------------------
    # Tab 4: Superficie
    # ------------------------------------------------------------------
    with tab_sup:
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Presión mín. en cabezal (psi)", min_value=0.0,
                            max_value=5000.0, step=10.0, key="frm_whp")
            st.number_input("Longitud de flowline (ft)", min_value=0.0,
                            max_value=100000.0, step=100.0, key="frm_fl_length")
            st.number_input("ID de flowline (in)", min_value=0.5,
                            max_value=24.0, step=0.5, key="frm_fl_id")
            st.number_input("Cambio de elevación flowline (ft)", min_value=-500.0,
                            max_value=500.0, step=5.0, key="frm_fl_elev")
        with col2:
            st.number_input("Presión de separador (psi)", min_value=0.0,
                            max_value=2000.0, step=10.0, key="frm_sep_p")
            st.number_input("Voltaje de suministro (V)", min_value=200.0,
                            max_value=30000.0, step=100.0, key="frm_voltage")
            st.selectbox("Frecuencia de red (Hz)", [60.0, 50.0],
                         format_func=lambda f: f"{f:.0f} Hz",
                         key="frm_freq")

    # ------------------------------------------------------------------
    # Tab 5: Objetivos
    # ------------------------------------------------------------------
    with tab_obj:
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Tasa de producción objetivo (STB/d)", min_value=10.0,
                            max_value=50000.0, step=50.0, key="frm_target_q")
            st.number_input("Margen de seguridad profundidad (ft)", min_value=0.0,
                            max_value=1000.0, step=10.0, key="frm_safety_depth")
            st.number_input("Vida útil de diseño (años)", min_value=0.5,
                            max_value=30.0, step=0.5, key="frm_design_life")
        with col2:
            st.slider("GIP máximo permitido (fracción)", 0.0, 1.0, step=0.01,
                      key="frm_max_gip")
            st.checkbox("Permitir venteo de gas", key="frm_allow_vent")
            st.checkbox("Usar variador de velocidad (VSD)", key="frm_vsd")

            # Provider preference — populated from the loaded catalog
            _cat = st.session_state.get("catalog")
            _mfrs = []
            if _cat is not None:
                _mfrs = sorted({p.manufacturer for p in _cat.get_all_pumps()})
            st.selectbox(
                "Proveedor preferido",
                [_NO_PREFERENCE] + _mfrs,
                key="frm_preferred_mfr",
                help="Si elegís un proveedor, sus equipos puntúan más alto en el ranking "
                     "(30 % del score). 'Sin preferencia' no sesga la selección.",
            )

    # ------------------------------------------------------------------
    # Validation warnings (live)
    # ------------------------------------------------------------------
    st.divider()
    _show_validation_warnings()

    # ------------------------------------------------------------------
    # Action buttons
    # ------------------------------------------------------------------
    bc1, bc2, bc3 = st.columns(3)

    with bc1:
        if st.button("📥 Cargar Ejemplo 2A", use_container_width=True):
            _load_example("2A")

    with bc2:
        if st.button("📥 Cargar Ejemplo 3A", use_container_width=True):
            _load_example("3A")

    with bc3:
        if st.button("💾 Guardar Datos", type="primary", use_container_width=True):
            try:
                reservoir, fluid, well, surface, objectives = _build_models()
                st.session_state.reservoir  = reservoir
                st.session_state.fluid      = fluid
                st.session_state.well       = well
                st.session_state.surface    = surface
                st.session_state.objectives = objectives
                st.session_state.design_results = None  # invalidate previous results
                st.success("✅ Datos guardados correctamente. Ir a '⚙️ Diseño BES' para calcular.")
            except ValueError as exc:
                st.error(f"❌ Error de validación: {exc}")
            except Exception as exc:
                st.error(f"❌ Error inesperado: {exc}")
