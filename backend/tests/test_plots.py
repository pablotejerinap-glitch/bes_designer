"""Tests de los builders de figuras de bes.plotting.

Los builders son agnósticos de framework: devuelven una plotly.Figure que la
API serializa con to_json(). Acá se verifica que producen una figura válida y
que la de catálogo contiene las trazas esperadas (head/HP/eficiencia + BEP).
"""
from __future__ import annotations

import json

import pytest

from bes.catalogs.loader import CatalogManager
from bes.plotting import plot_pump_catalog_curve, plot_pump_curve


@pytest.fixture(scope="module")
def manager() -> CatalogManager:
    return CatalogManager()


@pytest.fixture(scope="module")
def wd4300(manager):
    match = [p for p in manager.get_all_pumps() if p.model == "TD-4300"]
    assert match, "TD-4300 not found in catalog"
    return match[0]


class TestPumpCatalogCurve:
    def test_returns_serializable_figure(self, wd4300):
        fig = plot_pump_catalog_curve(wd4300)
        payload = json.loads(fig.to_json())
        assert "data" in payload and "layout" in payload

    def test_has_head_hp_eff_and_bep_traces(self, wd4300):
        fig = plot_pump_catalog_curve(wd4300)
        names = {t.name for t in fig.data}
        assert {"Head (ft/etapa)", "HP/etapa", "Eficiencia (%)", "BEP"} <= names

    def test_title_names_the_pump(self, wd4300):
        fig = plot_pump_catalog_curve(wd4300)
        assert "TD-4300" in fig.layout.title.text

    def test_head_trace_matches_catalog_points(self, wd4300):
        fig = plot_pump_catalog_curve(wd4300)
        head = next(t for t in fig.data if t.name == "Head (ft/etapa)")
        assert len(head.x) == len(wd4300.points)
        assert head.y[0] == pytest.approx(wd4300.points[0].head_per_stage)


class TestPumpDesignCurve:
    """La curva con contexto de diseño escala head por el nº de etapas."""

    def test_scales_head_by_stages(self, wd4300):
        fig = plot_pump_curve(wd4300, operating_flow=wd4300.bep_flow, stages=100)
        head = next(t for t in fig.data if t.name == "TDH (ft)")
        assert head.y[0] == pytest.approx(wd4300.points[0].head_per_stage * 100)


class TestIPRCurve:
    """La curva IPR sale del solo reservorio (sin bomba), para la vista de cálculo IPR."""

    def _res(self, method):
        from bes.core.models import Reservoir, IPRMethod, DriveMechanism
        return Reservoir(
            static_pressure=3000, bubble_point=2500, productivity_index=5.0,
            ipr_method=method, reservoir_temp=180,
            drive_mechanism=DriveMechanism.SOLUTION_GAS,
        )

    def test_linear_aof_equals_j_times_pr(self):
        from bes.core.models import IPRMethod
        from bes.plotting import plot_ipr_curve
        fig = plot_ipr_curve(self._res(IPRMethod.LINEAR))
        q = fig.data[0].x
        assert max(q) == pytest.approx(5.0 * 3000, rel=0.01)  # J·Pr

    def test_vogel_aof_es_el_del_generalizado(self):
        """AOF = J·(Pr − Pb) + J·Pb/1.8, no J·Pr/1.8.

        El reservorio del fixture es SUBSATURADO (Pb 2500 < Pr 3000), así que
        el tramo recto aporta caudal antes de que empiece Vogel. Tomar
        J·Pr/1.8 —Vogel puro desde Pr— subestima el AOF y era el síntoma del
        bug: la curva se graficaba doblada desde Pr, sin tramo recto.
        """
        from bes.core.models import IPRMethod
        from bes.plotting import plot_ipr_curve
        fig = plot_ipr_curve(self._res(IPRMethod.VOGEL))
        q = fig.data[0].x
        aof = 5.0 * (3000 - 2500) + 5.0 * 2500 / 1.8
        assert max(q) == pytest.approx(aof, rel=0.01)

    def test_vogel_es_recta_por_encima_de_la_burbuja(self):
        """Pr → Pb tiene que ser una RECTA de pendiente J (Beggs §2, ec. 2-38).

        Regresión del bug reportado sobre el gráfico: el tramo monofásico salía
        curvo porque el plot usaba Vogel puro desde Pr en vez del generalizado.
        Se verifica que todos los puntos con Pwf >= Pb caen sobre q = J·(Pr−Pwf)
        y que el caudal en la burbuja es exactamente J·(Pr−Pb).
        """
        from bes.core.models import IPRMethod
        from bes.plotting import plot_ipr_curve
        fig = plot_ipr_curve(self._res(IPRMethod.VOGEL))
        curva = fig.data[0]
        pr, pb, j = 3000.0, 2500.0, 5.0

        recto = [(q, p) for q, p in zip(curva.x, curva.y) if p >= pb]
        assert len(recto) > 5, "el tramo recto tiene que tener puntos"
        for q, pwf in recto:
            assert q == pytest.approx(j * (pr - pwf), abs=1e-6)

        # El marcador de burbuja se apoya sobre el final de la recta.
        burbuja = next(t for t in fig.data if "burbuja" in t.name)
        assert burbuja.x[0] == pytest.approx(j * (pr - pb), abs=1e-6)

    def test_serializes_for_all_methods(self):
        import json
        from bes.core.models import IPRMethod
        from bes.plotting import plot_ipr_curve
        for meth in (IPRMethod.LINEAR, IPRMethod.VOGEL):
            fig = plot_ipr_curve(self._res(meth))
            assert "data" in json.loads(fig.to_json())


