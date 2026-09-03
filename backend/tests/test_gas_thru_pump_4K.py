"""Apéndice 4K de Brown — «Method for estimating the percent of free gas that
will go thru a pump», by Don Rhoads (Vol. 2b, págs. 345-347).

Los valores contra los que se compara están **escritos en el propio test**,
tomados del impreso, así que la validación no depende de ningún archivo de
datos: si alguien edita la digitalización, estos tests lo delatan.
"""

import json
from pathlib import Path

import pytest

from bes.core.gas_handling import (
    approach_velocity,
    free_gas_thru_pump,
)

# Datos del ejemplo resuelto de la pág. 347, transcritos del impreso.
EJEMPLO = {
    "pbb_psig": 2800.0,
    "pi_psig": 2660.0,
    "oil_viscosity_cp": 2.0,
    "water_cut": 0.40,
    "casing_id_in": 6.276,      # 7 in, 26 lb/ft (peso que declara la Tabla 1)
    "seal_od_in": 5.13,         # serie 513 = OD en centésimas de pulgada
    "intake_flow_bpd": 6000.0,
    "va_impreso_ft_s": 5.5,
    "pct_base_impreso": 26.1,
    "pct_burbuja_impreso": 1.0,
    "pct_viscosidad_impreso": 0.5,
    "pct_neto_impreso": 25.6,
}


class TestElEjemploImpresoSeReproduce:
    """El ejemplo de la pág. 347, paso por paso."""

    def test_la_velocidad_geometrica_reproduce_la_tabla_1(self):
        """La Tabla 1 declara estar basada en el área sello-casing, así que la
        geometría tiene que devolver lo mismo que la tabla."""
        va = approach_velocity(
            EJEMPLO["intake_flow_bpd"],
            EJEMPLO["casing_id_in"],
            EJEMPLO["seal_od_in"],
        )
        assert va == pytest.approx(EJEMPLO["va_impreso_ft_s"], abs=0.1)

    def test_el_porcentaje_base_con_separador(self):
        r = free_gas_thru_pump(EJEMPLO["va_impreso_ft_s"], has_separator=True)
        assert r["pct_base"] == pytest.approx(EJEMPLO["pct_base_impreso"], abs=0.05)

    def test_el_efecto_del_tamano_de_burbuja(self):
        r = free_gas_thru_pump(
            EJEMPLO["va_impreso_ft_s"], has_separator=True,
            pi_over_pbb=EJEMPLO["pi_psig"] / EJEMPLO["pbb_psig"],
            water_cut=EJEMPLO["water_cut"],
        )
        assert r["pct_bubble"] == pytest.approx(
            EJEMPLO["pct_burbuja_impreso"], abs=0.05
        )

    def test_el_efecto_de_la_viscosidad(self):
        r = free_gas_thru_pump(
            EJEMPLO["va_impreso_ft_s"], has_separator=True,
            liquid_viscosity_cp=EJEMPLO["oil_viscosity_cp"],
            water_cut=EJEMPLO["water_cut"],
        )
        assert r["pct_viscosity"] == pytest.approx(
            EJEMPLO["pct_viscosidad_impreso"], abs=0.05
        )

    def test_el_neto(self):
        r = free_gas_thru_pump(
            EJEMPLO["va_impreso_ft_s"], has_separator=True,
            pi_over_pbb=EJEMPLO["pi_psig"] / EJEMPLO["pbb_psig"],
            liquid_viscosity_cp=EJEMPLO["oil_viscosity_cp"],
            water_cut=EJEMPLO["water_cut"],
        )
        assert r["pct_net"] == pytest.approx(EJEMPLO["pct_neto_impreso"], abs=0.05)


