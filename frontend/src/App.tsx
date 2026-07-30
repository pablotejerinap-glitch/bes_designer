// Layout de dos paneles estilo pengtools: toolbar arriba, entradas a la
// izquierda (secciones colapsables + botón Calcular fijo al pie) y la zona de
// gráficos/resultados a la derecha con sub-tabs. Bajo ~1000px colapsa a una
// columna (ver styles.css).
import { useEffect, useState } from "react";
import {
  ActionIcon,
  Button,
  Card,
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
import type { DesignInputs, DesignResponse, ExampleWell, PumpSummary } from "./api/types";
import { WellForm } from "./components/WellForm";
import { ResultsView } from "./components/ResultsView";
import { SensitivityView } from "./components/SensitivityView";
import { IprPanel } from "./components/IprPanel";
import { PumpLibrary } from "./components/PumpLibrary";
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
  const [examples, setExamples] = useState<ExampleWell[]>([]);
  const [catalogPumps, setCatalogPumps] = useState<PumpSummary[]>([]);
  const [inputs, setInputs] = useState<DesignInputs | null>(null);
  const [calculating, setCalculating] = useState(false);
  const [manualPumpModel, setManualPumpModel] = useState<string | null>(null);
  const [manualCalculating, setManualCalculating] = useState(false);
  const [tab, setTab] = useState<string | null>("design");
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
        const ex = await api.examples();
        setExamples(ex);
        if (ex.length > 0) setInputs(syncPb(structuredClone(ex[0].inputs)));
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

  function loadExample(key: string | null) {
    const ex = examples.find((e) => e.key === key);
    if (ex) {
      setInputs(syncPb(structuredClone(ex.inputs)));
      setResult(null);
      setManualResult(null);
      setManualPumpModel(null);
    }
  }

  async function calculate() {
    if (!inputs) return;
    setCalculating(true);
    setResult(null);
    const snapshot = structuredClone(inputs);
    try {
      const res = await api.design({ ...snapshot, n: 3 });
      setResult({ response: res, inputs: snapshot });
      setTab("design");
      notifications.show({
        color: "teal",
        message: `Diseño listo: ${res.recommendations.length} opción(es) de ${res.n_candidates_evaluated} candidatos.`,
      });
    } catch (e) {
      notifications.show({
        color: "red",
        title: "No se pudo calcular",
        message: e instanceof ApiError ? e.message : String(e),
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

  function openCase(name: string) {
    const saved = savedCases[name];
    if (!saved) return;
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
            <Button
              variant="default"
              leftSection={<IconFolderOpen />}
              disabled={caseNames.length === 0}
            >
              Abrir
            </Button>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Label>Casos guardados</Menu.Label>
            {caseNames.map((name) => (
              <Menu.Item key={name} onClick={() => openCase(name)}>
                {name}
              </Menu.Item>
            ))}
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
            <Select
              label="Casos ejemplos"
              placeholder="Elegí un ejemplo…"
              data={examples.map((e) => ({ value: e.key, label: e.label }))}
              onChange={loadExample}
              disabled={examples.length === 0}
              searchable
              mb="sm"
            />

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
          </div>
        </aside>

        <section className="app-results">
          <Tabs value={tab} onChange={setTab}>
            <Tabs.List mb="md">
              <Tabs.Tab value="design">Diseño</Tabs.Tab>
              <Tabs.Tab value="ipr">Curva IPR</Tabs.Tab>
              <Tabs.Tab value="sensitivity">Sensibilidad</Tabs.Tab>
              <Tabs.Tab value="library">Biblioteca ESP</Tabs.Tab>
            </Tabs.List>

            <Tabs.Panel value="design">
              <Stack gap="md">
                {!result && !manualResult && (
                  <Card>
                    <Title order={3}>Sin diseño calculado</Title>
                    <Text c="dimmed" size="sm" mt={4}>
                      Configurá las entradas en el panel izquierdo (o cargá un ejemplo del
                      libro) y presioná "Calcular diseño BES". Las recomendaciones, la curva
                      de la bomba y el análisis nodal aparecen acá.
                    </Text>
                  </Card>
                )}
                {result && <ResultsView response={result.response} inputs={result.inputs} />}
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

            <Tabs.Panel value="sensitivity">
              <SensitivityView inputs={inputs} />
            </Tabs.Panel>

            <Tabs.Panel value="library">
              <PumpLibrary pumps={catalogPumps} casingId={inputs?.well.casing_id ?? null} />
            </Tabs.Panel>
          </Tabs>
        </section>
      </div>
    </div>
  );
}
