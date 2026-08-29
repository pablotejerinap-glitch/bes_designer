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
  La comparación de opciones ya está cubierta (tab de resultados).
- **El análisis de sensibilidad se retiró** (ago-2026): no hacía falta en el
  proyecto. No volver a agregarlo sin que Pablo lo pida.
- **UI única:** React es la única interfaz. La app Streamlit se retiró al
  alcanzar paridad; si hace falta una vista nueva, va acá, no a otra UI.
