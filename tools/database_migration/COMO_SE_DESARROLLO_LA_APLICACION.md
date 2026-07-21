# Cómo se desarrolló BES Designer

## Explicación para quien no sabe programación

---

## 1. Qué es la aplicación, en una frase

BES Designer es un programa que hace, en segundos y sin errores de
cuenta, el mismo procedimiento de diseño de bombeo electrosumergible
que un ingeniero hace a mano con el libro de Kermit Brown, las
planillas y los catálogos de fabricantes: recibe los datos del pozo y
devuelve el equipo recomendado (bomba, número de etapas, motor, cable,
sello, separador de gas y transformador), comparando alternativas y
justificando cada elección.

## 2. La idea central: separar el MÉTODO de los DATOS

Todo el desarrollo se ordenó alrededor de una distinción simple:

**El método** es el procedimiento de diseño: las fórmulas y criterios
que enseña la bibliografía (Brown, las correlaciones PVT, el cálculo de
TDH, la selección por eficiencia). El método no cambia si mañana
aparece un fabricante nuevo. Por eso vive "escrito en el programa",
igual que un procedimiento vive escrito en un manual — y cada fórmula
lleva su cita bibliográfica, como en la tesis.

**Los datos** son los catálogos: qué bombas existen, sus curvas de
rendimiento, los motores con sus voltajes, los cables con su caída de
tensión. Esto cambia todo el tiempo (fabricantes nuevos, modelos
nuevos). Por eso vive FUERA del programa, en una base de datos con
archivos Excel que cualquier ingeniero puede abrir, leer y corregir
sin saber programar.

La consecuencia práctica: **para agregar un fabricante no se toca el
programa** — se agregan filas en los Excel. Lo demostramos con
Alkhorayef: entraron 37 bombas nuevas con sus curvas y el programa
las empezó a recomendar sin modificar una sola línea de su lógica.

## 3. Cómo está organizado el programa (la analogía de la planta)

El programa está dividido en "sectores", como una planta de proceso
donde cada sector hace una sola cosa y le pasa su producto al
siguiente:

1. **Entrada de datos**: el usuario carga el pozo (presiones,
   temperaturas, casing, fluido, caudal objetivo) en pantallas simples.
2. **Cálculos de yacimiento**: con esos datos se calcula cuánto puede
   aportar el pozo (curva IPR) y las propiedades del fluido a cada
   presión y temperatura (PVT).
3. **Cálculos hidráulicos**: se calcula la presión en la admisión de la
   bomba y la altura total que hay que vencer (TDH), con las mismas
   fórmulas del libro.
4. **Selección de equipos**: el programa consulta la base de datos,
   descarta lo que no entra en el casing o no cubre el caudal, calcula
   etapas y potencia para cada bomba candidata, y elige motor, cable,
   sello y transformador compatibles.
5. **Recomendación**: las alternativas se puntúan (eficiencia, cercanía
   al punto de máxima eficiencia, preferencia de fabricante) y se
   presentan las mejores, con su justificación.
6. **Resultados**: pantallas con gráficos y un reporte Excel
   descargable.

Cada sector se puede revisar, corregir o mejorar sin tocar los demás —
igual que en una planta se interviene una unidad sin parar el resto.

## 4. Cómo sabemos que calcula bien: los ensayos automáticos

Acá está el corazón de la confiabilidad. El programa tiene **663
ensayos automáticos** ("tests"): pequeñas pruebas que se ejecutan todas
juntas con un solo comando y verifican, una por una, que cada cálculo
da lo que tiene que dar.

Los más importantes son los **ejemplos resueltos del libro de Brown**:
el Ejemplo 2A del libro da TDH = 5.830 pies y 254 etapas con la bomba
Reda D-40; el ensayo automático corre el programa con esos mismos datos
y verifica que dé exactamente eso. Si alguna modificación futura
rompiera un cálculo, el ensayo falla inmediatamente y avisa.

Es el equivalente a validar un instrumento contra un patrón de
laboratorio: cada vez que se cambia algo, se re-valida TODO contra los
patrones (el libro) en menos de medio minuto.

