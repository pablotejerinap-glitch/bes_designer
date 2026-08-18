// Método de incrementos de presión para pozos con gas — Kermit Brown Vol. 2b
// §4.53103.
//
// En presencia de gas libre el caudal volumétrico NO es constante a lo largo de
// la bomba: el gas se comprime, parte pasa a solución y el volumen de mezcla
// cae del orden del 40 % entre admisión y descarga. Por eso la bomba se resuelve
// tramo por tramo, y no con un único caudal promedio.
//
// Todo el cálculo vive en POST /api/gas/increment-design
// (bes.services.gas_service → bes.core.gas_handling); acá sólo se arman los
// controles y se renderiza la tabla.
import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  NumberInput,
  ScrollArea,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { api, ApiError } from "../api/client";
import type {
  DesignInputs,
  DesignResponse,
  GasCompleteDesignResponse,
  GasIncrementResponse,
  PlotlyFigure,
} from "../api/types";
import { FormulaTraceSection } from "./FormulaTrace";
import { PlotFigure } from "./PlotFigure";
import { ResultsView } from "./ResultsView";

/** Pasos ofrecidos. Cuanto más chico, mejor representa el cambio del fluido. */
const PASOS = [25, 50, 100, 200];

function n(v: number, dec = 0): string {
  return v.toLocaleString("es-AR", {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  });
}

/**
 * Envuelve el diseño por gas en la forma que ya consume `ResultsView`.
 *
 * El backend devuelve `design` con el MISMO esquema que el camino convencional
 * (hay un test de API que lo fija), así que la vista de resultados se reutiliza
 * tal cual en vez de escribir una segunda. Lo único que falta es el envoltorio
 * de recomendación: acá hay una sola bomba, no un ranking.
 */
function asDesignResponse(r: GasCompleteDesignResponse): DesignResponse {
  const d = r.design;
  return {
    recommendations: [
      {
        rank: 1,
        criteria: {
          bep_flow_bpd: 0,
          bep_distance_frac: 0,
          flow_vs_bep_pct: 0,
          efficiency: d.pump_efficiency,
          total_pump_hp: d.total_pump_hp,
          classification: "no_aplica" as never,
        },
        design: d,
        rationale: r.method.reason,
        warnings: r.warnings,
      },
    ],
    design_basis: {
      tdh_increment_ft: r.tdh_increment_ft,
      tdh_conventional_ft: r.tdh_conventional_ft,
      p_intake_psia: r.summary.p_intake,
      p_discharge_psia: r.summary.p_discharge,
      free_gas_fraction_at_intake: r.method.free_gas_fraction,
    },
    ordering_criteria: [
      "Bomba única para toda la sarta, elegida sobre el caudal de mezcla representativo (Brown §4.53103 paso 6)",
      "Descarte por carcasas, eje/cojinete y disponibilidad de aparejo del mismo fabricante",
    ],
    n_candidates_evaluated: r.rejected.length + 1,
    warnings: r.warnings,
  };
}

/** Colorea el origen del dato PVT, para que se vea de un vistazo qué es medido. */
function OrigenPVT({ sources }: { sources: Record<string, string> }) {
  const deTabla = Object.values(sources).filter((s) => s === "pvt").length;
  const total = Object.keys(sources).length;
  if (deTabla === 0) {
    return (
      <Tooltip label="Todas las propiedades salen de correlaciones (Standing / DAK / McCain)">
        <Badge color="gray" variant="light" size="sm">
          correlación
        </Badge>
      </Tooltip>
    );
  }
  return (
    <Tooltip
      label={Object.entries(sources)
        .map(([k, v]) => `${k}: ${v}`)
        .join(" · ")}
    >
      <Badge color="teal" variant="light" size="sm">
        PVT {deTabla}/{total}
      </Badge>
    </Tooltip>
  );
}

/**
 * Escalera de incrementos — la figura 4.56B del libro.
 *
 * El gráfico lo construye el backend (`bes.plotting.plot_gas_increment_ladder`)
 * y viaja dentro de la respuesta del cálculo: acá sólo se pasa a <Plot>, que es
 * la regla del proyecto (ver `.claude/rules/frontend.md`).
 *
 * Si el backend no pudo armarla manda `{}` y no se dibuja nada — un gráfico no
 * puede hacer desaparecer el resto del resultado.
 */
