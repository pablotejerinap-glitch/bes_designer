# BES Designer — Guía de Usuario

**Versión:** 1.0.0 (Fase 12)  
**Referencia:** Kermit Brown, *The Technology of Artificial Lift Methods*, Vol. 2b, Cap. 4.5

---

## 1. Requisitos del Sistema

| Componente | Versión mínima |
|---|---|
| Python | 3.10 o superior |
| pip | 22.0 o superior |
| Sistema operativo | Windows 10/11, macOS 12+, Ubuntu 20.04+ |
| RAM | 2 GB (4 GB recomendado) |
| Espacio en disco | 500 MB (incluye entorno virtual) |

---

## 2. Instalación Paso a Paso

### 2.1 Obtener el código

```bash
# Opción A — clonar desde repositorio
git clone https://github.com/placeholder/bes_designer.git
cd bes_designer

# Opción B — descomprimir el zip
unzip bes_designer.zip
cd bes_designer
```

### 2.2 Crear el entorno virtual

```bash
# Crear entorno
python -m venv .venv

# Activar en Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Activar en Windows (cmd)
.venv\Scripts\activate.bat

# Activar en macOS / Linux
source .venv/bin/activate
```

### 2.3 Instalar dependencias

```bash
pip install -r requirements.txt
```

Las dependencias instaladas son:

| Paquete | Uso |
|---|---|
| fastapi + uvicorn | API HTTP |
| numpy, scipy | Cálculo numérico |
| pandas | Manejo de datos tabulares |
| matplotlib, plotly | Gráficos |
| reportlab | Generación de PDF |
| openpyxl | Generación de Excel |
| pytest | Suite de tests |

### 2.4 Verificar la instalación

```bash
# Correr la suite de tests para verificar que todo funciona
pytest tests/ -v
```

Se esperan 400+ tests en verde. Si alguno falla, verificar que las dependencias se instalaron correctamente.

---

## 3. Iniciar la Aplicación

```bash
# Desde el directorio del proyecto
uvicorn bes.api.main:app --port 8000   # backend
cd frontend && npm run dev             # frontend en :5173
```

La aplicación se abrirá automáticamente en el navegador en `http://localhost:8501`.

Para detenerla: `Ctrl + C` en la terminal.

---

## 4. Guía de Uso por Sección

### 4.1 📝 Datos del Pozo

Primera sección a completar. Contiene **5 pestañas**:

#### Pestaña: Reservorio
| Campo | Descripción | Unidad |
|---|---|---|
| Presión estática | Presión promedio del reservorio (Pr) | psi |
| Punto de burbuja | Presión de burbuja del fluido (Pb) | psi |
| Ensayo · Pwf medida | Presión de fondo fluyente del ensayo estabilizado | psi |
| Ensayo · caudal medido | Caudal bruto de líquido del mismo ensayo | STB/d |
| Método IPR | Correlación a aplicar | — |
| Temperatura | Temperatura estática de fondo | °F |
| Longitud del caño | Profundidad de referencia de las presiones | ft TVD |
| Mecanismo de empuje | Fuente de energía del reservorio | — |

> **El índice de productividad no se carga.** Se deriva del ensayo con el método
> IPR elegido y se muestra en solo lectura, junto al draw-down y al AOF, en el
> bloque "Derivado del ensayo". Es la magnitud que efectivamente se mide en el
> pozo la que entra al cálculo. Con el método **Fetkovich** hay que cargar además
> el exponente *n*: un ensayo de un solo punto no permite ajustar *C* y *n* a la
> vez, así que la app despeja *C* y muestra el valor resultante.

**Métodos IPR disponibles:**
- **LINEAR**: Darcy / línea recta (arriba del punto de burbuja)
- **VOGEL**: Correlación de Vogel (drive por gas en solución)
- **FETKOVICH**: IPR empírica de Fetkovich

