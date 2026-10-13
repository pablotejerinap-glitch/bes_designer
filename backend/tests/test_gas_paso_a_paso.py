"""Método nuevo de gas, paso a paso. Cada paso se contrasta con la tesis Inv_83338."""
import math

import pytest

from bes.core.gas_paso_a_paso import paso1_ipr_vogel

# Pozo «Facultad 01» de la tesis Inv_83338 (caso con gas externo de la app).
PR, PB, PWF_T, Q_T, Q_OBJ = 888.617, 1863.26, 842.053, 691.82, 4070.70


class TestPaso1IPR:
    def test_reproduce_la_pwf_de_la_tesis(self):
        pwf, pasos = paso1_ipr_vogel(PR, PB, PWF_T, Q_T, Q_OBJ)
        assert pwf == pytest.approx(570.35, abs=0.01)   # tesis, pág. 40
        assert [p.cita for p in pasos] == [
            "Brown Vol. 4, Ejemplo #5 (pág. 14)",
            "Brown Vol. 4, ec. 2.19 (pág. 14)",
            "Brown Vol. 4, ec. 2.20 (pág. 14)",
        ]

    def test_ejemplo_5_de_brown(self):
        """Brown Vol. 4, Ej. #5 (pág. 14): q_o max = 250 b/d; q = 211 b/d a 800 psi."""
        _, pasos = paso1_ipr_vogel(2400, 2400, 1800, 100, 211)
        assert pasos[1].valor == pytest.approx(250, abs=0.5)
        pwf, _ = paso1_ipr_vogel(2400, 2400, 1800, 100, 211.0)
        assert pwf == pytest.approx(800, abs=5)

    def test_subsaturado_ejemplo_8_de_brown(self):
        """Brown Vol. 4, Ejemplo #8 (pág. 16): Pr 4000, Pb 3000, ensayo 600 b/d a 2000 psi.
        La curva da 162 b/d a 3500 psi y 780 b/d a 1000 psi."""
        pwf, _ = paso1_ipr_vogel(4000, 3000, 2000, 600, 162)
        assert pwf == pytest.approx(3500, abs=5)
        pwf, pasos = paso1_ipr_vogel(4000, 3000, 2000, 600, 780)
        assert pwf == pytest.approx(1000, abs=10)
        assert "ec. 2.30" in pasos[0].cita and "ec. 2.29" in pasos[-1].cita

    def test_caudal_mayor_que_qmax(self):
        with pytest.raises(ValueError):
            paso1_ipr_vogel(PR, PB, PWF_T, Q_T, 8000)


class TestPaso2aPVT:
    def test_z_y_bg_unicos_de_ahmed(self):
        """Una sola correlación de z (DAK + pseudocríticas de Standing, Ahmed) y de Bg."""
        from bes.core.gas_paso_a_paso import paso2a_pvt
        from bes.core.pvt import gas_bg, gas_z_factor
        r, pasos = paso2a_pvt(1000 - 14.7, 150, 30, 0.6, 1.0, 300)
        assert r["z"] == pytest.approx(gas_z_factor(1000.0, 150, 0.6))
        assert r["bg"] == pytest.approx(gas_bg(1000.0, 150, r["z"]))
        d = {p.nombre: p.valor for p in pasos}
        # Ahmed ecs. 2-18 y 2-19 con γg = 0,6
        assert d["Presión pseudocrítica (Standing)"] == pytest.approx(677 + 15 * 0.6 - 37.5 * 0.36)
        assert d["Temperatura pseudocrítica (Standing)"] == pytest.approx(168 + 325 * 0.6 - 12.5 * 0.36)

    def test_bo_unico_standing_de_ahmed(self):
        """Una sola correlación de Bo (Ahmed ec. 2-84) en todo el programa."""
        from bes.core.gas_paso_a_paso import paso2a_pvt
        from bes.core.pvt import standing_bo
        r, _ = paso2a_pvt(570.35, 197.6, 21, 0.65, 1.012, 67.4)
        assert r["bo"] == pytest.approx(standing_bo(r["rs"], 197.6, 21, 0.65))

    def test_pozo_de_la_tesis_en_el_fondo(self):
        from bes.core.gas_paso_a_paso import paso2a_pvt
        r, _ = paso2a_pvt(570.35, 197.6, 21, 0.65, 1.012, 67.4)
        assert r["p_abs"] == pytest.approx(585.05)
        # Papay (Takács ec. 4.26) con pseudocríticas de Standing (Ahmed ecs. 2-18 y 2-19).
        assert r["z"] == pytest.approx(0.94992, abs=0.0001)
        assert r["bg"] * 1000 == pytest.approx(5.376, abs=0.001)


