"""
Tests for the equipment catalog loader.
Validates against Kermit Brown examples and physical consistency rules.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from bes.catalogs.loader import CatalogManager
from bes.core.models import PumpCurve



@pytest.fixture(scope="module")
def manager() -> CatalogManager:
    return CatalogManager()


@pytest.fixture(scope="module")
def d40(manager: CatalogManager) -> PumpCurve:
    pumps = manager.get_all_pumps()
    match = [p for p in pumps if p.model == "D-40"]
    assert match, "D-40 not found in catalog"
    return match[0]


@pytest.fixture(scope="module")
def i300(manager: CatalogManager) -> PumpCurve:
    pumps = manager.get_all_pumps()
    match = [p for p in pumps if p.model == "I-300"]
    assert match, "I-300 not found in catalog"
    return match[0]


# ---------------------------------------------------------------------------
# Catalog loading
# ---------------------------------------------------------------------------

class TestCatalogLoading:
    def test_at_least_10_pumps(self, manager):
        assert len(manager.get_all_pumps()) >= 10

    def test_all_pumps_are_pump_curve_instances(self, manager):
        for p in manager.get_all_pumps():
            assert isinstance(p, PumpCurve)

    def test_at_least_15_motors(self, manager):
        assert len(manager._motors) >= 15

    def test_cables_loaded(self, manager):
        assert len(manager._cables) >= 10

    def test_seals_loaded(self, manager):
        assert len(manager._seals) >= 5

    def test_pumps_have_points(self, manager):
        for pump in manager.get_all_pumps():
            assert len(pump.points) >= 10, f"{pump.model} has fewer than 10 curve points"

    def test_gas_handlers_loaded(self, manager):
        assert len(manager.get_all_gas_handlers()) >= 10

    def test_sensors_loaded(self, manager):
        assert len(manager.get_all_sensors()) >= 4

    def test_solo_los_tres_proveedores(self, manager):
        """El catálogo trabaja con REDA, Centrilift y Wood Group ESP y nadie más.

        «Brown (libro)» no es un proveedor: son los ejemplos numerados de Kermit
        Brown que anclan la validación, y por eso se admite entre las bombas.
        """
        proveedores = {"REDA", "Centrilift", "Wood Group ESP"}
        for nombre, items in (("motores", manager._motors),
                              ("sellos", manager._seals),
                              ("cables", manager._cables)):
            fabricantes = {x.get("manufacturer") for x in items}
            assert fabricantes <= proveedores, f"{nombre}: sobra {fabricantes - proveedores}"
        fab_bombas = {p.manufacturer for p in manager.get_all_pumps()}
        assert fab_bombas <= proveedores | {"Brown (libro)"}

    def test_aparejo_propio_por_proveedor(self, manager):
        """Qué proveedores pueden armar un aparejo completo, y cuáles no.

        Es la contracara de la regla de no mezclar fabricantes: un proveedor que
        aporta bombas pero no motores no puede diseñar nada. Hoy pasa con Wood
        Group ESP —tiene 7 bombas y 39 protectores, pero ningún catálogo de
        motores llegó al proyecto—, así que sus bombas quedan en el catálogo y
        el diseño las descarta avisando el motivo.

        El test fija ese estado a propósito: si aparece el catálogo de motores
        Wood Group, falla y hay que sacarlo de la lista de incompletos. Si otro
        proveedor pierde su aparejo, también falla.
        """
        SIN_MOTOR_PROPIO = {"Wood Group ESP"}

        con_bomba = {p.manufacturer for p in manager.get_all_pumps()} - {"Brown (libro)"}
        con_motor = {m.get("manufacturer") for m in manager._motors}
        con_sello = {s.get("manufacturer") for s in manager._seals}
        incompletos = con_bomba - (con_motor & con_sello)

        assert incompletos == SIN_MOTOR_PROPIO, (
            f"Cambió qué proveedores pueden armar aparejo. Esperado sin aparejo "
            f"propio: {SIN_MOTOR_PROPIO}; encontrado: {incompletos}."
        )


# ---------------------------------------------------------------------------
# Seal / protector selection
# ---------------------------------------------------------------------------

class TestSealSelection:
    def test_selects_compatible_series(self, manager):
        seal = manager.get_seal("400", temp_f=200, thrust_lbs=1000, prefer_type="labyrinth")
        assert "400" in seal["compatible_motor_series"]

    def test_respeta_el_fabricante_pedido(self, manager):
        """Con `manufacturer` el protector sale de ese proveedor y de ningún otro."""
        for fabricante, serie in (("Centrilift", "450"), ("REDA", "456")):
            seal = manager.get_seal(serie, temp_f=200, thrust_lbs=1000,
                                    manufacturer=fabricante)
            assert seal["manufacturer"] == fabricante

    def test_sin_protector_del_fabricante_falla_explicito(self, manager):
        """Antes que devolver uno de otra marca, avisa que no hay."""
        with pytest.raises(ValueError, match="Wood Group ESP"):
            manager.get_seal("450", temp_f=200, thrust_lbs=1000,
                             manufacturer="Wood Group ESP")

    def test_prefers_requested_type(self, manager):
        seal = manager.get_seal("540", temp_f=200, thrust_lbs=1000, prefer_type="bag")
        assert seal["type"] == "bag"

    def test_smallest_thrust_that_qualifies(self, manager):
        """Con empuje publicado se elige el menor que aguanta; sin él, no descalifica.

        Hoy ningún protector del catálogo publica capacidad de empuje —ni REDA
        ni Wood Group ni Centrilift la imprimen por modelo—, así que el criterio
        queda sin aplicar y la verificación se reporta como no realizada.
        """
        seal = manager.get_seal("540", temp_f=200, thrust_lbs=16000, prefer_type="labyrinth")
        capacidad = seal.get("thrust_capacity_lbs")
        assert capacidad is None or capacidad >= 16000

    def test_temperature_excludes_the_ones_that_publish_it(self, manager):
        """Un protector con temperatura publicada no se ofrece por encima de ella.

        Los que NO la publican siguen disponibles: es una verificación no
        realizada, no una aprobada. Se comprueba pidiendo una temperatura
        absurda y verificando que lo que vuelve tiene el dato en null.
        """
        seal = manager.get_seal("375", temp_f=600, thrust_lbs=100,
                                prefer_type="labyrinth")
        assert seal["max_temp_f"] is None

    def test_thrust_exceeding_all_published_capacities(self, manager):
        """Idem para el empuje: sólo sobreviven los de capacidad desconocida."""
        seal = manager.get_seal("375", temp_f=200, thrust_lbs=999999,
                                prefer_type="labyrinth")
        assert seal["thrust_capacity_lbs"] is None

    def test_published_capacity_wins_over_unknown(self, manager):
        """Con carga chica gana un protector verificado, no uno sin datos.

        Cuando ninguno publica capacidad —el caso de hoy: ni REDA ni Wood Group
        ni Centrilift la imprimen por modelo— no hay preferencia que aplicar y
        el criterio queda inactivo. El test protege el orden para el día que
        aparezca el dato, sin exigir que exista ahora.
        """
        candidatos = [s for s in manager._seals
                      if "375" in s.get("compatible_motor_series", [])]
        if not any(s.get("thrust_capacity_lbs") is not None for s in candidatos):
            pytest.skip("ningún protector de la serie 375 publica capacidad de empuje")
        seal = manager.get_seal("375", temp_f=200, thrust_lbs=100,
                                prefer_type="labyrinth")
        assert seal["thrust_capacity_lbs"] is not None

    def test_no_compatible_series_raises(self, manager):
        with pytest.raises(ValueError):
            manager.get_seal("999", temp_f=200, thrust_lbs=100,
                             prefer_type="labyrinth")


# ---------------------------------------------------------------------------
# Gas-handler and sensor selection
# ---------------------------------------------------------------------------

class TestGasHandlerSelection:
    def test_selects_within_flow_and_casing(self, manager):
        gh = manager.select_gas_handler(2000, casing_id_in=4.892, prefer_type="vortex")
        assert gh is not None
        assert gh["min_flow_bpd"] <= 2000 <= gh["max_flow_bpd"]
        assert gh["od_inches"] < 4.892

    def test_prefers_vortex(self, manager):
        gh = manager.select_gas_handler(2000, casing_id_in=4.892, prefer_type="vortex")
        assert gh["type"] == "vortex"

    def test_returns_none_when_too_large(self, manager):
        # No gas handler fits a 3-inch casing
        assert manager.select_gas_handler(1000, casing_id_in=3.0) is None


class TestSensorSelection:
    def test_hot_well_picks_xtreme(self, manager):
        s = manager.select_sensor(intake_pressure_psi=3000, bottom_temp_f=340, motor_voltage=1000)
        assert s is not None
        assert s["intake_temp_max_f"] >= 340

    def test_dual_when_discharge_needed(self, manager):
        s = manager.select_sensor(
            intake_pressure_psi=3000, bottom_temp_f=200, motor_voltage=1000,
            need_discharge_pressure=True,
        )
        assert s["discharge_pressure_max_psi"]

    def test_none_when_out_of_range(self, manager):
        assert manager.select_sensor(
            intake_pressure_psi=99999, bottom_temp_f=200, motor_voltage=1000,
        ) is None

    # Tolerancia sobre el rango de altura de cada curva. La exigencia original
    # era monotonía estricta, que valía mientras las curvas se generaban con una
    # forma centrífuga ideal. Las curvas digitalizadas del catálogo REDA son
    # trazos reales y no cumplen eso por dos motivos legítimos: las bombas de
    # muy alto caudal tienen la curva «enganchada», con un tramo central que
    # vuelve a subir, y el trazo del PDF tiene un espesor que introduce subidas
    # de una fracción de punto. Lo que sí se sigue exigiendo es la tendencia.
    _HEAD_RISE_TOLERANCE = 0.03

    def test_pump_head_decreasing_overall(self, manager):
        for pump in manager.get_all_pumps():
            heads = [p.head_per_stage for p in pump.points]
            span = max(heads) - min(heads)
            assert heads[0] > heads[-1], f"{pump.model}: la altura no baja con el caudal"
            for i in range(1, len(heads)):
                rise = (heads[i] - heads[i - 1]) / span if span else 0.0
                assert rise <= self._HEAD_RISE_TOLERANCE, (
                    f"{pump.model}: la altura sube {rise * 100:.1f}% del rango en "
                    f"el índice {i} ({heads[i-1]} -> {heads[i]}), por encima del "
                    f"{self._HEAD_RISE_TOLERANCE * 100:.0f}% tolerado"
                )

    def test_pump_efficiency_positive(self, manager):
        for pump in manager.get_all_pumps():
            for pt in pump.points:
                assert 0.0 < pt.efficiency <= 1.0

    def test_pump_bep_in_range(self, manager):
        for pump in manager.get_all_pumps():
            assert pump.min_flow <= pump.bep_flow <= pump.max_flow


# ---------------------------------------------------------------------------
# Pump curve interpolation — Book Example #2A (Kermit Brown, Vol. 2b)
# ---------------------------------------------------------------------------

class TestInterpolationD40:
    """Reda D-40 at 1227 bpd: head ≈ 23 ft/stage, hp ≈ 0.35 hp/stage."""

    def test_head_at_1227_bpd(self, manager, d40):
        result = manager.interpolate_pump_curve(d40, 1227)
        assert result["head_per_stage"] == pytest.approx(23.0, rel=0.02), (
            f"Expected ~23 ft/stage, got {result['head_per_stage']:.2f}"
        )

    def test_hp_at_1227_bpd(self, manager, d40):
        result = manager.interpolate_pump_curve(d40, 1227)
        assert result["hp_per_stage"] == pytest.approx(0.35, rel=0.03), (
            f"Expected ~0.35 hp/stage, got {result['hp_per_stage']:.3f}"
        )

    def test_efficiency_at_1227_positive(self, manager, d40):
        result = manager.interpolate_pump_curve(d40, 1227)
        assert 0.0 < result["efficiency"] <= 1.0

    def test_head_at_bep_higher_than_at_max(self, manager, d40):
        bep = manager.interpolate_pump_curve(d40, d40.bep_flow)
        at_max = manager.interpolate_pump_curve(d40, d40.max_flow)
        assert bep["head_per_stage"] > at_max["head_per_stage"]

    def test_out_of_range_raises(self, manager, d40):
        min_q = min(p.flow_rate for p in d40.points)
        max_q = max(p.flow_rate for p in d40.points)
        with pytest.raises(ValueError):
            manager.interpolate_pump_curve(d40, min_q - 1.0)
        with pytest.raises(ValueError):
            manager.interpolate_pump_curve(d40, max_q + 1.0)


# ---------------------------------------------------------------------------
# Pump curve interpolation — Book Example #1A (Kermit Brown, Vol. 2b)
# ---------------------------------------------------------------------------

class TestInterpolationI300:
    """Centrilift I-300 at 10000 bpd: head ≈ 59.5 ft/stage."""

    def test_head_at_10000_bpd(self, manager, i300):
        result = manager.interpolate_pump_curve(i300, 10000)
        assert result["head_per_stage"] == pytest.approx(59.5, rel=0.02), (
            f"Expected ~59.5 ft/stage, got {result['head_per_stage']:.2f}"
        )

    def test_hp_at_10000_bpd_positive(self, manager, i300):
        result = manager.interpolate_pump_curve(i300, 10000)
        assert result["hp_per_stage"] > 0

    def test_i300_od_fits_in_8625_casing(self, i300):
        # 8-5/8" casing 24 lb/ft has ID ≈ 7.825" — I-300 OD must be below this
        assert i300.od < 7.825


# ---------------------------------------------------------------------------
# Casing filter — 5.5" nominal casing
# ---------------------------------------------------------------------------

class TestCasingFilter:
    """For a 5.5" nominal casing the drift ID is ~4.892" (17 lb/ft).
    Only 400-series (4.00" OD) pumps should pass; 513-series and larger must not.
    """

    CASING_ID_5_5 = 4.892  # ID of 5.5" 17 lb/ft casing [in]

    def test_400_series_passes(self, manager):
        result = manager.get_pumps_by_casing(self.CASING_ID_5_5)
        models_found = {p.model for p in result}
        # D-40 es la bomba del Ejemplo #2A de Brown, con fuente en el libro.
        # D-55 y D-82 se borraron: su curva no tenía fuente confirmada.
        assert "D-40" in models_found
        assert "D-55" not in models_found
        assert all(p.od < self.CASING_ID_5_5 for p in result)

    def test_513_series_excluded(self, manager):
        result = manager.get_pumps_by_casing(self.CASING_ID_5_5)
        excluded_models = {"I-42B", "Y-62B", "N-80", "Z-69"}
        found_excluded = {p.model for p in result} & excluded_models
        assert not found_excluded, (
            f"513-series pumps should not fit in 5.5\" casing, but found: {found_excluded}"
        )

    def test_large_pumps_excluded(self, manager):
        result = manager.get_pumps_by_casing(self.CASING_ID_5_5)
        excluded = {p.model for p in result} & {"I-300", "G-52E"}
        assert not excluded

    def test_filter_returns_list(self, manager):
        result = manager.get_pumps_by_casing(self.CASING_ID_5_5)
        assert isinstance(result, list)

    def test_larger_casing_includes_513(self, manager):
        # 7" casing ID ≈ 6.276" should admit 5.13" pumps
        result = manager.get_pumps_by_casing(6.276)
        series_found = {p.series for p in result}
        assert "513" in series_found


# ---------------------------------------------------------------------------
# Flow range filter
# ---------------------------------------------------------------------------

class TestFlowRangeFilter:
    def test_1227_bpd_matches_d40(self, manager):
        result = manager.get_pumps_by_flow_range(1227)
        models = {p.model for p in result}
        assert "D-40" in models

    def test_10000_bpd_matches_i300(self, manager):
        result = manager.get_pumps_by_flow_range(10000)
        models = {p.model for p in result}
        assert "I-300" in models

    def test_10000_bpd_excludes_small_pumps(self, manager):
        result = manager.get_pumps_by_flow_range(10000)
        models = {p.model for p in result}
        assert "D-40" not in models
        assert "M-34" not in models

    def test_very_high_flow_returns_empty_or_only_large(self, manager):
        # 50 000 bpd solo puede cubrirlo una bomba de muy alto caudal (serie
        # grande, p. ej. Summit SN950). El catálogo puede no tener ninguna, o
        # tener solo bombas grandes cuyo rango incluya ese caudal; en ningún
        # caso aparecen bombas chicas.
        result = manager.get_pumps_by_flow_range(50000)
        for p in result:
            assert p.min_flow <= 50000 <= p.max_flow
            assert p.max_flow >= 50000  # solo bombas de alto caudal califican


# ---------------------------------------------------------------------------
# Motor query
# ---------------------------------------------------------------------------

class TestMotorQuery:
    def test_get_motor_returns_dict(self, manager):
        motor = manager.get_motor(hp=50, voltage=860, series="456")
        assert isinstance(motor, dict)
        assert "hp_rating" in motor

    def test_motor_hp_at_least_requested(self, manager):
        motor = manager.get_motor(hp=50, voltage=1000, series="456")
        assert motor["hp_rating"] >= 50

    def test_motor_fallback_ignores_series(self, manager):
        # Series "999" doesn't exist — should fall back to any series
        motor = manager.get_motor(hp=30, voltage=700, series="999")
        assert motor["hp_rating"] >= 30

    def test_motor_no_match_raises(self, manager):
        with pytest.raises(ValueError):
            manager.get_motor(hp=99999, voltage=440, series="375")


# ---------------------------------------------------------------------------
# Cable query
# ---------------------------------------------------------------------------

class TestCableQuery:
    def test_get_cable_returns_dict(self, manager):
        cable = manager.get_cable(amps=40, temp_f=150, voltage=1000)
        assert isinstance(cable, dict)
        assert "max_amps" in cable

    def test_cable_rated_for_amps(self, manager):
        cable = manager.get_cable(amps=40, temp_f=150, voltage=1000)
        assert cable["max_amps"] >= 40

    def test_cable_rated_for_temp(self, manager):
        cable = manager.get_cable(amps=40, temp_f=350, voltage=1000)
        assert cable["max_temp_f"] >= 350

    def test_no_cable_raises(self, manager):
        with pytest.raises(ValueError):
            manager.get_cable(amps=9999, temp_f=150, voltage=1000)

    def test_high_temp_requires_epdm_or_redalene(self, manager):
        cable = manager.get_cable(amps=40, temp_f=450, voltage=1000)
        assert cable["max_temp_f"] >= 450


class TestControllerSelection:
    """Selección de controlador de superficie (tablero / VSD)."""

    def _cm(self):
        from bes.catalogs.loader import CatalogManager
        cm = CatalogManager()
        if not cm.get_all_controllers():
            pytest.skip(
                "controllers.json quedó vacío: los 10 tableros eran nombres de "
                "modelo inventados ('representativo línea X'). Estos tests "
                "vuelven a correr solos cuando se cargue un catálogo real."
            )
        return cm

    def test_catalog_loaded(self):
        """Todo controlador cargado declara los tres límites que se verifican."""
        cm = self._cm()
        for controller in cm.get_all_controllers():
            assert controller["manufacturer"]
            for field in ("max_voltage", "max_amps", "max_kva"):
                assert controller[field] and controller[field] > 0, (
                    f"{controller['model']}: {field} sin valor")

    def test_vsd_falls_back_to_switchboard(self):
        """Pedir VSD sin VSD en catálogo devuelve un tablero, no un error.

        El único catálogo de superficie cargado es el de Wood Group, que
        publica tableros y no variadores. La preferencia es preferencia: si no
        hay del tipo pedido, `get_controller` entrega uno que sí cubra las
        condiciones. El día que entre un catálogo con VSD, este test lo detecta
        porque el tipo devuelto cambia.
        """
        cm = self._cm()
        tipos = {c["type"] for c in cm.get_all_controllers()}
        controller = cm.get_controller(voltage=1800, kva=200, amps=48,
                                       prefer_vsd=True)
        assert controller["type"] == ("vsd" if "vsd" in tipos else "switchboard")

    def test_prefers_switchboard_by_default(self):
        cm = self._cm()
        c = cm.get_controller(voltage=1800, kva=200, amps=48, prefer_vsd=False)
        assert c["type"] == "switchboard"

    def test_covers_requirements(self):
        cm = self._cm()
        c = cm.get_controller(voltage=2000, kva=300, amps=60, prefer_vsd=False)
        assert c["max_voltage"] >= 2000 and c["max_kva"] >= 300 and c["max_amps"] >= 60

    def test_no_controller_raises(self):
        import pytest
        cm = self._cm()
        with pytest.raises(ValueError):
            cm.get_controller(voltage=99999, kva=99999, amps=99999)
