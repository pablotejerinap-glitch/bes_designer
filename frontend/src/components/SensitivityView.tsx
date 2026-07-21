// Análisis de sensibilidad: barre un parámetro de entrada y muestra cómo
// responden HP, etapas, eficiencia y TDH del diseño óptimo.
//
// Todo el cálculo vive en POST /api/sensitivity (bes.services.sensitivity_service);
// acá sólo se arman los controles y se renderiza lo que vuelve.
import { lazy, Suspense, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Group,
  Loader,
  Select,
  SimpleGrid,
  Slider,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { api, ApiError } from "../api/client";
import type { DesignInputs, SensitivityParam, SensitivityResponse } from "../api/types";

const PlotFigure = lazy(() =>
  import("./PlotFigure").then((m) => ({ default: m.PlotFigure }))
);

// Espejan PARAM_LABELS de bes/services/sensitivity_service.py.
const PARAM_LABELS: Record<SensitivityParam, string> = {
  water_cut: "Corte de agua (WC)",
  gor: "GOR (scf/STB)",
  static_pressure: "Presión de reservorio (psi)",
  target_flow_rate: "Tasa objetivo (STB/d)",
};

const N_POINTS = 7; // DEFAULT_N_POINTS del servicio
const METRIC_KEYS = ["HP", "Etapas", "Eficiencia (%)", "TDH (ft)"];

// Los decimales de cada métrica, para que la tabla no muestre 172.00000001 etapas.
const METRIC_DECIMALS: Record<string, number> = {
  HP: 0,
  Etapas: 0,
  "Eficiencia (%)": 1,
  "TDH (ft)": 0,
};

export function SensitivityView({ inputs }: { inputs: DesignInputs | null }) {
  const [param, setParam] = useState<SensitivityParam>("water_cut");
  const [pctRange, setPctRange] = useState(40);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SensitivityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (!inputs) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.sensitivity({
        ...inputs,
        param,
        pct_range_pct: pctRange,
        n_points: N_POINTS,
      });
      if (res.param_values.length === 0) {
        setError("No se encontraron diseños válidos en el rango seleccionado.");
        return;
      }
      setResult(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  if (!inputs) {
    return (
      <Alert color="blue" variant="light" mt="md">
        Cargá los datos del pozo primero.
      </Alert>
    );
  }

  return (
    <Card withBorder radius="md" padding="lg" mt="md">
      <Title order={4}>Análisis de sensibilidad</Title>
      <Text c="dimmed" size="sm">
        Variá un parámetro de entrada dentro de un rango y observá cómo cambian HP,
        etapas, eficiencia y TDH del diseño óptimo.
      </Text>

      <SimpleGrid cols={{ base: 1, sm: 2 }} mt="md">
        <Select
          label="Parámetro a variar"
          data={Object.entries(PARAM_LABELS).map(([value, label]) => ({ value, label }))}
          value={param}
          onChange={(v) => v && setParam(v as SensitivityParam)}
          allowDeselect={false}
        />
        <div>
          <Text size="sm" fw={500} mb={2}>
            Rango de variación (±{pctRange} %)
          </Text>
          <Slider
            min={10}
            max={60}
            step={5}
            value={pctRange}
            onChange={setPctRange}
            marks={[
              { value: 10, label: "10" },
              { value: 40, label: "40" },
              { value: 60, label: "60" },
            ]}
            mb="lg"
          />
        </div>
      </SimpleGrid>

      <Group mt="xs">
        <Button onClick={run} loading={running}>
          ▶ Correr análisis
        </Button>
        <Text size="xs" c="dimmed">
          {N_POINTS} puntos de evaluación — cada uno corre un diseño completo
        </Text>
      </Group>

      {error && (
        <Alert color="red" mt="md" title="No se pudo correr el análisis">
          {error}
        </Alert>
      )}

      {result && (
        <>
          <Title order={5} mt="lg">
            Resultados — variación de {result.param_label}
          </Title>

          <Suspense
            fallback={
              <Group py="xl" justify="center">
                <Loader size="sm" />
                <Text c="dimmed" size="sm">
                  Cargando Plotly…
                </Text>
              </Group>
            }
          >
            <PlotFigure figure={result.figure} height={480} />
          </Suspense>

          <Table striped withTableBorder mt="md">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{result.param_label}</Table.Th>
                {METRIC_KEYS.map((k) => (
                  <Table.Th key={k}>{k}</Table.Th>
                ))}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {result.param_values.map((x, i) => (
                <Table.Tr key={i}>
                  <Table.Td>
                    <Text fw={500}>{x.toPrecision(3)}</Text>
                  </Table.Td>
                  {METRIC_KEYS.map((k) => (
                    <Table.Td key={k}>
                      {result.metrics[k]?.[i]?.toFixed(METRIC_DECIMALS[k] ?? 1) ?? "—"}
                    </Table.Td>
                  ))}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </>
      )}
    </Card>
  );
}