#### Pestaña: Fluido
Propiedades PVT del crudo producido: gravedad API, corte de agua, GOR, gravedades específicas de gas y agua, viscosidad, contenidos de H₂S y CO₂.

> **Nota:** Para pozos de agua pura, usar water_cut = 1.0, GOR = 0 y cualquier valor de API en [5, 70].

#### Pestaña: Geometría
Dimensiones del pozo: profundidad total, diámetros de casing y tubing, intervalo de perforaciones, temperatura en cabezal y BHT.

**Tablas de referencia disponibles:** Al seleccionar OD y peso del casing, la app muestra el ID típico (drift) según la norma API.

#### Pestaña: Superficie
Condiciones en superficie: presión mínima en cabezal (WHP), flowline (longitud, diámetro, elevación), presión del separador, voltaje disponible y frecuencia de red.

#### Pestaña: Objetivos
Tasa objetivo (STB/d), GIP máximo permitido, margen de seguridad en profundidad de bomba, vida útil de diseño, opción de variador de velocidad (VSD) y el umbral de gas que elige la correlación de pérdida de carga.

> **Gas para usar Poettmann-Carpenter.** La app calcula la fracción de gas libre
> en la admisión *antes* del TDH y con ella elige cómo computar la pérdida de
> carga en el tubing: por debajo del umbral usa Hazen-Williams (flujo
> monofásico), por encima usa Poettmann-Carpenter para flujo multifásico
> vertical. El default es 0.10. La correlación efectivamente usada aparece en
> la tabla de resultados de cada opción.

> **Frecuencia de diseño (VSD).** Al activar el variador aparece un campo para
> fijar la frecuencia a la que va a girar la bomba. Vacío = la frecuencia de red
> de la pestaña Superficie. La curva de catálogo se reescala a esa frecuencia
> con las leyes de afinidad **antes** de elegir la bomba, así que a 50 Hz el
> rango operativo, las etapas y el HP son los que corresponden.

#### Botones de acción

| Botón | Acción |
|---|---|
| 📥 Cargar Ejemplo 2A | Carga el ejemplo de pozo de petróleo estándar (Brown §4.5) |
| 📥 Cargar Ejemplo 3A | Carga el ejemplo de pozo con alta producción de gas |
| 💾 Guardar Datos | Valida e guarda todos los campos; habilita el diseño |

---

### 4.2 ⚙️ Diseño BES

Una vez guardados los datos del pozo, hacer clic en **"🚀 Calcular Diseño BES"**.

El motor evalúa cada bomba del catálogo y selecciona las **mejores 3 opciones**, mostrando para cada una:

- **TDH** (Total Dynamic Head) y su desglose (elevación vertical, fricción en tubing, cabezal)
- **Selección de bomba:** modelo, OD, número de etapas, eficiencia, HP
- **Carcasas (pump housings):** la combinación se elige automáticamente — no se
  carga a mano. La tabla muestra cada carcasa de la admisión a la descarga con
  sus etapas, código y material (si el catálogo los publica), las etapas activas
  acumuladas, la presión calculada, la admisible y el resultado de la
  verificación, más una justificación de por qué se eligió esa combinación. Un
  arreglo que supere la presión admisible nunca se ofrece: esa bomba se descarta
- **Diseño del motor:** modelo, HP, voltaje, amperaje
- **Diseño del cable:** tipo, calibre AWG, caída de tensión, voltaje en superficie
- **Transformador:** potencia en kVA recomendada
- **Gas en bomba (GIP):** fracción estimada de gas libre en la admisión
- **Advertencias:** flags para revisión del ingeniero

Las opciones se presentan en **tabs**, ordenadas por criterios de ingeniería.

**Criterios de ordenamiento**, en orden estricto de prioridad (sin puntajes ni
pesos configurables):
1. **Cercanía al BEP** — `|q − q_BEP| / q_BEP`, de menor a mayor
2. **Eficiencia hidráulica** en el punto operativo, de mayor a menor
3. **Potencia requerida** en el eje, de menor a mayor

