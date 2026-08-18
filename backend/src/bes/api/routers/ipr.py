"""POST /api/ipr/from-test — deriva la entregabilidad de un ensayo de producción.

El formulario carga el ensayo (Pwf medida + caudal medido) y muestra el índice
de productividad resultante en solo lectura. El cálculo vive acá abajo, en
``bes.core.ipr``: el front no despeja nada (``.claude/rules/frontend.md``).
"""
from __future__ import annotations

from fastapi import APIRouter

from bes.api.schemas.analysis import IPRFromTestResponse
from bes.api.schemas.inputs import IPRFromTestRequest
from bes.core.ipr import productivity_index_from_test
from bes.core.models import IPRMethod

router = APIRouter(prefix="/api/ipr", tags=["ipr"])

_IPR_BY_NAME = {m.name.lower(): m for m in IPRMethod}


@router.post("/from-test", response_model=IPRFromTestResponse)
def post_ipr_from_test(req: IPRFromTestRequest) -> IPRFromTestResponse:
    """Índice de productividad (y C de Fetkovich) a partir de un ensayo.

    Invierte el modelo IPR elegido para que la curva pase exactamente por el
    punto ensayado: lineal despeja J directo, Vogel pasa por qmax, y Fetkovich
    despeja C con el n dado (un solo punto no permite ajustar C y n a la vez).

    Un ensayo físicamente inválido —Pwf mayor o igual a la estática, caudal
    nulo— sale como HTTP 422 por el handler central.
    """
    derived = productivity_index_from_test(
        pr=req.static_pressure,
        pwf_test=req.test_pwf,
        q_test=req.test_rate,
        method=_IPR_BY_NAME[req.ipr_method.value],
        fetkovich_n=req.fetkovich_n,
        bubble_point=req.bubble_point,
    )
    return IPRFromTestResponse(**derived)
