"""
Unit tests for core/pvt.py.

Numerical references
---------------------
- Standing Rs / Pb: Brown Vol. 2b Table 4.53 — at P=500 psi, γg=0.65, API=35,
  T=160 °F the correlation gives Rs ≈ 84 scf/STB (book states "≈ 80").
- Standing Bo: Ejemplo #3C (Brown Vol. 2b p.26) — P=900 psi, Rs=340 → Bo≈1.19.
  Formula evaluated at T=171 °F, API=35, γg=0.65 gives Bo = 1.189 ≈ 1.19.
- Bg at SC: 0.00504×1×520/14.7 = 0.1783 bbl/scf — used to validate gas_bg().
"""

from dataclasses import replace

import numpy as np
import pytest

from bes.core.models import Fluid
from bes.core.pvt import (
    fluid_properties_at_conditions,
    gas_bg,
    gas_z_factor,
    mixture_specific_gravity,
    oil_viscosity_dead,
    oil_viscosity_live,
    standing_bo,
    standing_pb,
    standing_rs,
    water_bw,
)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def base_fluid() -> Fluid:
    """Typical 35 API crude with 40 % water cut, used across multiple tests."""
    return Fluid(
        oil_api=35.0,
        water_cut=0.40,
        gor=350.0,
        gas_sg=0.65,
        water_sg=1.08,
        oil_viscosity_dead=12.0,
        viscosity_temp_ref=100.0,
        bubble_point_pressure=1800.0,
        h2s_content=0.0,
        co2_content=0.0,
        sand_production=False,
    )


# ---------------------------------------------------------------------------
# standing_rs
# ---------------------------------------------------------------------------

class TestStandingRs:
    def test_book_table_4_53(self):
        """Brown Vol. 2b Table 4.53: P=500, T=160°F, API=35, γg=0.65 → Rs≈80.

        The Standing correlation evaluated exactly at these conditions gives
        83.98 scf/STB; the book rounds to ≈80 when reading from the chart.
        A ±10 % tolerance covers both the chart-reading and rounding.
        """
        rs = standing_rs(p=500, t=160, api=35, gas_sg=0.65, pb=3000)
        assert rs == pytest.approx(84.0, rel=0.10)

    def test_zero_pressure(self):
        rs = standing_rs(p=0, t=160, api=35, gas_sg=0.65, pb=2000)
        assert rs >= 0

    def test_increases_with_pressure(self):
        """Rs must increase monotonically as P rises toward Pb."""
        pb = 2000.0
        pressures = [200, 500, 800, 1200, 1600, 2000]
        rs_vals = [standing_rs(p, 160, 35, 0.65, pb) for p in pressures]
        assert rs_vals == sorted(rs_vals)

    def test_clamped_above_pb(self):
        """For P > Pb the function must return the same value as at P = Pb."""
        pb = 2200.0
        rs_at_pb = standing_rs(pb, 160, 35, 0.65, pb)
        rs_above = standing_rs(pb * 1.5, 160, 35, 0.65, pb)
        assert rs_above == pytest.approx(rs_at_pb, rel=1e-9)

    def test_pb_consistency(self):
        """At P = Pb, Rs recovers the GOR used to derive Pb (within Standing's fit).

        Standing's Rs (Ahmed Eq. 2-69, exponent 1.2048) and Pb (Ahmed Eq. 2-76,
        exponent 0.83) are SEPARATELY fitted correlations, not exact analytic
        inverses, so the round-trip carries a small inherent error (~0.02 %).
        """
        gor = 400.0
        t, api, gas_sg = 180.0, 35.0, 0.65
        pb = standing_pb(gor, t, api, gas_sg)
        rs_back = standing_rs(pb, t, api, gas_sg, pb)
        assert rs_back == pytest.approx(gor, rel=2e-3)

    def test_increases_with_api(self):
        """Higher API oil dissolves more gas at the same pressure."""
        rs_light = standing_rs(1000, 160, 45, 0.65, 3000)
        rs_heavy = standing_rs(1000, 160, 20, 0.65, 3000)
        assert rs_light > rs_heavy

    def test_negative_pressure_raises(self):
        with pytest.raises(ValueError, match="p"):
            standing_rs(p=-100, t=160, api=35, gas_sg=0.65, pb=2000)

    def test_zero_gas_sg_raises(self):
        with pytest.raises(ValueError, match="gas_sg"):
            standing_rs(p=500, t=160, api=35, gas_sg=0.0, pb=2000)


