"""
Tests for core/affinity.py — leyes de afinidad.

Referencias:
  - Brown, Vol. 2b, Table 4.21.
  - Apunte de cátedra Unidad N°9, pág. 135 (recuadro de leyes de afinidad):
        Q2 = Q1·(N2/N1)·(D2/D1)
        H2 = H1·(N2/N1)²·(D2/D1)²
        HP2 = HP1·(N2/N1)³·(D2/D1)³·(SG2/SG1)
    y HHP = Q·Hd·SG / 136 000 (constante redondeada; acá se usa 135 771).
"""
from __future__ import annotations

import pytest

from bes.catalogs.loader import CatalogManager
from bes.core import units
from bes.core.affinity import (
    frequency_for_flow,
    hydraulic_hp,
    motor_rpm,
    scale_curve,
    scale_flow,
    scale_head,
    scale_power,
    synchronous_rpm,
)


class TestExponents:
    """El contenido físico de las leyes son los exponentes: 1, 2 y 3."""

    def test_flow_is_linear_in_speed(self):
        assert scale_flow(1000.0, 60.0, 30.0) == pytest.approx(500.0)
        assert scale_flow(1000.0, 60.0, 120.0) == pytest.approx(2000.0)

    def test_head_goes_with_the_square(self):
        assert scale_head(40.0, 60.0, 30.0) == pytest.approx(10.0)
        assert scale_head(40.0, 60.0, 120.0) == pytest.approx(160.0)

    def test_power_goes_with_the_cube(self):
        assert scale_power(8.0, 60.0, 30.0) == pytest.approx(1.0)
        assert scale_power(8.0, 60.0, 120.0) == pytest.approx(64.0)

    def test_diameter_uses_the_same_exponents_as_speed(self):
        """El apunte lo dice explícito: el diámetro entra con los mismos
        exponentes que la velocidad."""
        assert scale_flow(100.0, 60.0, 60.0, diameter_ratio=0.9) == pytest.approx(90.0)
        assert scale_head(100.0, 60.0, 60.0, diameter_ratio=0.9) == pytest.approx(81.0)
        assert scale_power(100.0, 60.0, 60.0, diameter_ratio=0.9) == pytest.approx(72.9)

    def test_power_is_the_only_law_with_specific_gravity(self):
        """La altura no depende de la densidad; la potencia sí, linealmente."""
        assert scale_power(10.0, 60.0, 60.0, sg_ratio=1.2) == pytest.approx(12.0)
        # head y caudal no aceptan SG: mover un fluido más pesado no cambia
        # los pies de columna que desarrolla el impulsor.
        assert scale_head(30.0, 60.0, 60.0) == pytest.approx(30.0)

    def test_identity_when_nothing_changes(self):
        assert scale_flow(1234.0, 60.0, 60.0) == pytest.approx(1234.0)
        assert scale_head(56.7, 50.0, 50.0) == pytest.approx(56.7)
        assert scale_power(8.9, 50.0, 50.0) == pytest.approx(8.9)

    def test_round_trip(self):
        q = scale_flow(1000.0, 60.0, 50.0)
        assert scale_flow(q, 50.0, 60.0) == pytest.approx(1000.0)

    @pytest.mark.parametrize("fn", [scale_flow, scale_head, scale_power])
    def test_non_positive_frequency_rejected(self, fn):
        with pytest.raises(ValueError, match="freq_to"):
            fn(100.0, 60.0, 0.0)
        with pytest.raises(ValueError, match="freq_from"):
            fn(100.0, 0.0, 60.0)

    def test_non_positive_sg_ratio_rejected(self):
        with pytest.raises(ValueError, match="sg_ratio"):
            scale_power(10.0, 60.0, 60.0, sg_ratio=0.0)


class TestUnitsDelegatesToAffinity:
    """units.affinity_* son atajos de velocidad pura sobre el mismo motor:
    una sola implementación de las leyes en todo el proyecto."""

    def test_flow(self):
        assert units.affinity_flow(279.0, 50.0, 60.0) == pytest.approx(
            scale_flow(279.0, 50.0, 60.0)
        )

    def test_head(self):
        assert units.affinity_head(10.0, 60.0, 50.0) == pytest.approx(
            scale_head(10.0, 60.0, 50.0)
        )

    def test_power(self):
        assert units.affinity_power(2.0, 50.0, 60.0) == pytest.approx(
            scale_power(2.0, 50.0, 60.0)
        )


