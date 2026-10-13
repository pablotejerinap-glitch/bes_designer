import { Alert, Collapse, List, Text, UnstyledButton } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";

/** Cartel de advertencias plegable.
 *
 * Las advertencias de diseño son varias y largas —cada una explica el porqué,
 * no sólo el qué—, así que desplegadas tapaban la tabla de resultados. Arrancan
 * plegadas, pero el encabezado publica **cuántas** son: un cartel que esconde
 * su propio contenido sin decir que hay algo adentro se pasa por alto, y estas
 * advertencias son justamente lo que el usuario tiene que leer antes de dar un
 * diseño por bueno.
 *
 * Cada advertencia va como ítem de lista y no separada por «·»: son
 * independientes entre sí y el punto medio las hacía leer como un párrafo.
 */
export function WarningsAlert({
  warnings,
  title = "Advertencias de diseño",
  compact = false,
}: {
  warnings: string[];
  title?: string;
  compact?: boolean;
}) {
  const [opened, { toggle }] = useDisclosure(false);

  if (warnings.length === 0) return null;

  const size = compact ? "xs" : "sm";

  return (
    <Alert color="yellow" mt="sm" p={compact ? "xs" : undefined}>
      <UnstyledButton onClick={toggle} w="100%" aria-expanded={opened}>
        <Text size={size} fw={600} c="yellow.9">
          {opened ? "▾" : "▸"} {title} ({warnings.length})
        </Text>
      </UnstyledButton>

      <Collapse in={opened}>
        <List size={size} mt="xs" spacing="xs">
          {warnings.map((w, i) => (
            <List.Item key={i}>{w}</List.Item>
          ))}
        </List>
      </Collapse>
    </Alert>
  );
}
