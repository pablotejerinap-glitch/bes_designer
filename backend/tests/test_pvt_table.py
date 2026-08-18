"""Tabla PVT medida y trazabilidad del origen del dato.

Cubre los capítulos 5 y 25 del procedimiento: un análisis PVT de laboratorio
gana sobre las correlaciones, propiedad por propiedad, y cada valor viaja con
su origen para que en la tesis se pueda decir de dónde salió cada número.
"""
from __future__ import annotations

import pytest

from bes.core.models import Fluid
from bes.core.pvt import (
    PVT_SOURCE_CORRELATION,
    PVT_SOURCE_TABLE,
    PVTPoint,
    PVTTable,
    resolve_pvt,
    standing_rs,
)


@pytest.fixture(scope="module")
def fluido() -> Fluid:
    """Fluido del Ejemplo #3A de Brown."""
    return Fluid(
        oil_api=35.0, water_cut=0.5, gor=500.0, gas_sg=0.65, water_sg=1.07,
        oil_viscosity_dead=5.0, viscosity_temp_ref=100.0,
        bubble_point_pressure=2000.0,
        h2s_content=0.0, co2_content=0.0, sand_production=False,
    )


@pytest.fixture(scope="module")
def tabla_3a() -> PVTTable:
    """Los dos puntos que Brown publica para el #3A, como si fueran de un PVT."""
    return PVTTable(
        points=[
            PVTPoint(pressure=500.0, rs=80.0, bo=1.080, bg=0.00577),
            PVTPoint(pressure=700.0, rs=120.0, bo=1.094, bg=0.00404),
        ],
        source="Brown Vol. 2b §4.53103, tabla del Ejemplo #3A",
        temperature_f=160.0,
    )


class TestPVTPoint:

    def test_presion_debe_ser_positiva(self):
        with pytest.raises(ValueError, match="pressure must be > 0"):
            PVTPoint(pressure=0.0, rs=80.0)

    def test_propiedades_son_opcionales(self):
        """Un informe rara vez publica las seis columnas."""
        pt = PVTPoint(pressure=500.0, rs=80.0)
        assert pt.bo is None and pt.bg is None


class TestPVTTable:

    def test_necesita_dos_filas(self):
        with pytest.raises(ValueError, match="al menos 2 filas"):
            PVTTable(points=[PVTPoint(pressure=500.0, rs=80.0)])

    def test_rechaza_presiones_repetidas(self):
        with pytest.raises(ValueError, match="presiones repetidas"):
            PVTTable(points=[
                PVTPoint(pressure=500.0, rs=80.0),
                PVTPoint(pressure=500.0, rs=90.0),
            ])

    def test_ordena_sola_por_presion(self):
        t = PVTTable(points=[
            PVTPoint(pressure=700.0, rs=120.0),
            PVTPoint(pressure=500.0, rs=80.0),
        ])
        assert [p.pressure for p in t.points] == [500.0, 700.0]
        assert t.pressure_range == (500.0, 700.0)

    def test_devuelve_el_valor_exacto_en_una_fila(self, tabla_3a):
        assert tabla_3a.at(500.0)["rs"] == pytest.approx(80.0)
        assert tabla_3a.at(700.0)["bo"] == pytest.approx(1.094)

    def test_interpola_linealmente(self, tabla_3a):
        """A mitad de camino, la mitad de cada propiedad."""
        v = tabla_3a.at(600.0)
        assert v["rs"] == pytest.approx(100.0)
        assert v["bo"] == pytest.approx(1.087)
        assert v["bg"] == pytest.approx(0.004905)

    def test_no_extrapola(self, tabla_3a):
        """Fuera del rango medido devuelve None: extrapolar un PVT es inventar."""
        assert not tabla_3a.covers(300.0)
        assert all(v is None for v in tabla_3a.at(300.0).values())
        assert all(v is None for v in tabla_3a.at(2000.0).values())

    def test_propiedad_no_publicada_queda_none(self, tabla_3a):
        """La tabla no trae Bw ni Z, así que no los inventa."""
        v = tabla_3a.at(600.0)
        assert v["bw"] is None
        assert v["z"] is None