class TestSpeed:
    def test_synchronous_speed_two_poles(self):
        """El apunte: a 50 Hz el campo del estator gira a 3000 rpm."""
        assert synchronous_rpm(50.0) == pytest.approx(3000.0)
        assert synchronous_rpm(60.0) == pytest.approx(3600.0)

    def test_shaft_speed_after_slip(self):
        """Y el rotor solo llega a 2917 rpm — ese es el deslizamiento."""
        assert motor_rpm(50.0) == pytest.approx(2917.0, abs=1.0)

    def test_slip_cancels_in_the_ratio(self):
        """Por eso las leyes pueden aplicarse directo sobre la frecuencia."""
        assert motor_rpm(60.0) / motor_rpm(50.0) == pytest.approx(60.0 / 50.0)

    def test_invalid_slip_rejected(self):
        with pytest.raises(ValueError, match="slip"):
            motor_rpm(50.0, slip=1.0)


class TestFrequencyForFlow:
    def test_inverts_the_flow_law(self):
        assert frequency_for_flow(1300.0, 1560.0, 60.0) == pytest.approx(72.0)

    def test_round_trip_against_scale_flow(self):
        f = frequency_for_flow(1000.0, 1400.0, 60.0)
        assert scale_flow(1000.0, 60.0, f) == pytest.approx(1400.0)

    def test_rejects_non_positive(self):
        with pytest.raises(ValueError, match="target_flow"):
            frequency_for_flow(1000.0, 0.0, 60.0)


class TestHydraulicHp:
    def test_matches_the_apunte_formula(self):
        """HHP = Q·Hd·SG / 136 000 (el apunte redondea la constante)."""
        q, h, sg = 1300.0, 5830.0, 0.9
        assert hydraulic_hp(q, h, sg) == pytest.approx(q * h * sg / 136_000.0, rel=2e-3)

    def test_scales_with_specific_gravity(self):
        assert hydraulic_hp(1000.0, 1000.0, 2.0) == pytest.approx(
            2.0 * hydraulic_hp(1000.0, 1000.0, 1.0)
        )

    def test_non_positive_returns_zero(self):
        assert hydraulic_hp(0.0, 1000.0, 1.0) == 0.0


class TestScaleCurve:
    @pytest.fixture(scope="class")
    def pump(self):
        cm = CatalogManager()
        return next(p for p in cm.get_all_pumps() if p.model == "D-40")

    def test_catalog_frequency_is_the_default_baseline(self, pump):
        c = scale_curve(pump, pump.catalog_frequency_hz)
        assert c["speed_ratio"] == pytest.approx(1.0)
        assert c["bep_flow"] == pytest.approx(pump.bep_flow)
        assert c["min_flow"] == pytest.approx(pump.min_flow)
        assert c["max_flow"] == pytest.approx(pump.max_flow)

    def test_whole_envelope_shifts_with_the_flow_law(self, pump):
        c = scale_curve(pump, 50.0)
        r = 50.0 / pump.catalog_frequency_hz
        assert c["min_flow"] == pytest.approx(pump.min_flow * r)
        assert c["max_flow"] == pytest.approx(pump.max_flow * r)
        assert c["bep_flow"] == pytest.approx(pump.bep_flow * r)

    def test_efficiency_is_invariant(self, pump):
        """La eficiencia no se escala: es lo que hace de esto una transformación
        de similitud y no un ajuste."""
        base = [p.efficiency for p in pump.points]
        for freq in (40.0, 50.0, 70.0):
            got = [p["efficiency"] for p in scale_curve(pump, freq)["points"]]
            assert got == pytest.approx(base)

    def test_point_count_is_preserved(self, pump):
        assert len(scale_curve(pump, 45.0)["points"]) == len(pump.points)

    def test_lower_frequency_lowers_head_faster_than_flow(self, pump):
        """H ∝ N² cae más rápido que Q ∝ N: es el efecto que hace que bajar
        frecuencia no sea gratis."""
        c = scale_curve(pump, 30.0)          # mitad de la frecuencia
        assert c["bep_flow"] == pytest.approx(pump.bep_flow * 0.5)
        base_head = max(p.head_per_stage for p in pump.points)
        new_head = max(p["head_ft_per_stage"] for p in c["points"])
        assert new_head == pytest.approx(base_head * 0.25)

    def test_specific_gravity_only_touches_power(self, pump):
        plain = scale_curve(pump, 60.0)
        heavy = scale_curve(pump, 60.0, sg_ratio=1.2)
        assert [p["head_ft_per_stage"] for p in heavy["points"]] == pytest.approx(
            [p["head_ft_per_stage"] for p in plain["points"]]
        )
        assert [p["hp_per_stage"] for p in heavy["points"]] == pytest.approx(
            [1.2 * p["hp_per_stage"] for p in plain["points"]]
        )

    def test_explicit_baseline_overrides_the_catalog_one(self, pump):
        c = scale_curve(pump, 60.0, from_frequency_hz=50.0)
        assert c["from_frequency_hz"] == pytest.approx(50.0)
        assert c["speed_ratio"] == pytest.approx(1.2)

    def test_reports_the_shaft_speed(self, pump):
        c = scale_curve(pump, 50.0)
        assert c["synchronous_rpm"] == pytest.approx(3000.0)
        assert c["motor_rpm"] == pytest.approx(2917.0, abs=1.0)


