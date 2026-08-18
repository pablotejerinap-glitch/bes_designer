"""Separador de gas y límite de viabilidad de la BES.

El separador retira una fracción del gas libre antes de la admisión. Si lo que
queda supera el máximo que tolera la bomba, el diseño **no converge** y hay que
evaluar otro método de levantamiento artificial — el diseño falla, no advierte.
"""
from __future__ import annotations

import pytest

from bes.core.gas_handling import (
    GAS_FRACTION_PUMP_LIMIT,
    GAS_RATIO_DEGRADATION_START,
    SEPARATOR_DEFAULT_EFFICIENCY,
    evaluate_gas_feasibility,
    fraction_to_ratio,
    ratio_to_fraction,
    required_separator_efficiency,
    separator_outlet_fraction,
)
from bes.core.models import DesignObjectives


# ===========================================================================
# 1. La cuenta del separador: se escala la RELACIÓN, no la fracción
# ===========================================================================

class TestSeparatorOutletFraction:
    """El error clásico es hacer f' = f·(1−η). El separador saca gas y deja
    el líquido, así que lo proporcional es la relación gas/líquido."""

    def test_sin_separador_no_cambia_nada(self):
        assert separator_outlet_fraction(0.40, 0.0) == pytest.approx(0.40)

    def test_separacion_total_deja_cero(self):
        assert separator_outlet_fraction(0.65, 1.0) == pytest.approx(0.0)

    def test_sin_gas_no_hay_nada_que_separar(self):
        assert separator_outlet_fraction(0.0, 0.75) == pytest.approx(0.0)

    def test_escala_la_relacion_no_la_fraccion(self):
        """f = 50 % con η = 75 % da 20 %, no 12.5 %.

        r = 1.0 → r' = 0.25 → f' = 0.25/1.25 = 0.20
        La cuenta ingenua (0.50 × 0.25 = 0.125) subestima el gas remanente.
        """
        assert separator_outlet_fraction(0.50, 0.75) == pytest.approx(0.20)
        assert separator_outlet_fraction(0.50, 0.75) != pytest.approx(0.125)

    @pytest.mark.parametrize("f,eta,esperado", [
        (0.10, 0.75, 0.02703),
        (0.35, 0.75, 0.11864),
        (0.649, 0.75, 0.31612),
        (0.649, 0.90, 0.15600),
        (0.649, 0.97, 0.05265),
    ])
    def test_valores_de_referencia(self, f, eta, esperado):
        assert separator_outlet_fraction(f, eta) == pytest.approx(esperado, abs=1e-4)

    def test_el_error_de_la_cuenta_ingenua_crece_con_el_gas(self):
        """Con poco gas casi da igual; con mucho, se duplica. Fija por qué la
        distinción importa: es el punto donde un pozo inviable pasaría."""
        def ingenua(f, eta):
            return f * (1 - eta)

        error_bajo = separator_outlet_fraction(0.10, 0.75) / ingenua(0.10, 0.75)
        error_alto = separator_outlet_fraction(0.649, 0.75) / ingenua(0.649, 0.75)
        assert error_bajo < 1.10          # < 10 % de diferencia
        assert error_alto > 1.90          # casi el doble

    def test_es_consistente_con_las_conversiones_del_modulo(self):
        f, eta = 0.42, 0.80
        esperado = ratio_to_fraction(fraction_to_ratio(f) * (1 - eta))
        assert separator_outlet_fraction(f, eta) == pytest.approx(esperado)

    def test_eficiencia_invalida(self):
        with pytest.raises(ValueError, match="efficiency must be in"):
            separator_outlet_fraction(0.5, 1.5)


# ===========================================================================
# 2. Eficiencia necesaria (la inversa)
# ===========================================================================

class TestRequiredEfficiency:

    def test_si_ya_cumple_no_hace_falta_separador(self):
        assert required_separator_efficiency(0.05, 0.10) is None

    def test_despeja_la_eficiencia(self):
        """Ida y vuelta: separar exactamente lo necesario deja el límite."""
        f, limite = 0.649, 0.10
        eta = required_separator_efficiency(f, limite)
        assert separator_outlet_fraction(f, eta) == pytest.approx(limite, abs=1e-9)

    def test_el_pozo_de_prueba_necesita_94_por_ciento(self):
        eta = required_separator_efficiency(0.649, 0.10)
        assert eta == pytest.approx(0.940, abs=0.005)


# ===========================================================================
# 3. Veredicto de viabilidad
# ===========================================================================

