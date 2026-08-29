"""
Unit tests for core/multiphase.py — Poettmann & Carpenter.

Referencias numéricas
---------------------
- Gradiente de líquido puro: solo gravedad → ρ_l · sen(90°) / 144. Para agua a
  baja P/T el gradiente vale water_SG × 0.433 ≈ 0.433 psi/ft.
- Gradiente horizontal: sen(0°) = 0, desaparece la gravedad y queda solo la
  fricción — tiene que ser mucho menor que el vertical.
- Ejemplo #3 del libro (Brown Vol. 2b): presión de descarga ≈ 1300 psi; acá se
  verifica el orden de magnitud.
- Recorrido de presión: hacia arriba la presión baja, hacia abajo sube.
"""

from __future__ import annotations

import numpy as np
import pytest

import bes.core.multiphase as mp
from bes.core.models import DriveMechanism, Fluid, IPRMethod, Reservoir, WellGeometry
from bes.core.multiphase import (
    calculate_discharge_pressure,
    calculate_pip,
    poettmann_carpenter_components,
    poettmann_carpenter_gradient,
    pressure_traverse,
)


# ---------------------------------------------------------------------------
# Fixtures compartidas
# ---------------------------------------------------------------------------

@pytest.fixture
def base_fluid() -> Fluid:
    """Crudo de 35 API con GOR=500 y 50 % de agua — candidato típico a BES."""
    return Fluid(
        oil_api=35.0,
        water_cut=0.50,
        gor=500.0,
        gas_sg=0.65,
        water_sg=1.08,
        oil_viscosity_dead=10.0,
        viscosity_temp_ref=100.0,
        bubble_point_pressure=2000.0,
        h2s_content=0.0,
        co2_content=0.0,
        sand_production=False,
    )


@pytest.fixture
def high_gor_fluid() -> Fluid:
    """Crudo de 30 API con GOR=1000 y 60 % de agua — caso de mucho gas."""
    return Fluid(
        oil_api=30.0,
        water_cut=0.60,
        gor=1000.0,
        gas_sg=0.65,
        water_sg=1.08,
        oil_viscosity_dead=12.0,
        viscosity_temp_ref=100.0,
        bubble_point_pressure=2500.0,
        h2s_content=0.0,
        co2_content=0.0,
        sand_production=False,
    )


@pytest.fixture
def reservoir() -> Reservoir:
    return Reservoir(
        static_pressure=3000.0,
        bubble_point=2000.0,
        productivity_index=1.5,
        ipr_method=IPRMethod.VOGEL,
        reservoir_temp=180.0,
        drive_mechanism=DriveMechanism.SOLUTION_GAS,
    )


@pytest.fixture
def well() -> WellGeometry:
    return WellGeometry(
        total_depth=9000.0,
        casing_od=7.0,
        casing_weight=23.0,
        casing_id=6.366,
        tubing_od=2.875,
        tubing_id=2.441,
        perforations_top=8700.0,
        perforations_bottom=8900.0,
        deviation_max=5.0,
        wellhead_temp=80.0,
    )


_GRAD_KWARGS = dict(
    q_liq=1500.0,
    wc=0.50,
    gor=500.0,
    gas_sg=0.65,
    oil_api=35.0,
    water_sg=1.08,
    p=1500.0,
    t=160.0,
    pipe_id=2.992,
)


# ---------------------------------------------------------------------------
# 1. Gradiente de líquido puro  ≈ SG × 0.433 psi/ft
# ---------------------------------------------------------------------------

