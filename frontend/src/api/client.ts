// Cliente HTTP tipado del backend BES Designer.
// En dev, Vite proxya /api -> http://localhost:8000 (ver vite.config.ts), así que
// la base es relativa. Se puede sobreescribir con VITE_API_BASE en producción.

import type {
  AffinityResponse,
  CatalogSummary,
  DesignRequest,
  DesignResponse,
  FormulaCatalog,
  GasCompleteDesignRequest,
  GasCompleteDesignResponse,
  GasIncrementRequest,
  GasIncrementResponse,
  IPRFromTestResponse,
  IPRMethod,
  NodalRequest,
  NodalResponse,
  PlotlyFigure,
  ReservoirInput,
  TubularCatalog,
} from "./types";

// Origen del backend. Vacío = mismo origen, que es lo que vale en dev (Vite
// proxya /api al :8000) y detrás de nginx en docker-compose. En Netlify el
// estático y la API viven en dominios distintos y hay que declararlo.
//
// Se le saca la barra final: los `path` de este archivo empiezan con "/api",
// así que una base terminada en "/" armaría "https://host//api/design". La
// mayoría de los servidores lo toleran, pero no todos, y el que no lo tolera
// devuelve 404 sin explicar por qué.
//
// El cast quedó de más: VITE_API_BASE ahora está declarada en vite-env.d.ts.
const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// Etiquetas en español por clave de campo, para que los errores de validación
// digan QUÉ campo falló (Pydantic sólo devuelve la clave interna en `loc`).
const FIELD_LABELS: Record<string, string> = {
  // Reservorio
  static_pressure: "Presión estática", bubble_point: "Presión de burbuja",
  test_pwf: "Pwf del ensayo", test_rate: "Caudal del ensayo",
  productivity_index: "Índice de productividad", reservoir_temp: "Temperatura de reservorio",
  ipr_method: "Método IPR",
  drive_mechanism: "Mecanismo de empuje", fetkovich_c: "Coeficiente C de Fetkovich",
  fetkovich_n: "Exponente n de Fetkovich",
  // Fluido
  oil_api: "Gravedad API", water_cut: "Corte de agua", gor: "GOR", gas_sg: "SG del gas",
  water_sg: "SG de la salmuera", oil_viscosity_dead: "Viscosidad dead-oil",
  viscosity_temp_ref: "Temp. ref. viscosidad", bubble_point_pressure: "Pb del fluido",
  h2s_content: "H2S", co2_content: "CO2", sand_production: "Producción de arena",
  // Geometría
  total_depth: "Profundidad total", casing_od: "OD casing", casing_weight: "Peso casing",
  casing_id: "ID casing", tubing_od: "OD tubing", tubing_id: "ID tubing",
  perforations_top: "Tope perforaciones", perforations_bottom: "Base perforaciones",
  deviation_max: "Desviación máxima", wellhead_temp: "Temp. boca de pozo",
  // Superficie
  wellhead_pressure_required: "Presión en cabeza (Pth)", flowline_length: "Longitud flowline",
  flowline_id: "ID flowline", flowline_elevation_change: "Cambio de elevación",
  separator_pressure: "Presión separador", power_supply_voltage: "Voltaje de superficie",
  frequency: "Frecuencia de red",
  // Objetivos
  target_flow_rate: "Caudal objetivo", safety_margin_depth: "Margen de profundidad",
  max_gip: "Máx. gas en bomba", design_life_years: "Vida de diseño",
  design_frequency_hz: "Frecuencia de diseño (VSD)",
  allow_gas_venting: "Permite venteo de gas", use_vsd: "Usar variador (VSD)",
};

interface PydError {
  type?: string;
  loc?: (string | number)[];
  msg?: string;
  ctx?: Record<string, unknown>;
}

function fieldLabel(loc?: (string | number)[]): string | null {
  if (!loc) return null;
  for (let i = loc.length - 1; i >= 0; i--) {
    const k = loc[i];
    if (typeof k === "string" && FIELD_LABELS[k]) return FIELD_LABELS[k];
  }
  const last = [...loc].reverse().find((x) => typeof x === "string" && x !== "body");
  return typeof last === "string" ? last : null;
}

// Traduce el mensaje crudo de Pydantic a algo corto y en español, usando el
// tipo de error y su contexto (el límite viene en `ctx`).
function translatePyd(e: PydError): string {
  const c = e.ctx ?? {};
  switch (e.type) {
    case "greater_than": return `debe ser > ${c.gt}`;
    case "greater_than_equal": return `debe ser ≥ ${c.ge}`;
    case "less_than": return `debe ser < ${c.lt}`;
    case "less_than_equal": return `debe ser ≤ ${c.le}`;
    case "missing": return "es obligatorio";
    case "float_parsing": case "int_parsing":
    case "float_type": case "int_type": return "debe ser un número válido";
    default: return e.msg ?? "valor inválido";
  }
}

// Convierte el `detail` de un error (string del dominio o array de Pydantic) en
// un mensaje legible para el usuario.
function parseErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = (detail as PydError[]).map((e) => {
      const label = fieldLabel(e.loc);
      const msg = translatePyd(e);
      return label ? `${label}: ${msg}` : msg;
    });
    if (parts.length) return parts.join(" · ");
  }
  return fallback;
}

async function request<T>(path: string, body?: unknown): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${BASE}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    // El motivo depende de dónde está el backend, y confundirlos hace perder
    // tiempo: en dev casi siempre es que uvicorn no está levantado; con una
    // base configurada, que ese origen no responde o que rechazó el CORS.
    throw new ApiError(
      BASE
        ? `No se pudo conectar al backend en ${BASE}. Puede estar caído, o no ` +
          `tener este dominio en BES_CORS_ORIGINS. (${String(e)})`
        : `No se pudo conectar al backend. ¿Está corriendo uvicorn en :8000? ` +
          `(${String(e)})`,
      0
    );
  }
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const j = await resp.json();
      detail = parseErrorDetail(j.detail, detail);
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new ApiError(detail, resp.status);
  }
  return (await resp.json()) as T;
}

