"""
Unit tests for core/units.py — conversions and metric-method helpers.
"""
from __future__ import annotations

import pytest

from bes.core import units


class TestPressure:
    def test_kgfcm2_to_psi(self):
        assert units.kgfcm2_to_psi(1.0) == pytest.approx(14.2233, abs=1e-3)

    def test_roundtrip(self):
        assert units.psi_to_kgfcm2(units.kgfcm2_to_psi(31.0)) == pytest.approx(31.0)


class TestLength:
    def test_m_to_ft(self):
        assert units.m_to_ft(1.0) == pytest.approx(3.28084, abs=1e-4)

    def test_roundtrip(self):
        assert units.ft_to_m(units.m_to_ft(2250.0)) == pytest.approx(2250.0)


class TestFlow:
    def test_m3d_to_bpd(self):
        # 279.4 m³/d ≈ 1757 bbl/d (ESP 01 velocity step)
        assert units.m3d_to_bpd(279.4) == pytest.approx(1757.0, abs=2.0)

    def test_roundtrip(self):
        assert units.bpd_to_m3d(units.m3d_to_bpd(300.0)) == pytest.approx(300.0)


class TestDensity:
    def test_api_to_sg_28api(self):
        # 28 °API -> ~0.887 (the exercise rounds Peo to 0.89)
        assert units.api_to_sg(28.0) == pytest.approx(0.887, abs=0.002)

    def test_mixture_gravity_esp01(self):
        # Pem = 0.89·0.09 + 1.08·0.91 = 1.0629
        assert units.mixture_specific_gravity(0.89, 1.08, 0.91) == pytest.approx(1.0629, abs=1e-4)

    def test_mixture_gravity_rejects_bad_wc(self):
        with pytest.raises(ValueError):
            units.mixture_specific_gravity(0.89, 1.08, 1.5)


class TestHead:
    def test_pressure_to_head_water(self):
        # 1 kg/cm² ≈ 10 m of water
        assert units.pressure_to_head_m(1.0, 1.0) == pytest.approx(10.0)

    def test_pressure_to_head_mixture(self):
        # PIP 15 kg/cm² at Pem 1.0629 -> ~141.1 m
        assert units.pressure_to_head_m(15.0, 1.0629) == pytest.approx(141.1, abs=0.2)

    def test_head_pressure_roundtrip(self):
        assert units.head_m_to_pressure_kgcm2(
            units.pressure_to_head_m(10.0, 1.0629), 1.0629
        ) == pytest.approx(10.0)

    def test_head_m_to_psi(self):
        # 1 m of water ≈ 1.42 psi
        assert units.head_m_to_psi(1.0, 1.0) == pytest.approx(1.4206, abs=1e-3)


class TestAffinity:
    def test_flow_50_to_60(self):
        assert units.affinity_flow(279.0, 50.0, 60.0) == pytest.approx(334.8, abs=0.1)

    def test_head_60_to_50(self):
        # 10 m/et at 60 Hz -> ~6.94 m/et at 50 Hz
        assert units.affinity_head(10.0, 60.0, 50.0) == pytest.approx(6.944, abs=1e-3)

    def test_power_60_to_50(self):
        # 0.60 HP/et at 60 Hz -> ~0.347 HP/et at 50 Hz
        assert units.affinity_power(0.60, 60.0, 50.0) == pytest.approx(0.347, abs=1e-3)
