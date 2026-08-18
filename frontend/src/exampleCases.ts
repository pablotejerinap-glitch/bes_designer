import type { DesignInputs } from "./api/types";

/**
 * Casos precargados: se eligen del menú "Abrir" y reemplazan todo el formulario.
 *
 * Hay tres familias, y la diferencia importa para citarlos:
 *
 *   - **Brown #1A / #2B / #3A / #3B / #4A / #4B** — enunciados impresos de
 *     Kermit Brown, *The Technology of Artificial Lift Methods*, Vol. 2b §4.5.
 *     Los datos son los del libro. Donde el enunciado **no** da un valor que el
 *     modelo exige, se adopta un supuesto y queda anotado en el comentario del
 *     caso con la palabra SUPUESTO. Ninguno se inventó en silencio.
 *   - **Genérico Vaca Muerta** — inventado, representativo de la cuenca
 *     neuquina. No es un pozo real y no debe citarse como tal.
 *   - **Acuífero / Gas en bomba** — escenarios propios del proyecto, ya
 *     verificados contra el backend.
 *
 * En todos, la presión de burbuja es la que Standing devuelve para el GOR, °API
 * y temperatura del caso. Poner una Pb arbitraria haría que el PVT se
 * contradijera consigo mismo.
 *
 * Si el usuario guarda un caso con el mismo nombre, el suyo gana: estos sólo
 * completan los que faltan (ver `readCases()` en App.tsx).
 */

// ---------------------------------------------------------------------------
// Piezas compartidas
// ---------------------------------------------------------------------------

/** Casing 7", 26 lb/ft (API 5CT) — el de los problemas #2B y #4B. */
const CASING_7 = {
  casing_od: 7.0,
  casing_weight: 26.0,
  casing_id: 6.276,
} as const;

/** Casing 5½", 17 lb/ft — el de los problemas #2A, #3A, #3B y #4A. */
const CASING_5_5 = {
  casing_od: 5.5,
  casing_weight: 17.0,
  casing_id: 4.892,
} as const;

/** Tubing 2⅜" O.D. */
const TUBING_2_375 = { tubing_od: 2.375, tubing_id: 1.995 } as const;
/** Tubing 2⅞" O.D. */
const TUBING_2_875 = { tubing_od: 2.875, tubing_id: 2.441 } as const;
/** Tubing nominal 3" = 3½" O.D., 9.3 lb/ft. */
const TUBING_3 = { tubing_od: 3.5, tubing_id: 2.992 } as const;

const SIN_ACIDOS = { h2s_content: 0.0, co2_content: 0.0, sand_production: false } as const;

// ===========================================================================
// a) Genérico — Vaca Muerta (INVENTADO)
// ===========================================================================

/**
 * Pozo tipo de la ventana de petróleo negro de Vaca Muerta (cuenca neuquina),
 * ya entrado en producción y con BES instalada.
 *
 * **Es un caso inventado.** Los valores son representativos de la cuenca
 * —2 900 m TVD, crudo de 36 °API, GOR alto, corte de agua creciente, red de
 * 50 Hz— pero no salen de ningún pozo real ni de ningún informe. No citarlo
 * como dato de campo.
 *
 * Pb = 2 716 psia es la de Standing para 600 scf/STB, 36 °API y 240 °F, así que
 * el PVT es consistente. El reservorio quedó apenas por encima de la burbuja
 * (Pr = 3 000), que es la condición donde la IPR compuesta se ve bien: recta
 * hasta Pb y curva de Vogel abajo.
 *
 * El ensayo se eligió para que la admisión quede con **6,7 % de gas libre**, que
 * es la ventana interesante: por encima del 1 % la fricción pasa a
 * Poettmann-Carpenter y por encima del 5 % el diseño pide separador, pero sigue
 * por debajo del 10 % donde la bomba centrífuga deja de converger. Con un
 * abatimiento mayor el gas libre se iba a ~15 % y el caso dejaba de ser un
 * ejemplo válido del camino convencional.
 *
 * Verificado contra el backend: Centrilift FC1200, 298 etapas (2 bombas en
 * tándem), TDH 3 864 ft, PIP 2 322 psi, motor de 75 hp.
 */
