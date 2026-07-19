# BES Designer

Herramienta de diseño automatizado para sistemas de Bombeo Electrosumergible (BES/ESP).
Implementa la metodología completa de Kermit Brown — *The Technology of Artificial Lift Methods*, Vol. 2b, Cap. 4.5 — en 10 módulos Python con más de 400 tests automatizados y una interfaz Streamlit lista para usar.

A partir de los datos del pozo (reservorio, fluido, geometría, superficie y objetivos de producción), la herramienta selecciona y dimensiona el sistema completo: bomba + número de etapas, motor, cable, transformador y voltaje en superficie.

---

## Características

- **IPR multi-método**: Vogel, Linear, Fetkovich, Combined
- **PVT completo**: Standing (Bo, Rs, Pb), Dranchuk-Abou-Kassem (z-factor), Beggs-Robinson (viscosidad)
- **Traverse de presión multifásico**: Hagedorn-Brown + Beggs-Brill para pozos desviados
- **TDH por Hazen-Williams** + perfil hidrostático
- **Manejo de gas (GIP)** siguiendo Brown §4.53103
- **Corrección por viscosidad** según el estándar Hydraulic Institute
- **Scoring multi-criterio**: eficiencia 40 % · flexibilidad 30 % · preferencia de proveedor 30 %
- **Top-3 recomendaciones** con diversificación de fabricante
- **Reportes** PDF, Excel y JSON descargables desde la app
- **Análisis de sensibilidad** sobre parámetros clave
- **400+ tests** con pytest

---

## Estructura del proyecto

```
bes_designer/
├── src/bes/                # Paquete instalable (pip install -e .)
│   │
│   ├── core/               # Motor de cálculo
│   ├── models.py           # Dataclasses y validación de datos
│   ├── ipr.py              # IPR: Vogel, Linear, Fetkovich, Combined
│   ├── pvt.py              # PVT: Standing, DAK z-factor, Beggs-Robinson
│   ├── multiphase.py       # Hagedorn-Brown, Beggs-Brill, traverse de presión
│   ├── tdh.py              # Total Dynamic Head (Brown §4.5324)
│   ├── pump_design.py      # Etapas, HP, corrección por viscosidad HI
│   ├── electrical.py       # Motor, cable, transformador
│   └── gas_handling.py     # GIP (Brown §4.53103)
│
│   ├── catalogs/           # Catálogos de equipos (JSON)
│   ├── pumps.json          # Curvas de rendimiento de bombas
│   ├── motors.json         # Catálogo de motores
│   ├── cables.json         # Catálogo de cables
│   ├── seals.json          # Catálogo de sellos/protectores
│   └── loader.py           # CatalogManager
│
│   ├── recommender/        # Selección y ranking de equipos
│   ├── pump_selector.py    # select_top_n_pumps
│   ├── scoring.py          # Scores de eficiencia, flexibilidad, preferencia de proveedor
│   └── recommendation_engine.py  # generate_recommendations (API pública)
│
│   ├── reports/            # Generación de reportes
│   ├── pdf_generator.py    # generate_design_report → bytes PDF (ReportLab)
│   └── excel_exporter.py   # generate_design_excel → bytes XLSX (openpyxl)
│
│   ├── services/           # Orquestación agnóstica de framework
│   ├── plotting/           # Gráficos Plotly (agnósticos, los usa la API)
│   └── api/                # Backend FastAPI (routers, schemas, mappers)
│
├── streamlit_app/          # App Streamlit (red de seguridad)
│   ├── app.py              # Punto de entrada
│   ├── forms.py            # Formulario de datos del pozo (5 tabs)
│   ├── results_view.py     # Vista de resultados de diseño
│   ├── comparison_view.py  # Comparación de opciones
│   ├── sensitivity_view.py # Análisis de sensibilidad
│   └── api_client.py       # Cliente HTTP hacia la API
│
├── frontend/               # SPA React (Vite + TS + Mantine)
│
├── requirements.txt
│
├── tests/                  # Suite de tests pytest
│   ├── test_ipr.py
│   ├── test_pvt.py
│   ├── test_multiphase.py
│   ├── test_tdh.py         # (incluye test_pump_design)
│   ├── test_electrical.py
│   ├── test_gas_handling.py
│   ├── test_catalog.py
│   ├── test_models.py
│   ├── test_recommender.py
│   └── test_integration.py # Tests end-to-end con ejemplos del libro
│
├── data/
│   └── example_wells.json  # Ejemplos de Brown Vol. 2b (1A, 2A, 3A)
│
├── scripts/
│   └── validate_all_examples.py  # Genera docs/VALIDATION.md
│
└── docs/
    ├── USER_GUIDE.md       # Guía de instalación y uso
    ├── METHODOLOGY.md      # Correlaciones, suposiciones, limitaciones
    └── VALIDATION.md       # Tabla comparativa vs. libro (generada por script)
```

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/placeholder/bes_designer.git
cd bes_designer

