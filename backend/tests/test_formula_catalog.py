"""
El catálogo de fórmulas contra el motor que las ejecuta.

Estos tests son la garantía de que lo que se muestra en pantalla es lo que el
programa hace. Sin ellos el catálogo sería una segunda copia de las fórmulas
—escrita a mano, libre de desincronizarse— y el problema volvería por la
ventana.

Cubren las dos direcciones:

    motor -> catálogo   toda clave que el código ejecuta está declarada
    catálogo -> motor   toda fórmula declarada la ejecuta alguien

más la coherencia interna de cada declaración (los símbolos de la expresión
tienen glosario, y el glosario no inventa símbolos que la expresión no usa).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import bes.core.formula_catalog as fc
from bes.core.formula_catalog import (
    CATALOG,
    TOPIC_ORDER,
    TOPICS,
    catalog_by_topic,
    get_spec,
)
from bes.core.formulas import FormulaTrace

CORE = Path(fc.__file__).parent


def _claves_usadas_en_el_codigo() -> dict[str, str]:
    """Las claves que el motor pasa a ``trace.add(...)``, por AST.

    Se leen del árbol sintáctico y no con una expresión regular: interesa el
    primer argumento posicional de la llamada, no cualquier string que se le
    parezca en un comentario.

    Returns:
        dict clave -> archivo donde se ejecuta.
    """
    usadas: dict[str, str] = {}
    for archivo in sorted(CORE.glob("*.py")):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if (
                isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == "add"
                and isinstance(nodo.func.value, ast.Name)
                and nodo.func.value.id in ("trace", "traza")
                and nodo.args
                and isinstance(nodo.args[0], ast.Constant)
                and isinstance(nodo.args[0].value, str)
            ):
                usadas.setdefault(nodo.args[0].value, archivo.name)
    return usadas


class TestElCatalogoYElMotorNoSeDesincronizan:
    def test_toda_formula_que_el_motor_ejecuta_esta_declarada(self):
        """Sin esto, una cuenta podría correr sin que nadie pueda auditarla."""
        faltan = {
            k: v for k, v in _claves_usadas_en_el_codigo().items()
            if k not in CATALOG
        }
        assert not faltan, (
            f"Estas fórmulas se ejecutan pero no están en formula_catalog.py: "
            f"{faltan}"
        )

    def test_toda_formula_declarada_la_ejecuta_alguien(self):
        """El catálogo no es una lista de deseos: declara lo que el motor hace."""
        usadas = set(_claves_usadas_en_el_codigo())
        huerfanas = sorted(set(CATALOG) - usadas)
        assert not huerfanas, (
            f"Estas fórmulas están declaradas pero nadie las ejecuta: "
            f"{huerfanas}. O se instrumenta el cálculo, o se saca la "
            f"declaración — un catálogo con fórmulas muertas engaña."
        )

    def test_una_clave_no_declarada_falla_fuerte(self):
        """Y el mensaje explica por qué, no sólo que falta."""
        with pytest.raises(KeyError, match="no está declarada"):
            FormulaTrace().add("no_existe_esta_formula", {}, 1.0)


class TestCoherenciaDeCadaDeclaracion:
    def test_las_claves_son_unicas(self):
        assert len(CATALOG) == len(fc._ENTRIES)

    def test_todo_simbolo_de_la_expresion_tiene_glosario(self):
        """El profesor tiene que poder leer qué es cada letra, con su unidad."""
        sin_glosario = []
        for spec in fc._ENTRIES:
            for simbolo in spec.symbols:
                if simbolo not in spec.expression:
                    sin_glosario.append(f"{spec.key}: '{simbolo}' no aparece "
                                        f"en «{spec.expression}»")
        assert not sin_glosario, sin_glosario

    def test_ninguna_formula_se_queda_sin_simbolos(self):
        assert [s.key for s in fc._ENTRIES if not s.symbols] == []

    def test_toda_formula_cita_su_fuente(self):
        """Un número sin procedencia no es citable en la tesis."""
        assert [s.key for s in fc._ENTRIES if not s.reference.strip()] == []

    def test_toda_formula_declara_unidades_y_donde_se_ejecuta(self):
        assert [s.key for s in fc._ENTRIES if not s.units.strip()] == []
        assert [s.key for s in fc._ENTRIES if not s.module.startswith("bes.")] == []

    def test_todo_tema_declarado_existe(self):
        ajenos = sorted({s.topic for s in fc._ENTRIES} - set(TOPIC_ORDER))
        assert not ajenos, f"temas sin declarar en TOPICS: {ajenos}"


class TestLoQueSeMuestraEsLoQueSeEjecuto:
    def test_la_traza_toma_todo_del_catalogo(self):
        t = FormulaTrace()
        t.add("tdh", {"H_vert": 5060.0, "H_fric": 250.0, "H_wh": 520.0}, 5830.0)
        f = t.as_list()[0]
        spec = get_spec("tdh")
        assert f["expression"] == spec.expression
        assert f["units"] == spec.units
        assert f["reference"] == spec.reference
        assert f["symbols"] == spec.symbols
        assert f["topic"] == spec.topic and f["step"] == spec.step

    def test_la_sustitucion_pone_los_numeros(self):
        t = FormulaTrace()
        t.add("tdh", {"H_vert": 5060.0, "H_fric": 250.0, "H_wh": 520.0}, 5830.0)
        assert t.as_list()[0]["substitution"] == "TDH = 5060 + 250 + 520"

    def test_los_simbolos_largos_se_sustituyen_primero(self):
        """Si no, 'Pwf' se rompe al reemplazar 'Pr'... o al revés."""
        t = FormulaTrace()
        t.add("ajuste_drawdown", {"Pr": 4500.0, "Pwf": 2200.0}, 2300.0)
        assert t.as_list()[0]["substitution"] == "Δp = 4500 − 2200"

    def test_un_simbolo_de_una_letra_no_se_come_la_prosa(self):
        """El bug que apareció al instrumentar P&C, fijado para que no vuelva.

        La fórmula del gradiente por fricción tiene los símbolos ``f`` y ``d``
        sueltos, y el rótulo del lado izquierdo dice ``(dP/dz)_fric``. Con un
        ``str.replace`` pelado quedaba ``(0.2034P/0.2034z)_0.0157ric``.
        """
        t = FormulaTrace()
        t.add(
            "pc_gradiente_friccion",
            {"f": 0.0157, "ρ_m": 40.684, "v_m": 3.664, "g_c": 32.174,
             "d": 0.2034},
            0.00455,
        )
        s = t.as_list()[0]["substitution"]
        assert s.startswith("(dP/dz)_fric ="), s
        assert "0.0157ric" not in s and "0.2034P" not in s

    def test_el_exponente_no_bloquea_la_sustitucion(self):
        """``v_m`` tiene que reemplazarse también en ``v_m²``.

        El superíndice es notación de la fórmula, no parte del nombre de la
        variable, aunque Python lo considere alfanumérico.
        """
        t = FormulaTrace()
        t.add(
            "pc_gradiente_friccion",
            {"f": 0.0157, "ρ_m": 40.684, "v_m": 3.664, "g_c": 32.174,
             "d": 0.2034},
            0.00455,
        )
        s = t.as_list()[0]["substitution"]
        assert "3.664²" in s, s
        assert "v_m" not in s

    def test_los_totales_pueden_no_sustituirse(self):
        """Reemplazar un sumatorio por su valor imprimiría «51.8 = 51.8»."""
        t = FormulaTrace()
        t.add("gas_hp_total", {}, 51.8, substitute=False)
        assert t.as_list()[0]["substitution"] == "HP = Σ HP_tramo"

    def test_la_nota_permanente_y_la_del_caso_van_separadas(self):
        """Una es del método y vale siempre; la otra es de este pozo."""
        t = FormulaTrace()
        t.add("stages", {"TDH": 5830.0, "H_etapa": 23.0}, 254,
              context="Bomba D-40 a 1227 STB/d.")
        f = t.as_list()[0]
        assert f["note"] == get_spec("stages").note
        assert f["context"] == "Bomba D-40 a 1227 STB/d."
        assert f["note"] != f["context"]

    def test_el_rotulo_se_puede_precisar_sin_perder_la_declaracion(self):
        """El método de incrementos necesita decir de qué tramo habla."""
        t = FormulaTrace()
        t.add("gas_q_avg", {"Q_ent": 1000.0, "Q_sal": 900.0}, 950.0,
              label="Caudal de mezcla del tramo 500–700 psi")
        f = t.as_list()[0]
        assert f["label"] == "Caudal de mezcla del tramo 500–700 psi"
        assert f["expression"] == get_spec("gas_q_avg").expression


class TestElCatalogoSeEnumeraSinCorrerNada:
    """Es la razón de ser del módulo: el profesor ve TODAS las variantes.

    Con la traza sola se ve nada más que la rama que ese pozo ejecutó; para
    revisar Fetkovich habría que armar un caso de Fetkovich.
    """

    def test_devuelve_todos_los_temas_en_orden_de_diseno(self):
        temas = [t["key"] for t in catalog_by_topic()]
        assert temas == list(TOPIC_ORDER)
        assert temas[0] == "ipr", "el diseño arranca por el aporte del reservorio"

    def test_estan_las_cuatro_maneras_de_llegar_a_la_pwf(self):
        ipr = next(t for t in catalog_by_topic() if t["key"] == "ipr")
        pwf = [f["key"] for f in ipr["formulas"] if f["step"] == "pwf_diseno"]
        assert sorted(pwf) == [
            "pwf_fetkovich", "pwf_lineal", "pwf_vogel_bifasico", "pwf_vogel_recta",
        ]

    def test_estan_las_dos_correlaciones_de_friccion(self):
        tdh = next(t for t in catalog_by_topic() if t["key"] == "tdh")
        fric = sorted(f["key"] for f in tdh["formulas"] if f["step"] == "friccion")
        assert fric == ["friccion_hazen_williams", "friccion_pc"]

    def test_todos_los_temas_del_motor_estan_instrumentados(self):
        """Hoy no queda ninguno pendiente: los diez temas emiten fórmulas.

        Si mañana se agrega un tema nuevo sin instrumentar, se declara con
        ``instrumented=False`` y este test avisa. El mecanismo de publicar la
        cobertura real —en vez de esconder lo que falta— sigue vivo; lo cubre
        :meth:`test_un_tema_pendiente_se_publica_igual`.
        """
        pendientes = [t.key for t in TOPICS if not t.instrumented]
        assert pendientes == [], (
            f"temas sin instrumentar: {pendientes}. Instrumentarlos o dejar "
            f"constancia acá de por qué quedan afuera."
        )

    def test_un_tema_pendiente_se_publica_igual(self):
        """La cobertura se muestra, no se esconde: un tema vacío igual viaja."""
        pendiente = fc.Topic("x", "Tema X", "Algo que falta", instrumented=False)
        original = fc.TOPICS
        try:
            fc.TOPICS = original + (pendiente,)
            tema = next(t for t in catalog_by_topic() if t["key"] == "x")
        finally:
            fc.TOPICS = original
        assert tema["instrumented"] is False
        assert tema["formulas"] == []
        assert tema["blurb"] == "Algo que falta"

    def test_los_temas_instrumentados_traen_formulas(self):
        for tema in catalog_by_topic():
            if tema["instrumented"]:
                assert tema["formulas"], f"{tema['key']} dice estar instrumentado"

    def test_serializa_a_json_plano(self):
        """Va derecho a la API sin mappers a mano."""
        import json
        json.dumps(catalog_by_topic())