const VACA_MUERTA: DesignInputs = {
  reservoir: {
    static_pressure: 3000.0,
    bubble_point: 2716.0,
    test_pwf: 2600.0,
    test_rate: 900.0,
    ipr_method: "vogel",
    reservoir_temp: 240.0,
    drive_mechanism: "solution_gas",
    fetkovich_n: null,
  },
  fluid: {
    oil_api: 36.0,
    water_cut: 0.35,
    gor: 600.0,
    gas_sg: 0.75,
    water_sg: 1.02,
    oil_viscosity_dead: 2.0,
    viscosity_temp_ref: 100.0,
    bubble_point_pressure: 2716.0,
    ...SIN_ACIDOS,
  },
  well: {
    total_depth: 9500.0,
    ...CASING_5_5,
    ...TUBING_2_875,
    perforations_top: 9200.0,
    perforations_bottom: 9400.0,
    deviation_max: 30.0,
    wellhead_temp: 110.0,
  },
  surface: {
    wellhead_pressure_required: 250.0,
    flowline_length: 3000.0,
    flowline_id: 4.0,
    flowline_elevation_change: 50.0,
    separator_pressure: 150.0,
    power_supply_voltage: 4160.0,
    frequency: 50.0,
  },
  objectives: {
    target_flow_rate: 1200.0,
    safety_margin_depth: 200.0,
    allow_gas_venting: true,
    max_gip: 0.1,
    design_life_years: 5.0,
    use_vsd: true,
    design_frequency_hz: null,
  },
};

// ===========================================================================
// b) Brown #1A — §4.5332 "Example problem #1A (no gas)"
// ===========================================================================

/**
 * Pozo de agua, sin gas. Es el ejemplo que el libro usa para introducir el
 * procedimiento completo: 10 000 b/d, casing 8⅝", tubing 5½".
 *
 * Del enunciado impreso: casing 8⅝" O.D., tubing 5½" O.D. (nuevo), profundidad
 * 2 200 ft, punzados 1 900-2 200, primario 12 500 V, nivel estático 500 ft bajo
 * boca, γw = 1.1, T = 120 °F, PI = 10 b/d/ft de abatimiento, caudal deseado
 * 10 000 b/d, línea de 2 000 ft de 4" con 30 ft de subida, todo caño nuevo.
 *
 * SUPUESTOS (el enunciado no los da): peso de casing 24 lb/ft para fijar el ID,
 * temperatura de boca 75 °F, presión de separador 50 psi, tensión de
 * alimentación 4 160 V (los 12 500 V son el primario del transformador, no la
 * tensión disponible en el equipo), °API y viscosidad del petróleo son
 * irrelevantes con 100 % de agua pero el modelo los exige.
 *
 * OJO con la presión de cabeza: queda en 0 psi. El libro deriva la Pwh de la
 * línea de conducción, y el motor **no** hace esa cuenta —usa
 * `wellhead_pressure_required` tal cual (ver `tdh.py`)—, así que el término de
 * cabeza del TDH queda nulo. Es el mismo valor que traía el escenario validado
 * del proyecto; no se cambió para no mover un caso ya contrastado.
 *
 * Referencia impresa: TDH ≈ 1 670 ft, 28 etapas, ≈180 hp, bomba Centrilift I-300.
 *
 * Verificado contra el backend: elige la **I-300**, TDH 1 721 ft (+3 %) y 29
 * etapas (+4 %). La potencia da 217 hp al eje contra los ≈180 impresos, y el
 * desvío es enteramente el SG: acá el fluido es agua pura de γw = 1.1, y
 * 217 × 0.945/1.10 = 186 hp. El valor impreso sale de un SG de 0.945, no de
 * 1.10. Conviene contrastarlo con la página del libro antes de citarlo.
 */
const BROWN_1A: DesignInputs = {
  reservoir: {
    static_pressure: 1250.0,
    bubble_point: 0.0,
    test_pwf: 1000.0,
    test_rate: 2500.0,
    ipr_method: "linear",
    reservoir_temp: 120.0,
    drive_mechanism: "water_drive",
    fetkovich_n: null,
  },
  fluid: {
    oil_api: 35.0,
    water_cut: 1.0,
    gor: 0.0,
    gas_sg: 0.65,
    water_sg: 1.1,
    oil_viscosity_dead: 1.0,
    viscosity_temp_ref: 100.0,
    bubble_point_pressure: 0.0,
    ...SIN_ACIDOS,
  },
  well: {
    total_depth: 2200.0,
    casing_od: 8.625,
    casing_weight: 24.0,
    casing_id: 8.097,
    tubing_od: 5.5,
    tubing_id: 4.778,
    perforations_top: 1900.0,
    perforations_bottom: 2200.0,
    deviation_max: 0.0,
    wellhead_temp: 75.0,
  },
  surface: {
    wellhead_pressure_required: 0.0,
    flowline_length: 2000.0,
    flowline_id: 4.0,
    flowline_elevation_change: 30.0,
    separator_pressure: 50.0,
    power_supply_voltage: 4160.0,
    frequency: 60.0,
  },
  objectives: {
    target_flow_rate: 10000.0,
    safety_margin_depth: 100.0,
    allow_gas_venting: false,
    max_gip: 0.1,
    design_life_years: 5.0,
    use_vsd: false,
    design_frequency_hz: null,
  },
};