class TestOperatingRangeBand:
    """La banda del rango operativo recomendado tiene que estar DIBUJADA.

    Regresión de un bug silencioso: ``add_vrect`` descarta los subplots vacíos
    (``exclude_empty_subplots=True`` por defecto), así que llamarlo antes del
    primer ``add_trace`` no dibuja nada y tampoco falla. Las dos curvas de bomba
    lo hacían y la banda nunca se vio.
    """

    @staticmethod
    def _rects(fig) -> list[dict]:
        import json
        layout = json.loads(fig.to_json())["layout"]
        return [s for s in layout.get("shapes", []) if s.get("type") == "rect"]

    @pytest.fixture(scope="class")
    def pump(self):
        from bes.catalogs.loader import CatalogManager
        cm = CatalogManager()
        return next(p for p in cm.get_all_pumps() if p.model == "TD-850")

    def test_design_curve_draws_the_band(self, pump):
        from bes.plotting import plot_pump_curve
        rects = self._rects(plot_pump_curve(pump, operating_flow=850, stages=256))
        assert len(rects) == 1
        assert rects[0]["x0"] == pytest.approx(pump.min_flow)
        assert rects[0]["x1"] == pytest.approx(pump.max_flow)

    def test_catalog_curve_draws_the_band(self, pump):
        from bes.plotting import plot_pump_catalog_curve
        rects = self._rects(plot_pump_catalog_curve(pump))
        assert len(rects) == 1
        assert rects[0]["x0"] == pytest.approx(pump.min_flow)
        assert rects[0]["x1"] == pytest.approx(pump.max_flow)

    def test_band_sits_below_the_curves(self, pump):
        """Sombreado de fondo, no encima de las líneas."""
        from bes.plotting import plot_pump_curve
        assert self._rects(plot_pump_curve(pump, 940, 256))[0]["layer"] == "below"

    def test_band_is_not_symmetric_around_the_bep(self, pump):
        """No es BEP ±25 %: es el rango publicado, y sus dos límites responden
        a mecanismos distintos (downthrust abajo, upthrust arriba)."""
        low = (pump.bep_flow - pump.min_flow) / pump.bep_flow
        high = (pump.max_flow - pump.bep_flow) / pump.bep_flow
        assert low != pytest.approx(high, abs=0.05)


# ---------------------------------------------------------------------------
# Escalera de incrementos — Brown Vol. 2b Fig. 4.56B
# ---------------------------------------------------------------------------

