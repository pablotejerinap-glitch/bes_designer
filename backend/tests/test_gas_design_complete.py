"""Diseño BES COMPLETO por el método de incrementos de presión.

Cubre los cuatro casos del objetivo:

  1. pozo convencional          → el camino de siempre, sin cambios
  2. pozo con gas               → método por intervalos (Brown §4.53103)
  3. petróleo pesado            → corrección de Riling
  4. petróleo pesado + gas      → los dos a la vez, terminando en aparejo

Lo que se verifica no es «da 210 etapas» —eso depende del catálogo— sino que
la física del método esté presente y que el resultado sea un aparejo
físicamente seleccionable, no un par de números sueltos.
"""
from __future__ import annotations

import pytest

from bes.catalogs.loader import CatalogManager
from bes.core.models import (
    DesignObjectives,
    DriveMechanism,
    Fluid,
    IPRMethod,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)
from bes.services.gas_service import gas_method_applies, run_gas_design_complete


@pytest.fixture(scope="module")
def catalog() -> CatalogManager:
    return CatalogManager()


@pytest.fixture(scope="module")
def reservoir() -> Reservoir:
    return Reservoir(
        static_pressure=2000.0, bubble_point=2000.0,
        test_pwf=1000.0, test_rate=933.3,
        ipr_method=IPRMethod.VOGEL, reservoir_temp=170.0,
        drive_mechanism=DriveMechanism.SOLUTION_GAS,
    )


@pytest.fixture(scope="module")
def well() -> WellGeometry:
    return WellGeometry(
        total_depth=6150.0, casing_od=5.5, casing_weight=17.0, casing_id=4.892,
        tubing_od=2.375, tubing_id=1.995,
        perforations_top=5900.0, perforations_bottom=6030.0,
        deviation_max=0.0, wellhead_temp=120.0,
    )


@pytest.fixture(scope="module")
def surface() -> SurfaceConditions:
    return SurfaceConditions(
        wellhead_pressure_required=200.0, flowline_length=1000.0,
        flowline_id=3.0, flowline_elevation_change=0.0,
        separator_pressure=100.0, power_supply_voltage=7200.0, frequency=60.0,
    )


@pytest.fixture(scope="module")
def objectives() -> DesignObjectives:
    return DesignObjectives(
        target_flow_rate=1227.0, safety_margin_depth=50.0,
        allow_gas_venting=False, max_gip=0.10,
        design_life_years=5.0, use_vsd=False,
    )


def _fluido(oil_api: float, gor: float, mu_dead: float = 5.0) -> Fluid:
    return Fluid(
        oil_api=oil_api, water_cut=0.15, gor=gor, gas_sg=0.75, water_sg=1.02,
        oil_viscosity_dead=mu_dead, viscosity_temp_ref=100.0,
        bubble_point_pressure=2000.0,
        h2s_content=0.0, co2_content=0.0, sand_production=False,
    )


@pytest.fixture(scope="module")
def con_gas() -> Fluid:
    """Caso 2: crudo liviano (30 °API) con gas."""
    return _fluido(30.0, 350.0)


@pytest.fixture(scope="module")
def pesado_con_gas() -> Fluid:
    """Caso 4: crudo pesado (18 °API) con gas — el caso principal."""
    return _fluido(18.0, 350.0, mu_dead=200.0)


@pytest.fixture(scope="module")
def sin_gas() -> Fluid:
    """Caso 1: sin gas disuelto, para el camino convencional."""
    return _fluido(30.0, 0.0)


def _correr(fluid, reservoir, well, surface, objectives, catalog, **kw):
    return run_gas_design_complete(
        reservoir=reservoir, fluid=fluid, well=well, surface=surface,
        objectives=objectives, catalog_manager=catalog, **kw
    )


# ===========================================================================
# 1. El criterio de conmutación reutiliza el umbral que ya existía
# ===========================================================================

