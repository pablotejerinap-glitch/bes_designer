// Sección "Leyes de afinidad": explora la misma bomba a distintas frecuencias
// del variador. No resuelve un pozo — es un banco de pruebas sobre la curva de
// catálogo. Todo el cálculo vive en bes.core.affinity; acá solo se muestra.
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Card,
  Grid,
  Group,
  Loader,
  NumberInput,
  Select,
  Slider,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { api, ApiError } from "../api/client";
import type { AffinityResponse, PlotlyFigure, PumpSummary } from "../api/types";

const PlotFigure = lazy(() =>
  import("./PlotFigure").then((m) => ({ default: m.PlotFigure }))
);

// Rango operativo del deslizador: 40–60 Hz de a 0.5 Hz. Por debajo de 40 la
// bomba pierde demasiada altura (H ∝ N²) y por encima de la frecuencia de red
// se fuerza el eje y el motor. El backend acepta 20–90 Hz, así que este rango
// es una restricción de la interfaz, no del cálculo.
const FREQ_MIN = 40;
const FREQ_MAX = 60;
const FREQ_STEP = 0.5;
const FREQ_DEFAULT = 60;

// Marcas cada 5 Hz, para no saturar la escala.
const FREQ_MARKS = Array.from(
  { length: (FREQ_MAX - FREQ_MIN) / 5 + 1 },
  (_, i) => {
    const v = FREQ_MIN + i * 5;
    return { value: v, label: `${v}` };
  }
);