def _filas(presiones: list[float], caudales: list[float],
           etapas: int = 38) -> list[dict]:
    """Filas mínimas de ``increment_table`` para el builder de la escalera."""
    return [
        {"p_lo": presiones[i], "p_hi": presiones[i + 1],
         "delta_p": presiones[i + 1] - presiones[i],
         "q_lo_bpd": caudales[i], "q_hi_bpd": caudales[i + 1],
         "stages": etapas}
        for i in range(len(presiones) - 1)
    ]


class TestEscaleraDeIncrementos:
    """La figura del libro: admisión abajo, descarga arriba, ΔP en el medio.

    Los valores son los **impresos** en la Fig. 4.56B del ejemplo #3-B: la
    presión sube de 500 a 1300 psi en cuatro escalones de 200 psi y el volumen
    baja de 1752 a 873 b/d.
    """

    P_LIBRO = [500.0, 700.0, 900.0, 1100.0, 1300.0]
    Q_LIBRO = [1752.0, 1315.0, 1068.0, 922.0, 873.0]

    @pytest.fixture
    def fig(self):
        from bes.plotting import plot_gas_increment_ladder
        return plot_gas_increment_ladder(
            _filas(self.P_LIBRO, self.Q_LIBRO),
            p_intake=500.0, p_discharge=1300.0,
            pump_model="D-40", total_stages=209,
        )

    def test_figura_serializable(self, fig):
        assert json.loads(fig.to_json())["layout"]["title"]["text"]

    def test_un_peldano_por_frontera_mas_la_columna(self, fig):
        """5 fronteras → 5 peldaños + 1 columna + 3 trazos de la acotación."""
        assert len(fig.layout.shapes) == 5 + 1 + 3

    def test_la_columna_va_de_admision_a_descarga(self, fig):
        columna = fig.layout.shapes[0]
        assert (columna.y0, columna.y1) == (500.0, 1300.0)
        assert columna.x0 == columna.x1 == 0

    def test_el_volumen_baja_al_subir_la_presion(self, fig):
        """El invariante físico del método: con gas el caudal NO es constante."""
        traza = fig.data[0]
        assert list(traza.y) == self.P_LIBRO
        caudales = list(traza.customdata)
        assert caudales == self.Q_LIBRO
        assert all(b <= a for a, b in zip(caudales, caudales[1:]))

    def test_el_eje_x_esta_oculto_y_con_rango_fijo(self, fig):
        """Toda la figura son anotaciones: sin rango explícito Plotly ajusta al
        único trace (x=0) y las etiquetas quedan fuera del área visible."""
        assert fig.layout.xaxis.visible is False
        assert fig.layout.xaxis.range == (-3.0, 4.3)

    def test_sin_intervalos_levanta_valueerror(self):
        from bes.plotting import plot_gas_increment_ladder
        with pytest.raises(ValueError, match="al menos un intervalo"):
            plot_gas_increment_ladder([], p_intake=500.0, p_discharge=700.0)

    def test_el_ultimo_escalon_con_resto_queda_marcado(self):
        """El último tramo se queda con el resto de la división — defecto
        conocido del método. La figura lo marca con un asterisco en vez de
        presentarlo como un escalón más."""
        from bes.plotting import plot_gas_increment_ladder
        fig = plot_gas_increment_ladder(
            _filas([500.0, 700.0, 760.0], [1752.0, 1315.0, 1250.0]),
            p_intake=500.0, p_discharge=760.0,
        )
        marcados = [a.text for a in fig.layout.annotations
                    if a.text and "ΔP" in a.text and "*" in a.text]
        assert len(marcados) == 1
        assert "60" in marcados[0]

    def test_con_muchos_tramos_se_adelgazan_las_etiquetas(self):
        """Con paso de 25 psi salen decenas de tramos: si se rotularan todos,
        las etiquetas se pisarían. Las LÍNEAS se dibujan todas igual."""
        from bes.plotting import plot_gas_increment_ladder
        presiones = [400.0 + 25.0 * i for i in range(61)]
        caudales = [1800.0 - 12.0 * i for i in range(61)]
        fig = plot_gas_increment_ladder(
            _filas(presiones, caudales), p_intake=400.0, p_discharge=1900.0,
        )
        # 61 peldaños + columna + 3 de acotación: ninguna línea se pierde.
        assert len(fig.layout.shapes) == 61 + 1 + 3
        # Sin adelgazar serían 61*2 + 60 + 3 ≈ 185 anotaciones.
        assert len(fig.layout.annotations) < 60


