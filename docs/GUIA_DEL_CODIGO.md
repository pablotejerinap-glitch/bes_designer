# Guía del código — cómo encontrar y revisar una fórmula

Esta guía está escrita para alguien que **sabe de ingeniería de petróleo pero no
programa**. No hace falta entender Python para revisar los cálculos.

---

## Lo primero: probablemente no necesites abrir el código

La aplicación tiene una pestaña **«Fórmulas»** que lista las **82 fórmulas** que
ejecuta el motor de cálculo, cada una con:

- la expresión en símbolos, como está en el libro;
- qué significa cada símbolo, con su unidad;
- la cita bibliográfica (Brown, Beggs, Vogel, Fetkovich…);
- las condiciones de validez;
- y en qué archivo se ejecuta, por si querés ir a verlo.

Esa lista **se genera desde el propio código**, así que no puede decir una cosa
y el programa hacer otra. Es la manera recomendada de revisar el motor.

Para verla: levantar la app y entrar a la pestaña «Fórmulas». O pedir
`GET /api/formulas`, que devuelve lo mismo en JSON.

### Por qué la pantalla muestra más de lo que corre un pozo

Cuando se calcula un pozo concreto, sólo se ejecuta **un** camino: si el
reservorio se resolvió por Vogel, Fetkovich no se ejecutó. La pestaña
«Fórmulas» muestra **todas las variantes**, hayan corrido o no — las cuatro
maneras de llegar a la Pwf y las dos correlaciones de fricción conviven ahí.

Si además hay un diseño calculado, las que efectivamente corrieron aparecen
marcadas y con los números de ese pozo puestos en la fórmula.

---

## Si querés abrir el código igual

### Cómo está organizado

```
backend/src/bes/
    core/          ← LOS CÁLCULOS. Es acá donde está la ingeniería.
    catalogs/      ← los equipos: bombas, motores, cables, sellos
    recommender/   ← cómo se ordenan las alternativas
    services/      ← coordina los cálculos
    api/           ← la conexión con la pantalla
    plotting/      ← los gráficos
    reports/       ← el PDF y el Excel
frontend/          ← la pantalla (no tiene cálculos)
```

**Toda la ingeniería vive en `core/`.** El resto es plomería: transporta datos,
los muestra y los imprime, pero no calcula nada.

### Qué archivo tiene qué

| Archivo en `core/` | Qué resuelve |
|---|---|
| `ipr.py` | Cuánto entrega el reservorio y a qué presión de fondo (Vogel, Lineal, Fetkovich) |
| `pvt.py` | Propiedades del fluido: Rs, Bo, Bg, Bw, densidades, viscosidades |
| `multiphase.py` | Poettmann & Carpenter — gradiente de presión, PIP, presión de descarga |
| `tdh.py` | La altura total que tiene que dar la bomba |
| `pump_design.py` | Cuántas etapas y cuánta potencia |
| `viscosity.py` | Crudos pesados: procedimiento de Riling y láminas 4L |
| `gas_handling.py` | Pozos con gas: método de incrementos de presión |
| `affinity.py` | Leyes de afinidad (cambio de frecuencia o diámetro) |
| `electrical.py` | Motor, sello, cable, caída de tensión, transformador |
| `mechanical.py` | Verificación de eje y cojinete de empuje |
| `housing.py` | Carcasas y presión de reventamiento |
| `models.py` | El vocabulario: qué es cada dato de entrada |
| `metric_design.py` | El método de cátedra «ESP 01», en unidades métricas |
| `formula_catalog.py` | **La declaración de las 82 fórmulas** |

### Cómo leer un archivo de `core/`

Todos siguen la misma estructura. Arriba de todo hay un bloque entre comillas
triples que explica:

1. **qué resuelve el archivo**, en castellano llano;
2. **las fórmulas principales**, escritas como en el libro;
3. **Contenido** — el mapa numerado de lo que hay adentro y en qué orden;
4. **Nomenclatura** — cada símbolo con su unidad;
5. **Referencias** — de dónde sale cada cosa.

Después vienen las funciones. Cada una arranca con su propio bloque explicativo:
qué calcula, la fórmula, qué recibe (`Args`), qué devuelve (`Returns`) y cuándo
falla (`Raises`).

**Todo eso son comentarios: no son código que se ejecuta.** El código son las
líneas de abajo, que suelen ser dos o tres.

Ejemplo real, de `tdh.py`:

