import { useEffect, useState } from "react";
import {
  Accordion,
  Divider,
  Grid,
  NumberInput,
  Select,
  Switch,
  Text,
} from "@mantine/core";
import { api } from "../api/client";
import type {
  DesignInputs,
  DriveMechanism,
  FluidInput,
  IPRFromTestResponse,
  IPRMethod,
  ObjectivesInput,
  PressureLossMethod,
  ReservoirInput,
  SurfaceInput,
  TubularCatalog,
  TubularDim,
  WellInput,
} from "../api/types";

type Section = keyof DesignInputs;

interface NumField {
  key: string;
  label: string;
  unit?: string;
  step?: number;
  /** Aclaración bajo la etiqueta, p. ej. para marcar un campo opcional. */
  description?: string;
  /** Vacío viaja como null en vez de 0, para campos que el backend admite sin valor. */
  optional?: boolean;
}

// El índice de productividad NO se carga: es un resultado del ensayo. Acá se
// piden las magnitudes que efectivamente se miden en el pozo (la Pwf y el
// caudal estabilizados) y el backend despeja J con el método IPR elegido.
const RESERVOIR_NUM: NumField[] = [
  // Todas las presiones del formulario se rotulan "psi": la distinción psia/psi
  // que traía el dominio confundía sin aportar, porque el formulario nunca pide
  // una presión manométrica. Los valores siguen siendo absolutos.
  { key: "static_pressure", label: "Presión estática", unit: "psi" },
  { key: "bubble_point", label: "Presión de burbuja", unit: "psi" },
  { key: "test_pwf", label: "Ensayo · Pwf medida", unit: "psi" },
  { key: "test_rate", label: "Ensayo · caudal medido", unit: "STB/d" },
  { key: "reservoir_temp", label: "Temperatura de reservorio", unit: "°F" },
];

const FLUID_NUM: NumField[] = [
  { key: "oil_api", label: "Gravedad API", unit: "°API", step: 0.1 },
  { key: "water_cut", label: "Corte de agua", unit: "frac 0-1", step: 0.01 },
  { key: "gor", label: "GOR", unit: "scf/STB" },
  { key: "gas_sg", label: "SG del gas", unit: "aire=1", step: 0.01 },
  { key: "water_sg", label: "SG de la salmuera", step: 0.01 },
  // Opcionales: sin ensayo de laboratorio el backend lee la Fig. 4L(2) del
  // libro con la °API y la temperatura de admisión, que es el paso 2 de
  // Riling. Vacío viaja como null; un 0 sería un dato falso y da 422.
  {
    key: "oil_viscosity_dead",
    label: "Viscosidad del petróleo",
    unit: "cp",
    step: 0.1,
    description: "opcional · vacío = Fig. 4L(2)",
    optional: true,
  },
  {
    key: "viscosity_temp_ref",
    label: "Temp. de la viscosidad",
    unit: "°F",
    description: "sólo si cargaste la viscosidad",
    optional: true,
  },
  // Pb del fluido no se pide acá: es el mismo punto de burbuja del reservorio
  // ("Presión de burbuja"). App sincroniza fluid.bubble_point_pressure =
  // reservoir.bubble_point para que IPR y PVT usen un único valor.
  { key: "h2s_content", label: "H2S", unit: "ppm" },
  { key: "co2_content", label: "CO2", unit: "ppm" },
];

// Los diámetros de casing/tubing salen de la tabla Tenaris (OD -> peso -> ID),
// no de inputs numéricos sueltos; el resto de la geometría sí son números.
const WELL_TOP: NumField[] = [
  { key: "total_depth", label: "Profundidad total", unit: "ft MD" },
];
const WELL_BOTTOM: NumField[] = [
  { key: "perforations_top", label: "Tope perforaciones", unit: "ft MD" },
  { key: "perforations_bottom", label: "Base perforaciones", unit: "ft MD" },
  // Opcional: vacío = se calcula como tope de punzados menos el margen de
  // seguridad de la sección de objetivos. Cargarla manda sobre ese cálculo.
  {
    key: "pump_setting_depth",
    label: "Profundidad de succión",
    unit: "ft MD",
    description: "opcional · vacío = punzados − margen",
    optional: true,
  },
  { key: "deviation_max", label: "Desviación máxima", unit: "°", step: 0.5 },
  { key: "wellhead_temp", label: "Temp. boca de pozo", unit: "°F" },
];

