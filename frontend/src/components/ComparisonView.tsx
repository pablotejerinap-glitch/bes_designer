// Comparación lado a lado de las opciones recomendadas.
// No pide nada a la API: /api/design ya devuelve las N opciones con sus
// métricas, así que esto es pura presentación.
import { Alert, Badge, Card, Group, Progress, SimpleGrid, Table, Text } from "@mantine/core";
import type { Recommendation } from "../api/types";

const MEDALS = ["🥇", "🥈", "🥉"];

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <Group justify="space-between" gap="xs">
        <Text size="xs" c="dimmed">
          {label}
        </Text>
        <Text size="xs" fw={600}>
          {value.toFixed(1)}/10
        </Text>
      </Group>
      <Progress value={value * 10} size="sm" mt={2} />
    </div>
  );
}

function OptionCard({ rec, best }: { rec: Recommendation; best: Recommendation }) {
  const d = rec.design;
  const medal = MEDALS[rec.rank - 1] ?? `#${rec.rank}`;
  const delta = rec.rank === 1 ? null : rec.score - best.score;

  const specs: [string, string][] = [
    ["Etapas", `${d.num_stages}`],
    ["HP motor", `${d.motor_hp.toFixed(0)} hp`],
    ["Voltaje motor", `${d.motor_voltage.toFixed(0)} V`],
    ["Amperaje", `${d.motor_amperage.toFixed(0)} A`],
    ["Eficiencia bomba", `${(d.pump_efficiency * 100).toFixed(1)} %`],
    ["Transformador", `${d.transformer_kva.toFixed(0)} kVA`],
    ["TDH", `${d.total_head_required.toFixed(0)} ft`],
    ["PIP", `${d.intake_pressure.toFixed(0)} psi`],
    ["Cable", `#${d.cable_awg} ${d.cable_type}`],
    ["GIP en intake", `${(d.gip_fraction * 100).toFixed(1)} %`],
    ["Efic. sistema", `${(d.system_efficiency * 100).toFixed(1)} %`],
  ];

  return (
    <Card withBorder radius="md" padding="md">
      <Text fw={700} size="lg">
        {medal} Opción {rec.rank}
      </Text>
      <Text fw={500}>
        {d.pump_manufacturer} — {d.pump_model}
      </Text>
      <Text size="xs" c="dimmed">
        Serie: {d.pump_series} · OD: {d.pump_od.toFixed(3)}"
      </Text>

      <Group align="baseline" gap="xs" mt="sm">
        <Text fw={700} size="xl">
          {rec.score.toFixed(2)}
        </Text>
        <Text size="sm" c="dimmed">
          / 10
        </Text>
        {delta !== null && (
          <Badge color={delta < 0 ? "red" : "teal"} variant="light" size="sm">
            {delta >= 0 ? "+" : ""}
            {delta.toFixed(2)} vs 🥇
          </Badge>
        )}
      </Group>

      <Card.Section inheritPadding py="sm">
        <ScoreBar label="Eficiencia" value={rec.metrics.efficiency} />
        <ScoreBar label="Flexibilidad (BEP)" value={rec.metrics.flexibility} />
        <ScoreBar label="Preferencia de proveedor" value={rec.metrics.provider} />
      </Card.Section>

      <Table striped withTableBorder mt="xs">
        <Table.Tbody>
          {specs.map(([k, v]) => (
            <Table.Tr key={k}>
              <Table.Td>
                <Text size="xs">{k}</Text>
              </Table.Td>
              <Table.Td>
                <Text size="xs" fw={500}>
                  {v}
                </Text>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>

      <Text size="xs" c="dimmed" mt="sm">
        {rec.rationale}
      </Text>

      {d.warnings.length > 0 && (
        <Alert color="yellow" mt="sm" p="xs">
          <Text size="xs">{d.warnings.join(" · ")}</Text>
        </Alert>
      )}
    </Card>
  );
}

export function ComparisonView({ recommendations }: { recommendations: Recommendation[] }) {
  if (recommendations.length === 0) {
    return <Text c="dimmed">No hay recomendaciones para comparar.</Text>;
  }

  const shown = recommendations.slice(0, 3);
  return (
    <SimpleGrid cols={{ base: 1, md: shown.length }} mt="md">
      {shown.map((rec) => (
        <OptionCard key={rec.rank} rec={rec} best={recommendations[0]} />
      ))}
    </SimpleGrid>
  );
}
