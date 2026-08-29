"""Tests que hacen ejecutable la regla de dirección de dependencias.

`.claude/rules/architecture.md` declara que el dominio nunca importa un
framework y que las capas dependen hacia abajo. Eso era hasta ahora una regla
escrita: acá se verifica sola.

El chequeo es **estático** (AST) y no por import: un `import fastapi` adentro de
un `if TYPE_CHECKING:` o de una función igual violaría la capa, y un test que
sólo importe el módulo no lo detectaría.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src" / "bes"

# Capas que NO pueden depender de un framework de entrega ni de persistencia.
DOMAIN_PACKAGES = ["core", "catalogs", "recommender", "reports", "services", "plotting"]

FORBIDDEN_FRAMEWORKS = {"streamlit", "fastapi", "sqlalchemy"}


def _module_files(package: str) -> list[Path]:
    return sorted(p for p in (_SRC / package).rglob("*.py") if "__pycache__" not in p.parts)


def _imported_roots(path: Path) -> set[str]:
    """Módulos raíz importados por un archivo (`a.b.c` -> `a`), a cualquier
    profundidad del AST: nivel de módulo, dentro de función o de un `if`."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # level > 0 es un import relativo (`from .x import y`): nunca externo.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _is_type_checking_guard(node: ast.AST) -> bool:
    """¿Es un `if TYPE_CHECKING:` (o `if typing.TYPE_CHECKING:`)?"""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def _runtime_nodes(tree: ast.AST) -> list[ast.AST]:
    """Nodos que se ejecutan de verdad: excluye los cuerpos de `if TYPE_CHECKING:`.

    Un import ahí adentro existe sólo para anotar tipos y no acopla en runtime.
    Es el patrón de inyección de dependencias que usa `bes.core`: recibe el
    `CatalogManager` por parámetro e importa el nombre sólo para tiparlo.
    """
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if _is_type_checking_guard(node):
            for child in node.body:
                for inner in ast.walk(child):
                    skipped.add(id(inner))
    return [n for n in ast.walk(tree) if id(n) not in skipped]


def _imported_bes_subpackages(path: Path) -> set[str]:
    """Subpaquetes de `bes` importados **en runtime**: `from bes.api.deps import x`
    -> `api`. Los imports de tipo (TYPE_CHECKING) no cuentan como dependencia."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    subs: set[str] = set()
    for node in _runtime_nodes(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        for name in names:
            parts = name.split(".")
            if len(parts) >= 2 and parts[0] == "bes":
                subs.add(parts[1])
    return subs


def test_src_layout_exists() -> None:
    """Si esto falla, el resto de los tests de arquitectura pasarían en vacío."""
    assert _SRC.is_dir(), f"no existe {_SRC}"
    for package in DOMAIN_PACKAGES:
        assert (_SRC / package).is_dir(), f"falta el paquete bes/{package}"


@pytest.mark.parametrize("package", DOMAIN_PACKAGES)
def test_domain_does_not_import_frameworks(package: str) -> None:
    """El dominio no importa streamlit / fastapi / sqlalchemy.

    Es la regla 1-2-4 de architecture.md. `bes.plotting` entra acá a propósito:
    la API lo consume, así que si alguien le mete streamlit rompe el backend.
    """
    offenders: list[str] = []
    for path in _module_files(package):
        bad = _imported_roots(path) & FORBIDDEN_FRAMEWORKS
        if bad:
            offenders.append(f"{path.relative_to(_SRC.parent)} importa {sorted(bad)}")
    assert not offenders, (
        "El dominio no puede depender de un framework de entrega:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("package", DOMAIN_PACKAGES)
def test_domain_does_not_import_the_api_layer(package: str) -> None:
    """La dependencia va hacia abajo: `bes.api` conoce al dominio, no al revés."""
    offenders: list[str] = []
    for path in _module_files(package):
        if "api" in _imported_bes_subpackages(path):
            offenders.append(str(path.relative_to(_SRC.parent)))
    assert not offenders, (
        "El dominio no puede importar bes.api (invierte la dirección de "
        "dependencias):\n  " + "\n  ".join(offenders)
    )


def test_core_is_the_bottom_layer() -> None:
    """`bes.core` no depende **en runtime** de ninguna otra capa del paquete.

    `electrical.py`, `pump_design.py` y `gas_handling.py` mencionan
    `CatalogManager`, pero sólo bajo `if TYPE_CHECKING:`: el catálogo entra
    inyectado por parámetro. Ese import de tipo no invierte nada, y por eso
    `_runtime_nodes` lo descarta.
    """
    allowed = {"core"}
    offenders: list[str] = []
    for path in _module_files("core"):
        extra = _imported_bes_subpackages(path) - allowed
        if extra:
            offenders.append(f"{path.relative_to(_SRC.parent)} importa bes.{sorted(extra)}")
    assert not offenders, (
        "bes.core es la capa de más abajo y no puede depender de otras:\n  "
        + "\n  ".join(offenders)
    )


def test_no_streamlit_app_left_behind() -> None:
    """Streamlit se retiró cuando React alcanzó paridad. `streamlit` sigue
    en FORBIDDEN_FRAMEWORKS a propósito: es lo
    que impide que vuelva a filtrarse en el dominio, sobre todo en
    `bes.plotting`, que lo consume la API.
    """
    root = _SRC.parent.parent
    assert not (root / "streamlit_app").exists(), (
        "streamlit_app/ volvió a aparecer: la UI es frontend/ (React)"
    )
