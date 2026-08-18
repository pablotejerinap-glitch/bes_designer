"""Backend FastAPI de BES Designer.

Es una capa HTTP **delgada** sobre los paquetes ``services/`` y ``core/``, que
son agnósticos de framework. Acá no hay lógica de negocio: se reciben pedidos,
se llama a los servicios y se devuelve JSON.

Ver ``.claude/rules/api-contract.md``.
"""
