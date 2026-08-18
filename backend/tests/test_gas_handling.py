"""
Tests for ESP gas handling — Phase 8.
Validates against Kermit Brown, Vol. 2b, Sections 4.53102–4.53103.

Book examples used:
  Example 3A (pág 17-20):
      Well 7 000 ft, Pwf=500 psi, Pwh=200 psi, GOR=500 scf/STB,
      γg=0.65, γw=1.07, °API=35, qL=500 STB/d, 50 % water,
      T=160 °F (reservoir), 100 % GIP.
      Expected: ~209 stages (±40), ~27 HP (±10).
"""
from __future__ import annotations

import copy
import math

import pytest
from pathlib import Path

from bes.catalogs.loader import CatalogManager
from bes.core.models import (
    DesignObjectives,
    DriveMechanism,
    Fluid,
    IPRMethod,
    Reservoir,
    WellGeometry,
)
from bes.core.gas_handling import (
    check_gas_lock_risk,
    fraction_to_ratio,
    ratio_to_fraction,
    complete_gas_design,
    gas_ingestion_percentage,
    pressure_increment_design,
    pump_deterioration_factor,
    recommend_gas_separator,
)



# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def manager() -> CatalogManager:
    return CatalogManager()


@pytest.fixture(scope="module")
def reservoir_3a() -> Reservoir:
    """Brown Example 3A reservoir."""
    return Reservoir(
        static_pressure=2000.0,
        bubble_point=2300.0,
        productivity_index=0.5,
        ipr_method=IPRMethod.VOGEL,
        reservoir_temp=160.0,
        drive_mechanism=DriveMechanism.SOLUTION_GAS,
    )


@pytest.fixture(scope="module")
def fluid_3a() -> Fluid:
    """Brown Example 3A fluid — 35°API, GOR=500, γg=0.65, 50 % WC."""
    return Fluid(
        oil_api=35.0,
        water_cut=0.50,
        gor=500.0,
        gas_sg=0.65,
        water_sg=1.07,
        oil_viscosity_dead=5.0,
        viscosity_temp_ref=100.0,
        bubble_point_pressure=2300.0,
        h2s_content=0.0,
        co2_content=0.0,
        sand_production=False,
    )


@pytest.fixture(scope="module")
def well_7in() -> WellGeometry:
    """7″ 23 lb/ft casing — matches Brown 3A scenario."""
    return WellGeometry(
        total_depth=7000.0,
        casing_od=7.0,
        casing_weight=23.0,
        casing_id=6.366,
        tubing_od=2.875,
        tubing_id=2.441,
        perforations_top=6600.0,
        perforations_bottom=6900.0,
        deviation_max=0.0,
        wellhead_temp=90.0,
    )


# ---------------------------------------------------------------------------
# 1. gas_ingestion_percentage
# ---------------------------------------------------------------------------

