// Cliente HTTP tipado del backend BES Designer.
// En dev, Vite proxya /api → http://localhost:8000 (ver vite.config.ts), así que
// la base es relativa. Se puede sobreescribir con VITE_API_BASE en producción.

import type {
  CatalogSummary,
  DesignRequest,
  DesignResponse,
  ExampleWell,
  NodalRequest,
  NodalResponse,
  PlotlyFigure,
  SensitivityRequest,
  SensitivityResponse,
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
      if (typeof j.detail === "string") detail = j.detail;
      else if (Array.isArray(j.detail)) detail = j.detail.map((d: { msg?: string }) => d.msg).join("; ");
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
      detail = (await resp.json()).detail ?? detail;
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
