"""
Catálogo de fórmulas del motor de cálculo.

**Es la única declaración de cada fórmula del proyecto.** El código que calcula
no vuelve a escribir la expresión: la referencia por su clave y aporta sólo los
números (ver :mod:`bes.core.formulas`). Así la fórmula que se muestra en
pantalla es, por construcción, la que se ejecutó — no hay dos lugares que puedan
decir cosas distintas.

Para qué existe: que un ingeniero de petróleo pueda auditar el motor **sin abrir
un archivo .py**. Cada entrada trae la fórmula en símbolos, qué significa cada
símbolo con su unidad, la unidad del resultado, la cita del libro y las
condiciones de validez.

Se enumera sin correr ningún diseño (``GET /api/formulas``), de modo que se ven
también las variantes que un caso concreto no ejecutó: el profesor puede revisar
Fetkovich aunque el pozo se haya resuelto por Vogel.

Cómo agregar una fórmula:

1. Declararla acá con clave única, tema, símbolos y cita.
2. En el código que calcula, ``trace.add("clave", {...}, resultado)``.
3. ``tests/test_formula_catalog.py`` verifica que toda clave usada exista y que
   todo símbolo de la expresión esté documentado.

**No se declara una fórmula que el motor no ejecute**, y no se ejecuta una que no
esté declarada: son las dos mitades de la misma regla.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


# --------------------------------------------------------------------------
# Temas
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Topic:
    """Un capítulo del motor, tal como lo agruparía un libro de la materia.

    Attributes:
        key: Identificador estable.
        label: Nombre del tema en castellano.
        blurb: Qué resuelve, en una línea.
        instrumented: ``False`` mientras el tema todavía no emita traza. Se
            declara igual para que la pantalla muestre la cobertura real en vez
            de esconder lo que falta.
    """

    key: str
    label: str
    blurb: str
    instrumented: bool = True


TOPICS: tuple[Topic, ...] = (
    Topic(
        "ipr", "IPR — aporte del reservorio",
        "Cuánto entrega el reservorio y a qué presión de fondo fluyente.",
    ),
    Topic(
        "tdh", "TDH — altura dinámica total",
        "La altura que la bomba tiene que desarrollar, término por término.",
    ),
    Topic(
        "diseno", "Diseño de la bomba",
        "Etapas y potencia al eje a partir del TDH y la curva de catálogo.",
    ),
    Topic(
        "viscosidad", "Crudos viscosos",
        "Corrección de la curva de la bomba por viscosidad (Riling).",
    ),
    Topic(
        "gas", "Pozo con gas — método de incrementos",
        "La bomba resuelta tramo por tramo cuando el caudal volumétrico no es "
        "constante.",
    ),
    Topic(
        "pvt", "PVT — propiedades del fluido",
        "Rs, Bo, Bg, Bw, z y viscosidades según presión y temperatura.",
    ),
    Topic(
        "multifasico", "Flujo multifásico — Poettmann & Carpenter",
        "Gradiente de presión en tubing y anular; PIP y presión de descarga.",
    ),
    Topic(
        "afinidad", "Leyes de afinidad",
        "Cómo cambian caudal, altura y potencia con la velocidad y el diámetro.",
    ),
    Topic(
        "electrico", "Diseño eléctrico",
        "Motor, cable, caída de tensión, tensión en superficie y transformador.",
    ),
    Topic(
        "mecanica", "Verificación mecánica",
        "Eje, cojinete de empuje y presión de carcasa: el tope de etapas.",
    ),
)

TOPIC_ORDER: tuple[str, ...] = tuple(t.key for t in TOPICS)
TOPICS_BY_KEY: dict[str, Topic] = {t.key: t for t in TOPICS}


# --------------------------------------------------------------------------
# Declaración de una fórmula
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FormulaSpec:
    """Una fórmula del motor, declarada una sola vez.

    Attributes:
        key: Identificador único en todo el catálogo.
        topic: Tema al que pertenece (clave de :data:`TOPICS`).
        step: Paso conceptual. Varias fórmulas comparten ``step`` cuando son
            **el mismo paso resuelto por métodos distintos** —la Pwf en las
            perforaciones sale por Darcy, por Vogel o por Fetkovich— y en un
            diseño se ejecuta exactamente una. Sirve para agrupar en pantalla.
        label: Qué se calcula, en castellano.
        expression: La fórmula en símbolos, como está en el libro.
        units: Unidad del resultado.
        symbols: Cada símbolo de la expresión con su significado y unidad.
        reference: Cita bibliográfica.
        note: Condición de validez o supuesto que vale **siempre**. Lo que
            depende del caso se pasa por ``note`` en la llamada, no acá.
        module: Dónde se ejecuta, para quien sí quiera leer el código.
    """

    key: str
    topic: str
    step: str
    label: str
    expression: str
    units: str
    symbols: dict[str, str] = field(default_factory=dict)
    reference: str = ""
    note: str = ""
    module: str = ""


def _spec(*args, **kwargs) -> tuple[str, FormulaSpec]:
    s = FormulaSpec(*args, **kwargs)
    return s.key, s


# --------------------------------------------------------------------------
# El catálogo
# --------------------------------------------------------------------------
#
# Orden: el mismo en que corre un diseño. IPR -> TDH -> bomba -> (gas).

_ENTRIES: tuple[FormulaSpec, ...] = (

    # ---------------------------------------------------------------- IPR --
    # 1) Ajuste del modelo a partir del ensayo de pozo.
    FormulaSpec(
        key="ajuste_drawdown", topic="ipr", step="drawdown_ensayo",
        label="Caída de presión del ensayo (draw-down)",
        expression="Δp = Pr − Pwf", units="psi",
        symbols={
            "Pr": "Presión estática del reservorio [psia]",
            "Pwf": "Presión de fondo fluyente durante el ensayo [psia]",
        },
        reference="Brown Vol. 2b §4.522", module="bes.core.ipr",
    ),
    FormulaSpec(
        key="ajuste_j_lineal", topic="ipr", step="indice_productividad",
        label="Índice de productividad (recta de Darcy)",
        expression="J = q_ensayo / (Pr − Pwf)", units="STB/d/psi",
        symbols={
            "q_ensayo": "Caudal medido en el ensayo [STB/d]",
            "Pr": "Presión estática del reservorio [psia]",
            "Pwf": "Presión de fondo fluyente del ensayo [psia]",
        },
        reference="Brown Vol. 2b §4.522", module="bes.core.ipr",
        note="Válido con el reservorio sobre la presión de burbuja: el caudal "
             "crece en línea recta con la caída de presión.",
    ),
    FormulaSpec(
        key="ajuste_aof_lineal", topic="ipr", step="aof",
        label="AOF — caudal a Pwf = 0 (lineal)",
        expression="AOF = J · Pr", units="STB/d",
        symbols={
            "J": "Índice de productividad [STB/d/psi]",
            "Pr": "Presión estática del reservorio [psia]",
        },
        reference="Brown Vol. 2b §4.522", module="bes.core.ipr",
    ),
    FormulaSpec(
        key="ajuste_j_vogel_saturado", topic="ipr", step="indice_productividad",
        label="Índice de productividad (Vogel, reservorio saturado)",
        expression="J = 1.8 · q_max / Pr", units="STB/d/psi",
        symbols={
            "q_max": "Caudal máximo de Vogel [STB/d]",
            "Pr": "Presión estática del reservorio [psia]",
        },
        reference="Vogel, JPT (1968); Brown Vol. 2b §4.522",
        module="bes.core.ipr",
        note="Con el reservorio saturado (Pb ≥ Pr) la IPR compuesta se reduce "
             "sola a Vogel puro y no hay tramo recto.",
    ),
    FormulaSpec(
        key="ajuste_j_vogel_bajo_pb", topic="ipr", step="indice_productividad",
        label="Índice de productividad (Vogel generalizado, ensayo bajo Pb)",
        expression="J = q_ensayo / { (Pr − Pb) + (Pb/1.8)·"
                   "[1 − 0.2·(Pwf/Pb) − 0.8·(Pwf/Pb)²] }",
        units="STB/d/psi",
        symbols={
            "q_ensayo": "Caudal medido en el ensayo [STB/d]",
            "Pr": "Presión estática del reservorio [psia]",
            "Pb": "Presión de burbuja [psia]",
            "Pwf": "Presión de fondo fluyente del ensayo [psia]",
        },
        reference="Beggs, «Production Optimization», §2, Ej. 2-5B",
        module="bes.core.ipr",
        note="El ensayo cayó en el tramo curvo, así que hay que invertir la "
             "ecuación compuesta para despejar J.",
    ),
    FormulaSpec(
        key="ajuste_j_vogel_sobre_pb", topic="ipr", step="indice_productividad",
        label="Índice de productividad (Vogel generalizado, ensayo sobre Pb)",
        expression="J = q_ensayo / (Pr − Pwf)", units="STB/d/psi",
        symbols={
            "q_ensayo": "Caudal medido en el ensayo [STB/d]",
            "Pr": "Presión estática del reservorio [psia]",
            "Pwf": "Presión de fondo fluyente del ensayo [psia]",
        },
        reference="Beggs, «Production Optimization», §2, «Case 1 Procedure»",
        module="bes.core.ipr",
        note="El ensayo cayó en el tramo recto: J sale de la recta de Darcy, "
             "igual que en el método lineal.",
    ),
    FormulaSpec(
        key="ajuste_qb", topic="ipr", step="caudal_burbuja",
        label="Caudal al llegar a la presión de burbuja",
        expression="q_b = J · (Pr − Pb)", units="STB/d",
        symbols={
            "J": "Índice de productividad [STB/d/psi]",
            "Pr": "Presión estática del reservorio [psia]",
            "Pb": "Presión de burbuja [psia]",
        },
        reference="Beggs, «Production Optimization», §2", module="bes.core.ipr",
        note="Hasta acá la IPR es una RECTA: el flujo en el reservorio es "
             "monofásico. De acá para abajo se libera gas y la curva se dobla.",
    ),
    FormulaSpec(
        key="ajuste_aof_vogel", topic="ipr", step="aof",
        label="AOF — caudal a Pwf = 0 (Vogel compuesto)",
        expression="AOF = J·(Pr − Pb) + J·Pb/1.8", units="STB/d",
        symbols={
            "J": "Índice de productividad [STB/d/psi]",
            "Pr": "Presión estática del reservorio [psia]",
            "Pb": "Presión de burbuja [psia]",
        },
        reference="Beggs, «Production Optimization», §2", module="bes.core.ipr",
        note="El primer término es lo que aporta el tramo recto; el segundo, lo "
             "que agrega el tramo de Vogel de Pb hasta cero.",
    ),
    FormulaSpec(
        key="ajuste_fetkovich_c", topic="ipr", step="coef_fetkovich",
        label="Coeficiente de entregabilidad de Fetkovich",
        expression="C = q_ensayo / (Pr² − Pwf²)^n", units="STB/d/psia^(2n)",
        symbols={
            "q_ensayo": "Caudal medido en el ensayo [STB/d]",
            "Pr": "Presión estática del reservorio [psia]",
            "Pwf": "Presión de fondo fluyente del ensayo [psia]",
            "n": "Exponente de entregabilidad, entre 0.5 y 1.0 [-]",
        },
        reference="Fetkovich, SPE 4529 (1973)", module="bes.core.ipr",
        note="Un solo punto de ensayo no alcanza para ajustar C y n a la vez: "
             "n viene del ensayo isocronal, o se asume 1.0 (flujo laminar).",
    ),
    FormulaSpec(
        key="ajuste_aof_fetkovich", topic="ipr", step="aof",
        label="AOF — caudal a Pwf = 0 (Fetkovich)",
        expression="AOF = C · (Pr²)^n", units="STB/d",
        symbols={
            "C": "Coeficiente de entregabilidad [STB/d/psia^(2n)]",
            "Pr": "Presión estática del reservorio [psia]",
            "n": "Exponente de entregabilidad [-]",
        },
        reference="Fetkovich, SPE 4529 (1973)", module="bes.core.ipr",
    ),

    # 2) Pwf de diseño: el caudal objetivo, al revés.
    FormulaSpec(
        key="pwf_lineal", topic="ipr", step="pwf_diseno",
        label="Pwf en las perforaciones (IPR lineal)",
        expression="Pwf = Pr − q / J", units="psia",
        symbols={
            "Pr": "Presión estática del reservorio [psia]",
            "q": "Caudal objetivo de diseño [STB/d]",
            "J": "Índice de productividad [STB/d/psi]",
        },
        reference="Darcy; Brown Vol. 2b §4.522", module="bes.core.ipr",
        note="La recta de Darcy tiene despeje directo. Vale con flujo "
             "monofásico, o sea con Pwf por encima de la presión de burbuja.",
    ),
    FormulaSpec(
        key="pwf_vogel_recta", topic="ipr", step="pwf_diseno",
        label="Pwf en las perforaciones (Vogel, tramo recto)",
        expression="q = J · (Pr − Pwf)", units="psia",
        symbols={
            "q": "Caudal objetivo de diseño [STB/d]",
            "J": "Índice de productividad [STB/d/psi]",
            "Pr": "Presión estática del reservorio [psia]",
            "Pwf": "Presión de fondo fluyente resultante [psia]",
        },
        reference="Beggs, «Production Optimization», §2", module="bes.core.ipr",
        note="Arriba de la burbuja la IPR compuesta es una recta y el flujo en "
             "el reservorio sigue siendo monofásico.",
    ),
    FormulaSpec(
        key="pwf_qb", topic="ipr", step="caudal_burbuja",
        label="Caudal al llegar a la presión de burbuja",
        expression="q_b = J · (Pr − Pb)", units="STB/d",
        symbols={
            "J": "Índice de productividad [STB/d/psi]",
            "Pr": "Presión estática del reservorio [psia]",
            "Pb": "Presión de burbuja [psia]",
        },
        reference="Beggs, «Production Optimization», §2", module="bes.core.ipr",
        note="Marca dónde se dobla la curva. Decide cuál de los dos tramos "
             "aplica al caudal de diseño.",
    ),
    FormulaSpec(
        key="pwf_vogel_bifasico", topic="ipr", step="pwf_diseno",
        label="Pwf en las perforaciones (Vogel, tramo bifásico)",
        expression="q = q_b + (J·Pb/1.8) · [1 − 0.2·(Pwf/Pb) − 0.8·(Pwf/Pb)²]",
        units="psia",
        symbols={
            "q": "Caudal objetivo de diseño [STB/d]",
            "q_b": "Caudal al llegar a la presión de burbuja [STB/d]",
            "J": "Índice de productividad [STB/d/psi]",
            "Pb": "Presión de burbuja [psia]",
            "Pwf": "Presión de fondo fluyente resultante [psia]",
        },
        reference="Vogel, JPT (1968); Beggs §2, ec. 2-53", module="bes.core.ipr",
        note="Debajo de la burbuja se libera gas, el flujo se hace bifásico y "
             "la curva se dobla. Los dos tramos empalman con la misma pendiente "
             "en Pb: la IPR no tiene quiebre.",
    ),
    FormulaSpec(
        key="pwf_fetkovich", topic="ipr", step="pwf_diseno",
        label="Pwf en las perforaciones (Fetkovich)",
        expression="q = C · (Pr² − Pwf²)^n", units="psia",
        symbols={
            "q": "Caudal objetivo de diseño [STB/d]",
            "C": "Coeficiente de entregabilidad [STB/d/psia^(2n)]",
            "Pr": "Presión estática del reservorio [psia]",
            "Pwf": "Presión de fondo fluyente resultante [psia]",
            "n": "Exponente de entregabilidad [-]",
        },
        reference="Fetkovich, SPE 4529 (1973); Beggs §2, ec. 2-54",
        module="bes.core.ipr",
        note="Fetkovich NO se parte en la presión de burbuja: el ajuste de C y "
             "n ya absorbe el comportamiento bifásico del reservorio.",
    ),
    FormulaSpec(
        key="diseno_drawdown", topic="ipr", step="drawdown_diseno",
        label="Caída de presión sobre el reservorio (draw-down)",
        expression="Δp = Pr − Pwf", units="psi",
        symbols={
            "Pr": "Presión estática del reservorio [psia]",
            "Pwf": "Presión de fondo fluyente de diseño [psia]",
        },
        reference="Brown Vol. 2b §4.522", module="bes.core.ipr",
        note="Es lo que hay que quitarle al reservorio para que entregue el "
             "caudal objetivo. De la Pwf sale el PIP, y de ahí el TDH.",
    ),

    # ---------------------------------------------------------------- TDH --
    FormulaSpec(
        key="sg_liquid", topic="tdh", step="sg_liquido",
        label="Gravedad específica del líquido producido",
        expression="SG = SG_o · (1 − WC) + SG_w · WC", units="-",
        symbols={
            "SG_o": "Gravedad específica del petróleo, 141.5/(131.5+°API) [-]",
            "WC": "Corte de agua, en fracción [-]",
            "SG_w": "Gravedad específica del agua de formación [-]",
        },
        reference="Brown Vol. 2b §4.5324", module="bes.core.tdh",
        note="Ponderación por corte de agua. El catálogo publica la potencia "
             "para agua (SG = 1), por eso después se corrige por este valor.",
    ),
    FormulaSpec(
        key="pip_head", topic="tdh", step="sumergencia",
        label="Sumergencia — altura equivalente a la presión de admisión",
        expression="H_pip = PIP · 2.31 / SG", units="ft",
        symbols={
            "PIP": "Presión en la admisión de la bomba [psia]",
            "SG": "Gravedad específica del líquido producido [-]",
        },
        reference="Brown Vol. 2b §4.5324", module="bes.core.tdh",
        note="2.31 ft/psi es la columna de agua dulce; dividir por SG la lleva "
             "al fluido real. Es la altura que la bomba NO tiene que levantar.",
    ),
    FormulaSpec(
        key="vertical_lift", topic="tdh", step="elevacion",
        label="Elevación vertical neta",
        expression="H_vert = D_bomba − H_pip", units="ft",
        symbols={
            "D_bomba": "Profundidad de asentamiento de la bomba [ft TVD]",
            "H_pip": "Sumergencia [ft]",
        },
        reference="Brown Vol. 2b §4.5324", module="bes.core.tdh",
        note="Si el nivel de fluido queda por encima de la bomba, H_pip supera "
             "la profundidad y este término se vuelve negativo: la sumergencia "
             "ayuda en vez de estorbar.",
    ),
    FormulaSpec(
        key="friccion_hazen_williams", topic="tdh", step="friccion",
        label="Pérdida por fricción en el tubing (Hazen-Williams)",
        expression="H_fric = 0.2083 · (100/C)^1.852 · q^1.852 / d^4.8655 · L/100",
        units="ft",
        symbols={
            "C": "Coeficiente de rugosidad de Hazen-Williams [-]",
            "q": "Caudal de líquido [gpm]",
            "d": "Diámetro interno del tubing [in]",
            "L": "Longitud de tubería [ft]",
        },
        reference="Brown Vol. 2b §4.5324", module="bes.core.tdh",
        note="Correlación MONOFÁSICA. Se usa cuando la fracción de gas libre "
             "en la admisión no supera el umbral —el flujo en el tubing se "
             "puede tratar como líquido— **y** el líquido tiene menos de 5 cp. "
             "Por encima de esa viscosidad no puede seguir al fluido, porque "
             "se estableció con agua en régimen turbulento y su único "
             "parámetro libre, C, describe la rugosidad de la cañería y no el "
             "fluido: ahí manda Darcy-Weisbach.",
    ),
    FormulaSpec(
        key="friccion_darcy_weisbach", topic="tdh", step="friccion",
        label="Pérdida por fricción en el tubing (Darcy-Weisbach)",
        expression="H_fric = f · (L/d) · v² / (2·g)", units="ft",
        symbols={
            "f": "Factor de fricción de Darcy [-]",
            "L": "Longitud de tubería [ft]",
            "d": "Diámetro interno del tubing [ft]",
            "v": "Velocidad media del líquido [ft/s]",
            "g": "Aceleración de la gravedad [ft/s²]",
        },
        reference="Darcy-Weisbach; factor turbulento por Swamee y Jain (1976), "
                  "ajuste explícito de Colebrook-White",
        module="bes.core.tdh",
        note="La otra MONOFÁSICA, y la única de las dos que contempla la "
             "viscosidad. El factor depende del régimen: f = 64/Re en laminar "
             "(Re < 2000) y el ajuste de Swamee-Jain en turbulento "
             "(Re > 4000), interpolando entre ambos en la transición, donde no "
             "rige ninguna ley. En crudo pesado el flujo se vuelve laminar y "
             "ahí f crece LINEALMENTE con la viscosidad, comportamiento que "
             "ninguna potencia fija del caudal reproduce.",
    ),
    FormulaSpec(
        key="friccion_pc", topic="tdh", step="friccion",
        label="Pérdida por fricción en el tubing (Poettmann-Carpenter)",
        expression="H_fric = (dP/dz)_fricción · L · 2.31 / SG", units="ft",
        symbols={
            "(dP/dz)_fricción": "Término de fricción del gradiente P&C [psi/ft]",
            "L": "Longitud de tubería [ft]",
            "SG": "Gravedad específica del líquido producido [-]",
        },
        reference="Poettmann & Carpenter (1952); Brown Vol. 2b §4.5324",
        module="bes.core.tdh",
        note="Se toma SOLO el término de fricción: la elevación vertical ya "
             "representa la columna, y sumar el término de gravedad de P&C la "
             "contaría dos veces. Se integra en 30 tramos desde el cabezal "
             "porque el gas se expande y carga la fricción hacia el tope.",
    ),
    FormulaSpec(
        key="wellhead_head", topic="tdh", step="cabeza_superficie",
        label="Altura equivalente a la presión de boca de pozo",
        expression="H_wh = P_wh · 2.31 / SG", units="ft",
        symbols={
            "P_wh": "Presión requerida en boca de pozo [psi]",
            "SG": "Gravedad específica del líquido producido [-]",
        },
        reference="Brown Vol. 2b §4.5324", module="bes.core.tdh",
    ),
    FormulaSpec(
        key="tdh", topic="tdh", step="tdh",
        label="TDH — Altura dinámica total",
        expression="TDH = H_vert + H_fric + H_wh", units="ft",
        symbols={
            "H_vert": "Elevación vertical neta [ft]",
            "H_fric": "Pérdida por fricción en el tubing [ft]",
            "H_wh": "Altura equivalente a la presión de boca de pozo [ft]",
        },
        reference="Brown Vol. 2b §4.5324", module="bes.core.tdh",
        note="Es la altura total que la bomba tiene que desarrollar.",
    ),

    # ------------------------------------------------------------ DISEÑO --
    FormulaSpec(
        key="stages", topic="diseno", step="etapas",
        label="Cantidad de etapas",
        expression="N = TDH / H_etapa", units="etapas",
        symbols={
            "TDH": "Altura dinámica total [ft]",
            "H_etapa": "Altura por etapa de la curva de catálogo, al caudal de "
                       "operación y a la frecuencia de trabajo [ft/etapa]",
        },
        reference="Brown Vol. 2b §4.5325", module="bes.core.pump_design",
        note="H_etapa sale de la curva YA escalada a la frecuencia de "
             "operación: a 50 Hz una bomba da menos altura por etapa que a 60.",
    ),
    FormulaSpec(
        key="shaft_hp", topic="diseno", step="potencia_eje",
        label="Potencia al eje de la bomba",
        expression="HP = N · HP_etapa · SG", units="hp",
        symbols={
            "N": "Cantidad de etapas [-]",
            "HP_etapa": "Potencia por etapa de la curva de catálogo [hp/etapa]",
            "SG": "Gravedad específica del líquido producido [-]",
        },
        reference="Brown Vol. 2b §4.5325", module="bes.core.pump_design",
        note="HP_etapa del catálogo está calibrada para agua (SG = 1); "
             "multiplicar por el SG del fluido da la potencia real.",
    ),

    # -------------------------------------------------------- VISCOSIDAD --
    #
    # Los pasos 2, 3 y 4 del procedimiento de Riling, que hasta ahora entraban
    # al reporte ya resueltos: el SSU aparecía sin decir de dónde salía.
    FormulaSpec(
        key="visc_mu_muerta", topic="viscosidad", step="viscosidad_muerta",
        label="Paso 2 — viscosidad del crudo sin gas",
        expression="μ_od = f(°API, T)   —  Fig. 4L(2)", units="cp",
        symbols={
            "°API": "Gravedad del petróleo [°API]",
            "T": "Temperatura de evaluación [°F]",
            "μ_od": "Viscosidad del crudo muerto [cp]",
        },
        reference="Brown Vol. 2b, Apéndice 4L, Fig. 4L(2)",
        module="bes.core.viscosity",
        note="Riling dice «de ensayos o de la Fig. 4L», y ése es el orden: un "
             "dato medido a la temperatura correcta manda sobre la lámina. "
             "Beggs-Robinson NO interviene acá: en crudos pesados quedaba muy "
             "corta —59 cp contra 151.9 de la figura para 16 °API a 130 °F— y "
             "arrastraba el error por todo el procedimiento.",
    ),
    FormulaSpec(
        key="visc_mu_viva", topic="viscosidad", step="viscosidad_viva",
        label="Paso 3 — corrección por gas disuelto",
        expression="μ_ob = f(μ_od, Rs)   —  Fig. 4L(1)", units="cp",
        symbols={
            "μ_od": "Viscosidad del crudo muerto [cp]",
            "Rs": "Gas DISUELTO en la admisión [scf/STB]",
            "μ_ob": "Viscosidad del crudo saturado de gas [cp]",
        },
        reference="Brown Vol. 2b, Apéndice 4L, Fig. 4L(1)",
        module="bes.core.viscosity",
        note="Entra el gas DISUELTO, no el GOR total: el gas ya liberado está "
             "al lado, libre, y no adelgaza al petróleo. La lámina se titula "
             "«Viscosity of gas SATURATED crude oil».",
    ),
    FormulaSpec(
        key="visc_cinematica", topic="viscosidad", step="viscosidad_cinematica",
        label="Paso 4a — viscosidad cinemática",
        expression="ν = μ_ob / γ_o", units="cSt",
        symbols={
            "μ_ob": "Viscosidad dinámica del crudo saturado [cp]",
            "γ_o": "Densidad relativa del petróleo [-]",
        },
        reference="Brown Vol. 2b §4.53112", module="bes.core.viscosity",
        note="La conversión a SSU se indexa por viscosidad CINEMÁTICA, así que "
             "hay que dividir por la densidad relativa antes de convertir.",
    ),
    FormulaSpec(
        key="visc_factores", topic="viscosidad", step="factores_correccion",
        label="Paso 6 — factores de corrección de la curva",
        expression="(C_Q, C_H, C_HP, η_visc) = Tabla 4.520 / 4.521 (SSU)",
        units="%",
        symbols={
            "SSU": "Viscosidad de la mezcla a temperatura de bombeo [SSU]",
            "C_Q": "Factor de caudal [%]",
            "C_H": "Factor de altura [%]",
            "C_HP": "Factor de potencia [%]",
            "η_visc": "Rendimiento degradado [%]",
        },
        reference="Brown Vol. 2b §4.53112, Tablas 4.520 y 4.521 (Riling)",
        module="bes.core.viscosity",
        note="Dos tablas según el rendimiento máximo de la bomba —4.520 para "
             "60 % y 4.521 para 70 %—, interpoladas entre ambas. Fuera del "
             "rango de la tabla se acota al extremo y se avisa: no se "
             "extrapola.",
    ),
    FormulaSpec(
        key="visc_ssu", topic="viscosidad", step="conversion_ssu",
        label="Viscosidad en Segundos Saybolt Universal",
        expression="SSU = 2.273 · ( ν + sqrt( ν² + 158.4 ) )", units="SSU",
        symbols={"ν": "Viscosidad cinemática de la mezcla a temperatura de "
                      "bombeo, μ/γ_o [cSt]"},
        reference="Takács, «Electrical Submersible Pumps Manual», 2ª ed. "
                  "(2018), cap. 4, ec. 4.14, pág. 159",
        module="bes.core.viscosity",
        note="Es el paso 4 de Riling: las Tablas 4.520 y 4.521 se indexan por "
             "SSU, así que sin esta conversión no se puede entrar. Reemplaza a "
             "la lectura de la Fig. 4L-3 y también a la ASTM D2161 que usaba "
             "el proyecto: una sola conversión para los dos caminos —Riling y "
             "Hydraulic Institute—, que antes entraban con números distintos.",
    ),
    FormulaSpec(
        key="visc_q_water", topic="viscosidad", step="caudal_equivalente",
        label="Caudal equivalente en agua",
        expression="Q_agua = Q_pedido / C_Q", units="STB/d",
        symbols={
            "Q_pedido": "Caudal que se le pide a la bomba con el crudo [STB/d]",
            "C_Q": "Factor de corrección de caudal, en fracción [-]",
        },
        reference="Brown Vol. 2b §4.53112 (Riling), Tabla 4.52x",
        module="bes.core.pump_design",
        note="Se DIVIDE, no se multiplica: la curva del catálogo está levantada "
             "con agua, así que para entregar el caudal pedido con crudo hay "
             "que buscar una bomba que dé más en agua.",
    ),
    FormulaSpec(
        key="visc_h_water", topic="viscosidad", step="altura_equivalente",
        label="Altura equivalente en agua",
        expression="H_agua = TDH_pedido / C_H", units="ft",
        symbols={
            "TDH_pedido": "Altura que tiene que desarrollar con el crudo [ft]",
            "C_H": "Factor de corrección de altura, en fracción [-]",
        },
        reference="Brown Vol. 2b §4.53112 (Riling), Tabla 4.52x",
        module="bes.core.pump_design",
        note="Mismo criterio que el caudal: la bomba desarrolla menos altura "
             "con el crudo que con agua.",
    ),
    FormulaSpec(
        key="visc_hp", topic="viscosidad", step="potencia_corregida",
        label="Potencia corregida por viscosidad",
        expression="HP_crudo = HP_agua · C_HP", units="hp",
        symbols={
            "HP_agua": "Potencia al eje con la curva de agua [hp]",
            "C_HP": "Factor de corrección de potencia [-]",
        },
        reference="Brown Vol. 2b §4.53112 (Riling), Tabla 4.52x",
        module="bes.core.pump_design",
        note="Acá SÍ se multiplica: el rendimiento cae con el crudo viscoso y "
             "la potencia sube. C_HP es mayor que 1.",
    ),

    # --------------------------------------------------------------- GAS --
    #
    # 0) De dónde sale la fracción de gas libre. Es el número que gobierna TODO
    #    lo que viene después —la correlación de fricción, la escalera de
    #    manejo de gas y el método de incrementos—, así que el reporte tiene que
    #    poder mostrar su balance término por término. Con el porcentaje solo,
    #    el lector no puede verificar nada.
    FormulaSpec(
        key="gas_volumen_petroleo", topic="gas", step="balance_gas_libre",
        label="Volumen de petróleo en la admisión",
        expression="V_o = (1 − WC) · Bo", units="bbl",
        symbols={
            "WC": "Corte de agua [fracción 0–1]",
            "Bo": "Factor volumétrico del petróleo a P y T de admisión [bbl/STB]",
        },
        reference="Brown Vol. 2b §4.532", module="bes.core.gas_handling",
        note="Sobre la base de UN barril de líquido de superficie. El petróleo "
             "se dilata al bajar la presión y al tomar gas en solución, y por "
             "eso Bo es mayor que 1.",
    ),
    FormulaSpec(
        key="gas_volumen_agua", topic="gas", step="balance_gas_libre",
        label="Volumen de agua en la admisión",
        expression="V_w = WC · Bw", units="bbl",
        symbols={
            "WC": "Corte de agua [fracción 0–1]",
            "Bw": "Factor volumétrico del agua a P y T de admisión [bbl/STB]",
        },
        reference="Brown Vol. 2b §4.532", module="bes.core.gas_handling",
    ),
    FormulaSpec(
        key="gas_volumen_libre", topic="gas", step="balance_gas_libre",
        label="Volumen de gas libre en la admisión",
        expression="V_g = (1 − WC) · (GOR − Rs) · Bg", units="bbl",
        symbols={
            "WC": "Corte de agua [fracción 0–1]",
            "GOR": "Relación gas-petróleo producida [scf/STB]",
            "Rs": "Gas que sigue DISUELTO a P y T de admisión [scf/STB]",
            "Bg": "Factor volumétrico del gas [bbl/scf]",
        },
        reference="Brown Vol. 2b §4.532", module="bes.core.gas_handling",
        note="El gas libre es la diferencia entre el que el pozo produce y el "
             "que sigue disuelto. Rs se acota al GOR: no puede liberarse más "
             "gas del que el pozo produce. Multiplica por (1 − WC) porque el "
             "gas viene con el petróleo, no con el agua.",
    ),
    FormulaSpec(
        key="gas_fraccion_libre", topic="gas", step="balance_gas_libre",
        label="Fracción de gas libre en la admisión",
        expression="f = V_g / (V_o + V_w + V_g)", units="fracción",
        symbols={
            "V_o": "Volumen de petróleo [bbl]",
            "V_w": "Volumen de agua [bbl]",
            "V_g": "Volumen de gas libre [bbl]",
        },
        reference="Brown Vol. 2b §4.532; Takács (2018) §4.4.3",
        module="bes.core.gas_handling",
        note="Es una FRACCIÓN sobre el volumen total, no una relación "
             "gas/líquido. Gobierna la correlación de fricción, la escalera de "
             "manejo de gas y el método por incrementos.",
    ),
    FormulaSpec(
        key="gas_relacion_gas_liquido", topic="gas", step="balance_gas_libre",
        label="Relación gas/líquido en la admisión",
        expression="r = f / (1 − f)", units="bbl gas / bbl líquido",
        symbols={"f": "Fracción volumétrica de gas libre [0–1]"},
        reference="Brown Vol. 2b §4.523, pág. 59",
        module="bes.core.gas_handling",
        note="La misma cantidad de gas, expresada de la otra manera. Hace falta "
             "porque el criterio de Brown —la bomba pierde altura por encima de "
             "0.1— está declarado en RELACIÓN, mientras que las capacidades de "
             "Takács y los catálogos están en fracción. Confundirlas mueve los "
             "umbrales a la mitad de su valor.",
    ),

    # 0b) La escalera de manejo de gas: las dos condiciones que decide cada
    #     escalón, y la reducción que produce un separador.
    FormulaSpec(
        key="gas_capacidad_configuracion", topic="gas", step="escalera_gas",
        label="Condición 1 — capacidad de la configuración",
        expression="f_admisión ≤ capacidad", units="fracción",
        symbols={
            "f_admisión": "Gas libre que LLEGA a la admisión [0–1]",
            "capacidad": "Fracción de vacío que admite esa configuración de "
                         "aparejo [0–1]",
        },
        reference="Takács (2018), Fig. 4.25, pág. 195",
        module="bes.core.gas_handling",
        note="Es una propiedad de la TECNOLOGÍA: 20 % sin separador, 80 % con "
             "uno, 95 % en tándem. Se mide en la admisión —la figura dice «at "
             "pump suction conditions»— y no aguas abajo del separador.",
    ),
    FormulaSpec(
        key="gas_criterio_bomba", topic="gas", step="escalera_gas",
        label="Condición 2 — máximo de gas admisible en la bomba",
        expression="f_bomba ≤ max_gip", units="fracción",
        symbols={
            "f_bomba": "Gas libre que ENTRA a la bomba, ya separado [0–1]",
            "max_gip": "Máximo de gas admisible, criterio de diseño [0–1]",
        },
        reference="Criterio propio del proyecto. La bibliografía publica dos "
                  "criterios para esta misma magnitud: Takács (2018), pág. 10, "
                  "exige separador por encima del 5 % —la mitad—, y la "
                  "correlación de Turpin (Takács §4.4.3.2, ec. 4.30) hace "
                  "depender el límite de la presión de admisión",
        module="bes.core.gas_handling",
        note="Se mide DESPUÉS de separar, a diferencia de la condición 1. Un "
             "escalón de la escalera sirve sólo si cumple las dos. El valor "
             "por defecto es 10 %, configurable por pozo.",
    ),
    FormulaSpec(
        key="gas_separador_salida", topic="gas", step="escalera_gas",
        label="Gas remanente después del separador",
        expression="r' = r · (1 − η)   →   f' = r' / (1 + r')",
        units="fracción",
        symbols={
            "r": "Relación gas/líquido antes del separador [-]",
            "η": "Eficiencia de separación [0–1]",
            "r'": "Relación gas/líquido después del separador [-]",
        },
        reference="Brown Vol. 2b §4.524", module="bes.core.gas_handling",
        note="La reducción se aplica sobre la RELACIÓN, no sobre la fracción: "
             "el separador saca gas y deja el líquido. Un separador del 75 % NO "
             "deja f × 0.25; con f = 65 % deja 31.6 % y no 16.2 %.",
    ),

    FormulaSpec(
        key="gas_delta_p", topic="gas", step="salto_presion",
        label="Salto de presión que debe dar la bomba",
        expression="ΔP = P_desc − P_adm", units="psi",
        symbols={
            "P_desc": "Presión de descarga de la bomba [psia]",
            "P_adm": "Presión en la admisión (PIP) [psia]",
        },
        reference="Brown Vol. 2b §4.53103", module="bes.core.gas_handling",
        note="Es lo que se divide en escalones. Con gas libre el caudal "
             "volumétrico NO es constante a lo largo de la bomba —el gas se "
             "comprime y parte pasa a solución—, así que no se puede resolver "
             "con un caudal único.",
    ),
    FormulaSpec(
        key="gas_n_incrementos", topic="gas", step="escalones",
        label="Cantidad de escalones",
        expression="n = ⌈ΔP / escalón⌉", units="tramos",
        symbols={
            "ΔP": "Salto total de presión de la bomba [psi]",
            "escalón": "Tamaño del incremento elegido [psi]",
        },
        reference="Brown Vol. 2b §4.53103", module="bes.core.gas_handling",
        note="Lleva TECHO: el último escalón se queda con el resto de la "
             "división y por eso puede ser más corto que los demás.",
    ),
    FormulaSpec(
        key="gas_q_avg", topic="gas", step="caudal_tramo",
        label="Caudal de mezcla del tramo",
        expression="Q_prom = (Q_ent + Q_sal) / 2", units="b/d",
        symbols={
            "Q_ent": "Caudal volumétrico de mezcla al entrar al tramo [b/d]",
            "Q_sal": "Caudal volumétrico de mezcla al salir del tramo [b/d]",
        },
        reference="Brown Vol. 2b §4.53103 paso 5",
        module="bes.core.gas_handling",
        note="Se evalúa en los DOS extremos y se promedia, que es lo que hace "
             "el libro. No en el punto medio: Bg va con 1/P, así que el valor "
             "en el medio no es el promedio de los extremos.",
    ),
    FormulaSpec(
        key="gas_gradient", topic="gas", step="gradiente_tramo",
        label="Gradiente promedio del tramo",
        expression="grad = (grad_ent + grad_sal) / 2", units="psi/ft",
        symbols={
            "grad_ent": "Gradiente de la mezcla al entrar al tramo [psi/ft]",
            "grad_sal": "Gradiente de la mezcla al salir del tramo [psi/ft]",
        },
        reference="Brown Vol. 2b §4.53103 paso 4",
        module="bes.core.gas_handling",
        note="Gradiente de la mezcla completa: petróleo, agua y gas libre a la "
             "presión y temperatura del tramo.",
    ),
    FormulaSpec(
        key="gas_visc", topic="gas", step="viscosidad_tramo",
        label="Corrección por viscosidad del tramo",
        expression="H_etapa = H_agua(Q_prom / C_Q) · C_H", units="ft/etapa",
        symbols={
            "Q_prom": "Caudal de mezcla promedio del tramo [b/d]",
            "C_Q": "Factor de corrección de caudal del tramo [-]",
            "C_H": "Factor de corrección de altura del tramo [-]",
        },
        reference="Brown Vol. 2b §4.53112 (Riling)",
        module="bes.core.gas_handling",
        note="Se evalúa POR TRAMO: el gas en solución cambia con la presión y "
             "la viscosidad del crudo vivo con él, así que cada tramo ve un "
             "fluido distinto. Crudo ≥ 28 °API no se corrige.",
    ),
    FormulaSpec(
        key="gas_deterioro", topic="gas", step="deterioro_gas",
        label="Altura degradada por gas libre",
        expression="H_efec = H_etapa · f_det", units="ft/etapa",
        symbols={
            "H_etapa": "Altura por etapa según la curva corregida [ft/etapa]",
            "f_det": "Factor de deterioro por gas libre [-]",
        },
        reference="Brown Vol. 2b §4.53102", module="bes.core.gas_handling",
        note="Con gas libre la bomba entrega menos altura que su curva de agua.",
    ),
    FormulaSpec(
        key="gas_psi_etapa", topic="gas", step="psi_por_etapa",
        label="Presión que aporta cada etapa",
        expression="Δp_etapa = H_efec · grad", units="psi/etapa",
        symbols={
            "H_efec": "Altura efectiva por etapa [ft/etapa]",
            "grad": "Gradiente promedio de la mezcla del tramo [psi/ft]",
        },
        reference="Brown Vol. 2b §4.53103 paso 7",
        module="bes.core.gas_handling",
        note="Una etapa da una ALTURA fija en pies; cuántos psi son esos pies "
             "depende de la densidad de la mezcla, que cambia tramo a tramo.",
    ),
    FormulaSpec(
        key="gas_etapas_tramo", topic="gas", step="etapas_tramo",
        label="Etapas que necesita el tramo",
        expression="N_tramo = ΔP_tramo / Δp_etapa", units="etapas",
        symbols={
            "ΔP_tramo": "Salto de presión del tramo [psi]",
            "Δp_etapa": "Presión que aporta cada etapa en el tramo [psi/etapa]",
        },
        reference="Brown Vol. 2b §4.53103 paso 8",
        module="bes.core.gas_handling",
        note="NO se redondea acá. Redondear cada tramo cuesta hasta media etapa "
             "cada vez y el error se acumula con la cantidad de tramos.",
    ),
    FormulaSpec(
        key="gas_hp_tramo", topic="gas", step="hp_tramo",
        label="Potencia que consume el tramo",
        expression="HP_tramo = N_tramo · HP_etapa · SG_mezcla · C_HP", units="hp",
        symbols={
            "N_tramo": "Etapas del tramo [-]",
            "HP_etapa": "Potencia por etapa de catálogo [hp/etapa]",
            "SG_mezcla": "Gravedad específica de la mezcla del tramo [-]",
            "C_HP": "Factor de corrección por viscosidad [-]",
        },
        reference="Brown Vol. 2b §4.5325", module="bes.core.gas_handling",
        note="HP_etapa del catálogo está calibrada para agua (SG = 1).",
    ),
    FormulaSpec(
        key="gas_q_representativo", topic="gas", step="caudal_representativo",
        label="Caudal de mezcla representativo",
        expression="Q_rep = Σ Q_prom,i / n", units="b/d",
        symbols={
            "Q_prom,i": "Caudal de mezcla promedio de cada tramo [b/d]",
            "n": "Cantidad de tramos [-]",
        },
        reference="Brown Vol. 2b §4.53103 paso 6",
        module="bes.core.gas_handling",
        note="Con este caudal se elige UNA bomba para toda la sarta. "
             "Re-seleccionar por tramo daba sartas de 3-4 modelos distintos "
             "que no se pueden construir.",
    ),
    FormulaSpec(
        key="gas_etapas_total", topic="gas", step="etapas_total",
        label="Etapas totales de la sarta",
        expression="N = ⌈Σ N_tramo⌉", units="etapas",
        symbols={"N_tramo": "Etapas de cada tramo, en fracción [-]"},
        reference="Brown Vol. 2b §4.53103", module="bes.core.gas_handling",
        note="Se suman las fracciones y se redondea UNA sola vez al final.",
    ),
    FormulaSpec(
        key="gas_hp_total", topic="gas", step="hp_total",
        label="Potencia total al eje",
        expression="HP = Σ HP_tramo", units="hp",
        symbols={"HP_tramo": "Potencia de cada tramo [hp]"},
        reference="Brown Vol. 2b §4.5325", module="bes.core.gas_handling",
        note="Cada tramo aporta según sus propias etapas y el SG de su mezcla, "
             "que no son iguales entre tramos.",
    ),
    FormulaSpec(
        key="gas_tdh_equivalente", topic="gas", step="tdh_equivalente",
        label="Altura equivalente del método",
        expression="TDH_eq = Σ (ΔP_tramo / grad_tramo)", units="ft",
        symbols={
            "ΔP_tramo": "Salto de presión de cada tramo [psi]",
            "grad_tramo": "Gradiente promedio de cada tramo [psi/ft]",
        },
        reference="Identidad del conteo de etapas",
        module="bes.core.gas_handling",
        note="No es una correlación nueva: es la misma identidad del conteo de "
             "etapas despejada al revés, y por eso es coherente con él. El TDH "
             "convencional de tres términos viaja aparte y DISCREPA (11-12 % en "
             "los casos probados); no se elige una en silencio.",
    ),
    FormulaSpec(
        key="gas_masa", topic="gas", step="verificacion_masa",
        label="Caudal másico (verificación)",
        expression="ṁ = ρ_adm · V_adm · 5.615 · q_STB", units="lbm/d",
        symbols={
            "ρ_adm": "Densidad de la mezcla en la admisión [lbm/ft³]",
            "V_adm": "Volumen de mezcla por barril de petróleo [bbl/STB]",
            "5.615": "Conversión de bbl a ft³",
            "q_STB": "Caudal de petróleo en superficie [STB/d]",
        },
        reference="Conservación de masa", module="bes.core.gas_handling",
        note="Es el invariante de control del método: la masa NO cambia a lo "
             "largo de la bomba aunque el volumen sí. El test lo verifica "
             "entre los dos extremos.",
    ),

    # ------------------------------------------------------- MULTIFÁSICO --
    # Poettmann & Carpenter es la ÚNICA correlación multifásica del proyecto:
    # todas las pérdidas de carga se calculan por acá.
    FormulaSpec(
        key="pc_area", topic="multifasico", step="area_flujo",
        label="Área de flujo de la cañería",
        expression="A = (π/4) · (d/12)²", units="ft²",
        symbols={"d": "Diámetro interno de la cañería [in]"},
        reference="Geometría", module="bes.core.multiphase",
        note="El /12 pasa el diámetro de pulgadas a pies, que es la unidad en "
             "la que trabaja el resto del método.",
    ),
    FormulaSpec(
        key="pc_q_liquido_fondo", topic="multifasico", step="caudales_fondo",
        label="Caudal de líquido a condiciones de fondo",
        expression="q_l = q_o · Bo + q_w · Bw", units="bbl/d",
        symbols={
            "q_o": "Caudal de petróleo en superficie [STB/d]",
            "Bo": "Factor volumétrico del petróleo [bbl/STB]",
            "q_w": "Caudal de agua en superficie [STB/d]",
            "Bw": "Factor volumétrico del agua [bbl/STB]",
        },
        reference="Brown Vol. 2b §4.532", module="bes.core.multiphase",
        note="Los caudales de superficie se llevan a las condiciones del punto "
             "con los factores volumétricos del PVT: el fluido ocupa otro "
             "volumen ahí abajo.",
    ),
    FormulaSpec(
        key="pc_q_gas_fondo", topic="multifasico", step="caudales_fondo",
        label="Caudal de gas libre a condiciones de fondo",
        expression="q_g = q_o · (GOR − Rs) · Bg", units="bbl/d",
        symbols={
            "q_o": "Caudal de petróleo en superficie [STB/d]",
            "GOR": "Relación gas-petróleo total de producción [scf/STB]",
            "Rs": "Gas en solución a la presión del punto [scf/STB]",
            "Bg": "Factor volumétrico del gas [bbl/scf]",
        },
        reference="Brown Vol. 2b §4.532", module="bes.core.multiphase",
        note="Sólo el gas LIBRE ocupa volumen aparte: el que está en solución "
             "ya viaja dentro del petróleo y lo cuenta Bo. Por eso la resta, "
             "acotada a cero.",
    ),
    FormulaSpec(
        key="pc_velocidad_superficial", topic="multifasico", step="velocidades",
        label="Velocidad superficial de una fase",
        expression="v_s = q_fondo · 5.615 / 86400 / A", units="ft/s",
        symbols={
            "q_fondo": "Caudal de la fase a condiciones de fondo [bbl/d]",
            "5.615": "Conversión de bbl a ft³",
            "86400": "Segundos en un día",
            "A": "Área de flujo de la cañería [ft²]",
        },
        reference="Poettmann & Carpenter (1952)", module="bes.core.multiphase",
        note="«Superficial» quiere decir: la velocidad que tendría esa fase si "
             "ocupara ella sola toda la sección de la cañería.",
    ),
    FormulaSpec(
        key="pc_holdup_sin_deslizamiento", topic="multifasico", step="holdup",
        label="Fracción de líquido sin deslizamiento",
        expression="λ_l = v_sl / v_m", units="-",
        symbols={
            "v_sl": "Velocidad superficial del líquido [ft/s]",
            "v_m": "Velocidad de la mezcla, v_sl + v_sg [ft/s]",
        },
        reference="Poettmann & Carpenter (1952)", module="bes.core.multiphase",
        note="P&C supone mezcla HOMOGÉNEA: las dos fases viajan a la misma "
             "velocidad, sin deslizamiento entre ellas. Por eso la fracción de "
             "líquido se pondera por caudal y no hace falta un modelo de "
             "holdup — es la simplificación central del método.",
    ),
    FormulaSpec(
        key="pc_densidad_mezcla", topic="multifasico", step="densidad_mezcla",
        label="Densidad de la mezcla",
        expression="ρ_m = ρ_l · λ_l + ρ_g · (1 − λ_l)", units="lb/ft³",
        symbols={
            "ρ_l": "Densidad del líquido in-situ [lb/ft³]",
            "λ_l": "Fracción de líquido sin deslizamiento [-]",
            "ρ_g": "Densidad del gas in-situ [lb/ft³]",
        },
        reference="Poettmann & Carpenter (1952)", module="bes.core.multiphase",
    ),
    FormulaSpec(
        key="pc_factor_friccion", topic="multifasico", step="factor_friccion",
        label="Factor de fricción de Poettmann & Carpenter",
        expression="f = 0.030 · (ρ_m · v_m · d)^(−0.19)", units="-",
        symbols={
            "ρ_m": "Densidad de la mezcla [lb/ft³]",
            "v_m": "Velocidad de la mezcla [ft/s]",
            "d": "Diámetro interno de la cañería [ft]",
        },
        reference="Brown (1977) Vol. 1, Tabla 4-7", module="bes.core.multiphase",
        note="Ajuste log-log a la carta original de P&C. NO es el factor de "
             "Moody: el número de correlación ρ_m·v_m·d no es un Reynolds, no "
             "lleva viscosidad. Se acota a [0.005, 0.065], que es el rango que "
             "cubre la carta impresa.",
    ),
    FormulaSpec(
        key="pc_rgl", topic="multifasico", step="envelope",
        label="Relación gas-líquido (RGL)",
        expression="RGL = GOR / (1 + WOR)", units="scf/bbl",
        symbols={
            "GOR": "Relación gas-petróleo de producción [scf/STB]",
            "WOR": "Relación agua-petróleo, Wc/(1−Wc) [-]",
        },
        reference="Envelope de Poettmann & Carpenter (apuntes de cátedra)",
        module="bes.core.multiphase",
        note="El GOR se mide por barril de PETRÓLEO y la RGL por barril de "
             "LÍQUIDO: en un pozo con agua no son lo mismo. Es la magnitud en "
             "la que está declarado el límite del método —hasta 1500 scf/bbl—, "
             "así que compararlo contra el GOR pelado daría un veredicto "
             "equivocado en cuanto hay corte de agua.",
    ),
    FormulaSpec(
        key="pc_gradiente_gravedad", topic="multifasico", step="gradiente",
        label="Gradiente por gravedad",
        expression="(dP/dz)_grav = ρ_m · sen θ / 144", units="psi/ft",
        symbols={
            "ρ_m": "Densidad de la mezcla [lb/ft³]",
            "θ": "Ángulo de la cañería respecto de la horizontal [°]",
            "144": "Conversión de lb/ft² a psi",
        },
        reference="Poettmann & Carpenter (1952)", module="bes.core.multiphase",
        note="Es el peso de la columna. **Nunca sumarlo al TDH**: la elevación "
             "vertical ya representa esa columna y se contaría dos veces.",
    ),
    FormulaSpec(
        key="pc_gradiente_friccion", topic="multifasico", step="gradiente",
        label="Gradiente por fricción",
        expression="(dP/dz)_fric = f · ρ_m · v_m² / (2 · g_c · d · 144)",
        units="psi/ft",
        symbols={
            "f": "Factor de fricción de P&C [-]",
            "ρ_m": "Densidad de la mezcla [lb/ft³]",
            "v_m": "Velocidad de la mezcla [ft/s]",
            "g_c": "Constante gravitacional, 32.174 lbm·ft/(lbf·s²)",
            "d": "Diámetro interno de la cañería [ft]",
            "144": "Conversión de lb/ft² a psi",
        },
        reference="Poettmann & Carpenter (1952)", module="bes.core.multiphase",
        note="Éste es el único término que entra al TDH cuando hay gas libre, "
             "y se integra en tramos desde el cabezal hacia abajo porque el gas "
             "se expande y carga la fricción hacia el tope.",
    ),
    FormulaSpec(
        key="pc_gradiente_total", topic="multifasico", step="gradiente",
        label="Gradiente total de la mezcla",
        expression="(dP/dz) = (dP/dz)_grav + (dP/dz)_fric", units="psi/ft",
        symbols={
            "(dP/dz)_grav": "Gradiente por gravedad [psi/ft]",
            "(dP/dz)_fric": "Gradiente por fricción [psi/ft]",
        },
        reference="Poettmann & Carpenter (1952)", module="bes.core.multiphase",
        note="Es el gradiente que se integra a lo largo del pozo para obtener "
             "el PIP y la presión de descarga. En un pozo vertical la gravedad "
             "aporta casi todo: la fricción rara vez pasa del 5 %.",
    ),
    FormulaSpec(
        key="pip_recorrido", topic="multifasico", step="pip",
        label="Caída de presión en el anular, de las perforaciones a la bomba",
        expression="Δp_anular = Σᵢ (dP/dz)ᵢ · Δz", units="psi",
        symbols={
            "(dP/dz)ᵢ": "Gradiente total de P&C en el tramo i [psi/ft]",
            "Δz": "Largo de cada tramo de integración [ft]",
        },
        reference="Brown Vol. 2b §4.532", module="bes.core.tdh",
        note="El gradiente NO es constante: depende de la presión, que es "
             "justamente lo que se busca. Por eso el recorrido se parte en "
             "tramos y en cada uno se itera hasta que la presión del PVT sea "
             "consistente con la que sale. El anular usa el ID del casing.",
    ),
    FormulaSpec(
        key="pip_admision", topic="multifasico", step="pip",
        label="PIP — presión en la admisión de la bomba",
        expression="PIP = Pwf − Δp_anular", units="psia",
        symbols={
            "Pwf": "Presión de fondo fluyente en las perforaciones [psia]",
            "Δp_anular": "Caída de presión en el anular hasta la bomba [psi]",
        },
        reference="Brown Vol. 2b §4.532", module="bes.core.tdh",
        note="La Pwf sale del IPR y el fluido sube por el anular hasta la "
             "admisión perdiendo peso de columna y fricción. El PIP es el dato "
             "que después fija la sumergencia y, con ella, el TDH.",
    ),
    FormulaSpec(
        key="pip_gradiente_promedio", topic="multifasico", step="pip",
        label="Gradiente promedio del recorrido anular",
        expression="grad_prom = Δp_anular / (D_perf − D_bomba)", units="psi/ft",
        symbols={
            "Δp_anular": "Caída de presión en el anular hasta la bomba [psi]",
            "D_perf": "Profundidad de las perforaciones [ft TVD]",
            "D_bomba": "Profundidad de asentamiento de la bomba [ft TVD]",
        },
        reference="Brown Vol. 2b §4.532", module="bes.core.tdh",
        note="No es un paso del método: es el control de mano. Se compara "
             "contra el gradiente del líquido (≈0.43 psi/ft para agua) — si da "
             "mucho menos, hay gas libre aligerando la columna del anular.",
    ),

    # ---------------------------------------------------------- AFINIDAD --
    FormulaSpec(
        key="afinidad_caudal", topic="afinidad", step="ley_caudal",
        label="Ley de afinidad — caudal",
        expression="Q₂ = Q₁ · (N₂/N₁) · (D₂/D₁)", units="b/d",
        symbols={
            "Q₁": "Caudal en la condición de referencia [b/d]",
            "N₂/N₁": "Relación de velocidades, igual a f₂/f₁ [-]",
            "D₂/D₁": "Relación de diámetros del impulsor [-]",
        },
        reference="Brown Vol. 2b, Tabla 4.21", module="bes.core.affinity",
        note="El caudal va LINEAL con la velocidad. Es la ley que se invierte "
             "para preguntar «a qué frecuencia obtengo el caudal que quiero».",
    ),
    FormulaSpec(
        key="afinidad_altura", topic="afinidad", step="ley_altura",
        label="Ley de afinidad — altura",
        expression="H₂ = H₁ · (N₂/N₁)² · (D₂/D₁)²", units="ft",
        symbols={
            "H₁": "Altura en la condición de referencia [ft]",
            "N₂/N₁": "Relación de velocidades [-]",
            "D₂/D₁": "Relación de diámetros del impulsor [-]",
        },
        reference="Brown Vol. 2b, Tabla 4.21", module="bes.core.affinity",
        note="Va con el CUADRADO, y **no lleva término de SG**: un impulsor a "
             "una velocidad dada desarrolla la misma altura en pies bombee agua "
             "o salmuera. Lo que cambia con la densidad es la presión, no la "
             "altura.",
    ),
    FormulaSpec(
        key="afinidad_potencia", topic="afinidad", step="ley_potencia",
        label="Ley de afinidad — potencia",
        expression="HP₂ = HP₁ · (N₂/N₁)³ · (D₂/D₁)³ · (SG₂/SG₁)", units="hp",
        symbols={
            "HP₁": "Potencia al eje en la condición de referencia [hp]",
            "N₂/N₁": "Relación de velocidades [-]",
            "D₂/D₁": "Relación de diámetros del impulsor [-]",
            "SG₂/SG₁": "Relación de gravedades específicas del fluido [-]",
        },
        reference="Brown Vol. 2b, Tabla 4.21", module="bes.core.affinity",
        note="Va con el CUBO, y acá sí entra la densidad: mover un fluido más "
             "pesado a la misma altura cuesta proporcionalmente más. Las curvas "
             "de catálogo son de agua, así que SG₂/SG₁ es el SG del fluido "
             "producido. El rendimiento NO se escala.",
    ),
    FormulaSpec(
        key="afinidad_frecuencia_objetivo", topic="afinidad", step="frecuencia",
        label="Frecuencia para un caudal objetivo",
        expression="f₂ = f₁ · (Q₂/Q₁)", units="Hz",
        symbols={
            "f₁": "Frecuencia de referencia [Hz]",
            "Q₂": "Caudal deseado [b/d]",
            "Q₁": "Caudal conocido a la frecuencia de referencia [b/d]",
        },
        reference="Brown Vol. 2b, Tabla 4.21", module="bes.core.affinity",
        note="Es la ley del caudal invertida, y es la pregunta que realmente "
             "hace un diseño con VSD.",
    ),
    FormulaSpec(
        key="afinidad_rpm_sincronica", topic="afinidad", step="velocidad_motor",
        label="Velocidad sincrónica del motor",
        expression="N = 120 · f / polos", units="rpm",
        symbols={
            "f": "Frecuencia de alimentación [Hz]",
            "polos": "Cantidad de polos del motor [-]",
        },
        reference="Máquinas eléctricas — motor de inducción",
        module="bes.core.affinity",
        note="Se trabaja en Hz y no en rpm porque el deslizamiento se cancela "
             "en la relación N₂/N₁ = f₂/f₁. Esta velocidad es para mostrar; "
             "ningún resultado del módulo depende de ella.",
    ),
    FormulaSpec(
        key="afinidad_hp_hidraulico", topic="afinidad", step="potencia_hidraulica",
        label="Potencia hidráulica entregada al fluido",
        expression="HHP = Q · H · SG / 135771", units="hp",
        symbols={
            "Q": "Caudal [b/d]",
            "H": "Altura desarrollada [ft]",
            "SG": "Gravedad específica del fluido bombeado [-]",
            "135771": "Constante de unidades para Q en b/d y H en ft",
        },
        reference="Apunte de cátedra, Unidad N°9 (pág. 135)",
        module="bes.core.affinity",
        note="Con la potencia al eje de la curva de catálogo cierra la "
             "identidad de rendimiento η = HHP / BHP, que es como se "
             "controlaron las curvas digitalizadas.",
    ),

    # ---------------------------------------------------------- MECÁNICA --
    # Las tres verificaciones que trae al pie toda hoja de engineering data:
    # «Maximum staging may be limited by housing pressure limit, shaft capacity
    # or thrust loading». Manda la MENOR de las tres.
    FormulaSpec(
        key="mec_potencia_eje", topic="mecanica", step="eje",
        label="Potencia sobre el eje",
        expression="HP_eje = P_etapa · N · Pem", units="hp",
        symbols={
            "P_etapa": "Potencia por etapa de la curva de catálogo [hp/etapa]",
            "N": "Cantidad de etapas [-]",
            "Pem": "Gravedad específica media del fluido bombeado [-]",
        },
        reference="Apunte de cátedra, Unidad N°9 (pág. 140)",
        module="bes.core.mechanical",
        note="Pasar el límite del eje estándar obliga a eje de alta "
             "resistencia; pasar el de alta resistencia descarta la bomba.",
    ),
    FormulaSpec(
        key="mec_limite_eje_frecuencia", topic="mecanica", step="eje",
        label="Límite del eje llevado a otra frecuencia",
        expression="HP_lim(f) = HP_lim(f_ref) · f / f_ref", units="hp",
        symbols={
            "HP_lim(f_ref)": "Límite publicado por el fabricante [hp]",
            "f_ref": "Frecuencia a la que el fabricante publica el límite [Hz]",
            "f": "Frecuencia de operación del diseño [Hz]",
        },
        reference="Wood Group ESP, hoja ENGINEERING DATA TD1750 50Hz",
        module="bes.core.mechanical",
        note="Lo que aguanta un eje es un TORQUE, no una potencia, y potencia = "
             "torque × velocidad: por eso el límite escala lineal con la "
             "frecuencia. Los catálogos publican a distintas frecuencias —Wood "
             "Group a 50 Hz— y comparar un diseño de 60 Hz contra un límite de "
             "50 Hz castiga al eje un 20 % de más.",
    ),
    FormulaSpec(
        key="mec_carga_cojinete", topic="mecanica", step="cojinete",
        label="Carga axial sobre el cojinete de empuje",
        expression="TL = Ho · Pem / 2.31 · A_eje", units="lbs",
        symbols={
            "Ho": "Elevación que la bomba tiene que levantar hasta boca de "
                  "pozo [ft]",
            "Pem": "Gravedad específica media del fluido bombeado [-]",
            "2.31": "ft de columna de agua por psi",
            "A_eje": "Sección transversal del eje [in²]",
        },
        reference="Apunte de cátedra, Unidad N°9 (pág. 140)",
        module="bes.core.mechanical",
        note="Es la presión de la columna actuando sobre la sección del eje. "
             "**Va SIN el factor «× N etapas» que trae impreso el apunte**: Ho "
             "ya es la elevación total, o sea la suma de lo que aporta cada "
             "etapa, y multiplicar de nuevo cuenta la columna dos veces. Con el "
             "factor daría 198 000 lbs contra sellos de 5 000–30 000; sin él, "
             "792 lbs, que coincide con la estimación de Takács que ya usaba el "
             "diseño eléctrico. Se toma como errata del impreso.",
    ),
    FormulaSpec(
        key="mec_presion_carcasa", topic="mecanica", step="carcasa",
        label="Presión que soporta la carcasa a caudal cero",
        expression="MaxP = P(Q=0) · N_activas · Pem / 2.31", units="psi",
        symbols={
            "P(Q=0)": "Altura por etapa a caudal cero, el shut-in [ft/etapa]",
            "N_activas": "Etapas ACTIVAS acumuladas hasta esa carcasa [-]",
            "Pem": "Gravedad específica media del fluido bombeado [-]",
            "2.31": "ft de columna de agua por psi",
        },
        reference="Brown Vol. 2b §4.5451", module="bes.core.housing",
        note="El peor caso para el recipiente es caudal cero: ahí la altura por "
             "etapa es máxima y todo el diferencial presiona la carcasa. Se "
             "acumula desde la admisión, así que **la carcasa de arriba es la "
             "crítica**. Las etapas ciegas no generan altura y no se cuentan. "
             "Es restricción DURA: si ningún arreglo entra, la bomba se "
             "descarta.",
    ),
    FormulaSpec(
        key="mec_tope_etapas", topic="mecanica", step="tope_etapas",
        label="Tope de etapas — manda el menor de los tres",
        expression="N_max = mín(N_carcasa, N_eje, N_cojinete)", units="etapas",
        symbols={
            "N_carcasa": "Tope por presión de carcasa [etapas]",
            "N_eje": "Tope por capacidad del eje [etapas]",
            "N_cojinete": "Tope por carga sobre el cojinete de empuje [etapas]",
        },
        reference="Nota al pie de las hojas de engineering data",
        module="bes.core.mechanical",
        note="Las tres verificaciones son independientes: una sarta que entra "
             "en la presión de carcasa puede igual torcer el eje. Una serie sin "
             "ficha en pump_series.json deja las verificaciones SIN REALIZAR — "
             "nunca aprobadas.",
    ),

    # --------------------------------------------------------- ELÉCTRICO --
    FormulaSpec(
        key="elec_caida_tension", topic="electrico", step="caida_cable",
        label="Caída de tensión en el cable",
        expression="ΔV = v_caida · I · L / 1000", units="V",
        symbols={
            "v_caida": "Caída del cable a la temperatura de fondo "
                       "[V por amper por cada 1000 ft]",
            "I": "Corriente del motor a plena carga [A]",
            "L": "Longitud de cable, hasta la profundidad de la bomba [ft]",
        },
        reference="Brown Vol. 2b §4.5332", module="bes.core.electrical",
        note="La caída por amper sale del catálogo interpolada a la temperatura "
             "de fondo: un conductor caliente resiste más.",
    ),
    FormulaSpec(
        key="elec_resistencia_cable", topic="electrico", step="resistencia",
        label="Resistencia del cable",
        expression="R = v_caida / √3 · L / 1000", units="ohm",
        symbols={
            "v_caida": "Caída del cable [V/A por 1000 ft]",
            "√3": "Factor de sistema trifásico",
            "L": "Longitud de cable [ft]",
        },
        reference="Brown Vol. 2b §4.5332", module="bes.core.electrical",
        note="La caída de catálogo es de línea a línea; dividir por √3 la lleva "
             "a resistencia por fase.",
    ),
    FormulaSpec(
        key="elec_perdida_cable", topic="electrico", step="perdida_potencia",
        label="Potencia disipada en el cable",
        expression="P = 3 · I² · R / 1000", units="kW",
        symbols={
            "3": "Las tres fases",
            "I": "Corriente del motor [A]",
            "R": "Resistencia por fase [ohm]",
        },
        reference="Brown Vol. 2b §4.5332", module="bes.core.electrical",
        note="Es plata quemada en el pozo: entra en el costo operativo y en el "
             "criterio para no elegir el conductor más chico que aguante.",
    ),
    FormulaSpec(
        key="elec_tension_arranque", topic="electrico", step="arranque",
        label="Tensión disponible en el arranque",
        expression="r = (V_motor − k · ΔV) / V_motor", units="-",
        symbols={
            "V_motor": "Tensión nominal del motor [V]",
            "k": "Múltiplo de corriente de arranque respecto de la nominal [-]",
            "ΔV": "Caída de tensión del cable a plena carga [V]",
        },
        reference="Brown Vol. 2b §4.5332", module="bes.core.electrical",
        note="En el arranque la corriente es varias veces la nominal y la caída "
             "escala con ella: si la tensión que le llega al motor cae demasiado "
             "no desarrolla par y **no arranca**, aunque en régimen anduviera.",
    ),
    FormulaSpec(
        key="elec_tension_superficie", topic="electrico", step="tension_superficie",
        label="Tensión requerida en superficie",
        expression="V_s = (V_motor + ΔV) · (1 + pérdida/100)", units="V",
        symbols={
            "V_motor": "Tensión nominal del motor [V]",
            "ΔV": "Caída de tensión del cable [V]",
            "pérdida": "Pérdida del transformador [%]",
        },
        reference="Brown Vol. 2b §4.5332", module="bes.core.electrical",
    ),
    FormulaSpec(
        key="elec_kva", topic="electrico", step="transformador",
        label="Potencia aparente del transformador",
        expression="kVA = V_s · I · √3 / 1000", units="kVA",
        symbols={
            "V_s": "Tensión en superficie [V]",
            "I": "Corriente del motor [A]",
            "√3": "Factor de sistema trifásico",
        },
        reference="Brown Vol. 2b §4.5332", module="bes.core.electrical",
    ),
    FormulaSpec(
        key="elec_empuje_axial", topic="electrico", step="empuje_protector",
        label="Empuje axial sobre el protector",
        expression="F = ΔP · A_eje · margen", units="lbs",
        symbols={
            "ΔP": "Presión diferencial que desarrolla la bomba [psi]",
            "A_eje": "Sección transversal del eje [in²]",
            "margen": "Margen de seguridad sobre la estimación [-]",
        },
        reference="Takács, «Electrical Submersible Pumps Manual»",
        module="bes.core.electrical",
        note="Estimación para verificar que el sello elegido banca la carga. "
             "Es la misma magnitud que calcula la verificación mecánica por "
             "otro camino, y por eso sirven de control cruzado.",
    ),
    FormulaSpec(
        key="elec_area_anular", topic="electrico", step="refrigeracion",
        label="Área anular entre el motor y el casing",
        expression="A_anular = (π/4) · (ID_casing² − OD_motor²)", units="in²",
        symbols={
            "ID_casing": "Diámetro interno del casing [in]",
            "OD_motor": "Diámetro externo del motor [in]",
        },
        reference="Geometría", module="bes.core.electrical",
        note="Si da cero o negativo el motor no entra en el casing, y el diseño "
             "falla explícito en vez de seguir con un número sin sentido.",
    ),
    FormulaSpec(
        key="elec_velocidad_motor", topic="electrico", step="refrigeracion",
        label="Velocidad del fluido pasando el motor",
        expression="v = Q · 5.615 / 86400 / (A_anular / 144)", units="ft/s",
        symbols={
            "Q": "Caudal producido [b/d]",
            "5.615": "Conversión de bbl a ft³",
            "86400": "Segundos en un día",
            "A_anular": "Área entre el motor y el casing [in²]",
            "144": "Conversión de in² a ft²",
        },
        reference="Takács, «Electrical Submersible Pumps Manual»",
        module="bes.core.electrical",
        note="El motor se refrigera con el fluido que lo pasa: si va demasiado "
             "lento se recalienta. Brown y Takács recomiendan v ≥ 1 ft/s; por "
             "debajo hay que evaluar camisa de enfriamiento. Es la razón por la "
             "que no siempre se puede poner el motor más chico que entre.",
    ),

    # --------------------------------------------------------------- PVT --
    FormulaSpec(
        key="pvt_sg_petroleo", topic="pvt", step="sg_petroleo",
        label="Gravedad específica del petróleo",
        expression="γ_o = 141.5 / (131.5 + API)", units="-",
        symbols={"API": "Gravedad del petróleo [°API a 60 °F]"},
        reference="Definición API", module="bes.core.pvt",
    ),
    FormulaSpec(
        key="pvt_rs", topic="pvt", step="gas_en_solucion",
        label="Gas en solución (Standing)",
        expression="Rs = γ_g · [ (P_ef/18.2 + 1.4) · 10^(0.0125·API − 0.00091·T) ]^1.2048",
        units="scf/STB",
        symbols={
            "γ_g": "Gravedad específica del gas (aire = 1) [-]",
            "P_ef": "Presión efectiva, mín(P, Pb) [psia]",
            "API": "Gravedad del petróleo [°API]",
            "T": "Temperatura [°F]",
        },
        reference="Standing (1947)", module="bes.core.pvt",
        note="Se evalúa con mín(P, Pb): por encima de la burbuja ya está todo "
             "el gas disuelto y Rs no sigue creciendo. El exponente 1.2048 es "
             "1/0.83.",
    ),
    FormulaSpec(
        key="pvt_pb", topic="pvt", step="presion_burbuja",
        label="Presión de burbuja (Standing invertida)",
        expression="Pb = 18.2 · [ (Rs/γ_g)^0.83 · 10^(0.00091·T − 0.0125·API) − 1.4 ]",
        units="psia",
        symbols={
            "Rs": "Gas en solución a saturación, el GOR total [scf/STB]",
            "γ_g": "Gravedad específica del gas [-]",
            "T": "Temperatura [°F]",
            "API": "Gravedad del petróleo [°API]",
        },
        reference="Standing (1947)", module="bes.core.pvt",
        note="Es la misma correlación de Rs despejada al revés, así que las dos "
             "son consistentes por construcción.",
    ),
    FormulaSpec(
        key="pvt_bo", topic="pvt", step="factor_volumetrico_petroleo",
        label="Factor volumétrico del petróleo (Standing)",
        expression="Bo = 0.9759 + 0.00012 · F^1.2", units="bbl/STB",
        symbols={
            "F": "Grupo de correlación, Rs·(γ_g/γ_o)^0.5 + 1.25·T [-]",
        },
        reference="Standing (1947)", module="bes.core.pvt",
        note="Cuánto se expande un barril de petróleo de tanque al bajar al "
             "pozo, por el gas que lleva disuelto y la temperatura.",
    ),
    FormulaSpec(
        key="pvt_ppc", topic="pvt", step="pseudo_criticas",
        label="Presión pseudo-crítica del gas (Standing)",
        expression="P_pc = 677 + 15·γ_g − 37.5·γ_g²", units="psia",
        symbols={"γ_g": "Gravedad específica del gas (aire = 1) [-]"},
        reference="Standing (1977), citado en Ahmed, «Reservoir Engineering "
                  "Handbook»",
        module="bes.core.pvt",
        note="Un gas natural es una mezcla y no tiene punto crítico propio: se "
             "usan valores «pseudo» a partir de su gravedad específica. "
             "Correlación de gas seco, válida para 0.55 ≤ γ_g ≤ 0.75. Con H₂S "
             "o CO₂ habría que corregir (Wichert-Aziz), que el motor **no** "
             "aplica: el catálogo no lleva composición del gas.",
    ),
    FormulaSpec(
        key="pvt_tpc", topic="pvt", step="pseudo_criticas",
        label="Temperatura pseudo-crítica del gas (Standing)",
        expression="T_pc = 168 + 325·γ_g − 12.5·γ_g²", units="°R",
        symbols={"γ_g": "Gravedad específica del gas (aire = 1) [-]"},
        reference="Standing (1977), citado en Ahmed, «Reservoir Engineering "
                  "Handbook»",
        module="bes.core.pvt",
        note="Misma correlación y mismo rango de validez que P_pc: las dos "
             "salen juntas de la gravedad específica del gas.",
    ),
    FormulaSpec(
        key="pvt_ppr", topic="pvt", step="pseudo_reducidas",
        label="Presión pseudo-reducida",
        expression="P_pr = P / P_pc", units="-",
        symbols={
            "P": "Presión [psia]",
            "P_pc": "Presión pseudo-crítica [psia]",
        },
        reference="Definición de estado correspondiente", module="bes.core.pvt",
        note="Es la variable con la que se entra al factor z: dos gases "
             "distintos con la misma P_pr y T_pr tienen el mismo z.",
    ),
    FormulaSpec(
        key="pvt_tpr", topic="pvt", step="pseudo_reducidas",
        label="Temperatura pseudo-reducida",
        expression="T_pr = (T + 460) / T_pc", units="-",
        symbols={
            "T": "Temperatura [°F]",
            "460": "Conversión de °F a °R",
            "T_pc": "Temperatura pseudo-crítica [°R]",
        },
        reference="Definición de estado correspondiente", module="bes.core.pvt",
        note="La temperatura va en absoluta: dividir °F por °R daría cualquier "
             "cosa.",
    ),
    FormulaSpec(
        key="pvt_z", topic="pvt", step="factor_z",
        label="Factor de compresibilidad del gas (Dranchuk–Abou-Kassem)",
        expression="z = 1 + C₁·ρ_r + C₂·ρ_r² − C₃·ρ_r⁵ + C₄", units="-",
        symbols={
            "ρ_r": "Densidad reducida, 0.27·P_pr/(z·T_pr), con P_pr y T_pr la "
                   "presión y la temperatura pseudo-reducidas [-]",
            "C₁": "A₁ + A₂/T_pr + A₃/T_pr³ + A₄/T_pr⁴ + A₅/T_pr⁵",
            "C₂": "A₆ + A₇/T_pr + A₈/T_pr²",
            "C₃": "A₉ · (A₇/T_pr + A₈/T_pr²)",
            "C₄": "A₁₀ · (1 + A₁₁·ρ_r²) · ρ_r²/T_pr³ · e^(−A₁₁·ρ_r²)",
        },
        reference="Dranchuk & Abou-Kassem, JCPT (1975)", module="bes.core.pvt",
        note="Ecuación de estado de 11 constantes. Es IMPLÍCITA —z aparece a "
             "los dos lados a través de ρ_r— así que se resuelve iterando, con "
             "la correlación de Papay como semilla. Las pseudo-críticas salen "
             "de Standing (ver P_pc y T_pc). Rango declarado por los autores: "
             "1.05 ≤ T_pr ≤ 3.0 y 0.2 ≤ P_pr ≤ 30.",
    ),
    FormulaSpec(
        key="pvt_bg", topic="pvt", step="factor_volumetrico_gas",
        label="Factor volumétrico del gas",
        # 0.005035, NO 0.00504: es la constante que ejecuta `pvt.gas_fvf()`.
        # El catálogo declaraba la redondeada y la pantalla mostraba una
        # fórmula que no era la que corría — que es exactamente lo que este
        # catálogo existe para impedir.
        expression="Bg = 0.005035 · z · (T + 460) / P", units="bbl/scf",
        symbols={
            "z": "Factor de compresibilidad [-]",
            "T": "Temperatura [°F]",
            "460": "Conversión de °F a °R",
            "P": "Presión [psia]",
        },
        reference="Ley de gases reales", module="bes.core.pvt",
        note="Va con **1/P**, y ésa es la razón de fondo del método de "
             "incrementos: el gas cambia de volumen a lo largo de la bomba, así "
             "que el promedio de los extremos no es el valor del punto medio.",
    ),
    FormulaSpec(
        key="pvt_bw", topic="pvt", step="factor_volumetrico_agua",
        label="Factor volumétrico del agua (McCain)",
        # La expresión declarada era OTRA correlación —una forma lineal en ΔT
        # con un solo término en P— y no la que ejecuta `pvt.water_bw()`, que
        # es la ec. 2-125 de Ahmed: cuadrática en presión y con los tres
        # coeficientes A dependientes de la temperatura. No era un redondeo.
        expression="Bw = A₁ + A₂·P + A₃·P² ,  Aᵢ = a₁ᵢ + a₂ᵢ·T + a₃ᵢ·T²",
        units="bbl/STB",
        symbols={
            "P": "Presión [psia]",
            "T": "Temperatura [°F]",
            "Aᵢ": "Coeficientes de presión, cada uno cuadrático en temperatura",
            "a₁ᵢ": "Término independiente del coeficiente Aᵢ [tabulado]",
            "a₂ᵢ": "Término lineal en temperatura del coeficiente Aᵢ [tabulado]",
            "a₃ᵢ": "Término cuadrático en temperatura del coeficiente Aᵢ [tabulado]",
        },
        reference="McCain (1990), «The Properties of Petroleum Fluids», 2ª ed.; "
                  "reproducida en Ahmed (2010), ec. 2-125",
        module="bes.core.pvt",
        note="El agua se expande con la temperatura y se comprime con la "
             "presión; los dos efectos son chicos y se compensan en parte. Los "
             "coeficientes son los de agua **libre de gas**: el agua de "
             "formación disuelve muy poco, y la corrección por salinidad no se "
             "aplica porque el modelo de fluido no lleva composición del agua.",
    ),
    FormulaSpec(
        key="pvt_mu_muerta", topic="pvt", step="viscosidad_muerta",
        label="Viscosidad del crudo muerto (Beggs–Robinson)",
        expression="μ_od = 10^X − 1,  X = T^(−1.163) · e^(6.9824 − 0.04658·API)",
        units="cp",
        symbols={
            "T": "Temperatura [°F]",
            "API": "Gravedad del petróleo [°API]",
        },
        reference="Beggs & Robinson (1975)", module="bes.core.pvt",
        note="**No la usa el procedimiento de crudos viscosos**: ahí manda la "
             "Fig. 4L(2) del libro, que en crudos pesados da bastante más (150 "
             "cp contra 59 para 16 °API a 130 °F). Ésta queda para el PVT "
             "general.",
    ),
    FormulaSpec(
        key="pvt_mu_viva", topic="pvt", step="viscosidad_viva",
        label="Viscosidad del crudo saturado (Beggs–Robinson)",
        expression="μ_ob = a · μ_od^b,  a = 10.715·(Rs+100)^(−0.515),  "
                   "b = 5.44·(Rs+150)^(−0.338)",
        units="cp",
        symbols={
            "μ_od": "Viscosidad del crudo muerto [cp]",
            "Rs": "Gas en solución [scf/STB]",
        },
        reference="Beggs & Robinson (1975)", module="bes.core.pvt",
        note="Misma forma funcional que propuso Chew & Connally (1959) pero con "
             "otros coeficientes: son correlaciones distintas y no hay que "
             "citar una por la otra. **No la usa el procedimiento de crudos "
             "viscosos**, que lee la Fig. 4L(1).",
    ),
    FormulaSpec(
        key="pvt_densidad_petroleo", topic="pvt", step="densidades",
        label="Densidad del petróleo in-situ",
        expression="ρ_o = (62.4·γ_o + 0.0136·Rs·γ_g) / Bo", units="lb/ft³",
        symbols={
            "62.4": "Densidad del agua dulce [lb/ft³]",
            "γ_o": "Gravedad específica del petróleo [-]",
            "0.0136": "Masa de gas por scf y por unidad de γ_g [lb/scf]",
            "Rs": "Gas en solución [scf/STB]",
            "γ_g": "Gravedad específica del gas [-]",
            "Bo": "Factor volumétrico del petróleo [bbl/STB]",
        },
        reference="Balance de masa sobre 1 STB", module="bes.core.pvt",
        note="El numerador es la masa que hay en un barril de tanque —petróleo "
             "más el gas que lleva disuelto— y Bo es el volumen que ocupa ahí "
             "abajo.",
    ),
    FormulaSpec(
        key="pvt_densidad_gas", topic="pvt", step="densidades",
        label="Densidad del gas in-situ",
        expression="ρ_g = 2.70 · γ_g · P / (z · (T + 460))", units="lb/ft³",
        symbols={
            "γ_g": "Gravedad específica del gas [-]",
            "P": "Presión [psia]",
            "z": "Factor de compresibilidad [-]",
            "T": "Temperatura [°F]",
        },
        reference="Ley de gases reales", module="bes.core.pvt",
    ),
)


CATALOG: dict[str, FormulaSpec] = {s.key: s for s in _ENTRIES}


# --------------------------------------------------------------------------
# Consultas
# --------------------------------------------------------------------------

def get_spec(key: str) -> FormulaSpec:
    """Devuelve la declaración de una fórmula.

    Args:
        key: Clave del catálogo.

    Returns:
        La :class:`FormulaSpec`.

    Raises:
        KeyError: Si la clave no está declarada. Es a propósito: una fórmula
            que el motor ejecuta y el catálogo no declara sería justamente lo
            que este módulo viene a evitar.
    """
    try:
        return CATALOG[key]
    except KeyError:
        raise KeyError(
            f"La fórmula '{key}' no está declarada en formula_catalog.py. "
            f"Toda cuenta del motor tiene que estar declarada antes de "
            f"ejecutarse, para que se pueda auditar sin leer código."
        ) from None


def catalog_by_topic() -> list[dict]:
    """El catálogo completo, agrupado por tema y en orden de diseño.

    No necesita correr ningún cálculo: es la declaración, no una corrida. Por
    eso incluye las variantes que un caso concreto no ejecutaría.

    Returns:
        Una lista de dicts, uno por tema, con ``key``, ``label``, ``blurb``,
        ``instrumented`` y ``formulas`` (la lista de specs serializadas).
    """
    salida = []
    for topic in TOPICS:
        specs = [s for s in _ENTRIES if s.topic == topic.key]
        salida.append({
            "key": topic.key,
            "label": topic.label,
            "blurb": topic.blurb,
            "instrumented": topic.instrumented,
            "formulas": [asdict(s) for s in specs],
        })
    return salida