// ===========================================================================
// c) Brown #2B — "Class problem 2-B"
// ===========================================================================

/**
 * Pozo de 10 000 ft que produce 25 % petróleo y 75 % agua, con el gas libre
 * venteado por el anular.
 *
 * Del enunciado impreso: tubing 3", casing 7", profundidad 10 000 ft, 25 %
 * petróleo / 75 % agua, Pr = 2 800 psi, PI = 10 b/d/psi, °API = 36, γw = 1.07,
 * GOR = 100 scf/B (el gas libre se ventea), presión de separador 100 psi, línea
 * de 3 000 ft de 4" con 200 ft de subida.
 *
 * El ensayo se carga como Pwf = 2 600 psi con 2 000 b/d, que es exactamente el
 * PI = 10 b/d/psi del enunciado (2 000 / 200 psi de abatimiento). El modelo
 * pide un punto medido, no el índice ya procesado.
 *
 * SUPUESTOS (el enunciado no los da): temperatura de reservorio 180 °F y de
 * boca 100 °F; γg = 0.65; viscosidad muerta 2 cp a 100 °F; peso de casing
 * 26 lb/ft para fijar el ID; punzados 9 900-10 000 ft (sólo se da la
 * profundidad); tensión 4 160 V; "tubing 3 in" se interpreta como el nominal de
 * 3½" O.D. (ID 2.992"), que es la designación API — cuando Brown quiere decir
 * diámetro exterior lo escribe "O.D.", como en el #1A y el #3A.
 *
 * La presión de cabeza se carga con los 100 psi del separador: el motor no
 * convierte la línea de conducción en Pwh, así que las pérdidas de los 3 000 ft
 * de 4" y los 200 ft de subida **no** entran al TDH.
 *
 * Pb = 590 psia (Standing para 100 scf/STB, 36 °API, 180 °F) queda muy por
 * debajo de la admisión, así que no hay gas libre en la bomba — coherente con
 * la premisa "assume free gas is vented" y con el método IPR lineal.
 *
 * Referencia impresa: TDH ≈ 4 258 ft, 112 etapas, ≈65 hp, Centrilift I-42B, a
 * unos 2 080 b/d.
 *
 * **La app no elige la I-42B, y no es un error.** Con 2 080 b/d hay 12 bombas
 * candidatas y el orden es por distancia al BEP: la REDA DN2150 tiene su BEP
 * justo en 2 080 (distancia 0 %) y la I-42B queda séptima, a 22,4 %. El libro
 * eligió dentro de la línea Centrilift de 1980; el catálogo de hoy tiene bombas
 * mucho mejor centradas. Forzando la I-42B a mano (selección manual de bomba),
 * el head por etapa da **38,10 ft, exactamente el del libro**, y salen 117
 * etapas contra 112 — la diferencia es el +4,7 % del TDH, no la hidráulica.
 *
 * La potencia sí se aparta: 84 hp al eje contra los ≈65 impresos. El desvío es
 * la densidad de la mezcla — con 75 % de agua a γw = 1.07 el SG da 1.014, y los
 * 65 hp del libro salen de un SG cercano a 0.82. Vale la pena contrastarlo
 * contra la página impresa antes de citarlo.
 */