# ---------------------------------------------------------------------------
# Zona operativa del método de gas sobre la curva de bomba
# ---------------------------------------------------------------------------

class TestZonaOperativaDelMetodoDeGas:
    """Con gas el caudal NO es constante a lo largo de la bomba.

    La bomba se elige contra un caudal de mezcla representativo, y hay que
    poder ver dónde caen los dos extremos —el que entra y el que sale— contra
    la banda 0.75–1.25 × q_rep.
    """

    @pytest.fixture(scope="class")
    def pump(self):
        from bes.catalogs.loader import CatalogManager
        return next(p for p in CatalogManager().get_all_pumps()
                    if p.model == "TD-850")

    def _fig(self, pump, **cotas):
        from bes.plotting.plots import plot_pump_curve
        return plot_pump_curve(
            pump, operating_flow=pump.bep_flow, stages=100,
            gas_zone=cotas or None,
        )

    def _textos(self, fig) -> str:
        return " | ".join(a.text or "" for a in fig.layout.annotations)

    def test_sin_gas_no_se_dibuja_la_zona(self, pump):
        """El camino convencional tiene un solo caudal: la pregunta no existe."""
        assert "Zona operativa" not in self._textos(self._fig(pump))

    def test_la_banda_va_de_075_a_125_del_representativo(self, pump):
        from bes.plotting.plots import GAS_ZONE_LOWER, GAS_ZONE_UPPER
        q = 1000.0
        fig = self._fig(pump, q_representative=q, q_intake=1100.0,
                        q_discharge=900.0)
        xs = [sh.x0 for sh in fig.layout.shapes if sh.type == "rect"]
        assert GAS_ZONE_LOWER * q in xs
        assert any(sh.x1 == GAS_ZONE_UPPER * q for sh in fig.layout.shapes
                   if sh.type == "rect")

    def test_marca_los_dos_extremos_con_su_razon(self, pump):
        fig = self._fig(pump, q_representative=1000.0, q_intake=1100.0,
                        q_discharge=900.0)
        t = self._textos(fig)
        assert "q admisión (entra): 1,100 bpd (1.10× q_rep)" in t
        assert "q descarga (sale): 900 bpd (0.90× q_rep)" in t

    def test_el_extremo_fuera_de_banda_se_marca_en_el_dibujo(self, pump):
        """No alcanza con un aviso de texto: tiene que verse en la figura."""
        fig = self._fig(pump, q_representative=1000.0, q_intake=1800.0,
                        q_discharge=900.0)
        assert "FUERA" in self._textos(fig)
        # Y la línea del extremo que se fue queda en rojo.
        assert any(
            sh.line.color == "#C62828" for sh in fig.layout.shapes
            if sh.type == "line"
        )

    def test_la_banda_de_catalogo_sigue_estando(self, pump):
        """Son DOS zonas distintas y las dos tienen que verse.

        La del fabricante es propiedad de la bomba; la del método es de este
        diseño. Que una tape a la otra sería perder información.
        """
        fig = self._fig(pump, q_representative=1000.0, q_intake=1100.0,
                        q_discharge=900.0)
        t = self._textos(fig)
        assert "Rango operativo recomendado" in t
        assert "Zona operativa del método de gas" in t
        rects = [sh for sh in fig.layout.shapes if sh.type == "rect"]
        assert len(rects) == 2

    def test_sin_caudal_representativo_no_hay_contra_que_leer(self, pump):
        """Los extremos solos no dicen nada: se ignoran sin romper."""
        assert "Zona operativa" not in self._textos(
            self._fig(pump, q_intake=1100.0, q_discharge=900.0)
        )
