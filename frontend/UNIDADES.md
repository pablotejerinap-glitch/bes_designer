# Fase F pendiente — Toggle de unidades Campo / Métrico

Planificado, no implementado. El backend calcula **sólo en unidades de campo**;
el toggle es una **capa de presentación** en el front:

- Convertir para *mostrar* (inputs y resultados); **enviar siempre unidades de
  campo al backend**. Nada de conversión en `bes.core` ni en la API.
- Punto de implementación sugerido: un contexto React `UnitsProvider` con
  `format(value, quantity)` y `parse(displayValue, quantity)`, consumido por
  `WellForm` (inputs) y `ResultsView`/`ComparisonView` (salidas). El estado
  Campo/Métrico vive en la toolbar de `App.tsx`.
- Los gráficos Plotly vienen del backend en unidades de campo: en la primera
  iteración se dejan tal cual (etiquetados en el eje); convertirlos requeriría
  soporte del backend, no del front.

## Constantes de conversión

| Magnitud | Campo | Métrico | Factor |
|---|---|---|---|
| Presión | psi | kg/cm² | 1 kg/cm² = 14.2233 psi |
| Longitud / profundidad | ft | m | 1 m = 3.28084 ft |
| Temperatura | °F | °C | °F = °C × 9/5 + 32 |
| Caudal líquido | STB/d | m³/d | 1 m³/d = 6.28981 STB/d |
| GOR | scf/STB | m³/m³ | 1 m³/m³ = 5.61458 scf/STB |
| Diámetro | in | mm | 1 in = 25.4 mm |

Referencia interna: `backend/src/bes/core/units.py` ya tiene las conversiones
del camino métrico de cátedra; si los factores difieren, mandan los de ese
módulo para mantener consistencia con la tesis.