# ---------------------------------------------------------------------------
# standing_pb
# ---------------------------------------------------------------------------

class TestStandingPb:
    def test_roundtrip_with_rs(self):
        """standing_rs(Pb) → standing_pb(Rs) recovers Pb within Standing's fit.

        Rs (Ahmed Eq. 2-69) and Pb (Ahmed Eq. 2-76) are separately fitted, not
        exact inverses; the round-trip error is ~0.02 %.
        """
        pb_orig = 2200.0
        rs_at_pb = standing_rs(pb_orig, 160, 35, 0.65, pb_orig)
        pb_back = standing_pb(rs_at_pb, 160, 35, 0.65)
        assert pb_back == pytest.approx(pb_orig, rel=2e-3)

    def test_pb_increases_with_gor(self):
        """Higher GOR wells have higher bubble-point pressures."""
        pb_low = standing_pb(200, 160, 35, 0.65)
        pb_high = standing_pb(600, 160, 35, 0.65)
        assert pb_high > pb_low

    def test_zero_rs_raises(self):
        with pytest.raises(ValueError, match="rs"):
            standing_pb(rs=0.0, t=160, api=35, gas_sg=0.65)

    def test_negative_rs_raises(self):
        with pytest.raises(ValueError, match="rs"):
            standing_pb(rs=-50, t=160, api=35, gas_sg=0.65)


# ---------------------------------------------------------------------------
# standing_bo
# ---------------------------------------------------------------------------

class TestStandingBo:
    def test_book_example_3c(self):
        """Brown Vol. 2b Ejemplo #3C: Rs=340, T=171°F, API=35, γg=0.65 → Bo≈1.19.

        Formula gives 1.189 at these conditions (tolerance ±0.01 covers book
        rounding of intermediate steps).
        """
        bo = standing_bo(rs=340, t=171, api=35, gas_sg=0.65)
        assert bo == pytest.approx(1.19, abs=0.01)

    def test_greater_than_one(self):
        """Bo must always exceed 1.0 (oil expands at reservoir T/P)."""
        bo = standing_bo(rs=200, t=150, api=35, gas_sg=0.65)
        assert bo > 1.0

    def test_increases_with_rs(self):
        """More dissolved gas → larger volume at reservoir conditions."""
        bo_low = standing_bo(rs=100, t=160, api=35, gas_sg=0.65)
        bo_high = standing_bo(rs=500, t=160, api=35, gas_sg=0.65)
        assert bo_high > bo_low

    def test_increases_with_temperature(self):
        bo_cold = standing_bo(rs=300, t=100, api=35, gas_sg=0.65)
        bo_hot = standing_bo(rs=300, t=200, api=35, gas_sg=0.65)
        assert bo_hot > bo_cold

    def test_dead_oil_rs_zero(self):
        """With Rs=0, Bo should approach its minimum (≈0.98 at T=60 via formula)."""
        bo = standing_bo(rs=0, t=60, api=35, gas_sg=0.65)
        assert bo == pytest.approx(0.9759 + 0.00012 * (1.25 * 60) ** 1.2, rel=1e-6)

    def test_negative_rs_raises(self):
        with pytest.raises(ValueError, match="rs"):
            standing_bo(rs=-10, t=160, api=35, gas_sg=0.65)


