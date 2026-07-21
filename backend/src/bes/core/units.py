"""
Unit conversions and metric-method helpers for BES/ESP design.

The field design path (``bes/core/tdh.py``, ``bes/core/pump_design.py`` …) works in
US oilfield units (psia, °F, STB/d, ft, in).  The *metric* design path
(``bes/core/metric_design.py``, método de cátedra "ESP 01") works in kg/cm², m,
°C, m³/d and g/cm³.  This module isolates every conversion so both paths can
coexist without duplicating magic constants.

References for the constants:
    1 kgf/cm²  = 14.223343 psi
    1 m        = 3.280839895 ft
    1 m³       = 6.289810 bbl
    1 kgf/cm²  ≈ 10 m of water column  (technical-atmosphere convention)
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Primitive conversion factors
# ---------------------------------------------------------------------------

KGFCM2_TO_PSI = 14.223343
PSI_TO_KGFCM2 = 1.0 / KGFCM2_TO_PSI

M_TO_FT = 3.280839895
FT_TO_M = 1.0 / M_TO_FT

M3D_TO_BPD = 6.289810          # 1 m³/d -> bbl/d
BPD_TO_M3D = 1.0 / M3D_TO_BPD

# Head (m of a fluid of specific gravity SG) -> psi.
#   1 m water = 3.28084 ft × 0.433 psi/ft ≈ 1.4206 psi
# Used for the housing burst check (MHP) in the metric method.
M_HEAD_TO_PSI_PER_SG = 0.433 * M_TO_FT   # ≈ 1.4206

# Head (m of water) -> kg/cm²:  1 kg/cm² ≈ 10 m water  => 1 m water = 0.1 kg/cm²
# (see pressure_to_head_m / head_m_to_pressure_kgcm2 for the SG-aware form)


# ---------------------------------------------------------------------------
# Pressure
# ---------------------------------------------------------------------------

def kgfcm2_to_psi(p_kgfcm2: float) -> float:
    """Convert pressure from kgf/cm² to psi."""
    return p_kgfcm2 * KGFCM2_TO_PSI


def psi_to_kgfcm2(p_psi: float) -> float:
    """Convert pressure from psi to kgf/cm²."""
    return p_psi * PSI_TO_KGFCM2


# ---------------------------------------------------------------------------
# Length / depth
# ---------------------------------------------------------------------------

def m_to_ft(x_m: float) -> float:
    """Convert length from meters to feet."""
    return x_m * M_TO_FT


def ft_to_m(x_ft: float) -> float:
    """Convert length from feet to meters."""
    return x_ft * FT_TO_M


# ---------------------------------------------------------------------------
# Flow rate
# ---------------------------------------------------------------------------

def m3d_to_bpd(q_m3d: float) -> float:
    """Convert volumetric flow rate from m³/d to bbl/d."""
    return q_m3d * M3D_TO_BPD


def bpd_to_m3d(q_bpd: float) -> float:
    """Convert volumetric flow rate from bbl/d to m³/d."""
    return q_bpd * BPD_TO_M3D


# ---------------------------------------------------------------------------
# Density / gravity
# ---------------------------------------------------------------------------

def api_to_sg(api: float) -> float:
    """Stock-tank oil specific gravity (water = 1) from °API.

    SG = 141.5 / (131.5 + API)
    """
    return 141.5 / (131.5 + api)


def mixture_specific_gravity(oil_sg: float, water_sg: float, water_cut: float) -> float:
    """Gas-free liquid mixture specific gravity [g/cm³ ≡ SG].

    Pem = Peo·(1 − WC) + Pew·WC

    Args:
        oil_sg: Oil specific gravity [g/cm³].
        water_sg: Water specific gravity [g/cm³].
        water_cut: Produced water fraction [0–1].
    """
    if not (0.0 <= water_cut <= 1.0):
        raise ValueError(f"water_cut must be in [0, 1], got {water_cut}")
    return oil_sg * (1.0 - water_cut) + water_sg * water_cut


# ---------------------------------------------------------------------------
# Pressure <-> head (metric technical convention: 1 kg/cm² ≈ 10 m water)
# ---------------------------------------------------------------------------

def pressure_to_head_m(p_kgfcm2: float, sg: float) -> float:
    """Convert a pressure [kg/cm²] to fluid head [m] for a fluid of gravity *sg*.

    h[m] = P[kg/cm²] · 10 / SG
    """
    if sg <= 0:
        raise ValueError(f"sg must be > 0, got {sg}")
    return p_kgfcm2 * 10.0 / sg


def head_m_to_pressure_kgcm2(h_m: float, sg: float) -> float:
    """Convert a fluid head [m] of fluid gravity *sg* to pressure [kg/cm²].

    P[kg/cm²] = h[m] · SG / 10
    """
    return h_m * sg / 10.0


def head_m_to_psi(h_m: float, sg: float) -> float:
    """Convert a fluid head [m] of fluid gravity *sg* to pressure [psi].

    P[psi] = h[m] · SG · 1.4206
    """
    return h_m * sg * M_HEAD_TO_PSI_PER_SG


# ---------------------------------------------------------------------------
# Affinity laws (centrifugal pump speed change; Brown Table 4.21)
# ---------------------------------------------------------------------------

def affinity_flow(q: float, n_from: float, n_to: float) -> float:
    """Scale flow rate by the affinity law: Q2 = Q1·(N2/N1)."""
    return q * (n_to / n_from)


def affinity_head(h: float, n_from: float, n_to: float) -> float:
    """Scale head by the affinity law: H2 = H1·(N2/N1)²."""
    return h * (n_to / n_from) ** 2


def affinity_power(hp: float, n_from: float, n_to: float) -> float:
    """Scale power by the affinity law: HP2 = HP1·(N2/N1)³."""
    return hp * (n_to / n_from) ** 3