const SURFACE_NUM: NumField[] = [
  { key: "wellhead_pressure_required", label: "Presión en cabeza (Pth)", unit: "psi" },
  { key: "flowline_length", label: "Longitud flowline", unit: "ft" },
  { key: "flowline_id", label: "ID flowline", unit: "in", step: 0.1 },
  { key: "flowline_elevation_change", label: "Cambio de elevación", unit: "ft" },
  { key: "separator_pressure", label: "Presión separador", unit: "psi" },
  { key: "power_supply_voltage", label: "Voltaje de superficie", unit: "V" },
];

const OBJECTIVES_NUM: NumField[] = [
  { key: "target_flow_rate", label: "Caudal objetivo", unit: "STB/d" },
  { key: "safety_margin_depth", label: "Margen de profundidad", unit: "ft" },
  { key: "max_gip", label: "Máx. gas en bomba", unit: "frac 0-1", step: 0.01 },
  { key: "design_life_years", label: "Vida de diseño", unit: "años", step: 0.5 },
];

const IPR_OPTIONS: { value: IPRMethod; label: string }[] = [
  { value: "linear", label: "Linear (Darcy)" },
  { value: "vogel", label: "Vogel" },
  { value: "fetkovich", label: "Fetkovich" },
];

/** Los tres OD de tubing para los que se levantó Poettmann-Carpenter: los
 *  nominales de 2, 2½ y 3 pulg. Es el mismo `PC_TUBING_OD_IN` del dominio
 *  (`core/multiphase.py`); acá sólo se usa para no ofrecer una cañería que el
 *  backend va a rechazar con 422. */
const PC_TUBING_OD = [2.375, 2.875, 3.5];

const PRESSURE_LOSS_OPTIONS: { value: PressureLossMethod; label: string }[] = [
  { value: "poettmann_carpenter", label: "Poettmann & Carpenter (multifásico)" },
  { value: "hazen_williams", label: "Hazen-Williams (monofásico)" },
];

const DRIVE_OPTIONS: { value: DriveMechanism; label: string }[] = [
  { value: "solution_gas", label: "Solution gas" },
  { value: "water_drive", label: "Water drive" },
  { value: "gas_cap", label: "Gas cap" },
  { value: "combination", label: "Combination" },
];

interface Props {
  value: DesignInputs;
  onChange: (v: DesignInputs) => void;
}

