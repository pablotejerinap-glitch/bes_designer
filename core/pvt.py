"""
PVT (Pressure-Volume-Temperature) correlations for crude oil, gas, and brine.

Primary reference:
  Standing, M.B., "Volumetric and Phase Behavior of Oil Field Hydrocarbon Systems",
  SPE (1977).

Additional references:
  Dranchuk, P.M. & Abou-Kassem, H., "Calculation of Z Factors for Natural Gases
    Using Equations of State", J. Can. Pet. Tech. (1975) — gas z-factor.
  Beggs, H.D. & Robinson, J.R., "Estimating the Viscosity of Crude Oil Systems",
    JPT (1975) — oil viscosity.
  McCain, W.D., "The Properties of Petroleum Fluids", 2nd ed., PennWell (1990)
    — water Bw.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import fsolve

from core.models import Fluid

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

_BBL_TO_FT3 = 5.615      # ft³/bbl
_RHO_WATER_SC = 62.4     # lb/ft³ — pure water at standard conditions (SC)
_RHO_AIR_SC = 0.0764     # lb/scf  — dry air at 14.7 psia, 60 °F


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _oil_sg(api: float) -> float:
    """Convert API gravity to specific gravity (relative to water)."""
    return 141.5 / (131.5 + api)


def _pseudo_critical_standing(gas_sg: float) -> tuple[float, float]:
    """Standing (1977) pseudo-critical properties for dry natural gas.

    Correlations valid for 0.55 <= gas_sg <= 0.75.

    Args:
        gas_sg: Gas specific gravity (air = 1.0).

    Returns:
        Tuple (Ppc [psia], Tpc [°R]).
    """
    ppc = 677.0 + 15.0 * gas_sg - 37.5 * gas_sg ** 2
    tpc = 168.0 + 325.0 * gas_sg - 12.5 * gas_sg ** 2
    return ppc, tpc


# ---------------------------------------------------------------------------
# Standing Rs, Bo, Pb
# ---------------------------------------------------------------------------

def standing_rs(p: float, t: float, api: float, gas_sg: float, pb: float) -> float:
    """Solution GOR at pressure P using Standing's (1947) correlation.

    For P >= Pb the oil is undersaturated and Rs is anchored at its bubble-point
    value (evaluated by the same correlation at P = Pb). For P < Pb:

        Rs = γg × [(P/18.2 + 1.4) × 10^(0.0125·API − 0.00091·T)]^1.2048

    The exponent 1.2048 = 1/0.83 preserves consistency with the original
    Standing bubble-point equation.

    Reference: Standing, M.B., "A Pressure-Volume-Temperature Correlation for
    Mixtures of California Oils and Gases", API Drill. Prod. Prac. (1947).

    Args:
        p: Pressure [psia]. Must be >= 0.
        t: Temperature [°F]. Must be > 0.
        api: Oil gravity [°API].
        gas_sg: Gas specific gravity (air = 1.0). Must be > 0.
        pb: Bubble-point pressure [psia]. Must be > 0.

    Returns:
        Solution gas-oil ratio [scf/STB].

    Raises:
        ValueError: If any argument is outside its valid range.
    """
    if p < 0:
        raise ValueError(f"p must be >= 0, got {p}")
    if t <= 0:
        raise ValueError(f"t must be > 0 °F, got {t}")
    if gas_sg <= 0:
        raise ValueError(f"gas_sg must be > 0, got {gas_sg}")
    if pb <= 0:
        raise ValueError(f"pb must be > 0, got {pb}")

    p_eff = min(p, pb)
    exponent = 0.0125 * api - 0.00091 * t
    return gas_sg * ((p_eff / 18.2 + 1.4) * 10.0 ** exponent) ** 1.2048


def standing_pb(rs: float, t: float, api: float, gas_sg: float) -> float:
    """Bubble-point pressure — inverse of Standing's Rs correlation.

    Analytically inverts the Standing Rs equation:
        Pb = 18.2 × [(Rs/γg)^0.83 × 10^(0.00091·T − 0.0125·API) − 1.4]

    Use this to convert a measured producing GOR into a consistent bubble-point
    pressure, ensuring round-trip consistency with ``standing_rs``.

    Reference: Standing, M.B., API Drill. Prod. Prac. (1947).

    Args:
        rs: Solution GOR at bubble point (= total producing GOR) [scf/STB].
            Must be > 0.
        t: Reservoir temperature [°F]. Must be > 0.
        api: Oil gravity [°API].
        gas_sg: Gas specific gravity (air = 1.0). Must be > 0.

    Returns:
        Bubble-point pressure [psia].

    Raises:
        ValueError: If rs <= 0, t <= 0, gas_sg <= 0, or the result is non-positive
            (combination of inputs is physically inconsistent).
    """
    if rs <= 0:
        raise ValueError(f"rs must be > 0, got {rs}")
    if t <= 0:
        raise ValueError(f"t must be > 0 °F, got {t}")
    if gas_sg <= 0:
        raise ValueError(f"gas_sg must be > 0, got {gas_sg}")

    # (rs/gas_sg)^(1/1.2048) / 10^exponent = p_eff/18.2 + 1.4
    exponent = 0.0125 * api - 0.00091 * t
    pb = 18.2 * ((rs / gas_sg) ** (1.0 / 1.2048) / 10.0 ** exponent - 1.4)
    if pb <= 0:
        raise ValueError(
            f"Computed Pb = {pb:.1f} psia ≤ 0. Check API, T, gas_sg inputs "
            f"(very heavy oil or very low GOR can produce inconsistent results)."
        )
    return pb


def standing_bo(rs: float, t: float, api: float, gas_sg: float) -> float:
    """Oil formation volume factor — Standing's (1947) correlation.

    Formula:
        F   = Rs × (γg/γo)^0.5 + 1.25·T
        Bo  = 0.9759 + 0.000120 × F^1.2

    where γo = 141.5 / (131.5 + API) is the stock-tank oil specific gravity.

    Reference: Standing, M.B., API Drill. Prod. Prac. (1947).

    Args:
        rs: Solution GOR at the condition of interest [scf/STB]. Must be >= 0.
        t: Temperature [°F]. Must be > 0.
        api: Oil gravity [°API].
        gas_sg: Gas specific gravity (air = 1.0). Must be > 0.

    Returns:
        Oil FVF [bbl/STB]. Typically 1.0–2.0 for field crudes.

    Raises:
        ValueError: If rs < 0, t <= 0, or gas_sg <= 0.
    """
    if rs < 0:
        raise ValueError(f"rs must be >= 0, got {rs}")
    if t <= 0:
        raise ValueError(f"t must be > 0 °F, got {t}")
    if gas_sg <= 0:
        raise ValueError(f"gas_sg must be > 0, got {gas_sg}")

    oil_sg = _oil_sg(api)
    f = rs * (gas_sg / oil_sg) ** 0.5 + 1.25 * t
    return 0.9759 + 0.00012 * f ** 1.2


# ---------------------------------------------------------------------------
# Gas z-factor and Bg
# ---------------------------------------------------------------------------

def gas_z_factor(p: float, t: float, gas_sg: float) -> float:
    """Gas compressibility factor via Dranchuk-Abou-Kassem (DAK, 1975).

    Pseudo-critical properties are computed from Standing (1977). The DAK
    equation-of-state is solved iteratively with scipy fsolve, using the
    Papay explicit correlation as the initial guess.

    Valid range: 1.05 ≤ Tpr ≤ 3.0, 0.2 ≤ Ppr ≤ 30.

    Reference: Dranchuk, P.M. & Abou-Kassem, H., J. Can. Pet. Tech. (1975).

    Args:
        p: Pressure [psia]. Must be > 0.
        t: Temperature [°F]. Must be > 0.
        gas_sg: Gas specific gravity (air = 1.0). Must be > 0.

    Returns:
        Gas z-factor [-]. Always > 0.

    Raises:
        ValueError: If p <= 0 or gas_sg <= 0.
    """
    if p <= 0:
        raise ValueError(f"p must be > 0 for z-factor calculation, got {p}")
    if gas_sg <= 0:
        raise ValueError(f"gas_sg must be > 0, got {gas_sg}")

    ppc, tpc = _pseudo_critical_standing(gas_sg)
    ppr = p / ppc
    tpr = (t + 460.0) / tpc

    # DAK constants — Table 1, Dranchuk & Abou-Kassem (1975)
    A = [0.3265, -1.0700, -0.5339, 0.01569, -0.05165,
         0.5475, -0.7361,  0.1844,  0.1056,  0.6134,  0.7210]

    def _dak(z_val: float) -> float:
        rhor = 0.27 * ppr / (z_val * tpr)
        c1 = A[0] + A[1]/tpr + A[2]/tpr**3 + A[3]/tpr**4 + A[4]/tpr**5
        c2 = A[5] + A[6]/tpr + A[7]/tpr**2
        c3 = A[8] * (A[6]/tpr + A[7]/tpr**2)
        c4 = A[9] * (1.0 + A[10]*rhor**2) * (rhor**2/tpr**3) * np.exp(-A[10]*rhor**2)
        return 1.0 + c1*rhor + c2*rhor**2 - c3*rhor**5 + c4 - z_val

    # Papay explicit correlation as initial guess
    z0 = max(0.3, 1.0 - 3.52*ppr / 10.0**(0.9813*tpr) + 0.274*ppr**2 / 10.0**(0.8157*tpr))
    z_sol = float(fsolve(_dak, z0)[0])
    return max(0.05, z_sol)


def gas_bg(p: float, t: float, z: float) -> float:
    """Gas formation volume factor.

    Formula: Bg = 0.00504 × z × (T + 460) / P

    Derived from the real-gas law with unit conversion from reservoir cubic feet
    to stock-tank barrels (1 bbl = 5.615 ft³; constant accounts for SC at
    14.7 psia / 60 °F).

    Args:
        p: Pressure [psia]. Must be > 0.
        t: Temperature [°F].
        z: Gas compressibility factor [-]. Must be > 0.

    Returns:
        Gas FVF [bbl/scf].

    Raises:
        ValueError: If p <= 0 or z <= 0.
    """
    if p <= 0:
        raise ValueError(f"p must be > 0, got {p}")
    if z <= 0:
        raise ValueError(f"z must be > 0, got {z}")
    return 0.00504 * z * (t + 460.0) / p


# ---------------------------------------------------------------------------
# Water Bw
# ---------------------------------------------------------------------------

def water_bw(p: float, t: float) -> float:
    """Water formation volume factor — simplified McCain (1990) correlation.

    Bw ≈ 1 + 1.21×10⁻⁴·(T−60) + 1.0×10⁻⁶·(T−60)² − 3.33×10⁻⁶·P

    Valid for fresh to moderately saline water. Salinity effects on Bw are
    minor for ESP design purposes (< 1 % correction at 100 000 ppm TDS).

    Reference: McCain, W.D., "The Properties of Petroleum Fluids",
    2nd ed., PennWell (1990), p. 147.

    Args:
        p: Pressure [psia]. Must be >= 0.
        t: Temperature [°F]. Must be > 0.

    Returns:
        Water FVF [bbl/STB]. Typically 1.00–1.07.

    Raises:
        ValueError: If p < 0 or t <= 0.
    """
    if p < 0:
        raise ValueError(f"p must be >= 0, got {p}")
    if t <= 0:
        raise ValueError(f"t must be > 0 °F, got {t}")
    dt = t - 60.0
    return 1.0 + 1.21e-4 * dt + 1.0e-6 * dt ** 2 - 3.33e-6 * p


# ---------------------------------------------------------------------------
# Viscosity
# ---------------------------------------------------------------------------

def oil_viscosity_dead(api: float, t: float) -> float:
    """Dead-oil (gas-free) viscosity — Beggs-Robinson (1975) correlation.

    Formula:
        X       = T^(−1.163) × exp(6.9824 − 0.04658·API)
        μ_dead  = 10^X − 1   [cp]

    Correlation range: 16 ≤ API ≤ 58, 70 ≤ T ≤ 295 °F.
    Outside this range the correlation extrapolates with reduced accuracy.

    Reference: Beggs, H.D. & Robinson, J.R., "Estimating the Viscosity of
    Crude Oil Systems", JPT (1975).

    Args:
        api: Oil gravity [°API].
        t: Temperature [°F]. Must be > 0.

    Returns:
        Dead-oil viscosity [cp].

    Raises:
        ValueError: If t <= 0.
    """
    if t <= 0:
        raise ValueError(f"t must be > 0 °F, got {t}")
    x = t ** (-1.163) * np.exp(6.9824 - 0.04658 * api)
    return 10.0 ** x - 1.0


def oil_viscosity_live(mu_dead: float, rs: float) -> float:
    """Saturated live-oil viscosity — Beggs-Robinson (1975) correlation.

    Formula:
        a       = 10.715 × (Rs + 100)^(−0.515)
        b       = 5.44   × (Rs + 150)^(−0.338)
        μ_live  = a × μ_dead^b   [cp]

    Reference: Beggs, H.D. & Robinson, J.R., JPT (1975).

    Args:
        mu_dead: Dead-oil viscosity at the same temperature [cp]. Must be > 0.
        rs: Solution GOR at the condition of interest [scf/STB]. Must be >= 0.

    Returns:
        Saturated live-oil viscosity [cp].

    Raises:
        ValueError: If mu_dead <= 0 or rs < 0.
    """
    if mu_dead <= 0:
        raise ValueError(f"mu_dead must be > 0, got {mu_dead}")
    if rs < 0:
        raise ValueError(f"rs must be >= 0, got {rs}")
    a = 10.715 * (rs + 100.0) ** (-0.515)
    b = 5.44 * (rs + 150.0) ** (-0.338)
    return a * mu_dead ** b


# ---------------------------------------------------------------------------
# High-level composite function
# ---------------------------------------------------------------------------

def fluid_properties_at_conditions(fluid: Fluid, p: float, t: float) -> dict:
    """Evaluate all PVT properties for a Fluid at given pressure and temperature.

    Anchors Rs to the measured producing GOR when P >= Pb (undersaturated
    regime), and uses the Standing correlation below Pb. Densities and the
    mixture density are computed from a mass-balance over one STB of total
    liquid at surface conditions.

    Args:
        fluid: Fluid object with oil API, GOR, water cut, and fluid gravities.
        p: Pressure at which to evaluate properties [psia]. Must be > 0.
        t: Temperature [°F]. Must be > 0.

    Returns:
        Dictionary with the following keys:

        =====================  =============================================
        Key                    Description [units]
        =====================  =============================================
        rs                     Solution GOR [scf/STB]
        bo                     Oil FVF [bbl/STB]
        bg                     Gas FVF [bbl/scf]
        bw                     Water FVF [bbl/STB]
        mu_oil                 Live-oil viscosity [cp]
        oil_density            In-situ oil + dissolved-gas density [lb/ft³]
        water_density          In-situ brine density [lb/ft³]
        gas_density            In-situ free-gas density [lb/ft³]
        mixture_density        Volume-weighted density of oil+water+gas [lb/ft³]
        free_gas               Free-gas volume fraction at P,T [-]
        =====================  =============================================

    Raises:
        ValueError: If p <= 0 or t <= 0.
    """
    if p <= 0:
        raise ValueError(f"p must be > 0, got {p}")
    if t <= 0:
        raise ValueError(f"t must be > 0 °F, got {t}")

    pb = fluid.bubble_point_pressure
    oil_sg = _oil_sg(fluid.oil_api)
    wc = fluid.water_cut

    # --- Solution GOR ---
    if pb > 0 and p >= pb:
        rs = fluid.gor           # Undersaturated: all gas dissolved
    elif pb > 0:
        rs = min(standing_rs(p, t, fluid.oil_api, fluid.gas_sg, pb), fluid.gor)
    else:
        rs = fluid.gor           # pb=0 → dead or undersaturated oil

    bo = standing_bo(rs, t, fluid.oil_api, fluid.gas_sg)
    bw = water_bw(p, t)

    z = gas_z_factor(p, t, fluid.gas_sg)
    bg = gas_bg(p, t, z)

    mu_dead = oil_viscosity_dead(fluid.oil_api, t)
    mu_live = oil_viscosity_live(mu_dead, rs)

    # --- In-situ densities [lb/ft³] ---
    # Oil + dissolved gas per reservoir barrel
    rho_oil = (_RHO_WATER_SC * oil_sg + 0.0136 * rs * fluid.gas_sg) / bo
    # Water per reservoir barrel (0.0136 = RHO_AIR_SC / BBL_TO_FT3)
    rho_water = _RHO_WATER_SC * fluid.water_sg / bw
    # Free gas at reservoir conditions (real-gas law: 2.70 from unit conversion)
    rho_gas = 2.70 * fluid.gas_sg * p / (z * (t + 460.0))

    # --- Volumes per STB of total surface liquid ---
    free_gas_scf = max(fluid.gor - rs, 0.0)   # scf free gas per STB of oil
    v_oil   = (1.0 - wc) * bo                  # bbl/STB total
    v_water = wc * bw                           # bbl/STB total
    v_gas   = (1.0 - wc) * free_gas_scf * bg   # bbl/STB total
    total_v = v_oil + v_water + v_gas
    free_gas_frac = v_gas / total_v if total_v > 0.0 else 0.0

    # --- Mixture density [lb/ft³] --- mass balance over total_v ---
    # Mass contributions per STB of total surface liquid [lb]
    mass_oil   = (1.0 - wc) * (
        _RHO_WATER_SC * oil_sg * _BBL_TO_FT3     # stock-tank oil
        + _RHO_AIR_SC * rs * fluid.gas_sg         # dissolved gas
    )
    mass_water = wc * _RHO_WATER_SC * fluid.water_sg * _BBL_TO_FT3
    mass_gas   = (1.0 - wc) * free_gas_scf * _RHO_AIR_SC * fluid.gas_sg

    total_mass    = mass_oil + mass_water + mass_gas   # [lb]
    total_vol_ft3 = total_v * _BBL_TO_FT3              # [ft³]
    rho_mix = total_mass / total_vol_ft3 if total_vol_ft3 > 0.0 else 0.0

    return {
        "rs":               rs,
        "bo":               bo,
        "bg":               bg,
        "bw":               bw,
        "mu_oil":           mu_live,
        "oil_density":      rho_oil,
        "water_density":    rho_water,
        "gas_density":      rho_gas,
        "mixture_density":  rho_mix,
        "free_gas":         free_gas_frac,
    }


def mixture_specific_gravity(fluid: Fluid, p: float, t: float) -> float:
    """Volume-weighted specific gravity of the oil/water/gas mixture at P and T.

    Computes the mixture density via ``fluid_properties_at_conditions`` and
    divides by the density of pure water at standard conditions (62.4 lb/ft³).

    Args:
        fluid: Fluid object.
        p: Pressure [psia]. Must be > 0.
        t: Temperature [°F]. Must be > 0.

    Returns:
        Mixture specific gravity [-] relative to fresh water.
    """
    props = fluid_properties_at_conditions(fluid, p, t)
    return props["mixture_density"] / _RHO_WATER_SC
