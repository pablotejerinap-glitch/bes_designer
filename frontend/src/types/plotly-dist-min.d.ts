// `plotly.js-dist-min` no trae tipos propios; reusamos los de @types/plotly.js
// (que ya entra como dependencia de @types/react-plotly.js).
declare module "plotly.js-dist-min" {
  const Plotly: typeof import("plotly.js");
  export default Plotly;
}