const BROWN_2B: DesignInputs = {
  reservoir: {
    static_pressure: 2800.0,
    bubble_point: 590.0,
    test_pwf: 2600.0,
    test_rate: 2000.0,
    ipr_method: "linear",
    reservoir_temp: 180.0,
    drive_mechanism: "water_drive",
    fetkovich_n: null,
  },
  fluid: {
    oil_api: 36.0,
    water_cut: 0.75,
    gor: 100.0,
    gas_sg: 0.65,
    water_sg: 1.07,
    oil_viscosity_dead: 2.0,
    viscosity_temp_ref: 100.0,
    bubble_point_pressure: 590.0,
    ...SIN_ACIDOS,
  },
  well: {
    total_depth: 10000.0,
    ...CASING_7,
    ...TUBING_3,
    perforations_top: 9900.0,
    perforations_bottom: 10000.0,
    deviation_max: 0.0,
    wellhead_temp: 100.0,
  },
  surface: {
    wellhead_pressure_required: 100.0,
    flowline_length: 3000.0,
    flowline_id: 4.0,
    flowline_elevation_change: 200.0,
    separator_pressure: 100.0,
    power_supply_voltage: 4160.0,
    frequency: 60.0,
  },
  objectives: {
    target_flow_rate: 2080.0,
    safety_margin_depth: 100.0,
    allow_gas_venting: true,
    max_gip: 0.1,
    design_life_years: 5.0,
    use_vsd: false,
    design_frequency_hz: null,
  },
};

// ===========================================================================
// d) Brown #3A — §4.53103 "Example problem #3-A; pumping gas"
// ===========================================================================

/**
 * El ejemplo que ancla el **método de incrementos de presión**: 500 b/d con
 * 50 % de agua, GOR 500 scf/B y bombeo del 100 % del gas.
 *
 * Del enunciado impreso: profundidad 7 000 ft, tubing 2⅜" O.D., casing 5½",
 * Pr = 1 000 psi, Pwf = 500 psi, Pwh = 200 psi, G/O = 500 scf/b (GLR = 250),
 * γg = 0.65, qL = 500 b/d (50 % agua), γw = 1.07, γo = 35 °API, T superficie
 * 120 °F, T fondo 160 °F, se bombea el 100 % del gas.
 *
 * El libro resuelve el tramo de 500 a 700 psi para mostrar el procedimiento.
 * Usalo en la pestaña **"Pozo con gas"** con escalón de 200 psi para reproducir
 * ese tramo exacto.
 *
 * `max_gip = 1.0` **no es un descuido**: el enunciado dice "pumping 100 % of
 * gas", o sea sin separador. Es el único motivo para subirlo.
 *
 * Verificado contra el backend: por la pestaña "Pozo con gas" (escalón 200 psi)
 * da Centrilift DC800, 323 etapas, 31 hp, admisión 572 → descarga 2 010 psi en
 * 8 tramos, con 49,5 % de gas libre en la admisión que el separador baja a
 * 2,9 % en la bomba.
 *
 * **Por el camino convencional este caso devuelve 422** ("no se pudo armar un
 * diseño completo"), y está bien que así sea: con casi 50 % de gas libre en la
 * admisión el diseño monofásico no tiene sentido. Es justamente el pozo que hay
 * que resolver por incrementos.
 *
 * SUPUESTOS: punzados 6 950-7 000 ft; ensayo Pwf = 800 psi con 273.3 b/d, que
 * es el par que reproduce el punto (500 psi, 500 b/d) del enunciado por Vogel;
 * viscosidad muerta 5 cp; separador 100 psi; línea 1 000 ft de 3"; 4 160 V.
 */
const BROWN_3A: DesignInputs = {
  reservoir: {
    static_pressure: 1000.0,
    bubble_point: 2000.0,
    test_pwf: 800.0,
    test_rate: 273.3333,
    ipr_method: "vogel",
    reservoir_temp: 160.0,
    drive_mechanism: "solution_gas",
    fetkovich_n: null,
  },
  fluid: {
    oil_api: 35.0,
    water_cut: 0.5,
    gor: 500.0,
    gas_sg: 0.65,
    water_sg: 1.07,
    oil_viscosity_dead: 5.0,
    viscosity_temp_ref: 100.0,
    bubble_point_pressure: 2000.0,
    ...SIN_ACIDOS,
  },
  well: {
    total_depth: 7000.0,
    ...CASING_5_5,
    ...TUBING_2_375,
    perforations_top: 6950.0,
    perforations_bottom: 7000.0,
    deviation_max: 0.0,
    wellhead_temp: 120.0,
  },
  surface: {
    wellhead_pressure_required: 200.0,
    flowline_length: 1000.0,
    flowline_id: 3.0,
    flowline_elevation_change: 0.0,
    separator_pressure: 100.0,
    power_supply_voltage: 4160.0,
    frequency: 60.0,
  },
  objectives: {
    target_flow_rate: 500.0,
    safety_margin_depth: 50.0,
    allow_gas_venting: false,
    max_gip: 1.0,
    design_life_years: 5.0,
    use_vsd: false,
    design_frequency_hz: null,
  },
};

