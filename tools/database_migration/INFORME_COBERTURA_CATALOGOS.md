# Informe de cobertura: catálogos de TESIS vs base de datos

**Pregunta:** ¿qué contenido de los catálogos PDF de `TESIS/CATALOGOS` ya
está representado en la base de datos (esquema v3) y qué falta?

**Base de datos hoy:** 7 fabricantes; 23 bombas, 50 motores, 19 cables,
24 sellos, 12 separadores, 4 sensores (mayormente datos de validación del
libro de Brown + data sheets ChampionX/SLB, varios marcados "estimado /
por confirmar" en `data_sources.xlsx`); 8 transformadores genéricos;
`vsds` y `switchboards` vacíos.

---

## Catálogo por catálogo

### 1. REDA_ESP_Catalog.pdf — 548 páginas, 2007, texto extraíble ✅
Es el catálogo técnico más completo de la carpeta. Contiene:
* **~29 modelos de bomba** con curvas: series AN (AN550–AN1500), DN
  (DN1100–DN3100), D—N (D475N–D5850N), GN (GN1600–GN10000), SN
  (SN2600–SN8500), en **11 series de diámetro** (338 a 1125).
* Secciones de motores, sellos y cables (Redalene/Redahot ya citados en la base).

**Cobertura actual: mínima.** De la base, solo GN-4000 y GN-5600
corresponden a la nomenclatura de este catálogo; las otras 5 bombas Reda
(D-40, D-55, D-82, G-52E, D-20) son los modelos históricos del libro de
Brown (1980), que no figuran acá. **Este catálogo puede además reemplazar
las fuentes "estimado/por confirmar"** de motores y sellos Reda.

### 2. alkhorayef-esp-catalog-2019.pdf — 96 páginas, 2019, texto extraíble ✅
**Fabricante NUEVO** (no está en la base). Catálogo completo y muy
estructurado: bombas WA-xxx con ficha por modelo (rango óptimo, rango
floater, BEP, housing, casing mínimo, presión, eje), más intakes,
motores, protectores, sensores (gauges), cable y transformadores.
Ejemplo: WA-550, serie 338, 200–700 BPD, BEP 552 BPD.

**Cobertura actual: nula. Es el candidato ideal para la primera
importación real**: texto limpio, datos tabulados, fabricante completo.

### 3. Wood Group ESP (2003) — 5 archivos, texto extraíble ✅
**Fabricante NUEVO.** Los PDFs chicos son capítulos de su catálogo:

| Archivo | Contenido | Valor para la base |
|---|---|---|
| `Transformers.pdf` | Transformadores trifásicos y para VSD, 37.5–1000 kVA con tensiones | **Puebla `transformers.xlsx` con datos reales** — hoy solo hay 8 genéricos ≤300 kVA; esto agrega unidades hasta 750/1000 kVA con fabricante |
| `Swbd-Mtr Cntrl.pdf` | Switchboards 600–3600 V con part numbers | **Puebla `switchboards.xlsx`** (hoy vacía — hallazgo H5) |
| `Cable.pdf` | Motor lead cable (MLC) serie 300 + specs | Complementa `cables`; el MLE es justo el componente que `installation_components` modela |
| `Seals.pdf` | Guías de aplicación de sellos (bags HSN/Viton/Aflas) | Cualitativo: criterios de selección, más que registros |
| `Spl Products-Services.pdf` | Bombas especiales (WAG anticorrosión) | Nicho; baja prioridad |

### 4. Pump Curves-400.pdf — 44 páginas (Wood Group, serie 400)
Curvas de rendimiento como gráficos. El texto extraíble es mínimo
(las curvas son imágenes): la carga requiere lectura visual página por
página o digitalización manual. Factible pero laborioso.

### 5. Borets - ESP - Systems.pdf — 2 páginas ⚠️
Folleto comercial general: sin tablas de modelos, sin curvas, sin specs.
**Fabricante nuevo pero sin datos cargables.** Si querés incluir Borets,
hay que conseguir su catálogo técnico completo.

### 6. Centrilift-flexpump-series-pumps-slsh.pdf — 2 páginas ⚠️
Folleto de la línea FLEXPump: aplicaciones y beneficios, sin tablas de
curvas. Las 7 bombas Centrilift de la base son los modelos históricos de
Brown; este folleto no permite modernizarlas.

### 7. Carpeta ChampionX (data sheets) ✅ ya representada
Los motores serie 400, cable CAVALCADE EPDM, sellos VIGIL, separadores
WHIRLAWAY y sensores ACE **ya están en la base** (fuentes CHX-xx en
`data_sources.xlsx`), con la salvedad de que varios valores están
marcados "estimado" y conviene confirmarlos contra los PDFs.

---

## Resumen ejecutivo

| Catálogo | Fabricante | ¿En la base? | Datos cargables | Prioridad sugerida |
|---|---|---|---|---|
| Alkhorayef 2019 | Nuevo | No | Bombas, motores, protectores, sensores, cable | **1 — ideal para primera importación** |
| Wood Group Transformers + Swbd | Nuevo | No | Transformadores reales + switchboards | **2 — llena dos tablas vacías/genéricas** |
| REDA 2007 | Parcial (2/29 bombas) | Mínima | Todo el line-up moderno Reda | **3 — el más grande; por etapas** |
| ChampionX data sheets | Sí | Sí | Confirmar valores "estimado" | 4 — validación |
| Pump Curves-400 | Nuevo (WG) | No | Curvas serie 400 (gráficos) | 5 — manual |
| Centrilift FLEXPump | Parcial | Folleto | Nada tabulado | — |
| Borets | Nuevo | No | Nada tabulado | — (conseguir catálogo técnico) |

**Conclusión de arquitectura:** ninguna importación requiere tocar el
esquema v3 — todos los contenidos entran como filas nuevas en tablas
existentes (`manufacturers`, `pumps`+curvas+housings, `motors`, `seals`,
`cables`, `transformers`, `switchboards`, `sensors`). Exactamente el
objetivo de diseño: crecer agregando datos, no código.

**Nota VSD:** ningún catálogo de la carpeta trae variadores de frecuencia
con specs; `vsds.xlsx` seguirá vacía hasta conseguir ese material.