class TestPureLiquidGradient:
    """Sin gas libre (GOR=0) el gradiente lo domina la columna hidrostática.
    A baja P/T (Bw ≈ 1, Bo ≈ 1) y con agua pura debe rondar 0.433 psi/ft."""

    def test_pure_water(self):
        g = poettmann_carpenter_gradient(
            q_liq=500, wc=1.0, gor=0, gas_sg=0.65, oil_api=35,
            water_sg=1.0, p=50, t=70, pipe_id=2.441,
        )
        assert g == pytest.approx(0.433, rel=0.05), (
            f"Se esperaba ≈0.433 psi/ft para agua pura, se obtuvo {g:.4f}"
        )

    def test_pure_oil_gradient_less_than_water(self):
        """El petróleo (API=35, SG≈0.85) pesa menos que el agua."""
        g_oil = poettmann_carpenter_gradient(
            q_liq=500, wc=0.0, gor=0, gas_sg=0.65, oil_api=35,
            water_sg=1.0, p=50, t=70, pipe_id=2.441,
        )
        g_water = poettmann_carpenter_gradient(
            q_liq=500, wc=1.0, gor=0, gas_sg=0.65, oil_api=35,
            water_sg=1.0, p=50, t=70, pipe_id=2.441,
        )
        assert g_oil < g_water

    def test_gradient_proportional_to_sg(self):
        """Salmuera más densa → gradiente mayor."""
        g1 = poettmann_carpenter_gradient(
            q_liq=300, wc=1.0, gor=0, gas_sg=0.65, oil_api=35,
            water_sg=1.0, p=50, t=70, pipe_id=2.441,
        )
        g2 = poettmann_carpenter_gradient(
            q_liq=300, wc=1.0, gor=0, gas_sg=0.65, oil_api=35,
            water_sg=1.10, p=50, t=70, pipe_id=2.441,
        )
        assert g2 > g1


# ---------------------------------------------------------------------------
# 2. Gradiente horizontal — desaparece el término de gravedad
# ---------------------------------------------------------------------------

class TestHorizontalGradient:
    def test_horizontal_near_zero(self):
        g_h = poettmann_carpenter_gradient(**_GRAD_KWARGS, angle=0.0)
        g_v = poettmann_carpenter_gradient(**_GRAD_KWARGS, angle=90.0)
        assert g_h < 0.03, f"El gradiente horizontal {g_h:.5f} debería ser < 0.03 psi/ft"
        assert g_h < g_v * 0.15

    def test_vertical_greater_than_horizontal(self):
        g_v = poettmann_carpenter_gradient(**_GRAD_KWARGS, angle=90.0)
        g_h = poettmann_carpenter_gradient(**_GRAD_KWARGS, angle=0.0)
        assert g_v > g_h


# ---------------------------------------------------------------------------
# 3. Verificaciones físicas del gradiente
# ---------------------------------------------------------------------------

class TestGradientSanity:
    def test_positive_for_vertical(self):
        assert poettmann_carpenter_gradient(**_GRAD_KWARGS, angle=90.0) > 0.0

    def test_increases_with_water_cut(self):
        """Más agua → líquido más denso → mayor gradiente."""
        g_lo = poettmann_carpenter_gradient(
            q_liq=1000, wc=0.1, gor=300, gas_sg=0.65, oil_api=35,
            water_sg=1.08, p=1500, t=160, pipe_id=2.441,
        )
        g_hi = poettmann_carpenter_gradient(
            q_liq=1000, wc=0.9, gor=300, gas_sg=0.65, oil_api=35,
            water_sg=1.08, p=1500, t=160, pipe_id=2.441,
        )
        assert g_hi > g_lo

    def test_decreases_with_gor(self):
        """Más GOR → más gas libre → mezcla más liviana → menor gradiente."""
        g_lo = poettmann_carpenter_gradient(
            q_liq=1000, wc=0.5, gor=100, gas_sg=0.65, oil_api=35,
            water_sg=1.08, p=800, t=160, pipe_id=2.441,
        )
        g_hi = poettmann_carpenter_gradient(
            q_liq=1000, wc=0.5, gor=1000, gas_sg=0.65, oil_api=35,
            water_sg=1.08, p=800, t=160, pipe_id=2.441,
        )
        assert g_lo > g_hi

    def test_gradient_in_physical_range(self):
        g = poettmann_carpenter_gradient(**_GRAD_KWARGS, angle=90.0)
        assert 0.05 < g < 0.55, f"Gradiente {g:.4f} fuera del rango físico"

    def test_zero_q_raises(self):
        with pytest.raises(ValueError, match="q_liq"):
            poettmann_carpenter_gradient(
                q_liq=0, wc=0.5, gor=300, gas_sg=0.65, oil_api=35,
                water_sg=1.08, p=1000, t=160, pipe_id=2.441,
            )

    def test_zero_pipe_id_raises(self):
        with pytest.raises(ValueError, match="pipe_id"):
            poettmann_carpenter_gradient(
                q_liq=1000, wc=0.5, gor=300, gas_sg=0.65, oil_api=35,
                water_sg=1.08, p=1000, t=160, pipe_id=0,
            )


