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
 *   - **Pozo real MA-102** — datos de un informe de diseño de SLB, con el
 *     aparejo de referencia anotado. Es el único caso que sale de un pozo que
 *     existe, así que la trazabilidad de cada dato está escrita en su
 *     docstring: qué vino del informe, qué se derivó y qué es supuesto.
 *
 * En los casos inventados y en los del libro, la presión de burbuja es la que
 * Standing devuelve para el GOR, °API y temperatura del caso. Poner una Pb
 * arbitraria haría que el PVT se contradijera consigo mismo. **La excepción es
 * el MA-102**, donde hay un dato medido de laboratorio y ése manda sobre la
 * correlación; la diferencia queda anotada en su docstring.
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
 * **La app ya no puede elegir la I-300**: las tres bombas del libro se
 * retiraron del catálogo en ago-2026, porque la aplicación publica sólo curvas
 * digitalizadas de catálogos reales de fabricante. Sus datos impresos siguen
 * en `backend/tests/data/brown_pumps.json` y con ellos los tests reproducen el
 * ejemplo: elegía la I-300, TDH 1 721 ft (+3 %) y 29 etapas (+4 %).
 *
 * Con el catálogo de hoy el pozo se diseña con una **REDA GN10000** (62 etapas,
 * 205 hp al eje), que es una bomba real para 10 000 b/d. La comparación contra
 * el impreso ya no es bomba a bomba: lo que se contrasta es el TDH y el método.
 *
 * Sobre la potencia del libro: los ≈180 hp impresos salen de un SG de 0.945, no
 * del 1.10 del agua pura de este caso. Conviene contrastarlo con la página del
 * libro antes de citarlo.
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
// c) Brown #2B — §4.539 "Example problem #2B, oil well producing no gas"
// ===========================================================================

/**
 * Pozo de 11 000 ft con 30 % de agua y crudo de 40 °API, **sin gas**.
 *
 * Del enunciado impreso (§4.539, pág. 72): casing 7" O.D. 23 lb/ft, tubing
 * 2⅞" EUE 8rd, profundidad al fondo del casing 11 000 ft, punzados
 * 10 600-10 650 ft, presión estática 2 900 psig a 10 000 ft, presión fluyente
 * 2 540 psig a 10 000 ft para 1 000 STB/d totales, corte de agua 30 %,
 * 40 °API, γw = 1.05, viscosidad muerta 3.6 cp a 100 °F y 1.6 cp a 200 °F,
 * temperatura de pozo 225 °F a 10 000 ft y 160 °F en boca, presión requerida
 * en cabeza 200 psig, 60 Hz, caudal buscado 1 600 STB/d totales.
 *
 * El ensayo se carga como Pwf = 2 540 psi con 1 000 STB/d, que da el
 * PI = 2.78 b/d/psi del enunciado (1 000 / 360 psi de abatimiento).
 *
 * **GOR = 0**: el título del ejemplo es «oil well producing NO gas» y el texto
 * aclara que la cantidad de gas es tan chica que puede ignorarse. Sin gas
 * libre la pérdida de carga va por Hazen-Williams, que es lo que hace el libro.
 *
 * **La profundidad de asentamiento se fija a mano en 4 000 ft**, que es donde
 * el libro pone la bomba («set pump at 4000 ft from surface»). El enunciado
 * dice «as deep as necessary» y el autor la elige por el criterio de
 * sumergencia; no se deduce de los punzados, así que se carga explícita.
 *
 * SUPUESTOS (el enunciado no los da): γg = 0.65; tensión de red 4 160 V; línea
 * de conducción irrelevante para este cálculo —el TDH del libro usa la presión
 * de cabeza de 200 psig y no las pérdidas de la línea—.
 *
 * Referencia impresa: TDH = 4 258 ft, Centrilift I-42B (serie 513), 112 etapas,
 * ≈65 hp al eje, motor 75 hp (serie 544, 1 350 V, 35 A), cable #4 CU de
 * 4 100 ft, tensión de superficie 1 422 V, 86 kVA → 3 × 37.5 kVA.
 *
 * **La app no elige la I-42B**: esa bomba se retiró del catálogo en ago-2026
 * junto con las otras dos del libro, porque la aplicación publica sólo curvas
 * de catálogos comerciales vigentes. La validación del conteo de etapas sobre
 * la curva impresa se hace desde los tests, inyectándola con
 * `tests.brown_pumps`.
 */
