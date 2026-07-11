---
name: add-domain-function
description: Checklist para agregar un cálculo o correlación nueva al dominio (core/) de BES Designer, validándolo contra el libro de Brown y agregando un test. Usar al implementar física/ingeniería nueva.
---

# Agregar una función de dominio (core/)

Leé primero `.claude/rules/domain.md`.

## Pasos

1. **Ubicación**: la función va en el módulo de `core/` que corresponda
   (`ipr`, `pvt`, `multiphase`, `tdh`, `pump_design`, `electrical`,
   `gas_handling`, `nodal_analysis`). Si necesita catálogo, recibí
   `catalog_manager` como argumento (inyección, solo lectura).
2. **Pureza**: función pura, sin estado ni side-effects, sin imports de framework
   (ni streamlit ni fastapi). Opera sobre las dataclasses de `core/models.py`.
3. **Unidades**: respetá la convención (psia, °F, STB/d, ft, in, hp, V/A). Documentá
   las unidades de cada argumento y del retorno en el docstring.
4. **Validación**: si agregás un modelo nuevo a `models.py`, poné validación en
   `__post_init__` con `ValueError` y mensaje claro (patrón existente).
5. **Referencia del libro**: identificá el ejemplo de Brown (§ y número) que valida
   el cálculo. Si no hay ejemplo directo, documentá la fuente de la correlación.
6. **Test** (`tests/test_<modulo>.py`): agregá un test que compare contra el valor
   de referencia del libro (tolerancia razonable; ver `test_integration.py`).
7. **Correr** `pytest -q` — 545 + el nuevo, todo verde.

## Regla de oro
Ningún cálculo nuevo entra sin un test que lo ancle a un valor del libro de Brown.
