"""Regresión de las tablas dimensionales Tenaris (API 5CT): OD + peso -> ID/drift.

Los valores esperados son diámetros API estándar, verificables contra cualquier
tabla API 5CT publicada. La motivación (ver models.WellGeometry): el usuario elige
OD y peso nominal —lo que traen los catálogos— y el ID se resuelve por lookup.
"""
import pytest

from bes.catalogs.loader import CatalogManager


@pytest.fixture(scope="module")
def cm() -> CatalogManager:
    return CatalogManager()


class TestCasingDims:
    def test_known_api_ids_and_drifts(self, cm: CatalogManager) -> None:
        # (OD in, peso lb/ft, ID esperado, drift estándar esperado)
        cases = [
            (7.0, 26.0, 6.276, 6.151),
            (7.0, 23.0, 6.366, 6.241),
            (5.5, 17.0, 4.892, 4.767),
            (4.5, 11.6, 4.000, 3.875),
            (9.625, 47.0, 8.681, 8.525),
            (13.375, 68.0, 12.415, 12.259),
        ]
        for od, w, id_exp, drift_exp in cases:
            dims = cm.get_casing_dims(od, w)
            assert dims["id_in"] == pytest.approx(id_exp, abs=0.005), (od, w)
            assert dims["drift_in"] == pytest.approx(drift_exp, abs=0.005), (od, w)

    def test_id_between_drift_and_od(self, cm: CatalogManager) -> None:
        for od in cm.list_casing_ods():
            for w in cm.casing_weights(od["od_in"]):
                assert 0 < w["id_in"] < od["od_in"]
                if w["drift_in"] is not None:
                    assert w["drift_in"] <= w["id_in"] + 1e-9

    def test_heavier_weight_smaller_id(self, cm: CatalogManager) -> None:
        # A igual OD, más peso => pared más gruesa => menor ID.
        weights = cm.casing_weights(7.0)
        ids = [w["id_in"] for w in weights]  # ya vienen ordenados por peso
        assert ids == sorted(ids, reverse=True)

    def test_unknown_pair_raises(self, cm: CatalogManager) -> None:
        with pytest.raises(ValueError):
            cm.get_casing_dims(7.0, 999.0)

    def test_ods_present(self, cm: CatalogManager) -> None:
        labels = {o["od_label"] for o in cm.list_casing_ods()}
        assert {"4 1/2", "5 1/2", "7", "9 5/8", "13 3/8"} <= labels


class TestTubingDims:
    def test_known_api_ids(self, cm: CatalogManager) -> None:
        cases = [
            (2.375, 4.7, 1.995, 1.901),
            (2.875, 6.5, 2.441, 2.347),
            (3.5, 9.3, 2.992, 2.867),
            (4.0, 11.0, 3.476, 3.351),
        ]
        for od, w, id_exp, drift_exp in cases:
            dims = cm.get_tubing_dims(od, w)
            assert dims["id_in"] == pytest.approx(id_exp, abs=0.005), (od, w)
            assert dims["drift_in"] == pytest.approx(drift_exp, abs=0.005), (od, w)

    def test_all_tubing_ods(self, cm: CatalogManager) -> None:
        labels = {o["od_label"] for o in cm.list_tubing_ods()}
        assert labels == {"2 3/8", "2 7/8", "3 1/2", "4", "4 1/2"}

    def test_tables_nonempty(self, cm: CatalogManager) -> None:
        assert len(cm.all_casing_dims()) > 100
        assert len(cm.all_tubing_dims()) > 20
