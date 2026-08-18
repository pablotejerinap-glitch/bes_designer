// Gráficos que acompañan una recomendación: curva de bomba + análisis nodal.
// Las figuras las arma el backend (ui/plots.py) y viajan como Plotly JSON.
import { lazy, Suspense, useEffect, useState } from "react";
import { Alert, Group, Loader, Tabs, Text } from "@mantine/core";
import { api, ApiError } from "../api/client";
import type { DesignInputs, DesignResult, PlotlyFigure } from "../api/types";

// Plotly pesa ~4 MB: lo sacamos del bundle inicial y lo bajamos recién cuando
// hay una recomendación en pantalla. `lazy` espera un default export.
const PlotFigure = lazy(() =>
  import("./PlotFigure").then((m) => ({ default: m.PlotFigure }))
);

type State =
  | { status: "loading" }
  | { status: "ok"; figure: PlotlyFigure }
  | { status: "error"; message: string };

/** Carga una figura una sola vez, cancelando el set si el componente se desmonta. */
function useFigure(load: () => Promise<PlotlyFigure>, deps: unknown[]) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let alive = true;
    setState({ status: "loading" });
    load()
      .then((figure) => alive && setState({ status: "ok", figure }))
      .catch(
        (e) =>
          alive &&
          setState({
            status: "error",
            message: e instanceof ApiError ? e.message : String(e),
          })
      );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}

function Pending({ label, height }: { label: string; height?: number }) {
  return (
    <Group py="xl" justify="center" h={height}>
      <Loader size="sm" />
      <Text c="dimmed" size="sm">
        {label}
      </Text>
    </Group>
  );
}

function FigureSlot({ state, height }: { state: State; height?: number }) {
  if (state.status === "loading") {
    return <Pending label="Calculando gráfico…" height={height} />;
  }
  if (state.status === "error") {
    return (
      <Alert color="red" mt="sm" title="No se pudo generar el gráfico">
        {state.message}
      </Alert>
    );
  }
  return (
    <Suspense fallback={<Pending label="Cargando Plotly…" height={height} />}>
      <PlotFigure figure={state.figure} height={height} />
    </Suspense>
  );
}

export function DesignCharts({
  design,
  inputs,
}: {
  design: DesignResult;
  inputs: DesignInputs;
}) {
  const {
    pump_model,
    num_stages,
    flow_rate_achieved,
    pump_setting_depth,
    operating_frequency,
  } = design;

  const curve = useFigure(
    () =>
      api
        .pumpCurve({
          pump_model,
          operating_flow: flow_rate_achieved,
          stages: num_stages,
          frequency: operating_frequency,
        })
        .then((r) => r.figure),
    [pump_model, flow_rate_achieved, num_stages, operating_frequency]
  );

  const nodal = useFigure(
    () =>
      api
        .nodal({
          reservoir: inputs.reservoir,
          fluid: inputs.fluid,
          well: inputs.well,
          surface: inputs.surface,
          pump_model,
          stages: num_stages,
          pump_depth: pump_setting_depth,
        })
        .then((r) => r.figure),
    [pump_model, num_stages, pump_setting_depth, inputs]
  );

  return (
    <Tabs defaultValue="curve" mt="lg" variant="outline">
      <Tabs.List>
        <Tabs.Tab value="curve">Curva de bomba</Tabs.Tab>
        <Tabs.Tab value="nodal">Análisis nodal</Tabs.Tab>
      </Tabs.List>

      <Tabs.Panel value="curve" pt="sm">
        <FigureSlot state={curve} height={520} />
      </Tabs.Panel>
      <Tabs.Panel value="nodal" pt="sm">
        <FigureSlot state={nodal} height={560} />
      </Tabs.Panel>
    </Tabs>
  );
}
