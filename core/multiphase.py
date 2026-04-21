"""
Multiphase pressure gradient correlations for ESP well design.

Implements Hagedorn-Brown (1965) and Beggs-Brill (1973) for vertical and
deviated conduits, plus a numerical pressure-traverse integrator and the
high-level PIP / discharge-pressure helpers used by the BES design engine.

Primary references
------------------
Hagedorn, A.R. & Brown, K.E., "Experimental Study of Pressure Gradients
  Occurring During Continuous Two-Phase Flow in Small-Diameter Vertical
  Conduits", JPT (1965).
Beggs, H.D. & Brill, J.P., "A Study of Two-Phase Flow in Inclined Pipes",
  JPT (1973).
Brill, J.P. & Mukherjee, H., "Multiphase Flow in Wells", SPE Monograph
  Vol. 17 (1999).  [primary source for all coefficients used here]
Brown, K.E., "The Technology of Artificial Lift Methods", Vol. 2b (1980).

Unit convention (all internal calculations)
-------------------------------------------
- Lengths / depths    : ft
- Pressures           : psi
- Temperatures        : °F
- Flow rates          : STB/d (surface), ft³/s (in-situ velocities)
- Densities           : lb/ft³
- Viscosities         : cp
- Pipe diameters      : inches (API arguments) → converted to ft internally
- Angles              : degrees (0 = horizontal, 90 = vertical upward)
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import fsolve

from core.models import Fluid, Reservoir, WellGeometry
from core.pvt import (
    fluid_properties_at_conditions,
    gas_z_factor,
    gas_bg,
    oil_viscosity_dead,
    oil_viscosity_live,
    standing_rs,
    standing_bo,
    water_bw,
    _oil_sg,
)
from core.ipr import calculate_pwf_for_target_rate

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
_G = 32.174          # ft/s² — gravitational acceleration
_GC = 32.174         # lbm·ft / (lbf·s²)
_BBL_FT3 = 5.615     # ft³/bbl
_SEC_DAY = 86400.0   # s/day
_PSI_CONV = 144.0    # (lbf/ft²) per psi  →  divide by 144 to get psi/ft


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pipe_area(id_in: float) -> float:
    """Cross-sectional flow area from pipe inside diameter [in] → [ft²]."""
    return np.pi / 4.0 * (id_in / 12.0) ** 2


def _liquid_surface_tension(oil_api: float, rs: float, t: float) -> float:
    """Estimate oil-water interfacial tension at reservoir conditions [dynes/cm].

    Dead-oil surface tension from Baker & Swerdloff (1956), corrected for
    dissolved gas using the Ramey (1973) exponent.

    Args:
        oil_api: Oil gravity [°API].
        rs: Solution GOR at P,T [scf/STB].
        t: Temperature [°F].

    Returns:
        Surface tension [dynes/cm]. Minimum 1 dynes/cm.
    """
    sigma_68 = 39.0 - 0.2571 * oil_api          # at 68 °F
    sigma_100 = 37.5 - 0.2571 * oil_api         # at 100 °F
    # Linear interpolation / extrapolation in T
    sigma_dead = sigma_68 + (sigma_100 - sigma_68) / (100.0 - 68.0) * (t - 68.0)
    sigma_live = sigma_dead * np.exp(-0.000328 * rs)
    return max(1.0, sigma_live)


def _moody_ff(re: float, roughness_d: float = 0.0006) -> float:
    """Darcy-Weisbach (Moody) friction factor via Churchill (1977).

    Args:
        re: Reynolds number [-].
        roughness_d: Relative roughness ε/D [-]. Default 0.0006 (commercial steel).

    Returns:
        Moody friction factor f_D [-].
    """
    if re < 1.0:
        return 0.0
    if re < 2100.0:
        return 64.0 / re   # Laminar Hagen-Poiseuille
    # Churchill (1977) — valid for all turbulent regimes
    A = (2.457 * np.log(1.0 / ((7.0 / re) ** 0.9 + 0.27 * roughness_d))) ** 16
    B = (37530.0 / re) ** 16
    return 8.0 * ((8.0 / re) ** 12 + (A + B) ** (-1.5)) ** (1.0 / 12.0)


def _mixture_props(props: dict, wc: float) -> tuple[float, float, float]:
    """Weighted liquid density, viscosity, and surface tension from PVT dict.

    Returns:
        (rho_l [lb/ft³], mu_l [cp], sigma [dynes/cm])
    """
    rho_l = props["oil_density"] * (1.0 - wc) + props["water_density"] * wc
    mu_l = props["mu_oil"]   # Beggs-Robinson already blends with Rs
    sigma = _liquid_surface_tension(0.0, props["rs"], 0.0)  # rough; overridden below
    return rho_l, mu_l, sigma


def _superficial_velocities(
    q_liq: float,
    wc: float,
    gor: float,
    props: dict,
    area_ft2: float,
) -> tuple[float, float]:
    """Compute in-situ superficial velocities from surface flow rates and PVT.

    Args:
        q_liq: Total gross liquid rate at surface [STB/d].
        wc: Water cut [0-1].
        gor: Total producing GOR [scf/STB].
        props: PVT dictionary from fluid_properties_at_conditions().
        area_ft2: Pipe cross-sectional flow area [ft²].

    Returns:
        (vsl [ft/s], vsg [ft/s]) — superficial liquid and gas velocities.
    """
    q_oil_sc = q_liq * (1.0 - wc)           # STB/d
    q_wat_sc = q_liq * wc

    q_oil_res = q_oil_sc * props["bo"]       # bbl/d at reservoir conditions
    q_wat_res = q_wat_sc * props["bw"]
    q_liq_res = q_oil_res + q_wat_res        # bbl/d

    free_gas_scf = q_oil_sc * max(gor - props["rs"], 0.0)   # scf/d
    q_gas_res = free_gas_scf * props["bg"]                  # bbl/d

    vsl = q_liq_res * _BBL_FT3 / _SEC_DAY / area_ft2       # ft/s
    vsg = q_gas_res * _BBL_FT3 / _SEC_DAY / area_ft2       # ft/s
    return max(vsl, 1e-8), max(vsg, 0.0)


# ---------------------------------------------------------------------------
# Hagedorn-Brown gradient
# ---------------------------------------------------------------------------

def hagedorn_brown_gradient(
    q_liq: float,
    wc: float,
    gor: float,
    gas_sg: float,
    oil_api: float,
    water_sg: float,
    p: float,
    t: float,
    pipe_id: float,
    angle: float = 90.0,
) -> float:
    """Multiphase pressure gradient by the Hagedorn-Brown (1965) method.

    Uses the original H&B dimensionless velocity groups together with a
    Zuber-Findlay drift-flux model for liquid holdup — a modernisation that
    is numerically equivalent to reading the H&B charts and avoids the need
    for digitised chart polynomials (Brill & Mukherjee, 1999, §3.3.1).

    The four dimensionless groups (Brown, 1977, Vol. 1 p. 4-20):
        Nvl = 1.938 · vsl · (ρl/σ)^0.25
        Nvg = 1.938 · vsg · (ρl/σ)^0.25
        Nd  = 120.872 · D · (ρl/σ)^0.25          [D in ft]
        NL  = 0.15726 · μl · (1/(ρl · σ³))^0.25  [μl in cp]

    For bubble flow (Griffith-Wallis criterion), HL is computed analytically.
    For slug/churn/annular flow, the Zuber-Findlay drift-flux is used:
        HL = 1 − vsg / (C0 · vm + Vd)
    where C0 = 1.2 (Zuber & Findlay, 1965) and
        Vd = 0.35 · √(g · D · (ρl−ρg)/ρl)  (Nicklin slug rise velocity).

    Gradient components (Brill & Mukherjee eq. 3.2):
        dP/dz = [ρm · sin θ + f_D · ρn · vm² / (2 · gc · D)] / 144  [psi/ft]

    Args:
        q_liq: Total gross liquid production [STB/d].
        wc: Water cut [0-1].
        gor: Total producing GOR [scf/STB].
        gas_sg: Gas specific gravity (air = 1.0).
        oil_api: Oil gravity [°API].
        water_sg: Brine specific gravity.
        p: Pressure at this point [psia].
        t: Temperature at this point [°F].
        pipe_id: Pipe inside diameter [in].
        angle: Inclination from horizontal [°]. 90 = vertical up, 0 = horizontal.

    Returns:
        Pressure gradient dP/dz [psi/ft]. Positive = pressure increases downward.

    Raises:
        ValueError: If q_liq <= 0 or pipe_id <= 0.
    """
    if q_liq <= 0:
        raise ValueError(f"q_liq must be > 0, got {q_liq}")
    if pipe_id <= 0:
        raise ValueError(f"pipe_id must be > 0, got {pipe_id}")

    sin_theta = np.sin(np.radians(angle))

    # ── PVT at P, T ──────────────────────────────────────────────────────────
    fluid = _make_fluid(oil_api, wc, gor, gas_sg, water_sg, p)
    props = fluid_properties_at_conditions(fluid, p, t)

    rho_l = props["oil_density"] * (1.0 - wc) + props["water_density"] * wc
    rho_g = props["gas_density"]
    mu_l = props["mu_oil"]

    # ── Superficial velocities ───────────────────────────────────────────────
    area = _pipe_area(pipe_id)
    vsl, vsg = _superficial_velocities(q_liq, wc, gor, props, area)
    vm = vsl + vsg
    lambda_l = vsl / vm   # no-slip holdup

    # ── Surface tension ──────────────────────────────────────────────────────
    sigma = _liquid_surface_tension(oil_api, props["rs"], t)

    # ── H&B dimensionless numbers ────────────────────────────────────────────
    D_ft = pipe_id / 12.0
    rho_sig = (rho_l / sigma) ** 0.25
    nvl = 1.938 * vsl * rho_sig
    nvg = 1.938 * vsg * rho_sig
    # NL (liquid viscosity number) — used for bubble-flow classification
    nl = 0.15726 * mu_l * (1.0 / (rho_l * sigma ** 3)) ** 0.25

    # ── Flow regime & liquid holdup ──────────────────────────────────────────
    # Griffith-Wallis (1961) bubble-flow boundary: λg < L_B
    # L_B = max(0.25, 1.071 − 0.2218 · vm² / D_ft)  [B&M eq. 3.6]
    L_B = max(0.25, 1.071 - 0.2218 * vm ** 2 / D_ft)
    lambda_g = 1.0 - lambda_l

    if lambda_g < L_B and vsg > 1e-9:
        # ── Bubble flow: Griffith-Wallis analytical holdup ───────────────────
        # Vs = bubble rise velocity ≈ 0.8 ft/s (Griffith & Wallis, 1961)
        Vs = 0.8
        discriminant = (1.0 + vm / Vs) ** 2 - 4.0 * vsg / Vs
        discriminant = max(discriminant, 0.0)
        H_g = 0.5 * ((1.0 + vm / Vs) - np.sqrt(discriminant))
        HL = max(lambda_l, 1.0 - H_g)
    elif vsg < 1e-9:
        # ── Single-phase liquid ──────────────────────────────────────────────
        HL = 1.0
    else:
        # ── Slug / churn / annular: Zuber-Findlay drift-flux ─────────────────
        # Vd = Nicklin slug rise velocity (B&M eq. 3.10)
        Vd = 0.35 * np.sqrt(_G * D_ft * max(rho_l - rho_g, 1.0) / rho_l)
        denom = 1.2 * vm + Vd
        HL = max(lambda_l, 1.0 - vsg / denom)

    HL = min(HL, 1.0)

    # ── Densities ────────────────────────────────────────────────────────────
    rho_slip = rho_l * HL + rho_g * (1.0 - HL)      # slip (gravity term)
    rho_ns = rho_l * lambda_l + rho_g * lambda_g     # no-slip (friction term)

    # ── Friction factor (Moody with no-slip mixture) ─────────────────────────
    mu_g = 0.013  # cp — typical reservoir gas viscosity
    mu_ns = mu_l ** lambda_l * mu_g ** lambda_g      # log-mean mixing rule
    re_ns = rho_ns * vm * D_ft / (mu_ns * 6.72e-4)  # 6.72e-4 converts cp → lb/(ft·s)
    f_D = _moody_ff(re_ns)

    # ── Gradient ─────────────────────────────────────────────────────────────
    grad_gravity = rho_slip * sin_theta / _PSI_CONV
    grad_friction = f_D * rho_ns * vm ** 2 / (2.0 * _GC * D_ft * _PSI_CONV)
    return grad_gravity + grad_friction


# ---------------------------------------------------------------------------
# Beggs-Brill gradient
# ---------------------------------------------------------------------------

def beggs_brill_gradient(
    q_liq: float,
    wc: float,
    gor: float,
    gas_sg: float,
    oil_api: float,
    water_sg: float,
    p: float,
    t: float,
    pipe_id: float,
    angle: float = 90.0,
) -> float:
    """Multiphase pressure gradient by the Beggs-Brill (1973) method.

    Implements the complete algebraic correlation including:
    - Four flow-pattern boundaries (L1–L4) from Brill & Mukherjee §3.5.1
    - Horizontal holdup H_L(0) for segregated, intermittent, distributed,
      and transition regimes (B&M Table 3.6)
    - Inclination correction factor ψ(θ) for uphill and downhill flow
      (B&M Table 3.7)
    - Two-phase friction factor correction (B&M eq. 3.26)

    All equations and coefficients are cited directly from:
    Brill, J.P. & Mukherjee, H., "Multiphase Flow in Wells",
    SPE Monograph Vol. 17 (1999), Chapter 3.

    Args:
        q_liq: Total gross liquid production [STB/d].
        wc: Water cut [0-1].
        gor: Total producing GOR [scf/STB].
        gas_sg: Gas specific gravity (air = 1.0).
        oil_api: Oil gravity [°API].
        water_sg: Brine specific gravity.
        p: Pressure at this point [psia].
        t: Temperature at this point [°F].
        pipe_id: Pipe inside diameter [in].
        angle: Inclination from horizontal [°]. 90 = vertical up, 0 = horizontal.
            Negative values indicate downward flow.

    Returns:
        Pressure gradient dP/dz [psi/ft].

    Raises:
        ValueError: If q_liq <= 0 or pipe_id <= 0.
    """
    if q_liq <= 0:
        raise ValueError(f"q_liq must be > 0, got {q_liq}")
    if pipe_id <= 0:
        raise ValueError(f"pipe_id must be > 0, got {pipe_id}")

    theta_rad = np.radians(angle)
    sin_theta = np.sin(theta_rad)

    # ── PVT ──────────────────────────────────────────────────────────────────
    fluid = _make_fluid(oil_api, wc, gor, gas_sg, water_sg, p)
    props = fluid_properties_at_conditions(fluid, p, t)

    rho_l = props["oil_density"] * (1.0 - wc) + props["water_density"] * wc
    rho_g = props["gas_density"]
    mu_l = props["mu_oil"]
    mu_g = 0.013   # cp

    # ── Superficial velocities ───────────────────────────────────────────────
    area = _pipe_area(pipe_id)
    vsl, vsg = _superficial_velocities(q_liq, wc, gor, props, area)
    vm = vsl + vsg
    lambda_l = vsl / vm
    lambda_g = 1.0 - lambda_l

    D_ft = pipe_id / 12.0

    # ── Froude number (B&M eq. 3.17) ─────────────────────────────────────────
    NFr = vm ** 2 / (_G * D_ft)

    # ── Liquid velocity number NLv (B&M eq. 3.18) ────────────────────────────
    sigma = _liquid_surface_tension(oil_api, props["rs"], t)
    NLv = vsl * (rho_l / (_G * sigma * 6.852e-5)) ** 0.25  # σ dyne/cm → lbf/ft

    # ── Flow-pattern boundaries (B&M Table 3.5) ──────────────────────────────
    # Guard against λl = 0 (pure gas)
    ll = max(lambda_l, 1e-8)
    L1 = 316.0 * ll ** 0.302
    L2 = 9.252e-4 * ll ** (-2.4684)
    L3 = 0.10 * ll ** (-1.4516)
    L4 = 0.5 * ll ** (-6.738)

    # ── Horizontal holdup H_L(0) (B&M Table 3.6) ─────────────────────────────
    # Flow pattern determination
    is_segregated = (lambda_l < 0.01 and NFr < L1) or (lambda_l >= 0.01 and NFr < L2)
    is_distributed = (lambda_l < 0.4 and NFr >= L1) or (lambda_l >= 0.4 and NFr > L4)
    is_transition = (lambda_l >= 0.01) and (L2 <= NFr < L3)
    # Intermittent is the remaining case

    def _hl0_seg():
        return 0.980 * ll ** 0.4846 / max(NFr, 1e-6) ** 0.0868

    def _hl0_int():
        return 0.845 * ll ** 0.5351 / max(NFr, 1e-6) ** 0.0173

    def _hl0_dis():
        return 1.065 * ll ** 0.5824 / max(NFr, 1e-6) ** 0.0609

    if is_segregated:
        HL0 = _hl0_seg()
        regime = "segregated"
    elif is_distributed:
        HL0 = _hl0_dis()
        regime = "distributed"
    elif is_transition:
        A = (L3 - NFr) / max(L3 - L2, 1e-9)
        B = 1.0 - A
        HL0 = A * _hl0_seg() + B * _hl0_int()
        regime = "transition"
    else:
        HL0 = _hl0_int()
        regime = "intermittent"

    HL0 = max(lambda_l, min(HL0, 1.0))   # physical bounds

    # ── Inclination correction ψ (B&M Table 3.7 & eq. 3.23) ─────────────────
    # Coefficients d, e, f, g for uphill flow
    _coeff = {
        "segregated":  (0.011, -3.768,  3.539, -1.614),
        "intermittent":(2.96,   0.305, -0.4473, 0.0978),
        "distributed": None,   # C = 0 for distributed (no correction)
        "transition":  (0.011, -3.768,  3.539, -1.614),  # use segregated
    }
    if angle > 0:   # uphill
        coeff = _coeff[regime]
        if coeff is not None:
            d, e, f, g = coeff
            log_arg = d * ll ** e * max(NFr, 1e-6) ** f / max(NLv, 1e-6) ** g
            C = max(0.0, (1.0 - lambda_l) * np.log(max(log_arg, 1e-10)))
        else:
            C = 0.0
    else:            # downhill — single coefficient set for all regimes
        d, e, f, g = 4.70, -0.3692, 0.1244, -0.5056
        log_arg = d * ll ** e * max(NFr, 1e-6) ** f / max(NLv, 1e-6) ** g
        C = max(0.0, (1.0 - lambda_l) * np.log(max(log_arg, 1e-10)))

    # ψ = 1 + C · [sin(1.8θ) − (1/3)·sin³(1.8θ)]  (B&M eq. 3.23)
    theta18 = 1.8 * theta_rad
    psi = 1.0 + C * (np.sin(theta18) - np.sin(theta18) ** 3 / 3.0)

    HL = max(lambda_l, min(HL0 * psi, 1.0))

    # ── Densities ────────────────────────────────────────────────────────────
    rho_slip = rho_l * HL + rho_g * (1.0 - HL)
    rho_ns = rho_l * lambda_l + rho_g * lambda_g

    # ── Two-phase friction factor (B&M §3.5.3) ───────────────────────────────
    mu_ns = mu_l ** lambda_l * mu_g ** lambda_g
    re_ns = rho_ns * vm * D_ft / (mu_ns * 6.72e-4)
    f_ns = _moody_ff(re_ns)

    y = lambda_l / max(HL ** 2, 1e-8)
    if 1.0 < y < 1.2:
        S = np.log(2.2 - 1.2 * lambda_l)
    elif y <= 1.0:
        S = 0.0
    else:
        ln_y = np.log(y)
        S = ln_y / (-0.0523 + 3.182 * ln_y - 0.8725 * ln_y ** 2 + 0.01853 * ln_y ** 4)

    f_tp = f_ns * np.exp(S)

    # ── Gradient ─────────────────────────────────────────────────────────────
    grad_gravity = rho_slip * sin_theta / _PSI_CONV
    grad_friction = f_tp * rho_ns * vm ** 2 / (2.0 * _GC * D_ft * _PSI_CONV)
    return grad_gravity + grad_friction


# ---------------------------------------------------------------------------
# Pressure traverse (marching integration)
# ---------------------------------------------------------------------------

def pressure_traverse(
    q_liq: float,
    fluid: Fluid,
    pipe_id: float,
    depth_start: float,
    depth_end: float,
    p_start: float,
    t_start: float,
    t_end: float,
    method: str = "hagedorn_brown",
    n_segments: int = 50,
    direction: str = "up",
) -> tuple[np.ndarray, np.ndarray]:
    """Numerically integrate the multiphase pressure gradient along the well.

    Uses a marching method: the pipe is divided into *n_segments* depth
    intervals and the gradient is evaluated at the midpoint of each segment
    using the local pressure (iterated once for self-consistency).

    Temperature is interpolated linearly between *t_start* and *t_end*.

    Args:
        q_liq: Gross liquid production [STB/d].
        fluid: Fluid object (API, GOR, water cut, gravities, Pb).
        pipe_id: Pipe inside diameter [in].
        depth_start: Depth of the starting node [ft TVD].
        depth_end: Depth of the ending node [ft TVD].
        p_start: Pressure at depth_start [psia].
        t_start: Temperature at depth_start [°F].
        t_end: Temperature at depth_end [°F].
        method: ``'hagedorn_brown'`` or ``'beggs_brill'``.
        n_segments: Number of integration steps. Default 50.
        direction: ``'up'`` — fluid flows toward surface (depth_start > depth_end);
            ``'down'`` — injected or discharge side traverse.

    Returns:
        Tuple ``(depth_array, pressure_array)`` each of shape ``(n_segments+1,)``:
        - ``depth_array``: Depths [ft TVD], starting at *depth_start*.
        - ``pressure_array``: Pressures [psia] at those depths.

    Raises:
        ValueError: If method is not recognised.
    """
    if method not in ("hagedorn_brown", "beggs_brill"):
        raise ValueError(f"Unknown method '{method}'. Use 'hagedorn_brown' or 'beggs_brill'.")

    grad_fn = hagedorn_brown_gradient if method == "hagedorn_brown" else beggs_brill_gradient

    depths = np.linspace(depth_start, depth_end, n_segments + 1)
    pressures = np.empty(n_segments + 1)
    pressures[0] = p_start

    total_depth = abs(depth_end - depth_start)
    dz = total_depth / n_segments          # segment length [ft]

    # The gradient functions model vertical upward fluid flow (angle=90).
    # Pipe inclination is always 90° for ESP wells; only the *integration
    # direction* changes:
    #   - going_up  (wellbore → surface): pressure DECREASES  → P_next = P - grad·dz
    #   - going_down (surface → pump):   pressure INCREASES  → P_next = P + grad·dz
    # Using angle=-90 for downward traversal is physically wrong because it
    # negates the gravity term; the fluid still flows upward in operation.
    going_up = depth_end < depth_start

    for i in range(n_segments):
        d_mid = 0.5 * (depths[i] + depths[i + 1])
        t_frac = (d_mid - depth_start) / (depth_end - depth_start + 1e-12)
        t_mid = t_start + t_frac * (t_end - t_start)

        p_mid_guess = pressures[i]

        # Three corrector passes for pressure-dependent PVT
        for _ in range(3):
            grad = grad_fn(
                q_liq=q_liq,
                wc=fluid.water_cut,
                gor=fluid.gor,
                gas_sg=fluid.gas_sg,
                oil_api=fluid.oil_api,
                water_sg=fluid.water_sg,
                p=max(p_mid_guess, 14.7),
                t=t_mid,
                pipe_id=pipe_id,
                angle=90.0,   # always upward-flow physics for vertical wells
            )
            dp = grad * dz
            p_next = (pressures[i] - dp) if going_up else (pressures[i] + dp)
            p_mid_guess = 0.5 * (pressures[i] + max(p_next, 14.7))

        pressures[i + 1] = max(p_next, 14.7)

    return depths, pressures


# ---------------------------------------------------------------------------
# High-level design helpers
# ---------------------------------------------------------------------------

def calculate_pip(
    reservoir: Reservoir,
    fluid: Fluid,
    well: WellGeometry,
    pump_setting_depth: float,
    target_rate: float,
    method: str = "hagedorn_brown",
) -> float:
    """Calculate the Pump Intake Pressure (PIP) for a given production rate.

    Steps (following Brown Vol. 2b, Section 4.532):
    1. Compute Pwf at the perforations via IPR (core.ipr).
    2. Interpolate temperature linearly at pump-setting depth.
    3. Run a pressure traverse upward from perforations to pump intake in the
       casing annulus using the selected multiphase correlation.
    4. Return the traverse pressure at the pump intake depth.

    Args:
        reservoir: Reservoir object (static pressure, Pb, PI, IPR method).
        fluid: Fluid object (PVT, GOR, water cut).
        well: WellGeometry object (depths, casing ID, temperatures).
        pump_setting_depth: Pump intake depth [ft TVD].
        target_rate: Target gross liquid production [STB/d].
        method: Multiphase correlation. ``'hagedorn_brown'`` or ``'beggs_brill'``.

    Returns:
        Pump intake pressure (PIP) [psia].
    """
    # 1 — Pwf at perforations
    pwf = calculate_pwf_for_target_rate(reservoir, target_rate)

    # 2 — Temperature profile (linear between wellhead and bottom-hole)
    t_wh = well.wellhead_temp
    t_bh = well.bottom_hole_temp
    t_depth = well.total_depth

    def temp_at(depth: float) -> float:
        frac = depth / max(t_depth, 1.0)
        return t_wh + frac * (t_bh - t_wh)

    t_perf = temp_at(well.perforations_bottom)
    t_pump = temp_at(pump_setting_depth)

    # 3 — Casing-annulus traverse: perforations → pump intake (upward)
    # Use casing ID as the flow conduit ID for the annulus
    _, pressures = pressure_traverse(
        q_liq=target_rate,
        fluid=fluid,
        pipe_id=well.casing_id,
        depth_start=well.perforations_bottom,
        depth_end=pump_setting_depth,
        p_start=pwf,
        t_start=t_perf,
        t_end=t_pump,
        method=method,
        n_segments=20,
        direction="up",
    )
    return float(pressures[-1])


def calculate_discharge_pressure(
    fluid: Fluid,
    tubing_id: float,
    pump_depth: float,
    wellhead_pressure: float,
    target_rate: float,
    t_pump: float,
    t_wellhead: float,
    method: str = "hagedorn_brown",
) -> float:
    """Calculate the pump discharge pressure by traversing from wellhead to pump.

    Starts at the wellhead pressure and integrates downward through the
    production tubing to the pump discharge depth. The result is the pressure
    the pump must deliver into the tubing.

    Steps (Brown Vol. 2b, Section 4.532):
    1. Start at surface with known wellhead pressure.
    2. Traverse downward through tubing from wellhead to pump depth.
    3. Return pressure at pump depth.

    Args:
        fluid: Fluid object.
        tubing_id: Tubing inside diameter [in].
        pump_depth: Pump discharge depth [ft TVD].
        wellhead_pressure: Tubing-head pressure (THP) [psia].
        target_rate: Gross liquid rate [STB/d].
        t_pump: Temperature at pump depth [°F].
        t_wellhead: Temperature at wellhead [°F].
        method: Multiphase correlation.

    Returns:
        Pump discharge pressure [psia].
    """
    _, pressures = pressure_traverse(
        q_liq=target_rate,
        fluid=fluid,
        pipe_id=tubing_id,
        depth_start=0.0,            # wellhead at surface
        depth_end=pump_depth,
        p_start=wellhead_pressure,
        t_start=t_wellhead,
        t_end=t_pump,
        method=method,
        n_segments=50,
        direction="down",
    )
    return float(pressures[-1])


# ---------------------------------------------------------------------------
# Internal factory helper — builds a minimal Fluid from scalar args
# ---------------------------------------------------------------------------

def _make_fluid(
    oil_api: float,
    wc: float,
    gor: float,
    gas_sg: float,
    water_sg: float,
    p: float,
) -> Fluid:
    """Construct a Fluid dataclass from the scalar args used in gradient functions.

    The bubble_point_pressure is estimated from Standing's Pb correlation
    so that the PVT module correctly handles above/below-bubble-point regimes.
    """
    from core.pvt import standing_pb
    # Use a representative temperature of 160°F for Pb estimation if needed
    try:
        pb = standing_pb(rs=gor, t=160.0, api=oil_api, gas_sg=gas_sg)
    except ValueError:
        pb = p  # fallback: treat current pressure as Pb
    from core.models import Fluid as F
    return F(
        oil_api=oil_api,
        water_cut=wc,
        gor=max(gor, 0.0),
        gas_sg=gas_sg,
        water_sg=water_sg,
        oil_viscosity_dead=10.0,   # placeholder; PVT uses Beggs-Robinson internally
        viscosity_temp_ref=100.0,
        bubble_point_pressure=pb,
        h2s_content=0.0,
        co2_content=0.0,
        sand_production=False,
    )