## 5. Cómo se construyó la base de datos

La base de datos se construyó en etapas, cada una verificada antes de
seguir:

**Etapa 1 — Sacar los datos del programa.** Los catálogos estaban
mezclados con el código (en archivos internos). Se migraron a archivos
Excel organizados como tablas relacionadas: una tabla de fabricantes,
una de bombas, una de curvas (punto por punto), una de motores, etc.
Un programa verificador comparó campo por campo que los 132 registros
migrados fueran idénticos a los originales.

**Etapa 2 — Auditoría y diseño profesional.** Se revisó el diseño con
criterios de ingeniería de datos (formas normales, claves, relaciones)
y se corrigieron problemas reales — por ejemplo, la caída de tensión
de los cables estaba repetida en varios lugares y se llevó a una sola
tabla física. Todo el modelo quedó documentado en un diagrama
entidad-relación (el "plano" de la base de datos).

**Etapa 3 — Incorporar un catálogo real.** Del catálogo PDF de
Alkhorayef (96 páginas) se extrajeron automáticamente las fichas de
las 37 bombas. Las curvas de rendimiento, que el fabricante publica
como gráficos, se convirtieron en números con una técnica de lectura
de imagen: el programa reconoce cada curva por su color, calibra los
ejes leyendo los números del gráfico, y toma ~10 puntos por curva.

**Control de calidad físico:** cada curva digitalizada se validó con
la identidad hidráulica (la eficiencia debe ser igual a
Q·H·γ / (135.773 · HP) en cada punto — si la lectura fuera mala, la
ecuación no cierra) y verificando que el pico de eficiencia caiga en
el caudal de máxima eficiencia que declara la ficha. La tolerancia
usada es coherente con el estándar API (±5 % en altura, ±8 % en
potencia). Este control incluso detectó una inconsistencia del propio
catálogo del fabricante.

**Trazabilidad:** cada número de la base tiene una columna que indica
su fuente (libro, catálogo, norma), con un registro bibliográfico de
49 fuentes. Ningún dato queda sin cita — el mismo criterio que exige
una tesis.

## 6. Cómo se conectó la base al programa

El programa habla con la base de datos a través de una sola "ventanilla"
(una pieza de código que sabe leer los Excel y entregar los datos en el
formato que los cálculos esperan). Cambiar de almacenamiento — de los
archivos internos viejos a Excel hoy, de Excel a una base SQLite
mañana — es cambiar la ventanilla, nunca los cálculos.

Cuando se hizo el cambio definitivo, la prueba fue simple y
contundente: se corrieron los 663 ensayos automáticos con la base
nueva. Todos pasaron.

## 7. Las herramientas usadas (sin entrar en detalle)

* **Python**: el lenguaje de programación, estándar en ingeniería y
  ciencia de datos.
* **Streamlit**: la herramienta que convierte el programa en una
  aplicación con pantallas, sin necesidad de desarrollar una página
  web desde cero.
* **Excel** como base de datos de desarrollo (editable por ingenieros)
  y **SQLite** como destino futuro (una base de datos formal que vive
  en un solo archivo).
* **pytest**: el sistema que ejecuta los 663 ensayos automáticos.

## 8. Resumen del proceso de desarrollo, en cinco líneas

1. Se implementó el método de Brown en módulos separados por
   responsabilidad, cada fórmula con su cita.
2. Cada cálculo se validó contra los ejemplos resueltos del libro,
   y esa validación quedó automatizada (663 ensayos).
3. Los datos de ingeniería se sacaron del código y se organizaron en
   una base de datos Excel normalizada, documentada y auditada.
4. Se incorporó un fabricante real completo (Alkhorayef) solo
   agregando datos — cero cambios de programa — incluyendo la
   digitalización de sus curvas con control de calidad físico.
5. La aplicación quedó conectada a la base nueva, con los 663 ensayos
   en verde como evidencia de que nada se alteró.

El resultado es una herramienta que crece agregando conocimiento
(datos, catálogos, pozos) sin reescribir su ingeniería — y en la que
cada número puede rastrearse hasta su fuente.