# 2. Crear y activar entorno virtual
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows (cmd)
.venv\Scripts\Activate.ps1      # Windows (PowerShell)

# 3. Instalar dependencias + el paquete en editable
pip install -r requirements.txt
pip install -e .
```

Requiere **Python 3.10 o superior**.

---

## Uso

### Interfaz gráfica (Streamlit)

```bash
# 1. Backend (requerido)
uvicorn bes.api.main:app --reload --port 8000

# 2. Streamlit
streamlit run streamlit_app/app.py
```

O todo junto con Docker: `docker compose up --build`
(frontend :8080 · api :8000 · streamlit :8501)

La app abre en `http://localhost:8501`. Flujo típico:

1. **Datos del Pozo** — completar las 5 pestañas (o cargar un ejemplo) → Guardar
2. **Diseño BES** → Calcular → revisar las 3 opciones rankeadas
3. **Comparación** — gráfico radar y tabla comparativa
4. **Sensibilidad** — evaluar el impacto de variaciones en Pr, WC, GOR
5. **Descargar** — PDF · Excel · JSON

### API Python

```python
from bes.catalogs.loader import CatalogManager
from bes.core.models import Reservoir, Fluid, WellGeometry, SurfaceConditions, DesignObjectives, IPRMethod, DriveMechanism
from bes.recommender.recommendation_engine import generate_recommendations

# Sin argumento: resuelve los JSON desde el paquete, sea cual sea el CWD.
catalog = CatalogManager()

reservoir = Reservoir(
    static_pressure=2500.0,
    bubble_point=1500.0,
    productivity_index=1.0,
    ipr_method=IPRMethod.VOGEL,
    reservoir_temp=180.0,
    drive_mechanism=DriveMechanism.SOLUTION_GAS,
    datum_depth=5000.0,
)
# ... (Fluid, WellGeometry, SurfaceConditions, DesignObjectives)

results = generate_recommendations(
    reservoir=reservoir, fluid=fluid, well=well,
    surface=surface, objectives=objectives,
    catalog=catalog, n=3,
)

best = results["recommendations"][0]["design"]
print(f"Bomba: {best.pump_model}, {best.num_stages} etapas, TDH={best.total_head_required:.0f} ft")
```

---

## Tests

```bash
# Suite completa
pytest tests/ -v

# Solo integración (ejemplos del libro)
pytest tests/test_integration.py -v

# Con reporte de cobertura
pytest tests/ --cov=core --cov=recommender --cov-report=term-missing
```

---

## Validación

Compara los resultados de la app con los valores de referencia de Kermit Brown:

```bash
python scripts/validate_all_examples.py
```

Genera `docs/VALIDATION.md` con una tabla comparativa de TDH, etapas y HP para los tres ejemplos del libro (1A, 2A, 3A). Ver [docs/METHODOLOGY.md](docs/METHODOLOGY.md) para la descripción completa de las correlaciones implementadas.

---

## Correlaciones principales

| Módulo | Método |
|---|---|
| IPR | Vogel (1968), Linear, Fetkovich (1973), Combined |
| PVT | Standing (1947): Bo, Rs, Pb |
| z-factor | Dranchuk & Abou-Kassem (1975) |
| Viscosidad | Beggs & Robinson (1975) |
| Presión de admisión | Hagedorn & Brown (1965), Beggs & Brill (1973) |
| TDH | Hazen-Williams + columna hidrostática (Brown §4.5324) |
| Corrección viscosidad | Hydraulic Institute HI 9.6.7 |
| Gas en bomba | Brown §4.53103 |

---

## Citación académica

Si usás este software en publicaciones académicas, citalo como:

```
Tejerina, P. (2026). BES Designer: Herramienta de diseño automatizado para
sistemas de Bombeo Electrosumergible (v1.0.0). Proyecto de Tesis de Grado,
Ingeniería de Petróleo. https://github.com/placeholder/bes_designer
```

Basado en:

> Brown, K.E. (1984). *The Technology of Artificial Lift Methods, Vol. 2b:
> Electric Submersible Pumping Systems*. PennWell Books, Tulsa, Oklahoma.

---

## Licencia

MIT License

Copyright (c) 2026 Pablo Tejerina

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
