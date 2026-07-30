// Sistema de diseño estilo pengtools: tema claro, plano, denso en datos.
// Tokens de color/tipografía/forma centralizados acá y en styles.css.
import { createTheme, rem } from "@mantine/core";
import type { MantineColorsTuple } from "@mantine/core";

// Acento azul pengtools. Índices relevantes:
//   0 = fondo tenue (#e8f1fc) · 6 = primario (#2a7ae2)
//   7 = hover (#1f66c2)       · 8 = activo (#17539e)
const pengBlue: MantineColorsTuple = [
  "#e8f1fc",
  "#d4e5f9",
  "#b0cef4",
  "#8ab6ee",
  "#66a0e9",
  "#438be5",
  "#2a7ae2",
  "#1f66c2",
  "#17539e",
  "#10407a",
];

export const theme = createTheme({
  colors: { pengBlue },
  primaryColor: "pengBlue",
  primaryShade: { light: 6, dark: 5 },

  fontFamily:
    "Inter, 'Segoe UI', Roboto, -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif",
  // Cuerpo 14px (md); el resto escala hacia abajo para densidad de ingeniería.
  fontSizes: {
    xs: rem(11.5),
    sm: rem(13),
    md: rem(14),
    lg: rem(16),
    xl: rem(18),
  },
  lineHeights: { md: "1.5" },
  headings: {
    fontWeight: "500",
    sizes: {
      h1: { fontSize: rem(20) },
      h2: { fontSize: rem(16) },
      h3: { fontSize: rem(14) },
      h4: { fontSize: rem(14) },
      h5: { fontSize: rem(13) },
    },
  },

  // Bordes finos y radios chicos: 4px controles, 6px cards.
  defaultRadius: "sm",
  radius: {
    xs: rem(2),
    sm: rem(4),
    md: rem(6),
    lg: rem(8),
    xl: rem(12),
  },
  // Sin sombras dramáticas: todo plano, separado por bordes.
  shadows: {
    xs: "none",
    sm: "none",
    md: "0 1px 2px rgba(31, 41, 51, 0.06)",
    lg: "0 2px 6px rgba(31, 41, 51, 0.10)",
    xl: "0 4px 12px rgba(31, 41, 51, 0.12)",
  },

  components: {
    Card: {
      defaultProps: { radius: "md", withBorder: true, shadow: "none", padding: "md" },
    },
    Paper: {
      defaultProps: { radius: "md", shadow: "none" },
    },
    Button: {
      defaultProps: { size: "sm", radius: "sm" },
    },
    NumberInput: {
      defaultProps: { size: "sm" },
    },
    TextInput: {
      defaultProps: { size: "sm" },
    },
    Select: {
      defaultProps: { size: "sm" },
    },
    Badge: {
      defaultProps: { radius: "sm" },
    },
    Table: {
      defaultProps: { verticalSpacing: 6, horizontalSpacing: "sm" },
    },
    Alert: {
      defaultProps: { radius: "md" },
    },
    Tabs: {
      defaultProps: { radius: "sm" },
    },
    Accordion: {
      defaultProps: { radius: "md" },
    },
  },
});
