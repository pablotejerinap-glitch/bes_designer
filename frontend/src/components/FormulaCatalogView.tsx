import { useEffect, useMemo, useState } from "react";
import {
  Alert, Badge, Card, Code, Group, Loader, Stack, Table, Text, TextInput, Title,
} from "@mantine/core";
import { api } from "../api/client";
import type { Formula, FormulaCatalog, FormulaSpec, FormulaTopic } from "../api/types";

/**
 * Todas las fórmulas del motor de cálculo, para revisarlas con un profesional.
 *
 * Se pide a `/api/formulas`, que las lista **sin correr ningún diseño**: la
 * traza de una corrida sólo muestra la rama que ese pozo ejecutó, así que para
 * revisar Fetkovich habría que armar un caso de Fetkovich. Acá están las cuatro
 * maneras de llegar a la Pwf y las dos correlaciones de fricción, todas juntas.
 *
 * Cuando hay un diseño calculado, las fórmulas que efectivamente se ejecutaron
 * se marcan y muestran los números de ese caso. Esos números los arma el mismo
 * código que hace la cuenta, de modo que no pueden contradecir a la fórmula.
 */
export function FormulaCatalogView({
  active,
  formulas,
}: {
  active: boolean;
  /** Traza del último diseño calculado, si hay uno. */
  formulas?: Formula[];
}) {
  const [catalog, setCatalog] = useState<FormulaCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    if (!active || catalog || error) return;
    api
      .formulas()
      .then(setCatalog)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [active, catalog, error]);

  /** Lo que se ejecutó en el caso actual, por clave. */
  const ejecutadas = useMemo(() => {
    const m = new Map<string, Formula>();
    for (const f of formulas ?? []) m.set(f.key, f);
    return m;
  }, [formulas]);

  const filtro = q.trim().toLowerCase();
  const coincide = (f: FormulaSpec) =>
    !filtro ||
    [f.label, f.expression, f.reference, f.key, ...Object.keys(f.symbols)]
      .join(" ")
      .toLowerCase()
      .includes(filtro);

  if (error) {
    return (
      <Alert color="red" title="No se pudo leer el catálogo de fórmulas">
        {error}
      </Alert>
    );
  }
  if (!catalog) {
    return (
      <Group gap="xs">
        <Loader size="sm" />
        <Text size="sm" c="dimmed">Cargando las fórmulas del motor…</Text>
      </Group>
    );
  }

  const visibles = catalog.topics
    .map((t) => ({ ...t, formulas: t.formulas.filter(coincide) }))
    .filter((t) => t.formulas.length > 0 || (!filtro && !t.instrumented));

  return (
    <Stack gap="md">
      <Card withBorder padding="sm">
        <Text size="sm">
          Las <b>{catalog.total} fórmulas</b> que ejecuta el motor de cálculo, con
          su glosario de símbolos y la cita del libro. Se listan desde el propio
          código, así que no pueden decir una cosa y el programa hacer otra.
        </Text>
        <Text size="xs" c="dimmed" mt={6}>
          Están todas las variantes, también las que un pozo concreto no ejecuta:
          las cuatro maneras de llegar a la Pwf y las dos correlaciones de
          fricción conviven acá aunque un diseño use una sola.
          {ejecutadas.size > 0 && (
            <> Las {ejecutadas.size} que corrieron en tu último diseño están
            marcadas y traen sus números.</>
          )}
        </Text>
      </Card>

      <TextInput
        placeholder="Buscar por fórmula, símbolo, referencia… (ej. Vogel, Pwf, §4.5324)"
        value={q}
        onChange={(e) => setQ(e.currentTarget.value)}
      />

      {visibles.length === 0 && (
        <Text c="dimmed" size="sm">Ninguna fórmula coincide con «{q}».</Text>
      )}

      {visibles.map((tema) => (
        <TopicSection key={tema.key} topic={tema} ejecutadas={ejecutadas} />
      ))}
    </Stack>
  );
}

function TopicSection({
  topic,
  ejecutadas,
}: {
  topic: FormulaTopic;
  ejecutadas: Map<string, Formula>;
}) {
  return (
    <Stack gap="xs">
      <Group gap="xs" align="baseline">
        <Title order={4}>{topic.label}</Title>
        {topic.instrumented ? (
          <Badge size="sm" variant="light">{topic.formulas.length}</Badge>
        ) : (
          <Badge size="sm" variant="light" color="gray">
            todavía sin instrumentar
          </Badge>
        )}
      </Group>
      <Text size="sm" c="dimmed">{topic.blurb}</Text>

      {!topic.instrumented && (
        <Text size="xs" c="dimmed" fs="italic">
          El motor hace estos cálculos, pero todavía no publican sus fórmulas:
          para revisarlos hay que leer el código. Es lo que falta completar.
        </Text>
      )}

      {topic.formulas.map((f) => (
        <FormulaCard key={f.key} spec={f} corrida={ejecutadas.get(f.key)} />
      ))}
    </Stack>
  );
}

function FormulaCard({
  spec,
  corrida,
}: {
  spec: FormulaSpec;
  /** La misma fórmula, ya ejecutada en el diseño actual. */
  corrida?: Formula;
}) {
  return (
    <Card withBorder radius="sm" padding="sm">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Group gap={6} align="baseline">
          <Text fw={600} size="sm">{spec.label}</Text>
          {corrida && (
            <Badge size="xs" variant="filled" color="teal">
              usada en tu diseño
            </Badge>
          )}
        </Group>
        {spec.reference && (
          <Badge variant="light" size="sm" style={{ flexShrink: 0 }}>
            {spec.reference}
          </Badge>
        )}
      </Group>

      <Code block mt={6} style={{ fontSize: 13 }}>
        {spec.expression}
      </Code>

      {corrida && (
        <Code block mt={4} style={{ fontSize: 13 }}>
          {corrida.substitution} = {formatResult(corrida.result)} {corrida.units}
        </Code>
      )}

      {Object.keys(spec.symbols).length > 0 && (
        <Table mt={8} withRowBorders={false} verticalSpacing={2} fz="xs">
          <Table.Tbody>
            {Object.entries(spec.symbols).map(([sim, sig]) => (
              <Table.Tr key={sim}>
                <Table.Td style={{ width: "8em", verticalAlign: "top" }}>
                  <Code>{sim}</Code>
                </Table.Td>
                <Table.Td c="dimmed">{sig}</Table.Td>
              </Table.Tr>
            ))}
            <Table.Tr>
              <Table.Td style={{ verticalAlign: "top" }}>
                <Text size="xs" c="dimmed">resultado</Text>
              </Table.Td>
              <Table.Td c="dimmed">en <Code>{spec.units}</Code></Table.Td>
            </Table.Tr>
          </Table.Tbody>
        </Table>
      )}

      {spec.note && (
        <Text size="xs" c="dimmed" mt={6}>{spec.note}</Text>
      )}
      {corrida?.context && (
        <Text size="xs" mt={4} c="teal.8">En este caso: {corrida.context}</Text>
      )}

      <Text size="xs" c="dimmed" mt={6} fs="italic">
        Se ejecuta en <Code>{spec.module}</Code>
      </Text>
    </Card>
  );
}

/** Redondeo de lectura: sin decimales de más ni notación científica inútil. */
function formatResult(x: number): string {
  const a = Math.abs(x);
  if (a !== 0 && (a < 1e-3 || a >= 1e6)) return x.toExponential(4);
  if (a < 1) return x.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  if (a < 100) return x.toFixed(2);
  return x.toLocaleString("es-AR", { maximumFractionDigits: 1 });
}