El criterio 2 solo desempata igualdades del 1, y el 3 solo igualdades de los
dos primeros. El fabricante se muestra como información y **no** interviene en
el orden. La etiqueta de distancia al BEP (≤ 10 % "muy cerca", ≤ 25 %
"moderadamente alejado", > 25 % "alejado") es solo visual.

---

### 4.3 📊 Comparación de Opciones

Presenta las opciones calculadas en una tabla comparativa con:
- Los tres criterios de ordenamiento por opción, con sus valores crudos
- Tabla lado a lado con los parámetros clave
- Distancia al BEP de cada opción respecto a la primera, en puntos porcentuales

Útil para tomar la decisión final cuando hay varias opciones similares.

---

### 4.4 📈 Análisis de Sensibilidad

Permite variar parámetros del reservorio y el fluido (Pr, WC, GOR, tasa objetivo) dentro de un rango definido y ver cómo cambian:
- TDH
- Número de etapas
- HP total
- Eficiencia del sistema

El gráfico muestra la curva de sensibilidad y marca el punto de diseño base.

---

### 4.5 🔁 Leyes de afinidad

Sección independiente del diseño: un banco de pruebas sobre la curva de catálogo
de cualquier bomba. Se elige la bomba, se marcan las frecuencias a comparar
(40–70 Hz) y opcionalmente se ajusta el diámetro del impulsor (D₂/D₁) y la
gravedad específica del fluido (SG₂/SG₁).

Muestra la familia de curvas superpuestas y una tabla con, por frecuencia: la
relación de velocidad N₂/N₁, las rpm del eje, el rango operativo desplazado, el
BEP, y el head, HP y eficiencia por etapa.

Si se carga un **caudal objetivo**, además despeja la frecuencia que lleva el BEP
de esa bomba a ese caudal (f₂ = f₁·Q₂/Q₁) — la pregunta típica de un diseño con
variador.

> **Qué esperar.** Al bajar la frecuencia el caudal cae en proporción directa
> pero la altura cae con el cuadrado, así que reducir velocidad no sale gratis en
> capacidad de elevación. La eficiencia no cambia: es invariante ante el cambio
> de velocidad.

---

### 4.6 📥 Descargar Reportes

Al final de la sección **Diseño BES**, aparecen tres botones de descarga:

| Botón | Contenido | Formato |
|---|---|---|
| 📕 Descargar PDF | Reporte completo de diseño (portada, inputs, TDH, bomba, eléctrico, advertencias) | PDF |
| 📗 Descargar Excel | 6 hojas: Resumen, Inputs, TDH, Bomba, Eléctrico, Advertencias | XLSX |
| 💾 Guardar Caso JSON | Todos los datos de entrada + resultado de diseño en formato reutilizable | JSON |

> El JSON generado puede reimportarse manualmente recreando los objetos Python correspondientes.

---

## 5. Flujo de Trabajo Típico

```
1. Ingresar datos del pozo (5 tabs) → Guardar Datos
2. Ir a "Diseño BES" → Calcular
3. Revisar las 3 opciones → seleccionar la más adecuada
4. Verificar Comparación de Opciones para confirmar elección
5. Opcionalmente: Análisis de Sensibilidad para evaluar robustez
6. Descargar reporte PDF/Excel para documentación
```

---

## 6. Metodología de Cálculo

