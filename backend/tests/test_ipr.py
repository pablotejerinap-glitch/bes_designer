"""
Unit tests for core/ipr.py.

Numerical references:
  - Vogel Example #2A: Brown Vol. 2b p.70, Pr=2000 psi, Pwf=340 psi,
    qmax=1188 STB/d → q ≈ 1117 STB/d (book rounds intermediate steps).
"""

import numpy as np
import pytest
from scipy.optimize import brentq

from bes.core.models import (
    DesignObjectives,
    DriveMechanism,
    Fluid,
    IPRMethod,
    Reservoir,
    SurfaceConditions,
    WellGeometry,
)
from bes.core.ipr import (
    calculate_pwf_for_target_rate,
    fetkovich_ipr,
    generate_ipr_curve,
    linear_ipr,
    productivity_index_from_test,
    vogel_j_from_test,
    vogel_aof,
    effective_bubble_point,
    ipr_trace,
    ipr_validity_warning,
    vogel_composite_ipr,
    vogel_ipr,
    vogel_qmax_from_test,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_reservoir(
    method: IPRMethod,
    pr: float = 2000.0,
    pb: float = 1500.0,
    pi: float = 1.0,
    fetkovich_c: float | None = None,
    fetkovich_n: float | None = None,
) -> Reservoir:
    return Reservoir(
        static_pressure=pr,
        bubble_point=pb,
        productivity_index=pi,
        ipr_method=method,
        reservoir_temp=160.0,
        drive_mechanism=DriveMechanism.SOLUTION_GAS,
        fetkovich_c=fetkovich_c,
        fetkovich_n=fetkovich_n,
    )


# ---------------------------------------------------------------------------
# linear_ipr
# ---------------------------------------------------------------------------

class TestLinearIPR:
    def test_zero_drawdown(self):
        assert linear_ipr(pr=2000, pwf=2000, pi=1.5) == pytest.approx(0.0)

    def test_full_drawdown(self):
        assert linear_ipr(pr=2000, pwf=0, pi=1.5) == pytest.approx(3000.0)

    def test_typical_case(self):
        # q = 1.5 * (2000 - 1500) = 750 STB/d
        assert linear_ipr(pr=2000, pwf=1500, pi=1.5) == pytest.approx(750.0)

    def test_proportionality(self):
        q1 = linear_ipr(pr=3000, pwf=1000, pi=2.0)
        q2 = linear_ipr(pr=3000, pwf=2000, pi=2.0)
        assert q1 == pytest.approx(2.0 * q2)

    def test_negative_pi_raises(self):
        with pytest.raises(ValueError, match="pi"):
            linear_ipr(pr=2000, pwf=1000, pi=-1.0)

    def test_zero_pi_raises(self):
        with pytest.raises(ValueError, match="pi"):
            linear_ipr(pr=2000, pwf=1000, pi=0.0)

    def test_pwf_above_pr_raises(self):
        with pytest.raises(ValueError, match="pwf"):
            linear_ipr(pr=2000, pwf=2500, pi=1.0)


# ---------------------------------------------------------------------------
# vogel_ipr — including Example #2A from Kermit Brown Vol. 2b, p.70
# ---------------------------------------------------------------------------

class TestVogelIPR:
    def test_zero_drawdown(self):
        # Pwf = Pr → q = 0
        assert vogel_ipr(pr=2000, pwf=2000, qmax=1188) == pytest.approx(0.0)

    def test_full_drawdown(self):
        # Pwf = 0 → q = qmax
        assert vogel_ipr(pr=2000, pwf=0, qmax=1188) == pytest.approx(1188.0)

    def test_book_example_2a(self):
        """Brown Vol. 2b Example #2A: Pr=2000, Pwf=340, qmax=1188 → q≈1117 STB/d.

        Formula gives 1188 * (1 - 0.2*(340/2000) - 0.8*(340/2000)^2) = 1120.1.
        The ±1 % tolerance covers the book's intermediate rounding of qmax.
        """
        q = vogel_ipr(pr=2000, pwf=340, qmax=1188)
        assert q == pytest.approx(1117, rel=0.01)

    def test_monotonically_decreasing_with_pwf(self):
        pwf_values = [0, 400, 800, 1200, 1600, 2000]
        q_values = [vogel_ipr(pr=2000, pwf=p, qmax=1000) for p in pwf_values]
        assert q_values == sorted(q_values, reverse=True)

    def test_negative_qmax_raises(self):
        with pytest.raises(ValueError, match="qmax"):
            vogel_ipr(pr=2000, pwf=500, qmax=-100)

    def test_pwf_above_pr_raises(self):
        with pytest.raises(ValueError, match="pwf"):
            vogel_ipr(pr=2000, pwf=2500, qmax=1000)


# ---------------------------------------------------------------------------
# vogel_qmax_from_test
# ---------------------------------------------------------------------------

class TestVogelQmaxFromTest:
    def test_roundtrip(self):
        """qmax → vogel_ipr at test point → vogel_qmax_from_test → original qmax."""
        pr, qmax_true = 2000.0, 1188.0
        pwf_test = 500.0
        q_test = vogel_ipr(pr, pwf_test, qmax_true)
        qmax_calc = vogel_qmax_from_test(pr, pwf_test, q_test)
        assert qmax_calc == pytest.approx(qmax_true, rel=1e-6)

    def test_book_example_2a_derive_qmax(self):
        """If q=1117 at Pwf=340 and Pr=2000, recover qmax≈1188."""
        qmax = vogel_qmax_from_test(pr=2000, pwf_test=340, q_test=1117)
        assert qmax == pytest.approx(1188, rel=0.01)

    def test_zero_q_test_raises(self):
        with pytest.raises(ValueError, match="q_test"):
            vogel_qmax_from_test(pr=2000, pwf_test=500, q_test=0)

    def test_pwf_equal_to_pr_raises(self):
        with pytest.raises(ValueError, match="pwf_test"):
            vogel_qmax_from_test(pr=2000, pwf_test=2000, q_test=100)


# ---------------------------------------------------------------------------
# fetkovich_ipr
# ---------------------------------------------------------------------------

class TestFetkovichIPR:
    def test_n1_equals_linear_scaled(self):
        """For n=1, Fetkovich becomes q = C*(Pr²-Pwf²), verify against manual calc."""
        pr, pwf, c, n = 2000.0, 1000.0, 1e-4, 1.0
        expected = c * (pr ** 2 - pwf ** 2)
        assert fetkovich_ipr(pr, pwf, c, n) == pytest.approx(expected, rel=1e-9)

    def test_zero_drawdown(self):
        assert fetkovich_ipr(pr=2000, pwf=2000, c=1e-4, n=0.8) == pytest.approx(0.0)

    def test_negative_c_raises(self):
        with pytest.raises(ValueError, match="c"):
            fetkovich_ipr(pr=2000, pwf=1000, c=-1e-4, n=1.0)

    def test_negative_n_raises(self):
        with pytest.raises(ValueError, match="n"):
            fetkovich_ipr(pr=2000, pwf=1000, c=1e-4, n=-0.5)

    def test_pwf_above_pr_raises(self):
        with pytest.raises(ValueError, match="pwf"):
            fetkovich_ipr(pr=2000, pwf=2500, c=1e-4, n=1.0)


# ---------------------------------------------------------------------------
# calculate_pwf_for_target_rate — round-trip consistency
# ---------------------------------------------------------------------------

class TestCalculatePwfForTargetRate:
    """For each method: compute Pwf from a target q, then re-compute q from that
    Pwf; the recovered q must match the original target within 0.5 STB/d."""

    def test_roundtrip_linear(self):
        res = make_reservoir(IPRMethod.LINEAR, pr=3000, pi=2.0)
        target = 1200.0
        pwf = calculate_pwf_for_target_rate(res, target)
        q_back = linear_ipr(pr=res.static_pressure, pwf=pwf, pi=res.productivity_index)
        assert q_back == pytest.approx(target, abs=0.5)

    def test_roundtrip_vogel(self):
        """Vogel invierte contra el COMPUESTO, no contra Vogel puro.

        El reservorio de prueba es subsaturado (Pr = 2000 > Pb = 1500), así que
        la IPR tiene tramo recto. Invertir con Vogel puro desde Pr —lo que hacía
        el módulo— no vuelve al caudal pedido.
        """
        res = make_reservoir(IPRMethod.VOGEL, pr=2000, pb=1500, pi=1.5)
        target = 600.0
        pwf = calculate_pwf_for_target_rate(res, target)
        q_back = vogel_composite_ipr(
            pr=res.static_pressure, pb=res.bubble_point,
            pwf=pwf, pi=res.productivity_index,
        )
        assert q_back == pytest.approx(target, abs=0.5)

    def test_roundtrip_fetkovich(self):
        # AOF = c*(pr²)^n = 5e-4*(3000²)^0.8 ≈ 183 STB/d > target=50 ✓
        c, n = 5e-4, 0.8
        res = make_reservoir(IPRMethod.FETKOVICH, pr=3000,
                             fetkovich_c=c, fetkovich_n=n)
        target = 50.0
        pwf = calculate_pwf_for_target_rate(res, target, fetkovich_c=c, fetkovich_n=n)
        q_back = fetkovich_ipr(pr=res.static_pressure, pwf=pwf, c=c, n=n)
        assert q_back == pytest.approx(target, abs=0.5)

    def test_roundtrip_fetkovich_params_from_reservoir(self):
        """C and n carried inside the Reservoir object — no explicit args."""
        c, n = 5e-4, 0.8
        res = make_reservoir(IPRMethod.FETKOVICH, pr=3000,
                             fetkovich_c=c, fetkovich_n=n)
        target = 50.0
        pwf = calculate_pwf_for_target_rate(res, target)
        q_back = fetkovich_ipr(pr=res.static_pressure, pwf=pwf, c=c, n=n)
        assert q_back == pytest.approx(target, abs=0.5)

    def test_target_above_aof_raises(self):
        res = make_reservoir(IPRMethod.LINEAR, pr=2000, pi=1.0)
        # AOF = 1.0 * 2000 = 2000; request more
        with pytest.raises(ValueError, match="AOF"):
            calculate_pwf_for_target_rate(res, target_rate=2500.0)

    def test_zero_target_raises(self):
        res = make_reservoir(IPRMethod.LINEAR)
        with pytest.raises(ValueError, match="target_rate"):
            calculate_pwf_for_target_rate(res, target_rate=0.0)

    def test_fetkovich_missing_c_raises(self):
        # Since C/n became Reservoir fields, the error is raised earlier:
        # at model construction, not deep inside the solver.
        with pytest.raises(ValueError, match="fetkovich_c"):
            make_reservoir(IPRMethod.FETKOVICH)

    def test_linear_closed_form_exact(self):
        """Linear IPR has a closed-form inverse — result must be exact."""
        res = make_reservoir(IPRMethod.LINEAR, pr=2000, pi=2.0)
        target = 1000.0
        pwf = calculate_pwf_for_target_rate(res, target)
        # Pwf = Pr - q/PI = 2000 - 1000/2 = 1500
        assert pwf == pytest.approx(1500.0, abs=0.01)


# ---------------------------------------------------------------------------
# generate_ipr_curve
# ---------------------------------------------------------------------------

class TestGenerateIPRCurve:
    def test_shape(self):
        res = make_reservoir(IPRMethod.LINEAR)
        q, pwf = generate_ipr_curve(res, n_points=20)
        assert q.shape == (20,)
        assert pwf.shape == (20,)

    def test_pwf_monotonically_decreasing(self):
        """Pwf array must run from Pr down to 0."""
        res = make_reservoir(IPRMethod.VOGEL, pr=2000, pi=1.5)
        _, pwf = generate_ipr_curve(res, n_points=30)
        assert np.all(np.diff(pwf) <= 0)

    def test_q_monotonically_nondecreasing_linear(self):
        res = make_reservoir(IPRMethod.LINEAR, pr=3000, pi=2.0)
        q, _ = generate_ipr_curve(res, n_points=30)
        assert np.all(np.diff(q) >= 0)

    def test_q_monotonically_nondecreasing_vogel(self):
        res = make_reservoir(IPRMethod.VOGEL, pr=2000, pi=1.5)
        q, _ = generate_ipr_curve(res, n_points=50)
        assert np.all(np.diff(q) >= -1e-9)

    def test_q_monotonically_nondecreasing_fetkovich(self):
        res = make_reservoir(IPRMethod.FETKOVICH, pr=3000,
                             fetkovich_c=1e-5, fetkovich_n=0.8)
        q, _ = generate_ipr_curve(res, n_points=30)
        assert np.all(np.diff(q) >= -1e-9)

    def test_boundary_values_linear(self):
        """At Pwf=Pr, q must be 0; at Pwf=0, q must equal PI*Pr (AOF)."""
        res = make_reservoir(IPRMethod.LINEAR, pr=2000, pi=1.5)
        q, pwf = generate_ipr_curve(res, n_points=50)
        assert q[0] == pytest.approx(0.0, abs=1e-6)   # Pwf = Pr
        assert q[-1] == pytest.approx(1.5 * 2000, rel=1e-6)  # Pwf = 0

    def test_boundary_values_vogel(self):
        """AOF del Vogel generalizado: J(Pr − Pb) + J·Pb/1.8."""
        res = make_reservoir(IPRMethod.VOGEL, pr=2000, pb=1500, pi=1.8)
        q, pwf = generate_ipr_curve(res, n_points=50)
        assert q[0] == pytest.approx(0.0, abs=1e-6)
        esperado = 1.8 * (2000 - 1500) + 1.8 * 1500 / 1.8    # = 900 + 1500
        assert q[-1] == pytest.approx(esperado, rel=1e-6)

    def test_el_tramo_sobre_la_burbuja_es_una_recta(self):
        """Lo que el gráfico mostraba curvo y no lo era.

        Con Pwf por encima de Pb el flujo en el reservorio es monofásico: la
        IPR es la recta de Darcy, con pendiente J. El módulo aplicaba Vogel
        desde Pr en todo el rango y curvaba también ese tramo.
        """
        res = make_reservoir(IPRMethod.VOGEL, pr=4500, pb=2900, pi=0.6)
        q, pwf = generate_ipr_curve(res, n_points=200)
        arriba = [(qq, pp) for qq, pp in zip(q, pwf) if pp >= res.bubble_point]
        assert len(arriba) > 10
        # Toda la rama de arriba tiene que caer sobre la misma recta.
        for qq, pp in arriba:
            assert qq == pytest.approx(0.6 * (4500 - pp), rel=1e-9)

    def test_la_curva_no_tiene_quiebre_en_la_burbuja(self):
        """Los dos tramos empalman con la MISMA pendiente (Beggs §2)."""
        pr, pb, j = 4500.0, 2900.0, 0.6
        e = 1e-4
        q_arr = vogel_composite_ipr(pr, pb, pb + e, j)
        q_ab = vogel_composite_ipr(pr, pb, pb - e, j)
        assert q_arr == pytest.approx(q_ab, abs=1e-3)          # continua
        m_arr = (vogel_composite_ipr(pr, pb, pb + 2 * e, j) - q_arr) / -e
        m_ab = (q_ab - vogel_composite_ipr(pr, pb, pb - 2 * e, j)) / -e
        assert m_arr == pytest.approx(j, rel=1e-4)
        assert m_ab == pytest.approx(j, rel=1e-4)

    def test_fetkovich_missing_c_raises(self):
        # The missing-parameter error now fires at Reservoir construction.
        with pytest.raises(ValueError, match="fetkovich_c"):
            make_reservoir(IPRMethod.FETKOVICH)


# ---------------------------------------------------------------------------
# Deliverability from a production test
# ---------------------------------------------------------------------------

class TestProductivityIndexFromTest:
    """The derivation must be the exact inverse of each IPR model: feeding the
    test point back through the model has to return the rate that was measured.
    That round-trip is the only property worth asserting — it is what makes the
    IPR curve pass through the point the engineer measured in the well."""

    def test_linear_is_darcy_definition(self):
        out = productivity_index_from_test(
            pr=1250.0, pwf_test=1000.0, q_test=2500.0, method=IPRMethod.LINEAR
        )
        assert out["productivity_index"] == pytest.approx(10.0)
        assert out["drawdown_psi"] == pytest.approx(250.0)
        assert out["aof"] == pytest.approx(12500.0)
        assert out["qmax_vogel"] is None and out["fetkovich_c"] is None

    def test_linear_roundtrip(self):
        pr, pwf, q = 3000.0, 1800.0, 960.0
        pi = productivity_index_from_test(
            pr, pwf, q, IPRMethod.LINEAR
        )["productivity_index"]
        assert linear_ipr(pr, pwf, pi) == pytest.approx(q, rel=1e-12)

    def test_vogel_saturado_equivale_a_vogel_puro(self):
        """Sin Pb (o con Pb >= Pr) se degrada a Vogel puro, como antes."""
        pr, pwf, q = 2000.0, 340.0, 1117.0
        out = productivity_index_from_test(pr, pwf, q, IPRMethod.VOGEL)
        qmax = vogel_qmax_from_test(pr, pwf, q)
        assert out["aof"] == pytest.approx(qmax)
        assert out["productivity_index"] * pr / 1.8 == pytest.approx(qmax)
        assert vogel_ipr(pr, pwf, qmax) == pytest.approx(q, rel=1e-12)

    def test_vogel_subsaturado_pasa_por_el_punto_de_ensayo(self):
        """El ajuste tiene que reproducir el ensayo, sea cual sea el tramo."""
        pr, pb = 4500.0, 2900.0
        for pwf, etiqueta in ((2200.0, "ensayo BAJO la burbuja"),
                              (3600.0, "ensayo SOBRE la burbuja")):
            out = productivity_index_from_test(
                pr, pwf, 1200.0, IPRMethod.VOGEL, bubble_point=pb
            )
            j = out["productivity_index"]
            assert vogel_composite_ipr(pr, pb, pwf, j) == pytest.approx(
                1200.0, rel=1e-9
            ), etiqueta

    def test_vogel_puro_sobreestima_el_indice_de_productividad(self):
        """El bug que tenía la app, fijado como número.

        Pr = 4500, Pb = 2900, ensayo de 1200 STB/d a 2200 psi. Ignorar la
        burbuja daba J = 0.6751 en vez de 0.5393: un 25 % de más.
        """
        pr, pb, pwf, q = 4500.0, 2900.0, 2200.0, 1200.0
        j_ok = productivity_index_from_test(
            pr, pwf, q, IPRMethod.VOGEL, bubble_point=pb
        )["productivity_index"]
        j_malo = 1.8 * vogel_qmax_from_test(pr, pwf, q) / pr
        assert j_ok == pytest.approx(0.5393, abs=0.0005)
        assert j_malo == pytest.approx(0.6751, abs=0.0005)
        assert j_malo / j_ok == pytest.approx(1.25, abs=0.01)

    def test_fetkovich_derives_c_for_the_given_n(self):
        pr, pwf, q, n = 2000.0, 1200.0, 350.0, 0.85
        out = productivity_index_from_test(
            pr, pwf, q, IPRMethod.FETKOVICH, fetkovich_n=n
        )
        assert out["fetkovich_n"] == pytest.approx(n)
        assert fetkovich_ipr(pr, pwf, out["fetkovich_c"], n) == pytest.approx(
            q, rel=1e-12
        )
        assert out["aof"] == pytest.approx(fetkovich_ipr(pr, 0.0, out["fetkovich_c"], n))

    def test_fetkovich_defaults_to_laminar_n(self):
        out = productivity_index_from_test(
            2000.0, 1200.0, 350.0, IPRMethod.FETKOVICH
        )
        assert out["fetkovich_n"] == pytest.approx(1.0)

    @pytest.mark.parametrize("method", list(IPRMethod))
    def test_zero_drawdown_rejected(self, method):
        with pytest.raises(ValueError, match="draw-down"):
            productivity_index_from_test(
                2000.0, 2000.0, 500.0, method, fetkovich_n=0.8
            )

    @pytest.mark.parametrize("method", list(IPRMethod))
    def test_non_positive_rate_rejected(self, method):
        with pytest.raises(ValueError, match="q_test"):
            productivity_index_from_test(
                2000.0, 1200.0, 0.0, method, fetkovich_n=0.8
            )


class TestReservoirDerivesFromTest:
    """Reservoir must accept the test point and fill PI in itself, so every
    downstream calculation keeps reading ``reservoir.productivity_index``."""

    def _res(self, **over) -> Reservoir:
        kwargs = dict(
            static_pressure=1250.0,
            bubble_point=0.0,
            ipr_method=IPRMethod.LINEAR,
            reservoir_temp=160.0,
            drive_mechanism=DriveMechanism.WATER_DRIVE,
            test_pwf=1000.0,
            test_rate=2500.0,
        )
        kwargs.update(over)
        return Reservoir(**kwargs)

    def test_pi_is_derived(self):
        assert self._res().productivity_index == pytest.approx(10.0)

    def test_explicit_pi_wins_over_the_test(self):
        """A published PI (the book examples) must not be overwritten."""
        assert self._res(productivity_index=4.2).productivity_index == pytest.approx(4.2)

    def test_fetkovich_c_derived_from_test_and_n(self):
        res = self._res(ipr_method=IPRMethod.FETKOVICH, fetkovich_n=0.854)
        assert res.fetkovich_c is not None
        assert fetkovich_ipr(1250.0, 1000.0, res.fetkovich_c, 0.854) == pytest.approx(
            2500.0, rel=1e-9
        )

    def test_fetkovich_without_n_still_raises(self):
        with pytest.raises(ValueError, match="fetkovich_n"):
            self._res(ipr_method=IPRMethod.FETKOVICH)

    def test_half_a_test_is_rejected(self):
        with pytest.raises(ValueError, match="both test_pwf and test_rate"):
            self._res(test_rate=None)

    def test_no_test_and_no_pi_is_rejected(self):
        with pytest.raises(ValueError, match="productivity_index"):
            self._res(test_pwf=None, test_rate=None)


# ---------------------------------------------------------------------------
# Vogel generalizado — regresión contra los ejemplos del Beggs
# ---------------------------------------------------------------------------

class TestVogelGeneralizadoBeggs:
    """Beggs, *Production Optimization Using Nodal Analysis*, §2.

    Los ejemplos del libro llevan flow efficiency (FE); el proyecto no modela
    daño de formación, así que se trabaja con FE = 1. El Ejemplo 2-2 ya es
    FE = 1 y sirve de regresión exacta.
    """

    def test_ejemplo_2_2_reservorio_saturado(self):
        """Pr = 2085 < Pb = 2100: saturado, Vogel puro en todo el rango."""
        pr, pb = 2085.0, 2100.0
        j = vogel_j_from_test(pr, pb, 1765.0, 282.0)
        assert vogel_aof(pr, pb, j) == pytest.approx(1097.0, abs=2.0)
        assert vogel_composite_ipr(pr, pb, 1485.0, j) == pytest.approx(496.0, abs=2.0)

    def test_ejemplo_2_2_pwf_para_un_caudal(self):
        pr, pb = 2085.0, 2100.0
        j = vogel_j_from_test(pr, pb, 1765.0, 282.0)
        pwf = brentq(lambda p: vogel_composite_ipr(pr, pb, p, j) - 400.0, 0.0, pr)
        assert pwf == pytest.approx(1618.0, abs=5.0)

    def test_ejemplo_2_5b_subsaturado_con_ensayo_bajo_la_burbuja(self):
        """Pr = 4000 > Pb = 2000, ensayo a 1200 psi. Caso 2 del libro.

        Con FE = 1 la cuenta a mano da J = 378/2657.8 = 0.14222; el libro
        publica 0.14 resolviendo con FE = 0.7, que redondea al mismo valor.
        """
        pr, pb = 4000.0, 2000.0
        j = vogel_j_from_test(pr, pb, 1200.0, 378.0)
        assert j == pytest.approx(0.14222, abs=0.0002)
        assert vogel_composite_ipr(pr, pb, 1200.0, j) == pytest.approx(378.0, rel=1e-9)

    def test_el_saturado_colapsa_exactamente_a_vogel_puro(self):
        """Con Pb >= Pr el compuesto y Vogel puro tienen que dar lo mismo."""
        pr, pb, j = 3000.0, 3500.0, 0.5
        for pwf in (3000.0, 2000.0, 1000.0, 0.0):
            assert vogel_composite_ipr(pr, pb, pwf, j) == pytest.approx(
                vogel_ipr(pr, pwf, j * pr / 1.8), rel=1e-12
            )

    def test_la_burbuja_acotada_a_la_estatica(self):
        assert effective_bubble_point(2000.0, 3000.0) == 2000.0
        assert effective_bubble_point(2000.0, 1500.0) == 1500.0
        assert effective_bubble_point(2000.0, 0.0) == 2000.0

    def test_el_aof_crece_con_la_burbuja_mas_baja(self):
        """Menos gas libre = más aporte: un reservorio menos saturado da más."""
        pr, j = 4000.0, 0.5
        aofs = [vogel_aof(pr, pb, j) for pb in (4000.0, 3000.0, 2000.0, 1000.0)]
        assert aofs == sorted(aofs), "el AOF tiene que subir al bajar Pb"


# ---------------------------------------------------------------------------
# Lineal y Fetkovich — validez y regresión
# ---------------------------------------------------------------------------

class TestValidezDelMetodoLineal:
    """La recta de Darcy es correcta como fórmula, pero tiene rango.

    No se «corrige» — el usuario que elige Lineal está pidiendo la recta. Lo
    que corresponde es avisarle cuando la está usando donde no vale.
    """

    def _res(self, metodo, pb=2900.0):
        return Reservoir(
            static_pressure=4500.0, bubble_point=pb, ipr_method=metodo,
            reservoir_temp=220.0, drive_mechanism=DriveMechanism.SOLUTION_GAS,
            test_pwf=3600.0, test_rate=540.0,
            fetkovich_n=0.85 if metodo is IPRMethod.FETKOVICH else None,
        )

    def test_avisa_bajo_la_burbuja(self):
        aviso = ipr_validity_warning(self._res(IPRMethod.LINEAR), 2000.0)
        assert aviso is not None
        assert "bifásico" in aviso and "Vogel" in aviso

    def test_no_avisa_sobre_la_burbuja(self):
        assert ipr_validity_warning(self._res(IPRMethod.LINEAR), 3500.0) is None

    def test_no_avisa_para_vogel(self):
        """Vogel ya contempla el tramo bifásico: no hay nada que advertir."""
        assert ipr_validity_warning(self._res(IPRMethod.VOGEL), 2000.0) is None

    def test_no_avisa_para_fetkovich(self):
        assert ipr_validity_warning(self._res(IPRMethod.FETKOVICH), 2000.0) is None

    def test_el_aviso_cuantifica_la_sobreestimacion(self):
        """El número tiene que salir del cálculo, no de una frase hecha."""
        res = self._res(IPRMethod.LINEAR)
        aviso = ipr_validity_warning(res, 500.0)
        j = res.productivity_index
        recta = j * (4500.0 - 500.0)
        vogel = vogel_composite_ipr(4500.0, 2900.0, 500.0, j)
        assert f"{recta:.0f} STB/d" in aviso
        assert f"{vogel:.0f} STB/d" in aviso
        assert recta > vogel, "la recta siempre sobreestima bajo la burbuja"

    def test_sin_presion_de_burbuja_no_hay_nada_que_avisar(self):
        assert ipr_validity_warning(self._res(IPRMethod.LINEAR, pb=0.0), 100.0) is None


class TestFetkovichBeggs:
    """Fetkovich NO lleva corte por presión de burbuja, y está bien así.

    Beggs (§2, ec. 2-58) muestra que al integrar la ecuación de Darcy sobre las
    dos regiones de un reservorio subsaturado, «Fetkovich then stated that the
    composite effect results in an equation of the form q = C(Pr² − Pwf²)^n».
    O sea: el ajuste de C y n ya absorbe el comportamiento bifásico. Un tramo
    recto agregado a mano sería un error.
    """

    def test_ejemplo_2_7a_reproduce_la_curva_del_libro(self):
        c, n, pr = 0.00079, 0.854, 3600.0
        esperado = {3000: 340, 2000: 684, 1500: 796, 1000: 875, 500: 922, 0: 937}
        for pwf, q_libro in esperado.items():
            assert fetkovich_ipr(pr, float(pwf), c, n) == pytest.approx(
                q_libro, abs=1.5
            ), f"Pwf = {pwf} psi"

    def test_ejemplo_2_7a_aof(self):
        assert fetkovich_ipr(3600.0, 0.0, 0.00079, 0.854) == pytest.approx(937.0, abs=1.0)

    def test_no_depende_de_la_presion_de_burbuja(self):
        """La misma C y n dan la misma curva sea cual sea Pb."""
        c, n, pr = 0.00079, 0.854, 3600.0
        for pb in (0.0, 1000.0, 2000.0, 3600.0):
            res = Reservoir(
                static_pressure=pr, bubble_point=pb, ipr_method=IPRMethod.FETKOVICH,
                reservoir_temp=200.0, drive_mechanism=DriveMechanism.SOLUTION_GAS,
                productivity_index=0.5, fetkovich_c=c, fetkovich_n=n,
            )
            q, _ = generate_ipr_curve(res, n_points=20)
            assert q[-1] == pytest.approx(fetkovich_ipr(pr, 0.0, c, n), rel=1e-12)


# ---------------------------------------------------------------------------
# La traza de fórmulas del paso IPR
# ---------------------------------------------------------------------------

class TestTrazaIPR:
    """La IPR es el primer cálculo del diseño: tiene que verse en pantalla.

    La traza arrancaba en el TDH, así que el paso que fija el punto de partida
    —la Pwf en las perforaciones— quedaba invisible para el que quiere chequear.
    """

    def _res(self, metodo, **kw):
        return Reservoir(
            static_pressure=4500.0, bubble_point=2900.0, ipr_method=metodo,
            reservoir_temp=220.0, drive_mechanism=DriveMechanism.SOLUTION_GAS,
            test_pwf=2200.0, test_rate=1200.0, **kw,
        )

    def test_vogel_emite_SIEMPRE_los_dos_tramos(self):
        """Vogel generalizado es una función partida: con media no se revisa.

        Antes se emitía sólo el tramo que gobernaba, así que el profesor no
        podía ver dónde se dobla la curva ni por qué el pozo cayó de un lado.
        """
        res = self._res(IPRMethod.VOGEL)
        pwf = calculate_pwf_for_target_rate(res, 1200.0)
        claves = [f["key"] for f in ipr_trace(res, 1200.0, pwf)]
        assert claves == [
            "pwf_qb", "pwf_vogel_recta", "pwf_vogel_bifasico", "diseno_drawdown",
        ]

    def test_se_marca_cual_tramo_gobierna_como_dato(self):
        """La distinción es `applies`, no una frase escondida en la prosa."""
        res = self._res(IPRMethod.VOGEL)
        for q, esperado in ((1200.0, "pwf_vogel_bifasico"),   # bajo la burbuja
                            (400.0, "pwf_vogel_recta")):      # sobre la burbuja
            pwf = calculate_pwf_for_target_rate(res, q)
            tramos = [f for f in ipr_trace(res, q, pwf)
                      if f["step"] == "pwf_diseno"]
            gobiernan = [f for f in tramos if f["applies"] is True]
            assert len(gobiernan) == 1
            assert gobiernan[0]["key"] == esperado
            assert [f for f in tramos if f["applies"] is False]

    def test_el_tramo_que_no_gobierna_se_evalua_en_la_burbuja(self):
        """Los dos tramos empalman en Pb: es la continuidad del método.

        Evaluar el tramo inactivo en su propio borde muestra justamente eso,
        y de paso dice hasta dónde llega cada uno.
        """
        res = self._res(IPRMethod.VOGEL)
        pb = res.bubble_point
        for q in (400.0, 1200.0):
            pwf = calculate_pwf_for_target_rate(res, q)
            inactivo = next(f for f in ipr_trace(res, q, pwf)
                            if f["step"] == "pwf_diseno" and f["applies"] is False)
            assert inactivo["result"] == pytest.approx(pb, abs=1.0)

    def test_el_paso_conceptual_agrupa_las_variantes(self):
        """Los cuatro caminos a la Pwf comparten `step` y difieren en `key`.

        Es lo que permite listarlos juntos en pantalla —«Pwf en las
        perforaciones, resuelta de cuatro maneras»— y a la vez saber cuál se
        ejecutó en este caso.
        """
        res = self._res(IPRMethod.VOGEL)
        pwf = calculate_pwf_for_target_rate(res, 1200.0)
        f = next(x for x in ipr_trace(res, 1200.0, pwf)
                 if x["step"] == "pwf_diseno" and x["applies"] is True)
        assert f["key"] == "pwf_vogel_bifasico"
        assert f["topic"] == "ipr"

    def test_vogel_sobre_la_burbuja_usa_el_tramo_recto(self):
        res = self._res(IPRMethod.VOGEL)
        pwf = calculate_pwf_for_target_rate(res, 400.0)      # queda sobre Pb
        t = ipr_trace(res, 400.0, pwf)
        f = next(x for x in t
                 if x["step"] == "pwf_diseno" and x["applies"] is True)
        assert f["key"] == "pwf_vogel_recta"
        assert "tramo recto" in f["label"]
        assert f["expression"] == "q = J · (Pr − Pwf)"

    def test_lineal_muestra_el_despeje_directo(self):
        res = self._res(IPRMethod.LINEAR)
        pwf = calculate_pwf_for_target_rate(res, 1200.0)
        f = next(x for x in ipr_trace(res, 1200.0, pwf)
                 if x["step"] == "pwf_diseno")
        assert f["key"] == "pwf_lineal"
        assert f["expression"] == "Pwf = Pr − q / J"

    def test_fetkovich_aclara_que_no_se_parte_en_la_burbuja(self):
        res = self._res(IPRMethod.FETKOVICH, fetkovich_n=0.85)
        pwf = calculate_pwf_for_target_rate(res, 1200.0)
        f = next(x for x in ipr_trace(res, 1200.0, pwf)
                 if x["step"] == "pwf_diseno")
        assert f["key"] == "pwf_fetkovich"
        assert "C · (Pr² − Pwf²)^n" in f["expression"]
        assert "burbuja" in f["note"]
        # Fetkovich NO se parte en la burbuja: un solo tramo, y se dice por qué.
        assert f["applies"] is None
        assert "no se parte" in f["context"].lower()

    def test_la_sustitucion_lleva_los_valores_del_pozo(self):
        """La sustitución se genera de las mismas variables que entran al cálculo."""
        res = self._res(IPRMethod.VOGEL)
        pwf = calculate_pwf_for_target_rate(res, 1200.0)
        f = next(x for x in ipr_trace(res, 1200.0, pwf) if x["key"] == "pwf_qb")
        assert "4500" in f["substitution"] and "2900" in f["substitution"]
        assert f["result"] == pytest.approx(res.productivity_index * 1600.0)

    def test_el_drawdown_cierra(self):
        res = self._res(IPRMethod.VOGEL)
        pwf = calculate_pwf_for_target_rate(res, 1200.0)
        f = next(x for x in ipr_trace(res, 1200.0, pwf)
                 if x["key"] == "diseno_drawdown")
        assert f["result"] == pytest.approx(4500.0 - pwf)

    def test_la_traza_del_diseno_arranca_en_la_ipr(self):
        """En el TDH, que es de donde la toma el diseño completo."""
        from bes.core.tdh import calculate_tdh
        res = self._res(IPRMethod.VOGEL)
        fluid = Fluid(
            oil_api=30.0, water_cut=0.4, gor=600.0, gas_sg=0.7, water_sg=1.02,
            oil_viscosity_dead=5.0, viscosity_temp_ref=100.0,
            bubble_point_pressure=2900.0, h2s_content=0.0, co2_content=0.0,
            sand_production=False,
        )
        well = WellGeometry(
            total_depth=12000.0, casing_od=7.0, casing_weight=26.0, casing_id=6.276,
            tubing_od=2.875, tubing_id=2.441, perforations_top=11000.0,
            perforations_bottom=11500.0, deviation_max=0.0, wellhead_temp=100.0,
        )
        surface = SurfaceConditions(
            wellhead_pressure_required=300.0, flowline_length=500.0, flowline_id=3.0,
            flowline_elevation_change=0.0, separator_pressure=100.0,
            power_supply_voltage=480.0, frequency=60.0,
        )
        obj = DesignObjectives(
            target_flow_rate=1200.0, safety_margin_depth=200.0, allow_gas_venting=True,
            max_gip=0.10, design_life_years=5.0, use_vsd=False,
        )
        info = calculate_tdh(res, fluid, well, surface, obj, 10500.0, 1500.0)
        pasos = [f["step"] for f in info["formulas"]]
        temas = [f["topic"] for f in info["formulas"]]
        assert temas[0] == "ipr"
        assert "pwf_diseno" in pasos
        assert pasos.index("pwf_diseno") < pasos.index("sg_liquido")
