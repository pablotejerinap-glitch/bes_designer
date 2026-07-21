"""BES Designer — diseño automatizado de sistemas de Bombeo Electrosumergible.

Metodología Kermit Brown, *The Technology of Artificial Lift Methods*, Vol. 2b,
Cap. 4.5.

Capas (ver ``.claude/rules/architecture.md``):

- ``bes.core``        — dominio puro; no importa ningún framework.
- ``bes.catalogs``    — catálogos JSON de equipos + queries.
- ``bes.recommender`` — selección de bombas y ordenamiento por criterios.
- ``bes.reports``     — generación de PDF/Excel.
- ``bes.services``    — orquestación agnóstica de framework (números crudos).
- ``bes.plotting``    — builders Plotly; agnósticos, los consume la API.
- ``bes.api``         — capa de entrega HTTP (FastAPI).

Los adaptadores de entrega (``bes.api``, ``frontend/``) dependen de las capas
de abajo, nunca al revés.
"""