class TestPaso2bcMezcla:
    def test_pozo_de_la_tesis_en_el_fondo(self):
        from bes.core.gas_paso_a_paso import paso2a_pvt, paso2bc_mezcla
        pvt, _ = paso2a_pvt(570.35, 197.6, 21, 0.65, 1.012, 67.4)
        m, _ = paso2bc_mezcla(4070.70, 0.89, 67.4, 0.65, 1.012, pvt)
        assert m["qo"] == pytest.approx(447.777, abs=0.001)
        # La masa no depende del PVT: es la de la tesis (pág. 43) con BOPD = 447,777.
        assert m["masa"] == pytest.approx((447.777 * 0.927869 + 3622.923 * 1.012) * 62.4 * 5.615
                                          + 67.4 * 447.777 * 0.65 * 0.0764, rel=1e-6)
        assert m["sg"] == pytest.approx(m["masa"] / (m["v_total"] * 5.615 * 62.4))


class TestPaso3PIP:
    def test_con_el_sg_de_la_tesis_da_su_pip(self):
        """Tesis pág. 43: 570,35 − 0,4039 × (7391,71 − 6686,332) = 285,39 psi."""
        from bes.core.gas_paso_a_paso import paso3_pip
        pip, _ = paso3_pip(570.35, 0.9330, 7391.71, 6686.332)
        assert pip == pytest.approx(285.39, abs=0.05)

    def test_pozo_de_la_tesis_con_nuestro_sg(self):
        from bes.core.gas_paso_a_paso import paso2a_pvt, paso2bc_mezcla, paso3_pip
        pvt, _ = paso2a_pvt(570.35, 197.6, 21, 0.65, 1.012, 67.4)
        m, _ = paso2bc_mezcla(4070.70, 0.89, 67.4, 0.65, 1.012, pvt)
        pip, _ = paso3_pip(570.35, m["sg"], 7391.71, 6686.332)
        assert pip == pytest.approx(570.35 - 0.433 * m["sg"] * 705.378, abs=1e-6)


class TestPaso4GorSuccion:
    def test_gor_bomba_es_rs_mas_el_gas_libre_no_separado(self):
        from bes.core.gas_paso_a_paso import paso2a_pvt, paso2bc_mezcla, paso4_gor_succion
        pvt, _ = paso2a_pvt(277.36, 184.469, 21, 0.65, 1.012, 67.4)
        m, _ = paso2bc_mezcla(4070.70, 0.89, 67.4, 0.65, 1.012, pvt)
        r, _ = paso4_gor_succion(m, pvt, 0.70)
        assert r["gor_bomba"] == pytest.approx(pvt["rs"] + 0.30 * (67.4 - pvt["rs"]), rel=1e-9)
        # separar el gas equivale a escalar la relación gas/líquido por (1 − η)
        ra = r["f_adm"] / (1 - r["f_adm"]); rb = r["f_bomba"] / (1 - r["f_bomba"])
        assert rb == pytest.approx(ra * 0.30, rel=1e-9)

    def test_sin_separador_no_cambia_nada(self):
        from bes.core.gas_paso_a_paso import paso2a_pvt, paso2bc_mezcla, paso4_gor_succion
        pvt, _ = paso2a_pvt(277.36, 184.469, 21, 0.65, 1.012, 67.4)
        m, _ = paso2bc_mezcla(4070.70, 0.89, 67.4, 0.65, 1.012, pvt)
        r, _ = paso4_gor_succion(m, pvt, 0.0)
        assert r["gor_bomba"] == pytest.approx(67.4) and r["f_bomba"] == pytest.approx(r["f_adm"])