export function WellForm({ value, onChange }: Props) {
  function setNum<S extends Section>(section: S, key: string, v: number | string) {
    const num = typeof v === "number" ? v : parseFloat(v);
    onChange({
      ...value,
      [section]: { ...value[section], [key]: Number.isFinite(num) ? num : 0 },
    });
  }

  function setRaw<S extends Section>(section: S, key: string, v: unknown) {
    onChange({ ...value, [section]: { ...value[section], [key]: v } });
  }

  // Campos opcionales: vacío viaja como null, no como 0 — un 0 sería un valor
  // fuera de rango que el backend rechazaría con 422.
  function toNumOrNull(v: number | string): number | null {
    const num = typeof v === "number" ? v : parseFloat(v);
    return Number.isFinite(num) ? num : null;
  }

  // La unidad va como sufijo dentro del input (estilo pengtools), no como
  // description: siempre visible al lado del número.
  function numGrid<S extends Section>(section: S, fields: NumField[]) {
    const obj = value[section] as unknown as Record<string, number>;
    return (
      <Grid gutter="xs">
        {fields.map((f) => (
          <Grid.Col span={{ base: 12, xs: 6 }} key={f.key}>
            <NumberInput
              label={f.label}
              description={f.description}
              value={obj[f.key] ?? ""}
              step={f.step ?? 1}
              onChange={(v) =>
                f.optional
                  ? setRaw(section, f.key, toNumOrNull(v))
                  : setNum(section, f.key, v)
              }
              min={f.optional ? 0 : undefined}
              hideControls
              rightSection={
                f.unit ? (
                  <Text size="xs" c="dimmed" pr={10} className="num" style={{ whiteSpace: "nowrap" }}>
                    {f.unit}
                  </Text>
                ) : undefined
              }
              rightSectionPointerEvents="none"
              rightSectionWidth="auto"
            />
          </Grid.Col>
        ))}
      </Grid>
    );
  }

  const reservoir = value.reservoir as ReservoirInput;
  const fluid = value.fluid as FluidInput;
  const surface = value.surface as SurfaceInput;
  const objectives = value.objectives as ObjectivesInput;
  const well = value.well as WellInput;

  // --- Casing / tubing dimensional (tablas Tenaris API 5CT) ---
  // El usuario elige OD y peso nominal (lo que traen los catálogos); el ID —que
  // casi nunca está a mano— se autocompleta desde la tabla. Se puede editar a
  // mano si hace falta un valor no estándar.
  const [tubulars, setTubulars] = useState<TubularCatalog | null>(null);
  useEffect(() => {
    api.tubulars().then(setTubulars).catch(() => setTubulars(null));
  }, []);

  // --- Entregabilidad derivada del ensayo (solo lectura) ---
  // J no es un dato: sale de invertir el modelo IPR sobre el punto ensayado.
  // El despeje vive en el backend, acá sólo se muestra lo que devuelve. Un
  // ensayo inválido (Pwf >= Pr) deja el bloque vacío; el error real lo da
  // /api/design al calcular.
  const [derived, setDerived] = useState<IPRFromTestResponse | null>(null);
  const { static_pressure, bubble_point, test_pwf, test_rate, ipr_method, fetkovich_n } =
    reservoir;
  useEffect(() => {
    let cancelled = false;
    if (!(static_pressure > 0 && test_rate > 0 && test_pwf >= 0 && test_pwf < static_pressure)) {
      setDerived(null);
      return;
    }
    const t = setTimeout(() => {
      api
        .iprFromTest({
          static_pressure,
          bubble_point,
          test_pwf,
          test_rate,
          ipr_method,
          fetkovich_n,
        })
        .then((d) => !cancelled && setDerived(d))
        .catch(() => !cancelled && setDerived(null));
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [static_pressure, bubble_point, test_pwf, test_rate, ipr_method, fetkovich_n]);

  function setWell(fields: Partial<WellInput>) {
    onChange({ ...value, well: { ...value.well, ...fields } });
  }

  const uniqueOds = (rows: TubularDim[]) => {
    const seen = new Map<number, string>();
    for (const r of rows) if (!seen.has(r.od_in)) seen.set(r.od_in, r.od_label);
    return [...seen.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([od_in, od_label]) => ({ od_in, od_label }));
  };
  const weightRows = (rows: TubularDim[], od: number) =>
    rows
      .filter((r) => Math.abs(r.od_in - od) < 1e-6)
      .sort((a, b) => a.weight_lbft - b.weight_lbft);
  const near = (a: number, b: number, tol = 1e-6) => Math.abs(a - b) < tol;

  function tubularBlock(opts: {
    title: string;
    rows: TubularDim[];
    od: number;
    weight: number | null;
    id: number;
    driftIn: number | null;
    onOd: (od: number, first: TubularDim | null) => void;
    onWeight: (row: TubularDim) => void;
    onId: (v: number) => void;
    /** Si viene, el desplegable de OD ofrece SÓLO estos diámetros. Lo usa el
     *  tubing cuando se eligió P&C, que no es aplicable a otras cañerías. */
    onlyOds?: number[];
  }) {
    const { title, rows, od, weight, id, driftIn, onlyOds } = opts;
    const todos = uniqueOds(rows);
    const ods = onlyOds
      ? todos.filter((o) => onlyOds.some((allowed) => near(o.od_in, allowed)))
      : todos;
    const odFuera = onlyOds ? !onlyOds.some((allowed) => near(od, allowed)) : false;
    let odData = ods.map((o) => ({ value: String(o.od_in), label: `${o.od_label}"  ·  ${o.od_in} in` }));
    if (od && !odFuera && !ods.some((o) => near(o.od_in, od))) {
      odData = [{ value: String(od), label: `${od} in (manual)` }, ...odData];
    }
    const wr = weightRows(rows, od);
    let wData = wr.map((r) => ({ value: String(r.weight_lbft), label: `${r.weight_lbft} lb/ft  ·  ID ${r.id_in}"` }));
    if (weight != null && !wr.some((r) => near(r.weight_lbft, weight))) {
      wData = [{ value: String(weight), label: `${weight} lb/ft (manual)` }, ...wData];
    }
    return (
      <>
        <Divider my="xs" label={title} labelPosition="left" />
        <Grid gutter="xs">
          <Grid.Col span={{ base: 12, xs: 4 }}>
            <Select
              label="OD"
              data={odData}
              value={od && !odFuera ? String(od) : null}
              searchable
              allowDeselect={false}
              error={
                odFuera
                  ? `Poettmann-Carpenter no es aplicable a ${od} in: elegí 2 3/8, 2 7/8 o 3 1/2`
                  : undefined
              }
              placeholder={odFuera ? `${od} in — fuera del método` : undefined}
              onChange={(v) => {
                if (!v) return;
                const newOd = parseFloat(v);
                opts.onOd(newOd, weightRows(rows, newOd)[0] ?? null);
              }}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, xs: 4 }}>
            <Select
              label="Peso nominal"
              data={wData}
              value={weight != null ? String(weight) : null}
              searchable
              allowDeselect={false}
              nothingFoundMessage="Elegí un OD"
              onChange={(v) => {
                if (!v) return;
                const w = parseFloat(v);
                const row = weightRows(rows, od).find((r) => near(r.weight_lbft, w));
                if (row) opts.onWeight(row);
              }}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, xs: 4 }}>
            <NumberInput
              label="ID"
              value={id}
              step={0.001}
              decimalScale={3}
              onChange={(v) => opts.onId(typeof v === "number" ? v : parseFloat(String(v)))}
              hideControls
              rightSection={<Text size="xs" c="dimmed" pr={10} className="num">in</Text>}
              rightSectionPointerEvents="none"
              rightSectionWidth="auto"
              description={driftIn != null ? `Drift API: ${driftIn}"` : "autocompletado desde la tabla"}
            />
          </Grid.Col>
        </Grid>
      </>
    );
  }

  // Fallback si el backend no está disponible: los 5 campos como números sueltos.
  const WELL_TUBULARS_FALLBACK: NumField[] = [
    { key: "casing_od", label: "OD casing", unit: "in", step: 0.001 },
    { key: "casing_weight", label: "Peso casing", unit: "lb/ft", step: 0.1 },
    { key: "casing_id", label: "ID casing", unit: "in", step: 0.001 },
    { key: "tubing_od", label: "OD tubing", unit: "in", step: 0.001 },
    { key: "tubing_id", label: "ID tubing", unit: "in", step: 0.001 },
  ];

  const tubingWeight = tubulars
    ? weightRows(tubulars.tubing, well.tubing_od).find((r) => near(r.id_in, well.tubing_id, 1e-3))?.weight_lbft ?? null
    : null;
  const casingDrift = tubulars
    ? weightRows(tubulars.casing, well.casing_od).find((r) => near(r.weight_lbft, well.casing_weight))?.drift_in ?? null
    : null;
  const tubingDrift = tubulars
    ? weightRows(tubulars.tubing, well.tubing_od).find((r) => tubingWeight != null && near(r.weight_lbft, tubingWeight))?.drift_in ?? null
    : null;

  return (
    <Accordion multiple defaultValue={["reservoir"]} variant="separated">
      <Accordion.Item value="reservoir">
        <Accordion.Control>1 · Reservorio</Accordion.Control>
        <Accordion.Panel>
          {numGrid("reservoir", RESERVOIR_NUM)}
          <Grid mt="xs">
            <Grid.Col span={{ base: 12, sm: 6 }}>
              <Select
                label="Método IPR"
                data={IPR_OPTIONS}
                value={reservoir.ipr_method}
                onChange={(v) => v && setRaw("reservoir", "ipr_method", v)}
                allowDeselect={false}
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12, sm: 6 }}>
              <Select
                label="Mecanismo de empuje"
                data={DRIVE_OPTIONS}
                value={reservoir.drive_mechanism}
                onChange={(v) => v && setRaw("reservoir", "drive_mechanism", v)}
                allowDeselect={false}
              />
            </Grid.Col>
          </Grid>

          {/* n sólo aplica a Fetkovich y ahí es obligatorio: un ensayo de un
              solo punto no permite ajustar C y n a la vez, así que n se carga
              y C se despeja. El backend rechaza con 422 si falta. */}
          {reservoir.ipr_method === "fetkovich" && (
            <Grid mt="xs">
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <NumberInput
                  label="Exponente n de Fetkovich"
                  description="1.0 = laminar · 0.5 = turbulento pleno"
                  value={reservoir.fetkovich_n ?? ""}
                  step={0.01}
                  min={0.5}
                  max={1}
                  decimalScale={3}
                  onChange={(v) => setRaw("reservoir", "fetkovich_n", toNumOrNull(v))}
                  hideControls
                />
              </Grid.Col>
            </Grid>
          )}

          <Divider my="sm" label="Derivado del ensayo" labelPosition="left" />
          {derived ? (
            <Grid gutter="xs">
              <Grid.Col span={{ base: 12, sm: 4 }}>
                <NumberInput
                  label="Índice de productividad"
                  description={
                    reservoir.ipr_method === "fetkovich"
                      ? "secante en el ensayo — informativo"
                      : "calculado, no editable"
                  }
                  value={Number(derived.productivity_index.toFixed(4))}
                  rightSection={<Text size="xs" c="dimmed" pr={8}>STB/d/psi</Text>}
                  rightSectionPointerEvents="none"
                  rightSectionWidth="auto"
                  readOnly
                  hideControls
                />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 4 }}>
                <NumberInput
                  label="Draw-down del ensayo"
                  value={Number(derived.drawdown_psi.toFixed(1))}
                  rightSection={<Text size="xs" c="dimmed" pr={8}>psi</Text>}
                  rightSectionPointerEvents="none"
                  rightSectionWidth="auto"
                  readOnly
                  hideControls
                />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 4 }}>
                <NumberInput
                  label="AOF"
                  description="caudal a Pwf = 0"
                  value={Number(derived.aof.toFixed(1))}
                  rightSection={<Text size="xs" c="dimmed" pr={8}>STB/d</Text>}
                  rightSectionPointerEvents="none"
                  rightSectionWidth="auto"
                  readOnly
                  hideControls
                />
              </Grid.Col>
              {derived.fetkovich_c != null && (
                <Grid.Col span={{ base: 12, sm: 6 }}>
                  <NumberInput
                    label="Coeficiente C de Fetkovich"
                    description="despejado del ensayo con el n cargado"
                    value={Number(derived.fetkovich_c.toPrecision(6))}
                    readOnly
                    hideControls
                  />
                </Grid.Col>
              )}
            </Grid>
          ) : (
            <Text size="xs" c="dimmed">
              Cargá un ensayo válido (Pwf menor que la presión estática y caudal
              mayor que cero) para ver el índice de productividad.
            </Text>
          )}
        </Accordion.Panel>
      </Accordion.Item>

      <Accordion.Item value="fluid">
        <Accordion.Control>2 · Fluido</Accordion.Control>
        <Accordion.Panel>
          {numGrid("fluid", FLUID_NUM)}
          <Switch
            mt="sm"
            label="Producción de arena"
            checked={fluid.sand_production}
            onChange={(e) => setRaw("fluid", "sand_production", e.currentTarget.checked)}
          />
        </Accordion.Panel>
      </Accordion.Item>

      <Accordion.Item value="well">
        <Accordion.Control>3 · Geometría del pozo</Accordion.Control>
        <Accordion.Panel>
          {numGrid("well", WELL_TOP)}
          {tubulars ? (
            <>
              {tubularBlock({
                title: "Casing (Tenaris API 5CT)",
                rows: tubulars.casing,
                od: well.casing_od,
                weight: well.casing_weight,
                id: well.casing_id,
                driftIn: casingDrift,
                onOd: (od, first) =>
                  setWell({
                    casing_od: od,
                    casing_weight: first?.weight_lbft ?? well.casing_weight,
                    casing_id: first?.id_in ?? well.casing_id,
                  }),
                onWeight: (row) => setWell({ casing_weight: row.weight_lbft, casing_id: row.id_in }),
                onId: (v) => setWell({ casing_id: Number.isFinite(v) ? v : well.casing_id }),
              })}
              {tubularBlock({
                title: "Tubing (Tenaris API 5CT)",
                rows: tubulars.tubing,
                od: well.tubing_od,
                weight: tubingWeight,
                id: well.tubing_id,
                driftIn: tubingDrift,
                onOd: (od, first) =>
                  setWell({ tubing_od: od, tubing_id: first?.id_in ?? well.tubing_id }),
                onWeight: (row) => setWell({ tubing_id: row.id_in }),
                onId: (v) => setWell({ tubing_id: Number.isFinite(v) ? v : well.tubing_id }),
                onlyOds:
                  objectives.pressure_loss_method === "poettmann_carpenter"
                    ? PC_TUBING_OD
                    : undefined,
              })}
              <Divider my="xs" />
            </>
          ) : (
            numGrid("well", WELL_TUBULARS_FALLBACK)
          )}
          {numGrid("well", WELL_BOTTOM)}
        </Accordion.Panel>
      </Accordion.Item>

      <Accordion.Item value="surface">
        <Accordion.Control>4 · Superficie</Accordion.Control>
        <Accordion.Panel>
          {numGrid("surface", SURFACE_NUM)}
          {/* La red es 50 o 60 Hz y nada más: el dominio rechaza cualquier
              otro valor. Un caso cargado con, por ejemplo, 51 Hz —que es una
              frecuencia de VARIADOR, no de red— tiene que verse acá y no
              descubrirse recién en el 422, así que el valor fuera de lista se
              muestra como opción propia y el campo queda en error. */}
          <Select
            mt="xs"
            label="Frecuencia de red"
            description="La de la línea. Para operar a otra frecuencia, usar el variador en Objetivos."
            data={[
              { value: "60", label: "60 Hz" },
              { value: "50", label: "50 Hz" },
              ...(surface.frequency === 50 || surface.frequency === 60
                ? []
                : [
                    {
                      value: String(surface.frequency),
                      label: `${surface.frequency} Hz (no válida)`,
                    },
                  ]),
            ]}
            value={String(surface.frequency)}
            error={
              surface.frequency === 50 || surface.frequency === 60
                ? undefined
                : `La frecuencia de red sólo puede ser 50 o 60 Hz. ${surface.frequency} Hz parece una frecuencia de operación: cargala en "Frecuencia de diseño" (Objetivos) con el variador activado.`
            }
            onChange={(v) => v && setRaw("surface", "frequency", parseFloat(v))}
            allowDeselect={false}
            w={260}
          />
        </Accordion.Panel>
      </Accordion.Item>

      <Accordion.Item value="objectives">
        <Accordion.Control>5 · Objetivos</Accordion.Control>
        <Accordion.Panel>
          {numGrid("objectives", OBJECTIVES_NUM)}
          <Switch
            mt="sm"
            label="Permite venteo de gas"
            checked={objectives.allow_gas_venting}
            onChange={(e) => setRaw("objectives", "allow_gas_venting", e.currentTarget.checked)}
          />
          {/* La correlación de pérdida de carga. Vacío = la decide la fracción
              de gas libre en la admisión, que es lo que hacía el programa
              antes de que esto se pudiera elegir. El umbral de gas sigue sin
              exponerse: se elige el método, no el corte. */}
          <Select
            mt="sm"
            label="Cálculo de pérdidas de carga en tubería"
            description={
              objectives.pressure_loss_method === "poettmann_carpenter"
                ? "Aplicable a tubing de 2, 2½ y 3 pulg · μo < 5 cp · RGL < 1500 scf/bbl · q > 400 bbl/d"
                : "Vacío: la elige la fracción de gas libre en la admisión"
            }
            data={PRESSURE_LOSS_OPTIONS}
            value={objectives.pressure_loss_method ?? null}
            placeholder="Automático (según gas libre)"
            clearable
            onChange={(v) =>
              setRaw("objectives", "pressure_loss_method", v as PressureLossMethod | null)
            }
          />
          <Switch
            mt="xs"
            label="Usar variador (VSD)"
            checked={objectives.use_vsd}
            onChange={(e) => setRaw("objectives", "use_vsd", e.currentTarget.checked)}
          />
          {/* Sin variador la bomba gira a la frecuencia de línea: el campo sólo
              tiene sentido con VSD, y el backend lo rechaza si no lo hay. */}
          {objectives.use_vsd && (
            <NumberInput
              mt="sm"
              label="Frecuencia de diseño"
              description="Hz — vacío usa la frecuencia de red"
              value={objectives.design_frequency_hz ?? ""}
              min={20}
              max={90}
              step={1}
              decimalScale={1}
              onChange={(v) =>
                setRaw("objectives", "design_frequency_hz", toNumOrNull(v))
              }
              hideControls
            />
          )}
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}