async function requestBlob(path: string, body: unknown): Promise<Blob> {
  const resp = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      detail = parseErrorDetail((await resp.json()).detail, detail);
    } catch {
      /* noop */
    }
    throw new ApiError(detail, resp.status);
  }
  return await resp.blob();
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  // Todas las fórmulas del motor, sin correr ningún diseño. Incluye las
  // variantes que un caso concreto no ejecuta (Fetkovich cuando el pozo se
  // resolvió por Vogel), que es justamente lo que la traza sola no muestra.
  formulas: () => request<FormulaCatalog>("/api/formulas"),
  catalogs: () => request<CatalogSummary>("/api/catalogs"),
  // Tablas dimensionales Tenaris (API 5CT): OD + peso -> ID y drift.
  tubulars: () => request<TubularCatalog>("/api/catalogs/tubulars"),
  design: (req: DesignRequest) => request<DesignResponse>("/api/design", req),
  nodal: (req: NodalRequest) => request<NodalResponse>("/api/nodal", req),
  pumpCurve: (p: {
    pump_model: string;
    operating_flow: number;
    stages: number;
    /** Frecuencia de operación [Hz]: reescala la curva de catálogo. */
    frequency?: number;
    /** Sólo pozos con gas: dibuja la zona operativa del método de
     *  incrementos (0.75 a 1.25 × el caudal representativo) con los caudales
     *  de admisión y descarga marcados. */
    q_representative?: number;
    q_intake?: number;
    q_discharge?: number;
  }) => {
    const q = new URLSearchParams({
      pump_model: p.pump_model,
      operating_flow: String(p.operating_flow),
      stages: String(p.stages),
    });
    if (p.frequency) q.set("frequency", String(p.frequency));
    // Las tres van juntas o no va ninguna: sin el representativo no hay banda
    // contra la cual leer los extremos.
    if (p.q_representative) {
      q.set("q_representative", String(p.q_representative));
      if (p.q_intake) q.set("q_intake", String(p.q_intake));
      if (p.q_discharge) q.set("q_discharge", String(p.q_discharge));
    }
    return request<{ figure: PlotlyFigure }>(`/api/plots/pump-curve?${q}`);
  },
  // Curva IPR sin diseño previo: sólo necesita el reservorio.
  iprCurve: (reservoir: ReservoirInput) =>
    request<{ figure: PlotlyFigure }>("/api/plots/ipr-curve", reservoir),
  // Índice de productividad derivado del ensayo. El despeje vive en el
  // backend (bes.core.ipr); acá sólo se muestra el resultado.
  iprFromTest: (req: {
    static_pressure: number;
    test_pwf: number;
    test_rate: number;
    ipr_method: IPRMethod;
    // Vogel la necesita: separa el tramo recto de la IPR (arriba de Pb) del
    // curvo (abajo). Sin ella se degrada a Vogel puro y sobreestima J.
    bubble_point: number;
    fetkovich_n?: number | null;
  }) => request<IPRFromTestResponse>("/api/ipr/from-test", req),
  // Leyes de afinidad: la misma bomba a distintas frecuencias.
  affinity: (p: {
    pump_model: string;
    frequencies: string;
    diameter_ratio?: number;
    sg_ratio?: number;
    target_flow?: number;
  }) => {
    const q = new URLSearchParams({
      pump_model: p.pump_model,
      frequencies: p.frequencies,
      diameter_ratio: String(p.diameter_ratio ?? 1),
      sg_ratio: String(p.sg_ratio ?? 1),
    });
    if (p.target_flow) q.set("target_flow", String(p.target_flow));
    return request<AffinityResponse>(`/api/affinity?${q}`);
  },
  affinityFigure: (p: {
    pump_model: string;
    frequencies: string;
    diameter_ratio?: number;
    sg_ratio?: number;
    target_flow?: number;
  }) => {
    const q = new URLSearchParams({
      pump_model: p.pump_model,
      frequencies: p.frequencies,
      diameter_ratio: String(p.diameter_ratio ?? 1),
      sg_ratio: String(p.sg_ratio ?? 1),
    });
    if (p.target_flow) q.set("target_flow", String(p.target_flow));
    return request<{ figure: PlotlyFigure }>(`/api/affinity/figure?${q}`);
  },
  // Curva de catálogo cruda de una bomba (biblioteca ESP).
  pumpCatalogCurve: (pump_model: string) =>
    request<{ figure: PlotlyFigure }>(
      `/api/plots/pump-catalog-curve?${new URLSearchParams({ pump_model })}`
    ),
  // Método de incrementos de presión para pozos con gas (Brown §4.53103):
  // resuelve la bomba tramo por tramo desde la admisión hasta la descarga.
  gasIncrementDesign: (req: GasIncrementRequest) =>
    request<GasIncrementResponse>("/api/gas/increment-design", req),
  // Diseño COMPLETO por incrementos: termina en aparejo (bomba, motor, sello,
  // cable, transformador), no sólo en etapas y potencia.
  gasCompleteDesign: (req: GasCompleteDesignRequest) =>
    request<GasCompleteDesignResponse>("/api/gas/design", req),
  report: (fmt: "pdf" | "xlsx", req: DesignRequest & { rank?: number }) =>
    requestBlob(`/api/reports/${fmt}`, req),
};

// Dispara la descarga de un Blob en el navegador.
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