class TestResolvePVT:

    def test_sin_tabla_todo_es_correlacion(self, fluido):
        r = resolve_pvt(500.0, 160.0, fluido, table=None)
        assert set(r["sources"].values()) == {PVT_SOURCE_CORRELATION}
        assert r["warnings"] == []

    def test_la_tabla_gana_sobre_la_correlacion(self, fluido, tabla_3a):
        """Con PVT medido, Rs sale del laboratorio, no de Standing."""
        r = resolve_pvt(500.0, 160.0, fluido, tabla_3a)
        correlacion = standing_rs(500.0, 160.0, 35.0, 0.65, 2000.0)

        assert r["rs"] == pytest.approx(80.0)          # el del libro
        assert r["rs"] != pytest.approx(correlacion)   # NO el de Standing
        assert r["sources"]["rs"] == PVT_SOURCE_TABLE

    def test_mezcla_tabla_y_correlacion_por_propiedad(self, fluido, tabla_3a):
        """Rs/Bo/Bg de la tabla; Bw y Z de correlación, porque la tabla no los trae."""
        r = resolve_pvt(600.0, 160.0, fluido, tabla_3a)
        assert r["sources"]["rs"] == PVT_SOURCE_TABLE
        assert r["sources"]["bo"] == PVT_SOURCE_TABLE
        assert r["sources"]["bg"] == PVT_SOURCE_TABLE
        assert r["sources"]["bw"] == PVT_SOURCE_CORRELATION
        assert r["sources"]["z"] == PVT_SOURCE_CORRELATION

    def test_fuera_de_rango_cae_a_correlacion_y_avisa(self, fluido, tabla_3a):
        r = resolve_pvt(1500.0, 160.0, fluido, tabla_3a)
        assert set(r["sources"].values()) == {PVT_SOURCE_CORRELATION}
        assert any("fuera de rango" in w for w in r["warnings"])

    def test_avisa_si_la_tabla_esta_a_otra_temperatura(self, fluido, tabla_3a):
        r = resolve_pvt(500.0, 250.0, fluido, tabla_3a)
        assert any("°F de diferencia" in w for w in r["warnings"])

    def test_rs_se_acota_al_gor(self, fluido):
        """Ni la tabla puede disolver más gas del que el pozo produce."""
        exagerada = PVTTable(points=[
            PVTPoint(pressure=500.0, rs=5000.0),
            PVTPoint(pressure=700.0, rs=6000.0),
        ])
        r = resolve_pvt(500.0, 160.0, fluido, exagerada)
        assert r["rs"] == pytest.approx(fluido.gor)

    def test_presion_invalida(self, fluido):
        with pytest.raises(ValueError, match="p must be > 0"):
            resolve_pvt(0.0, 160.0, fluido)


class TestTablaPVTEnElMetodoDeIncrementos:
    """La tabla tiene que llegar hasta el diseño, no quedarse en el resolvedor."""

    def test_la_tabla_cambia_el_resultado(self, fluido, tabla_3a):
        from bes.core.gas_handling import _mixture_volumes_and_density

        con = _mixture_volumes_and_density(500.0, 160.0, fluido, 0.5, 1.0, tabla_3a)
        sin = _mixture_volumes_and_density(500.0, 160.0, fluido, 0.5, 1.0, None)

        # Con la tabla, Rs y Bo son EXACTAMENTE los impresos por Brown.
        assert con["rs"] == pytest.approx(80.0)
        assert con["bo"] == pytest.approx(1.080)
        assert con["rs"] != pytest.approx(sin["rs"])
        assert con["pvt_sources"]["rs"] == PVT_SOURCE_TABLE

    def test_con_la_tabla_del_libro_el_volumen_es_el_impreso(self, fluido, tabla_3a):
        """Alimentado con el PVT de Brown, el volumen da 4.5034 b/STB de petróleo.

        Es la prueba de que el desvío del 1.3 % contra la página viene del PVT
        (Standing/DAK contra la tabla del libro) y no del método de volúmenes.
        """
        from bes.core.gas_handling import _mixture_volumes_and_density
        mv = _mixture_volumes_and_density(500.0, 160.0, fluido, 0.5, 1.0, tabla_3a)
        vol_por_stb_oil = mv["v_total"] / (1.0 - 0.5)
        assert vol_por_stb_oil == pytest.approx(4.5034, rel=0.005)

    def test_el_diseno_reporta_el_origen_del_pvt(self, fluido, tabla_3a):
        from bes.catalogs.loader import CatalogManager
        from bes.core.gas_handling import pressure_increment_design
        from bes.core.models import DriveMechanism, IPRMethod, Reservoir

        res = Reservoir(
            static_pressure=2000.0, bubble_point=2000.0, productivity_index=0.5,
            ipr_method=IPRMethod.VOGEL, reservoir_temp=160.0,
            drive_mechanism=DriveMechanism.SOLUTION_GAS,
        )
        r = pressure_increment_design(
            reservoir=res, fluid=fluido, p_intake=500.0, p_discharge=700.0,
            target_rate=500.0, catalog_manager=CatalogManager(),
            gip=1.0, water_cut=0.5, increment_psi=200.0,
            fixed_pump_model="D-40", pvt_table=tabla_3a,
        )
        assert "Brown" in r["pvt_source"]
        assert r["increment_table"][0]["pvt_sources"]["rs"] == PVT_SOURCE_TABLE

    def test_sin_tabla_el_origen_dice_correlacion(self, fluido):
        from bes.catalogs.loader import CatalogManager
        from bes.core.gas_handling import pressure_increment_design
        from bes.core.models import DriveMechanism, IPRMethod, Reservoir

        res = Reservoir(
            static_pressure=2000.0, bubble_point=2000.0, productivity_index=0.5,
            ipr_method=IPRMethod.VOGEL, reservoir_temp=160.0,
            drive_mechanism=DriveMechanism.SOLUTION_GAS,
        )
        r = pressure_increment_design(
            reservoir=res, fluid=fluido, p_intake=500.0, p_discharge=700.0,
            target_rate=500.0, catalog_manager=CatalogManager(),
            gip=1.0, water_cut=0.5, fixed_pump_model="D-40",
        )
        assert "Correlaciones" in r["pvt_source"]
        assert r["increment_table"][0]["pvt_sources"]["rs"] == PVT_SOURCE_CORRELATION
