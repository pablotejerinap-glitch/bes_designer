"""Tests del módulo de TDH — el término de fricción en la tubería.

La elevación vertical y la altura de boca de pozo se verifican en
``test_pump_design.py`` junto con el resto del diseño; acá se cubre la parte
que tiene alternativas: cómo se calcula la fricción.
"""
import pytest

from bes.core.tdh import (
    RE_LAMINAR,
    RE_TURBULENTO,
    friction_loss_darcy_weisbach,
    friction_loss_hazen_williams,
)


class TestDarcyWeisbachSiContemplaLaViscosidad:
    """La fricción dependiente del Reynolds, que Hazen-Williams no puede dar.

    Hazen-Williams se estableció con AGUA en régimen turbulento y su único
    parámetro libre —el coeficiente C— describe la rugosidad de la cañería, no
    el fluido. En un crudo pesado el flujo se vuelve laminar y ahí el factor de
    fricción crece linealmente con la viscosidad, cosa que ninguna potencia
    fija del caudal reproduce.
    """

    #: Caso de §2.4.4: 14 °API, 1 500 b/d, tubing de 2 3/8" y 6 300 ft.
    Q, D, L = 1500.0, 1.995, 6300.0
    RHO = 62.4 * 0.9730          # densidad del crudo de 14 °API

    def test_en_laminar_el_factor_es_64_sobre_re(self):
        r = friction_loss_darcy_weisbach(self.Q, self.D, self.L, self.RHO, 194.0)
        assert r["regimen"] == "laminar"
        assert r["reynolds"] < RE_LAMINAR
        assert r["friction_factor"] * r["reynolds"] == pytest.approx(64.0)

    def test_en_laminar_la_perdida_es_proporcional_a_la_viscosidad(self):
        """Es la propiedad que Hazen-Williams no puede tener."""
        a = friction_loss_darcy_weisbach(1000.0, 2.441, 5000.0, 55.0, 300.0)
        b = friction_loss_darcy_weisbach(1000.0, 2.441, 5000.0, 55.0, 600.0)
        assert a["regimen"] == b["regimen"] == "laminar"
        assert b["head_ft"] / a["head_ft"] == pytest.approx(2.0, rel=1e-9)

    def test_con_crudo_liviano_coincide_con_hazen_williams(self):
        """A 5 cp —el techo del envelope de P&C— las dos dan lo mismo.

        Es lo que acota el alcance del cambio: no corrige un error general,
        sino uno del extremo viscoso.
        """
        dw = friction_loss_darcy_weisbach(self.Q, self.D, self.L, self.RHO, 5.0)
        hw = friction_loss_hazen_williams(self.Q, self.D, self.L)
        assert dw["regimen"] == "turbulento"
        assert abs(dw["head_ft"] - hw) / hw < 0.05

    def test_con_crudo_pesado_se_aparta_del_lado_no_conservador(self):
        """Hazen-Williams SUBESTIMA, que es lo que vuelve grave el hueco."""
        dw = friction_loss_darcy_weisbach(self.Q, self.D, self.L, self.RHO, 194.0)
        hw = friction_loss_hazen_williams(self.Q, self.D, self.L)
        assert dw["head_ft"] > 5 * hw

    def test_la_zona_de_transicion_se_declara_y_queda_acotada(self):
        """Entre 2000 y 4000 no hay ley: se interpola y se avisa."""
        # Con este pozo la transición cae entre 7 y 15 cp: Re va con 1/mu, así
        # que un barrido grueso la saltea. Se recorre fino a propósito.
        vistos = {}
        for mu in (0.5, 2.0, 5.0, 7.5, 9.0, 11.0, 13.0, 14.5, 20.0, 60.0, 200.0):
            r = friction_loss_darcy_weisbach(800.0, 2.441, 5000.0, 60.0, mu)
            vistos.setdefault(r["regimen"], []).append((mu, r))
        assert set(vistos) == {"laminar", "transicion", "turbulento"}, (
            f"el barrido no cubrió los tres regímenes: {sorted(vistos)}"
        )
        for _, r in vistos["transicion"]:
            assert r["transicion"] is True

    def test_la_interpolacion_empalma_sin_salto_en_las_dos_fronteras(self):
        """Lo que hay que exigirle a la transición es CONTINUIDAD.

        La interpolación arranca en el laminar evaluado en Re = 2000 y termina
        en el turbulento evaluado en Re = 4000, de modo que en cada frontera
        los dos tramos deben coincidir. Si no empalmaran, el factor de fricción
        daría un salto y un pozo apenas más viscoso que otro arrojaría una
        pérdida discontinua.

        Se busca la viscosidad de cada frontera por bisección, porque el
        Reynolds va con 1/mu y no admite despeje limpio desde estos datos.
        """
        def re_de(mu):
            return friction_loss_darcy_weisbach(
                800.0, 2.441, 5000.0, 60.0, mu)["reynolds"]

        for objetivo in (RE_LAMINAR, RE_TURBULENTO):
            lo, hi = 0.1, 500.0
            for _ in range(200):
                mid = (lo + hi) / 2.0
                if re_de(mid) > objetivo:
                    lo = mid
                else:
                    hi = mid
            f_abajo = friction_loss_darcy_weisbach(
                800.0, 2.441, 5000.0, 60.0, lo)["friction_factor"]
            f_arriba = friction_loss_darcy_weisbach(
                800.0, 2.441, 5000.0, 60.0, hi)["friction_factor"]
            assert f_abajo == pytest.approx(f_arriba, rel=1e-6), (
                f"salto del factor de fricción en Re = {objetivo:.0f}"
            )

    def test_la_perdida_crece_con_el_caudal_y_baja_con_el_diametro(self):
        base = friction_loss_darcy_weisbach(1000.0, 2.441, 5000.0, 62.4, 0.6)
        mas_caudal = friction_loss_darcy_weisbach(2000.0, 2.441, 5000.0, 62.4, 0.6)
        mas_ancho = friction_loss_darcy_weisbach(1000.0, 2.875, 5000.0, 62.4, 0.6)
        assert mas_caudal["head_ft"] > base["head_ft"]
        assert mas_ancho["head_ft"] < base["head_ft"]

    def test_rechaza_argumentos_sin_sentido(self):
        for kw in ({"q_bpd": 0.0}, {"pipe_id_in": 0.0},
                   {"density_lb_ft3": 0.0}, {"viscosity_cp": 0.0}):
            args = dict(q_bpd=self.Q, pipe_id_in=self.D, length_ft=self.L,
                        density_lb_ft3=self.RHO, viscosity_cp=10.0)
            args.update(kw)
            with pytest.raises(ValueError):
                friction_loss_darcy_weisbach(**args)
