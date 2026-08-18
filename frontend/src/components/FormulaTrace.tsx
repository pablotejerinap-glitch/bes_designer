import { Badge, Card, Code, Group, Stack, Text, Title } from "@mantine/core";
import type { Formula } from "../api/types";

/**
 * Muestra las cuentas del diseño en orden, con la fórmula en símbolos, los
 * números reemplazados y el resultado.
 *
 * El objetivo es que se pueda verificar a mano que la fórmula aplicada es la
 * correcta, sin abrir el código. Los datos vienen del backend, armados por el
 * mismo código que calcula, así que lo que se ve acá es necesariamente lo que
 * se ejecutó.
 */
export function FormulaTrace({ formulas }: { formulas?: Formula[] }) {
  if (!formulas || formulas.length === 0) {
    return (
      <Text c="dimmed" size="sm">
        Este diseño no registró fórmulas.
      </Text>
    );
  }

  return (
    <Stack gap="sm">
      <Text size="sm" c="dimmed">
        Cada paso del cálculo con su fórmula, los valores reemplazados y la
        fuente. Se genera desde el mismo código que hace la cuenta.
      </Text>

      {formulas.map((f, i) => {
        /*
          Los métodos partidos en tramos (Vogel generalizado) publican TODOS
          sus tramos, no sólo el que gobierna: con media función no se puede
          revisar el método. Pero entonces hay que distinguirlos bien, porque
          si no se puede leer el número equivocado. El tramo que no gobierna va
          atenuado y con su etiqueta; el que gobierna, resaltado.
        */
        const inactivo = f.applies === false;
        return (
          <Card
            key={f.key + i}
            withBorder
            radius="sm"
            padding="sm"
            style={inactivo ? { opacity: 0.62, borderStyle: "dashed" } : undefined}
          >
            <Group justify="space-between" align="flex-start" wrap="nowrap">
              <Group gap={6} align="baseline" wrap="nowrap">
                <Text fw={600} size="sm">
                  {i + 1}. {f.label}
                </Text>
                {f.applies === true && (
                  <Badge size="xs" variant="filled" color="teal">
                    gobierna este pozo
                  </Badge>
                )}
                {inactivo && (
                  <Badge size="xs" variant="outline" color="gray">
                    otro tramo del método
                  </Badge>
                )}
              </Group>
              {f.reference && (
                <Badge variant="light" size="sm" style={{ flexShrink: 0 }}>
                  {f.reference}
                </Badge>
              )}
            </Group>

            <Code block mt={6} style={{ fontSize: 13 }}>
              {f.expression}
            </Code>

            <Code block mt={4} style={{ fontSize: 13 }}>
              {f.substitution} = {formatResult(f.result)} {f.units}
            </Code>

            {/*
              Dos notas distintas y a propósito separadas: `note` es del método y
              vale siempre —viene del catálogo—; `context` es de ESTE pozo.
              Mezclarlas haría parecer condición general lo que es circunstancia.
            */}
            {f.note && (
              <Text size="xs" c="dimmed" mt={6}>
                {f.note}
              </Text>
            )}
            {f.context && (
              <Text size="xs" c={inactivo ? "dimmed" : "teal.8"} mt={4}>
                {inactivo ? "" : "En este caso: "}
                {f.context}
              </Text>
            )}
          </Card>
        );
      })}
    </Stack>
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

/** Encabezado reutilizable para la sección de fórmulas. */
export function FormulaTraceSection({ formulas }: { formulas?: Formula[] }) {
  return (
    <>
      <Title order={4} mt="lg" mb="xs">
        Fórmulas aplicadas
      </Title>
      <FormulaTrace formulas={formulas} />
    </>
  );
}
