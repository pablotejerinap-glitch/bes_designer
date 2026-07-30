// Biblioteca ESP interactiva: tabla filtrable del catálogo (GET /api/catalogs)
// y curva de catálogo de la bomba seleccionada (GET /api/plots/pump-catalog-curve).
// La "interactive ESP library" de pengtools: sin lógica de negocio, solo filtros
// de presentación sobre datos que ya vienen del backend.
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Card,
  Grid,
  Group,
  Loader,
  NumberInput,
  ScrollArea,
  Select,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { api, ApiError } from "../api/client";
import type { PlotlyFigure, PumpSummary } from "../api/types";

const PlotFigure = lazy(() =>
  import("./PlotFigure").then((m) => ({ default: m.PlotFigure }))
);

export function PumpLibrary({
  pumps,
  casingId,
}: {
  pumps: PumpSummary[];
  casingId: number | null;
}) {
  const [search, setSearch] = useState("");
  const [manufacturer, setManufacturer] = useState<string | null>(null);
  const [flow, setFlow] = useState<number | string>("");
  const [onlyCasing, setOnlyCasing] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const [figure, setFigure] = useState<PlotlyFigure | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const manufacturers = useMemo(
    () => Array.from(new Set(pumps.map((p) => p.manufacturer))).sort(),
    [pumps]
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const flowNum = typeof flow === "number" ? flow : NaN;
    return pumps.filter((p) => {
      if (q && !`${p.model} ${p.series} ${p.manufacturer}`.toLowerCase().includes(q)) return false;
      if (manufacturer && p.manufacturer !== manufacturer) return false;
      // Mismo criterio geométrico que el backend (get_pumps_by_casing): OD < ID casing.
      if (onlyCasing && casingId != null && p.od >= casingId) return false;
      if (Number.isFinite(flowNum) && !(p.min_flow <= flowNum && flowNum <= p.max_flow)) return false;
      return true;
    });
  }, [pumps, search, manufacturer, flow, onlyCasing, casingId]);

  useEffect(() => {
    if (!selected) return;
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .pumpCatalogCurve(selected)
      .then((r) => {
        if (alive) setFigure(r.figure);
      })
      .catch((e) => {
        if (alive) setError(e instanceof ApiError ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [selected]);

  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, lg: 5 }}>
        <Card>
          <Title order={3}>Biblioteca ESP</Title>
          <Text size="sm" c="dimmed">
            {filtered.length} de {pumps.length} bombas del catálogo. Elegí una fila para
            ver su curva.
          </Text>

          <Group grow mt="sm" gap="xs">
            <TextInput
              placeholder="Buscar modelo o serie…"
              value={search}
              onChange={(e) => setSearch(e.currentTarget.value)}
            />
            <Select
              placeholder="Fabricante"
              data={manufacturers}
              value={manufacturer}
              onChange={setManufacturer}
              clearable
            />
          </Group>
          <Group mt="xs" gap="md" align="center">
            <NumberInput
              placeholder="Caudal de interés"
              value={flow}
              onChange={setFlow}
              hideControls
              w={180}
              rightSection={
                <Text size="xs" c="dimmed" pr={10}>
                  bpd
                </Text>
              }
              rightSectionPointerEvents="none"
              rightSectionWidth="auto"
            />
            <Switch
              label="Solo las que entran en el casing actual"
              size="sm"
              checked={onlyCasing}
              onChange={(e) => setOnlyCasing(e.currentTarget.checked)}
              disabled={casingId == null}
            />
          </Group>

          <ScrollArea.Autosize mah={520} mt="sm">
            <Table stickyHeader highlightOnHover withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Modelo</Table.Th>
                  <Table.Th>Fabricante</Table.Th>
                  <Table.Th style={{ textAlign: "right" }}>OD [in]</Table.Th>
                  <Table.Th style={{ textAlign: "right" }}>Rango [bpd]</Table.Th>
                  <Table.Th style={{ textAlign: "right" }}>BEP [bpd]</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {filtered.map((p) => {
                  const isSel = p.model === selected;
                  return (
                    <Table.Tr
                      key={p.model}
                      onClick={() => setSelected(p.model)}
                      style={{
                        cursor: "pointer",
                        background: isSel ? "var(--app-accent-soft)" : undefined,
                      }}
                    >
                      <Table.Td>
                        <Text size="sm" fw={isSel ? 600 : 400}>
                          {p.model}
                        </Text>
                        <Text size="xs" c="dimmed">
                          serie {p.series}
                        </Text>
                      </Table.Td>
                      <Table.Td>{p.manufacturer}</Table.Td>
                      <Table.Td style={{ textAlign: "right" }}>{p.od.toFixed(2)}</Table.Td>
                      <Table.Td style={{ textAlign: "right" }}>
                        {Math.round(p.min_flow)} – {Math.round(p.max_flow)}
                      </Table.Td>
                      <Table.Td style={{ textAlign: "right" }}>{Math.round(p.bep_flow)}</Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </ScrollArea.Autosize>
        </Card>
      </Grid.Col>

      <Grid.Col span={{ base: 12, lg: 7 }}>
        <Card>
          <Group justify="space-between" align="baseline">
            <Title order={3}>{selected ? `Curva de catálogo — ${selected}` : "Curva de catálogo"}</Title>
            {loading && <Loader size="xs" />}
          </Group>

          {error && (
            <Alert color="red" variant="light" mt="sm" title="No se pudo cargar la curva">
              {error}
            </Alert>
          )}

          {!selected && (
            <Text c="dimmed" size="sm" mt="md">
              Seleccioná una bomba de la tabla para ver head/etapa, HP/etapa y eficiencia
              frente al caudal, con su BEP y rango operativo.
            </Text>
          )}

          {figure && !error && (
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
              <PlotFigure figure={figure} height={560} />
            </Suspense>
          )}
        </Card>
      </Grid.Col>
    </Grid>
  );
}
