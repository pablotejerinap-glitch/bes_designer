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
        "gip":                 resultado.get("gip", inc["gip"]),
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


class GasPasoAPasoRequest(GasCompleteDesignRequest):
    eta_separador: float = 0.75


@router.post("/paso-a-paso")
def post_gas_paso_a_paso(req: GasPasoAPasoRequest, catalog=Depends(get_catalog)) -> dict:
    """Método nuevo de gas, paso a paso (bes.core.gas_paso_a_paso).

    Devuelve cada bloque de cuentas (fórmula, sustitución, resultado y cita),
    la tabla de evolución del fluido en el pozo y la tabla de escalones.
    """
    return _paso_a_paso(req, catalog)[0]


class GasMemoriaRequest(GasPasoAPasoRequest):
    titulo: str | None = None


@router.post("/memoria")
def post_gas_memoria(req: GasMemoriaRequest, formato: str = "html", catalog=Depends(get_catalog)):
    """Memoria de cálculo del método de gas paso a paso (HTML imprimible o PDF)."""
    from fastapi import HTTPException
    from fastapi.responses import Response

    from bes.reports.memoria import PDFNoDisponible, html_a_pdf
    from bes.reports.memoria.gas_nuevo import memoria_gas_html

    calculo, datos = _paso_a_paso(req, catalog)
    html = memoria_gas_html(calculo, datos, (req.titulo or "").strip())
    if formato == "html":
        return Response(content=html, media_type="text/html; charset=utf-8")
    if formato != "pdf":
        raise HTTPException(status_code=404, detail=f"Formato '{formato}' no soportado (html|pdf)")
    try:
        data = html_a_pdf(html)
    except PDFNoDisponible as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="memoria_de_calculo_gas.pdf"'})


def _paso_a_paso(req: GasPasoAPasoRequest, catalog) -> tuple[dict, dict]:
    """Corre el método y devuelve (respuesta, datos de entrada con los nombres de calcular)."""
    from dataclasses import asdict

    from fastapi import HTTPException

    from bes.core import gas_paso_a_paso as G

    r, f, w, s, o = req.reservoir, req.fluid, req.well, req.surface, req.objectives
    # Mismas validaciones de datos que el diseño normal (punzados, tubing, etc.).
    try:
        to_reservoir(r); to_fluid(f); to_well(w); to_surface(s); to_objectives(o)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Misma convención que el diseño normal: si no se carga, la bomba va en el
    # tope de los punzados menos el margen de seguridad.
    d_bomba = (req.pump_depth or w.pump_setting_depth
               or max(w.perforations_top - (o.safety_margin_depth or 0.0), 100.0))
    hz = o.design_frequency_hz or s.frequency
    datos = dict(
        pr=r.static_pressure, pb=r.bubble_point, pwf_ensayo=r.test_pwf, q_ensayo=r.test_rate,
        q_objetivo=o.target_flow_rate, api=f.oil_api or 0.0, wc=f.water_cut, gor=f.gor,
        gas_sg=f.gas_sg, water_sg=f.water_sg, t_boca=w.wellhead_temp, t_fondo=r.reservoir_temp,
        d_pwf=w.perforations_bottom, d_bomba=d_bomba, p_boca=s.wellhead_pressure_required,
        d_tubing_in=w.tubing_id, eta_sep=req.eta_separador, casing_id=w.casing_id,
        frecuencia_hz=hz, incremento_psi=req.increment_psi,
        desviacion_max=w.deviation_max or 0.0, usa_vsd=bool(o.use_vsd))
    try:
        res, bloques = G.calcular(catalog_manager=catalog, **datos)
    except (NotImplementedError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    tabla = G.tabla_evolucion(res, o.target_flow_rate, f.water_cut, f.gor, f.oil_api or 0.0,
                              f.gas_sg, f.water_sg, r.reservoir_temp, w.wellhead_temp)
    inc = res.get("incrementos") or {}
    sel = res.get("seleccion") or {}
    mec = res.get("mecanica") or {}
    pro = res.get("protector") or {}
    mot = res.get("motor") or {}
    cab = res.get("cable") or {}
    sup = res.get("superficie") or {}
    return ({
        "bloques": [{"titulo": t, "pasos": [asdict(p) for p in ps]} for t, ps in bloques],
        "tabla_evolucion": tabla,
        "escalones": inc.get("tramos", []),
        "resumen": {
            "pwf": res["pwf"], "pip": res["pip"], "t_admision": res["t_adm"],
            "gor_bomba": res["succion"]["gor_bomba"], "gas_libre_bomba": res["succion"]["f_bomba"],
            "p_descarga": (res.get("descarga") or {}).get("p_descarga"),
            "bomba": f"{sel.get('fabricante', '')} {sel.get('modelo', '')}".strip(),
            "frecuencia_hz": hz, "etapas": inc.get("etapas"), "etapas_exactas": inc.get("etapas_exactas"),
            "hp": inc.get("hp"),
            "eje": mec.get("eje"), "carcasa": mec.get("carcasa"), "p_max_carcasa": mec.get("p_max"),
            "carcasas": mec.get("carcasas"), "etapas_ciegas": mec.get("etapas_ciegas"),
            "largo_bomba_ft": mec.get("largo_ft"),
            "protector": pro.get("protector"), "protector_pn": pro.get("part_number"),
            "protector_largo_ft": pro.get("largo_ft"), "elastomero": pro.get("elastomero"),
            "serie_motor": ", ".join(pro.get("serie_motor") or []) or None,
            "motor": mot.get("motor"), "motor_n": mot.get("n"), "motor_arreglo": mot.get("arreglo"),
            "motor_hp": mot.get("hp_placa"), "motor_voltaje": mot.get("voltaje"),
            "motor_corriente": mot.get("corriente"), "bhp_sistema": mot.get("bhp_sistema"),
            "v_anular": mot.get("v_anular"),
            "cable": (f"{cab['fabricante']} {cab['tipo']} {cab['calibre']} AWG {cab['conductor']}" if cab else None),
            "cable_largo_ft": cab.get("largo_ft"), "cable_caida_v": cab.get("caida"),
            "mle_largo_ft": cab.get("mle_ft"), "u_superficie": sup.get("u_superficie"),
            "kva": sup.get("kva"), "tablero": sup.get("tablero"),
            "transformador_kva": sup.get("transformador_kva"), "transformador_pn": sup.get("transformador_pn"),
        },
    }, datos)
