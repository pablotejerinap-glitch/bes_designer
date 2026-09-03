import { Alert, SimpleGrid, Text, Tooltip } from "@mantine/core";
import type { GasFeasibility } from "../api/types";

/**
 * El veredicto de manejo de gas, compartido por los dos caminos de diseño.
 *
 * Vivía dentro de `GasIncrementView`, así que el mismo pozo mostraba el panel
 * cuando se lo diseñaba por incrementos y no lo mostraba cuando se lo diseñaba
 * por el camino convencional — aunque la escalera se corre igual en los dos.
 * Está acá para que sean literalmente el mismo componente y no dos que se
 * parecen: si mañana cambia una etiqueta, cambia en los dos lados o en ninguno.
 *
 * Las dos preguntas de cada escalón se muestran por separado a propósito
 * (`.claude/rules/domain.md`): «¿la configuración admite este gas?» se mide en
 * la ADMISIÓN contra `capacity`, y «¿la bomba tolera lo que le llega?» se mide
 * DESPUÉS de separar contra `tolerance`. Fallan por motivos distintos y se
 * remedian distinto, así que juntarlas en un solo número escondería cuál falló.
 */

/** Los cuatro escalones de la escalera, en castellano. */
const ETIQUETA_ESCALON: Record<string, string> = {
  ninguno: "sin separador",
  simple: "1 separador",
  tandem: "tándem (2)",
  agh: "manejador avanzado",
  no_viable: "no viable",
};

function pct(v: number | null | undefined, dec = 1): string {
  // Un dato ausente se declara ausente. Multiplicar undefined por 100 da NaN,
  // y "NaN %" en pantalla parece un error de cálculo y no un dato que falta.
  if (v == null || !Number.isFinite(v)) return "sin dato";
  return `${(v * 100).toLocaleString("es-AR", {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  })} %`;
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
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

export function GasHandlingPanel({ feasibility }: { feasibility: GasFeasibility }) {
  const f = feasibility;

  // Que no haya equipo BES capaz de manejar este gas no es una métrica más:
  // es la conclusión de que hay que cambiar de método de levantamiento. Va como
  // alerta roja aparte, arriba del panel.
  const cambiarDeMetodo = f.switch_lift_method || f.strategy === "no_viable";

  return (
    <>
      {cambiarDeMetodo && (
        <Alert color="red" variant="filled" title="Cambiar de método de levantamiento">
          <Text size="sm">{f.verdict}</Text>
          <Text size="sm" mt="xs">
            Ni el techo de la tecnología BES —tándem de separadores más manejador
            avanzado— deja el gas por debajo de lo que la bomba tolera (Takács,
            Fig. 4.25, pág. 195). Corresponde evaluar bombeo de cavidad
            progresiva, gas lift o pistón.
          </Text>
        </Alert>
      )}

      <Alert
        color={cambiarDeMetodo ? "orange" : "teal"}
        variant="light"
        title="Manejo del gas"
        mt={cambiarDeMetodo ? "sm" : undefined}
      >
        {!cambiarDeMetodo && <Text size="sm">{f.verdict}</Text>}
        <SimpleGrid cols={{ base: 2, sm: 3 }} mt="sm" spacing="xs">
          <Metric
            label="Configuración"
            value={ETIQUETA_ESCALON[f.strategy] ?? f.strategy}
            hint={
              f.uses_agh
                ? `sobre ${f.n_separators} separador(es) · ${f.agh_model ?? "AGH"}`
                : undefined
            }
          />
          <Metric
            label="Gas libre en admisión"
            value={pct(f.f_intake)}
            hint="1.ª pregunta: ¿lo admite la configuración?"
          />
          <Metric
            label="Capacidad de esa configuración"
            value={pct(f.capacity, 0)}
            hint="Takács, Fig. 4.25, pág. 195"
          />
          <Metric
            label="Separador"
            value={f.separator_efficiency != null ? pct(f.separator_efficiency, 0) : "sin separador"}
            hint={f.separator_model ?? undefined}
          />
          <Metric
            label="Gas que entra a la bomba"
            value={pct(f.f_pump)}
            hint="2.ª pregunta: ¿lo tolera la bomba?"
          />
          <Metric
            label="Máximo admisible"
            value={pct(f.max_gip)}
            hint="objectives.max_gip — por encima, la BES no converge"
          />
        </SimpleGrid>
        {f.tandem_arrangement && (
          <Text size="xs" c="dimmed" mt="xs">
            Tándem armado con {f.tandem_arrangement}.
            {f.tandem_arrangement !== "tipos distintos" &&
              " La bibliografía documenta la capacidad del tándem para tipos" +
                " distintos de separador; este arreglo es una extrapolación."}
          </Text>
        )}
      </Alert>
    </>
  );
}