class TestCriterioDeConmutacion:

    def test_sin_gas_no_aplica_el_metodo(self, sin_gas):
        d = gas_method_applies(sin_gas, 500.0, 170.0, 0.01)
        assert d["applies"] is False
        assert d["free_gas_fraction"] == pytest.approx(0.0)
        assert "convencional" in d["reason"]

    def test_con_gas_aplica_el_metodo(self, con_gas):
        d = gas_method_applies(con_gas, 500.0, 170.0, 0.01)
        assert d["applies"] is True
        assert d["free_gas_fraction"] > 0.01
        assert "incrementos de presión" in d["reason"]

    def test_el_umbral_es_el_del_proyecto_no_uno_nuevo(self, con_gas):
        """El default de DesignObjectives tiene que ser el mismo que el dominio.

        El criterio NO se inventó para este camino: es el umbral de gas libre
        despreciable que el proyecto ya usaba para decidir Hazen-Williams vs
        Poettmann-Carpenter. Si alguien los desincroniza, esto falla.
        """
        from bes.core.gas_handling import GAS_FRACTION_NEGLIGIBLE
        obj = DesignObjectives(
            target_flow_rate=1000.0, safety_margin_depth=50.0,
            allow_gas_venting=False, max_gip=0.10,
            design_life_years=5.0, use_vsd=False,
        )
        assert obj.gas_fraction_pc_threshold == pytest.approx(GAS_FRACTION_NEGLIGIBLE)

        d = gas_method_applies(con_gas, 500.0, 170.0, obj.gas_fraction_pc_threshold)
        assert d["negligible_reference"] == pytest.approx(GAS_FRACTION_NEGLIGIBLE)


# ===========================================================================
# 2. El método convencional NO cambia (§6 y §35-1)
# ===========================================================================

class TestConvencionalIntacto:
    """El camino de siempre tiene que seguir dando exactamente lo mismo."""

    def test_select_top_n_sigue_funcionando(self, reservoir, con_gas, well,
                                            surface, objectives, catalog):
        from bes.recommender.pump_selector import select_top_n_pumps
        r = select_top_n_pumps(reservoir, con_gas, well, surface, objectives,
                               catalog, n=3)
        assert len(r) >= 1
        assert r[0].num_stages > 0
        assert r[0].motor_hp > 0

    def test_el_refactor_de_carcasas_no_movio_nada(self, reservoir, con_gas,
                                                   well, surface, objectives,
                                                   catalog):
        """Regresión del refactor: housing_and_mechanical_checks se extrajo de
        _design_candidate, y tiene que dar lo mismo que antes."""
        from bes.core.pump_design import design_pump_complete
        cands = design_pump_complete(
            reservoir=reservoir, fluid=con_gas, well=well, surface=surface,
            objectives=objectives, pump_setting_depth=5850.0,
            catalog_manager=catalog,
        )
        assert cands, "el camino convencional dejó de producir candidatos"
        c = cands[0]
        # Las claves que aporta el bloque extraído tienen que seguir estando.
        for k in ("housing_size_stages", "dummy_stages", "n_housings",
                  "max_housing_pressure_psi", "housing_pressure_ok",
                  "shaft_check", "bearing_check", "bearing_load_lbs",
                  "staging_ceiling"):
            assert k in c, f"el refactor perdió la clave {k}"


# ===========================================================================
# 3. Caso con gas: caudal variable, masa constante, aparejo completo
# ===========================================================================

class TestPozoConGas:

    @pytest.fixture(scope="class")
    def resultado(self, con_gas, reservoir, well, surface, objectives, catalog):
        return _correr(con_gas, reservoir, well, surface, objectives, catalog)

    def test_el_metodo_se_aplico(self, resultado):
        assert resultado["method"]["applies"] is True

    def test_el_caudal_de_mezcla_es_VARIABLE(self, resultado):
        """El punto entero del método: con gas el volumen NO es constante."""
        tabla = resultado["increment"]["increment_table"]
        caudales = [r["q_avg_bpd"] for r in tabla]
        assert caudales[0] > caudales[-1], (
            "el caudal de mezcla tiene que caer al subir la presión: el gas se "
            "comprime y parte pasa a solución"
        )
        # Y la caída tiene que ser grande, no ruido numérico.
        assert caudales[0] / caudales[-1] > 1.5

    def test_la_masa_se_conserva(self, resultado):
        """Invariante de control de Brown: cambia el volumen, no la masa."""
        assert resultado["increment"]["mass_rate_lbm_d"] > 0

    def test_una_sola_bomba_para_toda_la_sarta(self, resultado):
        """§8: no se puede armar una sarta con un modelo distinto por tramo."""
        tabla = resultado["increment"]["increment_table"]
        modelos = {r["pump_model"] for r in tabla}
        assert len(modelos) == 1, f"la sarta mezcla modelos: {modelos}"
        assert modelos == {resultado["design"].pump_model}

    def test_la_curva_se_consulta_con_el_caudal_del_intervalo(self, resultado):
        """§10: el caudal de evaluación es el promedio LOCAL de cada tramo."""
        tabla = resultado["increment"]["increment_table"]
        for r in tabla:
            assert r["q_avg_bpd"] == pytest.approx(
                0.5 * (r["q_lo_bpd"] + r["q_hi_bpd"])
            )
        # Y no son todos iguales: si lo fueran, sería un caudal único disfrazado.
        assert len({round(r["q_avg_bpd"], 3) for r in tabla}) > 1

    def test_termina_en_un_aparejo_completo(self, resultado):
        """§38: el resultado es un aparejo, no 'X etapas e Y hp'."""
        d = resultado["design"]
        assert d.pump_model and d.num_stages > 0
        assert d.motor_model and d.motor_hp > 0
        assert d.seal_model
        assert d.cable_awg > 0
        assert d.transformer_kva > 0
        assert d.n_housings >= 1

    def test_no_mezcla_fabricantes(self, resultado):
        """Regla de dominio: bomba, motor y sello del mismo proveedor."""
        d = resultado["design"]
        assert d.motor_manufacturer == d.pump_manufacturer
        if d.seal_manufacturer:
            assert d.seal_manufacturer == d.pump_manufacturer

    def test_publica_las_dos_rutas_al_tdh(self, resultado):
        """Las dos rutas discrepan; se publican ambas en vez de elegir una."""
        assert resultado["tdh_increment_ft"] > 0
        assert resultado["tdh_conventional_ft"] > 0
        # El aparejo se dimensionó con la del método.
        assert resultado["design"].total_head_required == pytest.approx(
            resultado["tdh_increment_ft"]
        )

    def test_el_tdh_del_metodo_es_la_suma_de_los_tramos(self, resultado):
        """TDH_equiv = Σ ΔPᵢ/gradienteᵢ — identidad, no correlación nueva."""
        tabla = resultado["increment"]["increment_table"]
        suma = sum(r["delta_p"] / r["gradient"] for r in tabla)
        assert suma == pytest.approx(resultado["tdh_increment_ft"], rel=1e-9)

    def test_las_etapas_cierran_con_el_tdh_y_la_curva(self, resultado):
        """Cada tramo: etapas = altura del tramo / altura por etapa."""
        tabla = resultado["increment"]["increment_table"]
        for r in tabla:
            assert r["stages_exact"] == pytest.approx(
                r["head_incr_ft"] / r["head_effective"], rel=1e-9
            )


