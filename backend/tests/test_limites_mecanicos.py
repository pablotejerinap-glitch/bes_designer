"""Consulta única de los datos mecánicos de una bomba (eje y carcasa).

Orden, el mismo para el camino convencional, el método con gas y la memoria:
hoja de la bomba → ficha de la serie del MISMO fabricante → sin verificar.
"""
from dataclasses import replace

import pytest

from bes.catalogs.loader import CatalogManager
from bes.core import mechanical as mx
from bes.core.gas_paso_a_paso import paso8_eje_carcasas


@pytest.fixture(scope="module")
def cm():
    return CatalogManager()


def _bomba(cm, modelo):
    return next(p for p in cm.get_all_pumps() if p.model == modelo)


def test_la_hoja_de_la_bomba_manda_sobre_la_serie(cm):
    """Con las dos fuentes, gana la del modelo, con su propia frecuencia."""
    td = _bomba(cm, "TD-1750")
    con_hoja = replace(td, shaft_hp_limit_std=90.0, shaft_hp_limit_high_strength=140.0,
                       catalog_frequency_hz=60.0)
    d = mx.mechanical_data(con_hoja, cm)
    assert d["origen"] == "modelo"
    assert d["shaft_hp_limit_std"] == 90.0 and d["reference_frequency_hz"] == 60.0
    # y conserva los datos de la serie que la hoja no publica (misma marca)
    assert d["max_staging_bearing_std"] == 303


def test_la_frecuencia_del_limite_es_la_de_su_fuente(cm):
    """La ficha de la serie 400 de Wood Group está a 50 Hz: 104 hp → 124,8 hp a 60 Hz."""
    res, _ = paso8_eje_carcasas("TD-1750", 100, 50.0, 0.40, 60.0, cm)
    assert res["hp_eje_std"] == pytest.approx(104.0 * 60 / 50)
    assert res["hp_eje_ar"] == pytest.approx(167.0 * 60 / 50)


@pytest.mark.parametrize("modelo", ["DN1100", "TD-1750", "FC1200"])
def test_los_dos_caminos_leen_el_mismo_limite(cm, modelo):
    """Paridad: el método con gas y el convencional usan la misma consulta."""
    datos = mx.mechanical_data(_bomba(cm, modelo), cm)
    conv = mx.verify_shaft(50.0, datos, 50.0)
    if datos is None:
        assert conv["verified"] is False
        with pytest.raises(ValueError, match="límites mecánicos"):
            paso8_eje_carcasas(modelo, 100, 50.0, 0.40, 50.0, cm)
    else:
        gas, _ = paso8_eje_carcasas(modelo, 100, 50.0, 0.40, 50.0, cm)
        assert gas["hp_eje_std"] == pytest.approx(conv["limit_std"])


def test_la_procedencia_queda_declarada(cm):
    assert mx.mechanical_data(_bomba(cm, "DN1100"), cm)["origen"] == "modelo"
    assert mx.mechanical_data(_bomba(cm, "TD-1750"), cm)["origen"] == "serie"
    _, pasos = paso8_eje_carcasas("TD-1750", 100, 50.0, 0.40, 60.0, cm)
    assert "ficha de la serie 400" in pasos[0].cita


def test_ninguna_marca_toma_la_ficha_de_otra(cm):
    """Centrilift no publica límites de eje y la serie 400 de Wood Group no se le presta."""
    for p in cm.get_all_pumps():
        if p.manufacturer == "Centrilift":
            assert mx.mechanical_data(p, cm) is None, p.model


#: Bombas que hoy quedan SIN VERIFICAR porque ni su hoja ni la serie de su marca
#: publican el límite del eje. Si entra una bomba nueva sin datos, o una de éstas
#: los consigue, el test avisa para revisar la lista a conciencia.
SIN_DATOS = {"D-40", "DC800", "DC1000", "B11W", "FC925", "FC1200", "FC1600", "FC2200",
             "FC2700", "GC1200", "GC1600"}


def test_guardia_de_catalogo(cm):
    sin = {p.model for p in cm.get_all_pumps() if mx.mechanical_data(p, cm) is None}
    assert sin == SIN_DATOS