function Escalera({ figure }: { figure: PlotlyFigure | Record<string, never> }) {
  if (!("data" in figure)) return null;
  return (
    <Card padding="lg">
      <Title order={5}>Escalera de incrementos</Title>
      <Text c="dimmed" size="sm" mt={4}>
        La Fig. 4.56B de Brown: la admisión abajo, la descarga arriba, el caudal
        de mezcla a la izquierda de cada peldaño y la presión a la derecha. El
        volumen <b>baja</b> al subir la presión, porque el gas se comprime y
        parte pasa a solución — es el motivo de todo el método. La separación
        entre peldaños es proporcional al ΔP, así que un último escalón corto
        (marcado con <b>*</b>) es el resto de la división.
      </Text>
      <PlotFigure figure={figure as PlotlyFigure} height={620} />
    </Card>
  );
}

export function GasIncrementView({ inputs }: { inputs: DesignInputs | null }) {
  const [incrementPsi, setIncrementPsi] = useState<number>(200);
  const [pIntake, setPIntake] = useState<number | string>("");
  const [pDischarge, setPDischarge] = useState<number | string>("");
  const [ventGasPct, setVentGasPct] = useState<number | string>(0);
  const [aplicarViscosidad, setAplicarViscosidad] = useState(true);
  const [aplicarDeterioro, setAplicarDeterioro] = useState(false);
  const [detalleExtremos, setDetalleExtremos] = useState(false);

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<GasIncrementResponse | null>(null);
  const [completo, setCompleto] = useState<GasCompleteDesignResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (!inputs) return;
    setRunning(true);
    setError(null);
    setResult(null);
    setCompleto(null);
    try {
      const res = await api.gasIncrementDesign({
        ...inputs,
        increment_psi: incrementPsi,
        p_intake: pIntake === "" ? null : Number(pIntake),
        p_discharge: pDischarge === "" ? null : Number(pDischarge),
        vent_gas_pct: Number(ventGasPct) / 100,
        apply_viscosity: aplicarViscosidad,
        apply_deterioration: aplicarDeterioro,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  /**
   * Diseño completo: además de la hidráulica arma el aparejo entero.
   * Las presiones las calcula el backend con el recorrido multifásico, así que
   * este camino no acepta p_intake/p_discharge cargadas a mano.
   */
  async function runCompleto() {
    if (!inputs) return;
    setRunning(true);
    setError(null);
    setCompleto(null);
    try {
      const res = await api.gasCompleteDesign({
        ...inputs,
        increment_psi: incrementPsi,
        vent_gas_pct: Number(ventGasPct) / 100,
        apply_viscosity: aplicarViscosidad,
        apply_deterioration: aplicarDeterioro,
      });
      setCompleto(res);
      // La tabla por intervalo es la misma; se reusa el render de abajo.
      setResult({
        summary: res.summary,
        increments: res.increments,
        free_gas_fraction_at_intake: res.method.free_gas_fraction,
        gas_risk: {},
        separator: {},
        warnings: res.warnings,
        ladder_figure: res.ladder_figure,
        // Las mismas fórmulas del método: en este camino viajan dentro del
        // DesignResult, y ResultsView es quien las muestra.
        formulas: res.design.formulas ?? [],
      });
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

  const s = result?.summary;

  return (
    <Stack gap="md">
      <Card padding="lg">
        <Title order={4}>Método de incrementos de presión</Title>
        <Text c="dimmed" size="sm">
          Brown Vol. 2b §4.53103. Divide el salto de presión de la bomba en
          escalones, evalúa el fluido en <b>los dos extremos</b> de cada uno y
          resuelve etapas y potencia tramo por tramo. Con gas libre el caudal de
          mezcla cambia con la presión, así que un único caudal promedio no
          alcanza.
        </Text>

        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} mt="md">
          <NumberInput
            label="Escalón de presión"
            description="Más chico = más fiel"
            suffix=" psi"
            value={incrementPsi}
            onChange={(v) => setIncrementPsi(Number(v) || 200)}
            min={1}
            max={1000}
          />
          <NumberInput
            label="Presión de admisión"
            description="vacío = calcularla"
            suffix=" psia"
            value={pIntake}
            onChange={setPIntake}
            min={1}
          />
          <NumberInput
            label="Presión de descarga"
            description="vacío = calcularla"
            suffix=" psia"
            value={pDischarge}
            onChange={setPDischarge}
            min={1}
          />
          <NumberInput
            label="Gas venteado por el anular"
            suffix=" %"
            value={ventGasPct}
            onChange={setVentGasPct}
            min={0}
            max={100}
          />
        </SimpleGrid>

        <Group mt="sm" gap="xs">
          {PASOS.map((p) => (
            <Button
              key={p}
              size="compact-xs"
              variant={incrementPsi === p ? "filled" : "default"}
              onClick={() => setIncrementPsi(p)}
            >
              {p} psi
            </Button>
          ))}
        </Group>

        <Group mt="md" gap="xl">
          <Checkbox
            label="Corregir por viscosidad (Riling)"
            description="Sin efecto en crudos de 28 °API o más"
            checked={aplicarViscosidad}
            onChange={(e) => setAplicarViscosidad(e.currentTarget.checked)}
          />
          <Checkbox
            label="Degradar altura por gas libre"
            description="Brown §4.53102"
            checked={aplicarDeterioro}
            onChange={(e) => setAplicarDeterioro(e.currentTarget.checked)}
          />
        </Group>

        <Group mt="md">
          <Button onClick={runCompleto} loading={running}>
            Diseñar BES completo
          </Button>
          <Button variant="default" onClick={run} loading={running}>
            Sólo hidráulica
          </Button>
          <Text size="xs" c="dimmed">
            El diseño completo agrega motor, sello, cable y transformador. Las
            presiones las calcula con el recorrido multifásico.
          </Text>
        </Group>

        {error && (
          <Alert color="red" mt="md" title="No se pudo correr el método">
            {error}
          </Alert>
        )}
      </Card>

      {completo && (
        <>
          <Alert color="teal" variant="light" title="Manejo del gas">
            <Text size="sm">{completo.feasibility.verdict}</Text>
            <SimpleGrid cols={{ base: 2, sm: 4 }} mt="sm" spacing="xs">
              <Metric
                label="Gas libre en admisión"
                value={`${n(completo.feasibility.f_intake * 100, 1)} %`}
              />
              <Metric
                label="Separador"
                value={
                  completo.feasibility.separator_efficiency != null
                    ? `${n(completo.feasibility.separator_efficiency * 100, 0)} %`
                    : "sin separador"
                }
                hint={completo.feasibility.separator_model ?? undefined}
              />
              <Metric
                label="Gas que entra a la bomba"
                value={`${n(completo.feasibility.f_pump * 100, 1)} %`}
              />
              <Metric
                label="Máximo admisible"
                value={`${n(completo.feasibility.max_gip * 100, 1)} %`}
                hint="objectives.max_gip — por encima, la BES no converge"
              />
            </SimpleGrid>
          </Alert>

          <Alert
            color={completo.method.applies ? "teal" : "blue"}
            variant="light"
            title="Método aplicado"
          >
            <Text size="sm">{completo.method.reason}</Text>
            <Text size="sm" mt="xs">
              <b>TDH:</b> {n(completo.tdh_increment_ft)} ft por incrementos
              (con este se dimensionó el aparejo) contra{" "}
              {n(completo.tdh_conventional_ft)} ft por la fórmula convencional
              de tres términos —{" "}
              {n(
                (Math.abs(
                  completo.tdh_increment_ft - completo.tdh_conventional_ft
                ) /
                  completo.tdh_conventional_ft) *
                  100,
                1
              )}{" "}
              % de diferencia. Son dos rutas independientes a la misma magnitud;
              se publican las dos para poder auditarlas.
            </Text>
            {completo.rejected.length > 0 && (
              <Text size="xs" c="dimmed" mt="xs">
                Bombas descartadas antes de llegar a ésta:{" "}
                {completo.rejected.join(" · ")}
              </Text>
            )}
          </Alert>

          {/* La escalera NO va acá: `runCompleto` también setea `result`, así que
              se dibuja una sola vez junto a la tabla que explica, más abajo. */}
          <ResultsView
            response={asDesignResponse(completo)}
            inputs={inputs}
            title="Diseño BES — método por incrementos de presión"
          />
        </>
      )}

      {result && s && (
        <>
          {result.warnings.length > 0 && (
            <Alert color="yellow" variant="light" title="Advertencias">
              <Stack gap={4}>
                {result.warnings.map((w, i) => (
                  <Text key={i} size="sm">
                    {w}
                  </Text>
                ))}
              </Stack>
            </Alert>
          )}

          <Card padding="lg">
            <Group justify="space-between" align="flex-start">
              <Title order={5}>Resumen</Title>
              <Badge variant="light" color="gray">
                PVT: {s.pvt_source}
              </Badge>
            </Group>

            <SimpleGrid cols={{ base: 2, sm: 3, lg: 4 }} mt="md" spacing="lg">
              <Metric label="Presión de admisión" value={`${n(s.p_intake)} psia`} />
              <Metric label="Presión de descarga" value={`${n(s.p_discharge)} psia`} />
              <Metric label="ΔP total" value={`${n(s.delta_p)} psi`} />
              <Metric
                label="Escalón"
                value={`${n(s.increment_psi)} psi · ${s.n_increments} tramos`}
              />
              <Metric
                label="Caudal objetivo de petróleo"
                value={`${n(s.target_oil_rate)} STB/d`}
              />
              <Metric
                label="Mezcla en la admisión"
                value={`${n(s.q_mix_intake_bpd)} b/d`}
              />
              <Metric
                label="Mezcla en la descarga"
                value={`${n(s.q_mix_discharge_bpd)} b/d`}
              />
              <Metric
                label="Caudal másico"
                value={`${n(s.mass_rate_lbm_d)} lbm/d`}
                hint="Constante en toda la bomba: es el invariante de control del método"
              />
              <Metric label="Etapas totales" value={n(s.total_stages)} />
              <Metric
                label="Etapas (cálculo a mano)"
                value={n(s.total_stages_longhand)}
                hint="Sumando el redondeo hacia arriba de cada tramo, como en el libro"
              />
              <Metric label="Potencia requerida" value={`${n(s.total_hp, 1)} hp`} />
              <Metric
                label="Bomba"
                value={`${s.pump_model} — ${s.pump_manufacturer}`}
                hint={`Serie ${s.pump_series}`}
              />
              <Metric
                label="Profundidad de admisión"
                value={`${n(s.pump_setting_depth)} ft`}
              />
              <Metric
                label="Temperatura de admisión"
                value={`${n(s.pump_intake_temp_f)} °F`}
              />
              <Metric
                label="Gas que entra a la bomba"
                value={`${n(s.gip * 100, 0)} %`}
              />
              <Metric
                label="Gas libre en la admisión"
                value={`${n(result.free_gas_fraction_at_intake * 100, 1)} %`}
              />
            </SimpleGrid>
          </Card>

          <Escalera figure={result.ladder_figure} />

          <Card padding="lg">
            <Group justify="space-between">
              <Title order={5}>Tabla por intervalo</Title>
              <Switch
                label="Mostrar valores en cada extremo"
                checked={detalleExtremos}
                onChange={(e) => setDetalleExtremos(e.currentTarget.checked)}
              />
            </Group>
            <Text c="dimmed" size="sm" mt={4}>
              Cada fila es un escalón de presión. Las columnas de PVT y caudal son
              el <b>promedio del intervalo</b>, calculado sobre sus dos extremos.
            </Text>

            <ScrollArea mt="md">
              <Table striped withTableBorder highlightOnHover fz="xs">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>P ent.</Table.Th>
                    <Table.Th>P sal.</Table.Th>
                    <Table.Th>ΔP</Table.Th>
                    {detalleExtremos && (
                      <>
                        <Table.Th>Qo ent.</Table.Th>
                        <Table.Th>Qw ent.</Table.Th>
                        <Table.Th>Qg ent.</Table.Th>
                        <Table.Th>Qmix ent.</Table.Th>
                        <Table.Th>Qmix sal.</Table.Th>
                      </>
                    )}
                    <Table.Th>Q prom.</Table.Th>
                    <Table.Th>Rs</Table.Th>
                    <Table.Th>Bo</Table.Th>
                    <Table.Th>Bg</Table.Th>
                    <Table.Th>ρ</Table.Th>
                    <Table.Th>Grad.</Table.Th>
                    <Table.Th>Head/et.</Table.Th>
                    <Table.Th>η</Table.Th>
                    <Table.Th>psi/et.</Table.Th>
                    <Table.Th>Etapas</Table.Th>
                    <Table.Th>hp</Table.Th>
                    <Table.Th>Origen</Table.Th>
                  </Table.Tr>
                  <Table.Tr>
                    <Table.Th c="dimmed" fw={400}>psia</Table.Th>
                    <Table.Th c="dimmed" fw={400}>psia</Table.Th>
                    <Table.Th c="dimmed" fw={400}>psi</Table.Th>
                    {detalleExtremos && (
                      <>
                        <Table.Th c="dimmed" fw={400}>b/d</Table.Th>
                        <Table.Th c="dimmed" fw={400}>b/d</Table.Th>
                        <Table.Th c="dimmed" fw={400}>b/d</Table.Th>
                        <Table.Th c="dimmed" fw={400}>b/d</Table.Th>
                        <Table.Th c="dimmed" fw={400}>b/d</Table.Th>
                      </>
                    )}
                    <Table.Th c="dimmed" fw={400}>b/d</Table.Th>
                    <Table.Th c="dimmed" fw={400}>scf/b</Table.Th>
                    <Table.Th c="dimmed" fw={400}>rb/STB</Table.Th>
                    <Table.Th c="dimmed" fw={400}>b/scf</Table.Th>
                    <Table.Th c="dimmed" fw={400}>lbm/ft³</Table.Th>
                    <Table.Th c="dimmed" fw={400}>psi/ft</Table.Th>
                    <Table.Th c="dimmed" fw={400}>ft</Table.Th>
                    <Table.Th c="dimmed" fw={400}>%</Table.Th>
                    <Table.Th c="dimmed" fw={400}>psi</Table.Th>
                    <Table.Th c="dimmed" fw={400}>—</Table.Th>
                    <Table.Th c="dimmed" fw={400}>hp</Table.Th>
                    <Table.Th c="dimmed" fw={400}>PVT</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {result.increments.map((r, i) => (
                    <Table.Tr key={i}>
                      <Table.Td>{n(r.p_lo)}</Table.Td>
                      <Table.Td>{n(r.p_hi)}</Table.Td>
                      <Table.Td>{n(r.delta_p)}</Table.Td>
                      {detalleExtremos && (
                        <>
                          <Table.Td>{n(r.q_oil_lo)}</Table.Td>
                          <Table.Td>{n(r.q_water_lo)}</Table.Td>
                          <Table.Td>{n(r.q_gas_lo)}</Table.Td>
                          <Table.Td>{n(r.q_lo_bpd)}</Table.Td>
                          <Table.Td>{n(r.q_hi_bpd)}</Table.Td>
                        </>
                      )}
                      <Table.Td fw={600}>{n(r.q_avg_bpd)}</Table.Td>
                      <Table.Td>{n(r.rs)}</Table.Td>
                      <Table.Td>{n(r.bo, 3)}</Table.Td>
                      <Table.Td>{r.bg.toExponential(2)}</Table.Td>
                      <Table.Td>{n(r.rho_mix, 1)}</Table.Td>
                      <Table.Td>{n(r.gradient, 4)}</Table.Td>
                      <Table.Td>
                        {n(r.head_per_stage, 1)}
                        {r.is_viscous && (
                          <Tooltip
                            label={`Riling: C_Q ${n(r.capacity_factor, 1)} % · C_H ${n(
                              r.head_factor,
                              1
                            )} % · C_HP ${n(r.hp_factor, 1)} %`}
                          >
                            <Badge ml={4} size="xs" color="orange" variant="light">
                              visc
                            </Badge>
                          </Tooltip>
                        )}
                      </Table.Td>
                      <Table.Td>{n(r.efficiency, 1)}</Table.Td>
                      <Table.Td>{n(r.psi_per_stage, 2)}</Table.Td>
                      <Table.Td fw={600}>{n(r.stages_exact, 1)}</Table.Td>
                      <Table.Td>{n(r.hp, 2)}</Table.Td>
                      <Table.Td>
                        <OrigenPVT sources={r.pvt_sources} />
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
                <Table.Tfoot>
                  <Table.Tr>
                    <Table.Th colSpan={detalleExtremos ? 17 : 12}>Total</Table.Th>
                    <Table.Th>{n(s.total_stages_exact, 1)}</Table.Th>
                    <Table.Th>{n(s.total_hp, 2)}</Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Tfoot>
              </Table>
            </ScrollArea>

            <Text c="dimmed" size="xs" mt="sm">
              Las etapas se acumulan como fracción y se redondean una sola vez al
              final ({n(s.total_stages_exact, 1)} → {n(s.total_stages)}). Redondear
              cada tramo por separado —la convención del cálculo a mano, que da{" "}
              {n(s.total_stages_longhand)}— acumula hasta media etapa por escalón y
              empeora el resultado al afinar el paso.
            </Text>
          </Card>

          {/* En el camino completo las fórmulas ya las muestra ResultsView
              (DesignResult.formulas). Acá sólo cuando se corrió la hidráulica
              sola, para no duplicar la misma sección. */}
          {!completo && (
            <Card padding="lg">
              <FormulaTraceSection formulas={result.formulas} />
            </Card>
          )}
        </>
      )}
    </Stack>
  );
}

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  const cuerpo = (
    <div>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={600}>{value}</Text>
    </div>
  );
  return hint ? <Tooltip label={hint}>{cuerpo}</Tooltip> : cuerpo;
}
