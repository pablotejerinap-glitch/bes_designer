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
    match = [p for p in manager.get_all_pumps() if p.model == "WD-4300"]
    assert match, "WD-4300 not found in catalog"
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
        assert "WD-4300" in fig.layout.title.text

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
            drive_mechanism=DriveMechanism.SOLUTION_GAS, datum_depth=7000,
        )

    def test_linear_aof_equals_j_times_pr(self):
        from bes.core.models import IPRMethod
        from bes.plotting import plot_ipr_curve
        fig = plot_ipr_curve(self._res(IPRMethod.LINEAR))
        q = fig.data[0].x
        assert max(q) == pytest.approx(5.0 * 3000, rel=0.01)  # J·Pr

    def test_vogel_aof_equals_j_pr_over_1_8(self):
        from bes.core.models import IPRMethod
        from bes.plotting import plot_ipr_curve
        fig = plot_ipr_curve(self._res(IPRMethod.VOGEL))
        q = fig.data[0].x
        assert max(q) == pytest.approx(5.0 * 3000 / 1.8, rel=0.01)  # Vogel AOF

    def test_serializes_for_all_methods(self):
        import json
        from bes.core.models import IPRMethod
        from bes.plotting import plot_ipr_curve
        for meth in (IPRMethod.LINEAR, IPRMethod.VOGEL, IPRMethod.COMBINED):
            fig = plot_ipr_curve(self._res(meth))
            assert "data" in json.loads(fig.to_json())
