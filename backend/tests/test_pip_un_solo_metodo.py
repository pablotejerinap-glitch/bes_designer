"""La PIP se calcula con un solo método en toda la herramienta (Brown, Ej. #1C).

    PIP = Pwf − 0,433 · SG_fondo · (D_punzados − D_bomba)

El camino convencional y el método para pozos con gas tienen que dar el mismo
número, y la fracción de gas libre que decide la derivación tiene que ser la
misma que después usa el método con gas.
"""
import pytest

from bes.core.gas_handling import free_gas_fraction_at_intake
from bes.core.gas_paso_a_paso import paso1_ipr_vogel, paso2a_pvt, paso2bc_mezcla, paso3_pip
from bes.core.models import Fluid, IPRMethod, Reservoir, WellGeometry
from bes.core.multiphase import calculate_pip


@pytest.fixture
def pozo():
    r = Reservoir(static_pressure=888.617, bubble_point=1863.26, ipr_method=IPRMethod.VOGEL,
                  reservoir_temp=197.6, drive_mechanism="solution_gas",
                  test_pwf=842.053, test_rate=691.82)
    f = Fluid(oil_api=21, water_cut=0.89, gor=67.4, gas_sg=0.65, water_sg=1.012,
              bubble_point_pressure=1863.26, oil_viscosity_dead=None, viscosity_temp_ref=None,
              h2s_content=0, co2_content=0, sand_production=False)
    w = WellGeometry(total_depth=7391.71, casing_od=5.5, casing_weight=14.0, casing_id=5.012,
                     tubing_od=2.875, tubing_id=2.441, perforations_top=7341.71,
                     perforations_bottom=7391.71, deviation_max=0, wellhead_temp=60,
                     pump_setting_depth=6686.332)
    return r, f, w


def test_convencional_y_gas_dan_la_misma_pip(pozo):
    r, f, w = pozo
    pip_conv = calculate_pip(r, f, w, 6686.332, 4070.7)
    pwf, _ = paso1_ipr_vogel(888.617, 1863.26, 842.053, 691.82, 4070.7)
    pvt, _ = paso2a_pvt(pwf, 197.6, 21, 0.65, 1.012, 67.4)
    mez, _ = paso2bc_mezcla(4070.7, 0.89, 67.4, 0.65, 1.012, pvt)
    pip_gas, _ = paso3_pip(pwf, mez["sg"], 7391.71, 6686.332)
    assert pip_conv == pytest.approx(pip_gas, abs=0.01)
    assert pip_conv == pytest.approx(277.27, abs=0.01)


def test_fraccion_de_gas_libre_es_la_del_metodo_con_gas(pozo):
    r, f, w = pozo
    t_adm = 60 + (197.6 - 60) * 6686.332 / 7391.71
    assert free_gas_fraction_at_intake(f, 277.363, t_adm) == pytest.approx(0.044856, abs=1e-5)