class TestEvaluateGasFeasibility:

    def test_poco_gas_es_viable_sin_separador(self):
        r = evaluate_gas_feasibility(0.05, separator_efficiency=None)
        assert r["viable"] is True
        assert r["f_pump"] == pytest.approx(0.05)
        assert "sin separador" in r["verdict"]

    def test_mucho_gas_con_buen_separador_es_viable(self):
        """El vórtex del catálogo (97 %) salva el pozo de prueba."""
        r = evaluate_gas_feasibility(0.649, separator_efficiency=0.97)
        assert r["viable"] is True
        assert r["f_pump"] == pytest.approx(0.0526, abs=1e-3)

    def test_mucho_gas_con_separador_del_75_no_converge(self):
        """El caso que motivó la funcionalidad."""
        r = evaluate_gas_feasibility(
            0.649, separator_efficiency=SEPARATOR_DEFAULT_EFFICIENCY
        )
        assert r["viable"] is False
        assert r["f_pump"] == pytest.approx(0.316, abs=1e-3)
        assert "NO VIABLE" in r["verdict"]
        assert "otro método de levantamiento" in r["verdict"]

    def test_el_veredicto_dice_cuanta_eficiencia_faltaba(self):
        r = evaluate_gas_feasibility(0.649, separator_efficiency=0.75)
        assert r["required_efficiency"] == pytest.approx(0.940, abs=0.005)
        assert "94" in r["verdict"]

    def test_avisa_cuando_ningun_separador_alcanza(self):
        """Con gas altísimo ni el 100 % sirve: el líquido restante no alcanza."""
        r = evaluate_gas_feasibility(0.999, separator_efficiency=0.97)
        assert r["viable"] is False
        assert r["required_efficiency"] > 0.99

    def test_el_venteo_se_aplica_antes_que_el_separador(self):
        """Dos etapas en cadena, ambas sobre la relación."""
        f = 0.649
        r = evaluate_gas_feasibility(f, separator_efficiency=0.75,
                                     vent_fraction=0.50)
        esperado = separator_outlet_fraction(
            separator_outlet_fraction(f, 0.50), 0.75
        )
        assert r["f_after_vent"] == pytest.approx(separator_outlet_fraction(f, 0.50))
        assert r["f_pump"] == pytest.approx(esperado)

        # Las dos etapas se componen multiplicando RELACIONES:
        # r_final = r₀ · (1−0.50) · (1−0.75) = 1.849 · 0.125 = 0.231 → f = 18.8 %
        assert r["f_pump"] == pytest.approx(0.1878, abs=1e-3)

        # Sigue sin alcanzar: ventear la mitad más separar el 75 % deja 18.8 %,
        # todavía por encima del 10 %. Es la magnitud del problema — el gas de
        # este pozo no se arregla acumulando etapas de separación modestas.
        assert r["viable"] is False

        sin_venteo = evaluate_gas_feasibility(f, separator_efficiency=0.75)
        assert r["f_pump"] < sin_venteo["f_pump"], "el venteo tiene que ayudar"

    def test_el_sobre_de_diseno_del_separador_del_75(self):
        """Con 75 % de separación, el máximo tolerable en la admisión es 30.8 %."""
        limite = evaluate_gas_feasibility(0.308, separator_efficiency=0.75)
        assert limite["f_pump"] == pytest.approx(0.10, abs=0.002)
        assert evaluate_gas_feasibility(0.30, separator_efficiency=0.75)["viable"]
        assert not evaluate_gas_feasibility(0.32, separator_efficiency=0.75)["viable"]

    def test_max_gip_invalido(self):
        with pytest.raises(ValueError, match="max_gip must be in"):
            evaluate_gas_feasibility(0.3, max_gip=1.5)


# ===========================================================================
# 4. Los dos 0.10 del proyecto son cosas distintas
# ===========================================================================

class TestLosDosDiezPorCiento:
    """``GAS_FRACTION_PUMP_LIMIT`` y ``GAS_RATIO_DEGRADATION_START`` valen
    los dos 0.10 pero NO son el mismo criterio: uno es fracción y el otro
    relación. Confundirlos corre el umbral casi a la mitad."""

    def test_valen_lo_mismo_pero_no_significan_lo_mismo(self):
        assert GAS_FRACTION_PUMP_LIMIT == pytest.approx(GAS_RATIO_DEGRADATION_START)

    def test_la_relacion_de_0_10_equivale_a_una_fraccion_menor(self):
        assert ratio_to_fraction(GAS_RATIO_DEGRADATION_START) == pytest.approx(
            0.0909, abs=1e-4
        )

    def test_el_limite_de_bomba_es_fraccion(self):
        """Un pozo con f = 0.10 exacto cumple el límite de bomba…"""
        assert evaluate_gas_feasibility(0.10)["viable"] is True
        """…aunque su relación (0.111) ya supere el umbral de degradación."""
        assert fraction_to_ratio(0.10) > GAS_RATIO_DEGRADATION_START


# ===========================================================================
# 5. El default vive en el modelo y coincide con el dominio
# ===========================================================================

class TestMaxGipEnLosObjetivos:

    def test_el_default_es_el_del_dominio(self):
        o = DesignObjectives(
            target_flow_rate=1000.0, safety_margin_depth=50.0,
            allow_gas_venting=False, design_life_years=5.0, use_vsd=False,
        )
        assert o.max_gip == pytest.approx(GAS_FRACTION_PUMP_LIMIT)

    def test_se_puede_apartar_declarandolo(self):
        o = DesignObjectives(
            target_flow_rate=1000.0, safety_margin_depth=50.0,
            allow_gas_venting=False, design_life_years=5.0, use_vsd=False,
            max_gip=0.05,
        )
        assert o.max_gip == pytest.approx(0.05)

    def test_sigue_validando_el_rango(self):
        with pytest.raises(ValueError, match="max_gip"):
            DesignObjectives(
                target_flow_rate=1000.0, safety_margin_depth=50.0,
                allow_gas_venting=False, design_life_years=5.0, use_vsd=False,
                max_gip=1.5,
            )
