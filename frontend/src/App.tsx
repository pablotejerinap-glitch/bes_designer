import { useEffect, useState } from "react";
import {
  AppShell,
  Badge,
  Button,
  Card,
  Container,
  Group,
  Loader,
  Select,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { api, ApiError } from "./api/client";
import type { DesignInputs, DesignResponse, ExampleWell } from "./api/types";
import { WellForm } from "./components/WellForm";
import { ResultsView } from "./components/ResultsView";

type Health = "checking" | "ok" | "error";

export function App() {
  const [health, setHealth] = useState<Health>("checking");
  const [examples, setExamples] = useState<ExampleWell[]>([]);
  const [inputs, setInputs] = useState<DesignInputs | null>(null);
  const [calculating, setCalculating] = useState(false);
  // Los resultados guardan el snapshot de inputs que los produjo: si el usuario
  // sigue editando el form, los gráficos y el reporte tienen que seguir
  // correspondiendo al diseño que está en pantalla.
  const [result, setResult] = useState<{
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
        if (ex.length > 0) setInputs(structuredClone(ex[0].inputs));
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
      setInputs(structuredClone(ex.inputs));
      setResult(null);
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

  return (
    <AppShell header={{ height: 60 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Title order={3}>🛢️ BES Designer</Title>
          <Badge
            color={health === "ok" ? "teal" : health === "error" ? "red" : "gray"}
            variant="light"
          >
            backend: {health}
          </Badge>
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        <Container size="lg">
          <Stack>
            <div>
              <Title order={2}>Diseño de Bombeo Electrosumergible</Title>
              <Text c="dimmed">Metodología Kermit Brown Vol. 2b Cap. 4.5.</Text>
            </div>

            <Card withBorder radius="md" padding="lg">
              <Group justify="space-between" align="flex-end" mb="md">
                <Select
                  label="Cargar ejemplo del libro"
                  placeholder="Elegí un ejemplo…"
                  data={examples.map((e) => ({ value: e.key, label: e.label }))}
                  onChange={loadExample}
                  disabled={examples.length === 0}
                  w={420}
                  searchable
                />
                <Button
                  onClick={calculate}
                  loading={calculating}
                  disabled={!inputs || health !== "ok"}
                  size="md"
                >
                  🚀 Calcular Diseño BES
                </Button>
              </Group>

              {inputs ? (
                <WellForm value={inputs} onChange={setInputs} />
              ) : (
                <Group>
                  <Loader size="sm" />
                  <Text>Cargando…</Text>
                </Group>
              )}
            </Card>

            {result && (
              <ResultsView response={result.response} inputs={result.inputs} />
            )}
          </Stack>
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}
