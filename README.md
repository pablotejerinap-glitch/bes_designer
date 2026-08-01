# BES Designer

Herramienta de diseño automatizado para sistemas de Bombeo Electrosumergible (BES/ESP).
Implementa la metodología completa de Kermit Brown — *The Technology of Artificial Lift Methods*, Vol. 2b, Cap. 4.5 — en 10 módulos Python con 750 tests automatizados, una API FastAPI y una SPA React.

A partir de los datos del pozo (reservorio, fluido, geometría, superficie y objetivos de producción), la herramienta selecciona y dimensiona el sistema completo: bomba + número de etapas, motor, cable, transformador y voltaje en superficie.

---

## Características

- **IPR multi-método**: Vogel, Linear, Fetkovich, Combined
- **PVT completo**: Standing (Bo, Rs, Pb), Dranchuk-Abou-Kassem (z-factor), Beggs-Robinson (viscosidad)
- **Traverse de presión multifásico**: Hagedorn-Brown + Beggs-Brill para pozos desviados
- **TDH por Hazen-Williams** + perfil hidrostático
- **Manejo de gas (GIP)** siguiendo Brown §4.53103
- **Corrección por viscosidad** según el estándar Hydraulic Institute
- **Ordenamiento por criterios de ingeniería**: 1. cercanía al BEP · 2. eficiencia · 3. menor potencia (lexicográfico, sin pesos ni puntajes). El fabricante es informativo y no influye en el orden.
- **Top-3 recomendaciones** con la justificación construida a partir de los valores calculados
- **Método métrico de cátedra** ("ESP 01") como motor paralelo en kg/cm² · m · °C · m³/d
- **Reportes** PDF, Excel y JSON descargables desde la app
- **Análisis de sensibilidad** sobre parámetros clave
- **750 tests** con pytest

---

## Estructura del proyecto

```
bes_designer/
├── backend/                    # Todo el Python — desplegable por separado
│   ├── src/bes/                # Paquete instalable (pip install -e backend/)
│   │   ├── core/               # Motor de cálculo (dominio puro, sin frameworks)
│   │   │   ├── models.py       # Dataclasses y validación
│   │   │   ├── ipr.py          # IPR: Vogel, Linear, Fetkovich, Combined
│   │   │   ├── pvt.py          # PVT: Standing, DAK z-factor, Beggs-Robinson
│   │   │   ├── multiphase.py   # Hagedorn-Brown, Beggs-Brill, traverse
│   │   │   ├── tdh.py          # Total Dynamic Head (Brown §4.5324)
│   │   │   ├── pump_design.py  # Etapas, HP, corrección por viscosidad HI
│   │   │   ├── electrical.py   # Motor, cable, transformador
│   │   │   ├── gas_handling.py # GIP (Brown §4.53103)
│   │   │   └── metric_design.py# Método métrico de cátedra "ESP 01"
│   │   ├── catalogs/           # Catálogos de equipos (JSON) + CatalogManager
│   │   ├── recommender/        # Selección y ordenamiento (select_top_n_pumps, ranking)
│   │   ├── reports/            # PDF (ReportLab) · Excel (openpyxl)
│   │   ├── services/           # Orquestación agnóstica de framework
│   │   ├── plotting/           # Gráficos Plotly (agnósticos, los usa la API)
│   │   └── api/                # Backend FastAPI (routers, schemas, mappers)
│   ├── tests/                  # Suite pytest
│   ├── data/                   # example_wells.json (ejemplos de Brown)
│   ├── scripts/                # validate_all_examples.py, ingest, generación
│   ├── pyproject.toml
│   ├── requirements*.txt
│   └── Dockerfile
│
├── frontend/                   # SPA React (Vite + TS + Mantine)
│   ├── src/
│   ├── Dockerfile
│   └── nginx.conf
│
├── tools/                      # Utilitarios de desarrollo, fuera del paquete
│   ├── catalog_pipeline/       # Digitalización de PDFs de catálogo
│   └── database_migration/     # Diseño de la base de datos (Excel → SQLite)
│
├── docs/                       # METHODOLOGY · FORMULAS · VALIDATION · USER_GUIDE
├── docker-compose.yml          # Levanta api + frontend
├── README.md
└── CLAUDE.md
```

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/pablotejerinap-glitch/bes_designer.git
cd bes_designer

