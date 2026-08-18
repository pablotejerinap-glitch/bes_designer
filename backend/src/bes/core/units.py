"""Conversión de unidades y auxiliares del método métrico.

En este proyecto conviven **dos sistemas de unidades**, y este módulo es el
único lugar donde se pasa de uno al otro.

El **camino de campo** (``tdh.py``, ``pump_design.py``, …) trabaja en unidades
de campo norteamericanas: psia, °F, STB/d, ft, in. Es el sistema del libro de
Brown y de los catálogos de los fabricantes.

El **camino métrico** (``metric_design.py``, método de cátedra "ESP 01")
trabaja en kg/cm², m, °C, m³/d y g/cm³, que es como está planteado el
ejercicio de la materia.

Tener las conversiones acá aisladas permite que los dos caminos convivan sin
duplicar constantes mágicas desparramadas por el código.

Las constantes
--------------
    1 kgf/cm²  = 14.223343 psi
    1 m        = 3.280839895 ft
    1 m³       = 6.289810 bbl
    1 kgf/cm²  ≈ 10 m de columna de agua (convención de atmósfera técnica)

Nota sobre las leyes de afinidad
--------------------------------
Los atajos ``affinity_*`` de este módulo son los de velocidad pura que usa el
camino métrico, y **delegan** en :mod:`bes.core.affinity`. Hay una sola
implementación de las leyes en todo el proyecto.
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
    """Convierte caudal de m³/d a bbl/d."""
    return q_m3d * M3D_TO_BPD


def bpd_to_m3d(q_bpd: float) -> float:
    """Convierte caudal de bbl/d a m³/d."""
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
#
# Atajos de velocidad pura para el camino métrico. La implementación completa
# —con diámetro de impulsor y gravedad específica— vive en ``bes.core.affinity``
# y es la que usan estas tres funciones: una sola fuente de verdad para las
# leyes, dos formas de llamarlas.
# ---------------------------------------------------------------------------

def affinity_flow(q: float, n_from: float, n_to: float) -> float:
    """Ley de afinidad para el caudal: ``Q2 = Q1·(N2/N1)``.

    Atajo de velocidad pura para el camino métrico. Delega en
    :mod:`bes.core.affinity`, que es la única implementación de las leyes.
    """
    from bes.core.affinity import scale_flow
    return scale_flow(q, n_from, n_to)


def affinity_head(h: float, n_from: float, n_to: float) -> float:
    """Scale head by the affinity law: H2 = H1·(N2/N1)²."""
    from bes.core.affinity import scale_head
    return scale_head(h, n_from, n_to)


def affinity_power(hp: float, n_from: float, n_to: float) -> float:
    """Scale power by the affinity law: HP2 = HP1·(N2/N1)³."""
    from bes.core.affinity import scale_power
    return scale_power(hp, n_from, n_to)