# ---------------------------------------------------------------------------
# 4. Descomposición en gravedad + fricción
# ---------------------------------------------------------------------------

class TestComponents:
    def test_total_is_sum_of_parts(self):
        c = poettmann_carpenter_components(**_GRAD_KWARGS, angle=90.0)
        assert c["total"] == pytest.approx(c["gravity"] + c["friction"])

    def test_gradient_matches_components_total(self):
        c = poettmann_carpenter_components(**_GRAD_KWARGS, angle=90.0)
        g = poettmann_carpenter_gradient(**_GRAD_KWARGS, angle=90.0)
        assert g == pytest.approx(c["total"])

    def test_horizontal_has_no_gravity(self):
        c = poettmann_carpenter_components(**_GRAD_KWARGS, angle=0.0)
        assert c["gravity"] == pytest.approx(0.0, abs=1e-12)
        assert c["friction"] > 0.0

    def test_friction_factor_within_chart_bounds(self):
        """El factor de fricción queda acotado al rango de la carta original."""
        c = poettmann_carpenter_components(**_GRAD_KWARGS, angle=90.0)
        assert 0.005 <= c["friction_factor"] <= 0.065

    def test_noslip_holdup_between_zero_and_one(self):
        c = poettmann_carpenter_components(**_GRAD_KWARGS, angle=90.0)
        assert 0.0 < c["liquid_holdup_noslip"] <= 1.0

    def test_no_free_gas_means_holdup_one(self):
        """Sin gas libre la mezcla es todo líquido: λl = 1."""
        c = poettmann_carpenter_components(
            q_liq=500, wc=1.0, gor=0, gas_sg=0.65, oil_api=35,
            water_sg=1.0, p=50, t=70, pipe_id=2.441,
        )
        assert c["liquid_holdup_noslip"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 5. Recorrido de presión (pressure traverse)
# ---------------------------------------------------------------------------

class TestPressureTraverse:
    def test_shape(self, base_fluid):
        depths, pressures = pressure_traverse(
            q_liq=1000, fluid=base_fluid, pipe_id=2.441,
            depth_start=8500, depth_end=7000,
            p_start=2500, t_start=175, t_end=150,
            n_segments=20,
        )
        assert depths.shape == (21,)
        assert pressures.shape == (21,)

    def test_upward_pressure_decreases(self, base_fluid):
        """Subiendo (profundidad decreciente) la presión baja monótonamente."""
        _, pressures = pressure_traverse(
            q_liq=1000, fluid=base_fluid, pipe_id=2.441,
            depth_start=8000, depth_end=2000,
            p_start=2800, t_start=175, t_end=100,
            n_segments=30,
        )
        assert np.all(np.diff(pressures) <= 0)

    def test_downward_pressure_increases(self, base_fluid):
        """Bajando (boca de pozo → bomba) la presión sube."""
        _, pressures = pressure_traverse(
            q_liq=1000, fluid=base_fluid, pipe_id=2.441,
            depth_start=0, depth_end=7000,
            p_start=200, t_start=80, t_end=165,
            n_segments=30,
        )
        assert np.all(np.diff(pressures) >= 0)

    def test_depth_array_matches_bounds(self, base_fluid):
        depths, _ = pressure_traverse(
            q_liq=1000, fluid=base_fluid, pipe_id=2.441,
            depth_start=8000, depth_end=3000,
            p_start=2500, t_start=175, t_end=120,
        )
        assert depths[0] == pytest.approx(8000.0)
        assert depths[-1] == pytest.approx(3000.0)

    def test_start_pressure_preserved(self, base_fluid):
        _, pressures = pressure_traverse(
            q_liq=1000, fluid=base_fluid, pipe_id=2.441,
            depth_start=8000, depth_end=3000,
            p_start=2500, t_start=175, t_end=120,
        )
        assert pressures[0] == pytest.approx(2500.0)

    def test_more_segments_stable(self, base_fluid):
        """Más segmentos no deberían cambiar mucho el resultado."""
        _, p20 = pressure_traverse(
            q_liq=1000, fluid=base_fluid, pipe_id=2.441,
            depth_start=8000, depth_end=3000,
            p_start=2500, t_start=175, t_end=120, n_segments=20,
        )
        _, p100 = pressure_traverse(
            q_liq=1000, fluid=base_fluid, pipe_id=2.441,
            depth_start=8000, depth_end=3000,
            p_start=2500, t_start=175, t_end=120, n_segments=100,
        )
        assert p20[-1] == pytest.approx(p100[-1], rel=0.05)


# ---------------------------------------------------------------------------
# 6. calculate_discharge_pressure
# ---------------------------------------------------------------------------

class TestCalculateDischarge:
    """Presión de descarga en un pozo con mucho gas.

    Escenario: q=1000 STB/d, GOR=1000 scf/STB, WC=0.60, API=30, tubing 2.441",
    bomba a 5000 ft, THP=100 psi. La columna hidrostática de líquido puro sería
    ≈ 5000 ft × 0.44 psi/ft ≈ 2200 psi; con 1000 scf/STB de gas la mezcla se
    aliviana mucho, y como Poettmann & Carpenter no considera deslizamiento
    (las dos fases viajan a la misma velocidad) el resultado queda bastante por
    debajo de esa cota. El test fija el orden de magnitud, no un valor del libro.
    """

    def test_high_gor_discharge_order_of_magnitude(self, high_gor_fluid):
        p_disc = calculate_discharge_pressure(
            fluid=high_gor_fluid,
            tubing_id=2.441,
            pump_depth=5000.0,
            wellhead_pressure=100.0,
            target_rate=1000.0,
            t_pump=170.0,
            t_wellhead=80.0,
        )
        # Entre la THP de superficie y la columna de líquido puro.
        assert 100 < p_disc < 2200, (
            f"La presión de descarga {p_disc:.0f} psi cae fuera del rango esperado"
        )
        assert p_disc == pytest.approx(681.0, rel=0.10), (
            f"Valor de regresión de P&C para este escenario: {p_disc:.0f} psi"
        )

    def test_higher_thp_gives_higher_discharge(self, base_fluid):
        """Más contrapresión en superficie sube la presión de descarga."""
        p_lo = calculate_discharge_pressure(
            fluid=base_fluid, tubing_id=2.441, pump_depth=6000,
            wellhead_pressure=100, target_rate=1000,
            t_pump=165, t_wellhead=80,
        )
        p_hi = calculate_discharge_pressure(
            fluid=base_fluid, tubing_id=2.441, pump_depth=6000,
            wellhead_pressure=300, target_rate=1000,
            t_pump=165, t_wellhead=80,
        )
        # Más THP mete más gas en solución en toda la columna, así que la
        # densidad de la mezcla sube y la descarga crece más que el ΔTHP.
        assert p_hi > p_lo
        assert (p_hi - p_lo) > 200.0

    def test_deeper_pump_gives_higher_discharge(self, base_fluid):
        p_shallow = calculate_discharge_pressure(
            fluid=base_fluid, tubing_id=2.441, pump_depth=4000,
            wellhead_pressure=150, target_rate=1000,
            t_pump=150, t_wellhead=80,
        )
        p_deep = calculate_discharge_pressure(
            fluid=base_fluid, tubing_id=2.441, pump_depth=7000,
            wellhead_pressure=150, target_rate=1000,
            t_pump=165, t_wellhead=80,
        )
        assert p_deep > p_shallow

    def test_higher_gor_gives_lower_discharge(self, base_fluid):
        """Más gas en el tubing aliviana la mezcla y baja la descarga."""
        lo_gor = Fluid(
            oil_api=35, water_cut=0.5, gor=200, gas_sg=0.65, water_sg=1.08,
            oil_viscosity_dead=10, viscosity_temp_ref=100,
            bubble_point_pressure=1000, h2s_content=0, co2_content=0,
            sand_production=False,
        )
        hi_gor = Fluid(
            oil_api=35, water_cut=0.5, gor=1500, gas_sg=0.65, water_sg=1.08,
            oil_viscosity_dead=10, viscosity_temp_ref=100,
            bubble_point_pressure=3000, h2s_content=0, co2_content=0,
            sand_production=False,
        )
        p_lo = calculate_discharge_pressure(lo_gor, 2.441, 6000, 150, 1000, 165, 80)
        p_hi = calculate_discharge_pressure(hi_gor, 2.441, 6000, 150, 1000, 165, 80)
        assert p_lo > p_hi


# ---------------------------------------------------------------------------
# 7. calculate_pip
# ---------------------------------------------------------------------------

class TestCalculatePIP:
    def test_pip_less_than_pwf(self, reservoir, base_fluid, well):
        """El PIP tiene que estar por debajo de la Pwf: la presión cae desde
        las perforaciones hasta la admisión."""
        from bes.core.ipr import calculate_pwf_for_target_rate
        target = 1200.0
        pwf = calculate_pwf_for_target_rate(reservoir, target)
        pip = calculate_pip(reservoir, base_fluid, well,
                            pump_setting_depth=8400, target_rate=target)
        assert pip < pwf

    def test_pip_positive(self, reservoir, base_fluid, well):
        pip = calculate_pip(reservoir, base_fluid, well,
                            pump_setting_depth=8400, target_rate=1000.0)
        assert pip > 0.0

    def test_pip_reasonable_at_several_rates(self, reservoir, base_fluid, well):
        pip_lo = calculate_pip(reservoir, base_fluid, well,
                               pump_setting_depth=8400, target_rate=500.0)
        pip_hi = calculate_pip(reservoir, base_fluid, well,
                               pump_setting_depth=8400, target_rate=1500.0)
        assert pip_lo > 0 and pip_hi > 0

    def test_pip_below_reservoir_pressure(self, reservoir, base_fluid, well):
        pip = calculate_pip(reservoir, base_fluid, well,
                            pump_setting_depth=8400, target_rate=1000.0)
        assert pip < reservoir.static_pressure


# ---------------------------------------------------------------------------
# 5. Envelope de aplicabilidad de Poettmann & Carpenter
# ---------------------------------------------------------------------------
#
# Los cuatro límites del método, aportados por Pablo de los apuntes de cátedra:
# tubing de 2, 2½ y 3 pulg · μo < 5 cp · RGL < 1500 scf/bbl · q > 400 bbl/d.

class TestRelacionGasLiquido:
    """RGL = GOR/(1 + WOR). No es lo mismo que el GOR en cuanto hay agua."""

    def test_sin_agua_la_rgl_es_el_gor(self):
        assert mp.gas_liquid_ratio(500.0, 0.0) == pytest.approx(500.0)

    def test_con_agua_la_rgl_baja(self):
        """40 % de agua: el mismo gas repartido en más barriles de líquido."""
        assert mp.gas_liquid_ratio(500.0, 0.40) == pytest.approx(300.0)

    def test_es_la_forma_de_la_catedra_despejada(self):
        """RGL = GOR/(1+WOR) y GOR·(1−Wc) son la misma cuenta."""
        for wc in (0.0, 0.15, 0.5, 0.9):
            wor = wc / (1 - wc)
            assert mp.gas_liquid_ratio(800.0, wc) == pytest.approx(
                800.0 / (1 + wor)
            ) == pytest.approx(800.0 * (1 - wc))

    def test_un_pozo_de_puro_agua_no_tiene_rgl(self):
        with pytest.raises(ValueError, match="water_cut"):
            mp.gas_liquid_ratio(500.0, 1.0)


class TestTuberiasParaLasQueValeElMetodo:
    def test_las_tres_nominales(self):
        """2, 2½ y 3 pulg son estos OD en la tabla API."""
        assert all(mp.tubing_od_is_pc_range(od) for od in (2.375, 2.875, 3.5))

    def test_las_mas_grandes_quedan_afuera(self):
        assert not mp.tubing_od_is_pc_range(4.0)
        assert not mp.tubing_od_is_pc_range(4.5)


class TestEnvelopeCompleto:
    def _fluido(self, **cambios) -> Fluid:
        base = dict(
            oil_api=35.0, water_cut=0.0, gor=500.0, gas_sg=0.65, water_sg=1.08,
            oil_viscosity_dead=2.0, viscosity_temp_ref=160.0,
            bubble_point_pressure=2000.0, h2s_content=0.0, co2_content=0.0,
            sand_production=False,
        )
        return Fluid(**{**base, **cambios})

    def test_un_pozo_adentro_del_envelope_no_avisa_nada(self, well):
        v = mp.poettmann_carpenter_applicability(
            self._fluido(), well, q_liq=1500.0, temp_f=160.0
        )
        assert v["applicable"] is True
        assert v["warnings"] == []

    def test_el_crudo_viscoso_avisa(self, well):
        v = mp.poettmann_carpenter_applicability(
            self._fluido(oil_viscosity_dead=20.0), well, q_liq=1500.0,
            temp_f=160.0,
        )
        assert v["applicable"] is False
        assert any("livianos" in w for w in v["warnings"])

    def test_el_limite_de_viscosidad_es_estricto(self, well):
        """«Menores a 5 cp»: 5.0 exactos ya no cumple."""
        v = mp.poettmann_carpenter_applicability(
            self._fluido(oil_viscosity_dead=5.0), well, q_liq=1500.0,
            temp_f=160.0,
        )
        assert not next(c for c in v["checks"] if c["item"] == "viscosidad")["ok"]

    def test_mucho_gas_avisa(self, well):
        v = mp.poettmann_carpenter_applicability(
            self._fluido(gor=2000.0), well, q_liq=1500.0, temp_f=160.0
        )
        assert any("gas-líquido" in w for w in v["warnings"])

    def test_el_limite_de_gas_se_mide_en_rgl_no_en_gor(self, well):
        """Un GOR de 2000 con 50 % de agua da RGL 1000: adentro del rango.

        Comparar el GOR pelado contra el límite daría un aviso equivocado.
        """
        v = mp.poettmann_carpenter_applicability(
            self._fluido(gor=2000.0, water_cut=0.50), well, q_liq=1500.0,
            temp_f=160.0,
        )
        assert v["glr_scf_bbl"] == pytest.approx(1000.0)
        assert not any("gas-líquido" in w for w in v["warnings"])

    def test_caudal_bajo_avisa(self, well):
        v = mp.poettmann_carpenter_applicability(
            self._fluido(), well, q_liq=300.0, temp_f=160.0
        )
        assert any("caudal" in w for w in v["warnings"])

    def test_la_tuberia_grande_avisa(self, base_fluid):
        grande = WellGeometry(
            total_depth=9000.0, casing_od=7.0, casing_weight=23.0,
            casing_id=6.366, tubing_od=4.5, tubing_id=3.958,
            perforations_top=8700.0, perforations_bottom=8900.0,
            deviation_max=5.0, wellhead_temp=80.0,
        )
        v = mp.poettmann_carpenter_applicability(
            self._fluido(), grande, q_liq=1500.0, temp_f=160.0
        )
        assert any("fuera del rango" in w for w in v["warnings"])

    def test_sin_ensayo_la_viscosidad_sale_de_la_lamina(self, well):
        """El envelope no exige ensayo de laboratorio: se lee la Fig. 4L(2)."""
        v = mp.poettmann_carpenter_applicability(
            self._fluido(oil_viscosity_dead=None, viscosity_temp_ref=None),
            well, q_liq=1500.0, temp_f=160.0,
        )
        assert "4L(2)" in v["viscosity_source"]
        assert v["viscosity_cp"] > 0