```python
def friction_loss_hazen_williams(q_bpd, pipe_id_in, length_ft, c_factor=120.0):
    """Pérdida de carga por fricción en el tubing — Hazen-Williams.

    Es la fórmula **monofásica**: vale cuando lo que sube por el tubing se
    puede tratar como líquido, o sea con poco gas libre::

        H_fric = 0.2083 · (100/C)^1.852 · q^1.852 / d^4.8655 · L/100

    Fijarse en los exponentes: la pérdida crece casi con el **cuadrado del
    caudal** y baja con la **quinta potencia del diámetro**.

    Args:
        q_bpd: Caudal [STB/d].
        pipe_id_in: Diámetro interior de la cañería [in].
        length_ft: Largo de la cañería [ft].
        c_factor: Coeficiente de rugosidad (120 = acero de diseño).

    Returns:
        Pérdida de carga total por fricción [ft].
    """
    q_gpm = q_bpd * 42.0 / 1440.0
    return (
        0.2083
        * (100.0 / c_factor) ** 1.852
        * q_gpm ** 1.852
        / pipe_id_in ** 4.8655
        * length_ft / 100.0
    )
```

La fórmula del comentario y la cuenta de abajo son la misma. **Eso es lo que hay
que verificar.**

La primera línea de la cuenta convierte el caudal de barriles por día a galones
por minuto, que es la unidad en la que Hazen-Williams pide el caudal:
42 galones por barril, 1440 minutos por día.

---

## Los símbolos de Python que aparecen en las fórmulas

| En el código | Quiere decir |
|---|---|
| `*` | multiplicación |
| `/` | división |
| `**` | potencia — `q ** 1.852` es q elevado a la 1,852 |
| `math.ceil(x)` | redondeo **hacia arriba** |
| `min(a, b)` / `max(a, b)` | el menor / el mayor de los dos |
| `abs(x)` | valor absoluto |
| `\` al final de una línea | la fórmula sigue en la línea siguiente |
| `#` | comentario: todo lo que sigue no se ejecuta |
| `1e-6` | notación científica: 1 × 10⁻⁶ |

---

## Los tres controles que impiden que el código mienta

### 1. La fórmula se declara una sola vez

Está en `core/formula_catalog.py`. El código que calcula **no vuelve a escribir
la expresión**: la referencia por su nombre y aporta sólo los números. Si
estuviera escrita en dos lugares, podrían decir cosas distintas.

### 2. Hay tests que atan el catálogo al motor, en los dos sentidos

`backend/tests/test_formula_catalog.py` verifica que:

- toda fórmula que el motor ejecuta **esté declarada** — nada corre sin poder
  auditarse;
- toda fórmula declarada **la ejecute alguien** — el catálogo no es una lista de
  deseos;
- cada fórmula tenga glosario de símbolos, cita, unidades y módulo.

### 3. Los cálculos se validan contra ejemplos numerados del libro

| Ejemplo | Bomba | Caudal | TDH | Etapas |
|---|---|---:|---:|---:|
| #1A | Centrilift I-300 | 10 000 bpd | 1 670 ft | 28 |
| #2A | Reda D-40 | 1 227 bpd | 5 830 ft | 254 |
| #2B | Centrilift I-42B | ~2 080 bpd | 4 258 ft | 112 |

Más el ejercicio de cátedra de crudos viscosos, que la app reproduce entrando
sólo con °API, temperatura y gas en solución: 151,9 cp / 68,7 cp / 327,2 SSU
contra 150 / 68 / 325 del libro.

En total hay **1 098 verificaciones automáticas**. Si alguien cambia una fórmula
y rompe un resultado del libro, el sistema avisa.

---

## Dónde está documentado el resto

| Documento | Qué cubre |
|---|---|
| `docs/FORMULAS.md` | Compendio de fórmulas en texto corrido, para leer de una |
| `docs/CRUDOS_VISCOSOS.md` | El procedimiento de Riling paso por paso |
| `docs/METHODOLOGY.md` | Metodología general y el método de cátedra (§7) |
| `docs/EJEMPLO_3B_BROWN.md` | El ejemplo #3B y sus desvíos, documentados |
| `docs/EJEMPLO_ESP01.md` | El ejercicio ESP 01 resuelto |

> **Ojo:** `FORMULAS.md` se escribe a mano y puede quedar atrasado. La fuente
> autoritativa es el catálogo de la pestaña «Fórmulas», que se genera del código.

---

## Si encontrás un error en una fórmula

Anotá **la clave de la fórmula** (aparece en la pestaña «Fórmulas», por ejemplo
`pwf_vogel_bifasico` o `friccion_hazen_williams`) y qué debería decir. Con la
clave se ubica en un paso tanto la declaración como el lugar donde se ejecuta.
