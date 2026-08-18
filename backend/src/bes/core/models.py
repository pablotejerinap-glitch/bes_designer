"""
Data models for BES/ESP system design.
Based on: Kermit Brown, "The Technology of Artificial Lift Methods", Vol. 2b, Ch. 4.5.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class IPRMethod(Enum):
    """Inflow Performance Relationship method for reservoir modeling."""
    LINEAR = auto()       # Darcy / straight-line PI (above bubble point)
    VOGEL = auto()        # Vogel correlation (solution-gas drive)
    FETKOVICH = auto()    # Fetkovich empirical IPR


class DriveMechanism(Enum):
    """Primary reservoir energy source."""
    SOLUTION_GAS = auto()
    WATER_DRIVE = auto()
    GAS_CAP = auto()
    COMBINATION = auto()


@dataclass
class Reservoir:
    """Static reservoir properties used for IPR and fluid-behavior calculations.

    The well's deliverability is normally entered as a **production test**
    (``test_pwf`` + ``test_rate``), which is what is actually measured in the
    field; ``productivity_index`` is then derived from it with the IPR model
    selected in ``ipr_method``. Passing ``productivity_index`` directly is
    still supported for cases where only the processed PI is published (the
    Brown book examples, operator reports).

    Attributes:
        static_pressure: Current average reservoir pressure [psi].
        bubble_point: Bubble-point pressure of the reservoir fluid [psi].
        ipr_method: IPR correlation to apply.
        reservoir_temp: Bottom-hole static temperature [°F].
        drive_mechanism: Primary energy mechanism of the reservoir.
        test_pwf: Stabilized flowing bottomhole pressure measured during the
            production test [psi]. Must satisfy 0 <= test_pwf < static_pressure.
        test_rate: Stabilized gross liquid rate measured during the same test
            [STB/d]. Must be > 0.
        productivity_index: Well PI at test conditions [STB/d/psi]. Derived
            from the test when omitted; see :func:`bes.core.ipr.
            productivity_index_from_test`.
        fetkovich_c: Fetkovich deliverability coefficient C
            [STB/d/psia^(2n)]. Derived from the test when omitted and
            ``fetkovich_n`` is known; otherwise it comes from a multi-rate
            (flow-after-flow or isochronal) test.
        fetkovich_n: Fetkovich flow exponent n [-]. Physical range [0.5, 1.0]:
            1.0 = laminar (no turbulence), 0.5 = fully turbulent. Required
            when ipr_method is FETKOVICH — a single test point cannot fit both
            C and n.
    """
    static_pressure: float
    bubble_point: float
    ipr_method: IPRMethod
    reservoir_temp: float
    drive_mechanism: DriveMechanism
    test_pwf: Optional[float] = None
    test_rate: Optional[float] = None
    productivity_index: Optional[float] = None
    fetkovich_c: Optional[float] = None
    fetkovich_n: Optional[float] = None

    def __post_init__(self) -> None:
        if self.static_pressure <= 0:
            raise ValueError(f"static_pressure must be > 0, got {self.static_pressure}")
        if self.bubble_point < 0:
            raise ValueError(f"bubble_point must be >= 0, got {self.bubble_point}")
        if self.bubble_point > self.static_pressure:
            import warnings
            warnings.warn(
                f"bubble_point ({self.bubble_point}) exceeds static_pressure "
                f"({self.static_pressure}). This is normal in depleted "
                f"reservoirs with solution gas drive (Vogel IPR applies).",
                UserWarning,
                stacklevel=2,
            )

        self._derive_deliverability_from_test()

        if self.ipr_method is IPRMethod.FETKOVICH:
            if self.fetkovich_c is None or self.fetkovich_n is None:
                raise ValueError(
                    "ipr_method FETKOVICH requires fetkovich_c and fetkovich_n "
                    "(from a multi-rate flow-after-flow or isochronal test), "
                    "or a production test (test_pwf/test_rate) plus fetkovich_n; "
                    f"got C={self.fetkovich_c}, n={self.fetkovich_n}"
                )
        if self.fetkovich_c is not None and self.fetkovich_c <= 0:
            raise ValueError(f"fetkovich_c must be > 0, got {self.fetkovich_c}")
        if self.fetkovich_n is not None and not (0.5 <= self.fetkovich_n <= 1.0):
            raise ValueError(
                f"fetkovich_n must be in [0.5, 1.0], got {self.fetkovich_n}"
            )
        if self.productivity_index is None:
            raise ValueError(
                "productivity_index could not be established: supply either a "
                "production test (test_pwf and test_rate) or productivity_index "
                "directly"
            )
        if self.productivity_index <= 0:
            raise ValueError(f"productivity_index must be > 0, got {self.productivity_index}")
        if self.reservoir_temp <= 0:
            raise ValueError(f"reservoir_temp must be > 0 °F, got {self.reservoir_temp}")

    def _derive_deliverability_from_test(self) -> None:
        """Fill in PI (and Fetkovich C) from the production test when needed.

        Does nothing when no test was supplied, or when the values it would
        derive were already given explicitly — an explicit value always wins,
        so a case that carries both a published PI and a test point keeps the
        published PI.

        Raises:
            ValueError: If only one of ``test_pwf`` / ``test_rate`` is given,
                or if the test point is physically invalid.
        """
        has_pwf = self.test_pwf is not None
        has_rate = self.test_rate is not None
        if has_pwf != has_rate:
            raise ValueError(
                "a production test needs both test_pwf and test_rate; got "
                f"test_pwf={self.test_pwf}, test_rate={self.test_rate}"
            )
        if not has_pwf:
            return

        needs_pi = self.productivity_index is None
        needs_c = (
            self.ipr_method is IPRMethod.FETKOVICH
            and self.fetkovich_c is None
            and self.fetkovich_n is not None
        )
        if not (needs_pi or needs_c):
            return

        # Deferred import: bes.core.ipr imports this module at load time.
        from bes.core.ipr import productivity_index_from_test

        derived = productivity_index_from_test(
            pr=self.static_pressure,
            pwf_test=self.test_pwf,
            q_test=self.test_rate,
            method=self.ipr_method,
            fetkovich_n=self.fetkovich_n,
            # Vogel la necesita para separar el tramo recto (arriba de la
            # burbuja) del curvo. Sin ella se degrada a Vogel puro, que en un
            # reservorio subsaturado sobreestima J.
            bubble_point=self.bubble_point,
        )
        if needs_pi:
            self.productivity_index = derived["productivity_index"]
        if needs_c:
            self.fetkovich_c = derived["fetkovich_c"]


@dataclass
class Fluid:
    """Fluid PVT and composition properties.

    Attributes:
        oil_api: Stock-tank oil gravity [°API]. Valid range: 5–70.
        water_cut: Produced water fraction at surface conditions [0–1].
        gor: Producing gas-oil ratio at surface [scf/STB].
        gas_sg: Gas specific gravity (air = 1.0).
        water_sg: Brine specific gravity (pure water = 1.0).
        oil_viscosity_dead: Dead-oil viscosity at viscosity_temp_ref [cp].
        viscosity_temp_ref: Temperature at which dead-oil viscosity was measured [°F].
        bubble_point_pressure: Fluid bubble-point pressure for PVT calculations [psi].
        h2s_content: Hydrogen sulfide concentration [ppm]. Affects material selection.
        co2_content: Carbon dioxide concentration [ppm]. Affects corrosion design.
        sand_production: True if well produces sand (affects pump selection).
    """
    oil_api: float
    water_cut: float
    gor: float
    gas_sg: float
    water_sg: float
    oil_viscosity_dead: float
    viscosity_temp_ref: float
    bubble_point_pressure: float
    h2s_content: float
    co2_content: float
    sand_production: bool

    def __post_init__(self) -> None:
        if not (5.0 <= self.oil_api <= 70.0):
            raise ValueError(f"oil_api must be in [5, 70] °API, got {self.oil_api}")
        if not (0.0 <= self.water_cut <= 1.0):
            raise ValueError(f"water_cut must be in [0, 1], got {self.water_cut}")
        if self.gor < 0:
            raise ValueError(f"gor must be >= 0, got {self.gor}")
        if self.gas_sg <= 0:
            raise ValueError(f"gas_sg must be > 0, got {self.gas_sg}")
        if self.water_sg <= 0:
            raise ValueError(f"water_sg must be > 0, got {self.water_sg}")
        if self.oil_viscosity_dead <= 0:
            raise ValueError(f"oil_viscosity_dead must be > 0, got {self.oil_viscosity_dead}")
        if self.viscosity_temp_ref <= 0:
            raise ValueError(f"viscosity_temp_ref must be > 0 °F, got {self.viscosity_temp_ref}")
        if self.bubble_point_pressure < 0:
            raise ValueError(f"bubble_point_pressure must be >= 0, got {self.bubble_point_pressure}")
        if self.h2s_content < 0:
            raise ValueError(f"h2s_content must be >= 0, got {self.h2s_content}")
        if self.co2_content < 0:
            raise ValueError(f"co2_content must be >= 0, got {self.co2_content}")


@dataclass
class WellGeometry:
    """Wellbore geometry and completion dimensions.

    Attributes:
        total_depth: Measured depth to the bottom of the well [ft MD].
        casing_od: Casing outer diameter [in].
        casing_weight: Casing nominal weight [lb/ft] — determines wall thickness.
        casing_id: Casing inner diameter (drift) [in]. Constrains pump OD.
        tubing_od: Production tubing outer diameter [in].
        tubing_id: Production tubing inner diameter [in]. Governs friction losses.
        perforations_top: Measured depth to top of perforated interval [ft MD].
        perforations_bottom: Measured depth to bottom of perforated interval [ft MD].
        deviation_max: Maximum wellbore inclination along the production string [°].
            Values > 30° may require bent-housing or flex-shaft pump considerations.
        wellhead_temp: Ambient temperature at surface / wellhead [°F].
            Es el extremo superior del perfil geotérmico lineal; el inferior es
            ``Reservoir.reservoir_temp``. De ese perfil sale la temperatura a
            cualquier profundidad (``bes.core.tdh.temp_at_depth``), que alimenta
            el PVT del traverse de presión, la temperatura de admisión de la
            bomba y la corrección por viscosidad.
        pump_setting_depth: Profundidad de succión — dónde se asienta la
            admisión de la bomba [ft MD]. **Opcional**: cuando se deja en
            ``None`` se calcula como ``perforations_top − safety_margin_depth``
            (Brown §4.532), que es el comportamiento por defecto. Cargarla
            explícitamente sirve para reproducir los ejemplos del libro, donde
            la profundidad viene dada (5850 ft en el #2A, 7000 ft en el #3B),
            y para respetar una instalación ya existente.

            Manda sobre buena parte del diseño: fija el PIP y con él la
            sumergencia del TDH, el largo de cable y su caída de tensión, y la
            temperatura a la que trabaja el motor.
    """
    total_depth: float
    casing_od: float
    casing_weight: float
    casing_id: float
    tubing_od: float
    tubing_id: float
    perforations_top: float
    perforations_bottom: float
    deviation_max: float
    wellhead_temp: float
    pump_setting_depth: Optional[float] = None

    def __post_init__(self) -> None:
        if self.total_depth <= 0:
            raise ValueError(f"total_depth must be > 0, got {self.total_depth}")
        if self.casing_od <= 0:
            raise ValueError(f"casing_od must be > 0, got {self.casing_od}")
        if self.casing_weight <= 0:
            raise ValueError(f"casing_weight must be > 0, got {self.casing_weight}")
        if self.casing_id <= 0:
            raise ValueError(f"casing_id must be > 0, got {self.casing_id}")
        if self.casing_id >= self.casing_od:
            raise ValueError(
                f"casing_id ({self.casing_id}) must be < casing_od ({self.casing_od})"
            )
        if self.tubing_od <= 0:
            raise ValueError(f"tubing_od must be > 0, got {self.tubing_od}")
        if self.tubing_id <= 0:
            raise ValueError(f"tubing_id must be > 0, got {self.tubing_id}")
        if self.tubing_id >= self.tubing_od:
            raise ValueError(
                f"tubing_id ({self.tubing_id}) must be < tubing_od ({self.tubing_od})"
            )
        if self.tubing_od >= self.casing_id:
            raise ValueError(
                f"tubing_od ({self.tubing_od}) must be < casing_id ({self.casing_id})"
            )
        if self.perforations_top <= 0:
            raise ValueError(f"perforations_top must be > 0, got {self.perforations_top}")
        if self.perforations_bottom <= self.perforations_top:
            raise ValueError(
                f"perforations_bottom ({self.perforations_bottom}) must be "
                f"> perforations_top ({self.perforations_top})"
            )
        if self.perforations_bottom > self.total_depth:
            raise ValueError(
                f"perforations_bottom ({self.perforations_bottom}) cannot exceed "
                f"total_depth ({self.total_depth})"
            )
        if not (0.0 <= self.deviation_max <= 90.0):
            raise ValueError(f"deviation_max must be in [0, 90]°, got {self.deviation_max}")
        if self.wellhead_temp <= 0:
            raise ValueError(f"wellhead_temp must be > 0 °F, got {self.wellhead_temp}")
        if self.pump_setting_depth is not None:
            # La bomba va DENTRO del pozo y POR ENCIMA de las perforaciones: si
            # se asentara más abajo, el fluido tendría que bajar para entrar.
            if self.pump_setting_depth <= 0:
                raise ValueError(
                    f"pump_setting_depth must be > 0, got {self.pump_setting_depth}"
                )
            if self.pump_setting_depth >= self.perforations_top:
                raise ValueError(
                    f"pump_setting_depth ({self.pump_setting_depth}) must be "
                    f"above perforations_top ({self.perforations_top}): la bomba "
                    f"se asienta por encima del intervalo punzado"
                )


@dataclass
class SurfaceConditions:
    """Surface infrastructure and power-supply parameters.

    Attributes:
        wellhead_pressure_required: Minimum required tubing-head pressure [psi].
        flowline_length: Total flowline length from wellhead to separator [ft].
        flowline_id: Flowline inner diameter [in].
        flowline_elevation_change: Net elevation change along flowline (+ = uphill) [ft].
        separator_pressure: Operating pressure of the production separator [psi].
        power_supply_voltage: Available surface supply voltage [V].
        frequency: Power grid frequency [Hz]. Typically 60 (Americas) or 50 (rest).
    """
    wellhead_pressure_required: float
    flowline_length: float
    flowline_id: float
    flowline_elevation_change: float
    separator_pressure: float
    power_supply_voltage: float
    frequency: float

    def __post_init__(self) -> None:
        if self.wellhead_pressure_required < 0:
            raise ValueError(
                f"wellhead_pressure_required must be >= 0, got {self.wellhead_pressure_required}"
            )
        if self.flowline_length < 0:
            raise ValueError(f"flowline_length must be >= 0, got {self.flowline_length}")
        if self.flowline_id <= 0:
            raise ValueError(f"flowline_id must be > 0, got {self.flowline_id}")
        if self.separator_pressure < 0:
            raise ValueError(f"separator_pressure must be >= 0, got {self.separator_pressure}")
        if self.power_supply_voltage <= 0:
            raise ValueError(f"power_supply_voltage must be > 0, got {self.power_supply_voltage}")
        if self.frequency not in (50.0, 60.0):
            raise ValueError(f"frequency must be 50 or 60 Hz, got {self.frequency}")


@dataclass
class DesignObjectives:
    """User-specified production targets and design constraints.

    Attributes:
        target_flow_rate: Desired gross liquid production rate [STB/d].
        safety_margin_depth: Additional depth added below pump-setting for
            operational contingency (e.g., fluid level drop) [ft].
        allow_gas_venting: If True, a vent/gas-separator is assumed available.
        max_gip: **Fracción** máxima de gas libre admisible a la entrada de la
            bomba, ya descontados el venteo por el anular y el separador [0–1].
            Por encima de este valor el diseño BES no converge y corresponde
            evaluar otro método de levantamiento artificial: lo verifica
            ``bes.core.gas_handling.evaluate_gas_feasibility()`` y el diseño
            **falla**, no advierte.

            Es una FRACCIÓN ``V_gas/(V_gas+V_líquido)``, no una relación
            ``V_gas/V_líquido``. El default coincide con
            ``gas_handling.GAS_FRACTION_PUMP_LIMIT``; no se importa de ahí
            porque ``gas_handling`` importa este módulo y sería circular.

            **Historia:** el campo existía desde el principio, se imprimía en
            el PDF y el Excel, y **ningún cálculo lo leía**. Los casos guardados
            de esa época traen valores como 0.7, que nunca significaron nada y
            ahora sí: con 0.7 cargado, un pozo con 70 % de gas en la bomba
            pasaría la verificación. Revisar los casos viejos.
        design_life_years: Expected run-life for equipment sizing and MTBF targets [years].
        use_vsd: If True, design includes a Variable Speed Drive (VSD/VFD).
        gas_fraction_pc_threshold: Fracción volumétrica de gas libre en la
            admisión por encima de la cual la pérdida de carga en el tubing se
            calcula con Poettmann-Carpenter en vez de Hazen-Williams [0–1].

            **No es un parámetro de diseño y NO se pide por pantalla ni por la
            API.** El umbral lo fija la física, no el usuario: con más del 1 %
            de gas libre, usar un gradiente de líquido constante introduce un
            error de diseño grande (Brown Vol. 2b §4.53102; Takács, *ESP
            Manual*). El programa decide solo qué correlación corresponde.

            Queda como parámetro únicamente para poder **reproducir los
            ejemplos impresos** de Brown, que se resuelven a mano como
            monofásicos y necesitan fijarlo en 1.0. Sólo los tests lo tocan.

            El valor por defecto tiene que coincidir con
            ``bes.core.gas_handling.GAS_FRACTION_NEGLIGIBLE``; no se importa de
            ahí porque ``gas_handling`` importa este módulo y sería circular.
            ``tests/test_gas_handling.py`` verifica que no se desincronicen.
        design_frequency_hz: Frequency the pump will actually run at [Hz].
            ``None`` = the grid frequency in ``SurfaceConditions.frequency``.
            Only meaningful with ``use_vsd``: a fixed switchboard runs the pump
            at line frequency, a variable-speed drive does not. The pump curve
            is rescaled to this frequency with the affinity laws before any
            selection is made — see :func:`bes.core.affinity.pump_at_frequency`.
    """
    target_flow_rate: float
    safety_margin_depth: float
    allow_gas_venting: bool
    design_life_years: float
    use_vsd: bool
    # max_gip quedó DESPUÉS de los obligatorios para poder llevar default. Todas
    # las construcciones del proyecto son por keyword, así que el reordenamiento
    # no rompe llamadas posicionales.
    max_gip: float = 0.10
    gas_fraction_pc_threshold: float = 0.01
    design_frequency_hz: Optional[float] = None

    def __post_init__(self) -> None:
        if not (0.0 <= self.gas_fraction_pc_threshold <= 1.0):
            raise ValueError(
                "gas_fraction_pc_threshold must be in [0, 1], got "
                f"{self.gas_fraction_pc_threshold}"
            )
        if self.design_frequency_hz is not None:
            if not (20.0 <= self.design_frequency_hz <= 90.0):
                raise ValueError(
                    "design_frequency_hz must be in [20, 90] Hz (VSD operating "
                    f"range), got {self.design_frequency_hz}"
                )
            if not self.use_vsd:
                raise ValueError(
                    "design_frequency_hz requires use_vsd=True: without a "
                    "variable-speed drive the pump runs at line frequency"
                )
        if self.target_flow_rate <= 0:
            raise ValueError(f"target_flow_rate must be > 0, got {self.target_flow_rate}")
        if self.safety_margin_depth < 0:
            raise ValueError(f"safety_margin_depth must be >= 0, got {self.safety_margin_depth}")
        if not (0.0 <= self.max_gip <= 1.0):
            raise ValueError(f"max_gip must be in [0, 1], got {self.max_gip}")
        if self.design_life_years <= 0:
            raise ValueError(f"design_life_years must be > 0, got {self.design_life_years}")


@dataclass
class PumpPerformancePoint:
    """Single operating point on a pump performance curve.

    Attributes:
        flow_rate: Liquid throughput at this point [b/d].
        head_per_stage: Hydraulic head developed per stage at this flow [ft/stage].
        hp_per_stage: Shaft power required per stage [hp/stage].
        efficiency: Pump hydraulic efficiency at this point [0–1].
    """
    flow_rate: float
    head_per_stage: float
    hp_per_stage: float
    efficiency: float

    def __post_init__(self) -> None:
        if self.flow_rate < 0:
            raise ValueError(f"flow_rate must be >= 0, got {self.flow_rate}")
        if self.head_per_stage < 0:
            raise ValueError(f"head_per_stage must be >= 0, got {self.head_per_stage}")
        if self.hp_per_stage < 0:
            raise ValueError(f"hp_per_stage must be >= 0, got {self.hp_per_stage}")
        if not (0.0 <= self.efficiency <= 1.0):
            raise ValueError(f"efficiency must be in [0, 1], got {self.efficiency}")


@dataclass
class PumpHousing:
    """One housing (carcasa) length offered by the manufacturer for a pump.

    A housing is the pressure vessel the stages are stacked into. Catalogs
    publish it as a discrete set of lengths, each holding a fixed number of
    stages; a design that needs more stages than the largest housing holds is
    assembled as a tandem of several housings in series.

    Only ``stages`` is required — it is the one attribute every catalog in the
    project publishes today. The rest are **optional metadata** that stay empty
    until the corresponding manufacturer data is loaded; nothing in the
    selection algorithm requires them, so a catalog can be enriched later
    without touching code.

    Attributes:
        stages: Stage capacity of this housing [stages]. Must be > 0.
        code: Manufacturer housing code / part number. Empty when unknown.
        material: Housing material (e.g. "Carbon steel", "Ni-Resist").
            Empty when the catalog does not publish it.
        od_in: Housing outer diameter [in]. 0 = unknown (fall back to the
            pump OD).
        pressure_limit_psi: Working pressure rating of *this* housing [psi].
            0 = unknown, in which case the pump-level limit applies. A
            non-zero value lets a tandem mix standard and high-pressure
            housings, with the higher-rated one placed where the pressure is
            greatest.
        length_ft: Housing length [ft]. 0 = unknown.
        weight_lbs: Housing weight [lbs]. 0 = unknown.
    """
    stages: int
    code: str = ""
    material: str = ""
    od_in: float = 0.0
    pressure_limit_psi: float = 0.0
    length_ft: float = 0.0
    weight_lbs: float = 0.0

    def __post_init__(self) -> None:
        if self.stages <= 0:
            raise ValueError(f"stages must be > 0, got {self.stages}")
        if self.od_in < 0:
            raise ValueError(f"od_in must be >= 0, got {self.od_in}")
        if self.pressure_limit_psi < 0:
            raise ValueError(
                f"pressure_limit_psi must be >= 0, got {self.pressure_limit_psi}"
            )


@dataclass
class PumpCurve:
    """Manufacturer pump catalog entry with full performance curve.

    Attributes:
        manufacturer: Equipment manufacturer name (e.g., "Reda", "Centrilift").
        series: Pump series / product line (e.g., "DN1750", "GC6100").
        model: Specific model designation.
        od: Pump outer diameter [in]. Must fit inside casing_id.
        min_flow: Minimum recommended operating flow rate [b/d].
        max_flow: Maximum recommended operating flow rate [b/d].
        bep_flow: Best efficiency point flow rate [b/d].
        points: List of performance points spanning the operating range.
        max_stages: Maximum number of stages available in this housing.
        housing_options: Available housing sizes (number of stages) from catalog.
        housings: Full housing catalog for this pump. Synthesised from
            ``housing_options`` when the catalog carries only the stage counts,
            so callers can always work with :class:`PumpHousing` objects.
    """
    manufacturer: str
    series: str
    model: str
    od: float
    min_flow: float
    max_flow: float
    bep_flow: float
    points: list[PumpPerformancePoint]
    max_stages: int
    housing_options: list[int]
    # Presión máxima de trabajo de la carcasa [psi] (opcional; 0 = sin dato).
    housing_pressure_limit_psi: float = 0.0
    housings: list[PumpHousing] = field(default_factory=list)
    # Frecuencia a la que el fabricante publicó la curva [Hz]. Es el punto de
    # partida de las leyes de afinidad (bes.core.affinity). 60 Hz por defecto:
    # es la frecuencia declarada en el _source de los catálogos digitalizados y
    # la de los ejemplos del libro de Brown.
    catalog_frequency_hz: float = 60.0

    def __post_init__(self) -> None:
        if self.od <= 0:
            raise ValueError(f"od must be > 0, got {self.od}")
        if self.min_flow < 0:
            raise ValueError(f"min_flow must be >= 0, got {self.min_flow}")
        if self.max_flow <= self.min_flow:
            raise ValueError(
                f"max_flow ({self.max_flow}) must be > min_flow ({self.min_flow})"
            )
        if not (self.min_flow <= self.bep_flow <= self.max_flow):
            raise ValueError(
                f"bep_flow ({self.bep_flow}) must be in "
                f"[min_flow={self.min_flow}, max_flow={self.max_flow}]"
            )
        if not self.points:
            raise ValueError("points list cannot be empty")
        if self.max_stages <= 0:
            raise ValueError(f"max_stages must be > 0, got {self.max_stages}")
        if not self.housing_options:
            raise ValueError("housing_options list cannot be empty")
        if any(s <= 0 for s in self.housing_options):
            raise ValueError("all housing_options values must be > 0")
        if not self.manufacturer.strip():
            raise ValueError("manufacturer cannot be empty")
        if not self.model.strip():
            raise ValueError("model cannot be empty")
        # Un catálogo que solo publica las longitudes disponibles (el caso de
        # todos los catálogos actuales) queda igualmente expresado como objetos
        # PumpHousing, sin metadatos. Así el selector tiene una sola forma de
        # leer las carcasas y enriquecer el catálogo no toca código.
        if not self.housings:
            self.housings = [
                PumpHousing(stages=int(s)) for s in sorted(set(self.housing_options))
            ]


@dataclass
class DesignResult:
    """Complete output of a BES/ESP design calculation.

    Attributes:
        pump_manufacturer: Selected pump manufacturer.
        pump_series: Selected pump series.
        pump_model: Selected pump model designation.
        pump_od: Pump outer diameter [in].
        num_stages: Number of pump stages required.
        pump_setting_depth: Recommended pump intake depth [ft MD].
        intake_pressure: Pressure at pump intake [psi].
        total_head_required: Total dynamic head the pump must develop [ft].
        head_per_stage: Head per stage at operating point [ft/stage].
        hp_per_stage: Power per stage at operating point [hp/stage].
        pump_efficiency: Pump hydraulic efficiency at operating point [0–1].
        total_pump_hp: Total pump shaft power requirement [hp].
        motor_manufacturer: Selected motor manufacturer.
        motor_model: Motor model designation.
        motor_hp: Motor nameplate power rating [hp].
        motor_voltage: Motor nameplate voltage [V].
        motor_amperage: Motor nameplate current at rated load [A].
        motor_od: Motor outer diameter [in].
        motor_length: Motor length (one or stacked) [ft].
        cable_type: Cable jacket type / insulation class (e.g., "EPDM", "Polypro").
        cable_awg: Cable conductor size [AWG].
        cable_voltage_drop: Estimated voltage drop along cable [V].
        surface_voltage_required: Required surface voltage to deliver motor voltage [V].
        transformer_kva: Recommended transformer rating [kVA].
        system_efficiency: Overall system efficiency (pump × motor × cable) [0–1].
        flow_rate_achieved: Calculated gross liquid rate at operating point [STB/d].
        operating_frequency: Pump operating frequency (relevant for VSD designs) [Hz].
        gip_fraction: Estimated free-gas fraction at pump intake [0–1].
        warnings: List of design warnings or flags for engineer review.
        alternatives: List of alternative equipment combinations considered.
    """
    pump_manufacturer: str
    pump_series: str
    pump_model: str
    pump_od: float
    num_stages: int
    pump_setting_depth: float
    intake_pressure: float
    total_head_required: float
    head_per_stage: float
    hp_per_stage: float
    pump_efficiency: float
    total_pump_hp: float
    motor_manufacturer: str
    motor_model: str
    motor_hp: float
    motor_voltage: float
    motor_amperage: float
    motor_od: float
    motor_length: float
    cable_type: str
    cable_awg: int
    cable_voltage_drop: float
    surface_voltage_required: float
    transformer_kva: float
    system_efficiency: float
    flow_rate_achieved: float
    operating_frequency: float
    gip_fraction: float
    warnings: list[str] = field(default_factory=list)

    # Traza de fórmulas: cada cuenta del diseño con su expresión simbólica, los
    # números reemplazados, el resultado y la cita bibliográfica. La arma el
    # propio código que calcula (ver bes/core/formulas.py), así no puede decir
    # una cosa y el programa hacer otra.
    formulas: list[dict] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    # Correlación con la que se calculó la pérdida de carga en el tubing:
    # "hazen_williams" (monofásica) o "poettmann_carpenter" (multifásica), según
    # la fracción de gas libre en la admisión frente al umbral de objetivos.
    friction_method: str = "hazen_williams"
    gas_fraction_threshold: float = 0.10
    # Housing / carcasas (poblado por bes.core.housing.optimize_housings)
    housing_size_stages: int = 0     # capacidad total instalada [etapas]
    dummy_stages: int = 0            # etapas ciegas para completar la carcasa
    n_housings: int = 1              # nº de carcasas/unidades (>1 = tándem)
    max_housing_pressure_psi: float = 0.0   # MaxP shut-in sobre la carcasa superior
    housing_pressure_limit_psi: float = 0.0 # límite de trabajo de la carcasa
    housing_pressure_ok: bool = True         # MaxP <= límite en TODAS las carcasas
    # Ficha por carcasa, de la admisión a la descarga: posición, etapas, código,
    # material, OD, etapas activas por debajo, presión calculada, límite y OK.
    housing_detail: list[dict] = field(default_factory=list)
    housing_rationale: str = ""      # justificación técnica de la combinación
    housing_pressure_verified: bool = False  # False = el catálogo no publica el límite
    # Verificación mecánica de la serie (bes.core.mechanical). Vacías cuando el
    # catálogo no tiene ficha de la serie: sin verificar, nunca aprobadas.
    shaft_check: dict = field(default_factory=dict)      # HP eje vs límite std/HR
    bearing_check: dict = field(default_factory=dict)    # etapas vs cojinete y BHT
    bearing_load_lbs: float = 0.0    # Carga TL = Ho × Pem × A_eje
    staging_ceiling: dict = field(default_factory=dict)  # tope por housing/eje/cojinete
    # Enfriamiento del motor (velocidad de fluido en el anular)
    fluid_velocity_ft_s: float = 0.0
    cooling_ok: bool = True
    # HP máximo de eje (fluido más pesado); el motor se dimensiona sobre este.
    # ``total_pump_hp`` es el HP operativo (SG de la mezcla).
    motor_hp_max: float = 0.0
    # Controlador de superficie (tablero fijo o VSD)
    controller_manufacturer: str = ""
    controller_model: str = ""
    controller_type: str = ""
    # Seal / protector (optional; populated by the electrical design)
    seal_manufacturer: str = ""
    seal_model: str = ""
    seal_type: str = ""
    seal_thrust_capacity_lbs: float = 0.0
    axial_thrust_lbs: float = 0.0
    # Gas handler / separator (optional; recommended only when free gas warrants)
    gas_handler_manufacturer: str = ""
    gas_handler_model: str = ""
    gas_handler_type: str = ""
    gas_handler_efficiency: float = 0.0
    # Downhole sensor (optional; recommended for monitoring)
    sensor_manufacturer: str = ""
    sensor_model: str = ""

    def __post_init__(self) -> None:
        if self.num_stages <= 0:
            raise ValueError(f"num_stages must be > 0, got {self.num_stages}")
        if self.pump_setting_depth <= 0:
            raise ValueError(f"pump_setting_depth must be > 0, got {self.pump_setting_depth}")
        if self.intake_pressure <= 0:
            raise ValueError(f"intake_pressure must be > 0, got {self.intake_pressure}")
        if self.total_head_required <= 0:
            raise ValueError(f"total_head_required must be > 0, got {self.total_head_required}")
        if not (0.0 <= self.pump_efficiency <= 1.0):
            raise ValueError(f"pump_efficiency must be in [0, 1], got {self.pump_efficiency}")
        if not (0.0 <= self.system_efficiency <= 1.0):
            raise ValueError(f"system_efficiency must be in [0, 1], got {self.system_efficiency}")
        if self.flow_rate_achieved <= 0:
            raise ValueError(f"flow_rate_achieved must be > 0, got {self.flow_rate_achieved}")
        if not (0.0 <= self.gip_fraction <= 1.0):
            raise ValueError(f"gip_fraction must be in [0, 1], got {self.gip_fraction}")
        if self.motor_hp <= 0:
            raise ValueError(f"motor_hp must be > 0, got {self.motor_hp}")
        if self.motor_voltage <= 0:
            raise ValueError(f"motor_voltage must be > 0, got {self.motor_voltage}")
        if self.transformer_kva <= 0:
            raise ValueError(f"transformer_kva must be > 0, got {self.transformer_kva}")
        if self.cable_awg <= 0:
            raise ValueError(f"cable_awg must be > 0, got {self.cable_awg}")
        if not self.pump_manufacturer.strip():
            raise ValueError("pump_manufacturer cannot be empty")
        if not self.motor_manufacturer.strip():
            raise ValueError("motor_manufacturer cannot be empty")
