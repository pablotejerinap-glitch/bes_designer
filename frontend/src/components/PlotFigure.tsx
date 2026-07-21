// La API devuelve Plotly figure JSON (ver .claude/rules/api-contract.md).
// Este componente sólo lo pasa a <Plot> — no hay lógica de gráficos en el front.
//
// Usamos el factory con `plotly.js-dist-min` porque el import por defecto de
// `react-plotly.js` resuelve el bundle completo `plotly.js`, que no está
// instalado (y pesa ~3 MB más).
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import type { PlotlyFigure } from "../api/types";

const Plot = createPlotlyComponent(Plotly);

export function PlotFigure({ figure, height = 460 }: { figure: PlotlyFigure; height?: number }) {
  return (
    <Plot
      data={figure.data as Plotly.Data[]}
      layout={{
        ...(figure.layout as Partial<Plotly.Layout>),
        autosize: true,
        // El alto lo fija el contenedor; sacamos el que venga del builder de Python.
        height: undefined,
        margin: { t: 40, r: 20, b: 48, l: 60 },
      }}
      config={{ displaylogo: false, responsive: true }}
      style={{ width: "100%", height }}
      useResizeHandler
    />
  );
}