class TestPumpAtFrequency:
    """La curva llevada a la frecuencia de operación. Es la corrección que hace
    que un pozo a 50 Hz no se diseñe contra una curva de 60 Hz."""

    @pytest.fixture(scope="class")
    def pump(self):
        cm = CatalogManager()
        return next(p for p in cm.get_all_pumps() if p.model == "D-40")

    def test_point_to_point_invariant(self, pump):
        """El invariante de las leyes es punto CORRESPONDIENTE: el punto
        (Q, H, HP) va a (Q·r, H·r², HP·r³). No vale a caudal fijo."""
        from bes.core.affinity import pump_at_frequency
        r = 50.0 / pump.catalog_frequency_hz
        scaled = pump_at_frequency(pump, 50.0)
        for a, b in zip(pump.points, scaled.points):
            assert b.flow_rate == pytest.approx(a.flow_rate * r)
            assert b.head_per_stage == pytest.approx(a.head_per_stage * r ** 2)
            assert b.hp_per_stage == pytest.approx(a.hp_per_stage * r ** 3)
            assert b.efficiency == pytest.approx(a.efficiency)

    def test_operating_envelope_moves_with_the_flow_law(self, pump):
        """Lo que hace que la lista de candidatas cambie a 50 Hz."""
        from bes.core.affinity import pump_at_frequency
        r = 50.0 / pump.catalog_frequency_hz
        scaled = pump_at_frequency(pump, 50.0)
        assert scaled.min_flow == pytest.approx(pump.min_flow * r)
        assert scaled.max_flow == pytest.approx(pump.max_flow * r)
        assert scaled.bep_flow == pytest.approx(pump.bep_flow * r)

    def test_identity_at_the_catalog_frequency(self, pump):
        from bes.core.affinity import pump_at_frequency
        assert pump_at_frequency(pump, pump.catalog_frequency_hz) is pump

    def test_idempotent(self, pump):
        """Escalar una curva ya escalada no vuelve a escalarla: el resultado
        declara su propia frecuencia."""
        from bes.core.affinity import pump_at_frequency
        once = pump_at_frequency(pump, 50.0)
        twice = pump_at_frequency(once, 50.0)
        assert twice is once
        assert once.catalog_frequency_hz == pytest.approx(50.0)

    def test_round_trip_recovers_the_catalog_curve(self, pump):
        from bes.core.affinity import pump_at_frequency
        back = pump_at_frequency(pump_at_frequency(pump, 50.0), 60.0)
        for a, b in zip(pump.points, back.points):
            assert b.flow_rate == pytest.approx(a.flow_rate)
            assert b.head_per_stage == pytest.approx(a.head_per_stage)

    def test_identity_and_housings_are_carried_over(self, pump):
        """Solo se mueve la hidráulica: la bomba sigue siendo la misma."""
        from bes.core.affinity import pump_at_frequency
        scaled = pump_at_frequency(pump, 50.0)
        assert scaled.model == pump.model
        assert scaled.manufacturer == pump.manufacturer
        assert scaled.od == pump.od
        assert scaled.max_stages == pump.max_stages
        assert scaled.housing_options == pump.housing_options
        assert scaled.housing_pressure_limit_psi == pump.housing_pressure_limit_psi