// ===========================================================================
// e) Brown #3B — §4.53104-07 "Class problem #3-B (well pumping gas)"
// ===========================================================================

/**
 * El mismo método de incrementos pero llevado al **diseño completo**, y con el
 * pozo produciendo todo petróleo.
 *
 * Del enunciado impreso: profundidad 8 000 ft, tubing 2⅜" O.D., casing 5½",
 * Pr = 1 200 psi, Pwf = 400 psi, Pwh = 180 psi, GOR = 600 scf/B, γg = 0.7,
 * qL = 800 b/d a esa Pwf, γo = 36 °API, T = 170 °F. Pide las etapas entre
 * 400 y 600 psi de admisión, en dos variantes: (a) todo petróleo y (b) 50 % de
 * agua con γw = 1.12.
 *
 * Este caso carga la variante **(a), todo petróleo**. Para la (b) alcanza con
 * poner corte de agua 0.5 y γw 1.12 en la pestaña Fluido.
 *
 * `max_gip = 1.0` por el mismo motivo que el #3A: el ejemplo bombea el gas.
 *
 * SUPUESTOS: punzados 7 950-8 000 ft; ensayo Pwf = 400 psi con 800 b/d, que es
 * el punto que da el propio enunciado; viscosidad muerta 5 cp a 100 °F;
 * temperatura de boca 120 °F; separador 100 psi; línea 1 000 ft de 3"; 4 160 V.
 *
 * OJO al comparar: las **209 etapas** que circulan como respuesta del "#3B" (y
 * que están en `docs/EJEMPLO_3B_BROWN.md` y en el fixture `example_3b_brown`)
 * **no son de este pozo**. Corresponden al ejemplo resuelto de §4.53104-07, que
 * continúa el pozo del #3-A: 7 000 ft, GOR 500, 35 °API, 160 °F. Este caso es
 * el CLASS PROBLEM #3-B del enunciado, que es otro pozo: 8 000 ft, GOR 600,
 * 36 °API, 170 °F. No hay respuesta impresa disponible para contrastarlo.
 *
 * Verificado contra el backend por la pestaña "Pozo con gas" (escalón 200 psi):
 * Centrilift FC2200, 279 etapas, 52 hp, admisión 392 → descarga 1 240 psi en
 * 5 tramos. Gas libre 79,2 % en la admisión, que el separador del catálogo baja
 * a 10,2 % en la bomba — **apenas por encima del 10 %**. Pasa sólo porque este
 * caso lleva `max_gip = 1.0` para reproducir la premisa del libro; con el 0,10
 * por defecto el diseño se rechazaría, y sería lo correcto.
 */
const BROWN_3B: DesignInputs = {
  reservoir: {
    static_pressure: 1200.0,
    bubble_point: 2000.0,
    test_pwf: 400.0,
    test_rate: 800.0,
    ipr_method: "vogel",
    reservoir_temp: 170.0,
    drive_mechanism: "solution_gas",
    fetkovich_n: null,
  },
  fluid: {
    oil_api: 36.0,
    water_cut: 0.0,
    gor: 600.0,
    gas_sg: 0.7,
    water_sg: 1.12,
    oil_viscosity_dead: 5.0,
    viscosity_temp_ref: 100.0,
    bubble_point_pressure: 2000.0,
    ...SIN_ACIDOS,
  },
  well: {
    total_depth: 8000.0,
    ...CASING_5_5,
    ...TUBING_2_375,
    perforations_top: 7950.0,
    perforations_bottom: 8000.0,
    deviation_max: 0.0,
    wellhead_temp: 120.0,
  },
  surface: {
    wellhead_pressure_required: 180.0,
    flowline_length: 1000.0,
    flowline_id: 3.0,
    flowline_elevation_change: 0.0,
    separator_pressure: 100.0,
    power_supply_voltage: 4160.0,
    frequency: 60.0,
  },
  objectives: {
    target_flow_rate: 800.0,
    safety_margin_depth: 50.0,
    allow_gas_venting: false,
    max_gip: 1.0,
    design_life_years: 5.0,
    use_vsd: false,
    design_frequency_hz: null,
  },
};

// ===========================================================================
// f) Brown #4A y #4B — "Class problem #4 (pumping viscous crudes)"
// ===========================================================================

