import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  SimpleGrid,
  Table,
  Tabs,
  Text,
  Title,
} from "@mantine/core";
import { api, ApiError, downloadBlob } from "../api/client";
import type { DesignInputs, DesignResponse, Recommendation } from "../api/types";
import { DesignCharts } from "./DesignCharts";
import { ComparisonView } from "./ComparisonView";

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Card withBorder padding="sm" radius="md">
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={700} size="lg">
        {value}
      </Text>
    </Card>
  );
}

function RecPanel({ rec, inputs }: { rec: Recommendation; inputs: DesignInputs }) {
  const [busy, setBusy] = useState<"pdf" | "xlsx" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const d = rec.design;

  async function download(fmt: "pdf" | "xlsx") {
    setBusy(fmt);
    setErr(null);
    try {
      const blob = await api.report(fmt, { ...inputs, n: 3, rank: rec.rank - 1 });
      downloadBlob(blob, `reporte_bes_opcion${rec.rank}.${fmt}`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const rows: [string, string][] = [
    ["Bomba", `${d.pump_manufacturer} ${d.pump_model} (${d.pump_series})`],
    ["Etapas", `${d.num_stages}`],
    ["OD bomba", `${d.pump_od.toFixed(2)} in`],
    ["TDH", `${Math.round(d.total_head_required)} ft`],
    ["Profundidad de asentamiento", `${Math.round(d.pump_setting_depth)} ft`],
    ["Presión de admisión (PIP)", `${Math.round(d.intake_pressure)} psi`],
    ["Motor", `${d.motor_manufacturer} ${d.motor_model}`],
    ["Potencia motor", `${Math.round(d.motor_hp)} hp @ ${Math.round(d.motor_voltage)} V / ${Math.round(d.motor_amperage)} A`],
    ["Cable", `#${d.cable_awg} ${d.cable_type}`],
    ["Voltaje de superficie", `${Math.round(d.surface_voltage_required)} V`],
    ["Transformador", `${Math.round(d.transformer_kva)} kVA`],
    ["Sello / protector", d.seal_model ? `${d.seal_manufacturer} ${d.seal_model}` : "—"],
    ["Manejo de gas", d.gas_handler_model ? `${d.gas_handler_manufacturer} ${d.gas_handler_model}` : "—"],
    ["Sensor", d.sensor_model ? `${d.sensor_manufacturer} ${d.sensor_model}` : "—"],
  ];

  return (
    <>
      <SimpleGrid cols={{ base: 2, sm: 3, md: 5 }} mt="md">
        <Metric label="Score" value={`${rec.score.toFixed(1)} / 10`} />
        <Metric label="Eficiencia bomba" value={`${(d.pump_efficiency * 100).toFixed(1)} %`} />
        <Metric label="Etapas" value={`${d.num_stages}`} />
        <Metric label="Potencia" value={`${Math.round(d.motor_hp)} hp`} />
        <Metric label="Gas en bomba" value={`${(d.gip_fraction * 100).toFixed(0)} %`} />
      </SimpleGrid>

      <Text mt="md" c="dimmed" size="sm">
        {rec.rationale}
      </Text>

      {d.warnings.length > 0 && (
        <Alert color="yellow" mt="sm" title="Advertencias de diseño">
          {d.warnings.join(" · ")}
        </Alert>
      )}

      <Table mt="md" striped withTableBorder>
        <Table.Tbody>
          {rows.map(([k, v]) => (
            <Table.Tr key={k}>
              <Table.Td w="45%">
                <Text fw={500}>{k}</Text>
              </Table.Td>
              <Table.Td>{v}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>

      <DesignCharts design={d} inputs={inputs} />

      <Group mt="md">
        <Button onClick={() => download("pdf")} loading={busy === "pdf"} variant="light">
          📕 Descargar PDF
        </Button>
        <Button onClick={() => download("xlsx")} loading={busy === "xlsx"} variant="light">
          📗 Descargar Excel
        </Button>
      </Group>
      {err && (
        <Text c="red" mt="xs" size="sm">
          {err}
        </Text>
      )}
    </>
  );
}

export function ResultsView({
  response,
  inputs,
}: {
  response: DesignResponse;
  inputs: DesignInputs;
}) {
  const recs = response.recommendations;
  if (recs.length === 0) {
    return <Text c="dimmed">Sin recomendaciones.</Text>;
  }

  const medal = (rank: number) => (rank === 1 ? "🥇" : rank === 2 ? "🥈" : "🥉");

  return (
    <Card withBorder radius="md" padding="lg">
      <Group justify="space-between">
        <Title order={4}>Recomendaciones</Title>
        <Badge variant="light">{response.n_candidates_evaluated} candidatos evaluados</Badge>
      </Group>

      {response.warnings.length > 0 && (
        <Alert color="blue" mt="sm" variant="light">
          {response.warnings.join(" · ")}
        </Alert>
      )}

      <Tabs defaultValue="0" mt="sm">
        <Tabs.List>
          {recs.map((r, i) => (
            <Tabs.Tab key={r.rank} value={String(i)}>
              {medal(r.rank)} Opción {r.rank}: {r.design.pump_model}
            </Tabs.Tab>
          ))}
          {recs.length > 1 && <Tabs.Tab value="compare">⚖️ Comparar</Tabs.Tab>}
        </Tabs.List>
        {recs.map((r, i) => (
          <Tabs.Panel key={r.rank} value={String(i)}>
            <RecPanel rec={r} inputs={inputs} />
          </Tabs.Panel>
        ))}
        {recs.length > 1 && (
          <Tabs.Panel value="compare">
            <ComparisonView recommendations={recs} />
          </Tabs.Panel>
        )}
      </Tabs>
    </Card>
  );
}
