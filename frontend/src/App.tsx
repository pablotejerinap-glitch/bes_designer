// Layout de dos paneles estilo pengtools: toolbar arriba, entradas a la
// izquierda (secciones colapsables + botón Calcular fijo al pie) y la zona de
// gráficos/resultados a la derecha con sub-tabs. Bajo ~1000px colapsa a una
// columna (ver styles.css).
import { useEffect, useState } from "react";
import {
  ActionIcon,
  Alert,
  Button,
  Card,
  Checkbox,
  Divider,
  Group,
  Loader,
  Menu,
  Select,
  Stack,
  Tabs,
  Text,
  TextInput,
  Title,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { api, ApiError, downloadBlob } from "./api/client";
import { EXAMPLE_CASES, EXAMPLE_ORDER } from "./exampleCases";
import type { DesignInputs, DesignResponse, PumpSummary } from "./api/types";
import { WellForm } from "./components/WellForm";
import { ResultsView } from "./components/ResultsView";
import { IprPanel } from "./components/IprPanel";
import { FormulaCatalogView } from "./components/FormulaCatalogView";
import { PumpLibrary } from "./components/PumpLibrary";
import { AffinityPanel } from "./components/AffinityPanel";
import { GasIncrementView } from "./components/GasIncrementView";
import { IconDownload, IconFolderOpen, IconMoon, IconSave, IconSun } from "./components/icons";

type Health = "checking" | "ok" | "error";

const HEALTH_LABEL: Record<Health, string> = {
  checking: "Verificando backend…",
  ok: "Backend conectado",
  error: "Backend sin conexión",
};

// Guardar/cargar casos: persistencia local del navegador (localStorage).
// El backend tiene case_bundle.py para persistencia real cuando llegue la DB.
const CASES_KEY = "bes_designer_cases";
type SavedCases = Record<string, DesignInputs>;

// El punto de burbuja es una sola magnitud física, pero el modelo lo guarda en
// dos campos (Reservoir.bubble_point para IPR/nodal, Fluid.bubble_point_pressure
// para PVT). El formulario pide uno solo ("Presión de burbuja"); acá forzamos
// que el de fluido lo iguale, así IPR y PVT nunca quedan inconsistentes.
function syncPb(di: DesignInputs): DesignInputs {
  if (di.fluid.bubble_point_pressure === di.reservoir.bubble_point) return di;
  return { ...di, fluid: { ...di.fluid, bubble_point_pressure: di.reservoir.bubble_point } };
}

// Punto de partida del formulario. NO es un caso de ejemplo: son los valores
// que no se pueden dejar vacíos sin romper la validación del dominio (geometría
// de casing y tubing, temperaturas, frecuencia de red). Todo lo que define al
// pozo —presiones, ensayo, fluido, caudal objetivo— arranca en cero y lo carga
// el usuario. Los ejemplos precargados viven aparte (exampleCases.ts) y se
// ofrecen desde "Abrir": el formulario sigue arrancando en blanco.
const BLANK_INPUTS: DesignInputs = {
  reservoir: {
    static_pressure: 0,
    bubble_point: 0,
    test_pwf: 0,
    test_rate: 0,
    ipr_method: "vogel",
    reservoir_temp: 0,
    drive_mechanism: "solution_gas",
    fetkovich_n: null,
  },
  fluid: {
    oil_api: 0,
    water_cut: 0,
    gor: 0,
    gas_sg: 0.65,
    water_sg: 1.05,
    // Vacío por defecto: sin ensayo el backend lee la Fig. 4L(2). Un 0 acá
    // era un dato falso que además hacía rebotar el diseño con 422.
    oil_viscosity_dead: null,
    viscosity_temp_ref: null,
    bubble_point_pressure: 0,
    h2s_content: 0,
    co2_content: 0,
    sand_production: false,
  },
  well: {
    total_depth: 0,
    casing_od: 5.5,
    casing_weight: 17,
    casing_id: 4.892,
    tubing_od: 2.875,
    tubing_id: 2.441,
    perforations_top: 0,
    perforations_bottom: 0,
    deviation_max: 0,
    wellhead_temp: 100,
  },
  surface: {
    wellhead_pressure_required: 0,
    flowline_length: 0,
    flowline_id: 3,
    flowline_elevation_change: 0,
    separator_pressure: 0,
    power_supply_voltage: 480,
    frequency: 50,
  },
  objectives: {
    target_flow_rate: 0,
    safety_margin_depth: 0,
    allow_gas_venting: true,
    max_gip: 0.1,
    design_life_years: 5,
    use_vsd: false,
    design_frequency_hz: null,
  },
};

// Sólo los casos del usuario. Los ejemplos NO se mezclan acá: viven en
// EXAMPLE_CASES y el menú los muestra en su propia sección, así queda claro
// cuáles son datos de referencia y cuáles guardó el usuario.
function readCases(): SavedCases {
  try {
    const raw = localStorage.getItem(CASES_KEY);
    return raw ? (JSON.parse(raw) as SavedCases) : {};
  } catch {
    return {};
  }
}

export function App() {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme("light");

  const [health, setHealth] = useState<Health>("checking");
  const [catalogPumps, setCatalogPumps] = useState<PumpSummary[]>([]);
  const [inputs, setInputs] = useState<DesignInputs | null>(syncPb(BLANK_INPUTS));
  const [calculating, setCalculating] = useState(false);
  const [manualPumpModel, setManualPumpModel] = useState<string | null>(null);
  const [manualCalculating, setManualCalculating] = useState(false);
  const [tab, setTab] = useState<string | null>("design");
  // Detección automática de gas. Por defecto ACTIVADA: si el pozo tiene gas
  // libre por encima del umbral, el método convencional subestima las etapas,
  // así que lo correcto es llevar al usuario al camino que corresponde en vez
  // de dejarlo leyendo un resultado que no aplica. Se puede apagar para
  // comparar las dos rutas a mano, que es un resultado del trabajo.
  const [autoDetectarGas, setAutoDetectarGas] = useState(true);
  // Token que dispara el diseño por incrementos en la pestaña de gas. Se
  // incrementa en vez de ser un booleano: dos corridas seguidas del mismo pozo
  // tienen que disparar dos veces.
  const [gasAutoRun, setGasAutoRun] = useState(0);
  // El motivo por el que no se pudo diseñar, para mostrarlo EN la pestaña.
  // Antes vivía sólo en una notificación que se va sola a los pocos segundos:
  // el usuario quedaba con la pantalla vacía y sin manera de releer por qué.
  const [designError, setDesignError] = useState<string | null>(null);
  const [caseName, setCaseName] = useState("");
  const [savedCases, setSavedCases] = useState<SavedCases>(readCases);
  const [exporting, setExporting] = useState<"pdf" | "xlsx" | null>(null);

  // Los resultados guardan el snapshot de inputs que los produjo: si el usuario
  // sigue editando el form, los gráficos y el reporte tienen que seguir
  // correspondiendo al diseño que está en pantalla.
  const [result, setResult] = useState<{
    response: DesignResponse;
    inputs: DesignInputs;
  } | null>(null);
  const [manualResult, setManualResult] = useState<{
    response: DesignResponse;
    inputs: DesignInputs;
  } | null>(null);

  useEffect(() => {
    (async () => {
      try {
        await api.health();
        setHealth("ok");
        const cat = await api.catalogs();
        setCatalogPumps(cat.pumps);
      } catch (e) {
        setHealth("error");
        notifications.show({
          color: "red",
          title: "Backend no disponible",
          message: e instanceof ApiError ? e.message : String(e),
        });
      }
    })();
  }, []);

  async function calculate() {
    if (!inputs) return;
    setCalculating(true);
    setResult(null);
    setDesignError(null);
    const snapshot = structuredClone(inputs);
    try {
      const res = await api.design({ ...snapshot, n: 3 });
      setResult({ response: res, inputs: snapshot });

      // El backend ya respondió si este pozo pedía el método por incrementos
      // (misma fracción de gas libre que usó para diseñar, no una segunda
      // cuenta). El resultado convencional NO se descarta: queda en su pestaña
      // para poder comparar las dos rutas al TDH.
      const conGas = res.gas_method?.applies === true;
      if (conGas && autoDetectarGas) {
        setTab("gas");
        setGasAutoRun((k) => k + 1);
        notifications.show({
          color: "orange",
          title: "Pozo con gas libre",
          message: `Gas libre en la admisión ${(
            (res.gas_method?.free_gas_fraction ?? 0) * 100
          ).toFixed(1)} %: se pasa al método de incrementos. El diseño convencional queda en la pestaña "Diseño".`,
        });
      } else {
        setTab("design");
        notifications.show({
          color: conGas ? "orange" : "teal",
          message: conGas
            ? `Diseño listo, pero el pozo tiene gas libre: el método de incrementos es el que corresponde.`
            : `Diseño listo: ${res.recommendations.length} opción(es) de ${res.n_candidates_evaluated} candidatos.`,
        });
      }
    } catch (e) {
      const motivo = e instanceof ApiError ? e.message : String(e);
      setDesignError(motivo);
      setTab("design");
      notifications.show({
        color: "red",
        title: "No se pudo calcular",
        message: "El motivo queda en la pestaña Diseño.",
      });
    } finally {
      setCalculating(false);
    }
  }

  async function calculateManual() {
    if (!inputs || !manualPumpModel) return;
    setManualCalculating(true);
    setManualResult(null);
    const snapshot = structuredClone(inputs);
    try {
      const res = await api.design({ ...snapshot, n: 1, pump_model: manualPumpModel });
      setManualResult({ response: res, inputs: snapshot });
      setTab("design");
      notifications.show({ color: "teal", message: `Diseño calculado para ${manualPumpModel}.` });
    } catch (e) {
      notifications.show({
        color: "red",
        title: "No se pudo calcular con esta bomba",
        message: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setManualCalculating(false);
    }
  }

  // Export rápido desde la toolbar: la Opción 1 del último diseño automático.
  // Cada recomendación conserva sus propios botones de descarga en la vista.
  async function exportReport(fmt: "pdf" | "xlsx") {
    if (!result) return;
    setExporting(fmt);
    try {
      const blob = await api.report(fmt, { ...result.inputs, n: 3, rank: 0 });
      const stem = caseName.trim() ? caseName.trim().replace(/\s+/g, "_") : "diseno_bes";
      downloadBlob(blob, `${stem}_opcion1.${fmt}`);
    } catch (e) {
      notifications.show({
        color: "red",
        title: "No se pudo exportar el reporte",
        message: e instanceof ApiError ? e.message : String(e),
      });
    } finally {
      setExporting(null);
    }
  }

  function saveCase() {
    const name = caseName.trim();
    if (!name || !inputs) {
      notifications.show({ color: "red", message: "Poné un nombre de caso antes de guardar." });
      return;
    }
    const next = { ...savedCases, [name]: structuredClone(inputs) };
    setSavedCases(next);
    localStorage.setItem(CASES_KEY, JSON.stringify(next));
    notifications.show({ color: "teal", message: `Caso "${name}" guardado en este navegador.` });
  }

  // El caso guardado gana sobre el ejemplo del mismo nombre: lo que el usuario
  // guardó nunca lo pisa un dato de referencia.
  function openCase(name: string) {
    const saved = savedCases[name] ?? EXAMPLE_CASES[name];
    if (!saved) return;
    // Casos guardados antes de que la entregabilidad se cargara como ensayo:
    // traen el índice de productividad ya procesado y no el punto medido. No se
    // reconstruye acá (sería lógica de negocio en el front) — se avisa para que
    // el usuario cargue la Pwf y el caudal del ensayo.
    const r = saved.reservoir as Partial<typeof saved.reservoir>;
    if (r.test_pwf == null || r.test_rate == null) {
      notifications.show({
        color: "yellow",
        message: `El caso "${name}" es anterior al ingreso por ensayo: completá la Pwf y el caudal medidos en Reservorio.`,
      });
    }
    setInputs(syncPb(structuredClone(saved)));
    setCaseName(name);
    setResult(null);
    setManualResult(null);
    setManualPumpModel(null);
  }

  // Solo bombas cuyo OD entra en el casing actual — mismo criterio que el
  // backend (get_pumps_by_casing), para no ofrecer opciones condenadas a 422.
  const pumpOptions = (
    inputs ? catalogPumps.filter((p) => p.od < inputs.well.casing_id) : catalogPumps
  ).map((p) => ({
    value: p.model,
    label: `${p.model} (${p.manufacturer}, serie ${p.series}) — BEP ${Math.round(p.bep_flow)} bpd`,
  }));

  const caseNames = Object.keys(savedCases).sort();
  // Un ejemplo cuyo nombre el usuario ya reutilizó para guardar lo suyo sale de
  // la lista de ejemplos: aparece una sola vez, en "Casos guardados".
  const ejemplosVisibles = EXAMPLE_ORDER.filter((name) => !(name in savedCases));

  return (
    <div className="app-root">
      <header className="app-toolbar">
        <Title order={1} size="h2" style={{ whiteSpace: "nowrap" }}>
          BES Designer
        </Title>
        <Text size="xs" c="dimmed" visibleFrom="lg" style={{ whiteSpace: "nowrap" }}>
          Autor: Pablo Agustín Tejerina ING-9659
        </Text>

        <Divider orientation="vertical" />

        <TextInput
          placeholder="Nombre del caso"
          value={caseName}
          onChange={(e) => setCaseName(e.currentTarget.value)}
          w={190}
          aria-label="Nombre del caso"
        />
        <Button variant="default" leftSection={<IconSave />} onClick={saveCase} disabled={!inputs}>
          Guardar
        </Button>
        <Menu position="bottom-start" withinPortal>
          <Menu.Target>
            <Button variant="default" leftSection={<IconFolderOpen />}>
              Abrir
            </Button>
          </Menu.Target>
          <Menu.Dropdown mah="70vh" style={{ overflowY: "auto" }}>
            <Menu.Label>Ejemplos precargados</Menu.Label>
            {ejemplosVisibles.map((name) => (
              <Menu.Item key={name} onClick={() => openCase(name)}>
                {name}
              </Menu.Item>
            ))}
            {caseNames.length > 0 && (
              <>
                <Menu.Divider />
                <Menu.Label>Casos guardados</Menu.Label>
                {caseNames.map((name) => (
                  <Menu.Item key={name} onClick={() => openCase(name)}>
                    {name}
                  </Menu.Item>
                ))}
              </>
            )}
          </Menu.Dropdown>
        </Menu>

        <div style={{ flex: 1 }} />

        <Button
          variant="default"
          leftSection={<IconDownload />}
          onClick={() => exportReport("xlsx")}
          loading={exporting === "xlsx"}
          disabled={!result}
          title="Exporta la Opción 1 del último diseño"
        >
          Excel
        </Button>
        <Button
          variant="default"
          leftSection={<IconDownload />}
          onClick={() => exportReport("pdf")}
          loading={exporting === "pdf"}
          disabled={!result}
          title="Exporta la Opción 1 del último diseño"
        >
          PDF
        </Button>

        <ActionIcon
          variant="default"
          size="lg"
          onClick={() => setColorScheme(scheme === "light" ? "dark" : "light")}
          aria-label="Cambiar tema claro/oscuro"
        >
          {scheme === "light" ? <IconMoon /> : <IconSun />}
        </ActionIcon>

        <Group gap={6} wrap="nowrap">
          <span
            className={`status-dot status-dot--${
              health === "ok" ? "ok" : health === "error" ? "error" : "checking"
            }`}
          />
          <Text size="xs" c="dimmed" style={{ whiteSpace: "nowrap" }}>
            {HEALTH_LABEL[health]}
          </Text>
        </Group>
      </header>

      <div className="app-main">
        <aside className="app-inputs">
          <div className="app-inputs-scroll">

            {inputs ? (
              <WellForm value={inputs} onChange={(v) => setInputs(syncPb(v))} />
            ) : (
              <Group py="lg" justify="center">
                <Loader size="sm" />
                <Text c="dimmed" size="sm">
                  Cargando…
                </Text>
              </Group>
            )}

            <Divider my="md" label="Bomba manual (opcional)" labelPosition="left" />
            <Select
              placeholder="Forzar un modelo del catálogo…"
              description="Aparte de la recomendación automática"
              data={pumpOptions}
              value={manualPumpModel}
              onChange={setManualPumpModel}
              disabled={catalogPumps.length === 0}
              searchable
              clearable
            />
            <Button
              fullWidth
              mt="xs"
              variant="light"
              onClick={calculateManual}
              loading={manualCalculating}
              disabled={!inputs || !manualPumpModel || health !== "ok"}
            >
              Calcular con esta bomba
            </Button>
          </div>

          <div className="app-inputs-footer">
            <Button
              fullWidth
              size="md"
              onClick={calculate}
              loading={calculating}
              disabled={!inputs || health !== "ok"}
            >
              Calcular diseño BES
            </Button>
            {/*
              Va acá, pegado al botón, porque describe qué pasa al apretarlo.
              El umbral con que se decide NO se expone: es el corte con que el
              programa elige solo (.claude/rules/domain.md). Lo que se elige es
              si la app actúa sobre esa detección o sólo la informa.
            */}
            <Checkbox
              mt="sm"
              size="sm"
              label="Detectar gas automáticamente"
              description="Con gas libre por encima del umbral, pasa sola al método de incrementos. El diseño convencional queda igual en su pestaña."
              checked={autoDetectarGas}
              onChange={(e) => setAutoDetectarGas(e.currentTarget.checked)}
            />
          </div>
        </aside>

        <section className="app-results">
          <Tabs value={tab} onChange={setTab}>
            <Tabs.List mb="md">
              <Tabs.Tab value="design">Diseño</Tabs.Tab>
              <Tabs.Tab value="ipr">Curva IPR</Tabs.Tab>
              <Tabs.Tab value="gas">Pozo con gas</Tabs.Tab>
              <Tabs.Tab value="affinity">Leyes de afinidad</Tabs.Tab>
              <Tabs.Tab value="library">Biblioteca ESP</Tabs.Tab>
              <Tabs.Tab value="formulas">Fórmulas</Tabs.Tab>
            </Tabs.List>

            <Tabs.Panel value="design">
              <Stack gap="md">
                {designError && (
                  <Alert color="red" variant="light" title="No se pudo armar ningún aparejo">
                    <Text size="sm">{designError}</Text>
                    <Text size="sm" mt="xs" c="dimmed">
                      El diseño hidráulico puede haber salido bien y aun así no
                      haber aparejo: bomba, motor y sello tienen que ser del
                      mismo proveedor, y el motor tiene que dejar luz para el
                      cable dentro del casing.
                    </Text>
                    <Button
                      size="xs"
                      mt="sm"
                      variant="light"
                      color="orange"
                      onClick={() => {
                        setTab("gas");
                        setGasAutoRun((k) => k + 1);
                      }}
                    >
                      Probar el método de incrementos
                    </Button>
                  </Alert>
                )}
                {!result && !manualResult && !designError && (
                  <Card>
                    <Title order={3}>Sin diseño calculado</Title>
                    <Text c="dimmed" size="sm" mt={4}>
                      Cargá los datos del pozo en el panel izquierdo y presioná "Calcular diseño BES". Las recomendaciones, la curva
                      de la bomba y el análisis nodal aparecen acá.
                    </Text>
                  </Card>
                )}
                {result && (
                  <ResultsView
                    response={result.response}
                    inputs={result.inputs}
                    onGoToGas={() => {
                      setTab("gas");
                      setGasAutoRun((k) => k + 1);
                    }}
                  />
                )}
                {manualResult && (
                  <ResultsView
                    response={manualResult.response}
                    inputs={manualResult.inputs}
                    title="Bomba seleccionada manualmente"
                    manual
                  />
                )}
              </Stack>
            </Tabs.Panel>

            <Tabs.Panel value="ipr">
              <IprPanel reservoir={inputs?.reservoir ?? null} active={tab === "ipr"} />
            </Tabs.Panel>

            <Tabs.Panel value="gas">
              <GasIncrementView
                inputs={inputs}
                autoRunToken={gasAutoRun}
                fixedPumpModel={manualPumpModel}
              />
            </Tabs.Panel>

            <Tabs.Panel value="affinity">
              <AffinityPanel
                pumps={catalogPumps}
                active={tab === "affinity"}
                defaultFlow={inputs?.objectives.target_flow_rate ?? null}
              />
            </Tabs.Panel>

            <Tabs.Panel value="library">
              <PumpLibrary pumps={catalogPumps} casingId={inputs?.well.casing_id ?? null} />
            </Tabs.Panel>

            {/*
              Las fórmulas del motor, para revisarlas con un profesional. No
              depende de que haya un diseño calculado: el catálogo se lista
              solo. Si lo hay, se le pasa la traza para marcar cuáles corrieron.
            */}
            <Tabs.Panel value="formulas">
              <FormulaCatalogView
                active={tab === "formulas"}
                formulas={result?.response.recommendations?.[0]?.design?.formulas}
              />
            </Tabs.Panel>
          </Tabs>
        </section>
      </div>
    </div>
  );
}