# ---------------------------------------------------------------------------
# gas_z_factor
# ---------------------------------------------------------------------------

class TestGasZFactor:
    def test_near_atmospheric_close_to_one(self):
        """At very low pressures z → 1 (ideal gas behavior)."""
        z = gas_z_factor(p=50, t=60, gas_sg=0.65)
        assert z == pytest.approx(1.0, abs=0.05)

    def test_reasonable_range_at_mid_pressure(self):
        """At 1000 psia / 200°F the z-factor must be 0.8–1.0 for typical gas."""
        z = gas_z_factor(p=1000, t=200, gas_sg=0.65)
        assert 0.80 < z < 1.00

    def test_positive(self):
        z = gas_z_factor(p=2000, t=150, gas_sg=0.70)
        assert z > 0

    def test_increases_with_temperature_at_fixed_pressure(self):
        """Higher T → gas less compressed → z closer to 1 (or higher)."""
        z_cold = gas_z_factor(p=3000, t=100, gas_sg=0.65)
        z_hot = gas_z_factor(p=3000, t=300, gas_sg=0.65)
        assert z_hot > z_cold

    def test_zero_pressure_raises(self):
        with pytest.raises(ValueError, match="p"):
            gas_z_factor(p=0, t=150, gas_sg=0.65)

    def test_negative_gas_sg_raises(self):
        with pytest.raises(ValueError, match="gas_sg"):
            gas_z_factor(p=1000, t=150, gas_sg=-0.5)


# ---------------------------------------------------------------------------
# gas_bg
# ---------------------------------------------------------------------------

class TestGasBg:
    def test_standard_conditions(self):
        """Ahmed Eq. 2-54: Bg = 0.005035×z×T[°R]/P bbl/scf. At 14.7 psia/60°F/z=1."""
        bg = gas_bg(p=14.7, t=60, z=1.0)
        assert bg == pytest.approx(0.005035 * 520.0 / 14.7, rel=1e-6)

    def test_decreases_with_pressure(self):
        """Higher pressure compresses gas → smaller Bg."""
        bg_low = gas_bg(p=500, t=200, z=0.92)
        bg_high = gas_bg(p=2000, t=200, z=0.88)
        assert bg_low > bg_high

    def test_zero_pressure_raises(self):
        with pytest.raises(ValueError, match="p"):
            gas_bg(p=0, t=150, z=0.9)

    def test_zero_z_raises(self):
        with pytest.raises(ValueError, match="z"):
            gas_bg(p=1000, t=150, z=0.0)


# ---------------------------------------------------------------------------
# water_bw
# ---------------------------------------------------------------------------

class TestWaterBw:
    def test_near_unity_at_standard_conditions(self):
        """At 14.7 psia / 60°F, Bw ≈ 1.0 (minimal correction)."""
        bw = water_bw(p=14.7, t=60)
        assert bw == pytest.approx(1.0, abs=0.005)

    def test_greater_than_zero(self):
        bw = water_bw(p=3000, t=200)
        assert bw > 0

    def test_increases_with_temperature(self):
        """Water expands with temperature."""
        bw_cold = water_bw(p=1000, t=80)
        bw_hot = water_bw(p=1000, t=200)
        assert bw_hot > bw_cold

    def test_negative_pressure_raises(self):
        with pytest.raises(ValueError, match="p"):
            water_bw(p=-100, t=160)

    def test_zero_temperature_raises(self):
        with pytest.raises(ValueError, match="t"):
            water_bw(p=1000, t=0)


# ---------------------------------------------------------------------------
# oil_viscosity_dead
# ---------------------------------------------------------------------------

