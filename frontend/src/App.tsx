import { useEffect, useState } from "react";
import {
  AppShell,
  Badge,
  Card,
  Container,
  Group,
  Loader,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { api, ApiError } from "./api/client";
import type { CatalogSummary } from "./api/types";

type Health = "checking" | "ok" | "error";

export function App() {
  const [health, setHealth] = useState<Health>("checking");
  const [catalog, setCatalog] = useState<CatalogSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        await api.health();
        setHealth("ok");
        setCatalog(await api.catalogs());
      } catch (e) {
        setHealth("error");
        setError(e instanceof ApiError ? e.message : String(e));
      }
    })();
  }, []);

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
            <Title order={2}>Diseño de Bombeo Electrosumergible</Title>
            <Text c="dimmed">
              Frontend React consumiendo la API FastAPI. Metodología Kermit Brown
              Vol. 2b Cap. 4.5.
            </Text>

            <Card withBorder radius="md" padding="lg">
              <Title order={4} mb="sm">
                Estado del backend
              </Title>
              {health === "checking" && (
                <Group>
                  <Loader size="sm" />
                  <Text>Conectando…</Text>
                </Group>
              )}
              {health === "error" && (
                <Text c="red">No se pudo conectar: {error}</Text>
              )}
              {health === "ok" && catalog && (
                <Stack gap="xs">
                  <Text>
                    Catálogo cargado: <b>{catalog.counts.pumps}</b> bombas ·{" "}
                    <b>{catalog.counts.seals}</b> sellos
                  </Text>
                  <Group gap="xs">
                    {catalog.manufacturers.map((m) => (
                      <Badge key={m} variant="outline">
                        {m}
                      </Badge>
                    ))}
                  </Group>
                </Stack>
              )}
            </Card>

            <Card withBorder radius="md" padding="lg">
              <Text c="dimmed" ta="center">
                🚧 Formulario del pozo y resultados — próximo paso (una vez Node
                esté instalado y el front corriendo).
              </Text>
            </Card>
          </Stack>
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}
