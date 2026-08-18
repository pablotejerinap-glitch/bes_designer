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

from bes.core.models import Fluid

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
    """Bubble-point pressure — Standing's correlation.

    Standing's published bubble-point equation, exactly as given in Ahmed,
    *Reservoir Engineering Handbook*, 4th ed., Eq. 2-76/2-77:
        Pb = 18.2 × [(Rs/γg)^0.83 × 10^a − 1.4]
        a  = 0.00091·(T[°R] − 460) − 0.0125·API = 0.00091·T[°F] − 0.0125·API

    Use this to convert a measured producing GOR into a bubble-point pressure.

    Reference: Standing, M.B., API Drill. Prod. Prac. (1947); Ahmed (2010),
    Eq. 2-76.

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

    # Ahmed Eq. 2-76: Pb = 18.2·[(Rs/γg)^0.83·10^a − 1.4], a = 0.00091·T − 0.0125·API
    a = 0.00091 * t - 0.0125 * api
    pb = 18.2 * ((rs / gas_sg) ** 0.83 * 10.0 ** a - 1.4)
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

    Formula (Ahmed, *Reservoir Engineering Handbook*, 4th ed., Eq. 2-54):
        Bg = 0.005035 × z × T[°R] / P   [bbl/scf]

    Derived from the real-gas law with unit conversion from reservoir cubic feet
    to stock-tank barrels (1 bbl = 5.615 ft³; constant accounts for SC at
    14.65 psia / 60 °F, per Ahmed Eq. 2-54).

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
    return 0.005035 * z * (t + 460.0) / p


# ---------------------------------------------------------------------------
# Water Bw
# ---------------------------------------------------------------------------

def water_bw(p: float, t: float) -> float:
    """Water formation volume factor — McCain correlation (gas-free water).

    Full correlation as given in Ahmed, *Reservoir Engineering Handbook*,
    4th ed., Eq. 2-125:
        Bw = A1 + A2·P + A3·P²
        Ai = a1 + a2·(T[°R] − 460) + a3·(T[°R] − 460)²   (T−460 = T[°F])
    with the gas-free-water coefficients tabulated in Ahmed (Eq. 2-125).

    Reference: McCain, W.D., "The Properties of Petroleum Fluids", 2nd ed.,
    PennWell (1990); reproduced in Ahmed (2010), Eq. 2-125.

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
    # Ahmed Eq. 2-125 — gas-free water coefficients (Ai = a1 + a2·T + a3·T², T in °F)
    a1 = 0.9947 + 5.8e-6 * t + 1.02e-6 * t ** 2
    a2 = -4.228e-6 + 1.8376e-8 * t - 6.77e-11 * t ** 2
    a3 = 1.3e-10 - 1.3855e-12 * t + 4.285e-15 * t ** 2
    return a1 + a2 * p + a3 * p ** 2


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


# ===========================================================================
# TABLA PVT MEDIDA — tiene prioridad sobre las correlaciones
# ===========================================================================
#
# Una correlación es un ajuste estadístico sobre cientos de crudos que no son
# el nuestro. Un análisis PVT de laboratorio es el fluido del pozo. Cuando el
# dato medido existe, manda; la correlación queda de respaldo para las
# propiedades que la tabla no publica.
#
# Cada valor que sale de acá viaja con su ORIGEN (`sources`), porque en la
# tesis hay que poder decir de dónde salió cada número. Los tres orígenes son:
#
#     "pvt"          interpolado de la tabla de laboratorio
#     "correlacion"  calculado con Standing / DAK / Beggs-Robinson / McCain
#     "supuesto"     valor fijado a mano, sin respaldo experimental
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field   # noqa: E402  (sección auto-contenida)

#: Propiedades que una tabla PVT puede publicar y este módulo sabe consumir.
PVT_TABLE_FIELDS = ("rs", "bo", "bg", "bw", "z", "mu_oil")