class TestOilViscosityDead:
    def test_decreases_with_temperature(self):
        """Crude oil viscosity decreases with rising temperature."""
        mu_cold = oil_viscosity_dead(api=35, t=100)
        mu_hot = oil_viscosity_dead(api=35, t=200)
        assert mu_cold > mu_hot

    def test_decreases_with_api(self):
        """Higher API (lighter) oil is less viscous."""
        mu_heavy = oil_viscosity_dead(api=20, t=160)
        mu_light = oil_viscosity_dead(api=45, t=160)
        assert mu_heavy > mu_light

    def test_positive(self):
        mu = oil_viscosity_dead(api=35, t=160)
        assert mu > 0

    def test_beggs_robinson_reference(self):
        """Beggs-Robinson: API=35, T=160°F → X = 160^(-1.163) × exp(6.9824-0.04658×35).
        Formula gives mu_dead ≈ 2.77 cp (light-medium crude, typical for 35 API).
        """
        mu = oil_viscosity_dead(api=35, t=160)
        assert mu == pytest.approx(2.77, rel=0.05)

    def test_zero_temperature_raises(self):
        with pytest.raises(ValueError, match="t"):
            oil_viscosity_dead(api=35, t=0)


# ---------------------------------------------------------------------------
# oil_viscosity_live
# ---------------------------------------------------------------------------

class TestOilViscosityLive:
    def test_live_less_than_dead(self):
        """Dissolved gas reduces oil viscosity."""
        mu_dead = oil_viscosity_dead(api=35, t=160)
        mu_live = oil_viscosity_live(mu_dead=mu_dead, rs=300)
        assert mu_live < mu_dead

    def test_decreases_with_rs(self):
        """More gas in solution → lower live-oil viscosity."""
        mu_dead = 3.0
        mu_low_rs = oil_viscosity_live(mu_dead, rs=100)
        mu_high_rs = oil_viscosity_live(mu_dead, rs=500)
        assert mu_high_rs < mu_low_rs

    def test_zero_rs_converges_to_dead(self):
        """With Rs=0 (no dissolved gas), live viscosity must equal dead viscosity."""
        mu_dead = 5.0
        mu_live = oil_viscosity_live(mu_dead, rs=0)
        a = 10.715 * 100.0 ** (-0.515)
        b = 5.44 * 150.0 ** (-0.338)
        expected = a * mu_dead ** b
        assert mu_live == pytest.approx(expected, rel=1e-9)

    def test_positive(self):
        assert oil_viscosity_live(mu_dead=3.0, rs=300) > 0

    def test_negative_mu_dead_raises(self):
        with pytest.raises(ValueError, match="mu_dead"):
            oil_viscosity_live(mu_dead=-1.0, rs=300)

    def test_negative_rs_raises(self):
        with pytest.raises(ValueError, match="rs"):
            oil_viscosity_live(mu_dead=3.0, rs=-10)


# ---------------------------------------------------------------------------
# fluid_properties_at_conditions
# ---------------------------------------------------------------------------

