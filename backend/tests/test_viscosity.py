"""
Crudos viscosos — procedimiento de Riling (Brown Vol. 2b, §4.53112).

Ejercicio de referencia (filminas de cátedra, resuelto a mano sobre las figuras
del Apéndice 4L):

    Crudo de 16 °API a 130 °F, con 50 scf/bbl de gas en solución.
    Bomba de 70 % de rendimiento máximo. El pozo pide 1700 b/d y 5230 ft.

    Paso 2  Fig. 4L-2  ->  150 cp   (crudo sin gas)
    Paso 3  Fig. 4L-1  ->   68 cp   (saturado con gas)
    Paso 4  Fig. 4L-3  ->  325 SSU
    Paso 5  30 % de agua, MEDIDO -> 650 SSU
    Paso 6  Tabla 4.521 -> C_Q = 88 %, C_H = 88.75 %, C_HP = 117.3 %
    Paso 7  1700/0.88 = 1932 b/d ; 5230/0.8875 = 5893 ft

El segundo bloque de tests (clases 8 a 10) cubre el modelo Hydraulic Institute
curve-fiteado por Turzo et al., contra los tres ejemplos publicados:

    Takács Ej. 4.1  88 cSt, BEP 900 bpd / 21.8 ft  -> Q* = 23.34
    Takács Ej. 4.2  402 SSU, tabla 4.1 Centrilift  -> C_Q = 0.847
    Turzo OGJ 2000  55 cSt, BEP 9212 gpm / 770 ft  -> y = 94.7, Q* = 2.698
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bes.core.viscosity import (
    HI_HEAD_RANGE_FT,
    HI_Q_STAR_MAX,
    HI_RATE_RANGE_BPD,
    HI_VISCOSITY_RANGE_CST,
    VISCOUS_CRUDE_API_THRESHOLD,
    _CHARTS_PATH,
    _TABLES_PATH,
    brake_horsepower,
    dead_oil_viscosity_chart,
    gas_saturated_viscosity_chart,
    centrilift_factors,
    cst_to_ssu_takacs,
    evaluate_viscosity,
    hi_corrected_curve,
    hydraulic_institute_factors,
    is_viscous_crude,
    crude_viscosity_ssu,
    cst_to_ssu,
    ssu_to_cst,
    viscosity_factors,
    water_equivalent_duty,
)

#: Los cuatro puntos de la curva de agua del Ejemplo 4.1 de Takács (pág. 157).
CURVA_EJEMPLO_4_1 = {
    0.6: {"q": 540.0, "h": 27.9, "eff": 50.9},
    0.8: {"q": 720.0, "h": 25.5, "eff": 60.3},
    1.0: {"q": 900.0, "h": 21.8, "eff": 64.0},
    1.2: {"q": 1080.0, "h": 15.2, "eff": 55.4},
}


# ---------------------------------------------------------------------------
# 1. Las tablas como dato
# ---------------------------------------------------------------------------

class TestTablasDeCorreccion:
    @pytest.fixture(scope="class")
    def tablas(self):
        return json.loads(Path(_TABLES_PATH).read_text(encoding="utf-8"))

    def test_tiene_procedencia(self, tablas):
        assert "Brown" in tablas["_source"]
        assert "4.520" in tablas["_source"] and "4.521" in tablas["_source"]

    def test_las_dos_tablas_con_las_mismas_viscosidades(self, tablas):
        s60 = [r["ssu"] for r in tablas["tables"]["60"]["rows"]]
        s70 = [r["ssu"] for r in tablas["tables"]["70"]["rows"]]
        assert s60 == s70
        assert s60 == sorted(s60), "las filas tienen que venir ordenadas por SSU"
        assert s60[0] == 50 and s60[-1] == 5000

    def test_relacion_interna_del_factor_de_potencia(self, tablas):
        """C_HP = (C_Q · C_H / η_nuevo) · η_agua · 100.

        Sale de la definición de potencia hidráulica: la potencia escala con
        caudal y altura, y baja con el rendimiento. Es la verificación que
        confirmó que la columna «× 80» del escaneo es en realidad «× γ_o» —
        el símbolo se degradó, pero la aritmética cierra.

        Tolerancia de 4 puntos porcentuales: unas pocas filas del impreso no
        cierran fino (ver docs/CRUDOS_VISCOSOS.md §8.6, quedan por releer de
        una copia mejor). Lo que se protege acá es que ninguna fila esté
        groseramente mal transcrita.
        """
        for clave, tabla in tablas["tables"].items():
            eff_agua = tabla["water_efficiency_pct"]
            for fila in tabla["rows"]:
                calc = (
                    (fila["capacity_factor"] / 100.0 * fila["head_factor"] / 100.0)
                    / (fila["new_efficiency"] / 100.0) * (eff_agua / 100.0) * 100.0
                )
                assert calc == pytest.approx(fila["hp_factor"], abs=4.0), (
                    f"tabla {clave}, {fila['ssu']} SSU: impreso "
                    f"{fila['hp_factor']}, la relación interna da {calc:.1f}"
                )

    def test_los_factores_caen_al_subir_la_viscosidad(self, tablas):
        for tabla in tablas["tables"].values():
            for campo in ("capacity_factor", "head_factor", "new_efficiency"):
                vals = [r[campo] for r in tabla["rows"]]
                for a, b in zip(vals, vals[1:]):
                    assert a >= b, f"{campo} tiene que ser monótono decreciente"

    def test_la_bomba_de_70_siempre_aguanta_mejor(self, tablas):
        """A igual viscosidad, la bomba más eficiente se degrada menos."""
        for f60, f70 in zip(tablas["tables"]["60"]["rows"],
                            tablas["tables"]["70"]["rows"]):
            assert f70["capacity_factor"] >= f60["capacity_factor"]
            assert f70["head_factor"] >= f60["head_factor"]
            assert f70["new_efficiency"] > f60["new_efficiency"]


# ---------------------------------------------------------------------------
# 2. Paso 4 — conversión de unidades
# ---------------------------------------------------------------------------

class TestConversionSSU:
    def test_ida_y_vuelta(self):
        for cst in (2.0, 10.0, 34.31, 70.88, 500.0, 1080.0):
            assert ssu_to_cst(cst_to_ssu(cst)) == pytest.approx(cst, rel=1e-6)

    def test_las_dos_ramas_de_astm_d2161(self):
        # < 100 SSU y >= 100 SSU usan fórmulas distintas
        assert ssu_to_cst(50.0) == pytest.approx(0.226 * 50 - 195 / 50)
        assert ssu_to_cst(200.0) == pytest.approx(0.220 * 200 - 135 / 200)

    def test_el_ejemplo_de_la_filmina(self):
        """68 cp de crudo de 16 °API → 325 SSU."""
        sg = 141.5 / (131.5 + 16.0)
        assert cst_to_ssu(68.0 / sg) == pytest.approx(325.0, abs=2.0)

    def test_es_creciente(self):
        vals = [cst_to_ssu(c) for c in (5.0, 20.0, 100.0, 500.0)]
        assert vals == sorted(vals)

    def test_rechaza_valores_imposibles(self):
        with pytest.raises(ValueError, match="cst must be > 0"):
            cst_to_ssu(0.0)
        with pytest.raises(ValueError, match="ssu must be >= 31"):
            ssu_to_cst(10.0)


# ---------------------------------------------------------------------------
# 2-bis. Paso 2 — la Fig. 4L(2) digitalizada
# ---------------------------------------------------------------------------

class TestFigura4L2:
    """La lámina «Viscosity of gas-free crude oil at oil-field temperatures».

    Digitalizada de la lámina que aportó Pablo y verificada por él contra el
    impreso. El ancla es el punto que la cátedra lee de esta misma figura.
    """

    def test_el_ancla_de_catedra(self):
        """16 °API a 130 °F = 150 cp — el paso 2 del ejercicio resuelto."""
        assert dead_oil_viscosity_chart(16.0, 130.0)["mu_cp"] == pytest.approx(
            150.0, rel=0.05
        )

    def test_los_nodos_de_la_grilla_se_devuelven_tal_cual(self):
        """En un punto de grilla no hay interpolación que valga: es el dato."""
        fig = json.loads(_CHARTS_PATH.read_text(encoding="utf-8"))["fig_4L_2"]
        for iso in fig["isotermas"]:
            for api, mu in zip(fig["api"], iso["mu_cp"]):
                leido = dead_oil_viscosity_chart(api, iso["temp_f"])["mu_cp"]
                assert leido == pytest.approx(mu, rel=1e-9), (
                    f"{api} °API a {iso['temp_f']} °F"
                )

    def test_mas_temperatura_menos_viscosidad(self):
        """Cada isoterma queda por debajo de la anterior, en todo el rango."""
        for api in (10, 16, 20, 25, 30, 40, 55, 60):
            mus = [
                dead_oil_viscosity_chart(api, t)["mu_cp"]
                for t in (100, 130, 160, 190, 220)
            ]
            assert mus == sorted(mus, reverse=True), f"{api} °API"

    def test_mas_grados_api_menos_viscosidad(self):
        """El crudo liviano es menos viscoso: la curva baja hacia la derecha."""
        for t in (100, 130, 160, 190, 220):
            mus = [
                dead_oil_viscosity_chart(api, t)["mu_cp"]
                for api in range(10, 61, 5)
            ]
            assert mus == sorted(mus, reverse=True), f"{t} °F"

    def test_el_contraste_de_los_100_f(self):
        """Lo que ya estaba anotado en docs/CRUDOS_VISCOSOS.md sobre la lámina."""
        assert dead_oil_viscosity_chart(20.0, 100.0)["mu_cp"] == pytest.approx(
            100.0, rel=0.05
        )
        assert dead_oil_viscosity_chart(40.0, 100.0)["mu_cp"] < 3.0

    def test_interpola_dentro_del_tramo(self):
        """Un punto interior cae entre sus dos vecinos, no sobre uno de ellos."""
        bajo = dead_oil_viscosity_chart(35.0, 130.0)["mu_cp"]
        alto = dead_oil_viscosity_chart(40.0, 130.0)["mu_cp"]
        medio = dead_oil_viscosity_chart(37.5, 130.0)["mu_cp"]
        assert alto < medio < bajo

    def test_no_extrapola_fuera_de_la_lamina(self):
        """Fuera de la grilla acota al borde y lo dice — nunca extrapola."""
        borde = dead_oil_viscosity_chart(10.0, 100.0)["mu_cp"]
        r = dead_oil_viscosity_chart(6.0, 80.0)
        assert r["mu_cp"] == pytest.approx(borde)
        assert r["clamped"] is True
        assert any("°API" in w for w in r["warnings"])
        assert any("°F" in w for w in r["warnings"])

    def test_dentro_de_la_lamina_no_avisa_nada(self):
        r = dead_oil_viscosity_chart(22.0, 145.0)
        assert r["clamped"] is False
        assert r["warnings"] == []

    def test_rechaza_entradas_imposibles(self):
        with pytest.raises(ValueError, match="oil_api"):
            dead_oil_viscosity_chart(0.0, 130.0)
        with pytest.raises(ValueError, match="temp_f"):
            dead_oil_viscosity_chart(16.0, -10.0)

    def test_la_lamina_declara_su_procedencia(self):
        """Sin `_source` el número no es citable en la tesis."""
        datos = json.loads(_CHARTS_PATH.read_text(encoding="utf-8"))
        assert "Brown" in datos["_source"]
        assert "Fig. 4L" in datos["_source"]
        assert "_ancla" in datos["fig_4L_2"]
        assert "_incertidumbre" in datos["fig_4L_2"]


class TestFigura4L1:
    """La lámina «Viscosity of gas saturated crude oil at reservoir T & P».

    Cada curva está rotulada con la viscosidad del crudo **sin** gas, así que en
    ``rs = 0`` cada una vale su propia etiqueta. El ancla es el paso 3 del
    ejercicio de cátedra.
    """

    def test_el_ancla_de_catedra(self):
        """150 cp de crudo muerto con 50 scf/bbl = 68 cp."""
        assert gas_saturated_viscosity_chart(150.0, 50.0)["mu_cp"] == pytest.approx(
            68.0, rel=0.03
        )

    def test_sin_gas_disuelto_cada_curva_vale_su_etiqueta(self):
        """En rs = 0 el crudo saturado ES el crudo muerto. Es la identidad de la
        lámina, y sirve de control de que la familia está bien cargada."""
        fig = json.loads(_CHARTS_PATH.read_text(encoding="utf-8"))["fig_4L_1"]
        for curva in fig["curvas"]:
            etiqueta = curva["mu_dead_cp"]
            assert curva["mu_cp"][0] == pytest.approx(etiqueta), (
                f"la curva de {etiqueta} cp no arranca en su etiqueta"
            )
            leido = gas_saturated_viscosity_chart(etiqueta, 0.0)["mu_cp"]
            assert leido == pytest.approx(etiqueta, rel=1e-9)

    def test_los_nodos_de_cada_curva_se_devuelven_tal_cual(self):
        fig = json.loads(_CHARTS_PATH.read_text(encoding="utf-8"))["fig_4L_1"]
        for curva in fig["curvas"]:
            mu_od = curva["mu_dead_cp"]
            for rs, mu in zip(curva["rs_scf_bbl"], curva["mu_cp"]):
                leido = gas_saturated_viscosity_chart(mu_od, rs)["mu_cp"]
                assert leido == pytest.approx(mu, rel=1e-9), f"{mu_od} cp @ {rs}"

    def test_mas_gas_disuelto_menos_viscosidad(self):
        """El gas en solución adelgaza el crudo: toda curva baja hacia la derecha."""
        for mu_od in (0.7, 1.0, 3.0, 10.0, 50.0, 300.0):
            mus = [
                gas_saturated_viscosity_chart(mu_od, rs)["mu_cp"]
                for rs in (0, 50, 100, 200, 300)
            ]
            assert mus == sorted(mus, reverse=True), f"{mu_od} cp"

    def test_las_curvas_no_se_cruzan(self):
        """Un crudo más viscoso sigue siendo más viscoso a igual gas disuelto."""
        for rs in (0, 50, 100, 200, 300):
            mus = [
                gas_saturated_viscosity_chart(mu_od, rs)["mu_cp"]
                for mu_od in (0.7, 1.5, 3, 7, 20, 50, 100, 300, 500)
            ]
            assert mus == sorted(mus), f"{rs} scf/bbl"

    def test_interpola_entre_dos_curvas(self):
        """150 cp no es una curva de la lámina: cae entre la de 100 y la de 300."""
        cien = gas_saturated_viscosity_chart(100.0, 100.0)["mu_cp"]
        trescientos = gas_saturated_viscosity_chart(300.0, 100.0)["mu_cp"]
        medio = gas_saturated_viscosity_chart(150.0, 100.0)["mu_cp"]
        assert cien < medio < trescientos

    def test_no_extrapola_fuera_de_la_familia(self):
        borde = gas_saturated_viscosity_chart(500.0, 100.0)["mu_cp"]
        r = gas_saturated_viscosity_chart(900.0, 100.0)
        assert r["mu_cp"] == pytest.approx(borde)
        assert r["clamped"] is True
        assert any("familia de curvas" in w for w in r["warnings"])

    def test_no_extrapola_pasado_el_final_de_la_curva(self):
        """La de 500 cp se corta a 350 scf/bbl: más allá no hay lámina que leer."""
        fin = gas_saturated_viscosity_chart(500.0, 350.0)["mu_cp"]
        r = gas_saturated_viscosity_chart(500.0, 1400.0)
        assert r["mu_cp"] == pytest.approx(fin)
        assert r["clamped"] is True
        assert any("scf/bbl" in w for w in r["warnings"])

    def test_manda_la_curva_que_termina_antes(self):
        """Entre dos curvas de distinto alcance, el límite es el de la más corta.

        Pasado ese punto una de las dos ya no tiene dato, y promediar sería
        mitad lectura y mitad invento.
        """
        # La de 10 cp llega a 1000 scf/bbl y la de 15 cp a 900.
        r = gas_saturated_viscosity_chart(12.0, 980.0)
        assert r["clamped"] is True
        assert "900" in " ".join(r["warnings"])

    def test_dentro_de_la_lamina_no_avisa_nada(self):
        r = gas_saturated_viscosity_chart(25.0, 250.0)
        assert r["clamped"] is False
        assert r["warnings"] == []

    def test_rechaza_entradas_imposibles(self):
        with pytest.raises(ValueError, match="mu_dead_cp"):
            gas_saturated_viscosity_chart(0.0, 50.0)
        with pytest.raises(ValueError, match="rs_scf_bbl"):
            gas_saturated_viscosity_chart(150.0, -1.0)

    def test_la_lamina_declara_su_procedencia(self):
        fig = json.loads(_CHARTS_PATH.read_text(encoding="utf-8"))["fig_4L_1"]
        assert "_ancla" in fig
        assert "_incertidumbre" in fig
        assert "_terminacion" in fig


# ---------------------------------------------------------------------------
# 3. Pasos 2, 3 y 4 encadenados
# ---------------------------------------------------------------------------

class TestViscosidadDelCrudo:
    def test_el_valor_medido_manda_sobre_la_correlacion(self):
        """Riling dice «de ensayos o de la Fig. 4L»: el dato gana."""
        r = crude_viscosity_ssu(16.0, 130.0, 50.0, dead_oil_cp=150.0)
        assert r["mu_dead_cp"] == 150.0
        assert r["dead_oil_source"] == "medido"
        assert r["warnings"] == []

    def test_sin_dato_lee_la_figura_y_avisa(self):
        r = crude_viscosity_ssu(16.0, 130.0, 50.0)
        assert r["dead_oil_source"] == "fig_4L_2"
        assert any("Fig. 4L(2)" in w for w in r["warnings"])

    def test_sin_dato_la_figura_da_lo_que_da_el_libro(self):
        """La brecha con Beggs-Robinson se cerró digitalizando la figura.

        Este test reemplaza al que documentaba los 59 cp de la correlación
        contra los 150 de la lámina: ahora el paso 2 lee la lámina.
        """
        r = crude_viscosity_ssu(16.0, 130.0, 50.0)
        assert r["mu_dead_cp"] == pytest.approx(150.0, rel=0.05)

    def test_el_ejercicio_de_catedra_sale_de_las_laminas_solas(self):
        """Los tres pasos seguidos, entrando únicamente con °API, T y gas.

        Es la validación fuerte de las dos digitalizaciones: antes había que
        cargarle los 150 cp a mano porque Beggs-Robinson daba 59, y el paso 3
        se iba a 76.6 contra los 68 del libro. Ahora los tres números salen
        solos.

            paso 2  Fig. 4L(2)   -> 150 cp
            paso 3  Fig. 4L(1)   ->  68 cp
            paso 4  ASTM D2161   -> 325 SSU
        """
        r = crude_viscosity_ssu(16.0, 130.0, 50.0)
        assert r["mu_dead_cp"] == pytest.approx(150.0, rel=0.03)
        assert r["mu_live_cp"] == pytest.approx(68.0, rel=0.03)
        assert r["ssu"] == pytest.approx(325.0, rel=0.03)

    def test_el_gas_disuelto_adelgaza_el_crudo(self):
        r = crude_viscosity_ssu(16.0, 130.0, 50.0, dead_oil_cp=150.0)
        assert r["mu_live_cp"] < r["mu_dead_cp"]

    def test_sin_gas_no_hay_correccion(self):
        r = crude_viscosity_ssu(16.0, 130.0, 0.0, dead_oil_cp=150.0)
        assert r["mu_live_cp"] == pytest.approx(r["mu_dead_cp"], rel=0.01)

    def test_mas_temperatura_menos_viscosidad(self):
        fria = crude_viscosity_ssu(16.0, 100.0, 50.0)
        caliente = crude_viscosity_ssu(16.0, 200.0, 50.0)
        assert caliente["ssu"] < fria["ssu"]

    def test_rechaza_entradas_imposibles(self):
        with pytest.raises(ValueError, match="oil_api"):
            crude_viscosity_ssu(0.0, 130.0, 50.0)
        with pytest.raises(ValueError, match="temp_f"):
            crude_viscosity_ssu(16.0, 0.0, 50.0)
        with pytest.raises(ValueError, match="rs_scf_bbl"):
            crude_viscosity_ssu(16.0, 130.0, -1.0)


# ---------------------------------------------------------------------------
# 4. Paso 6 — los factores
# ---------------------------------------------------------------------------

class TestFactoresDeCorreccion:
    def test_el_caso_de_la_filmina(self):
        """650 SSU, bomba de 70 % → 88 / 88.75 / 117.3."""
        f = viscosity_factors(ssu=650.0, pump_efficiency_pct=70.0)
        assert f["capacity_factor"] == pytest.approx(88.00, abs=0.01)
        assert f["head_factor"] == pytest.approx(88.75, abs=0.01)
        assert f["hp_factor"] == pytest.approx(117.30, abs=0.01)

    def test_una_fila_exacta_no_se_interpola(self):
        f = viscosity_factors(ssu=1000.0, pump_efficiency_pct=60.0)
        assert f["capacity_factor"] == pytest.approx(75.0)
        assert f["new_efficiency"] == pytest.approx(26.5)

    def test_interpola_entre_las_dos_tablas(self):
        """Una bomba de 65 % cae justo en el medio de 60 % y 70 %."""
        f60 = viscosity_factors(1000.0, 60.0)
        f70 = viscosity_factors(1000.0, 70.0)
        f65 = viscosity_factors(1000.0, 65.0)
        for k in ("capacity_factor", "head_factor", "new_efficiency"):
            assert f65[k] == pytest.approx((f60[k] + f70[k]) / 2, abs=0.01)

    def test_no_extrapola_por_rendimiento(self):
        """Fuera de [60, 70] se acota al extremo y se avisa."""
        baja = viscosity_factors(1000.0, 45.0)
        assert baja["capacity_factor"] == pytest.approx(
            viscosity_factors(1000.0, 60.0)["capacity_factor"]
        )
        assert baja["clamped_efficiency"]
        assert any("rendimiento máximo" in w for w in baja["warnings"])

    def test_no_extrapola_por_viscosidad(self):
        alta = viscosity_factors(20000.0, 70.0)
        assert alta["capacity_factor"] == pytest.approx(55.0)   # el tope de 5000 SSU
        assert alta["clamped_ssu"]
        assert any("cavidad progresiva" in w for w in alta["warnings"])

    def test_avisa_cuando_la_centrifuga_deja_de_servir(self):
        alta = viscosity_factors(20000.0, 70.0)
        assert alta["warnings"], "por encima del rango tiene que advertir"

    def test_mas_viscosidad_castiga_mas(self):
        suave = viscosity_factors(100.0, 70.0)
        dura = viscosity_factors(3000.0, 70.0)
        assert dura["capacity_factor"] < suave["capacity_factor"]
        assert dura["new_efficiency"] < suave["new_efficiency"]


# ---------------------------------------------------------------------------
# 5. Paso 7 — el sentido de la corrección
# ---------------------------------------------------------------------------

class TestEquivalenteEnAgua:
    def test_el_caso_de_la_filmina(self):
        """1700 b/d y 5230 ft con el crudo → 1932 b/d y 5893 ft con agua."""
        f = viscosity_factors(ssu=650.0, pump_efficiency_pct=70.0)
        d = water_equivalent_duty(1700.0, 5230.0, f, sg_mixture=1.02)
        assert d["q_water"] == pytest.approx(1932.0, abs=1.0)
        assert d["h_water"] == pytest.approx(5893.0, abs=1.0)

    def test_divide_no_multiplica(self):
        """El error más común del procedimiento: la bomba pedida es MAYOR."""
        f = viscosity_factors(ssu=1000.0, pump_efficiency_pct=70.0)
        d = water_equivalent_duty(1000.0, 4000.0, f, sg_mixture=0.95)
        assert d["q_water"] > 1000.0
        assert d["h_water"] > 4000.0

    def test_ida_y_vuelta(self):
        """Corregir de agua a viscoso y volver devuelve el original."""
        f = viscosity_factors(ssu=800.0, pump_efficiency_pct=65.0)
        d = water_equivalent_duty(1500.0, 3000.0, f, sg_mixture=0.9)
        assert d["q_water"] * f["capacity_factor"] / 100 == pytest.approx(1500.0)
        assert d["h_water"] * f["head_factor"] / 100 == pytest.approx(3000.0)

    def test_la_potencia_lleva_gamma_o(self):
        """El factor de la tabla se multiplica por el SG de la mezcla."""
        f = viscosity_factors(ssu=650.0, pump_efficiency_pct=70.0)
        d = water_equivalent_duty(1700.0, 5230.0, f, sg_mixture=1.02)
        assert d["hp_multiplier"] == pytest.approx(1.173 * 1.02, rel=1e-6)

    def test_reporta_el_rendimiento_degradado(self):
        f = viscosity_factors(ssu=650.0, pump_efficiency_pct=70.0)
        d = water_equivalent_duty(1700.0, 5230.0, f, sg_mixture=1.02)
        assert d["degraded_efficiency"] == pytest.approx(0.466, abs=0.001)
        assert d["degraded_efficiency"] < 0.70

    def test_rechaza_entradas_imposibles(self):
        f = viscosity_factors(ssu=650.0, pump_efficiency_pct=70.0)
        with pytest.raises(ValueError, match="q_required"):
            water_equivalent_duty(0.0, 5230.0, f, 1.0)
        with pytest.raises(ValueError, match="h_required"):
            water_equivalent_duty(1700.0, 0.0, f, 1.0)


# ---------------------------------------------------------------------------
# 6. La regla de los 28 °API
# ---------------------------------------------------------------------------

class TestUmbralDeCrudoViscoso:
    """De 28 °API para arriba el crudo es liviano y no se corrige nada.

    El corte tiene respaldo numérico: evaluando la cadena completa en el
    umbral, los factores dan ≥ 99.6 %, o sea que la corrección ya es menor
    que el error de leer la viscosidad de un gráfico.
    """

    def test_el_umbral_es_28(self):
        assert VISCOUS_CRUDE_API_THRESHOLD == 28.0

    def test_liviano_no_es_viscoso(self):
        assert not is_viscous_crude(28.0)
        assert not is_viscous_crude(35.0)

    def test_pesado_si_es_viscoso(self):
        assert is_viscous_crude(27.9)
        assert is_viscous_crude(16.0)

    def test_justo_en_el_umbral_cuenta_como_liviano(self):
        """28.0 exactos es liviano: el criterio es «28 para arriba»."""
        assert not is_viscous_crude(28.0)

    def test_liviano_devuelve_factores_unitarios(self):
        r = evaluate_viscosity(30.0, 180.0, 200.0, pump_efficiency_pct=70.0)
        assert r["is_viscous"] is False
        assert r["capacity_factor"] == 100.0
        assert r["head_factor"] == 100.0
        assert r["hp_factor"] == 100.0
        assert r["viscosity"] is None
        assert "liviano" in r["reason"]

    def test_liviano_conserva_el_rendimiento_de_la_bomba(self):
        r = evaluate_viscosity(35.0, 180.0, 200.0, pump_efficiency_pct=68.0)
        assert r["new_efficiency"] == 68.0

    def test_pesado_corre_la_cadena_completa(self):
        r = evaluate_viscosity(16.0, 130.0, 50.0, 70.0, dead_oil_cp=150.0)
        assert r["is_viscous"] is True
        assert r["viscosity"] is not None
        assert r["capacity_factor"] < 100.0
        assert r["new_efficiency"] < 70.0

    def test_en_el_umbral_la_correccion_seria_despreciable(self):
        """Justifica dónde está puesto el corte: a 28 °API los factores son ~100 %.

        Los números se movieron al digitalizar la Fig. 4L(2): la lámina da
        18.8 cp a 120 °F donde Beggs-Robinson daba 12.1, así que la corrección
        en el umbral pasó de ~0.4 % a ~1 %. Sigue siendo menos que el error de
        leer una viscosidad de un gráfico, de modo que el corte de 28 °API
        —que además es el de Riling— se sostiene.
        """
        v = crude_viscosity_ssu(28.0, 120.0, 0.0)
        f = viscosity_factors(v["ssu"], 70.0)
        assert f["capacity_factor"] > 98.5
        assert f["head_factor"] > 99.0

        # Más caliente, la corrección se va a cero sola.
        v = crude_viscosity_ssu(28.0, 180.0, 0.0)
        f = viscosity_factors(v["ssu"], 70.0)
        assert f["capacity_factor"] > 99.5
        assert f["head_factor"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# 7. Paso 5 — corte de agua
# ---------------------------------------------------------------------------

class TestCorteDeAgua:
    def test_sin_dato_medido_queda_sin_realizar(self):
        """Riling dice «si hay datos disponibles»: sin dato no se inventa."""
        r = evaluate_viscosity(16.0, 130.0, 50.0, 70.0, dead_oil_cp=150.0)
        assert r["water_cut_correction"] == "no_realizada"
        assert any("SIN REALIZAR" in w for w in r["warnings"])

    def test_el_dato_medido_reemplaza_al_del_crudo_solo(self):
        """El caso de la filmina: 30 % de agua lleva 325 SSU a 650 SSU."""
        r = evaluate_viscosity(16.0, 130.0, 50.0, 70.0, dead_oil_cp=150.0,
                               measured_mixture_ssu=650.0)
        assert r["water_cut_correction"] == "medida"
        assert r["design_ssu"] == 650.0
        assert r["capacity_factor"] == pytest.approx(88.0, abs=0.01)
        assert r["head_factor"] == pytest.approx(88.75, abs=0.01)

    def test_el_agua_castiga_mas(self):
        """Ignorar el corte de agua subdimensiona el equipo."""
        sin = evaluate_viscosity(16.0, 130.0, 50.0, 70.0, dead_oil_cp=150.0)
        con = evaluate_viscosity(16.0, 130.0, 50.0, 70.0, dead_oil_cp=150.0,
                                 measured_mixture_ssu=650.0)
        assert con["capacity_factor"] < sin["capacity_factor"]
        assert con["new_efficiency"] < sin["new_efficiency"]

    def test_en_crudo_liviano_no_aplica(self):
        r = evaluate_viscosity(35.0, 180.0, 200.0, 70.0)
        assert r["water_cut_correction"] == "no_aplica"


# ---------------------------------------------------------------------------
# 8. Modelo Hydraulic Institute — los tres ejemplos publicados
# ---------------------------------------------------------------------------

class TestHydraulicInstitute:
    """Regresión contra Takács §4.2.2 y el paper original de Turzo en OGJ."""

    def test_ejemplo_4_1_parametro_de_correlacion(self):
        """Takács Ej. 4.1: 88 cSt sobre un BEP de 900 bpd y 21.8 ft."""
        f = hydraulic_institute_factors(88.0, 900.0, 21.8)
        assert f["y"] == pytest.approx(-4.276, abs=0.002)
        assert f["q_star"] == pytest.approx(23.34, abs=0.01)

    def test_ejemplo_4_1_factores_de_caudal_y_rendimiento(self):
        f = hydraulic_institute_factors(88.0, 900.0, 21.8)
        assert f["capacity_factor"] == pytest.approx(0.812, abs=0.001)
        assert f["efficiency_factor"] == pytest.approx(0.385, abs=0.001)

    def test_ejemplo_4_1_factores_de_altura(self):
        """Los cuatro C_H. El de 1.0 sigue la ECUACIÓN, no el ejemplo resuelto."""
        f = hydraulic_institute_factors(88.0, 900.0, 21.8)["head_factors"]
        assert f[0.6] == pytest.approx(0.890, abs=0.001)
        assert f[0.8] == pytest.approx(0.873, abs=0.001)
        assert f[1.0] == pytest.approx(0.829, abs=0.001)   # el libro imprime 0.844
        assert f[1.2] == pytest.approx(0.797, abs=0.001)

    def test_ejemplo_4_1_curva_corregida(self):
        f = hydraulic_institute_factors(88.0, 900.0, 21.8)
        puntos = hi_corrected_curve(CURVA_EJEMPLO_4_1, f)
        esperado = [(438.5, 24.8, 19.6), (584.6, 22.3, 23.2),
                    (730.8, 18.1, 24.7), (876.9, 12.1, 21.3)]
        for p, (q, h, e) in zip(puntos, esperado):
            assert p["q_bpd"] == pytest.approx(q, abs=0.3)
            assert p["head_ft"] == pytest.approx(h, abs=0.15)
            assert p["efficiency_pct"] == pytest.approx(e, abs=0.15)

    def test_turzo_ogj_2000(self):
        """El ejemplo del paper original: bomba de oleoducto, 55 cSt.

        Es el que dirime la errata de signo: con el término cuadrático en +,
        C_H,1.0 daría 0.9812 en vez de los 0.9810 publicados.
        """
        q_bpd = 9212.0 * 1440.0 / 42.0          # 9212 gpm -> bpd
        f = hydraulic_institute_factors(55.0, q_bpd, 770.0)
        assert f["y"] == pytest.approx(94.7, abs=0.05)
        assert f["q_star"] == pytest.approx(2.698, abs=0.001)
        assert f["capacity_factor"] == pytest.approx(0.9879, abs=0.0001)
        assert f["efficiency_factor"] == pytest.approx(0.9129, abs=0.0001)
        h = f["head_factors"]
        assert h[0.6] == pytest.approx(0.9898, abs=0.0001)
        assert h[0.8] == pytest.approx(0.9870, abs=0.0007)
        assert h[1.0] == pytest.approx(0.9810, abs=0.0001)
        assert h[1.2] == pytest.approx(0.9758, abs=0.0001)

    def test_el_signo_negativo_es_el_que_mantiene_el_orden(self):
        """Con el cuadrático en +, las curvas de 0.8 y 1.0 se cruzarían.

        La corrección no puede ser MÁS benigna en el BEP que al 80 % del BEP:
        justamente en el BEP es donde la bomba trabaja mejor. Con el signo
        impreso en la ecuación (−) el orden se mantiene a toda viscosidad.
        """
        for cst in (10.0, 100.0, 500.0, 900.0):
            h = hydraulic_institute_factors(cst, 5000.0, 25.0)["head_factors"]
            assert h[0.6] > h[0.8] > h[1.0] > h[1.2], f"se cruzan a {cst} cSt"

    def test_con_agua_el_ajuste_no_vuelve_exactamente_a_uno(self):
        """Documenta un sesgo del ajuste, no lo disimula.

        A 1 cSt —agua— los factores deberían ser exactamente 1.0 y no lo son:
        dan 0.99 en caudal y 0.95 en rendimiento. Es que Q* no se anula con la
        viscosidad, también depende del tamaño de la bomba. El sesgo de ~5 %
        en rendimiento es del ajuste, y es una de las razones por las que el
        modelo no se usa como camino principal de diseño.
        """
        f = hydraulic_institute_factors(1.0, 5000.0, 25.0)
        assert f["capacity_factor"] == pytest.approx(0.994, abs=0.005)
        assert f["efficiency_factor"] == pytest.approx(0.951, abs=0.005)
        assert f["efficiency_factor"] < 1.0

    def test_mas_viscosidad_castiga_mas(self):
        anterior = None
        for cst in (10.0, 50.0, 200.0, 800.0):
            f = hydraulic_institute_factors(cst, 5000.0, 25.0)
            if anterior is not None:
                assert f["capacity_factor"] < anterior["capacity_factor"]
                assert f["efficiency_factor"] < anterior["efficiency_factor"]
            anterior = f

    def test_el_tope_de_q_star_muerde_dentro_del_rango_declarado(self):
        """Hallazgo: el modelo se rompe antes de los 3000 cSt que declara.

        Sobre una bomba de tamaño BES (BEP 5000 bpd, 25 ft/etapa) el ajuste
        pierde sentido alrededor de los 1000 cSt, un tercio del techo publicado.
        El techo de 3000 cSt supone bombas de oleoducto, que son con las que se
        levantaron los diagramas originales.
        """
        assert HI_Q_STAR_MAX == pytest.approx(57.27, abs=0.01)
        hydraulic_institute_factors(900.0, 5000.0, 25.0)     # todavía entra
        with pytest.raises(ValueError, match="tope"):
            hydraulic_institute_factors(3000.0, 5000.0, 25.0)

    def test_una_bomba_de_oleoducto_si_llega_a_3000_cst(self):
        """La misma viscosidad sobre una bomba grande sí entra en el modelo."""
        f = hydraulic_institute_factors(3000.0, 300_000.0, 500.0)
        assert f["q_star"] < HI_Q_STAR_MAX
        assert 0.0 < f["capacity_factor"] < 1.0

    def test_el_punto_de_cierre_no_se_corrige(self):
        """A caudal cero no hay fricción interna: la altura de cierre no cambia."""
        f = hydraulic_institute_factors(88.0, 900.0, 21.8)
        puntos = hi_corrected_curve(CURVA_EJEMPLO_4_1, f, shutoff_head_ft=33.0)
        assert len(puntos) == 5
        assert puntos[0]["q_bpd"] == 0.0
        assert puntos[0]["head_ft"] == 33.0
        assert puntos[0]["corrected"] is False

    def test_avisa_fuera_del_rango_validado(self):
        """Casi todo diseño BES cae por debajo del piso de caudal del modelo."""
        f = hydraulic_institute_factors(88.0, 1200.0, 21.8)
        assert any("rango validado" in w for w in f["warnings"])
        assert HI_RATE_RANGE_BPD[0] == 3_400.0
        assert HI_HEAD_RANGE_FT == (6.0, 600.0)
        assert HI_VISCOSITY_RANGE_CST == (4.0, 3_000.0)

    def test_dentro_del_rango_no_avisa(self):
        f = hydraulic_institute_factors(88.0, 10_000.0, 25.0)
        assert f["warnings"] == []

    @pytest.mark.parametrize("cst,q,h", [(0, 900, 21.8), (88, 0, 21.8), (88, 900, 0)])
    def test_rechaza_entradas_no_positivas(self, cst, q, h):
        with pytest.raises(ValueError):
            hydraulic_institute_factors(cst, q, h)

    def test_falla_explicito_si_falta_un_punto_de_la_curva(self):
        f = hydraulic_institute_factors(88.0, 900.0, 21.8)
        incompleta = {k: v for k, v in CURVA_EJEMPLO_4_1.items() if k != 1.2}
        with pytest.raises(ValueError, match="1.2"):
            hi_corrected_curve(incompleta, f)


# ---------------------------------------------------------------------------
# 9. Conversión cerrada y potencia al freno
# ---------------------------------------------------------------------------

class TestConversionYPotencia:

    def test_ec_4_14_reproduce_el_ejemplo(self):
        assert cst_to_ssu_takacs(88.0) == pytest.approx(402.0, abs=1.0)

    def test_ec_4_14_cubre_los_extremos_declarados(self):
        """El libro dice «4 a 3000 cSt (40 a 15 000 SSU)»."""
        assert cst_to_ssu_takacs(4.0) == pytest.approx(40.0, abs=1.5)
        assert cst_to_ssu_takacs(3000.0) > 13_000.0

    def test_ec_4_14_es_monotona(self):
        anterior = 0.0
        for cst in (1, 4, 10, 50, 88, 400, 1000, 3000):
            v = cst_to_ssu_takacs(cst)
            assert v > anterior
            anterior = v

    def test_takacs_y_astm_no_son_la_misma_cuenta(self):
        """Se documenta la brecha, no se disimula: van ~1-2 % aparte."""
        for cst in (50.0, 88.0, 400.0, 1000.0):
            a, t = cst_to_ssu(cst), cst_to_ssu_takacs(cst)
            assert abs(a - t) / a < 0.03, f"brecha inesperada a {cst} cSt"

    def test_ec_4_12_con_rendimiento_en_fraccion(self):
        """El BEP con agua del Ej. 4.1 tiene que dar los 0.225 HP del Ej. 4.2."""
        assert brake_horsepower(900.0, 21.8, 1.0, 0.64) == pytest.approx(0.225, abs=0.002)

    def test_ec_4_12_rechaza_el_rendimiento_en_porcentaje(self):
        """Pasar 64 en vez de 0.64 es el error que el libro induce."""
        with pytest.raises(ValueError, match="fraction"):
            brake_horsepower(900.0, 21.8, 1.0, 64.0)

    def test_la_potencia_sube_con_la_densidad_y_baja_con_el_rendimiento(self):
        base = brake_horsepower(900.0, 21.8, 1.0, 0.64)
        assert brake_horsepower(900.0, 21.8, 0.9, 0.64) < base
        assert brake_horsepower(900.0, 21.8, 1.0, 0.32) == pytest.approx(2 * base)


# ---------------------------------------------------------------------------
# 10. Tabla 4.1 de Centrilift — la tercera fuente
# ---------------------------------------------------------------------------

class TestTablaCentrilift:

    def test_ejemplo_4_2(self):
        c = centrilift_factors(402.0)
        assert c["capacity_factor"] == pytest.approx(0.847, abs=0.002)
        assert c["head_factor"] == pytest.approx(0.909, abs=0.002)
        assert c["efficiency_factor"] == pytest.approx(0.497, abs=0.002)
        assert c["bhp_factor"] == pytest.approx(1.549, abs=0.003)

    def test_ejemplo_4_2_bep_corregido(self):
        c = centrilift_factors(402.0)
        assert c["capacity_factor"] * 900 == pytest.approx(762, abs=2)
        assert c["head_factor"] * 21.8 == pytest.approx(19.8, abs=0.1)
        assert c["efficiency_factor"] * 64 == pytest.approx(31.8, abs=0.2)
        assert c["bhp_factor"] * 0.22 == pytest.approx(0.34, abs=0.01)

    def test_comparte_grilla_con_las_tablas_de_brown(self):
        """Dos escaneos independientes de la misma familia de tablas."""
        d = json.loads(Path(_TABLES_PATH).read_text(encoding="utf-8"))
        grilla = [r["ssu"] for r in d["centrilift_table"]["rows"]]
        assert grilla == [r["ssu"] for r in d["tables"]["60"]["rows"]]
        assert grilla == [r["ssu"] for r in d["tables"]["70"]["rows"]]

    def test_centrilift_es_mas_severa_en_caudal_que_brown(self):
        """Las fuentes NO coinciden, y el test fija en cuánto difieren.

        Centrilift queda por debajo de la tabla de 60 % de Brown en capacidad y
        por encima en altura. No es un promedio de las dos: es otra fuente con
        otro criterio. La dispersión es el dato honesto del método tabulado.
        """
        d = json.loads(Path(_TABLES_PATH).read_text(encoding="utf-8"))
        pares = list(zip(d["tables"]["60"]["rows"], d["centrilift_table"]["rows"]))
        cq_menor = sum(1 for r60, cl in pares
                       if cl["capacity_factor"] <= r60["capacity_factor"])
        ch_mayor = sum(1 for r60, cl in pares
                       if cl["head_factor"] >= r60["head_factor"])
        assert cq_menor >= 15, "Centrilift debería ser más severa en caudal"
        assert ch_mayor >= 17, "Centrilift debería ser más benigna en altura"

    def test_la_dispersion_entre_fuentes_esta_acotada_y_documentada(self):
        """En el extremo viscoso las tablas llegan a ~13 puntos de diferencia."""
        d = json.loads(Path(_TABLES_PATH).read_text(encoding="utf-8"))
        brecha = max(
            abs(cl["head_factor"] - r60["head_factor"])
            for r60, cl in zip(d["tables"]["60"]["rows"], d["centrilift_table"]["rows"])
        )
        assert 12.0 < brecha < 25.0
        assert "dispersión entre fuentes" in d["centrilift_table"]["_contraste"]

    def test_la_potencia_crece_monotona(self):
        d = json.loads(Path(_TABLES_PATH).read_text(encoding="utf-8"))
        filas = d["centrilift_table"]["rows"]
        for lo, hi in zip(filas, filas[1:]):
            assert hi["bhp_factor"] > lo["bhp_factor"]

    def test_la_errata_de_4000_ssu_esta_transcrita_y_avisada(self):
        """Se guarda tal como está impreso; la advertencia lo señala."""
        t = json.loads(Path(_TABLES_PATH).read_text(encoding="utf-8"))["centrilift_table"]
        fila = next(r for r in t["rows"] if r["ssu"] == 4000)
        assert fila["efficiency_factor"] == pytest.approx(27.8)   # rompe la tendencia
        assert "imprenta" in t["_anomalia"].lower()
        assert any("4000" in w for w in centrilift_factors(3500.0)["warnings"])

    def test_fuera_de_rango_acota_sin_extrapolar(self):
        bajo = centrilift_factors(10.0)
        alto = centrilift_factors(50_000.0)
        assert bajo["clamped"] and alto["clamped"]
        assert bajo["capacity_factor"] == pytest.approx(1.0)
        assert alto["capacity_factor"] == pytest.approx(0.479)

    def test_rechaza_viscosidad_no_positiva(self):
        with pytest.raises(ValueError):
            centrilift_factors(0.0)


# ---------------------------------------------------------------------------
# 11. Enganche al motor de diseño (etapa 5)
# ---------------------------------------------------------------------------

from bes.catalogs.loader import CatalogManager
from bes.core.models import (
    DesignObjectives, DriveMechanism, Fluid, IPRMethod, Reservoir,
    SurfaceConditions, WellGeometry,
)
from bes.core.pump_design import (
    VISCOSITY_TEMP_TOLERANCE_F, _pump_max_efficiency_pct, _viscosity_context,
    design_pump_complete,
)


def _pozo(oil_api: float, mu_dead: float, temp_ref: float) -> dict:
    """Mismo pozo, distinto crudo. Admisión a 5600 ft → 136 °F con este perfil."""
    return dict(
        reservoir=Reservoir(
            static_pressure=2500.0, bubble_point=1500.0, productivity_index=1.5,
            ipr_method=IPRMethod.VOGEL, reservoir_temp=140.0,
            drive_mechanism=DriveMechanism.SOLUTION_GAS),
        fluid=Fluid(
            oil_api=oil_api, water_cut=0.20, gor=50.0, gas_sg=0.7, water_sg=1.02,
            oil_viscosity_dead=mu_dead, viscosity_temp_ref=temp_ref,
            bubble_point_pressure=1500.0, h2s_content=0.0, co2_content=0.0,
            sand_production=False),
        well=WellGeometry(
            total_depth=6000.0, casing_od=7.0, casing_weight=26.0, casing_id=6.276,
            tubing_od=2.875, tubing_id=2.441, perforations_top=5800.0,
            perforations_bottom=5900.0, deviation_max=5.0,
            wellhead_temp=80.0),
        surface=SurfaceConditions(
            wellhead_pressure_required=150.0, flowline_length=1000.0, flowline_id=3.0,
            flowline_elevation_change=0.0, separator_pressure=80.0,
            power_supply_voltage=480.0, frequency=60.0),
        objectives=DesignObjectives(
            target_flow_rate=1500.0, safety_margin_depth=200.0, allow_gas_venting=True,
            max_gip=0.10, design_life_years=5.0, use_vsd=False,
            gas_fraction_pc_threshold=1.0),
        pump_setting_depth=5600.0,
        catalog_manager=CatalogManager(),
    )


def _misma_bomba(oil_api, mu_dead, temp_ref, modelo="DN1800"):
    r = design_pump_complete(**_pozo(oil_api, mu_dead, temp_ref))
    return next((c for c in r if c["pump_model"] == modelo), None)


class TestEngancheAlMotorDeDiseno:

    def test_crudo_liviano_no_toca_nada(self):
        c = _misma_bomba(32.0, 2.0, 136.0)
        assert c is not None
        assert c["viscosity_correction"] is None
        assert c["design_flow_rate"] == pytest.approx(1500.0)
        assert c["design_head_ft"] == pytest.approx(c["tdh_ft"])
        assert not [f for f in c["formulas"] if f["key"].startswith("visc")]

    def test_crudo_pesado_busca_contra_el_equivalente_en_agua(self):
        """Se DIVIDE: la bomba se busca contra más caudal y más altura."""
        c = _misma_bomba(16.0, 150.0, 136.0)
        assert c is not None
        v = c["viscosity_correction"]
        assert v is not None
        assert c["design_flow_rate"] > 1500.0
        assert c["design_head_ft"] > c["tdh_ft"]
        assert c["design_flow_rate"] == pytest.approx(
            1500.0 / (v["capacity_factor"] / 100.0))
        assert c["design_head_ft"] == pytest.approx(
            c["tdh_ft"] / (v["head_factor"] / 100.0))

    def test_crudo_pesado_pide_mas_etapas_y_mas_potencia(self):
        liviano = _misma_bomba(32.0, 2.0, 136.0)
        pesado = _misma_bomba(16.0, 150.0, 136.0)
        assert pesado["stages"] > liviano["stages"]
        assert pesado["total_pump_hp"] > liviano["total_pump_hp"]

    def test_la_potencia_lleva_el_factor_de_la_tabla_una_sola_vez(self):
        """C_HP se aplica al HP de agua, que YA trae el SG. No se duplica γ_o."""
        c = _misma_bomba(16.0, 150.0, 136.0)
        v = c["viscosity_correction"]
        hp = next(f for f in c["formulas"] if f["key"] == "visc_hp")
        assert hp["result"] == pytest.approx(c["total_pump_hp"], rel=1e-9)
        assert hp["inputs"]["C_HP"] == pytest.approx(v["hp_factor"] / 100.0)
        # El HP de agua que entra ya trae el SG del fluido: C_HP entra una vez.
        assert hp["result"] == pytest.approx(
            hp["inputs"]["HP_agua"] * hp["inputs"]["C_HP"])

    def test_la_traza_sale_completa(self):
        c = _misma_bomba(16.0, 150.0, 136.0)
        claves = [f["key"] for f in c["formulas"]]
        for k in ("visc_q_water", "visc_h_water", "visc_hp"):
            assert k in claves
        # y en orden: primero el equivalente, después las etapas
        assert claves.index("visc_q_water") < claves.index("stages")

    def test_el_rendimiento_degradado_se_reporta(self):
        c = _misma_bomba(16.0, 150.0, 136.0)
        v = c["viscosity_correction"]
        assert 0 < v["degraded_efficiency"] * 100 < v["pump_max_efficiency_pct"]

    def test_el_corte_de_agua_sigue_sin_realizarse(self):
        """La etapa 6 está bloqueada: se dice, no se disimula."""
        c = _misma_bomba(16.0, 150.0, 136.0)
        assert c["viscosity_correction"]["water_cut_correction"] == "no_realizada"
        assert any("SIN REALIZAR" in w for w in c["viscosity_correction"]["warnings"])

    def test_no_repite_avisos(self):
        c = _misma_bomba(16.0, 150.0, 136.0)
        avisos = c["viscosity_correction"]["warnings"]
        assert len(avisos) == len(set(avisos))


class TestTemperaturaDeEvaluacion:

    def test_se_evalua_en_la_admision_no_en_el_fondo(self):
        """136 °F en la admisión (5600 ft), no los 140 °F de fondo."""
        p = _pozo(16.0, 150.0, 136.0)
        v = _viscosity_context(p["fluid"], p["well"], p["pump_setting_depth"],
                           p["reservoir"].reservoir_temp)
        assert v["intake_temp_f"] == pytest.approx(136.0, abs=0.5)
        assert v["intake_temp_f"] < p["reservoir"].reservoir_temp

    def test_usa_la_viscosidad_medida_si_esta_a_la_temperatura_correcta(self):
        p = _pozo(16.0, 150.0, 136.0)
        v = _viscosity_context(p["fluid"], p["well"], p["pump_setting_depth"],
                           p["reservoir"].reservoir_temp)
        assert v["viscosity"]["dead_oil_source"] == "medido"
        assert v["viscosity"]["mu_dead_cp"] == 150.0

    def test_descarta_la_medida_si_es_a_otra_temperatura(self):
        """No se extrapola un dato medido: la viscosidad es exponencial con T."""
        p = _pozo(16.0, 150.0, 60.0)      # medida a 60 °F, admisión a 136 °F
        v = _viscosity_context(p["fluid"], p["well"], p["pump_setting_depth"],
                           p["reservoir"].reservoir_temp)
        assert v["viscosity"]["dead_oil_source"] == "fig_4L_2"
        assert any("referida a" in w for w in v["warnings"])

    def test_la_tolerancia_es_la_declarada(self):
        assert VISCOSITY_TEMP_TOLERANCE_F == 5.0
        p = _pozo(16.0, 150.0, 136.0 + 4.0)          # dentro
        assert _viscosity_context(
            p["fluid"], p["well"], p["pump_setting_depth"],
            p["reservoir"].reservoir_temp
        )["viscosity"]["dead_oil_source"] == "medido"
        p = _pozo(16.0, 150.0, 136.0 + 20.0)         # fuera
        assert _viscosity_context(
            p["fluid"], p["well"], p["pump_setting_depth"],
            p["reservoir"].reservoir_temp
        )["viscosity"]["dead_oil_source"] == "fig_4L_2"


class TestUnidadDelRendimiento:
    """El dominio guarda fracción [0,1]; las tablas se indexan por porcentaje."""

    def test_el_helper_convierte_a_porcentaje(self):
        cat = CatalogManager()
        pump = next(p for p in cat.get_all_pumps() if p.model == "DN1800")
        frac = max(pt.efficiency for pt in pump.points)
        assert frac <= 1.0
        assert _pump_max_efficiency_pct(pump) == pytest.approx(frac * 100.0)

    def test_las_tablas_rechazan_la_fraccion(self):
        """Pasar 0.7 donde va 70 daba factores plausibles pero equivocados."""
        with pytest.raises(ValueError, match="porcentaje"):
            viscosity_factors(365.0, 0.7)

    def test_y_aceptan_el_porcentaje(self):
        f = viscosity_factors(365.0, 70.0)
        assert 0 < f["capacity_factor"] <= 100