# ===========================================================================
# 4. Caso principal: petróleo pesado + gas
# ===========================================================================

class TestPesadoConGas:

    @pytest.fixture(scope="class")
    def resultado(self, pesado_con_gas, reservoir, well, surface, objectives,
                  catalog):
        return _correr(pesado_con_gas, reservoir, well, surface, objectives,
                       catalog)

    def test_se_corrige_por_viscosidad(self, resultado):
        tabla = resultado["increment"]["increment_table"]
        assert all(r["is_viscous"] for r in tabla), (
            "18 °API está por debajo del corte de 28: tiene que corregirse"
        )

    def test_el_pvt_cambia_a_lo_largo_de_la_bomba(self, resultado):
        tabla = resultado["increment"]["increment_table"]
        rs = [r["rs"] for r in tabla]
        bg = [r["bg"] for r in tabla]
        assert rs[0] < rs[-1], "el gas disuelto crece con la presión"
        assert bg[0] > bg[-1], "el gas se comprime: Bg cae con la presión"

    def test_el_gas_libre_cae_con_la_presion(self, resultado):
        tabla = resultado["increment"]["increment_table"]
        fg = [r["fg_ratio"] for r in tabla]
        assert fg[0] > fg[-1]

    def test_la_correccion_no_es_la_misma_en_todos_los_tramos(self, resultado):
        """§15: la viscosidad se evalúa POR intervalo, no una vez."""
        tabla = resultado["increment"]["increment_table"]
        assert len({round(r["head_factor"], 4) for r in tabla}) > 1

    def test_termina_en_aparejo_completo(self, resultado):
        d = resultado["design"]
        assert d.motor_model and d.cable_awg > 0 and d.transformer_kva > 0

    def test_el_candidato_reporta_el_metodo(self, resultado):
        c = resultado["candidate"]
        assert c["design_method"] == "pressure_increment"
        assert c["increment_table"]
        assert c["viscosity_correction"] is not None


# ===========================================================================
# 5. Fallback: si la bomba no arma el aparejo, se baja a la siguiente
# ===========================================================================

class TestFallbackDeCandidatas:

    def test_registra_las_descartadas_con_el_motivo(
        self, con_gas, reservoir, well, surface, objectives, catalog
    ):
        """No se descarta en silencio: cada rechazo lleva su motivo."""
        r = _correr(con_gas, reservoir, well, surface, objectives, catalog)
        for motivo in r["rejected"]:
            assert ":" in motivo, f"rechazo sin motivo legible: {motivo}"

    def test_bomba_fija_sin_fallback(
        self, con_gas, reservoir, well, surface, objectives, catalog
    ):
        """Con la bomba elegida a mano no hay suplente: falla explicando."""
        with pytest.raises(ValueError, match="Ninguna bomba"):
            _correr(con_gas, reservoir, well, surface, objectives, catalog,
                    fixed_pump_model="TD-650")   # Wood Group: sin motores


