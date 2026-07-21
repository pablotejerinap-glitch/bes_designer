import {
  Accordion,
  Grid,
  NumberInput,
  Select,
  Switch,
  TextInput,
} from "@mantine/core";
import type {
  DesignInputs,
  DriveMechanism,
  FluidInput,
  IPRMethod,
  ObjectivesInput,
  ReservoirInput,
  SurfaceInput,
  WellInput,
} from "../api/types";

type Section = keyof DesignInputs;

interface NumField {
  key: string;
  label: string;
  unit?: string;
  step?: number;
}

const RESERVOIR_NUM: NumField[] = [
  { key: "static_pressure", label: "Presión estática", unit: "psia" },
  { key: "bubble_point", label: "Presión de burbuja", unit: "psia" },
  { key: "productivity_index", label: "Índice de productividad", unit: "STB/d/psi", step: 0.1 },
  { key: "reservoir_temp", label: "Temperatura de reservorio", unit: "°F" },
  { key: "datum_depth", label: "Profundidad de referencia", unit: "ft TVD" },
];

const FLUID_NUM: NumField[] = [
  { key: "oil_api", label: "Gravedad API", unit: "°API", step: 0.1 },
  { key: "water_cut", label: "Corte de agua", unit: "frac 0-1", step: 0.01 },
  { key: "gor", label: "GOR", unit: "scf/STB" },
  { key: "gas_sg", label: "SG del gas", unit: "aire=1", step: 0.01 },
  { key: "water_sg", label: "SG de la salmuera", step: 0.01 },
  { key: "oil_viscosity_dead", label: "Viscosidad dead-oil", unit: "cp", step: 0.1 },
  { key: "viscosity_temp_ref", label: "Temp. ref. viscosidad", unit: "°F" },
  { key: "bubble_point_pressure", label: "Pb del fluido", unit: "psia" },
  { key: "h2s_content", label: "H2S", unit: "ppm" },
  { key: "co2_content", label: "CO2", unit: "ppm" },
];

const WELL_NUM: NumField[] = [
  { key: "total_depth", label: "Profundidad total", unit: "ft MD" },
  { key: "casing_od", label: "OD casing", unit: "in", step: 0.001 },
  { key: "casing_weight", label: "Peso casing", unit: "lb/ft", step: 0.1 },
  { key: "casing_id", label: "ID casing", unit: "in", step: 0.001 },
  { key: "tubing_od", label: "OD tubing", unit: "in", step: 0.001 },
  { key: "tubing_id", label: "ID tubing", unit: "in", step: 0.001 },
  { key: "perforations_top", label: "Tope perforaciones", unit: "ft MD" },
  { key: "perforations_bottom", label: "Base perforaciones", unit: "ft MD" },
  { key: "deviation_max", label: "Desviación máxima", unit: "°", step: 0.5 },
  { key: "wellhead_temp", label: "Temp. boca de pozo", unit: "°F" },
  { key: "bottom_hole_temp", label: "Temp. de fondo", unit: "°F" },
];

const SURFACE_NUM: NumField[] = [
  { key: "wellhead_pressure_required", label: "Presión requerida en cabeza", unit: "psi" },
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
  { value: "combined", label: "Combined" },
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

  function numGrid<S extends Section>(section: S, fields: NumField[]) {
    const obj = value[section] as unknown as Record<string, number>;
    return (
      <Grid>
        {fields.map((f) => (
          <Grid.Col span={{ base: 12, sm: 6, md: 4 }} key={f.key}>
            <NumberInput
              label={f.label}
              description={f.unit}
              value={obj[f.key]}
              step={f.step ?? 1}
              onChange={(v) => setNum(section, f.key, v)}
              hideControls
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
  // well used only via numGrid; kept typed for clarity
  void (value.well as WellInput);

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
        <Accordion.Panel>{numGrid("well", WELL_NUM)}</Accordion.Panel>
      </Accordion.Item>

      <Accordion.Item value="surface">
        <Accordion.Control>4 · Superficie</Accordion.Control>
        <Accordion.Panel>
          {numGrid("surface", SURFACE_NUM)}
          <Select
            mt="xs"
            label="Frecuencia de red"
            data={[
              { value: "60", label: "60 Hz" },
              { value: "50", label: "50 Hz" },
            ]}
            value={String(surface.frequency)}
            onChange={(v) => v && setRaw("surface", "frequency", parseFloat(v))}
            allowDeselect={false}
            w={160}
          />
        </Accordion.Panel>
      </Accordion.Item>

      <Accordion.Item value="objectives">
        <Accordion.Control>5 · Objetivos</Accordion.Control>
        <Accordion.Panel>
          {numGrid("objectives", OBJECTIVES_NUM)}
          <Grid mt="xs">
            <Grid.Col span={{ base: 12, sm: 6 }}>
              <TextInput
                label="Fabricante preferido"
                placeholder="(vacío = sin preferencia)"
                value={objectives.preferred_manufacturer}
                onChange={(e) =>
                  setRaw("objectives", "preferred_manufacturer", e.currentTarget.value)
                }
              />
            </Grid.Col>
          </Grid>
          <Switch
            mt="sm"
            label="Permite venteo de gas"
            checked={objectives.allow_gas_venting}
            onChange={(e) => setRaw("objectives", "allow_gas_venting", e.currentTarget.checked)}
          />
          <Switch
            mt="xs"
            label="Usar variador (VSD)"
            checked={objectives.use_vsd}
            onChange={(e) => setRaw("objectives", "use_vsd", e.currentTarget.checked)}
          />
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}
