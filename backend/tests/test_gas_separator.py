"""Separador de gas y límite de viabilidad de la BES.

El separador retira una fracción del gas libre antes de la admisión. Si lo que
queda supera el máximo que tolera la bomba, el diseño **no converge** y hay que
evaluar otro método de levantamiento artificial — el diseño falla, no advierte.
"""
from __future__ import annotations

import pytest

from bes.core.gas_handling import (
    gas_handler_power_at_frequency,
    tandem_separation_efficiency,
    select_gas_handling_strategy,
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


# ---------------------------------------------------------------------------
# Separador en tándem y potencia por frecuencia (Takács §4.4.5)
# ---------------------------------------------------------------------------

class TestPotenciaDelSeparadorPorFrecuencia:
    """El separador va en el mismo eje: gira a la velocidad de la bomba.

    Takács ec. 4.31: el consumo lo publica el fabricante a frecuencia fija y
    hay que corregirlo por afinidad, BHP = BHP_base·(f/f_base)³.
    """

    def test_a_la_frecuencia_base_no_cambia(self):
        assert gas_handler_power_at_frequency(2.0, 60.0) == pytest.approx(2.0)

    def test_a_50_hz_consume_menos(self):
        """(50/60)³ = 0.5787 → 1.157 hp, no 2."""
        assert gas_handler_power_at_frequency(2.0, 50.0) == pytest.approx(1.1574, abs=1e-4)

    def test_escala_con_el_cubo(self):
        base = gas_handler_power_at_frequency(2.0, 30.0)
        doble = gas_handler_power_at_frequency(2.0, 60.0)
        assert doble / base == pytest.approx(8.0, rel=1e-9)

    def test_es_la_misma_ley_que_escala_la_bomba(self):
        """Dejar la curva escalada y el separador sin escalar era incoherente."""
        from bes.core.affinity import HYDRAULIC_HP_CONSTANT  # noqa: F401
        for f in (40.0, 50.0, 60.0):
            assert gas_handler_power_at_frequency(1.0, f, 60.0) == pytest.approx(
                (f / 60.0) ** 3
            )

    @pytest.mark.parametrize("f", [0.0, -10.0])
    def test_rechaza_frecuencias_imposibles(self, f):
        with pytest.raises(ValueError):
            gas_handler_power_at_frequency(2.0, f)


class TestEficienciaDelTandem:
    """En serie se multiplica lo que PASA, no lo que se retira."""

    def test_uno_solo_devuelve_su_propia_eficiencia(self):
        assert tandem_separation_efficiency([0.90]) == pytest.approx(0.90)

    def test_dos_en_serie(self):
        """1 − (1−0.90)(1−0.97) = 0.997."""
        assert tandem_separation_efficiency([0.90, 0.97]) == pytest.approx(0.997)

    def test_no_es_el_promedio_ni_la_suma(self):
        eta = tandem_separation_efficiency([0.90, 0.97])
        assert eta != pytest.approx((0.90 + 0.97) / 2)
        assert eta < 1.0, "nunca puede separar más del 100 %"

    def test_lista_vacia_no_separa_nada(self):
        assert tandem_separation_efficiency([]) == 0.0

    def test_rechaza_eficiencias_fuera_de_rango(self):
        with pytest.raises(ValueError):
            tandem_separation_efficiency([0.9, 1.5])


class TestEscaleraDeManejoDeGas:
    """ninguno → simple → tándem → cambiar de método de levantamiento."""

    ROT, VOR = 0.90, 0.97

    def _e(self, f, **kw):
        base = dict(single_efficiency=self.VOR,
                    tandem_efficiencies=[self.ROT, self.VOR], max_gip=0.10)
        base.update(kw)
        return select_gas_handling_strategy(f, **base)

    def test_sin_gas_no_pone_separador(self):
        r = self._e(0.05)
        assert r["strategy"] == "ninguno"
        assert r["n_separators"] == 0
        assert r["viable"] and not r["switch_lift_method"]

    def test_gas_medio_alcanza_con_uno(self):
        r = self._e(0.35)
        assert r["strategy"] == "simple"
        assert r["n_separators"] == 1

    def test_gas_alto_necesita_tandem(self):
        r = self._e(0.85)
        assert r["strategy"] == "tandem"
        assert r["n_separators"] == 2
        assert r["efficiency"] == pytest.approx(0.997)
        assert r["f_pump"] <= 0.10

    def test_se_queda_en_el_primer_escalon_que_alcanza(self):
        """No se instala equipo de más."""
        r = self._e(0.35)
        assert r["strategy"] == "simple"
        assert r["ladder"][1]["alcanza"] is True

    def test_si_ni_el_tandem_alcanza_hay_que_cambiar_de_metodo(self):
        """El caso que importa: el techo de la tecnología BES no da."""
        r = self._e(0.995)
        assert r["strategy"] == "no_viable"
        assert r["switch_lift_method"] is True
        assert r["viable"] is False
        assert r["f_pump"] > 0.10
        assert "CAMBIAR DE MÉTODO DE LEVANTAMIENTO" in r["verdict"]
        assert "levantamiento artificial" in r["verdict"]

    def test_sin_separador_en_el_catalogo_tambien_puede_ser_inviable(self):
        r = select_gas_handling_strategy(0.60, single_efficiency=None, max_gip=0.10)
        assert r["switch_lift_method"] is True

    def test_la_escalera_reporta_los_tres_escalones(self):
        r = self._e(0.85)
        assert [e["strategy"] for e in r["ladder"]] == ["ninguno", "simple", "tandem"]

    def test_avisa_que_la_eficiencia_es_la_maxima_de_catalogo(self):
        """Takács Fig. 4.19: la eficiencia real cae con el caudal."""
        r = self._e(0.35)
        assert any("MÁXIMA" in w for w in r["warnings"])

    def test_avisa_al_pasar_el_rango_documentado_del_rgs(self):
        """Relación in situ > 0.6 (Takács pág. 186) es extrapolación."""
        assert any("0.6" in w for w in self._e(0.85)["warnings"])
        assert not any("0.6" in w for w in self._e(0.20)["warnings"])

    def test_la_reduccion_va_sobre_la_relacion_no_sobre_la_fraccion(self):
        """Con f=65 % y η=75 % lo correcto es 31.6 %, no 16.2 %."""
        r = select_gas_handling_strategy(0.65, single_efficiency=0.75, max_gip=0.40)
        assert r["f_pump"] == pytest.approx(0.316, abs=0.005)


# ===========================================================================
# El cuarto escalón: el manejador avanzado de gas (AGH)
# ===========================================================================

class TestElEscalonDelManejadorAvanzado:
    """El AGH **no separa gas**: sube la tolerancia de la bomba.

    Los tres primeros escalones bajan ``f_pump`` retirando gas. El cuarto lo
    deja donde está y en cambio compara contra la fracción de vacío que el
    fabricante publica para el equipo (REDA declara 45 % de GVF, ESP Catalog
    pág. 393). Confundir las dos cosas —creer que el AGH «separa 45 %»— haría
    aparecer un pozo como más limpio de lo que es.
    """

    def test_el_agh_no_baja_el_gas_lo_tolera(self):
        r = select_gas_handling_strategy(
            0.30, single_efficiency=None, max_gip=0.10, agh_max_gvf=0.45,
            agh_model="AGH D20-60",
        )
        assert r["strategy"] == "agh"
        assert r["viable"] is True
        assert not r["switch_lift_method"]
        # Sin separador, el gas que entra a la bomba es TODO el de la admisión.
        assert r["f_pump"] == pytest.approx(0.30)
        assert r["f_pump"] > r["max_gip"]
        # Lo que cambió es contra qué se compara.
        assert r["tolerance"] == pytest.approx(0.45)
        assert r["uses_agh"] is True
        assert r["agh_model"] == "AGH D20-60"

    def test_se_apila_SOBRE_el_separador_no_en_su_lugar(self):
        """El catálogo lo dice: «installed in series above ... gas separators».

        Con separador el gas baja primero, y el AGH tolera el remanente. La
        cuenta de separadores del escalón elegido tiene que conservarse, porque
        de ella sale el consumo que se le carga al motor.
        """
        r = select_gas_handling_strategy(
            0.63, single_efficiency=0.75, max_gip=0.10, agh_max_gvf=0.45,
        )
        assert r["strategy"] == "agh"
        assert r["n_separators"] == 1
        assert r["efficiency"] == pytest.approx(0.75)
        # 0.63 → r=1.70 → ×0.25 → r'=0.426 → f'=29.9 %
        assert r["f_pump"] == pytest.approx(0.299, abs=0.005)
        assert r["f_pump"] <= 0.45

    def test_por_encima_de_su_GVF_manda_cambiar_de_metodo(self):
        r = select_gas_handling_strategy(
            0.70, single_efficiency=None, max_gip=0.10, agh_max_gvf=0.45,
        )
        assert r["strategy"] == "no_viable"
        assert r["switch_lift_method"] is True
        assert "manejador avanzado" in r["verdict"]

    def test_no_puede_pasar_por_encima_de_un_max_gip_mas_estricto(self):
        """Si el usuario apretó el límite POR DEBAJO del estándar, manda él.

        ``max_gip`` por debajo de ``GAS_FRACTION_PUMP_LIMIT`` es un requisito
        deliberado —una instalación particular, un criterio de operación— y un
        equipo de catálogo no lo puede anular. Al revés sí: con la tolerancia
        estándar, el AGH la extiende hasta su GVF publicado.
        """
        r = select_gas_handling_strategy(
            0.30, single_efficiency=None, max_gip=0.01, agh_max_gvf=0.45,
        )
        assert r["strategy"] == "no_viable"
        assert r["uses_agh"] is False

    def test_sin_manejador_en_el_catalogo_el_escalon_no_existe(self):
        r = select_gas_handling_strategy(
            0.30, single_efficiency=None, max_gip=0.10, agh_max_gvf=None,
        )
        assert r["strategy"] == "no_viable"
        assert [e["strategy"] for e in r["ladder"]] == ["ninguno", "simple", "tandem"]

    def test_el_aviso_dice_que_el_gas_SIGUE_entrando(self):
        """Es la advertencia que evita leer mal el resultado."""
        r = select_gas_handling_strategy(
            0.30, single_efficiency=None, max_gip=0.10, agh_max_gvf=0.45,
        )
        assert any("NO retira gas" in w for w in r["warnings"])


class TestElCatalogoDeManejadoresEsREDA:
    """La purga de proveedores dejó tres fabricantes; ChampionX no es uno.

    Ver ``.claude/rules/domain.md``, «Proveedores del proyecto». El catálogo de
    manejadores de gas era el último lugar donde sobrevivía ChampionX, y su
    eficiencia del 97 % era de la que dependía el veredicto de viabilidad.
    """

    @pytest.fixture(scope="class")
    def handlers(self):
        from bes.catalogs.loader import CatalogManager
        return CatalogManager().get_all_gas_handlers()

    def test_no_queda_ningun_fabricante_purgado(self, handlers):
        proveedores = {g["manufacturer"] for g in handlers}
        assert proveedores == {"REDA"}

    def test_ninguna_eficiencia_inventada(self, handlers):
        """REDA no publica eficiencia de separación: el campo va en null.

        Poner un número estimado haría el veredicto de viabilidad incitable en
        la tesis. Sin dato, el dominio aplica SEPARATOR_DEFAULT_EFFICIENCY y lo
        DECLARA en el veredicto, que es lo honesto.
        """
        assert all(g["max_efficiency"] is None for g in handlers)

    def test_el_consumo_publicado_viaja_por_modelo(self, handlers):
        """Los tres vórtice y los seis AGH publican su hp a 60 Hz."""
        from bes.core.gas_handling import GAS_SEPARATOR_HP, gas_handler_hp
        con_hp = {g["model"]: g["hp"] for g in handlers if g["hp"]}
        assert con_hp["VGSA D20-60"] == 3
        assert con_hp["VGSA S20-90"] == 6
        assert con_hp["VGSA S70-150"] == 14
        assert con_hp["AGH H100-250"] == 102
        assert all(g["hp_frequency_hz"] == 60 for g in handlers)
        # Y el que no lo publica cae al respaldo, no a cero.
        sin_hp = next(g for g in handlers if g["hp"] is None)
        assert gas_handler_hp(sin_hp) == pytest.approx(GAS_SEPARATOR_HP)

    def test_los_rotativos_estan_pero_no_se_pueden_elegir(self, handlers):
        """ARS / CRS-ES / DRS-ES: el catálogo no publica su rango de caudal.

        Se cargan igual —el fabricante los ofrece— pero sin rango no se pueden
        verificar contra un pozo, así que el selector no los devuelve.
        Suponerles un rango sería inventar el dato.
        """
        from bes.catalogs.loader import CatalogManager
        rotativos = [g for g in handlers if g["type"] == "rotary"]
        assert {g["model"] for g in rotativos} == {"ARS", "CRS-ES", "DRS-ES"}
        assert all(g["min_flow_bpd"] is None for g in rotativos)

        cm = CatalogManager()
        elegidos = {
            (cm.select_gas_handler(q, 8.0, prefer_type="rotary") or {}).get("model")
            for q in (500, 2000, 5000, 12000, 30000)
        }
        assert not (elegidos & {"ARS", "CRS-ES", "DRS-ES"})

    def test_el_AGH_no_se_ofrece_como_separador(self, handlers):
        """No separa: pedirlo como separador le atribuiría una eficiencia."""
        from bes.catalogs.loader import CatalogManager
        cm = CatalogManager()
        # 1500 bpd: el único equipo REDA de ese rango es el AGH D5-21.
        assert cm.select_gas_handler(1500.0, 6.0) is None
        agh = cm.select_gas_handler(
            1500.0, 6.0, prefer_type="agh", require_separation=False
        )
        assert agh is not None and agh["type"] == "agh"
        assert agh["separates_gas"] is False


class TestElRangoDelSeparadorEsDeMEZCLA:
    """El catálogo declara «total liquid and gas operating range» (pág. 392).

    Consultarlo con el caudal de líquido solo descarta separadores que en
    realidad califican, y en un pozo con mucho gas es la diferencia entre
    poder diseñarlo y declararlo inviable.
    """

    def test_el_gas_sube_el_caudal_que_ve_el_equipo(self):
        from bes.core.gas_handling import total_intake_rate
        # 1227 bpd de líquido con 63 % de gas libre son 3316 bpd de mezcla.
        assert total_intake_rate(1227.0, 0.63) == pytest.approx(3316.2, abs=1.0)

    def test_sin_gas_no_cambia_nada(self):
        from bes.core.gas_handling import total_intake_rate
        assert total_intake_rate(1227.0, 0.0) == pytest.approx(1227.0)

    def test_decide_si_el_vortex_de_REDA_califica(self):
        """El VGSA D20-60 arranca en 2000 bpd: con el líquido pelado no entra."""
        from bes.catalogs.loader import CatalogManager
        from bes.core.gas_handling import total_intake_rate
        cm = CatalogManager()
        assert cm.select_gas_handler(1227.0, 4.892) is None
        q_mezcla = total_intake_rate(1227.0, 0.63)
        elegido = cm.select_gas_handler(q_mezcla, 4.892)
        assert elegido is not None
        assert elegido["model"] == "VGSA D20-60"