class TestPaso5Descarga:
    def test_sin_gas_libre_la_mezcla_es_el_liquido(self):
        from bes.core.gas_paso_a_paso import gradiente_pc
        _, pasos = gradiente_pc(3000, 180, 4000, 0.89, 36.7, 21, 0.65, 1.012, 2.441)
        d = {p.nombre: p.valor for p in pasos}
        assert d["Caudal de gas libre en el punto"] == 0
        assert d["Densidad de la mezcla"] == pytest.approx(d["Densidad del líquido"])

    def test_la_descarga_es_la_suma_de_los_tramos(self):
        from bes.core.gas_paso_a_paso import paso5_descarga
        r, _ = paso5_descarga(100, 60, 184.469, 6686.332, 4070.70, 0.89, 36.712, 21, 0.65, 1.012, 2.441)
        assert len(r["tramos"]) == 50
        assert r["p_descarga"] == pytest.approx(100 + sum(t["dp"] for t in r["tramos"]))
        assert all(t["p1"] > t["p0"] for t in r["tramos"])


class TestPaso6Seleccion:
    def test_pozo_de_la_tesis_elige_la_d5800n(self):
        """Tesis pág. 46: con estos caudales elige la REDA D5800N."""
        from bes.catalogs.loader import CatalogManager
        from bes.core.gas_paso_a_paso import paso6_seleccion
        r, _ = paso6_seleccion(4258.54, 4178.75, 4.892, 50.0, CatalogManager())
        assert r["modelo"] == "D5800N"
        # empata en eficiencia con la D5850N y gana por diámetro
        modelos = [c["modelo"] for c in r["candidatas"]]
        assert "D5850N" in modelos

    def test_sin_bomba_posible(self):
        from bes.catalogs.loader import CatalogManager
        from bes.core.gas_paso_a_paso import paso6_seleccion
        with pytest.raises(ValueError):
            paso6_seleccion(4000, 3900, 3.0, 60.0, CatalogManager())


class TestPaso7Incrementos:
    @pytest.fixture(scope="class")
    def base(self):
        from bes.catalogs.loader import CatalogManager
        from bes.core.affinity import pump_at_frequency
        cm = CatalogManager()
        b = pump_at_frequency(next(p for p in cm.get_all_pumps() if p.model == "D5800N"), 50)
        return cm, b

    def test_cada_escalon_cierra(self, base):
        from bes.core.gas_paso_a_paso import paso7_incrementos
        cm, b = base
        r, _ = paso7_incrementos(277.363, 3159.429, 184.469, 4070.70, 0.89, 36.712, 21, 0.65, 1.012, b, cm)
        for t in r["tramos"]:
            assert t["n"] == pytest.approx(t["dp"] / (t["h"] * t["grad"]))
            assert t["hp"] == pytest.approx(t["n"] * t["hp_et"] * t["sg"])
        assert r["etapas"] == math.ceil(r["etapas_exactas"])
        assert sum(t["dp"] for t in r["tramos"]) == pytest.approx(3159.429 - 277.363)

    def test_converge_al_achicar_el_escalon(self, base):
        """Como la Tab. 5 de la tesis: con más escalones el resultado se estabiliza."""
        from bes.core.gas_paso_a_paso import paso7_incrementos
        cm, b = base
        n = [paso7_incrementos(277.363, 3159.429, 184.469, 4070.70, 0.89, 36.712, 21, 0.65, 1.012,
                               b, cm, inc)[0]["etapas_exactas"] for inc in (2882.066, 720.5, 180.1, 100)]
        assert abs(n[-1] - n[-2]) < abs(n[0] - n[1])
        assert n[-1] == pytest.approx(422.5, abs=0.5)


