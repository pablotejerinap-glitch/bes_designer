# Reglas del frontend (React + Vite + TS) — Semana 3+

- **Stack:** Vite + React + TypeScript (estricto) + Mantine + `react-plotly.js`.
- **Cliente tipado generado desde OpenAPI** — no escribir tipos a mano; se generan
  desde el schema OpenAPI del backend (`/openapi.json`).
- **Gráficos:** la API devuelve Plotly figure JSON; el front solo lo pasa a un
  componente `<Plot>`. No reimplementar la lógica de gráficos en JS.
- **Sin lógica de negocio en el front:** todo cálculo vive en el backend/servicios.
  El front formatea y renderiza.
- **Orden de construcción (money-shot primero):** form 5-tabs → `/api/design` →
  vista de resultados → gráficos (curva de bomba + nodal) → descarga PDF/Excel.
  Comparación y sensibilidad son *stretch* (Streamlit las cubre para la defensa).
- **Red de seguridad:** `streamlit_app/` consume la MISMA API y es la demo
  garantizada para la defensa. Mantenerla viva.
