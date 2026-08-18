"""
Traza de fórmulas: qué cuenta hizo el programa, con qué números y de dónde sale.

El objetivo es que cualquiera —sobre todo alguien que no lee código— pueda
verificar que la fórmula aplicada es la correcta, sin abrir un archivo `.py`.
Cada paso del cálculo emite un registro con cuatro cosas:

    1. la fórmula en símbolos            TDH = H_vert + H_fric + H_wh
    2. la misma fórmula con los números  TDH = 5060 + 250 + 520
    3. el resultado con su unidad        5830 ft
    4. la referencia bibliográfica       Brown Vol. 2b §4.5324

Regla de oro de este módulo: **la traza se arma con las mismas variables que
entran a la cuenta**. No se escribe la fórmula a mano en otro lado, porque
entonces podría decir una cosa y el programa hacer otra — que es exactamente el
error que esto viene a evitar.

Uso típico dentro de una función de cálculo::

    trace = FormulaTrace()
    tdh = vertical + friccion + cabeza
    trace.add(
        "TDH", "Altura dinámica total",
        "TDH = H_vert + H_fric + H_wh",
        {"H_vert": vertical, "H_fric": friccion, "H_wh": cabeza},
        tdh, "ft", "Brown Vol. 2b §4.5324",
    )
    return {..., "formulas": trace.as_list()}
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


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


@dataclass
class Formula:
    """Una cuenta del diseño, lista para mostrar y auditar.

    Attributes:
        key: Identificador estable para la UI (``"tdh"``, ``"stages"``…).
        label: Nombre en castellano de lo que se calcula.
        expression: La fórmula en símbolos, como está en el libro.
        substitution: La misma fórmula con los números reemplazados.
        inputs: Los valores que entraron, por nombre de símbolo.
        result: El resultado.
        units: Unidad del resultado.
        reference: De dónde sale la fórmula.
        note: Aclaración opcional (una condición de validez, un supuesto).
    """

    key: str
    label: str
    expression: str
    substitution: str
    inputs: dict[str, float]
    result: float
    units: str
    reference: str = ""
    note: str = ""


@dataclass
class FormulaTrace:
    """Acumula las fórmulas de un procedimiento, en orden de ejecución."""

    items: list[Formula] = field(default_factory=list)

    def add(
        self,
        key: str,
        label: str,
        expression: str,
        inputs: dict[str, float],
        result: float,
        units: str,
        reference: str = "",
        note: str = "",
    ) -> float:
        """Registra una cuenta y devuelve el resultado, para poder encadenar.

        La sustitución se arma reemplazando cada símbolo de ``expression`` por su
        valor en ``inputs``. Los símbolos se ordenan de más largo a más corto
        para que ``P_wf`` no se rompa al sustituir ``P``.

        Args:
            key: Identificador estable del paso.
            label: Qué se está calculando, en castellano.
            expression: Fórmula en símbolos.
            inputs: Valor de cada símbolo que aparece en la fórmula.
            result: Resultado de la cuenta.
            units: Unidad del resultado.
            reference: Cita bibliográfica.
            note: Condición de validez o supuesto, si corresponde.

        Returns:
            El mismo ``result`` que se le pasó.
        """
        sustituida = expression
        for simbolo in sorted(inputs, key=len, reverse=True):
            sustituida = sustituida.replace(simbolo, _fmt(inputs[simbolo]))

        self.items.append(Formula(
            key=key, label=label, expression=expression, substitution=sustituida,
            inputs={k: v for k, v in inputs.items()}, result=result,
            units=units, reference=reference, note=note,
        ))
        return result

    def as_list(self) -> list[dict]:
        """Las fórmulas como diccionarios, listas para serializar a JSON."""
        return [asdict(f) for f in self.items]

    def __len__(self) -> int:
        return len(self.items)