class TestGasIngestionPercentage:

    def test_no_venting_full_ingestion(self):
        assert gas_ingestion_percentage(100.0, 0.0) == pytest.approx(1.0)

    def test_half_vented(self):
        assert gas_ingestion_percentage(100.0, 50.0) == pytest.approx(0.5)

    def test_all_vented(self):
        assert gas_ingestion_percentage(100.0, 100.0) == pytest.approx(0.0)

    def test_zero_free_gas_returns_zero(self):
        assert gas_ingestion_percentage(0.0, 0.0) == pytest.approx(0.0)

    def test_separator_reduces_gip(self):
        gip_no_sep = gas_ingestion_percentage(100.0, 0.0, separator_efficiency=0.0)
        gip_with_sep = gas_ingestion_percentage(100.0, 0.0, separator_efficiency=0.9)
        assert gip_with_sep < gip_no_sep
        assert gip_with_sep == pytest.approx(0.10, rel=1e-6)

    def test_separator_and_venting_combined(self):
        # 50 % vented, then separator removes 80 % of rest → GIP = 0.5 * 0.2 = 0.1
        gip = gas_ingestion_percentage(100.0, 50.0, separator_efficiency=0.80)
        assert gip == pytest.approx(0.10, rel=1e-6)

    def test_clamped_to_zero(self):
        # More vented than available → clamp to 0
        assert gas_ingestion_percentage(100.0, 200.0) == pytest.approx(0.0)

    def test_clamped_to_one(self):
        # Negative venting makes no sense; clamp to 1
        assert gas_ingestion_percentage(100.0, -10.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 2. check_gas_lock_risk
# ---------------------------------------------------------------------------

class TestCheckGasLockRisk:
    """Los cuatro umbrales de Brown §4.53102 y Takács.

    OJO con las dos magnitudes: la función recibe la FRACCIÓN del volumen total
    (lo que calcula free_gas_fraction_at_intake) y convierte internamente a
    RELACIÓN gas/líquido, que es como la bibliografía expresa la degradación
    (r > 0.1) y el bloqueo (r ≥ 1.0). Una relación de 1.0 es una fracción de
    0.50, no de 1.0: confundirlas corre los umbrales a la mitad.
    """

    def test_gas_despreciable(self):
        """f ≤ 1 %: vale el diseño monofásico con gradiente constante."""
        assert check_gas_lock_risk(0.005)["risk"] == "none"

    def test_apenas_sobre_el_uno_por_ciento_pide_multifasico(self):
        """f > 1 %: hay que calcular la pérdida de carga como multifásica."""
        r = check_gas_lock_risk(0.03)
        assert r["risk"] == "low"
        assert not r["needs_separator"]
        assert "multifásico" in r["recommendation"]

    def test_sobre_cinco_por_ciento_exige_separador(self):
        """f > 5 %: separador o manejador de gas obligatorio."""
        r = check_gas_lock_risk(0.08)
        assert r["risk"] == "medium"
        assert r["needs_separator"]

    def test_degradacion_arranca_en_relacion_0p10(self):
        """La bomba pierde altura cuando r > 0.1, que es f > 0.0909."""
        assert not check_gas_lock_risk(0.09)["pump_degrades"]
        assert check_gas_lock_risk(0.10)["pump_degrades"]

    def test_bloqueo_en_relacion_1p0_o_sea_fraccion_0p50(self):
        """Gas lock a r ≥ 1.0. En fracción eso es 0.50, NO 1.0."""
        assert not check_gas_lock_risk(0.49)["gas_locked"]
        bloqueado = check_gas_lock_risk(0.50)
        assert bloqueado["gas_locked"]
        assert bloqueado["risk"] == "high"

    def test_convierte_bien_entre_fraccion_y_relacion(self):
        for f in (0.0, 0.01, 0.0909, 0.25, 0.50, 0.75):
            assert ratio_to_fraction(fraction_to_ratio(f)) == pytest.approx(f, abs=1e-9)

    def test_relacion_reportada_es_coherente(self):
        r = check_gas_lock_risk(0.20)
        assert r["free_gas_ratio"] == pytest.approx(0.20 / 0.80)

    def test_devuelve_las_claves_esperadas(self):
        r = check_gas_lock_risk(0.20)
        assert {"risk", "free_gas_fraction", "free_gas_ratio", "needs_separator",
                "pump_degrades", "gas_locked", "recommendation"} <= set(r)

    def test_cero_es_despreciable(self):
        assert check_gas_lock_risk(0.0)["risk"] == "none"

    def test_medium_recommendation_mentions_separator(self):
        assert "eparador" in check_gas_lock_risk(0.20)["recommendation"]


# ---------------------------------------------------------------------------
# 3. pump_deterioration_factor
# ---------------------------------------------------------------------------

class TestPumpDeteriorationFactor:
    """Degradación entre r = 0.1 y r = 1.0 (fracción 0.0909 a 0.50)."""

    def test_sin_gas_no_degrada(self):
        assert pump_deterioration_factor(0.0) == pytest.approx(1.0)

    def test_por_debajo_del_inicio_no_degrada(self):
        # r = 0.1 corresponde a f = 0.0909
        assert pump_deterioration_factor(0.05) == pytest.approx(1.0)
        assert pump_deterioration_factor(0.0909) == pytest.approx(1.0, abs=1e-3)

    def test_punto_medio(self):
        # r = 0.55 (mitad entre 0.1 y 1.0) -> f = 0.3548, factor = 0.5
        f = ratio_to_fraction(0.55)
        assert pump_deterioration_factor(f) == pytest.approx(0.5, abs=1e-6)

    def test_bloqueo_total_no_entrega_altura(self):
        # r = 1.0 -> f = 0.50
        assert pump_deterioration_factor(0.50) == pytest.approx(0.0)
        assert pump_deterioration_factor(0.80) == pytest.approx(0.0)

    def test_monotonamente_decreciente(self):
        vals = [pump_deterioration_factor(f)
                for f in (0.0, 0.05, 0.10, 0.20, 0.35, 0.50, 0.70)]
        for a, b in zip(vals, vals[1:]):
            assert a >= b

    def test_negativo_se_acota(self):
        assert pump_deterioration_factor(-0.1) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 4. pressure_increment_design — unit tests
# ---------------------------------------------------------------------------

class TestPressureIncrementDesign:
    """Validate the increment method physics, not specific pump selections."""

    @pytest.fixture(scope="class")
    def base_result(self, manager, reservoir_3a, fluid_3a):
        """Run Example 3A: 500→2300 psi, 500 bpd, 50 % WC, GIP=1."""
        return pressure_increment_design(
            reservoir=reservoir_3a,
            fluid=fluid_3a,
            p_intake=500.0,
            p_discharge=2300.0,
            target_rate=500.0,
            catalog_manager=manager,
            gip=1.0,
            water_cut=0.5,
            increment_psi=200.0,
        )

    def test_returns_required_keys(self, base_result):
        for k in ("total_stages", "total_hp", "pump_combination", "increment_table"):
            assert k in base_result

    def test_stages_positive(self, base_result):
        assert base_result["total_stages"] > 0

    def test_hp_positive(self, base_result):
        assert base_result["total_hp"] > 0.0

    def test_correct_number_of_increments(self, base_result):
        # 500→2300 = 1800 psi / 200 = 9 increments
        assert base_result["n_increments"] == 9

    def test_stages_sum_matches(self, base_result):
        """El total sale de sumar las etapas EXACTAS y redondear una sola vez.

        La columna ``stages`` de la tabla es cada incremento redondeado hacia
        arriba —la convención del cálculo a mano del libro— y su suma se reporta
        aparte como ``total_stages_longhand``. Sumar esa columna para obtener el
        total era justamente el error: acumulaba hasta media etapa por
        incremento y hacía que el resultado empeorara al afinar el paso.
        """
        exacto = sum(row["stages_exact"] for row in base_result["increment_table"])
        # total_stages_exact viene redondeado a 2 decimales para el reporte
        assert exacto == pytest.approx(base_result["total_stages_exact"], abs=0.01)
        assert base_result["total_stages"] == math.ceil(base_result["total_stages_exact"])

        a_mano = sum(row["stages"] for row in base_result["increment_table"])
        assert a_mano == base_result["total_stages_longhand"]
        assert a_mano >= base_result["total_stages"]

    def test_converge_al_afinar_el_paso(self, manager, reservoir_3a, fluid_3a):
        """El conteo se estabiliza cuando el paso se achica.

        Regresión del bug de redondeo: antes daba 204 etapas con paso de 200 psi
        y 428 con paso de 2 psi para el mismo pozo, o sea que refinar el cálculo
        lo empeoraba. La solución por computadora del libro (§4.53105) resuelve
        etapa por etapa, así que el método tiene que soportar pasos finos.
        """
        totales = [
            pressure_increment_design(
                reservoir_3a, fluid_3a, 500.0, 1300.0, 500.0, manager,
                gip=1.0, water_cut=0.5, increment_psi=paso, fixed_pump_model="D-40",
            )["total_stages"]
            for paso in (50.0, 20.0, 10.0, 5.0, 2.0)
        ]
        assert max(totales) - min(totales) <= 2, (
            f"El conteo no converge al afinar el paso: {totales}"
        )

    def test_hp_sum_matches(self, base_result):
        table_hp = sum(row["hp"] for row in base_result["increment_table"])
        assert table_hp == pytest.approx(base_result["total_hp"], rel=0.01)

    # --- Book Example 3A approximate values ---

    # NOTA sobre esta fixture: recorre 500→2300 psi (ΔP 1800) con selección
    # automática. NO es un caso impreso del libro — el #3B caso 1 es 500→1300
    # psi (ΔP 800) con una D-40 fija. Comparar el HP de esta corrida contra los
    # 27 HP del #3B era comparar un pozo con otro; la validación contra valores
    # impresos vive en TestExample3ABrownPrinted, más abajo.

    def test_example_3a_stages_orden_de_magnitud(self, base_result):
        """Centenares de etapas para 1800 psi de salto: el orden correcto."""
        assert 150 <= base_result["total_stages"] <= 400

    def test_hp_consistente_con_etapas_y_curva(self, base_result):
        """El HP total tiene que salir de las etapas, la curva y el SG.

        Chequeo interno, no contra el libro: cada tramo aporta
        ``etapas × hp/etapa × SG_mezcla``, así que el total no puede despegarse
        de recomponerlo desde la tabla. Antes esto se validaba contra los 27 HP
        del #3B, que son de otro pozo y otro salto de presión.
        """
        recompuesto = sum(
            row["stages_exact"] * row["hp_per_stage_w"] * row["sg_mix"]
            for row in base_result["increment_table"]
        )
        assert recompuesto == pytest.approx(base_result["total_hp"], rel=0.01)
        assert base_result["total_hp"] > 0.0

    # --- Physical monotonicity ---

    def test_v_total_decreases_with_pressure(self, base_result):
        """At higher pressures more gas dissolves → smaller total volume."""
        vols = [row["v_total"] for row in base_result["increment_table"]]
        # Not strictly monotone (temperature constant, Bo increases) but
        # gas dominates at low P so v_total[0] > v_total[-1]
        assert vols[0] > vols[-1]

    def test_gradient_increases_with_pressure(self, base_result):
        """Mixture gets denser as gas dissolves at higher P."""
        grads = [row["gradient"] for row in base_result["increment_table"]]
        assert grads[0] < grads[-1]

    def test_q_res_decreases_with_pressure(self, base_result):
        """Less gas expansion at higher pressures → lower reservoir flow."""
        flows = [row["q_res_bpd"] for row in base_result["increment_table"]]
        assert flows[0] > flows[-1]

    def test_stages_decrease_with_pressure(self, base_result):
        """Denser fluid at high P → more psi/stage → fewer stages per increment."""
        stages = [row["stages"] for row in base_result["increment_table"]]
        assert stages[0] > stages[-1]

    # --- GIP sensitivity ---

    def test_higher_gip_more_stages(self, manager, reservoir_3a, fluid_3a):
        """More gas in pump → lighter mixture → more stages needed.

        This invariant only holds for a *fixed* pump: ``pressure_increment_design``
        re-selects the pump per increment by reservoir-condition rate, so with a
        multi-pump catalog the gassier (higher-volume) case can land on a
        higher-rate, higher-head pump and need fewer stages — masking the effect.
        We pin the catalog to a single pump (D-20) to test the underlying physics.
        """
        single = copy.copy(manager)
        single._pumps = [p for p in manager.get_all_pumps() if p.model == "D-20"]

        r_100 = pressure_increment_design(
            reservoir_3a, fluid_3a, 500.0, 2300.0, 500.0,
            single, gip=1.0, water_cut=0.5,
        )
        r_0 = pressure_increment_design(
            reservoir_3a, fluid_3a, 500.0, 2300.0, 500.0,
            single, gip=0.0, water_cut=0.5,
        )
        assert r_100["total_stages"] > r_0["total_stages"]

    def test_higher_gip_higher_hp(self, manager, reservoir_3a, fluid_3a):
        """More gas in pump → larger reservoir volume + more stages → higher total HP."""
        r_100 = pressure_increment_design(
            reservoir_3a, fluid_3a, 500.0, 2300.0, 500.0,
            manager, gip=1.0, water_cut=0.5,
        )
        r_0 = pressure_increment_design(
            reservoir_3a, fluid_3a, 500.0, 2300.0, 500.0,
            manager, gip=0.0, water_cut=0.5,
        )
        assert r_100["total_hp"] > r_0["total_hp"]

    def test_higher_water_cut_fewer_stages(self, manager, reservoir_3a):
        """More water (denser) → more gradient → fewer stages per increment."""
        fluid_0wc = Fluid(
            oil_api=35.0, water_cut=0.0, gor=500.0,
            gas_sg=0.65, water_sg=1.07, oil_viscosity_dead=5.0,
            viscosity_temp_ref=100.0, bubble_point_pressure=2300.0,
            h2s_content=0.0, co2_content=0.0, sand_production=False,
        )
        fluid_80wc = Fluid(
            oil_api=35.0, water_cut=0.80, gor=500.0,
            gas_sg=0.65, water_sg=1.07, oil_viscosity_dead=5.0,
            viscosity_temp_ref=100.0, bubble_point_pressure=2300.0,
            h2s_content=0.0, co2_content=0.0, sand_production=False,
        )
        r0 = pressure_increment_design(
            reservoir_3a, fluid_0wc, 500.0, 2300.0, 500.0,
            manager, gip=1.0, water_cut=0.0,
        )
        r80 = pressure_increment_design(
            reservoir_3a, fluid_80wc, 500.0, 2300.0, 500.0,
            manager, gip=1.0, water_cut=0.80,
        )
        assert r0["total_stages"] > r80["total_stages"]

    def test_invalid_pressures_raises(self, manager, reservoir_3a, fluid_3a):
        with pytest.raises(ValueError):
            pressure_increment_design(
                reservoir_3a, fluid_3a, 2300.0, 500.0, 500.0, manager
            )

    def test_pump_combination_nonempty(self, base_result):
        assert len(base_result["pump_combination"]) > 0

    def test_increment_table_has_expected_keys(self, base_result):
        row = base_result["increment_table"][0]
        for k in ("p_lo", "p_hi", "p_mid", "rs", "bo", "bg",
                  "v_total", "rho_mix", "gradient", "q_res_bpd",
                  "psi_per_stage", "stages", "hp"):
            assert k in row

    def test_rs_below_gor_everywhere(self, base_result, fluid_3a):
        for row in base_result["increment_table"]:
            assert row["rs"] <= fluid_3a.gor + 1e-6

    def test_gradient_in_physical_range(self, base_result):
        for row in base_result["increment_table"]:
            # Gradient between ~0.10 psi/ft (very gassy) and 0.50 psi/ft (dense brine)
            assert 0.05 <= row["gradient"] <= 0.55

    # --- Custom increment size ---

    def test_custom_increment_100psi(self, manager, reservoir_3a, fluid_3a):
        # Fija la bomba (fixed_pump_model) para aislar el método de incrementos:
        # sin fijarla, el diseño re-selecciona una bomba por incremento según el
        # caudal in situ, y al enriquecer el catálogo la selección cambia entre
        # 100/200 psi (más incrementos → más bins de caudal → distinta bomba),
        # rompiendo la comparación aunque el método sea correcto. Con bomba fija,
        # 100 vs 200 psi convergen dentro del 10 % (verificado).
        r200 = pressure_increment_design(
            reservoir_3a, fluid_3a, 500.0, 2300.0, 500.0, manager,
            gip=1.0, water_cut=0.5, increment_psi=200.0, fixed_pump_model="D-40",
        )
        r100 = pressure_increment_design(
            reservoir_3a, fluid_3a, 500.0, 2300.0, 500.0, manager,
            gip=1.0, water_cut=0.5, increment_psi=100.0, fixed_pump_model="D-40",
        )
        # Finer steps → similar total but more rows
        assert r100["n_increments"] == 18
        assert r100["total_stages"] == pytest.approx(r200["total_stages"], rel=0.10)


# ---------------------------------------------------------------------------
# 4bis. VALIDACIÓN contra los valores IMPRESOS del Ejemplo #3A
# ---------------------------------------------------------------------------

class TestExample3ABrownPrinted:
    """Contraste directo contra la página impresa de Brown Vol. 2b §4.53103.

    El ejemplo #3A resuelve a mano el incremento 500 → 700 psi de un pozo de
    7 000 ft con 500 b/d al 50 % de agua, GOR 500 scf/b, 35 °API, γg 0.65,
    γw 1.07, a 160 °F, bombeando el 100 % del gas. Es el único tramo que el
    libro publica con TODOS los intermedios, así que es el mejor ancla que hay
    para el método de incrementos.

    Los valores están escritos acá adentro a propósito: la validación no puede
    depender de un archivo de datos que se borre.

    ERRATA DEL IMPRESO — el libro publica ``Grad_700 = 0.2474`` y es un error
    de tipeo por ``0.2374``. Tres verificaciones independientes lo confirman:
      1. ρ₇₀₀/144 = 34.185/144 = 0.2374, y ρ₇₀₀ = 34.185 lo imprime el propio
         libro dos renglones antes.
      2. El promedio que el libro imprime, 0.2143, sólo cierra con 0.2374
         ((0.1913 + 0.2374)/2 = 0.21435; con 0.2474 daría 0.21935).
      3. Los 5.36 psi/etapa y las 37.3 etapas impresas salen de 0.2143, no de
         0.2193 (que daría 5.48 psi/etapa y 36.5 etapas).
    Se valida contra 0.2374. Misma política que las erratas ya documentadas de
    Takács en .claude/rules/domain.md: se corrigen y se deja escrito por qué.
    """

    # --- Valores impresos, tal cual salen de la página ---------------------
    P_LO, P_HI, TEMP = 500.0, 700.0, 160.0
    Q_LIQ_SURF = 500.0          # b/d totales (250 petróleo + 250 agua)
    WC = 0.5

    LIBRO = {
        500.0: {
            "rs": 80.0, "bo": 1.08, "free_gas": 420.0, "bg": 0.00577,
            "vol_por_stb_oil": 4.5034, "q_total": 1125.85,
            "rho": 27.55, "gradient": 0.1913,
        },
        700.0: {
            "rs": 120.0, "bo": 1.094, "free_gas": 380.0, "bg": 0.00404,
            "vol_por_stb_oil": 3.6292, "q_total": 907.3,
            "rho": 34.185, "gradient": 0.2374,   # impreso 0.2474 — ver errata
        },
    }
    MASA_POR_STB_OIL = 696.63   # lb  (297.3 petróleo + 374.5 agua + 24.83 gas)
    CAUDAL_MASICO = 174_157.5   # lbm/d
    GRADIENTE_PROMEDIO = 0.2143
    CAUDAL_PROMEDIO = 1017.0    # b/d
    HEAD_POR_ETAPA_D40 = 25.0   # ft/etapa
    PSI_POR_ETAPA = 5.36
    ETAPAS = 38                 # 37.3 redondeado hacia arriba

    @pytest.fixture(scope="class")
    def fluido(self) -> Fluid:
        return Fluid(
            oil_api=35.0, water_cut=0.5, gor=500.0,
            gas_sg=0.65, water_sg=1.07,
            oil_viscosity_dead=5.0, viscosity_temp_ref=100.0,
            bubble_point_pressure=2000.0,
            h2s_content=0.0, co2_content=0.0, sand_production=False,
        )

    @pytest.fixture(scope="class")
    def props(self, fluido) -> dict:
        from bes.core.gas_handling import _mixture_volumes_and_density
        return {
            p: _mixture_volumes_and_density(p, self.TEMP, fluido, self.WC, 1.0)
            for p in (self.P_LO, self.P_HI)
        }

    # --- PVT en cada extremo ----------------------------------------------

    @pytest.mark.parametrize("p", [500.0, 700.0])
    @pytest.mark.parametrize("clave,tol", [
        ("rs", 0.10), ("bo", 0.05), ("bg", 0.05),
    ])
    def test_pvt_en_los_extremos(self, props, p, clave, tol):
        esperado = self.LIBRO[p][clave]
        obtenido = props[p][clave]
        assert obtenido == pytest.approx(esperado, rel=tol), (
            f"{clave}({p:.0f} psi) = {obtenido:.5f} contra {esperado} del libro"
        )

    @pytest.mark.parametrize("p", [500.0, 700.0])
    def test_gas_libre_en_los_extremos(self, props, p):
        """Gas libre = GOR − Rs, y baja al subir la presión."""
        assert props[p]["free_gas_scf"] == pytest.approx(
            self.LIBRO[p]["free_gas"], rel=0.10
        )

    # --- Volumen de mezcla -------------------------------------------------

    @pytest.mark.parametrize("p", [500.0, 700.0])
    def test_volumen_por_stb_de_petroleo(self, props, p):
        """Brown trabaja por STB de PETRÓLEO; la app, por STB de líquido total.

        Vol_libro = Bo + Bw + gas_libre·Bg  (base: 1 STB de petróleo)
        Vol_app   = (1−WC)·Bo + WC·Bw + (1−WC)·gas_libre·Bg
        Con WC = 0.5 la app da exactamente la mitad, así que se divide por
        (1−WC) para comparar contra la página.
        """
        vol_app = props[p]["v_total"] / (1.0 - self.WC)
        assert vol_app == pytest.approx(self.LIBRO[p]["vol_por_stb_oil"], rel=0.05)

    @pytest.mark.parametrize("p", [500.0, 700.0])
    def test_caudal_total_en_los_extremos(self, props, p):
        """1125.85 b/d a 500 psi y 907.3 b/d a 700 psi."""
        q = self.Q_LIQ_SURF * props[p]["v_total"]
        assert q == pytest.approx(self.LIBRO[p]["q_total"], rel=0.05)

    # --- Masa: el invariante de control (§12 del procedimiento) ------------

    def test_masa_por_stb_de_petroleo(self, props):
        """696.63 lb = 297.3 petróleo + 374.5 agua + 24.83 gas."""
        p = self.P_LO
        masa_liq = props[p]["rho_mix"] * props[p]["v_total"] * 5.615
        assert masa_liq / (1.0 - self.WC) == pytest.approx(
            self.MASA_POR_STB_OIL, rel=0.02
        )

    def test_caudal_masico_constante(self, props):
        """La masa NO cambia con la presión aunque el volumen sí (§12).

        Es el control que Brown usa para verificar el método: 174 157.5 lbm/d
        «constant value for each pressure point». Si esto se mueve entre
        extremos, el balance está mal planteado.
        """
        masas = {
            p: props[p]["rho_mix"] * props[p]["v_total"] * 5.615 * self.Q_LIQ_SURF
            for p in (self.P_LO, self.P_HI)
        }
        assert masas[self.P_LO] == pytest.approx(masas[self.P_HI], rel=1e-9), (
            f"la masa cambió entre extremos: {masas}"
        )
        assert masas[self.P_LO] == pytest.approx(self.CAUDAL_MASICO, rel=0.02)

    # --- Densidad y gradiente ---------------------------------------------

    @pytest.mark.parametrize("p", [500.0, 700.0])
    def test_densidad_y_gradiente(self, props, p):
        assert props[p]["rho_mix"] == pytest.approx(self.LIBRO[p]["rho"], rel=0.05)
        assert props[p]["gradient"] == pytest.approx(
            self.LIBRO[p]["gradient"], rel=0.05
        )

    def test_gradiente_es_densidad_sobre_144(self, props):
        """Gradient = ρ/144 — la ecuación, no un ajuste."""
        for p in (self.P_LO, self.P_HI):
            assert props[p]["gradient"] == pytest.approx(
                props[p]["rho_mix"] / 144.0, rel=1e-12
            )

    # --- El promedio del intervalo (§11) -----------------------------------

    def test_gradiente_promedio_del_intervalo(self, props):
        """(0.1913 + 0.2374)/2 = 0.2143 — promedio de EXTREMOS, no punto medio."""
        promedio = 0.5 * (props[self.P_LO]["gradient"] + props[self.P_HI]["gradient"])
        assert promedio == pytest.approx(self.GRADIENTE_PROMEDIO, rel=0.05)

    def test_caudal_promedio_del_intervalo(self, props):
        """(1125.85 + 907.3)/2 = 1017 b/d — el caudal con que se elige la bomba."""
        promedio = 0.5 * sum(
            self.Q_LIQ_SURF * props[p]["v_total"] for p in (self.P_LO, self.P_HI)
        )
        assert promedio == pytest.approx(self.CAUDAL_PROMEDIO, rel=0.05)

    def test_la_convencion_del_libro_es_promediar_extremos(self):
        """El libro promedia los EXTREMOS. Se demuestra con sus propios números.

        Brown publica Vol₅₀₀ = 4.5034 y Vol₇₀₀ = 3.6292 b/STB de petróleo, y
        publica el promedio del intervalo: 1017 b/d. Promediando sus dos
        extremos por 250 STB/d de petróleo se llega exactamente ahí. El libro
        NO publica ninguna propiedad a 600 psi, así que el punto medio no es
        siquiera calculable desde la tabla impresa: la convención es el
        promedio de extremos y no hay ambigüedad.
        """
        q_500 = self.LIBRO[500.0]["vol_por_stb_oil"] * 250.0
        q_700 = self.LIBRO[700.0]["vol_por_stb_oil"] * 250.0
        assert 0.5 * (q_500 + q_700) == pytest.approx(self.CAUDAL_PROMEDIO, abs=1.0)

        grad = 0.5 * (self.LIBRO[500.0]["gradient"] + self.LIBRO[700.0]["gradient"])
        assert grad == pytest.approx(self.GRADIENTE_PROMEDIO, abs=0.0005)

    def test_punto_medio_y_promedio_no_son_lo_mismo(self, fluido):
        """Bg va con 1/P, así que f((P₁+P₂)/2) ≠ (f(P₁)+f(P₂))/2.

        Es la razón de haber cambiado el método: son dos cuentas distintas y
        el libro hace una sola de las dos.

        ATENCIÓN — este test NO afirma que el promedio de extremos quede más
        cerca del número impreso. Con nuestras correlaciones (Standing/DAK, no
        la tabla de Brown) el punto medio da 1010 b/d y el promedio 1029,
        contra los 1017 del libro: el punto medio queda casualmente más cerca.
        Esa cercanía es coincidencia del error de las correlaciones, no un
        argumento de método. Se sigue el procedimiento del libro, no el número
        que mejor pega.
        """
        from bes.core.gas_handling import _mixture_volumes_and_density
        medio = _mixture_volumes_and_density(
            0.5 * (self.P_LO + self.P_HI), self.TEMP, fluido, self.WC, 1.0
        )
        props = {
            p: _mixture_volumes_and_density(p, self.TEMP, fluido, self.WC, 1.0)
            for p in (self.P_LO, self.P_HI)
        }
        promedio = 0.5 * (props[self.P_LO]["v_total"] + props[self.P_HI]["v_total"])
        assert medio["v_total"] != pytest.approx(promedio, rel=1e-6)
        # Ambos caen dentro del 2 % del impreso: la elección es de método.
        for valor in (medio["v_total"], promedio):
            assert self.Q_LIQ_SURF * valor == pytest.approx(
                self.CAUDAL_PROMEDIO, rel=0.02
            )

    # --- Etapas del incremento --------------------------------------------

    def test_psi_por_etapa_y_etapas(self, props):
        """25 ft/etapa × 0.2143 psi/ft = 5.36 psi/etapa → 200/5.36 = 38 etapas."""
        grad = 0.5 * (props[self.P_LO]["gradient"] + props[self.P_HI]["gradient"])
        psi_etapa = self.HEAD_POR_ETAPA_D40 * grad
        assert psi_etapa == pytest.approx(self.PSI_POR_ETAPA, rel=0.05)
        assert math.ceil(200.0 / psi_etapa) == self.ETAPAS

    def test_el_motor_completo_reproduce_el_incremento(self, fluido, manager,
                                                       reservoir_3a):
        """Mismo tramo, pero pasando por ``pressure_increment_design`` entero.

        Cierra el circuito: que los helpers den bien no sirve si el motor no
        los usa. La bomba se fija en D-40 —la que elige Brown en el paso 6— y
        se corre un único incremento de 200 psi.
        """
        r = pressure_increment_design(
            reservoir=reservoir_3a, fluid=fluido,
            p_intake=self.P_LO, p_discharge=self.P_HI,
            target_rate=self.Q_LIQ_SURF, catalog_manager=manager,
            gip=1.0, water_cut=self.WC, increment_psi=200.0,
            fixed_pump_model="D-40",
        )
        assert r["n_increments"] == 1
        fila = r["increment_table"][0]

        assert fila["q_lo_bpd"] == pytest.approx(self.LIBRO[500.0]["q_total"], rel=0.05)
        assert fila["q_hi_bpd"] == pytest.approx(self.LIBRO[700.0]["q_total"], rel=0.05)
        assert fila["q_avg_bpd"] == pytest.approx(self.CAUDAL_PROMEDIO, rel=0.05)
        assert fila["gradient"] == pytest.approx(self.GRADIENTE_PROMEDIO, rel=0.05)
        assert r["mass_rate_lbm_d"] == pytest.approx(self.CAUDAL_MASICO, rel=0.02)
        # 35 °API es crudo liviano: la corrección de Riling no debe tocar nada.
        assert fila["is_viscous"] is False
        assert fila["head_factor"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# 4ter. Viscosidad dentro del método de incrementos (Riling, §4.53112)
# ---------------------------------------------------------------------------

class TestViscosidadPorIntervalo:
    """La corrección de Riling se evalúa intervalo por intervalo.

    El gas en solución cambia con la presión y la viscosidad del crudo vivo con
    él, así que cada tramo de la bomba ve un fluido distinto. Evaluar una sola
    vez en la admisión sobrecorrige los tramos de arriba.
    """

    @pytest.fixture(scope="class")
    def pesado(self) -> Fluid:
        """16 °API — crudo pesado, bien por debajo del corte de 28.

        La viscosidad medida está referida a 100 °F y el pozo está a 160 °F, o
        sea 60 °F de diferencia: queda fuera de tolerancia y no se usa, así que
        la viscosidad la estima Beggs-Robinson. Es a propósito — se está
        probando el camino de correlación.
        """
        return Fluid(
            oil_api=16.0, water_cut=0.0, gor=100.0,
            gas_sg=0.65, water_sg=1.07,
            oil_viscosity_dead=250.0, viscosity_temp_ref=100.0,
            bubble_point_pressure=2000.0,
            h2s_content=0.0, co2_content=0.0, sand_production=False,
        )

    @pytest.fixture(scope="class")
    def liviano(self) -> Fluid:
        """35 °API — el crudo del #3A, liviano."""
        return Fluid(
            oil_api=35.0, water_cut=0.0, gor=100.0,
            gas_sg=0.65, water_sg=1.07,
            oil_viscosity_dead=5.0, viscosity_temp_ref=100.0,
            bubble_point_pressure=2000.0,
            h2s_content=0.0, co2_content=0.0, sand_production=False,
        )

    def _correr(self, fluido, manager, reservoir_3a, **kw):
        return pressure_increment_design(
            reservoir=reservoir_3a, fluid=fluido,
            p_intake=500.0, p_discharge=1300.0, target_rate=800.0,
            catalog_manager=manager, gip=1.0, water_cut=0.0,
            increment_psi=200.0, fixed_pump_model="D-40", **kw
        )

    def test_crudo_liviano_no_se_corrige(self, liviano, manager, reservoir_3a):
        """≥ 28 °API: factores unitarios y la curva de agua tal cual."""
        r = self._correr(liviano, manager, reservoir_3a)
        for fila in r["increment_table"]:
            assert fila["is_viscous"] is False
            assert fila["capacity_factor"] == pytest.approx(100.0)
            assert fila["head_factor"] == pytest.approx(100.0)
            assert fila["hp_factor"] == pytest.approx(100.0)

    def test_crudo_pesado_si_se_corrige(self, pesado, manager, reservoir_3a):
        """< 28 °API: la bomba entrega menos que su curva de agua."""
        r = self._correr(pesado, manager, reservoir_3a)
        assert all(f["is_viscous"] for f in r["increment_table"])
        assert all(f["head_factor"] < 100.0 for f in r["increment_table"])
        assert all(f["hp_factor"] > 100.0 for f in r["increment_table"])

    def test_corregir_pide_mas_etapas_y_mas_potencia(self, pesado, manager,
                                                     reservoir_3a):
        """MISMO fluido, corrección prendida y apagada: ese es el contraste.

        No se compara pesado contra liviano: ahí se mezclan dos efectos que
        van en sentidos opuestos —el crudo pesado es más denso, y más densidad
        da más psi por etapa, o sea MENOS etapas— y el resultado no dice nada
        sobre la viscosidad. Prendiendo y apagando la corrección sobre el mismo
        fluido queda una sola variable.

        Se compara ``total_stages_exact`` y no el entero: el redondeo final se
        come diferencias de menos de una etapa, que es lo que da este caso
        (79.1 contra 79.8, las dos redondean a 80).
        """
        con = self._correr(pesado, manager, reservoir_3a, apply_viscosity=True)
        sin = self._correr(pesado, manager, reservoir_3a, apply_viscosity=False)

        assert con["total_stages_exact"] > sin["total_stages_exact"]
        assert con["total_hp"] > sin["total_hp"]
        assert all(not f["is_viscous"] for f in sin["increment_table"])

    def test_a_menor_temperatura_la_correccion_muerde(self, pesado, manager):
        """A 100 °F el mismo crudo de 16 °API sí mueve el diseño.

        A 160 °F con gas en solución este crudo da 61–73 SSU y la corrección
        vale menos del 1 % — chico pero real. Enfriándolo la viscosidad se
        dispara (es exponencial con T) y la corrección pasa a ser gruesa. Fija
        que el efecto está modelado y no sólo enchufado.
        """
        frio = Reservoir(
            static_pressure=2000.0, bubble_point=2300.0, productivity_index=0.5,
            ipr_method=IPRMethod.VOGEL, reservoir_temp=100.0,
            drive_mechanism=DriveMechanism.SOLUTION_GAS,
        )
        con = self._correr(pesado, manager, frio, apply_viscosity=True)
        sin = self._correr(pesado, manager, frio, apply_viscosity=False)

        assert con["total_stages"] > sin["total_stages"]
        factor = min(f["head_factor"] for f in con["increment_table"])
        assert factor < 95.0, (
            f"a 100 °F la corrección de altura debería ser gruesa, dio {factor:.1f} %"
        )

    def test_la_correccion_cambia_entre_intervalos(self, pesado, manager,
                                                   reservoir_3a):
        """El punto entero: los factores NO son constantes a lo largo de la bomba.

        A mayor presión hay más gas disuelto, el crudo se aliviana y la
        corrección afloja. Si todos los tramos dieran el mismo factor, la
        evaluación por intervalo no estaría haciendo nada.
        """
        r = self._correr(pesado, manager, reservoir_3a)
        factores = [f["head_factor"] for f in r["increment_table"]]
        rs = [f["rs"] for f in r["increment_table"]]

        assert rs[0] < rs[-1], "el gas disuelto tiene que crecer con la presión"
        assert len(set(factores)) > 1, (
            f"los factores de Riling son constantes ({factores[0]}): la "
            f"corrección no se está evaluando por intervalo"
        )
        assert factores[-1] >= factores[0], (
            "con más gas disuelto el crudo es más liviano y la corrección "
            "tiene que aflojar, no apretar"
        )


# ---------------------------------------------------------------------------
# 5. recommend_gas_separator
# ---------------------------------------------------------------------------

class TestRecommendGasSeparator:

    def test_series_400_returns_gasmaster(self):
        result = recommend_gas_separator(0.20, "400")
        assert "GasMaster" in result["separator"]["model"]

    def test_series_513_returns_mvp(self):
        result = recommend_gas_separator(0.20, "513")
        assert "MVP" in result["separator"]["model"]

    def test_unknown_series_returns_generic(self):
        result = recommend_gas_separator(0.20, "999")
        assert result["separator"] is not None
        assert "model" in result["separator"]

    def test_returns_required_keys(self):
        result = recommend_gas_separator(0.15, "400")
        assert "separator" in result
        assert "free_gas_ratio" in result
        assert "notes" in result

    def test_high_gas_note_mentions_recommended(self):
        result = recommend_gas_separator(0.40, "400")
        assert any("recommended" in n.lower() for n in result["notes"])

    def test_low_gas_note_mentions_optional(self):
        result = recommend_gas_separator(0.05, "400")
        assert any("optional" in n.lower() for n in result["notes"])


# ---------------------------------------------------------------------------
# 6. complete_gas_design — integration
# ---------------------------------------------------------------------------

class TestCompleteGasDesign:

    @pytest.fixture(scope="class")
    def design(self, manager, reservoir_3a, fluid_3a, well_7in):
        return complete_gas_design(
            reservoir=reservoir_3a,
            fluid=fluid_3a,
            well=well_7in,
            pump_depth=6500.0,
            target_rate=500.0,
            catalog_manager=manager,
            vent_gas_pct=0.0,
        )

    def test_returns_required_keys(self, design):
        for k in ("pip", "p_discharge", "gip", "free_gas_ratio_at_intake",
                  "gas_lock_risk", "deterioration_factor",
                  "separator_recommendation", "increment_design"):
            assert k in design

    def test_pip_positive(self, design):
        assert design["pip"] > 0.0

    def test_p_discharge_exceeds_pip(self, design):
        assert design["p_discharge"] > design["pip"]

    def test_gip_in_range(self, design):
        assert 0.0 <= design["gip"] <= 1.0

    def test_free_gas_ratio_in_range(self, design):
        assert 0.0 <= design["free_gas_ratio_at_intake"] <= 1.0

    def test_gas_lock_risk_has_risk_key(self, design):
        assert design["gas_lock_risk"]["risk"] in ("low", "medium", "high")

    def test_deterioration_factor_in_range(self, design):
        """El factor va de 1 (sin degradación) a 0 (bloqueo total por gas).

        El cero es un resultado válido, no un error: con relación gas/líquido
        ≥ 1.0 la bomba no entrega altura. Este pozo de prueba tiene 70 % de gas
        libre en la admisión, o sea muy por encima del bloqueo.
        """
        assert 0.0 <= design["deterioration_factor"] <= 1.0
        if design["gas_lock_risk"]["gas_locked"]:
            assert design["deterioration_factor"] == pytest.approx(0.0)

    def test_increment_design_has_stages(self, design):
        assert design["increment_design"]["total_stages"] > 0

    def test_increment_design_has_hp(self, design):
        assert design["increment_design"]["total_hp"] > 0.0

    def test_full_venting_reduces_stages(self, manager, reservoir_3a, fluid_3a, well_7in):
        """Venting all gas → GIP=0 → single-phase liquid → fewer stages.

        Se fija la bomba (fixed_pump_model) para aislar el efecto del gas: sin
        fijarla, el diseño re-selecciona la bomba por caudal in situ y, con un
        catálogo denso, el caso venteado (menor caudal) puede elegir una bomba de
        menor head/etapa que requiere MÁS etapas, invirtiendo la comparación
        aunque físicamente ventear reduzca la carga. Con bomba fija, ventear
        reduce las etapas de forma consistente (verificado: D-40 221→154).
        """
        d_no_vent = complete_gas_design(
            reservoir_3a, fluid_3a, well_7in, 6500.0, 500.0,
            manager, vent_gas_pct=0.0, fixed_pump_model="D-40",
        )
        d_full_vent = complete_gas_design(
            reservoir_3a, fluid_3a, well_7in, 6500.0, 500.0,
            manager, vent_gas_pct=1.0, fixed_pump_model="D-40",
        )
        assert (
            d_no_vent["increment_design"]["total_stages"]
            > d_full_vent["increment_design"]["total_stages"]
        )


# ---------------------------------------------------------------------------
# El umbral de Poettmann-Carpenter lo decide la física, no el usuario
# ---------------------------------------------------------------------------

class TestUmbralAutomaticoDePoettmannCarpenter:
    """El programa elige solo la correlación de fricción.

    El umbral estuvo cargado en tres lugares con dos valores distintos: el
    dominio en 0.01 y tanto el schema de la API como el formulario en 0.10.
    Como el front manda el suyo en cada request, la app venía corriendo con
    el 10 % viejo — o sea que pozos con hasta 10 % de gas libre se diseñaban
    como monofásicos. Estos tests fijan que eso no vuelva a pasar.
    """

    def test_el_default_del_dominio_es_el_umbral_documentado(self):
        import dataclasses
        from bes.core.gas_handling import GAS_FRACTION_NEGLIGIBLE
        from bes.core.models import DesignObjectives

        campo = next(f for f in dataclasses.fields(DesignObjectives)
                     if f.name == "gas_fraction_pc_threshold")
        assert campo.default == GAS_FRACTION_NEGLIGIBLE == 0.01

    def test_la_api_no_pide_el_umbral(self):
        """Si vuelve al request, vuelve a poder pisar el default del dominio."""
        from bes.api.schemas.inputs import ObjectivesSchema
        assert "gas_fraction_pc_threshold" not in ObjectivesSchema.model_fields

    def test_un_objetivo_armado_sin_tocarlo_usa_el_1_por_ciento(self):
        from bes.core.models import DesignObjectives
        o = DesignObjectives(
            target_flow_rate=1500.0, safety_margin_depth=200.0,
            allow_gas_venting=True, max_gip=0.10, design_life_years=5.0,
            use_vsd=False,
        )
        assert o.gas_fraction_pc_threshold == 0.01

    def test_con_10_por_ciento_de_gas_libre_manda_poettmann_carpenter(self):
        """El caso concreto que el umbral viejo dejaba pasar como monofásico."""
        from bes.core.models import DesignObjectives
        o = DesignObjectives(
            target_flow_rate=1500.0, safety_margin_depth=200.0,
            allow_gas_venting=True, max_gip=0.10, design_life_years=5.0,
            use_vsd=False,
        )
        assert 0.10 > o.gas_fraction_pc_threshold, (
            "un pozo con 10 % de gas libre tiene que resolverse con P&C"
        )


class TestTrazaDeFormulasDelMetodo:
    """La traza tiene que decir lo que el programa hizo, no otra cosa.

    Es la razón de ser de `bes.core.formulas`: si la fórmula que se muestra se
    escribiera aparte del cálculo, podría decir una cosa y el código hacer otra.
    """

    @pytest.fixture(scope="class")
    def resultado(self, manager, reservoir_3a, fluid_3a):
        return pressure_increment_design(
            reservoir=reservoir_3a, fluid=fluid_3a,
            p_intake=500.0, p_discharge=2300.0, target_rate=500.0,
            catalog_manager=manager, gip=1.0, water_cut=0.5,
            increment_psi=200.0,
        )

    @pytest.fixture(scope="class")
    def por_clave(self, resultado):
        return {f["key"]: f for f in resultado["formulas"]}

    def test_la_traza_viaja_en_el_resultado(self, resultado):
        assert resultado["formulas"], "el método tiene que publicar sus fórmulas"

    def test_estan_los_pasos_del_metodo(self, por_clave):
        """Los pasos que definen el procedimiento de §4.53103."""
        for k in ("gas_delta_p", "gas_n_incrementos", "gas_q_representativo",
                  "gas_q_avg", "gas_gradient", "gas_psi_etapa",
                  "gas_etapas_tramo", "gas_hp_tramo", "gas_etapas_total",
                  "gas_hp_total", "gas_tdh_equivalente", "gas_masa"):
            assert k in por_clave, f"falta el paso {k}"

    def test_solo_se_traza_un_tramo(self, resultado, por_clave):
        """9 tramos, pero la cadena por tramo se muestra UNA vez: repetirla no
        agrega información y con paso fino serían decenas."""
        assert resultado["n_increments"] == 9
        assert sum(1 for f in resultado["formulas"]
                   if f["key"] == "gas_etapas_tramo") == 1

    def test_el_conteo_de_tramos_lleva_techo(self, por_clave):
        """847/200 da 4.24 y los tramos son 5: la división NO es exacta y el
        último se queda con el resto. Sin el ⌈⌉ la fórmula mostrada mentiría."""
        assert "⌈" in por_clave["gas_n_incrementos"]["expression"]

    def test_las_etapas_del_tramo_cierran_con_su_sustitucion(self, por_clave):
        """El control que hace útil a la traza: rehacer la cuenta a mano con los
        números que muestra tiene que dar el resultado que declara."""
        et = por_clave["gas_etapas_tramo"]
        dp = et["inputs"]["ΔP_tramo"]
        psi = et["inputs"]["Δp_etapa"]
        assert dp / psi == pytest.approx(et["result"], rel=1e-9)

    def test_las_etapas_totales_coinciden_con_el_resultado(self, resultado, por_clave):
        assert por_clave["gas_etapas_total"]["result"] == resultado["total_stages"]

    def test_la_masa_trazada_es_la_calculada(self, resultado, por_clave):
        """La traza se arma con la MISMA variable que entra al resultado."""
        assert por_clave["gas_masa"]["result"] == pytest.approx(
            resultado["mass_rate_lbm_d"], rel=1e-12
        )

    def test_los_totales_no_se_sustituyen_a_si_mismos(self, por_clave):
        """Reemplazar un sumatorio por su propio valor daría «51.8 = 51.8», que
        no informa nada: esos dos pasos quedan en símbolos."""
        for k in ("gas_hp_total", "gas_tdh_equivalente"):
            f = por_clave[k]
            assert f["substitution"] == f["expression"]
            assert "Σ" in f["substitution"]

    def test_toda_formula_cita_su_fuente(self, resultado):
        for f in resultado["formulas"]:
            assert f["reference"], f"{f['key']} no cita de dónde sale"

    def test_el_primer_paso_es_el_salto_de_presion(self, resultado):
        """El orden es el de ejecución: lo primero que hace el método es partir
        el ΔP de la bomba en escalones."""
        assert resultado["formulas"][0]["key"] == "gas_delta_p"