#: Orígenes posibles de un valor PVT, de mayor a menor jerarquía.
PVT_SOURCE_TABLE = "pvt"
PVT_SOURCE_CORRELATION = "correlacion"
PVT_SOURCE_ASSUMED = "supuesto"


@dataclass(frozen=True)
class PVTPoint:
    """Una fila del análisis PVT: las propiedades medidas a una presión.

    Los campos son **opcionales** porque un informe de laboratorio rara vez
    publica las seis columnas. Lo que falte se completa con la correlación y
    queda marcado como tal en ``sources``.

    Args:
        pressure: Presión de la fila [psia]. Debe ser > 0.
        rs: Gas en solución [scf/STB].
        bo: Factor volumétrico del petróleo [rb/STB].
        bg: Factor volumétrico del gas [bbl/scf].
        bw: Factor volumétrico del agua [bbl/STB].
        z: Factor de compresibilidad del gas [-].
        mu_oil: Viscosidad del petróleo vivo [cp].
    """

    pressure: float
    rs: float | None = None
    bo: float | None = None
    bg: float | None = None
    bw: float | None = None
    z: float | None = None
    mu_oil: float | None = None

    def __post_init__(self) -> None:
        if self.pressure <= 0:
            raise ValueError(f"pressure must be > 0, got {self.pressure}")


@dataclass
class PVTTable:
    """Análisis PVT de laboratorio: filas ordenadas por presión.

    Interpola **linealmente** entre filas y no extrapola: fuera del rango
    medido devuelve ``None`` para todas las propiedades, de modo que el
    resolvedor caiga a la correlación en vez de inventar un valor. Extrapolar
    un PVT es exactamente el tipo de dato falso que el capítulo 25 del pliego
    prohíbe.

    Args:
        points: Filas del informe. Se ordenan solas por presión.
        source: De dónde sale la tabla — va textual a los reportes.
            Ej.: ``"PVT experimental pozo LLL-1001, informe 2024-03"``.
        temperature_f: Temperatura del ensayo [°F]. Informativa: si difiere
            mucho de la de evaluación, :func:`resolve_pvt` avisa.

    Raises:
        ValueError: Si no hay al menos dos filas, o si hay presiones repetidas.
    """

    points: list[PVTPoint]
    source: str = "PVT experimental"
    temperature_f: float | None = None
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError(
                f"PVTTable necesita al menos 2 filas para interpolar, "
                f"recibió {len(self.points)}"
            )
        self.points = sorted(self.points, key=lambda pt: pt.pressure)
        presiones = [pt.pressure for pt in self.points]
        if len(set(presiones)) != len(presiones):
            raise ValueError("PVTTable tiene presiones repetidas")

    @property
    def pressure_range(self) -> tuple[float, float]:
        """Presión mínima y máxima medidas [psia]."""
        return self.points[0].pressure, self.points[-1].pressure

    def covers(self, p: float) -> bool:
        """¿La presión *p* cae dentro del rango medido?"""
        lo, hi = self.pressure_range
        return lo <= p <= hi

    def at(self, p: float) -> dict[str, float | None]:
        """Interpola las propiedades a la presión *p*.

        Returns:
            dict con las claves de :data:`PVT_TABLE_FIELDS`. Cada una vale
            ``None`` si la tabla no la publica o si *p* cae fuera del rango.
        """
        if not self.covers(p):
            return {campo: None for campo in PVT_TABLE_FIELDS}

        # Fila exacta, o el par que encierra a p.
        lo = max((pt for pt in self.points if pt.pressure <= p),
                 key=lambda pt: pt.pressure)
        hi = min((pt for pt in self.points if pt.pressure >= p),
                 key=lambda pt: pt.pressure)

        if lo.pressure == hi.pressure:
            return {campo: getattr(lo, campo) for campo in PVT_TABLE_FIELDS}

        peso = (p - lo.pressure) / (hi.pressure - lo.pressure)
        salida: dict[str, float | None] = {}
        for campo in PVT_TABLE_FIELDS:
            v_lo = getattr(lo, campo)
            v_hi = getattr(hi, campo)
            # Sólo se interpola si LAS DOS filas publican la propiedad.
            salida[campo] = (
                v_lo + peso * (v_hi - v_lo)
                if v_lo is not None and v_hi is not None
                else None
            )
        return salida