class TestFrequencyReachesTheDesign:
    """El pozo a 50 Hz tiene que diseñarse a 50 Hz. Antes de esta corrección
    la frecuencia se mostraba pero no se usaba en ningún cálculo."""

    def _case(self, frequency: float, **objective_overrides):
        """Pozo sintético cargado a mano: crudo pesado, alto corte de agua.

        No es un caso de libro ni de cátedra — sólo tiene que ser un pozo
        físicamente coherente donde la DC1000 diseñe, para poder comparar el
        mismo pozo a dos frecuencias.
        """
        import warnings
        from bes.core.models import (
            DesignObjectives, DriveMechanism, Fluid, IPRMethod, Reservoir,
            SurfaceConditions, WellGeometry,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = Reservoir(
                static_pressure=1564.6, bubble_point=640.0,
                ipr_method=IPRMethod.VOGEL, reservoir_temp=194.0,
                drive_mechanism=DriveMechanism.SOLUTION_GAS,
                test_pwf=800.0, test_rate=1096.7,      # ⇒ J ≈ 1.15 STB/d/psi
            )
        fluid = Fluid(
            oil_api=17.0, water_cut=0.99, gor=1038.7, gas_sg=0.65,
            water_sg=1.004, oil_viscosity_dead=15.0, viscosity_temp_ref=194.0,
            bubble_point_pressure=640.0, h2s_content=0.0, co2_content=0.0,
            sand_production=False,
        )
        well = WellGeometry(
            total_depth=6400.9, casing_od=5.5, casing_weight=20.0,
            casing_id=4.778, tubing_od=2.875, tubing_id=2.441,
            perforations_top=4274.9, perforations_bottom=6141.7,
            deviation_max=0.0, wellhead_temp=100.0,
        )
        surf = SurfaceConditions(
            wellhead_pressure_required=142.2, flowline_length=1000.0,
            flowline_id=3.0, flowline_elevation_change=0.0,
            separator_pressure=100.0, power_supply_voltage=4160.0,
            frequency=frequency,
        )
        obj = DesignObjectives(**{
            "target_flow_rate": 953.5, "safety_margin_depth": 100.0,
            "allow_gas_venting": False, "max_gip": 0.1,
            "design_life_years": 5.0, "use_vsd": True,
            **objective_overrides,
        })
        return res, fluid, well, surf, obj

    def test_lower_frequency_needs_more_stages(self):
        """Misma bomba, mismo pozo: a 50 Hz el head por etapa cae, así que
        hacen falta más etapas para el mismo TDH."""
        from bes.core.pump_design import design_pump_by_model
        cm = CatalogManager()
        stages = {}
        for freq in (60.0, 50.0):
            res, fluid, well, surf, obj = self._case(freq)
            depth = max(well.perforations_top - obj.safety_margin_depth, 100.0)
            c = design_pump_by_model(res, fluid, well, surf, obj, depth, cm, "DC1000")
            stages[freq] = c["stages"]
            assert c["operating_frequency_hz"] == pytest.approx(freq)
        assert stages[50.0] > stages[60.0]

    def test_tdh_does_not_depend_on_frequency(self):
        """El TDH lo fija el pozo, no la bomba: tiene que ser el mismo."""
        from bes.core.pump_design import design_pump_by_model
        cm = CatalogManager()
        tdh = []
        for freq in (60.0, 50.0):
            res, fluid, well, surf, obj = self._case(freq)
            depth = max(well.perforations_top - obj.safety_margin_depth, 100.0)
            tdh.append(
                design_pump_by_model(res, fluid, well, surf, obj, depth, cm, "DC1000")["tdh_ft"]
            )
        assert tdh[0] == pytest.approx(tdh[1])

    def test_vsd_frequency_overrides_the_grid(self):
        from bes.core.pump_design import design_pump_by_model
        cm = CatalogManager()
        res, fluid, well, surf, obj = self._case(
            50.0, use_vsd=True, design_frequency_hz=55.0
        )
        depth = max(well.perforations_top - obj.safety_margin_depth, 100.0)
        c = design_pump_by_model(res, fluid, well, surf, obj, depth, cm, "DC1000")
        assert c["operating_frequency_hz"] == pytest.approx(55.0)

    def test_design_frequency_requires_a_vsd(self):
        with pytest.raises(ValueError, match="use_vsd"):
            self._case(50.0, use_vsd=False, design_frequency_hz=55.0)

    def test_design_frequency_out_of_vsd_range_rejected(self):
        with pytest.raises(ValueError, match="design_frequency_hz"):
            self._case(50.0, use_vsd=True, design_frequency_hz=120.0)