/**
 * Crudo de 14 °API con 50 % de agua. Por debajo de los 28 °API la corrección
 * por viscosidad de Riling (§4.53112) muerde de verdad, y es lo que este caso
 * viene a mostrar.
 *
 * Del enunciado impreso: casing 5½" × tubing 2⅜" O.D., punzados 6 400-6 450 ft,
 * longitud de tubing 6 300 ft, PI = 5, Pr = 1 750 psia, corte de agua 50 %
 * (γw = 1.07), caudal deseado 1 500 b/d de líquido total, Pwh = 120 psi,
 * 14 °API, temperatura de fondo 160 °F. "Assume no gas is to be pumped."
 *
 * Los 6 300 ft de tubing fijan la profundidad de admisión, que es el tope de
 * punzados (6 400) menos 100 ft de margen — por eso `safety_margin_depth` = 100
 * y no es un número elegido.
 *
 * El ensayo se carga como Pwf = 1 550 psia con 1 000 b/d, que es exactamente el
 * PI = 5 b/d/psi del enunciado (1 000 / 200 psi de abatimiento).
 *
 * SUPUESTOS: GOR = 0 (el enunciado dice que no se bombea gas); peso de casing
 * 17 lb/ft; temperatura de boca 100 °F; viscosidad muerta 250 cp a 100 °F, que
 * es el orden de magnitud de un crudo de 14 °API y hace que Riling tenga algo
 * que corregir; separador 100 psi; línea 1 000 ft de 3"; 4 160 V; 60 Hz.
 *
 * Verificado contra el backend: Centrilift FC1600, 163 etapas, TDH 3 793 ft,
 * motor de 102 hp. Sale **una sola alternativa**, no tres: el caudal alto en
 * casing de 5½" deja pocas bombas candidatas.
 *
 * Mirá los avisos que levanta: la viscosidad medida está referida a 100 °F y la
 * admisión trabaja a 159 °F, así que el motor la descarta y estima con
 * Beggs-Robinson (34,5 cp). Y el paso 5 de Riling —la corrección por corte de
 * agua— queda **sin realizar** por falta de una viscosidad de mezcla medida.
 * Con 50 % de agua eso puede subestimar bastante; no es un detalle menor si el
 * caso se usa para la tesis.
 */
const BROWN_4A: DesignInputs = {
  reservoir: {
    static_pressure: 1750.0,
    bubble_point: 0.0,
    test_pwf: 1550.0,
    test_rate: 1000.0,
    ipr_method: "linear",
    reservoir_temp: 160.0,
    drive_mechanism: "water_drive",
    fetkovich_n: null,
  },
  fluid: {
    oil_api: 14.0,
    water_cut: 0.5,
    gor: 0.0,
    gas_sg: 0.65,
    water_sg: 1.07,
    oil_viscosity_dead: 250.0,
    viscosity_temp_ref: 100.0,
    bubble_point_pressure: 0.0,
    ...SIN_ACIDOS,
  },
  well: {
    total_depth: 6450.0,
    ...CASING_5_5,
    ...TUBING_2_375,
    perforations_top: 6400.0,
    perforations_bottom: 6450.0,
    deviation_max: 0.0,
    wellhead_temp: 100.0,
  },
  surface: {
    wellhead_pressure_required: 120.0,
    flowline_length: 1000.0,
    flowline_id: 3.0,
    flowline_elevation_change: 0.0,
    separator_pressure: 100.0,
    power_supply_voltage: 4160.0,
    frequency: 60.0,
  },
  objectives: {
    target_flow_rate: 1500.0,
    safety_margin_depth: 100.0,
    allow_gas_venting: true,
    max_gip: 0.1,
    design_life_years: 5.0,
    use_vsd: false,
    design_frequency_hz: null,
  },
};