#: Diferencia de temperatura a partir de la cual se avisa que la tabla PVT
#: está medida lejos de la condición evaluada. Bo y Rs dependen de T, así que
#: una tabla levantada a otra temperatura deja de ser el fluido del problema.
PVT_TEMP_TOLERANCE_F = 20.0


def resolve_pvt(
    p: float,
    t: float,
    fluid: Fluid,
    table: "PVTTable | None" = None,
) -> dict:
    """Rs, Bo, Bg, Bw y Z a P y T, con el origen de cada valor.

    Jerarquía del pliego (§5): **tabla de laboratorio > correlación**. Para
    cada propiedad por separado, porque un informe puede publicar Rs y Bo pero
    no Bg.

    Rs se acota al GOR total del pozo: no puede haber más gas disuelto que el
    que el pozo produce, ni siquiera si la tabla lo dice.

    Args:
        p: Presión [psia]. Debe ser > 0.
        t: Temperatura [°F].
        fluid: Fluido — aporta GOR, °API, SG del gas y presión de burbuja.
        table: Análisis PVT medido. ``None`` = sólo correlaciones.

    Returns:
        dict con ``rs``, ``bo``, ``bg``, ``bw``, ``z``, más:
          - ``sources``   dict propiedad → origen (``"pvt"`` / ``"correlacion"``)
          - ``warnings``  lista de avisos (tabla fuera de rango, T distinta…)

    Raises:
        ValueError: Si p <= 0.
    """
    if p <= 0:
        raise ValueError(f"p must be > 0, got {p}")

    medido = table.at(p) if table is not None else {c: None for c in PVT_TABLE_FIELDS}
    origenes: dict[str, str] = {}
    avisos: list[str] = []

    if table is not None:
        if not table.covers(p):
            lo, hi = table.pressure_range
            avisos.append(
                f"La tabla PVT ({table.source}) cubre {lo:.0f}–{hi:.0f} psia y "
                f"se evaluó a {p:.0f} psia: fuera de rango. No se extrapola — "
                f"se usan correlaciones en ese punto."
            )
        if (
            table.temperature_f is not None
            and abs(table.temperature_f - t) > PVT_TEMP_TOLERANCE_F
        ):
            avisos.append(
                f"La tabla PVT está medida a {table.temperature_f:.0f} °F y se "
                f"evaluó a {t:.0f} °F ({abs(table.temperature_f - t):.0f} °F de "
                f"diferencia). Rs y Bo dependen de la temperatura: verificar que "
                f"la tabla corresponda a la condición del problema."
            )

    def _tomar(campo: str, calcular):
        """Devuelve el valor medido si existe; si no, el de la correlación."""
        v = medido.get(campo)
        if v is not None:
            origenes[campo] = PVT_SOURCE_TABLE
            return float(v)
        origenes[campo] = PVT_SOURCE_CORRELATION
        return calcular()

    pb = fluid.bubble_point_pressure
    gor = fluid.gor

    rs = _tomar(
        "rs",
        lambda: (
            standing_rs(p, t, fluid.oil_api, fluid.gas_sg, pb) if pb > 0 else gor
        ),
    )
    # Tope físico: el gas disuelto no puede superar al que produce el pozo.
    rs = min(rs, gor)

    bo = _tomar("bo", lambda: standing_bo(rs, t, fluid.oil_api, fluid.gas_sg))
    z = _tomar("z", lambda: gas_z_factor(p, t, fluid.gas_sg))
    bg = _tomar("bg", lambda: gas_bg(p, t, z))
    bw = _tomar("bw", lambda: water_bw(p, t))

    return {
        "rs": rs,
        "bo": bo,
        "bg": bg,
        "bw": bw,
        "z": z,
        "sources": origenes,
        "warnings": avisos,
    }
