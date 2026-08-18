"""
Traza de fórmulas: qué cuenta hizo el programa, con qué números y de dónde sale.

El objetivo es que cualquiera —sobre todo alguien que no lee código— pueda
verificar que la fórmula aplicada es la correcta, sin abrir un archivo `.py`.
Cada paso del cálculo emite un registro con:

    1. la fórmula en símbolos            TDH = H_vert + H_fric + H_wh
    2. la misma fórmula con los números  TDH = 5060 + 250 + 520
    3. el resultado con su unidad        5830 ft
    4. qué significa cada símbolo        H_vert: elevación vertical neta [ft]
    5. la referencia bibliográfica       Brown Vol. 2b §4.5324

Regla de oro de este módulo: **la fórmula se declara una sola vez**, en
:mod:`bes.core.formula_catalog`. Acá sólo entran los números. Si la expresión se
escribiera también en el sitio de la cuenta, los dos lugares podrían decir cosas
distintas — que es exactamente el error que esto viene a evitar.

Uso típico dentro de una función de cálculo::

    trace = FormulaTrace()
    tdh = vertical + friccion + cabeza
    trace.add(
        "tdh",
        {"H_vert": vertical, "H_fric": friccion, "H_wh": cabeza},
        tdh,
    )
    return {..., "formulas": trace.as_list()}

La clave ``"tdh"`` tiene que existir en el catálogo; si no, se levanta
``KeyError`` con el motivo. Lo que depende del caso concreto —«el ensayo se hizo
por debajo de la burbuja»— va en ``context=``, separado de la nota permanente
que trae la declaración.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

from bes.core.formula_catalog import get_spec


def _fmt(x: float) -> str:
    """Formatea un número para que se lea, sin notación científica innecesaria."""
    if x is None:
        return "—"
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return str(x)
    ax = abs(x)
    if x == int(x) and ax < 1e6:
        return str(int(x))
    if ax != 0 and (ax < 1e-3 or ax >= 1e6):
        return f"{x:.4g}"
    if ax < 1:
        return f"{x:.4f}".rstrip("0").rstrip(".")
    if ax < 100:
        return f"{x:.3f}".rstrip("0").rstrip(".")
    return f"{x:,.1f}".rstrip("0").rstrip(".")


#: Caracteres que, pegados a un símbolo, indican que NO está suelto: es parte de
#: una palabra más larga. Son los alfanuméricos **menos** los superíndices y
#: subíndices, que en una fórmula son notación y no letras del nombre.
_NO_FRONTERA = r"[^\W²³¹⁰-₟]"


def _sustituir(texto: str, simbolo: str, valor: str) -> str:
    """Reemplaza ``simbolo`` por ``valor`` sólo donde está **suelto**.

    Un ``str.replace`` pelado pisa letras de la prosa de la fórmula: el símbolo
    ``d`` de ``(dP/dz)_fric = f · ρ_m · v_m² / (2 · g_c · d · 144)`` convertía el
    rótulo entero en ``(0.2034P/0.2034z)_0.0157ric``. Con símbolos de una sola
    letra —que en ingeniería son la mayoría— el problema es la regla, no la
    excepción.

    La solución es exigir que a los costados no haya un carácter de palabra, de
    modo que ``d`` case en ``· d ·`` pero no dentro de ``dP`` ni de ``_fricción``.

    Los superíndices y subíndices **no** cuentan como frontera de palabra aunque
    Python los considere alfanuméricos: en ``v_m²`` el exponente es parte de la
    fórmula, no del nombre de la variable, así que ``v_m`` tiene que sustituirse
    igual. Sin esta excepción el término elevado al cuadrado se quedaba sin
    reemplazar.

    Args:
        texto: La expresión donde sustituir.
        simbolo: El símbolo a reemplazar.
        valor: El número ya formateado.

    Returns:
        La expresión con el símbolo reemplazado donde correspondía.
    """
    return re.sub(rf"(?<!{_NO_FRONTERA}){re.escape(simbolo)}(?!{_NO_FRONTERA})",
                  valor, texto)


@dataclass
class Formula:
    """Una cuenta del diseño, lista para mostrar y auditar.

    Todo lo permanente —expresión, unidades, símbolos, cita, nota de validez—
    sale de :mod:`bes.core.formula_catalog`. Lo único propio de esta corrida son
    ``inputs``, ``substitution``, ``result`` y ``context``.

    Attributes:
        key: Clave del catálogo, única en todo el proyecto.
        step: Paso conceptual. Varias fórmulas comparten paso cuando son el
            mismo cálculo por métodos distintos (la Pwf por Darcy, Vogel o
            Fetkovich); en una corrida se ejecuta exactamente una.
        topic: Tema del catálogo al que pertenece.
        label: Nombre en castellano de lo que se calcula.
        expression: La fórmula en símbolos, como está en el libro.
        substitution: La misma fórmula con los números reemplazados.
        inputs: Los valores que entraron, por nombre de símbolo.
        symbols: Qué significa cada símbolo, con su unidad.
        result: El resultado.
        units: Unidad del resultado.
        reference: De dónde sale la fórmula.
        note: Condición de validez que vale siempre (viene del catálogo).
        context: Por qué esta variante y con qué datos, en este caso concreto.
    """

    key: str
    step: str
    topic: str
    label: str
    expression: str
    substitution: str
    inputs: dict[str, float]
    symbols: dict[str, str]
    result: float
    units: str
    reference: str = ""
    note: str = ""
    context: str = ""


@dataclass
class FormulaTrace:
    """Acumula las fórmulas de un procedimiento, en orden de ejecución."""

    items: list[Formula] = field(default_factory=list)

    def add(
        self,
        key: str,
        inputs: dict[str, float],
        result: float,
        *,
        context: str = "",
        label: str | None = None,
        substitute: bool = True,
    ) -> float:
        """Registra una cuenta y devuelve el resultado, para poder encadenar.

        La expresión, las unidades, los símbolos y la cita salen del catálogo:
        acá sólo entran los números. La sustitución se arma reemplazando cada
        símbolo de la expresión por su valor. Los símbolos se ordenan de más
        largo a más corto para que ``P_wf`` no se rompa al sustituir ``P``.

        Args:
            key: Clave declarada en :mod:`bes.core.formula_catalog`.
            inputs: Valor de cada símbolo que aparece en la fórmula.
            result: Resultado de la cuenta.
            context: Aclaración propia de este caso: por qué se tomó esta
                variante, con qué datos. Lo permanente ya está en el catálogo.
            label: Sobrescribe el rótulo del catálogo. Sólo para cuando el paso
                necesita identificar de qué tramo se trata.
            substitute: ``False`` deja la expresión sin reemplazar. Se usa en
                los totales, donde sustituir un sumatorio por su propio valor
                imprimiría «51.8 = 51.8».

        Returns:
            El mismo ``result`` que se le pasó.

        Raises:
            KeyError: Si la clave no está declarada en el catálogo.
        """
        spec = get_spec(key)

        sustituida = spec.expression
        if substitute:
            for simbolo in sorted(inputs, key=len, reverse=True):
                sustituida = _sustituir(sustituida, simbolo, _fmt(inputs[simbolo]))

        self.items.append(Formula(
            key=spec.key, step=spec.step, topic=spec.topic,
            label=label or spec.label,
            expression=spec.expression, substitution=sustituida,
            inputs={k: v for k, v in inputs.items()}, symbols=dict(spec.symbols),
            result=result, units=spec.units, reference=spec.reference,
            note=spec.note, context=context,
        ))
        return result

    def as_list(self) -> list[dict]:
        """Las fórmulas como diccionarios, listas para serializar a JSON."""
        return [asdict(f) for f in self.items]

    def __len__(self) -> int:
        return len(self.items)
