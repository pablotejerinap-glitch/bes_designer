# Contexto Completo — Tesis BES Designer

> **Cómo usar este archivo:** abrí una nueva conversación con Claude (web, Cowork mode, o Claude Code) y pegá el contenido completo de este archivo como primer mensaje. Claude entenderá inmediatamente el proyecto, su estado, qué falta, y podrá continuar trabajando con vos sin necesidad de re-explicar nada.

---

## 0. Saludo a Claude del nuevo chat

Hola Claude. Soy Pablo Tejerina, alumno de Ingeniería de Petróleo en la Universidad Nacional del Comahue (UNCo, Neuquén, Argentina). Estoy desarrollando mi Proyecto Integrador Profesional (PIP, equivalente a tesis de grado) sobre automatización de diseño de sistemas de Bombeo Electrosumergible (BES/ESP) en Python. El proyecto se llama **BES Designer** y vive en `C:\Users\pablo\bes_designer\`.

Necesito que retomes el contexto completo del proyecto desde donde lo dejé en una conversación anterior. **No empezar de cero.** Leé este archivo entero, después leé los archivos de docs/ que menciono, y después esperá mis instrucciones.

**Tu rol esperado:**
- Asistente técnico que conoce el código, las correlaciones del libro de Kermit Brown, y mi cronograma de tesis.
- No te ofrezcas a "armar el proyecto desde cero" — ya está construido.
- Cuando te pida cambios al código, hacelos directamente con Edit/Write, no me sugieras "podrías hacer X" sin hacerlo (a menos que requiera decisión mía).
- Cuando te pida sugerencias, dame ítems concretos con archivo y línea, no genéricos.

---

## 1. Identidad del proyecto

| Dato | Valor |
|---|---|
| Nombre | BES Designer |
| Lenguaje | Python 3.14 |
| Arquitectura | Tres capas: SPA React (`frontend/`) → API FastAPI (`bes.api`) → dominio (`bes.core`, `bes.services`) |
| Repositorio local | `C:\Users\pablo\bes_designer\` |
| Tests | pytest, **705 tests pasando** |
| Base teórica | Kermit Brown, *The Technology of Artificial Lift Methods*, Vol. 2b Cap. 4.5 + Vol. 4 (Nodal Analysis) |
| Director PIP | Pendiente de definir (en el plan original quedó vacío) |
| Universidad | Universidad Nacional del Comahue, Neuquén |
| Cronograma | 6 meses, ~280 hs, ~12 hs/semana |

---

## 2. Marco académico (PIP)

**Objetivo general:** desarrollar un sistema automatizado de diseño y selección de equipos BES en Python, validado contra el libro de Brown y contra un caso real de la cuenca Neuquina.

**Las 14 actividades del cronograma del PIP:**

| # | Actividad | Estado actual |
|---|---|---|
| 1 | Revisión bibliográfica | ✅ |
| 2 | Diseño de arquitectura y modelo de datos | ✅ `bes/core/models.py` |
| 3 | Módulos de cálculo (IPR, PVT, multifásico) | ✅ `bes/core/ipr.py`, `pvt.py`, `multiphase.py` |
| 4 | Digitalización de catálogos | ✅ `bes/catalogs/*.json` |
| 5 | Módulos TDH, bomba, eléctrico | ✅ `bes/core/tdh.py`, `pump_design.py`, `electrical.py` |
| 6 | Manejo de gas (200 psi method) | ✅ `bes/core/gas_handling.py` |
| 7 | Motor de recomendación | ✅ `bes/recommender/` completo |
| 8 | Interfaz de usuario | ✅ SPA React en `frontend/` sobre la API FastAPI (`bes/api/`). La app Streamlit original se retiró al alcanzar React paridad. |
| 9 | Reportes PDF/Excel | ✅ `bes/reports/` |
| 10 | Validación contra Brown | ⚠️ Parcial — #1A, #2A, #2B sí; #3A/3B/3C/4 faltan |
| 11 | Aplicación a pozo real Neuquino | ❌ Pendiente (depende de datos de operadora) |
| 12 | Análisis de sensibilidad | ✅ UI existe; falta documentar |
| 13 | Redacción del informe final | ❌ Pendiente |
| 14 | Defensa | ❌ Pendiente |

**Extra que está en el repo y no figura en el plan original:** `bes/core/nodal_analysis.py` (basado en Brown Vol. 4, §4.54 Couto's operational approach).

---

## 3. Arquitectura del proyecto

### Estructura de directorios

Desde el rediseño de arquitectura el repo tiene dos carpetas de primer nivel,
cada una desplegable por separado. La app Streamlit se retiró al alcanzar
React paridad funcional; el dominio no cambió de contenido, solo de ubicación
(`core/` → `backend/src/bes/core/`, etc.).

```
bes_designer/
├── docker-compose.yml      # Levanta las tres capas
├── README.md
├── CLAUDE.md               # Instrucciones para Claude Code
│
├── backend/                # Todo el Python — unidad de despliegue autocontenida
│   ├── pyproject.toml      # pip install -e backend/ ; paquete único: bes
│   ├── requirements*.txt
│   │
│   ├── src/bes/
│   │   ├── core/                   # Dominio puro — sin frameworks
│   │   │   ├── models.py           # Dataclasses validadas
│   │   │   ├── ipr.py              # Vogel, Linear, Fetkovich, Combined
│   │   │   ├── pvt.py              # Standing, DAK, Beggs-Robinson
│   │   │   ├── multiphase.py       # Hagedorn-Brown, Beggs-Brill
│   │   │   ├── tdh.py              # Hazen-Williams + lift + WHP head
│   │   │   ├── pump_design.py      # Etapas, HP, corrección viscosidad HI
│   │   │   ├── electrical.py       # Motor, cable, transformador
│   │   │   ├── gas_handling.py     # GIP, 200-psi method
│   │   │   ├── nodal_analysis.py   # Master regions, Couto — extra
│   │   │   ├── units.py            # Conversores campo ↔ métrico
│   │   │   └── metric_design.py    # Método de cátedra ESP 01 (17 pasos)
│   │   │
│   │   ├── catalogs/               # JSON + loaders (viajan con el paquete)
│   │   │   ├── pumps.json          # Reda D-40, D-55, I-300, I-42B, etc.
│   │   │   ├── motors.json, cables.json, seals.json
│   │   │   ├── gas_handlers.json, sensors.json
│   │   │   ├── loader.py           # CatalogManager (interpolación lineal)
│   │   │   ├── metric_catalog.json # Catálogo del método métrico
│   │   │   └── metric_loader.py    # MetricCatalog
│   │   │
│   │   ├── recommender/            # Selección y ordenamiento
│   │   ├── reports/                # PDF (ReportLab) / Excel (openpyxl)
│   │   ├── services/               # Orquestación agnóstica de framework
│   │   ├── plotting/               # Builders Plotly — los consume la API
│   │   └── api/                    # Capa de entrega HTTP (FastAPI)
│   │
│   ├── tests/                      # ~705 tests
│   ├── data/example_wells.json     # Ejemplos Brown + pozo Neuquino
│   └── scripts/validate_all_examples.py   # Genera VALIDATION.md
│
├── frontend/               # SPA React (Vite + TS + Mantine)
│
├── tools/                  # Utilitarios de desarrollo, fuera del paquete
│   ├── catalog_pipeline/   # Digitalización de PDFs de catálogo
│   └── database_migration/ # Construcción de la DB desde Excel
│
└── docs/
    ├── METHODOLOGY.md                 # ← incluye §7, método métrico ESP 01
    ├── USER_GUIDE.md
    ├── FORMULAS.md
    ├── EJEMPLO_ESP01.md
    ├── BROWN_CHAPTER_SUMMARY.md       # ← Resumen Brown Vol 2b §4.5
    ├── BROWN_VOL4_NODAL_ANALYSIS.md   # ← Resumen Brown Vol 4 (nodal)
    └── TESIS_CONTEXTO_COMPLETO.md     # ← este archivo
```

### Convenciones técnicas

- **Unidades:** psia/psi, °F, STB/d, ft, in, hp, V/A.
- **TDH (Brown §4.5324):** `TDH = Vertical Lift + Tubing Friction + WHP Head`
- **Hazen-Williams:** `0.2083 × (100/C)^1.852 × q_gpm^1.852 / d^4.8655 × L/100`, C=120 default.
- **HP/stage del catálogo** está rated para water (SG=1.0). Multiplicar por `sg_fluid`.
- **`pump_setting_depth`** se setea como `max(perforations_top − safety_margin_depth, 100 ft)` en `select_top_n_pumps` (Brown §4.532). El proxy viejo `total_depth × 0.80`, físicamente incorrecto, quedó solo como fallback de `electrical_design_complete()` cuando no se le pasa la profundidad.

---

## 4. Validación contra Brown — estado actual

### Vol. 2b §4.5 — Tests existentes

| Ejemplo | Pump | Flow (bpd) | TDH (ft) | Stages | HP | Test |
|---|---|---|---|---|---|---|
| #1A | Centrilift I-300 | 10 000 | 1 670 | 28 | 180 | ✅ existe |
| #2A | Reda D-40 | 1 227 | 5 830 | 254 | ≈79 | ✅ existe |
| #2B | Centrilift I-42B | ~2 080 | 4 258 | 112 | ≈65 | ✅ existe |
| Friction 5" | — | 10 000 | 18.5 ft/1000 | — | — | ✅ existe |

### Vol. 2b §4.5 — Tests faltantes

| Ejemplo | Datos clave | Resultado esperado |
|---|---|---|
| #3B Hagedorn long-hand | 7000 ft, 5½" csg, GOR=500, 100% gas | 209 stages D-40, 27 hp, P_disch=1300 psi |
| #3B Orkiszewski no-slip | mismo | 21 D-55 + 173 D-40, 27.84 hp |
| #3B con deterioration | mismo | 263 stages mixed, ~30 hp |
| #3B 50% gas vented | mismo | 211 stages (58 D-40 + 153 D-20), 31.86 hp |
| #3B 50% water + 50% GIP | mismo | 231 stages D-20, 41.25 hp |
| #4 viscoso (Riling) | 16°API, 130°F, GOR=50, WC=30% | 137 stages Y-62B, 162 hp |
| Affinity 60↔50 Hz (#1A) | misma data #1A pero 50 Hz | 48 stages, 190 hp |

Los datos completos de cada ejemplo están en `docs/BROWN_CHAPTER_SUMMARY.md`.

### Vol. 4 — Tests sugeridos (no existen)

| Test | Descripción | Esperado |
|---|---|---|
| Nodal §4.2 oil | Separator=100, flowline 3000ft×2", 5000ft, GOR=400, P̄_R=2200, PI=1.0, tubing 2⅜", WOR=0 | q ≈ 900 b/d, P_wh ≈ 245 psi |
| Tapered string | 2⅜"+2⅞" vs solo 2⅜" | Aumento de 900 → 1020 b/d |
| Pivot Point | Dos tests del pozo a P̄_R distintos | (q_max)_f con error < 5% |

Los detalles completos están en `docs/BROWN_VOL4_NODAL_ANALYSIS.md`.

---

## 5. Gaps identificados (sugerencias de mejora)

### Críticas — antes de la defensa

1. **`requirements.txt` sin versiones pinneadas** — riesgo de irreproducibilidad. Generar `requirements.lock` con pip-tools.
2. **`pump_setting_depth = total_depth × 0.80`** en `bes/recommender/pump_selector.py:209` es incorrecto físicamente. Reemplazar por `well.perforations_top - objectives.safety_margin_depth`.
3. **Falta `docs/VALIDATION.md`** — el script `backend/scripts/validate_all_examples.py` lo debe generar pero no se ha corrido.
4. **Tests faltantes para Ejemplos #3 y #4 del libro** — son los más complejos y los que diferencian la app.

### Alto valor académico

5. **Interpolación lineal vs cúbica** — el plan original decía "cúbica", el código usa "linear" en `bes/catalogs/loader.py:196`. Decidir y documentar.
6. **`system_efficiency = pump_efficiency × 0.92`** — proxy hardcodeado en `bes/recommender/pump_selector.py:134`. Usar eficiencia real del motor del catálogo.
7. **`gip_fraction` se calcula pero no afecta el ranking.** Agregar `reliability_score` (estaba en el plan original como 4to criterio).
8. **Falta `transformers.json`** — los tamaños están hardcodeados en `bes/core/electrical.py:27`.
9. **Test affinity laws 60↔50 Hz** — no documentado.
10. **Logging real** — toda la app usa `warnings.append(string)`. Agregar `logging` con niveles.

### Polish

11. **Type hints incompletos** — `-> dict` sin parametrizar en muchas firmas (ej. `bes/core/tdh.py:51`). Convertir a `TypedDict` o dataclass.
12. **CI/CD GitHub Actions** — falta `.github/workflows/`.
13. **Coverage badge** — generar con `pytest --cov=core --cov=recommender --cov-report=html`.
14. **i18n inconsistente** — docstrings en inglés, UI en español. Documentar la decisión.
15. **`pyproject.toml` + ruff** — no hay configuración de linter ni packaging moderno.
16. **Diagrama mermaid** — el data-flow ASCII de `CLAUDE.md` debería ser SVG/mermaid.

### Pendientes según el plan + libro

17. **Caso real Neuquino** (actividad #11 del PIP) — pendiente de datos de operadora.
18. **Análisis de sensibilidad documentado** — la UI existe (`frontend/src/components/SensitivityView.tsx` sobre `bes/services/sensitivity_service.py`), falta correr y guardar en `docs/SENSITIVITY_ANALYSIS.md`.

### Mejoras del libro Brown Vol. 4 que valdría implementar

19. **Composite IPR con water cut** (Brown Vol 4 §2.227) — fórmula dada en `docs/BROWN_VOL4_NODAL_ANALYSIS.md`.
20. **Standing FE ≠ 1.0** (§2.224) — para pozos dañados/estimulados.
21. **Pivot Point future IPR** (§2.235) — solo necesita 2 tests reales, ideal para el pozo Neuquino.
22. **Tapered strings** (§4.27) — diferenciador para tu defensa, pocos OSS lo hacen.
23. **Surface choke con Gilbert** (§3.5.1.1) — útil para análisis de optimización.
24. **Gravel pack ΔP con Jones-Blount-Glaze** (§4.5) — relevante para Comahue convencional.

---

## 6. Cómo correr el proyecto

Los comandos de Python usan el intérprete del venv (`.venv\Scripts\python.exe`)
y se corren desde `backend/`, que es donde viven `pyproject.toml` y `backend/tests/`.

```powershell
cd C:\Users\pablo\bes_designer

# Instalar (primera vez): editable, sin sys.path
.venv\Scripts\python.exe -m pip install -e backend

# Backend FastAPI — lo necesita la SPA
cd backend
..\.venv\Scripts\python.exe -m uvicorn bes.api.main:app --reload --port 8000

# SPA React (otra terminal)
cd frontend; npm run dev

# Las tres capas juntas
docker compose up --build

# Todos los tests (desde backend/)
..\.venv\Scripts\python.exe -m pytest -q

# Un test específico
..\.venv\Scripts\python.exe -m pytest tests/test_pump_design.py::TestCalculateStages -v

# Validar contra ejemplos del libro
..\.venv\Scripts\python.exe scripts\validate_all_examples.py
```

---

## 7. Comandos clave de Git

```powershell
git status
git log --oneline -20
git add docs/
git commit -m "docs: add tesis context dump"
```

Últimos commits relevantes (al momento de escribir este archivo):
- `18c9469 Análisis Nodal: sección Streamlit`
- `095948c Análisis Nodal: gráficos Plotly`
- `2e8ea52 Análisis Nodal: motor de cálculo + correlaciones P&C y D&R`
- `6e2b1c9 Fase 12: proyecto completo - 497 tests passing (96%)`
- `c68ec9f Fase 10: Interfaz Streamlit completa y funcional`

---

## 8. Documentos del proyecto a leer

Para entender el proyecto a fondo, leé estos archivos del repo en orden:

1. **`README.md`** — descripción general, instalación, uso.
2. **`CLAUDE.md`** — convenciones del codebase (importante para Claude).
3. **`docs/METHODOLOGY.md`** — correlaciones y suposiciones.
4. **`docs/USER_GUIDE.md`** — guía de uso de la app.
5. **`docs/BROWN_CHAPTER_SUMMARY.md`** — resumen Brown Vol. 2b §4.5 (53 páginas).
6. **`docs/BROWN_VOL4_NODAL_ANALYSIS.md`** — resumen Brown Vol. 4 (nodal analysis, 182 páginas).
7. **`bes/core/models.py`** — para ver las dataclasses que estructuran todo.
8. **`bes/recommender/recommendation_engine.py`** — para entender el flujo de alto nivel.

---

## 9. Bibliografía

### Principal

- **Brown, K. E.** (1980). *The Technology of Artificial Lift Methods, Vol. 2b: Electric Submersible Pumping Systems.* PennWell Books, Tulsa, Oklahoma. — Cap. 4.5 es el ground truth.
- **Brown, K. E.** (1984). *The Technology of Artificial Lift Methods, Vol. 4: Production Systems Analysis (Nodal Analysis).* PennWell Books. — Base de `bes/core/nodal_analysis.py`.
- **Takacs, G.** (2009). *Electrical Submersible Pumps Manual.* Gulf Professional Publishing.
- **Brill, J. P. & Mukherjee, H.** (1999). *Multiphase Flow in Wells.* SPE Monograph Series, Vol. 17.

### Correlaciones implementadas

- Vogel, J. V. (1968). "Inflow Performance Relationships for Solution-Gas Drive Wells." *JPT* 20(1): 83–92.
- Standing, M. B. (1947). "A Pressure-Volume-Temperature Correlation for Mixtures of California Oils and Gases." *API Drilling and Production Practice*: 275–287.
- Hagedorn, A. R. & Brown, K. E. (1965). "Experimental Study of Pressure Gradients Occurring During Continuous Two-Phase Flow in Small-Diameter Vertical Conduits." *JPT* 17(4): 475–484.
- Beggs, H. D. & Brill, J. P. (1973). "A Study of Two-Phase Flow in Inclined Pipes." *JPT* 25(5): 607–617.
- Beggs, H. D. & Robinson, J. R. (1975). "Estimating the Viscosity of Crude Oil Systems." *JPT* 27(9): 1140–1141.
- Dranchuk, P. M. & Abou-Kassem, J. H. (1975). "Calculation of Z Factors for Natural Gases Using Equations of State." *JCPT* 14(3): 34–36.
- Fetkovich, M. J. (1973). "The Isochronal Testing of Oil Wells." SPE-4529.

### Catálogos de fabricantes

- Schlumberger/REDA. *REDA ESP Systems Catalog.*
- Baker Hughes/Centrilift. *Submersible Pump Handbook.*
- Weatherford. *ESP Product Manual.*
- Borets. *ESP Catalog.*

---

## 10. Estilo de comunicación que prefiero

- **Escribí en castellano (rioplatense argentino).** Vos / sos / tenés.
- **Sé conciso.** Listas y tablas en lugar de párrafos largos.
- **Cuando me sugieras cambios, dame archivo:línea concreto**, no genéricos.
- **Evitá repetir lo que ya sé.** Si menciono "el Ejemplo #3A del libro", no me expliques qué es Brown.
- **Cuando te diga "hacelo", hacelo.** No me preguntes "¿querés que lo haga?".
- **Honestidad técnica.** Si hay un trade-off, decime los dos lados. Si algo está mal en el código, decímelo crudo.
- **No emojis** salvo que yo los use primero.

---

## 11. Próximos pasos sugeridos (orden recomendado)

| # | Tarea | Esfuerzo | Impacto |
|---|---|---|---|
| 1 | Fix `pump_setting_depth` (gap #2) + re-correr validation | 1h | 🔴 Alto |
| 2 | Pinear versiones en `requirements.txt` (gap #1) | 30 min | 🔴 Alto |
| 3 | Generar `docs/VALIDATION.md` con validate_all_examples.py | 30 min | 🔴 Alto |
| 4 | Tests para Ejemplos #3A/3B/4 (gap #4) | 4h | 🔴 Alto |
| 5 | Implementar `reliability_score` con GIP (gap #7) | 2h | 🟡 Alto |
| 6 | Eficiencia del sistema con catálogo real (gap #6) | 2h | 🟡 Alto |
| 7 | Composite IPR con water cut (Brown Vol 4 §2.227) | 4h | 🟡 Alto |
| 8 | Pivot Point IPR (Brown Vol 4 §2.235) | 3h | 🟡 Alto |
| 9 | `pyproject.toml` + ruff (gap #15) | 30 min | 🟢 Medio |
| 10 | CI/CD GitHub Actions (gap #12) | 1h | 🟢 Medio |
| 11 | Empezar esqueleto del informe final | 4h+ | 🔴 Alto |
| 12 | Buscar pozo real Neuquino | semanas | 🔴 Alto |

---

## 12. Resumen ejecutivo

**Estado:** el código del proyecto está esencialmente terminado (12 fases del plan original ejecutadas, 497 tests pasando). Lo que queda es:

1. **Validación robusta** contra los ejemplos #3 y #4 del libro (gas y viscoso).
2. **Mejoras de calidad** que diferencian una tesis "buena" de una "excelente": versiones pinneadas, tests faltantes, validation report, fix del bug de `pump_setting_depth`.
3. **Pozo real Neuquino** — actividad #11 del PIP, depende de datos de operadora.
4. **Informe final + defensa** — actividades #13 y #14.

**Ideas para diferenciar la defensa:**

- Comparar contra software comercial (SubPUMP, DesignPro, Autograph PC).
- Demo en vivo durante la defensa.
- Análisis de sensibilidad sistemático sobre WC, GOR, P̄_R.
- Caso real de Neuquén con comparación a diseño histórico de operadora.

---

**Fin del contexto. Después de leer esto y los archivos referenciados, esperá mis instrucciones.**

*Documento generado el 6 de mayo de 2026.*