class TestFluidPropertiesAtConditions:
    def test_returns_all_keys(self, base_fluid):
        props = fluid_properties_at_conditions(base_fluid, p=1000, t=160)
        expected_keys = {
            "rs", "bo", "bg", "bw", "mu_oil",
            "oil_density", "water_density", "gas_density",
            "mixture_density", "free_gas",
        }
        assert set(props.keys()) == expected_keys

    def test_above_pb_rs_equals_gor(self, base_fluid):
        """Above bubble point all gas stays dissolved: Rs must equal the producing GOR."""
        p_above = base_fluid.bubble_point_pressure * 1.5
        props = fluid_properties_at_conditions(base_fluid, p=p_above, t=160)
        assert props["rs"] == pytest.approx(base_fluid.gor, rel=1e-9)

    def test_above_pb_no_free_gas(self, base_fluid):
        """No free gas can exist above the bubble point."""
        p_above = base_fluid.bubble_point_pressure + 500.0
        props = fluid_properties_at_conditions(base_fluid, p=p_above, t=160)
        assert props["free_gas"] == pytest.approx(0.0, abs=1e-9)

    def test_below_pb_rs_less_than_gor(self, base_fluid):
        """Below Pb, solution GOR must be less than the total producing GOR."""
        p_below = base_fluid.bubble_point_pressure * 0.5
        props = fluid_properties_at_conditions(base_fluid, p=p_below, t=160)
        assert props["rs"] < base_fluid.gor

    def test_below_pb_free_gas_positive(self, base_fluid):
        """Gas exsolution below Pb must produce a positive free-gas fraction."""
        p_below = base_fluid.bubble_point_pressure * 0.5
        props = fluid_properties_at_conditions(base_fluid, p=p_below, t=160)
        assert props["free_gas"] > 0.0

    def test_free_gas_fraction_bounded(self, base_fluid):
        """Free-gas volume fraction must be in [0, 1] at any pressure."""
        for p in [500, 1000, 1800, 2500, 4000]:
            props = fluid_properties_at_conditions(base_fluid, p=float(p), t=160)
            assert 0.0 <= props["free_gas"] <= 1.0, f"free_gas out of range at p={p}"

    def test_all_densities_positive(self, base_fluid):
        props = fluid_properties_at_conditions(base_fluid, p=1000, t=160)
        for key in ("oil_density", "water_density", "gas_density", "mixture_density"):
            assert props[key] > 0.0, f"{key} must be positive"

    def test_bo_exceeds_one(self, base_fluid):
        props = fluid_properties_at_conditions(base_fluid, p=1000, t=160)
        assert props["bo"] > 1.0

    def test_rs_increases_toward_pb(self, base_fluid):
        """Solution GOR increases as pressure approaches Pb from below."""
        pb = base_fluid.bubble_point_pressure
        pressures = [300.0, 600.0, 900.0, 1200.0, 1500.0, pb]
        rs_vals = [
            fluid_properties_at_conditions(base_fluid, p, 160)["rs"]
            for p in pressures
        ]
        assert rs_vals == sorted(rs_vals)

    def test_mixture_density_is_volume_weighted(self, base_fluid):
        """Mixture density must lie between the lightest (gas) and heaviest (water) phases."""
        props = fluid_properties_at_conditions(base_fluid, p=800, t=160)
        assert props["gas_density"] < props["mixture_density"] < props["water_density"]

    def test_zero_pressure_raises(self, base_fluid):
        with pytest.raises(ValueError, match="p"):
            fluid_properties_at_conditions(base_fluid, p=0, t=160)

    def test_zero_temperature_raises(self, base_fluid):
        with pytest.raises(ValueError, match="t"):
            fluid_properties_at_conditions(base_fluid, p=1000, t=0)

    def test_numerical_spot_check_above_pb(self, base_fluid):
        """Above Pb: Rs=350, T=160, API=35, γg=0.65 → Bo from formula ≈ 1.187."""
        props = fluid_properties_at_conditions(
            base_fluid, p=base_fluid.bubble_point_pressure + 500, t=160
        )
        assert props["rs"] == pytest.approx(350.0, rel=1e-9)
        assert props["bo"] == pytest.approx(
            standing_bo(350.0, 160.0, 35.0, 0.65), rel=1e-9
        )

    def test_numerical_spot_check_below_pb(self, base_fluid):
        """Below Pb at P=900 psi: spot-check mixture density value is stable."""
        props = fluid_properties_at_conditions(base_fluid, p=900, t=160)
        # Mixture density should be a physically plausible liquid (25–80 lb/ft³)
        assert 25.0 < props["mixture_density"] < 80.0


# ---------------------------------------------------------------------------
# mixture_specific_gravity
# ---------------------------------------------------------------------------

