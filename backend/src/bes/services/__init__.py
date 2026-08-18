"""Capa de servicios — orquestación agnóstica de framework.

Es la **fuente única de verdad** que hay detrás de la API. Coordina los
cálculos del dominio (``bes.core``) y devuelve **números crudos**: nunca
cadenas ya formateadas ni objetos de una interfaz gráfica.

Que sea agnóstica de framework significa que no importa ``fastapi`` ni
ninguna librería de UI. Así, si mañana hay otra interfaz —o un script batch,
o un trabajo programado— llama a esta misma capa y obtiene exactamente los
mismos resultados que la pantalla.

Ver ``.claude/rules/architecture.md``.
"""