| Módulo | Método implementado |
|---|---|
| **IPR** | Vogel (1968), Linear (Darcy), Fetkovich (1973) |
| **PVT** | Standing (1947): Bo, Rs, Pb; Dranchuk-Abou-Kassem (1975): z-factor |
| **Presión de admisión** | Hagedorn-Brown (1965), Beggs-Brill (1973) |
| **TDH** | Hazen-Williams (fricción) + columna hidrostática (Brown §4.5324) |
| **Corrección por viscosidad** | Hydraulic Institute (HI) standard |
| **Etapas** | ceil(TDH / head_per_stage) con interpolación lineal de curva |
| **HP de la bomba** | stages × hp/stage × SG_fluido |
| **Motor** | Selección por HP ≥ pump_HP × 1.15, OD < ID casing |
| **Cable** | Selección por AWG, longitud, tipo (EPDM/Polypro) |
| **Transformador** | Potencia en kVA con factor de servicio 1.25 |
| **Gas en bomba (GIP)** | Método de volumenes a condiciones de admisión (Brown §4.53103) |
| **Ordenamiento** | Lexicográfico: 1. cercanía al BEP, 2. eficiencia, 3. menor potencia. Sin pesos ni preferencia de proveedor |

---

## 7. Ejemplos Predefinidos

### Ejemplo 2A — Pozo de Petróleo Estándar
Basado en Brown Vol. 2b §4.5, Example 2A.
- Casing 5-1/2", profundidad ~6 100 ft
- Crudo 30 °API, 15 % de agua, GOR bajo
- Sin gas libre en la admisión de la bomba
- Tasa objetivo: 1 000 STB/d

### Ejemplo 3A — Pozo con Alta Producción de Gas
Basado en Brown Vol. 2b §4.5, Example 3A.
- Casing 5-1/2", profundidad 7 000 ft
- Crudo 35 °API, 50 % de agua, GOR alto
- Reservorio severamente depletado: Pb >> Pr
- Alta fracción de gas libre en admisión (GIP > 30 %)
- Tasa objetivo: 700 STB/d

---

## 8. Solución de Problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| "Primero completá y guardá los datos del pozo" | Datos no guardados | Ir a Datos del Pozo → hacer clic en 💾 Guardar Datos |
| "No se encontró diseño válido" | Sin bomba compatible en catálogo | Ampliar max_gip, revisar tasa objetivo o tamaño de casing |
| PDF genera error | reportlab no instalado | `pip install reportlab` |
| Excel genera error | openpyxl no instalado | `pip install openpyxl` |
| La app no abre el navegador | Puerto 5173 en uso | `npm run dev -- --port 5174` |
| Tests fallan | Dependencias desactualizadas | `pip install -r requirements.txt --upgrade` |
| Advertencia "bubble_point > static_pressure" | Reservorio depletado | Normal para drive por gas en solución; Vogel aplica |

---

## 9. Ejecutar los Tests

```bash
# Suite completa (400+ tests)
pytest tests/ -v

# Solo tests de integración (ejemplos del libro)
pytest tests/test_integration.py -v

# Tests de un módulo específico
pytest tests/test_ipr.py -v
pytest tests/test_tdh.py -v
```

---

## 10. Validación contra el Libro

Para generar la tabla de comparación entre los resultados de la app y los valores de referencia de Kermit Brown:

```bash
python scripts/validate_all_examples.py
```

El resultado se guarda en `docs/VALIDATION.md`.

---

## 11. Créditos y Referencias

| Ítem | Detalle |
|---|---|
| **Herramienta** | BES Designer v1.0.0 |
| **Autor** | Proyecto de tesis de grado — Ingeniería de Petróleo |
| **Referencia principal** | Brown, K.E. (1984). *The Technology of Artificial Lift Methods, Vol. 2b*. PennWell Books. |
| **IPR** | Vogel, J.V. (1968). SPE-1476. *J. Petroleum Technology*, 20(1), 83–92. |
| **PVT** | Standing, M.B. (1947). *API Drilling and Production Practice*. |
| **z-factor** | Dranchuk, P.M. & Abou-Kassem, H. (1975). *J. Canadian Petroleum Technology*. |
| **Multifásico** | Hagedorn, A.R. & Brown, K.E. (1965). *J. Petroleum Technology*. |