class TestMixtureSpecificGravity:
    def test_less_than_water(self, base_fluid):
        """Oil-dominated mixture SG must be below 1.0 at low water cut."""
        light_fluid = Fluid(
            oil_api=35.0, water_cut=0.05, gor=200, gas_sg=0.65, water_sg=1.02,
            oil_viscosity_dead=5.0, viscosity_temp_ref=100.0,
            bubble_point_pressure=1500.0, h2s_content=0, co2_content=0,
            sand_production=False,
        )
        sg = mixture_specific_gravity(light_fluid, p=2000, t=160)
        assert sg < 1.0

    def test_returns_ratio_of_mixture_density(self, base_fluid):
        """mixture_specific_gravity must equal mixture_density / 62.4 exactly."""
        p, t = 1000.0, 160.0
        props = fluid_properties_at_conditions(base_fluid, p, t)
        sg = mixture_specific_gravity(base_fluid, p, t)
        assert sg == pytest.approx(props["mixture_density"] / 62.4, rel=1e-9)

    def test_positive(self, base_fluid):
        sg = mixture_specific_gravity(base_fluid, p=1500, t=160)
        assert sg > 0.0


# ---------------------------------------------------------------------------
# La cadena que alimenta al factor z
# ---------------------------------------------------------------------------

class TestLaCadenaDelFactorZ:
    """El z no aparece de la nada: se entra por P_pr y T_pr, y ésas por Standing.

    La traza publicaba el z solo, con una densidad reducida que además estaba
    mal calculada (usaba la presión absoluta en vez de la pseudo-reducida y se
    olvidaba de T_pr), así que la correlación no se podía auditar.
    """

    def _paso(self, fluido: Fluid, clave: str, p=1200.0, t=180.0) -> dict:
        from bes.core.pvt import pvt_trace
        return next(f for f in pvt_trace(fluido, p, t) if f["key"] == clave)

    def test_las_pseudo_criticas_salen_de_standing(self, base_fluid):
        from bes.core.pvt import _pseudo_critical_standing
        ppc, tpc = _pseudo_critical_standing(base_fluid.gas_sg)
        assert self._paso(base_fluid, "pvt_ppc")["result"] == pytest.approx(ppc)
        assert self._paso(base_fluid, "pvt_tpc")["result"] == pytest.approx(tpc)

    def test_las_reducidas_dividen_por_las_criticas(self, base_fluid):
        ppc = self._paso(base_fluid, "pvt_ppc")["result"]
        tpc = self._paso(base_fluid, "pvt_tpc")["result"]
        assert self._paso(base_fluid, "pvt_ppr")["result"] == pytest.approx(
            1200.0 / ppc
        )
        assert self._paso(base_fluid, "pvt_tpr")["result"] == pytest.approx(
            (180.0 + 460.0) / tpc
        )

    def test_la_temperatura_reducida_va_en_absoluta(self, base_fluid):
        """Dividir °F por °R daría cualquier cosa: T_pr tiene que dar ~1.7."""
        assert 1.05 <= self._paso(base_fluid, "pvt_tpr")["result"] <= 3.0

    def test_la_densidad_reducida_es_la_de_dak(self, base_fluid):
        """ρ_r = 0.27·P_pr/(z·T_pr), no 0.27·P/z."""
        z = self._paso(base_fluid, "pvt_z")
        ppr = self._paso(base_fluid, "pvt_ppr")["result"]
        tpr = self._paso(base_fluid, "pvt_tpr")["result"]
        assert z["inputs"]["ρ_r"] == pytest.approx(
            0.27 * ppr / (z["result"] * tpr)
        )
        assert z["inputs"]["P_pr"] == pytest.approx(ppr)
        assert z["inputs"]["T_pr"] == pytest.approx(tpr)

    def test_fuera_del_rango_de_la_correlacion_se_avisa(self, base_fluid):
        """γ_g = 0.95 está fuera del 0.55–0.75 de Standing: se usa igual, avisando."""
        pesado = replace(base_fluid, gas_sg=0.95)
        assert "fuera del rango" in self._paso(pesado, "pvt_ppc")["context"]
        assert self._paso(base_fluid, "pvt_ppc")["context"] == ""
