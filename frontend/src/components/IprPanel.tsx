// Curva IPR en vivo: al editar el reservorio se vuelve a pedir la figura al
// backend (POST /api/plots/ipr-curve) con un debounce de ~400 ms.
// El cálculo vive íntegro en bes.core/bes.plotting; acá sólo se renderiza.
import { lazy, Suspense, useEffect, useState } from "react";
import { Alert, Card, Group, Loader, Text, Title } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { api, ApiError } from "../api/client";
import type { PlotlyFigure, ReservoirInput } from "../api/types";

const PlotFigure = lazy(() =>
  import("./PlotFigure").then((m) => ({ default: m.PlotFigure }))
);

const METHOD_LABELS: Record<string, string> = {
  linear: "Linear (Darcy)",
  vogel: "Vogel",
  fetkovich: "Fetkovich",
};

export function IprPanel({
  reservoir,
  active,
}: {
  reservoir: ReservoirInput | null;
  active: boolean;
}) {
  // El debounce evita pedir una curva por cada tecla en el formulario.
  const [debounced] = useDebouncedValue(reservoir, 400);
  const [figure, setFigure] = useState<PlotlyFigure | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!active || !debounced) return;
    // Fetkovich sin n daría 422 seguro: mejor avisar sin pegarle a la API.
    // (C no se carga: se despeja del ensayo, pero necesita el n.)
    if (debounced.ipr_method === "fetkovich" && debounced.fetkovich_n == null) {
      setError("El método Fetkovich requiere el exponente n (sección Reservorio).");
      return;
    }
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .iprCurve(debounced)
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
  }, [debounced, active]);

  if (!reservoir) {
    return (
      <Alert color="blue" variant="light">
        Cargá los datos del pozo primero.
      </Alert>
    );
  }

  return (
    <Card>
      <Group justify="space-between" align="baseline">
        <div>
          <Title order={3}>Curva IPR</Title>
          <Text size="sm" c="dimmed">
            Método {METHOD_LABELS[reservoir.ipr_method] ?? reservoir.ipr_method} — se
            actualiza en vivo al editar el reservorio.
          </Text>
        </div>
        {loading && <Loader size="xs" />}
      </Group>

      {error && (
        <Alert color="red" variant="light" mt="sm" title="No se pudo calcular la curva">
          {error}
        </Alert>
      )}

      {figure ? (
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
      ) : (
        !error && (
          <Group py="xl" justify="center">
            <Loader size="sm" />
            <Text c="dimmed" size="sm">
              Calculando curva IPR…
            </Text>
          </Group>
        )
      )}
    </Card>
  );
}
