"""Los scripts de `scripts/` no tienen cobertura funcional (tocan catálogos y
regeneran docs), pero al menos tienen que importar y resolver sus rutas.

Existe por una regresión real: al migrar a `src/`, dos scripts quedaron
apuntando a `<raíz>/catalogs/`, que había dejado de existir. La suite siguió
verde porque nada los ejercitaba.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _ROOT / "scripts"

SCRIPT_NAMES = sorted(p.stem for p in _SCRIPTS.glob("*.py") if not p.stem.startswith("_"))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_there_are_scripts_to_check() -> None:
    """Si el glob no encuentra nada, los tests de abajo pasarían en vacío."""
    assert SCRIPT_NAMES, f"no se encontraron scripts en {_SCRIPTS}"


@pytest.mark.parametrize("name", SCRIPT_NAMES)
def test_script_imports(name: str) -> None:
    """Importar el script no debe explotar (detecta imports rotos tras un move)."""
    _load(name)


@pytest.mark.parametrize("name", SCRIPT_NAMES)
def test_script_paths_exist(name: str) -> None:
    """Toda constante Path de nivel de módulo tiene que apuntar a algo real.

    Cubre las rutas de entrada (catálogos, data). Se saltean las de salida, que
    el script crea al correr.
    """
    module = _load(name)
    missing = [
        f"{key} -> {value}"
        for key, value in vars(module).items()
        if isinstance(value, Path)
        and key.endswith(("_JSON", "_DIR"))
        and not value.exists()
    ]
    assert not missing, (
        f"{name}: rutas que no existen (¿se movio una carpeta?):\n  "
        + "\n  ".join(missing)
    )
