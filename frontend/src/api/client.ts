// Cliente HTTP tipado del backend BES Designer.
// En dev, Vite proxya /api -> http://localhost:8000 (ver vite.config.ts), así que
// la base es relativa. Se puede sobreescribir con VITE_API_BASE en producción.

import type {
  CatalogSummary,
  DesignRequest,
  DesignResponse,
  ExampleWell,
  NodalRequest,
  NodalResponse,
  PlotlyFigure,
  ReservoirInput,
  SensitivityRequest,
  SensitivityResponse,
  TubularCatalog,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

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
  productivity_index: "Índice de productividad", reservoir_temp: "Temperatura de reservorio",
  datum_depth: "Profundidad de referencia", ipr_method: "Método IPR",
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
  bottom_hole_temp: "Temp. de fondo",
  // Superficie
  wellhead_pressure_required: "Presión requerida en cabeza", flowline_length: "Longitud flowline",
  flowline_id: "ID flowline", flowline_elevation_change: "Cambio de elevación",
  separator_pressure: "Presión separador", power_supply_voltage: "Voltaje de superficie",
  frequency: "Frecuencia de red",
  // Objetivos
  target_flow_rate: "Caudal objetivo", safety_margin_depth: "Margen de profundidad",
  max_gip: "Máx. gas en bomba", design_life_years: "Vida de diseño",
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
    throw new ApiError(
      `No se pudo conectar al backend. ¿Está corriendo uvicorn en :8000? (${String(e)})`,
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
  catalogs: () => request<CatalogSummary>("/api/catalogs"),
  // Tablas dimensionales Tenaris (API 5CT): OD + peso -> ID y drift.
  tubulars: () => request<TubularCatalog>("/api/catalogs/tubulars"),
  examples: () => request<ExampleWell[]>("/api/examples"),
  design: (req: DesignRequest) => request<DesignResponse>("/api/design", req),
  nodal: (req: NodalRequest) => request<NodalResponse>("/api/nodal", req),
  pumpCurve: (p: { pump_model: string; operating_flow: number; stages: number }) =>
    request<{ figure: PlotlyFigure }>(
      `/api/plots/pump-curve?${new URLSearchParams({
        pump_model: p.pump_model,
        operating_flow: String(p.operating_flow),
        stages: String(p.stages),
      })}`
    ),
  // Curva IPR sin diseño previo: sólo necesita el reservorio.
  iprCurve: (reservoir: ReservoirInput) =>
    request<{ figure: PlotlyFigure }>("/api/plots/ipr-curve", reservoir),
  // Curva de catálogo cruda de una bomba (biblioteca ESP).
  pumpCatalogCurve: (pump_model: string) =>
    request<{ figure: PlotlyFigure }>(
      `/api/plots/pump-catalog-curve?${new URLSearchParams({ pump_model })}`
    ),
  sensitivity: (req: SensitivityRequest) =>
    request<SensitivityResponse>("/api/sensitivity", req),
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
