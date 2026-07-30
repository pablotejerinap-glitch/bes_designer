// Comparación lado a lado de las opciones recomendadas.
// No pide nada a la API: /api/design ya devuelve las N opciones con sus
// métricas, así que esto es pura presentación.
import { Alert, Badge, Card, Group, SimpleGrid, Table, Text } from "@mantine/core";
import type { BepClassification, Recommendation } from "../api/types";

// Etiquetas de la clasificación de distancia al BEP. Solo informan: el orden
// lo fija el criterio lexicográfico del backend, no estos colores.
const CLASSIFICATION: Record<BepClassification, { label: string; color: string }> = {
  optimo: { label: "Muy cerca del BEP", color: "teal" },
  aceptable: { label: "Moderadamente alejado del BEP", color: "yellow" },
  alejado: { label: "Alejado del BEP", color: "red" },
};

function OptionCard({ rec, best }: { rec: Recommendation; best: Recommendation }) {
  const d = rec.design;
  const c = rec.criteria;
  const cls = CLASSIFICATION[c.classification];
  // Criterio 1: cuánto más lejos del BEP queda esta opción que la primera.
  const deltaBep =
    rec.rank === 1 ? null : (c.bep_distance_frac - best.criteria.bep_distance_frac) * 100;

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
        Opción {rec.rank}
      </Text>
      <Text fw={500}>
        {d.pump_manufacturer} — {d.pump_model}
      </Text>
      <Text size="xs" c="dimmed">
        Serie: {d.pump_series} · OD: {d.pump_od.toFixed(3)}"
      </Text>

      <Group align="baseline" gap="xs" mt="sm">
        <Text fw={700} size="xl">
          {(c.bep_distance_frac * 100).toFixed(1)} %
        </Text>
        <Text size="sm" c="dimmed">
          del BEP
        </Text>
        {deltaBep !== null && (
          <Badge color={deltaBep > 0 ? "red" : "teal"} variant="light" size="sm">
            {deltaBep >= 0 ? "+" : ""}
            {deltaBep.toFixed(1)} pp vs Opción 1
          </Badge>
        )}
      </Group>
      <Badge color={cls.color} variant="light" size="sm" mt={4}>
        {cls.label}
      </Badge>

      <Card.Section inheritPadding py="sm">
        <Text size="xs" c="dimmed">
          Criterios de ordenamiento
        </Text>
        <Table mt={4}>
          <Table.Tbody>
            <Table.Tr>
              <Table.Td>
                <Text size="xs">1. Distancia al BEP</Text>
              </Table.Td>
              <Table.Td>
                <Text size="xs" fw={600}>
                  {(c.bep_distance_frac * 100).toFixed(1)} % ({c.bep_flow_bpd.toFixed(0)} STB/d)
                </Text>
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>
                <Text size="xs">2. Eficiencia hidráulica</Text>
              </Table.Td>
              <Table.Td>
                <Text size="xs" fw={600}>
                  {(c.efficiency * 100).toFixed(1)} %
                </Text>
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>
                <Text size="xs">3. Potencia en el eje</Text>
              </Table.Td>
              <Table.Td>
                <Text size="xs" fw={600}>
                  {c.total_pump_hp.toFixed(1)} hp
                </Text>
              </Table.Td>
            </Table.Tr>
          </Table.Tbody>
        </Table>
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