/**
 * El más pesado de los dos: 12 °API, 8 000 ft, casing 7".
 *
 * Del enunciado impreso: casing 7", tubing 3", longitud de tubing 8 000 ft,
 * punzados 8 030-8 090 ft, PI = 2, Pr = 2 600 psi, corte de agua 40 %
 * (γw = 1.10), caudal deseado 1 800 b/d de líquido total, Pwh = 160 psig,
 * 12 °API, T a 8 000 ft = 200 °F, GOR = 100 scf/b. "Assume pumping no gas."
 *
 * Los 8 000 ft de tubing contra los 8 030 de tope de punzados fijan el margen
 * en 30 ft.
 *
 * El ensayo se carga como Pwf = 2 100 psia con 1 000 b/d — el PI = 2 b/d/psi
 * del enunciado (1 000 / 500 psi de abatimiento).
 *
 * OJO — **psig vs psia**: el enunciado da la Pwh en psig y el motor trabaja en
 * psia. Se carga 160 tal cual, que es lo que hace el resto del proyecto; si
 * querés ser estricto son 174.7 psia. La diferencia son ~35 ft de TDH.
 *
 * SUPUESTOS: peso de casing 26 lb/ft; "tubing 3 in" = 3½" O.D. (mismo criterio
 * que el #2B); temperatura de boca 100 °F; γg = 0.65; viscosidad muerta 400 cp
 * a 100 °F; separador 100 psi; línea 1 000 ft de 3"; 4 160 V; 60 Hz.
 *
 * Pb = 1 255 psia (Standing para 100 scf/STB, 12 °API, 200 °F). Con la admisión
 * por encima de ese valor no hay gas libre en la bomba, que es la premisa
 * "pumping no gas" del enunciado.
 *
 * Verificado contra el backend: REDA DN1800, 257 etapas, TDH 4 725 ft, motor de
 * 105 hp, 0,00 % de gas libre en la admisión — la premisa se cumple sola.
 *
 * Levanta un aviso propio de este caso: el libro publica tablas de corrección
 * para bombas de 60 % y 70 % de rendimiento máximo, y ésta da 73,6 %, así que
 * se usa la tabla del extremo más cercano **sin extrapolar**. Igual que el #4A,
 * el paso de corte de agua de Riling queda sin realizar.
 */
const BROWN_4B: DesignInputs = {
  reservoir: {
    static_pressure: 2600.0,
    bubble_point: 1255.0,
    test_pwf: 2100.0,
    test_rate: 1000.0,
    ipr_method: "linear",
    reservoir_temp: 200.0,
    drive_mechanism: "water_drive",
    fetkovich_n: null,
  },
  fluid: {
    oil_api: 12.0,
    water_cut: 0.4,
    gor: 100.0,
    gas_sg: 0.65,
    water_sg: 1.1,
    oil_viscosity_dead: 400.0,
    viscosity_temp_ref: 100.0,
    bubble_point_pressure: 1255.0,
    ...SIN_ACIDOS,
  },
  well: {
    total_depth: 8090.0,
    ...CASING_7,
    ...TUBING_3,
    perforations_top: 8030.0,
    perforations_bottom: 8090.0,
    deviation_max: 0.0,
    wellhead_temp: 100.0,
  },
  surface: {
    wellhead_pressure_required: 160.0,
    flowline_length: 1000.0,
    flowline_id: 3.0,
    flowline_elevation_change: 0.0,
    separator_pressure: 100.0,
    power_supply_voltage: 4160.0,
    frequency: 60.0,
  },
  objectives: {
    target_flow_rate: 1800.0,
    safety_margin_depth: 30.0,
    allow_gas_venting: true,
    max_gip: 0.1,
    design_life_years: 5.0,
    use_vsd: false,
    design_frequency_hz: null,
  },
};

// ===========================================================================
// Escenarios propios del proyecto (previos, ya verificados)
// ===========================================================================

const SUPERFICIE_PROPIA = {
  wellhead_pressure_required: 250.0,
  flowline_length: 1500.0,
  flowline_id: 3.0,
  flowline_elevation_change: 0.0,
  separator_pressure: 100.0,
  power_supply_voltage: 480.0,
  frequency: 50.0,
} as const;

/**
 * Pozo con empuje por acuífero, sin gas libre.
 *
 * El acuífero mantiene la presión muy por encima de la de burbuja, así que el
 * flujo en la formación es monofásico en todo el rango operativo: por eso el
 * método IPR es el **lineal** y no Vogel. El corte de agua alto (80 %) y el GOR
 * bajo (20 scf/STB, sólo gas residual en solución) caracterizan a un pozo
 * maduro de este tipo.
 *
 * Verificado: 0,00 % de gas libre en la admisión → la fricción se calcula por
 * Hazen-Williams. Resultado esperado ≈ REDA DN2150, 97 etapas, motor de 38 hp.
 */
