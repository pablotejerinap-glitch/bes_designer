// Gráficos que acompañan una recomendación: curva de bomba + análisis nodal.
// Las figuras las arma el backend (ui/plots.py) y viajan como Plotly JSON.
import { lazy, Suspense, useEffect, useState } from "react";
import { Alert, Group, Image, Loader, Table, Tabs, Text } from "@mantine/core";
import { api, ApiError, BASE } from "../api/client";
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

/**
 * Curva de la bomba: la FOTO de la página del catálogo del fabricante, a la
 * frecuencia de diseño (50 o 60 Hz), y debajo lo que la app leyó de esa curva.
 * Reemplaza al gráfico dibujado, que con gas quedaba ilegible.
 */
function CurvaCatalogo({ design }: { design: DesignResult }) {
  const [info, setInfo] = useState<
    { tiene_foto: boolean; hz: number | null; fuente: string | null; url?: string } | null
  >(null);
  const hz = design.operating_frequency || 60;
  useEffect(() => {
    let vivo = true;
    api
      .curvaInfo(design.pump_model, hz)
      .then((r) => vivo && setInfo(r))
      .catch(() => vivo && setInfo({ tiene_foto: false, hz: null, fuente: null }));
    return () => {
      vivo = false;
    };
  }, [design.pump_model, hz]);

  const q = design.gas_q_representative_bpd || design.flow_rate_achieved;
  const filas: [string, string][] = [
    ["Bomba", `${design.pump_manufacturer} ${design.pump_model}`],
    ["Frecuencia de diseño", `${hz.toFixed(0)} Hz`],
    ["Caudal con que se entra a la curva", `${q.toFixed(1)} bbl/d`],
    ["Altura por etapa", `${design.head_per_stage.toFixed(3)} ft/etapa`],
    ["Potencia por etapa", `${design.hp_per_stage.toFixed(4)} hp/etapa`],
    ["Eficiencia", `${(design.pump_efficiency * 100).toFixed(1)} %`],
    ["Etapas", `${design.num_stages}`],
  ];

  return (
    <>
      {info === null ? (
        <Pending label="Buscando la curva del catálogo…" />
      ) : info.tiene_foto && info.url ? (
        <>
          <Image src={`${BASE}${info.url}`} alt={`Curva de catálogo ${design.pump_model}`} fit="contain" />
          <Text size="xs" c="dimmed" mt={4}>
            Fuente: {info.fuente}.
            {info.hz !== hz &&
              ` La foto es a ${info.hz} Hz; la app lleva la curva a ${hz.toFixed(0)} Hz con las leyes de afinidad.`}
          </Text>
        </>
      ) : (
        <Alert color="gray" variant="light" mt="sm">
          El catálogo de este fabricante no publica la curva dibujada: la app trabaja con los
          coeficientes que publica.
        </Alert>
      )}
      <Table mt="sm" withTableBorder striped>
        <Table.Tbody>
          {filas.map(([k, v]) => (
            <Table.Tr key={k}>
              <Table.Td>{k}</Table.Td>
              <Table.Td>{v}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </>
  );
}

export function DesignCharts({
  design,
  inputs,
}: {
  design: DesignResult;
  inputs: DesignInputs;
}) {
  const { pump_model, num_stages, pump_setting_depth } = design;

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
        <CurvaCatalogo design={design} />
      </Tabs.Panel>
      <Tabs.Panel value="nodal" pt="sm">
        <FigureSlot state={nodal} height={560} />
      </Tabs.Panel>
    </Tabs>
  );
}