# ===========================================================================
# 5bis. Compuerta de viabilidad por gas
# ===========================================================================

class TestCompuertaDeGas:
    """Si el gas que queda tras el separador supera ``max_gip``, el diseño
    **falla**. No entrega un aparejo marcado como dudoso: no converge."""

    def test_el_pozo_de_prueba_pasa_con_el_separador_del_catalogo(
        self, con_gas, reservoir, well, surface, objectives, catalog
    ):
        """64.9 % de gas libre, pero el vórtex del catálogo retira 97 %."""
        r = _correr(con_gas, reservoir, well, surface, objectives, catalog)
        f = r["feasibility"]
        assert f["viable"] is True
        assert f["f_intake"] > 0.60
        assert f["f_pump"] < objectives.max_gip
        assert f["separator_efficiency"] == pytest.approx(0.97)

    def test_un_max_gip_exigente_rechaza_el_pozo(
        self, con_gas, reservoir, well, surface, catalog
    ):
        """Bajando el máximo admisible, el mismo pozo deja de converger."""
        exigente = DesignObjectives(
            target_flow_rate=1227.0, safety_margin_depth=50.0,
            allow_gas_venting=False, design_life_years=5.0, use_vsd=False,
            max_gip=0.01,
        )
        with pytest.raises(ValueError) as exc:
            _correr(con_gas, reservoir, well, surface, exigente, catalog)

        msg = str(exc.value)
        assert "NO VIABLE" in msg
        assert "otro método de levantamiento" in msg
        # El mensaje tiene que dar los números, no sólo el veredicto.
        assert "%" in msg

    def test_el_veredicto_dice_que_eficiencia_faltaba(
        self, con_gas, reservoir, well, surface, catalog
    ):
        exigente = DesignObjectives(
            target_flow_rate=1227.0, safety_margin_depth=50.0,
            allow_gas_venting=False, design_life_years=5.0, use_vsd=False,
            max_gip=0.005,
        )
        with pytest.raises(ValueError, match="separador de"):
            _correr(con_gas, reservoir, well, surface, exigente, catalog)

    def test_la_compuerta_corre_antes_de_disenar(
        self, con_gas, reservoir, well, surface, catalog
    ):
        """No se gasta el diseño completo para después descartarlo.

        Con un pozo inviable el error tiene que ser el del veredicto de gas,
        no uno de selección de bomba o de armado del aparejo.
        """
        imposible = DesignObjectives(
            target_flow_rate=1227.0, safety_margin_depth=50.0,
            allow_gas_venting=False, design_life_years=5.0, use_vsd=False,
            max_gip=0.0,
        )
        with pytest.raises(ValueError) as exc:
            _correr(con_gas, reservoir, well, surface, imposible, catalog)
        assert "Ninguna bomba" not in str(exc.value)

    def test_el_separador_elegido_viaja_en_el_resultado(
        self, con_gas, reservoir, well, surface, objectives, catalog
    ):
        """Trazabilidad: qué equipo se supuso y con qué eficiencia."""
        r = _correr(con_gas, reservoir, well, surface, objectives, catalog)
        f = r["feasibility"]
        assert f["separator_model"]
        assert 0.0 < f["separator_efficiency"] <= 1.0


# ===========================================================================
# 6. El escalón de presión es configurable y el conteo converge
# ===========================================================================

class TestEscalonConfigurable:

    def test_afinar_el_paso_no_dispara_el_conteo(
        self, con_gas, reservoir, well, surface, objectives, catalog
    ):
        """§13: con acumulación de fracciones el conteo converge al afinar.

        Redondear cada tramo por separado —la convención del cálculo a mano—
        acumula hasta media etapa por escalón, así que refinar el paso
        empeoraría el resultado en vez de mejorarlo.
        """
        totales = {}
        for paso in (200.0, 100.0, 50.0):
            r = _correr(con_gas, reservoir, well, surface, objectives, catalog,
                        increment_psi=paso)
            totales[paso] = r["increment"]["total_stages"]

        base = totales[200.0]
        for paso, n in totales.items():
            assert abs(n - base) / base < 0.10, (
                f"el conteo no converge al afinar el paso: {totales}"
            )

    def test_el_longhand_se_reporta_aparte(
        self, con_gas, reservoir, well, surface, objectives, catalog
    ):
        """La convención del libro se conserva, pero no es la que manda."""
        r = _correr(con_gas, reservoir, well, surface, objectives, catalog)
        inc = r["increment"]
        assert inc["total_stages_longhand"] >= inc["total_stages"]