export function AffinityPanel({
  pumps,
  active,
  defaultFlow,
}: {
  pumps: PumpSummary[];
  active: boolean;
  defaultFlow?: number | null;
}) {
  const [model, setModel] = useState<string | null>(null);
  // `freq` sigue al pulgar mientras se arrastra (para que el número se vea
  // moverse); `freqApplied` sólo cambia al soltar, y es la que dispara el
  // pedido al backend. Sin esa separación, arrastrar el deslizador lanzaría
  // una consulta por cada paso de 0.5 Hz.
  const [freq, setFreq] = useState<number>(FREQ_DEFAULT);
  const [freqApplied, setFreqApplied] = useState<number>(FREQ_DEFAULT);
  const [sgRatio, setSgRatio] = useState<number | string>(1);
  const [diameterRatio, setDiameterRatio] = useState<number | string>(1);
  const [targetFlow, setTargetFlow] = useState<number | string>(defaultFlow ?? "");

  const [data, setData] = useState<AffinityResponse | null>(null);
  const [figure, setFigure] = useState<PlotlyFigure | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const options = useMemo(
    () =>
      pumps.map((p) => ({
        value: p.model,
        label: `${p.model} — ${p.manufacturer} (serie ${p.series}, BEP ${Math.round(p.bep_flow)} bpd)`,
      })),
    [pumps]
  );

  // Primera bomba del catálogo como arranque, para que la sección no abra vacía.
  useEffect(() => {
    if (!model && pumps.length > 0) setModel(pumps[0].model);
  }, [pumps, model]);

  // Se pide siempre la curva del deslizador MÁS la de catálogo (60 Hz), para
  // que el gráfico muestre contra qué se está comparando. Si coinciden, va una
  // sola: pedir dos veces la misma frecuencia dibujaría curvas superpuestas.
  const frequencies = useMemo(() => {
    const base = FREQ_DEFAULT;
    return freqApplied === base
      ? String(base)
      : [freqApplied, base].sort((a, b) => a - b).join(",");
  }, [freqApplied]);

  useEffect(() => {
    if (!active || !model) return;
    let alive = true;
    setLoading(true);
    setError(null);
    const params = {
      pump_model: model,
      frequencies,
      diameter_ratio: Number(diameterRatio) || 1,
      sg_ratio: Number(sgRatio) || 1,
      target_flow: Number(targetFlow) || undefined,
    };
    Promise.all([api.affinity(params), api.affinityFigure(params)])
      .then(([d, f]) => {
        if (!alive) return;
        setData(d);
        setFigure(f.figure);
      })
      .catch((e) => {
        if (alive) setError(e instanceof ApiError ? e.message : String(e));
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [active, model, frequencies, diameterRatio, sgRatio, targetFlow]);

  return (
    <>
      <Title order={4}>Leyes de afinidad</Title>
      <Text size="sm" c="dimmed" mb="md">
        Las curvas de catálogo se publican a una frecuencia fija, con agua limpia
        (SG = 1, µ = 1 cp) y para una etapa. Las leyes de afinidad predicen la
        curva a otra velocidad, otro diámetro de impulsor u otro fluido:{" "}
        <b>Q ∝ N·D</b>, <b>H ∝ N²·D²</b>, <b>HP ∝ N³·D³·SG</b>. La eficiencia no
        cambia.
      </Text>

      <Grid>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Select
            label="Bomba"
            data={options}
            value={model}
            onChange={setModel}
            searchable
            allowDeselect={false}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 6, md: 2 }}>
          <NumberInput
            label="Caudal objetivo"
            description="opcional"
            value={targetFlow}
            onChange={setTargetFlow}
            min={0}
            step={100}
            hideControls
          />
        </Grid.Col>
        <Grid.Col span={{ base: 6, md: 2 }}>
          <NumberInput
            label="SG del fluido"
            description="SG₂/SG₁"
            value={sgRatio}
            onChange={setSgRatio}
            min={0.1}
            max={3}
            step={0.01}
            decimalScale={2}
            hideControls
          />
        </Grid.Col>
        <Grid.Col span={{ base: 6, md: 2 }}>
          <NumberInput
            label="Diámetro"
            description="D₂/D₁"
            value={diameterRatio}
            onChange={setDiameterRatio}
            min={0.1}
            max={2}
            step={0.01}
            decimalScale={2}
            hideControls
          />
        </Grid.Col>
      </Grid>

      <Group justify="space-between" align="baseline" mt="lg" mb={4}>
        <Text size="sm" fw={500}>
          Frecuencia de operación
        </Text>
        <Text size="sm" fw={700}>
          {freq.toFixed(1)} Hz
        </Text>
      </Group>
      <Slider
        value={freq}
        onChange={setFreq}
        onChangeEnd={setFreqApplied}
        min={FREQ_MIN}
        max={FREQ_MAX}
        step={FREQ_STEP}
        marks={FREQ_MARKS}
        label={(v) => `${v.toFixed(1)} Hz`}
        mb="xl"
      />
      <Text size="xs" c="dimmed">
        De {FREQ_MIN} a {FREQ_MAX} Hz, de a {FREQ_STEP} Hz. La curva de{" "}
        {FREQ_DEFAULT} Hz se muestra siempre como referencia del catálogo.
        Bajar la frecuencia recorta el caudal en proporción directa (Q ∝ N) pero
        la altura al cuadrado (H ∝ N²): a 40 Hz una etapa entrega el 44 % de la
        altura que da a 60.
      </Text>

      {error && (
        <Alert color="red" mt="md">
          {error}
        </Alert>
      )}

      {data?.frequency_for_target_flow != null && (
        <Card mt="md" padding="sm" withBorder>
          <Text size="sm">
            Para llevar el BEP de <b>{data.pump_model}</b> a{" "}
            <b>{Math.round(Number(targetFlow))} STB/d</b> hace falta{" "}
            <b>{data.frequency_for_target_flow.toFixed(1)} Hz</b>{" "}
            <Text span c="dimmed">
              (f₂ = f₁·Q₂/Q₁ desde {data.catalog_frequency_hz.toFixed(0)} Hz)
            </Text>
            .
          </Text>
        </Card>
      )}

      {loading && (
        <Group mt="md">
          <Loader size="sm" />
          <Text size="sm" c="dimmed">
            Calculando…
          </Text>
        </Group>
      )}

      {figure && (
        <Suspense fallback={<Loader size="sm" />}>
          <PlotFigure figure={figure} />
        </Suspense>
      )}

      {data && data.curves.length > 0 && (
        <Table mt="md" striped withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Hz</Table.Th>
              <Table.Th>N₂/N₁</Table.Th>
              <Table.Th>rpm</Table.Th>
              <Table.Th>Rango operativo</Table.Th>
              <Table.Th>BEP</Table.Th>
              <Table.Th>Head/etapa</Table.Th>
              <Table.Th>HP/etapa</Table.Th>
              <Table.Th>Eficiencia</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data.curves.map((c) => (
              <Table.Tr key={c.frequency_hz}>
                <Table.Td>
                  <b>{c.frequency_hz.toFixed(1)}</b>
                  {c.frequency_hz === c.from_frequency_hz && (
                    <Text span size="xs" c="dimmed">
                      {" "}
                      catálogo
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>{c.speed_ratio.toFixed(3)}</Table.Td>
                <Table.Td>{Math.round(c.motor_rpm)}</Table.Td>
                <Table.Td>
                  {Math.round(c.min_flow)} – {Math.round(c.max_flow)} STB/d
                </Table.Td>
                <Table.Td>{Math.round(c.bep_flow)} STB/d</Table.Td>
                <Table.Td>{c.bep_head_per_stage.toFixed(2)} ft</Table.Td>
                <Table.Td>{c.bep_hp_per_stage.toFixed(3)}</Table.Td>
                <Table.Td>{(c.bep_efficiency * 100).toFixed(1)} %</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Text size="xs" c="dimmed" mt="xs">
        Los valores del BEP son por etapa. La rpm es la del eje después del
        deslizamiento del motor (≈2.8 %); en las leyes se usa la relación de
        frecuencias, donde el deslizamiento se cancela.
      </Text>
    </>
  );
}