# 2. Crear y activar entorno virtual
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows (cmd)
.venv\Scripts\Activate.ps1      # Windows (PowerShell)

# 3. Instalar el backend en editable (arrastra sus dependencias)
pip install -e backend
```

Requiere **Python 3.11 o superior** (el entorno de desarrollo usa 3.14) y
**Node 18+** para el frontend.

---

## Uso

### Interfaz gráfica (React)

```bash
# 1. Backend (requerido) — desde backend/
uvicorn bes.api.main:app --reload --port 8000

# 2. Frontend — desde frontend/
npm install && npm run dev
```

La app abre en `http://localhost:5173` (Vite proxya `/api` al backend).
O todo junto con Docker: `docker compose up --build` → frontend en
`http://localhost:8080`, API en `http://localhost:8000` (`/docs` para el
Swagger).

Flujo típico — la pantalla es de dos paneles: los datos del pozo a la
izquierda, los resultados a la derecha.

1. **Panel izquierdo** — cargar un caso de ejemplo o completar los datos del pozo (reservorio, fluido, geometría, superficie y objetivos) → Calcular
2. **Diseño** — las 3 opciones ordenadas por criterios de ingeniería, con la comparación y las curvas de bomba
3. **Curva IPR** — el análisis nodal del pozo
4. **Sensibilidad** — impacto de variaciones en Pr, WC, GOR
5. **Biblioteca ESP** — el catálogo de equipos disponible
6. **Descargar** — PDF · Excel · JSON

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

Todos los comandos se corren desde `backend/` (ahí viven `pyproject.toml` y `tests/`).

```bash
# Suite completa — 750 tests
pytest

# Solo integración (ejemplos del libro)
pytest tests/test_integration.py -v

# Con reporte de cobertura
pytest --cov=bes --cov-report=term-missing
```

---

## Validación

Compara los resultados de la app con los valores de referencia de Kermit Brown:

```bash
# desde backend/
python scripts/validate_all_examples.py
```

Genera `docs/VALIDATION.md` con una tabla comparativa de TDH, etapas y HP para los tres ejemplos del libro (1A, 2A, 3A). Ver [docs/METHODOLOGY.md](docs/METHODOLOGY.md) para la descripción completa de las correlaciones implementadas y [docs/FORMULAS.md](docs/FORMULAS.md) para las ecuaciones.

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

Ver [docs/FORMULAS.md](docs/FORMULAS.md) para las ecuaciones con su archivo,
línea y fuente bibliográfica.

---

## Documentación

Índice completo en [docs/README.md](docs/README.md).

| Documento | Contenido |
|---|---|
| [METHODOLOGY.md](docs/METHODOLOGY.md) | Metodología de cálculo paso a paso |
| [FORMULAS.md](docs/FORMULAS.md) | Todas las fórmulas, con archivo, línea y fuente |
| [VALIDATION.md](docs/VALIDATION.md) | Comparación app vs. libro |
| [USER_GUIDE.md](docs/USER_GUIDE.md) | Guía de usuario |
| [EJEMPLO_ESP01.md](docs/EJEMPLO_ESP01.md) | Ejercicio de cátedra, método métrico |

---

## Citación académica

Si usás este software en publicaciones académicas, citalo como:

```
Tejerina, P. (2026). BES Designer: Herramienta de diseño automatizado para
sistemas de Bombeo Electrosumergible (v1.0.0). Proyecto de Tesis de Grado,
Ingeniería de Petróleo. https://github.com/pablotejerinap-glitch/bes_designer
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
