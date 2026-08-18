"""POST /api/gas/increment-design — método de incrementos de presión.

Reproduce el procedimiento de Kermit Brown Vol. 2b §4.53103 para pozos con gas
libre: divide el salto de presión de la bomba en escalones, evalúa el fluido en
los dos extremos de cada uno y resuelve etapas y potencia tramo por tramo.

El cálculo vive en ``bes.services.gas_service``; acá sólo se mapean los
esquemas. Un diseño inviable sale como HTTP 422 por el handler central de
``main.py``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from bes.api.deps import get_catalog
from bes.api.mappers import (
    to_fluid, to_objectives, to_reservoir, to_surface, to_well,
)
from bes.api.schemas.analysis import (
    GasCompleteDesignRequest,
    GasCompleteDesignResponse,
    GasIncrementRequest,
    GasIncrementResponse,
    PVTTableSchema,
)
from bes.core.pvt import PVTPoint, PVTTable
from bes.plotting import plot_gas_increment_ladder
from bes.services.gas_service import (
    run_gas_design_complete,
    run_gas_increment_design,
)

router = APIRouter(prefix="/api/gas", tags=["gas"])


def _to_pvt_table(schema: PVTTableSchema | None) -> PVTTable | None:
    """Esquema Pydantic → dataclass del dominio (``.claude/rules/api-contract.md``)."""
    if schema is None:
        return None
    return PVTTable(
        points=[PVTPoint(**p.model_dump()) for p in schema.points],
        source=schema.source,
        temperature_f=schema.temperature_f,
    )


def _ladder(rows: list[dict], resumen: dict) -> dict:
    """Escalera de incrementos como Plotly figure JSON (Brown Fig. 4.56B).

    El gráfico acompaña al cálculo y viaja dentro de su respuesta, que es la
    convención del proyecto para figuras que dependen de un cómputo (ver
    ``.claude/rules/api-contract.md``). Nunca hace fallar al diseño: si la
    figura no se puede armar, la respuesta sale sin ella.
    """
    import json

    try:
        fig = plot_gas_increment_ladder(
            rows,
            p_intake=resumen["p_intake"],
            p_discharge=resumen["p_discharge"],
            pump_model=resumen.get("pump_model", "") or "",
            total_stages=resumen.get("total_stages"),
        )
        return json.loads(fig.to_json())
    except (ValueError, KeyError):
        return {}


@router.post("/increment-design", response_model=GasIncrementResponse)
def post_gas_increment_design(
    req: GasIncrementRequest, catalog=Depends(get_catalog)
) -> GasIncrementResponse:
    """Diseño por incrementos de presión para un pozo con gas.

    Con ``p_intake`` y ``p_discharge`` vacíos las presiones se calculan con el
    recorrido multifásico; pasándolas se reproduce un caso con las presiones ya
    conocidas (los ejemplos impresos del libro, por ejemplo).
    """
    resultado = run_gas_increment_design(
        reservoir=to_reservoir(req.reservoir),
        fluid=to_fluid(req.fluid),
        well=to_well(req.well),
        surface=to_surface(req.surface),
        objectives=to_objectives(req.objectives),
        catalog_manager=catalog,
        pump_depth=req.pump_depth,
        increment_psi=req.increment_psi,
        p_intake=req.p_intake,
        p_discharge=req.p_discharge,
        vent_gas_pct=req.vent_gas_pct,
        apply_deterioration=req.apply_deterioration,
        apply_viscosity=req.apply_viscosity,
        fixed_pump_model=req.fixed_pump_model,
        pvt_table=_to_pvt_table(req.pvt_table),
    )

    return GasIncrementResponse(
        summary=resultado["summary"],
        increments=resultado["increments"],
        free_gas_fraction_at_intake=resultado["gas"]["free_gas_fraction_at_intake"],
        gas_risk=resultado["gas"]["risk"],
        separator=resultado["gas"]["separator"],
        warnings=resultado["warnings"],
        ladder_figure=_ladder(resultado["increments"], resultado["summary"]),
        formulas=resultado["formulas"],
    )


@router.post("/design", response_model=GasCompleteDesignResponse)
def post_gas_complete_design(
    req: GasCompleteDesignRequest, catalog=Depends(get_catalog)
) -> GasCompleteDesignResponse:
    """Diseño BES **completo** por el método de incrementos de presión.

    A diferencia de ``/increment-design``, que devuelve sólo la hidráulica,
    este termina en un aparejo seleccionable: bomba, carcasas, motor, sello,
    cable, transformador y VSD. El armado usa el mismo camino que el diseño
    convencional, así que ``design`` es el esquema de resultados de siempre.

    Si ninguna bomba del catálogo completa el aparejo, sale 422 con el motivo
    de cada candidata descartada.
    """
    import dataclasses

    resultado = run_gas_design_complete(
        reservoir=to_reservoir(req.reservoir),
        fluid=to_fluid(req.fluid),
        well=to_well(req.well),
        surface=to_surface(req.surface),
        objectives=to_objectives(req.objectives),
        catalog_manager=catalog,
        pump_depth=req.pump_depth,
        increment_psi=req.increment_psi,
        vent_gas_pct=req.vent_gas_pct,
        apply_deterioration=req.apply_deterioration,
        apply_viscosity=req.apply_viscosity,
        fixed_pump_model=req.fixed_pump_model,
        pvt_table=_to_pvt_table(req.pvt_table),
    )

    inc = resultado["increment"]
    fluido = to_fluid(req.fluid)
    objetivos = to_objectives(req.objectives)

    resumen = {
        "p_intake":            inc["p_intake"],
        "p_discharge":         inc["p_discharge"],
        "delta_p":             inc["delta_p"],
        "increment_psi":       inc["increment_psi"],
        "n_increments":        inc["n_increments"],
        "target_oil_rate":     objetivos.target_flow_rate * (1.0 - fluido.water_cut),
        "target_liquid_rate":  objetivos.target_flow_rate,
        "q_mix_intake_bpd":    inc["q_mix_intake_bpd"],
        "q_mix_discharge_bpd": inc["q_mix_discharge_bpd"],
        "q_mix_max_bpd":       inc["q_mix_max_bpd"],
        "q_mix_min_bpd":       inc["q_mix_min_bpd"],
        "mass_rate_lbm_d":     inc["mass_rate_lbm_d"],
        "total_stages":        inc["total_stages"],
        "total_stages_exact":  inc["total_stages_exact"],
        "total_stages_longhand": inc["total_stages_longhand"],
        "total_hp":            inc["total_hp"],
        "pump_model":          inc["pump_model"],
        "pump_manufacturer":   inc["pump_manufacturer"],
        "pump_series":         inc["pump_series"],
        "pump_setting_depth":  resultado["pump_setting_depth"],
        "pump_intake_temp_f":  resultado["pump_intake_temp_f"],
        "pvt_source":          inc["pvt_source"],
        "gip":                 inc["gip"],
    }

    return GasCompleteDesignResponse(
        design=dataclasses.asdict(resultado["design"]),
        method=resultado["method"],
        feasibility=resultado["feasibility"],
        increments=inc["increment_table"],
        summary=resumen,
        tdh_increment_ft=resultado["tdh_increment_ft"],
        tdh_conventional_ft=resultado["tdh_conventional_ft"],
        rejected=resultado["rejected"],
        warnings=resultado["warnings"],
        ladder_figure=_ladder(inc["increment_table"], resumen),
    )
