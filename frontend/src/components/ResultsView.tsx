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
import { FormulaTraceSection } from "./FormulaTrace";

/** Los cuatro escalones de la escalera de manejo de gas, en castellano.
 *
 * Los tres primeros RETIRAN gas; el cuarto no: el manejador avanzado
 * acondiciona la mezcla para que la bomba la pueda impulsar con el gas
 * adentro. Por eso lleva etiqueta propia y no se lo llama «separador».
 */
const ETIQUETA_GAS: Record<string, string> = {
  ninguno: "sin separador",
  simple: "separador simple",
  tandem: "separador en tándem",
  agh: "manejador avanzado (AGH)",
  no_viable: "no viable — cambiar de método",
};

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Card padding="sm">
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={600} size="lg" className="num">
        {value}
      </Text>
    </Card>
  );
}

function RecPanel({
  rec,
  inputs,
  manual = false,
}: {
  rec: Recommendation;
  inputs: DesignInputs;
  manual?: boolean;
}) {
  const [busy, setBusy] = useState<"pdf" | "xlsx" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const d = rec.design;

  async function download(fmt: "pdf" | "xlsx") {
    setBusy(fmt);
    setErr(null);
    try {
      // Una bomba elegida manualmente no tiene "rank" en el motor de
      // recomendación: hay que volver a pedir el reporte con pump_model para
      // no descargar, sin querer, la opción rank 0 del top-N.
      const req = manual
        ? { ...inputs, n: 1, pump_model: d.pump_model }
        : { ...inputs, n: 3, rank: rec.rank - 1 };
      const blob = await api.report(fmt, req);
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
    [
      "Carcasa (housing)",
      `${d.housing_size_stages} et${d.n_housings > 1 ? ` en ${d.n_housings} carcasas (tándem)` : ""}${d.dummy_stages > 0 ? ` · ${d.dummy_stages} dummy` : ""}`,
    ],
    [
      "Presión sobre housing",
      `${Math.round(d.max_housing_pressure_psi)} / ${Math.round(d.housing_pressure_limit_psi)} psi ${d.housing_pressure_ok ? "✓" : "⚠ excede"}`,
    ],
    ["OD bomba", `${d.pump_od.toFixed(2)} in`],
    [
      "Eje",
      d.shaft_check?.verified
        ? `${d.shaft_check.hp_shaft.toFixed(1)} / ${d.shaft_check.limit_std.toFixed(0)} hp — ${
            d.shaft_check.shaft_type === "high_strength" ? "alta resistencia" : "estándar"
          } ${d.shaft_check.ok ? "✓" : "⚠"}`
        : "sin verificar (el catálogo no tiene la serie)",
    ],
    [
      "Cojinete de empuje",
      d.bearing_check?.verified
        ? `${d.bearing_check.stages} / ${d.bearing_check.limit_stages} etapas — ${
            d.bearing_check.bearing_type === "high_load" ? "alta carga" : "estándar"
          } (máx ${d.bearing_check.bht_max_f.toFixed(0)} °F) ${d.bearing_check.ok ? "✓" : "⚠"}`
        : "sin verificar (el catálogo no tiene la serie)",
    ],
    [
      "Carga axial sobre el sello",
      `${Math.round(d.bearing_load_lbs)} lbs (Ho × Pem × A_eje)`,
    ],
    [
      "Tope de etapas",
      d.staging_ceiling?.governing
        ? `${d.staging_ceiling.governing} — manda ${
            {
              by_housing_pressure: "la presión de carcasa",
              by_shaft: "el eje",
              by_bearing: "el cojinete",
            }[d.staging_ceiling.governing_by] ?? d.staging_ceiling.governing_by
          } (carcasa ${d.staging_ceiling.by_housing_pressure || "—"} · eje ${
            d.staging_ceiling.by_shaft || "—"
          } · cojinete ${d.staging_ceiling.by_bearing || "—"})`
        : "sin datos de serie",
    ],
    ["TDH", `${Math.round(d.total_head_required)} ft`],
    [
      "Pérdida de carga en tubing",
      d.friction_method === "poettmann_carpenter"
        ? `Poettmann-Carpenter (gas en admisión ${(d.gip_fraction * 100).toFixed(0)} % > umbral ${(d.gas_fraction_threshold * 100).toFixed(0)} %)`
        : `Hazen-Williams (gas en admisión ${(d.gip_fraction * 100).toFixed(0)} % ≤ umbral ${(d.gas_fraction_threshold * 100).toFixed(0)} %)`,
    ],
    ["Profundidad de asentamiento", `${Math.round(d.pump_setting_depth)} ft`],
    ["Presión de admisión (PIP)", `${Math.round(d.intake_pressure)} psi`],
    ["Motor", `${d.motor_manufacturer} ${d.motor_model}`],
    ["HP eje (operativo / máximo)", `${Math.round(d.total_pump_hp)} / ${Math.round(d.motor_hp_max)} hp`],
    ["Potencia motor", `${Math.round(d.motor_hp)} hp @ ${Math.round(d.motor_voltage)} V / ${Math.round(d.motor_amperage)} A`],
    [
      "Velocidad de refrigeración",
      `${d.fluid_velocity_ft_s.toFixed(2)} ft/s ${d.cooling_ok ? "✓" : "⚠ < 1 ft/s"}`,
    ],
    ["Cable", `#${d.cable_awg} ${d.cable_type}`],
    ["Voltaje de superficie", `${Math.round(d.surface_voltage_required)} V`],
    [
      "Controlador",
      d.controller_model ? `${d.controller_manufacturer} ${d.controller_model} (${d.controller_type})` : "—",
    ],
    ["Transformador", `${Math.round(d.transformer_kva)} kVA`],
    ["Sello / protector", d.seal_model ? `${d.seal_manufacturer} ${d.seal_model}` : "—"],
    [
      "Manejo de gas",
      d.gas_handler_model
        ? `${d.gas_handler_manufacturer} ${d.gas_handler_model}` +
          // Cuántos equipos cuelgan del eje: separador simple, tándem, o
          // separador + manejador avanzado. El consumo es la suma de todos.
          (d.gas_handler_count > 1 ? ` ×${d.gas_handler_count}` : "") +
          (d.gas_strategy ? ` · ${ETIQUETA_GAS[d.gas_strategy] ?? d.gas_strategy}` : "") +
          (d.gas_handler_hp ? ` · +${d.gas_handler_hp.toFixed(1)} hp al motor` : "")
        : "—",
    ],
    [
      "Gas libre en la bomba",
      d.gas_fraction_at_pump
        ? `${(d.gas_fraction_at_pump * 100).toFixed(1)} %` +
          (d.gas_strategy === "agh"
            ? " (el manejador avanzado no lo retira: lo tolera)"
            : "")
        : "—",
    ],
    ["Sensor", d.sensor_model ? `${d.sensor_manufacturer} ${d.sensor_model}` : "—"],
  ];

  return (
    <>
      <SimpleGrid cols={{ base: 2, sm: 3, md: 5 }} mt="md">
        <Metric
          label="Distancia al BEP"
          value={`${(rec.criteria.bep_distance_frac * 100).toFixed(1)} %`}
        />
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

      {d.housing_detail.length > 0 && (
        <>
          <Title order={5} mt="lg">
            Carcasas (pump housings)
          </Title>
          <Text size="sm" c="dimmed" mb="xs">
            {d.housing_rationale}
          </Text>
          <Table striped withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>#</Table.Th>
                <Table.Th>Etapas</Table.Th>
                <Table.Th>Código</Table.Th>
                <Table.Th>Material</Table.Th>
                <Table.Th>Etapas activas acum.</Table.Th>
                <Table.Th>Presión</Table.Th>
                <Table.Th>Admisible</Table.Th>
                <Table.Th>Verificación</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {d.housing_detail.map((h) => (
                <Table.Tr key={h.position}>
                  <Table.Td>{h.position}</Table.Td>
                  <Table.Td>{h.stages}</Table.Td>
                  <Table.Td>{h.code || "—"}</Table.Td>
                  <Table.Td>{h.material || "—"}</Table.Td>
                  <Table.Td>{h.active_stages_below}</Table.Td>
                  <Table.Td>{Math.round(h.pressure_psi)} psi</Table.Td>
                  <Table.Td>{h.limit_known ? `${Math.round(h.limit_psi)} psi` : "sin dato"}</Table.Td>
                  <Table.Td>
                    {!h.limit_known ? (
                      <Badge color="gray" variant="light">
                        Sin verificar
                      </Badge>
                    ) : h.pressure_ok ? (
                      <Badge color="teal" variant="light">
                        OK
                      </Badge>
                    ) : (
                      <Badge color="red" variant="light">
                        FAIL
                      </Badge>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          <Text size="xs" c="dimmed" mt={4}>
            La posición 1 es la carcasa de admisión. La presión se acumula con
            las etapas activas por debajo (MaxP = P<sub>Q=0</sub> × etapas ×
            Pem), así que la carcasa superior es la crítica.
          </Text>
        </>
      )}

      <DesignCharts design={d} inputs={inputs} />

      <FormulaTraceSection formulas={d.formulas} />

      <Group mt="md">
        <Button onClick={() => download("pdf")} loading={busy === "pdf"} variant="light">
          Descargar PDF
        </Button>
        <Button onClick={() => download("xlsx")} loading={busy === "xlsx"} variant="light">
          Descargar Excel
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
  title = "Recomendaciones",
  manual = false,
}: {
  response: DesignResponse;
  inputs: DesignInputs;
  title?: string;
  manual?: boolean;
}) {
  const recs = response.recommendations;
  if (recs.length === 0) {
    return <Text c="dimmed">Sin recomendaciones.</Text>;
  }

  return (
    <Card withBorder radius="md" padding="lg">
      <Group justify="space-between">
        <Title order={4}>{title}</Title>
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
              {manual ? "Bomba" : `Opción ${r.rank}`}: {r.design.pump_model}
            </Tabs.Tab>
          ))}
          {recs.length > 1 && <Tabs.Tab value="compare">Comparar</Tabs.Tab>}
        </Tabs.List>
        {recs.map((r, i) => (
          <Tabs.Panel key={r.rank} value={String(i)}>
            <RecPanel rec={r} inputs={inputs} manual={manual} />
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