def test_endpoint_paso_a_paso_pozo_de_la_tesis():
    from fastapi.testclient import TestClient
    from bes.api.main import app
    from tests.test_memoria import CASOS  # noqa: F401  (misma carpeta de datos)
    body = {
        "reservoir": {"static_pressure": 888.617, "bubble_point": 1863.26, "test_pwf": 842.053,
                      "test_rate": 691.82, "ipr_method": "vogel", "reservoir_temp": 197.6,
                      "drive_mechanism": "solution_gas"},
        "fluid": {"oil_api": 21, "water_cut": 0.89, "gor": 67.4, "gas_sg": 0.65, "water_sg": 1.012,
                  "bubble_point_pressure": 1863.26},
        "well": {"total_depth": 7391.71, "casing_od": 5.5, "casing_weight": 15.5, "casing_id": 5.012,
                 "tubing_od": 2.875, "tubing_id": 2.441, "perforations_top": 7341.71,
                 "perforations_bottom": 7391.71, "deviation_max": 0, "wellhead_temp": 60,
                 "pump_setting_depth": 6686.332},
        "surface": {"wellhead_pressure_required": 100, "flowline_length": 1000, "flowline_id": 4,
                    "flowline_elevation_change": 0, "separator_pressure": 100,
                    "power_supply_voltage": 4160, "frequency": 50},
        "objectives": {"target_flow_rate": 4070.70, "safety_margin_depth": 0, "allow_gas_venting": False,
                       "max_gip": 1.0, "design_life_years": 5, "use_vsd": False},
    }
    r = TestClient(app).post("/api/gas/paso-a-paso", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["resumen"]["bomba"] == "REDA D5800N"
    # 410 con el factor de la Fig. 2.36 de Brown Vol. 1 (antes 423 con el ajuste 0,030·N^−0,19).
    assert j["resumen"]["etapas"] == 410
    zonas = [f["zona"] for f in j["tabla_evolucion"]]
    assert zonas[0] == "fondo" and "bomba" in zonas and zonas[-1] == "tubing"
    assert len(j["bloques"]) == 15
    assert j["resumen"]["cable"] == "REDA Redared #2 AWG CU"
    assert j["resumen"]["tablero"] == "FixStar 3900-70" and j["resumen"]["transformador_kva"] == 400
    assert j["resumen"]["motor"] == "REDA-456-RX-TYPE-192HP-1890V" and j["resumen"]["motor_n"] == 2
    assert j["resumen"]["motor_voltaje"] == pytest.approx(3150)
    assert j["resumen"]["v_anular"] == pytest.approx(11.58, abs=0.01)
    body["well"]["casing_id"], body["well"]["casing_weight"] = 4.892, 17
    r2 = TestClient(app).post("/api/gas/paso-a-paso", json=body)
    assert r2.status_code == 422 and "15.96 ft/s" in r2.text
    assert j["resumen"]["protector"] == "LSLSL-HL-HSS"
    assert j["resumen"]["elastomero"] == "Neoprene/Nitrile"
    assert j["resumen"]["serie_motor"] == "456"
    assert j["resumen"]["eje"] == "alta resistencia"
    assert j["resumen"]["carcasa"] == "estándar"
    assert j["resumen"]["carcasas"] == [
        {"carcasa": "150", "etapas": 67, "cantidad": 6, "largo_ft": 21.7},
        {"carcasa": "20", "etapas": 8, "cantidad": 1, "largo_ft": 3.5},
    ]


class TestPaso8EjeCarcasas:
    """REDA D5800N (catálogo págs. 182 y 184) con los números del pozo de la tesis."""

    @pytest.fixture(scope="class")
    def cm(self):
        import bes.catalogs.loader as L
        return next(getattr(L, n) for n in dir(L) if n.endswith("Manager"))()

    def test_limites_leidos_del_catalogo(self, cm):
        b = next(p for p in cm.get_all_pumps() if p.model == "D5800N")
        assert (b.shaft_hp_limit_std, b.shaft_hp_limit_high_strength) == (255, 410)
        assert b.housing_burst_psi == {"standard": 5000, "buttress": 6000, "welded": 6000}
        assert b.fuente_mecanica.endswith("pág. 184") and b.fuente_carcasas.endswith("pág. 182")

    def test_eje_a_50_hz_coincide_con_la_hoja_de_50_hz(self, cm):
        """Takács ec. 5.12: 255 y 410 hp a 60 Hz → 213 y 342 hp, lo que imprime REDA pág. 186."""
        from bes.core.gas_paso_a_paso import paso8_eje_carcasas
        r, _ = paso8_eje_carcasas("D5800N", 423, 301.41, 0.423203, 50, cm)
        assert r["hp_eje_std"] == pytest.approx(213, abs=0.5)
        assert r["hp_eje_ar"] == pytest.approx(342, abs=0.5)
        assert r["eje"] == "alta resistencia"

    def test_presion_de_carcasa_takacs_5_13(self, cm):
        from bes.core.gas_paso_a_paso import paso8_eje_carcasas
        r, _ = paso8_eje_carcasas("D5800N", 423, 301.41, 0.423203, 50, cm)
        assert r["p_max"] == pytest.approx(29.5403 * 423 * 0.423203 * (50 / 60) ** 2, rel=1e-4)
        assert r["carcasa"] == "estándar" and r["limite_carcasa"] == 5000

    def test_arreglo_exacto_y_largo(self, cm):
        from bes.core.gas_paso_a_paso import paso8_eje_carcasas
        r, _ = paso8_eje_carcasas("D5800N", 423, 301.41, 0.423203, 50, cm)
        assert r["n_carcasas"] == 7 and r["etapas_ciegas"] == 0
        assert r["largo_ft"] == pytest.approx(137.9)

    def test_eje_insuficiente(self, cm):
        from bes.core.gas_paso_a_paso import paso8_eje_carcasas
        with pytest.raises(ValueError):
            paso8_eje_carcasas("D5800N", 423, 400, 0.4232, 50, cm)


class TestPaso9Protector:
    """REDA D5800N: tabla de tándem pág. 183, protectores pág. 407, elastómeros pág. 404."""

    @pytest.fixture(scope="class")
    def cm(self):
        import bes.catalogs.loader as L
        return next(getattr(L, n) for n in dir(L) if n.endswith("Manager"))()

    def test_tabla_de_tandem_leida(self, cm):
        b = next(p for p in cm.get_all_pumps() if p.model == "D5800N")
        assert b.tandem["etapas_cojinete_hl"] == 197 and b.tandem["etapas_max_tabla"] == 237
        assert b.tandem["tipo_etapa"] == "compression"

    def test_pozo_de_la_tesis(self, cm):
        from bes.core.gas_paso_a_paso import paso9_protector
        r, _ = paso9_protector("D5800N", 423, "alta resistencia", 197.6, 0, cm)
        assert r["protector"] == "LSLSL-HL-HSS" and r["part_number"] == "1096320"
        assert r["hl"] and r["hss"] and r["elastomero"] == "Neoprene/Nitrile"
        assert r["serie_motor"] == ["456"] and r["hp_protector"] == 0.0

    def test_pocas_etapas_y_eje_base(self, cm):
        from bes.core.gas_paso_a_paso import paso9_protector
        r, _ = paso9_protector("D5800N", 150, "estándar", 197.6, 0, cm)
        assert not r["hl"] and not r["hss"] and r["protector"] == "LSL"

    def test_pozo_desviado_descarta_laberinto(self, cm):
        from bes.core.gas_paso_a_paso import paso9_protector
        r, _ = paso9_protector("D5800N", 150, "estándar", 197.6, 45, cm)
        assert r["tipo"] != "labyrinth"
        with pytest.raises(ValueError):   # el único HL+HSS de la serie 400 es de laberinto
            paso9_protector("D5800N", 423, "alta resistencia", 197.6, 45, cm)

    def test_elastomero_por_temperatura(self, cm):
        from bes.core.gas_paso_a_paso import paso9_protector
        assert paso9_protector("D5800N", 150, "estándar", 260, 0, cm)[0]["elastomero"] == "Carboxynitrile"


class TestPaso10Motor:
    @pytest.fixture(scope="class")
    def cm(self):
        import bes.catalogs.loader as L
        return next(getattr(L, n) for n in dir(L) if n.endswith("Manager"))()

    def test_tipos_leidos_del_catalogo(self, cm):
        """REDA pág. 417: el RX de 192 hp a 1 890 V viene S, UT y LT; el de 2 537 V, solo S y UT."""
        m = {x["model"]: x for x in cm.get_all_motors()}
        assert m["REDA-456-RX-TYPE-192HP-1890V"]["tipos"] == ["S", "UT", "LT"]
        assert m["REDA-456-RX-TYPE-192HP-2537V"]["tipos"] == ["S", "UT"]

    def test_pozo_de_la_tesis(self, cm):
        from bes.core.gas_paso_a_paso import paso10_motor
        r, _ = paso10_motor(301.41, 0.0, True, ["456"], "REDA", 50, 5.012, 4209.08, cm)
        assert r["bhp_sistema"] == pytest.approx(302.91)
        assert (r["n"], r["arreglo"]) == (2, ["UT", "LT"])
        assert r["hp_placa"] == pytest.approx(320) and r["voltaje"] == pytest.approx(3150)
        # Corriente de placa, como el camino convencional (Brown 4.5325).
        assert r["corriente"] == pytest.approx(65)
        assert r["v_anular"] == pytest.approx(0.0119 * 4209.08 / (5.012 ** 2 - 4.56 ** 2))

    def test_sin_separador_y_motor_simple(self, cm):
        from bes.core.gas_paso_a_paso import paso10_motor
        r, _ = paso10_motor(100, 0.0, False, ["456"], "REDA", 60, 5.012, 1500, cm)
        assert r["hp_separador"] == 0 and r["n"] == 1 and r["hp_placa"] >= 100

    def test_velocidad_alta_descarta(self, cm):
        from bes.core.gas_paso_a_paso import paso10_motor
        with pytest.raises(ValueError, match="descartado"):
            paso10_motor(301.41, 0.0, True, ["456"], "REDA", 50, 4.892, 4209.08, cm)


class TestPasos11y12:
    """Cable y superficie con el mismo método que el camino convencional (Brown 4.5325 y 4.5326)."""

    @pytest.fixture(scope="class")
    def cm(self):
        import bes.catalogs.loader as L
        return next(getattr(L, n) for n in dir(L) if n.endswith("Manager"))()

    def test_cable_es_el_del_camino_convencional(self, cm):
        from bes.core.electrical import select_cable
        from bes.core.gas_paso_a_paso import paso11_cable
        r, _ = paso11_cable(6686.332, 65.0, 3150, 197.6, 137.9, 8.2, 5.012, 4.56, cm)
        c = select_cable(65.0, 6686.332, 197.6, 5.012, 4.56, cm, 3150, True)
        assert r["calibre"] == c["cable_size"] and r["tipo"] == c["cable_type"]
        assert r["caida"] == pytest.approx(c["voltage_drop_per_1000ft"] * c["length_ft"] / 1000)
        assert r["caida_1000"] <= 30.0
        assert r["mle_ft"] == pytest.approx(152.1)

    def test_superficie_brown(self, cm):
        """V_sup = (V_motor + ΔV)·1,025 y kVA = V_sup·I·1,732/1000 (Brown 4.5325 y 4.5326)."""
        from bes.core.gas_paso_a_paso import paso12_superficie
        r, _ = paso12_superficie(968, 142.2, 48, "REDA", False, cm)
        assert r["u_superficie"] == pytest.approx((968 + 142.2) * 1.025)
        assert r["kva"] == pytest.approx(r["u_superficie"] * 48 * 3 ** 0.5 / 1000)