class TestLosExtremosQueDeclaraElLibro:
    """Los cuatro casos límite del enunciado, pág. 345, punto 2."""

    def test_sin_separador_a_velocidad_nula_no_pasa_gas(self):
        assert free_gas_thru_pump(0.0, has_separator=False)["pct_base"] == \
            pytest.approx(0.5, abs=0.01)

    def test_sin_separador_a_16_ft_s_pasa_el_90(self):
        assert free_gas_thru_pump(16.0, has_separator=False)["pct_base"] == \
            pytest.approx(90.5, abs=0.01)

    def test_con_separador_a_velocidad_nula_no_pasa_gas(self):
        assert free_gas_thru_pump(0.0, has_separator=True)["pct_base"] == \
            pytest.approx(0.5, abs=0.01)

    def test_con_separador_a_16_ft_s_pasa_el_45(self):
        assert free_gas_thru_pump(16.0, has_separator=True)["pct_base"] == \
            pytest.approx(45.5, abs=0.01)

    def test_el_separador_corta_a_la_mitad_el_gas_pasante(self):
        """Es la única cuantificación del efecto de un separador que publica
        el libro: de 90 % a 45 % en el extremo de velocidad."""
        sin_sep = free_gas_thru_pump(16.0, has_separator=False)["pct_base"]
        con_sep = free_gas_thru_pump(16.0, has_separator=True)["pct_base"]
        assert (con_sep - 0.5) / (sin_sep - 0.5) == pytest.approx(0.5, abs=0.01)


class TestLaDigitalizacionEsCoherente:
    """Controles internos sobre las tablas, derivados de sus propias notas."""

    @staticmethod
    def _tablas():
        import bes.catalogs as _c
        p = Path(_c.__file__).parent / "gas_thru_pump_4K.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def test_la_tabla_3_es_la_raiz_cubica_de_la_tabla_2(self):
        """La nota de la Tabla 3 declara esa derivación, con el factor que
        lleva el efecto máximo a 5.0 %."""
        t = self._tablas()
        t2 = t["tabla_2_tamano_burbuja_relativo"]["valores"]
        t3 = t["tabla_3_efecto_burbuja"]["valores"]
        factor = 5.0 / (5.0 ** (1 / 3))
        for fila2, fila3 in zip(t2, t3):
            for v2, v3 in zip(fila2, fila3):
                esperado = (v2 ** (1 / 3)) * factor if v2 > 0 else 0.0
                assert v3 == pytest.approx(esperado, abs=0.06)

    def test_las_tres_tablas_comparten_la_grilla_de_corte_de_agua(self):
        t = self._tablas()
        n = len(t["water_cut_pct"])
        for clave in ("tabla_2_tamano_burbuja_relativo",
                      "tabla_3_efecto_burbuja",
                      "tabla_4_efecto_viscosidad"):
            for fila in t[clave]["valores"]:
                assert len(fila) == n, f"{clave} no tiene {n} columnas"

    def test_a_100_por_ciento_de_agua_no_hay_efecto(self):
        """La última columna de las tres tablas es cero en el impreso: sin
        petróleo no hay ni burbuja ni viscosidad que corregir."""
        t = self._tablas()
        for clave in ("tabla_2_tamano_burbuja_relativo",
                      "tabla_3_efecto_burbuja",
                      "tabla_4_efecto_viscosidad"):
            for fila in t[clave]["valores"]:
                assert fila[-1] == 0.0

    def test_no_se_extrapola_fuera_de_las_tablas(self):
        """Viscosidad por encima de 16 cp se acota al borde, no dispara."""
        borde = free_gas_thru_pump(8.0, has_separator=False,
                                   liquid_viscosity_cp=16.0, water_cut=0.0)
        fuera = free_gas_thru_pump(8.0, has_separator=False,
                                   liquid_viscosity_cp=500.0, water_cut=0.0)
        assert fuera["pct_viscosity"] == pytest.approx(borde["pct_viscosity"])


class TestLosLimitesDeLaFuncion:
    def test_el_corte_de_agua_fuera_de_rango_falla(self):
        with pytest.raises(ValueError, match="water_cut"):
            free_gas_thru_pump(8.0, has_separator=False, water_cut=1.5)

    def test_un_sello_que_no_entra_en_el_casing_falla(self):
        with pytest.raises(ValueError, match="área anular"):
            approach_velocity(1000.0, casing_id_in=4.0, seal_od_in=4.5)

    def test_la_velocidad_se_acota_al_maximo_de_la_correlacion(self):
        """Por encima de 16 ft/s la parábola volvería a bajar, que no es lo
        que describe el método."""
        a = free_gas_thru_pump(16.0, has_separator=False)["pct_base"]
        b = free_gas_thru_pump(40.0, has_separator=False)["pct_base"]
        assert a == pytest.approx(b)