const ACUIFERO: DesignInputs = {
  reservoir: {
    static_pressure: 3000.0,
    bubble_point: 400.0,
    test_pwf: 2450.0,
    test_rate: 1600.0,
    ipr_method: "linear",
    reservoir_temp: 175.0,
    drive_mechanism: "water_drive",
    fetkovich_n: null,
  },
  fluid: {
    oil_api: 28.0,
    water_cut: 0.8,
    gor: 20.0,
    gas_sg: 0.65,
    water_sg: 1.05,
    oil_viscosity_dead: 1.8,
    viscosity_temp_ref: 100.0,
    bubble_point_pressure: 400.0,
    ...SIN_ACIDOS,
  },
  well: {
    total_depth: 6200.0,
    ...CASING_7,
    ...TUBING_2_875,
    perforations_top: 5900.0,
    perforations_bottom: 6100.0,
    deviation_max: 5.0,
    wellhead_temp: 95.0,
  },
  surface: { ...SUPERFICIE_PROPIA },
  objectives: {
    target_flow_rate: 1800.0,
    safety_margin_depth: 200.0,
    allow_gas_venting: true,
    max_gip: 0.1,
    design_life_years: 5.0,
    use_vsd: false,
    design_frequency_hz: null,
  },
};

/**
 * Pozo con gas libre en la bomba, por debajo del 10 %.
 *
 * Empuje por gas en solución, con la presión de admisión (1 317 psia) por
 * debajo de la de burbuja (1 572 psia): parte del gas ya se liberó y entra a la
 * bomba. La Pb es la que Standing devuelve para 250 scf/STB, 30 °API y 190 °F.
 *
 * Verificado: **5,89 % de gas libre** en la admisión (relación V_g/V_l = 0,063),
 * que cae entre dos umbrales y dispara las dos consecuencias: por encima del
 * 1 % la fricción pasa a Poettmann-Carpenter, y por encima del 5 % el diseño
 * recomienda separador. Queda cómodo bajo el 10 %, que es donde la bomba
 * centrífuga deja de converger.
 *
 * Resultado esperado ≈ REDA DN1800, 165 etapas (2 bombas en tándem), 37,5 hp.
 */
const CON_GAS: DesignInputs = {
  reservoir: {
    static_pressure: 2400.0,
    bubble_point: 1572.0,
    test_pwf: 1700.0,
    test_rate: 1200.0,
    ipr_method: "vogel",
    reservoir_temp: 190.0,
    drive_mechanism: "solution_gas",
    fetkovich_n: null,
  },
  fluid: {
    oil_api: 30.0,
    water_cut: 0.35,
    gor: 250.0,
    gas_sg: 0.65,
    water_sg: 1.05,
    oil_viscosity_dead: 2.5,
    viscosity_temp_ref: 100.0,
    bubble_point_pressure: 1572.0,
    ...SIN_ACIDOS,
  },
  well: {
    total_depth: 5000.0,
    ...CASING_7,
    ...TUBING_2_875,
    perforations_top: 4700.0,
    perforations_bottom: 4900.0,
    deviation_max: 5.0,
    wellhead_temp: 95.0,
  },
  surface: { ...SUPERFICIE_PROPIA },
  objectives: {
    target_flow_rate: 1600.0,
    safety_margin_depth: 200.0,
    allow_gas_venting: true,
    max_gip: 0.1,
    design_life_years: 5.0,
    use_vsd: false,
    design_frequency_hz: null,
  },
};

// ---------------------------------------------------------------------------
// Registro. El orden es el del menú: primero el genérico, después los seis
// ejemplos del libro en el orden del capítulo, y al final los propios.
// ---------------------------------------------------------------------------

export const EXAMPLE_CASES: Record<string, DesignInputs> = {
  "Genérico · Vaca Muerta (inventado)": VACA_MUERTA,
  "Brown #1A · Pozo de agua, sin gas": BROWN_1A,
  "Brown #2B · 25 % petróleo / 75 % agua": BROWN_2B,
  "Brown #3A · Con gas — incrementos": BROWN_3A,
  "Brown #3B · Con gas — diseño completo": BROWN_3B,
  "Brown #4A · Crudo viscoso 14 °API": BROWN_4A,
  "Brown #4B · Crudo viscoso 12 °API": BROWN_4B,
  "Propio · Acuífero (sin gas)": ACUIFERO,
  "Propio · Gas en bomba (5,9 %)": CON_GAS,
};

/** Orden de presentación en el menú (los `Record` no garantizan orden estable
 *  para claves no numéricas en todos los motores, y acá el orden es
 *  información: sigue al capítulo del libro). */
export const EXAMPLE_ORDER: readonly string[] = Object.keys(EXAMPLE_CASES);