const BROWN_2B: DesignInputs = {
  reservoir: {
    static_pressure: 2900.0,
    bubble_point: 0.0,
    test_pwf: 2540.0,
    test_rate: 1000.0,
    ipr_method: "linear",
    reservoir_temp: 225.0,
    drive_mechanism: "water_drive",
    fetkovich_n: null,
  },
  fluid: {
    oil_api: 40.0,
    water_cut: 0.30,
    gor: 0.0,
    gas_sg: 0.65,
    water_sg: 1.05,
    oil_viscosity_dead: 1.6,
    viscosity_temp_ref: 200.0,
    bubble_point_pressure: 0.0,
    ...SIN_ACIDOS,
  },
  well: {
    total_depth: 11000.0,
    casing_od: 7.0,
    casing_weight: 23.0,
    casing_id: 6.366,
    ...TUBING_2_875,
    perforations_top: 10600.0,
    perforations_bottom: 10650.0,
    deviation_max: 0.0,
    wellhead_temp: 160.0,
    pump_setting_depth: 4000.0,
  },
  surface: {
    wellhead_pressure_required: 200.0,
    flowline_length: 1000.0,
    flowline_id: 4.0,
    flowline_elevation_change: 0.0,
    separator_pressure: 100.0,
    power_supply_voltage: 4160.0,
    frequency: 60.0,
  },
  objectives: {
    target_flow_rate: 1600.0,
    safety_margin_depth: 0.0,
    allow_gas_venting: false,
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


// ===========================================================================
// d) Pozo real MA-102 — Meseta Alta, Rincón de los Sauces, Neuquén
// ===========================================================================

/**
 * **MA-102 — pozo REAL.** Campo Meseta Alta, Rincón de los Sauces, Neuquén.
 *
 * Fuente: informe de diseño de SLB «20260309 - MA 0102_ecd_General_Case»,
 * 9-mar-2026, ing. Tamara Lobianco, para PSA (`TESIS/Casos reales/`). Es el
 * caso que se desarrolla a lo largo del **Capítulo II** de la tesis, así que
 * acá la trazabilidad del dato importa más que en el resto del archivo: cada
 * valor dice si viene del informe, si se derivó de él o si es supuesto.
 *
 * El informe está en métrico; las conversiones están hechas y anotadas al lado
 * de cada valor.
 *
 * ## La IPR se lee de la carta del informe (pág. 5)
 *
 * El informe no publica la presión estática ni el ensayo como números: los
 * publica como la carta «Inflow / Outflow Performance Curve **Utilizada para
 * el diseño**» (pág. 5), que es la que SLB efectivamente usó — distinta de la
 * de la pág. 4, «Enviada por el cliente». De ahí salen los tres valores:
 *
 * ```
 *   Pr    = 52,0 kgf/cm²  = 739,6 psia   (curva roja «Inflow Performance» en q = 0)
 *   Pwf   = 39,6 kgf/cm²  = 563,2 psia   (punto verde «Test Point»)
 *   q     = 167 m³/d      = 1 050,4 b/d  (mismo punto verde)
 * ```
 *
 * **La carta está en presión ABSOLUTA**, no manométrica. Se verificó contra la
 * curva «Inflow At Intake», que al caudal de diseño lee ≈28,5 kgf/cm² =
 * 405,4 psia, contra los 407,9 psia de PIP que el informe sí publica como
 * número: 0,6 % de desvío. Leída como manométrica el desvío sería del 3 %.
 *
 * ## Tres controles cruzados de que la lectura reproduce el diseño de SLB
 *
 * 1. `vogel_qmax_from_test(739.6, 563.2, 1050.4)` = 2 737 b/d = **435,2 m³/d**,
 *    contra los **≈440 m³/d** donde la curva roja corta el eje → **1,1 %**.
 * 2. Esa misma Vogel al caudal de diseño (195,62 m³/d = 1 230,4 b/d) da
 *    **Pwf = 528,0 psia**. Por un camino **independiente** —el PIP y el
 *    gradiente de mezcla que publica el informe, bajando por la columna del
 *    anular desde la admisión hasta los punzados—:
 *
 *    ```
 *      PIP a 960 m (3 149,6 ft)      =  407,9 psia      (informe)
 *      punzados a 1 046 m (3 431,8 ft)
 *      columna = 1 046 − 960 = 86 m  =  282,2 ft
 *      Δp = 282,2 ft × 0,448 psi/ft  =  126,4 psi       (gradiente del informe)
 *      Pwf = 407,9 + 126,4           =  534,3 psia
 *    ```
 *
 *    Las dos rutas cierran a **1,2 %**.
 * 3. De 1 y 2 se concluye que **SLB resolvió la IPR con Vogel puro**, que es lo
 *    que declara `ipr_method`.
 *
 * Con esa Pwf y Pb = 3 052,6 psia el reservorio queda **saturado en todo el
 * rango operativo**, así que `Reservoir` emite el aviso de reservorio depletado
 * (`bubble_point > static_pressure`). Es correcto y esperado para este pozo, y
 * con la Pr real es aún más marcado —la burbuja es 4,1 veces la presión
 * estática— pero no se silencia.
 *
 * ## PVT: manda el informe, no Standing
 *
 * Para Rs = 449,2 scf/STB, 24 °API y 127,4 °F, Standing devuelve **Pb ≈ 2 684
 * psia** contra los **3 052,6 psia** que informa SLB: 12 % de diferencia. La
 * regla del archivo —Pb = la de Standing— existe para que los casos inventados
 * no se contradigan solos; acá hay un dato de laboratorio y **ese manda**. La
 * consecuencia asumida es que el Rs que calcula el motor a la Pb del informe no
 * coincide exactamente con el GOR declarado.
 *
 * ## SUPUESTOS (el informe no los da)
 *
 * - `perforations_bottom = 3 441,6 ft`: el informe publica una sola
 *   profundidad de punzados (1 046 m), no un intervalo, y el dominio exige
 *   espesor (`perforations_bottom must be > perforations_top`). Se adoptan
 *   3 m de espesor.
 * - `deviation_max = 0`: no hay survey en el informe.
 * - `power_supply_voltage = 480 V`: el informe sólo da 1 227,2 V en la caja de
 *   empalme, que es la tensión del cable, no la de red.
 * - `surface.frequency = 50 Hz`: red argentina. Los **51 Hz del informe son la
 *   frecuencia de operación del variador**, no la de red, y viajan en
 *   `objectives.design_frequency_hz`. La curva de la bomba se reescala de 50 a
 *   51 Hz con las leyes de afinidad antes de elegir nada
 *   (`bes.core.affinity.pump_at_frequency`), así que el diseño sale a la
 *   frecuencia del informe. Una red de 51 Hz no existe y el dominio la
 *   rechaza.
 * - Línea de conducción y presión de separador: los mismos que los casos
 *   propios (`SUPERFICIE_PROPIA`).
 *
 * ## APAREJO DE REFERENCIA — lo que diseñó SLB
 *
 * Es el valor del caso: contra esto se compara lo que arma la app.
 *
 * ```
 *   Bomba      REDA 400 DN1750, 173 etapas, CR-CT, ES
 *   Separador  REDA 400/400 DRS-ES · 2,6 hp
 *              separación natural 23,94 % · separador 95 % · total 96,2 %
 *              gas libre a la bomba 0,4 %
 *   Protector  400 Maximus HL, 3 sellos, LSBSB, 3 cámaras
 *   Motor      REDA 456 Maximus 4053 · 60 hp placa, 1 402,8 V, 27,4 A,
 *              derrateo 80 % · a 51 Hz: 39,2 hp, 22,5 A, 1 192,4 V
 *   Cable      ELB #4, 3 249,61 ft, 5 kV, 450 °F
 *   Sensor     Phoenix XT150 Tipo 0
 *
 *   PIP 407,9 psia · descarga 1 557,3 psia · TDH 2 564,5 ft (781,65 m)
 *   gradiente de mezcla 0,448 psi/ft · sumergencia 774,3 ft (236 m)
 * ```
 */
const MA_102: DesignInputs = {
  reservoir: {
    // 52,0 kgf/cm² abs — arranque de la curva «Inflow Performance» de la carta
    // de la pág. 5 del informe. Ver el docstring: lectura verificada por tres
    // controles cruzados.
    static_pressure: 739.6,
    bubble_point: 3052.6,        // psia — informe
    test_pwf: 563.2,             // psia — 39,6 kgf/cm², punto verde de la carta
    test_rate: 1050.4,           // b/d — 167 m³/d, mismo punto verde
    ipr_method: "vogel",
    reservoir_temp: 127.4,       // °F — informe
    drive_mechanism: "solution_gas",
    fetkovich_n: null,
  },
  fluid: {
    oil_api: 24.0,               // informe
    water_cut: 0.96,             // informe
    gor: 449.2,                  // scf/STB — 80 m³/m³ × 35,3147/6,28981
    gas_sg: 0.65,                // informe
    water_sg: 1.05,              // informe
    // Sin ensayo de viscosidad: se lee la Fig. 4L(2) con °API y temperatura.
    oil_viscosity_dead: null,
    viscosity_temp_ref: null,
    bubble_point_pressure: 3052.6,   // informe — NO la de Standing (docstring)
    ...SIN_ACIDOS,
  },
  well: {
    total_depth: 4150.3,         // ft — 1 265 m de casing (informe)
    // Casing 5½" del informe: 14 lb/ft, ID 5,012". NO es el CASING_5_5 de este
    // archivo, que es el de 17 lb/ft (ID 4,892") de los ejemplos de Brown.
    casing_od: 5.5,
    casing_weight: 14.0,
    casing_id: 5.012,
    ...TUBING_2_875,
    perforations_top: 3431.8,    // ft — 1 046 m (informe)
    // SUPUESTO: el informe da UNA sola profundidad de punzados (1 046 m), y el
    // dominio exige que el intervalo tenga espesor. Se le dan 3 m (9,8 ft)
    // hacia abajo. El valor no interviene en el diseño —la bomba se asienta
    // por `pump_setting_depth`— pero cambia el arranque del recorrido de
    // presión, así que cuando aparezca el intervalo real hay que corregirlo.
    perforations_bottom: 3441.6,
    deviation_max: 0.0,          // SUPUESTO: no hay survey en el informe
    wellhead_temp: 86.0,         // °F — informe
    pump_setting_depth: 3149.6,  // ft — 960 m, «Intake Depth» del informe
  },
  surface: {
    ...SUPERFICIE_PROPIA,        // SUPUESTOS: línea de conducción y separador
    wellhead_pressure_required: 142.2,  // psia — informe
    power_supply_voltage: 480.0,        // SUPUESTO: el informe no da la de red
    // SUPUESTO: red argentina de 50 Hz. Los 51 Hz que declara el informe son
    // la frecuencia de OPERACIÓN del variador, no la de red — viajan en
    // `objectives.design_frequency_hz`, y el motor las aplica reescalando la
    // curva con las leyes de afinidad. Una red de 51 Hz no existe, y el
    // dominio la rechaza (`frequency must be 50 or 60 Hz`).
    frequency: 50.0,
  },
  objectives: {
    target_flow_rate: 1258.0,    // b/d — 200 m³/d de diseño (informe)
    // La admisión viene dada por `pump_setting_depth`, así que el margen no
    // interviene: ponerle un valor movería la bomba respecto del informe.
    safety_margin_depth: 0.0,
    allow_gas_venting: false,
    max_gip: 0.1,
    design_life_years: 5.0,
    use_vsd: true,               // informe
    design_frequency_hz: 51.0,   // Hz — informe
  },
};

// ---------------------------------------------------------------------------
// Registro. El orden es el del menú: primero el genérico, después los seis
// ejemplos del libro en el orden del capítulo, después los propios y al final
// el pozo real.
// ---------------------------------------------------------------------------

export const EXAMPLE_CASES: Record<string, DesignInputs> = {
  "Genérico · Vaca Muerta (inventado)": VACA_MUERTA,
  "Brown #1A · Pozo de agua, sin gas": BROWN_1A,
  "Brown #2B · Pozo de petróleo sin gas": BROWN_2B,
  "Brown #3A · Con gas — incrementos": BROWN_3A,
  "Brown #3B · Con gas — diseño completo": BROWN_3B,
  "Brown #4A · Crudo viscoso 14 °API": BROWN_4A,
  "Brown #4B · Crudo viscoso 12 °API": BROWN_4B,
  "Propio · Acuífero (sin gas)": ACUIFERO,
  "Propio · Gas en bomba (5,9 %)": CON_GAS,
  "Real · MA-102 Meseta Alta": MA_102,
};

/** Orden de presentación en el menú (los `Record` no garantizan orden estable
 *  para claves no numéricas en todos los motores, y acá el orden es
 *  información: sigue al capítulo del libro). */
export const EXAMPLE_ORDER: readonly string[] = Object.keys(EXAMPLE_CASES);
